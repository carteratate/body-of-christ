"""OCR clean-up tool and quality gate (corpus-cleanup item 1.2f, D9).

Turns a scanned book's OCR into text a work's adapter can use, and gates it:
`pages` reads the scan's positioned lines, `layout` puts them in reading order,
`furniture` removes page furniture and mends broken words, `correct` has a model fix
misread characters under a hard word-change limit and spend ceiling, `gate` measures the
unrecognized-word rate and records the person's check, and `report` writes `gate.md`.
`label` is the source label scanned passages carry. Run it with `python3 -m ocr`.
"""
