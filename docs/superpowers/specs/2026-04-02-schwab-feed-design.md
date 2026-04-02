# SchwabFeed Design

**Date:** 2026-04-02
**Status:** Approved

## Summary

Enrich the MarketFeed packet with live Schwab quotes (bulk, every cycle) and
fundamental data (PE, EPS, market cap, 52-week range, dividend yield) cached
twice per trading day. No browser scraping. No new authentication. Existing
NewsFeed continues unchanged.

## Architecture

### SchwabClient additions (`core/data/schwab_client.py`)

Two thin wrapper methods — no caching logic, no business logic:

- `get_quotes_bulk(symbols: list[str]) -> dict` — calls `client.get_quotes(symbols)`, one API call for the full watchlist
- `get_instrument_fundamental(symbol: str) -> dict` — calls `client.get_instruments(symbol, projection="fundamental")`

### New file: `core/data/schwab_feed.py`

`SchwabFeed` class owns all caching and merging:

```
SchwabFeed
  __init__(schwab: SchwabClient, watchlist: list[str])
  fetch() -> dict[str, dict]   # per-symbol merged data
  _current_slot() -> str       # "open" | "midday" | None
  _refresh_fundamentals()      # calls get_instrument_fundamental per symbol
```

Internal state:
- `_fundamentals: dict[str, dict]` — cached per-symbol fundamental data
- `_fund_slot: str | None` — which half-day slot was last refreshed

### MarketFeed integration (`core/data/market_feed.py`)

- `MarketFeed.__init__` gains optional `schwab_feed: SchwabFeed | None = None`
- `fetch_and_dispatch()` calls `schwab_feed.fetch()` if present and adds
  `"schwab_data"` key to the packet — no existing keys modified

### main.py

Construct `SchwabFeed(schwab, DEFAULT_WATCHLIST)`, pass to `MarketFeed`.

## Data Shape

`"schwab_data"` added to each MarketFeed packet:

```python
"schwab_data": {
    "AAPL": {
        # Live — refreshed every cycle via get_quotes_bulk
        "last":     172.50,
        "volume":   45_000_000,
        "bid":      172.48,
        "ask":      172.52,
        "net_pct":  1.2,        # % change from prior close

        # Cached — refreshed at open + midday via get_instrument_fundamental
        "pe":         28.1,
        "eps":         6.12,
        "market_cap":  2.8e12,
        "52wk_high":  198.2,
        "52wk_low":   164.1,
        "div_yield":   0.52,
    },
    ...
}
```

## Refresh Logic

Two half-day slots (ET):
- `"open"` — 9:30 AM to 12:00 PM
- `"midday"` — 12:00 PM to 4:00 PM

On each `fetch()` call, `SchwabFeed._current_slot()` computes the current slot.
If it differs from `_fund_slot` (including `None` on first call), all symbols
are re-fetched via `get_instrument_fundamental()` sequentially. `_fund_slot` is
updated after a successful refresh.

Outside regular hours: `MarketFeed` already skips `"closed"` sessions, so no
fundamental refresh occurs outside trading hours.

## Error Handling

| Failure | Behavior |
|---------|----------|
| `get_quotes_bulk` fails entirely | Log warning; `"schwab_data"` key omitted from packet; no crash |
| Individual symbol quote fails | Symbol omitted from `"schwab_data"`; others unaffected |
| `get_instrument_fundamental` fails for a symbol | Symbol's fundamental fields omitted from cache; live quote still included |
| All fundamentals fail | `_fund_slot` not updated; retry on next cycle |

Pattern matches existing `NewsFeed` / `InstitutionalFeed` error handling in MarketFeed.

## Testing

- Unit test `SchwabFeed` with mocked `SchwabClient`
  - Slot transition triggers re-fetch
  - Same-slot call does not re-fetch
  - Failed symbol is skipped; others succeed
  - First call (`_fund_slot = None`) always fetches
- No integration tests (Schwab OAuth makes local integration testing impractical)

## Out of Scope

- Analyst price targets (not available via Schwab API)
- News (existing `NewsFeed` covers this)
- Options chain data
- agent-browser / Yahoo Finance scraping
