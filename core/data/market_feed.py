"""
Market feed: fetches live signals for both agents and puts packets into queues.
Runs as its own thread. Calls TechnicalAnalyzer + SignalAggregator + NewsFeed
+ InstitutionalFeed each cycle, then puts a data packet into each agent queue.
"""
import queue
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.analysis.technical import TechnicalAnalyzer
from core.analysis.signal_aggregator import SignalAggregator
from core.data.news_feed import NewsFeed
from core.data.institutional_feed import InstitutionalFeed
from core.data.yfinance_client import YFinanceClient

_ET = ZoneInfo("America/New_York")

# Watchlist — expand over time; agents learn which ones produce signals
DEFAULT_WATCHLIST = [
    # Core large caps
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "AMD", "SPY", "QQQ",
    # Inverse ETFs — long-only bearish exposure (no short selling)
    "SH",   # ProShares Short S&P500 (1x inverse)
    "SDS",  # ProShares UltraShort S&P500 (2x inverse) — short-hold only
    "QID",  # ProShares UltraShort QQQ (2x inverse) — short-hold only
    "DOG",  # ProShares Short Dow30 (1x inverse)
]


def _get_session() -> str:
    et = datetime.now(_ET)
    hour = et.hour + et.minute / 60
    if 4.0 <= hour < 9.5:
        return "pre_market"
    if 9.5 <= hour < 16.0:
        return "regular"
    if 16.0 <= hour < 20.0:
        return "post_market"
    return "closed"


class MarketFeed:
    def __init__(self, agent_queues: list[queue.Queue],
                 watchlist: list[str] = DEFAULT_WATCHLIST):
        self._queues = agent_queues
        self._watchlist = watchlist
        self._tech = TechnicalAnalyzer()
        self._agg = SignalAggregator()
        self._news = NewsFeed()
        self._inst = InstitutionalFeed()
        self._yf = YFinanceClient()

    def fetch_and_dispatch(self) -> None:
        session = _get_session()
        if session == "closed":
            return

        # Technical signals
        raw_signals = []
        for symbol in self._watchlist:
            try:
                df = self._yf.fetch_ohlcv(symbol, period="3mo")
                raw_signals.extend(self._tech.analyze(df, symbol))
            except Exception:
                continue
        ranked = self._agg.rank(raw_signals)

        # News (broad market)
        try:
            news = self._news.fetch("stock market earnings breakout", page_size=20)
        except Exception:
            news = []

        # Institutional (top movers only — avoid rate limit)
        inst_signals = []
        for symbol in self._watchlist[:3]:  # limit API calls on free tier
            try:
                inst_signals.extend(self._inst.fetch_insider_trades(symbol)[:2])
            except Exception:
                continue

        packet = {
            "session": session,
            "signals": ranked[:10],   # top 10 breakout candidates
            "news": [{"title": a["title"], "source": a.get("source", {}).get("name")}
                     for a in news[:10]],
            "institutional": inst_signals[:10],
        }

        for q in self._queues:
            q.put(packet)

    def run(self, interval_seconds: int, stop_event) -> None:
        while not stop_event.is_set():
            try:
                self.fetch_and_dispatch()
            except Exception:
                pass
            time.sleep(interval_seconds)
