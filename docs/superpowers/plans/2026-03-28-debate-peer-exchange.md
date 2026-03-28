# Debate + Peer Exchange Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured self-debate (bull/bear case) to every trading decision and post-trade agent-to-agent peer exchange via a shared in-memory queue so agents learn from each other's trades.

**Architecture:** Eight sequential tasks — each builds on the last. SQLite schema and PositionTracker first (foundational), then PeerExchange and decision layer, then self-improve peer learning, then market feed prices, then the full agent overhaul that wires it all together, then main.py.

**Tech Stack:** Python 3.14, sqlite3, queue.Queue, pytest, pytest-mock, pyyaml, anthropic SDK

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/state/persistence.py` | Modify | Add `entry_time` to Position; schema migration; `get_position(symbol)` |
| `core/risk/position_tracker.py` | Modify | Accept optional `store` param to share StateStore with Agent |
| `agents/peer_exchange.py` | **Create** | PeerExchange: register/publish/drain per-agent inboxes |
| `core/decision/prompt_builder.py` | Modify | Add bull/bear to decision prompt; add `build_peer_learning_prompt` |
| `core/decision/claude_client.py` | Modify | Add `bull_case`/`bear_case` to `TradeDecision`; update `_parse_response`; raise `max_tokens` |
| `agents/self_improve.py` | Modify | Add `run_peer_learning(insight)` method |
| `core/data/market_feed.py` | Modify | Collect `prices` dict during OHLCV loop; add to packet |
| `agents/agent.py` | Modify | Own PositionTracker; revised `run_cycle`; `close_position`; peer exchange wiring |
| `main.py` | Modify | Instantiate PeerExchange; register IDs; pass to agents |
| `tests/agents/test_peer_exchange.py` | **Create** | Unit tests for register/publish/drain |
| `tests/agents/test_agent.py` | Modify | Add tests: peer drain at REUSE, close_position, stop-triggered close |
| `tests/agents/test_self_improve.py` | Modify | Add test: run_peer_learning updates expertise |
| `tests/core/decision/test_claude_client.py` | Modify | Add test: bull_case/bear_case parsed from response |
| `tests/core/risk/test_position_tracker.py` | Modify | Add test: shared store param |

---

## Task 1: SQLite Schema — entry_time + get_position

**Files:**
- Modify: `core/state/persistence.py`
- Modify: `tests/core/state/test_persistence.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/state/test_persistence.py`:

```python
from datetime import datetime, timezone

def test_position_saves_and_loads_entry_time(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    pos = Position("AAPL", "long", 180.0, stop_loss=176.4,
                   trailing_stop=177.3, quantity=10,
                   entry_time="2026-03-28T14:00:00+00:00")
    store.save_position(pos)
    loaded = store.get_positions()
    assert loaded[0].entry_time == "2026-03-28T14:00:00+00:00"

def test_get_position_returns_none_for_missing(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    assert store.get_position("AAPL") is None

def test_get_position_returns_correct_position(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    pos = Position("AAPL", "long", 180.0, stop_loss=176.4,
                   trailing_stop=177.3, quantity=10)
    store.save_position(pos)
    result = store.get_position("AAPL")
    assert result is not None
    assert result.symbol == "AAPL"
    assert result.entry_price == 180.0

def test_schema_migration_adds_entry_time_to_existing_db(tmp_dir):
    """Simulate opening a pre-existing database that lacks entry_time."""
    import sqlite3
    db_path = tmp_dir / "agent_a.db"
    # Create old-style table without entry_time
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE positions (
        symbol TEXT PRIMARY KEY, direction TEXT,
        entry_price REAL, stop_loss REAL, trailing_stop REAL, quantity INTEGER
    )""")
    conn.execute("INSERT INTO positions VALUES ('AAPL','long',180.0,176.4,177.3,10)")
    conn.commit()
    conn.close()
    # Opening StateStore should migrate without error
    store = StateStore("agent_a", db_dir=tmp_dir)
    pos = store.get_position("AAPL")
    assert pos is not None
    assert pos.entry_time == ""
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/core/state/test_persistence.py::test_position_saves_and_loads_entry_time tests/core/state/test_persistence.py::test_get_position_returns_none_for_missing tests/core/state/test_persistence.py::test_get_position_returns_correct_position tests/core/state/test_persistence.py::test_schema_migration_adds_entry_time_to_existing_db -v
```

Expected: FAIL — `Position` has no `entry_time`, `get_position` doesn't exist.

- [ ] **Step 3: Implement**

Replace `core/state/persistence.py` entirely:

```python
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Position:
    symbol: str
    direction: str          # "long" or "short"
    entry_price: float
    stop_loss: float
    trailing_stop: float
    quantity: int
    entry_time: str = ""    # ISO-8601 UTC string


_DEFAULT_DB_DIR = Path(__file__).parent.parent.parent / "state"


class StateStore:
    def __init__(self, agent_id: str, db_dir: Path = _DEFAULT_DB_DIR):
        db_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_dir / f"{agent_id}.db")
        self._create_tables()

    def __del__(self):
        if hasattr(self, '_conn'):
            self._conn.close()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                direction TEXT,
                entry_price REAL,
                stop_loss REAL,
                trailing_stop REAL,
                quantity INTEGER,
                entry_time TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS round_state (
                key TEXT PRIMARY KEY,
                value REAL
            );
        """)
        self._conn.commit()
        # Migration: add entry_time to pre-existing databases
        try:
            self._conn.execute(
                "ALTER TABLE positions ADD COLUMN entry_time TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    def save_position(self, pos: Position) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO positions
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (pos.symbol, pos.direction, pos.entry_price,
              pos.stop_loss, pos.trailing_stop, pos.quantity, pos.entry_time))
        self._conn.commit()

    def get_positions(self) -> list[Position]:
        rows = self._conn.execute("SELECT * FROM positions").fetchall()
        return [Position(*r) for r in rows]

    def get_position(self, symbol: str) -> 'Position | None':
        row = self._conn.execute(
            "SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
        return Position(*row) if row else None

    def remove_position(self, symbol: str) -> None:
        self._conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        self._conn.commit()

    def update_round_pnl(self, pnl: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO round_state VALUES ('round_pnl', ?)", (pnl,))
        self._conn.commit()

    def get_round_pnl(self) -> float:
        row = self._conn.execute(
            "SELECT value FROM round_state WHERE key='round_pnl'").fetchone()
        return row[0] if row else 0.0
```

- [ ] **Step 4: Run tests**

```
pytest tests/core/state/test_persistence.py -v
```

Expected: all 7 pass (4 new + 3 existing).

- [ ] **Step 5: Commit**

```bash
git add core/state/persistence.py tests/core/state/test_persistence.py
git commit -m "feat: add entry_time to Position, schema migration, get_position method"
```

---

## Task 2: PositionTracker Shared Store

**Files:**
- Modify: `core/risk/position_tracker.py`
- Modify: `tests/core/risk/test_position_tracker.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/risk/test_position_tracker.py`:

```python
from core.state.persistence import StateStore

def test_shared_store_is_used_when_provided(tmp_dir):
    shared_store = StateStore("agent_a", db_dir=tmp_dir)
    tracker = PositionTracker(trailing_pct=1.5, agent_id="agent_a", store=shared_store)
    assert tracker.store is shared_store

def test_own_store_created_when_no_store_provided(tmp_dir):
    tracker = PositionTracker(trailing_pct=1.5, agent_id="agent_a", db_dir=tmp_dir)
    assert tracker.store is not None
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/core/risk/test_position_tracker.py::test_shared_store_is_used_when_provided tests/core/risk/test_position_tracker.py::test_own_store_created_when_no_store_provided -v
```

Expected: FAIL — `PositionTracker` doesn't accept `store` param.

- [ ] **Step 3: Implement**

Replace `core/risk/position_tracker.py`:

```python
from pathlib import Path
from core.state.persistence import StateStore


class PositionTracker:
    def __init__(self, trailing_pct: float, agent_id: str,
                 db_dir: Path | None = None, store: StateStore | None = None):
        self._trailing_pct = trailing_pct
        self.store = store if store is not None else StateStore(agent_id, db_dir)

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
```

- [ ] **Step 4: Run tests**

```
pytest tests/core/risk/test_position_tracker.py -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add core/risk/position_tracker.py tests/core/risk/test_position_tracker.py
git commit -m "feat: PositionTracker accepts optional shared StateStore"
```

---

## Task 3: PeerExchange Class

**Files:**
- Create: `agents/peer_exchange.py`
- Create: `tests/agents/test_peer_exchange.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/agents/test_peer_exchange.py`:

```python
import pytest
from agents.peer_exchange import PeerExchange


def test_register_and_drain_empty():
    ex = PeerExchange()
    ex.register("agent_a")
    assert ex.drain("agent_a") == []


def test_publish_delivers_to_other_agent():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    insight = {"from_agent": "agent_a", "event": "entry", "symbol": "AAPL"}
    ex.publish("agent_a", insight)
    received = ex.drain("agent_b")
    assert len(received) == 1
    assert received[0]["symbol"] == "AAPL"


def test_publish_does_not_deliver_to_sender():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    ex.publish("agent_a", {"event": "entry"})
    assert ex.drain("agent_a") == []


def test_drain_clears_inbox():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    ex.publish("agent_a", {"event": "entry"})
    ex.drain("agent_b")
    assert ex.drain("agent_b") == []


def test_multiple_insights_all_delivered():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    ex.publish("agent_a", {"event": "entry", "n": 1})
    ex.publish("agent_a", {"event": "close", "n": 2})
    received = ex.drain("agent_b")
    assert len(received) == 2


def test_unregistered_publish_raises():
    ex = PeerExchange()
    ex.register("agent_a")
    with pytest.raises(KeyError):
        ex.publish("agent_x", {"event": "entry"})


def test_unregistered_drain_raises():
    ex = PeerExchange()
    with pytest.raises(KeyError):
        ex.drain("agent_x")
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/agents/test_peer_exchange.py -v
```

Expected: FAIL — `agents/peer_exchange.py` doesn't exist.

- [ ] **Step 3: Implement**

Create `agents/peer_exchange.py`:

```python
import queue


class PeerExchange:
    """Thread-safe per-agent inbox for post-trade peer insights."""

    def __init__(self):
        self._inboxes: dict[str, queue.Queue] = {}

    def register(self, agent_id: str) -> None:
        """Create an inbox for agent_id. Call before starting agent threads."""
        self._inboxes[agent_id] = queue.Queue()

    def publish(self, from_agent_id: str, insight: dict) -> None:
        """Put insight into every registered inbox except the sender's own."""
        if from_agent_id not in self._inboxes:
            raise KeyError(f"Agent '{from_agent_id}' not registered")
        for agent_id, inbox in self._inboxes.items():
            if agent_id != from_agent_id:
                inbox.put(insight)

    def drain(self, for_agent_id: str) -> list[dict]:
        """Return and clear all pending insights for for_agent_id."""
        if for_agent_id not in self._inboxes:
            raise KeyError(f"Agent '{for_agent_id}' not registered")
        inbox = self._inboxes[for_agent_id]
        items = []
        while True:
            try:
                items.append(inbox.get_nowait())
            except queue.Empty:
                break
        return items
```

- [ ] **Step 4: Run tests**

```
pytest tests/agents/test_peer_exchange.py -v
```

Expected: all 7 pass.

- [ ] **Step 5: Commit**

```bash
git add agents/peer_exchange.py tests/agents/test_peer_exchange.py
git commit -m "feat: PeerExchange class — thread-safe per-agent insight inboxes"
```

---

## Task 4: Debate Fields — TradeDecision + Decision Prompt

**Files:**
- Modify: `core/decision/claude_client.py`
- Modify: `core/decision/prompt_builder.py`
- Modify: `tests/core/decision/test_claude_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/decision/test_claude_client.py`:

```python
def test_parse_decision_extracts_bull_bear_case():
    raw = json.dumps({
        "bull_case": "Strong volume breakout above VWAP",
        "bear_case": "Broad market showing weakness",
        "action": "buy", "symbol": "AAPL", "confidence": 0.78,
        "position_size_pct": 3.0, "reasoning": "bull case wins — volume decisive",
        "signals_used": ["volume_spike"], "skip_reason": None
    })
    decision = ClaudeClient._parse_response(raw)
    assert decision.bull_case == "Strong volume breakout above VWAP"
    assert decision.bear_case == "Broad market showing weakness"

def test_parse_decision_defaults_empty_bull_bear():
    """Older response without bull/bear fields should not raise."""
    raw = json.dumps({
        "action": "hold", "symbol": None, "confidence": 0.4,
        "position_size_pct": 0, "reasoning": "no signal",
        "signals_used": [], "skip_reason": "nothing"
    })
    decision = ClaudeClient._parse_response(raw)
    assert decision.bull_case == ""
    assert decision.bear_case == ""
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/core/decision/test_claude_client.py::test_parse_decision_extracts_bull_bear_case tests/core/decision/test_claude_client.py::test_parse_decision_defaults_empty_bull_bear -v
```

Expected: FAIL — `TradeDecision` has no `bull_case`/`bear_case`.

- [ ] **Step 3: Update claude_client.py**

In `core/decision/claude_client.py`:

1. Add fields to `TradeDecision` dataclass (after `skip_reason`):
```python
bull_case: str = ""
bear_case: str = ""
```

2. Raise `max_tokens` in `decide()` from `512` to `768`.

3. In `_parse_response`, add extraction (after `skip_reason` line):
```python
bull_case=data.get("bull_case", ""),
bear_case=data.get("bear_case", ""),
```

- [ ] **Step 4: Update prompt_builder.py decision prompt**

In `build_decision_prompt`, make two edits:

1. Replace the `## Task` line:
```python
## Task
Analyze the signals above and return a trading decision.
```
with:
```python
## Task
Analyze the signals above. Before deciding, articulate the strongest bull and bear case for the leading candidate. Let the better argument win. Return a trading decision.
```

2. Replace the `## Response Format` block:
```python
## Response Format (JSON only)
{{
  "action": "buy|sell|short|cover|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "brief explanation",
  "signals_used": [],
  "skip_reason": "if hold, why"
}}
```
with:
```python
## Response Format (JSON only)
{{
  "bull_case": "strongest argument FOR this trade",
  "bear_case": "strongest argument AGAINST this trade",
  "action": "buy|sell|short|cover|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "which case won and why",
  "signals_used": [],
  "skip_reason": "if hold, why"
}}
```

- [ ] **Step 5: Run tests**

```
pytest tests/core/decision/test_claude_client.py -v
```

Expected: all 7 pass (5 existing + 2 new).

- [ ] **Step 6: Commit**

```bash
git add core/decision/claude_client.py core/decision/prompt_builder.py tests/core/decision/test_claude_client.py
git commit -m "feat: add bull_case/bear_case debate fields to TradeDecision and decision prompt"
```

---

## Task 5: Peer Learning Prompt + SelfImprove

**Files:**
- Modify: `core/decision/prompt_builder.py`
- Modify: `agents/self_improve.py`
- Modify: `tests/agents/test_self_improve.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/agents/test_self_improve.py`:

```python
def test_run_peer_learning_updates_expertise(tmp_dir):
    mgr = ExpertiseManager("agent_b", expertise_dir=tmp_dir)
    mgr.load("market")  # seed

    mock_claude = MagicMock()
    updated_yaml = yaml.dump({
        "overview": {"last_updated": "2026-03-28", "total_patterns_tracked": 1},
        "breakout_patterns": [
            {"id": "bp_peer_001", "description": "peer-learned", "confidence": 0.65,
             "occurrences": 1, "win_rate": 1.0, "avg_gain_pct": 2.0,
             "last_seen": "2026-03-28"}
        ],
        "volume_signals": [],
        "known_false_signals": [],
    })
    mock_claude.self_improve.return_value = updated_yaml

    orchestrator = SelfImproveOrchestrator(mgr, mock_claude)
    insight = {
        "from_agent": "agent_a",
        "event": "close",
        "trade_record": {
            "trade_id": "t_a_001", "symbol": "NVDA", "direction": "long",
            "entry": 900.0, "exit": 920.0, "pnl_pct": 2.22,
            "signals_used": ["volume_spike"], "outcome": "win",
        },
        "reasoning": "volume spike above VWAP",
        "bull_case": "NVDA breaking out on earnings volume",
        "bear_case": "Market may pull back",
        "outcome": "win",
        "pnl_pct": 2.22,
        "duration": "45m",
    }
    orchestrator.run_peer_learning(insight)

    assert mock_claude.self_improve.called
    prompt_used = mock_claude.self_improve.call_args[0][0]
    assert "NVDA" in prompt_used
    assert "do not copy blindly" in prompt_used

def test_run_peer_learning_with_unknown_signal_still_updates_trade(tmp_dir):
    """Signals not in _SIGNAL_TO_EXPERTISE map only update trade file."""
    mgr = ExpertiseManager("agent_b", expertise_dir=tmp_dir)
    mgr.load("trade")

    mock_claude = MagicMock()
    mock_claude.self_improve.return_value = yaml.dump({
        "overview": {}, "lessons_learned": [], "evolved_parameters": {},
        "recent_trades": [],
    })

    orchestrator = SelfImproveOrchestrator(mgr, mock_claude)
    insight = {
        "from_agent": "agent_a", "event": "entry",
        "trade_record": {
            "trade_id": "t_a_002", "symbol": "TSLA", "direction": "long",
            "entry": 200.0, "exit": None, "pnl_pct": None,
            "signals_used": ["unknown_signal_type"], "outcome": None,
        },
        "reasoning": "test", "bull_case": "", "bear_case": "",
        "outcome": "open", "pnl_pct": 0.0, "duration": "0m",
    }
    orchestrator.run_peer_learning(insight)
    # Should call self_improve once (only trade file updated)
    assert mock_claude.self_improve.call_count == 1
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/agents/test_self_improve.py::test_run_peer_learning_updates_expertise tests/agents/test_self_improve.py::test_run_peer_learning_with_unknown_signal_still_updates_trade -v
```

Expected: FAIL — `run_peer_learning` doesn't exist.

- [ ] **Step 3: Add build_peer_learning_prompt to prompt_builder.py**

Add at the end of `core/decision/prompt_builder.py`:

```python
def build_peer_learning_prompt(
    insight: dict,
    current_yaml: str,
    max_lines: int = 1000,
) -> str:
    trade = insight.get("trade_record", {})
    symbol = trade.get("symbol", "unknown")
    direction = trade.get("direction", "unknown")
    event = insight.get("event", "unknown")
    bull_case = insight.get("bull_case", "")
    bear_case = insight.get("bear_case", "")
    reasoning = insight.get("reasoning", "")
    outcome = insight.get("outcome", "unknown")
    pnl_pct = insight.get("pnl_pct", 0.0)
    duration = insight.get("duration", "unknown")

    return f"""## Peer Trade Insight (your competitor — do not copy blindly)
Event: {event}
They traded: {symbol} {direction}
Their bull case: {bull_case}
Their bear case: {bear_case}
Their reasoning: {reasoning}
Outcome: {outcome} | P&L: {pnl_pct:.2f}% | Duration: {duration}

## Your Current Expertise File (max {max_lines} lines)
{current_yaml}

## Task
What can you learn from your competitor's trade?
- If they identified a pattern you've missed, add it with confidence 0.1 lower than theirs
- If their outcome confirms your existing beliefs, increase confidence by 0.05
- If their outcome contradicts your existing beliefs, decrease confidence by 0.05
- Do NOT copy their position sizing or stop levels — evolve your own parameters
- Return the complete updated YAML only, no prose"""
```

- [ ] **Step 4: Add run_peer_learning to self_improve.py**

Add import at top of `agents/self_improve.py`:
```python
from core.decision.prompt_builder import build_self_improve_prompt, build_peer_learning_prompt
```

Add method to `SelfImproveOrchestrator`:

```python
def run_peer_learning(self, insight: dict) -> None:
    """Update expertise files based on a peer agent's trade insight."""
    files_to_update = self._determine_files(insight["trade_record"])
    files_to_update.add("trade")
    for file_name in files_to_update:
        current_data = self._mgr.load(file_name)
        current_yaml = yaml.dump(current_data, default_flow_style=False)
        prompt = build_peer_learning_prompt(insight, current_yaml)
        updated_yaml = self._claude.self_improve(prompt)
        try:
            updated_data = yaml.safe_load(updated_yaml)
            if updated_data:
                self._mgr.save(file_name, updated_data)
        except yaml.YAMLError:
            pass  # keep existing file if Claude returns invalid YAML
```

- [ ] **Step 5: Run tests**

```
pytest tests/agents/test_self_improve.py -v
```

Expected: all 3 pass (1 existing + 2 new).

- [ ] **Step 6: Commit**

```bash
git add core/decision/prompt_builder.py agents/self_improve.py tests/agents/test_self_improve.py
git commit -m "feat: peer learning prompt and SelfImproveOrchestrator.run_peer_learning"
```

---

## Task 6: Market Feed Prices

**Files:**
- Modify: `core/data/market_feed.py`
- Modify: `tests/core/data/test_market_feed.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/data/test_market_feed.py`:

```python
def test_packet_includes_prices_dict():
    """Prices dict should be in the dispatched packet keyed by symbol."""
    import queue as q
    from unittest.mock import MagicMock, patch
    from core.data.market_feed import MarketFeed

    agent_queue = q.Queue()

    import pandas as pd
    import numpy as np
    mock_df = pd.DataFrame({
        "open": [100.0], "high": [105.0], "low": [99.0],
        "close": [103.5], "volume": [1_000_000]
    })

    with patch("core.data.market_feed.YFinanceClient") as mock_yf_cls, \
         patch("core.data.market_feed.NewsFeed") as mock_news_cls, \
         patch("core.data.market_feed.InstitutionalFeed") as mock_inst_cls, \
         patch("core.data.market_feed.TechnicalAnalyzer") as mock_tech_cls, \
         patch("core.data.market_feed.SignalAggregator") as mock_agg_cls, \
         patch("core.data.market_feed._get_session", return_value="regular"):
        mock_yf_cls.return_value.fetch_ohlcv.return_value = mock_df
        mock_tech_cls.return_value.analyze.return_value = []
        mock_agg_cls.return_value.rank.return_value = []
        mock_news_cls.return_value.fetch.return_value = []
        mock_inst_cls.return_value.fetch_insider_trades.return_value = []

        feed = MarketFeed([agent_queue], watchlist=["AAPL"])
        feed.fetch_and_dispatch()

    packet = agent_queue.get_nowait()
    assert "prices" in packet
    assert "AAPL" in packet["prices"]
    assert packet["prices"]["AAPL"] == 103.5
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/core/data/test_market_feed.py::test_packet_includes_prices_dict -v
```

Expected: FAIL — packet has no `prices` key.

- [ ] **Step 3: Implement**

In `core/data/market_feed.py`, modify `fetch_and_dispatch`. Replace the OHLCV loop:

```python
        # Technical signals
        raw_signals = []
        for symbol in self._watchlist:
            try:
                df = self._yf.fetch_ohlcv(symbol, period="3mo")
                raw_signals.extend(self._tech.analyze(df, symbol))
            except Exception:
                continue
        ranked = self._agg.rank(raw_signals)
```

with:

```python
        # Technical signals + last prices
        raw_signals = []
        prices: dict[str, float] = {}
        for symbol in self._watchlist:
            try:
                df = self._yf.fetch_ohlcv(symbol, period="3mo")
                if not df.empty:
                    prices[symbol] = float(df["close"].iloc[-1])
                raw_signals.extend(self._tech.analyze(df, symbol))
            except Exception:
                continue
        ranked = self._agg.rank(raw_signals)
```

Then add `"prices": prices` to the packet dict:

```python
        packet = {
            "session": session,
            "signals": ranked[:10],
            "news": [{"title": a["title"], "source": a.get("source", {}).get("name")}
                     for a in news[:10]],
            "institutional": inst_signals[:10],
            "prices": prices,
        }
```

- [ ] **Step 4: Run tests**

```
pytest tests/core/data/test_market_feed.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/data/market_feed.py tests/core/data/test_market_feed.py
git commit -m "feat: add prices dict to market feed dispatch packet"
```

---

## Task 7: Agent Overhaul

**Files:**
- Modify: `agents/agent.py`
- Modify: `tests/agents/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Replace `tests/agents/test_agent.py` entirely:

```python
import queue
import time
from unittest.mock import MagicMock, patch
from agents.agent import Agent, AgentConfig
from agents.peer_exchange import PeerExchange
from core.state.persistence import StateStore, Position


def _make_agent(tmp_dir, peer_exchange=None, decision=None):
    config = AgentConfig(
        agent_id="agent_a",
        session="regular",
        base_capital=50000.0,
    )
    mock_claude = MagicMock()
    if decision is None:
        decision = MagicMock(
            action="hold", symbol=None, confidence=0.3,
            position_size_pct=0, reasoning="no signal",
            signals_used=[], skip_reason="low confidence",
            bull_case="", bear_case="",
        )
    mock_claude.decide.return_value = decision
    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {"cash": 50000.0, "positions": []}
    mock_schwab.get_quote.return_value = {"lastPrice": 150.0}
    data_queue = queue.Queue()
    data_queue.put({
        "signals": [], "news": [], "institutional": [],
        "session": "regular", "prices": {},
    })
    return Agent(config, mock_claude, mock_schwab,
                 data_queue=data_queue, expertise_dir=tmp_dir,
                 db_dir=tmp_dir, peer_exchange=peer_exchange)


def test_agent_runs_one_cycle(tmp_dir):
    agent = _make_agent(tmp_dir)
    agent.run_cycle()  # should not raise


def test_agent_hold_does_not_execute(tmp_dir):
    agent = _make_agent(tmp_dir)
    agent.run_cycle()
    agent._schwab.place_order.assert_not_called()


def test_agent_drains_peer_insights_at_reuse(tmp_dir):
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    insight = {
        "from_agent": "agent_b", "event": "entry",
        "trade_record": {
            "trade_id": "t_b_001", "symbol": "MSFT", "direction": "long",
            "entry": 400.0, "exit": None, "pnl_pct": None,
            "signals_used": ["volume_spike"], "outcome": None,
        },
        "reasoning": "strong volume", "bull_case": "breakout", "bear_case": "risky",
        "outcome": "open", "pnl_pct": 0.0, "duration": "0m",
    }
    ex.publish("agent_b", insight)

    agent = _make_agent(tmp_dir, peer_exchange=ex)
    agent._improve.run_peer_learning = MagicMock()
    agent.run_cycle()

    agent._improve.run_peer_learning.assert_called_once()
    call_arg = agent._improve.run_peer_learning.call_args[0][0]
    assert call_arg["trade_record"]["symbol"] == "MSFT"


def test_close_position_places_sell_and_logs(tmp_dir):
    agent = _make_agent(tmp_dir)
    # Save an open long position
    pos = Position("AAPL", "long", 180.0, stop_loss=176.4,
                   trailing_stop=177.3, quantity=10,
                   entry_time="2026-03-28T13:00:00+00:00")
    agent._store.save_position(pos)

    agent.close_position("AAPL", exit_price=185.0, trigger_reason="trailing_stop")

    agent._schwab.place_order.assert_called_once_with(
        symbol="AAPL", action="sell", quantity=10)
    assert agent._store.get_position("AAPL") is None


def test_close_position_accumulates_round_pnl(tmp_dir):
    agent = _make_agent(tmp_dir)
    agent._store.update_round_pnl(100.0)  # existing P&L
    pos = Position("AAPL", "long", 180.0, stop_loss=176.4,
                   trailing_stop=177.3, quantity=10,
                   entry_time="2026-03-28T13:00:00+00:00")
    agent._store.save_position(pos)

    agent.close_position("AAPL", exit_price=185.0, trigger_reason="stop_loss")

    new_pnl = agent._store.get_round_pnl()
    assert new_pnl > 100.0  # 100 + gain from AAPL trade


def test_close_position_guard_on_missing_position(tmp_dir):
    """Should not raise if position already removed."""
    agent = _make_agent(tmp_dir)
    agent.close_position("UNKNOWN", exit_price=100.0, trigger_reason="stop_loss")
    agent._schwab.place_order.assert_not_called()


def test_stop_triggered_calls_close_position(tmp_dir):
    agent = _make_agent(tmp_dir)
    pos = Position("AAPL", "long", 180.0, stop_loss=176.4,
                   trailing_stop=177.3, quantity=10,
                   entry_time="2026-03-28T13:00:00+00:00")
    agent._store.save_position(pos)
    # Also save to tracker's store (same instance via shared store)

    data_queue = queue.Queue()
    data_queue.put({
        "signals": [], "news": [], "institutional": [],
        "session": "regular",
        "prices": {"AAPL": 175.0},  # below stop_loss of 176.4
    })
    agent._queue = data_queue
    agent.close_position = MagicMock()
    agent.run_cycle()

    agent.close_position.assert_called_once()
    call_kwargs = agent.close_position.call_args
    assert call_kwargs[1]["symbol"] == "AAPL" or call_kwargs[0][0] == "AAPL"


def test_entry_insight_published_to_exchange(tmp_dir):
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")

    buy_decision = MagicMock(
        action="buy", symbol="NVDA", confidence=0.82,
        position_size_pct=3.0, reasoning="breakout",
        signals_used=["volume_spike"], skip_reason=None,
        bull_case="strong volume", bear_case="market weak",
    )
    agent = _make_agent(tmp_dir, peer_exchange=ex, decision=buy_decision)

    # Mock risk gate to approve
    agent._risk.check = MagicMock(return_value=MagicMock(approved=True, reason=""))
    agent.run_cycle()

    received = ex.drain("agent_b")
    assert len(received) == 1
    assert received[0]["event"] == "entry"
    assert received[0]["trade_record"]["symbol"] == "NVDA"
    assert received[0]["bull_case"] == "strong volume"
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/agents/test_agent.py -v
```

Expected: some pass (existing), new ones FAIL.

- [ ] **Step 3: Implement new agent.py**

Replace `agents/agent.py` entirely:

```python
import queue
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agents.expertise_manager import ExpertiseManager
from agents.peer_exchange import PeerExchange
from agents.self_improve import SelfImproveOrchestrator
from core.decision.prompt_builder import build_decision_prompt
from core.execution.risk_gate import RiskGate, RiskConfig
from core.risk.position_tracker import PositionTracker
from core.state.persistence import StateStore, Position
from core.logger import get_logger
from config import settings


@dataclass
class AgentConfig:
    agent_id: str
    session: str
    base_capital: float


class Agent:
    def __init__(self, config: AgentConfig, claude_client, schwab_client,
                 data_queue: queue.Queue,
                 expertise_dir: Path | None = None,
                 db_dir: Path | None = None,
                 log_dir: Path | None = None,
                 peer_exchange: PeerExchange | None = None):
        self._cfg = config
        self._claude = claude_client
        self._schwab = schwab_client
        self._queue = data_queue
        self._exchange = peer_exchange
        self._mgr = ExpertiseManager(config.agent_id, expertise_dir)
        self._store = StateStore(config.agent_id, db_dir) if db_dir \
            else StateStore(config.agent_id)
        self._tracker = PositionTracker(
            trailing_pct=settings.get("risk", "trailing_stop_pct"),
            agent_id=config.agent_id,
            store=self._store,
        )
        self._improve = SelfImproveOrchestrator(self._mgr, claude_client)
        self._logger = get_logger(config.agent_id, "trades", log_dir) \
            if log_dir else get_logger(config.agent_id, "trades")
        self._risk = RiskGate(RiskConfig(
            max_position_size_pct=settings.get("risk", "max_position_size_pct"),
            daily_loss_limit_pct=settings.get("risk", "daily_loss_limit_pct"),
            max_concurrent_positions=settings.get("risk", "max_concurrent_positions"),
            confidence_threshold_regular=settings.get(
                "risk", "confidence_threshold_regular"),
            confidence_threshold_extended=settings.get(
                "risk", "confidence_threshold_extended"),
            open_blackout_minutes=settings.get("risk", "open_blackout_minutes"),
        ))

    # --- REUSE → ACT ---
    def run_cycle(self) -> None:
        try:
            market_data = self._queue.get_nowait()
        except queue.Empty:
            return

        prices = market_data.get("prices", {})

        # Drain and process peer insights before loading expertise
        if self._exchange:
            for insight in self._exchange.drain(self._cfg.agent_id):
                self._improve.run_peer_learning(insight)

        # REUSE: load expertise after peer learning has updated YAML files
        expertise = self._mgr.load_all()

        # Check stops and close triggered positions
        triggered = self._tracker.check_stops(prices)
        for symbol, info in triggered.items():
            self.close_position(symbol, info["trigger_price"], info["reason"])

        # Advance trailing stops for remaining positions
        self._tracker.update_stops(prices)

        # Build evolved risk params from trade expertise
        evolved = expertise.get("trade", {}).get("evolved_parameters", {})
        session = market_data.get("session", "regular")

        # Gather portfolio state from Schwab
        account = self._schwab.get_account_info()
        cash = account.get("cash", self._cfg.base_capital)
        open_positions = self._store.get_positions()
        round_pnl = self._store.get_round_pnl()
        daily_pnl_pct = (round_pnl / self._cfg.base_capital) * 100

        prompt = build_decision_prompt(
            session=session,
            expertise=expertise,
            signals=market_data.get("signals", []),
            news=market_data.get("news", []),
            institutional=market_data.get("institutional", []),
            open_positions=[{"symbol": p.symbol, "direction": p.direction,
                              "entry": p.entry_price} for p in open_positions],
            cash=cash,
            daily_pnl=round_pnl,
            daily_pnl_pct=daily_pnl_pct,
            daily_loss_remaining=(self._cfg.base_capital *
                                   settings.get("risk", "daily_loss_limit_pct") / 100
                                   + round_pnl),
        )

        decision = self._claude.decide("", prompt)

        if decision.action == "hold":
            self._logger.log({"event": "hold", "reason": decision.skip_reason,
                               "confidence": decision.confidence})
            return

        # ACT: risk gate
        has_inst = len(market_data.get("institutional", [])) > 0
        risk_result = self._risk.check(
            action=decision.action,
            confidence=decision.confidence,
            position_size_pct=decision.position_size_pct,
            session=session,
            open_positions=len(open_positions),
            portfolio_value=cash,
            daily_pnl_pct=daily_pnl_pct,
            institutional_signal_present=has_inst,
            current_time=datetime.now(timezone.utc),
        )

        if not risk_result.approved:
            self._logger.log({"event": "risk_blocked", "reason": risk_result.reason,
                               "action": decision.action, "symbol": decision.symbol})
            return

        self._execute(decision, cash, evolved)

    def close_position(self, symbol: str, exit_price: float,
                       trigger_reason: str) -> None:
        pos = self._store.get_position(symbol)
        if pos is None:
            self._logger.log({"event": "close_position_not_found", "symbol": symbol})
            return

        # Place exit order with broker
        exit_action = "sell" if pos.direction == "long" else "cover"
        self._schwab.place_order(symbol=symbol, action=exit_action,
                                  quantity=pos.quantity)

        # Calculate P&L
        if pos.direction == "long":
            pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
        else:
            pnl_pct = ((pos.entry_price - exit_price) / pos.entry_price) * 100
        pnl_dollars = (pnl_pct / 100) * (pos.entry_price * pos.quantity)

        # Calculate duration
        if pos.entry_time:
            try:
                entry_dt = datetime.fromisoformat(pos.entry_time)
                delta = datetime.now(timezone.utc) - entry_dt
                duration = f"{int(delta.total_seconds() / 60)}m"
            except ValueError:
                duration = "unknown"
        else:
            duration = "unknown"

        outcome = "win" if pnl_pct > 0 else "loss"
        trade_record = {
            "trade_id": f"t_{self._cfg.agent_id}_{symbol}_{int(time.time())}",
            "symbol": symbol,
            "direction": pos.direction,
            "entry": pos.entry_price,
            "exit": exit_price,
            "pnl_pct": round(pnl_pct, 4),
            "signals_used": [],
            "outcome": outcome,
            "claude_confidence": None,
        }

        # Accumulate round P&L
        self._store.update_round_pnl(self._store.get_round_pnl() + pnl_dollars)

        # LEARN: self-improve with real outcome
        self._improve.run(
            trade_record=trade_record,
            original_reasoning="",
            outcome=outcome,
            pnl_pct=pnl_pct,
            duration=duration,
        )

        # Publish close insight to exchange
        if self._exchange:
            self._exchange.publish(self._cfg.agent_id, {
                "from_agent": self._cfg.agent_id,
                "event": "close",
                "trade_record": trade_record,
                "reasoning": "",
                "bull_case": "",
                "bear_case": "",
                "outcome": outcome,
                "pnl_pct": pnl_pct,
                "duration": duration,
            })

        self._store.remove_position(symbol)
        self._logger.log({
            "event": "position_closed",
            "symbol": symbol,
            "pnl_pct": round(pnl_pct, 4),
            "reason": trigger_reason,
        })

    def _execute(self, decision, cash: float, evolved: dict) -> None:
        size_pct = min(decision.position_size_pct,
                       evolved.get("max_position_size_pct", 5.0))

        quote = self._schwab.get_quote(decision.symbol)
        price = quote.get("lastPrice") or quote.get("mark") or 1.0
        quantity = max(1, int((cash * size_pct / 100) / price))

        stop_pct = evolved.get("stop_loss_pct", 2.0)
        trailing_pct = evolved.get("trailing_stop_pct", 1.5)
        stop_price = round(price * (1 - stop_pct / 100), 2) \
            if decision.action in ("buy",) else \
            round(price * (1 + stop_pct / 100), 2)

        self._schwab.place_order(
            symbol=decision.symbol,
            action=decision.action,
            quantity=quantity,
        )

        direction = "long" if decision.action == "buy" else "short"
        entry_time = datetime.now(timezone.utc).isoformat()
        self._store.save_position(
            Position(
                symbol=decision.symbol,
                direction=direction,
                entry_price=price,
                stop_loss=stop_price,
                trailing_stop=round(
                    price * (1 - trailing_pct / 100) if direction == "long"
                    else price * (1 + trailing_pct / 100),
                    2
                ),
                quantity=quantity,
                entry_time=entry_time,
            )
        )

        trade_record = {
            "trade_id": f"t_{self._cfg.agent_id}_{int(time.time())}",
            "symbol": decision.symbol,
            "direction": direction,
            "entry": price,
            "exit": None,
            "pnl_pct": None,
            "signals_used": decision.signals_used,
            "outcome": None,
            "claude_confidence": decision.confidence,
            "bull_case": decision.bull_case,
            "bear_case": decision.bear_case,
        }

        self._logger.log({
            "event": "trade_placed", **trade_record,
            "reasoning": decision.reasoning,
        })

        # LEARN: trigger self-improve immediately after placing trade
        self._improve.run(
            trade_record=trade_record,
            original_reasoning=decision.reasoning,
            outcome="open",
            pnl_pct=0.0,
            duration="0m",
        )

        # Publish entry insight to peer exchange
        if self._exchange:
            self._exchange.publish(self._cfg.agent_id, {
                "from_agent": self._cfg.agent_id,
                "event": "entry",
                "trade_record": trade_record,
                "reasoning": decision.reasoning,
                "bull_case": decision.bull_case,
                "bear_case": decision.bear_case,
                "outcome": "open",
                "pnl_pct": 0.0,
                "duration": "0m",
            })
```

- [ ] **Step 4: Run tests**

```
pytest tests/agents/test_agent.py -v
```

Expected: all 9 pass.

- [ ] **Step 5: Commit**

```bash
git add agents/agent.py tests/agents/test_agent.py
git commit -m "feat: agent overhaul — close_position, peer exchange wiring, PositionTracker integration"
```

---

## Task 8: main.py Wiring + Full Suite

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Read main.py to find Agent construction**

Open `main.py` and locate where `Agent(config_a, ...)` and `Agent(config_b, ...)` are constructed (around line 80-110).

- [ ] **Step 2: Add PeerExchange import**

Add to the imports at the top of `main.py`:

```python
from agents.peer_exchange import PeerExchange
```

- [ ] **Step 3: Wire PeerExchange before agent construction**

In the `main()` function, find where agents are constructed and insert before them:

```python
    exchange = PeerExchange()
    exchange.register("agent_a")
    exchange.register("agent_b")
```

Then pass `peer_exchange=exchange` to both Agent constructors. For example:

```python
    agent_a = Agent(config_a, claude_a, schwab, queue_a,
                    peer_exchange=exchange)
    agent_b = Agent(config_b, claude_b, schwab, queue_b,
                    peer_exchange=exchange)
```

- [ ] **Step 4: Run the full test suite**

```
pytest tests/ -v
```

Expected: **all 37+ tests pass**, 0 failures.

If any tests fail, fix before committing. Do not skip.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: wire PeerExchange into main.py — agents now share trade insights"
```

---

## Final: Push + Merge to main

- [ ] **Step 1: Push feature branch**

```bash
git push origin feature/phase1-implementation
```

- [ ] **Step 2: Merge to main**

```bash
git checkout main
git merge feature/phase1-implementation --no-ff -m "feat: debate self-debate + peer exchange agentic learning

- Structured bull/bear case in every Claude trading decision
- PeerExchange: agents share entry and close insights via in-memory queue
- Peer learning prompt: agents update expertise from competitor trades
- PositionTracker integrated into Agent with shared SQLite store
- close_position: broker exit order + P&L accounting + self-improve on close
- Market feed now includes prices dict for stop detection
- Position.entry_time for duration calculation
- 4-week competition round duration (was 2 weeks)"
git push origin main
git checkout feature/phase1-implementation
```
