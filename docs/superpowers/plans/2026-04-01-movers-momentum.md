# Movers-First Momentum Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed Schwab's real-time top market movers into the agents' decision prompt so Claude scans what the market has already validated before choosing a position.

**Architecture:** `SchwabClient.get_movers()` fetches top gainers from Schwab each cycle. `MarketFeed` accepts a `schwab_client` parameter, calls `get_movers()`, and includes the results in the data packet. `build_decision_prompt()` renders a movers section and updated Task instructions that encourage patience and cross-referencing.

**Tech Stack:** Python, schwab-py (`schwab.client.Client.Movers.Index`), pytest

---

## File Map

| File | Change |
|---|---|
| `core/data/schwab_client.py` | Add `get_movers()` method |
| `core/data/market_feed.py` | Accept `schwab_client`; call `get_movers()`; add `movers` to packet |
| `core/decision/prompt_builder.py` | Add `movers` param; render movers section; update Task instructions |
| `main.py` | Pass `schwab` instance to `MarketFeed(...)` |
| `tests/core/data/test_market_feed.py` | Add movers test |
| `tests/core/decision/test_prompt_builder.py` | Create; test movers section rendering |

---

## Task 1: `SchwabClient.get_movers()`

**Files:**
- Modify: `core/data/schwab_client.py`
- Test: (inline in Task 2 — movers are tested via MarketFeed integration)

- [ ] **Step 1: Add `get_movers()` to `SchwabClient`**

Open `core/data/schwab_client.py`. Add this method after `place_order()`:

```python
def get_movers(self, index: str = "SPX", top_n: int = 10) -> list[dict]:
    from schwab.client import Client as _C
    _index_map = {
        "SPX": _C.Movers.Index.SPX,
        "COMPX": _C.Movers.Index.COMPX,
        "DJI": _C.Movers.Index.DJI,
    }
    idx = _index_map.get(index, _C.Movers.Index.SPX)
    try:
        resp = self._client.get_movers(idx)
        resp.raise_for_status()
        screeners = resp.json().get("screeners", [])
        gainers = [
            {
                "symbol": s["symbol"],
                "description": s.get("description", ""),
                "lastPrice": s.get("lastPrice", 0.0),
                "netChange": s.get("netChange", 0.0),
                "netPercentChange": round(s.get("netPercentChange", 0.0) * 100, 2),
                "volume": s.get("volume", 0),
            }
            for s in screeners
            if s.get("netChange", 0.0) > 0
        ]
        gainers.sort(key=lambda x: x["netPercentChange"], reverse=True)
        return gainers[:top_n]
    except Exception:
        return []
```

- [ ] **Step 2: Commit**

```bash
git add core/data/schwab_client.py
git commit -m "feat: add get_movers() to SchwabClient"
```

---

## Task 2: `MarketFeed` — accept schwab_client and include movers

**Files:**
- Modify: `core/data/market_feed.py`
- Modify: `tests/core/data/test_market_feed.py`

- [ ] **Step 1: Write the failing test**

Open `tests/core/data/test_market_feed.py`. Add this test after the existing one:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/data/test_market_feed.py::test_packet_includes_movers -v
```

Expected: FAIL — `MarketFeed.__init__` does not accept `schwab_client`

- [ ] **Step 3: Update `MarketFeed`**

Open `core/data/market_feed.py`. Update `__init__` and `fetch_and_dispatch`:

```python
class MarketFeed:
    def __init__(self, agent_queues: list[queue.Queue],
                 watchlist: list[str] = DEFAULT_WATCHLIST,
                 schwab_client=None):
        self._queues = agent_queues
        self._watchlist = watchlist
        self._schwab = schwab_client
        self._tech = TechnicalAnalyzer()
        self._agg = SignalAggregator()
        self._news = NewsFeed()
        self._inst = InstitutionalFeed()
        self._yf = YFinanceClient()
```

In `fetch_and_dispatch()`, add movers fetch after the institutional block and before building the packet:

```python
        # Top market movers (Schwab real-time)
        movers = []
        if self._schwab is not None:
            try:
                movers = self._schwab.get_movers()
            except Exception:
                movers = []

        packet = {
            "session": session,
            "movers": movers,
            "signals": ranked[:10],
            "news": [{"title": a["title"], "source": a.get("source", {}).get("name")}
                     for a in news[:10]],
            "institutional": inst_signals[:10],
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/core/data/test_market_feed.py -v
```

Expected: both tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/data/market_feed.py tests/core/data/test_market_feed.py
git commit -m "feat: include top movers in MarketFeed data packet"
```

---

## Task 3: `prompt_builder.py` — movers section + updated Task instructions

**Files:**
- Modify: `core/decision/prompt_builder.py`
- Create: `tests/core/decision/test_prompt_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/core/decision/test_prompt_builder.py`:

```python
from core.decision.prompt_builder import build_decision_prompt


def _base_kwargs(**overrides):
    kwargs = dict(
        session="regular",
        expertise={},
        signals=[],
        news=[],
        institutional=[],
        open_positions=[],
        cash=500.0,
        daily_pnl=0.0,
        daily_pnl_pct=0.0,
        daily_loss_remaining=30.0,
        movers=[],
    )
    kwargs.update(overrides)
    return kwargs


def test_movers_section_present():
    prompt = build_decision_prompt(**_base_kwargs())
    assert "Top Market Movers" in prompt


def test_movers_rendered_in_prompt():
    movers = [
        {"symbol": "NVDA", "description": "NVIDIA CORP",
         "lastPrice": 175.58, "netChange": 8.06,
         "netPercentChange": 4.81, "volume": 121693985},
    ]
    prompt = build_decision_prompt(**_base_kwargs(movers=movers))
    assert "NVDA" in prompt
    assert "4.81%" in prompt


def test_empty_movers_shows_none():
    prompt = build_decision_prompt(**_base_kwargs(movers=[]))
    assert "(none)" in prompt


def test_patience_instruction_in_task():
    prompt = build_decision_prompt(**_base_kwargs())
    assert "Patience is a valid strategy" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/core/decision/test_prompt_builder.py -v
```

Expected: FAIL — `build_decision_prompt` does not accept `movers` parameter

- [ ] **Step 3: Update `build_decision_prompt`**

Open `core/decision/prompt_builder.py`. Update the function signature and body:

```python
def build_decision_prompt(
    session: str,
    expertise: dict[str, dict],
    signals: list[dict],
    news: list[dict],
    institutional: list[dict],
    open_positions: list[dict],
    cash: float,
    daily_pnl: float,
    daily_pnl_pct: float,
    daily_loss_remaining: float,
    movers: list[dict] | None = None,
) -> str:
    if movers is None:
        movers = []
    now = datetime.now(timezone.utc)
    return f"""## Current Market Context
Date: {now.strftime('%Y-%m-%d')} | Time: {now.strftime('%H:%M')} UTC | Session: {session}

## Agent Expertise (Mental Model)
### Market
{_yaml_summary(expertise.get('market', {}))}

### News
{_yaml_summary(expertise.get('news', {}))}

### Institutional
{_yaml_summary(expertise.get('institutional', {}))}

### Trade History
{_yaml_summary(expertise.get('trade', {}))}

## Top Market Movers (S&P 500 — sorted by % gain)
{_format_movers(movers)}

## Live Signals
### Breakout Candidates
{_format_list(signals)}

### News Sentiment
{_format_list(news)}

### Institutional Activity
{_format_list(institutional)}

## Current Positions
{_format_list(open_positions)}

## Portfolio State
Cash available: ${cash:,.2f}
Daily P&L: ${daily_pnl:,.2f} ({daily_pnl_pct:.1f}%)
Daily loss limit remaining: ${daily_loss_remaining:,.2f}

## Task
Start by reviewing the top market movers. These are stocks the market has already
validated with real volume and price action today. Cross-reference with the breakout
signals and news below. Only enter a position when you see alignment — a mover that
also has technical confirmation and/or news support. Patience is a valid strategy.
If nothing meets that bar, hold. A missed opportunity is better than a bad trade.
Long positions only — no short selling. To express bearish conviction, buy an inverse
ETF (SH, SDS, QID, or DOG) instead.

## Response Format (JSON only)
{{
  "action": "buy|sell|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "brief explanation",
  "signals_used": [],
  "skip_reason": "if hold, why"
}}"""
```

Add `_format_movers()` helper at the bottom of the file:

```python
def _format_movers(movers: list[dict]) -> str:
    if not movers:
        return "  (none)"
    lines = []
    for m in movers:
        lines.append(
            f"  - {m['symbol']:6s}  +{m['netPercentChange']:.2f}%"
            f"  ${m['lastPrice']:.2f}"
            f"  vol {m['volume']:,}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/core/decision/test_prompt_builder.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/decision/prompt_builder.py tests/core/decision/test_prompt_builder.py
git commit -m "feat: add movers section and patience instructions to decision prompt"
```

---

## Task 4: Wire `SchwabClient` into `MarketFeed` in `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Update `MarketFeed` instantiation in `main.py`**

Find this line in `main.py` (around line 157):

```python
feed = MarketFeed([queue_a, queue_b])
```

Replace with:

```python
feed = MarketFeed([queue_a, queue_b], schwab_client=schwab)
```

- [ ] **Step 2: Run full test suite to verify nothing broken**

```bash
pytest --tb=short -q
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: wire SchwabClient into MarketFeed for live movers data"
```

---

## Task 5: Full integration smoke test

- [ ] **Step 1: Verify movers load end-to-end**

```bash
python -c "
from core.data.schwab_client import SchwabClient
c = SchwabClient()
movers = c.get_movers()
print(f'Movers fetched: {len(movers)}')
for m in movers[:3]:
    print(f'  {m[\"symbol\"]:6s}  +{m[\"netPercentChange\"]:.2f}%  \${m[\"lastPrice\"]:.2f}')
"
```

Expected: 3 movers printed with symbol, % gain, and price.

- [ ] **Step 2: Commit if all green**

No new files — this is a verification step only.
