"""Unit tests for SupervisorAgent's routing policy.

Replaces the original skeleton-guard test (see git history) now that
SupervisorAgent.run is implemented.
"""

from multi_agent_research_lab.agents.supervisor import DONE, SupervisorAgent
from multi_agent_research_lab.core.schemas import ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState


def _state() -> ResearchState:
    return ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))


def test_routes_to_researcher_when_no_sources() -> None:
    state = SupervisorAgent().run(_state())
    assert state.route_history == ["researcher"]
    assert state.iteration == 1


def test_routes_to_analyst_when_research_notes_present() -> None:
    state = _state()
    state.sources = [SourceDocument(title="t", snippet="s")]
    state.research_notes = "notes"

    state = SupervisorAgent().run(state)

    assert state.route_history == ["analyst"]


def test_routes_to_writer_when_analysis_notes_present() -> None:
    state = _state()
    state.sources = [SourceDocument(title="t", snippet="s")]
    state.research_notes = "notes"
    state.analysis_notes = "analysis"

    state = SupervisorAgent().run(state)

    assert state.route_history == ["writer"]


def test_routes_to_done_when_final_answer_present() -> None:
    state = _state()
    state.sources = [SourceDocument(title="t", snippet="s")]
    state.research_notes = "notes"
    state.analysis_notes = "analysis"
    state.final_answer = "answer"

    state = SupervisorAgent().run(state)

    assert state.route_history == [DONE]


def test_stops_at_max_iterations_even_if_incomplete() -> None:
    state = _state()
    state.iteration = 999  # far beyond default max_iterations

    state = SupervisorAgent().run(state)

    assert state.route_history == [DONE]
    assert any("max_iterations" in error for error in state.errors)
