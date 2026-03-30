from datetime import datetime
from zoneinfo import ZoneInfo
from core.execution.risk_gate import RiskGate, RiskConfig

_ET = ZoneInfo("America/New_York")


def _config():
    return RiskConfig(
        max_position_size_pct=5.0,
        daily_loss_limit_pct=6.0,
        max_concurrent_positions=5,
        confidence_threshold_regular=0.65,
        open_blackout_minutes=5,
    )


def test_passes_valid_trade():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.80, position_size_pct=3.0,
        session="regular", open_positions=2,
        portfolio_value=50000, daily_pnl_pct=-1.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert result.approved


def test_blocks_short_selling():
    gate = RiskGate(_config())
    result = gate.check(
        action="short", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "short selling" in result.reason.lower()


def test_blocks_pre_market():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="pre_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 7, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "pre/post" in result.reason.lower()


def test_blocks_post_market():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="post_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 17, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "pre/post" in result.reason.lower()


def test_blocks_low_confidence():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.50, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "confidence" in result.reason.lower()


def test_blocks_daily_loss_limit():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=-7.0,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "loss limit" in result.reason.lower()


def test_blocks_open_blackout():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        current_time=datetime(2026, 3, 21, 9, 32, tzinfo=_ET),
    )
    assert not result.approved
    assert "blackout" in result.reason.lower()
