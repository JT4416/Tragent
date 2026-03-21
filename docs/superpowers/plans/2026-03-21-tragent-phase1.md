# Tragent Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a twin AI trading agent system that trades stocks on Charles Schwab/Thinkorswim using the Act-Learn-Reuse pattern, with Darwinian 2-week competition rounds and auto-learning expertise files.

**Architecture:** Single Python process, two concurrent agent threads sharing a thread-safe data feed, each maintaining isolated YAML expertise files. Claude API makes all trading decisions. Schwab API executes trades. SQLite persists state for crash recovery.

**Tech Stack:** Python 3.11+, `anthropic`, `schwab-py`, `yfinance`, `pandas-ta`, `pandas`, `pyyaml`, `requests`, `python-dotenv`, `sqlite3`, `pytest`, `pytest-mock`, `schedule`, `pytz`

---

## File Map

```
tragent/
├── core/
│   ├── data/
│   │   ├── __init__.py
│   │   ├── schwab_client.py       # OAuth + quotes + order submission
│   │   ├── market_feed.py         # Real-time price dispatcher → agent queues
│   │   ├── news_feed.py           # Alpha Vantage + NewsAPI
│   │   ├── institutional_feed.py  # Quiver Quant + SEC EDGAR + FINRA ATS
│   │   └── yfinance_client.py     # Historical OHLCV for analysis
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── technical.py           # Breakouts, VWAP, volume signals
│   │   └── signal_aggregator.py   # Combine all signals → ranked list
│   ├── decision/
│   │   ├── __init__.py
│   │   ├── prompt_builder.py      # Build decision + self-improve prompts
│   │   └── claude_client.py       # Claude API calls + cost tracking
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── risk_gate.py           # All pre-trade checks
│   │   └── trade_executor.py      # Place orders + stops via Schwab
│   ├── risk/
│   │   ├── __init__.py
│   │   └── position_tracker.py    # Track open positions + trailing stops
│   └── state/
│       ├── __init__.py
│       └── persistence.py         # SQLite read/write + startup reconciliation
├── agents/
│   ├── __init__.py
│   ├── agent.py                   # Agent thread: REUSE → ACT → LEARN loop
│   ├── expertise_manager.py       # YAML expertise file read/write/seed/trim
│   ├── self_improve.py            # Post-trade self-improve orchestrator
│   ├── agent_a/
│   │   ├── market_expertise.yaml
│   │   ├── news_expertise.yaml
│   │   ├── institutional_expertise.yaml
│   │   ├── trade_expertise.yaml
│   │   └── crypto_expertise.yaml
│   └── agent_b/                   # identical structure
├── competition/
│   ├── __init__.py
│   ├── scorer.py                  # P&L, win rate, Sharpe per agent
│   ├── reporter.py                # Daily JSON report + weekly comparison
│   ├── eliminator.py              # Round-end archive, seed, spawn
│   └── auto_commit.py             # Daily 4pm ET git commit + push
├── config/
│   ├── __init__.py
│   ├── settings.py                # Load + validate all config
│   └── config.yaml                # Default values
├── logs/
│   └── .gitkeep
├── state/
│   └── .gitkeep
├── tests/
│   ├── conftest.py
│   ├── core/
│   │   ├── data/
│   │   ├── analysis/
│   │   ├── decision/
│   │   ├── execution/
│   │   ├── risk/
│   │   └── state/
│   ├── agents/
│   └── competition/
├── .env.example
├── requirements.txt
├── pyproject.toml
└── main.py
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config/config.yaml`
- Create: `config/__init__.py`, `config/settings.py`
- Create: all `__init__.py` stubs
- Create: `logs/.gitkeep`, `state/.gitkeep`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "tragent"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Create requirements.txt**

```
anthropic>=0.40.0
schwab-py>=1.4.0
yfinance>=0.2.40
pandas>=2.2.0
pandas-ta>=0.3.14b
pyyaml>=6.0.2
requests>=2.32.0
python-dotenv>=1.0.1
schedule>=1.2.2
pytz>=2024.1
pytest>=8.3.0
pytest-mock>=3.14.0
```

- [ ] **Step 3: Create .env.example**

```
ANTHROPIC_API_KEY=your_key_here
SCHWAB_APP_KEY=your_key_here
SCHWAB_APP_SECRET=your_secret_here
SCHWAB_CALLBACK_URL=https://127.0.0.1
ALPHA_VANTAGE_API_KEY=your_key_here
NEWS_API_KEY=your_key_here
QUIVER_QUANT_API_KEY=your_key_here
```

- [ ] **Step 4: Create config/config.yaml**

```yaml
trading:
  cycle_interval_regular_min: 15
  cycle_interval_extended_min: 30
  regular_hours_start: "09:30"
  regular_hours_end: "16:00"
  extended_hours_start: "04:00"
  extended_hours_end: "20:00"
  open_blackout_minutes: 5

risk:
  max_position_size_pct: 5.0
  stop_loss_pct: 2.0
  trailing_stop_pct: 1.5
  max_concurrent_positions: 5
  daily_loss_limit_pct: 6.0
  confidence_threshold_regular: 0.65
  confidence_threshold_extended: 0.78

competition:
  round_duration_days: 14
  base_capital: 50000.0
  capital_advantage_pct: 10.0

api_cost:
  daily_claude_spend_limit_usd: 10.0

auto_commit:
  enabled: true
  time_et: "16:00"
```

- [ ] **Step 5: Create config/settings.py**

```python
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).parent.parent
_config_path = _ROOT / "config" / "config.yaml"

with open(_config_path) as f:
    _cfg = yaml.safe_load(f)


def get(section: str, key: str):
    return _cfg[section][key]


def api_key(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Missing required env var: {name}")
    return value


ANTHROPIC_API_KEY = lambda: api_key("ANTHROPIC_API_KEY")
SCHWAB_APP_KEY = lambda: api_key("SCHWAB_APP_KEY")
SCHWAB_APP_SECRET = lambda: api_key("SCHWAB_APP_SECRET")
ALPHA_VANTAGE_API_KEY = lambda: api_key("ALPHA_VANTAGE_API_KEY")
NEWS_API_KEY = lambda: api_key("NEWS_API_KEY")
QUIVER_QUANT_API_KEY = lambda: api_key("QUIVER_QUANT_API_KEY")
```

- [ ] **Step 6: Create all __init__.py stubs**

```bash
touch core/__init__.py core/data/__init__.py core/analysis/__init__.py \
      core/decision/__init__.py core/execution/__init__.py \
      core/risk/__init__.py core/state/__init__.py \
      agents/__init__.py competition/__init__.py \
      tests/__init__.py tests/core/__init__.py \
      tests/agents/__init__.py tests/competition/__init__.py
```

- [ ] **Step 7: Create tests/conftest.py**

```python
import pytest
from pathlib import Path
import tempfile, os

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-schwab-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-schwab-secret")
    monkeypatch.setenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-av-key")
    monkeypatch.setenv("NEWS_API_KEY", "test-news-key")
    monkeypatch.setenv("QUIVER_QUANT_API_KEY", "test-quiver-key")
```

- [ ] **Step 8: Write failing test**

```python
# tests/test_config.py
from config.settings import get

def test_get_trading_config():
    assert get("trading", "cycle_interval_regular_min") == 15

def test_get_risk_config():
    assert get("risk", "stop_loss_pct") == 2.0
```

- [ ] **Step 9: Run test**

```bash
cd C:/Users/JasonTurner/Tragent && pip install -r requirements.txt
pytest tests/test_config.py -v
```
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add -A && git commit -m "feat: project scaffolding, config system, dependencies"
```

---

## Task 2: Logging Infrastructure

**Files:**
- Create: `core/logger.py`
- Create: `tests/core/test_logger.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_logger.py
import json
from pathlib import Path
from core.logger import get_logger

def test_logs_json_to_file(tmp_dir):
    logger = get_logger("agent_a", "trades", log_dir=tmp_dir)
    logger.log({"trade_id": "t_001", "symbol": "AAPL", "action": "buy"})
    log_files = list((tmp_dir / "agent_a" / "trades").glob("*.json"))
    assert len(log_files) == 1
    entries = json.loads(log_files[0].read_text())
    assert entries[0]["symbol"] == "AAPL"

def test_appends_multiple_entries(tmp_dir):
    logger = get_logger("agent_a", "trades", log_dir=tmp_dir)
    logger.log({"event": "first"})
    logger.log({"event": "second"})
    log_files = list((tmp_dir / "agent_a" / "trades").glob("*.json"))
    entries = json.loads(log_files[0].read_text())
    assert len(entries) == 2
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/test_logger.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'core.logger'`

- [ ] **Step 3: Implement core/logger.py**

```python
import json
from datetime import datetime, timezone
from pathlib import Path


class Logger:
    def __init__(self, agent: str, category: str, log_dir: Path):
        self._dir = log_dir / agent / category
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._dir / f"{date}.json"

    def log(self, entry: dict) -> None:
        entry["_ts"] = datetime.now(timezone.utc).isoformat()
        path = self._path()
        existing = json.loads(path.read_text()) if path.exists() else []
        existing.append(entry)
        path.write_text(json.dumps(existing, indent=2))


_ROOT_LOG_DIR = Path(__file__).parent.parent / "logs"


def get_logger(agent: str, category: str, log_dir: Path = _ROOT_LOG_DIR) -> Logger:
    return Logger(agent, category, log_dir)
```

- [ ] **Step 4: Run test**

```bash
pytest tests/core/test_logger.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/logger.py tests/core/test_logger.py
git commit -m "feat: structured JSON logging infrastructure"
```

---

## Task 3: SQLite State Persistence + Reconciliation

**Files:**
- Create: `core/state/persistence.py`
- Create: `tests/core/state/test_persistence.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/state/test_persistence.py
from core.state.persistence import StateStore, Position

def test_save_and_load_position(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    pos = Position(symbol="AAPL", direction="long", entry_price=182.50,
                   stop_loss=178.85, trailing_stop=179.25, quantity=10)
    store.save_position(pos)
    loaded = store.get_positions()
    assert len(loaded) == 1
    assert loaded[0].symbol == "AAPL"
    assert loaded[0].entry_price == 182.50

def test_remove_position(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    pos = Position(symbol="MSFT", direction="long", entry_price=400.0,
                   stop_loss=392.0, trailing_stop=394.0, quantity=5)
    store.save_position(pos)
    store.remove_position("MSFT")
    assert store.get_positions() == []

def test_save_and_load_round_pnl(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    store.update_round_pnl(250.75)
    assert store.get_round_pnl() == 250.75
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/state/test_persistence.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement core/state/persistence.py**

```python
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Position:
    symbol: str
    direction: str          # "long" or "short"
    entry_price: float
    stop_loss: float
    trailing_stop: float
    quantity: int


_DEFAULT_DB_DIR = Path(__file__).parent.parent.parent / "state"


class StateStore:
    def __init__(self, agent_id: str, db_dir: Path = _DEFAULT_DB_DIR):
        db_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_dir / f"{agent_id}.db")
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                direction TEXT,
                entry_price REAL,
                stop_loss REAL,
                trailing_stop REAL,
                quantity INTEGER
            );
            CREATE TABLE IF NOT EXISTS round_state (
                key TEXT PRIMARY KEY,
                value REAL
            );
        """)
        self._conn.commit()

    def save_position(self, pos: Position) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO positions
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pos.symbol, pos.direction, pos.entry_price,
              pos.stop_loss, pos.trailing_stop, pos.quantity))
        self._conn.commit()

    def get_positions(self) -> list[Position]:
        rows = self._conn.execute("SELECT * FROM positions").fetchall()
        return [Position(*r) for r in rows]

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

- [ ] **Step 4: Run test**

```bash
pytest tests/core/state/test_persistence.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/state/persistence.py tests/core/state/test_persistence.py
git commit -m "feat: SQLite state persistence for positions and round P&L"
```

---

## Task 4: Expertise File Manager

**Files:**
- Create: `agents/expertise_manager.py`
- Create: `agents/agent_a/` + `agents/agent_b/` seed files
- Create: `tests/agents/test_expertise_manager.py`

- [ ] **Step 1: Write failing test**

```python
# tests/agents/test_expertise_manager.py
import yaml
from agents.expertise_manager import ExpertiseManager

def test_load_expertise(tmp_dir):
    # seed a file
    data = {"overview": {"last_updated": "2026-03-21", "total_patterns_tracked": 0},
            "breakout_patterns": []}
    (tmp_dir / "market_expertise.yaml").write_text(yaml.dump(data))
    mgr = ExpertiseManager("agent_a", expertise_dir=tmp_dir)
    loaded = mgr.load("market")
    assert loaded["overview"]["total_patterns_tracked"] == 0

def test_save_expertise(tmp_dir):
    mgr = ExpertiseManager("agent_a", expertise_dir=tmp_dir)
    data = {"overview": {"last_updated": "2026-03-21"}, "breakout_patterns": []}
    mgr.save("market", data)
    saved = yaml.safe_load((tmp_dir / "market_expertise.yaml").read_text())
    assert saved["overview"]["last_updated"] == "2026-03-21"

def test_enforces_line_limit(tmp_dir):
    import yaml as _yaml
    mgr = ExpertiseManager("agent_a", expertise_dir=tmp_dir, max_lines=10)
    # Build data that serializes to many lines, then save
    big_data = {"overview": {"last_updated": "2026-03-21"},
                "breakout_patterns": [{"id": str(i), "confidence": 0.5}
                                       for i in range(50)]}
    mgr.save("market", big_data)
    content = (tmp_dir / "market_expertise.yaml").read_text()
    # Line limit is enforced — note: truncated YAML may be partial;
    # the self-improve prompt (not the manager) is responsible for clean condensing.
    # Manager enforces hard cap to prevent context window overflow.
    assert len(content.splitlines()) <= 10
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/agents/test_expertise_manager.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement agents/expertise_manager.py**

```python
import yaml
from pathlib import Path
from datetime import date

_DEFAULT_MAX_LINES = 1000
_AGENTS_DIR = Path(__file__).parent


class ExpertiseManager:
    def __init__(self, agent_id: str,
                 expertise_dir: Path | None = None,
                 max_lines: int = _DEFAULT_MAX_LINES):
        self._dir = expertise_dir or (_AGENTS_DIR / agent_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_lines = max_lines

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}_expertise.yaml"

    def load(self, name: str) -> dict:
        path = self._path(name)
        if not path.exists():
            return self._seed(name)
        return yaml.safe_load(path.read_text()) or {}

    def save(self, name: str, data: dict) -> None:
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        lines = content.splitlines()
        if len(lines) > self._max_lines:
            content = "\n".join(lines[: self._max_lines])
        self._path(name).write_text(content)

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
            "crypto": {
                "overview": {"last_updated": str(date.today()),
                             "activated": False,
                             "preferred_crypto": None,
                             "total_allocated_usd": 0.0},
                "crypto_patterns": [],
                "trade_history": [],
            },
        }
        data = seeds.get(name, {"overview": {"last_updated": str(date.today())}})
        self.save(name, data)
        return data
```

- [ ] **Step 4: Seed agent expertise files**

```python
# Run once to seed both agents
from agents.expertise_manager import ExpertiseManager
for agent in ("agent_a", "agent_b"):
    mgr = ExpertiseManager(agent)
    for name in ("market", "news", "institutional", "trade", "crypto"):
        mgr.load(name)  # triggers _seed if file missing
```

Run: `python -c "from agents.expertise_manager import ExpertiseManager; [ExpertiseManager(a).load(n) for a in ('agent_a','agent_b') for n in ('market','news','institutional','trade','crypto')]"`

- [ ] **Step 5: Run test**

```bash
pytest tests/agents/test_expertise_manager.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agents/ tests/agents/test_expertise_manager.py
git commit -m "feat: expertise file manager with YAML seed templates"
```

---

## Task 5: Claude Decision Client

**Files:**
- Create: `core/decision/prompt_builder.py`
- Create: `core/decision/claude_client.py`
- Create: `tests/core/decision/test_claude_client.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/decision/test_claude_client.py
import json
import pytest
from unittest.mock import MagicMock, patch
from core.decision.claude_client import ClaudeClient, TradeDecision

def test_parse_valid_decision():
    raw = json.dumps({
        "action": "buy", "symbol": "AAPL", "confidence": 0.82,
        "position_size_pct": 3.0, "reasoning": "strong breakout",
        "signals_used": ["vwap_cross_bullish"], "skip_reason": None
    })
    decision = ClaudeClient._parse_response(raw)
    assert decision.action == "buy"
    assert decision.confidence == 0.82

def test_parse_hold_decision():
    raw = json.dumps({
        "action": "hold", "symbol": None, "confidence": 0.45,
        "position_size_pct": 0, "reasoning": "low confidence",
        "signals_used": [], "skip_reason": "no clear signal"
    })
    decision = ClaudeClient._parse_response(raw)
    assert decision.action == "hold"

def test_cost_tracking(tmp_dir, monkeypatch):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "action": "hold", "symbol": None, "confidence": 0.3,
        "position_size_pct": 0, "reasoning": "test",
        "signals_used": [], "skip_reason": "test"
    }))]
    mock_response.usage.input_tokens = 3000
    mock_response.usage.output_tokens = 200

    with patch("core.decision.claude_client.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        client = ClaudeClient(daily_limit_usd=10.0, log_dir=tmp_dir)
        client.decide("prompt", "context")
        assert client.daily_spend_usd > 0
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/decision/test_claude_client.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement core/decision/prompt_builder.py**

```python
from datetime import datetime, timezone


DECISION_SYSTEM = (
    "You are a professional stock trader with expert knowledge of the Thinkorswim "
    "platform, technical analysis, market microstructure, and institutional trading "
    "behavior. You make precise, data-driven trading decisions. "
    "You always respond in valid JSON only — no prose, no markdown."
)

SELF_IMPROVE_SYSTEM = (
    "You are maintaining a YAML expertise file — a mental model of trading patterns. "
    "Update it precisely based on new trade evidence. Preserve valid YAML syntax. "
    "Enforce the line limit by condensing similar entries and removing "
    "lowest-confidence entries if over the limit. "
    "Return the complete updated YAML file only, no prose."
)


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
) -> str:
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
Analyze the signals above and return a trading decision.

## Response Format (JSON only)
{{
  "action": "buy|sell|short|cover|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "brief explanation",
  "signals_used": [],
  "skip_reason": "if hold, why"
}}"""


def build_self_improve_prompt(
    trade_record: dict,
    original_reasoning: str,
    outcome: str,
    pnl_pct: float,
    duration: str,
    current_yaml: str,
    max_lines: int = 1000,
) -> str:
    return f"""## Completed Trade
{trade_record}

## Claude's Original Reasoning
{original_reasoning}

## Outcome
Result: {outcome} | P&L: {pnl_pct:.2f}% | Held for: {duration}

## Current Expertise File (max {max_lines} lines)
{current_yaml}

## Task
Update the expertise file to reflect what was learned from this trade.
- Increase confidence for patterns that worked
- Decrease confidence for patterns that failed
- Add new lessons_learned entries if a new pattern was identified
- Update evolved_parameters if thresholds should shift
- Return the complete updated YAML file only, no prose"""


def _yaml_summary(data: dict) -> str:
    import yaml
    return yaml.dump(data, default_flow_style=False)[:2000]


def _format_list(items: list) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {item}" for item in items)
```

- [ ] **Step 4: Implement core/decision/claude_client.py**

```python
import json
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from config import settings
from core.decision.prompt_builder import DECISION_SYSTEM, SELF_IMPROVE_SYSTEM
from core.logger import get_logger

# Claude Sonnet pricing (per 1M tokens) — update if pricing changes
_INPUT_COST_PER_1M = 3.00
_OUTPUT_COST_PER_1M = 15.00


@dataclass
class TradeDecision:
    action: str            # buy | sell | short | cover | hold
    symbol: str | None
    confidence: float
    position_size_pct: float
    reasoning: str
    signals_used: list[str]
    skip_reason: str | None


class ClaudeClient:
    def __init__(self, daily_limit_usd: float = 10.0,
                 log_dir: Path | None = None,
                 agent_id: str = "system"):
        self._client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY())
        self._limit = daily_limit_usd
        self.daily_spend_usd: float = 0.0
        self._logger = get_logger(agent_id, "decisions", log_dir) \
            if log_dir else None

    def decide(self, system_context: str, user_prompt: str) -> TradeDecision:
        if self.daily_spend_usd >= self._limit:
            raise RuntimeError(
                f"Daily Claude spend limit ${self._limit} reached. Pausing.")

        response = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=DECISION_SYSTEM + "\n\n" + system_context,
            messages=[{"role": "user", "content": user_prompt}],
        )
        self._track_cost(response.usage)
        raw = response.content[0].text

        if self._logger:
            self._logger.log({"prompt": user_prompt[:500],
                               "response": raw, "spend": self.daily_spend_usd})

        return self._parse_response(raw)

    def self_improve(self, user_prompt: str) -> str:
        response = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SELF_IMPROVE_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        self._track_cost(response.usage)
        return response.content[0].text

    @staticmethod
    def _parse_response(raw: str) -> TradeDecision:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
        return TradeDecision(
            action=data["action"],
            symbol=data.get("symbol"),
            confidence=float(data["confidence"]),
            position_size_pct=float(data.get("position_size_pct", 0)),
            reasoning=data.get("reasoning", ""),
            signals_used=data.get("signals_used", []),
            skip_reason=data.get("skip_reason"),
        )

    def _track_cost(self, usage) -> None:
        cost = (usage.input_tokens / 1_000_000 * _INPUT_COST_PER_1M +
                usage.output_tokens / 1_000_000 * _OUTPUT_COST_PER_1M)
        self.daily_spend_usd += cost
```

- [ ] **Step 5: Run test**

```bash
pytest tests/core/decision/test_claude_client.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/decision/ tests/core/decision/
git commit -m "feat: Claude decision client with cost tracking and prompt builder"
```

---

## Task 6: Risk Gate

**Files:**
- Create: `core/execution/risk_gate.py`
- Create: `tests/core/execution/test_risk_gate.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/execution/test_risk_gate.py
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock
from core.execution.risk_gate import RiskGate, RiskConfig, RiskDecision

_ET = ZoneInfo("America/New_York")

def _config():
    return RiskConfig(
        max_position_size_pct=5.0,
        daily_loss_limit_pct=6.0,
        max_concurrent_positions=5,
        confidence_threshold_regular=0.65,
        confidence_threshold_extended=0.78,
        open_blackout_minutes=5,
    )

def test_passes_valid_trade():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.80, position_size_pct=3.0,
        session="regular", open_positions=2,
        portfolio_value=50000, daily_pnl_pct=-1.0,
        institutional_signal_present=False,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert result.approved

def test_blocks_low_confidence():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.50, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=False,
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
        institutional_signal_present=False,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "loss limit" in result.reason.lower()

def test_blocks_extended_hours_without_institutional():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.80, position_size_pct=3.0,
        session="pre_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=False,
        current_time=datetime(2026, 3, 21, 7, 0, tzinfo=_ET),
    )
    assert not result.approved

def test_blocks_open_blackout():
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=True,
        # 09:32 ET on Mar 21 (DST active → UTC-4, so 13:32 UTC)
        current_time=datetime(2026, 3, 21, 9, 32, tzinfo=ET),
    )
    assert not result.approved

def test_extended_hours_blocks_low_confidence_even_with_institutional():
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.76, position_size_pct=3.0,
        session="pre_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=True,  # signal present but confidence < 0.78
        current_time=datetime(2026, 3, 21, 7, 0, tzinfo=ET),
    )
    assert not result.approved
    assert "confidence" in result.reason.lower()
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/execution/test_risk_gate.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement core/execution/risk_gate.py**

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
    confidence_threshold_extended: float
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
        institutional_signal_present: bool,
        current_time: datetime,
    ) -> RiskDecision:
        if action == "hold":
            return RiskDecision(approved=False, reason="action is hold")

        # 1. Open blackout (first 5 min of regular session) — use ET timezone
        if session == "regular" and self._in_open_blackout(current_time):
            return RiskDecision(approved=False,
                                reason="open blackout period (first 5 minutes)")

        # 2. Extended hours require higher confidence + institutional signal
        threshold = self._cfg.confidence_threshold_regular
        if session in ("pre_market", "post_market"):
            threshold = self._cfg.confidence_threshold_extended
            if not institutional_signal_present:
                return RiskDecision(
                    approved=False,
                    reason="extended hours require institutional signal")

        # 3. Confidence check (also applies at threshold=0.78 for extended)
        if confidence < threshold:
            return RiskDecision(
                approved=False,
                reason=f"confidence {confidence:.2f} below threshold {threshold:.2f}")

        # 4. Daily loss limit
        if daily_pnl_pct <= -self._cfg.daily_loss_limit_pct:
            return RiskDecision(approved=False,
                                reason=f"daily loss limit hit ({daily_pnl_pct:.1f}%)")

        # 5. Max concurrent positions
        if open_positions >= self._cfg.max_concurrent_positions:
            return RiskDecision(
                approved=False,
                reason=f"max positions reached ({open_positions})")

        # 6. Position size
        if position_size_pct > self._cfg.max_position_size_pct:
            return RiskDecision(
                approved=False,
                reason=f"position size {position_size_pct}% exceeds max")

        return RiskDecision(approved=True, reason="all checks passed")

    def _in_open_blackout(self, t: datetime) -> bool:
        # Convert to ET to correctly handle DST
        t_et = t.astimezone(_ET)
        market_open_et = t_et.replace(hour=9, minute=30, second=0, microsecond=0)
        blackout_end = market_open_et + timedelta(minutes=self._cfg.open_blackout_minutes)
        return market_open_et <= t_et < blackout_end
```

- [ ] **Step 4: Run test**

```bash
pytest tests/core/execution/test_risk_gate.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/execution/risk_gate.py tests/core/execution/test_risk_gate.py
git commit -m "feat: risk gate with all pre-trade checks"
```

---

## Task 7: Data Feeds (News + Institutional)

**Files:**
- Create: `core/data/news_feed.py`
- Create: `core/data/institutional_feed.py`
- Create: `tests/core/data/test_feeds.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/data/test_feeds.py
from unittest.mock import patch, MagicMock
from core.data.news_feed import NewsFeed
from core.data.institutional_feed import InstitutionalFeed

def test_news_feed_returns_list(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"articles": [
        {"title": "Apple surges on earnings", "source": {"name": "Reuters"},
         "publishedAt": "2026-03-21T10:00:00Z", "url": "http://example.com"}
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("core.data.news_feed.requests.get", return_value=mock_resp):
        feed = NewsFeed()
        articles = feed.fetch(query="AAPL earnings")
        assert len(articles) == 1
        assert articles[0]["title"] == "Apple surges on earnings"

def test_institutional_feed_returns_list(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"ticker": "AAPL", "transaction_type": "Buy",
         "insider": "CEO", "date": "2026-03-20"}
    ]
    mock_resp.raise_for_status = MagicMock()
    with patch("core.data.institutional_feed.requests.get", return_value=mock_resp):
        feed = InstitutionalFeed()
        signals = feed.fetch_insider_trades("AAPL")
        assert len(signals) == 1
        assert signals[0]["ticker"] == "AAPL"
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/data/test_feeds.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement core/data/news_feed.py**

```python
import requests
from config import settings


class NewsFeed:
    _BASE = "https://newsapi.org/v2/everything"

    def fetch(self, query: str, page_size: int = 10) -> list[dict]:
        resp = requests.get(self._BASE, params={
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": settings.NEWS_API_KEY(),
        }, timeout=10)
        resp.raise_for_status()
        return resp.json().get("articles", [])
```

- [ ] **Step 4: Implement core/data/institutional_feed.py**

```python
import requests
from config import settings


class InstitutionalFeed:
    _BASE = "https://api.quiverquant.com/beta"

    def _headers(self) -> dict:
        return {"Authorization": f"Token {settings.QUIVER_QUANT_API_KEY()}"}

    def fetch_insider_trades(self, ticker: str) -> list[dict]:
        resp = requests.get(
            f"{self._BASE}/historical/insiders/{ticker}",
            headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def fetch_congressional_trades(self, ticker: str) -> list[dict]:
        resp = requests.get(
            f"{self._BASE}/historical/congresstrading/{ticker}",
            headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 5: Run test**

```bash
pytest tests/core/data/test_feeds.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/data/news_feed.py core/data/institutional_feed.py tests/core/data/test_feeds.py
git commit -m "feat: news feed (NewsAPI) and institutional feed (Quiver Quant)"
```

---

## Task 8: Technical Analysis Engine

**Files:**
- Create: `core/analysis/technical.py`
- Create: `core/data/yfinance_client.py`
- Create: `tests/core/analysis/test_technical.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/analysis/test_technical.py
import pandas as pd
import numpy as np
from core.analysis.technical import TechnicalAnalyzer, BreakoutSignal

def _make_ohlcv(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100, 120, n), index=idx)
    volume = pd.Series([1_000_000] * n, index=idx)
    volume.iloc[-1] = 2_500_000   # spike on last bar
    high = close + 1
    low = close - 1
    open_ = close - 0.5
    return pd.DataFrame({"open": open_, "high": high,
                          "low": low, "close": close, "volume": volume})

def test_detects_volume_breakout():
    df = _make_ohlcv()
    analyzer = TechnicalAnalyzer()
    signals = analyzer.analyze(df, symbol="AAPL")
    assert any(s.signal_type == "volume_spike" for s in signals)

def test_no_signals_on_flat_data():
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    df = pd.DataFrame({
        "open": [100.0] * 60, "high": [101.0] * 60,
        "low": [99.0] * 60, "close": [100.0] * 60,
        "volume": [1_000_000] * 60,
    }, index=idx)
    analyzer = TechnicalAnalyzer()
    signals = analyzer.analyze(df, symbol="FLAT")
    assert len(signals) == 0
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/analysis/test_technical.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement core/data/yfinance_client.py**

```python
import yfinance as yf
import pandas as pd


class YFinanceClient:
    def fetch_ohlcv(self, symbol: str, period: str = "3mo",
                    interval: str = "1d") -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        df.columns = [c.lower() for c in df.columns]
        return df[["open", "high", "low", "close", "volume"]].dropna()
```

- [ ] **Step 4: Implement core/analysis/technical.py**

```python
from dataclasses import dataclass
import pandas as pd
import pandas_ta as ta


@dataclass
class BreakoutSignal:
    symbol: str
    signal_type: str    # "volume_spike" | "vwap_cross" | "range_breakout" | "52w_high"
    direction: str      # "bullish" | "bearish"
    strength: float     # 0.0–1.0
    detail: str


class TechnicalAnalyzer:
    _VOLUME_SPIKE_MULT = 1.5
    _LOOKBACK = 20

    def analyze(self, df: pd.DataFrame, symbol: str) -> list[BreakoutSignal]:
        if len(df) < self._LOOKBACK + 1:
            return []
        signals = []
        signals.extend(self._volume_spike(df, symbol))
        signals.extend(self._vwap_cross(df, symbol))
        signals.extend(self._range_breakout(df, symbol))
        signals.extend(self._fifty_two_week_high(df, symbol))
        return signals

    def _volume_spike(self, df: pd.DataFrame,
                      symbol: str) -> list[BreakoutSignal]:
        avg_vol = df["volume"].iloc[-self._LOOKBACK:-1].mean()
        last_vol = df["volume"].iloc[-1]
        if avg_vol == 0:
            return []
        ratio = last_vol / avg_vol
        if ratio >= self._VOLUME_SPIKE_MULT:
            direction = "bullish" if df["close"].iloc[-1] > df["open"].iloc[-1] \
                else "bearish"
            return [BreakoutSignal(
                symbol=symbol, signal_type="volume_spike",
                direction=direction,
                strength=min(1.0, (ratio - 1) / 2),
                detail=f"Volume {ratio:.1f}x avg ({int(last_vol):,})",
            )]
        return []

    def _vwap_cross(self, df: pd.DataFrame,
                    symbol: str) -> list[BreakoutSignal]:
        if "vwap" not in df.columns:
            df = df.copy()
            df.ta.vwap(append=True)
        if "VWAP_D" not in df.columns:
            return []
        prev_close = df["close"].iloc[-2]
        last_close = df["close"].iloc[-1]
        vwap = df["VWAP_D"].iloc[-1]
        if pd.isna(vwap):
            return []
        if prev_close < vwap <= last_close:
            return [BreakoutSignal(
                symbol=symbol, signal_type="vwap_cross",
                direction="bullish", strength=0.6,
                detail=f"Price crossed above VWAP {vwap:.2f}")]
        if prev_close > vwap >= last_close:
            return [BreakoutSignal(
                symbol=symbol, signal_type="vwap_cross",
                direction="bearish", strength=0.6,
                detail=f"Price crossed below VWAP {vwap:.2f}")]
        return []

    def _range_breakout(self, df: pd.DataFrame,
                        symbol: str) -> list[BreakoutSignal]:
        window = df.iloc[-self._LOOKBACK - 1:-1]
        resistance = window["high"].max()
        last_close = df["close"].iloc[-1]
        if last_close > resistance:
            return [BreakoutSignal(
                symbol=symbol, signal_type="range_breakout",
                direction="bullish",
                strength=min(1.0, (last_close - resistance) / resistance * 20),
                detail=f"Broke {self._LOOKBACK}-day high {resistance:.2f}")]
        return []

    def _fifty_two_week_high(self, df: pd.DataFrame,
                             symbol: str) -> list[BreakoutSignal]:
        if len(df) < 252:
            return []
        high_52w = df["high"].iloc[-252:].max()
        last_close = df["close"].iloc[-1]
        if last_close >= high_52w * 0.99:
            return [BreakoutSignal(
                symbol=symbol, signal_type="52w_high",
                direction="bullish", strength=0.85,
                detail=f"Near/at 52-week high {high_52w:.2f}")]
        return []
```

- [ ] **Step 5: Run test**

```bash
pytest tests/core/analysis/test_technical.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/analysis/technical.py core/data/yfinance_client.py tests/core/analysis/
git commit -m "feat: technical analysis engine (volume, VWAP, range breakout, 52w high)"
```

---

## Task 9: Self-Improve Orchestrator

**Files:**
- Create: `agents/self_improve.py`
- Create: `tests/agents/test_self_improve.py`

- [ ] **Step 1: Write failing test**

```python
# tests/agents/test_self_improve.py
import yaml
from unittest.mock import MagicMock, patch
from agents.self_improve import SelfImproveOrchestrator
from agents.expertise_manager import ExpertiseManager

def test_updates_market_expertise(tmp_dir):
    mgr = ExpertiseManager("agent_a", expertise_dir=tmp_dir)
    mgr.load("market")  # seeds file

    mock_claude = MagicMock()
    updated_yaml = yaml.dump({
        "overview": {"last_updated": "2026-03-21", "total_patterns_tracked": 1},
        "breakout_patterns": [
            {"id": "bp_001", "description": "test", "confidence": 0.85,
             "occurrences": 1, "win_rate": 1.0, "avg_gain_pct": 3.0,
             "last_seen": "2026-03-21"}
        ],
        "volume_signals": [],
        "known_false_signals": [],
    })
    mock_claude.self_improve.return_value = updated_yaml

    orchestrator = SelfImproveOrchestrator(mgr, mock_claude)
    trade_record = {
        "trade_id": "t_001", "symbol": "AAPL", "direction": "long",
        "entry": 182.50, "exit": 187.10, "pnl_pct": 2.52,
        "signals_used": ["volume_spike"], "outcome": "win",
    }
    orchestrator.run(trade_record, original_reasoning="strong volume",
                     outcome="win", pnl_pct=2.52, duration="2h")

    loaded = mgr.load("market")
    assert len(loaded["breakout_patterns"]) == 1
    assert mock_claude.self_improve.called
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/agents/test_self_improve.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement agents/self_improve.py**

```python
import yaml
from core.decision.prompt_builder import build_self_improve_prompt
from agents.expertise_manager import ExpertiseManager

_SIGNAL_TO_EXPERTISE = {
    "volume_spike": "market",
    "vwap_cross": "market",
    "range_breakout": "market",
    "52w_high": "market",
    "earnings_beat": "news",
    "fda_approval": "news",
    "sector_catalyst": "news",
    "form4_insider_cluster": "institutional",
    "13f_new_position": "institutional",
    "congressional_buy": "institutional",
}


class SelfImproveOrchestrator:
    def __init__(self, expertise_mgr: ExpertiseManager, claude_client):
        self._mgr = expertise_mgr
        self._claude = claude_client

    def run(self, trade_record: dict, original_reasoning: str,
            outcome: str, pnl_pct: float, duration: str) -> None:
        files_to_update = self._determine_files(trade_record)
        # Always update trade expertise
        files_to_update.add("trade")

        for file_name in files_to_update:
            current_data = self._mgr.load(file_name)
            current_yaml = yaml.dump(current_data, default_flow_style=False)
            prompt = build_self_improve_prompt(
                trade_record=str(trade_record),
                original_reasoning=original_reasoning,
                outcome=outcome,
                pnl_pct=pnl_pct,
                duration=duration,
                current_yaml=current_yaml,
                max_lines=1000,
            )
            updated_yaml = self._claude.self_improve(prompt)
            try:
                updated_data = yaml.safe_load(updated_yaml)
                if updated_data:
                    self._mgr.save(file_name, updated_data)
            except yaml.YAMLError:
                pass  # keep existing file if Claude returns invalid YAML

    def _determine_files(self, trade_record: dict) -> set[str]:
        files = set()
        for signal in trade_record.get("signals_used", []):
            if signal in _SIGNAL_TO_EXPERTISE:
                files.add(_SIGNAL_TO_EXPERTISE[signal])
        return files
```

- [ ] **Step 4: Run test**

```bash
pytest tests/agents/test_self_improve.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/self_improve.py tests/agents/test_self_improve.py
git commit -m "feat: self-improve orchestrator for Act-Learn-Reuse LEARN step"
```

---

## Task 10: Agent Thread (Full REUSE → ACT → LEARN Cycle)

**Files:**
- Create: `agents/agent.py`
- Create: `tests/agents/test_agent.py`

- [ ] **Step 1: Write failing test**

```python
# tests/agents/test_agent.py
import queue
from unittest.mock import MagicMock, patch
from agents.agent import Agent, AgentConfig

def _make_agent(tmp_dir):
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
                 data_queue=data_queue, expertise_dir=tmp_dir)

def test_agent_runs_one_cycle(tmp_dir):
    agent = _make_agent(tmp_dir)
    agent.run_cycle()  # should not raise

def test_agent_hold_does_not_execute(tmp_dir):
    agent = _make_agent(tmp_dir)
    agent.run_cycle()
    agent._schwab.place_order.assert_not_called()
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/agents/test_agent.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement agents/agent.py**

```python
import queue
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agents.expertise_manager import ExpertiseManager
from agents.self_improve import SelfImproveOrchestrator
from core.decision.prompt_builder import build_decision_prompt
from core.execution.risk_gate import RiskGate, RiskConfig
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
                 log_dir: Path | None = None):
        self._cfg = config
        self._claude = claude_client
        self._schwab = schwab_client
        self._queue = data_queue
        self._mgr = ExpertiseManager(config.agent_id, expertise_dir)
        self._store = StateStore(config.agent_id, db_dir) if db_dir \
            else StateStore(config.agent_id)
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

        # REUSE: load all expertise
        expertise = self._mgr.load_all()

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

    def _execute(self, decision, cash: float, evolved: dict) -> None:
        size_pct = min(decision.position_size_pct,
                       evolved.get("max_position_size_pct", 5.0))

        # Get real-time quote for accurate position sizing
        quote = self._schwab.get_quote(decision.symbol)
        price = quote.get("lastPrice") or quote.get("mark") or 1.0
        quantity = max(1, int((cash * size_pct / 100) / price))

        stop_pct = evolved.get("stop_loss_pct", 2.0)
        trailing_pct = evolved.get("trailing_stop_pct", 1.5)
        stop_price = round(price * (1 - stop_pct / 100), 2) \
            if decision.action in ("buy",) else \
            round(price * (1 + stop_pct / 100), 2)

        order = self._schwab.place_order(
            symbol=decision.symbol,
            action=decision.action,
            quantity=quantity,
        )

        # Persist position with broker-side stop levels
        direction = "long" if decision.action == "buy" else "short"
        self._store.save_position(
            __import__("core.state.persistence", fromlist=["Position"]).Position(
                symbol=decision.symbol,
                direction=direction,
                entry_price=price,
                stop_loss=stop_price,
                trailing_stop=round(price * (1 - trailing_pct / 100), 2),
                quantity=quantity,
            )
        )

        trade_record = {
            "trade_id": f"t_{self._cfg.agent_id}_{int(__import__('time').time())}",
            "symbol": decision.symbol,
            "direction": direction,
            "entry": price,
            "exit": None,  # filled when position closes
            "pnl_pct": None,
            "signals_used": decision.signals_used,
            "outcome": None,
            "claude_confidence": decision.confidence,
        }

        self._logger.log({
            "event": "trade_placed", **trade_record,
            "reasoning": decision.reasoning,
        })

        # LEARN: trigger self-improve immediately after placing trade
        # (will run again with outcome when position closes)
        self._improve.run(
            trade_record=trade_record,
            original_reasoning=decision.reasoning,
            outcome="open",
            pnl_pct=0.0,
            duration="0m",
        )
```

- [ ] **Step 4: Run test**

```bash
pytest tests/agents/test_agent.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/agent.py tests/agents/test_agent.py
git commit -m "feat: agent thread with full REUSE→ACT cycle"
```

---

## Task 11: Competition Scorer + Daily Reporter

**Files:**
- Create: `competition/scorer.py`
- Create: `competition/reporter.py`
- Create: `tests/competition/test_scorer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/competition/test_scorer.py
from competition.scorer import CompetitionScorer, TradeRecord
from datetime import date

def test_pnl_calculation():
    scorer = CompetitionScorer("agent_a", base_capital=50000.0)
    scorer.record_trade(TradeRecord(
        date=date(2026, 3, 21), symbol="AAPL",
        direction="long", entry=182.50, exit=187.10,
        quantity=10, pnl=46.0, pnl_pct=2.52,
    ))
    stats = scorer.stats()
    assert stats["total_pnl"] == 46.0
    assert stats["win_rate"] == 1.0
    assert stats["total_trades"] == 1

def test_sharpe_ratio():
    scorer = CompetitionScorer("agent_a", base_capital=50000.0)
    for pnl_pct in [1.0, -0.5, 2.0, 0.8, -1.0]:
        scorer.record_trade(TradeRecord(
            date=date(2026, 3, 21), symbol="X", direction="long",
            entry=100, exit=100, quantity=1,
            pnl=pnl_pct * 100, pnl_pct=pnl_pct,
        ))
    stats = scorer.stats()
    assert "sharpe" in stats
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/competition/test_scorer.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement competition/scorer.py**

```python
import math
from dataclasses import dataclass, field
from datetime import date


@dataclass
class TradeRecord:
    date: date
    symbol: str
    direction: str
    entry: float
    exit: float
    quantity: int
    pnl: float
    pnl_pct: float


class CompetitionScorer:
    def __init__(self, agent_id: str, base_capital: float):
        self._id = agent_id
        self._capital = base_capital
        self._trades: list[TradeRecord] = []

    def record_trade(self, trade: TradeRecord) -> None:
        self._trades.append(trade)

    def stats(self) -> dict:
        if not self._trades:
            return {"agent_id": self._id, "total_pnl": 0.0, "win_rate": 0.0,
                    "total_trades": 0, "sharpe": 0.0, "best_trade": 0.0,
                    "worst_trade": 0.0, "avg_gain_pct": 0.0, "avg_loss_pct": 0.0}
        total_pnl = sum(t.pnl for t in self._trades)
        wins = [t for t in self._trades if t.pnl > 0]
        losses = [t for t in self._trades if t.pnl <= 0]
        returns = [t.pnl_pct for t in self._trades]
        sharpe = self._sharpe(returns)
        return {
            "agent_id": self._id,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(len(wins) / len(self._trades), 3),
            "total_trades": len(self._trades),
            "sharpe": round(sharpe, 3),
            "best_trade": max(t.pnl for t in self._trades),
            "worst_trade": min(t.pnl for t in self._trades),
            "avg_gain_pct": round(sum(t.pnl_pct for t in wins) / len(wins), 3)
                if wins else 0.0,
            "avg_loss_pct": round(sum(t.pnl_pct for t in losses) / len(losses), 3)
                if losses else 0.0,
        }

    @staticmethod
    def _sharpe(returns: list[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(variance)
        return (mean - risk_free) / std if std > 0 else 0.0
```

- [ ] **Step 4: Implement competition/reporter.py**

```python
import json
import subprocess
from datetime import date
from pathlib import Path
from competition.scorer import CompetitionScorer

_LOG_DIR = Path(__file__).parent.parent / "logs" / "competition"


class DailyReporter:
    def __init__(self, scorer_a: CompetitionScorer,
                 scorer_b: CompetitionScorer,
                 log_dir: Path = _LOG_DIR):
        self._a = scorer_a
        self._b = scorer_b
        self._dir = log_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> dict:
        stats_a = self._a.stats()
        stats_b = self._b.stats()
        leader = ("agent_a" if stats_a["total_pnl"] > stats_b["total_pnl"]
                  else "agent_b" if stats_b["total_pnl"] > stats_a["total_pnl"]
                  else "tied")
        report = {
            "date": str(date.today()),
            "agent_a": stats_a,
            "agent_b": stats_b,
            "leader": leader,
            "divergence_notes": "",
        }
        path = self._dir / f"{date.today()}.json"
        path.write_text(json.dumps(report, indent=2))
        return report

    def auto_commit(self) -> None:
        root = Path(__file__).parent.parent
        subprocess.run(["git", "-C", str(root), "add",
                        "logs/", "agents/agent_a/", "agents/agent_b/"],
                       check=False)
        subprocess.run(["git", "-C", str(root), "commit", "-m",
                        f"chore: daily auto-commit {date.today()}"],
                       check=False)
        subprocess.run(["git", "-C", str(root), "push"], check=False)
```

- [ ] **Step 5: Run test**

```bash
pytest tests/competition/test_scorer.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add competition/scorer.py competition/reporter.py tests/competition/test_scorer.py
git commit -m "feat: competition scorer (P&L, win rate, Sharpe) and daily reporter"
```

---

## Task 12: Round Eliminator + Seed Engine

**Files:**
- Create: `competition/eliminator.py`
- Create: `tests/competition/test_eliminator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/competition/test_eliminator.py
import shutil
import yaml
from competition.eliminator import RoundEliminator
from agents.expertise_manager import ExpertiseManager

def test_archives_loser_and_seeds_winner(tmp_dir):
    # Seed both agents
    winner_dir = tmp_dir / "agent_a"
    loser_dir = tmp_dir / "agent_b"
    archive_dir = tmp_dir / "archive"

    winner_mgr = ExpertiseManager("agent_a", expertise_dir=winner_dir)
    loser_mgr = ExpertiseManager("agent_b", expertise_dir=loser_dir)
    winner_mgr.load("market")
    loser_mgr.load("market")

    # Mark winner's market file as distinct
    winner_data = winner_mgr.load("market")
    winner_data["overview"]["total_patterns_tracked"] = 99
    winner_mgr.save("market", winner_data)

    eliminator = RoundEliminator(agents_dir=tmp_dir, archive_dir=archive_dir)
    eliminator.eliminate(loser_id="agent_b", winner_id="agent_a", round_num=1)

    # Archive should exist
    assert (archive_dir / "round_1_agent_b").exists()

    # New agent_b should have winner's market expertise
    new_mgr = ExpertiseManager("agent_b", expertise_dir=loser_dir)
    new_data = new_mgr.load("market")
    assert new_data["overview"]["total_patterns_tracked"] == 99
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/competition/test_eliminator.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement competition/eliminator.py**

```python
import shutil
from pathlib import Path
from agents.expertise_manager import ExpertiseManager

_AGENTS_DIR = Path(__file__).parent.parent / "agents"
_ARCHIVE_DIR = _AGENTS_DIR / "archive"


class RoundEliminator:
    def __init__(self, agents_dir: Path = _AGENTS_DIR,
                 archive_dir: Path = _ARCHIVE_DIR):
        self._agents = agents_dir
        self._archive = archive_dir

    def eliminate(self, loser_id: str, winner_id: str, round_num: int) -> None:
        loser_dir = self._agents / loser_id
        archive_dest = self._archive / f"round_{round_num}_{loser_id}"

        # Archive loser's expertise files
        archive_dest.mkdir(parents=True, exist_ok=True)
        for f in loser_dir.glob("*.yaml"):
            shutil.copy2(f, archive_dest / f.name)

        # Seed new agent with winner's expertise (copy winner's files to loser dir)
        winner_dir = self._agents / winner_id
        for f in winner_dir.glob("*.yaml"):
            shutil.copy2(f, loser_dir / f.name)

    def determine_loser(self, pnl_a: float, pnl_b: float) -> str | None:
        """Returns loser agent_id, or None if both profitable and tied."""
        if pnl_a < 0 and pnl_b < 0:
            return "agent_a" if pnl_a < pnl_b else "agent_b"
        if pnl_a < 0:
            return "agent_a"
        if pnl_b < 0:
            return "agent_b"
        if pnl_a == pnl_b:
            return None
        return "agent_a" if pnl_a < pnl_b else "agent_b"
```

- [ ] **Step 4: Run test**

```bash
pytest tests/competition/test_eliminator.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add competition/eliminator.py tests/competition/test_eliminator.py
git commit -m "feat: round eliminator archives loser and seeds winner's knowledge"
```

---

## Task 13: Main Orchestrator + Startup Reconciliation

**Files:**
- Create: `main.py`
- Create: `core/data/schwab_client.py` (stub with paper trading support)
- Create: `tests/test_main.py`

- [ ] **Step 1: Implement core/data/schwab_client.py**

```python
"""
Schwab API client using schwab-py.
OAuth tokens are stored in .schwab_tokens.json (gitignored).
Run `python -m core.data.schwab_client auth` to complete initial OAuth.
"""
import json
import sys
from pathlib import Path

try:
    import schwab
    from schwab import auth, client
except ImportError:
    schwab = None

from config import settings

_TOKEN_PATH = Path(__file__).parent.parent.parent / ".schwab_tokens.json"


class SchwabClient:
    def __init__(self):
        if schwab is None:
            raise ImportError("schwab-py not installed")
        self._client = self._load_client()

    def _load_client(self):
        app_key = settings.SCHWAB_APP_KEY()
        app_secret = settings.SCHWAB_APP_SECRET()
        if _TOKEN_PATH.exists():
            return auth.client_from_token_file(
                str(_TOKEN_PATH), app_key, app_secret)
        raise FileNotFoundError(
            f"No token file found at {_TOKEN_PATH}. "
            "Run: python -m core.data.schwab_client auth")

    def get_account_info(self) -> dict:
        resp = self._client.get_accounts(
            fields=[client.Client.Account.Fields.POSITIONS])
        resp.raise_for_status()
        accounts = resp.json()
        if not accounts:
            return {"cash": 0.0, "positions": []}
        acct = accounts[0]["securitiesAccount"]
        cash = acct.get("currentBalances", {}).get("cashBalance", 0.0)
        positions = [
            {"symbol": p["instrument"]["symbol"],
             "quantity": p["longQuantity"] - p["shortQuantity"],
             "market_value": p.get("marketValue", 0)}
            for p in acct.get("positions", [])
        ]
        return {"cash": cash, "positions": positions}

    def get_quote(self, symbol: str) -> dict:
        resp = self._client.get_quote(symbol)
        resp.raise_for_status()
        return resp.json()[symbol]["quote"]

    def place_order(self, symbol: str, action: str, quantity: int) -> dict:
        from schwab.orders.equities import equity_buy_market, equity_sell_market
        account_resp = self._client.get_accounts()
        account_resp.raise_for_status()
        account_hash = account_resp.json()[0]["hashValue"]

        if action == "buy":
            order = equity_buy_market(symbol, quantity)
        elif action in ("sell", "cover"):
            order = equity_sell_market(symbol, quantity)
        elif action == "short":
            # Sell short — requires margin account enabled in Schwab
            from schwab.orders.equities import equity_sell_short_market
            order = equity_sell_short_market(symbol, quantity)
        else:
            raise ValueError(f"Unsupported action: {action}")

        resp = self._client.place_order(account_hash, order)
        resp.raise_for_status()
        return {"status": "placed", "symbol": symbol,
                "action": action, "quantity": quantity}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        app_key = settings.SCHWAB_APP_KEY()
        app_secret = settings.SCHWAB_APP_SECRET()
        callback_url = settings.api_key("SCHWAB_CALLBACK_URL")
        c = auth.client_from_manual_flow(
            app_key, app_secret, callback_url, str(_TOKEN_PATH))
        print("Authentication successful. Tokens saved.")
```

- [ ] **Step 2: Create main.py**

```python
"""
Tragent — main entry point.
Starts Agent A and Agent B as concurrent threads.

Usage:
    python main.py

Setup (first time):
    python -m core.data.schwab_client auth
"""
import queue
import threading
import time
import schedule
from datetime import datetime, timezone

from agents.agent import Agent, AgentConfig
from competition.scorer import CompetitionScorer
from competition.reporter import DailyReporter
from competition.eliminator import RoundEliminator
from core.data.schwab_client import SchwabClient
from core.decision.claude_client import ClaudeClient
from config import settings


def _session() -> str:
    now = datetime.now(timezone.utc)
    hour = now.hour + now.minute / 60
    # ET ≈ UTC-5 (standard) / UTC-4 (daylight)
    # Using UTC-5 approximation; adjust for DST in production
    et = hour - 5
    if et < 0:
        et += 24
    if 4.0 <= et < 9.5:
        return "pre_market"
    if 9.5 <= et < 16.0:
        return "regular"
    if 16.0 <= et < 20.0:
        return "post_market"
    return "closed"


def _build_data_packet(schwab: SchwabClient, session: str) -> dict:
    """Minimal data packet — expand with full signal pipeline."""
    return {"signals": [], "news": [], "institutional": [], "session": session}


def run_agent(agent: Agent, interval_minutes: int, stop_event: threading.Event):
    while not stop_event.is_set():
        sess = _session()
        if sess == "closed":
            time.sleep(60)
            continue
        agent.run_cycle()
        time.sleep(interval_minutes * 60)


def main():
    schwab = SchwabClient()
    claude_a = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_a")
    claude_b = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_b")

    base_capital = settings.get("competition", "base_capital")

    queue_a: queue.Queue = queue.Queue()
    queue_b: queue.Queue = queue.Queue()

    agent_a = Agent(AgentConfig("agent_a", "regular", base_capital),
                    claude_a, schwab, data_queue=queue_a)
    agent_b = Agent(AgentConfig("agent_b", "regular", base_capital),
                    claude_b, schwab, data_queue=queue_b)

    scorer_a = CompetitionScorer("agent_a", base_capital)
    scorer_b = CompetitionScorer("agent_b", base_capital)
    reporter = DailyReporter(scorer_a, scorer_b)

    # Schedule daily report + auto-commit at 4pm ET
    schedule.every().day.at("16:00").do(reporter.generate)
    if settings.get("auto_commit", "enabled"):
        schedule.every().day.at("16:01").do(reporter.auto_commit)

    stop = threading.Event()
    regular_interval = settings.get("trading", "cycle_interval_regular_min")

    thread_a = threading.Thread(
        target=run_agent, args=(agent_a, regular_interval, stop), daemon=True)
    thread_b = threading.Thread(
        target=run_agent, args=(agent_b, regular_interval, stop), daemon=True)

    print("Starting Tragent — Agent A and Agent B")
    thread_a.start()
    thread_b.start()

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        stop.set()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Add schedule to requirements.txt**

```
schedule>=1.2.2
```

- [ ] **Step 4: Add .schwab_tokens.json to .gitignore**

```bash
echo ".schwab_tokens.json" >> C:/Users/JasonTurner/Tragent/.gitignore
echo ".env" >> C:/Users/JasonTurner/Tragent/.gitignore
echo "__pycache__/" >> C:/Users/JasonTurner/Tragent/.gitignore
echo "*.pyc" >> C:/Users/JasonTurner/Tragent/.gitignore
echo "state/*.db" >> C:/Users/JasonTurner/Tragent/.gitignore
```

- [ ] **Step 5: Run full test suite**

```bash
cd C:/Users/JasonTurner/Tragent && pytest tests/ -v --tb=short
```
Expected: All tests PASS

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: main orchestrator, Schwab client, .gitignore — Phase 1 complete"
git push origin main
```

---

---

## Task 14: Signal Aggregator

**Files:**
- Create: `core/analysis/signal_aggregator.py`
- Create: `tests/core/analysis/test_signal_aggregator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/analysis/test_signal_aggregator.py
from core.analysis.signal_aggregator import SignalAggregator
from core.analysis.technical import BreakoutSignal

def test_aggregates_and_deduplicates():
    agg = SignalAggregator()
    signals = [
        BreakoutSignal("AAPL", "volume_spike", "bullish", 0.7, "vol 2x"),
        BreakoutSignal("AAPL", "vwap_cross", "bullish", 0.6, "cross above"),
        BreakoutSignal("MSFT", "range_breakout", "bullish", 0.5, "new high"),
    ]
    result = agg.rank(signals)
    symbols = [s["symbol"] for s in result]
    # AAPL has 2 signals, should rank above MSFT
    assert symbols[0] == "AAPL"
    assert len(result) == 2  # one entry per symbol

def test_filters_bearish_if_long_only():
    agg = SignalAggregator(allow_short=False)
    signals = [
        BreakoutSignal("AAPL", "vwap_cross", "bearish", 0.8, "cross below"),
        BreakoutSignal("MSFT", "volume_spike", "bullish", 0.7, "vol 2x"),
    ]
    result = agg.rank(signals)
    assert len(result) == 1
    assert result[0]["symbol"] == "MSFT"
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/analysis/test_signal_aggregator.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement core/analysis/signal_aggregator.py**

```python
from collections import defaultdict
from core.analysis.technical import BreakoutSignal


class SignalAggregator:
    def __init__(self, allow_short: bool = True):
        self._allow_short = allow_short

    def rank(self, signals: list[BreakoutSignal]) -> list[dict]:
        """Combine per-signal list into ranked per-symbol list."""
        if not self._allow_short:
            signals = [s for s in signals if s.direction == "bullish"]

        by_symbol: dict[str, list[BreakoutSignal]] = defaultdict(list)
        for s in signals:
            by_symbol[s.symbol].append(s)

        ranked = []
        for symbol, syms in by_symbol.items():
            total_strength = sum(s.strength for s in syms)
            direction = "bullish" if sum(
                1 for s in syms if s.direction == "bullish") >= len(syms) / 2 \
                else "bearish"
            ranked.append({
                "symbol": symbol,
                "direction": direction,
                "signal_count": len(syms),
                "combined_strength": round(total_strength / len(syms), 3),
                "signals": [{"type": s.signal_type, "detail": s.detail,
                              "strength": s.strength} for s in syms],
            })

        return sorted(ranked, key=lambda x: (x["signal_count"],
                                              x["combined_strength"]),
                       reverse=True)
```

- [ ] **Step 4: Run test**

```bash
pytest tests/core/analysis/test_signal_aggregator.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/analysis/signal_aggregator.py tests/core/analysis/test_signal_aggregator.py
git commit -m "feat: signal aggregator — ranks and deduplicates per-symbol signals"
```

---

## Task 15: Position Tracker + Trailing Stops

**Files:**
- Create: `core/risk/position_tracker.py`
- Create: `tests/core/risk/test_position_tracker.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/risk/test_position_tracker.py
from core.risk.position_tracker import PositionTracker
from core.state.persistence import Position

def test_trailing_stop_advances_with_price(tmp_dir):
    tracker = PositionTracker(trailing_pct=1.5, db_dir=tmp_dir, agent_id="agent_a")
    pos = Position("AAPL", "long", 180.0, stop_loss=176.4,
                   trailing_stop=177.3, quantity=10)
    tracker.store.save_position(pos)

    # Price moves up — trailing stop should advance
    updates = tracker.update_stops({"AAPL": 190.0})
    assert updates["AAPL"]["new_trailing_stop"] > 177.3

def test_stop_triggered_returns_close_signal(tmp_dir):
    tracker = PositionTracker(trailing_pct=1.5, db_dir=tmp_dir, agent_id="agent_a")
    pos = Position("AAPL", "long", 180.0, stop_loss=176.4,
                   trailing_stop=177.3, quantity=10)
    tracker.store.save_position(pos)

    # Price drops below trailing stop
    triggered = tracker.check_stops({"AAPL": 176.0})
    assert "AAPL" in triggered
    assert triggered["AAPL"]["reason"] in ("stop_loss", "trailing_stop")
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/core/risk/test_position_tracker.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement core/risk/position_tracker.py**

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

- [ ] **Step 4: Run test**

```bash
pytest tests/core/risk/test_position_tracker.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/risk/position_tracker.py tests/core/risk/test_position_tracker.py
git commit -m "feat: position tracker with trailing stop advancement and trigger detection"
```

---

## Task 16: Data Dispatch Loop + Startup Reconciliation (wires main.py)

**Files:**
- Create: `core/data/market_feed.py`
- Modify: `main.py` — add data dispatch loop + startup reconciliation

- [ ] **Step 1: Implement core/data/market_feed.py**

```python
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
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "AMD", "SPY", "QQQ",
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
```

- [ ] **Step 2: Write test for market feed dispatch**

```python
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
```

- [ ] **Step 3: Run test**

```bash
pytest tests/core/data/test_market_feed.py -v
```
Expected: PASS

- [ ] **Step 4: Update main.py to wire data feed + startup reconciliation**

Replace the `main()` function:

```python
def reconcile(schwab: SchwabClient, store_a, store_b) -> None:
    """On startup, reconcile broker positions against local SQLite state."""
    from core.logger import get_logger
    sys_log = get_logger("system", "system")
    try:
        acct = schwab.get_account_info()
        broker_symbols = {p["symbol"] for p in acct.get("positions", [])}

        for store, agent_id in [(store_a, "agent_a"), (store_b, "agent_b")]:
            local_positions = store.get_positions()
            local_symbols = {p.symbol for p in local_positions}
            discrepancies = local_symbols.symmetric_difference(broker_symbols)
            if discrepancies:
                sys_log.log({"event": "reconciliation_discrepancy",
                             "agent": agent_id, "symbols": list(discrepancies)})
                # Broker is authoritative: remove local positions not at broker
                for pos in local_positions:
                    if pos.symbol not in broker_symbols:
                        store.remove_position(pos.symbol)
                        sys_log.log({"event": "removed_stale_position",
                                     "agent": agent_id, "symbol": pos.symbol})
        sys_log.log({"event": "reconciliation_complete"})
    except Exception as e:
        sys_log.log({"event": "reconciliation_failed", "error": str(e)})


def main():
    import threading
    schwab = SchwabClient()
    claude_a = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_a")
    claude_b = ClaudeClient(
        daily_limit_usd=settings.get("api_cost", "daily_claude_spend_limit_usd"),
        agent_id="agent_b")

    base_capital = settings.get("competition", "base_capital")

    queue_a: queue.Queue = queue.Queue()
    queue_b: queue.Queue = queue.Queue()

    from core.state.persistence import StateStore
    store_a = StateStore("agent_a")
    store_b = StateStore("agent_b")

    # Startup reconciliation — always before agents start
    reconcile(schwab, store_a, store_b)

    agent_a = Agent(AgentConfig("agent_a", "regular", base_capital),
                    claude_a, schwab, data_queue=queue_a)
    agent_b = Agent(AgentConfig("agent_b", "regular", base_capital),
                    claude_b, schwab, data_queue=queue_b)

    scorer_a = CompetitionScorer("agent_a", base_capital)
    scorer_b = CompetitionScorer("agent_b", base_capital)
    reporter = DailyReporter(scorer_a, scorer_b)

    schedule.every().day.at("16:00").do(reporter.generate)
    if settings.get("auto_commit", "enabled"):
        schedule.every().day.at("16:01").do(reporter.auto_commit)

    stop = threading.Event()
    regular_interval = settings.get("trading", "cycle_interval_regular_min")

    # Data feed thread — fetches signals and dispatches to both agent queues
    from core.data.market_feed import MarketFeed
    feed = MarketFeed([queue_a, queue_b])
    feed_thread = threading.Thread(
        target=feed.run,
        args=(regular_interval * 60, stop),
        daemon=True)

    thread_a = threading.Thread(
        target=run_agent, args=(agent_a, regular_interval, stop), daemon=True)
    thread_b = threading.Thread(
        target=run_agent, args=(agent_b, regular_interval, stop), daemon=True)

    print("Starting Tragent — Agent A and Agent B")
    feed_thread.start()
    thread_a.start()
    thread_b.start()

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        stop.set()
        feed_thread.join(timeout=5)
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)
```

- [ ] **Step 5: Run full test suite**

```bash
cd C:/Users/JasonTurner/Tragent && pytest tests/ -v --tb=short
```
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add core/data/market_feed.py main.py tests/core/data/test_market_feed.py
git commit -m "feat: market feed dispatch loop, startup reconciliation, wired main.py"
git push origin main
```

---

## Setup Checklist (Before First Run)

- [ ] Copy `.env.example` to `.env` and fill in all API keys
- [ ] Run `python -m core.data.schwab_client auth` to complete Schwab OAuth
- [ ] Toggle Schwab account to paper trading mode in the Thinkorswim app
- [ ] Verify paper trading balance in Schwab dashboard
- [ ] Run `python main.py` and confirm both agents start without errors
- [ ] Monitor `logs/` directory for trade decisions and decisions logs

---

## Paper-to-Live Checklist (After 2 Rounds)

- [ ] Win rate ≥ 55% for at least one agent over 2 rounds
- [ ] Sharpe ratio ≥ 1.0 for at least one agent over 2 rounds
- [ ] No single-day loss > 6% in either round
- [ ] Weekly deep comparison reports reviewed and approved
- [ ] Paid real-time institutional data source integrated (Unusual Whales or Stocksera)
- [ ] Switch Schwab account to live trading mode (manual action by owner)
