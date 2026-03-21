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
│   ├── decision/      # Claude API decision engine
│   ├── execution/     # Schwab API trade execution
│   └── risk/          # Stop loss, trailing stop, portfolio limits
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
├── docs/
│   └── superpowers/
│       └── specs/     # Design documents
└── main.py            # Entry point — spawns both agent threads
```

---

## Data Sources (Free Tier)

| Source | Purpose |
|--------|---------|
| Schwab API | Real-time quotes, order execution, account data |
| yfinance | Historical OHLCV data |
| Alpha Vantage | News sentiment, earnings data |
| NewsAPI | Real-time financial headlines |
| Quiver Quantitative API | 13F filings, congressional trades, insider buying |
| FINRA ATS | Dark pool / large block prints |
| SEC EDGAR | Form 13F (institutional holdings) + Form 4 (insider transactions) |

**Future (before live trading):** Paid institutional data sources (e.g., Unusual Whales, Stocksera) for real-time dark pool prints.

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
3. LEARN  → Log trade outcome and Claude's reasoning
             → Run self-improve prompt
             → Update expertise files
Repeat every N minutes during trading hours (4am–8pm ET)
```

### Expertise Files (Per Agent)

| File | Contents |
|------|---------|
| `market_expertise.yaml` | Breakout patterns, volume behavior, VWAP signals learned over time |
| `news_expertise.yaml` | Which news types/sources correlate with price moves |
| `institutional_expertise.yaml` | Which institutional signals preceded strong moves |
| `trade_expertise.yaml` | What worked, what didn't, refined risk thresholds |
| `crypto_expertise.yaml` | Activated Round 2+ — crypto trading patterns and preferences |

**Line limit per file:** ~600–1000 lines max (context window protection).

---

## Technical Analysis & Signal Detection

Signals are ranked by priority and fed holistically into Claude's decision layer:

### 1. Price & Volume Breakouts
- Price breaking above resistance with volume spike (>1.5x avg volume)
- VWAP cross with momentum confirmation
- Opening range breakout (first 30 min high/low)

### 2. Institutional Signals
- Large dark pool prints relative to avg daily volume (FINRA ATS)
- Form 4 insider buying clusters (SEC EDGAR)
- 13F position increases from major funds (Quiver Quant)
- Congressional buy disclosures (Quiver Quant)

### 3. News Sentiment
- Positive/negative sentiment score (Alpha Vantage + NewsAPI)
- Earnings surprise detection
- Sector-wide catalyst identification

### 4. Claude Decision Layer
All signals are passed to Claude API. Claude weighs them holistically, produces a trade decision with a confidence score, and logs its full reasoning. This reasoning log becomes the primary input for the self-improve cycle.

---

## Risk Management

### Per-Trade Rules
| Parameter | Default Value | Configurable |
|-----------|--------------|-------------|
| Max position size | 5% of portfolio | Yes |
| Stop loss | 2% below entry | Yes |
| Trailing stop | 1.5% | Yes |
| Max concurrent positions | 5 | Yes |

### Portfolio-Level Rules
- Max daily loss limit: 6% of portfolio — agents pause if hit
- No trading in first 5 minutes of market open
- Pre/post market trades require high-conviction signal (institutional + news catalyst both present)

### Risk Gate Flow
```
Signal identified → Risk gate checks:
  ├── Position size within limit?
  ├── Daily loss limit not hit?
  ├── Not already at max positions?
  ├── Institutional signal confirms direction? (preferred, not required)
  └── Claude confidence score above threshold?
      → PASS: Execute trade + place stop loss immediately
      → FAIL: Log reason, skip trade, add to expertise learning
```

Risk parameters start identical for both agents. Through the Act-Learn-Reuse cycle, each agent independently evolves its thresholds.

---

## Competition Framework

### Round Structure
- **Duration:** 2-week rounds
- **Starting capital:** Paper trading balance split 50/50 between agents
- **Elimination:** Agent ending in the red OR with lower P&L than the other is deleted at round end
- **New twin:** A fresh Agent B (or A) is spawned from a blank expertise template, seeded with the winner's expertise files

### Scoring Metrics
- Total P&L (primary)
- Win rate (% of profitable trades)
- Avg gain vs avg loss
- Sharpe ratio
- Best / worst single trade

### Daily Competition Report (committed to repo)
```
Date: YYYY-MM-DD
Agent A P&L: +$XXX | Win Rate: XX% | Trades: XX
Agent B P&L: +$XXX | Win Rate: XX% | Trades: XX
Leader: Agent A/B
Key divergence: [what each agent learned differently]
```

### Weekly Deep Comparison
- Which expertise file learnings drove better performance?
- Losing agent may inherit a winning pattern from the leader
- Both agents reset to same capital for fair next-round competition

---

## Winner Rewards

| Round | Loser | Winner Prizes |
|-------|-------|--------------|
| Round 1 | Deleted | Strategic params choice + Knowledge inheritance + Capital advantage + Seeds new twin |
| Round 2+ | Deleted | All Round 1 prizes + 5% of profits paid in crypto of winner's choice + Independent crypto trading account |

### Crypto Reward System (Round 2+)
- Winning agent selects its preferred cryptocurrency
- Owner pays 5% of round profits to the agent's designated crypto wallet/exchange account
- Agent manages this crypto independently via exchange API (Coinbase/Kraken)
- Crypto P&L tracked separately via `crypto_expertise.yaml`
- Act-Learn-Reuse cycle applies to crypto trading as well

---

## Instruments

| Phase | Instruments |
|-------|------------|
| Phase 1 (now) | Stocks only |
| Phase 2 (future) | Stocks + Options |

---

## Trading Hours
- Active monitoring and trading: 4am–8pm ET (pre/post market included)
- Pre/post market: high-conviction signals only

---

## Deployment

- **Initial deployment:** Paper trading (Schwab account toggled to paper mode)
- **Live trading:** After successful paper trading performance, account switched to live
- **Crypto integration:** Activated at Round 2 upon first live winner reward

---

## Setup Requirements (In Scope)
1. Schwab developer account + API credentials
2. Alpha Vantage API key (free tier)
3. NewsAPI key (free tier)
4. Quiver Quantitative API key (free tier)
5. Claude API key (Anthropic)
6. SEC EDGAR (no key required — public API)
7. FINRA ATS data (public, no key required)

---

## Key Design Principles
- **One agent, one purpose** — each agent is a specialized expert, not a generic executor
- **Mental models, not source of truth** — expertise files are working memory, validated against actual trade history
- **Darwinian improvement** — elimination pressure drives genuine learning
- **Isolation** — agents share data feeds but never share decision state or expertise files
- **Audit trail** — every decision, trade, and learning update committed to the repo
