"""Supervisor / router skeleton."""

import time

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.state import ResearchState

DONE = "done"


class SupervisorAgent(BaseAgent):
    """Decides which worker should run next and when to stop.

    Routing policy (in priority order):
    1. Stop if `max_iterations` or `timeout_seconds` has been exceeded (guardrail).
    2. Route to `researcher` if we have no sources / research notes yet.
    3. Route to `analyst` if research notes exist but analysis notes do not.
    4. Route to `writer` if analysis notes exist but the final answer does not.
    5. Otherwise, we are done.
    """

    name = "supervisor"

    def run(self, state: ResearchState) -> ResearchState:
        """Update `state.route_history` with the next route."""

        settings = get_settings()
        state.started_at = state.started_at or time.time()
        elapsed = time.time() - state.started_at

        if state.iteration >= settings.max_iterations:
            state.errors.append(
                f"Supervisor: reached max_iterations={settings.max_iterations}, stopping."
            )
            route = DONE
        elif elapsed > settings.timeout_seconds:
            state.errors.append(
                f"Supervisor: exceeded timeout_seconds={settings.timeout_seconds}, stopping."
            )
            route = DONE
        elif not state.sources or not state.research_notes:
            route = "researcher"
        elif not state.analysis_notes:
            route = "analyst"
        elif not state.final_answer:
            route = "writer"
        else:
            route = DONE

        state.record_route(route)
        state.add_trace_event(
            "supervisor.route", {"route": route, "iteration": state.iteration, "elapsed_s": elapsed}
        )
        return state
