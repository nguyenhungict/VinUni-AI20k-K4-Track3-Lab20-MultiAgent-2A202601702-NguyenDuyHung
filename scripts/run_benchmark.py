"""Run the single-agent baseline and the multi-agent workflow on the same query,
compare them with `evaluation.benchmark`, and write `reports/benchmark_report.md`.

Usage:
    python scripts/run_benchmark.py --query "..."
"""

import argparse

from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.benchmark import run_benchmark
from multi_agent_research_lab.evaluation.report import render_markdown_report
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.logging import configure_logging
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.storage import LocalArtifactStore

_BASELINE_SYSTEM_PROMPT = (
    "You are a research assistant working alone. Research, analyze, and write a "
    "well-structured answer to the user's query in a single response, using your own "
    "knowledge. Be explicit about any claim you are not fully certain of."
)


def run_baseline(query: str) -> ResearchState:
    state = ResearchState(request=ResearchQuery(query=query))
    try:
        response = LLMClient().complete(_BASELINE_SYSTEM_PROMPT, query)
    except AgentExecutionError as exc:
        state.errors.append(str(exc))
        return state
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
    return state


def run_multi_agent(query: str) -> ResearchState:
    state = ResearchState(request=ResearchQuery(query=query))
    return MultiAgentWorkflow().run(state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        default="Compare single-agent vs multi-agent architectures for research report writing",
    )
    args = parser.parse_args()

    configure_logging()

    _, baseline_metrics = run_benchmark("single-agent baseline", args.query, run_baseline)
    _, multi_agent_metrics = run_benchmark("multi-agent workflow", args.query, run_multi_agent)

    report = render_markdown_report([baseline_metrics, multi_agent_metrics])
    path = LocalArtifactStore().write_text("benchmark_report.md", report)
    print(f"Wrote {path}")
    print(report)


if __name__ == "__main__":
    main()
