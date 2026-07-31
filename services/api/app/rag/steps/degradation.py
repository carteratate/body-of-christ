"""Structured, per-request accounting for graceful pipeline degradation.

Production remains available when a redundant path fails, while evaluation can
quarantine the same result from quality aggregates.  A ContextVar keeps events scoped
to one pipeline run even when collection work fans out into concurrent tasks.
"""
from __future__ import annotations

import contextvars
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class DegradationPolicy(StrEnum):
    """How a caller wants recorded degradation to affect execution."""

    ALLOW = "allow"
    QUARANTINE = "quarantine"
    RAISE = "raise"


@dataclass(frozen=True)
class DegradationEvent:
    stage: str
    reason: str
    action: str
    scope: str | None = None
    details: dict[str, Any] | None = None

    @property
    def legacy_label(self) -> str:
        """Compact label retained for existing logs and stored eval artifacts."""
        target = f":{self.scope}" if self.scope else ""
        return f"{self.stage}{target}:{self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_events: contextvars.ContextVar[list[DegradationEvent] | None] = contextvars.ContextVar(
    "pipeline_degradation_events", default=None,
)
_recoveries: contextvars.ContextVar[list[DegradationEvent] | None] = contextvars.ContextVar(
    "pipeline_recovery_events", default=None,
)
_policy: contextvars.ContextVar[DegradationPolicy] = contextvars.ContextVar(
    "pipeline_degradation_policy", default=DegradationPolicy.ALLOW,
)


def begin_degradation_accounting(
    policy: DegradationPolicy = DegradationPolicy.ALLOW,
) -> list[DegradationEvent]:
    """Start a fresh accumulator for this pipeline run."""
    box: list[DegradationEvent] = []
    _events.set(box)
    _recoveries.set([])
    _policy.set(policy)
    return box


def record(
    stage: str,
    reason: str | None = None,
    action: str = "fallback",
    *,
    scope: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record a degradation.

    ``record("cohere:summa")`` remains supported while call sites migrate to the
    structured form.
    """
    if reason is None:
        parts = stage.split(":")
        stage = parts[0]
        if len(parts) > 2:
            scope = ":".join(parts[1:-1])
            reason = parts[-1]
        elif len(parts) == 2:
            reason = parts[1]
        else:
            reason = "degraded"
    event = DegradationEvent(
        stage=stage,
        scope=scope,
        reason=reason,
        action=action,
        details=details,
    )
    box = _events.get()
    if box is not None:
        box.append(event)
    if _policy.get() == DegradationPolicy.RAISE:
        # The first degradation terminates a fail-fast run. Reset before raising so
        # the ContextVar cannot leak RAISE into later work executed by the same task
        # (notably async test runners).
        _policy.set(DegradationPolicy.ALLOW)
        raise RuntimeError(f"pipeline degraded: {event.legacy_label}")


def events() -> list[DegradationEvent]:
    return list(_events.get() or [])


def record_recovery(
    stage: str,
    reason: str,
    action: str,
    *,
    scope: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record a transient defect that the pipeline is actively recovering from.

    Recovery events do not make a result ineligible when the repair succeeds. They
    exist so production telemetry can distinguish a genuinely clean request from a
    request that needed an extra provider call and was therefore slower and closer
    to degrading.
    """
    event = DegradationEvent(
        stage=stage,
        scope=scope,
        reason=reason,
        action=action,
        details=details,
    )
    box = _recoveries.get()
    if box is not None:
        box.append(event)


def recovery_events() -> list[DegradationEvent]:
    return list(_recoveries.get() or [])


def recovery_event_dicts() -> list[dict[str, Any]]:
    return [event.to_dict() for event in recovery_events()]


def event_dicts() -> list[dict[str, Any]]:
    return [event.to_dict() for event in events()]


def degradations() -> list[str]:
    """Compatibility view for existing logs and consumers."""
    return [event.legacy_label for event in events()]
