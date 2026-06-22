#!/usr/bin/env bash
# Deploys the Multi-Tenant Agentic Voice Orchestrator to GCP Cloud Run.
#
# Prerequisites:
#   1. `gcloud auth login` and `gcloud config set project <YOUR_PROJECT_ID>`
#   2. APIs enabled: run.googleapis.com, cloudbuild.googleapis.com,
#      secretmanager.googleapis.com, sqladmin.googleapis.com (if using Cloud SQL)
#   3. Secrets created in Secret Manager (one-time):
#        gcloud secrets create DATABASE_URL --data-file=-
#        gcloud secrets create VAPI_PRIVATE_KEY --data-file=-
#        gcloud secrets create VAPI_ASSISTANT_ID --data-file=-
#        gcloud secrets create VAPI_PHONE_NUMBER_ID --data-file=-
#        gcloud secrets create VAPI_WEBHOOK_SECRET --data-file=-
#        gcloud secrets create OPENAI_API_KEY --data-file=-
#        gcloud secrets create GEMINI_API_KEY --data-file=-
#      (each command reads the secret value from stdin; pipe in the value or
#       paste it and press Ctrl+D)
#
# Usage:
#   ./deploy.sh

set -euo pipefail

PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
REGION="us-central1"
SERVICE_NAME="voice-orchestrator"
CLOUDSQL_INSTANCE="" # Set this to your Cloud SQL instance connection name (e.g. PROJECT:REGION:INSTANCE) if using Cloud SQL

if [[ -z "$PROJECT_ID" ]]; then
  echo "No active gcloud project. Run: gcloud config set project <YOUR_PROJECT_ID>"
  exit 1
fi

echo "==> Building and deploying to project: $PROJECT_ID (region: $REGION)"

gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION="$REGION",_CLOUDSQL_INSTANCE="$CLOUDSQL_INSTANCE" .

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --format="value(status.url)")"

echo ""
echo "==> Deployed successfully."
echo "==> Service URL: $SERVICE_URL"
echo "==> Register this as your Vapi assistant's webhook target:"
echo "       ${SERVICE_URL}/api/webhooks/vapi"
