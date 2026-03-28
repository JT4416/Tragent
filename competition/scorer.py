import math
from dataclasses import dataclass, field
from datetime import date


@dataclass
class TradeRecord:
    date: date
    symbol: str
    direction: str
    entry: float
    exit: float
    quantity: int
    pnl: float
    pnl_pct: float


class CompetitionScorer:
    def __init__(self, agent_id: str, base_capital: float):
        self._id = agent_id
        self._capital = base_capital
        self._trades: list[TradeRecord] = []

    def record_trade(self, trade: TradeRecord) -> None:
        self._trades.append(trade)

    def stats(self) -> dict:
        if not self._trades:
            return {"agent_id": self._id, "total_pnl": 0.0, "win_rate": 0.0,
                    "total_trades": 0, "sharpe": 0.0, "best_trade": 0.0,
                    "worst_trade": 0.0, "avg_gain_pct": 0.0, "avg_loss_pct": 0.0}
        total_pnl = sum(t.pnl for t in self._trades)
        wins = [t for t in self._trades if t.pnl > 0]
        losses = [t for t in self._trades if t.pnl <= 0]
        returns = [t.pnl_pct for t in self._trades]
        sharpe = self._sharpe(returns)
        return {
            "agent_id": self._id,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(len(wins) / len(self._trades), 3),
            "total_trades": len(self._trades),
            "sharpe": round(sharpe, 3),
            "best_trade": max(t.pnl for t in self._trades),
            "worst_trade": min(t.pnl for t in self._trades),
            "avg_gain_pct": round(sum(t.pnl_pct for t in wins) / len(wins), 3)
                if wins else 0.0,
            "avg_loss_pct": round(sum(t.pnl_pct for t in losses) / len(losses), 3)
                if losses else 0.0,
        }

    @staticmethod
    def _sharpe(returns: list[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(variance)
        return (mean - risk_free) / std if std > 0 else 0.0
