import json
import yaml
from datetime import datetime, timezone


DECISION_SYSTEM = (
    "You are a professional stock trader with expert knowledge of the Thinkorswim "
    "platform, technical analysis, market microstructure, and institutional trading "
    "behavior. You make precise, data-driven trading decisions. "
    "You always respond in valid JSON only — no prose, no markdown."
)

SELF_IMPROVE_SYSTEM = (
    "You are maintaining a YAML expertise file — a mental model of trading patterns. "
    "Update it precisely based on new trade evidence. Preserve valid YAML syntax. "
    "Enforce the line limit by condensing similar entries and removing "
    "lowest-confidence entries if over the limit. "
    "Return the complete updated YAML file only, no prose."
)


def build_decision_prompt(
    session: str,
    expertise: dict[str, dict],
    signals: list[dict],
    news: list[dict],
    institutional: list[dict],
    open_positions: list[dict],
    cash: float,
    daily_pnl: float,
    daily_pnl_pct: float,
    daily_loss_remaining: float,
    movers: list[dict] | None = None,
) -> str:
    if movers is None:
        movers = []
    now = datetime.now(timezone.utc)
    return f"""## Current Market Context
Date: {now.strftime('%Y-%m-%d')} | Time: {now.strftime('%H:%M')} UTC | Session: {session}

## Agent Expertise (Mental Model)
### Market
{_yaml_summary(expertise.get('market', {}))}

### News
{_yaml_summary(expertise.get('news', {}))}

### Institutional
{_yaml_summary(expertise.get('institutional', {}))}

### Trade History
{_yaml_summary(expertise.get('trade', {}))}

## Top Market Movers (S&P 500 — sorted by % gain)
{_format_movers(movers)}

## Live Signals
### Breakout Candidates
{_format_list(signals)}

### News Sentiment
{_format_list(news)}

### Institutional Activity
{_format_list(institutional)}

## Current Positions
{_format_list(open_positions)}

## Portfolio State
Cash available: ${cash:,.2f}
Daily P&L: ${daily_pnl:,.2f} ({daily_pnl_pct:.1f}%)
Daily loss limit remaining: ${daily_loss_remaining:,.2f}

## Task
Start by reviewing the top market movers. These are stocks the market has already
validated with real volume and price action today. Cross-reference with the breakout
signals and news below. Only enter a position when you see alignment — a mover that
also has technical confirmation and/or news support. Patience is a valid strategy.
If nothing meets that bar, hold. A missed opportunity is better than a bad trade.
Long positions only — no short selling. To express bearish conviction, buy an inverse
ETF (SH, SDS, QID, or DOG) instead.

## Response Format (JSON only)
{{
  "action": "buy|sell|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "brief explanation",
  "signals_used": [],
  "skip_reason": "if hold, why"
}}"""


def build_self_improve_prompt(
    trade_record: dict,
    original_reasoning: str,
    outcome: str,
    pnl_pct: float,
    duration: str,
    current_yaml: str,
    max_lines: int = 1000,
) -> str:
    return f"""## Completed Trade
{json.dumps(trade_record, indent=2)}

## Claude's Original Reasoning
{original_reasoning}

## Outcome
Result: {outcome} | P&L: {pnl_pct:.2f}% | Held for: {duration}

## Current Expertise File (max {max_lines} lines)
{current_yaml}

## Task
Update the expertise file to reflect what was learned from this trade.
- Increase confidence for patterns that worked
- Decrease confidence for patterns that failed
- Add new lessons_learned entries if a new pattern was identified
- Update evolved_parameters if thresholds should shift
- Return the complete updated YAML file only, no prose"""


def _yaml_summary(data: dict) -> str:
    return yaml.dump(data, default_flow_style=False)[:2000]


def _format_list(items: list) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {item}" for item in items)


def _format_movers(movers: list[dict]) -> str:
    if not movers:
        return "  (none)"
    lines = []
    for m in movers:
        lines.append(
            f"  - {m['symbol']:6s}  +{m['netPercentChange']:.2f}%"
            f"  ${m['lastPrice']:.2f}"
            f"  vol {m['volume']:,}"
        )
    return "\n".join(lines)
