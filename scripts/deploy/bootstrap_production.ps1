<#
One-time production bootstrap for ChantierMobile (Windows / PowerShell version).

What this does:
  1. Reads the LIVE "chantiermobile" Cloud Run service's exact image,
     Cloud SQL connection, VPC connector, env vars and secrets.
  2. Shows you what it found and asks for confirmation.
  3. Creates (or updates) a one-off Cloud Run Job with that same config,
     overriding the container command to run:
       python manage.py bootstrap_admin_and_roles
  4. Executes the job and prints its logs, which include the generated
     temporary passwords for the demo accounts (shown only this once).

The command it runs is idempotent: dieudonneishara@gmail.com is promoted
to superuser/staff, and one demo account per role (DIRECTOR,
CHIEF_ENGINEER, ENGINEER, ACCOUNTANT, CASHIER, WORKER) is created with a
random password and must_change_password=True. Re-running this script
later is safe -- existing accounts are left untouched.

Requirements: Google Cloud SDK installed (gcloud available on PATH) and
already authenticated (`gcloud auth login`) with access to the
chantiermobile-prod project.

Usage (PowerShell):
    .\bootstrap_production.ps1
#>

$ErrorActionPreference = "Stop"

$Project = if ($env:PROJECT) { $env:PROJECT } else { "chantiermobile-prod" }
$Region  = if ($env:REGION)  { $env:REGION }  else { "us-central1" }
$Service = if ($env:SERVICE) { $env:SERVICE } else { "chantiermobile" }
$Job     = if ($env:JOB)     { $env:JOB }     else { "chantiermobile-bootstrap" }

Write-Host "Project: $Project | Region: $Region | Service: $Service"
gcloud config set project $Project | Out-Null

Write-Host "==> Reading live service config for '$Service'..."
$svcJsonText = gcloud run services describe $Service --region $Region --format=json
$svc = $svcJsonText | ConvertFrom-Json

$container = $svc.spec.template.spec.containers[0]
$image = $container.image
$serviceAccount = $svc.spec.template.spec.serviceAccountName
$annotations = $svc.spec.template.metadata.annotations
$cloudsql = $null
$vpcConnector = $null
if ($annotations) {
    $cloudsql = $annotations.'run.googleapis.com/cloudsql-instances'
    $vpcConnector = $annotations.'run.googleapis.com/vpc-access-connector'
}

$envPairs = @()
$secretPairs = @()
foreach ($e in $container.env) {
    if ($e.valueFrom -and $e.valueFrom.secretKeyRef) {
        $ref = $e.valueFrom.secretKeyRef
        $key = if ($ref.key) { $ref.key } else { "latest" }
        $secretPairs += "$($e.name)=$($ref.name):$key"
    } else {
        $envPairs += "$($e.name)=$($e.value)"
    }
}

$envVars = $envPairs -join ","
$secretVars = $secretPairs -join ","

Write-Host ""
Write-Host "Resolved from the live service:"
Write-Host "  Image:           $image"
Write-Host "  Service account: $(if ($serviceAccount) { $serviceAccount } else { '<default>' })"
Write-Host "  Cloud SQL:       $(if ($cloudsql) { $cloudsql } else { '<none>' })"
Write-Host "  VPC connector:   $(if ($vpcConnector) { $vpcConnector } else { '<none>' })"
Write-Host "  Env vars found:  $($envPairs.Count)"
Write-Host "  Secrets found:   $($secretPairs.Count)"
Write-Host ""

$confirm = Read-Host "Create and run the one-off bootstrap job with this config? [y/N]"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Aborted -- nothing was created or run."
    exit 1
}

$jobArgs = @(
    $Job,
    "--image=$image",
    "--region=$Region",
    "--command=python",
    "--args=manage.py,bootstrap_admin_and_roles",
    "--task-timeout=300",
    "--max-retries=0"
)
if ($serviceAccount) { $jobArgs += "--service-account=$serviceAccount" }
if ($cloudsql)       { $jobArgs += "--set-cloudsql-instances=$cloudsql" }
if ($vpcConnector)   { $jobArgs += "--vpc-connector=$vpcConnector" }
if ($envVars)        { $jobArgs += "--set-env-vars=$envVars" }
if ($secretVars)      { $jobArgs += "--set-secrets=$secretVars" }

Write-Host "==> Creating/updating job '$Job'..."
gcloud run jobs describe $Job --region $Region *> $null
if ($LASTEXITCODE -eq 0) {
    gcloud run jobs update @jobArgs
} else {
    gcloud run jobs create @jobArgs
}

Write-Host "==> Executing job (usually 30-60s)..."
$execution = gcloud run jobs execute $Job --region $Region --wait --format='value(metadata.name)'

Write-Host ""
Write-Host "==> Job output (generated credentials print near the bottom):"
Write-Host ""
Start-Sleep -Seconds 5
$filter = "resource.type=cloud_run_job AND resource.labels.job_name=`"$Job`" AND labels.`"run.googleapis.com/execution_name`"=`"$execution`""
gcloud logging read $filter --project $Project --format='value(textPayload)' --order=asc --freshness=10m

Write-Host ""
Write-Host "Done. Save the printed passwords now -- they will not be shown again."
Write-Host "Optional cleanup once you've saved them:"
Write-Host "  gcloud run jobs delete $Job --region=$Region"
