"""Registry mapping each collection to its generation guidance module."""
from __future__ import annotations

from enrichment.prompts.base import compose_generation_system
from enrichment.prompts.generation import (
    bible, catechism, summa, encyclicals, church_fathers, medieval,
    councils, canon_law, apostolic_exhortations, papal_documents,
)

_GUIDANCE = {
    "bible": bible.GUIDANCE,
    "catechism": catechism.GUIDANCE,
    "summa": summa.GUIDANCE,
    "encyclicals": encyclicals.GUIDANCE,
    "church-fathers": church_fathers.GUIDANCE,
    "medieval": medieval.GUIDANCE,
    "councils": councils.GUIDANCE,
    "canon-law": canon_law.GUIDANCE,
    "apostolic-exhortations": apostolic_exhortations.GUIDANCE,
    "papal-documents": papal_documents.GUIDANCE,
}


def generation_system(collection: str) -> str:
    return compose_generation_system(_GUIDANCE[collection])
