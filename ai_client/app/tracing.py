"""
Phoenix / OpenTelemetry setup for the PanKB agent client.

Registers a tracer provider that auto-instruments the openai package and
exposes a module-level `tracer` for manual spans around the agent loop and
tool calls. Safe to import even when Phoenix is unreachable: failures are
logged and tracing degrades to a no-op tracer.
"""
import logging
import os

from opentelemetry import trace

logger = logging.getLogger(__name__)

_initialized = False


def init_tracing() -> trace.Tracer:
    """
    Initialize Phoenix tracing once per process. Subsequent calls return the
    same tracer. If the Phoenix collector is unreachable, returns the global
    no-op tracer so the app still runs.
    """
    global _initialized

    if _initialized:
        return trace.get_tracer("pankb.agent")

    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    project_name = os.getenv("PHOENIX_PROJECT_NAME", "pankb-agent")

    if not endpoint:
        logger.info("PHOENIX_COLLECTOR_ENDPOINT not set — tracing disabled")
        _initialized = True
        return trace.get_tracer("pankb.agent")

    try:
        from phoenix.otel import register

        register(
            project_name=project_name,
            endpoint=f"{endpoint.rstrip('/')}/v1/traces",
            auto_instrument=True,  # picks up openinference-instrumentation-openai
            batch=True,
        )
        logger.info(
            "Phoenix tracing initialized: project=%s endpoint=%s",
            project_name,
            endpoint,
        )
    except Exception as e:
        logger.warning("Phoenix tracing init failed (%s) — continuing without traces", e)

    _initialized = True
    return trace.get_tracer("pankb.agent")
