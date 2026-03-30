import queue
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agents.expertise_manager import ExpertiseManager
from agents.self_improve import SelfImproveOrchestrator
from core.decision.prompt_builder import build_decision_prompt
from core.execution.risk_gate import RiskGate, RiskConfig
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
                 log_dir: Path | None = None):
        self._cfg = config
        self._claude = claude_client
        self._schwab = schwab_client
        self._queue = data_queue
        self._mgr = ExpertiseManager(config.agent_id, expertise_dir)
        self._store = StateStore(config.agent_id, db_dir) if db_dir \
            else StateStore(config.agent_id)
        self._improve = SelfImproveOrchestrator(self._mgr, claude_client)
        self._logger = get_logger(config.agent_id, "trades", log_dir) \
            if log_dir else get_logger(config.agent_id, "trades")
        self._risk = RiskGate(RiskConfig(
            max_position_size_pct=settings.get("risk", "max_position_size_pct"),
            daily_loss_limit_pct=settings.get("risk", "daily_loss_limit_pct"),
            max_concurrent_positions=settings.get("risk", "max_concurrent_positions"),
            confidence_threshold_regular=settings.get(
                "risk", "confidence_threshold_regular"),
            open_blackout_minutes=settings.get("risk", "open_blackout_minutes"),
        ))

    # --- REUSE → ACT ---
    def run_cycle(self) -> None:
        try:
            market_data = self._queue.get_nowait()
        except queue.Empty:
            return

        # REUSE: load all expertise
        expertise = self._mgr.load_all()

        # Build evolved risk params from trade expertise
        evolved = expertise.get("trade", {}).get("evolved_parameters", {})
        session = market_data.get("session", "regular")

        # Gather portfolio state from Schwab
        account = self._schwab.get_account_info()
        cash = account.get("cash", self._cfg.base_capital)
        open_positions = self._store.get_positions()
        round_pnl = self._store.get_round_pnl()
        daily_pnl_pct = (round_pnl / self._cfg.base_capital) * 100

        prompt = build_decision_prompt(
            session=session,
            expertise=expertise,
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
        )

        decision = self._claude.decide("", prompt)

        if decision.action == "hold":
            self._logger.log({"event": "hold", "reason": decision.skip_reason,
                               "confidence": decision.confidence})
            return

        # ACT: risk gate
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

        # Get real-time quote for accurate position sizing
        quote = self._schwab.get_quote(decision.symbol)
        price = quote.get("lastPrice") or quote.get("mark") or 1.0
        quantity = max(1, int((cash * size_pct / 100) / price))

        stop_pct = evolved.get("stop_loss_pct", 2.0)
        trailing_pct = evolved.get("trailing_stop_pct", 1.5)
        stop_price = round(price * (1 - stop_pct / 100), 2)
        direction = "long"

        order = self._schwab.place_order(
            symbol=decision.symbol,
            action=decision.action,
            quantity=quantity,
        )

        # Persist position with broker-side stop levels
        self._store.save_position(
            Position(
                symbol=decision.symbol,
                direction=direction,
                entry_price=price,
                stop_loss=stop_price,
                trailing_stop=round(price * (1 - trailing_pct / 100), 2),
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
        }

        self._logger.log({
            "event": "trade_placed", **trade_record,
            "reasoning": decision.reasoning,
        })

        # LEARN: trigger self-improve immediately after placing trade
        self._improve.run(
            trade_record=trade_record,
            original_reasoning=decision.reasoning,
            outcome="open",
            pnl_pct=0.0,
            duration="0m",
        )
