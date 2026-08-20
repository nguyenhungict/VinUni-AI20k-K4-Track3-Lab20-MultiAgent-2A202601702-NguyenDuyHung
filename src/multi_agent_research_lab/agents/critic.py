"""Optional critic agent skeleton for bonus work."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.state import ResearchState

_LOW_COVERAGE_THRESHOLD = 0.3


class CriticAgent(BaseAgent):
    """Validates the final answer: citation coverage against `state.sources`.

    Runs as a non-blocking guardrail: it never raises, it only appends findings to
    `state.errors` / `state.trace` so the workflow can finish and the failure is visible.
    """

    name = "critic"

    def run(self, state: ResearchState) -> ResearchState:
        """Validate final answer and append findings."""

        if not state.final_answer:
            state.errors.append("CriticAgent: no final_answer to validate.")
            state.add_trace_event("critic.skipped", {"reason": "no final_answer"})
            return state

        source_ids = {
            source.metadata.get("source_id")
            for source in state.sources
            if source.metadata.get("source_id")
        }
        cited_ids = {sid for sid in source_ids if f"[{sid}]" in state.final_answer}
        coverage = len(cited_ids) / len(source_ids) if source_ids else 0.0

        state.add_trace_event(
            "critic.citation_check",
            {"coverage": coverage, "num_sources": len(source_ids), "num_cited": len(cited_ids)},
        )
        if coverage < _LOW_COVERAGE_THRESHOLD:
            state.errors.append(
                f"CriticAgent: low citation coverage ({coverage:.0%}). "
                "Consider adding more [source_id] references in the final answer."
            )
        return state
