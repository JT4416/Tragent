import pytest
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
    agent = Agent(config, mock_claude, mock_schwab,
                  data_queue=data_queue, expertise_dir=tmp_path,
                  db_dir=tmp_path)
    agent._improve = MagicMock()
    return agent


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
