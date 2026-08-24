import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys

import pytest

from identity import passage_id
from model import Document, Passage
from publication import (
    CollectionPublicationRunner,
    PublicationRequest,
    PublicationTarget,
    SOURCE_ADAPTERS,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))
from services.api.app.rag.constants import VALID_COLLECTIONS


def _document(*anchors: str) -> Document:
    return Document(
        id="11111111-1111-1111-1111-111111111111",
        collection="medieval",
        title="On Loving God",
        author="Bernard of Clairvaux",
        passages=[
            Passage(
                content=f"Passage {anchor}",
                reference=anchor,
                anchor=anchor,
                chapter_key="chapter-1",
                chapter_label="Chapter 1",
                position=position,
            )
            for position, anchor in enumerate(anchors)
        ],
    )


class FakeReaderStore:
    def __init__(self, events: list[str], live_ids: set[str] | None = None):
        self.events = events
        self.live_ids = live_ids or set()

    async def passage_ids(self, collection: str) -> set[str]:
        self.events.append("reader:inspect")
        return self.live_ids

    async def wipe(self, collection: str) -> None:
        self.events.append("reader:wipe")

    async def write(self, document: Document, *, prune: bool) -> int:
        self.events.append(f"reader:write:{prune}")
        return 0

    async def prune_documents(self, collection: str, keep_ids: set[str]) -> int:
        self.events.append("reader:prune")
        return 0


class FakeSearchIndex:
    def __init__(
        self,
        events: list[str],
        live_ids: set[str] | None = None,
        fail_writes: int = 0,
    ):
        self.events = events
        self.live_ids = live_ids or set()
        self.pruned_keep_ids: set[str] | None = None
        self.fail_writes = fail_writes

    async def passage_ids(self, collection: str) -> set[str]:
        self.events.append("search:inspect")
        return self.live_ids

    async def reset(self, collection: str) -> None:
        self.events.append("search:reset")

    async def write(self, document: Document) -> None:
        self.events.append("search:write")
        if self.fail_writes:
            self.fail_writes -= 1
            raise RuntimeError("interrupted search write")

    async def prune(self, collection: str, keep_ids: set[str]) -> int:
        self.events.append("search:prune")
        self.pruned_keep_ids = keep_ids
        return 0


def _runner(
    events: list[str],
    documents: list[Document],
    *,
    reader: FakeReaderStore | None = None,
    search: FakeSearchIndex | None = None,
) -> CollectionPublicationRunner:
    reader = reader or FakeReaderStore(events)
    search = search or FakeSearchIndex(events)

    @asynccontextmanager
    async def acquire_reader():
        events.append("reader:acquire")
        try:
            yield reader
        finally:
            events.append("reader:close")

    @asynccontextmanager
    async def acquire_search():
        events.append("search:acquire")
        try:
            yield search
        finally:
            events.append("search:close")

    return CollectionPublicationRunner(
        source_adapters={"medieval": lambda: documents},
        acquire_reader_store=acquire_reader,
        acquire_search_index=acquire_search,
    )


def test_source_adapter_registry_exactly_matches_production_collections():
    assert set(SOURCE_ADAPTERS) == VALID_COLLECTIONS == {
        "apostolic-exhortations",
        "bible",
        "canon-law",
        "catechism",
        "church-fathers",
        "councils",
        "encyclicals",
        "medieval",
        "papal-documents",
        "summa",
    }
    assert all(callable(adapter) for adapter in SOURCE_ADAPTERS.values())


@pytest.mark.parametrize(
    ("target", "expected_events"),
    [
        (
            PublicationTarget.READER,
            [
                "reader:acquire",
                "reader:inspect",
                "reader:write:True",
                "reader:prune",
                "reader:close",
            ],
        ),
        (
            PublicationTarget.SEARCH,
            [
                "search:acquire",
                "search:inspect",
                "search:write",
                "search:prune",
                "search:close",
            ],
        ),
        (
            PublicationTarget.BOTH,
            [
                "reader:acquire",
                "reader:inspect",
                "reader:write:True",
                "reader:prune",
                "reader:close",
                "search:acquire",
                "search:inspect",
                "search:write",
                "search:prune",
                "search:close",
            ],
        ),
    ],
)
def test_publication_acquires_only_selected_targets_and_writes_before_pruning(
    target: PublicationTarget, expected_events: list[str]
):
    events: list[str] = []
    runner = _runner(events, [_document("a/1")])

    result = asyncio.run(runner.publish(PublicationRequest("medieval", target=target)))

    assert events == expected_events
    assert result.document_count == 1
    assert result.passage_count == 1


def test_limited_publication_writes_without_collection_wide_pruning():
    events: list[str] = []
    runner = _runner(events, [_document("a/1"), _document("b/1")])

    asyncio.run(
        runner.publish(
            PublicationRequest("medieval", target=PublicationTarget.BOTH, limit=1)
        )
    )

    assert "reader:prune" not in events
    assert "search:prune" not in events
    assert events.count("reader:write:False") == 1
    assert events.count("search:write") == 1


def test_both_store_publication_is_safe_to_rerun_after_search_interruption():
    events: list[str] = []
    search = FakeSearchIndex(events, fail_writes=1)
    runner = _runner(events, [_document("a/1")], search=search)
    request = PublicationRequest("medieval", target=PublicationTarget.BOTH)

    with pytest.raises(RuntimeError, match="interrupted search write"):
        asyncio.run(runner.publish(request))

    assert events[-1] == "search:close"

    result = asyncio.run(runner.publish(request))

    assert result.passage_count == 1
    assert events.count("reader:write:True") == 2
    assert events.count("search:write") == 2
    assert events[-1] == "search:close"


def test_explicit_search_reset_happens_before_search_writes():
    events: list[str] = []
    runner = _runner(events, [_document("a/1")])

    asyncio.run(
        runner.publish(
            PublicationRequest(
                "medieval",
                target=PublicationTarget.SEARCH,
                reset_search_index=True,
            )
        )
    )

    assert events == [
        "search:acquire",
        "search:inspect",
        "search:reset",
        "search:write",
        "search:close",
    ]


def test_reader_wipe_requires_an_exact_collection_confirmation():
    events: list[str] = []
    runner = _runner(events, [_document("a/1")])

    with pytest.raises(ValueError, match="confirmation must exactly match 'medieval'"):
        asyncio.run(
            runner.publish(
                PublicationRequest(
                    "medieval",
                    target=PublicationTarget.READER,
                    wipe_reader=True,
                    wipe_reader_confirmation="Medieval",
                )
            )
        )

    assert events == []


@pytest.mark.parametrize(
    "publication_request",
    [
        PublicationRequest(
            "medieval", target=PublicationTarget.READER, reset_search_index=True
        ),
        PublicationRequest(
            "medieval",
            target=PublicationTarget.SEARCH,
            wipe_reader=True,
            wipe_reader_confirmation="medieval",
        ),
        PublicationRequest(
            "medieval", limit=1, reset_search_index=True
        ),
        PublicationRequest(
            "medieval",
            limit=1,
            wipe_reader=True,
            wipe_reader_confirmation="medieval",
        ),
    ],
)
def test_invalid_destructive_combinations_are_refused_before_store_acquisition(
    publication_request: PublicationRequest,
):
    events: list[str] = []
    runner = _runner(events, [_document("a/1")])

    with pytest.raises(ValueError):
        asyncio.run(runner.publish(publication_request))

    assert events == []


def test_confirmed_reader_wipe_rebuilds_without_incremental_pruning():
    events: list[str] = []
    runner = _runner(events, [_document("a/1")])

    asyncio.run(
        runner.publish(
            PublicationRequest(
                "medieval",
                target=PublicationTarget.READER,
                wipe_reader=True,
                wipe_reader_confirmation="medieval",
            )
        )
    )

    assert events == [
        "reader:acquire",
        "reader:inspect",
        "reader:wipe",
        "reader:write:False",
        "reader:close",
    ]


def test_collapsed_build_is_refused_before_writes():
    events: list[str] = []
    live_ids = {f"live-{position}" for position in range(20)}
    runner = _runner(
        events,
        [_document("a/1")],
        reader=FakeReaderStore(events, live_ids),
    )

    with pytest.raises(ValueError, match="build produced 1 passages against 20"):
        asyncio.run(
            runner.publish(
                PublicationRequest("medieval", target=PublicationTarget.READER)
            )
        )

    assert events == ["reader:acquire", "reader:inspect", "reader:close"]


def test_identity_churn_is_refused_when_counts_match():
    events: list[str] = []
    document = _document(*[f"new/{position}" for position in range(20)])
    live_ids = {f"old-{position}" for position in range(20)}
    runner = _runner(
        events,
        [document],
        search=FakeSearchIndex(events, live_ids),
    )

    with pytest.raises(ValueError, match="live passage ids"):
        asyncio.run(
            runner.publish(
                PublicationRequest("medieval", target=PublicationTarget.SEARCH)
            )
        )

    assert events == ["search:acquire", "search:inspect", "search:close"]


def test_reset_authorizes_search_identity_replacement():
    events: list[str] = []
    document = _document(*[f"new/{position}" for position in range(20)])
    live_ids = {f"old-{position}" for position in range(20)}
    runner = _runner(
        events,
        [document],
        search=FakeSearchIndex(events, live_ids),
    )

    asyncio.run(
        runner.publish(
            PublicationRequest(
                "medieval",
                target=PublicationTarget.SEARCH,
                reset_search_index=True,
            )
        )
    )

    assert "search:reset" in events
    assert "search:write" in events


def test_built_passage_ids_use_the_shared_identity_contract():
    events: list[str] = []
    document = _document("a/1")
    search = FakeSearchIndex(events)
    runner = _runner(events, [document], search=search)

    asyncio.run(
        runner.publish(
            PublicationRequest("medieval", target=PublicationTarget.SEARCH)
        )
    )

    assert search.pruned_keep_ids == {passage_id(document.id, "a/1")}
