"""
Tragent — main entry point.
Starts Agent A and Agent B as concurrent threads.

Usage:
    python main.py

Setup (first time):
    python -m core.data.schwab_client auth
"""
import queue
import threading
import time
import schedule
from datetime import datetime, timezone
from pathlib import Path

from agents.agent import Agent, AgentConfig
from competition.scorer import CompetitionScorer
from competition.reporter import DailyReporter
from competition.eliminator import RoundEliminator
from core.data.schwab_client import SchwabClient
from core.decision.claude_client import ClaudeClient
from core.execution.paper_broker import PaperBroker
from config import settings
from core.kill_switch import KillSwitch
from core.risk.stop_enforcer import StopEnforcer
from core.monitor.alerter import Alerter
from agents.peer_exchange import PeerExchange
from core.state.persistence import StateStore
from core.data.market_feed import MarketFeed, DEFAULT_WATCHLIST
from core.data.schwab_feed import SchwabFeed


def _session() -> str:
    from zoneinfo import ZoneInfo
    from datetime import datetime
    et = datetime.now(ZoneInfo("America/New_York"))
    hour = et.hour + et.minute / 60
    if 4.0 <= hour < 9.5:
        return "pre_market"
    if 9.5 <= hour < 16.0:
        return "regular"
    if 16.0 <= hour < 20.0:
        return "post_market"
    return "closed"


def run_agent(agent: Agent, interval_minutes: int, stop_event: threading.Event):
    import logging
    _log = logging.getLogger(__name__)
    while not stop_event.is_set():
        sess = _session()
        if sess == "closed":
            time.sleep(60)
            continue
        try:
            agent.run_cycle()
        except Exception:
            _log.exception("run_cycle raised for %s — skipping cycle",
                           agent._cfg.agent_id)
        time.sleep(interval_minutes * 60)


def reconcile(schwab: SchwabClient, store_a, store_b) -> None:
    """On startup, reconcile broker positions against local SQLite state."""
    from core.logger import get_logger
    sys_log = get_logger("system", "system")
    try:
        acct = schwab.get_account_info()
        broker_symbols = {p["symbol"] for p in acct.get("positions", [])}

        for store, agent_id in [(store_a, "agent_a"), (store_b, "agent_b")]:
            local_positions = store.get_positions()
            local_symbols = {p.symbol for p in local_positions}
            discrepancies = local_symbols.symmetric_difference(broker_symbols)
            if discrepancies:
                sys_log.log({"event": "reconciliation_discrepancy",
                             "agent": agent_id, "symbols": list(discrepancies)})
                # Remove local positions that no longer exist at broker
                for pos in local_positions:
                    if pos.symbol not in broker_symbols:
                        store.remove_position(pos.symbol)
                        sys_log.log({"event": "removed_stale_position",
                                     "agent": agent_id, "symbol": pos.symbol})
                # Log broker positions absent from local state (manual review needed)
                for symbol in broker_symbols - local_symbols:
                    sys_log.log({"event": "unknown_broker_position",
                                 "agent": agent_id, "symbol": symbol,
                                 "note": "broker holds position with no local state — review manually"})
        sys_log.log({"event": "reconciliation_complete"})
    except Exception as e:
        sys_log.log({"event": "reconciliation_failed", "error": str(e)})


def main():
    schwab = SchwabClient()
    claude_a = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_a", log_dir=Path("logs"))
    claude_b = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_b", log_dir=Path("logs"))

    base_capital = settings.get("competition", "base_capital")

    queue_a: queue.Queue = queue.Queue()
    queue_b: queue.Queue = queue.Queue()

    store_a = StateStore("agent_a")
    store_b = StateStore("agent_b")

    # Startup reconciliation — always before agents start
    reconcile(schwab, store_a, store_b)

    paper_mode = settings.get("paper_trading", "enabled")
    if paper_mode:
        state_dir = Path("state")
        broker_a = PaperBroker(schwab, base_capital,
                                agent_id="agent_a", state_dir=state_dir)
        broker_b = PaperBroker(schwab, base_capital,
                                agent_id="agent_b", state_dir=state_dir)
        days = broker_a.trading_days_completed()
        gate = settings.get("paper_trading", "trading_days_gate")
        if not broker_a.is_live_ready():
            print(f"PAPER TRADING MODE — {days}/{gate} trading days completed "
                  f"before live capital is used.")
        else:
            print(f"Paper gate cleared ({days} days). "
                  f"Set paper_trading.enabled=false to trade live capital.")
    else:
        broker_a = schwab
        broker_b = schwab

    exchange = PeerExchange()
    exchange.register("agent_a")
    exchange.register("agent_b")

    scorer_a = CompetitionScorer("agent_a", base_capital)
    scorer_b = CompetitionScorer("agent_b", base_capital)

    agent_a = Agent(AgentConfig("agent_a", "regular", base_capital),
                    claude_a, broker_a, data_queue=queue_a,
                    peer_exchange=exchange, scorer=scorer_a)
    agent_b = Agent(AgentConfig("agent_b", "regular", base_capital),
                    claude_b, broker_b, data_queue=queue_b,
                    peer_exchange=exchange, scorer=scorer_b)

    reporter = DailyReporter(scorer_a, scorer_b)

    schedule.every().day.at("16:00").do(reporter.generate)
    if settings.get("auto_commit", "enabled"):
        schedule.every().day.at("16:01").do(reporter.auto_commit)

    stop = threading.Event()
    kill_switch = KillSwitch(stop)
    alerter = Alerter()
    monitoring_enabled = settings.get("monitoring", "enabled")
    drawdown_threshold = settings.get("monitoring", "drawdown_alert_pct")
    idle_threshold = settings.get("monitoring", "idle_agent_minutes")

    enforcer = StopEnforcer(
        agents=[agent_a, agent_b],
        broker=schwab,   # only needs get_quote(); same price feed for both agents
        interval_seconds=30,
    )
    enforcer_thread = threading.Thread(
        target=enforcer.run, args=(stop,), daemon=True)
    kill_switch.arm()
    regular_interval = settings.get("trading", "cycle_interval_regular_min")

    schwab_feed = SchwabFeed(schwab, DEFAULT_WATCHLIST)
    feed = MarketFeed([queue_a, queue_b], schwab_client=schwab,
                      schwab_feed=schwab_feed)
    feed_thread = threading.Thread(
        target=feed.run,
        args=(regular_interval * 60, stop),
        daemon=True)

    thread_a = threading.Thread(
        target=run_agent, args=(agent_a, regular_interval, stop), daemon=True)
    thread_b = threading.Thread(
        target=run_agent, args=(agent_b, regular_interval, stop), daemon=True)

    print("Starting Tragent — Agent A and Agent B")
    print("To kill: create a KILL file in project root, or press Ctrl+C")
    feed_thread.start()
    enforcer_thread.start()
    thread_a.start()
    thread_b.start()

    while not stop.is_set():
        schedule.run_pending()
        kill_switch.poll()

        if monitoring_enabled:
            pnl_a = store_a.get_round_pnl()
            pnl_b = store_b.get_round_pnl()
            pnl_a_pct = (pnl_a / base_capital) * 100
            pnl_b_pct = (pnl_b / base_capital) * 100
            alerter.check_drawdown("agent_a", pnl_a_pct, drawdown_threshold)
            alerter.check_drawdown("agent_b", pnl_b_pct, drawdown_threshold)

            alerter.check_api_errors(
                "claude_a", claude_a.api_error_count,
                threshold=settings.get("monitoring", "api_error_threshold"),
            )
            alerter.check_api_errors(
                "claude_b", claude_b.api_error_count,
                threshold=settings.get("monitoring", "api_error_threshold"),
            )

        time.sleep(60)   # alert check cadence: once per minute

    print("Shutdown signal received — waiting for threads to finish...")
    feed_thread.join(timeout=5)
    enforcer_thread.join(timeout=5)
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)
    print("Tragent stopped.")


if __name__ == "__main__":
    main()
