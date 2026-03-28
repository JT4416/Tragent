from pathlib import Path
from core.state.persistence import StateStore


class PositionTracker:
    def __init__(self, trailing_pct: float, agent_id: str,
                 db_dir: Path | None = None):
        self._trailing_pct = trailing_pct
        self.store = StateStore(agent_id, db_dir) if db_dir \
            else StateStore(agent_id)

    def update_stops(self, prices: dict[str, float]) -> dict:
        """Advance trailing stops as prices move in favour. Returns updated levels."""
        updates = {}
        for pos in self.store.get_positions():
            price = prices.get(pos.symbol)
            if price is None:
                continue
            if pos.direction == "long":
                new_trail = round(price * (1 - self._trailing_pct / 100), 2)
                if new_trail > pos.trailing_stop:
                    pos.trailing_stop = new_trail
                    self.store.save_position(pos)
                    updates[pos.symbol] = {"new_trailing_stop": new_trail}
            else:  # short
                new_trail = round(price * (1 + self._trailing_pct / 100), 2)
                if new_trail < pos.trailing_stop:
                    pos.trailing_stop = new_trail
                    self.store.save_position(pos)
                    updates[pos.symbol] = {"new_trailing_stop": new_trail}
        return updates

    def check_stops(self, prices: dict[str, float]) -> dict:
        """Return positions where stop has been triggered."""
        triggered = {}
        for pos in self.store.get_positions():
            price = prices.get(pos.symbol)
            if price is None:
                continue
            if pos.direction == "long":
                if price <= pos.stop_loss:
                    triggered[pos.symbol] = {"reason": "stop_loss",
                                              "trigger_price": pos.stop_loss}
                elif price <= pos.trailing_stop:
                    triggered[pos.symbol] = {"reason": "trailing_stop",
                                              "trigger_price": pos.trailing_stop}
            else:  # short
                if price >= pos.stop_loss:
                    triggered[pos.symbol] = {"reason": "stop_loss",
                                              "trigger_price": pos.stop_loss}
                elif price >= pos.trailing_stop:
                    triggered[pos.symbol] = {"reason": "trailing_stop",
                                              "trigger_price": pos.trailing_stop}
        return triggered
