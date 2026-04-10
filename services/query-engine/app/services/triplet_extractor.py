"""Triplet extraction from text using LLM."""

import re

from llama_index.core import Settings
from llama_index.core.prompts import PromptTemplate
from llama_index.core.prompts.default_prompts import (
    DEFAULT_KG_TRIPLET_EXTRACT_TMPL,
)

KG_TRIPLET_EXTRACT_PROMPT = PromptTemplate(DEFAULT_KG_TRIPLET_EXTRACT_TMPL)

_TRIPLET_RE = re.compile(r"\(([^,]+),\s*([^,]+),\s*([^)]+)\)")
MAX_ENTITY_LENGTH = 128


def extract_triplets(
    text: str,
    max_triplets: int = 10,
) -> list[tuple[str, str, str]]:
    """
    Extract knowledge triplets from text via LLM.

    Uses Settings.llm (the globally configured LlamaIndex LLM) to
    extract (subject, predicate, object) triplets. Returns a list
    of string triples, truncated to MAX_ENTITY_LENGTH.
    """
    response = Settings.llm.predict(
        KG_TRIPLET_EXTRACT_PROMPT,
        max_knowledge_triplets=max_triplets,
        text=text,
    )

    triplets: list[tuple[str, str, str]] = []
    for match in _TRIPLET_RE.finditer(response):
        subj = match.group(1).strip()[:MAX_ENTITY_LENGTH]
        pred = match.group(2).strip()[:MAX_ENTITY_LENGTH]
        obj = match.group(3).strip()[:MAX_ENTITY_LENGTH]
        if subj and pred and obj:
            triplets.append((subj, pred, obj))
    return triplets
