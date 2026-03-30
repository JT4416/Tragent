from unittest.mock import patch, MagicMock
from core.monitor.alerter import Alerter


def _alerter(url="https://hooks.example.com/test"):
    return Alerter(webhook_url=url)


def test_send_posts_json_payload():
    alerter = _alerter()
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        alerter.send("agent_a", "large_drawdown", "Agent A down 4.2%")
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["agent"] == "agent_a"
        assert payload["type"] == "large_drawdown"
        assert "Agent A down 4.2%" in payload["message"]
        assert "timestamp" in payload


def test_send_silently_handles_request_failure():
    alerter = _alerter()
    with patch("requests.post", side_effect=Exception("network down")):
        # Should not raise
        alerter.send("agent_a", "test", "msg")


def test_no_webhook_url_skips_send():
    alerter = Alerter(webhook_url=None)
    with patch("requests.post") as mock_post:
        alerter.send("agent_a", "test", "msg")
        mock_post.assert_not_called()


def test_check_drawdown_fires_alert_when_threshold_exceeded():
    alerter = _alerter()
    with patch.object(alerter, "send") as mock_send:
        alerter.check_drawdown("agent_a", daily_pnl_pct=-4.0,
                                threshold_pct=3.0)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[1] == "large_drawdown"


def test_check_drawdown_does_not_fire_below_threshold():
    alerter = _alerter()
    with patch.object(alerter, "send") as mock_send:
        alerter.check_drawdown("agent_a", daily_pnl_pct=-2.0,
                                threshold_pct=3.0)
        mock_send.assert_not_called()


def test_check_idle_fires_when_no_recent_trade():
    from datetime import datetime, timezone, timedelta
    alerter = _alerter()
    old_time = datetime.now(timezone.utc) - timedelta(hours=3)
    with patch.object(alerter, "send") as mock_send:
        alerter.check_idle("agent_a", last_trade_time=old_time,
                            idle_threshold_minutes=120)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[1] == "agent_idle"


def test_check_idle_does_not_fire_within_threshold():
    from datetime import datetime, timezone, timedelta
    alerter = _alerter()
    recent = datetime.now(timezone.utc) - timedelta(minutes=30)
    with patch.object(alerter, "send") as mock_send:
        alerter.check_idle("agent_a", last_trade_time=recent,
                            idle_threshold_minutes=120)
        mock_send.assert_not_called()


def test_check_api_errors_fires_when_threshold_exceeded():
    alerter = _alerter()
    with patch.object(alerter, "send") as mock_send:
        alerter.check_api_errors("claude", error_count=6, threshold=5)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[1] == "api_errors"
