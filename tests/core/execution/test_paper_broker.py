import json
from unittest.mock import MagicMock
from core.execution.paper_broker import PaperBroker, TRADING_DAYS_GATE


def _mock_schwab(price=150.0):
    s = MagicMock()
    s.get_quote.return_value = {"lastPrice": price}
    return s


def test_initial_cash_equals_base_capital(tmp_path):
    broker = PaperBroker(_mock_schwab(), base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    info = broker.get_account_info()
    assert info["cash"] == 50000.0
    assert info["positions"] == []


def test_buy_reduces_cash_and_adds_position(tmp_path):
    schwab = _mock_schwab(price=100.0)
    broker = PaperBroker(schwab, base_capital=10000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    result = broker.place_order("AAPL", "buy", 10)
    assert result["status"] == "FILLED"
    info = broker.get_account_info()
    # 10 shares * ~100.10 (0.1% slippage)
    assert info["cash"] < 10000.0
    assert any(p["symbol"] == "AAPL" for p in info["positions"])


def test_sell_removes_position_and_adds_cash(tmp_path):
    schwab = _mock_schwab(price=100.0)
    broker = PaperBroker(schwab, base_capital=10000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    broker.place_order("AAPL", "buy", 10)
    cash_after_buy = broker.get_account_info()["cash"]
    broker.place_order("AAPL", "sell", 10)
    info = broker.get_account_info()
    assert info["cash"] > cash_after_buy
    assert not any(p["symbol"] == "AAPL" for p in info["positions"])


def test_state_persists_across_instances(tmp_path):
    schwab = _mock_schwab(price=200.0)
    broker1 = PaperBroker(schwab, base_capital=50000.0,
                           agent_id="agent_a", state_dir=tmp_path)
    broker1.place_order("MSFT", "buy", 5)
    # New instance should load the same state
    broker2 = PaperBroker(schwab, base_capital=50000.0,
                           agent_id="agent_a", state_dir=tmp_path)
    info = broker2.get_account_info()
    assert any(p["symbol"] == "MSFT" for p in info["positions"])


def test_trading_days_increments_on_get_account_info(tmp_path):
    broker = PaperBroker(_mock_schwab(), base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    broker.get_account_info()
    assert broker.trading_days_completed() == 1


def test_is_not_live_ready_before_gate(tmp_path):
    broker = PaperBroker(_mock_schwab(), base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    assert not broker.is_live_ready()


def test_get_quote_delegates_to_schwab(tmp_path):
    schwab = _mock_schwab(price=300.0)
    broker = PaperBroker(schwab, base_capital=50000.0,
                          agent_id="agent_a", state_dir=tmp_path)
    quote = broker.get_quote("NVDA")
    assert quote["lastPrice"] == 300.0
    schwab.get_quote.assert_called_once_with("NVDA")
