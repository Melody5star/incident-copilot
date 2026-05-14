#!/bin/bash
# One-command Cloud Run deployment for Incident Copilot
# Run: bash deploy.sh
# Prerequisites: gcloud auth login done, Elastic Cloud credentials ready

set -e  # stop on any error

PROJECT_ID="incidentcopilotgchackthon"
REGION="us-central1"
SERVICE_NAME="incident-copilot"
REPO_NAME="incident-copilot"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/app:latest"

echo "=== Step 1: Set GCP project ==="
gcloud config set project $PROJECT_ID

echo "=== Step 2: Enable required APIs ==="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --quiet

echo "=== Step 3: Create Artifact Registry repo (if not exists) ==="
gcloud artifacts repositories create $REPO_NAME \
  --repository-format=docker \
  --location=$REGION \
  --quiet 2>/dev/null || echo "Repo already exists — continuing"

echo "=== Step 4: Authenticate Docker to Artifact Registry ==="
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

echo "=== Step 5: Build and push Docker image ==="
cd "$(dirname "$0")"
docker build -t $IMAGE .
docker push $IMAGE

echo "=== Step 6: Deploy to Cloud Run ==="
# Load env vars from .env file
source .env

gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=2 \
  --memory=2Gi \
  --cpu=1 \
  --timeout=300 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION" \
  --set-env-vars="GEMINI_MODEL=$GEMINI_MODEL" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=$GOOGLE_GENAI_USE_VERTEXAI" \
  --set-env-vars="GOOGLE_API_KEY=$GOOGLE_API_KEY" \
  --set-env-vars="ELASTIC_CLOUD_ID=$ELASTIC_CLOUD_ID" \
  --set-env-vars="ELASTIC_API_KEY=$ELASTIC_API_KEY" \
  --set-env-vars="ELASTIC_INDEX_PATTERN=$ELASTIC_INDEX_PATTERN" \
  --set-env-vars="GITLAB_URL=$GITLAB_URL" \
  --set-env-vars="GITLAB_TOKEN=$GITLAB_TOKEN" \
  --set-env-vars="GITLAB_PROJECT_ID=$GITLAB_PROJECT_ID" \
  --set-env-vars="PHOENIX_API_KEY=$PHOENIX_API_KEY" \
  --set-env-vars="PHOENIX_COLLECTOR_ENDPOINT=$PHOENIX_COLLECTOR_ENDPOINT" \
  --set-env-vars="PHOENIX_PROJECT_NAME=$PHOENIX_PROJECT_NAME" \
  --set-env-vars="APP_HOST=0.0.0.0" \
  --set-env-vars="APP_PORT=8080" \
  --set-env-vars="LOG_LEVEL=INFO" \
  --quiet

echo ""
echo "=== Deployment complete! ==="
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")
echo "Live URL: $SERVICE_URL"
echo "Health check: $SERVICE_URL/health"
echo ""
echo "Save this URL for DevPost submission: $SERVICE_URL"
