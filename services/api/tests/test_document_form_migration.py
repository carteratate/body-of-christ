"""Exercise 0044 (documents.form and corpus_forms) against an isolated local PostgreSQL
cluster, on top of 2.2a's migrations. Carter decided on 9 Nov 2026 that a papal
document's form (bull, brief) is a label separate from its genre (corpus cleanup 1.3b).
"""

import re
import runpy

import pytest

from tests.pg_cluster import MIGRATIONS
from tests.test_corpus_facts_migration import (  # noqa: F401  (postgres is a fixture)
    DOC_A, EARLIER, REGISTRY, SCHEMA_MIGRATION, SEED, VALIDATE_MIGRATION, _fails, postgres)

FORM_MIGRATION = MIGRATIONS / "0044_document_form.sql"


@pytest.fixture()
def formed(postgres):  # noqa: F811
    postgres(SEED)
    postgres.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name,
                     FORM_MIGRATION.name)
    return postgres


def _genres_module() -> dict:
    return runpy.run_path(str(REGISTRY / "genres.py"))


def test_form_seed_matches_registry_module(formed):
    text = FORM_MIGRATION.read_text()
    values = text.split("INSERT INTO corpus_forms (key) VALUES", 1)[1].split(";", 1)[0]
    forms = _genres_module()["PAPAL_FORMS"]
    assert tuple(re.findall(r"\('([a-z-]+)'\)", values)) == forms
    assert [r[0] for r in formed("SELECT key FROM corpus_forms ORDER BY key")] == sorted(forms)


def test_form_is_null_by_default_and_accepts_only_forms(formed):
    assert formed("SELECT count(*) FROM documents WHERE form IS NOT NULL") == [["0"]]
    for form in _genres_module()["PAPAL_FORMS"]:
        formed(f"UPDATE documents SET form = '{form}' WHERE id = '{DOC_A}'")
    for bad in ("encyclical", "Bull", "breve"):
        assert "documents_form_fk" in _fails(
            formed, f"UPDATE documents SET form = '{bad}' WHERE id = '{DOC_A}'")


def test_bull_is_a_form_not_a_genre(formed):
    assert "documents_genre_fk" in _fails(
        formed, f"UPDATE documents SET genre = 'bull' WHERE id = '{DOC_A}'")
    formed(f"UPDATE documents SET genre = 'apostolic-constitution', form = 'bull' "
           f"WHERE id = '{DOC_A}'")


def test_a_document_still_holding_bull_stops_the_migration(postgres):  # noqa: F811
    postgres(SEED)
    postgres.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
    postgres(f"UPDATE documents SET genre = 'bull' WHERE id = '{DOC_A}'")
    with pytest.raises(Exception):
        postgres.migrate(FORM_MIGRATION.name)
    # One transaction: nothing of 0044 is left behind.
    assert postgres("SELECT to_regclass('public.corpus_forms') IS NULL") == [["t"]]
    assert postgres("SELECT count(*) FROM corpus_genres WHERE key = 'bull'") == [["1"]]


def test_staging_made_before_0044_gains_the_column(formed):
    # 0043 created the staging tables; 0044 adds the column to them.
    formed(f"INSERT INTO staging.documents (id, collection, title, form) "
           f"VALUES ('{DOC_A}', 'bible', 'A', 'brief')")


def test_staging_made_after_0044_has_the_column(formed):
    formed("SELECT public.drop_corpus_staging(); SELECT public.create_corpus_staging();")
    assert formed("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'staging' AND table_name = 'documents' AND column_name = 'form'
    """) == [["1"]]


def test_corpus_forms_is_closed_to_client_roles(formed):
    for role in ("anon", "authenticated"):
        assert formed(f"SELECT has_table_privilege('{role}', 'public.corpus_forms', 'SELECT')"
                      ) == [["f"]], role
    assert formed("SELECT relrowsecurity FROM pg_class WHERE relname = 'corpus_forms'"
                  ) == [["t"]]
    assert formed("SELECT count(*) FROM pg_policies WHERE tablename = 'corpus_forms'"
                  ) == [["0"]]
