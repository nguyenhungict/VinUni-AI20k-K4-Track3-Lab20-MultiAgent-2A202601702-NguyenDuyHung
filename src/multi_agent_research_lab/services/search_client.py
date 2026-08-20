"""Search client abstraction for ResearcherAgent."""

import json
from pathlib import Path
from typing import Any

from multi_agent_research_lab.core.schemas import SourceDocument

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CORPUS_FILE = (
    _REPO_ROOT
    / "ai_agent_offline_research_corpus_v2"
    / "topics"
    / "01_single_agent_vs_multi_agent_architectures_for_complex_research_tasks.json"
)


class SearchClient:
    """Offline, provider-agnostic search client.

    Loads a single benchmark corpus topic file (see
    `ai_agent_offline_research_corpus_v2/README.md`) and performs keyword search over its
    knowledge base. No network access required, so the lab can run without a Tavily/Bing key.
    Swap `corpus_path` for a different topic, or replace this class with a real web-search
    provider by keeping the same `search()` signature.
    """

    def __init__(self, corpus_path: Path | None = None) -> None:
        path = corpus_path or _DEFAULT_CORPUS_FILE
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._entries: list[SourceDocument] = _build_entries(data["knowledge_base"])

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        """Return the entries whose title/snippet best match the query terms."""

        terms = {term.lower() for term in query.split() if len(term) > 2}
        scored: list[tuple[int, SourceDocument]] = []
        for entry in self._entries:
            haystack = f"{entry.title} {entry.snippet}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        results = [entry for _, entry in scored[:max_results]]
        if not results:
            results = self._entries[:max_results]
        return results


def _build_entries(knowledge_base: dict[str, Any]) -> list[SourceDocument]:
    entries: list[SourceDocument] = []
    for article in knowledge_base.get("knowledge_articles", []):
        entries.append(
            SourceDocument(
                title=article["title"],
                url=None,
                snippet=article["content"][:600],
                metadata={"source_id": article["article_id"], "type": "knowledge_article"},
            )
        )
    for doc in knowledge_base.get("source_documents", []):
        entries.append(
            SourceDocument(
                title=doc["title"],
                url=doc.get("provenance_url"),
                snippet=doc["full_text"][:600],
                metadata={
                    "source_id": doc["document_id"],
                    "type": "source_document",
                    "is_synthetic": doc.get("is_synthetic", False),
                },
            )
        )
    return entries
