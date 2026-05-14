"""GitLab MCP tool wrappers for commit search, MR lookup, and issue filing."""

from datetime import datetime, timedelta, timezone
from typing import Any

import gitlab
from google.adk.tools import FunctionTool

from config import settings


def _get_client() -> gitlab.Gitlab:
    return gitlab.Gitlab(settings.gitlab_url, private_token=settings.gitlab_token)


def _get_project(gl: gitlab.Gitlab) -> Any:
    return gl.projects.get(settings.gitlab_project_id)


async def search_recent_commits(
    file_path: str = "",
    hours_back: int = 24,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search GitLab for commits touching a specific file path in the recent time window.

    Args:
        file_path: Path filter — returns commits touching this file (empty = all commits).
        hours_back: How many hours of history to search (default 24).
        max_results: Maximum commits to return (default 20).

    Returns:
        Dict with 'commits' list of {sha, title, author, created_at, web_url}.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    gl = _get_client()
    project = _get_project(gl)
    kwargs: dict[str, Any] = {"since": since, "per_page": max_results}
    if file_path:
        kwargs["path"] = file_path

    try:
        commits_raw = project.commits.list(**kwargs, get_all=False)
    except Exception as exc:
        return {"error": str(exc), "commits": []}
    return {
        "commits": [
            {
                "sha": c.id,
                "short_sha": c.short_id,
                "title": c.title,
                "author": c.author_name,
                "created_at": c.created_at,
                "web_url": f"{settings.gitlab_url}/{project.path_with_namespace}/-/commit/{c.id}",
            }
            for c in commits_raw
        ]
    }


async def get_merge_request(mr_iid: int) -> dict[str, Any]:
    """Fetch details of a specific GitLab Merge Request by its internal ID.

    Args:
        mr_iid: The merge request's internal project IID (not the global ID).

    Returns:
        Dict with MR title, description, author, merged_at, state, and web_url.
    """
    try:
        gl = _get_client()
        project = _get_project(gl)
        mr = project.mergerequests.get(mr_iid)
    except Exception as exc:
        return {"error": str(exc)}
    return {
        "iid": mr.iid,
        "title": mr.title,
        "description": mr.description,
        "author": mr.author["name"],
        "state": mr.state,
        "merged_at": getattr(mr, "merged_at", None),
        "source_branch": mr.source_branch,
        "target_branch": mr.target_branch,
        "web_url": mr.web_url,
    }


async def find_mr_for_commit(commit_sha: str) -> dict[str, Any]:
    """Find the merge request that introduced a specific commit SHA.

    Args:
        commit_sha: The full or short commit SHA to look up.

    Returns:
        Dict with 'merge_request' details if found, or 'found': False.
    """
    gl = _get_client()
    project = _get_project(gl)
    try:
        commit = project.commits.get(commit_sha)
        mrs = commit.merge_requests()
        if mrs:
            mr = mrs[0]
            return {
                "found": True,
                "merge_request": {
                    "iid": mr["iid"],
                    "title": mr["title"],
                    "author": mr["author"]["name"],
                    "merged_at": mr.get("merged_at"),
                    "web_url": mr["web_url"],
                },
            }
    except Exception:
        pass
    return {"found": False}


async def create_incident_issue(
    title: str,
    service_name: str,
    root_cause_hypothesis: str,
    evidence_summary: str,
    suspect_commit_sha: str = "",
    suspect_mr_url: str = "",
    recommended_action: str = "",
) -> dict[str, Any]:
    """Create a structured incident issue in GitLab with root cause analysis.

    Args:
        title: Issue title (e.g. 'Incident: checkout-service error spike — 2026-05-10').
        service_name: Name of the impacted service.
        root_cause_hypothesis: Gemini's hypothesis for what caused the incident.
        evidence_summary: Summary of logs/traces that support the hypothesis.
        suspect_commit_sha: The commit SHA suspected to have introduced the bug (optional).
        suspect_mr_url: Web URL to the suspect merge request (optional).
        recommended_action: Suggested fix or rollback command (optional).

    Returns:
        Dict with 'issue_iid', 'web_url', and 'created_at'.
    """
    gl = _get_client()
    project = _get_project(gl)

    body_parts = [
        f"## Incident Report — {service_name}",
        f"**Detected:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "### Root Cause Hypothesis",
        root_cause_hypothesis,
        "",
        "### Evidence",
        evidence_summary,
    ]
    if suspect_commit_sha:
        body_parts += ["", f"### Suspect Commit", f"`{suspect_commit_sha}`"]
    if suspect_mr_url:
        body_parts += ["", f"### Suspect MR", suspect_mr_url]
    if recommended_action:
        body_parts += ["", "### Recommended Action", f"```\n{recommended_action}\n```"]
    body_parts += ["", "---", "*Filed automatically by Incident Copilot agent.*"]

    # Try with labels first; fall back to no labels if GitLab returns 500
    # (happens when label names don't pre-exist in the project)
    for payload in [
        {"title": title, "description": "\n".join(body_parts), "labels": ["incident", "automated"]},
        {"title": title, "description": "\n".join(body_parts)},
    ]:
        try:
            issue = project.issues.create(payload)
            return {
                "issue_iid": issue.iid,
                "web_url": issue.web_url,
                "created_at": issue.created_at,
            }
        except Exception as exc:
            last_exc = exc
            continue

    return {
        "error": str(last_exc),
        "issue_draft": "\n".join(body_parts[:10]),
    }


def get_gitlab_tools() -> list[FunctionTool]:
    return [
        FunctionTool(search_recent_commits),
        FunctionTool(get_merge_request),
        FunctionTool(find_mr_for_commit),
        FunctionTool(create_incident_issue),
    ]
