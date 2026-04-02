# tests/core/data/test_market_feed.py
import queue
from unittest.mock import patch, MagicMock
from core.data.market_feed import MarketFeed

def test_puts_packet_into_all_queues():
    q1, q2 = queue.Queue(), queue.Queue()
    feed = MarketFeed([q1, q2], watchlist=["AAPL"])

    mock_df = MagicMock()
    mock_df.__len__ = lambda s: 60

    with patch.object(feed._yf, "fetch_ohlcv", return_value=mock_df), \
         patch.object(feed._tech, "analyze", return_value=[]), \
         patch.object(feed._news, "fetch", return_value=[]), \
         patch.object(feed._inst, "fetch_insider_trades", return_value=[]), \
         patch("core.data.market_feed._get_session", return_value="regular"):
        feed.fetch_and_dispatch()

    assert not q1.empty()
    assert not q2.empty()
    pkt = q1.get_nowait()
    assert "signals" in pkt
    assert "movers" in pkt
    assert pkt["session"] == "regular"

def test_packet_includes_movers():
    q = queue.Queue()
    mock_schwab = MagicMock()
    mock_schwab.get_movers.return_value = [
        {"symbol": "NVDA", "description": "NVIDIA CORP",
         "lastPrice": 175.58, "netChange": 8.06,
         "netPercentChange": 4.81, "volume": 121693985},
    ]
    feed = MarketFeed([q], watchlist=["AAPL"], schwab_client=mock_schwab)

    mock_df = MagicMock()
    mock_df.__len__ = lambda s: 60

    with patch.object(feed._yf, "fetch_ohlcv", return_value=mock_df), \
         patch.object(feed._tech, "analyze", return_value=[]), \
         patch.object(feed._news, "fetch", return_value=[]), \
         patch.object(feed._inst, "fetch_insider_trades", return_value=[]), \
         patch("core.data.market_feed._get_session", return_value="regular"):
        feed.fetch_and_dispatch()

    pkt = q.get_nowait()
    assert "movers" in pkt
    assert pkt["movers"][0]["symbol"] == "NVDA"
    assert set(pkt.keys()) >= {"session", "movers", "signals", "news", "institutional"}


import pandas as pd


def _make_ohlcv():
    return pd.DataFrame({
        "open": [100.0], "high": [105.0], "low": [99.0],
        "close": [103.5], "volume": [1_000_000],
    })


def test_packet_contains_prices_for_fetched_symbols():
    q = queue.Queue()
    feed = MarketFeed([q])
    feed._yf = MagicMock()
    feed._yf.fetch_ohlcv.return_value = _make_ohlcv()
    feed._tech = MagicMock()
    feed._tech.analyze.return_value = []
    feed._agg = MagicMock()
    feed._agg.rank.return_value = []
    feed._news = MagicMock()
    feed._news.fetch.return_value = []
    feed._inst = MagicMock()
    feed._inst.fetch_insider_trades.return_value = []

    with patch("core.data.market_feed._get_session", return_value="regular"):
        feed.fetch_and_dispatch()

    packet = q.get_nowait()
    assert "prices" in packet
    assert len(packet["prices"]) > 0
    for price in packet["prices"].values():
        assert isinstance(price, float)
        assert price > 0


def test_packet_prices_empty_when_all_fetches_fail():
    q = queue.Queue()
    feed = MarketFeed([q])
    feed._yf = MagicMock()
    feed._yf.fetch_ohlcv.side_effect = Exception("network error")
    feed._tech = MagicMock()
    feed._agg = MagicMock()
    feed._agg.rank.return_value = []
    feed._news = MagicMock()
    feed._news.fetch.return_value = []
    feed._inst = MagicMock()
    feed._inst.fetch_insider_trades.return_value = []

    with patch("core.data.market_feed._get_session", return_value="regular"):
        feed.fetch_and_dispatch()

    packet = q.get_nowait()
    assert "prices" in packet
    assert packet["prices"] == {}
