# Debate + Peer Exchange Design

**Date:** 2026-03-28
**Status:** Approved

## Goal

Add two agentic learning improvements to Tragent:

1. **Structured self-debate** — force Claude to articulate a bull case and bear case before every trading decision; both fields persisted and fed into the LEARN phase
2. **Post-trade peer exchange** — after each trade (at entry and at close), agents share insights via a shared in-memory queue; the receiving agent runs a peer learning prompt to update its own expertise without blindly copying the sender

---

## 1. Structured Self-Debate

### Changes to `core/decision/prompt_builder.py`

`build_decision_prompt` adds one sentence to the `## Task` section:

> "Before deciding, articulate the strongest bull and bear case for the leading candidate. Let the better argument win."

The `## Response Format` block gains two new required fields:

```json
{
  "bull_case": "strongest argument FOR this trade",
  "bear_case": "strongest argument AGAINST this trade",
  "action": "buy|sell|short|cover|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "which case won and why",
  "signals_used": [],
  "skip_reason": "if hold, why"
}
```

### Changes to `core/decision/claude_client.py`

**`TradeDecision` dataclass** gains two new fields with defaults (existing tests unaffected):
```python
bull_case: str = ""
bear_case: str = ""
```

**`_parse_response`** extracts them:
```python
bull_case=data.get("bull_case", ""),
bear_case=data.get("bear_case", ""),
```

`max_tokens` for `decide()` is raised from 512 to 768 to accommodate the two new fields.

### Downstream propagation

- `bull_case` and `bear_case` are included in the trade log entry in `agent.py`
- Both are passed into `build_self_improve_prompt` so the LEARN phase can evaluate which argument proved correct in hindsight
- Both are included in peer exchange insights

### No extra LLM calls — zero latency increase beyond prompt length

---

## 2. PeerExchange Class

### New file: `agents/peer_exchange.py`

Agent IDs are registered explicitly via `register(agent_id)` before threads start. `main.py` calls `register` for each agent after instantiating `PeerExchange` and before constructing agents. `publish` and `drain` raise `KeyError` for unregistered IDs — fail-fast, not silent.

```python
class PeerExchange:
    def register(self, agent_id: str) -> None
        # creates a queue.Queue inbox for this agent_id

    def publish(self, from_agent_id: str, insight: dict) -> None
        # puts insight into every registered inbox except from_agent_id's own

    def drain(self, for_agent_id: str) -> list[dict]
        # non-blocking: returns and clears all items in for_agent_id's inbox
```

Thread-safe: `queue.Queue` is thread-safe by default; no additional locking needed.

### Insight shape

```python
{
    "from_agent":   "agent_a",
    "event":        "entry" | "close",
    "trade_record": { ... },     # full trade record dict
    "reasoning":    "...",
    "bull_case":    "...",
    "bear_case":    "...",
    "outcome":      "open" | "win" | "loss",
    "pnl_pct":      0.0,
    "duration":     "12m",
}
```

### Instantiation in `main.py`

```python
exchange = PeerExchange()
exchange.register("agent_a")
exchange.register("agent_b")
agent_a = Agent(config_a, ..., peer_exchange=exchange)
agent_b = Agent(config_b, ..., peer_exchange=exchange)
```

`peer_exchange` defaults to `None` — agents without it run in isolation (backward-compatible).

---

## 3. Prices in Market Packet

`PositionTracker.check_stops` and `update_stops` require `prices: dict[str, float]`. The current packet has no `prices` key.

### Change to `core/data/market_feed.py`

During the existing per-symbol OHLCV loop in `fetch_and_dispatch`, collect the last close price for each symbol that successfully fetches data:

```python
prices = {}
for symbol in self._watchlist:
    try:
        df = self._yf.fetch_ohlcv(symbol, period="3mo")
        if not df.empty:
            prices[symbol] = float(df["close"].iloc[-1])
        raw_signals.extend(self._tech.analyze(df, symbol))
    except Exception:
        continue
```

Add `"prices": prices` to the packet. No extra network calls — the OHLCV data is already fetched in this loop. If a symbol fails to fetch, it simply won't appear in `prices` and stop checks for that symbol are skipped silently (consistent with existing error-handling pattern).

---

## 4. SQLite Schema Changes (`core/state/persistence.py`)

### New `entry_time` column on `positions` table

`Position` dataclass gains a new field:
```python
entry_time: str = ""   # ISO-8601 UTC string; default "" for crash-recovery safety
```

`save_position` writes it; `get_positions` and `get_position` read it.

**Schema migration** — `_create_tables` adds an explicit migration block after the `CREATE TABLE IF NOT EXISTS` call:
```python
try:
    self._conn.execute(
        "ALTER TABLE positions ADD COLUMN entry_time TEXT DEFAULT ''")
    self._conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists — safe to ignore
```

This handles existing databases without dropping data. New databases get the column at creation via the `CREATE TABLE` statement (which is updated to include `entry_time TEXT DEFAULT ''`).

### New `get_position` method

`close_position` needs to look up a single position by symbol. `StateStore` gains:

```python
def get_position(self, symbol: str) -> Position | None:
    row = self._conn.execute(
        "SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
    return Position(*row) if row else None
```

### `update_round_pnl` accumulation

`update_round_pnl` currently does `INSERT OR REPLACE` with the value as-is — it sets the total, not adds to it. `close_position` in `agent.py` must read the current value before writing:

```python
current_pnl = self._store.get_round_pnl()
self._store.update_round_pnl(current_pnl + pnl_dollars)
```

`update_round_pnl` itself is not changed — the accumulation is the caller's responsibility.

---

## 5. Agent Changes (`agents/agent.py`)

### Constructor additions

```python
peer_exchange: PeerExchange | None = None
```

Also constructs a `PositionTracker`, passing `self._store` (shared instance, no SQLite contention):
```python
self._tracker = PositionTracker(
    trailing_pct=settings.get("risk", "trailing_stop_pct"),
    agent_id=config.agent_id,
    store=self._store,
)
```

### `run_cycle()` revised execution order

```
1. Get market_data from queue (return early if empty)
2. Extract prices = market_data.get("prices", {})
3. Drain peer insights → run_peer_learning for each (updates YAML)
4. REUSE: load_all() — runs AFTER peer learning so expertise is current
5. Check stops: triggered = tracker.check_stops(prices)
   → for symbol, info in triggered.items():
       close_position(symbol, info["trigger_price"], info["reason"])
   (exit_price is info["trigger_price"] — the stop level that was breached.
    Slippage vs. actual fill is accepted as a known limitation at this stage.)
6. Update stops: tracker.update_stops(prices)
7. Build decision prompt with freshly loaded expertise
8. Call claude.decide()
9. ACT: risk gate → _execute()
10. LEARN: self_improve.run() triggered inside _execute()
```

### New method `close_position(symbol: str, exit_price: float, trigger_reason: str) -> None`

```
1. pos = self._store.get_position(symbol)
   → if None: log warning and return (guard against double-close)
2. Place exit order: self._schwab.place_order(symbol,
       "sell" if pos.direction == "long" else "cover", pos.quantity)
3. Calculate P&L:
   - long:  pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
   - short: pnl_pct = ((pos.entry_price - exit_price) / pos.entry_price) * 100
   - pnl_dollars = (pnl_pct / 100) * (pos.entry_price * pos.quantity)
4. Calculate duration from pos.entry_time to now
5. Build trade_record with exit, pnl_pct, outcome = "win" if pnl_pct > 0 else "loss"
6. Accumulate round P&L: self._store.update_round_pnl(self._store.get_round_pnl() + pnl_dollars)
7. self._improve.run(trade_record, original_reasoning="", outcome=..., pnl_pct, duration)
8. If exchange: exchange.publish(agent_id, close_insight)
9. self._store.remove_position(symbol)
10. Log {"event": "position_closed", "symbol": ..., "pnl_pct": ..., "reason": trigger_reason}
```

Note: `original_reasoning` for the close self-improve call is `""` — the original reasoning was captured at entry; the close call focuses on outcome only.

### After `_execute` (entry event)

```python
if self._exchange:
    self._exchange.publish(self._cfg.agent_id, {
        "from_agent": self._cfg.agent_id, "event": "entry",
        "trade_record": trade_record,
        "reasoning": decision.reasoning,
        "bull_case": decision.bull_case,
        "bear_case": decision.bear_case,
        "outcome": "open", "pnl_pct": 0.0, "duration": "0m",
    })
```

---

## 6. SQLite Contention Fix (`core/risk/position_tracker.py`)

`PositionTracker.__init__` gains an optional `store` parameter. Existing `agent_id` and `db_dir` parameters are kept for standalone use (e.g., tests that construct `PositionTracker` directly). `store` takes precedence: if provided, it is used directly and `agent_id`/`db_dir` are ignored for storage purposes:

```python
def __init__(self, trailing_pct, agent_id, db_dir=None, store=None):
    self._trailing_pct = trailing_pct
    self.store = store if store is not None else StateStore(agent_id, db_dir)
```

`Agent` passes `self._store` so all reads and writes happen on a single connection within a single agent thread — no concurrent write contention.

---

## 7. New Prompt: `build_peer_learning_prompt`

Added to `core/decision/prompt_builder.py`.

**Signature:**
```python
def build_peer_learning_prompt(
    insight: dict,
    current_yaml: str,
    max_lines: int = 1000,
) -> str
```

**Prompt body:**
```
## Peer Trade Insight (your competitor — do not copy blindly)
Event: {entry|close}
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
- Return the complete updated YAML only, no prose
```

Uses `SELF_IMPROVE_SYSTEM`. Called via `self._claude.self_improve(prompt)` — no new `ClaudeClient` method needed.

### `agents/self_improve.py` change

New method:
```python
def run_peer_learning(self, insight: dict) -> None:
    files_to_update = self._determine_files(insight["trade_record"])
    files_to_update.add("trade")
    for file_name in files_to_update:
        current_yaml = yaml.dump(self._mgr.load(file_name), default_flow_style=False)
        prompt = build_peer_learning_prompt(insight, current_yaml)
        updated_yaml = self._claude.self_improve(prompt)
        try:
            updated_data = yaml.safe_load(updated_yaml)
            if updated_data:
                self._mgr.save(file_name, updated_data)
        except yaml.YAMLError:
            pass
```

**Known constraint:** `_determine_files` routes signals to expertise files via `_SIGNAL_TO_EXPERTISE`. Any signal type not in that map is silently dropped; only `"trade"` is always updated. Implementers must keep `_SIGNAL_TO_EXPERTISE` current as new signal types are added. This is an existing limitation of self-improve, not new to peer learning.

---

## 8. `main.py` Wiring

Changes limited to:
1. Instantiate `PeerExchange` and register agent IDs before constructing agents
2. Pass `peer_exchange` to both agents

Stop detection and close execution are handled entirely inside `agent.run_cycle()`. `main.py` has no knowledge of position tracker or close events.

---

## Files Changed

| File | Change |
|---|---|
| `agents/peer_exchange.py` | **New** — PeerExchange class with register/publish/drain |
| `core/decision/prompt_builder.py` | Add debate instruction + bull_case/bear_case to decision prompt; add `build_peer_learning_prompt` |
| `core/decision/claude_client.py` | Add `bull_case`/`bear_case` to `TradeDecision`; update `_parse_response`; raise `max_tokens` to 768 |
| `agents/agent.py` | Accept exchange; revised run_cycle order; publish at entry; add `close_position()`; own PositionTracker |
| `agents/self_improve.py` | Add `run_peer_learning(insight)` method |
| `core/risk/position_tracker.py` | Accept optional `store` parameter |
| `core/state/persistence.py` | Add `entry_time` to `Position`; schema migration; add `get_position(symbol)` |
| `core/data/market_feed.py` | Add `prices` dict to dispatch packet |
| `main.py` | Instantiate PeerExchange, register IDs, pass to agents |
| `tests/agents/test_peer_exchange.py` | **New** — unit tests for register/publish/drain |
| `tests/agents/test_agent.py` | Extend: peer learning at REUSE, close_position, stop-triggered close |
| `tests/agents/test_self_improve.py` | Extend: run_peer_learning with entry and close insights |
| `tests/core/decision/test_claude_client.py` | Extend: bull_case/bear_case parsed from response |
| `tests/core/risk/test_position_tracker.py` | Extend: shared store parameter |

**Total: 14 files (8 existing modified, 1 new class file, 4 test files extended, 1 test file new)**

---

## Non-Goals

- No persistent exchange log (can be added later if auditability is needed)
- No rate limiting on peer learning calls
- No cross-round peer learning (expertise files carry forward via the seeding mechanism)
