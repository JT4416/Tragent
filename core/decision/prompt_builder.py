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
    daily_prep: dict | None = None,
) -> str:
    if movers is None:
        movers = []
    now = datetime.now(timezone.utc)
    prep_section = _format_daily_prep(daily_prep) if daily_prep else ""
    return f"""## Current Market Context
Date: {now.strftime('%Y-%m-%d')} | Time: {now.strftime('%H:%M')} UTC | Session: {session}
{prep_section}
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

## Live Signals (breakout, momentum, trend, mean-reversion)
### Trading Candidates
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
PRIORITY TICKERS: RKLB, SATS, DXYZ, BPTRX, JOBY, ACHR, FCUV, SMX, MLEC, SPCE, FUBO,
CLIR, SIDU, BVC — evaluate these first every cycle.

TOP MOVERS ARE TRADEABLE: The "Top Market Movers" list above shows what's actually
moving RIGHT NOW. If a mover is up big (5%+) on strong volume, it's a valid trade
candidate even if it's not on the priority list. Don't ignore the movers — they are
real-time market intelligence showing you where the money is flowing.

OPEN MOMENTUM STRATEGY (first 30 minutes of session):
When the market first opens, look for top movers already showing strong upward momentum
with real volume confirmation. These are stocks the market is validating RIGHT NOW.
Jump in and ride the wave — but with a tight 1.5% trailing stop. The first 30 minutes
often set the tone for the day. Don't overthink it: if a mover is up 2%+ on 2x+ average
volume with multiple signals firing, that's your entry. Speed matters more than
perfection at the open.

After the first 30 minutes, revert to normal analysis: require technical confirmation
and/or news support. Patience is a valid strategy mid-day.

BEARISH PIVOT RULE — CRITICAL:
If the market opens bearish, or if your bullish homework picks FAIL within the first
30 minutes (price below VWAP, entry triggers not met), IMMEDIATELY pivot to bearish
plays. Do NOT keep re-evaluating failed longs cycle after cycle. Instead:
1. Buy an inverse ETF (SH, SDS, QID, or DOG) to express bearish conviction.
2. Treat inverse ETFs like any other long — they go UP when the market goes DOWN.
   Apply the same momentum entry logic: if QID/SH is up 1%+ on rising volume while
   the broad market sells off, that IS your trade.
3. Inverse ETFs are valid holds during regular hours. You do NOT need to exit the
   same day — 1x inverse ETFs (SH, DOG) have minimal decay. Only 2x leveraged
   (SDS, QID) should be short-duration holds (1-3 days max).
4. Do not talk yourself out of a bearish trade just because you started the day
   looking for longs. The market tells you what it wants — listen.

Long positions only — no short selling. To express bearish conviction, buy an inverse
ETF (SH, SDS, QID, or DOG) instead.
Before deciding, articulate the strongest bull and bear case for the leading candidate.
Let the better argument win.

## Response Format (JSON only)
{{
  "bull_case": "strongest argument FOR this trade",
  "bear_case": "strongest argument AGAINST this trade",
  "action": "buy|sell|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "reasoning": "which case won and why",
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


def build_peer_learning_prompt(
    insight: dict,
    current_yaml: str,
    max_lines: int = 1000,
) -> str:
    return f"""## Peer Trade Insight (your competitor — do not copy blindly)
From: {insight['from_agent']} | Event: {insight['event']}
They traded: {insight['trade_record'].get('symbol', 'unknown')} {insight['trade_record'].get('direction', '')}
Their bull case: {insight['bull_case']}
Their bear case: {insight['bear_case']}
Their reasoning: {insight['reasoning']}
Outcome: {insight['outcome']} | P&L: {insight['pnl_pct']:.2f}% | Duration: {insight['duration']}

## Your Current Expertise File (max {max_lines} lines)
{current_yaml}

## Task
What can you learn from your competitor's trade?
- If they identified a pattern you have missed, add it with confidence 0.1 lower than theirs
- If their outcome confirms your existing beliefs, increase confidence by 0.05
- If their outcome contradicts your existing beliefs, decrease confidence by 0.05
- Do NOT copy their position sizing or stop levels — evolve your own parameters
- Return the complete updated YAML only, no prose"""


def build_homework_prompt(
    signals: list[dict],
    news: list[dict],
    institutional: list[dict],
    movers: list[dict],
    expertise: dict[str, dict],
    today_decisions: list[dict],
    open_positions: list[dict],
    watchlist: list[str],
) -> str:
    return f"""## Post-Market Homework — Prepare for Tomorrow's Open

You are reviewing today's market action after the close. Your job is to do your
homework so you walk into tomorrow's 9:30 AM open with a clear plan.

## Today's Signals (what the market showed you)
{_format_list(signals)}

## Today's Market Movers
{_format_movers(movers)}

## News Headlines
{_format_list(news)}

## Institutional Activity
{_format_list(institutional)}

## Your Decisions Today
{_format_decisions(today_decisions)}

## Current Positions
{_format_list(open_positions)}

## Your Expertise (current mental model)
### Market
{_yaml_summary(expertise.get('market', {}))}
### Trade
{_yaml_summary(expertise.get('trade', {}))}

## Priority Watchlist
{', '.join(watchlist)}

## Task
Analyze today's action and prepare a briefing for tomorrow's open. Return valid
YAML only (no markdown fences, no prose) with this structure:

top_picks:
  - symbol: "TICKER"
    setup: "description of the setup developing"
    entry_trigger: "what needs to happen to enter"
    target_price: estimated target or null
    stop_price: where you'd place the stop
    confidence: 0.0-1.0
    signals: ["signal_type_1", "signal_type_2"]

market_outlook:
  bias: "bullish|bearish|neutral"
  reasoning: "1-2 sentence thesis"
  key_levels:
    - "SPY support/resistance level to watch"

avoid_list:
  - symbol: "TICKER"
    reason: "why to avoid tomorrow"

lessons_from_today:
  - "what you learned from today's action that changes your approach"

Focus on your priority watchlist. Identify 2-4 actionable setups with specific
entry triggers. Be concrete — not 'watch for strength' but 'buy above $X.XX
on volume > Y with stop at $Z.ZZ'. A good prep separates tomorrow's noise from
tomorrow's signals."""


def _format_daily_prep(prep: dict) -> str:
    if not prep:
        return ""
    lines = ["\n## Yesterday's Homework (your pre-market prep)"]
    outlook = prep.get("market_outlook", {})
    if outlook:
        lines.append(f"Market bias: {outlook.get('bias', '?')} — {outlook.get('reasoning', '')}")
    picks = prep.get("top_picks", [])
    if picks:
        lines.append("### Top Picks for Today")
        for p in picks:
            lines.append(
                f"  - {p.get('symbol', '?')}: {p.get('setup', '')} | "
                f"Entry: {p.get('entry_trigger', '?')} | "
                f"Stop: {p.get('stop_price', '?')} | "
                f"Conf: {p.get('confidence', '?')}")
    avoid = prep.get("avoid_list", [])
    if avoid:
        lines.append("### Avoid")
        for a in avoid:
            lines.append(f"  - {a.get('symbol', '?')}: {a.get('reason', '')}")
    lessons = prep.get("lessons_from_today", [])
    if lessons:
        lines.append("### Lessons")
        for l in lessons:
            lines.append(f"  - {l}")
    return "\n".join(lines) + "\n"


def _format_decisions(decisions: list[dict]) -> str:
    if not decisions:
        return "  (no decisions today)"
    lines = []
    for d in decisions[-10:]:
        conf = d.get("confidence", "?")
        event = d.get("event", "?")
        reason = d.get("reason", "")[:150]
        lines.append(f"  - {event} (conf={conf}): {reason}")
    return "\n".join(lines)


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
            f"  - {m['symbol']:6s}  {m['netPercentChange']:+.2f}%"
            f"  ${m['lastPrice']:.2f}"
            f"  vol {m['volume']:,}"
        )
    return "\n".join(lines)
