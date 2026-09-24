import io
import json
import logging
import sys
import warnings

import pytest

from app.logging_setup import JsonFormatter, configure_logging, railway_level


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _restore_logging():
    """configure_logging rewires process-wide loggers; put them back afterwards.

    Restores the state found rather than a default: importing app.main elsewhere in
    the suite has already configured logging, warning capture included.
    """
    # logging keeps its own record of whether it captured warnings, so restore
    # through captureWarnings rather than by reassigning warnings.showwarning.
    was_capturing_warnings = warnings.showwarning is logging._showwarning
    root = logging.getLogger()
    saved_root = (root.handlers[:], root.level)
    saved_uvicorn = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    }
    yield
    logging.captureWarnings(was_capturing_warnings)
    root.handlers[:], root.level = saved_root[0], saved_root[1]
    for name, (handlers, propagate) in saved_uvicorn.items():
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate


def _record(level=logging.INFO, msg="hello %s", args=("world",), exc_info=None, **extra):
    record = logging.LogRecord("app.test", level, __file__, 1, msg, args, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (logging.DEBUG, "debug"),
        (logging.INFO, "info"),
        (logging.WARNING, "warn"),
        (logging.ERROR, "error"),
        (logging.CRITICAL, "error"),
        (logging.INFO + 5, "info"),
    ],
)
def test_levels_map_to_railway_severities(level, expected):
    assert railway_level(level) == expected


def test_json_line_carries_level_message_and_logger():
    line = JsonFormatter().format(_record(logging.WARNING))

    entry = json.loads(line)
    assert entry["level"] == "warn"
    assert entry["message"] == "hello world"
    assert entry["logger"] == "app.test"
    assert entry["timestamp"].endswith("+00:00")


def test_a_traceback_stays_on_one_line():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record(logging.ERROR, "failed", (), exc_info=sys.exc_info())

    line = JsonFormatter().format(record)

    assert "\n" not in line
    entry = json.loads(line)
    assert entry["level"] == "error"
    assert "ValueError: boom" in entry["exception"]


def test_extra_fields_become_attributes_and_unserialisable_values_survive():
    line = JsonFormatter().format(_record(collection="bible", payload=object()))

    entry = json.loads(line)
    assert entry["collection"] == "bible"
    assert entry["payload"].startswith("<object object")
    # Standard record attributes are not repeated as fields.
    assert "levelno" not in entry and "args" not in entry


def test_configure_logging_writes_json_to_the_stream():
    stream = io.StringIO()
    configure_logging("auto", stream=stream)

    logging.getLogger("app.rag.pipeline").info("pipeline timing: runner=%.2fs", 1.5)

    entry = json.loads(stream.getvalue())
    assert entry == {**entry, "level": "info", "message": "pipeline timing: runner=1.50s",
                     "logger": "app.rag.pipeline"}


def test_a_terminal_gets_text_unless_json_is_forced():
    tty = _Tty()
    configure_logging("auto", stream=tty)
    logging.getLogger("app.x").info("readable")
    assert tty.getvalue().rstrip().endswith("app.x INFO readable")

    forced = _Tty()
    configure_logging("json", stream=forced)
    logging.getLogger("app.x").info("structured")
    assert json.loads(forced.getvalue())["message"] == "structured"


@pytest.mark.parametrize("name", ["uvicorn.error", "uvicorn.access"])
def test_uvicorn_records_reach_the_same_handler(name):
    # As uvicorn's LOGGING_CONFIG leaves them: "uvicorn" and "uvicorn.access" each get
    # a stream handler and propagate=False; "uvicorn.error" has none and propagates
    # to "uvicorn".
    stream = io.StringIO()
    stale = logging.StreamHandler(io.StringIO())
    for configured in ("uvicorn", "uvicorn.access"):
        logging.getLogger(configured).handlers[:] = [stale]
        logging.getLogger(configured).propagate = False
    logging.getLogger("uvicorn.error").handlers.clear()
    logging.getLogger("uvicorn.error").propagate = True

    configure_logging("json", stream=stream)
    logging.getLogger(name).info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1", "GET", "/health", "1.1", 200)

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["logger"] == name
    assert entry["message"] == '127.0.0.1:1 - "GET /health HTTP/1.1" 200'
    assert stale not in logging.getLogger("uvicorn").handlers
    assert stale not in logging.getLogger("uvicorn.access").handlers


def test_configuring_twice_does_not_duplicate_lines():
    first, second = io.StringIO(), io.StringIO()
    configure_logging("json", stream=first)
    configure_logging("json", stream=second)

    logging.getLogger("app.x").info("once")

    assert first.getvalue() == ""
    assert len(second.getvalue().splitlines()) == 1


def test_python_warnings_are_logged_instead_of_printed_to_stderr():
    stream = io.StringIO()
    configure_logging("json", stream=stream)

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn("Failed to obtain server version", UserWarning)

    entry = json.loads(stream.getvalue())
    assert entry["level"] == "warn"
    assert entry["logger"] == "py.warnings"
    assert "Failed to obtain server version" in entry["message"]


def test_a_logger_uvicorn_silenced_stays_silent():
    """--no-access-log leaves uvicorn.access with no handler and no propagation."""
    stream = io.StringIO()
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False

    configure_logging("json", stream=stream)
    access.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1", "GET", "/health", "1.1", 200)

    assert stream.getvalue() == ""


def test_uvicorns_ansi_duplicate_of_the_message_is_dropped():
    line = JsonFormatter().format(_record(color_message="\x1b[1mhello\x1b[0m"))
    assert "color_message" not in json.loads(line)


def test_an_extra_that_json_cannot_encode_still_logs_one_line():
    line = JsonFormatter().format(_record(lookup={1: "a", (2, 3): "b"}))

    entry = json.loads(line)
    assert entry["message"] == "hello world"
    assert entry["lookup"] == repr({1: "a", (2, 3): "b"})


def test_a_message_that_is_not_valid_unicode_still_encodes():
    line = JsonFormatter().format(_record(msg="caf\u00e9 \udcff", args=()))

    line.encode("utf-8")  # a lone surrogate written raw would raise here
    assert json.loads(line)["message"] == "caf\u00e9 \udcff"
