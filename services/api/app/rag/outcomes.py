from enum import StrEnum


class PersistedSearchOutcome(StrEnum):
    SUCCESS = "success"
    DEGRADED_SUCCESS = "degraded_success"
    NO_CANDIDATES = "no_candidates"


class CollectionOutcome(StrEnum):
    RESULTS = "results"
    RESULTS_DEGRADED = "results_degraded"
    NO_CANDIDATES = "no_candidates"
    BELOW_THRESHOLD = "below_threshold"
    RETRIEVAL_FAILED = "retrieval_failed"
    CORPUS_SYNC_FAILED = "corpus_sync_failed"
    RANKING_FAILED = "ranking_failed"
