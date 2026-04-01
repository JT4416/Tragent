from core.decision.prompt_builder import build_decision_prompt


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
    assert "4.81%" in prompt


def test_empty_movers_shows_none():
    prompt = build_decision_prompt(**_base_kwargs(movers=[]))
    assert "(none)" in prompt


def test_patience_instruction_in_task():
    prompt = build_decision_prompt(**_base_kwargs())
    assert "Patience is a valid strategy" in prompt
