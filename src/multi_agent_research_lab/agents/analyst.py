"""Analyst agent skeleton."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient

_SYSTEM_PROMPT = (
    "You are a careful research analyst. Given research notes with [source_id] citations, "
    "extract the key claims, compare viewpoints across sources, and explicitly flag any "
    "claim that is weak, unsupported, or backed by only one source. Preserve [source_id] "
    "citations in your output."
)


class AnalystAgent(BaseAgent):
    """Turns research notes into structured insights."""

    name = "analyst"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.analysis_notes`."""

        if not state.research_notes:
            raise AgentExecutionError(
                "AnalystAgent requires state.research_notes (run ResearcherAgent first)."
            )

        user_prompt = (
            f"Research question: {state.request.query}\n\n"
            f"Research notes:\n{state.research_notes}\n\n"
            "Produce a structured analysis: key claims, points of agreement/disagreement "
            "between sources, and any evidence that looks weak or unsupported. Keep "
            "[source_id] citations."
        )

        with trace_span("analyst.llm_call") as span:
            response = self._llm_client.complete(_SYSTEM_PROMPT, user_prompt)
            span["attributes"]["output_tokens"] = response.output_tokens

        state.analysis_notes = response.content
        state.agent_results.append(
            AgentResult(
                agent=AgentName.ANALYST,
                content=response.content,
                metadata={
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cost_usd": response.cost_usd,
                },
            )
        )
        state.add_trace_event("analyst.completed", {"cost_usd": response.cost_usd})
        return state
