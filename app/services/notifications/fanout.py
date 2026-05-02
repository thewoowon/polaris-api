import asyncio
import logging

from app.services.notifications.base import Notification, Notifier


logger = logging.getLogger("polaris.notifications")


class FanoutNotifier:
    """Dispatch the same Notification to multiple backends concurrently.

    If one backend raises, other backends still fire — the exception is
    logged, not re-raised. Use this from the registry so callers always
    get a single Notifier object.
    """

    def __init__(self, backends: list[Notifier]):
        self.backends = backends

    async def notify(self, n: Notification) -> None:
        if not self.backends:
            return
        results = await asyncio.gather(
            *(b.notify(n) for b in self.backends),
            return_exceptions=True,
        )
        for backend, res in zip(self.backends, results):
            if isinstance(res, Exception):
                logger.warning(
                    "notifier %s failed: %s", type(backend).__name__, res
                )
