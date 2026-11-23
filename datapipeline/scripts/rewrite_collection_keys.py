"""Rewrite the collection keys stored in user rows to the new keys (corpus cleanup 5.1b.3).

    python3 scripts/rewrite_collection_keys.py                                    # dry run
    python3 scripts/rewrite_collection_keys.py --apply --release <name>           # write

Three places hold keys: `user_preferences.default_collections`, and the saved filters of
`searches` and `guest_trials` (`collections`, `collection_outcomes` and `scopes`).
Bookmarks hold passage IDs only. The 5.1b.3 publish rewrites the corpus; this rewrites
these rows, in one transaction. Since 5.1b.1 the API reads both vocabularies and since
5.1b.2 the web translates any old key it reads, so the rows work whether or not this
has run, and it has no reverse (D11).

The rules are the web's restore rules (`canonicalSearchFilters` and `canonicalOutcomes`
in apps/web), so a restored search reads the same before and after:
  - keys are mapped and de-duplicated, keeping the first; a key neither vocabulary knows
    (the old `saints`) is left as it is, and so is the row's order;
  - the old papal keys become a Papal documents genre selection: per old key, the genres
    its own 5.1a selection named or else the genres it stood for; all three with no
    selection are the whole collection; popes narrow only if every old key named some;
  - outcomes of old keys that merge: results if any had results (degraded if another
    failed or was degraded), else the most informative. The spec said "the worse
    outcome", which would report no results for a merged collection that had them.

A dry run (the default) reads in a read-only transaction and prints counts per table and
key, never user content. `--apply` writes, refusing anything but a local database unless
datapipeline/PUBLISH_LOCK.json has an entry for collection `all` and the release with
step `repair`. It refuses while any saved filters are a double-encoded JSON string (the
0033 repair), as it would skip them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collection_keys import RENAMES  # noqa: E402

# Old papal key → (the only genres it read | None, the genres it did not read | None),
# as the API's LEGACY_COLLECTIONS and the web's mirror say.
PAPAL_SUBSETS: dict[str, tuple[frozenset[str] | None, frozenset[str] | None]] = {
    "encyclicals": (frozenset({"encyclical"}), None),
    "apostolic-exhortations": (frozenset({"apostolic-exhortation"}), None),
    "papal-documents": (None, frozenset({"encyclical", "apostolic-exhortation"})),
}
OUTCOME_ORDER = ("results", "results_degraded", "retrieval_failed", "corpus_sync_failed",
                 "ranking_failed", "below_threshold", "no_candidates")
OUTCOME_FAILURES = frozenset({"results_degraded", "retrieval_failed", "corpus_sync_failed",
                              "ranking_failed"})


def papal_genres(works: list[dict]) -> list[str]:
    """The papal genres the web's filter lists (`collection-scopes.json`): those of
    published papal works, most documents first, `other` last."""
    counts = Counter(w["genre"] for w in works
                     if RENAMES.get(w.get("collection")) == "papal" and w.get("genre"))
    return sorted(counts, key=lambda g: (g == "other", -counts[g], g))


def canonical_keys(keys: list) -> list:
    out = []
    for key in keys:
        new = RENAMES.get(key, key) if isinstance(key, str) else key
        if new not in out:
            out.append(new)
    return out


def merge_outcomes(values: list[str]) -> str:
    if any(v in ("results", "results_degraded") for v in values):
        return "results_degraded" if any(v in OUTCOME_FAILURES for v in values) else "results"
    return next((o for o in OUTCOME_ORDER if o in values), values[0])


def canonical_outcomes(outcomes: dict) -> dict:
    grouped: dict[str, list[str]] = {}
    for key, value in outcomes.items():
        grouped.setdefault(RENAMES.get(key, key), []).append(value)
    return {k: (vs[0] if len(vs) == 1 else merge_outcomes(vs)) for k, vs in grouped.items()}


def _names(value) -> list[str] | None:
    if not isinstance(value, list):
        return None
    kept = list(dict.fromkeys(v for v in value if isinstance(v, str)))
    return kept or None


def papal_scope(keys: list[str], scopes: dict, vocabulary: list[str]) -> dict | None:
    """The Papal documents selection a search of the old papal `keys` stands for."""
    genres: set[str] = set()
    for key in keys:
        only, without = PAPAL_SUBSETS[key]
        named = _names((scopes.get(key) or {}).get("genres")) if isinstance(scopes.get(key), dict) else None
        genres |= set(named) if named else (
            set(only) if only is not None else {g for g in vocabulary if g not in without})
    issuer_lists = [_names(scopes[k].get("issuers")) if isinstance(scopes.get(k), dict) else None
                    for k in keys]
    entry: dict = {}
    if any(g not in genres for g in vocabulary):
        entry["genres"] = [g for g in vocabulary if g in genres]
    if all(lst is not None for lst in issuer_lists):
        entry["issuers"] = list(dict.fromkeys(i for lst in issuer_lists for i in lst))
    return entry or None


def rewrite_filters(filters: dict, vocabulary: list[str]) -> dict:
    """A saved search's filters in the new keys. Fields other than the three are kept."""
    out = dict(filters)
    raw = filters.get("collections")
    keys = raw if isinstance(raw, list) else []
    scopes = filters.get("scopes") if isinstance(filters.get("scopes"), dict) else {}
    if isinstance(raw, list):
        out["collections"] = canonical_keys(raw)
    if isinstance(filters.get("collection_outcomes"), dict):
        out["collection_outcomes"] = canonical_outcomes(filters["collection_outcomes"])
    old_papal = [k for k in dict.fromkeys(keys) if k in PAPAL_SUBSETS]
    new_scopes = {k: v for k, v in scopes.items() if k not in RENAMES}
    if old_papal and "papal" not in keys:
        entry = papal_scope(old_papal, scopes, vocabulary)
        if entry:
            new_scopes["papal"] = entry
    if new_scopes:
        out["scopes"] = new_scopes
    else:
        out.pop("scopes", None)
    return out


def key_counts(values) -> Counter:
    return Counter(v for v in values if isinstance(v, str) and v in RENAMES)


# --------------------------------------------------------------------------- database

PREFERENCES_SQL = "SELECT user_id, default_collections FROM public.user_preferences"
FILTERS_SQL = """SELECT {key}::text AS key, filters, jsonb_typeof(filters) AS kind
                 FROM public.{table} WHERE filters IS NOT NULL"""
FILTER_TABLES = {"searches": "id", "guest_trials": "id"}


async def plan(conn, vocabulary: list[str]) -> dict:
    """Every change, and the counts the dry run prints."""
    report: dict = {"tables": {}, "changes": {"user_preferences": [], "searches": [],
                                               "guest_trials": []}}
    prefs = await conn.fetch(PREFERENCES_SQL)
    keys = Counter()
    for row in prefs:
        old = list(row["default_collections"] or [])
        keys += key_counts(old)
        new = canonical_keys(old)
        if new != old:
            report["changes"]["user_preferences"].append((row["user_id"], new))
    report["tables"]["user_preferences"] = {
        "rows": len(prefs), "to_change": len(report["changes"]["user_preferences"]),
        "old_keys": dict(sorted(keys.items()))}

    for table, key in FILTER_TABLES.items():
        rows = await conn.fetch(FILTERS_SQL.format(key=key, table=table))
        keys, outcome_keys, scoped, merged, strings = Counter(), Counter(), 0, 0, 0
        for row in rows:
            if row["kind"] == "string":
                strings += 1
            if row["kind"] != "object":
                continue
            filters = row["filters"] if isinstance(row["filters"], dict) else json.loads(row["filters"])
            collections = filters.get("collections") if isinstance(filters.get("collections"), list) else []
            keys += key_counts(collections)
            outcomes = filters.get("collection_outcomes")
            if isinstance(outcomes, dict):
                outcome_keys += key_counts(outcomes)
                merged += len(outcomes) - len(canonical_outcomes(outcomes))
            new = rewrite_filters(filters, vocabulary)
            if new != filters:
                scoped += "papal" in (new.get("scopes") or {}) and "papal" not in (filters.get("scopes") or {})
                report["changes"][table].append((row["key"], new))
        report["tables"][table] = {
            "rows": len(rows), "to_change": len(report["changes"][table]),
            "old_keys_in_collections": dict(sorted(keys.items())),
            "old_keys_in_outcomes": dict(sorted(outcome_keys.items())),
            "outcomes_merged": merged, "papal_selection_added": scoped,
            "double_encoded_filters": strings}
    return report


async def apply_changes(conn, report: dict) -> None:
    for user_id, new in report["changes"]["user_preferences"]:
        await conn.execute(
            "UPDATE public.user_preferences SET default_collections = $2 WHERE user_id = $1",
            user_id, new)
    for table, key in FILTER_TABLES.items():
        for row_key, new in report["changes"][table]:
            # A jsonb parameter: the datapipeline pool registers no codec (CLAUDE.md §4).
            await conn.execute(
                f"UPDATE public.{table} SET filters = $2::jsonb WHERE {key}::text = $1",
                row_key, json.dumps(new))


def summary(report: dict) -> str:
    return json.dumps(report["tables"], indent=1)


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--release", metavar="RELEASE_ID",
                    help="the release whose PUBLISH_LOCK.json entry approves --apply")
    args = ap.parse_args(argv)

    import asyncpg

    import registry
    from config import settings

    if args.apply:
        from publish_lock import PublishLocked, assert_live_write_allowed
        try:
            assert_live_write_allowed("rewrite_collection_keys.py --apply", "all",
                                      args.release, "repair")
        except PublishLocked as exc:
            print(exc, file=sys.stderr)
            return 2

    vocabulary = papal_genres(registry.current().works)
    conn = await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)
    try:
        async with conn.transaction(readonly=not args.apply):
            report = await plan(conn, vocabulary)
            print(summary(report))
            strings = sum(t.get("double_encoded_filters", 0) for t in report["tables"].values())
            if not args.apply:
                print("dry run: nothing written")
                return 0
            if strings:
                print(f"REFUSING: {strings} saved filters are a double-encoded JSON string; "
                      "repair them as 0033 did first", file=sys.stderr)
                return 1
            await apply_changes(conn, report)
            print("applied")
            return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
