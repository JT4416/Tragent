from competition.scorer import CompetitionScorer, TradeRecord
from datetime import date

def test_pnl_calculation():
    scorer = CompetitionScorer("agent_a", base_capital=50000.0)
    scorer.record_trade(TradeRecord(
        date=date(2026, 3, 21), symbol="AAPL",
        direction="long", entry=182.50, exit=187.10,
        quantity=10, pnl=46.0, pnl_pct=2.52,
    ))
    stats = scorer.stats()
    assert stats["total_pnl"] == 46.0
    assert stats["win_rate"] == 1.0
    assert stats["total_trades"] == 1

def test_sharpe_ratio():
    scorer = CompetitionScorer("agent_a", base_capital=50000.0)
    for pnl_pct in [1.0, -0.5, 2.0, 0.8, -1.0]:
        scorer.record_trade(TradeRecord(
            date=date(2026, 3, 21), symbol="X", direction="long",
            entry=100, exit=100, quantity=1,
            pnl=pnl_pct * 100, pnl_pct=pnl_pct,
        ))
    stats = scorer.stats()
    assert "sharpe" in stats
