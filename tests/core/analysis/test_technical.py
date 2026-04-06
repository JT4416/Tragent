import pandas as pd
import numpy as np
from core.analysis.technical import TechnicalAnalyzer, TradingSignal

def _make_ohlcv(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100, 120, n), index=idx)
    volume = pd.Series([1_000_000] * n, index=idx)
    volume.iloc[-1] = 2_500_000   # spike on last bar
    high = close + 1
    low = close - 1
    open_ = close - 0.5
    return pd.DataFrame({"open": open_, "high": high,
                          "low": low, "close": close, "volume": volume})

def test_detects_volume_breakout():
    df = _make_ohlcv()
    analyzer = TechnicalAnalyzer()
    signals = analyzer.analyze(df, symbol="AAPL")
    assert any(s.signal_type == "volume_spike" for s in signals)

def test_no_signals_on_flat_data():
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    df = pd.DataFrame({
        "open": [100.0] * 60, "high": [101.0] * 60,
        "low": [99.0] * 60, "close": [100.0] * 60,
        "volume": [1_000_000] * 60,
    }, index=idx)
    analyzer = TechnicalAnalyzer()
    signals = analyzer.analyze(df, symbol="FLAT")
    assert len(signals) == 0
