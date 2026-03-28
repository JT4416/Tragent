from config.settings import get

def test_get_trading_config():
    assert get("trading", "cycle_interval_regular_min") == 15

def test_get_risk_config():
    assert get("risk", "stop_loss_pct") == 2.0
