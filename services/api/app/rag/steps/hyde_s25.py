"""S2.5 HyDE strategy: genre-selected bible passages + 1 per other collection."""
from __future__ import annotations

import asyncio
import json
import logging

import anthropic

from app.config import settings
from app.rag.api_keys import get_client, get_key_for, get_semaphore
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.embed import run as embed_run
from app.rag.steps import degradation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default prompt (non-Bible, unknown collection)
# ---------------------------------------------------------------------------

_HYDE_SYSTEM_DEFAULT = (
    "You are a Catholic theology expert. Given a question, write a passage of "
    "approximately 150 words from whichever authoritative Catholic source would "
    "most naturally address it — Scripture, Catechism, Church Fathers, or a "
    "Magisterial document. Choose the source type based on what kind of answer the "
    "question calls for: a doctrinal question calls for catechism or encyclical "
    "style, a scriptural question calls for biblical prose, a devotional question "
    "may call for patristic voice. Write in the authentic voice and style of that "
    "source — formal and archaic where appropriate. Do not use modern paraphrase. "
    "Return only the passage text. Do not include any attribution, labels, headings, "
    "or explanation."
)

# ---------------------------------------------------------------------------
# Bible: free-form prompt (unconstrained — goes wherever the query leads)
# ---------------------------------------------------------------------------

_HYDE_BIBLE_FREE_PROMPT = (
    "You are a biblical scholar. Given a question, write a passage of approximately "
    "120-150 words from whichever part of the Bible would most naturally and directly "
    "address it. Choose the book, genre, and style entirely on the basis of what fits "
    "the question best — Psalms, wisdom literature, prophecy, Gospel narrative, "
    "epistle, or OT story. Write in the authentic voice of that genre and in the "
    "formal, archaic prose of a traditional biblical translation (Douay-Rheims or "
    "King James register). Return only the passage text. Do not include book names, "
    "verse numbers, headings, or attribution."
)

# ---------------------------------------------------------------------------
# Bible: genre detection
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Bible: per-genre HyDE prompts
# ---------------------------------------------------------------------------

_HYDE_PSALMS_PROMPT = (
    "Write a passage of approximately 120-150 words in the style of the Psalms that "
    "would directly address the following question. The passage should read like a "
    "psalm — a psalm of praise (celebrating God's character or deeds), lament (crying "
    "out from distress with hope), trust, or thanksgiving. Use the distinctive "
    "vocabulary of the Psalms: steadfast love, refuge, fortress, shepherd, the LORD "
    "reigns, my soul, I will sing, praise the LORD, everlasting, enemies, deliver. "
    "Use parallelism: the second line restates or develops the first. Use the formal, "
    "archaic prose of a traditional biblical translation (Douay-Rheims or King James "
    "register). Return only the passage text. Do not include psalm numbers, headings, "
    "or attribution."
)

_HYDE_OT_WISDOM_PROMPT = (
    "Write a passage of approximately 120-150 words in the style of Old Testament "
    "wisdom literature (Proverbs, Ecclesiastes, Sirach, Wisdom of Solomon, or Job's "
    "dialogues) that would directly address the following question. The passage should "
    "read like wisdom teaching — aphoristic sayings about human nature, the fear of "
    "the Lord as the beginning of wisdom, the contrast between the wise and the "
    "foolish, the vanity of earthly things, or practical moral instruction. Use the "
    "characteristic vocabulary: fear of the Lord, folly, prudence, understanding, "
    "instruction, vanity, the way of the righteous. Use the formal, archaic prose of "
    "a traditional biblical translation. Return only the passage text. Do not include "
    "chapter headings, verse numbers, or attribution."
)

_HYDE_OT_PROPHETS_PROMPT = (
    "Write a passage of approximately 120-150 words in the style of an Old Testament "
    "prophetic book (Isaiah, Jeremiah, Ezekiel, or one of the twelve minor prophets) "
    "that would directly address the following question. The passage should read like "
    "a prophetic oracle — often opening with 'Thus says the LORD' or 'Hear, O Israel,' "
    "declaring God's word about sin and judgment, covenant faithfulness, restoration "
    "and hope, the coming Messiah, or social justice. Use the distinctive register: "
    "'says the LORD of hosts,' the remnant, the servant of the LORD, 'in that day,' "
    "covenant, restoration. Use the formal, archaic prose of a traditional biblical "
    "translation. Return only the passage text. Do not include book names, chapter "
    "headings, or attribution."
)

_HYDE_OT_STORIES_PROMPT = (
    "Write a passage of approximately 120-150 words in the style of an Old Testament "
    "narrative (Genesis, Exodus, Samuel, Kings, or similar historical books) that "
    "would directly address the following question. The passage should read like a "
    "biblical narrative episode involving figures such as Adam and Eve, Abraham, "
    "Moses, David, Solomon, or the patriarchs and kings of Israel. The narrative "
    "voice is simple, direct, and spare: 'And the LORD said...,' 'And he arose...,' "
    "'And it came to pass...'. The passage may show God acting in history, testing "
    "faith, making covenant, or delivering his people. Use the formal, archaic prose "
    "of a traditional biblical translation (Douay-Rheims or King James register). "
    "Return only the passage text. Do not include chapter headings, verse numbers, "
    "or attribution."
)

_HYDE_NT_STORIES_PROMPT = (
    "Write a passage of approximately 120-150 words in the style of a New Testament "
    "narrative (the Gospels or Acts of the Apostles) that would directly address the "
    "following question. The passage should read like a Gospel episode or Acts scene — "
    "a healing, a miracle, an encounter between Jesus and a person, a scene from the "
    "Passion or Resurrection, or an event from the early Church. The narrative voice "
    "is direct and spare, as in the Synoptic Gospels: 'And Jesus said...,' 'And he "
    "came...,' 'And it came to pass...'; or the more reflective voice of John. Use "
    "the formal, archaic prose of a traditional biblical translation. Return only the "
    "passage text. Do not include chapter headings, verse numbers, or attribution."
)

_HYDE_NT_EPISTLES_PROMPT = (
    "Write a passage of approximately 120-150 words in the style of a New Testament "
    "epistle that would directly address the following question. The passage should "
    "read like a section of a Pauline letter (Romans, Corinthians, Galatians, "
    "Ephesians, Philippians, Colossians, Thessalonians) or a general epistle (James, "
    "Peter, John, Jude) — a theological argument, a doctrinal exposition, or a "
    "pastoral exhortation. Use the vocabulary and cadence of the epistles: grace, "
    "tribulation, endurance, sanctification, justification, glory, hope, sharing in "
    "Christ's sufferings, bearing one another's burdens, the Spirit interceding, the "
    "groaning of creation. Use the formal, archaic prose of a traditional biblical "
    "translation (Douay-Rheims or King James register). Return only the passage text. "
    "Do not include verse numbers, chapter headings, book names, or attribution."
)

_HYDE_NT_TEACHINGS_PROMPT = (
    "Write a passage of approximately 120-150 words in the style of Jesus's direct "
    "teaching as recorded in the Gospels — the Sermon on the Mount, the Beatitudes, "
    "parables, discourses, or the 'I am' sayings in John — that would directly "
    "address the following question. The passage should read like Jesus speaking: "
    "'Blessed are...,' 'You have heard it said... but I say to you...,' 'The kingdom "
    "of heaven is like...,' 'I am the...,' 'Truly, truly I say to you...'. The "
    "passage represents Jesus's own words and teaching rather than narrative about "
    "him. Use the formal, archaic prose of a traditional biblical translation. Return "
    "only the passage text. Do not include chapter headings, verse numbers, or "
    "attribution."
)

_GENRE_HYDE_PROMPTS: dict[str, str] = {
    "psalms": _HYDE_PSALMS_PROMPT,
    "ot-wisdom": _HYDE_OT_WISDOM_PROMPT,
    "ot-prophets": _HYDE_OT_PROPHETS_PROMPT,
    "ot-stories": _HYDE_OT_STORIES_PROMPT,
    "nt-stories": _HYDE_NT_STORIES_PROMPT,
    "nt-epistles": _HYDE_NT_EPISTLES_PROMPT,
    "nt-teachings": _HYDE_NT_TEACHINGS_PROMPT,
}

# ---------------------------------------------------------------------------
# Non-Bible collection prompts
# ---------------------------------------------------------------------------

_COLLECTION_HYDE_PROMPTS: dict[str, str] = {
    "catechism": (
        "Write a passage of approximately 120-150 words in the style of the Catechism "
        "of the Catholic Church (CCC). The CCC has a distinctive three-part rhythm: "
        "first a doctrinal statement, then its grounding in Scripture and Tradition, "
        "then a practical or spiritual application. Numbered paragraph references (e.g. "
        "§1234) are appropriate. Use the CCC's characteristic style: formal but "
        "accessible, authoritative, cross-referencing Scripture and the Church Fathers, "
        "never polemical. The passage should directly address the question. Return only "
        "the passage text. Do not include headings, labels, or attribution."
    ),
    "encyclicals": (
        "Write a passage of approximately 180-200 words in the style of a papal "
        "encyclical. Papal encyclicals have a distinctive argumentative shape: they "
        "address a question or problem facing the faithful, invoke Scripture and/or "
        "prior Church teaching to frame the answer, develop the theological argument "
        "in flowing paragraphs, and conclude with a directive or encouragement to the "
        "faithful. The prose is elevated, formal, and authoritative — neither "
        "conversational nor academic — with the measured cadence of Latin translated "
        "into dignified English. Direct scriptural quotations are common. The passage "
        "should directly address the question. Return only the passage text. Do not "
        "include papal signature, encyclical title, attribution, or headings."
    ),
    "church-fathers": (
        "Write a passage of approximately 180-200 words in the style of an early Church "
        "Father as rendered in a Victorian-era English translation (the style of the "
        "Ante-Nicene Fathers or Nicene and Post-Nicene Fathers series). Patristic "
        "writing is characteristically dense with Scripture quotation — a theological "
        "point is rarely made without immediate reference to a Gospel verse, an epistle, "
        "or a psalm. The argument builds through scriptural exposition: cite a verse, "
        "interpret it theologically, draw a spiritual application, cite another verse. "
        "The register is formal and elevated, sometimes homiletic (addressing 'beloved' "
        "or 'brethren'), sometimes disputational, always theologically earnest. The "
        "passage should directly address the question. Return only the passage text. "
        "Do not include author name, work title, attribution, or headings."
    ),
    "summa": (
        "Write a Summa Theologiae article of approximately 180 words on the following "
        "question using the exact structure: state the question as 'Whether [proposition]...'; "
        "one objection beginning 'Objection 1. It seems that...'; the sed contra beginning "
        "'On the contrary,'; the respondeo beginning 'I answer that...' drawing distinctions "
        "using act and potency, essence and existence, will, intellect; cite Aristotle "
        "or Augustine. Close with 'Reply to Objection 1...'. "
        "Return only the article text."
    ),
    "councils": (
        "Write a passage of approximately 200-220 words in the style of an ecumenical "
        "council document. Use judgment about which style fits the question: "
        "if the question concerns a specific doctrinal definition or condemnation "
        "(heresy, sacramental validity, scripture vs. tradition), write in the style "
        "of the Council of Trent or an early ecumenical council — formal canons or "
        "decrees, often structured as 'If anyone says X, let him be anathema' or "
        "'The holy council declares that...'; "
        "if the question concerns the nature of the Church, the laity, liturgy, "
        "ecumenism, or the Church in the modern world, write in the style of Vatican "
        "II — longer pastoral paragraphs, warmer in register, developing an argument "
        "rather than issuing crisp definitions, citing Scripture and Tradition "
        "throughout. Either way: formal, authoritative, doctrinal. Return only the "
        "passage text. Do not include council name, document title, attribution, or headings."
    ),
    "medieval": (
        "Write a passage of approximately 150-180 words in the style of medieval "
        "Christian theological or devotional writing. Use judgment about register based "
        "on the question: a question about the soul, reason, or divine nature calls for "
        "philosophical prose in the tradition of Boethius or Anselm — rigorous, "
        "analytic, drawing on Platonic categories; a question about love of God, prayer, "
        "or the spiritual life calls for the affective, devotional voice of Bernard of "
        "Clairvaux or Thomas à Kempis — warm, personal, addressed directly to the soul, "
        "rich in the vocabulary of love, union, and longing. Either way: formal "
        "English, elevated register, pre-Reformation Catholic piety. Return only the "
        "passage text. Do not include author name, title, attribution, or headings."
    ),
    "canon-law": (
        "Write a passage of 3-5 canons in the style of the 1983 Code of Canon Law. "
        "Each canon follows a precise format: 'Can. [number] §[paragraph number].' and "
        "then a prescriptive legal sentence. The language is formal and unambiguous: "
        "'The Christian faithful are bound...', 'No one may lawfully...', "
        "'It is the right and duty of...', 'The competent authority shall...', "
        "'A person who commits [act] is to be punished with...'. Multiple canons on "
        "related topics are grouped with sub-paragraphs (§1, §2, §3) for different "
        "conditions or exceptions. The passage should directly address the question "
        "in prescriptive legal terms. Return only the canon text. Do not include "
        "title, section headings, attribution, or explanatory notes."
    ),
}

_BIBLE_GENRE_SELECT_SYSTEM = (
    "You are choosing which biblical genres to search for a theological query. "
    "Given a query, select the 3 genres most likely to contain directly relevant biblical passages.\n\n"
    "Available genres:\n"
    "  free        — unconstrained; picks the most fitting part of the Bible for the query\n"
    "  psalms      — Psalms: lament, praise, trust, thanksgiving, worship\n"
    "  ot-wisdom   — Proverbs, Ecclesiastes, Sirach, Job: moral instruction, fear of the Lord\n"
    "  ot-prophets — Isaiah, Jeremiah, Ezekiel, minor prophets: oracles, judgment, restoration\n"
    "  ot-stories  — Genesis, Exodus, Kings, etc.: narrative, covenant, salvation history\n"
    "  nt-stories  — Gospels and Acts: miracles, Passion, Resurrection, early Church events\n"
    "  nt-epistles — Paul and general epistles: theological argument, pastoral instruction\n"
    "  nt-teachings — Jesus's direct teaching: Sermon on the Mount, parables, I am sayings\n\n"
    "Return ONLY a JSON array of exactly 3 genre keys, e.g. [\"psalms\", \"nt-teachings\", \"free\"]. "
    "No explanation, no other text."
)

_COLLECTION_MAX_TOKENS: dict[str, int] = {
    "bible": 300,
    "catechism": 250,
    "encyclicals": 400,
    "church-fathers": 400,
    "summa": 300,
    "councils": 450,
    "medieval": 350,
    "canon-law": 350,
}
_DEFAULT_MAX_TOKENS = 300

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _generate_single(
    client: anthropic.AsyncAnthropic,
    system: str,
    query: str,
    max_tokens: int,
    cost_tracker: CostTracker | None = None,
    cost_step: str = "hyde",
) -> str | None:
    """Generate one HyDE passage and optionally record token cost."""
    try:
        response = await client.messages.create(
            model=settings.hyde_model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": query}],
        )
        if cost_tracker is not None:
            cost_tracker.record(
                cost_step, settings.hyde_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        return response.content[0].text
    except Exception as exc:
        logger.warning("HyDE passage generation failed: %s", exc)
        degradation.record(
            "hyde", type(exc).__name__, "passage_omitted",
            details={"message": str(exc)[:300]},
        )
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def choose_bible_hyde_genres(
    query: str,
    client: anthropic.AsyncAnthropic,
    k: int = 3,
) -> list[str]:
    """Pre-select k bible genres before any HyDE generation (S2.5).

    One Haiku call decides which genres to generate, so only k generation
    calls follow instead of all 8. Falls back to a sensible default on error.
    """
    _VALID = {"free", "psalms", "ot-wisdom", "ot-prophets", "ot-stories",
              "nt-stories", "nt-epistles", "nt-teachings"}
    _DEFAULT = ["free", "nt-epistles", "psalms"]

    try:
        response = await client.messages.create(
            model=settings.hyde_model,
            max_tokens=50,
            temperature=0,
            system=_BIBLE_GENRE_SELECT_SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        genres = json.loads(response.content[0].text.strip())
        selected = [g for g in genres if isinstance(g, str) and g in _VALID]
        if len(selected) == k:
            return selected
        logger.warning(
            "choose_bible_hyde_genres: expected %d valid genres, got %d; using defaults",
            k, len(selected),
        )
    except Exception as exc:
        logger.warning("choose_bible_hyde_genres: failed (%s); using defaults", exc)

    return _DEFAULT[:k]


async def generate_hyde_passages(
    query: str,
    collection: str | None,
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
    selected_genres: list[str] | None = None,
    cost_tracker: CostTracker | None = None,
) -> list[str]:
    """Return hypothetical passages for the given collection, tracking LLM cost."""
    max_tokens = _COLLECTION_MAX_TOKENS.get(collection or "", _DEFAULT_MAX_TOKENS)

    if collection == "bible":
        all_bible_prompts: dict[str, str] = {"free": _HYDE_BIBLE_FREE_PROMPT, **_GENRE_HYDE_PROMPTS}
        prompts = (
            {g: all_bible_prompts[g] for g in selected_genres if g in all_bible_prompts}
            if selected_genres
            else all_bible_prompts
        )

        async def _guarded(system: str) -> str | None:
            async with semaphore:
                return await _generate_single(client, system, query, max_tokens,
                                              cost_tracker=cost_tracker, cost_step="hyde")

        results = await asyncio.gather(*[_guarded(p) for p in prompts.values()])
        return [r for r in results if r is not None]

    system = _COLLECTION_HYDE_PROMPTS.get(collection or "", _HYDE_SYSTEM_DEFAULT)
    async with semaphore:
        result = await _generate_single(client, system, query, max_tokens,
                                        cost_tracker=cost_tracker, cost_step="hyde")
    return [result] if result is not None else []


async def run(
    query: str,
    collections: list[str],
    cost_tracker: CostTracker,
) -> dict[str, list[list[float]]]:
    """Generate HyDE passages and embed them per collection.

    Returns dict[collection, list[embedding_vectors]].
    Bible gets 3 vectors (1 selector call + 3 genre generators).
    Each other collection gets 1 vector.
    """
    async def _hyde_and_embed(col: str) -> tuple[str, list[list[float]]]:
        key = get_key_for(col)
        client = get_client(key)
        semaphore = get_semaphore(key)

        if col == "bible":
            response = await client.messages.create(
                model=settings.hyde_model,
                max_tokens=50,
                temperature=0,
                system=_BIBLE_GENRE_SELECT_SYSTEM,
                messages=[{"role": "user", "content": query}],
            )
            cost_tracker.record(
                "hyde_genre_select", settings.hyde_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            try:
                _VALID = {"free", "psalms", "ot-wisdom", "ot-prophets", "ot-stories",
                          "nt-stories", "nt-epistles", "nt-teachings"}
                genres = json.loads(response.content[0].text.strip())
                selected = [g for g in genres if isinstance(g, str) and g in _VALID]
                if len(selected) != 3:
                    selected = ["free", "nt-epistles", "psalms"]
            except Exception:
                degradation.record(
                    "hyde_genre_select", "invalid_response", "defaults_used",
                    scope="bible",
                )
                selected = ["free", "nt-epistles", "psalms"]
            passages = await generate_hyde_passages(
                query, col, client, semaphore, selected_genres=selected,
                cost_tracker=cost_tracker,
            )
        else:
            passages = await generate_hyde_passages(
                query, col, client, semaphore, cost_tracker=cost_tracker,
            )

        if not passages:
            return col, []
        embed_results = await asyncio.gather(
            *[embed_run(p, cost_tracker) for p in passages],
            return_exceptions=True,
        )
        for result in embed_results:
            if isinstance(result, BaseException):
                degradation.record(
                    "hyde_embed", type(result).__name__, "vector_omitted",
                    scope=col, details={"message": str(result)[:300]},
                )
        vecs = [v for v in embed_results if not isinstance(v, BaseException)]
        return col, vecs

    results = await asyncio.gather(
        *[_hyde_and_embed(col) for col in collections],
        return_exceptions=True,
    )
    output: dict[str, list[list[float]]] = {}
    for item in results:
        if isinstance(item, BaseException):
            logger.warning("hyde_s25: collection failed: %s", item)
            degradation.record(
                "hyde", type(item).__name__, "collection_omitted",
                details={"message": str(item)[:300]},
            )
            continue
        col, vecs = item
        if vecs:
            output[col] = vecs
    return output
