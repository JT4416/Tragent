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
