import logging
import re
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter()


class SourceDocument(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    chunk_count: int


class SourcesResponse(BaseModel):
    sources: list[SourceDocument]


# Clean up "Part Fourth." / trailing periods from author labels in ANF/NPNF references.
_SERIES_SUFFIX = re.compile(r':\s*Part\s+\w+\.?\s*$', re.IGNORECASE)
_TRAILING_PUNCT = re.compile(r'[.:]+$')

# Strings that appear as ref_author in ThML files but are actually work titles.
# Maps work title → real author name.
_WORK_TITLE_AUTHOR = {
    "City of God": "Augustine",
    "On Christian Doctrine": "Augustine",
}

# Known author labels that are editorial descriptions rather than person names.
_AUTHOR_LABEL_OVERRIDES = {
    "Doctrinal Treatises of St. Augustin": "Augustine",
    "Moral Treatises of St. Augustin": "Augustine",
    "Letters of St. Augustin": "Augustine",
    "Expositions on the Book of Psalms": "Augustine",
    "Sermons on New-Testament Lessons": "Augustine",
}


def _clean_author(name: str) -> str:
    if name in _AUTHOR_LABEL_OVERRIDES:
        return _AUTHOR_LABEL_OVERRIDES[name]
    name = _SERIES_SUFFIX.sub("", name).strip()
    name = _TRAILING_PUNCT.sub("", name).strip()
    return name


def _clean_title(title: str) -> str:
    return _TRAILING_PUNCT.sub("", title.strip())


async def _get_church_fathers(pool) -> list[SourceDocument]:
    """Return church-fathers entries split by individual (author, work) pairs.

    Multi-author ANF/NPNF volumes are expanded into one entry per church father work.
    Single-work files (Confessions, Incarnation) are returned as-is.
    Volumes whose ref_author labels are all work titles (e.g. NPNF1-02 with
    "City of God" and "On Christian Doctrine") are collapsed to one entry per
    work title with the real author looked up from _WORK_TITLE_AUTHOR.
    """
    rows = await pool.fetch(
        """
        WITH ref_groups AS (
            SELECT
                d.id::text                                               AS doc_id,
                d.title                                                  AS doc_title,
                d.author                                                 AS doc_author,
                d.year                                                   AS doc_year,
                split_part(c.reference, ' — ', 1)                        AS ref_author,
                split_part(split_part(c.reference, ' — ', 2), ', ', 1)   AS ref_work,
                COUNT(c.id)::int                                         AS chunk_count
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.collection = 'church-fathers'
              AND c.reference LIKE '% — %'
            GROUP BY d.id, d.title, d.author, d.year, ref_author, ref_work
        ),
        doc_summary AS (
            SELECT
                doc_id, doc_title, doc_author, doc_year,
                COUNT(DISTINCT ref_author)::int  AS unique_authors,
                COUNT(DISTINCT ref_work)::int    AS unique_works,
                SUM(chunk_count)::int            AS total_chunks
            FROM ref_groups
            GROUP BY doc_id, doc_title, doc_author, doc_year
        )
        SELECT r.doc_id, r.doc_title, r.doc_author, r.doc_year,
               r.ref_author, r.ref_work, r.chunk_count,
               s.unique_authors, s.unique_works, s.total_chunks
        FROM ref_groups r
        JOIN doc_summary s USING (doc_id)
        ORDER BY r.ref_author, r.ref_work
        """
    )

    # Group rows by doc_id so we can inspect all ref_authors before deciding path.
    by_doc: dict[str, list] = defaultdict(list)
    for row in rows:
        by_doc[row["doc_id"]].append(row)

    results: list[SourceDocument] = []

    for doc_id, doc_rows in by_doc.items():
        first = doc_rows[0]
        unique_authors: int = first["unique_authors"]
        unique_works: int = first["unique_works"]
        total_chunks: int = first["total_chunks"]
        year = first["doc_year"]

        if unique_authors == 1:
            if unique_works == 1:
                # Genuine single (author, work) file.
                results.append(SourceDocument(
                    id=doc_id,
                    collection="church-fathers",
                    title=_clean_title(first["ref_work"]),
                    author=_clean_author(first["ref_author"]),
                    year=year,
                    chunk_count=total_chunks,
                ))
            else:
                # The ref_author label is a work title; ref_works are sub-sections.
                work_title = _clean_title(first["ref_author"])
                results.append(SourceDocument(
                    id=doc_id,
                    collection="church-fathers",
                    title=work_title,
                    author=_WORK_TITLE_AUTHOR.get(work_title),
                    year=year,
                    chunk_count=total_chunks,
                ))

        else:
            # Multiple distinct ref_authors.
            all_ref_authors = {r["ref_author"] for r in doc_rows}

            if all_ref_authors <= _WORK_TITLE_AUTHOR.keys():
                # Every "author" label is actually a work title — collapse to one
                # entry per work title (e.g. "City of God" + "On Christian Doctrine").
                by_work_title: dict[str, int] = defaultdict(int)
                for r in doc_rows:
                    by_work_title[r["ref_author"]] += r["chunk_count"]
                for ref_author, chunk_count in sorted(by_work_title.items()):
                    work_title = _clean_title(ref_author)
                    results.append(SourceDocument(
                        id=f"{doc_id}:{ref_author}",
                        collection="church-fathers",
                        title=work_title,
                        author=_WORK_TITLE_AUTHOR.get(work_title),
                        year=year,
                        chunk_count=chunk_count,
                    ))
            else:
                # True multi-author volume: one entry per (author, work) pair.
                by_pair: dict[tuple[str, str], int] = defaultdict(int)
                for r in doc_rows:
                    by_pair[(r["ref_author"], r["ref_work"])] += r["chunk_count"]
                for (ref_author, ref_work), chunk_count in sorted(by_pair.items()):
                    results.append(SourceDocument(
                        id=f"{doc_id}:{ref_author}:{ref_work}",
                        collection="church-fathers",
                        title=_clean_title(ref_work),
                        author=_clean_author(ref_author),
                        year=year,
                        chunk_count=chunk_count,
                    ))

    results.sort(key=lambda d: (d.author or "\xff", d.title))
    return results


@router.get("/sources", response_model=SourcesResponse)
async def get_sources(
    user: AuthUser = Depends(get_current_user),
) -> SourcesResponse:
    """Return all documents in the corpus with passage counts."""
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        # Non-church-fathers: simple document-level query.
        doc_rows = await pool.fetch(
            """
            SELECT d.id::text, d.collection, d.title, d.author, d.year,
                   NULLIF(d.translation, '') AS translation,
                   COUNT(c.id)::int AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            WHERE d.collection != 'church-fathers'
            GROUP BY d.id
            ORDER BY d.collection, d.year NULLS LAST, d.title
            """,
        )

        cf_entries = await _get_church_fathers(pool)

    except Exception as exc:
        logger.error("get_sources query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    sources: list[SourceDocument] = [
        SourceDocument(
            id=row["id"],
            collection=row["collection"],
            title=row["title"],
            author=row["author"] or None,
            year=row["year"],
            translation=row["translation"],
            chunk_count=row["chunk_count"],
        )
        for row in doc_rows
    ]
    sources.extend(cf_entries)

    return SourcesResponse(sources=sources)
