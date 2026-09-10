#!/usr/bin/env bash
# Compute Engine startup script for the ChantierMobile Celery worker + beat VM.
#
# Runs on every boot (GCE re-runs the startup script on restart). Installs
# Docker, the Cloud SQL Auth Proxy, and (re)starts the celery worker+beat
# container against the same Cloud SQL instance and Upstash Redis broker
# used by the Cloud Run web service.
#
# Expects these to have been set as VM metadata (see deploy.sh):
#   gce-container-image   -- e.g. gcr.io/PROJECT/chantiermobile:latest
#   database-url          -- postgresql://... (Cloud SQL Auth Proxy target: 127.0.0.1:5432)
#   redis-url             -- rediss://... (Upstash)
#   secret-key            -- Django SECRET_KEY
#   cloudsql-connection   -- PROJECT:REGION:INSTANCE

set -euo pipefail

apt-get update -y
apt-get install -y docker.io

CONNECTION_NAME=$(curl -sH "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/cloudsql-connection")
IMAGE=$(curl -sH "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/gce-container-image")
DATABASE_URL=$(curl -sH "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/database-url")
REDIS_URL=$(curl -sH "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/redis-url")
SECRET_KEY=$(curl -sH "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/secret-key")

# Cloud SQL Auth Proxy as a sidecar container, exposing 127.0.0.1:5432 on the VM.
docker rm -f cloudsql-proxy 2>/dev/null || true
docker run -d --name cloudsql-proxy --restart=always --network=host \
  gcr.io/cloud-sql-connectors/cloud-sql-proxy:latest \
  --address 0.0.0.0 --port 5432 "$CONNECTION_NAME"

docker pull "$IMAGE"
docker rm -f celery-worker 2>/dev/null || true
docker run -d --name celery-worker --restart=always --network=host \
  -e DJANGO_SETTINGS_MODULE=chantiermobile.settings \
  -e DEBUG=False \
  -e SECRET_KEY="$SECRET_KEY" \
  -e DATABASE_URL="$DATABASE_URL" \
  -e REDIS_URL="$REDIS_URL" \
  "$IMAGE" \
  celery -A chantiermobile worker --beat --loglevel=info --concurrency=1
