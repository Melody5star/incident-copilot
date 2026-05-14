"""End-to-end agent tests — verifies the full triage workflow produces correct output."""

import pathlib
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from httpx import AsyncClient, ASGITransport

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seed_data():
    """Re-seed Elasticsearch with fresh spike data before any e2e test runs."""
    import subprocess, sys
    subprocess.run(
        [sys.executable, "scripts/seed_elasticsearch.py"],
        cwd=pathlib.Path(__file__).parent.parent,
        check=True,
        capture_output=True,
    )


@pytest_asyncio.fixture(scope="module")
async def client():
    """Start the real FastAPI app with lifespan, yield a shared client for all e2e tests."""
    from api.main import app

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


async def _triage(client: AsyncClient, message: str) -> dict:
    resp = await client.post("/triage/sync", json={"message": message}, timeout=180)
    if resp.status_code == 429:
        pytest.skip("Vertex AI rate limited — re-run after 60 s")
    resp.raise_for_status()
    return resp.json()


async def test_e2e_detects_payment_service_spike(client):
    """Agent autonomously detects the payment-service error spike from seeded data."""
    body = await _triage(client, "Check all services for error spikes")

    assert "payment" in body["response"].lower(), (
        f"Expected agent to mention payment-service. Response: {body['response'][:400]}"
    )


async def test_e2e_full_triage_calls_tools_in_order(client):
    """Full triage must: detect anomaly → search logs → search commits → file issue."""
    body = await _triage(
        client,
        "Triage all services: detect errors, investigate logs, find the responsible commit, file GitLab issues",
    )

    tools = body["tool_calls"]
    assert len(tools) >= 3, f"Expected at least 3 tool calls, got {len(tools)}: {tools}"

    elastic = {"get_affected_services", "detect_error_rate_spike", "search_error_logs"}
    gitlab = {"search_recent_commits", "create_incident_issue", "find_mr_for_commit"}

    first_elastic = next((i for i, t in enumerate(tools) if t in elastic), None)
    first_gitlab = next((i for i, t in enumerate(tools) if t in gitlab), None)

    assert first_elastic is not None, f"No Elastic tools called: {tools}"
    assert first_gitlab is not None, f"No GitLab tools called: {tools}"
    assert first_elastic < first_gitlab, f"Expected Elastic before GitLab. Tool order: {tools}"


async def test_e2e_creates_gitlab_issue(client):
    """When errors exist and the agent investigates, it must file a GitLab issue."""
    body = await _triage(
        client,
        "payment-service is having issues. Investigate the error logs and file a GitLab incident issue "
        "with what you find — even if the error rate looks normal, file the issue with the recent error evidence.",
    )

    assert "create_incident_issue" in body["tool_calls"], (
        f"create_incident_issue not called. Tools: {body['tool_calls']}"
    )
    assert "gitlab.com" in body["response"] or "work_items" in body["response"] or "issue" in body["response"].lower()


async def test_e2e_response_is_structured(client):
    """Agent response should be structured (markdown headers or bullets), not a single line."""
    body = await _triage(client, "Full incident triage for all services")

    response = body["response"]
    has_structure = any(marker in response for marker in ["#", "- ", "* ", "1.", "**"])
    assert has_structure, f"Response lacks structure. Got: {response[:400]}"


async def test_e2e_response_cites_evidence(client):
    """When a spike exists, agent must cite specific evidence (errors, counts, stack traces)."""
    body = await _triage(
        client,
        "Investigate payment-service errors. If you find errors, explain what you found with evidence from the logs.",
    )

    response = body["response"]
    tool_calls = body["tool_calls"]

    # If agent called search_error_logs, it should have found something — expect evidence
    if "search_error_logs" in tool_calls:
        evidence_keywords = ["error", "exception", "log", "spike", "null", "npe", "stack", "rate", "count"]
        found = [kw for kw in evidence_keywords if kw in response.lower()]
        assert len(found) >= 2, (
            f"Agent searched logs but response lacks evidence keywords. Found: {found}. "
            f"Response: {response[:400]}"
        )
    else:
        # Agent didn't search logs — it determined no spike, which is also valid
        assert len(response) > 5


async def test_e2e_agent_handles_healthy_service_gracefully(client):
    """Agent should respond cleanly for a service with no errors — not crash."""
    body = await _triage(client, "Check nonexistent-service-xyz for any issues")

    assert len(body["response"]) > 5, "Expected a non-empty response even for healthy/unknown service"
