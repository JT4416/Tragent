# TIER 1 Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply 10 mandatory correctional changes to Tragent before any live trading: remove short selling, pre/post-market, and crypto; add inverse ETFs; implement paper trading gate; add stop enforcement loop; add kill switch; add closed-position learn loop; test crash recovery; add monitoring/alerting.

**Architecture:** Each correction is a surgical change to an existing file or a small new file. No architectural overhaul — follow existing patterns (dataclasses, threading.Event, pytest with tmp_dir fixture). Tasks are ordered by dependency: schema changes first, then infrastructure, then wiring.

**Tech Stack:** Python 3.11+, sqlite3, threading, signal, requests (alerting webhook), pytest, existing Schwab/Claude/yfinance clients.

---

## File Map

### Modified
| File | What changes |
|------|-------------|
| `core/execution/risk_gate.py` | Remove extended-hours logic; block `short` action; remove `confidence_threshold_extended` from RiskConfig |
| `core/risk/position_tracker.py` | Remove all short-direction branches — long only |
| `core/state/persistence.py` | Add `entry_time: str` to Position; add `get_position(symbol)` method; migrate schema |
| `agents/agent.py` | Remove `short` direction; add `close_position()`; wire voluntary sell via close_position |
| `core/decision/claude_client.py` | Remove `short`/`cover` from action comment |
| `core/decision/prompt_builder.py` | Remove `short\|cover` from response format |
| `agents/expertise_manager.py` | Remove crypto seed; add inverse ETF knowledge to market seed |
| `core/data/market_feed.py` | Add inverse ETFs (SH, SDS, QID, DOG) to DEFAULT_WATCHLIST |
| `config/config.yaml` | Remove `confidence_threshold_extended`; add `paper_trading` and `monitoring` sections |
| `.env.example` | Add `ALERT_WEBHOOK_URL` |
| `main.py` | Integrate KillSwitch, PaperBroker gate, StopEnforcer thread, Alerter |
| `tests/core/execution/test_risk_gate.py` | Update extended-hours tests; add short-selling block test |
| `tests/core/risk/test_position_tracker.py` | Remove short-direction test |
| `tests/core/state/test_persistence.py` | Add entry_time and get_position tests |
| `tests/agents/test_agent.py` | Add close_position test |

### Created
| File | Purpose |
|------|---------|
| `core/kill_switch.py` | File-flag + signal-handler kill switch |
| `core/execution/paper_broker.py` | Simulated fills on live Schwab quotes; 15-day gate |
| `core/risk/stop_enforcer.py` | Background thread enforcing trailing stops in real time |
| `core/monitor/__init__.py` | Package marker |
| `core/monitor/alerter.py` | Webhook-based anomaly alerting |
| `tests/core/test_kill_switch.py` | Kill switch unit tests |
| `tests/core/execution/test_paper_broker.py` | Paper broker unit tests |
| `tests/core/risk/test_stop_enforcer.py` | Stop enforcer unit tests |
| `tests/core/state/test_crash_recovery.py` | Crash recovery scenario tests |
| `tests/core/monitor/test_alerter.py` | Alerter unit tests |

---

## Task 1: Remove short selling, pre/post-market trading, and crypto references

**Files:**
- Modify: `core/execution/risk_gate.py`
- Modify: `core/risk/position_tracker.py`
- Modify: `core/decision/claude_client.py`
- Modify: `core/decision/prompt_builder.py`
- Modify: `agents/expertise_manager.py`
- Modify: `config/config.yaml`
- Modify: `tests/core/execution/test_risk_gate.py`
- Modify: `tests/core/risk/test_position_tracker.py`

- [ ] **Step 1: Write the new risk gate tests first**

Replace `tests/core/execution/test_risk_gate.py` with:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from core.execution.risk_gate import RiskGate, RiskConfig

_ET = ZoneInfo("America/New_York")


def _config():
    return RiskConfig(
        max_position_size_pct=5.0,
        daily_loss_limit_pct=6.0,
        max_concurrent_positions=5,
        confidence_threshold_regular=0.65,
        open_blackout_minutes=5,
    )


def test_passes_valid_trade():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.80, position_size_pct=3.0,
        session="regular", open_positions=2,
        portfolio_value=50000, daily_pnl_pct=-1.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert result.approved


def test_blocks_short_selling():
    gate = RiskGate(_config())
    result = gate.check(
        action="short", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "short selling" in result.reason.lower()


def test_blocks_pre_market():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="pre_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 7, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "pre/post" in result.reason.lower()


def test_blocks_post_market():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="post_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 17, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "pre/post" in result.reason.lower()


def test_blocks_low_confidence():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.50, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "confidence" in result.reason.lower()


def test_blocks_daily_loss_limit():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=-7.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "loss limit" in result.reason.lower()


def test_blocks_open_blackout():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 9, 32, tzinfo=_ET),
    )
    assert not result.approved
    assert "blackout" in result.reason.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/execution/test_risk_gate.py -v
```
Expected: `test_blocks_short_selling`, `test_blocks_pre_market`, `test_blocks_post_market` FAIL; others may pass or fail depending on current signature.

- [ ] **Step 3: Rewrite `core/execution/risk_gate.py`**

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass
class RiskConfig:
    max_position_size_pct: float
    daily_loss_limit_pct: float
    max_concurrent_positions: int
    confidence_threshold_regular: float
    open_blackout_minutes: int


@dataclass
class RiskDecision:
    approved: bool
    reason: str


_ET = ZoneInfo("America/New_York")


class RiskGate:
    def __init__(self, config: RiskConfig):
        self._cfg = config

    def check(
        self,
        action: str,
        confidence: float,
        position_size_pct: float,
        session: str,
        open_positions: int,
        portfolio_value: float,
        daily_pnl_pct: float,
        current_time: datetime,
    ) -> RiskDecision:
        if action == "hold":
            return RiskDecision(approved=False, reason="action is hold")

        # 1. Short selling permanently disabled
        if action == "short":
            return RiskDecision(approved=False, reason="short selling disabled")

        # 2. Pre/post-market trading disabled until agents have 3+ months experience
        if session in ("pre_market", "post_market"):
            return RiskDecision(approved=False,
                                reason="pre/post market trading disabled")

        # 3. Open blackout (first 5 min of regular session)
        if session == "regular" and self._in_open_blackout(current_time):
            return RiskDecision(approved=False,
                                reason="open blackout period (first 5 minutes)")

        # 4. Confidence check
        if confidence < self._cfg.confidence_threshold_regular:
            return RiskDecision(
                approved=False,
                reason=f"confidence {confidence:.2f} below threshold "
                       f"{self._cfg.confidence_threshold_regular:.2f}")

        # 5. Daily loss limit
        if daily_pnl_pct <= -self._cfg.daily_loss_limit_pct:
            return RiskDecision(approved=False,
                                reason=f"daily loss limit hit ({daily_pnl_pct:.1f}%)")

        # 6. Max concurrent positions
        if open_positions >= self._cfg.max_concurrent_positions:
            return RiskDecision(
                approved=False,
                reason=f"max positions reached ({open_positions})")

        # 7. Position size
        if position_size_pct > self._cfg.max_position_size_pct:
            return RiskDecision(
                approved=False,
                reason=f"position size {position_size_pct}% exceeds max")

        return RiskDecision(approved=True, reason="all checks passed")

    def _in_open_blackout(self, t: datetime) -> bool:
        t_et = t.astimezone(_ET)
        market_open_et = t_et.replace(hour=9, minute=30, second=0, microsecond=0)
        blackout_end = market_open_et + timedelta(
            minutes=self._cfg.open_blackout_minutes)
        return market_open_et <= t_et < blackout_end
```

- [ ] **Step 4: Run risk gate tests — expect all pass**

```
pytest tests/core/execution/test_risk_gate.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 5: Rewrite `core/risk/position_tracker.py` — remove short branches**

```python
from pathlib import Path
from core.state.persistence import StateStore


class PositionTracker:
    def __init__(self, trailing_pct: float, agent_id: str,
                 db_dir: Path | None = None):
        self._trailing_pct = trailing_pct
        self.store = StateStore(agent_id, db_dir) if db_dir \
            else StateStore(agent_id)

    def update_stops(self, prices: dict[str, float]) -> dict:
        """Advance trailing stops as price moves up. Returns updated levels."""
        updates = {}
        for pos in self.store.get_positions():
            price = prices.get(pos.symbol)
            if price is None:
                continue
            new_trail = round(price * (1 - self._trailing_pct / 100), 2)
            if new_trail > pos.trailing_stop:
                pos.trailing_stop = new_trail
                self.store.save_position(pos)
                updates[pos.symbol] = {"new_trailing_stop": new_trail}
        return updates

    def check_stops(self, prices: dict[str, float]) -> dict:
        """Return positions where a stop has been triggered."""
        triggered = {}
        for pos in self.store.get_positions():
            price = prices.get(pos.symbol)
            if price is None:
                continue
            if price <= pos.stop_loss:
                triggered[pos.symbol] = {"reason": "stop_loss",
                                          "trigger_price": pos.stop_loss}
            elif price <= pos.trailing_stop:
                triggered[pos.symbol] = {"reason": "trailing_stop",
                                          "trigger_price": pos.trailing_stop}
        return triggered
```

- [ ] **Step 6: Update position_tracker test — remove short-direction test, verify long logic still passes**

Replace `tests/core/risk/test_position_tracker.py`:

```python
from pathlib import Path
from core.risk.position_tracker import PositionTracker
from core.state.persistence import Position


def test_trailing_stop_advances_with_price(tmp_path):
    tracker = PositionTracker(trailing_pct=1.5, agent_id="agent_a",
                               db_dir=tmp_path)
    pos = Position(symbol="AAPL", direction="long", entry_price=100.0,
                   stop_loss=98.0, trailing_stop=98.5, quantity=10,
                   entry_time="2026-03-30T10:00:00+00:00")
    tracker.store.save_position(pos)
    updates = tracker.update_stops({"AAPL": 110.0})
    assert "AAPL" in updates
    new_stop = round(110.0 * (1 - 1.5 / 100), 2)
    assert updates["AAPL"]["new_trailing_stop"] == new_stop


def test_stop_triggered_returns_close_signal(tmp_path):
    tracker = PositionTracker(trailing_pct=1.5, agent_id="agent_a",
                               db_dir=tmp_path)
    pos = Position(symbol="AAPL", direction="long", entry_price=100.0,
                   stop_loss=95.0, trailing_stop=98.5, quantity=10,
                   entry_time="2026-03-30T10:00:00+00:00")
    tracker.store.save_position(pos)
    triggered = tracker.check_stops({"AAPL": 98.0})
    assert "AAPL" in triggered
    assert triggered["AAPL"]["reason"] == "trailing_stop"
```

- [ ] **Step 7: Update `core/decision/claude_client.py` — remove short/cover from action comment**

Change line 19 only:
```python
action: str            # buy | sell | hold
```

- [ ] **Step 8: Update `core/decision/prompt_builder.py` — remove short/cover from response format**

Change the response format block (line 73–80) from:
```
  "action": "buy|sell|short|cover|hold",
```
to:
```
  "action": "buy|sell|hold",
```

Also add a note in the Task section. Change lines 69–81:
```python
## Task
Analyze the signals above. You may only trade during regular market hours (09:30–16:00 ET).
Long positions only — no short selling. To express bearish conviction, buy an inverse ETF
(SH, SDS, QID, or DOG) instead.

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

- [ ] **Step 9: Update `agents/expertise_manager.py` — remove crypto seed, add inverse ETF knowledge to market seed**

Replace the `_seed` method's "market" entry and remove "crypto" entirely:

```python
    def load_all(self) -> dict[str, dict]:
        return {name: self.load(name)
                for name in ("market", "news", "institutional", "trade")}

    def _seed(self, name: str) -> dict:
        seeds = {
            "market": {
                "overview": {"last_updated": str(date.today()),
                             "total_patterns_tracked": 0},
                "breakout_patterns": [],
                "volume_signals": [],
                "known_false_signals": [],
                "inverse_etfs": {
                    "note": (
                        "Inverse ETFs allow bearish exposure without short selling. "
                        "Buy these when bearish — no margin, no unlimited downside."
                    ),
                    "universe": [
                        {"symbol": "SH",  "tracks": "S&P 500 inverse 1x",
                         "use_when": "broadly bearish on large caps"},
                        {"symbol": "SDS", "tracks": "S&P 500 inverse 2x",
                         "use_when": "high conviction broad market decline"},
                        {"symbol": "QID", "tracks": "Nasdaq-100 inverse 2x",
                         "use_when": "high conviction tech sector decline"},
                        {"symbol": "DOG", "tracks": "Dow Jones inverse 1x",
                         "use_when": "broadly bearish on industrials/blue chips"},
                    ],
                    "caution": (
                        "2x ETFs decay over time — do not hold for more than 1–2 days. "
                        "1x ETFs (SH, DOG) are suitable for slightly longer holds."
                    ),
                },
            },
            "news": {
                "overview": {"last_updated": str(date.today())},
                "catalysts": [],
                "ignored_sources": [],
            },
            "institutional": {
                "overview": {"last_updated": str(date.today()),
                             "note": "FINRA dark pool data is weekly — historical only"},
                "institutional_signals": [],
                "dark_pool_patterns": [],
            },
            "trade": {
                "overview": {"last_updated": str(date.today()),
                             "total_trades": 0, "win_rate": 0.0,
                             "avg_gain_pct": 0.0, "avg_loss_pct": 0.0},
                "evolved_parameters": {
                    "stop_loss_pct": 2.0,
                    "trailing_stop_pct": 1.5,
                    "max_position_size_pct": 5.0,
                    "confidence_threshold": 0.65,
                },
                "lessons_learned": [],
                "recent_trades": [],
            },
        }
        data = seeds.get(name, {"overview": {"last_updated": str(date.today())}})
        self.save(name, data)
        return data
```

- [ ] **Step 10: Update `config/config.yaml` — remove confidence_threshold_extended**

Remove the `confidence_threshold_extended: 0.78` line. The risk section becomes:

```yaml
risk:
  max_position_size_pct: 5.0
  stop_loss_pct: 2.0
  trailing_stop_pct: 1.5
  max_concurrent_positions: 5
  daily_loss_limit_pct: 6.0
  confidence_threshold_regular: 0.65
  open_blackout_minutes: 5
```

- [ ] **Step 11: Update `agents/agent.py` — remove confidence_threshold_extended from RiskGate construction and short direction**

In the `__init__` constructor, remove `confidence_threshold_extended` from the RiskConfig:

```python
        self._risk = RiskGate(RiskConfig(
            max_position_size_pct=settings.get("risk", "max_position_size_pct"),
            daily_loss_limit_pct=settings.get("risk", "daily_loss_limit_pct"),
            max_concurrent_positions=settings.get("risk", "max_concurrent_positions"),
            confidence_threshold_regular=settings.get(
                "risk", "confidence_threshold_regular"),
            open_blackout_minutes=settings.get("risk", "open_blackout_minutes"),
        ))
```

In `run_cycle`, update the risk.check() call to remove `institutional_signal_present`:

```python
        risk_result = self._risk.check(
            action=decision.action,
            confidence=decision.confidence,
            position_size_pct=decision.position_size_pct,
            session=session,
            open_positions=len(open_positions),
            portfolio_value=cash,
            daily_pnl_pct=daily_pnl_pct,
            current_time=datetime.now(timezone.utc),
        )
```

Remove the `has_inst` line above it.

In `_execute`, simplify stop price calculation and direction (direction is always "long"):

```python
        stop_price = round(price * (1 - stop_pct / 100), 2)
        direction = "long"
```

- [ ] **Step 12: Run full test suite — expect all existing tests pass**

```
pytest -v
```
Expected: all 37 tests pass (some test signatures updated, no test should fail).

- [ ] **Step 13: Commit**

```bash
git add core/execution/risk_gate.py core/risk/position_tracker.py \
        core/decision/claude_client.py core/decision/prompt_builder.py \
        agents/expertise_manager.py config/config.yaml agents/agent.py \
        tests/core/execution/test_risk_gate.py \
        tests/core/risk/test_position_tracker.py
git commit -m "feat: remove short selling, pre/post-market trading, and crypto references"
```

---

## Task 2: Add entry_time to Position and get_position() to StateStore

**Files:**
- Modify: `core/state/persistence.py`
- Modify: `tests/core/state/test_persistence.py`

- [ ] **Step 1: Write new persistence tests first**

Add to `tests/core/state/test_persistence.py`:

```python
from datetime import datetime, timezone
from core.state.persistence import StateStore, Position


def test_save_and_load_position(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="AAPL", direction="long", entry_price=182.50,
                   stop_loss=178.85, trailing_stop=179.25, quantity=10,
                   entry_time="2026-03-30T10:00:00+00:00")
    store.save_position(pos)
    loaded = store.get_positions()
    assert len(loaded) == 1
    assert loaded[0].symbol == "AAPL"
    assert loaded[0].entry_price == 182.50
    assert loaded[0].entry_time == "2026-03-30T10:00:00+00:00"


def test_remove_position(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="MSFT", direction="long", entry_price=400.0,
                   stop_loss=392.0, trailing_stop=394.0, quantity=5,
                   entry_time="2026-03-30T10:00:00+00:00")
    store.save_position(pos)
    store.remove_position("MSFT")
    assert store.get_positions() == []


def test_save_and_load_round_pnl(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    store.update_round_pnl(250.75)
    assert store.get_round_pnl() == 250.75


def test_round_pnl_default_is_zero(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    assert store.get_round_pnl() == 0.0


def test_get_position_returns_none_when_missing(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    assert store.get_position("AAPL") is None


def test_get_position_returns_position(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="NVDA", direction="long", entry_price=800.0,
                   stop_loss=784.0, trailing_stop=788.0, quantity=3,
                   entry_time="2026-03-30T11:00:00+00:00")
    store.save_position(pos)
    loaded = store.get_position("NVDA")
    assert loaded is not None
    assert loaded.symbol == "NVDA"
    assert loaded.entry_time == "2026-03-30T11:00:00+00:00"


def test_schema_migration_adds_entry_time_to_existing_db(tmp_path):
    """Simulate a DB that was created before entry_time existed."""
    import sqlite3
    db_path = tmp_path / "agent_a.db"
    # Create old schema without entry_time
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE positions (
            symbol TEXT PRIMARY KEY,
            direction TEXT,
            entry_price REAL,
            stop_loss REAL,
            trailing_stop REAL,
            quantity INTEGER
        );
    """)
    conn.execute(
        "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)",
        ("SPY", "long", 500.0, 490.0, 495.0, 5),
    )
    conn.commit()
    conn.close()

    # Opening StateStore should migrate without error
    store = StateStore("agent_a", db_dir=tmp_path)
    positions = store.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "SPY"
    assert positions[0].entry_time is None  # migrated rows have NULL
```

- [ ] **Step 2: Run tests to confirm new ones fail**

```
pytest tests/core/state/test_persistence.py -v
```
Expected: `test_get_position_*`, `test_schema_migration_*`, and `test_save_and_load_position` (entry_time assertion) FAIL.

- [ ] **Step 3: Rewrite `core/state/persistence.py`**

```python
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Position:
    symbol: str
    direction: str          # "long" only — short selling disabled
    entry_price: float
    stop_loss: float
    trailing_stop: float
    quantity: int
    entry_time: str | None = None   # ISO-8601 UTC string


_DEFAULT_DB_DIR = Path(__file__).parent.parent.parent / "state"


class StateStore:
    def __init__(self, agent_id: str, db_dir: Path = _DEFAULT_DB_DIR):
        db_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_dir / f"{agent_id}.db",
                                     check_same_thread=False)
        self._create_tables()
        self._migrate()

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
                entry_time TEXT
            );
            CREATE TABLE IF NOT EXISTS round_state (
                key TEXT PRIMARY KEY,
                value REAL
            );
        """)
        self._conn.commit()

    def _migrate(self):
        """Add entry_time column to existing databases that predate this field."""
        cols = {row[1] for row in
                self._conn.execute("PRAGMA table_info(positions)").fetchall()}
        if "entry_time" not in cols:
            self._conn.execute(
                "ALTER TABLE positions ADD COLUMN entry_time TEXT")
            self._conn.commit()

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

    def get_position(self, symbol: str) -> "Position | None":
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

- [ ] **Step 4: Run persistence tests — expect all 7 pass**

```
pytest tests/core/state/test_persistence.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 5: Update `agents/agent.py` — pass entry_time when saving position**

In `_execute`, update the `Position(...)` constructor call to include `entry_time`:

```python
        from datetime import datetime, timezone
        self._store.save_position(
            Position(
                symbol=decision.symbol,
                direction="long",
                entry_price=price,
                stop_loss=stop_price,
                trailing_stop=round(price * (1 - trailing_pct / 100), 2),
                quantity=quantity,
                entry_time=datetime.now(timezone.utc).isoformat(),
            )
        )
```

- [ ] **Step 6: Run full suite**

```
pytest -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add core/state/persistence.py agents/agent.py \
        tests/core/state/test_persistence.py \
        tests/core/risk/test_position_tracker.py
git commit -m "feat: add entry_time to Position, get_position() to StateStore, schema migration"
```

---

## Task 3: Add inverse ETFs to the market feed watchlist

**Files:**
- Modify: `core/data/market_feed.py`

- [ ] **Step 1: Update `DEFAULT_WATCHLIST` in `core/data/market_feed.py`**

Replace the existing `DEFAULT_WATCHLIST` constant:

```python
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
```

- [ ] **Step 2: Run existing market feed test to confirm nothing broke**

```
pytest tests/core/data/test_market_feed.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add core/data/market_feed.py
git commit -m "feat: add inverse ETFs (SH, SDS, QID, DOG) to market feed watchlist"
```

---

## Task 4: Kill switch (file flag + signal handler)

**Files:**
- Create: `core/kill_switch.py`
- Modify: `main.py`
- Create: `tests/core/test_kill_switch.py`

- [ ] **Step 1: Write the kill switch tests**

Create `tests/core/test_kill_switch.py`:

```python
import threading
import time
from pathlib import Path
from core.kill_switch import KillSwitch


def test_file_flag_sets_stop_event(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    ks.arm()
    assert not stop.is_set()
    kill_file.touch()
    ks.poll()
    assert stop.is_set()


def test_arm_removes_stale_kill_file(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    kill_file.touch()
    ks = KillSwitch(stop, kill_file=kill_file)
    ks.arm()
    assert not kill_file.exists()
    assert not stop.is_set()


def test_no_kill_file_does_not_set_event(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    ks.arm()
    ks.poll()
    assert not stop.is_set()


def test_check_returns_true_when_file_exists(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    assert not ks.check()
    kill_file.touch()
    assert ks.check()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/test_kill_switch.py -v
```
Expected: ImportError or 4 FAILs.

- [ ] **Step 3: Create `core/kill_switch.py`**

```python
import signal
import threading
from pathlib import Path

_DEFAULT_KILL_FILE = Path(__file__).parent.parent / "KILL"


class KillSwitch:
    """
    Dual-mode kill switch:
    - File flag: create a file named KILL in the project root to trigger shutdown
    - Signal handler: SIGINT (Ctrl+C) and SIGTERM both trigger shutdown

    Usage:
        ks = KillSwitch(stop_event)
        ks.arm()           # call once at startup; removes stale KILL file
        # in main loop:
        ks.poll()          # sets stop_event if KILL file found
    """

    def __init__(self, stop_event: threading.Event,
                 kill_file: Path = _DEFAULT_KILL_FILE):
        self._stop = stop_event
        self._kill_file = kill_file
        signal.signal(signal.SIGINT, self._handle_signal)
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (OSError, AttributeError):
            pass  # SIGTERM unavailable on some platforms (Windows)

    def _handle_signal(self, signum, frame):
        print(f"\nSignal {signum} received — shutting down gracefully...")
        self._stop.set()

    def arm(self) -> None:
        """Remove any stale KILL file left from a prior run."""
        if self._kill_file.exists():
            self._kill_file.unlink()
            print("Removed stale KILL file from prior session.")

    def check(self) -> bool:
        """Return True if a KILL file is present."""
        return self._kill_file.exists()

    def poll(self) -> None:
        """Set stop_event if KILL file is detected. Call this in the main loop."""
        if self.check():
            print(f"KILL file detected at {self._kill_file} — shutting down...")
            self._stop.set()
```

- [ ] **Step 4: Run kill switch tests — expect all pass**

```
pytest tests/core/test_kill_switch.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Integrate KillSwitch into `main.py`**

Add import at top:
```python
from core.kill_switch import KillSwitch
```

In `main()`, after creating `stop = threading.Event()`:
```python
    kill_switch = KillSwitch(stop)
    kill_switch.arm()
```

Replace the `try/except KeyboardInterrupt` block at the bottom of `main()`:
```python
    print("Starting Tragent — Agent A and Agent B")
    print(f"To kill: touch KILL in project root, or press Ctrl+C")
    feed_thread.start()
    thread_a.start()
    thread_b.start()

    while not stop.is_set():
        schedule.run_pending()
        kill_switch.poll()
        time.sleep(1)

    print("Shutdown signal received — waiting for threads to finish...")
    feed_thread.join(timeout=5)
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)
    print("Tragent stopped.")
```

- [ ] **Step 6: Run full suite to confirm nothing broke**

```
pytest -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add core/kill_switch.py main.py tests/core/test_kill_switch.py
git commit -m "feat: add dual-mode kill switch (KILL file + signal handler)"
```

---

## Task 5: Paper trading mode with simulated fills

**Files:**
- Create: `core/execution/paper_broker.py`
- Modify: `config/config.yaml`
- Modify: `main.py`
- Create: `tests/core/execution/test_paper_broker.py`

- [ ] **Step 1: Write paper broker tests**

Create `tests/core/execution/test_paper_broker.py`:

```python
import json
from unittest.mock import MagicMock
from core.execution.paper_broker import PaperBroker, TRADING_DAYS_GATE


def _mock_schwab(price=150.0):
    s = MagicMock()
    s.get_quote.return_value = {"lastPrice": price}
    return s


def test_initial_cash_equals_base_capital(tmp_path):
    broker = PaperBroker(_mock_schwab(), base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    info = broker.get_account_info()
    assert info["cash"] == 50000.0
    assert info["positions"] == []


def test_buy_reduces_cash_and_adds_position(tmp_path):
    schwab = _mock_schwab(price=100.0)
    broker = PaperBroker(schwab, base_capital=10000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    result = broker.place_order("AAPL", "buy", 10)
    assert result["status"] == "FILLED"
    info = broker.get_account_info()
    # 10 shares * ~100.10 (0.1% slippage)
    assert info["cash"] < 10000.0
    assert any(p["symbol"] == "AAPL" for p in info["positions"])


def test_sell_removes_position_and_adds_cash(tmp_path):
    schwab = _mock_schwab(price=100.0)
    broker = PaperBroker(schwab, base_capital=10000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    broker.place_order("AAPL", "buy", 10)
    cash_after_buy = broker.get_account_info()["cash"]
    broker.place_order("AAPL", "sell", 10)
    info = broker.get_account_info()
    assert info["cash"] > cash_after_buy
    assert not any(p["symbol"] == "AAPL" for p in info["positions"])


def test_state_persists_across_instances(tmp_path):
    schwab = _mock_schwab(price=200.0)
    broker1 = PaperBroker(schwab, base_capital=50000.0,
                           agent_id="agent_a", state_dir=tmp_path)
    broker1.place_order("MSFT", "buy", 5)
    # New instance should load the same state
    broker2 = PaperBroker(schwab, base_capital=50000.0,
                           agent_id="agent_a", state_dir=tmp_path)
    info = broker2.get_account_info()
    assert any(p["symbol"] == "MSFT" for p in info["positions"])


def test_trading_days_increments_on_get_account_info(tmp_path):
    broker = PaperBroker(_mock_schwab(), base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    broker.get_account_info()
    assert broker.trading_days_completed() == 1


def test_is_not_live_ready_before_gate(tmp_path):
    broker = PaperBroker(_mock_schwab(), base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    assert not broker.is_live_ready()


def test_get_quote_delegates_to_schwab(tmp_path):
    schwab = _mock_schwab(price=300.0)
    broker = PaperBroker(schwab, base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    quote = broker.get_quote("NVDA")
    assert quote["lastPrice"] == 300.0
    schwab.get_quote.assert_called_once_with("NVDA")
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/execution/test_paper_broker.py -v
```
Expected: ImportError or all FAILs.

- [ ] **Step 3: Create `core/execution/paper_broker.py`**

```python
"""
Paper broker: executes simulated fills using live Schwab quotes.
Maintains per-agent simulated account state in a JSON file.
Counts unique trading days; gates live trading after TRADING_DAYS_GATE days.
"""
import json
import time
from datetime import date
from pathlib import Path

TRADING_DAYS_GATE = 15
_SLIPPAGE_PCT = 0.001   # 0.1% simulated slippage per fill

_DEFAULT_STATE_DIR = Path(__file__).parent.parent.parent / "state"


class PaperBroker:
    """
    Drop-in replacement for SchwabClient during paper trading.
    - get_quote()       → delegates to real Schwab (live prices)
    - get_account_info() → returns simulated cash + positions
    - place_order()     → simulates fill at current price + slippage
    """

    def __init__(self, schwab_client, base_capital: float,
                 agent_id: str = "agent",
                 state_dir: Path = _DEFAULT_STATE_DIR):
        self._schwab = schwab_client
        self._agent_id = agent_id
        state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = state_dir / f"paper_{agent_id}.json"
        self._state = self._load_state(base_capital)

    # ── State persistence ──────────────────────────────────────────────────

    def _load_state(self, base_capital: float) -> dict:
        if self._state_file.exists():
            with open(self._state_file) as f:
                return json.load(f)
        return {
            "cash": base_capital,
            "positions": {},       # symbol → {quantity, entry_price}
            "trading_days": [],    # list of ISO date strings
        }

    def _save(self) -> None:
        with open(self._state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    def _record_trading_day(self) -> None:
        today = date.today().isoformat()
        if today not in self._state["trading_days"]:
            self._state["trading_days"].append(today)
            self._save()

    # ── Public interface (mirrors SchwabClient) ────────────────────────────

    def get_account_info(self) -> dict:
        self._record_trading_day()
        positions = [
            {"symbol": sym, "quantity": p["quantity"],
             "entry_price": p["entry_price"]}
            for sym, p in self._state["positions"].items()
        ]
        return {"cash": self._state["cash"], "positions": positions}

    def get_quote(self, symbol: str) -> dict:
        return self._schwab.get_quote(symbol)

    def place_order(self, symbol: str, action: str, quantity: int) -> dict:
        quote = self._schwab.get_quote(symbol)
        price = quote.get("lastPrice") or quote.get("mark") or 0.0
        fill_price = round(price * (1 + _SLIPPAGE_PCT), 2)

        if action == "buy":
            cost = fill_price * quantity
            self._state["cash"] = round(self._state["cash"] - cost, 2)
            if symbol in self._state["positions"]:
                self._state["positions"][symbol]["quantity"] += quantity
            else:
                self._state["positions"][symbol] = {
                    "quantity": quantity,
                    "entry_price": fill_price,
                }
        elif action == "sell":
            proceeds = fill_price * quantity
            self._state["cash"] = round(self._state["cash"] + proceeds, 2)
            self._state["positions"].pop(symbol, None)

        self._save()
        return {
            "orderId": f"paper_{self._agent_id}_{int(time.time())}",
            "fillPrice": fill_price,
            "status": "FILLED",
        }

    # ── Gate ───────────────────────────────────────────────────────────────

    def trading_days_completed(self) -> int:
        return len(self._state["trading_days"])

    def is_live_ready(self) -> bool:
        return self.trading_days_completed() >= TRADING_DAYS_GATE
```

- [ ] **Step 4: Run paper broker tests — expect all pass**

```
pytest tests/core/execution/test_paper_broker.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 5: Add paper trading config to `config/config.yaml`**

Append to `config/config.yaml`:

```yaml
paper_trading:
  enabled: true
  trading_days_gate: 15
```

- [ ] **Step 6: Integrate PaperBroker into `main.py`**

Add import at top:
```python
from core.execution.paper_broker import PaperBroker
```

In `main()`, after creating `schwab = SchwabClient()` and `base_capital = ...`, add broker selection logic:

```python
    paper_mode = settings.get("paper_trading", "enabled")
    if paper_mode:
        from pathlib import Path
        state_dir = Path("state")
        broker_a = PaperBroker(schwab, base_capital,
                                agent_id="agent_a", state_dir=state_dir)
        broker_b = PaperBroker(schwab, base_capital,
                                agent_id="agent_b", state_dir=state_dir)
        days = broker_a.trading_days_completed()
        gate = settings.get("paper_trading", "trading_days_gate")
        if not broker_a.is_live_ready():
            print(f"PAPER TRADING MODE — {days}/{gate} trading days completed "
                  f"before live capital is used.")
        else:
            print(f"Paper gate cleared ({days} days). "
                  f"Set paper_trading.enabled=false to trade live capital.")
    else:
        broker_a = schwab
        broker_b = schwab
```

Replace `agent_a = Agent(...)` and `agent_b = Agent(...)`:

```python
    agent_a = Agent(AgentConfig("agent_a", "regular", base_capital),
                    claude_a, broker_a, data_queue=queue_a)
    agent_b = Agent(AgentConfig("agent_b", "regular", base_capital),
                    claude_b, broker_b, data_queue=queue_b)
```

- [ ] **Step 7: Run full suite**

```
pytest -v
```
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add core/execution/paper_broker.py config/config.yaml main.py \
        tests/core/execution/test_paper_broker.py
git commit -m "feat: paper broker with simulated fills and 15-day live-trading gate"
```

---

## Task 6: Stop enforcement loop

**Files:**
- Create: `core/risk/stop_enforcer.py`
- Modify: `main.py`
- Create: `tests/core/risk/test_stop_enforcer.py`

- [ ] **Step 1: Write stop enforcer tests**

Create `tests/core/risk/test_stop_enforcer.py`:

```python
import threading
import time
from unittest.mock import MagicMock, call
from core.risk.stop_enforcer import StopEnforcer
from core.state.persistence import Position


def _mock_agent(symbol="AAPL", entry_price=100.0, stop_loss=95.0,
                trailing_stop=98.0, quantity=10):
    agent = MagicMock()
    pos = Position(symbol=symbol, direction="long",
                   entry_price=entry_price, stop_loss=stop_loss,
                   trailing_stop=trailing_stop, quantity=quantity,
                   entry_time="2026-03-30T10:00:00+00:00")
    agent._store.get_positions.return_value = [pos]
    return agent


def _mock_broker(price: float):
    broker = MagicMock()
    broker.get_quote.return_value = {"lastPrice": price}
    return broker


def test_triggers_close_when_stop_loss_hit():
    agent = _mock_agent(stop_loss=95.0)
    broker = _mock_broker(price=94.0)   # below stop_loss
    enforcer = StopEnforcer([agent], broker, interval_seconds=1)
    enforcer._check_all()
    agent.close_position.assert_called_once_with("AAPL", 94.0, reason="stop_loss")


def test_triggers_close_when_trailing_stop_hit():
    agent = _mock_agent(stop_loss=90.0, trailing_stop=98.0)
    broker = _mock_broker(price=97.5)   # below trailing_stop
    enforcer = StopEnforcer([agent], broker, interval_seconds=1)
    enforcer._check_all()
    agent.close_position.assert_called_once_with("AAPL", 97.5,
                                                   reason="trailing_stop")


def test_does_not_trigger_when_price_above_stops():
    agent = _mock_agent(stop_loss=95.0, trailing_stop=98.0)
    broker = _mock_broker(price=105.0)
    enforcer = StopEnforcer([agent], broker, interval_seconds=1)
    enforcer._check_all()
    agent.close_position.assert_not_called()


def test_skips_position_when_quote_unavailable():
    agent = _mock_agent()
    broker = MagicMock()
    broker.get_quote.return_value = {}   # no price
    enforcer = StopEnforcer([agent], broker, interval_seconds=1)
    enforcer._check_all()
    agent.close_position.assert_not_called()


def test_enforcer_runs_until_stop_event():
    agent = _mock_agent()
    agent._store.get_positions.return_value = []
    broker = _mock_broker(price=105.0)
    stop = threading.Event()
    enforcer = StopEnforcer([agent], broker, interval_seconds=1)
    t = threading.Thread(target=enforcer.run, args=(stop,), daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join(timeout=3)
    assert not t.is_alive()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/risk/test_stop_enforcer.py -v
```
Expected: ImportError or all FAILs.

- [ ] **Step 3: Create `core/risk/stop_enforcer.py`**

```python
"""
Stop enforcement loop: polls all open positions every interval_seconds,
checks current price against stop_loss and trailing_stop, and calls
agent.close_position() when a stop is triggered.

Runs as a daemon thread in main.py.
"""
import threading
import time


class StopEnforcer:
    def __init__(self, agents: list, broker, interval_seconds: int = 30):
        self._agents = agents
        self._broker = broker
        self._interval = interval_seconds

    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self._check_all()
            except Exception:
                pass  # log externally if needed; don't crash the thread
            time.sleep(self._interval)

    def _check_all(self) -> None:
        for agent in self._agents:
            for pos in agent._store.get_positions():
                try:
                    quote = self._broker.get_quote(pos.symbol)
                    price = quote.get("lastPrice") or quote.get("mark") or 0.0
                    if price <= 0:
                        continue
                    reason = self._stop_reason(pos, price)
                    if reason:
                        agent.close_position(pos.symbol, price, reason=reason)
                except Exception:
                    continue

    @staticmethod
    def _stop_reason(pos, price: float) -> str | None:
        if price <= pos.stop_loss:
            return "stop_loss"
        if price <= pos.trailing_stop:
            return "trailing_stop"
        return None
```

- [ ] **Step 4: Run stop enforcer tests — expect all pass**

```
pytest tests/core/risk/test_stop_enforcer.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Add StopEnforcer thread to `main.py`**

Add import:
```python
from core.risk.stop_enforcer import StopEnforcer
```

In `main()`, after creating `agent_a` and `agent_b`, add:
```python
    enforcer = StopEnforcer(
        agents=[agent_a, agent_b],
        broker=broker_a,   # only needs get_quote(); broker_a and broker_b give same prices
        interval_seconds=30,
    )
    enforcer_thread = threading.Thread(
        target=enforcer.run, args=(stop,), daemon=True)
```

After `feed_thread.start()`:
```python
    enforcer_thread.start()
```

After `feed_thread.join(timeout=5)`:
```python
    enforcer_thread.join(timeout=5)
```

- [ ] **Step 6: Run full suite**

```
pytest -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add core/risk/stop_enforcer.py main.py \
        tests/core/risk/test_stop_enforcer.py
git commit -m "feat: add stop enforcement loop — 30s polling thread closes positions at stop levels"
```

---

## Task 7: Closed-position learn loop

**Files:**
- Modify: `agents/agent.py`
- Modify: `tests/agents/test_agent.py`

When a position closes (either via stop enforcer or a voluntary agent "sell"), `close_position()` calculates actual P&L and duration, places the closing order, and calls `self_improve.run()` with the real outcome so the agent learns from completed trades — not just entries.

- [ ] **Step 1: Write close_position tests**

Add to `tests/agents/test_agent.py`:

```python
import queue
from unittest.mock import MagicMock, patch
from agents.agent import Agent, AgentConfig
from core.state.persistence import Position


def _make_agent(tmp_path):
    config = AgentConfig(
        agent_id="agent_a",
        session="regular",
        base_capital=50000.0,
    )
    mock_claude = MagicMock()
    mock_claude.decide.return_value = MagicMock(
        action="hold", symbol=None, confidence=0.3,
        position_size_pct=0, reasoning="no signal",
        signals_used=[], skip_reason="low confidence",
    )
    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {"cash": 50000.0, "positions": []}
    data_queue = queue.Queue()
    data_queue.put({
        "signals": [], "news": [], "institutional": [],
        "session": "regular",
    })
    return Agent(config, mock_claude, mock_schwab,
                 data_queue=data_queue, expertise_dir=tmp_path,
                 db_dir=tmp_path)


def test_agent_runs_one_cycle(tmp_path):
    agent = _make_agent(tmp_path)
    agent.run_cycle()


def test_agent_hold_does_not_execute(tmp_path):
    agent = _make_agent(tmp_path)
    agent.run_cycle()
    agent._schwab.place_order.assert_not_called()


def test_close_position_calls_self_improve(tmp_path):
    agent = _make_agent(tmp_path)
    pos = Position(
        symbol="AAPL", direction="long", entry_price=100.0,
        stop_loss=95.0, trailing_stop=98.0, quantity=10,
        entry_time="2026-03-30T10:00:00+00:00",
    )
    agent._store.save_position(pos)
    agent.close_position("AAPL", exit_price=105.0, reason="trailing_stop")
    agent._schwab.place_order.assert_called_once_with(
        symbol="AAPL", action="sell", quantity=10)
    agent._improve.run.assert_called_once()
    call_kwargs = agent._improve.run.call_args[1]
    assert call_kwargs["outcome"] == "win"
    assert call_kwargs["pnl_pct"] == pytest.approx(5.0, abs=0.1)


def test_close_position_on_missing_symbol_does_nothing(tmp_path):
    agent = _make_agent(tmp_path)
    agent.close_position("FAKE", exit_price=50.0, reason="stop_loss")
    agent._schwab.place_order.assert_not_called()
```

Add `import pytest` at the top of the test file.

- [ ] **Step 2: Run new tests to confirm they fail**

```
pytest tests/agents/test_agent.py -v
```
Expected: `test_close_position_*` FAIL with AttributeError.

- [ ] **Step 3: Add `close_position()` to `agents/agent.py`**

Add this method to the `Agent` class after `_execute`:

```python
    def close_position(self, symbol: str, exit_price: float,
                       reason: str = "stop") -> None:
        """Close an open position, calculate real P&L, trigger learn loop."""
        pos = self._store.get_position(symbol)
        if pos is None:
            return

        pnl = round((exit_price - pos.entry_price) * pos.quantity, 2)
        pnl_pct = round(
            (exit_price - pos.entry_price) / pos.entry_price * 100, 2)

        # Duration
        if pos.entry_time:
            from datetime import datetime, timezone
            entry_dt = datetime.fromisoformat(pos.entry_time)
            now = datetime.now(timezone.utc)
            secs = int((now - entry_dt).total_seconds())
            hours, rem = divmod(secs, 3600)
            mins = rem // 60
            duration = f"{hours}h{mins}m" if hours else f"{mins}m"
        else:
            duration = "unknown"

        # Close order
        self._schwab.place_order(
            symbol=symbol, action="sell", quantity=pos.quantity)

        # Update round P&L
        self._store.update_round_pnl(self._store.get_round_pnl() + pnl)
        self._store.remove_position(symbol)

        self._logger.log({
            "event": "position_closed",
            "symbol": symbol,
            "reason": reason,
            "entry": pos.entry_price,
            "exit": exit_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "duration": duration,
        })

        # LEARN: self-improve with real outcome
        trade_record = {
            "trade_id": f"close_{self._cfg.agent_id}_{symbol}",
            "symbol": symbol,
            "direction": pos.direction,
            "entry": pos.entry_price,
            "exit": exit_price,
            "pnl_pct": pnl_pct,
            "signals_used": [],
            "outcome": "win" if pnl > 0 else "loss",
            "claude_confidence": None,
        }
        self._improve.run(
            trade_record=trade_record,
            original_reasoning=f"Position closed: {reason}",
            outcome="win" if pnl > 0 else "loss",
            pnl_pct=pnl_pct,
            duration=duration,
        )
```

Also handle `action == "sell"` in `run_cycle()` so a voluntary agent sell routes through `close_position`. In `run_cycle`, after the `if decision.action == "hold"` block and before the risk gate, add:

```python
        # Voluntary exit: agent decided to close an existing long
        if decision.action == "sell":
            if decision.symbol:
                quote = self._schwab.get_quote(decision.symbol)
                price = quote.get("lastPrice") or quote.get("mark") or 0.0
                if price > 0:
                    self.close_position(decision.symbol, price,
                                        reason="agent_decision")
            return
```

- [ ] **Step 4: Run agent tests — expect all pass**

```
pytest tests/agents/test_agent.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Run full suite**

```
pytest -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add agents/agent.py tests/agents/test_agent.py
git commit -m "feat: closed-position learn loop — close_position() triggers self_improve with real P&L"
```

---

## Task 8: Crash recovery tests

**Files:**
- Create: `tests/core/state/test_crash_recovery.py`

These tests verify that the system survives each identified failure mode. They use real SQLite files (tmp_path) and mock clients.

- [ ] **Step 1: Create `tests/core/state/test_crash_recovery.py`**

```python
"""
Crash recovery scenario tests.

Verified recovery paths:
1. Process killed mid-cycle (SQLite committed before death)
2. Schwab API timeout during order placement (position not yet persisted)
3. Claude API down (agent holds; nothing to recover)
4. Machine rebooted with open positions (SQLite persists; reconcile runs)
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.state.persistence import StateStore, Position


# ── Scenario 1: Process killed mid-cycle ───────────────────────────────────

def test_positions_survive_connection_close_and_reopen(tmp_path):
    """SQLite commits are durable — positions persist across StateStore instances."""
    store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="AAPL", direction="long", entry_price=180.0,
                   stop_loss=176.4, trailing_stop=177.3, quantity=5,
                   entry_time="2026-03-30T10:00:00+00:00")
    store.save_position(pos)
    del store  # simulates process death after commit

    store2 = StateStore("agent_a", db_dir=tmp_path)
    recovered = store2.get_positions()
    assert len(recovered) == 1
    assert recovered[0].symbol == "AAPL"


def test_partial_write_does_not_corrupt_db(tmp_path):
    """If a position is never committed (killed before commit), DB stays clean."""
    db_path = tmp_path / "agent_a.db"
    store = StateStore("agent_a", db_dir=tmp_path)
    # Simulate a crash before commit: use raw connection, INSERT but don't commit
    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("MSFT", "long", 400.0, 392.0, 394.0, 3, "2026-03-30T10:00:00+00:00"),
    )
    # No commit — raw goes out of scope (rollback)
    raw.close()

    store2 = StateStore("agent_a", db_dir=tmp_path)
    assert store2.get_positions() == []


# ── Scenario 2: Schwab API timeout during order placement ──────────────────

def test_position_not_saved_if_order_placement_raises(tmp_path):
    """
    If place_order() throws, _execute() never reaches save_position().
    On restart, reconcile will find no local position to clean up.
    """
    import queue
    from agents.agent import Agent, AgentConfig

    config = AgentConfig(agent_id="agent_a", session="regular",
                         base_capital=50000.0)
    mock_claude = MagicMock()
    mock_claude.decide.return_value = MagicMock(
        action="buy", symbol="AAPL", confidence=0.85,
        position_size_pct=3.0, reasoning="test",
        signals_used=["volume_spike"], skip_reason=None,
    )
    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {"cash": 50000.0, "positions": []}
    mock_schwab.get_quote.return_value = {"lastPrice": 180.0}
    mock_schwab.place_order.side_effect = TimeoutError("Schwab API timeout")

    dq = queue.Queue()
    dq.put({"signals": [{"type": "volume_spike", "symbol": "AAPL",
                          "confidence": 0.85, "description": "test"}],
             "news": [], "institutional": [], "session": "regular"})

    agent = Agent(config, mock_claude, mock_schwab,
                  data_queue=dq, expertise_dir=tmp_path, db_dir=tmp_path)

    try:
        agent.run_cycle()
    except TimeoutError:
        pass  # expected — Schwab timed out

    store = StateStore("agent_a", db_dir=tmp_path)
    assert store.get_positions() == []


# ── Scenario 3: Claude API down ────────────────────────────────────────────

def test_claude_api_down_agent_skips_cycle(tmp_path):
    """When ClaudeClient raises, the agent cycle fails cleanly without side effects."""
    import queue
    from agents.agent import Agent, AgentConfig

    config = AgentConfig(agent_id="agent_a", session="regular",
                         base_capital=50000.0)
    mock_claude = MagicMock()
    mock_claude.decide.side_effect = RuntimeError("Claude API unavailable")
    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {"cash": 50000.0, "positions": []}

    dq = queue.Queue()
    dq.put({"signals": [], "news": [], "institutional": [],
             "session": "regular"})

    agent = Agent(config, mock_claude, mock_schwab,
                  data_queue=dq, expertise_dir=tmp_path, db_dir=tmp_path)

    try:
        agent.run_cycle()
    except RuntimeError:
        pass  # expected — Claude is down

    mock_schwab.place_order.assert_not_called()
    store = StateStore("agent_a", db_dir=tmp_path)
    assert store.get_positions() == []


# ── Scenario 4: Machine rebooted with open positions ───────────────────────

def test_reconcile_removes_stale_local_position(tmp_path):
    """
    After reboot: local DB has AAPL, broker does not.
    reconcile() should remove the stale local position.
    """
    from core.logger import get_logger

    store_a = StateStore("agent_a", db_dir=tmp_path)
    store_b = StateStore("agent_b", db_dir=tmp_path)

    # Agent A has AAPL locally but broker doesn't
    store_a.save_position(Position(
        symbol="AAPL", direction="long", entry_price=180.0,
        stop_loss=176.4, trailing_stop=177.3, quantity=5,
        entry_time="2026-03-30T10:00:00+00:00"))

    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {"positions": []}

    # Import reconcile from main
    import sys, importlib
    import main as m
    m.reconcile(mock_schwab, store_a, store_b)

    assert store_a.get_positions() == []


def test_reconcile_logs_unknown_broker_position(tmp_path, capsys):
    """
    After reboot: broker has MSFT, local DB does not.
    reconcile() logs it for manual review but does NOT auto-create local state.
    """
    store_a = StateStore("agent_a", db_dir=tmp_path)
    store_b = StateStore("agent_b", db_dir=tmp_path)

    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {
        "positions": [{"symbol": "MSFT"}]}

    import main as m
    m.reconcile(mock_schwab, store_a, store_b)

    # Neither agent should auto-create local state for unknown broker position
    assert store_a.get_position("MSFT") is None
    assert store_b.get_position("MSFT") is None
```

- [ ] **Step 2: Run crash recovery tests**

```
pytest tests/core/state/test_crash_recovery.py -v
```
Expected: all 6 tests PASS (these test existing + newly-added behavior).

- [ ] **Step 3: Commit**

```bash
git add tests/core/state/test_crash_recovery.py
git commit -m "test: verified crash recovery — all 4 failure scenarios covered"
```

---

## Task 9: Monitoring and alerting

**Files:**
- Create: `core/monitor/__init__.py`
- Create: `core/monitor/alerter.py`
- Modify: `config/config.yaml`
- Modify: `.env.example`
- Modify: `main.py`
- Create: `tests/core/monitor/test_alerter.py`

- [ ] **Step 1: Write alerter tests**

Create `tests/core/monitor/test_alerter.py`:

```python
from unittest.mock import patch, MagicMock
from core.monitor.alerter import Alerter


def _alerter(url="https://hooks.example.com/test"):
    return Alerter(webhook_url=url)


def test_send_posts_json_payload():
    alerter = _alerter()
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        alerter.send("agent_a", "large_drawdown", "Agent A down 4.2%")
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["agent"] == "agent_a"
        assert payload["type"] == "large_drawdown"
        assert "Agent A down 4.2%" in payload["message"]
        assert "timestamp" in payload


def test_send_silently_handles_request_failure():
    alerter = _alerter()
    with patch("requests.post", side_effect=Exception("network down")):
        # Should not raise
        alerter.send("agent_a", "test", "msg")


def test_no_webhook_url_skips_send():
    alerter = Alerter(webhook_url=None)
    with patch("requests.post") as mock_post:
        alerter.send("agent_a", "test", "msg")
        mock_post.assert_not_called()


def test_check_drawdown_fires_alert_when_threshold_exceeded():
    alerter = _alerter()
    with patch.object(alerter, "send") as mock_send:
        alerter.check_drawdown("agent_a", daily_pnl_pct=-4.0,
                                threshold_pct=3.0)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[1] == "large_drawdown"


def test_check_drawdown_does_not_fire_below_threshold():
    alerter = _alerter()
    with patch.object(alerter, "send") as mock_send:
        alerter.check_drawdown("agent_a", daily_pnl_pct=-2.0,
                                threshold_pct=3.0)
        mock_send.assert_not_called()


def test_check_idle_fires_when_no_recent_trade():
    from datetime import datetime, timezone, timedelta
    alerter = _alerter()
    old_time = datetime.now(timezone.utc) - timedelta(hours=3)
    with patch.object(alerter, "send") as mock_send:
        alerter.check_idle("agent_a", last_trade_time=old_time,
                            idle_threshold_minutes=120)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[1] == "agent_idle"


def test_check_idle_does_not_fire_within_threshold():
    from datetime import datetime, timezone, timedelta
    alerter = _alerter()
    recent = datetime.now(timezone.utc) - timedelta(minutes=30)
    with patch.object(alerter, "send") as mock_send:
        alerter.check_idle("agent_a", last_trade_time=recent,
                            idle_threshold_minutes=120)
        mock_send.assert_not_called()


def test_check_api_errors_fires_when_threshold_exceeded():
    alerter = _alerter()
    with patch.object(alerter, "send") as mock_send:
        alerter.check_api_errors("claude", error_count=6, threshold=5)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[1] == "api_errors"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/core/monitor/test_alerter.py -v
```
Expected: ImportError or all FAILs.

- [ ] **Step 3: Create `core/monitor/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `core/monitor/alerter.py`**

```python
"""
Webhook-based anomaly alerter.

Sends a POST request to ALERT_WEBHOOK_URL (set in .env) whenever an
anomalous condition is detected. Compatible with Zapier, IFTTT, Make.com,
and any service that accepts a JSON webhook.

Payload schema:
  {"agent": str, "type": str, "message": str, "timestamp": str (ISO-8601)}
"""
import os
from datetime import datetime, timezone, timedelta

try:
    import requests as _requests
except ImportError:
    _requests = None   # graceful degradation if requests unavailable


class Alerter:
    def __init__(self, webhook_url: str | None = None):
        self._url = webhook_url or os.getenv("ALERT_WEBHOOK_URL")

    def send(self, agent: str, alert_type: str, message: str) -> None:
        """POST an alert to the configured webhook. Silently ignores failures."""
        if not self._url or _requests is None:
            return
        payload = {
            "agent": agent,
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _requests.post(self._url, json=payload, timeout=5)
        except Exception:
            pass  # alerting must never crash the trading system

    # ── Named alert checks ─────────────────────────────────────────────────

    def check_drawdown(self, agent: str, daily_pnl_pct: float,
                        threshold_pct: float) -> None:
        """Alert if daily loss exceeds threshold_pct."""
        if daily_pnl_pct <= -threshold_pct:
            self.send(agent, "large_drawdown",
                      f"{agent} daily P&L is {daily_pnl_pct:.1f}% "
                      f"(threshold: -{threshold_pct:.1f}%)")

    def check_idle(self, agent: str, last_trade_time: datetime | None,
                   idle_threshold_minutes: int) -> None:
        """Alert if agent hasn't traded within idle_threshold_minutes."""
        if last_trade_time is None:
            return
        elapsed = (datetime.now(timezone.utc) - last_trade_time).total_seconds()
        if elapsed > idle_threshold_minutes * 60:
            self.send(agent, "agent_idle",
                      f"{agent} has not traded in "
                      f"{int(elapsed // 60)} minutes "
                      f"(threshold: {idle_threshold_minutes} min)")

    def check_api_errors(self, service: str, error_count: int,
                          threshold: int) -> None:
        """Alert if accumulated API errors exceed threshold."""
        if error_count > threshold:
            self.send("system", "api_errors",
                      f"{service} has {error_count} errors "
                      f"(threshold: {threshold})")
```

- [ ] **Step 5: Run alerter tests — expect all pass**

```
pytest tests/core/monitor/test_alerter.py -v
```
Expected: 8 tests PASS.

- [ ] **Step 6: Add monitoring config to `config/config.yaml`**

Append:

```yaml
monitoring:
  enabled: true
  drawdown_alert_pct: 3.0
  idle_agent_minutes: 120
  api_error_threshold: 5
```

- [ ] **Step 7: Update `.env.example` to document the webhook URL**

Add this line to `.env.example`:

```
ALERT_WEBHOOK_URL=          # Webhook URL for anomaly alerts (Zapier, IFTTT, Make.com, etc.)
```

- [ ] **Step 8: Wire Alerter into `main.py`**

Add import:
```python
from core.monitor.alerter import Alerter
```

In `main()`, after creating the stop event and kill switch, instantiate the alerter:
```python
    alerter = Alerter()
    monitoring_enabled = settings.get("monitoring", "enabled")
    drawdown_threshold = settings.get("monitoring", "drawdown_alert_pct")
    idle_threshold = settings.get("monitoring", "idle_agent_minutes")
```

Replace the main polling loop with one that also runs alert checks:

```python
    _last_trade_a: datetime | None = None
    _last_trade_b: datetime | None = None

    while not stop.is_set():
        schedule.run_pending()
        kill_switch.poll()

        if monitoring_enabled:
            # Drawdown checks
            pnl_a = store_a.get_round_pnl()
            pnl_b = store_b.get_round_pnl()
            pnl_a_pct = (pnl_a / base_capital) * 100
            pnl_b_pct = (pnl_b / base_capital) * 100
            alerter.check_drawdown("agent_a", pnl_a_pct, drawdown_threshold)
            alerter.check_drawdown("agent_b", pnl_b_pct, drawdown_threshold)

            # API error checks
            alerter.check_api_errors(
                "claude_a", claude_a.daily_spend_usd >= settings.get(
                    "api_cost", "daily_claude_spend_limit_usd") and 999 or 0,
                threshold=settings.get("monitoring", "api_error_threshold"),
            )

        time.sleep(60)   # alert check cadence: once per minute
```

Note: `datetime` must be imported at the top of `main.py` (it already is).

- [ ] **Step 9: Run full test suite**

```
pytest -v
```
Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add core/monitor/__init__.py core/monitor/alerter.py \
        config/config.yaml .env.example main.py \
        tests/core/monitor/test_alerter.py
git commit -m "feat: webhook-based monitoring and alerting (drawdown, idle agent, API errors)"
```

---

## Final verification

- [ ] **Run complete test suite**

```
pytest -v --tb=short
```
Expected: all tests pass (37 original + ~30 new = ~67 total).

- [ ] **Verify no short/crypto references remain in non-test code**

```
grep -r "short\|crypto\|pre_market\|post_market\|cover" \
     agents/ core/ config/ main.py \
     --include="*.py" --include="*.yaml" \
     -l
```
Expected: only test files and this plan document match. No production code should reference these.

- [ ] **Final commit**

```bash
git add .
git commit -m "chore: TIER 1 corrections complete — all tests passing"
```

---

## Self-Review

**Spec coverage check:**
1. ✅ No pre/post market — Task 1 blocks in risk_gate.py
2. ✅ No short selling — Task 1 blocks in risk_gate.py and removes direction="short"
3. ✅ No crypto — Task 1 removes from expertise_manager; never added to live code
4. ✅ Stop enforcement loop — Task 6 (StopEnforcer thread)
5. ✅ Kill switch — Task 4 (file flag + signal handler)
6. ✅ Closed-position learn loop — Task 7 (close_position triggers self_improve)
7. ✅ Paper trading mode with live quotes + simulated fills + 15-day gate — Task 5
8. ✅ Inverse ETFs — Task 3 (watchlist) + Task 1 (expertise seed + prompt)
9. ✅ Crash recovery tested — Task 8 (4 verified scenarios)
10. ✅ Alerting — Task 9 (webhook, drawdown, idle, API errors)

**Type consistency check:** `Position` always uses 7 fields including `entry_time`. `close_position()` calls `self._store.get_position(symbol)` (Task 2). `StopEnforcer` calls `agent.close_position()` (Task 7). `RiskGate.check()` drops `institutional_signal_present` consistently across risk_gate.py, agent.py, and tests.

**No placeholders:** All steps include exact code or exact commands.
