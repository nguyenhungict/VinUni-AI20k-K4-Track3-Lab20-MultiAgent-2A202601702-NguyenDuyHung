"""Benchmark skeleton for single-agent vs multi-agent."""

from collections.abc import Callable
from time import perf_counter

from multi_agent_research_lab.core.schemas import BenchmarkMetrics
from multi_agent_research_lab.core.state import ResearchState

Runner = Callable[[str], ResearchState]

# Automated quality is a heuristic proxy only (length + citation density). The rubric-based
# 0-10 peer review score (docs/peer_review_rubric.md) is the score that should ship in
# reports/benchmark_report.md; keep both side by side rather than trusting this number alone.
_TARGET_WORDS_FOR_FULL_LENGTH_SCORE = 400
_MAX_LENGTH_POINTS = 5.0
_MAX_CITATION_POINTS = 5.0


def run_benchmark(
    run_name: str, query: str, runner: Runner
) -> tuple[ResearchState, BenchmarkMetrics]:
    """Run `runner`, measure latency, and derive cost/quality/citation/failure metrics."""

    started = perf_counter()
    state = runner(query)
    latency = perf_counter() - started

    metrics = BenchmarkMetrics(
        run_name=run_name,
        latency_seconds=latency,
        estimated_cost_usd=_total_cost(state),
        quality_score=_estimate_quality(state),
        citation_coverage=_citation_coverage(state),
        failure_rate=1.0 if state.errors or not state.final_answer else 0.0,
        notes="; ".join(state.errors) if state.errors else "",
    )
    return state, metrics


def _total_cost(state: ResearchState) -> float | None:
    costs: list[float] = [
        cost
        for result in state.agent_results
        if (cost := result.metadata.get("cost_usd")) is not None
    ]
    return sum(costs) if costs else None


def _citation_coverage(state: ResearchState) -> float | None:
    if not state.final_answer:
        return None
    source_ids = {
        source.metadata.get("source_id")
        for source in state.sources
        if source.metadata.get("source_id")
    }
    if not source_ids:
        return None
    cited = sum(1 for source_id in source_ids if f"[{source_id}]" in state.final_answer)
    return cited / len(source_ids)


def _estimate_quality(state: ResearchState) -> float | None:
    """Cheap automated proxy: rewards substantive length and citation density."""

    if not state.final_answer:
        return 0.0
    words = len(state.final_answer.split())
    length_score = min(words / _TARGET_WORDS_FOR_FULL_LENGTH_SCORE, 1.0) * _MAX_LENGTH_POINTS
    citation_score = min(state.final_answer.count("["), 5) / 5 * _MAX_CITATION_POINTS
    return round(min(length_score + citation_score, 10.0), 1)
