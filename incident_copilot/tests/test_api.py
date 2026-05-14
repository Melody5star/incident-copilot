"""Tests for the FastAPI backend — uses httpx AsyncClient with lifespan startup."""

import pathlib
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from httpx import AsyncClient, ASGITransport

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module")
async def client():
    """Start the real FastAPI app with lifespan (initializes the agent), yield a client."""
    from api.main import app

    # Trigger lifespan manually so _agent is initialized before any test runs
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


async def test_health_endpoint(client):
    """GET /health returns 200 with status=ok."""
    resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["agent"] == "incident_copilot"


async def test_triage_sync_returns_response_and_tool_calls(client):
    """POST /triage/sync with a simple message returns a non-empty response and tool_calls list."""
    resp = await client.post(
        "/triage/sync",
        json={"message": "What services have errors right now?"},
        timeout=120,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "response" in body
    assert "tool_calls" in body
    assert "session_id" in body
    assert isinstance(body["tool_calls"], list)
    assert len(body["response"]) > 0


async def test_triage_sync_uses_elastic_tool(client):
    """Triaging an anomaly question must call at least one Elastic tool."""
    resp = await client.post(
        "/triage/sync",
        json={"message": "Check payment-service for error spikes"},
        timeout=120,
    )

    body = resp.json()
    elastic_tools = {"get_affected_services", "detect_error_rate_spike", "search_error_logs", "get_log_context"}
    called = set(body.get("tool_calls", []))
    assert called & elastic_tools, (
        f"Expected at least one Elastic tool call, got: {called}"
    )


async def test_triage_sync_full_workflow_uses_gitlab_tool(client):
    """A full triage request should invoke Elastic tools then GitLab tools."""
    resp = await client.post(
        "/triage/sync",
        json={"message": "Triage payment-service — detect errors, find the commit, file an incident issue"},
        timeout=120,
    )

    assert resp.status_code == 200
    body = resp.json()
    tool_calls = body.get("tool_calls", [])

    elastic_used = any(t in tool_calls for t in ["get_affected_services", "detect_error_rate_spike", "search_error_logs"])
    gitlab_used = any(t in tool_calls for t in ["search_recent_commits", "create_incident_issue", "find_mr_for_commit"])

    assert elastic_used, f"No Elastic tools called: {tool_calls}"
    assert gitlab_used, f"No GitLab tools called: {tool_calls}"


async def test_triage_sync_response_mentions_service(client):
    """Agent response should mention the service name it investigated."""
    resp = await client.post(
        "/triage/sync",
        json={"message": "Is payment-service healthy?"},
        timeout=120,
    )

    body = resp.json()
    assert "payment" in body["response"].lower()


async def test_triage_streaming_endpoint_returns_sse(client):
    """POST /triage returns text/event-stream content type."""
    resp = await client.post(
        "/triage",
        json={"message": "Quick health check"},
        timeout=120,
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


async def test_triage_streaming_delivers_data_events(client):
    """Streaming endpoint emits at least one 'data: ...' SSE line."""
    resp = await client.post(
        "/triage",
        json={"message": "What services have errors?"},
        timeout=120,
    )

    content = resp.text
    assert "data:" in content, f"Expected SSE data lines, got: {content[:200]}"


async def test_triage_sync_empty_message_still_responds(client):
    """An empty message should return a response, not a 500."""
    resp = await client.post(
        "/triage/sync",
        json={"message": ""},
        timeout=60,
    )

    # Should return 200 (agent handles gracefully) or 422 (validation) — not 500
    assert resp.status_code in (200, 422)


async def test_triage_sync_unrelated_question_still_returns(client):
    """Non-incident question returns a response without crashing."""
    resp = await client.post(
        "/triage/sync",
        json={"message": "What is 2 + 2?"},
        timeout=60,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["response"]) > 0
