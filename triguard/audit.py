"""Append-only, privacy-conscious local audit logging."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


_write_lock = Lock()


class AuditLogger:
    """Writes one JSON event per line so logs can be shipped or queried easily."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, event: dict[str, Any]) -> None:
        safe_event = {
            "recorded_at": datetime.now(UTC).isoformat(),
            **event,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe_event, default=str, separators=(",", ":")) + "\n")
