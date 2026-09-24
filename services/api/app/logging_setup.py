"""Process-wide logging: one stdout handler, JSON lines in production.

Railway labels anything written to stderr as an error, and both the stdlib default
(logging.basicConfig) and uvicorn's own handler write there. Every INFO line the API
emitted therefore showed up as an error, which made real errors unfindable and ruled
out alerting on severity.

Everything now goes to stdout. In JSON mode each record is one line that Railway
parses as a structured log (docs.railway.com/observability/logs#structured-logs):
`level` sets the severity, `message` is the text, and every other field becomes a
filterable attribute, e.g. @logger:app.rag.pipeline.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Literal, TextIO

LogFormat = Literal["auto", "json", "text"]

# Attributes every LogRecord carries. Anything else was passed through `extra=`
# and is emitted as its own field. uvicorn's `color_message` duplicates the message
# with ANSI escapes for its own terminal formatter.
_RECORD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()
) | {"message", "asctime", "taskName", "color_message"}

TEXT_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

# uvicorn installs its own handlers (stderr for server messages) before it imports
# the app. Those it gave a handler are re-pointed at the root handler instead; one it
# silenced (no handler, no propagation, as --no-access-log leaves uvicorn.access)
# stays silent.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def railway_level(levelno: int) -> str:
    """Map a stdlib level to Railway's severities: debug, info, warn, error."""
    if levelno >= logging.ERROR:
        return "error"
    if levelno >= logging.WARNING:
        return "warn"
    if levelno >= logging.INFO:
        return "info"
    return "debug"


class JsonFormatter(logging.Formatter):
    """Render a record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "level": railway_level(record.levelno),
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds"),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        for key, value in vars(record).items():
            if key not in _RECORD_ATTRS and key not in entry:
                entry[str(key)] = value
        # json.dumps escapes newlines, so tracebacks stay on one line, and non-ASCII
        # (a lone surrogate included), so the line is always valid UTF-8. default=str
        # keeps an unserialisable `extra` value from dropping the whole record; a
        # value json cannot encode even so (a dict with non-string keys) is repr'd.
        try:
            return json.dumps(entry, default=str)
        except (TypeError, ValueError):
            safe = {key: value if isinstance(value, (str, int, float, bool, type(None)))
                    else repr(value) for key, value in entry.items()}
            return json.dumps(safe)


def _resolve_format(log_format: LogFormat, stream: TextIO) -> Literal["json", "text"]:
    if log_format != "auto":
        return log_format
    # A terminal gets readable lines; a pipe (Railway, docker logs) gets JSON.
    isatty = getattr(stream, "isatty", None)
    return "text" if callable(isatty) and isatty() else "json"


def configure_logging(
    log_format: LogFormat = "auto",
    level: int = logging.INFO,
    stream: TextIO | None = None,
) -> None:
    """Send every log record, uvicorn's and Python warnings included, to one handler.

    Safe to call more than once: it replaces the root handlers rather than adding.
    """
    stream = stream or sys.stdout
    handler = logging.StreamHandler(stream)
    if _resolve_format(log_format, stream) == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT))

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        if uvicorn_logger.handlers:
            uvicorn_logger.handlers.clear()
            uvicorn_logger.propagate = True

    # `warnings.warn` (e.g. qdrant-client's compatibility check) otherwise prints
    # straight to stderr; route it through the "py.warnings" logger instead. This
    # replaces warnings.showwarning process-wide, so tests that call this restore it.
    logging.captureWarnings(True)
