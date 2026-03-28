from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock
from core.execution.risk_gate import RiskGate, RiskConfig, RiskDecision

_ET = ZoneInfo("America/New_York")

def _config():
    return RiskConfig(
        max_position_size_pct=5.0,
        daily_loss_limit_pct=6.0,
        max_concurrent_positions=5,
        confidence_threshold_regular=0.65,
        confidence_threshold_extended=0.78,
        open_blackout_minutes=5,
    )

def test_passes_valid_trade():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.80, position_size_pct=3.0,
        session="regular", open_positions=2,
        portfolio_value=50000, daily_pnl_pct=-1.0,
        institutional_signal_present=False,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert result.approved

def test_blocks_low_confidence():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.50, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=False,
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
        institutional_signal_present=False,
        current_time=datetime(2026, 3, 21, 14, 0, tzinfo=_ET),
    )
    assert not result.approved
    assert "loss limit" in result.reason.lower()

def test_blocks_extended_hours_without_institutional():
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.80, position_size_pct=3.0,
        session="pre_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=False,
        current_time=datetime(2026, 3, 21, 7, 0, tzinfo=_ET),
    )
    assert not result.approved

def test_blocks_open_blackout():
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.90, position_size_pct=3.0,
        session="regular", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=True,
        # 09:32 ET on Mar 21 (DST active → UTC-4, so 13:32 UTC)
        current_time=datetime(2026, 3, 21, 9, 32, tzinfo=ET),
    )
    assert not result.approved

def test_extended_hours_blocks_low_confidence_even_with_institutional():
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    gate = RiskGate(_config())
    result = gate.check(
        action="buy", confidence=0.76, position_size_pct=3.0,
        session="pre_market", open_positions=0,
        portfolio_value=50000, daily_pnl_pct=0.0,
        institutional_signal_present=True,  # signal present but confidence < 0.78
        current_time=datetime(2026, 3, 21, 7, 0, tzinfo=ET),
    )
    assert not result.approved
    assert "confidence" in result.reason.lower()
