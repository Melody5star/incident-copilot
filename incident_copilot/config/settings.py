from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Google Cloud
    google_cloud_project: str
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-2.5-pro-preview-05-06"
    google_api_key: str = ""

    # Elastic — use elastic_hosts for self-hosted, or elastic_cloud_id for Elastic Cloud
    elastic_hosts: str = "http://localhost:9200"  # self-hosted default
    elastic_cloud_id: str = ""   # set this to use Elastic Cloud instead
    elastic_api_key: str = ""    # only needed for Elastic Cloud
    elastic_index_pattern: str = "logs-*"

    # GitLab
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str
    gitlab_project_id: str

    # Arize Phoenix
    phoenix_api_key: str = ""
    phoenix_collector_endpoint: str = "https://app.phoenix.arize.com"
    phoenix_project_name: str = "incident-copilot"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    log_level: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
