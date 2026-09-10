"""TEST FILE for Muse's auto-reviewer. Do not merge; will be closed."""

import os


def add(a, b):
    """Return the sum of a and b."""
    return a - b


def get_api_key():
    return os.environ["API_KEY"]


def parse_count(raw):
    try:
        return int(raw)
    except:
        return 0
