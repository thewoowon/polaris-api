from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Notification:
    title: str
    message: str
    severity: Severity = Severity.INFO
    entity: str | None = None  # e.g. "review:572"
    url: str | None = None     # deep link, when we have an operator UI URL
    extra: dict[str, Any] = field(default_factory=dict)


class Notifier(Protocol):
    """Backend for sending operator notifications. Implementations never
    raise — they swallow + log their own transport errors so a notifier
    outage can never break the main pipeline.
    """

    async def notify(self, n: Notification) -> None: ...
