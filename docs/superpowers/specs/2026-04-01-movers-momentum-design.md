# Movers-First Momentum Strategy — Design Specification
**Date:** 2026-04-01
**Status:** Approved
**Author:** JT4416

---

## Overview

Agents currently make decisions based on a predefined watchlist of stocks analyzed with technical indicators. This design adds Schwab's real-time top movers list as a primary signal source, so agents scan what the market has already validated before consulting technical analysis. The strategy: ride stocks already showing confirmed momentum ("ride the train up").

---

## Architecture

No new files. Three targeted changes to existing components.

### 1. `SchwabClient` — add `get_movers()`

New method on `SchwabClient`:

```python
def get_movers(self, index: str = "SPX", top_n: int = 10) -> list[dict]:
```

Calls `schwab-py`'s `get_movers()` endpoint for the given index. Returns a clean list:

```python
[
  {
    "symbol": "NVDA",
    "description": "NVIDIA CORP",
    "lastPrice": 175.58,
    "netChange": 8.06,
    "netPercentChange": 4.81,
    "volume": 121693985,
  },
  ...
]
```

Results are sorted by `netPercentChange` descending (biggest gainers first), limited to `top_n` entries. Only gainers (positive `netPercentChange`) are included — bearish movers are excluded since agents express bearish conviction via inverse ETFs, not by chasing falling stocks.

Error handling: any exception returns `[]` silently.

---

### 2. `MarketFeed` — include movers in data packet

`fetch_and_dispatch()` calls `get_movers()` on the `SchwabClient` instance each cycle and adds the result to the packet:

```python
packet = {
    "session": session,
    "movers": movers,          # NEW — top gainers from Schwab
    "signals": ranked[:10],
    "news": [...],
    "institutional": inst_signals[:10],
}
```

`MarketFeed.__init__` accepts a `schwab_client` parameter (currently it has no broker reference). `main.py` passes the existing `SchwabClient` instance in.

Error handling: if `get_movers()` raises, `movers` defaults to `[]` and the cycle continues normally.

---

### 3. `prompt_builder.py` — movers section + updated Task instructions

`build_decision_prompt()` accepts a new `movers: list[dict]` parameter.

A new `## Top Market Movers` section is inserted above `## Live Signals`:

```
## Top Market Movers (S&P 500 — sorted by % gain)
  - NVDA  +4.81%  $175.58  vol 121.7M
  - INTC  +11.1%  $47.93   vol 104.0M
  ...
```

The Task section is updated to:

> Start by reviewing the top market movers. These are stocks the market has already validated with real volume and price action today. Cross-reference with the breakout signals and news below. Only enter a position when you see alignment — a mover that also has technical confirmation and/or news support. **Patience is a valid strategy.** If nothing meets that bar, hold. A missed opportunity is better than a bad trade.

---

## Data Flow

```
Schwab API
    └── SchwabClient.get_movers()
            └── MarketFeed.fetch_and_dispatch()  [each cycle]
                    └── packet["movers"]
                            └── build_decision_prompt(movers=...)
                                    └── Claude decision
```

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| `get_movers()` API error | Returns `[]`; agents fall back to existing signals |
| Session is `closed` | `fetch_and_dispatch()` returns early; movers never fetched |
| No gainers in movers list | `movers=[]`; prompt shows "(none)"; agents rely on signals |
| Mover not in watchlist | Claude still sees it in movers; can decide to buy based on price/volume alone |

---

## What Is Not Changing

- Static watchlist remains — technical analysis still runs on it each cycle
- Agent decision loop (`run_cycle`) is unchanged
- Risk gate is unchanged
- No new files created
