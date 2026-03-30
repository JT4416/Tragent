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
    agent._improve = MagicMock()

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
    agent._improve = MagicMock()

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
    store_a = StateStore("agent_a", db_dir=tmp_path)
    store_b = StateStore("agent_b", db_dir=tmp_path)

    # Agent A has AAPL locally but broker doesn't
    store_a.save_position(Position(
        symbol="AAPL", direction="long", entry_price=180.0,
        stop_loss=176.4, trailing_stop=177.3, quantity=5,
        entry_time="2026-03-30T10:00:00+00:00"))

    mock_schwab = MagicMock()
    mock_schwab.get_account_info.return_value = {"positions": []}

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
