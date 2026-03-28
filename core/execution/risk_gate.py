from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass
class RiskConfig:
    max_position_size_pct: float
    daily_loss_limit_pct: float
    max_concurrent_positions: int
    confidence_threshold_regular: float
    confidence_threshold_extended: float
    open_blackout_minutes: int


@dataclass
class RiskDecision:
    approved: bool
    reason: str


_ET = ZoneInfo("America/New_York")


class RiskGate:
    def __init__(self, config: RiskConfig):
        self._cfg = config

    def check(
        self,
        action: str,
        confidence: float,
        position_size_pct: float,
        session: str,
        open_positions: int,
        portfolio_value: float,
        daily_pnl_pct: float,
        institutional_signal_present: bool,
        current_time: datetime,
    ) -> RiskDecision:
        if action == "hold":
            return RiskDecision(approved=False, reason="action is hold")

        # 1. Open blackout (first 5 min of regular session) — use ET timezone
        if session == "regular" and self._in_open_blackout(current_time):
            return RiskDecision(approved=False,
                                reason="open blackout period (first 5 minutes)")

        # 2. Extended hours require higher confidence + institutional signal
        threshold = self._cfg.confidence_threshold_regular
        if session in ("pre_market", "post_market"):
            threshold = self._cfg.confidence_threshold_extended
            if not institutional_signal_present:
                return RiskDecision(
                    approved=False,
                    reason="extended hours require institutional signal")

        # 3. Confidence check (also applies at threshold=0.78 for extended)
        if confidence < threshold:
            return RiskDecision(
                approved=False,
                reason=f"confidence {confidence:.2f} below threshold {threshold:.2f}")

        # 4. Daily loss limit
        if daily_pnl_pct <= -self._cfg.daily_loss_limit_pct:
            return RiskDecision(approved=False,
                                reason=f"daily loss limit hit ({daily_pnl_pct:.1f}%)")

        # 5. Max concurrent positions
        if open_positions >= self._cfg.max_concurrent_positions:
            return RiskDecision(
                approved=False,
                reason=f"max positions reached ({open_positions})")

        # 6. Position size
        if position_size_pct > self._cfg.max_position_size_pct:
            return RiskDecision(
                approved=False,
                reason=f"position size {position_size_pct}% exceeds max")

        return RiskDecision(approved=True, reason="all checks passed")

    def _in_open_blackout(self, t: datetime) -> bool:
        # Convert to ET to correctly handle DST
        t_et = t.astimezone(_ET)
        market_open_et = t_et.replace(hour=9, minute=30, second=0, microsecond=0)
        blackout_end = market_open_et + timedelta(minutes=self._cfg.open_blackout_minutes)
        return market_open_et <= t_et < blackout_end
