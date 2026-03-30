"""
Stop enforcement loop: polls all open positions every interval_seconds,
checks current price against stop_loss and trailing_stop, and calls
agent.close_position() when a stop is triggered.

Runs as a daemon thread in main.py.
"""
import threading
import time


class StopEnforcer:
    def __init__(self, agents: list, broker, interval_seconds: int = 30):
        self._agents = agents
        self._broker = broker
        self._interval = interval_seconds

    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self._check_all()
            except Exception:
                pass  # log externally if needed; don't crash the thread
            time.sleep(self._interval)

    def _check_all(self) -> None:
        for agent in self._agents:
            for pos in agent._store.get_positions():
                try:
                    quote = self._broker.get_quote(pos.symbol)
                    price = quote.get("lastPrice") or quote.get("mark") or 0.0
                    if price <= 0:
                        continue
                    reason = self._stop_reason(pos, price)
                    if reason:
                        agent.close_position(pos.symbol, price, reason=reason)
                except Exception:
                    continue

    @staticmethod
    def _stop_reason(pos, price: float) -> str | None:
        if price <= pos.stop_loss:
            return "stop_loss"
        if price <= pos.trailing_stop:
            return "trailing_stop"
        return None
