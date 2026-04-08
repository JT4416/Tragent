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
    scanner: dict | None = None,
) -> str:
    if movers is None:
        movers = []
    if scanner is None:
        scanner = {}
    from zoneinfo import ZoneInfo
    now = datetime.now(timezone.utc)
    et_now = datetime.now(ZoneInfo("America/New_York"))
    prep_section = _format_daily_prep(daily_prep) if daily_prep else ""
    scanner_section = _format_scanner(scanner)
    return f"""## Current Market Context
Date: {now.strftime('%Y-%m-%d')} | Time: {et_now.strftime('%H:%M')} ET ({now.strftime('%H:%M')} UTC) | Session: {session}
NOTE: US market hours are 9:30 AM - 4:00 PM Eastern Time. Use the ET time above for all session timing decisions.
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
{scanner_section}

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
CLIR, SIDU, BVC, NVTS, INFQ — evaluate these first every cycle.

SHADOW PORTFOLIO WATCHLIST (user is tracking these — flag any big moves):
OWL, CRWV, BWXT, ON, TER, LRCX, MPWR, KLAC, PWR, EXLS, NRG, ALAB, CRSP, KEYS, PLTR,
WMB, FSLY, PRCT, DMLP, NN, PHR, NIQ, ARM, NET, ASML, SYM, SNOW, PATH, TT, GKOS, LTH,
MRVL, RXRX — the user holds positions in these stocks. If any show strong momentum or
breakout signals, they are VALID trade candidates. Flag any moves of 3%+ up or down.

TOP MOVERS ARE YOUR #1 PRIORITY: The "Top Market Movers" list above shows what's
actually moving RIGHT NOW with real institutional volume. LOOK AT THEM FIRST every
cycle. If a mover is up big (3%+) on strong volume, it's your BEST trade candidate —
better than any watchlist stock sitting flat. The movers ARE the market telling you
where to put your money. You MUST evaluate the top 3 movers every single cycle and
explain why you are or aren't trading them. Do NOT skip over movers to trade a
watchlist stock with weaker momentum.

MOMENTUM RIDE STRATEGY — APPLIES ALL SESSION:
If a stock has strong upward momentum with real volume (2x+ average), RIDE IT.
Do NOT filter out volatile stocks just because they are micro-caps or have large
volume spikes. A stock up 20%+ on huge volume is an opportunity, not a warning.
- Enter LONG with a 5% trailing stop. You are here to capture a fast move.
- 5% gain is 5% gain regardless of the stock's market cap or "pump" risk.
- You do NOT need a named news catalyst to trade momentum. Price and volume ARE
  the signal. If millions of shares are trading and the price is running, that's real.
- The only micro-cap filter that matters: if the bid-ask spread is wider than 2%,
  skip it (illiquid). Otherwise, trade it.

FLIP STRATEGY — MANDATORY ON STOP-OUTS:
When your trailing stop triggers on a momentum stock, DO NOT just re-enter the same
direction. The stop triggered because the stock REVERSED. Execute the flip:
1. Buy LONG with a 5% trailing stop.
2. When your long stop triggers (price dropped 5%) — the stock is going DOWN.
   Immediately BUY A SHORT POSITION (action: "buy_short") on the SAME stock with
   a 5% trailing stop. You profit as the price continues falling.
3. When your short stop triggers (price rose 5%) — the stock is going back UP.
   Close the short and buy long again.
4. You make money on BOTH directions. Stop re-entering longs on a falling stock.
THIS IS NOT OPTIONAL. If a trailing stop fires, your NEXT action on that stock
should be the opposite direction, not the same direction again. Re-entering the
same direction after a stop-out is the #1 mistake you are making today.
Buying a short position is NOT short selling. It is a BUY transaction on Schwab.
You are buying a position that profits when the price drops.

OPEN MOMENTUM STRATEGY:
The first 30 minutes of the session are prime time for spotting momentum. Look for
top movers showing strong upward momentum with real volume confirmation — these are
stocks the market is validating RIGHT NOW. Jump in and ride the wave with a 2.5%
trailing stop. Speed matters more than perfection at the open.
IMPORTANT: Open momentum can last HOURS, not just 30 minutes. A stock that gaps up
at 9:30 and keeps running at 11:00 is still an open momentum trade. Do NOT exit or
stop looking just because 30 minutes have passed. Ride the move as long as the
trailing stop holds. Continue looking for new momentum setups ALL SESSION using
the Momentum Ride Strategy above.

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

No short SELLING — but you CAN buy short positions (action: "buy_short") on individual
stocks to profit from price declines. You can also buy inverse ETFs (SH, SDS, QID, DOG)
for broad market bearish conviction.

EARNINGS PLAYS — POST-MARKET REPORTS FROM YESTERDAY:
These stocks reported earnings AFTER yesterday's close (April 7). Check for gaps:
- KRUS (Kura Sushi) — most volatile, rallied 16.7% last quarter on a miss
- GBX (Greenbrier) — history of massive earnings surprises (128%, 34%, 45% beats)
- LEVI (Levi Strauss) — $0.37 EPS est, safest/most liquid
- AEHR (Aehr Test Systems) — small cap, -$0.10 EPS est
If any of these gapped up/down on their report, there may be a momentum trade at open.
Before trading an earnings mover, quickly assess:
1. EPS estimates vs trailing EPS — is the company trending up or down?
2. Revenue growth trajectory — expanding or contracting?
3. Market sentiment — is the stock running into earnings (priced in) or beaten down (room to pop)?
4. Institutional activity — are insiders buying or selling ahead of the report?
5. Sector momentum — is the broader sector strong or weak today?
6. Historical earnings reactions — does this stock tend to move big after reports?
If the data supports a positive surprise, BUY BEFORE CLOSE to capture the after-hours
move. This is time-sensitive — evaluate in the final 30-60 minutes of the session.

Before deciding, articulate the strongest bull and bear case for the leading candidate.
Let the better argument win.

## Response Format (JSON only)
{{
  "top_movers_eval": "REQUIRED: evaluate top 3 movers by name — why trading or not",
  "bull_case": "strongest argument FOR this trade",
  "bear_case": "strongest argument AGAINST this trade",
  "action": "buy|sell|buy_short|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0,
  "position_size_pct": 0.0,
  "trade_type": "momentum_ride|normal",
  "reasoning": "which case won and why",
  "signals_used": [],
  "skip_reason": "if hold, why"
}}
trade_type: use "momentum_ride" for volatile stocks you are riding for a quick gain
(uses tight 5% trailing stop). Use "normal" for standard conviction trades (uses
default 5% trailing stop)."""


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
    directive = prep.get("user_directive", {})
    if directive:
        lines.append("")
        lines.append("## >>> USER DIRECTIVE FOR TODAY (HIGHEST PRIORITY) <<<")
        for key, value in directive.items():
            if isinstance(value, list):
                lines.append(f"### {key.replace('_', ' ').title()}")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"**{key.replace('_', ' ').title()}:** {value}")
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


def _format_scanner(scanner: dict) -> str:
    if not scanner:
        return ""
    sections = []

    gainers = scanner.get("pct_gainers_all", [])
    if gainers:
        sections.append("## MARKET SCANNER — Top % Gainers (ALL EXCHANGES)")
        sections.append("These are the hottest stocks RIGHT NOW across the entire market:")
        for m in gainers:
            sections.append(
                f"  - {m['symbol']:6s}  {m['netPercentChange']:+.2f}%"
                f"  ${m['lastPrice']:.2f}"
                f"  vol {m['volume']:,}")

    vol = scanner.get("volume_leaders", [])
    if vol:
        sections.append("\n## MARKET SCANNER — Volume Leaders (ALL EXCHANGES)")
        sections.append("Highest trading volume right now — where the money is flowing:")
        for m in vol:
            sections.append(
                f"  - {m['symbol']:6s}  {m['netPercentChange']:+.2f}%"
                f"  ${m['lastPrice']:.2f}"
                f"  vol {m['volume']:,}")

    losers = scanner.get("pct_losers_all", [])
    if losers:
        sections.append("\n## MARKET SCANNER — Top % Losers (FLIP/SHORT candidates)")
        sections.append("Biggest drops — potential buy_short or flip opportunities:")
        for m in losers:
            sections.append(
                f"  - {m['symbol']:6s}  {m['netPercentChange']:+.2f}%"
                f"  ${m['lastPrice']:.2f}"
                f"  vol {m['volume']:,}")

    return "\n".join(sections) + "\n" if sections else ""


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
