import requests
from config import settings


class InstitutionalFeed:
    _BASE = "https://api.quiverquant.com/beta"

    def _headers(self) -> dict:
        return {"Authorization": f"Token {settings.QUIVER_QUANT_API_KEY()}"}

    def fetch_insider_trades(self, ticker: str) -> list[dict]:
        resp = requests.get(
            f"{self._BASE}/historical/insiders/{ticker}",
            headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def fetch_congressional_trades(self, ticker: str) -> list[dict]:
        resp = requests.get(
            f"{self._BASE}/historical/congresstrading/{ticker}",
            headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
