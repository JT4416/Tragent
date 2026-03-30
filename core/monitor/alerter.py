"""
Webhook-based anomaly alerter.

Sends a POST request to ALERT_WEBHOOK_URL (set in .env) whenever an
anomalous condition is detected. Compatible with Zapier, IFTTT, Make.com,
and any service that accepts a JSON webhook.

Payload schema:
  {"agent": str, "type": str, "message": str, "timestamp": str (ISO-8601)}
"""
import os
from datetime import datetime, timezone, timedelta

try:
    import requests as _requests
except ImportError:
    _requests = None   # graceful degradation if requests unavailable


class Alerter:
    def __init__(self, webhook_url: str | None = None):
        self._url = webhook_url or os.getenv("ALERT_WEBHOOK_URL")

    def send(self, agent: str, alert_type: str, message: str) -> None:
        """POST an alert to the configured webhook. Silently ignores failures."""
        if not self._url or _requests is None:
            return
        payload = {
            "agent": agent,
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _requests.post(self._url, json=payload, timeout=5)
        except Exception:
            pass  # alerting must never crash the trading system

    # ── Named alert checks ─────────────────────────────────────────────────

    def check_drawdown(self, agent: str, daily_pnl_pct: float,
                        threshold_pct: float) -> None:
        """Alert if daily loss exceeds threshold_pct."""
        if daily_pnl_pct <= -threshold_pct:
            self.send(agent, "large_drawdown",
                      f"{agent} daily P&L is {daily_pnl_pct:.1f}% "
                      f"(threshold: -{threshold_pct:.1f}%)")

    def check_idle(self, agent: str, last_trade_time: datetime | None,
                   idle_threshold_minutes: int) -> None:
        """Alert if agent hasn't traded within idle_threshold_minutes."""
        if last_trade_time is None:
            return
        elapsed = (datetime.now(timezone.utc) - last_trade_time).total_seconds()
        if elapsed > idle_threshold_minutes * 60:
            self.send(agent, "agent_idle",
                      f"{agent} has not traded in "
                      f"{int(elapsed // 60)} minutes "
                      f"(threshold: {idle_threshold_minutes} min)")

    def check_api_errors(self, service: str, error_count: int,
                          threshold: int) -> None:
        """Alert if accumulated API errors exceed threshold."""
        if error_count > threshold:
            self.send("system", "api_errors",
                      f"{service} has {error_count} errors "
                      f"(threshold: {threshold})")
