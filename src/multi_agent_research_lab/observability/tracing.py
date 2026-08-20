"""Tracing hooks.

The local span dict is always produced, so the workflow keeps working with no tracing
provider configured. When `LANGSMITH_API_KEY` is set, the same span is mirrored to LangSmith
as a run, giving a hosted trace UI on top of the in-state `ResearchState.trace` events.
"""

import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from time import perf_counter
from typing import Any

from multi_agent_research_lab.core.config import get_settings

logger = logging.getLogger(__name__)


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Time a unit of work and, when configured, mirror it to LangSmith.

    The yielded dict is mutable: callers add to `span["attributes"]` inside the block and
    those values are sent to LangSmith as run outputs when the block exits.

    Tracing is best-effort by design — a provider outage must never break a research run, so
    LangSmith errors degrade to local-only timing. Exceptions raised by the *caller's* block
    always propagate untouched, so agent failures still reach the workflow's error handling.
    """

    span: dict[str, Any] = {"name": name, "attributes": attributes or {}, "duration_seconds": None}
    started = perf_counter()

    with ExitStack() as stack:
        run = _start_langsmith_run(stack, name, span)
        try:
            yield span
        finally:
            span["duration_seconds"] = perf_counter() - started
            if run is not None:
                try:
                    run.end(outputs=_span_outputs(span))
                except Exception as exc:  # noqa: BLE001 - tracing must not break the workflow
                    logger.warning("LangSmith run.end failed for span %r (%s).", name, exc)


def _start_langsmith_run(stack: ExitStack, name: str, span: dict[str, Any]) -> Any | None:
    """Open a LangSmith run inside `stack`, or return None when tracing is unavailable."""

    settings = get_settings()
    if not settings.langsmith_api_key:
        return None

    try:
        from langsmith import Client
        from langsmith.run_helpers import trace as langsmith_trace
        from langsmith.run_helpers import tracing_context

        client = Client(api_key=settings.langsmith_api_key)

        # LangSmith only uploads runs when tracing is enabled, which by default requires the
        # LANGSMITH_TRACING env var. Configuring LANGSMITH_API_KEY in .env is the intent
        # signal here, so enable it explicitly — otherwise `trace` silently builds a run
        # that is never sent, and the workflow looks traced while nothing reaches LangSmith.
        stack.enter_context(tracing_context(enabled=True, client=client))

        return stack.enter_context(
            langsmith_trace(
                name=name,
                run_type="chain",
                inputs=dict(span["attributes"]),
                project_name=settings.langsmith_project,
                client=client,
            )
        )
    except Exception as exc:  # noqa: BLE001 - includes ImportError when `llm` extra is absent
        logger.warning("LangSmith unavailable for span %r (%s); running untraced.", name, exc)
        return None


def _span_outputs(span: dict[str, Any]) -> dict[str, Any]:
    return {"duration_seconds": span["duration_seconds"], **span["attributes"]}
