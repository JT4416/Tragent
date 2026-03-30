"""
Paper broker: executes simulated fills using live Schwab quotes.
Maintains per-agent simulated account state in a JSON file.
Counts unique trading days; gates live trading after TRADING_DAYS_GATE days.
"""
import json
import time
from datetime import date
from pathlib import Path

TRADING_DAYS_GATE = 15
_SLIPPAGE_PCT = 0.001   # 0.1% simulated slippage per fill

_DEFAULT_STATE_DIR = Path(__file__).parent.parent.parent / "state"


class PaperBroker:
    """
    Drop-in replacement for SchwabClient during paper trading.
    - get_quote()       → delegates to real Schwab (live prices)
    - get_account_info() → returns simulated cash + positions
    - place_order()     → simulates fill at current price + slippage
    """

    def __init__(self, schwab_client, base_capital: float,
                 agent_id: str = "agent",
                 state_dir: Path = _DEFAULT_STATE_DIR):
        self._schwab = schwab_client
        self._agent_id = agent_id
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = state_dir / f"paper_{agent_id}.json"
        self._state = self._load_state(base_capital)

    # ── State persistence ──────────────────────────────────────────────────

    def _load_state(self, base_capital: float) -> dict:
        if self._state_file.exists():
            with open(self._state_file) as f:
                return json.load(f)
        return {
            "cash": base_capital,
            "positions": {},       # symbol → {quantity, entry_price}
            "trading_days": [],    # list of ISO date strings
        }

    def _save(self) -> None:
        with open(self._state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    def _record_trading_day(self) -> None:
        today = date.today().isoformat()
        if today not in self._state["trading_days"]:
            self._state["trading_days"].append(today)
            self._save()

    # ── Public interface (mirrors SchwabClient) ────────────────────────────

    def get_account_info(self) -> dict:
        self._record_trading_day()
        positions = [
            {"symbol": sym, "quantity": p["quantity"],
             "entry_price": p["entry_price"]}
            for sym, p in self._state["positions"].items()
        ]
        return {"cash": self._state["cash"], "positions": positions}

    def get_quote(self, symbol: str) -> dict:
        return self._schwab.get_quote(symbol)

    def place_order(self, symbol: str, action: str, quantity: int) -> dict:
        quote = self._schwab.get_quote(symbol)
        price = quote.get("lastPrice") or quote.get("mark") or 0.0
        fill_price = round(price * (1 + _SLIPPAGE_PCT), 2)

        if action == "buy":
            cost = fill_price * quantity
            self._state["cash"] = round(self._state["cash"] - cost, 2)
            if symbol in self._state["positions"]:
                self._state["positions"][symbol]["quantity"] += quantity
            else:
                self._state["positions"][symbol] = {
                    "quantity": quantity,
                    "entry_price": fill_price,
                }
        elif action == "sell":
            proceeds = fill_price * quantity
            self._state["cash"] = round(self._state["cash"] + proceeds, 2)
            self._state["positions"].pop(symbol, None)

        self._save()
        return {
            "orderId": f"paper_{self._agent_id}_{int(time.time())}",
            "fillPrice": fill_price,
            "status": "FILLED",
        }

    # ── Gate ───────────────────────────────────────────────────────────────

    def trading_days_completed(self) -> int:
        return len(self._state["trading_days"])

    def is_live_ready(self) -> bool:
        return self.trading_days_completed() >= TRADING_DAYS_GATE
