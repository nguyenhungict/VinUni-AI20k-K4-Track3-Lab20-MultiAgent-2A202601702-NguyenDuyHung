"""Tests for the trace_span hook, including its LangSmith integration."""

import pytest

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.observability import tracing
from multi_agent_research_lab.observability.tracing import trace_span


def test_span_records_duration_without_provider() -> None:
    with trace_span("unit.work") as span:
        assert span["name"] == "unit.work"
        assert span["duration_seconds"] is None

    assert span["duration_seconds"] is not None
    assert span["duration_seconds"] >= 0


def test_attributes_set_inside_block_are_kept() -> None:
    with trace_span("unit.work", {"query": "q"}) as span:
        span["attributes"]["num_sources"] = 3

    assert span["attributes"] == {"query": "q", "num_sources": 3}


def test_caller_exception_propagates_and_duration_still_recorded() -> None:
    """Regression: the span must never swallow the caller's exception.

    Agents wrap failing LLM calls in trace_span, and the workflow relies on
    AgentExecutionError reaching it to record the failure and re-route.
    """

    span_ref: dict[str, object] = {}
    with pytest.raises(ValueError, match="boom"), trace_span("unit.failing") as span:
        span_ref = span
        raise ValueError("boom")

    assert span_ref["duration_seconds"] is not None


def test_configuring_a_key_actually_enables_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: an API key must actually switch LangSmith tracing on.

    LangSmith builds a run object but never uploads it while tracing is disabled (it
    defaults to off unless LANGSMITH_TRACING is set). Without this, a span looks
    perfectly successful locally while nothing ever reaches the server.
    """

    import langsmith
    from langsmith import run_helpers, utils

    monkeypatch.setattr(
        tracing,
        "get_settings",
        lambda: Settings(LANGSMITH_API_KEY="ls-fake-key"),  # type: ignore[call-arg]
    )

    observed: dict[str, object] = {}

    class _FakeRun:
        def end(self, outputs: dict[str, object] | None = None) -> None:
            observed["outputs"] = outputs

    class _FakeTrace:
        def __init__(self, **kwargs: object) -> None:
            observed["project_name"] = kwargs.get("project_name")

        def __enter__(self) -> _FakeRun:
            observed["enabled_inside"] = utils.tracing_is_enabled()
            return _FakeRun()

        def __exit__(self, *exc_info: object) -> bool:
            return False

    monkeypatch.setattr(run_helpers, "trace", _FakeTrace)
    monkeypatch.setattr(langsmith, "Client", lambda **kwargs: object())

    with trace_span("unit.traced") as span:
        span["attributes"]["num_sources"] = 5

    assert observed["enabled_inside"] is True, "tracing was off: the run would never upload"
    assert observed["project_name"] == "multi-agent-research-lab"
    assert observed["outputs"] == {
        "duration_seconds": span["duration_seconds"],
        "num_sources": 5,
    }


def test_langsmith_failure_degrades_to_local_span(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken/unreachable tracing provider must not break the research run."""

    monkeypatch.setattr(
        tracing,
        "get_settings",
        lambda: Settings(LANGSMITH_API_KEY="ls-invalid-key"),  # type: ignore[call-arg]
    )

    def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("langsmith unreachable")

    monkeypatch.setattr(tracing.ExitStack, "enter_context", _explode)

    with trace_span("unit.traced") as span:
        span["attributes"]["ok"] = True

    assert span["duration_seconds"] is not None
    assert span["attributes"]["ok"] is True
