"""API key assignment and per-key semaphore management for HyDE generation.

Key A: Bible (dedicated, semaphore=4 for 2-wave 8-call HyDE)
Key B: round-robin non-Bible
Key C: round-robin non-Bible
Key D: round-robin non-Bible

Falls back to ANTHROPIC_API_KEY for any key not configured via env var.
"""
from __future__ import annotations

import asyncio
import itertools
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_BIBLE_COLLECTION = "bible"
_NON_BIBLE_KEYS = ["B", "C", "D"]

_clients: dict[str, anthropic.AsyncAnthropic] = {}
_semaphores: dict[str, asyncio.Semaphore] = {}
_key_cycle = itertools.cycle(_NON_BIBLE_KEYS)


def init_api_keys() -> None:
    """Build one Anthropic client and one semaphore per key letter. Call once at startup."""
    global _key_cycle
    _key_cycle = itertools.cycle(_NON_BIBLE_KEYS)  # reset on re-init

    key_values = {
        "A": settings.anthropic_api_key,
        "B": settings.anthropic_api_key_b or settings.anthropic_api_key,
        "C": settings.anthropic_api_key_c or settings.anthropic_api_key,
        "D": settings.anthropic_api_key_d or settings.anthropic_api_key,
    }
    semaphore_sizes = {"A": 4, "B": 3, "C": 3, "D": 3}

    _clients.clear()
    _semaphores.clear()
    for letter, api_key in key_values.items():
        _clients[letter] = anthropic.AsyncAnthropic(api_key=api_key)
        _semaphores[letter] = asyncio.Semaphore(semaphore_sizes[letter])

    logger.info(
        "api_keys: A=...%s B=...%s C=...%s D=...%s",
        key_values["A"][-4:], key_values["B"][-4:],
        key_values["C"][-4:], key_values["D"][-4:],
    )


async def close_api_keys() -> None:
    """Close all Anthropic clients. Call at shutdown."""
    for client in _clients.values():
        await client.close()
    _clients.clear()
    _semaphores.clear()


def get_key_for(collection: str) -> str:
    """Return the key letter for this collection. Bible always gets 'A'."""
    if collection == _BIBLE_COLLECTION:
        return "A"
    return next(_key_cycle)


def get_client(key: str) -> anthropic.AsyncAnthropic:
    return _clients.get(key, _clients["A"])


def get_semaphore(key: str) -> asyncio.Semaphore:
    return _semaphores.get(key, _semaphores["A"])
