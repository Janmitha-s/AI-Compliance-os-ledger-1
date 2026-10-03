"""
Every tool call and every agent decision gets one of these. Without this,
"why did the system say X" is unanswerable six months later — which is
exactly when a CS/CA or an auditor will ask.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass
class AuditEvent:
    ts: str
    actor: str
    action: str
    inputs_hash: str
    outputs_hash: str
    detail: dict = field(default_factory=dict)


class AuditLog:
    def __init__(self):
        self._events: list[AuditEvent] = []

    def record(self, actor: str, action: str, inputs: Any, outputs: Any, detail: dict | None = None) -> AuditEvent:
        ev = AuditEvent(
            ts=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            action=action,
            inputs_hash=_hash(inputs),
            outputs_hash=_hash(outputs),
            detail=detail or {},
        )
        self._events.append(ev)
        return ev

    def events(self) -> list[AuditEvent]:
        return list(self._events)

    def for_actor(self, actor: str) -> list[AuditEvent]:
        return [e for e in self._events if e.actor == actor]