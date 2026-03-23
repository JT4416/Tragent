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
