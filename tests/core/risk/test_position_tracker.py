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
