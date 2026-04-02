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

def test_cost_tracking(tmp_dir):
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

def test_parse_response_with_markdown_fence():
    raw = '```json\n{"action": "buy", "symbol": "AAPL", "confidence": 0.82, "position_size_pct": 3.0, "reasoning": "test", "signals_used": [], "skip_reason": null}\n```'
    decision = ClaudeClient._parse_response(raw)
    assert decision.action == "buy"
    assert decision.confidence == 0.82

def test_spend_limit_raises(monkeypatch):
    with patch("core.decision.claude_client.anthropic.Anthropic"):
        client = ClaudeClient(daily_limit_usd=5.0)
        client.daily_spend_usd = 5.0
        import pytest as _pytest
        with _pytest.raises(RuntimeError, match="spend limit"):
            client.decide("system", "prompt")


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
