from unittest.mock import patch, MagicMock
from core.data.news_feed import NewsFeed
from core.data.institutional_feed import InstitutionalFeed


def test_news_feed_returns_list(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"articles": [
        {"title": "Apple surges on earnings", "source": {"name": "Reuters"},
         "publishedAt": "2026-03-21T10:00:00Z", "url": "http://example.com"}
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("core.data.news_feed.requests.get", return_value=mock_resp):
        feed = NewsFeed()
        articles = feed.fetch(query="AAPL earnings")
        assert len(articles) == 1
        assert articles[0]["title"] == "Apple surges on earnings"


def test_institutional_feed_returns_list(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"Ticker": "AAPL", "transaction_type": "Buy",
         "insider": "CEO", "date": "2026-03-20"}
    ]
    mock_resp.raise_for_status = MagicMock()
    with patch("core.data.institutional_feed.requests.get", return_value=mock_resp):
        feed = InstitutionalFeed()
        signals = feed.fetch_insider_trades("AAPL")
        assert len(signals) == 1
        assert signals[0]["Ticker"] == "AAPL"
