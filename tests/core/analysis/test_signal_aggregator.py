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


def test_filters_bearish_if_long_only():
    agg = SignalAggregator(allow_short=False)
    signals = [
        BreakoutSignal("AAPL", "vwap_cross", "bearish", 0.8, "cross below"),
        BreakoutSignal("MSFT", "volume_spike", "bullish", 0.7, "vol 2x"),
    ]
    result = agg.rank(signals)
    assert len(result) == 1
    assert result[0]["symbol"] == "MSFT"
