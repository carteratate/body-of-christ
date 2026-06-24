import datetime
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.evaluate import (
    CollectionScore,
    EvaluateRequest,
    EvaluateResponse,
    ExplainRequest,
)
import app.rag.rerank as _rerank_mod

logger = logging.getLogger(__name__)

router = APIRouter()

_DAILY_EVALUATE_LIMIT = 10

# Shared system prompt — cached for both Phase 1 (scores) and Phase 2 (explain).
_EVALUATE_SYSTEM = (
    "You are evaluating which Catholic theological source collections are most "
    "likely to contain passages that directly answer a user's question. You have "
    "access to exactly 10 collections. Score each 0.0–1.0 and provide a 1–2 "
    "sentence explanation.\n\n"
    "IMPORTANT: You are scoring the LIKELIHOOD that each collection contains "
    "relevant passages, not generating those passages. Base your assessment on "
    "the content and scope described below.\n\n"
    "COLLECTION DESCRIPTIONS:\n\n"
    '1. "bible" — The complete 73-book Catholic biblical canon in the World '
    "English Bible — Catholic Edition (WEB-C) translation. Includes all 46 "
    "Old Testament books (protocanonical + 7 deuterocanonicals: Tobit, Judith, "
    "1 & 2 Maccabees, Wisdom, Sirach, Baruch) and 27 New Testament books. "
    "Chunked by pericope (named passage units for the 66 protocanonical books) "
    "or by chapter (deuterocanonicals). Coverage spans: Pentateuch law and "
    "narrative, historical books, wisdom literature (Job, Proverbs, "
    "Ecclesiastes, Song of Solomon, Wisdom, Sirach), Psalms, prophetic books "
    "(major and minor), the four Gospels, Acts, Pauline and general epistles, "
    "and Revelation.\n"
    "STRONGEST FOR: scriptural foundations of any doctrine, moral teaching "
    "rooted in Scripture, prayer/devotion from Psalms and wisdom, Jesus's "
    "direct teachings and parables, Pauline theology, Old Testament typology, "
    "prophetic and apocalyptic literature.\n\n"
    '2. "catechism" — The complete Catechism of the Catholic Church (CCC), '
    "paragraphs §1–§2865. Organized into four pillars: the Profession of Faith "
    "(Creed), the Celebration of the Christian Mystery (Sacraments), Life in "
    "Christ (Moral teaching and the Commandments), and Christian Prayer "
    "(including commentary on the Our Father). Each chunk is a page-level "
    "section containing numbered CCC paragraphs with cross-references to "
    "Scripture and the Church Fathers.\n"
    'STRONGEST FOR: "What does the Church teach about X?" questions, systematic '
    "doctrinal definitions, sacramental theology, moral theology organized by "
    "the Commandments, the theological virtues, and prayer.\n\n"
    '3. "summa" — The complete Summa Theologiae by St. Thomas Aquinas (1265–1274). '
    "Structured as: First Part (God, creation, angels, man), First Part of the "
    "Second Part (happiness, human acts, habits, virtues, vices, law, grace), "
    "Second Part of the Second Part (faith, hope, charity, prudence, justice, "
    "fortitude, temperance, specific moral questions), and Third Part "
    "(Incarnation, sacraments). Each article follows the dialectical structure: "
    'Objections, Sed Contra, Respondeo ("I answer that..."), and Replies to '
    "Objections. Cites Aristotle (\"the Philosopher\"), Augustine, and Scripture "
    "extensively.\n"
    "STRONGEST FOR: rigorous philosophical theology, virtue and vice analysis, "
    "natural law, the nature and attributes of God, the soul and intellect, "
    "sacramental theology grounded in metaphysics, questions that benefit from "
    "systematic dialectical reasoning using act/potency, form/matter, "
    "essence/existence distinctions.\n\n"
    '4. "encyclicals" — 131 papal encyclicals spanning 1740–2025, from Pope '
    "Benedict XIV through Pope Leo XIV. Major encyclicals include: Rerum "
    "Novarum (labor/social justice), Humanae Vitae (contraception/marriage), "
    "Fides et Ratio (faith and reason), Laudato Si' (environment/creation "
    "care), Veritatis Splendor (moral theology), Evangelium Vitae (sanctity "
    "of life), Deus Caritas Est (love), Redemptor Hominis (Christ the "
    "Redeemer), Mit Brennender Sorge (against Nazism), Divini Redemptoris "
    "(against communism), Mystici Corporis Christi (the Church as Body of "
    "Christ), Mediator Dei (sacred liturgy).\n"
    "STRONGEST FOR: Catholic social teaching, papal responses to modern moral "
    "questions, faith and reason, marriage and family, economic justice, "
    "dignity of human life, the Church's engagement with the modern world, "
    "liturgical theology.\n\n"
    '5. "councils" — Documents from all 20 ecumenical councils (Nicaea I in 325 '
    "through Vatican I in 1870) plus 16 Vatican II documents (4 constitutions: "
    "Dei Verbum, Lumen Gentium, Sacrosanctum Concilium, Gaudium et Spes; 9 "
    "decrees; 3 declarations including Nostra Aetate and Dignitatis Humanae). "
    "Earlier councils are canons and anathemas; Vatican II is pastoral prose.\n"
    "STRONGEST FOR: dogmatic definitions (Trinity, Christology, canon of "
    "Scripture), sacramental validity, Church governance, ecumenism, religious "
    "liberty, liturgical reform, the nature of the Church, responses to "
    "historical heresies (Arianism, Nestorianism, Pelagianism, Protestant "
    "Reformation doctrines).\n\n"
    '6. "church-fathers" — Works from the Ante-Nicene and Nicene/Post-Nicene '
    "Fathers series (CCEL editions). Includes major works by Augustine "
    "(Confessions, City of God, On the Holy Trinity), Athanasius (On the "
    "Incarnation), and other patristic authors from the ANF/NPNF volumes. "
    "Dense with Scripture quotation and theological interpretation.\n"
    "STRONGEST FOR: early Church interpretation of Scripture, patristic "
    "theology of the Trinity and Incarnation, development of doctrine in the "
    "first centuries, anti-heretical arguments, spiritual and devotional "
    "writings from the Fathers, Augustinian theology (grace, original sin, "
    "the two cities, the Trinity).\n\n"
    '7. "medieval" — Medieval theological and devotional texts from the CCEL '
    "collection. Includes authors such as Anselm (Proslogion, Cur Deus Homo, "
    "Monologion), Boethius (Consolation of Philosophy), Bernard of Clairvaux, "
    "and Thomas à Kempis (Imitation of Christ). Ranges from rigorous "
    "philosophical theology (ontological argument, divine attributes) to "
    "affective devotional writing (love of God, prayer, spiritual life).\n"
    "STRONGEST FOR: medieval philosophical theology, the ontological argument "
    "for God's existence, atonement theory, devotional spirituality, mystical "
    "theology, the relationship between faith and reason in the medieval "
    "period.\n\n"
    '8. "canon-law" — The complete 1983 Code of Canon Law (Codex Iuris '
    "Canonici), canons 1–1752, organized into 7 books: General Norms, The "
    "People of God, The Teaching Function, The Sanctifying Function, Temporal "
    "Goods, Sanctions, and Processes. One passage per canon. Prescriptive "
    "legal language defining rights, duties, and procedures.\n"
    "STRONGEST FOR: Church law and governance, sacramental requirements "
    "(marriage validity, baptism, ordination), rights and obligations of the "
    "faithful, ecclesiastical offices, penal law, tribunal procedures, "
    "religious life regulations.\n\n"
    '9. "apostolic-exhortations" — 30 post-synodal apostolic exhortations from '
    "1908–2025 (Pope Pius X through Pope Leo XIV). Includes Familiaris "
    "Consortio (family), Evangelii Gaudium (joy of the Gospel), Amoris "
    "Laetitia (love in the family), Christifideles Laici (lay faithful), "
    "Vita Consecrata (consecrated life), Pastores Dabo Vobis (priestly "
    "formation), Verbum Domini (the Word of God), Sacramentum Caritatis "
    "(the Eucharist), Gaudete et Exsultate (holiness), Laudate Deum "
    "(climate), C'est la confiance (St. Therese), Catechesi Tradendae "
    "(catechesis).\n"
    "STRONGEST FOR: pastoral guidance on Christian living, family and "
    "marriage, priestly and religious vocation, evangelization, lay "
    "spirituality, post-synodal teaching that synthesizes bishops' "
    "deliberations.\n\n"
    '10. "papal-documents" — 14 historical papal bulls and modern apostolic '
    "letters spanning 1302–2020. Includes Unam Sanctam (papal authority), "
    "Exsurge Domine (against Luther), Sublimis Deus (indigenous rights), "
    "Salvifici Doloris (suffering), Mulieris Dignitatem (dignity of women), "
    "Ordinatio Sacerdotalis (male-only ordination), Dies Domini (the Lord's "
    "Day), Rosarium Virginis Mariae (the Rosary), Patris Corde (St. Joseph).\n"
    "STRONGEST FOR: specific papal declarations on contested doctrinal "
    "points, historical Church pronouncements, devotional practices (Rosary, "
    "Sunday observance), suffering and redemption, dignity and vocation of "
    "women, papal authority.\n\n"
    "SCORING GUIDELINES — use the FULL 0.0–1.0 range:\n"
    "  0.9–1.0: This collection almost certainly contains passages that directly "
    "and substantively answer the question. Reserve for collections where the "
    "topic is a primary focus.\n"
    "  0.7–0.89: Strong relevance — the collection addresses this topic from a "
    "clearly useful angle, even if not its central focus.\n"
    "  0.4–0.69: Tangential — may touch on the theme but won't directly answer.\n"
    "  0.1–0.39: Unlikely to contain relevant material for this specific question.\n"
    "  0.0–0.09: No meaningful connection between this question and this collection.\n\n"
    "QUESTION TYPE AWARENESS — let the nature of the question guide scoring:\n"
    '  - Doctrinal ("What does the Church teach about..."): weight catechism, '
    "councils, summa higher.\n"
    '  - Scriptural ("What does the Bible say about..."): weight bible highest.\n'
    '  - Moral/Ethical ("Is it moral to...", "What is the Church\'s position on..."): '
    "weight summa, catechism, encyclicals.\n"
    '  - Historical ("When did the Church...", "How did early Christians..."): '
    "weight councils, church-fathers, medieval.\n"
    '  - Pastoral/Devotional ("How do I pray about...", "How should a Catholic..."): '
    "weight bible, apostolic-exhortations, catechism.\n"
    '  - Legal/Canonical ("Is it required to...", "What are the rules for..."): '
    "weight canon-law highest.\n"
    '  - Social Teaching ("What about poverty...", "economic justice..."): '
    "weight encyclicals, apostolic-exhortations, papal-documents.\n"
    '  - Philosophical ("Does God exist?", "What is the soul?", "faith and reason"): '
    "weight summa, medieval, church-fathers.\n\n"
    "Respond with ONLY a JSON array of all 10 collections, ordered by score "
    "descending. Each element: {\"collection\": \"<key>\", \"score\": <float>}. "
    "No text before or after the array. No explanations in this response."
)

_EXPLAIN_USER_TEMPLATE = (
    "Query: {query}\n\n"
    "Relevance scores for this query (highest to lowest):\n{score_lines}\n\n"
    "For each collection above, write 1-2 sentences explaining the score. "
    "For high scores (0.7+): explain what specific content in that collection "
    "makes it directly useful for this question. "
    "For low scores (below 0.4): explain specifically what this collection covers "
    "and why that content does not address this particular question.\n\n"
    "Output ONLY JSONL — one JSON object per line in the exact order listed above, "
    "no other text before or after:\n"
    '{{"collection": "<key>", "explanation": "<1-2 sentences>"}}'
)


def _extract_scores(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in evaluate response")
    return json.loads(match.group(0))


async def _check_evaluate_rate_limit(user_id: str) -> int:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO user_usage (user_id, evaluate_date, evaluate_count)
            VALUES ($1, CURRENT_DATE, 1)
            ON CONFLICT (user_id) DO UPDATE SET
                evaluate_count = CASE
                    WHEN user_usage.evaluate_date = CURRENT_DATE
                    THEN user_usage.evaluate_count + 1
                    ELSE 1
                END,
                evaluate_date = CURRENT_DATE
            RETURNING evaluate_count
            """,
            user_id,
        )
    except Exception as exc:
        logger.error("evaluate rate_limit check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    count = row["evaluate_count"]
    if count > _DAILY_EVALUATE_LIMIT:
        now = datetime.datetime.now(datetime.timezone.utc)
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        retry_after = str(max(1, int((midnight - now).total_seconds())))
        raise HTTPException(
            status_code=429,
            detail="Daily evaluation limit reached",
            headers={"Retry-After": retry_after},
        )
    return count


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_collections(
    body: EvaluateRequest,
    user: AuthUser = Depends(get_current_user),
) -> EvaluateResponse:
    """Phase 1 — return scores only (fast). Phase 2 explain is a separate SSE stream."""
    count = await _check_evaluate_rate_limit(user.user_id)

    if _rerank_mod._client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        response = await _rerank_mod._client.messages.create(
            model=settings.evaluate_model,
            max_tokens=400,
            system=[{
                "type": "text",
                "text": _EVALUATE_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": body.query}],
        )
        usage = response.usage
        logger.info(
            "evaluate: input=%d cache_create=%d cache_read=%d output=%d",
            getattr(usage, "input_tokens", 0),
            getattr(usage, "cache_creation_input_tokens", 0),
            getattr(usage, "cache_read_input_tokens", 0),
            getattr(usage, "output_tokens", 0),
        )
        raw_text = response.content[0].text
        scored = _extract_scores(raw_text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("evaluate LLM call failed: %s", exc)
        raise HTTPException(status_code=500, detail="Evaluation failed. Please try again.") from exc

    scores = [
        CollectionScore(
            collection=str(item.get("collection", "")),
            score=max(0.0, min(1.0, float(item.get("score", 0.0)))),
        )
        for item in scored
    ]
    scores.sort(key=lambda s: s.score, reverse=True)

    return EvaluateResponse(
        query=body.query,
        remaining=max(0, _DAILY_EVALUATE_LIMIT - count),
        scores=scores,
    )


@router.post("/evaluate/explain")
async def explain_collections(
    body: ExplainRequest,
    user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    """Phase 2 — stream explanations for each collection, highest score first."""
    if _rerank_mod._client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    score_lines = "\n".join(
        f"- {item.collection}: {item.score:.2f}"
        for item in body.scores
    )
    user_message = _EXPLAIN_USER_TEMPLATE.format(
        query=body.query,
        score_lines=score_lines,
    )

    async def generate():
        try:
            buffer = ""
            async with _rerank_mod._client.messages.stream(
                model=settings.evaluate_model,
                max_tokens=1200,
                system=[{
                    "type": "text",
                    "text": _EVALUATE_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                async for text in stream.text_stream:
                    buffer += text
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if "collection" in data and "explanation" in data:
                                yield f"event: explanation\ndata: {json.dumps(data)}\n\n"
                        except json.JSONDecodeError:
                            pass
                # flush remaining buffer
                if buffer.strip():
                    try:
                        data = json.loads(buffer.strip())
                        if "collection" in data and "explanation" in data:
                            yield f"event: explanation\ndata: {json.dumps(data)}\n\n"
                    except json.JSONDecodeError:
                        pass
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:
            logger.error("explain stream failed: %s", exc)
            yield f"event: error\ndata: {json.dumps({'message': 'Explanation stream failed'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
