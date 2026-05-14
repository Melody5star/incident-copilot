# Incident Copilot 🚨

Autonomous DevOps incident triage agent built on **Google Cloud ADK + Gemini**. Detects production anomalies via **Elastic**, traces the offending commit in **GitLab**, and files a structured incident issue — all in under 60 seconds, without paging a human.

> Built for Google Cloud Rapid Agent Hackathon (May–June 2026)  
> Partner tracks: **GitLab · Elastic · Arize**

---

## What it does

1. **Detect** — Queries Elasticsearch for services with elevated error rates
2. **Investigate** — Pulls recent error logs and stack traces
3. **Hypothesize** — Gemini reasons over the evidence to form a root cause hypothesis
4. **Trace source** — Searches GitLab for commits touching the suspect file
5. **Act** — Files a structured GitLab issue with all evidence, cited

All LLM calls are traced in **Arize Phoenix** for observability and hallucination monitoring.

---

## Architecture

```
User / Demo UI (Streamlit)
        │
        ▼
FastAPI Backend (Cloud Run)
        │
        ▼
  Incident Copilot Agent (Google ADK)
        │
   ┌────┼────────────────────┐
   │    │                    │
   ▼    ▼                    ▼
Elastic  GitLab MCP      Arize Phoenix
(logs)  (commits/issues)  (LLM traces)
   │
Gemini 2.5 Pro (Vertex AI)
```

---

## Quick start

```bash
# 1. Clone and install
git clone <your-repo-url>
cd incident_copilot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Fill in: GOOGLE_CLOUD_PROJECT, ELASTIC_*, GITLAB_*, PHOENIX_*

# 3. Authenticate with GCP
gcloud auth application-default login

# 4. Run backend
uvicorn api.main:app --port 8080 --reload

# 5. Run UI (separate terminal)
streamlit run ui/app.py
```

---

## Credentials setup

### Google Cloud
1. Create a project at [console.cloud.google.com](https://console.cloud.google.com)
2. Enable APIs: `gcloud services enable aiplatform.googleapis.com run.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com`
3. Apply for $100 hackathon credits via the DevPost Resources tab (deadline: June 4)

### Elastic
1. Sign up at [elastic.co/cloud](https://cloud.elastic.co/) (14-day trial)
2. Create a deployment, copy the Cloud ID from the deployment page
3. Create an API key in Kibana > Stack Management > API Keys

### GitLab
1. Create a Personal Access Token at gitlab.com/-/user_settings/personal_access_tokens
2. Scopes required: `api`, `read_repository`, `write_repository`
3. Set `GITLAB_PROJECT_ID` to the numeric ID of your target project

### Arize Phoenix
1. Sign up at [app.phoenix.arize.com](https://app.phoenix.arize.com)
2. Copy your API key from the settings page
3. Set `PHOENIX_PROJECT_NAME` to identify this project's traces

---

## Deploy to Cloud Run

```bash
# Build and push via Cloud Build
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION=us-central1

# Or manually
docker build -t gcr.io/$PROJECT_ID/incident-copilot .
docker push gcr.io/$PROJECT_ID/incident-copilot
gcloud run deploy incident-copilot \
  --image gcr.io/$PROJECT_ID/incident-copilot \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 1
```

---

## License

MIT
