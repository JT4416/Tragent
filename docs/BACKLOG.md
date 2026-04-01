# Tragent Backlog

Items here are approved for future development but not yet spec'd or scheduled unless noted.

---

## Dashboard
**Status:** Placeholder — not yet spec'd

A web-based dashboard for monitoring the two competing agents in real time.

Minimum viable scope (to be defined):
- Live portfolio state for Agent A and Agent B (cash, positions, P&L)
- Round standings (who's winning, by how much)
- Recent trades and reasoning
- Paper trading day count / live-ready status

---

## Debate + Peer Exchange
**Status:** Spec and plan written — not yet implemented
**Spec:** `docs/superpowers/specs/2026-03-28-debate-peer-exchange-design.md`
**Plan:** `docs/superpowers/plans/2026-03-28-debate-peer-exchange.md`

Two agentic learning improvements:
1. **Structured self-debate** — Claude articulates a bull case and bear case before every decision; both fields persisted into the LEARN phase
2. **Post-trade peer exchange** — agents share insights via a shared queue after each trade; receiving agent runs a peer learning prompt to update its own expertise without blindly copying

---

## Crypto Reward System (Round 2+)
**Status:** Placeholder — not yet spec'd

At Round 2, the winning agent earns crypto rewards:
- Owner pays 5% of round profits to a designated exchange account (Coinbase or Kraken)
- Agent selects its preferred cryptocurrency via a decision prompt
- Agent trades crypto independently via exchange API on its own sub-account
- Crypto P&L tracked separately; cycle runs every 60 minutes
- `crypto_expertise.yaml` activated and maintained per agent

---

## Options Trading (Phase 2)
**Status:** Placeholder — not yet spec'd

Extend agents to trade options in addition to stocks:
- Add options chain data and Greeks to the decision prompt context
- Add `options_expertise.yaml` per agent
- Risk management: max options allocation % and delta-based position sizing
- Data source: Schwab API already supports options chains

---

## Real-Time Dark Pool / Institutional Data (Pre-Live Gate)
**Status:** Placeholder — required before live trading

Replace FINRA ATS weekly bulk files with a real-time dark pool feed:
- Candidates: Unusual Whales, Stocksera
- Required as part of the paper-to-live criteria before switching to live capital
- Current FINRA ATS integration is historical-only (pattern learning, not intraday signals)

---

## SEC EDGAR Integration
**Status:** Placeholder — partially referenced, not built

Pull Form 4 (insider transactions) and Form 13F (institutional holdings) directly from SEC EDGAR:
- No API key required — public API
- Currently only Quiver Quant is used for institutional signals
- EDGAR gives raw filings; adds redundancy and depth

---

## Pre/Post Market Trading
**Status:** Blocked until agents have 3+ months live trading experience (TIER 1 constraint)

Enable agents to trade during pre-market (4am–9:30am ET) and post-market (4pm–8pm ET):
- Confidence threshold: ≥ 0.78 (vs 0.65 regular hours)
- At least one institutional signal required
- Currently hard-disabled in `RiskGate`

---

## Paper-to-Live Criteria Checker
**Status:** Placeholder — not yet spec'd

Automated check that reports whether all criteria for switching to live trading are met:
- 2+ complete paper trading rounds completed
- At least one agent: cumulative win rate ≥ 55% over 2 rounds
- At least one agent: Sharpe ratio ≥ 1.0 over 2 rounds
- No catastrophic losses (single-day loss > 6%) in either round
- Paid real-time institutional data source integrated
- Owner reviews and manually flips the switch — this checker just surfaces the status

---

## Weekly Deep Comparison Report
**Status:** Placeholder — not yet spec'd

End-of-week analysis comparing the two agents:
- Which expertise file learnings drove better performance?
- Where did agents diverge in their decisions on the same signals?
- Losing agent may inherit one specific lesson from the winner's expertise
- Auto-committed to repo alongside daily reports

---

## OAuth Token Expiry Alert
**Status:** Placeholder — not yet built

Schwab refresh tokens expire after 7 days of inactivity:
- On startup, validate token freshness
- If expired or within 24 hours of expiry, alert the owner (log + webhook notification)
- Agents pause new trade entries; existing positions held with broker-side stops active
- Owner re-authorizes via `python -m core.data.schwab_client auth`

---

## Backtesting Framework
**Status:** Placeholder — not yet spec'd

Replay historical market data through the full agent decision pipeline to evaluate strategy performance before deploying changes to paper trading:
- Run both agents against historical OHLCV + news data
- Measure P&L, win rate, Sharpe, max drawdown across date ranges
- Useful for validating prompt changes, signal tweaks, and risk parameter updates before they go live
- Candidate libraries: `backtrader`, `vectorbt`, or a custom replay harness using existing `YFinanceClient`

---

## Alphalens Signal Validation
**Status:** Placeholder — not yet spec'd

Use [Alphalens](https://github.com/quantopian/alphalens) to measure the predictive power of individual signals (VWAP cross, volume spike, movers momentum, etc.) before trusting them in live decisions:
- Forward returns analysis per signal
- Information coefficient (IC) and IC decay
- Turnover and sector breakdown
- Identifies which signals are genuinely alpha-generative vs noise
- Feeds findings back into `market_expertise.yaml` confidence calibration

---

## Multi-Timeframe Alignment (5m / 15m / 1h)
**Status:** Placeholder — not yet spec'd

Require signals to align across multiple timeframes before Claude acts on them — reduces false positives from single-timeframe noise:
- 5-minute: entry timing and momentum confirmation
- 15-minute: current cycle interval (primary)
- 1-hour: trend direction and context
- A signal only reaches Claude if it's visible on at least 2 of 3 timeframes
- Requires extending `TechnicalAnalyzer` and `YFinanceClient` to fetch multi-period OHLCV

---

## FRED Macro Context Layer
**Status:** Placeholder — under consideration

Inject Federal Reserve Economic Data (FRED) macro indicators into the decision prompt as background context:
- Candidates: Fed Funds Rate, 10Y/2Y yield spread (recession indicator), CPI, unemployment, VIX
- Updated daily or on scheduled intervals (not real-time)
- Gives Claude awareness of the macro regime (risk-on vs risk-off, tightening vs easing)
- Free API via `fredapi` Python library
- Marked "maybe" — assess value after first paper trading round

---

## Empyrical Risk-Adjusted Returns in Learn Phase
**Status:** Placeholder — not yet spec'd

Replace raw win rate as the primary optimization signal in the LEARN phase with risk-adjusted return metrics from [Empyrical](https://github.com/quantopian/empyrical):
- Sharpe ratio, Sortino ratio, Calmar ratio, max drawdown
- Currently `trade_expertise.yaml` tracks win rate and avg P&L — agents optimize for wins, not quality of wins
- Empyrical metrics computed on rolling trade history and fed into the self-improve prompt
- Agent learns to prefer high-Sharpe setups over raw win count

---

## Institutional Options Flow as a Signal
**Status:** Placeholder — not yet spec'd

Add unusual options activity from institutional players as a signal source:
- Large call/put sweeps, unusual open interest changes, dark pool prints tied to options
- Data candidates: Unusual Whales, Market Chameleon, Tradier options API
- Particularly useful for detecting directional conviction before price moves
- Complements existing insider buying signals in `institutional_expertise.yaml`

---

## Kelly Criterion Position Sizing
**Status:** Placeholder — not yet spec'd

Replace fixed `position_size_pct` with Kelly Criterion-based sizing that adapts to each agent's observed win rate and avg win/loss ratio:
- Full Kelly: `f* = (bp - q) / b` where b = avg win/loss ratio, p = win rate, q = 1-p
- Use fractional Kelly (e.g., half-Kelly) to reduce volatility
- Size computed per trade from rolling `trade_expertise.yaml` stats
- Replaces the current static 20% cap with a dynamically earned allocation
- RiskGate still enforces a hard ceiling as a safety backstop
