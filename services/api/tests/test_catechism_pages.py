"""Catechism passages link to the flipbook page where their paragraph starts."""
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app import catechism_pages, reader_access
from app.catechism_pages import COVER_URL, FLIPBOOK, _publication, check_publication, page_url

TABLE = json.loads(Path(catechism_pages.__file__).with_name("catechism_pages.json").read_text())
CONTENTS = json.loads(
    Path(catechism_pages.__file__).with_name("catechism_contents.json").read_text())
DOC = "11111111-1111-1111-1111-111111111111"


def test_the_table_places_every_paragraph_in_reading_order():
    pages = TABLE["flipbook_page"]
    assert list(pages) == [str(n) for n in range(1, 2866)]
    values = list(pages.values())
    assert values == sorted(values)
    # The Prologue starts on index 27 and Part Four ends before the indexes at 709.
    assert values[0] == 27 and values[-1] < 709
    assert len(TABLE["guid"]) == 32 and TABLE["numeration_offset"] == 18


def test_each_heading_and_its_first_paragraph_share_a_page_order():
    """The contents tree's headings are in paragraph order, so their pages must be too."""
    def walk(nodes):
        for node in nodes:
            yield node["first"]
            yield from walk(node["children"])

    pages = [TABLE["flipbook_page"][str(first)] for first in walk(CONTENTS)]
    assert pages == sorted(pages)


def test_a_passage_links_to_its_paragraphs_page():
    # §1127 is printed on page 292, flipbook index 312, which the viewer opens as /294/.
    assert page_url("§1127") == f"{FLIPBOOK}/294/index.html"
    assert page_url("§1") == f"{FLIPBOOK}/{TABLE['flipbook_page']['1'] - 18}/index.html"


@pytest.mark.parametrize("label", [None, "", "CCC", "§0", "§2866", "§12a", "Can. 1055 §1"])
def test_a_label_naming_no_paragraph_has_no_page(label):
    assert page_url(label) is None


def _catechism_access():
    return {DOC: reader_access.DocumentAccess(
        "excerpt", COVER_URL, reader_access.CATECHISM_NOTICE)}


def test_access_fields_link_catechism_passages_to_their_page():
    fields = reader_access.access_fields(_catechism_access(), DOC, "§1127")
    assert fields == {"reader_access": "excerpt", "source_url": f"{FLIPBOOK}/294/index.html",
                      "source_credit": reader_access.CATECHISM_NOTICE}
    # A passage with no paragraph keeps the cover.
    assert reader_access.access_fields(_catechism_access(), DOC)["source_url"] == COVER_URL


def test_other_documents_keep_their_own_link():
    url = "https://www.vatican.va/x.html"
    access = {DOC: reader_access.DocumentAccess("excerpt", url, reader_access.VATICAN_CREDIT)}
    assert reader_access.access_fields(access, DOC, "§1127")["source_url"] == url
    assert reader_access.access_fields({}, DOC, "§1127")["source_url"] is None


def _client(response=None, error=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=response, side_effect=error)
    return client


def _response(body, status=200):
    return httpx.Response(status, text=body, request=httpx.Request("GET", COVER_URL))


def test_a_republished_flipbook_sends_passages_back_to_the_cover():
    other = 'FBInit.GUID = "' + "0" * 32 + '";'
    assert asyncio.run(check_publication(_client(_response(other)))) is False
    assert page_url("§1127") is None
    assert reader_access.access_fields(_catechism_access(), DOC, "§1127")["source_url"] \
        == COVER_URL

    same = f'FBInit.GUID = "{TABLE["guid"]}";'
    assert asyncio.run(check_publication(_client(_response(same)))) is True
    assert page_url("§1127") == f"{FLIPBOOK}/294/index.html"


@pytest.mark.parametrize("client", [
    _client(error=httpx.ConnectError("down")),
    _client(_response("", status=503)),
    _client(_response("<html>no guid here</html>")),
], ids=["unreachable", "server-error", "no-guid"])
def test_a_failed_check_changes_nothing(client):
    assert asyncio.run(check_publication(client)) is None
    assert page_url("§1127") == f"{FLIPBOOK}/294/index.html"


def test_the_check_runs_in_the_background_at_most_once_a_day(monkeypatch):
    calls = []

    async def fake_check():
        calls.append(1)
        _publication.checked_at = time.monotonic()

    monkeypatch.setattr(catechism_pages, "check_publication", fake_check)

    async def run():
        _publication.checked_at = None
        page_url("§1")
        page_url("§2")  # the first check is still running
        await _publication.task
        page_url("§3")  # checked moments ago
        _publication.checked_at = time.monotonic() - 25 * 3600
        page_url("§4")
        await _publication.task

    asyncio.run(run())
    assert len(calls) == 2
