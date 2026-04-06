from dataclasses import dataclass
import pandas as pd
import pandas_ta as ta


@dataclass
class TradingSignal:
    symbol: str
    signal_type: str    # breakout: volume_spike | vwap_cross | range_breakout | 52w_high
                        # momentum: rsi_oversold | rsi_overbought | macd_crossover
                        # trend: ema_crossover | sma_trend
                        # mean_reversion: bb_squeeze | bb_bounce | obv_divergence
    direction: str      # "bullish" | "bearish"
    strength: float     # 0.0–1.0
    detail: str


class TechnicalAnalyzer:
    _VOLUME_SPIKE_MULT = 1.5
    _LOOKBACK = 20

    def analyze(self, df: pd.DataFrame, symbol: str) -> list[TradingSignal]:
        if len(df) < self._LOOKBACK + 1:
            return []
        signals = []
        # Breakout signals
        signals.extend(self._volume_spike(df, symbol))
        signals.extend(self._vwap_cross(df, symbol))
        signals.extend(self._range_breakout(df, symbol))
        signals.extend(self._fifty_two_week_high(df, symbol))
        # Momentum signals
        signals.extend(self._rsi(df, symbol))
        signals.extend(self._macd_crossover(df, symbol))
        # Trend signals
        signals.extend(self._ema_crossover(df, symbol))
        signals.extend(self._sma_trend(df, symbol))
        # Mean-reversion signals
        signals.extend(self._bollinger_bands(df, symbol))
        signals.extend(self._obv_divergence(df, symbol))
        return signals

    def _volume_spike(self, df: pd.DataFrame,
                      symbol: str) -> list[TradingSignal]:
        avg_vol = df["volume"].iloc[-self._LOOKBACK:-1].mean()
        last_vol = df["volume"].iloc[-1]
        if avg_vol == 0:
            return []
        ratio = last_vol / avg_vol
        if ratio >= self._VOLUME_SPIKE_MULT:
            direction = "bullish" if df["close"].iloc[-1] > df["open"].iloc[-1] \
                else "bearish"
            return [TradingSignal(
                symbol=symbol, signal_type="volume_spike",
                direction=direction,
                strength=min(1.0, (ratio - 1) / 2),
                detail=f"Volume {ratio:.1f}x avg ({int(last_vol):,})",
            )]
        return []

    def _vwap_cross(self, df: pd.DataFrame,
                    symbol: str) -> list[TradingSignal]:
        if "VWAP_D" not in df.columns:
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
            return [TradingSignal(
                symbol=symbol, signal_type="vwap_cross",
                direction="bullish", strength=0.6,
                detail=f"Price crossed above VWAP {vwap:.2f}")]
        if prev_close > vwap >= last_close:
            return [TradingSignal(
                symbol=symbol, signal_type="vwap_cross",
                direction="bearish", strength=0.6,
                detail=f"Price crossed below VWAP {vwap:.2f}")]
        return []

    def _range_breakout(self, df: pd.DataFrame,
                        symbol: str) -> list[TradingSignal]:
        window = df.iloc[-self._LOOKBACK - 1:-1]
        resistance = window["high"].max()
        last_close = df["close"].iloc[-1]
        if last_close > resistance:
            return [TradingSignal(
                symbol=symbol, signal_type="range_breakout",
                direction="bullish",
                strength=min(1.0, (last_close - resistance) / resistance * 20),
                detail=f"Broke {self._LOOKBACK}-day high {resistance:.2f}")]
        return []

    def _fifty_two_week_high(self, df: pd.DataFrame,
                             symbol: str) -> list[TradingSignal]:
        if len(df) < 252:
            return []
        high_52w = df["high"].iloc[-253:-1].max()
        last_close = df["close"].iloc[-1]
        if last_close >= high_52w * 0.99:
            return [TradingSignal(
                symbol=symbol, signal_type="52w_high",
                direction="bullish", strength=0.85,
                detail=f"Near/at 52-week high {high_52w:.2f}")]
        return []

    # ── Momentum signals ──────────────────────────────────────────────

    def _rsi(self, df: pd.DataFrame, symbol: str) -> list[TradingSignal]:
        rsi = ta.rsi(df["close"], length=14)
        if rsi is None or len(rsi) < 2:
            return []
        cur = rsi.iloc[-1]
        prev = rsi.iloc[-2]
        if pd.isna(cur) or pd.isna(prev):
            return []
        if cur < 30 and cur > prev:
            return [TradingSignal(
                symbol=symbol, signal_type="rsi_oversold",
                direction="bullish",
                strength=min(1.0, (30 - cur) / 30 + 0.4),
                detail=f"RSI {cur:.1f} oversold and turning up from {prev:.1f}")]
        if cur > 70:
            return [TradingSignal(
                symbol=symbol, signal_type="rsi_overbought",
                direction="bearish",
                strength=min(1.0, (cur - 70) / 30 + 0.4),
                detail=f"RSI {cur:.1f} overbought — caution")]
        return []

    def _macd_crossover(self, df: pd.DataFrame,
                        symbol: str) -> list[TradingSignal]:
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is None or len(macd_df) < 2:
            return []
        hist_col = [c for c in macd_df.columns if "h" in c.lower()]
        if not hist_col:
            return []
        hist = macd_df[hist_col[0]]
        cur_h = hist.iloc[-1]
        prev_h = hist.iloc[-2]
        if pd.isna(cur_h) or pd.isna(prev_h):
            return []
        if prev_h <= 0 < cur_h:
            return [TradingSignal(
                symbol=symbol, signal_type="macd_crossover",
                direction="bullish", strength=0.65,
                detail=f"MACD histogram flipped positive ({cur_h:.3f})")]
        if prev_h >= 0 > cur_h:
            return [TradingSignal(
                symbol=symbol, signal_type="macd_crossover",
                direction="bearish", strength=0.65,
                detail=f"MACD histogram flipped negative ({cur_h:.3f})")]
        return []

    # ── Trend signals ─────────────────────────────────────────────────

    def _ema_crossover(self, df: pd.DataFrame,
                       symbol: str) -> list[TradingSignal]:
        ema9 = ta.ema(df["close"], length=9)
        ema21 = ta.ema(df["close"], length=21)
        if ema9 is None or ema21 is None or len(ema9) < 2:
            return []
        cur9, prev9 = ema9.iloc[-1], ema9.iloc[-2]
        cur21, prev21 = ema21.iloc[-1], ema21.iloc[-2]
        if any(pd.isna(v) for v in (cur9, prev9, cur21, prev21)):
            return []
        if prev9 <= prev21 and cur9 > cur21:
            return [TradingSignal(
                symbol=symbol, signal_type="ema_crossover",
                direction="bullish", strength=0.7,
                detail=f"EMA 9 ({cur9:.2f}) crossed above EMA 21 ({cur21:.2f})")]
        if prev9 >= prev21 and cur9 < cur21:
            return [TradingSignal(
                symbol=symbol, signal_type="ema_crossover",
                direction="bearish", strength=0.7,
                detail=f"EMA 9 ({cur9:.2f}) crossed below EMA 21 ({cur21:.2f})")]
        return []

    def _sma_trend(self, df: pd.DataFrame,
                   symbol: str) -> list[TradingSignal]:
        if len(df) < 50:
            return []
        sma50 = ta.sma(df["close"], length=50)
        if sma50 is None:
            return []
        cur_sma = sma50.iloc[-1]
        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        if pd.isna(cur_sma):
            return []
        pct_above = (last_close - cur_sma) / cur_sma * 100
        if prev_close < cur_sma <= last_close:
            return [TradingSignal(
                symbol=symbol, signal_type="sma_trend",
                direction="bullish", strength=0.7,
                detail=f"Price crossed above 50-day SMA {cur_sma:.2f}")]
        if prev_close > cur_sma >= last_close:
            return [TradingSignal(
                symbol=symbol, signal_type="sma_trend",
                direction="bearish", strength=0.7,
                detail=f"Price crossed below 50-day SMA {cur_sma:.2f}")]
        if pct_above > 5:
            return [TradingSignal(
                symbol=symbol, signal_type="sma_trend",
                direction="bullish", strength=0.5,
                detail=f"Price {pct_above:.1f}% above 50-day SMA — strong uptrend")]
        if pct_above < -5:
            return [TradingSignal(
                symbol=symbol, signal_type="sma_trend",
                direction="bearish", strength=0.5,
                detail=f"Price {abs(pct_above):.1f}% below 50-day SMA — downtrend")]
        return []

    # ── Mean-reversion signals ────────────────────────────────────────

    def _bollinger_bands(self, df: pd.DataFrame,
                         symbol: str) -> list[TradingSignal]:
        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is None or len(bb) < 2:
            return []
        upper_col = [c for c in bb.columns if "u" in c.lower()]
        lower_col = [c for c in bb.columns if "l" in c.lower()]
        bw_col = [c for c in bb.columns if "b" in c.lower() and "w" in c.lower()]
        if not upper_col or not lower_col:
            return []
        upper = bb[upper_col[0]]
        lower = bb[lower_col[0]]
        last_close = df["close"].iloc[-1]
        signals = []
        # Bollinger squeeze: bandwidth narrowing then price breaking out
        if bw_col:
            bw = bb[bw_col[0]]
            if len(bw) >= 20 and not pd.isna(bw.iloc[-1]):
                cur_bw = bw.iloc[-1]
                avg_bw = bw.iloc[-20:].mean()
                if cur_bw < avg_bw * 0.5 and last_close > upper.iloc[-1]:
                    signals.append(TradingSignal(
                        symbol=symbol, signal_type="bb_squeeze",
                        direction="bullish", strength=0.75,
                        detail=f"Bollinger squeeze breakout — bandwidth {cur_bw:.3f} "
                               f"(avg {avg_bw:.3f}), price above upper band"))
        # Bounce off lower band with RSI confirmation
        if not pd.isna(lower.iloc[-1]) and last_close <= lower.iloc[-1]:
            rsi = ta.rsi(df["close"], length=14)
            if rsi is not None and not pd.isna(rsi.iloc[-1]) and rsi.iloc[-1] < 35:
                signals.append(TradingSignal(
                    symbol=symbol, signal_type="bb_bounce",
                    direction="bullish", strength=0.65,
                    detail=f"At lower Bollinger Band {lower.iloc[-1]:.2f} "
                           f"with RSI {rsi.iloc[-1]:.1f} — oversold bounce setup"))
        return signals

    def _obv_divergence(self, df: pd.DataFrame,
                        symbol: str) -> list[TradingSignal]:
        obv = ta.obv(df["close"], df["volume"])
        if obv is None or len(obv) < self._LOOKBACK:
            return []
        price_chg = df["close"].iloc[-1] - df["close"].iloc[-self._LOOKBACK]
        obv_chg = obv.iloc[-1] - obv.iloc[-self._LOOKBACK]
        if price_chg < 0 and obv_chg > 0:
            return [TradingSignal(
                symbol=symbol, signal_type="obv_divergence",
                direction="bullish", strength=0.6,
                detail=f"Price down but OBV rising — accumulation (hidden buying)")]
        if price_chg > 0 and obv_chg < 0:
            return [TradingSignal(
                symbol=symbol, signal_type="obv_divergence",
                direction="bearish", strength=0.6,
                detail=f"Price up but OBV falling — distribution (smart money selling)")]
        return []
