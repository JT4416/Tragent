"""
Shadow Portfolio Monitor — tracks a fixed watchlist of 100 shares each.
Logs prices every cycle and maintains a running total portfolio value.

Usage:
    python shadow_portfolio.py              # one-shot snapshot
    python shadow_portfolio.py --daemon     # run continuously (every 5 min during market hours)
    python shadow_portfolio.py --report     # print latest report from saved state
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.data.schwab_client import SchwabClient

_ET = ZoneInfo("America/New_York")
STATE_FILE = Path("state/shadow_portfolio.json")
SHARES_PER_POSITION = 100

WATCHLIST = [
    "OWL", "CRWV", "BWXT", "ON", "TER", "LRCX", "MPWR", "KLAC",
    "PWR", "EXLS", "NRG", "ALAB", "CRSP", "KEYS", "PLTR", "WMB",
    "FSLY", "PRCT", "DMLP", "NN", "PHR", "NIQ", "ARM", "NET",
    "ASML", "SYM", "SNOW", "PATH", "TT", "GKOS", "LTH", "MRVL",
    "RXRX",
]


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _get_session() -> str:
    et = datetime.now(_ET)
    hour = et.hour + et.minute / 60
    if 4.0 <= hour < 9.5:
        return "pre_market"
    if 9.5 <= hour < 16.0:
        return "regular"
    if 16.0 <= hour < 20.0:
        return "post_market"
    return "closed"


def fetch_prices(schwab: SchwabClient) -> dict[str, dict]:
    """Fetch live quotes for all shadow portfolio tickers."""
    raw = schwab.get_quotes_bulk(WATCHLIST)
    prices = {}
    for symbol in WATCHLIST:
        q = raw.get(symbol, {}).get("quote", {})
        if q:
            prices[symbol] = {
                "last": q.get("lastPrice", 0.0),
                "net_pct": round(q.get("netPercentChangeInDouble", 0.0), 2),
                "volume": q.get("totalVolume", 0),
                "bid": q.get("bidPrice", 0.0),
                "ask": q.get("askPrice", 0.0),
            }
    return prices


def snapshot(schwab: SchwabClient) -> dict:
    """Take a snapshot of the shadow portfolio and update state."""
    state = _load_state()
    now = datetime.now(_ET)
    prices = fetch_prices(schwab)

    # Record baseline prices on first run
    if "baseline" not in state:
        state["baseline"] = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M ET"),
            "prices": {s: p["last"] for s, p in prices.items()},
        }

    # Current snapshot
    positions = {}
    total_value = 0.0
    baseline_total = 0.0
    for symbol in WATCHLIST:
        p = prices.get(symbol)
        if not p or not p["last"]:
            continue
        current_price = p["last"]
        position_value = current_price * SHARES_PER_POSITION
        baseline_price = state["baseline"]["prices"].get(symbol, current_price)
        baseline_value = baseline_price * SHARES_PER_POSITION
        change_pct = ((current_price - baseline_price) / baseline_price * 100
                      if baseline_price else 0.0)
        positions[symbol] = {
            "current_price": current_price,
            "baseline_price": baseline_price,
            "position_value": round(position_value, 2),
            "baseline_value": round(baseline_value, 2),
            "change_pct": round(change_pct, 2),
            "day_pct": p["net_pct"],
            "volume": p["volume"],
        }
        total_value += position_value
        baseline_total += baseline_value

    total_change_pct = ((total_value - baseline_total) / baseline_total * 100
                        if baseline_total else 0.0)

    state["latest"] = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M ET"),
        "session": _get_session(),
        "positions": positions,
        "total_value": round(total_value, 2),
        "baseline_total": round(baseline_total, 2),
        "total_change_pct": round(total_change_pct, 2),
        "total_change_dollar": round(total_value - baseline_total, 2),
    }

    # Append to daily history
    history_key = now.strftime("%Y-%m-%d")
    if "history" not in state:
        state["history"] = {}
    if history_key not in state["history"]:
        state["history"][history_key] = []
    state["history"][history_key].append({
        "time": now.strftime("%H:%M"),
        "total_value": round(total_value, 2),
        "total_change_pct": round(total_change_pct, 2),
    })

    _save_state(state)
    return state["latest"]


def print_report(data: dict | None = None) -> None:
    """Pretty-print the shadow portfolio."""
    if data is None:
        state = _load_state()
        data = state.get("latest")
        if not data:
            print("No data yet — run a snapshot first.")
            return

    print(f"\n{'='*75}")
    print(f"  SHADOW PORTFOLIO — {data['date']} {data['time']} ({data['session']})")
    print(f"  {SHARES_PER_POSITION} shares each | {len(WATCHLIST)} positions")
    print(f"{'='*75}")
    print(f"  {'SYMBOL':<8} {'PRICE':>8} {'BASE':>8} {'VALUE':>12} "
          f"{'CHG%':>8} {'TODAY%':>8} {'VOLUME':>12}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*12} {'-'*8} {'-'*8} {'-'*12}")

    positions = data.get("positions", {})
    # Sort by change% descending
    sorted_pos = sorted(positions.items(),
                        key=lambda x: x[1].get("change_pct", 0), reverse=True)
    for symbol, p in sorted_pos:
        chg = p["change_pct"]
        day = p["day_pct"]
        chg_str = f"{chg:+.2f}%"
        day_str = f"{day:+.2f}%"
        print(f"  {symbol:<8} ${p['current_price']:>7.2f} ${p['baseline_price']:>7.2f} "
              f"${p['position_value']:>10,.2f} {chg_str:>8} {day_str:>8} "
              f"{p['volume']:>12,}")

    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*12} {'-'*8}")
    chg_total = data["total_change_pct"]
    print(f"  {'TOTAL':<8} {'':>8} {'':>8} "
          f"${data['total_value']:>10,.2f} {chg_total:+.2f}%")
    print(f"  Baseline: ${data['baseline_total']:>10,.2f}  |  "
          f"Change: ${data['total_change_dollar']:>+10,.2f}")
    print(f"{'='*75}\n")


def daemon(schwab: SchwabClient) -> None:
    """Run continuously — snapshot every 5 minutes during market hours."""
    print("Shadow Portfolio Monitor — daemon mode (Ctrl+C to stop)")
    while True:
        session = _get_session()
        if session in ("regular", "pre_market", "post_market"):
            try:
                data = snapshot(schwab)
                print_report(data)
            except Exception as e:
                print(f"  [ERROR] {e}")
        else:
            print(f"  Market closed — sleeping until next session...")
        time.sleep(5 * 60)  # 5 minute intervals


if __name__ == "__main__":
    schwab = SchwabClient()

    if "--daemon" in sys.argv:
        daemon(schwab)
    elif "--report" in sys.argv:
        print_report()
    else:
        data = snapshot(schwab)
        print_report(data)
