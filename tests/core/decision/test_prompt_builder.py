from core.decision.prompt_builder import build_decision_prompt
from core.decision.prompt_builder import build_peer_learning_prompt


def _base_kwargs(**overrides):
    kwargs = dict(
        session="regular",
        expertise={},
        signals=[],
        news=[],
        institutional=[],
        open_positions=[],
        cash=500.0,
        daily_pnl=0.0,
        daily_pnl_pct=0.0,
        daily_loss_remaining=30.0,
        movers=[],
    )
    kwargs.update(overrides)
    return kwargs


def test_movers_section_present():
    prompt = build_decision_prompt(**_base_kwargs())
    assert "Top Market Movers" in prompt


def test_movers_rendered_in_prompt():
    movers = [
        {"symbol": "NVDA", "description": "NVIDIA CORP",
         "lastPrice": 175.58, "netChange": 8.06,
         "netPercentChange": 4.81, "volume": 121693985},
    ]
    prompt = build_decision_prompt(**_base_kwargs(movers=movers))
    assert "NVDA" in prompt
    assert "+4.81%" in prompt


def test_empty_movers_shows_none():
    prompt = build_decision_prompt(**_base_kwargs(movers=[]))
    assert "(none)" in prompt


def test_default_movers_none_shows_none():
    """Calling without movers kwarg (None default) renders (none) section."""
    prompt = build_decision_prompt(
        session="regular",
        expertise={},
        signals=[],
        news=[],
        institutional=[],
        open_positions=[],
        cash=500.0,
        daily_pnl=0.0,
        daily_pnl_pct=0.0,
        daily_loss_remaining=30.0,
        # movers intentionally omitted — tests the None default
    )
    assert "(none)" in prompt


def test_patience_instruction_in_task():
    prompt = build_decision_prompt(**_base_kwargs())
    assert "Patience is a valid strategy" in prompt


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
