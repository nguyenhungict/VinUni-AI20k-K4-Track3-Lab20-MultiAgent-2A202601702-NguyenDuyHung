"""Researcher agent skeleton."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.search_client import SearchClient

_SYSTEM_PROMPT = (
    "You are a meticulous research assistant. Given source snippets, write concise "
    "research notes as bullet points. Tag every claim with the [source_id] it comes from. "
    "Do not invent facts that are not present in the provided sources."
)


class ResearcherAgent(BaseAgent):
    """Collects sources and creates concise research notes."""

    name = "researcher"

    def __init__(
        self,
        search_client: SearchClient | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._search_client = search_client or SearchClient()
        self._llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.sources` and `state.research_notes`."""

        with trace_span("researcher.search", {"query": state.request.query}) as span:
            sources = self._search_client.search(
                state.request.query, max_results=state.request.max_sources
            )
            span["attributes"]["num_sources"] = len(sources)
        state.sources = sources

        sources_block = "\n".join(
            f"[{source.metadata.get('source_id', index)}] {source.title}: {source.snippet}"
            for index, source in enumerate(sources)
        )
        user_prompt = (
            f"Research question: {state.request.query}\n\n"
            f"Available sources:\n{sources_block}\n\n"
            "Write research notes summarizing the most relevant facts, each tagged with "
            "its [source_id]."
        )

        with trace_span("researcher.llm_call") as span:
            response = self._llm_client.complete(_SYSTEM_PROMPT, user_prompt)
            span["attributes"]["output_tokens"] = response.output_tokens

        state.research_notes = response.content
        state.agent_results.append(
            AgentResult(
                agent=AgentName.RESEARCHER,
                content=response.content,
                metadata={
                    "num_sources": len(sources),
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cost_usd": response.cost_usd,
                },
            )
        )
        state.add_trace_event(
            "researcher.completed",
            {"num_sources": len(sources), "cost_usd": response.cost_usd},
        )
        return state
