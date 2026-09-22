#!/usr/bin/env bash
#
# One-time production bootstrap for ChantierMobile.
#
# What this does:
#   1. Reads the LIVE "chantiermobile" Cloud Run service's exact image,
#      Cloud SQL connection, VPC connector, env vars and secrets.
#   2. Shows you what it found and asks for confirmation.
#   3. Creates (or updates) a one-off Cloud Run Job with that same config,
#      overriding the container command to run:
#        python manage.py bootstrap_admin_and_roles
#   4. Executes the job and prints its logs, which include the generated
#      temporary passwords for the demo accounts (shown only this once).
#
# The command it runs is idempotent: dieudonneishara@gmail.com is promoted
# to superuser/staff, and one demo account per role (DIRECTOR,
# CHIEF_ENGINEER, ENGINEER, ACCOUNTANT, CASHIER, WORKER) is created with a
# random password and must_change_password=True. Re-running this script
# later is safe -- existing accounts are left untouched.
#
# Usage (in Cloud Shell, with the chantiermobile-prod project available):
#   bash bootstrap_production.sh
#
set -euo pipefail

PROJECT="${PROJECT:-chantiermobile-prod}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-chantiermobile}"
JOB="${JOB:-chantiermobile-bootstrap}"

echo "Project: $PROJECT | Region: $REGION | Service: $SERVICE"
gcloud config set project "$PROJECT" >/dev/null

echo "==> Reading live service config for '$SERVICE'..."
gcloud run services describe "$SERVICE" --region="$REGION" --format=json > /tmp/svc.json

python3 > /tmp/job_config.sh <<'PYEOF'
import json

with open('/tmp/svc.json') as f:
    svc = json.load(f)

spec = svc['spec']['template']['spec']
meta = svc['spec']['template'].get('metadata', {})
ann = meta.get('annotations', {})
container = spec['containers'][0]

image = container['image']
service_account = spec.get('serviceAccountName', '')
cloudsql = ann.get('run.googleapis.com/cloudsql-instances', '')
vpc_connector = ann.get('run.googleapis.com/vpc-access-connector', '')

env_pairs = []
secret_pairs = []
for e in container.get('env', []):
    name = e['name']
    if 'valueFrom' in e and 'secretKeyRef' in e.get('valueFrom', {}):
        ref = e['valueFrom']['secretKeyRef']
        secret_pairs.append(f"{name}={ref['name']}:{ref.get('key', 'latest')}")
    else:
        env_pairs.append(f"{name}={e.get('value', '')}")

def sh_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"

print(f"IMAGE={sh_quote(image)}")
print(f"SERVICE_ACCOUNT={sh_quote(service_account)}")
print(f"CLOUDSQL={sh_quote(cloudsql)}")
print(f"VPC_CONNECTOR={sh_quote(vpc_connector)}")
print(f"ENV_VARS={sh_quote(','.join(env_pairs))}")
print(f"SECRET_VARS={sh_quote(','.join(secret_pairs))}")
PYEOF

# shellcheck source=/dev/null
source /tmp/job_config.sh

echo
echo "Resolved from the live service:"
echo "  Image:           $IMAGE"
echo "  Service account: ${SERVICE_ACCOUNT:-<default>}"
echo "  Cloud SQL:       ${CLOUDSQL:-<none>}"
echo "  VPC connector:   ${VPC_CONNECTOR:-<none>}"
echo "  Env vars found:  $(echo -n "$ENV_VARS" | tr ',' '\n' | grep -c . || true)"
echo "  Secrets found:   $(echo -n "$SECRET_VARS" | tr ',' '\n' | grep -c . || true)"
echo
read -r -p "Create and run the one-off bootstrap job with this config? [y/N] " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Aborted -- nothing was created or run."
  exit 1
fi

ARGS=(
  "$JOB"
  "--image=$IMAGE"
  "--region=$REGION"
  "--command=python"
  "--args=manage.py,bootstrap_admin_and_roles"
  "--task-timeout=300"
  "--max-retries=0"
)
[ -n "$SERVICE_ACCOUNT" ] && ARGS+=("--service-account=$SERVICE_ACCOUNT")
[ -n "$CLOUDSQL" ] && ARGS+=("--set-cloudsql-instances=$CLOUDSQL")
[ -n "$VPC_CONNECTOR" ] && ARGS+=("--vpc-connector=$VPC_CONNECTOR")
[ -n "$ENV_VARS" ] && ARGS+=("--set-env-vars=$ENV_VARS")
[ -n "$SECRET_VARS" ] && ARGS+=("--set-secrets=$SECRET_VARS")

echo "==> Creating/updating job '$JOB'..."
if gcloud run jobs describe "$JOB" --region="$REGION" >/dev/null 2>&1; then
  gcloud run jobs update "${ARGS[@]}"
else
  gcloud run jobs create "${ARGS[@]}"
fi

echo "==> Executing job (usually 30-60s)..."
EXECUTION=$(gcloud run jobs execute "$JOB" --region="$REGION" --wait --format='value(metadata.name)')

echo
echo "==> Job output (generated credentials print near the bottom):"
echo
sleep 5
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=\"$JOB\" AND labels.\"run.googleapis.com/execution_name\"=\"$EXECUTION\"" \
  --project="$PROJECT" \
  --format='value(textPayload)' \
  --order=asc \
  --freshness=10m

echo
echo "Done. Save the printed passwords now -- they will not be shown again."
echo "Optional cleanup once you've saved them:"
echo "  gcloud run jobs delete $JOB --region=$REGION"
