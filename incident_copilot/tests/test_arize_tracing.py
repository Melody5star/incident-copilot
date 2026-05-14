"""Tests for Arize Phoenix tracing setup."""

import pytest


def test_setup_arize_tracing_does_not_raise():
    """setup_arize_tracing() should complete without raising even if key is wrong."""
    from agent.tools.arize_tools import setup_arize_tracing

    # Should not raise — failures are caught and printed as warnings
    setup_arize_tracing()


def test_tracer_provider_is_registered_after_setup():
    """After setup, the global tracer provider should be set (not the NoOp default)."""
    from opentelemetry import trace
    from agent.tools.arize_tools import setup_arize_tracing

    setup_arize_tracing()

    provider = trace.get_tracer_provider()
    # If setup succeeded, provider is NOT the default NoOpTracerProvider
    provider_type = type(provider).__name__
    assert provider_type != "NoOpTracerProvider", (
        "Tracer provider is still NoOp — Phoenix setup may have silently failed"
    )


def test_setup_is_idempotent():
    """Calling setup_arize_tracing() twice should not raise."""
    from agent.tools.arize_tools import setup_arize_tracing

    setup_arize_tracing()
    setup_arize_tracing()  # second call — should not crash
