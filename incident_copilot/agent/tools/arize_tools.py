"""Arize Phoenix integration — traces via OpenTelemetry + MCP toolset for trace querying."""

import os
from typing import Optional

from config import settings


def get_phoenix_mcp_toolset() -> Optional[object]:
    """Return a McpToolset connected to the Arize Phoenix MCP server via npx.

    Returns None if PHOENIX_API_KEY is not configured so the agent still starts
    in local/dev environments that lack credentials.
    """
    if not settings.phoenix_api_key:
        return None

    from google.adk.tools.mcp_tool.mcp_toolset import (
        McpToolset,
        StdioConnectionParams,
        StdioServerParameters,
    )

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=[
                    "-y",
                    "@arizeai/phoenix-mcp@latest",
                    "--baseUrl",
                    settings.phoenix_collector_endpoint,
                    "--apiKey",
                    settings.phoenix_api_key,
                ],
            ),
            timeout=60.0,
        ),
        tool_name_prefix="phoenix",
    )


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
