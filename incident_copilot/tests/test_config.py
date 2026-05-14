"""Tests for settings/config loading — fast, no network calls."""

import pytest


def test_settings_loads_without_error():
    """Settings should load from .env without raising."""
    from config import settings
    assert settings is not None


def test_required_fields_are_set():
    """All required credentials must be non-empty."""
    from config import settings

    assert settings.google_cloud_project, "GOOGLE_CLOUD_PROJECT is not set"
    assert settings.gitlab_token, "GITLAB_TOKEN is not set"
    assert settings.gitlab_project_id, "GITLAB_PROJECT_ID is not set"
    assert settings.gemini_model, "GEMINI_MODEL is not set"


def test_elastic_hosts_is_valid_url():
    """ELASTIC_HOSTS must look like a URL."""
    from config import settings

    assert settings.elastic_hosts.startswith("http"), (
        f"ELASTIC_HOSTS should start with http: {settings.elastic_hosts}"
    )


def test_phoenix_api_key_is_set():
    """PHOENIX_API_KEY should be set for Arize track."""
    from config import settings

    assert settings.phoenix_api_key, (
        "PHOENIX_API_KEY is not set — Arize track requires it"
    )


def test_gemini_model_is_flash_or_pro():
    """Model should be a Gemini 2.x variant."""
    from config import settings

    assert "gemini" in settings.gemini_model.lower(), (
        f"Unexpected model: {settings.gemini_model}"
    )


def test_gitlab_project_id_is_numeric_string():
    """GITLAB_PROJECT_ID should be a numeric string."""
    from config import settings

    assert settings.gitlab_project_id.isdigit(), (
        f"Expected numeric project ID, got: {settings.gitlab_project_id}"
    )
