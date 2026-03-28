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
