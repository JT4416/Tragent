import queue
import time
from dataclasses import dataclass
from datetime import datetime, date, timezone
from pathlib import Path

from agents.expertise_manager import ExpertiseManager
from agents.self_improve import SelfImproveOrchestrator
from competition.scorer import CompetitionScorer, TradeRecord
from core.decision.prompt_builder import build_decision_prompt, build_homework_prompt
from core.execution.risk_gate import RiskGate, RiskConfig
from core.risk.position_tracker import PositionTracker
from core.state.persistence import StateStore, Position
from core.logger import get_logger
from config import settings


@dataclass
class AgentConfig:
    agent_id: str
    session: str
    base_capital: float


class Agent:
    def __init__(self, config: AgentConfig, claude_client, schwab_client,
                 data_queue: queue.Queue,
                 expertise_dir: Path | None = None,
                 db_dir: Path | None = None,
                 log_dir: Path | None = None,
                 peer_exchange=None,
                 scorer: CompetitionScorer | None = None,
                 paper_mode: bool = False):
        self._cfg = config
        self._claude = claude_client
        self._schwab = schwab_client
        self._queue = data_queue
        self._exchange = peer_exchange
        self._scorer = scorer
        self.last_trade_time: datetime | None = None
        self._mgr = ExpertiseManager(config.agent_id, expertise_dir)
        self._store = StateStore(config.agent_id, db_dir) if db_dir \
            else StateStore(config.agent_id)
        self._improve = SelfImproveOrchestrator(self._mgr, claude_client)
        self._tracker = PositionTracker(
            trailing_pct=settings.get("risk", "trailing_stop_pct"),
            agent_id=config.agent_id,
            store=self._store,
        )
        self._logger = get_logger(config.agent_id, "trades", log_dir) \
            if log_dir else get_logger(config.agent_id, "trades")
        threshold = settings.get("risk", "confidence_threshold_paper") \
            if paper_mode else settings.get("risk", "confidence_threshold_regular")
        self._risk = RiskGate(RiskConfig(
            max_position_size_pct=settings.get("risk", "max_position_size_pct"),
            daily_loss_limit_pct=settings.get("risk", "daily_loss_limit_pct"),
            max_concurrent_positions=settings.get("risk", "max_concurrent_positions"),
            confidence_threshold_regular=threshold,
            open_blackout_minutes=settings.get("risk", "open_blackout_minutes"),
        ))

    def run_cycle(self) -> None:
        try:
            market_data = self._queue.get(timeout=120)
        except queue.Empty:
            return

        prices = market_data.get("prices", {})

        # Drain and process peer insights BEFORE loading expertise
        if self._exchange:
            for insight in self._exchange.drain(self._cfg.agent_id):
                self._improve.run_peer_learning(insight)

        # REUSE: load all expertise (after peer learning so files are current)
        expertise = self._mgr.load_all()

        # Check stops and close any triggered positions
        triggered = self._tracker.check_stops(prices)
        for symbol, info in triggered.items():
            self.close_position(symbol, info["trigger_price"], info["reason"])

        # Advance trailing stops
        self._tracker.update_stops(prices)

        evolved = expertise.get("trade", {}).get("evolved_parameters", {})
        session = market_data.get("session", "regular")

        account = self._schwab.get_account_info()
        cash = account.get("cash", self._cfg.base_capital)
        open_positions = self._store.get_positions()
        round_pnl = self._store.get_round_pnl()
        daily_pnl_pct = (round_pnl / self._cfg.base_capital) * 100

        # Load yesterday's homework prep if available
        prep_path = Path(f"agents/{self._cfg.agent_id}/daily_prep.yaml")
        daily_prep = {}
        if prep_path.exists():
            import yaml as _yaml
            try:
                with open(prep_path) as f:
                    daily_prep = _yaml.safe_load(f) or {}
            except Exception:
                pass

        prompt = build_decision_prompt(
            session=session,
            expertise=expertise,
            daily_prep=daily_prep,
            signals=market_data.get("signals", []),
            news=market_data.get("news", []),
            institutional=market_data.get("institutional", []),
            open_positions=[{"symbol": p.symbol, "direction": p.direction,
                              "entry": p.entry_price} for p in open_positions],
            cash=cash,
            daily_pnl=round_pnl,
            daily_pnl_pct=daily_pnl_pct,
            daily_loss_remaining=(self._cfg.base_capital *
                                   settings.get("risk", "daily_loss_limit_pct") / 100
                                   + round_pnl),
            movers=market_data.get("movers", []),
        )

        decision = self._claude.decide("", prompt)

        if decision.action == "hold":
            self._logger.log({"event": "hold", "reason": decision.skip_reason,
                               "confidence": decision.confidence})
            return

        if decision.action == "sell":
            if decision.symbol:
                quote = self._schwab.get_quote(decision.symbol)
                price = quote.get("lastPrice") or quote.get("mark") or 0.0
                if price > 0:
                    self.close_position(decision.symbol, price,
                                        reason="agent_decision")
                else:
                    self._logger.log({
                        "event": "sell_skipped",
                        "reason": "no_quote",
                        "symbol": decision.symbol,
                    })
            return

        risk_result = self._risk.check(
            action=decision.action,
            confidence=decision.confidence,
            position_size_pct=decision.position_size_pct,
            session=session,
            open_positions=len(open_positions),
            portfolio_value=cash,
            daily_pnl_pct=daily_pnl_pct,
            current_time=datetime.now(timezone.utc),
        )

        if not risk_result.approved:
            self._logger.log({"event": "risk_blocked", "reason": risk_result.reason,
                               "action": decision.action, "symbol": decision.symbol})
            return

        self._execute(decision, cash, evolved)

    def _execute(self, decision, cash: float, evolved: dict) -> None:
        size_pct = min(decision.position_size_pct,
                       evolved.get("max_position_size_pct", 5.0))

        quote = self._schwab.get_quote(decision.symbol)
        price = quote.get("lastPrice") or quote.get("mark") or 1.0
        quantity = max(1, int((cash * size_pct / 100) / price))

        if decision.trade_type == "momentum_ride":
            stop_pct = 2.5
            trailing_pct = 2.5
        else:
            stop_pct = evolved.get("stop_loss_pct", 5.0)
            trailing_pct = evolved.get("trailing_stop_pct", 5.0)

        # Determine direction from action
        if decision.action == "buy_short":
            direction = "short"
            action = "buy_short"
            stop_price = round(price * (1 + stop_pct / 100), 2)
            trailing_stop = round(price * (1 + trailing_pct / 100), 2)
        else:
            direction = "long"
            action = "buy"
            stop_price = round(price * (1 - stop_pct / 100), 2)
            trailing_stop = round(price * (1 - trailing_pct / 100), 2)

        self._schwab.place_order(
            symbol=decision.symbol,
            action=action,
            quantity=quantity,
        )

        self.last_trade_time = datetime.now(timezone.utc)
        self._store.save_position(
            Position(
                symbol=decision.symbol,
                direction=direction,
                entry_price=price,
                stop_loss=stop_price,
                trailing_stop=trailing_stop,
                quantity=quantity,
                entry_time=datetime.now(timezone.utc).isoformat(),
            )
        )

        trade_record = {
            "trade_id": f"t_{self._cfg.agent_id}_{int(time.time())}",
            "symbol": decision.symbol,
            "direction": direction,
            "entry": price,
            "exit": None,
            "pnl_pct": None,
            "signals_used": decision.signals_used,
            "outcome": None,
            "claude_confidence": decision.confidence,
            "bull_case": decision.bull_case,
            "bear_case": decision.bear_case,
        }

        self._logger.log({
            "event": "trade_placed", **trade_record,
            "reasoning": decision.reasoning,
        })

        self._improve.run(
            trade_record=trade_record,
            original_reasoning=decision.reasoning,
            outcome="open",
            pnl_pct=0.0,
            duration="0m",
        )

        if self._exchange:
            self._exchange.publish(self._cfg.agent_id, {
                "from_agent": self._cfg.agent_id,
                "event": "entry",
                "trade_record": trade_record,
                "reasoning": decision.reasoning,
                "bull_case": decision.bull_case,
                "bear_case": decision.bear_case,
                "outcome": "open",
                "pnl_pct": 0.0,
                "duration": "0m",
            })

    def close_position(self, symbol: str, exit_price: float,
                       reason: str = "stop") -> None:
        """Close an open position, calculate real P&L, trigger learn loop."""
        pos = self._store.get_position(symbol)
        if pos is None:
            return

        if pos.direction == "short":
            # Short: profit when price goes down
            pnl = round((pos.entry_price - exit_price) * pos.quantity, 2)
            pnl_pct = round(
                (pos.entry_price - exit_price) / pos.entry_price * 100, 2
            ) if pos.entry_price else 0.0
        else:
            pnl = round((exit_price - pos.entry_price) * pos.quantity, 2)
            pnl_pct = round(
                (exit_price - pos.entry_price) / pos.entry_price * 100, 2
            ) if pos.entry_price else 0.0

        if pos.entry_time:
            entry_dt = datetime.fromisoformat(pos.entry_time)
            secs = int((datetime.now(timezone.utc) - entry_dt).total_seconds())
            hours, rem = divmod(secs, 3600)
            mins = rem // 60
            duration = f"{hours}h{mins}m" if hours else f"{mins}m"
        else:
            duration = "unknown"

        # Remove from store FIRST to prevent double-sell if order raises
        self._store.update_round_pnl(self._store.get_round_pnl() + pnl)
        self._store.remove_position(symbol)

        self.last_trade_time = datetime.now(timezone.utc)
        close_action = "sell_to_close" if pos.direction == "short" else "sell"
        self._schwab.place_order(
            symbol=symbol, action=close_action, quantity=pos.quantity)

        self._logger.log({
            "event": "position_closed", "symbol": symbol, "reason": reason,
            "entry": pos.entry_price, "exit": exit_price,
            "pnl": pnl, "pnl_pct": pnl_pct, "duration": duration,
        })

        trade_record = {
            "trade_id": f"close_{self._cfg.agent_id}_{int(time.time())}",
            "symbol": symbol, "direction": pos.direction,
            "entry": pos.entry_price, "exit": exit_price,
            "pnl_pct": pnl_pct, "signals_used": [],
            "outcome": "win" if pnl > 0 else "loss",
            "claude_confidence": None,
            "bull_case": "", "bear_case": "",
        }
        self._improve.run(
            trade_record=trade_record,
            original_reasoning=f"Position closed: {reason}",
            outcome="win" if pnl > 0 else "loss",
            pnl_pct=pnl_pct,
            duration=duration,
        )

        if self._scorer:
            self._scorer.record_trade(TradeRecord(
                date=date.today(),
                symbol=symbol,
                direction=pos.direction,
                entry=pos.entry_price,
                exit=exit_price,
                quantity=pos.quantity,
                pnl=pnl,
                pnl_pct=pnl_pct,
            ))

        if self._exchange:
            self._exchange.publish(self._cfg.agent_id, {
                "from_agent": self._cfg.agent_id,
                "event": "close",
                "trade_record": trade_record,
                "reasoning": f"Position closed: {reason}",
                "bull_case": "", "bear_case": "",
                "outcome": "win" if pnl > 0 else "loss",
                "pnl_pct": pnl_pct,
                "duration": duration,
            })

    def run_homework(self, market_data: dict, today_decisions: list[dict],
                     watchlist: list[str]) -> None:
        """Post-market homework: analyze today, prepare for tomorrow's open."""
        import yaml as _yaml
        expertise = self._mgr.load_all()
        open_positions = [{"symbol": p.symbol, "direction": p.direction,
                           "entry": p.entry_price}
                          for p in self._store.get_positions()]

        prompt = build_homework_prompt(
            signals=market_data.get("signals", []),
            news=market_data.get("news", []),
            institutional=market_data.get("institutional", []),
            movers=market_data.get("movers", []),
            expertise=expertise,
            today_decisions=today_decisions,
            open_positions=open_positions,
            watchlist=watchlist,
        )

        response = self._claude.self_improve(prompt)

        # Parse and save the daily prep
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("yaml"):
                text = text[4:]
        try:
            prep = _yaml.safe_load(text.strip())
        except Exception:
            prep = {"raw": text[:2000]}

        prep_path = Path(f"agents/{self._cfg.agent_id}/daily_prep.yaml")
        prep_path.parent.mkdir(parents=True, exist_ok=True)
        with open(prep_path, "w") as f:
            _yaml.dump(prep, f, default_flow_style=False, sort_keys=False)

        self._logger.log({
            "event": "homework_complete",
            "top_picks": [p.get("symbol") for p in prep.get("top_picks", [])],
            "market_bias": prep.get("market_outlook", {}).get("bias", "unknown"),
        })
