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
    "Write one hypothetical passage of about 100-150 words in the manner of a Catholic "
    "theological source that directly addresses the question's central subject. Choose one "
    "source form and develop its most relevant claim or concern; focus on an objection, "
    "exception, or qualification when the user asks for one. For a broad question, connect "
    "its main concepts within one coherent passage. Keep names and terms that matter when "
    "they fit the chosen form. Do not mix Scripture, catechism, and papal styles or invent "
    "titles, numbers, or exact quotations. Return only the passage, without a citation label "
    "or heading."
)

# ---------------------------------------------------------------------------
# Bible passage generation prompts
# ---------------------------------------------------------------------------

_HYDE_BIBLE_FREE_PROMPT = (
    "Write one hypothetical biblical passage of about 80-120 words that bears directly on the "
    "question. Choose the book and form most likely to address its central subject and the "
    "relationship between its main ideas. Use a question, warning, or counterexample when the "
    "user seeks one; otherwise choose the most direct biblical treatment. When a real passage "
    "or scene comes to mind, stay close to its substance and imagery rather than combining "
    "several books into one invented text. Keep relevant biblical people, places, and images "
    "from the question; express later theological terms through the closest biblical ideas. "
    "Use natural Bible-translation prose without forced archaism. Return only the passage, "
    "without a citation label, verse number, or explanation. A book name may appear within "
    "the prose if it is central to the question."
)

_HYDE_PSALMS_PROMPT = (
    "Write a psalm-like passage of about 80-120 words that addresses the question's central "
    "concern. Choose the fitting movement of prayer: lament, repentance, trust, thanksgiving, "
    "or praise. Let a complaint remain unresolved when the question calls for it. Address God "
    "through concrete images and parallel lines, as the Psalms do. Keep a relevant person, "
    "place, or image from the question when it belongs in this form. If a named event or "
    "later doctrine does not belong in a psalm, express its underlying concern through prayer "
    "without transplanting its details. Do not insert stock psalm words merely to signal the "
    "genre. Return only the passage, without a psalm number, heading, or attribution. A "
    "naturally brief prayer may be shorter."
)

_HYDE_OT_WISDOM_PROMPT = (
    "Write one passage of about 80-120 words in the manner of Old Testament wisdom "
    "literature, such as Proverbs, Job, Ecclesiastes, Wisdom, or Sirach. Choose the form that "
    "best addresses the question's central concern: a proverb, reflection, counsel, or part "
    "of a dispute about suffering and justice. Challenge an easy answer when the user asks "
    "about doubt, dispute, or an apparent exception; otherwise address the question directly. "
    "Connect the main concepts of a broad question within one coherent passage. Keep relevant "
    "names and images when they belong in the chosen form. If a named event or later doctrine "
    "does not belong in wisdom literature, express its underlying concern without "
    "transplanting its details. Do not blend these books into one generic voice. Return only "
    "the passage, without a citation label or invented title."
)

_HYDE_OT_PROPHETS_PROMPT = (
    "Write one prophetic passage of about 80-120 words that addresses the question's central "
    "concern. Draw on the concerns of Isaiah, Jeremiah, Ezekiel, the Twelve, or other "
    "prophetic books when relevant: covenant, injustice, judgment, repentance, mercy, "
    "restoration, and hope. Give the passage a warning, promise, or appeal that fits the "
    "question; use a protest when the user seeks one. Keep a relevant biblical name or place "
    "when it belongs, but do not invent an event involving it. If a named event or later "
    "doctrine belongs elsewhere, express its underlying concern through prophetic material. "
    "Use an oracle opening only if it fits; avoid stock prophetic phrases. Return only the "
    "passage, without a citation label or heading."
)

_HYDE_OT_STORIES_PROMPT = (
    "Write a concise Old Testament narrative passage of about 90-140 words based on one "
    "episode relevant to the question's central concern. It may come from Genesis, Exodus, "
    "Israel's judges and kings, or another historical book. Show the action and consequence "
    "that make the episode relevant. Let the outcome remain unsettled when the user asks "
    "about uncertainty or conflict. If the question names a biblical person, place, or event "
    "that belongs in this route, keep it. If it names something outside Old Testament "
    "narrative, choose a known episode that addresses the underlying concern. Do not invent a "
    "new deed for a named figure or combine episodes. Use direct narrative prose without "
    "forced archaic openings. Return only the passage, without a citation label or heading."
)

_HYDE_NT_STORIES_PROMPT = (
    "Write a Gospel or Acts narrative passage of about 90-140 words based on one event "
    "relevant to the question's central concern. Focus on an encounter, action, healing, "
    "Passion or Resurrection scene, or event in the early Church. Show what happens and how "
    "others respond; include resistance or uncertainty when the question calls for it. Keep a "
    "named person or event from the question when it belongs here. If the named subject "
    "belongs outside Gospel or Acts narrative, choose a known event that addresses its "
    "underlying concern. Do not invent a miracle or encounter, combine events, or replace the "
    "scene with a doctrinal summary. Return only the passage, without a citation label or "
    "heading."
)

_HYDE_NT_EPISTLES_PROMPT = (
    "Write one coherent passage of about 90-130 words in the manner of a New Testament "
    "letter. Develop the argument or exhortation that most directly addresses the question. "
    "Focus on a correction, objection, or unresolved tension when the user asks for one. For "
    "a broad question, connect its main concepts rather than treating one in isolation. Keep "
    "relevant people and theological terms when they fit the likely letter. If a named event "
    "or later doctrine does not belong in an epistle, express its underlying concern without "
    "transplanting its details. Do not pad the passage with stock terms about grace, "
    "suffering, or hope. Write as a letter to believers rather than a modern theological "
    "summary. Return only the passage, without a citation label, verse number, or "
    "attribution."
)

_HYDE_NT_TEACHINGS_PROMPT = (
    "Write a passage of about 80-120 words that paraphrases the substance of one teaching of "
    "Jesus relevant to the question's central concern. It may be a saying, parable, question, "
    "sermon, or discourse. Include a challenge or qualification when the user seeks one; "
    "otherwise choose the most direct teaching. Preserve a relevant person, image, or term "
    "when it belongs to that teaching. If a named event or later doctrine belongs outside "
    "Jesus's teaching, express its underlying concern without attributing that event or "
    "doctrine to him. If unsure of exact words or details, paraphrase the known point without "
    "inventing a claim or parable. Use natural biblical language without forced openings such "
    "as \"Blessed are\" or \"I am.\" Return only the passage, without a citation label or "
    "heading. A naturally brief saying may be shorter."
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
# Non-Bible collection passage generation prompts
# ---------------------------------------------------------------------------

_COLLECTION_HYDE_PROMPTS: dict[str, str] = {
    "catechism": (
        "Write one paragraph of about 100-140 words in the manner of the Catechism of the "
        "Catholic Church. State the teaching that most directly addresses the question; focus on "
        "a limit, distinction, or difficulty when the user asks for it. For a broad question, "
        "connect its main concepts within the paragraph. Keep named sacraments, doctrines, and "
        "other distinctive terms when they belong. Bring in Scripture, Tradition, or a practical "
        "implication only when it helps; do not force a three-part formula. Use careful "
        "distinctions rather than polemic. Do not invent a paragraph number or exact quotation. "
        "Return only the passage, without a heading or attribution. An essential name or title "
        "may appear within the prose."
    ),
    "encyclicals": (
        "Write one paragraph of about 120-170 words in the manner of a papal encyclical. Develop "
        "the theological or moral argument that most directly addresses the question. Focus on a "
        "concern or qualification when the user asks for it. For a broad question, connect its "
        "main concepts in one line of reasoning rather than reducing it to a single subtopic. "
        "Draw on Scripture, earlier Church teaching, or human experience when relevant. Keep "
        "distinctive terms and named subjects when they belong. Preserve the formal, measured "
        "voice of an encyclical without forcing a closing directive or quotation. Do not invent "
        "exact quotations or document claims. Return only the passage, without a citation label, "
        "signature, or heading. An essential title may appear within the prose."
    ),
    "church-fathers": (
        "Write one passage of about 100-150 words in the manner of an early Church Father "
        "speaking in a homily or treatise. Address the question's central concern through a "
        "concrete scriptural reading, theological distinction, or spiritual exhortation. Present "
        "an objection or disputed view when the user asks about it. For a broad question, connect "
        "its main concepts within one coherent passage. Keep a named biblical figure, doctrine, "
        "author, or work when it is essential to the subject. Scripture may shape the argument "
        "without invented verse quotations. Keep the formal, earnest voice of patristic writing "
        "without stock addresses such as \"beloved\" or \"brethren.\" Return only the passage, "
        "without an attribution label or heading."
    ),
    "summa": (
        "Write one passage of about 80-140 words in the manner of a single part of a Summa "
        "Theologiae article. When the user asks what Aquinas holds, choose the main answer or a "
        "reply. Choose an objection when the user asks for the opposing argument or why a "
        "position seems plausible; an objection may argue for a view Aquinas later rejects, so do "
        "not present it as his conclusion. A brief contrary authority is suitable when the user "
        "seeks that evidence. Keep the question's central subject and relevant technical terms; "
        "for a broad question, connect its main concepts within this one article part. Use act, "
        "potency, will, or intellect only when they belong. Do not compress several article parts "
        "into one passage or invent a citation. Return only the passage, without an article "
        "number or heading. An essential name or work may appear within the prose."
    ),
    "councils": (
        "Write one conciliar passage of about 120-170 words that directly addresses the "
        "question's central subject. Use the precise register of a decree or canon for a "
        "doctrinal definition or condemned position; use a developed pastoral register for the "
        "Church's life or mission. Focus on a condemnation, exception, or dispute when the user "
        "asks about it; otherwise develop the most relevant teaching or directive. For a broad "
        "question, connect its main concepts in one coherent passage. Keep a relevant doctrine, "
        "practice, council, or document name when it belongs in the prose, but do not invent what "
        "a named document says. Do not force the words \"let him be anathema.\" Return only the "
        "passage, without a citation label, section number, or attribution."
    ),
    "medieval": (
        "Write one passage of about 100-150 words in the manner of medieval Christian theology or "
        "devotion. Choose careful reasoning or direct meditation on prayer and the spiritual life "
        "according to the question. Develop an objection or qualification when the user asks for "
        "one. For a broad question, connect its main concepts while keeping one coherent line of "
        "thought. Keep relevant names and theological terms when they fit. Use medieval concepts "
        "when they illuminate the question, not as decoration. Return only the passage, without "
        "an attribution label or heading. An essential author or work may appear within the "
        "prose."
    ),
    "canon-law": (
        "Write one provision of about 50-100 words in the manner of a single canon of the 1983 "
        "Code of Canon Law. Express the right, duty, condition, procedure, or consequence that "
        "most directly addresses the question; focus on an exception or limit when the user asks "
        "for one. Keep a named office, sacrament, or legal term when it belongs. For a broad "
        "legal question, connect its main concepts within one rule. Add another clause only if it "
        "clarifies that rule. Do not invent a canon number, legal effect, or unrelated provision. "
        "Where exact details are uncertain, use a general legal formulation without invented "
        "specifics. Return only the provision, without a citation label or heading. A naturally "
        "brief rule may be shorter."
    ),
    "apostolic-exhortations": (
        "Write one paragraph of about 110-160 words in the manner of an apostolic exhortation. "
        "Connect the teaching most relevant to the question with Christian life; focus on a "
        "difficulty or qualification when the user asks about one. For a broad question, connect "
        "its main concepts within one pastoral line of thought. Keep distinctive terms and named "
        "subjects when they belong. Use a pastoral voice without turning every passage into a "
        "generic appeal or easy resolution. Draw on prayer, family life, holiness, "
        "evangelization, or care for others only when the subject calls for it. Do not invent "
        "what a named exhortation says. Return only the passage, without a citation label, "
        "paragraph number, or signature. An essential title may appear within the prose."
    ),
    "papal-documents": (
        "Write one paragraph of about 100-160 words in the manner of a papal letter, "
        "constitution, or bull. If the question concerns a papal act, address what it "
        "establishes, defines, directs, limits, or changes. If it concerns teaching, develop the "
        "most direct relevant claim; focus on an objection or qualification when the user asks "
        "about one. For a broad question, connect its main concepts in one coherent paragraph. "
        "Keep named offices, doctrines, and documents when they belong, but do not invent what a "
        "particular document says or does. Where exact details are uncertain, address the issue "
        "at a level that does not require invented dates or legal effects. Match the document's "
        "operative or teaching character. Return only the passage, without a citation label or "
        "signature. An essential title may appear within the prose."
    ),
}

_BIBLE_SELECTED_GENRE_COUNT = 4
_BIBLE_VALID_GENRES = {
    "free", "psalms", "ot-wisdom", "ot-prophets", "ot-stories",
    "nt-stories", "nt-epistles", "nt-teachings",
}
_BIBLE_DEFAULT_GENRES = ["free", "nt-epistles", "psalms", "nt-teachings"]

_BIBLE_GENRE_SELECT_SYSTEM = (
    "You are choosing four genres to search for a question about the Bible.\n\n"
    "For each genre you choose, another model will write a hypothetical biblical "
    "passage in that style. We will use each passage to search the entire Bible "
    "by meaning. Your choices do not restrict the search to those genres.\n\n"
    "Choose four distinct genres that, together, are likely to find relevant "
    "passages from different parts or forms of Scripture. Seek useful coverage, "
    "not four versions of the same likely answer.\n\n"
    "If the question names a book, person, event, or teaching, include the genre "
    "that best fits it. Use the remaining choices to find relevant support, "
    "contrast, or application elsewhere in Scripture. Do not force a balance "
    "between Old and New Testament when the question points strongly to one "
    "of them.\n\n"
    "Genres:\n"
    "free: A passage from any biblical book or form, guided by the question. "
    "Useful when the question crosses genres or a specific genre might miss "
    "its most direct biblical answer.\n"
    "psalms: Prayer and song addressed to God, including lament, guilt, trust, "
    "gratitude, and praise. Useful when a person's response to God matters as "
    "much as a doctrinal statement.\n"
    "ot-wisdom: Proverbs, Job, Ecclesiastes, Wisdom, and Sirach reflecting on "
    "suffering, virtue, death, justice, and daily life. Useful for counsel or "
    "sustained reflection rather than a narrated event.\n"
    "ot-prophets: God's words through the prophets about covenant, injustice, "
    "judgment, repentance, mercy, restoration, and the Messiah. Useful when a "
    "divine warning or promise could answer the question.\n"
    "ot-stories: Narratives of creation, the patriarchs, Exodus, Israel's rulers, "
    "and exile. Useful when God's actions in history or a person's choices could "
    "be helpful or informative to the user\n"
    "nt-stories: Narrated events in the Gospels and Acts, including Jesus's "
    "encounters, miracles, Passion, Resurrection, and the early Church. Useful "
    "for revealing Christ through his actions\n"
    "nt-epistles: Apostolic letters explaining Christ, grace, faith, the Church, "
    "moral life, suffering, and hope. Useful for theological argument or pastoral "
    "instruction.\n"
    "nt-teachings: Jesus's own teaching in sermons, parables, conversations, and "
    "discourses. Useful for what Jesus says and commands, rather than the event "
    "surrounding his words.\n\n"
    "Choose both nt-stories and nt-teachings only when an event and a teaching "
    "could provide meaningfully different evidence. Apply the same test to "
    "other overlapping genres.\n\n"
    "Return only a JSON array of exactly four distinct genre keys. No explanation. "
    "Example: [\"psalms\", \"ot-wisdom\", \"nt-epistles\", \"free\"]"
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
    scope: str | None = None,
) -> str | None:
    """Generate one HyDE passage and optionally record token cost."""
    try:
        response = await client.messages.create(
            model=settings.hyde_model,
            max_tokens=max_tokens,
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
            scope=scope,
            details={"message": str(exc)[:300]},
        )
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _parse_bible_genres(raw: str) -> list[str]:
    genres = json.loads(raw.strip())
    if not isinstance(genres, list):
        return []
    return list(dict.fromkeys(
        genre for genre in genres
        if isinstance(genre, str) and genre in _BIBLE_VALID_GENRES
    ))


async def choose_bible_hyde_genres(
    query: str,
    client: anthropic.AsyncAnthropic,
    k: int = _BIBLE_SELECTED_GENRE_COUNT,
) -> list[str]:
    """Pre-select k bible genres before any HyDE generation (S2.5).

    One Haiku call decides which genres to generate, so only k generation
    calls follow instead of all 8. Falls back to a sensible default on error.
    """
    try:
        response = await client.messages.create(
            model=settings.hyde_model,
            max_tokens=50,
            system=_BIBLE_GENRE_SELECT_SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        selected = _parse_bible_genres(response.content[0].text)
        if len(selected) == k:
            return selected
        logger.warning(
            "choose_bible_hyde_genres: expected %d valid genres, got %d; using defaults",
            k, len(selected),
        )
    except Exception as exc:
        logger.warning("choose_bible_hyde_genres: failed (%s); using defaults", exc)

    return _BIBLE_DEFAULT_GENRES[:k]


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
                                              cost_tracker=cost_tracker, cost_step="hyde",
                                              scope=collection)

        results = await asyncio.gather(*[_guarded(p) for p in prompts.values()])
        return [r for r in results if r is not None]

    system = _COLLECTION_HYDE_PROMPTS.get(collection or "", _HYDE_SYSTEM_DEFAULT)
    async with semaphore:
        result = await _generate_single(client, system, query, max_tokens,
                                        cost_tracker=cost_tracker, cost_step="hyde",
                                        scope=collection)
    return [result] if result is not None else []


async def run(
    query: str,
    collections: list[str],
    cost_tracker: CostTracker,
    *,
    all_bible_genres: bool = False,
) -> dict[str, list[list[float]]]:
    """Generate HyDE passages and embed them per collection.

    Returns dict[collection, list[embedding_vectors]].
    Bible normally gets 4 vectors (1 selector call + 4 genre generators).
    Focused Bible searches can request all 8 without a selector call.
    Each other collection gets 1 vector.
    """
    async def _hyde_and_embed(col: str) -> tuple[str, list[list[float]]]:
        key = get_key_for(col)
        client = get_client(key)
        semaphore = get_semaphore(key)

        if col == "bible":
            selected: list[str] | None = None
            if not all_bible_genres:
                response = await client.messages.create(
                    model=settings.hyde_model,
                    max_tokens=50,
                    system=_BIBLE_GENRE_SELECT_SYSTEM,
                    messages=[{"role": "user", "content": query}],
                )
                cost_tracker.record(
                    "hyde_genre_select", settings.hyde_model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
                try:
                    selected = _parse_bible_genres(response.content[0].text)
                    if len(selected) != _BIBLE_SELECTED_GENRE_COUNT:
                        degradation.record(
                            "hyde_genre_select", "invalid_response", "defaults_used",
                            scope="bible",
                            details={"valid_genre_count": len(selected)},
                        )
                        selected = _BIBLE_DEFAULT_GENRES
                except Exception:
                    degradation.record(
                        "hyde_genre_select", "invalid_response", "defaults_used",
                        scope="bible",
                    )
                    selected = _BIBLE_DEFAULT_GENRES
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
    for col, item in zip(collections, results):
        if isinstance(item, BaseException):
            logger.warning("hyde_s25: collection failed: %s", item)
            degradation.record(
                "hyde", type(item).__name__, "collection_omitted",
                scope=col,
                details={"message": str(item)[:300]},
            )
            continue
        col, vecs = item
        if vecs:
            output[col] = vecs
    return output
