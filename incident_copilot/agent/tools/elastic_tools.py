"""Elastic MCP tool wrappers for log search and anomaly detection."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from elasticsearch import AsyncElasticsearch
from google.adk.tools import FunctionTool

from config import settings


def _get_client() -> AsyncElasticsearch:
    if settings.elastic_cloud_id:
        # Elastic Cloud
        return AsyncElasticsearch(
            cloud_id=settings.elastic_cloud_id,
            api_key=settings.elastic_api_key,
        )
    # Self-hosted or Serverless Cloud endpoint
    return AsyncElasticsearch(
        hosts=[settings.elastic_hosts],
        api_key=settings.elastic_api_key if settings.elastic_api_key else None,
    )


async def search_error_logs(
    service_name: str,
    minutes_back: int = 15,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Elasticsearch for recent error logs from a specific service.

    Args:
        service_name: The name of the service to search logs for.
        minutes_back: How many minutes of history to search (default 15).
        max_results: Maximum number of log entries to return (default 50).

    Returns:
        Dict with 'total' count and 'logs' list of matching entries.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes_back)
    query = {
        "bool": {
            "must": [
                {"term": {"service.name.keyword": service_name}},
                {"terms": {"log.level.keyword": ["ERROR", "CRITICAL", "FATAL"]}},
                {"range": {"@timestamp": {"gte": since.isoformat()}}},
            ]
        }
    }
    async with _get_client() as es:
        resp = await es.search(
            index=settings.elastic_index_pattern,
            query=query,
            size=max_results,
            sort=[{"@timestamp": {"order": "desc"}}],
        )
    hits = resp["hits"]["hits"]
    return {
        "total": resp["hits"]["total"]["value"],
        "logs": [h["_source"] for h in hits],
    }


async def detect_error_rate_spike(
    service_name: str,
    window_minutes: int = 5,
    baseline_minutes: int = 60,
) -> dict[str, Any]:
    """Detect if a service has an unusual error rate spike compared to its baseline.

    Args:
        service_name: The service to check.
        window_minutes: Recent window to measure current error rate (default 5 min).
        baseline_minutes: Longer window for baseline comparison (default 60 min).

    Returns:
        Dict with 'spike_detected', 'current_rate', 'baseline_rate', 'multiplier'.
    """
    now = datetime.now(timezone.utc)
    recent_since = now - timedelta(minutes=window_minutes)
    baseline_since = now - timedelta(minutes=baseline_minutes)

    base_query = {
        "bool": {
            "must": [
                {"match": {"service.name": service_name}},
                {"terms": {"log.level.keyword": ["ERROR", "CRITICAL", "FATAL"]}},
            ]
        }
    }

    def _with_range(since: datetime) -> dict:
        return {
            "bool": {
                "must": [
                    {"term": {"service.name.keyword": service_name}},
                    {"terms": {"log.level.keyword": ["ERROR", "CRITICAL", "FATAL"]}},
                    {"range": {"@timestamp": {"gte": since.isoformat()}}},
                ]
            }
        }

    async with _get_client() as es:
        recent_resp = await es.count(
            index=settings.elastic_index_pattern,
            query=_with_range(recent_since),
        )
        baseline_resp = await es.count(
            index=settings.elastic_index_pattern,
            query=_with_range(baseline_since),
        )

    recent_count = recent_resp["count"]
    baseline_count = baseline_resp["count"]

    current_rate = recent_count / window_minutes
    baseline_rate = (baseline_count / baseline_minutes) if baseline_minutes else 0
    # 0/0 is not a spike — only flag when there are actual recent errors
    if recent_count == 0:
        multiplier = 0.0
    elif baseline_rate == 0:
        multiplier = float("inf")
    else:
        multiplier = current_rate / baseline_rate

    return {
        "spike_detected": recent_count > 0 and multiplier >= 3.0,
        "current_rate": round(current_rate, 2),
        "baseline_rate": round(baseline_rate, 2),
        "multiplier": round(multiplier, 2),
        "service_name": service_name,
    }


async def get_affected_services(minutes_back: int = 10) -> dict[str, Any]:
    """Find all services with elevated error rates in the recent time window.

    Args:
        minutes_back: How many minutes to look back (default 10).

    Returns:
        Dict with 'services' list of service names with error counts, sorted by severity.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes_back)
    agg_query = {
        "bool": {
            "must": [
                {"terms": {"log.level.keyword": ["ERROR", "CRITICAL", "FATAL"]}},
                {"range": {"@timestamp": {"gte": since.isoformat()}}},
            ]
        }
    }
    async with _get_client() as es:
        resp = await es.search(
            index=settings.elastic_index_pattern,
            query=agg_query,
            size=0,
            aggs={
                "by_service": {
                    "terms": {"field": "service.name.keyword", "size": 20, "order": {"_count": "desc"}}
                }
            },
        )
    buckets = resp["aggregations"]["by_service"]["buckets"]
    return {
        "services": [{"name": b["key"], "error_count": b["doc_count"]} for b in buckets]
    }


async def get_log_context(
    trace_id: str,
    max_results: int = 100,
) -> dict[str, Any]:
    """Fetch all log entries associated with a specific distributed trace ID.

    Args:
        trace_id: The trace ID to look up.
        max_results: Maximum log entries to return (default 100).

    Returns:
        Dict with 'logs' list of log entries for the trace, in time order.
    """
    async with _get_client() as es:
        resp = await es.search(
            index=settings.elastic_index_pattern,
            query={"term": {"trace.id": trace_id}},
            size=max_results,
            sort=[{"@timestamp": {"order": "asc"}}],
        )
    return {"logs": [h["_source"] for h in resp["hits"]["hits"]]}


def get_elastic_tools() -> list[FunctionTool]:
    return [
        FunctionTool(search_error_logs),
        FunctionTool(detect_error_rate_spike),
        FunctionTool(get_affected_services),
        FunctionTool(get_log_context),
    ]
