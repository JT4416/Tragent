import pytest
from pathlib import Path
import tempfile, os

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-schwab-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-schwab-secret")
    monkeypatch.setenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-av-key")
    monkeypatch.setenv("NEWS_API_KEY", "test-news-key")
    monkeypatch.setenv("QUIVER_QUANT_API_KEY", "test-quiver-key")
