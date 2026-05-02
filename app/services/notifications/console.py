import logging

from app.services.notifications.base import Notification, Severity


logger = logging.getLogger("polaris.notifications")


class ConsoleNotifier:
    """Logs notifications to stdout. Default fallback so every deploy has
    at least a paper trail even without Slack configured."""

    _LEVEL = {
        Severity.INFO: logging.INFO,
        Severity.WARNING: logging.WARNING,
        Severity.CRITICAL: logging.CRITICAL,
    }

    async def notify(self, n: Notification) -> None:
        logger.log(
            self._LEVEL.get(n.severity, logging.INFO),
            "[%s] %s — %s%s",
            n.severity.value.upper(),
            n.title,
            n.message,
            f"  (entity={n.entity})" if n.entity else "",
        )
