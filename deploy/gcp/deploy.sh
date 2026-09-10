#!/usr/bin/env bash
# ChantierMobile — GCP deployment script.
#
# Prerequisites (one-time, done by a human — see deploy/gcp/README.md):
#   1. GCP project created with billing enabled
#   2. `gcloud auth login` completed
#   3. Upstash Redis database created (free tier) — REDIS_URL below
#   4. Cloudflare R2 bucket + API token created (or reuse the existing one
#      from Railway) — CLOUDFARE_R2_* below
#
# Fill in the variables below, then run: bash deploy/gcp/deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="chantiermobile"
SQL_INSTANCE="chantiermobile-db"
SQL_DB_NAME="chantiermobile"
SQL_DB_USER="chantiermobile"
SQL_DB_PASSWORD="${SQL_DB_PASSWORD:?set SQL_DB_PASSWORD}"
SECRET_KEY="${SECRET_KEY:?set SECRET_KEY}"
REDIS_URL="${REDIS_URL:?set REDIS_URL (Upstash rediss:// URL)}"
CLOUDFARE_R2_TOKEN_NAME="${CLOUDFARE_R2_TOKEN_NAME:?set CLOUDFARE_R2_TOKEN_NAME}"
CLOUDFARE_API_TOKEN="${CLOUDFARE_API_TOKEN:?set CLOUDFARE_API_TOKEN}"
CLOUDFARE_R2_BUCKET_NAME="${CLOUDFARE_R2_BUCKET_NAME:?set CLOUDFARE_R2_BUCKET_NAME}"
CLOUDFARE_R2_BUCKET_URL="${CLOUDFARE_R2_BUCKET_URL:?set CLOUDFARE_R2_BUCKET_URL}"

gcloud config set project "$PROJECT_ID"

echo "== Enabling required APIs =="
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  compute.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

CONNECTION_NAME="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"

if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  echo "== Creating Cloud SQL Postgres instance (db-f1-micro) =="
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_16 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --storage-size=10GB \
    --storage-auto-increase
  gcloud sql databases create "$SQL_DB_NAME" --instance="$SQL_INSTANCE"
  gcloud sql users create "$SQL_DB_USER" --instance="$SQL_INSTANCE" --password="$SQL_DB_PASSWORD"
else
  echo "== Cloud SQL instance $SQL_INSTANCE already exists, skipping create =="
fi

# Cloud Run reaches Cloud SQL over a unix socket at /cloudsql/<connection-name>,
# mounted automatically by --add-cloudsql-instances.
DATABASE_URL="postgresql://${SQL_DB_USER}:${SQL_DB_PASSWORD}@/${SQL_DB_NAME}?host=/cloudsql/${CONNECTION_NAME}"

echo "== Building and deploying web service to Cloud Run =="
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances "$CONNECTION_NAME" \
  --min-instances 1 \
  --max-instances 1 \
  --set-env-vars "DJANGO_SETTINGS_MODULE=chantiermobile.settings,DEBUG=False,SECRET_KEY=${SECRET_KEY},DATABASE_URL=${DATABASE_URL},REDIS_URL=${REDIS_URL},CLOUDFARE_R2_TOKEN_NAME=${CLOUDFARE_R2_TOKEN_NAME},CLOUDFARE_API_TOKEN=${CLOUDFARE_API_TOKEN},CLOUDFARE_R2_BUCKET_NAME=${CLOUDFARE_R2_BUCKET_NAME},CLOUDFARE_R2_BUCKET_URL=${CLOUDFARE_R2_BUCKET_URL}"

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')
SERVICE_HOST="${SERVICE_URL#https://}"

echo "== Updating ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS now that the URL is known =="
gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --update-env-vars "ALLOWED_HOSTS=${SERVICE_HOST},CSRF_TRUSTED_ORIGINS=${SERVICE_URL}"

echo "== Deployed: ${SERVICE_URL} =="

IMAGE=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(spec.template.spec.containers[0].image)')

echo "== Creating/updating the Celery worker+beat VM =="
if ! gcloud compute instances describe chantiermobile-worker --zone "${REGION}-a" >/dev/null 2>&1; then
  gcloud compute instances create chantiermobile-worker \
    --zone "${REGION}-a" \
    --machine-type e2-micro \
    --image-family debian-12 \
    --image-project debian-cloud \
    --scopes cloud-platform \
    --metadata-from-file startup-script=deploy/gcp/celery-vm-startup.sh \
    --metadata "gce-container-image=${IMAGE},database-url=${DATABASE_URL},redis-url=${REDIS_URL},secret-key=${SECRET_KEY},cloudsql-connection=${CONNECTION_NAME}"
else
  gcloud compute instances add-metadata chantiermobile-worker \
    --zone "${REGION}-a" \
    --metadata "gce-container-image=${IMAGE},database-url=${DATABASE_URL},redis-url=${REDIS_URL},secret-key=${SECRET_KEY},cloudsql-connection=${CONNECTION_NAME}"
  gcloud compute instances reset chantiermobile-worker --zone "${REGION}-a"
fi

echo "== Done. Web: ${SERVICE_URL} | Worker VM: chantiermobile-worker (${REGION}-a) =="
