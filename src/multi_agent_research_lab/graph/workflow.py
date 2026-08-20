"""LangGraph workflow skeleton."""

from collections.abc import Callable

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import DONE, SupervisorAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.state import ResearchState

_NodeFn = Callable[[ResearchState], ResearchState]


class MultiAgentWorkflow:
    """Builds and runs the multi-agent graph.

    Keep orchestration here; keep agent internals in `agents/`.
    """

    def __init__(
        self,
        supervisor: SupervisorAgent | None = None,
        researcher: ResearcherAgent | None = None,
        analyst: AnalystAgent | None = None,
        writer: WriterAgent | None = None,
        critic: CriticAgent | None = None,
    ) -> None:
        self._supervisor = supervisor or SupervisorAgent()
        self._researcher = researcher or ResearcherAgent()
        self._analyst = analyst or AnalystAgent()
        self._writer = writer or WriterAgent()
        self._critic = critic or CriticAgent()

    def build(self) -> CompiledStateGraph[ResearchState, None, ResearchState, ResearchState]:
        """Create a LangGraph graph.

        Nodes: supervisor, researcher, analyst, writer, critic. The supervisor is the only
        node with conditional routing; workers always report back to the supervisor so it
        can re-evaluate state (and enforce guardrails) after every step.
        """

        graph = StateGraph(ResearchState)
        graph.add_node("supervisor", self._wrap(self._supervisor))  # type: ignore[call-overload]
        graph.add_node("researcher", self._wrap(self._researcher))  # type: ignore[call-overload]
        graph.add_node("analyst", self._wrap(self._analyst))  # type: ignore[call-overload]
        graph.add_node("writer", self._wrap(self._writer))  # type: ignore[call-overload]
        graph.add_node("critic", self._wrap(self._critic))  # type: ignore[call-overload]

        graph.set_entry_point("supervisor")
        graph.add_conditional_edges(
            "supervisor",
            _route_after_supervisor,
            {
                "researcher": "researcher",
                "analyst": "analyst",
                "writer": "writer",
                DONE: "critic",
            },
        )
        graph.add_edge("researcher", "supervisor")
        graph.add_edge("analyst", "supervisor")
        graph.add_edge("writer", "supervisor")
        graph.add_edge("critic", END)

        return graph.compile()

    def run(self, state: ResearchState) -> ResearchState:
        """Execute the graph and return final state."""

        compiled = self.build()
        recursion_limit = max(50, state.request.max_sources * 10)
        result = compiled.invoke(state, config={"recursion_limit": recursion_limit})
        return ResearchState.model_validate(result)

    @staticmethod
    def _wrap(agent: BaseAgent) -> _NodeFn:
        """Catch agent failures so one bad step doesn't crash the whole graph.

        A failed worker leaves its output field empty; the supervisor will simply route
        back to it on the next iteration (bounded retry) until `max_iterations`/
        `timeout_seconds` forces a stop with whatever partial state exists.
        """

        def _run(state: ResearchState) -> ResearchState:
            try:
                return agent.run(state)
            except AgentExecutionError as exc:
                state.errors.append(f"{agent.name} failed: {exc}")
                state.add_trace_event(f"{agent.name}.failed", {"error": str(exc)})
                return state

        return _run


def _route_after_supervisor(state: ResearchState) -> str:
    return state.route_history[-1] if state.route_history else DONE
