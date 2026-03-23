from dataclasses import dataclass
import pandas as pd
import pandas_ta as ta


@dataclass
class BreakoutSignal:
    symbol: str
    signal_type: str    # "volume_spike" | "vwap_cross" | "range_breakout" | "52w_high"
    direction: str      # "bullish" | "bearish"
    strength: float     # 0.0–1.0
    detail: str


class TechnicalAnalyzer:
    _VOLUME_SPIKE_MULT = 1.5
    _LOOKBACK = 20

    def analyze(self, df: pd.DataFrame, symbol: str) -> list[BreakoutSignal]:
        if len(df) < self._LOOKBACK + 1:
            return []
        signals = []
        signals.extend(self._volume_spike(df, symbol))
        signals.extend(self._vwap_cross(df, symbol))
        signals.extend(self._range_breakout(df, symbol))
        signals.extend(self._fifty_two_week_high(df, symbol))
        return signals

    def _volume_spike(self, df: pd.DataFrame,
                      symbol: str) -> list[BreakoutSignal]:
        avg_vol = df["volume"].iloc[-self._LOOKBACK:-1].mean()
        last_vol = df["volume"].iloc[-1]
        if avg_vol == 0:
            return []
        ratio = last_vol / avg_vol
        if ratio >= self._VOLUME_SPIKE_MULT:
            direction = "bullish" if df["close"].iloc[-1] > df["open"].iloc[-1] \
                else "bearish"
            return [BreakoutSignal(
                symbol=symbol, signal_type="volume_spike",
                direction=direction,
                strength=min(1.0, (ratio - 1) / 2),
                detail=f"Volume {ratio:.1f}x avg ({int(last_vol):,})",
            )]
        return []

    def _vwap_cross(self, df: pd.DataFrame,
                    symbol: str) -> list[BreakoutSignal]:
        if "vwap" not in df.columns:
            df = df.copy()
            df.ta.vwap(append=True)
        if "VWAP_D" not in df.columns:
            return []
        prev_close = df["close"].iloc[-2]
        last_close = df["close"].iloc[-1]
        vwap = df["VWAP_D"].iloc[-1]
        if pd.isna(vwap):
            return []
        if prev_close < vwap <= last_close:
            return [BreakoutSignal(
                symbol=symbol, signal_type="vwap_cross",
                direction="bullish", strength=0.6,
                detail=f"Price crossed above VWAP {vwap:.2f}")]
        if prev_close > vwap >= last_close:
            return [BreakoutSignal(
                symbol=symbol, signal_type="vwap_cross",
                direction="bearish", strength=0.6,
                detail=f"Price crossed below VWAP {vwap:.2f}")]
        return []

    def _range_breakout(self, df: pd.DataFrame,
                        symbol: str) -> list[BreakoutSignal]:
        window = df.iloc[-self._LOOKBACK - 1:-1]
        resistance = window["high"].max()
        last_close = df["close"].iloc[-1]
        if last_close > resistance:
            return [BreakoutSignal(
                symbol=symbol, signal_type="range_breakout",
                direction="bullish",
                strength=min(1.0, (last_close - resistance) / resistance * 20),
                detail=f"Broke {self._LOOKBACK}-day high {resistance:.2f}")]
        return []

    def _fifty_two_week_high(self, df: pd.DataFrame,
                             symbol: str) -> list[BreakoutSignal]:
        if len(df) < 252:
            return []
        high_52w = df["high"].iloc[-252:].max()
        last_close = df["close"].iloc[-1]
        if last_close >= high_52w * 0.99:
            return [BreakoutSignal(
                symbol=symbol, signal_type="52w_high",
                direction="bullish", strength=0.85,
                detail=f"Near/at 52-week high {high_52w:.2f}")]
        return []
