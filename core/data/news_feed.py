import requests
from config import settings


class NewsFeed:
    _BASE = "https://newsapi.org/v2/everything"

    def fetch(self, query: str, page_size: int = 10) -> list[dict]:
        resp = requests.get(self._BASE, params={
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": settings.NEWS_API_KEY(),
        }, timeout=10)
        resp.raise_for_status()
        return resp.json().get("articles", [])
