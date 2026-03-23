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
        elif action in ("sell", "cover"):
            order = equity_sell_market(symbol, quantity)
        elif action == "short":
            from schwab.orders.equities import equity_sell_short_market
            order = equity_sell_short_market(symbol, quantity)
        else:
            raise ValueError(f"Unsupported action: {action}")

        resp = self._client.place_order(account_hash, order)
        resp.raise_for_status()
        return {"status": "placed", "symbol": symbol,
                "action": action, "quantity": quantity}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        app_key = settings.SCHWAB_APP_KEY()
        app_secret = settings.SCHWAB_APP_SECRET()
        callback_url = settings.SCHWAB_CALLBACK_URL()
        c = auth.client_from_manual_flow(
            app_key, app_secret, callback_url, str(_TOKEN_PATH))
        print("Authentication successful. Tokens saved.")
