from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo


def _make_feed(watchlist=None):
    from core.data.schwab_feed import SchwabFeed
    mock_schwab = MagicMock()
    return SchwabFeed(mock_schwab, watchlist or ["AAPL", "MSFT"]), mock_schwab


_ET = ZoneInfo("America/New_York")


def _dt(hour, minute=0):
    """Return a datetime at the given ET hour."""
    return datetime(2026, 4, 2, hour, minute, tzinfo=_ET)


def test_current_slot_open():
    feed, _ = _make_feed()
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        assert feed._current_slot() == "open"


def test_current_slot_midday():
    feed, _ = _make_feed()
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(13, 0)
        assert feed._current_slot() == "midday"


def test_current_slot_none_outside_hours():
    feed, _ = _make_feed()
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(20, 0)
        assert feed._current_slot() is None


def test_fundamentals_fetched_on_first_call():
    feed, mock_schwab = _make_feed(["AAPL"])
    mock_schwab.get_instrument_fundamental.return_value = {
        "AAPL": {"fundamental": {"peRatio": 28.1, "eps": 6.12,
                                  "marketCap": 2.8e12, "high52": 198.2,
                                  "low52": 164.1, "dividendYield": 0.52}}
    }
    mock_schwab.get_quotes_bulk.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}}
    }
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        feed.fetch()

    mock_schwab.get_instrument_fundamental.assert_called_once_with("AAPL")
    assert feed._fund_slot == "open"


def test_fundamentals_not_refetched_in_same_slot():
    feed, mock_schwab = _make_feed(["AAPL"])
    mock_schwab.get_instrument_fundamental.return_value = {
        "AAPL": {"fundamental": {"peRatio": 28.1, "eps": 6.12,
                                  "marketCap": 2.8e12, "high52": 198.2,
                                  "low52": 164.1, "dividendYield": 0.52}}
    }
    mock_schwab.get_quotes_bulk.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}}
    }
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        feed.fetch()
        feed.fetch()

    # fundamental called once despite two fetch() calls in same slot
    assert mock_schwab.get_instrument_fundamental.call_count == 1


def test_fundamentals_refetched_on_slot_change():
    feed, mock_schwab = _make_feed(["AAPL"])
    mock_schwab.get_instrument_fundamental.return_value = {
        "AAPL": {"fundamental": {"peRatio": 28.1, "eps": 6.12,
                                  "marketCap": 2.8e12, "high52": 198.2,
                                  "low52": 164.1, "dividendYield": 0.52}}
    }
    mock_schwab.get_quotes_bulk.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}}
    }
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        feed.fetch()
        mock_dt.now.return_value = _dt(13, 0)
        feed.fetch()

    assert mock_schwab.get_instrument_fundamental.call_count == 2
    assert feed._fund_slot == "midday"


def test_failed_fundamental_symbol_skipped():
    feed, mock_schwab = _make_feed(["AAPL", "MSFT"])

    def fund_side_effect(symbol):
        if symbol == "MSFT":
            raise Exception("rate limit")
        return {"AAPL": {"fundamental": {"peRatio": 28.1, "eps": 6.12,
                                          "marketCap": 2.8e12, "high52": 198.2,
                                          "low52": 164.1, "dividendYield": 0.52}}}

    mock_schwab.get_instrument_fundamental.side_effect = fund_side_effect
    mock_schwab.get_quotes_bulk.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}},
        "MSFT": {"quote": {"lastPrice": 415.0, "totalVolume": 20000000,
                           "bidPrice": 414.9, "askPrice": 415.1,
                           "netPercentChangeInDouble": 0.8}},
    }
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        result = feed.fetch()

    assert "AAPL" in result
    assert "pe" in result["AAPL"]
    assert "MSFT" in result
    assert "pe" not in result["MSFT"]   # fundamental failed, live quote still present


def test_fetch_returns_merged_data():
    feed, mock_schwab = _make_feed(["AAPL"])
    mock_schwab.get_instrument_fundamental.return_value = {
        "AAPL": {"fundamental": {"peRatio": 28.1, "eps": 6.12,
                                  "marketCap": 2.8e12, "high52": 198.2,
                                  "low52": 164.1, "dividendYield": 0.52}}
    }
    mock_schwab.get_quotes_bulk.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}}
    }
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        result = feed.fetch()

    assert result["AAPL"]["last"] == 172.5
    assert result["AAPL"]["volume"] == 45000000
    assert result["AAPL"]["bid"] == 172.48
    assert result["AAPL"]["ask"] == 172.52
    assert result["AAPL"]["net_pct"] == 1.2
    assert result["AAPL"]["pe"] == 28.1
    assert result["AAPL"]["eps"] == 6.12
    assert result["AAPL"]["market_cap"] == 2.8e12
    assert result["AAPL"]["52wk_high"] == 198.2
    assert result["AAPL"]["52wk_low"] == 164.1
    assert result["AAPL"]["div_yield"] == 0.52


def test_fetch_returns_empty_on_bulk_quote_failure():
    feed, mock_schwab = _make_feed(["AAPL"])
    mock_schwab.get_instrument_fundamental.return_value = {
        "AAPL": {"fundamental": {"peRatio": 28.1, "eps": 6.12,
                                  "marketCap": 2.8e12, "high52": 198.2,
                                  "low52": 164.1, "dividendYield": 0.52}}
    }
    mock_schwab.get_quotes_bulk.side_effect = Exception("network error")
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        result = feed.fetch()

    assert result == {}


def test_fund_slot_not_updated_when_all_fundamentals_fail():
    feed, mock_schwab = _make_feed(["AAPL"])
    mock_schwab.get_instrument_fundamental.side_effect = Exception("rate limit")
    mock_schwab.get_quotes_bulk.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}}
    }
    with patch("core.data.schwab_feed.datetime") as mock_dt:
        mock_dt.now.return_value = _dt(10, 0)
        feed.fetch()
        # _fund_slot should still be None — retry should happen on next call
        assert feed._fund_slot is None
        # second call in same slot retries fundamentals
        feed.fetch()

    assert mock_schwab.get_instrument_fundamental.call_count == 2
