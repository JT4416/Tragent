# Debate + Peer Exchange Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured self-debate (bull/bear case) to every trading decision and post-trade agent-to-agent peer exchange via a shared in-memory queue so agents learn from each other's trades without blindly copying.

**Architecture:** Eight sequential tasks. Foundation first (PositionTracker shared store, PeerExchange), then decision layer (ClaudeClient, PromptBuilder), then SelfImprove peer learning, then MarketFeed prices, then the full Agent run_cycle overhaul that wires it all together, then main.py.

**Tech Stack:** Python 3.11+, sqlite3, queue.Queue, pytest, pyyaml, anthropic SDK

**Already done (skip these):**
- `core/state/persistence.py`: `entry_time` field, `get_position(symbol)`, schema migration ✅
- `agents/agent.py`: `close_position()` method ✅

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/risk/position_tracker.py` | Modify | Accept optional `store` param to share StateStore with Agent |
| `agents/peer_exchange.py` | **Create** | PeerExchange: register/publish/drain per-agent inboxes |
| `core/decision/claude_client.py` | Modify | Add `bull_case`/`bear_case` to `TradeDecision`; update `_parse_response`; raise `max_tokens` to 768 |
| `core/decision/prompt_builder.py` | Modify | Add debate instruction + bull/bear to response format; add `build_peer_learning_prompt` |
| `agents/self_improve.py` | Modify | Add `run_peer_learning(insight)` method |
| `core/data/market_feed.py` | Modify | Collect `prices` dict during OHLCV loop; add to packet |
| `agents/agent.py` | Modify | Accept `peer_exchange`; own `PositionTracker`; revised `run_cycle` with stop checks and peer drain; publish at entry/close |
| `main.py` | Modify | Instantiate PeerExchange; register IDs; pass to agents |
| `tests/agents/test_peer_exchange.py` | **Create** | Unit tests for register/publish/drain |
| `tests/agents/test_agent.py` | Modify | Add: stop-triggered close in run_cycle; peer drain at REUSE; entry publish |
| `tests/agents/test_self_improve.py` | Modify | Add: run_peer_learning updates trade expertise |
| `tests/core/decision/test_claude_client.py` | Modify | Add: bull_case/bear_case parsed from response |
| `tests/core/risk/test_position_tracker.py` | Modify | Add: shared store param |

---

## Task 1: PositionTracker — Accept Shared Store

**Files:**
- Modify: `core/risk/position_tracker.py`
- Modify: `tests/core/risk/test_position_tracker.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/risk/test_position_tracker.py`:

```python
from core.state.persistence import StateStore

def test_shared_store_is_used_directly(tmp_path):
    """PositionTracker should use a provided store, not create a new one."""
    shared_store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="MSFT", direction="long", entry_price=400.0,
                   stop_loss=392.0, trailing_stop=394.0, quantity=5,
                   entry_time="2026-04-01T10:00:00+00:00")
    shared_store.save_position(pos)

    tracker = PositionTracker(trailing_pct=1.5, agent_id="agent_a",
                               store=shared_store)
    # Tracker should see the position saved on the shared store
    triggered = tracker.check_stops({"MSFT": 393.0})
    assert "MSFT" in triggered
    assert triggered["MSFT"]["reason"] == "trailing_stop"
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/core/risk/test_position_tracker.py::test_shared_store_is_used_directly -v
```

Expected: FAIL — `PositionTracker.__init__` has no `store` parameter.

- [ ] **Step 3: Implement**

Replace `core/risk/position_tracker.py` entirely:

```python
from pathlib import Path
from core.state.persistence import StateStore


class PositionTracker:
    def __init__(self, trailing_pct: float, agent_id: str,
                 db_dir: Path | None = None, store=None):
        self._trailing_pct = trailing_pct
        self.store = store if store is not None else (
            StateStore(agent_id, db_dir) if db_dir else StateStore(agent_id)
        )

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

- [ ] **Step 4: Run all position tracker tests**

```
pytest tests/core/risk/test_position_tracker.py -v
```

Expected: all PASS (3 tests total).

- [ ] **Step 5: Commit**

```bash
git add core/risk/position_tracker.py tests/core/risk/test_position_tracker.py
git commit -m "feat: add optional shared store param to PositionTracker"
```

---

## Task 2: PeerExchange — New Class

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
    result = ex.drain("agent_b")
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"


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


def test_publish_unregistered_raises():
    ex = PeerExchange()
    ex.register("agent_a")
    with pytest.raises(KeyError):
        ex.publish("agent_z", {"event": "entry"})


def test_drain_unregistered_raises():
    ex = PeerExchange()
    with pytest.raises(KeyError):
        ex.drain("agent_z")


def test_multiple_insights_drained_in_order():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    ex.publish("agent_a", {"event": "entry", "n": 1})
    ex.publish("agent_a", {"event": "close", "n": 2})
    result = ex.drain("agent_b")
    assert len(result) == 2
    assert result[0]["n"] == 1
    assert result[1]["n"] == 2
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/agents/test_peer_exchange.py -v
```

Expected: FAIL — `agents/peer_exchange.py` does not exist.

- [ ] **Step 3: Implement**

Create `agents/peer_exchange.py`:

```python
import queue


class PeerExchange:
    """Thread-safe in-memory exchange for sharing trade insights between agents.

    Register each agent before use. publish() puts an insight into every
    registered inbox except the sender's. drain() returns and clears all
    pending insights for the caller.
    """

    def __init__(self):
        self._inboxes: dict[str, queue.Queue] = {}

    def register(self, agent_id: str) -> None:
        """Create an inbox for agent_id. Call once per agent before threads start."""
        self._inboxes[agent_id] = queue.Queue()

    def publish(self, from_agent_id: str, insight: dict) -> None:
        """Broadcast insight to all agents except the sender."""
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

Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/peer_exchange.py tests/agents/test_peer_exchange.py
git commit -m "feat: add PeerExchange for agent-to-agent insight sharing"
```

---

## Task 3: ClaudeClient — bull_case / bear_case

**Files:**
- Modify: `core/decision/claude_client.py`
- Modify: `tests/core/decision/test_claude_client.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/decision/test_claude_client.py`:

```python
def test_parse_decision_includes_bull_bear_cases():
    raw = json.dumps({
        "bull_case": "Strong volume breakout above 52W high",
        "bear_case": "Broader market in downtrend",
        "action": "buy",
        "symbol": "NVDA",
        "confidence": 0.75,
        "position_size_pct": 5.0,
        "reasoning": "Bull case wins — institutional accumulation confirms",
        "signals_used": ["volume_spike"],
        "skip_reason": None,
    })
    decision = ClaudeClient._parse_response(raw)
    assert decision.bull_case == "Strong volume breakout above 52W high"
    assert decision.bear_case == "Broader market in downtrend"


def test_parse_decision_defaults_bull_bear_to_empty_string():
    """Responses without bull_case/bear_case should still parse cleanly."""
    raw = json.dumps({
        "action": "hold", "symbol": None, "confidence": 0.4,
        "position_size_pct": 0, "reasoning": "no signal",
        "signals_used": [], "skip_reason": "nothing compelling",
    })
    decision = ClaudeClient._parse_response(raw)
    assert decision.bull_case == ""
    assert decision.bear_case == ""
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/core/decision/test_claude_client.py::test_parse_decision_includes_bull_bear_cases tests/core/decision/test_claude_client.py::test_parse_decision_defaults_bull_bear_to_empty_string -v
```

Expected: FAIL — `TradeDecision` has no `bull_case` or `bear_case` fields.

- [ ] **Step 3: Implement**

Replace `core/decision/claude_client.py` entirely:

```python
import json
from dataclasses import dataclass
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
    action: str            # buy | sell | hold
    symbol: str | None
    confidence: float
    position_size_pct: float
    reasoning: str
    signals_used: list[str]
    skip_reason: str | None
    bull_case: str = ""
    bear_case: str = ""


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
            max_tokens=768,
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
            bull_case=data.get("bull_case", ""),
            bear_case=data.get("bear_case", ""),
        )

    def _track_cost(self, usage) -> None:
        cost = (usage.input_tokens / 1_000_000 * _INPUT_COST_PER_1M +
                usage.output_tokens / 1_000_000 * _OUTPUT_COST_PER_1M)
        self.daily_spend_usd += cost
```

- [ ] **Step 4: Run all claude_client tests**

```
pytest tests/core/decision/test_claude_client.py -v
```

Expected: all PASS (6 tests total).

- [ ] **Step 5: Commit**

```bash
git add core/decision/claude_client.py tests/core/decision/test_claude_client.py
git commit -m "feat: add bull_case/bear_case to TradeDecision; raise max_tokens to 768"
```

---

## Task 4: PromptBuilder — Debate Instruction + Peer Learning Prompt

**Files:**
- Modify: `core/decision/prompt_builder.py`
- Modify: `tests/core/decision/test_prompt_builder.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/decision/test_prompt_builder.py`:

```python
from core.decision.prompt_builder import build_peer_learning_prompt


def test_decision_prompt_includes_debate_instruction():
    from core.decision.prompt_builder import build_decision_prompt
    prompt = build_decision_prompt(
        session="regular", expertise={}, signals=[], news=[],
        institutional=[], open_positions=[], cash=500.0,
        daily_pnl=0.0, daily_pnl_pct=0.0, daily_loss_remaining=30.0,
    )
    assert "bull_case" in prompt
    assert "bear_case" in prompt
    assert "bull" in prompt.lower()
    assert "bear" in prompt.lower()


def test_peer_learning_prompt_contains_insight_fields():
    insight = {
        "from_agent": "agent_a", "event": "close",
        "trade_record": {"symbol": "AAPL", "direction": "long"},
        "reasoning": "strong breakout",
        "bull_case": "VWAP cross confirmed",
        "bear_case": "market was choppy",
        "outcome": "win", "pnl_pct": 3.5, "duration": "45m",
    }
    prompt = build_peer_learning_prompt(insight, "patterns: []")
    assert "agent_a" in prompt
    assert "VWAP cross confirmed" in prompt
    assert "market was choppy" in prompt
    assert "win" in prompt
    assert "3.50" in prompt
    assert "patterns: []" in prompt


def test_peer_learning_prompt_includes_do_not_copy_instruction():
    insight = {
        "from_agent": "agent_b", "event": "entry",
        "trade_record": {"symbol": "MSFT"},
        "reasoning": "momentum", "bull_case": "up", "bear_case": "down",
        "outcome": "open", "pnl_pct": 0.0, "duration": "0m",
    }
    prompt = build_peer_learning_prompt(insight, "patterns: []")
    assert "not" in prompt.lower()
    assert "copy" in prompt.lower()
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/core/decision/test_prompt_builder.py::test_decision_prompt_includes_debate_instruction tests/core/decision/test_prompt_builder.py::test_peer_learning_prompt_contains_insight_fields tests/core/decision/test_prompt_builder.py::test_peer_learning_prompt_includes_do_not_copy_instruction -v
```

Expected: FAIL — prompt has no bull/bear fields; `build_peer_learning_prompt` doesn't exist.

- [ ] **Step 3: Implement**

Replace `core/decision/prompt_builder.py` entirely:

```python
import json
import yaml
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
Before deciding, articulate the strongest bull and bear case for the leading candidate.
Let the better argument win.

## Response Format (JSON only)
{{
  "bull_case": "strongest argument FOR this trade",
  "bear_case": "strongest argument AGAINST this trade",
  "action": "buy|sell|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "which case won and why",
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
{json.dumps(trade_record, indent=2)}

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


def build_peer_learning_prompt(
    insight: dict,
    current_yaml: str,
    max_lines: int = 1000,
) -> str:
    return f"""## Peer Trade Insight (your competitor — do not copy blindly)
From: {insight['from_agent']} | Event: {insight['event']}
They traded: {insight['trade_record'].get('symbol', 'unknown')} {insight['trade_record'].get('direction', '')}
Their bull case: {insight['bull_case']}
Their bear case: {insight['bear_case']}
Their reasoning: {insight['reasoning']}
Outcome: {insight['outcome']} | P&L: {insight['pnl_pct']:.2f}% | Duration: {insight['duration']}

## Your Current Expertise File (max {max_lines} lines)
{current_yaml}

## Task
What can you learn from your competitor's trade?
- If they identified a pattern you have missed, add it with confidence 0.1 lower than theirs
- If their outcome confirms your existing beliefs, increase confidence by 0.05
- If their outcome contradicts your existing beliefs, decrease confidence by 0.05
- Do NOT copy their position sizing or stop levels — evolve your own parameters
- Return the complete updated YAML only, no prose"""


def _yaml_summary(data: dict) -> str:
    return yaml.dump(data, default_flow_style=False)[:2000]


def _format_list(items: list) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {item}" for item in items)


def _format_movers(movers: list[dict]) -> str:
    if not movers:
        return "  (none)"
    lines = []
    for m in movers:
        lines.append(
            f"  - {m['symbol']:6s}  {m['netPercentChange']:+.2f}%"
            f"  ${m['lastPrice']:.2f}"
            f"  vol {m['volume']:,}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run all prompt_builder tests**

```
pytest tests/core/decision/test_prompt_builder.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/decision/prompt_builder.py tests/core/decision/test_prompt_builder.py
git commit -m "feat: add debate instruction and build_peer_learning_prompt to PromptBuilder"
```

---

## Task 5: SelfImprove — run_peer_learning

**Files:**
- Modify: `agents/self_improve.py`
- Modify: `tests/agents/test_self_improve.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/agents/test_self_improve.py`:

```python
def test_run_peer_learning_updates_trade_expertise(tmp_dir):
    mgr = ExpertiseManager("agent_b", expertise_dir=tmp_dir)
    mgr.load("trade")  # seeds file

    mock_claude = MagicMock()
    updated_yaml = yaml.dump({
        "overview": {"last_updated": "2026-04-02", "total_patterns_tracked": 1},
        "lessons_learned": [
            {"pattern": "peer: volume spike worked for competitor",
             "confidence": 0.65}
        ],
    })
    mock_claude.self_improve.return_value = updated_yaml

    orchestrator = SelfImproveOrchestrator(mgr, mock_claude)
    insight = {
        "from_agent": "agent_a", "event": "close",
        "trade_record": {
            "symbol": "AAPL", "direction": "long",
            "signals_used": ["volume_spike"],
        },
        "reasoning": "volume confirmation",
        "bull_case": "strong accumulation",
        "bear_case": "overbought RSI",
        "outcome": "win", "pnl_pct": 2.8, "duration": "1h30m",
    }
    orchestrator.run_peer_learning(insight)

    assert mock_claude.self_improve.called
    loaded = mgr.load("trade")
    assert loaded is not None
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/agents/test_self_improve.py::test_run_peer_learning_updates_trade_expertise -v
```

Expected: FAIL — `run_peer_learning` doesn't exist.

- [ ] **Step 3: Implement**

Replace `agents/self_improve.py` entirely:

```python
import yaml
from core.decision.prompt_builder import build_self_improve_prompt, build_peer_learning_prompt
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
        files_to_update.add("trade")

        for file_name in files_to_update:
            current_data = self._mgr.load(file_name)
            current_yaml = yaml.dump(current_data, default_flow_style=False)
            prompt = build_self_improve_prompt(
                trade_record=trade_record,
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

    def run_peer_learning(self, insight: dict) -> None:
        """Update expertise based on a trade insight from the competing agent."""
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
                pass

    def _determine_files(self, trade_record: dict) -> set[str]:
        files = set()
        for signal in trade_record.get("signals_used", []):
            if signal in _SIGNAL_TO_EXPERTISE:
                files.add(_SIGNAL_TO_EXPERTISE[signal])
        return files
```

- [ ] **Step 4: Run all self_improve tests**

```
pytest tests/agents/test_self_improve.py -v
```

Expected: all PASS (2 tests total).

- [ ] **Step 5: Commit**

```bash
git add agents/self_improve.py tests/agents/test_self_improve.py
git commit -m "feat: add run_peer_learning to SelfImproveOrchestrator"
```

---

## Task 6: MarketFeed — Add prices to packet

**Files:**
- Modify: `core/data/market_feed.py`
- Create: `tests/core/data/test_market_feed.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/data/test_market_feed.py`:

```python
import queue
from unittest.mock import MagicMock, patch
import pandas as pd
from core.data.market_feed import MarketFeed


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
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/core/data/test_market_feed.py -v
```

Expected: FAIL — `packet` has no `prices` key.

- [ ] **Step 3: Implement**

Replace `core/data/market_feed.py` entirely:

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
    # Core large caps
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "AMD", "SPY", "QQQ",
    # Inverse ETFs — long-only bearish exposure (no short selling)
    "SH",   # ProShares Short S&P500 (1x inverse)
    "SDS",  # ProShares UltraShort S&P500 (2x inverse) — short-duration hold only
    "QID",  # ProShares UltraShort QQQ (2x inverse) — short-duration hold only
    "DOG",  # ProShares Short Dow30 (1x inverse)
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
                 schwab_client=None):
        self._queues = agent_queues
        self._watchlist = watchlist
        self._schwab = schwab_client
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
                df = self._yf.fetch_ohlcv(symbol, period="3mo")
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
        for symbol in self._watchlist[:3]:
            try:
                inst_signals.extend(self._inst.fetch_insider_trades(symbol)[:2])
            except Exception:
                continue

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
            "prices": prices,
            "signals": ranked[:10],
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

- [ ] **Step 4: Run market feed tests**

```
pytest tests/core/data/test_market_feed.py -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add core/data/market_feed.py tests/core/data/test_market_feed.py
git commit -m "feat: add prices dict to MarketFeed packet"
```

---

## Task 7: Agent — PeerExchange Wiring + Revised run_cycle

**Files:**
- Modify: `agents/agent.py`
- Modify: `tests/agents/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/agents/test_agent.py`:

```python
from agents.peer_exchange import PeerExchange


def _make_agent_with_exchange(tmp_path):
    config = AgentConfig(agent_id="agent_a", session="regular",
                         base_capital=50000.0)
    mock_claude = MagicMock()
    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {"cash": 50000.0, "positions": []}
    exchange = PeerExchange()
    exchange.register("agent_a")
    exchange.register("agent_b")
    agent = Agent(config, mock_claude, mock_schwab,
                  data_queue=queue.Queue(), expertise_dir=tmp_path,
                  db_dir=tmp_path, peer_exchange=exchange)
    agent._improve = MagicMock()
    return agent, exchange


def test_run_cycle_drains_peer_insights_before_decide(tmp_path):
    agent, exchange = _make_agent_with_exchange(tmp_path)
    agent._claude.decide = MagicMock(return_value=MagicMock(
        action="hold", symbol=None, confidence=0.3, position_size_pct=0,
        reasoning="no signal", signals_used=[], skip_reason="low confidence",
        bull_case="", bear_case="",
    ))
    exchange.publish("agent_b", {
        "from_agent": "agent_b", "event": "entry",
        "trade_record": {"symbol": "MSFT", "signals_used": []},
        "reasoning": "breakout", "bull_case": "up", "bear_case": "down",
        "outcome": "open", "pnl_pct": 0.0, "duration": "0m",
    })
    agent._queue.put({
        "signals": [], "news": [], "institutional": [],
        "session": "regular", "movers": [], "prices": {},
    })
    agent.run_cycle()
    agent._improve.run_peer_learning.assert_called_once()


def test_run_cycle_triggers_stop_close(tmp_path):
    agent, _ = _make_agent_with_exchange(tmp_path)
    pos = Position(
        symbol="AAPL", direction="long", entry_price=100.0,
        stop_loss=95.0, trailing_stop=98.0, quantity=10,
        entry_time="2026-04-02T10:00:00+00:00",
    )
    agent._store.save_position(pos)
    agent._claude.decide = MagicMock(return_value=MagicMock(
        action="hold", symbol=None, confidence=0.3, position_size_pct=0,
        reasoning="no signal", signals_used=[], skip_reason="low confidence",
        bull_case="", bear_case="",
    ))
    agent._queue.put({
        "signals": [], "news": [], "institutional": [],
        "session": "regular", "movers": [],
        "prices": {"AAPL": 97.5},  # below trailing_stop of 98.0
    })
    agent.run_cycle()
    agent._schwab.place_order.assert_called_once_with(
        symbol="AAPL", action="sell", quantity=10)


def test_close_position_publishes_to_exchange(tmp_path):
    agent, exchange = _make_agent_with_exchange(tmp_path)
    pos = Position(
        symbol="NVDA", direction="long", entry_price=800.0,
        stop_loss=784.0, trailing_stop=788.0, quantity=5,
        entry_time="2026-04-02T10:00:00+00:00",
    )
    agent._store.save_position(pos)
    agent.close_position("NVDA", exit_price=850.0, reason="agent_decision")
    insights = exchange.drain("agent_b")
    assert len(insights) == 1
    assert insights[0]["event"] == "close"
    assert insights[0]["outcome"] == "win"
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/agents/test_agent.py::test_run_cycle_drains_peer_insights_before_decide tests/agents/test_agent.py::test_run_cycle_triggers_stop_close tests/agents/test_agent.py::test_close_position_publishes_to_exchange -v
```

Expected: FAIL — Agent has no `peer_exchange` param; run_cycle has no stop check or peer drain.

- [ ] **Step 3: Implement**

Replace `agents/agent.py` entirely:

```python
import queue
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agents.expertise_manager import ExpertiseManager
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
                 peer_exchange=None):
        self._cfg = config
        self._claude = claude_client
        self._schwab = schwab_client
        self._queue = data_queue
        self._exchange = peer_exchange
        self._mgr = ExpertiseManager(config.agent_id, expertise_dir)
        self._store = StateStore(config.agent_id, db_dir) if db_dir \
            else StateStore(config.agent_id)
        self._improve = SelfImproveOrchestrator(self._mgr, claude_client)
        self._tracker = PositionTracker(
            trailing_pct=settings.get("risk", "trailing_stop_pct"),
            agent_id=config.agent_id,
            store=self._store,
        )
        self._logger = get_logger(config.agent_id, "trades", log_dir) \
            if log_dir else get_logger(config.agent_id, "trades")
        self._risk = RiskGate(RiskConfig(
            max_position_size_pct=settings.get("risk", "max_position_size_pct"),
            daily_loss_limit_pct=settings.get("risk", "daily_loss_limit_pct"),
            max_concurrent_positions=settings.get("risk", "max_concurrent_positions"),
            confidence_threshold_regular=settings.get(
                "risk", "confidence_threshold_regular"),
            open_blackout_minutes=settings.get("risk", "open_blackout_minutes"),
        ))

    def run_cycle(self) -> None:
        try:
            market_data = self._queue.get_nowait()
        except queue.Empty:
            return

        prices = market_data.get("prices", {})

        # Drain and process peer insights BEFORE loading expertise
        if self._exchange:
            for insight in self._exchange.drain(self._cfg.agent_id):
                self._improve.run_peer_learning(insight)

        # REUSE: load all expertise (after peer learning so files are current)
        expertise = self._mgr.load_all()

        # Check stops and close any triggered positions
        triggered = self._tracker.check_stops(prices)
        for symbol, info in triggered.items():
            self.close_position(symbol, info["trigger_price"], info["reason"])

        # Advance trailing stops
        self._tracker.update_stops(prices)

        evolved = expertise.get("trade", {}).get("evolved_parameters", {})
        session = market_data.get("session", "regular")

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
            movers=market_data.get("movers", []),
        )

        decision = self._claude.decide("", prompt)

        if decision.action == "hold":
            self._logger.log({"event": "hold", "reason": decision.skip_reason,
                               "confidence": decision.confidence})
            return

        if decision.action == "sell":
            if decision.symbol:
                quote = self._schwab.get_quote(decision.symbol)
                price = quote.get("lastPrice") or quote.get("mark") or 0.0
                if price > 0:
                    self.close_position(decision.symbol, price,
                                        reason="agent_decision")
                else:
                    self._logger.log({
                        "event": "sell_skipped",
                        "reason": "no_quote",
                        "symbol": decision.symbol,
                    })
            return

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

        if not risk_result.approved:
            self._logger.log({"event": "risk_blocked", "reason": risk_result.reason,
                               "action": decision.action, "symbol": decision.symbol})
            return

        self._execute(decision, cash, evolved)

    def _execute(self, decision, cash: float, evolved: dict) -> None:
        size_pct = min(decision.position_size_pct,
                       evolved.get("max_position_size_pct", 5.0))

        quote = self._schwab.get_quote(decision.symbol)
        price = quote.get("lastPrice") or quote.get("mark") or 1.0
        quantity = max(1, int((cash * size_pct / 100) / price))

        stop_pct = evolved.get("stop_loss_pct", 2.0)
        trailing_pct = evolved.get("trailing_stop_pct", 1.5)
        stop_price = round(price * (1 - stop_pct / 100), 2)
        direction = "long"

        self._schwab.place_order(
            symbol=decision.symbol,
            action=decision.action,
            quantity=quantity,
        )

        self._store.save_position(
            Position(
                symbol=decision.symbol,
                direction=direction,
                entry_price=price,
                stop_loss=stop_price,
                trailing_stop=round(price * (1 - trailing_pct / 100), 2),
                quantity=quantity,
                entry_time=datetime.now(timezone.utc).isoformat(),
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

        self._improve.run(
            trade_record=trade_record,
            original_reasoning=decision.reasoning,
            outcome="open",
            pnl_pct=0.0,
            duration="0m",
        )

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

    def close_position(self, symbol: str, exit_price: float,
                       reason: str = "stop") -> None:
        """Close an open position, calculate real P&L, trigger learn loop."""
        pos = self._store.get_position(symbol)
        if pos is None:
            return

        pnl = round((exit_price - pos.entry_price) * pos.quantity, 2)
        pnl_pct = round(
            (exit_price - pos.entry_price) / pos.entry_price * 100, 2
        ) if pos.entry_price else 0.0

        if pos.entry_time:
            entry_dt = datetime.fromisoformat(pos.entry_time)
            secs = int((datetime.now(timezone.utc) - entry_dt).total_seconds())
            hours, rem = divmod(secs, 3600)
            mins = rem // 60
            duration = f"{hours}h{mins}m" if hours else f"{mins}m"
        else:
            duration = "unknown"

        # Remove from store FIRST to prevent double-sell if order raises
        self._store.update_round_pnl(self._store.get_round_pnl() + pnl)
        self._store.remove_position(symbol)

        self._schwab.place_order(
            symbol=symbol, action="sell", quantity=pos.quantity)

        self._logger.log({
            "event": "position_closed", "symbol": symbol, "reason": reason,
            "entry": pos.entry_price, "exit": exit_price,
            "pnl": pnl, "pnl_pct": pnl_pct, "duration": duration,
        })

        trade_record = {
            "trade_id": f"close_{self._cfg.agent_id}_{int(time.time())}",
            "symbol": symbol, "direction": pos.direction,
            "entry": pos.entry_price, "exit": exit_price,
            "pnl_pct": pnl_pct, "signals_used": [],
            "outcome": "win" if pnl > 0 else "loss",
            "claude_confidence": None,
            "bull_case": "", "bear_case": "",
        }
        self._improve.run(
            trade_record=trade_record,
            original_reasoning=f"Position closed: {reason}",
            outcome="win" if pnl > 0 else "loss",
            pnl_pct=pnl_pct,
            duration=duration,
        )

        if self._exchange:
            self._exchange.publish(self._cfg.agent_id, {
                "from_agent": self._cfg.agent_id,
                "event": "close",
                "trade_record": trade_record,
                "reasoning": f"Position closed: {reason}",
                "bull_case": "", "bear_case": "",
                "outcome": "win" if pnl > 0 else "loss",
                "pnl_pct": pnl_pct,
                "duration": duration,
            })
```

- [ ] **Step 4: Run all agent tests**

```
pytest tests/agents/test_agent.py -v
```

Expected: all PASS (7 tests total).

- [ ] **Step 5: Run full test suite**

```
pytest -v
```

Expected: all tests PASS. Note the count.

- [ ] **Step 6: Commit**

```bash
git add agents/agent.py tests/agents/test_agent.py
git commit -m "feat: wire PeerExchange into Agent; add stop checks and peer drain to run_cycle"
```

---

## Task 8: main.py — Wire PeerExchange

**Files:**
- Modify: `main.py`

No new tests needed — main.py is integration wiring; all components are unit-tested above.

- [ ] **Step 1: Add import**

At the top of `main.py`, after the existing imports, add:

```python
from agents.peer_exchange import PeerExchange
```

- [ ] **Step 2: Replace agent construction block**

Find and replace the two `Agent(...)` lines (currently lines 127–130):

```python
    # Before:
    agent_a = Agent(AgentConfig("agent_a", "regular", base_capital),
                    claude_a, broker_a, data_queue=queue_a)
    agent_b = Agent(AgentConfig("agent_b", "regular", base_capital),
                    claude_b, broker_b, data_queue=queue_b)
```

Replace with:

```python
    exchange = PeerExchange()
    exchange.register("agent_a")
    exchange.register("agent_b")

    agent_a = Agent(AgentConfig("agent_a", "regular", base_capital),
                    claude_a, broker_a, data_queue=queue_a,
                    peer_exchange=exchange)
    agent_b = Agent(AgentConfig("agent_b", "regular", base_capital),
                    claude_b, broker_b, data_queue=queue_b,
                    peer_exchange=exchange)
```

- [ ] **Step 3: Run full test suite**

```
pytest -v
```

Expected: all tests PASS. Record final count.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: instantiate PeerExchange in main and pass to both agents"
```

---

## Final Verification

- [ ] Run `pytest -v` — confirm all tests pass and count exceeds 85 (pre-implementation baseline)
- [ ] Confirm `agents/peer_exchange.py` exists
- [ ] Confirm `build_peer_learning_prompt` importable from `core.decision.prompt_builder`
- [ ] Confirm `TradeDecision.bull_case` and `.bear_case` accessible
- [ ] Update `docs/BACKLOG.md` — change Debate + Peer Exchange status to "implemented"
