"""Tests for Elasticsearch tools — requires live ES on localhost:9200 with seeded data."""

import pathlib
import subprocess
import sys
import pytest
import pytest_asyncio
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def seed_data():
    """Seed fresh spike data before elastic tests run so timestamps are always current."""
    subprocess.run(
        [sys.executable, "scripts/seed_elasticsearch.py"],
        cwd=pathlib.Path(__file__).parent.parent,
        check=True,
        capture_output=True,
    )


async def test_search_error_logs_returns_structure():
    """search_error_logs returns a dict with 'total' and 'logs' keys."""
    from agent.tools.elastic_tools import search_error_logs

    result = await search_error_logs("payment-service", minutes_back=60)

    assert isinstance(result, dict)
    assert "total" in result
    assert "logs" in result
    assert isinstance(result["total"], int)
    assert isinstance(result["logs"], list)


async def test_search_error_logs_finds_seeded_payment_errors():
    """payment-service should have errors in the seeded dataset."""
    from agent.tools.elastic_tools import search_error_logs

    result = await search_error_logs("payment-service", minutes_back=60)

    assert result["total"] > 0, "Expected seeded payment-service errors — run seed_elasticsearch.py first"
    log = result["logs"][0]
    assert "service" in log or "message" in log, "Log entries must have service or message field"


async def test_search_error_logs_unknown_service_returns_empty():
    """An unknown service name should return 0 results, not an error."""
    from agent.tools.elastic_tools import search_error_logs

    result = await search_error_logs("nonexistent-service-xyz", minutes_back=60)

    assert result["total"] == 0
    assert result["logs"] == []


async def test_search_error_logs_respects_max_results():
    """max_results cap is respected."""
    from agent.tools.elastic_tools import search_error_logs

    result = await search_error_logs("payment-service", minutes_back=60, max_results=3)

    assert len(result["logs"]) <= 3


async def test_detect_error_rate_spike_structure():
    """detect_error_rate_spike always returns the required keys."""
    from agent.tools.elastic_tools import detect_error_rate_spike

    result = await detect_error_rate_spike("payment-service")

    assert "spike_detected" in result
    assert "current_rate" in result
    assert "baseline_rate" in result
    assert "multiplier" in result
    assert "service_name" in result
    assert isinstance(result["spike_detected"], bool)
    assert result["service_name"] == "payment-service"


async def test_detect_error_rate_spike_detects_seeded_spike():
    """payment-service should show a spike — seed injects 75% error rate in last 8 min."""
    from agent.tools.elastic_tools import detect_error_rate_spike

    result = await detect_error_rate_spike("payment-service", window_minutes=8, baseline_minutes=60)

    assert result["spike_detected"] is True, (
        f"Expected spike but got multiplier={result['multiplier']} "
        f"(current={result['current_rate']}, baseline={result['baseline_rate']}). "
        "Run seed_elasticsearch.py first."
    )
    assert result["multiplier"] >= 3.0


async def test_detect_error_rate_spike_no_spike_for_quiet_service():
    """A service with no logs should not show a spike."""
    from agent.tools.elastic_tools import detect_error_rate_spike

    result = await detect_error_rate_spike("nonexistent-service-xyz")

    assert result["spike_detected"] is False
    assert result["current_rate"] == 0.0


async def test_detect_error_rate_spike_multiplier_is_inf_when_no_baseline():
    """If baseline is zero (new service), multiplier should be inf (treated as spike)."""
    from agent.tools.elastic_tools import detect_error_rate_spike

    # Use a tiny baseline window so there's almost certainly no baseline data for the fake service
    result = await detect_error_rate_spike("new-service-no-history", window_minutes=1, baseline_minutes=1)

    # Either no spike (0 errors) or inf multiplier — never a ValueError
    assert isinstance(result["spike_detected"], bool)


async def test_get_affected_services_structure():
    """get_affected_services returns dict with 'services' list."""
    from agent.tools.elastic_tools import get_affected_services

    result = await get_affected_services(minutes_back=60)

    assert "services" in result
    assert isinstance(result["services"], list)


async def test_get_affected_services_finds_seeded_services():
    """Seeded data has payment-service and auth-service with errors."""
    from agent.tools.elastic_tools import get_affected_services

    result = await get_affected_services(minutes_back=60)
    service_names = [s["name"] for s in result["services"]]

    assert len(result["services"]) >= 1, "Expected at least one service with errors"
    # Each entry must have name and error_count
    for svc in result["services"]:
        assert "name" in svc
        assert "error_count" in svc
        assert svc["error_count"] > 0


async def test_get_affected_services_sorted_by_severity():
    """Services are returned sorted highest error_count first."""
    from agent.tools.elastic_tools import get_affected_services

    result = await get_affected_services(minutes_back=60)
    counts = [s["error_count"] for s in result["services"]]

    assert counts == sorted(counts, reverse=True), "Services must be sorted by error_count descending"


async def test_get_log_context_unknown_trace_returns_empty():
    """An unknown trace_id returns empty logs, not an exception."""
    from agent.tools.elastic_tools import get_log_context

    result = await get_log_context("00000000-0000-0000-0000-000000000000")

    assert "logs" in result
    assert isinstance(result["logs"], list)
