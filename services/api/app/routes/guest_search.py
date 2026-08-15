"""Guest onboarding: two transferable searches without authentication."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import time
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.rag.constants import VALID_COLLECTIONS
from app.rag.pipeline import run_search_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()

_GUEST_QUOTA = 3
_GUEST_SEARCH_LIMIT = 2
_IP_ABUSE_LIMIT = _GUEST_SEARCH_LIMIT
_VALID_TRANSLATIONS = {"CPDV", "douay-rheims"}
_background_guest_tasks: set[asyncio.Task[None]] = set()


@dataclass(frozen=True)
class TrialClaim:
    allowed: bool
    claim_id: uuid.UUID | None


class TrialStoreUnavailable(RuntimeError):
    pass


class GuestTransferOwnershipLost(RuntimeError):
    """The account-claim path took ownership of an expired guest transfer."""


class GuestSearchFilters(BaseModel):
    collections: list[str]
    translation: str = "CPDV"

    @field_validator("collections")
    @classmethod
    def validate_collections(cls, collections: list[str]) -> list[str]:
        if not collections:
            raise ValueError("At least one collection is required")
        invalid = sorted(set(collections) - VALID_COLLECTIONS)
        if invalid:
            raise ValueError(f"Invalid collections: {invalid}")
        return list(dict.fromkeys(collections))


class GuestSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    filters: GuestSearchFilters
    quota: int = _GUEST_QUOTA
    session_token: str = Field(..., min_length=32, max_length=128)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, query: str) -> str:
        query = query.strip()
        if not query:
            raise ValueError("Query must not be blank")
        return query


class ClaimGuestSessionRequest(BaseModel):
    session_token: str = Field(..., min_length=32, max_length=128)
    saved_chunk_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class ClaimGuestSessionResponse(BaseModel):
    searches_imported: int
    passages_saved: int


def _get_client_ip(request: Request) -> str:
    proxy_ip = request.headers.get("x-theocorpus-client-ip")
    supplied_secret = request.headers.get("x-internal-secret")
    if settings.internal_api_secret and supplied_secret == settings.internal_api_secret and proxy_ip:
        try:
            return str(ipaddress.ip_address(proxy_ip.strip()))
        except ValueError:
            logger.warning("trusted proxy supplied invalid client IP")
    return request.client.host or "unknown"


def _hash_ip(ip: str) -> str:
    try:
        address = ipaddress.ip_address(ip.strip())
        # Temporary IPv6 interface addresses commonly rotate within the same
        # delegated network. Quota the network rather than each individual host.
        if isinstance(address, ipaddress.IPv6Address):
            ip = str(ipaddress.ip_network(f"{address}/64", strict=False).network_address) + "/64"
        else:
            ip = str(address)
    except ValueError:
        # Preserve stable behavior for framework test hosts or an unavailable IP.
        ip = ip.strip()
    secret = settings.guest_ip_hash_secret or settings.internal_api_secret
    if not secret:
        if settings.app_env != "development":
            raise RuntimeError("GUEST_IP_HASH_SECRET or INTERNAL_API_SECRET is required")
        secret = "theocorpus-development-only-guest-ip-key"
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def cleanup_expired_guest_trials() -> None:
    """Physically remove expired guest research and its cascaded retrievals."""
    pool = get_pool()
    if pool is None:
        return
    try:
        await pool.execute(
            "DELETE FROM guest_trials WHERE created_at < now() - interval '30 days'"
        )
    except Exception as exc:
        logger.warning("expired guest trial cleanup failed (%s)", exc.__class__.__name__)


async def _try_record_trial(ip_hash: str, session_token_hash: str) -> TrialClaim:
    """Atomically reserve one of two guest searches per session and IP."""
    pool = get_pool()
    if pool is None:
        raise TrialStoreUnavailable
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Bound retention without requiring a database scheduler. Cascades
                # remove the temporary retrieval rows as well.
                await conn.execute("DELETE FROM guest_trials WHERE created_at < now() - interval '30 days'")
                # Lock both counters in a deterministic order. Locking only the IP
                # lets the same session race through multiple proxy addresses.
                for lock_key in sorted((f"guest-ip:{ip_hash}", f"guest-session:{session_token_hash}")):
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", lock_key)
                row = await conn.fetchrow(
                    """
                    INSERT INTO guest_trials (ip_hash, session_token_hash)
                    SELECT $1, $2
                    WHERE (SELECT count(*) FROM guest_trials
                           WHERE ip_hash = $1 AND created_at > NOW() - INTERVAL '24 hours') < $4
                      AND (SELECT count(*) FROM guest_trials
                           WHERE session_token_hash = $2 AND created_at > NOW() - INTERVAL '30 days') < $3
                    RETURNING id
                    """,
                    ip_hash,
                    session_token_hash,
                    _GUEST_SEARCH_LIMIT,
                    _IP_ABUSE_LIMIT,
                )
                return TrialClaim(row is not None, uuid.UUID(str(row["id"])) if row else None)
    except Exception as exc:
        logger.warning("guest trial record failed (%s)", exc.__class__.__name__)
        raise TrialStoreUnavailable from exc


async def _refund_trial(ip_hash: str, claim_id: uuid.UUID) -> None:
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", ip_hash)
                await conn.execute("DELETE FROM guest_trials WHERE id = $1 AND ip_hash = $2", claim_id, ip_hash)
    except Exception:
        logger.warning("guest trial refund failed")


async def _persist_guest_results(
    claim_id: uuid.UUID,
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
    chunks: list[dict],
    explanations: dict[str, str],
) -> None:
    pool = get_pool()
    if pool is None:
        raise TrialStoreUnavailable
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """UPDATE guest_trials
                   SET query=$2, filters=$3::jsonb, result_count=$4,
                       completed_at=now(), transfer_pending_at=now(),
                       transfer_lease_until=now() + interval '90 seconds'
                   WHERE id=$1""",
                claim_id,
                query,
                json.dumps({"collections": collections, "translation": translation, "quota": quota}),
                len(chunks),
            )
            if chunks:
                await conn.executemany(
                    """INSERT INTO guest_trial_retrievals
                       (guest_trial_id, chunk_id, rank, reranker_score, explanation)
                       VALUES ($1,$2,$3,$4,$5) ON CONFLICT (guest_trial_id, chunk_id) DO NOTHING""",
                    [
                        (
                            claim_id,
                            uuid.UUID(str(chunk["chunk_id"])),
                            rank,
                            chunk.get("reranker_score"),
                            explanations.get(str(chunk["chunk_id"]), "")[:2000],
                        )
                        for rank, chunk in enumerate(chunks, start=1)
                    ],
                )


async def _finalize_guest_results(
    claim_id: uuid.UUID,
    session_token_hash: str,
    explanations: dict[str, str],
) -> None:
    """Persist final explanations and make this search atomically claimable."""
    pool = get_pool()
    if pool is None:
        raise TrialStoreUnavailable
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"guest-session:{session_token_hash}",
            )
            owns_transfer = await conn.fetchval(
                """SELECT EXISTS (
                       SELECT 1 FROM guest_trials
                       WHERE id=$1 AND session_token_hash=$2
                         AND claimed_by IS NULL AND transfer_ready_at IS NULL
                         AND transfer_pending_at IS NOT NULL
                   )""",
                claim_id,
                session_token_hash,
            )
            if not owns_transfer:
                raise GuestTransferOwnershipLost
            if explanations:
                await conn.executemany(
                    """UPDATE guest_trial_retrievals SET explanation=$3
                       WHERE guest_trial_id=$1 AND chunk_id=$2""",
                    [
                        (claim_id, uuid.UUID(chunk_id), text[:2000])
                        for chunk_id, text in explanations.items()
                    ],
                )
            await conn.execute(
                """UPDATE guest_trials
                   SET transfer_ready_at=now(), transfer_failed_at=NULL,
                       transfer_pending_at=NULL, transfer_lease_until=NULL
                   WHERE id=$1 AND session_token_hash=$2 AND completed_at IS NOT NULL
                     AND claimed_by IS NULL AND transfer_pending_at IS NOT NULL""",
                claim_id,
                session_token_hash,
            )


async def _refresh_guest_transfer_lease(claim_id: uuid.UUID, session_token_hash: str) -> bool:
    pool = get_pool()
    if pool is None:
        raise TrialStoreUnavailable
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"guest-session:{session_token_hash}",
            )
            refreshed = await conn.fetchval(
                """UPDATE guest_trials
                   SET transfer_lease_until=now() + interval '90 seconds'
                   WHERE id=$1 AND session_token_hash=$2
                     AND claimed_by IS NULL AND transfer_pending_at IS NOT NULL
                     AND transfer_ready_at IS NULL
                   RETURNING true""",
                claim_id,
                session_token_hash,
            )
            return bool(refreshed)


async def _mark_guest_transfer_failed(claim_id: uuid.UUID, session_token_hash: str) -> None:
    """Keep displayed results recoverable instead of deleting them on finalize failure."""
    pool = get_pool()
    if pool is None:
        raise TrialStoreUnavailable
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"guest-session:{session_token_hash}",
            )
            await conn.execute(
                """UPDATE guest_trials SET transfer_failed_at=now()
                                          , transfer_lease_until=NULL
                   WHERE id=$1 AND session_token_hash=$2
                     AND claimed_by IS NULL AND transfer_pending_at IS NOT NULL
                     AND completed_at IS NOT NULL AND transfer_ready_at IS NULL""",
                claim_id,
                session_token_hash,
            )


async def _produce_guest_events(
    queue: asyncio.Queue[str | Exception | None],
    *,
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
    ip_hash: str,
    session_token_hash: str,
    claim: TrialClaim,
) -> None:
    """Own the paid pipeline lifecycle independently of the browser connection."""
    refund = False
    persisted = False
    chunks: list[dict] = []
    explanations: dict[str, str] = {}
    done_event: dict | None = None
    last_lease_refresh = time.monotonic()
    try:
        async for event in run_search_pipeline(query=query, collections=collections, translation=translation, quota=quota, user_id=None):
            if event.get("type") == "chunk":
                chunks.append(event)
            elif event.get("type") == "explanation_delta":
                chunk_id = str(event.get("chunk_id"))
                explanations[chunk_id] = explanations.get(chunk_id, "") + str(event.get("delta", ""))
                if persisted and claim.claim_id is not None and time.monotonic() - last_lease_refresh >= 30:
                    try:
                        if not await _refresh_guest_transfer_lease(claim.claim_id, session_token_hash):
                            raise GuestTransferOwnershipLost
                        last_lease_refresh = time.monotonic()
                    except Exception as lease_exc:
                        logger.warning("guest transfer lease refresh failed (%s)", lease_exc.__class__.__name__)
            elif event.get("type") == "error":
                refund = True
            elif event.get("type") == "done" and claim.claim_id is not None:
                await _persist_guest_results(claim.claim_id, query, collections, translation, quota, chunks, explanations)
                persisted = True
                done_event = event
                await queue.put(f"data: {json.dumps({'type': 'results_ready', 'result_count': len(chunks)})}\n\n")
                continue
            await queue.put(f"data: {json.dumps(event)}\n\n")
        if not refund and claim.claim_id is not None:
            if not persisted or done_event is None:
                raise RuntimeError("Guest pipeline ended without a completion event")
            await _finalize_guest_results(claim.claim_id, session_token_hash, explanations)
            # A browser-visible completion now guarantees the search is already
            # transfer-ready; later navigation cannot race account creation.
            await queue.put(f"data: {json.dumps(done_event)}\n\n")
    except GuestTransferOwnershipLost:
        # Account claim recovered this expired lease first. It now owns the
        # durable copy, so this producer must not finalize or emit `done`.
        logger.info("guest transfer producer lost ownership before finalization")
    except asyncio.CancelledError:
        if persisted and claim.claim_id is not None:
            await asyncio.shield(_mark_guest_transfer_failed(claim.claim_id, session_token_hash))
        else:
            refund = True
        raise
    except Exception as exc:
        if persisted and claim.claim_id is not None:
            try:
                await _mark_guest_transfer_failed(claim.claim_id, session_token_hash)
            except Exception as mark_exc:
                logger.error("could not mark guest transfer failure (%s)", mark_exc.__class__.__name__)
        else:
            refund = True
        await queue.put(exc)
    finally:
        if refund and claim.claim_id is not None:
            await asyncio.shield(_refund_trial(ip_hash, claim.claim_id))
        await asyncio.shield(queue.put(None))


async def _stream_guest_events(**kwargs):
    """Stream events while allowing server-owned completion after disconnect."""
    queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
    task = asyncio.create_task(_produce_guest_events(queue, **kwargs))
    _background_guest_tasks.add(task)
    task.add_done_callback(_background_guest_tasks.discard)
    while True:
        item = await queue.get()
        if item is None:
            return
        if isinstance(item, Exception):
            raise item
        yield item


async def drain_guest_search_tasks(timeout_seconds: float = 30.0) -> None:
    """Finish active guest pipelines before search and DB clients are closed."""
    tasks = list(_background_guest_tasks)
    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
    if pending:
        logger.warning("cancelling %d guest search task(s) after shutdown grace period", len(pending))
        for task in pending:
            task.cancel()
    await asyncio.gather(*done, *pending, return_exceptions=True)


@router.post("/search/guest")
async def guest_search(body: GuestSearchRequest, request: Request) -> StreamingResponse:
    ip_hash = _hash_ip(_get_client_ip(request))
    token_hash = _hash_session_token(body.session_token)
    try:
        claim = await _try_record_trial(ip_hash, token_hash)
    except TrialStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="Guest search is temporarily unavailable.") from exc
    if not claim.allowed:
        raise HTTPException(status_code=429, detail="trial_exhausted")

    translation = body.filters.translation if body.filters.translation in _VALID_TRANSLATIONS else "CPDV"
    quota = max(1, min(body.quota, _GUEST_QUOTA))
    return StreamingResponse(
        _stream_guest_events(
            query=body.query,
            collections=body.filters.collections,
            translation=translation,
            quota=quota,
            ip_hash=ip_hash,
            session_token_hash=token_hash,
            claim=claim,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/guest/claim", response_model=ClaimGuestSessionResponse)
async def claim_guest_session(
    body: ClaimGuestSessionRequest,
    user: AuthUser = Depends(get_current_user),
) -> ClaimGuestSessionResponse:
    """Atomically transfer one guest session to its newly authenticated owner."""
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    token_hash = _hash_session_token(body.session_token)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"guest-session:{token_hash}",
                )
                incomplete = await conn.fetchval(
                    """SELECT EXISTS (
                           SELECT 1 FROM guest_trials
                           WHERE session_token_hash=$1 AND transfer_ready_at IS NULL
                             AND claimed_by IS NULL
                             AND created_at > now() - interval '30 days'
                       )""",
                    token_hash,
                )
                if incomplete:
                    # A displayed search whose final explanation transaction failed
                    # remains transferable with an explicit fallback rather than
                    # being deleted or silently imported with blank explanations.
                    failed_trials = await conn.fetch(
                        """SELECT id FROM guest_trials
                           WHERE session_token_hash=$1
                             AND transfer_ready_at IS NULL AND claimed_by IS NULL
                             AND (
                               transfer_failed_at IS NOT NULL
                               OR (
                                 transfer_pending_at IS NOT NULL
                                 AND transfer_lease_until < now()
                               )
                             )
                             AND created_at > now() - interval '30 days'
                           FOR UPDATE""",
                        token_hash,
                    )
                    for failed_trial in failed_trials:
                        await conn.execute(
                            """UPDATE guest_trial_retrievals
                               SET explanation=CASE
                                   WHEN explanation IS NULL OR explanation='' THEN
                                     'Explanation unavailable — please read the passage directly.'
                                   ELSE explanation
                               END
                               WHERE guest_trial_id=$1""",
                            failed_trial["id"],
                        )
                        await conn.execute(
                            """UPDATE guest_trials
                               SET transfer_ready_at=now(), transfer_pending_at=NULL,
                                   transfer_lease_until=NULL
                               WHERE id=$1 AND session_token_hash=$2
                                 AND transfer_ready_at IS NULL AND claimed_by IS NULL""",
                            failed_trial["id"],
                            token_hash,
                        )
                    incomplete = await conn.fetchval(
                        """SELECT EXISTS (
                               SELECT 1 FROM guest_trials
                               WHERE session_token_hash=$1 AND transfer_ready_at IS NULL
                                 AND claimed_by IS NULL
                                 AND created_at > now() - interval '30 days'
                           )""",
                        token_hash,
                    )
                if incomplete:
                    raise HTTPException(status_code=409, detail="Guest search is still completing")
                claimed_owner = await conn.fetchval(
                    """SELECT claimed_by FROM guest_trials
                       WHERE session_token_hash=$1 AND claimed_by IS NOT NULL
                         AND created_at > now() - interval '30 days'
                       ORDER BY claimed_at DESC LIMIT 1""",
                    token_hash,
                )
                if claimed_owner is not None and claimed_owner != uuid.UUID(user.user_id):
                    raise HTTPException(
                        status_code=409,
                        detail="This trial activity was already transferred to another account.",
                    )
                trials = await conn.fetch(
                    """SELECT id, query, filters, result_count, created_at
                       FROM guest_trials
                       WHERE session_token_hash=$1 AND transfer_ready_at IS NOT NULL AND claimed_by IS NULL
                         AND created_at > now() - interval '30 days'
                       ORDER BY created_at ASC FOR UPDATE""",
                    token_hash,
                )
                imported = 0
                allowed_chunks: set[uuid.UUID] = set()
                for trial in trials[:_GUEST_SEARCH_LIMIT]:
                    search_id = uuid.uuid4()
                    await conn.execute(
                        """INSERT INTO searches (id,user_id,query,filters,result_count,created_at)
                           VALUES ($1,$2,$3,$4::jsonb,$5,$6)""",
                        search_id, uuid.UUID(user.user_id), trial["query"],
                        json.dumps(trial["filters"]) if isinstance(trial["filters"], dict) else trial["filters"],
                        trial["result_count"], trial["created_at"],
                    )
                    retrievals = await conn.fetch(
                        """SELECT chunk_id, rank, reranker_score, explanation
                           FROM guest_trial_retrievals WHERE guest_trial_id=$1 ORDER BY rank""",
                        trial["id"],
                    )
                    allowed_chunks.update(row["chunk_id"] for row in retrievals)
                    if retrievals:
                        await conn.executemany(
                            """INSERT INTO retrievals (id,search_id,chunk_id,rank,reranker_score,explanation)
                               VALUES ($1,$2,$3,$4,$5,$6)""",
                            [(uuid.uuid4(), search_id, row["chunk_id"], row["rank"], row["reranker_score"], row["explanation"]) for row in retrievals],
                        )
                    imported += 1
                requested = set(body.saved_chunk_ids) & allowed_chunks
                for chunk_id in requested:
                    await conn.execute(
                        """INSERT INTO bookmarks (user_id,chunk_id) VALUES ($1,$2)
                           ON CONFLICT (user_id,chunk_id) DO NOTHING""",
                        uuid.UUID(user.user_id), chunk_id,
                    )
                if trials:
                    await conn.execute(
                        """UPDATE guest_trials SET claimed_by=$2, claimed_at=now()
                           WHERE session_token_hash=$1 AND claimed_by IS NULL
                             AND transfer_ready_at IS NOT NULL
                             AND created_at > now() - interval '30 days'""",
                        token_hash, uuid.UUID(user.user_id),
                    )
        return ClaimGuestSessionResponse(searches_imported=imported, passages_saved=len(requested))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("guest session claim failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Could not transfer guest activity") from exc
