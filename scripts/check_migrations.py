#!/usr/bin/env python3
"""Refuses migrations that are not additive, unless they say why.

Schema changes must be additive (CLAUDE.md §4): the API that is already running has to
keep working while a migration applies. This check compares the branch with a base
commit and looks only at the migrations the branch adds or changes:

1. **Non-additive statements.** DROP TABLE / COLUMN / VIEW / MATERIALIZED VIEW / TYPE /
   SCHEMA / FUNCTION / POLICY, RENAME, ALTER COLUMN ... TYPE, SET NOT NULL and TRUNCATE
   fail, except on objects in the `staging` schema, which the corpus writer drops and
   rebuilds by design. Dynamic SQL inside strings (EXECUTE format('...')) counts; SQL
   comments do not. A file with a line `-- non-additive: <reason>` passes: say what
   breaks for the running API and who approved it.
2. **Applied migrations are not edited.** Changing, renaming or deleting a migration
   the base already has fails, unless the changed file carries
   `-- migration-edit-approved: <reason>`.
3. **Migration numbers are unique.** A new file's number must not be one the base or
   another new file already uses (0026 and 0027 each have two files from before this
   check; see CLAUDE.md §4).

Not flagged: DROP INDEX, DROP TRIGGER and DROP CONSTRAINT (the usual way to replace a
trigger or widen a CHECK constraint), DELETE and UPDATE (data, not schema).

    python3 scripts/check_migrations.py --base <commit>   # CI passes the PR's base
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

MIGRATIONS = "supabase/migrations"
NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
NON_ADDITIVE_MARKER = re.compile(r"^\s*--\s*non-additive:[ \t]*\S", re.I | re.M)
EDIT_MARKER = re.compile(r"^\s*--\s*migration-edit-approved:[ \t]*\S", re.I | re.M)

IDENT = r'(?:"[^"]+"|[A-Za-z_][\w$]*)(?:\.(?:"[^"]+"|[A-Za-z_][\w$]*))?'
# A DROP of a whole object: the names follow the keyword.
DROP_OBJECT = re.compile(
    r"\bDROP\s+(TABLE|VIEW|MATERIALIZED\s+VIEW|TYPE|SCHEMA|FUNCTION|POLICY)\s+"
    r"(?:IF\s+EXISTS\s+)?(" + IDENT + r"(?:\s*,\s*" + IDENT + r")*)", re.I)
# A change to an existing table's columns: the table is named by the ALTER TABLE it is in.
ALTER_TABLE = re.compile(r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(" + IDENT + r")", re.I)
COLUMN_CHANGES = [
    ("DROP COLUMN", re.compile(r"\bDROP\s+COLUMN\b", re.I)),
    ("RENAME", re.compile(r"\bRENAME\b", re.I)),
    ("ALTER COLUMN ... TYPE", re.compile(r"\bALTER\s+(?:COLUMN\s+)?" + IDENT + r"\s+(?:SET\s+DATA\s+)?TYPE\b", re.I)),
    ("SET NOT NULL", re.compile(r"\bSET\s+NOT\s+NULL\b", re.I)),
]
# TRUNCATE as a statement, not a trigger event (AFTER TRUNCATE ON) or TG_OP = 'TRUNCATE'.
TRUNCATE = re.compile(r"(?:^|;|\bEXECUTE\s+')\s*TRUNCATE\b(?:\s+TABLE)?\s+(?:ONLY\s+)?(" + IDENT + r")", re.I | re.M)


def strip_comments(sql: str) -> str:
    """Drops -- and /* */ comments, keeping string literals (dynamic SQL lives there)."""
    out, i, n = [], 0, len(sql)
    while i < n:
        if sql.startswith("--", i):
            i = sql.find("\n", i)
            i = n if i < 0 else i
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif sql[i] == "'":
            end = i + 1
            while end < n and (sql[end] != "'" or sql.startswith("''", end)):
                end += 2 if sql.startswith("''", end) else 1
            out.append(sql[i:end + 1])
            i = end + 1
        else:
            out.append(sql[i])
            i += 1
    return "".join(out)


def _staging(name: str) -> bool:
    return name.strip().strip('"').lower().startswith("staging.")


def _line(sql: str, pos: int) -> int:
    return sql.count("\n", 0, pos) + 1


def non_additive(sql: str) -> list[str]:
    """Each non-additive statement as 'line N: WHAT name'. Line numbers are of the
    comment-free text, so close to, not always exactly, the file's own."""
    text = strip_comments(sql)
    found = []
    for m in DROP_OBJECT.finditer(text):
        names = re.split(r"\s*,\s*", m.group(2))
        if not all(_staging(n) for n in names):
            found.append(f"line {_line(text, m.start())}: DROP {' '.join(m.group(1).split()).upper()} {m.group(2)}")
    for m in TRUNCATE.finditer(text):
        if not _staging(m.group(1)):
            found.append(f"line {_line(text, m.start(1))}: TRUNCATE {m.group(1)}")
    # Column changes belong to the nearest ALTER TABLE before them in the same statement.
    for what, pattern in COLUMN_CHANGES:
        for m in pattern.finditer(text):
            statement_start = text.rfind(";", 0, m.start())
            table = None
            for t in ALTER_TABLE.finditer(text, statement_start + 1, m.start()):
                table = t.group(1)
            if table is None or _staging(table):
                continue
            found.append(f"line {_line(text, m.start())}: {what} on {table}")
    return sorted(found, key=lambda f: int(f.split()[1].rstrip(":")))


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def check(base: str, root: Path) -> list[str]:
    problems = []
    base_files = {Path(p).name for p in git("ls-tree", "--name-only", f"{base}:{MIGRATIONS}", cwd=root).split()}
    changes = [line.split("\t") for line in git(
        "diff", "--name-status", "--no-renames", base, "--", MIGRATIONS, cwd=root).splitlines()]
    # Untracked files too, so a local run sees a migration not yet committed.
    untracked = git("ls-files", "--others", "--exclude-standard", "--", MIGRATIONS, cwd=root).split()
    added = sorted({Path(p).name for status, p in changes if status == "A"} | {Path(p).name for p in untracked})
    touched = sorted(Path(p).name for status, p in changes if status in ("M", "D") and Path(p).name in base_files)

    used: dict[str, str] = {}
    for name in sorted(base_files):
        m = NAME.match(name)
        if m:
            used.setdefault(m.group(1), name)
    for name in added:
        m = NAME.match(name)
        if not m:
            if name.endswith(".sql"):
                problems.append(f"{name}: name it NNNN_lowercase_words.sql")
            continue
        if m.group(1) in used:
            problems.append(f"{name}: number {m.group(1)} is already used by {used[m.group(1)]}; "
                            "take the next free number")
        used.setdefault(m.group(1), name)

    for name in touched:
        path = root / MIGRATIONS / name
        if not path.exists() or not EDIT_MARKER.search(path.read_text()):
            problems.append(f"{name}: changes or deletes a migration that is already on the base. "
                            "Applied migrations must not change: write a new one. If it was never "
                            "applied, add `-- migration-edit-approved: <reason>` to it")

    for name in added + [n for n in touched if (root / MIGRATIONS / n).exists()]:
        if not name.endswith(".sql"):
            continue
        sql = (root / MIGRATIONS / name).read_text()
        if NON_ADDITIVE_MARKER.search(sql):
            continue
        for statement in non_additive(sql):
            problems.append(f"{name} {statement}: not additive. If the running API survives it, "
                            "add `-- non-additive: <what breaks, who approved it>` to the file")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", required=True, help="commit to compare against")
    args = parser.parse_args()
    root = Path(git("rev-parse", "--show-toplevel").strip())
    problems = check(args.base, root)
    for p in problems:
        print(f"::error file={MIGRATIONS}/{p.split()[0].rstrip(':')}::{p}" if "GITHUB_ACTIONS" in os.environ else p)
    if problems:
        print(f"\n{len(problems)} migration problem(s). See scripts/check_migrations.py.", file=sys.stderr)
        return 1
    print("migrations: additive, unedited, numbered uniquely")
    return 0


if __name__ == "__main__":
    sys.exit(main())
