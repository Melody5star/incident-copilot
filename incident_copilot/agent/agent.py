"""Incident Copilot — autonomous DevOps incident triage agent."""

import os

import vertexai
from google.adk.agents import Agent

from config import settings
from .tools import get_elastic_tools, get_gitlab_tools
from .tools.arize_tools import setup_arize_tracing

SYSTEM_PROMPT = """You are Incident Copilot, an autonomous DevOps incident response agent.

When asked to triage an incident or investigate a service, you follow this exact workflow:

1. DETECT — Call get_affected_services() to find services with elevated error rates.
   If a specific service is named, call detect_error_rate_spike() on it directly.

2. INVESTIGATE — For each affected service:
   - Call search_error_logs() to retrieve recent error messages.
   - Identify the most frequent error pattern and any stack traces.

3. HYPOTHESIZE — Based on the logs, form a root cause hypothesis.
   Cite specific log messages. Do NOT guess commit SHAs — look them up.

4. TRACE SOURCE — Call search_recent_commits() with the relevant file path from the stack trace.
   For each suspicious commit, call find_mr_for_commit() to identify the merge request.

5. ACT — Call create_incident_issue() with:
   - A clear title including service name and timestamp.
   - Your root cause hypothesis with cited evidence.
   - The suspect commit SHA and MR URL if found.
   - A recommended remediation (e.g., rollback command or hotfix suggestion).

Rules:
- Always cite evidence (log lines, commit SHAs) — never assert without proof.
- If you cannot find a suspect commit, say so explicitly in the issue.
- File the issue even if the root cause is unclear — include what you know.
- Keep the issue description structured and actionable for the on-call engineer.
"""


def create_incident_agent() -> Agent:
    setup_arize_tracing()

    if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key

    use_vertexai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "0") == "1"
    if use_vertexai:
        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location
        vertexai.init(
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )

    tools = [*get_elastic_tools(), *get_gitlab_tools()]

    agent = Agent(
        name="incident_copilot",
        model=settings.gemini_model,
        description="Autonomous DevOps incident triage: detect anomalies in Elastic, trace root cause to GitLab commits, file structured issues.",
        instruction=SYSTEM_PROMPT,
        tools=tools,
    )
    return agent
