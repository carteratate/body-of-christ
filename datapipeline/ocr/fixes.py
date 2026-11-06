"""What a person settles after the model: tracked fixes, and the frozen final text.

`ocr/works/<work>.fixes.json` lists edits checked against the page images, each
`{"passage", "find", "replace", "why"}`. `find` must occur exactly once, so a fix that no
longer fits its passage stops the run instead of doing nothing. They are not bound by the
model's 2% limit: a person, not a model, made them, and each says why. A passage's fixes
are applied to its corrected text in the order listed, and the sampled check runs on the
result.

`freeze` writes the text adapters read to `ocr/texts/<work>.json`. The clean-up can be
repeated from the locked scan files; the model's correction cannot, so what the gate
passed is kept in the repository and not only in the gitignored work directory.
"""
from __future__ import annotations

import json
from pathlib import Path

from ocr.gate import evaluate
from ocr.label import ocr_metadata
from ocr.work import TEXTS_DIR, WORKS_DIR, WorkDir


def read_fixes(work: str, works_dir: Path = WORKS_DIR) -> list[dict]:
    path = works_dir / f"{work}.fixes.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def apply_fixes(workdir: WorkDir, works_dir: Path = WORKS_DIR) -> int:
    """Rebuild every passage's `fixed` text from the fixes file. Returns the fixes applied."""
    fixes = read_fixes(workdir.config.work, works_dir)
    passages = workdir.passages()
    by_id = {p.id: p for p in passages}
    for p in passages:
        p.fixed = None
    for fix in fixes:
        passage = by_id.get(fix["passage"])
        if passage is None:
            raise ValueError(f"fix names no passage: {fix['passage']}")
        if not fix.get("why"):
            raise ValueError(f"{fix['passage']}: a fix says why ({fix['find']!r})")
        text = passage.text
        if text.count(fix["find"]) != 1:
            raise ValueError(f"{fix['passage']}: {fix['find']!r} occurs "
                             f"{text.count(fix['find'])} times, not once")
        passage.fixed = text.replace(fix["find"], fix["replace"])
    workdir.save_passages(passages)
    return len(fixes)


def freeze(workdir: WorkDir, texts_dir: Path = TEXTS_DIR) -> Path:
    """Write the work's final text with the gate's status at this moment."""
    config = workdir.config
    result = evaluate(workdir)
    data = {
        "work": config.work,
        "title": config.title,
        "metadata": ocr_metadata(config.scan),
        "gate": result.status,
        "passages": [{"id": p.id, "pages": p.pages, "leaves": p.leaves, "text": p.text}
                     for p in workdir.passages()],
    }
    texts_dir.mkdir(parents=True, exist_ok=True)
    path = texts_dir / f"{config.work}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def read_text(work: str, texts_dir: Path = TEXTS_DIR) -> dict:
    return json.loads((texts_dir / f"{work}.json").read_text(encoding="utf-8"))
