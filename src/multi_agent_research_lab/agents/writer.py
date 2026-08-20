"""Writer agent skeleton."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient

_SYSTEM_PROMPT = (
    "You are a technical writer. Synthesize research notes and analysis into a clear, "
    "well-structured answer for the target audience. Every non-obvious claim must carry "
    "its [source_id] citation, taken from the analysis notes. Do not introduce new facts "
    "that are not present in the notes."
)


class WriterAgent(BaseAgent):
    """Produces final answer from research and analysis notes."""

    name = "writer"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.final_answer`."""

        if not state.analysis_notes:
            raise AgentExecutionError(
                "WriterAgent requires state.analysis_notes (run AnalystAgent first)."
            )

        user_prompt = (
            f"Research question: {state.request.query}\n"
            f"Audience: {state.request.audience}\n\n"
            f"Research notes:\n{state.research_notes}\n\n"
            f"Analysis notes:\n{state.analysis_notes}\n\n"
            "Write the final answer for this audience, keeping [source_id] citations "
            "inline for every non-obvious claim."
        )

        with trace_span("writer.llm_call") as span:
            response = self._llm_client.complete(_SYSTEM_PROMPT, user_prompt)
            span["attributes"]["output_tokens"] = response.output_tokens

        state.final_answer = response.content
        state.agent_results.append(
            AgentResult(
                agent=AgentName.WRITER,
                content=response.content,
                metadata={
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cost_usd": response.cost_usd,
                },
            )
        )
        state.add_trace_event("writer.completed", {"cost_usd": response.cost_usd})
        return state
