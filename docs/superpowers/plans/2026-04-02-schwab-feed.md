# SchwabFeed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the MarketFeed packet with live Schwab bulk quotes every cycle and fundamental data (PE, EPS, market cap, 52-week range, dividend yield) cached twice per trading day.

**Architecture:** A new `SchwabFeed` class in `core/data/schwab_feed.py` owns all caching and merging logic. Two thin wrapper methods are added to `SchwabClient`. `MarketFeed` gains an optional `schwab_feed` param and adds a `"schwab_data"` key to each packet. `main.py` wires them together.

**Tech Stack:** Python 3.11+, schwab-py, `zoneinfo` (stdlib), `unittest.mock` for tests

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `core/data/schwab_client.py` | Add `get_quotes_bulk()` and `get_instrument_fundamental()` |
| Create | `core/data/schwab_feed.py` | `SchwabFeed` class — caching, slot logic, fetch/merge |
| Modify | `core/data/market_feed.py` | Accept optional `schwab_feed`, add `"schwab_data"` to packet |
| Modify | `main.py` | Construct `SchwabFeed`, pass to `MarketFeed` |
| Create | `tests/core/data/test_schwab_feed.py` | Unit tests for `SchwabFeed` |
| Modify | `tests/core/data/test_market_feed.py` | Tests for `schwab_data` in packet |

---

### Task 1: Add thin wrapper methods to SchwabClient

**Files:**
- Modify: `core/data/schwab_client.py`

- [ ] **Step 1: Write the failing tests**

Add to a new file `tests/core/data/test_schwab_client.py`:

```python
from unittest.mock import MagicMock, patch
import pytest


def _make_client(mock_inner):
    """Build a SchwabClient with a mocked inner schwab client."""
    with patch("core.data.schwab_client.auth") as mock_auth:
        mock_auth.client_from_token_file.return_value = mock_inner
        with patch("core.data.schwab_client._TOKEN_PATH") as mock_path:
            mock_path.exists.return_value = True
            from core.data.schwab_client import SchwabClient
            return SchwabClient()


def test_get_quotes_bulk_returns_dict():
    mock_inner = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}},
        "MSFT": {"quote": {"lastPrice": 415.0, "totalVolume": 20000000,
                           "bidPrice": 414.9, "askPrice": 415.1,
                           "netPercentChangeInDouble": 0.8}},
    }
    mock_resp.raise_for_status = MagicMock()
    mock_inner.get_quotes.return_value = mock_resp

    sc = _make_client(mock_inner)
    result = sc.get_quotes_bulk(["AAPL", "MSFT"])

    mock_inner.get_quotes.assert_called_once_with(["AAPL", "MSFT"])
    assert result == mock_resp.json.return_value


def test_get_instrument_fundamental_returns_dict():
    mock_inner = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "AAPL": {
            "fundamental": {
                "peRatio": 28.1, "eps": 6.12, "marketCap": 2.8e12,
                "high52": 198.2, "low52": 164.1, "dividendYield": 0.52,
            }
        }
    }
    mock_resp.raise_for_status = MagicMock()
    mock_inner.get_instruments.return_value = mock_resp

    sc = _make_client(mock_inner)
    result = sc.get_instrument_fundamental("AAPL")

    mock_inner.get_instruments.assert_called_once_with(
        "AAPL", projection="fundamental")
    assert result == mock_resp.json.return_value
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/data/test_schwab_client.py -v
```

Expected: `AttributeError: 'SchwabClient' object has no attribute 'get_quotes_bulk'`

- [ ] **Step 3: Add the two methods to SchwabClient**

In `core/data/schwab_client.py`, add after `get_movers()` (before `if __name__ == "__main__":`):

```python
def get_quotes_bulk(self, symbols: list[str]) -> dict:
    resp = self._client.get_quotes(symbols)
    resp.raise_for_status()
    return resp.json()

def get_instrument_fundamental(self, symbol: str) -> dict:
    resp = self._client.get_instruments(symbol, projection="fundamental")
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/core/data/test_schwab_client.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add core/data/schwab_client.py tests/core/data/test_schwab_client.py
git commit -m "feat: add get_quotes_bulk and get_instrument_fundamental to SchwabClient"
```

---

### Task 2: Create SchwabFeed — slot logic and fundamental caching

**Files:**
- Create: `core/data/schwab_feed.py`
- Create: `tests/core/data/test_schwab_feed.py`

- [ ] **Step 1: Write failing tests for slot logic and caching**

Create `tests/core/data/test_schwab_feed.py`:

```python
from unittest.mock import MagicMock, patch, call
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/data/test_schwab_feed.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.data.schwab_feed'`

- [ ] **Step 3: Implement SchwabFeed**

Create `core/data/schwab_feed.py`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/core/data/test_schwab_feed.py -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add core/data/schwab_feed.py tests/core/data/test_schwab_feed.py
git commit -m "feat: add SchwabFeed with bulk quotes and cached fundamentals"
```

---

### Task 3: Wire SchwabFeed into MarketFeed

**Files:**
- Modify: `core/data/market_feed.py`
- Modify: `tests/core/data/test_market_feed.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/data/test_market_feed.py`:

```python
def test_packet_includes_schwab_data_when_feed_provided():
    q = queue.Queue()
    mock_schwab_feed = MagicMock()
    mock_schwab_feed.fetch.return_value = {
        "AAPL": {"last": 172.5, "volume": 45000000, "bid": 172.48,
                 "ask": 172.52, "net_pct": 1.2, "pe": 28.1}
    }
    feed = MarketFeed([q], watchlist=["AAPL"], schwab_feed=mock_schwab_feed)
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

    pkt = q.get_nowait()
    assert "schwab_data" in pkt
    assert pkt["schwab_data"]["AAPL"]["last"] == 172.5
    assert pkt["schwab_data"]["AAPL"]["pe"] == 28.1


def test_packet_excludes_schwab_data_when_no_feed():
    q = queue.Queue()
    feed = MarketFeed([q], watchlist=["AAPL"])
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

    pkt = q.get_nowait()
    assert "schwab_data" not in pkt
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/data/test_market_feed.py::test_packet_includes_schwab_data_when_feed_provided tests/core/data/test_market_feed.py::test_packet_excludes_schwab_data_when_no_feed -v
```

Expected: `TypeError: MarketFeed.__init__() got an unexpected keyword argument 'schwab_feed'`

- [ ] **Step 3: Update MarketFeed**

In `core/data/market_feed.py`, update `__init__` signature:

```python
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
```

In `fetch_and_dispatch()`, add schwab_feed call just before building `packet`. Replace the `packet = { ... }` block with:

```python
        schwab_data = {}
        if self._schwab_feed is not None:
            try:
                schwab_data = self._schwab_feed.fetch()
            except Exception:
                pass

        packet = {
            "session": session,
            "movers": movers,
            "prices": prices,
            "signals": ranked[:10],
            "news": [{"title": a["title"], "source": a.get("source", {}).get("name")}
                     for a in news[:10]],
            "institutional": inst_signals[:10],
        }
        if schwab_data:
            packet["schwab_data"] = schwab_data
```

- [ ] **Step 4: Run all MarketFeed tests**

```
pytest tests/core/data/test_market_feed.py -v
```

Expected: all passed (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add core/data/market_feed.py tests/core/data/test_market_feed.py
git commit -m "feat: wire SchwabFeed into MarketFeed as optional schwab_data enrichment"
```

---

### Task 4: Wire SchwabFeed into main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add import and construction**

In `main.py`, add the import after the existing data imports:

```python
from core.data.schwab_feed import SchwabFeed
```

In `main()`, add SchwabFeed construction after `exchange = PeerExchange()` and before `MarketFeed` is constructed. Replace:

```python
    feed = MarketFeed([queue_a, queue_b], schwab_client=schwab)
```

with:

```python
    schwab_feed = SchwabFeed(schwab, DEFAULT_WATCHLIST)
    feed = MarketFeed([queue_a, queue_b], schwab_client=schwab,
                      schwab_feed=schwab_feed)
```

Also add the import for `DEFAULT_WATCHLIST` at the top of `main.py`:

```python
from core.data.market_feed import MarketFeed, DEFAULT_WATCHLIST
```

(Replace the existing `from core.data.market_feed import MarketFeed` line.)

- [ ] **Step 2: Run full test suite**

```
pytest tests/ -v --tb=short
```

Expected: all previously passing tests still pass

- [ ] **Step 3: Smoke test startup**

```
python -c "
from unittest.mock import MagicMock, patch
from core.data.schwab_feed import SchwabFeed
mock_schwab = MagicMock()
mock_schwab.get_quotes_bulk.return_value = {
    'AAPL': {'quote': {'lastPrice': 172.5, 'totalVolume': 45000000,
                       'bidPrice': 172.48, 'askPrice': 172.52,
                       'netPercentChangeInDouble': 1.2}}
}
mock_schwab.get_instrument_fundamental.return_value = {
    'AAPL': {'fundamental': {'peRatio': 28.1, 'eps': 6.12,
                              'marketCap': 2.8e12, 'high52': 198.2,
                              'low52': 164.1, 'dividendYield': 0.52}}
}
feed = SchwabFeed(mock_schwab, ['AAPL'])
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
dt = datetime(2026, 4, 2, 10, 0, tzinfo=ZoneInfo('America/New_York'))
with patch('core.data.schwab_feed.datetime') as m:
    m.now.return_value = dt
    result = feed.fetch()
print('schwab_data AAPL:', result['AAPL'])
assert result['AAPL']['last'] == 172.5
assert result['AAPL']['pe'] == 28.1
print('OK')
"
```

Expected: prints `schwab_data AAPL: {...}` and `OK`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: wire SchwabFeed into main.py"
```

---

### Task 5: Push and merge

- [ ] **Step 1: Push to remote**

```bash
git push origin main
```

- [ ] **Step 2: Verify CI passes** (if CI is configured)

Check GitHub Actions or equivalent. If no CI, skip.
