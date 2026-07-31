"""Fail-fast on unrecoverable API errors.

Skipping a query and continuing is right for a transient blip. It is wrong for a
dead credential: the suite pays Cohere and OpenAI in full for every subsequent
query, producing results the judge can never score. This happened live — the
Anthropic balance hit zero mid-run and the suite carried on to the next queries.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "run_eval_suite", Path(__file__).resolve().parents[1] / "scripts" / "run_eval_suite.py"
)
suite = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(suite)


@pytest.mark.parametrize("msg", [
    "Judge call failed: Error code: 400 - {'message': 'Your credit balance is too low'}",
    "Error code: 401 - {'type': 'authentication_error'}",
    "Error code: 401 - invalid x-api-key",
    "Error code: 403 - {'type': 'permission_error'}",
])
def test_fatal_errors_abort_the_suite(msg):
    with pytest.raises(SystemExit) as e:
        suite._abort_if_fatal(msg, "q3")
    assert "q3" in str(e.value)


@pytest.mark.parametrize("msg", [
    "Error code: 429 - rate_limit_error",
    "Connection error: temporary failure in name resolution",
    "Request timed out after 300s",
    "",
])
def test_transient_errors_do_not_abort(msg):
    suite._abort_if_fatal(msg, "q3")  # must not raise — these deserve a retry


def test_fatal_match_is_case_insensitive():
    with pytest.raises(SystemExit):
        suite._abort_if_fatal("YOUR CREDIT BALANCE IS TOO LOW", "preflight")


def test_none_message_is_survivable():
    suite._abort_if_fatal(None, "q0")
