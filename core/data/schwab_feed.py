"""
SchwabFeed: enriches MarketFeed packets with live Schwab quotes and
cached fundamental data. Quotes fetched every cycle (one bulk call).
Fundamentals cached per half-day slot: "open" (09:30–12:00 ET) and
"midday" (12:00–16:00 ET).
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

_log = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")


class SchwabFeed:
    def __init__(self, schwab, watchlist: list[str]):
        self._schwab = schwab
        self._watchlist = watchlist
        self._fundamentals: dict[str, dict] = {}
        self._fund_slot: str | None = None

    def _current_slot(self) -> str | None:
        now = datetime.now(_ET)
        hour = now.hour + now.minute / 60
        if 9.5 <= hour < 12.0:
            return "open"
        if 12.0 <= hour < 16.0:
            return "midday"
        return None

    def _refresh_fundamentals(self) -> None:
        for symbol in self._watchlist:
            try:
                raw = self._schwab.get_instrument_fundamental(symbol)
                fund = raw.get(symbol, {}).get("fundamental", {})
                self._fundamentals[symbol] = {
                    "pe":         fund.get("peRatio"),
                    "eps":        fund.get("eps"),
                    "market_cap": fund.get("marketCap"),
                    "52wk_high":  fund.get("high52"),
                    "52wk_low":   fund.get("low52"),
                    "div_yield":  fund.get("dividendYield"),
                }
            except Exception:
                _log.warning("fundamental fetch failed for %s — skipping", symbol)

    def fetch(self) -> dict[str, dict]:
        slot = self._current_slot()
        if slot != self._fund_slot:
            self._refresh_fundamentals()
            self._fund_slot = slot

        try:
            raw_quotes = self._schwab.get_quotes_bulk(self._watchlist)
        except Exception:
            _log.warning("get_quotes_bulk failed — skipping schwab_data this cycle")
            return {}

        result: dict[str, dict] = {}
        for symbol in self._watchlist:
            q = raw_quotes.get(symbol, {}).get("quote", {})
            if not q:
                continue
            entry: dict = {
                "last":    q.get("lastPrice"),
                "volume":  q.get("totalVolume"),
                "bid":     q.get("bidPrice"),
                "ask":     q.get("askPrice"),
                "net_pct": q.get("netPercentChangeInDouble"),
            }
            if symbol in self._fundamentals:
                entry.update(self._fundamentals[symbol])
            result[symbol] = entry

        return result
