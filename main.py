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

from agents.agent import Agent, AgentConfig
from competition.scorer import CompetitionScorer
from competition.reporter import DailyReporter
from competition.eliminator import RoundEliminator
from core.data.schwab_client import SchwabClient
from core.decision.claude_client import ClaudeClient
from config import settings


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
    while not stop_event.is_set():
        sess = _session()
        if sess == "closed":
            time.sleep(60)
            continue
        agent.run_cycle()
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
                for pos in local_positions:
                    if pos.symbol not in broker_symbols:
                        store.remove_position(pos.symbol)
                        sys_log.log({"event": "removed_stale_position",
                                     "agent": agent_id, "symbol": pos.symbol})
        sys_log.log({"event": "reconciliation_complete"})
    except Exception as e:
        sys_log.log({"event": "reconciliation_failed", "error": str(e)})


def main():
    schwab = SchwabClient()
    claude_a = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_a")
    claude_b = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_b")

    base_capital = settings.get("competition", "base_capital")

    queue_a: queue.Queue = queue.Queue()
    queue_b: queue.Queue = queue.Queue()

    from core.state.persistence import StateStore
    from core.data.market_feed import MarketFeed
    store_a = StateStore("agent_a")
    store_b = StateStore("agent_b")

    # Startup reconciliation — always before agents start
    reconcile(schwab, store_a, store_b)

    agent_a = Agent(AgentConfig("agent_a", "regular", base_capital),
                    claude_a, schwab, data_queue=queue_a)
    agent_b = Agent(AgentConfig("agent_b", "regular", base_capital),
                    claude_b, schwab, data_queue=queue_b)

    scorer_a = CompetitionScorer("agent_a", base_capital)
    scorer_b = CompetitionScorer("agent_b", base_capital)
    reporter = DailyReporter(scorer_a, scorer_b)

    schedule.every().day.at("16:00").do(reporter.generate)
    if settings.get("auto_commit", "enabled"):
        schedule.every().day.at("16:01").do(reporter.auto_commit)

    stop = threading.Event()
    regular_interval = settings.get("trading", "cycle_interval_regular_min")

    feed = MarketFeed([queue_a, queue_b])
    feed_thread = threading.Thread(
        target=feed.run,
        args=(regular_interval * 60, stop),
        daemon=True)

    thread_a = threading.Thread(
        target=run_agent, args=(agent_a, regular_interval, stop), daemon=True)
    thread_b = threading.Thread(
        target=run_agent, args=(agent_b, regular_interval, stop), daemon=True)

    print("Starting Tragent — Agent A and Agent B")
    feed_thread.start()
    thread_a.start()
    thread_b.start()

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        stop.set()
        feed_thread.join(timeout=5)
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)


if __name__ == "__main__":
    main()
