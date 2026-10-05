"""Source-completeness checks (corpus-cleanup item 0.1a).

These compare what the adapters build against the vendored source files, independently
of the adapters' own parsing: `source_text` reads each source format itself, `coverage`
measures how much body text reaches a passage, and `sequence` checks numbered units.
`report` is the CLI. See docs/corpus-cleanup/P0-checks-identity-research.md, item 0.1a.
"""
