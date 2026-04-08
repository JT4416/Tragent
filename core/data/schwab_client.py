"""
Schwab API client using schwab-py.
OAuth tokens are stored in .schwab_tokens.json (gitignored).
Run `python -m core.data.schwab_client auth` to complete initial OAuth.
"""
import json
import sys
from pathlib import Path

try:
    import schwab
    from schwab import auth, client
except ImportError:
    schwab = None

from config import settings

_TOKEN_PATH = Path(__file__).parent.parent.parent / ".schwab_tokens.json"


class SchwabClient:
    def __init__(self):
        if schwab is None:
            raise ImportError("schwab-py not installed")
        self._client = self._load_client()

    def _load_client(self):
        app_key = settings.SCHWAB_APP_KEY()
        app_secret = settings.SCHWAB_APP_SECRET()
        if _TOKEN_PATH.exists():
            return auth.client_from_token_file(
                str(_TOKEN_PATH), app_key, app_secret)
        raise FileNotFoundError(
            f"No token file found at {_TOKEN_PATH}. "
            "Run: python -m core.data.schwab_client auth")

    def get_account_info(self) -> dict:
        resp = self._client.get_accounts(
            fields=[client.Client.Account.Fields.POSITIONS])
        resp.raise_for_status()
        accounts = resp.json()
        if not accounts:
            return {"cash": 0.0, "positions": []}
        acct = accounts[0]["securitiesAccount"]
        cash = acct.get("currentBalances", {}).get("cashBalance", 0.0)
        positions = [
            {"symbol": p["instrument"]["symbol"],
             "quantity": p["longQuantity"] - p["shortQuantity"],
             "market_value": p.get("marketValue", 0)}
            for p in acct.get("positions", [])
        ]
        return {"cash": cash, "positions": positions}

    def get_quote(self, symbol: str) -> dict:
        resp = self._client.get_quote(symbol)
        resp.raise_for_status()
        return resp.json()[symbol]["quote"]

    def place_order(self, symbol: str, action: str, quantity: int) -> dict:
        from schwab.orders.equities import equity_buy_market, equity_sell_market
        account_resp = self._client.get_accounts()
        account_resp.raise_for_status()
        account_hash = account_resp.json()[0]["hashValue"]

        if action == "buy":
            order = equity_buy_market(symbol, quantity)
        elif action == "sell":
            order = equity_sell_market(symbol, quantity)
        else:
            raise ValueError(f"Unsupported action: {action}")

        resp = self._client.place_order(account_hash, order)
        resp.raise_for_status()
        return {"status": "placed", "symbol": symbol,
                "action": action, "quantity": quantity}

    def get_movers(self, index: str = "SPX", top_n: int = 10) -> list[dict]:
        from schwab.client import Client as _C
        _index_map = {
            "SPX": _C.Movers.Index.SPX,
            "COMPX": _C.Movers.Index.COMPX,
            "DJI": _C.Movers.Index.DJI,
        }
        idx = _index_map.get(index, _C.Movers.Index.SPX)
        try:
            resp = self._client.get_movers(idx, sort_order=_C.Movers.SortOrder.PERCENT_CHANGE_UP)
            resp.raise_for_status()
            screeners = resp.json().get("screeners", [])
            gainers = [
                {
                    "symbol": s["symbol"],
                    "description": s.get("description", ""),
                    "lastPrice": s.get("lastPrice", 0.0),
                    "netChange": s.get("netChange", 0.0),
                    "netPercentChange": round(s.get("netPercentChange", 0.0) * 100, 2),
                    "volume": s.get("volume", 0),
                }
                for s in screeners
                if s.get("netChange", 0.0) > 0
            ]
            gainers.sort(key=lambda x: x["netPercentChange"], reverse=True)
            return gainers[:top_n]
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("get_movers failed: %s", e)
            return []

    def scan_market(self, top_n: int = 10) -> dict[str, list[dict]]:
        """Broad market scanner — % gainers and volume leaders across ALL exchanges.

        Returns dict with keys:
          "pct_gainers_all"  — top % gainers across all equities
          "pct_gainers_nasdaq" — top % gainers on Nasdaq
          "pct_gainers_nyse" — top % gainers on NYSE
          "volume_leaders"   — top volume across all equities
          "pct_losers_all"   — top % losers (for flip/short opportunities)
        """
        from schwab.client import Client as _C
        import logging as _logging
        _log = _logging.getLogger(__name__)

        def _fetch(index, sort_order, freq=None):
            try:
                kwargs = {"sort_order": sort_order}
                if freq is not None:
                    kwargs["frequency"] = freq
                resp = self._client.get_movers(index, **kwargs)
                resp.raise_for_status()
                screeners = resp.json().get("screeners", [])
                results = []
                for s in screeners:
                    results.append({
                        "symbol": s["symbol"],
                        "description": s.get("description", ""),
                        "lastPrice": s.get("lastPrice", 0.0),
                        "netChange": s.get("netChange", 0.0),
                        "netPercentChange": round(
                            s.get("netPercentChange", 0.0) * 100, 2),
                        "volume": s.get("volume", 0),
                    })
                return results[:top_n]
            except Exception as e:
                _log.warning("scan_market %s/%s failed: %s",
                             index, sort_order, e)
                return []

        return {
            "pct_gainers_all": _fetch(
                _C.Movers.Index.EQUITY_ALL,
                _C.Movers.SortOrder.PERCENT_CHANGE_UP,
                _C.Movers.Frequency.FIVE,   # only 5%+ movers
            ),
            "pct_gainers_nasdaq": _fetch(
                _C.Movers.Index.NASDAQ,
                _C.Movers.SortOrder.PERCENT_CHANGE_UP,
                _C.Movers.Frequency.FIVE,
            ),
            "pct_gainers_nyse": _fetch(
                _C.Movers.Index.NYSE,
                _C.Movers.SortOrder.PERCENT_CHANGE_UP,
                _C.Movers.Frequency.FIVE,
            ),
            "volume_leaders": _fetch(
                _C.Movers.Index.EQUITY_ALL,
                _C.Movers.SortOrder.VOLUME,
            ),
            "pct_losers_all": _fetch(
                _C.Movers.Index.EQUITY_ALL,
                _C.Movers.SortOrder.PERCENT_CHANGE_DOWN,
                _C.Movers.Frequency.FIVE,
            ),
        }

    def get_quotes_bulk(self, symbols: list[str]) -> dict:
        resp = self._client.get_quotes(symbols)
        resp.raise_for_status()
        return resp.json()

    def get_instrument_fundamental(self, symbol: str) -> dict:
        resp = self._client.get_instruments(
            symbol, projection=client.Client.Instrument.Projection.FUNDAMENTAL)
        resp.raise_for_status()
        data = resp.json()
        # Schwab wraps in {"instruments": [...]}, re-key by symbol for callers
        instruments = data.get("instruments", [])
        return {inst["symbol"]: inst for inst in instruments if "symbol" in inst}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        app_key = settings.SCHWAB_APP_KEY()
        app_secret = settings.SCHWAB_APP_SECRET()
        callback_url = settings.SCHWAB_CALLBACK_URL()
        c = auth.client_from_manual_flow(
            app_key, app_secret, callback_url, str(_TOKEN_PATH))
        print("Authentication successful. Tokens saved.")
