from unittest.mock import MagicMock, patch


def _make_client(mock_inner):
    """Build a SchwabClient with a mocked inner schwab client."""
    with patch("core.data.schwab_client.auth") as mock_auth:
        mock_auth.client_from_token_file.return_value = mock_inner
        with patch("core.data.schwab_client._TOKEN_PATH") as mock_path:
            mock_path.exists.return_value = True
            from core.data.schwab_client import SchwabClient
            return SchwabClient()


def test_get_quotes_bulk_returns_dict():
    mock_inner = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "AAPL": {"quote": {"lastPrice": 172.5, "totalVolume": 45000000,
                           "bidPrice": 172.48, "askPrice": 172.52,
                           "netPercentChangeInDouble": 1.2}},
        "MSFT": {"quote": {"lastPrice": 415.0, "totalVolume": 20000000,
                           "bidPrice": 414.9, "askPrice": 415.1,
                           "netPercentChangeInDouble": 0.8}},
    }
    mock_resp.raise_for_status = MagicMock()
    mock_inner.get_quotes.return_value = mock_resp

    sc = _make_client(mock_inner)
    result = sc.get_quotes_bulk(["AAPL", "MSFT"])

    mock_inner.get_quotes.assert_called_once_with(["AAPL", "MSFT"])
    assert result == mock_resp.json.return_value


def test_get_instrument_fundamental_returns_dict():
    mock_inner = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "AAPL": {
            "fundamental": {
                "peRatio": 28.1, "eps": 6.12, "marketCap": 2.8e12,
                "high52": 198.2, "low52": 164.1, "dividendYield": 0.52,
            }
        }
    }
    mock_resp.raise_for_status = MagicMock()
    mock_inner.get_instruments.return_value = mock_resp

    sc = _make_client(mock_inner)
    result = sc.get_instrument_fundamental("AAPL")

    mock_inner.get_instruments.assert_called_once_with(
        "AAPL", projection="fundamental")
    assert result == mock_resp.json.return_value
