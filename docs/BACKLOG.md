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
