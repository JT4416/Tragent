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
