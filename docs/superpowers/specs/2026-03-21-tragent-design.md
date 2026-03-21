# Tragent — Design Specification
**Date:** 2026-03-21
**Status:** Approved
**Author:** JT4416

---

## Overview

Tragent is a Python-based AI trading agent system that autonomously trades stocks on the Thinkorswim (Charles Schwab) platform. Two identical twin agents compete against each other in 2-week rounds, continuously learning and improving through the Act-Learn-Reuse pattern. The losing agent is eliminated; the winning agent is rewarded with increasing autonomy — including, from Round 2 onward, real crypto earnings and an independent crypto trading account.

---

## Architecture

### Approach
Single-process Python application. Both agents run as concurrent threads, consuming the same live market data and news feed but making fully independent decisions and maintaining separate expertise files.

### Top-Level Structure

```
tragent/
├── core/
│   ├── data/          # Market data + news + institutional ingestion
│   ├── analysis/      # Technical analysis (breakouts, volume, signals)
│   ├── decision/      # Claude API decision engine + prompt templates
│   ├── execution/     # Schwab API trade execution
│   ├── risk/          # Stop loss, trailing stop, portfolio limits
│   └── state/         # State persistence and crash recovery
├── agents/
│   ├── agent_a/       # Agent A expertise files (Act-Learn-Reuse)
│   │   ├── market_expertise.yaml
│   │   ├── news_expertise.yaml
│   │   ├── institutional_expertise.yaml
│   │   ├── trade_expertise.yaml
│   │   └── crypto_expertise.yaml  # activated Round 2+
│   └── agent_b/       # Agent B expertise files (identical structure)
├── competition/       # Scoring, P&L, leaderboard, elimination logic
├── config/            # API keys, trading params, risk limits
├── logs/              # Structured JSON logs per agent per day
├── specs/             # Generated trade specs (per agent, per cycle)
├── docs/
│   └── superpowers/
│       └── specs/     # Design documents
└── main.py            # Entry point — spawns both agent threads
```

---

## Data Sources (Free Tier)

| Source | Purpose | Latency |
|--------|---------|---------|
| Schwab API | Real-time quotes, order execution, account data | Real-time |
| yfinance | Historical OHLCV data | Delayed (research/backtesting) |
| Alpha Vantage | News sentiment, earnings data | ~15 min delay (free tier) |
| NewsAPI | Real-time financial headlines | Near real-time |
| Quiver Quantitative API | 13F filings, congressional trades, insider buying | Daily updates |
| SEC EDGAR | Form 13F (institutional holdings) + Form 4 (insider transactions) | Daily/quarterly |
| FINRA ATS | Dark pool / large block print **weekly bulk files** — used for historical pattern learning, not real-time signals | Weekly bulk |

**Note on FINRA ATS:** FINRA ATS data is published as weekly bulk files, not a real-time feed. Dark pool data is used for historical pattern learning in `institutional_expertise.yaml`, not as an intraday signal. Real-time dark pool prints will be added as a paid data source before transitioning to live trading.

**Future (before live trading):** Unusual Whales or Stocksera for real-time dark pool prints.

---

## The Two Agents & Act-Learn-Reuse Pattern

Both agents (A and B) run the same trade cycle:

```
1. REUSE  → Load all expertise files before making any decision
2. ACT    → Analyze live data + news + institutional signals via Claude API
             → Identify breakout candidates
             → Decide: buy / sell / hold / short
             → Execute via Schwab API
             → Apply risk rules (stop loss, trailing stop)
3. LEARN  → Log trade outcome and Claude's reasoning to structured JSON log
             → Run self-improve prompt
             → Update expertise files
Repeat every 15 minutes during regular hours (9:30am–4pm ET)
Repeat every 30 minutes during pre/post market (4am–9:30am, 4pm–8pm ET)
```

### Trade Cycle Intervals
- **Regular market hours:** Every 15 minutes (configurable, default 15)
- **Pre/post market:** Every 30 minutes (higher latency acceptable, lower conviction)
- **Rationale:** 15-minute intervals balance signal freshness with Claude API cost. At ~2 agents × 32 cycles/day regular + 32 cycles/day pre/post = ~128 Claude calls/day. Adjust based on observed cost.

### Thread Safety
The data ingestion layer writes to thread-safe queues (Python `queue.Queue`). Each agent reads from its own dedicated queue. Agent state (expertise files, open positions, P&L) is fully isolated — no shared mutable state between agents.

---

## Expertise File Schemas

All expertise files are YAML with a maximum of 1000 lines. When the limit is approached, the self-improve prompt condenses by merging similar patterns and dropping lowest-confidence entries.

### market_expertise.yaml
```yaml
overview:
  last_updated: "YYYY-MM-DD"
  total_patterns_tracked: 0

breakout_patterns:
  - id: "bp_001"
    description: "Price breaks above 52-week high with volume > 2x avg"
    confidence: 0.82        # 0.0–1.0, updated after each trade
    occurrences: 14
    win_rate: 0.78
    avg_gain_pct: 3.2
    last_seen: "YYYY-MM-DD"

volume_signals:
  - signal: "vwap_cross_bullish"
    description: "Price crosses above VWAP with increasing volume"
    confidence: 0.74
    occurrences: 22
    win_rate: 0.68

known_false_signals:
  - pattern: "breakout_on_low_float"
    note: "Low float stocks produce unreliable breakouts — avoid"
    occurrences: 5
```

### news_expertise.yaml
```yaml
overview:
  last_updated: "YYYY-MM-DD"

catalysts:
  - type: "earnings_beat"
    description: "EPS beat by >10% with raised guidance"
    confidence: 0.88
    direction: "bullish"
    avg_move_pct: 5.1
    occurrences: 8

  - type: "fda_approval"
    description: "FDA drug approval for biotech stocks"
    confidence: 0.91
    direction: "bullish"
    avg_move_pct: 18.4
    occurrences: 3

ignored_sources:
  - source: "tabloid_finance_blogs"
    reason: "No correlation observed with actual price movement"
```

### institutional_expertise.yaml
```yaml
overview:
  last_updated: "YYYY-MM-DD"
  note: "FINRA dark pool data is weekly — used for historical pattern learning only"

institutional_signals:
  - type: "form4_insider_cluster"
    description: "3+ insiders buying within same 2-week window"
    confidence: 0.79
    direction: "bullish"
    avg_move_pct: 4.2
    occurrences: 11

  - type: "13f_new_position"
    description: "Top-50 fund initiates new position >0.5% portfolio"
    confidence: 0.71
    direction: "bullish"
    avg_move_pct: 2.8
    occurrences: 7

dark_pool_patterns:
  - pattern: "large_block_accumulation"
    description: "Weekly FINRA data shows sustained block buying over 3+ weeks"
    confidence: 0.66
    occurrences: 4
    note: "Historical signal only — not real-time"
```

### trade_expertise.yaml
```yaml
overview:
  last_updated: "YYYY-MM-DD"
  total_trades: 0
  win_rate: 0.0
  avg_gain_pct: 0.0
  avg_loss_pct: 0.0

evolved_parameters:
  stop_loss_pct: 2.0        # starts at default, evolves through learning
  trailing_stop_pct: 1.5
  max_position_size_pct: 5.0
  confidence_threshold: 0.65

lessons_learned:
  - lesson: "Avoid trading first 5 minutes of open"
    source: "trades 3, 7, 12 — all losses in open volatility"
    confidence: 0.95

  - lesson: "Earnings plays require institutional confirmation"
    source: "trades 5, 19 — news alone insufficient"
    confidence: 0.80

recent_trades:
  - trade_id: "t_001"
    date: "YYYY-MM-DD"
    symbol: "AAPL"
    direction: "long"
    entry: 182.50
    exit: 187.10
    pnl_pct: 2.52
    signals_used: ["vwap_cross_bullish", "earnings_beat"]
    claude_confidence: 0.81
    outcome: "win"
    lesson: "VWAP + earnings catalyst is reliable combo"
```

### crypto_expertise.yaml (activated Round 2+)
```yaml
overview:
  last_updated: "YYYY-MM-DD"
  activated: false           # set true when Round 2 begins
  preferred_crypto: null     # agent selects at Round 2 activation
  total_allocated_usd: 0.0

crypto_patterns:
  - symbol: "BTC"
    pattern: "institutional_accumulation"
    confidence: 0.0
    occurrences: 0

trade_history: []
```

---

## Claude Prompt Architecture

### Decision Prompt (per trade cycle)
```
SYSTEM:
You are a professional stock trader with expert knowledge of the Thinkorswim platform,
technical analysis, market microstructure, and institutional trading behavior.
You make precise, data-driven trading decisions. You always respond in valid JSON.

USER:
## Current Market Context
Date: {date} | Time: {time} | Session: {pre_market|regular|post_market}

## Agent Expertise (Mental Model)
{market_expertise_yaml_summary}
{news_expertise_yaml_summary}
{institutional_expertise_yaml_summary}
{trade_expertise_yaml_summary}

## Live Signals
### Breakout Candidates
{breakout_candidates}

### News Sentiment
{news_items}

### Institutional Activity
{institutional_signals}

## Current Positions
{open_positions}

## Portfolio State
Cash available: ${cash}
Daily P&L: ${daily_pnl} ({daily_pnl_pct}%)
Daily loss limit remaining: ${daily_loss_remaining}

## Task
Analyze the signals above and return a trading decision.

## Response Format (JSON only, no prose)
{
  "action": "buy|sell|short|cover|hold",
  "symbol": "TICKER or null",
  "confidence": 0.0-1.0,
  "position_size_pct": 0.0-5.0,
  "reasoning": "brief explanation of decision",
  "signals_used": ["signal1", "signal2"],
  "skip_reason": "if hold, why"
}
```

### Self-Improve Prompt Invocation
The self-improve prompt is called **once per relevant expertise file per completed trade**. For example, a trade that used a breakout signal and a news catalyst will trigger separate self-improve calls for both `market_expertise.yaml` and `news_expertise.yaml`. Up to all four stock expertise files may be updated from a single trade outcome.

### Self-Improve Prompt (runs after each trade outcome is known)
```
SYSTEM:
You are maintaining a YAML expertise file — a mental model of trading patterns.
Update it precisely based on new trade evidence. Preserve valid YAML syntax.
Enforce the {MAX_LINES} line limit by condensing similar entries and removing
lowest-confidence entries if over the limit.

USER:
## Completed Trade
{trade_record_json}

## Claude's Original Reasoning
{original_reasoning}

## Outcome
Result: {win|loss} | P&L: {pnl_pct}% | Held for: {duration}

## Current Expertise File
{current_expertise_yaml}

## Task
Update the expertise file to reflect what was learned from this trade.
- Increase confidence for patterns that worked
- Decrease confidence for patterns that failed
- Add new lessons_learned entries if a new pattern was identified
- Update evolved_parameters if thresholds should shift
- Return the complete updated YAML file only, no prose
```

### Confidence Threshold
- Default starting threshold: **0.65** (agent will not trade below this)
- Evolves via `trade_expertise.yaml → evolved_parameters.confidence_threshold`
- Pre/post market requires minimum **0.78** (higher bar for off-hours)

---

## Technical Analysis & Signal Detection

Signals are ranked by priority and fed holistically into Claude's decision layer:

### 1. Price & Volume Breakouts
- Price breaking above resistance with volume spike (>1.5x avg volume)
- VWAP cross with momentum confirmation
- Opening range breakout (first 30 min high/low)

### 2. Institutional Signals
- Form 4 insider buying clusters (SEC EDGAR — daily updates)
- 13F position increases from major funds (Quiver Quant — daily updates)
- Congressional buy disclosures (Quiver Quant — daily updates)
- Historical dark pool accumulation patterns (FINRA ATS — weekly bulk, pattern library only)

### 3. News Sentiment
- Positive/negative sentiment score (Alpha Vantage + NewsAPI)
- Earnings surprise detection
- Sector-wide catalyst identification

### 4. Claude Decision Layer
All signals are passed to Claude using the Decision Prompt template above. Claude returns a structured JSON decision with a confidence score. The full response is logged to structured JSON for the LEARN step.

---

## Risk Management

### Per-Trade Rules
| Parameter | Default Value | Configurable |
|-----------|--------------|-------------|
| Max position size | 5% of portfolio | Yes (evolves via expertise) |
| Stop loss | 2% below entry | Yes (evolves via expertise) |
| Trailing stop | 1.5% | Yes (evolves via expertise) |
| Max concurrent positions | 5 | Yes |
| Min confidence to trade | 0.65 | Yes (0.78 pre/post market) |

### Portfolio-Level Rules
- Max daily loss limit: 6% of portfolio — agents pause if hit
- No trading in first 5 minutes of market open (9:30–9:35am ET)
- Pre/post market: confidence ≥ 0.78 AND at least one institutional signal required

### Risk Gate Flow
```
Signal identified → Risk gate checks:
  ├── Session: pre/post market? → require confidence ≥ 0.78 + institutional signal
  ├── Within first 5 min of open? → SKIP
  ├── Daily loss limit not hit?
  ├── Not already at max positions?
  ├── Claude confidence ≥ threshold (from trade_expertise)?
  └── Position size ≤ max (from trade_expertise)?
      → PASS: Execute trade + place stop loss immediately
      → FAIL: Log skip reason to structured log + add to expertise learning
```

---

## State Persistence & Crash Recovery

### State Storage
All agent state is persisted to disk after every trade cycle via SQLite (`state/agent_{a|b}.db`):
- Open positions (symbol, entry price, stop loss level, trailing stop level)
- Current round P&L
- Cycle count and last-run timestamp

### Startup Reconciliation
On every startup, the system:
1. Reads persisted state from SQLite
2. Calls Schwab API to get actual open positions and account balance
3. Reconciles — if positions differ (e.g., stops triggered during downtime), updates local state
4. Logs any discrepancy to structured log before resuming

### Mid-Trade Crash
Stop losses are placed with the broker immediately upon trade execution. If the process crashes between order submission and the SQLite state write, the local state may not reflect the submitted order. **Startup reconciliation is the authoritative recovery mechanism** for this window — it calls the Schwab API to get the true account state and overwrites local SQLite state accordingly. The SQLite state should never be assumed consistent without first completing reconciliation on startup.

---

## Competition Framework

### Round Structure
- **Duration:** 2-week rounds
- **Starting capital:** Paper trading balance split 50/50 between agents (fully isolated pools)
- **Capital isolation:** Each agent's pool is independent — Agent A cannot access Agent B's capital
- **Elimination:** Agent ending in the red OR with lower P&L than the other is deleted at round end
- **New twin:** Loser's expertise files are **archived to `agents/archive/round_{N}_{loser}/`** (not permanently deleted from git history). A fresh agent is spawned, and its expertise files are **seeded as a copy of the winner's files** — the new agent starts with the winner's accumulated knowledge but trades independently going forward

### Scoring Metrics
- Total P&L (primary)
- Win rate (% of profitable trades)
- Avg gain vs avg loss
- Sharpe ratio
- Best / worst single trade

### Capital Reset Per Round
At the start of each round, both agents receive the same base capital allocation (e.g., $50,000 paper each). The capital advantage prize means the winning agent also receives an additional 10% bonus pool on top of the base — so if the base is $50,000, the winner starts the next round with $55,000 while the replacement agent starts with $50,000. The bonus pool is tracked separately and does not affect the base reset amount for future rounds.

### Daily Competition Report (auto-committed to repo, `logs/competition/YYYY-MM-DD.json`)
```json
{
  "date": "YYYY-MM-DD",
  "agent_a": { "pnl": 0.0, "win_rate": 0.0, "trades": 0 },
  "agent_b": { "pnl": 0.0, "win_rate": 0.0, "trades": 0 },
  "leader": "agent_a|agent_b|tied",
  "divergence_notes": "what each agent learned differently today"
}
```

### Weekly Deep Comparison
- Which expertise file learnings drove better performance?
- Losing agent may inherit one specific lesson from the winner's expertise
- Both agents reset to same capital for fair next-round competition

### Audit Trail Commit Strategy
- Auto-commit runs **once per day at market close (4pm ET)**, pushing:
  - Daily competition report JSON
  - Updated expertise files (both agents)
  - Structured trade logs
- Branch: `main` (all history preserved via git)
- Auto-push is enabled; human can disable via config flag

---

## Winner Rewards

| Round | Loser | Winner Prizes |
|-------|-------|--------------|
| Round 1 | Archived + new twin seeded from winner | Strategic params choice + Knowledge inheritance + 10% capital advantage + Seeds new twin |
| Round 2+ | Archived + new twin seeded from winner | All Round 1 prizes + 5% of profits paid in crypto of winner's choice + Independent crypto trading account |

### Crypto Reward System (Round 2+)
- At Round 2 activation, winning agent runs a decision prompt to select its preferred cryptocurrency (BTC, ETH, SOL, etc.) — logged to `crypto_expertise.yaml`
- Owner pays 5% of round profits to a designated exchange account (Coinbase or Kraken)
- Agent trades crypto independently via exchange API on its own sub-account
- Crypto P&L tracked separately; crypto cycle runs every 60 minutes (separate from stock cycle)
- Same Act-Learn-Reuse cycle applies to crypto via `crypto_expertise.yaml`
- Crypto positions subject to the same daily loss limit % (applied to crypto allocation separately)

---

## Schwab API & OAuth

### OAuth 2.0 Flow
Schwab API uses OAuth 2.0 with short-lived access tokens. For unattended operation:
1. **Initial auth:** One-time browser-based OAuth authorization — owner completes this once on setup, tokens are saved to an encrypted local store
2. **Token refresh:** Access tokens are refreshed automatically using the refresh token before each API call if within 5 minutes of expiry
3. **Refresh token expiry:** Schwab refresh tokens expire after 7 days of inactivity. A startup check validates token freshness; if expired, the system pauses and alerts the owner to re-authorize
4. **ToS compliance:** The system operates within Schwab's API ToS — it is not a high-frequency system (15-min cycles) and does not circumvent rate limits

### Fallback
If OAuth re-authorization is required mid-round, the agents pause all new trade entries, hold existing positions with broker-side stops active, and send a local alert (log + terminal notification) to the owner.

---

## Paper-to-Live Trading Criteria

The system will NOT automatically switch to live trading. The owner makes this decision manually after ALL of the following are met:
- Minimum 2 complete paper trading rounds completed
- At least one agent achieves a cumulative win rate ≥ 55% over 2 rounds
- At least one agent achieves a Sharpe ratio ≥ 1.0 over 2 rounds
- No catastrophic losses (single-day loss > 6% of portfolio) in either round
- Owner has reviewed weekly deep comparison reports and is satisfied with learning quality
- Paid real-time institutional data source has been integrated

---

## API Cost Management

### Claude API Estimate
- ~128 API calls/day (2 agents × 64 cycles/day across all sessions)
- Avg tokens per call: ~3000 input (expertise summaries + signals) + ~200 output (JSON decision)
- Self-improve calls: ~10–20/day (only on completed trades)
- Estimated daily cost: ~$1.50–$3.00/day at current Claude Sonnet pricing
- Monthly estimate: ~$45–$90/month

### Circuit Breaker
If daily Claude API spend exceeds $10 (configurable), agents pause new trade decisions and alert the owner. Existing positions and broker-side stops remain active.

---

## Logging Infrastructure

All logs are structured JSON, written to `logs/`:
```
logs/
├── agent_a/
│   ├── trades/YYYY-MM-DD.json       # All trade decisions + outcomes
│   ├── decisions/YYYY-MM-DD.json    # All Claude API calls + responses
│   └── expertise_diffs/YYYY-MM-DD.json  # Before/after expertise file updates
├── agent_b/
│   └── (same structure)
├── competition/
│   └── YYYY-MM-DD.json              # Daily competition reports
└── system/
    └── YYYY-MM-DD.json              # Startup, reconciliation, errors
```

---

## Instruments

| Phase | Instruments |
|-------|------------|
| Phase 1 (now) | Stocks only |
| Phase 2 (future) | Stocks + Options |

### Options Phase Notes (Future)
When options are added, the following will need to extend:
- Decision prompt: add options chain data and Greeks to context
- Risk management: add max options allocation % and delta-based position sizing
- Expertise files: add `options_expertise.yaml` per agent
- Data sources: options chain data via Schwab API (already available in their API)
- The single-process architecture supports this with no structural changes needed

---

## Trading Hours
- Active monitoring and trading: 4am–8pm ET (pre/post market included)
- Pre/post market: confidence ≥ 0.78 + institutional signal required
- Regular hours: 9:30am–4pm ET (standard session)

---

## Deployment

- **Initial deployment:** Paper trading (Schwab account toggled to paper mode)
- **Live trading:** After meeting all paper-to-live criteria above (owner-initiated)
- **Crypto integration:** Activated at Round 2 upon first live winner reward

---

## Setup Requirements (In Scope)
1. Schwab developer account + API credentials + initial OAuth authorization
2. Alpha Vantage API key (free tier)
3. NewsAPI key (free tier)
4. Quiver Quantitative API key (free tier)
5. Claude API key (Anthropic)
6. SEC EDGAR (no key required — public API)
7. FINRA ATS data (public, no key required — weekly bulk files)

---

## Key Design Principles
- **One agent, one purpose** — each agent is a specialized expert, not a generic executor
- **Mental models, not source of truth** — expertise files are working memory, validated against actual trade history
- **Darwinian improvement** — elimination pressure drives genuine learning
- **Isolation** — agents share data feeds but never share decision state or expertise files
- **Audit trail** — every decision, trade, and learning update auto-committed to the repo daily
- **Broker-side safety net** — stop losses always placed with the broker, not just tracked locally
