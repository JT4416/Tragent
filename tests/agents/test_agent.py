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
