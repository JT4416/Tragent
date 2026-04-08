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
    "SDS",  # ProShares UltraShort S&P500 (2x inverse) — short-duration hold only (leveraged decay)
    "QID",  # ProShares UltraShort QQQ (2x inverse) — short-duration hold only (leveraged decay)
    "DOG",  # ProShares Short Dow30 (1x inverse)
    # User-specified watchlist additions
    "RKLB", "BPTRX", "DXYZ", "SATS", "JOBY", "ACHR", "FCUV", "SMX", "MLEC",
    "SPCE", "FUBO", "CLIR", "SIDU", "BVC", "NVTS", "INFQ",
    # 2026-04-07 — hot at the open: energy/defense (Iran deadline), catalysts
    "XOM", "CVX", "OXY", "BATL",   # oil/energy
    "LMT", "RTX", "NOC",           # defense
    "ORGO",                         # Phase 3 catalyst
    "AMC",                          # box office momentum
    "SKYQ",                         # +57% today
    "ADVB",                         # +50.5% today
    # 2026-04-07 midday — sub-$7 momentum + earnings plays
    "AIXI",                         # +98%, patent win vs Apple
    "CETX",                         # +58%, Navy defense contract
    "LNAI",                         # +42%, first revenue contract
    "KRUS",                         # earnings after close, high volatility
    "GBX",                          # earnings after close, big surprise history
    "LEVI",                         # earnings after close
    "AEHR",                         # earnings after close
    "MGRT",                         # +40% today
    # User shadow portfolio — 30-day monitoring (added 2026-04-08)
    "OWL", "CRWV", "BWXT", "ON", "TER", "LRCX", "MPWR", "KLAC", "PWR", "EXLS",
    "NRG", "ALAB", "CRSP", "KEYS", "PLTR", "WMB", "FSLY", "PRCT", "DMLP", "NN",
    "PHR", "NIQ", "ARM", "NET", "ASML", "SYM", "SNOW", "PATH", "TT", "GKOS",
    "LTH", "MRVL", "RXRX",
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
                 watchlist: list[str] = DEFAULT_WATCHLIST,
                 schwab_client=None,
                 schwab_feed=None):
        self._queues = agent_queues
        self._watchlist = watchlist
        self._schwab = schwab_client
        self._schwab_feed = schwab_feed
        self._tech = TechnicalAnalyzer()
        self._agg = SignalAggregator()
        self._news = NewsFeed()
        self._inst = InstitutionalFeed()
        self._yf = YFinanceClient()

    def fetch_and_dispatch(self) -> None:
        session = _get_session()
        if session == "closed":
            return

        # Technical signals + prices — reuse OHLCV, no extra network calls
        raw_signals = []
        prices = {}
        for symbol in self._watchlist:
            try:
                df = self._yf.fetch_ohlcv(symbol, period="1y")
                if not df.empty:
                    prices[symbol] = float(df["close"].iloc[-1])
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

        # Top market movers (Schwab real-time)
        movers = []
        scanner = {}
        if self._schwab is not None:
            try:
                movers = self._schwab.get_movers()
            except Exception:
                movers = []
            try:
                scanner = self._schwab.scan_market(top_n=10)
            except Exception:
                scanner = {}

        schwab_data = {}
        if self._schwab_feed is not None:
            try:
                schwab_data = self._schwab_feed.fetch()
            except Exception:
                pass

        packet = {
            "session": session,
            "movers": movers,
            "scanner": scanner,
            "prices": prices,
            "signals": ranked[:10],
            "news": [{"title": a["title"], "source": a.get("source", {}).get("name")}
                     for a in news[:10]],
            "institutional": inst_signals[:10],
        }
        if schwab_data:
            packet["schwab_data"] = schwab_data

        for q in self._queues:
            q.put(packet)

    def run(self, interval_seconds: int, stop_event) -> None:
        while not stop_event.is_set():
            try:
                self.fetch_and_dispatch()
            except Exception:
                pass
            # Feed every 4 min in first 30 min of session, then normal interval
            from zoneinfo import ZoneInfo
            et_now = datetime.now(ZoneInfo("America/New_York"))
            minutes_since_open = (et_now.hour - 9) * 60 + (et_now.minute - 30)
            if 0 <= minutes_since_open < 30:
                time.sleep(4 * 60)  # 4-min feed at open (ahead of 5-min agent cycle)
            else:
                time.sleep(interval_seconds)
