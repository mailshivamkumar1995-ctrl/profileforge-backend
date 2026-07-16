#!/usr/bin/env pwsh

<#
.SYNOPSIS
Validates the OpenAPI schema for breaking changes.

.DESCRIPTION
Downloads the production (baseline) schema and compares it to the currently generated schema
using openapi-diff. Fails if breaking changes are detected.
#>

$ErrorActionPreference = "Stop"

$BaselineUrl = "https://api.profileforge.com/api/schema/?format=json"
$BaselinePath = "schema_baseline.json"
$CurrentPath = "schema.json"

Write-Host "Generating current schema..."
# Assuming Python environment is active
python manage.py spectacular --file $CurrentPath --format json

Write-Host "Fetching baseline schema from $BaselineUrl..."
try {
    Invoke-WebRequest -Uri $BaselineUrl -OutFile $BaselinePath -UseBasicParsing
} catch {
    Write-Warning "Could not fetch baseline schema. Skipping openapi-diff."
    exit 0
}

Write-Host "Running openapi-diff..."
# Run openapi-diff via docker container
docker run --rm -v ${PWD}:/data tufin/oasdiff breaking /data/$BaselinePath /data/$CurrentPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "Breaking changes detected! Please bump the major API version or maintain backward compatibility."
}

Write-Host "Contract verification passed. No breaking changes detected."
Write-Host "Cleaning up..."
Remove-Item $BaselinePath
Remove-Item $CurrentPath
