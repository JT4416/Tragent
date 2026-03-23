from collections import defaultdict
from core.analysis.technical import BreakoutSignal


class SignalAggregator:
    def __init__(self, allow_short: bool = True):
        self._allow_short = allow_short

    def rank(self, signals: list[BreakoutSignal]) -> list[dict]:
        """Combine per-signal list into ranked per-symbol list."""
        if not self._allow_short:
            signals = [s for s in signals if s.direction == "bullish"]

        by_symbol: dict[str, list[BreakoutSignal]] = defaultdict(list)
        for s in signals:
            by_symbol[s.symbol].append(s)

        ranked = []
        for symbol, syms in by_symbol.items():
            total_strength = sum(s.strength for s in syms)
            direction = "bullish" if sum(
                1 for s in syms if s.direction == "bullish") >= len(syms) / 2 \
                else "bearish"
            ranked.append({
                "symbol": symbol,
                "direction": direction,
                "signal_count": len(syms),
                "combined_strength": round(total_strength / len(syms), 3),
                "signals": [{"type": s.signal_type, "detail": s.detail,
                              "strength": s.strength} for s in syms],
            })

        return sorted(ranked, key=lambda x: (x["signal_count"],
                                              x["combined_strength"]),
                       reverse=True)
