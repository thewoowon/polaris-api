import logging

import httpx

from app.services.notifications.base import Notification, Severity


logger = logging.getLogger("polaris.notifications")


_COLOR = {
    Severity.INFO: "#3b82f6",
    Severity.WARNING: "#f59e0b",
    Severity.CRITICAL: "#dc2626",
}


class SlackWebhookNotifier:
    """Posts to an incoming-webhook URL. Errors are swallowed so notifier
    outages never block the operational pipeline."""

    def __init__(self, *, webhook_url: str, timeout_sec: float = 5.0):
        self.webhook_url = webhook_url
        self.timeout_sec = timeout_sec

    async def notify(self, n: Notification) -> None:
        if not self.webhook_url:
            return
        payload = {
            "attachments": [
                {
                    "color": _COLOR.get(n.severity, "#999999"),
                    "title": n.title,
                    "title_link": n.url,
                    "text": n.message,
                    "fields": (
                        [{"title": "entity", "value": n.entity, "short": True}]
                        if n.entity
                        else []
                    )
                    + [
                        {"title": k, "value": str(v)[:120], "short": True}
                        for k, v in (n.extra or {}).items()
                    ],
                    "footer": "polaris",
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as http:
                res = await http.post(self.webhook_url, json=payload)
            if res.status_code >= 400:
                logger.warning(
                    "slack webhook %s returned %s: %s",
                    self.webhook_url[:40] + "…",
                    res.status_code,
                    res.text[:200],
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("slack webhook send failed: %s", e)
