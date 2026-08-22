"""Relevance explanation streaming via OpenAI — moves stream_explanation() here unchanged."""
import asyncio
import logging
from collections.abc import AsyncGenerator

import openai

from app.config import settings
from app.rag.steps.passage_role import display_role

logger = logging.getLogger(__name__)

_client: openai.AsyncOpenAI | None = None

_EXPLAIN_SYSTEM = (
    "You are explaining how a specific passage is relevant to a user's question. "
    "Be faithful to what the passage actually says — do not misrepresent or exaggerate its content. "
    "You may draw on theological knowledge and context to explain how the passage connects to the "
    "question, but the connection must be honest: do not claim the passage addresses something it does not.\n\n"
    "Length: 1 sentence if the passage is only tangentially related or addresses the question "
    "indirectly; 2-3 sentences if it directly addresses the question with substance. "
    "Err toward 1 sentence when in doubt.\n\n"
    "Lead with the theological point — state what the passage contributes, then how that applies "
    "to the question. Do not open with any framing device that describes the relationship instead "
    "of stating it: avoid 'This passage...', 'The passage states...', 'That connects to...', "
    "'This relates to...', 'In relation to the question...', or any variant. Say the thing directly.\n\n"
    "If the connection is weak or indirect, your single sentence must name the limitation plainly. "
    "Do not pad with general theological statements that are not grounded in what the passage "
    "actually says.\n\n"
    "Write plain prose. No markdown, no headings, no bullet points.\n\n"
    "PASSAGE ROLE: the passage header may name its role inside its document. When "
    "that role is 'Objection N', the passage is a position the author states IN "
    "ORDER TO REFUTE — it argues AGAINST the conclusion the author reaches. Never "
    "present it as what the author teaches or what the Church holds. Say whose "
    "argument it is and that it is the view being answered (e.g. \"an objection "
    "Aquinas raises in order to reject\"). 'On the contrary' quotes an authority "
    "against the objections; 'I answer that' is the author's own determination; "
    "'Reply to Objection N' is the author answering that one objection. A role that "
    "is merely a section or verse locator ('Can. 33', '§17', '4') carries no such "
    "inversion — treat those passages normally.\n\n"
    "STITCHED PASSAGES: a Summa passage may arrive with a second passage attached "
    "across a marked boundary in square brackets. The two forms are:\n"
    "  '[Objection N — Aquinas answers:]' — everything ABOVE is the objection the "
    "user matched, a position Aquinas rejects; everything BELOW is his answer. "
    "Explain what the objection argues and how he answers it. Never attribute the "
    "objection's claim to him.\n"
    "  '[Objection N, which the passage below answers:]' followed later by "
    "'[Reply to Objection N — Aquinas's reply:]' — the FIRST passage is the objection, "
    "included only as context; the passage after the second marker is what the user "
    "matched, and it is Aquinas's own reply. Explain his reply, using the objection to "
    "say what he is answering. Do not treat the objection as the matched passage.\n"
    "In both forms the two passages are different voices; never present them as one "
    "continuous argument."
)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds — cumulative waits: 1+2+4 = 7s


def init_explain() -> None:
    global _client
    # timeout bounds a hung explanation stream (already best-effort/guarded downstream).
    _client = openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=45.0)


async def close_explain() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def stream(
    chunk_content: str,
    chunk_reference: str | None,
    collection: str,
    query: str,
    unit_label: str | None = None,
) -> AsyncGenerator[str, None]:
    """Async generator that yields text deltas from the explanation as they arrive.

    Retries on rate-limit errors before any tokens are emitted (can't un-yield).
    On unrecoverable failure yields the generic fallback as a single string.
    Never raises.
    """
    fallback = "Explanation unavailable — please read the passage directly."

    if _client is None:
        logger.warning("explain client not initialized")
        yield fallback
        return

    ref_label = chunk_reference or collection
    # The role goes in the header, never appended to the passage text, so a model told
    # to "be faithful to what the passage says" cannot read it as part of the source.
    # display_role() decides whether it is worth adding at all.
    role = display_role(unit_label, ref_label)
    if role:
        ref_label = f"{ref_label} — {role}"
    user_message = f"Question: {query}\n\nPassage ({ref_label}): {chunk_content}"

    for attempt in range(_MAX_RETRIES):
        tokens_started = False
        try:
            stream_resp = await _client.chat.completions.create(
                model=settings.explain_openai_model,
                max_completion_tokens=220,
                messages=[
                    {"role": "system", "content": _EXPLAIN_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
            )
            async for chunk in stream_resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    tokens_started = True
                    yield chunk.choices[0].delta.content
            return  # stream completed successfully

        except openai.RateLimitError:
            if tokens_started or attempt == _MAX_RETRIES - 1:
                if not tokens_started:
                    logger.warning("stream rate-limited after %d retries", _MAX_RETRIES)
                    yield fallback
                return
            delay = _BASE_DELAY * (2 ** attempt)
            logger.info(
                "stream rate-limited, retrying in %.1fs (attempt %d)",
                delay, attempt + 1,
            )
            await asyncio.sleep(delay)

        except Exception as exc:
            logger.warning("stream failed (%s): %s", exc.__class__.__name__, exc)
            if not tokens_started:
                yield fallback
            return

    yield fallback


stream_explanation = stream  # backward-compat alias
