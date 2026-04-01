from core.analysis.signal_aggregator import SignalAggregator
from core.analysis.technical import BreakoutSignal


def test_aggregates_and_deduplicates():
    agg = SignalAggregator()
    signals = [
        BreakoutSignal("AAPL", "volume_spike", "bullish", 0.7, "vol 2x"),
        BreakoutSignal("AAPL", "vwap_cross", "bullish", 0.6, "cross above"),
        BreakoutSignal("MSFT", "range_breakout", "bullish", 0.5, "new high"),
    ]
    result = agg.rank(signals)
    symbols = [s["symbol"] for s in result]
    # AAPL has 2 signals, should rank above MSFT
    assert symbols[0] == "AAPL"
    assert len(result) == 2  # one entry per symbol


def test_bearish_signals_pass_through():
    """Bearish signals reach Claude so it can decide to buy inverse ETFs.
    Short-sell blocking happens in RiskGate, not here."""
    agg = SignalAggregator()
    signals = [
        BreakoutSignal("AAPL", "vwap_cross", "bearish", 0.8, "cross below"),
        BreakoutSignal("MSFT", "volume_spike", "bullish", 0.7, "vol 2x"),
    ]
    result = agg.rank(signals)
    assert len(result) == 2
    symbols = [s["symbol"] for s in result]
    assert "AAPL" in symbols
    assert "MSFT" in symbols


def test_bearish_direction_label():
    """Symbol with majority bearish signals is labeled bearish in output."""
    agg = SignalAggregator()
    signals = [
        BreakoutSignal("NVDA", "vwap_cross", "bearish", 0.8, "cross below"),
        BreakoutSignal("NVDA", "volume_spike", "bearish", 0.7, "high vol down"),
    ]
    result = agg.rank(signals)
    assert result[0]["direction"] == "bearish"
