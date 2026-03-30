from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass
class RiskConfig:
    max_position_size_pct: float
    daily_loss_limit_pct: float
    max_concurrent_positions: int
    confidence_threshold_regular: float
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
        current_time: datetime,
    ) -> RiskDecision:
        if action == "hold":
            return RiskDecision(approved=False, reason="action is hold")

        # 1. Short selling permanently disabled
        if action == "short":
            return RiskDecision(approved=False, reason="short selling disabled")

        # 2. Pre/post-market trading disabled until agents have 3+ months experience
        if session in ("pre_market", "post_market"):
            return RiskDecision(approved=False,
                                reason="pre/post market trading disabled")

        # 3. Open blackout (first 5 min of regular session)
        if session == "regular" and self._in_open_blackout(current_time):
            return RiskDecision(approved=False,
                                reason="open blackout period (first 5 minutes)")

        # 4. Confidence check
        if confidence < self._cfg.confidence_threshold_regular:
            return RiskDecision(
                approved=False,
                reason=f"confidence {confidence:.2f} below threshold "
                       f"{self._cfg.confidence_threshold_regular:.2f}")

        # 5. Daily loss limit
        if daily_pnl_pct <= -self._cfg.daily_loss_limit_pct:
            return RiskDecision(approved=False,
                                reason=f"daily loss limit hit ({daily_pnl_pct:.1f}%)")

        # 6. Max concurrent positions
        if open_positions >= self._cfg.max_concurrent_positions:
            return RiskDecision(
                approved=False,
                reason=f"max positions reached ({open_positions})")

        # 7. Position size
        if position_size_pct > self._cfg.max_position_size_pct:
            return RiskDecision(
                approved=False,
                reason=f"position size {position_size_pct}% exceeds max")

        return RiskDecision(approved=True, reason="all checks passed")

    def _in_open_blackout(self, t: datetime) -> bool:
        t_et = t.astimezone(_ET)
        market_open_et = t_et.replace(hour=9, minute=30, second=0, microsecond=0)
        blackout_end = market_open_et + timedelta(
            minutes=self._cfg.open_blackout_minutes)
        return market_open_et <= t_et < blackout_end
