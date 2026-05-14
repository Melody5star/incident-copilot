"""Arize Phoenix integration for LLM observability — instruments all agent traces."""

import os

from config import settings


def setup_arize_tracing() -> None:
    """Configure OpenTelemetry to export agent traces to Arize Phoenix Cloud.

    Uses phoenix.otel.register() which auto-reads PHOENIX_API_KEY and
    PHOENIX_COLLECTOR_ENDPOINT from environment and handles auth correctly.
    """
    if not settings.phoenix_api_key:
        return

    # Ensure env vars are set before calling register()
    os.environ.setdefault("PHOENIX_API_KEY", settings.phoenix_api_key)
    # Phoenix Cloud base URL — register() appends /v1/traces automatically
    os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com")

    try:
        from phoenix.otel import register

        tracer_provider = register(
            project_name=settings.phoenix_project_name,
            # endpoint and api_key are read from env vars above
        )

        # Instrument Vertex AI SDK calls automatically
        try:
            from openinference.instrumentation.vertexai import VertexAIInstrumentor
            VertexAIInstrumentor().instrument(tracer_provider=tracer_provider)
        except ImportError:
            pass

    except Exception as exc:
        # Observability failure must never break the agent
        print(f"[WARNING] Arize Phoenix setup failed: {exc}")
