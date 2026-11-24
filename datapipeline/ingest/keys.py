"""Collection keys an adapter shares with the modules that register it, kept free of
imports so `publication.py` can name them without loading an adapter (or `config`).

The theologians and spiritual writers (5.6b) are built under the `medieval` source key,
which publishes as the `theologians` collection since 5.1b.3 (`publication.py`). A source
keeps its old name (the registry, the checks and the known defects are keyed by it), so
this constant names the source, not the published collection.
"""
THEOLOGIANS = "medieval"
