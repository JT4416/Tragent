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
    assert pkt["session"] == "regular"
