"""Neo4j-backed KG retriever for keyword-based entity lookup.

Flow: query → LLM keyword extraction → Neo4j entity search →
relationship traversal → source text nodes from docstore.
"""

import re
from typing import Any

import structlog
from llama_index.core import Settings
from llama_index.core.prompts import PromptTemplate
from llama_index.core.prompts.default_prompts import (
    DEFAULT_QUERY_KEYWORD_EXTRACT_TEMPLATE_TMPL,
)
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.graph_stores.neo4j import Neo4jGraphStore

logger = structlog.stdlib.get_logger(__name__)

KEYWORD_EXTRACT_PROMPT = PromptTemplate(
    DEFAULT_QUERY_KEYWORD_EXTRACT_TEMPLATE_TMPL
)


class Neo4jKGRetriever(BaseRetriever):
    """
    Retrieves text nodes from Neo4j by matching query keywords to entities.

    Uses the LLM to extract keywords from the query, searches Neo4j for
    entities matching those keywords, traverses relationships to collect
    context, and returns both relationship text and source document chunks.
    """

    def __init__(
        self,
        graph_store: Neo4jGraphStore,
        docstore: Any,
        include_text: bool = True,
        max_keywords: int = 10,
    ) -> None:
        self._graph_store = graph_store
        self._docstore = docstore
        self._include_text = include_text
        self._max_keywords = max_keywords
        super().__init__()

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract search keywords from the query using the LLM."""
        response = Settings.llm.predict(
            KEYWORD_EXTRACT_PROMPT,
            max_keywords=self._max_keywords,
            question=query,
        )
        match = re.search(r"KEYWORDS:\s*(.*)", response, re.IGNORECASE)
        if not match:
            return [query]
        return [kw.strip() for kw in match.group(1).split(",") if kw.strip()]

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        """Retrieve nodes by matching keywords to Neo4j entities."""
        keywords = self._extract_keywords(query_bundle.query_str)
        if not keywords:
            return []

        label = self._graph_store.node_label

        cypher = (
            f"MATCH (n:`{label}`)-[r]-(connected:`{label}`) "
            "WHERE ANY(kw IN $keywords WHERE toLower(n.id) CONTAINS toLower(kw)) "
            "RETURN DISTINCT n.id AS entity, type(r) AS relation, "
            "connected.id AS related, r.source_node_ids AS source_node_ids"
        )
        records = self._graph_store.query(cypher, {"keywords": keywords})
        if not records:
            return []

        source_node_ids: set[str] = set()
        relationship_lines: list[str] = []
        for record in records:
            line = f"{record['entity']} {record['relation']} {record['related']}"
            relationship_lines.append(line)
            node_ids = record.get("source_node_ids")
            if node_ids:
                source_node_ids.update(node_ids)

        results: list[NodeWithScore] = []

        if relationship_lines:
            kg_text = "\n".join(relationship_lines)
            kg_node = TextNode(text=kg_text, id_="kg_rel_text")
            results.append(NodeWithScore(node=kg_node, score=1.0))

        if self._include_text and source_node_ids:
            for node_id in source_node_ids:
                try:
                    doc = self._docstore.get_document(node_id)
                    if doc is not None:
                        results.append(NodeWithScore(node=doc, score=0.5))
                except (ValueError, KeyError):
                    logger.debug("source_node_not_found", node_id=node_id)

        return results
