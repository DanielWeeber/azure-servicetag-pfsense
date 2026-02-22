# Azure Service Tags → pfSense Aliases

Fetch Microsoft Azure Service Tags and keep pfSense aliases in sync via pfRest. The
script supports CLI flags and environment variables, and can run locally or in Docker.

## What this does

- Downloads the latest Service Tags JSON from Microsoft.
- Filters tags by service and region (global tags are included if the service matches).
- Builds aliases named `azure_service_tag_<AzureTagName>` (configurable prefix).
- Writes the results to `aliases.json`.
- Optionally updates pfSense aliases via pfRest (update-only by default).

## Quick start (local)

```bash
python3 -m pip install -r requirements.txt
python3 scripts/azure_service_tags_sync.py --dry-run
```

## Common CLI examples

Dry run with filters:

```bash
python3 scripts/azure_service_tags_sync.py \
  --service AzureStorage \
  --service ServiceBus \
  --region "West Europe" \
  --region "North Europe" \
  --dry-run
```

Sync to pfSense and apply changes:

```bash
PFREST_BASE_URL="https://pfsense.example.com:441" \
PFREST_API_TOKEN="<token>" \
PFREST_TLS_INSECURE=true \
PFREST_ALLOW_CREATE=true \
PFREST_APPLY_CHANGES=true \
python3 scripts/azure_service_tags_sync.py --apply
```

## Docker (public Python image)

Dry run with a bind mount:

```bash
docker run --rm \
  -v "$PWD":/app \
  -w /app \
  python:3.12-slim \
  sh -c "python -m pip install -r requirements.txt && python scripts/azure_service_tags_sync.py --dry-run"
```

Sync to pfSense (example):

```bash
docker run --rm \
  -v "$PWD":/app \
  -w /app \
  -e PFREST_BASE_URL="https://pfsense.example.com:441" \
  -e PFREST_API_TOKEN="<token>" \
  -e PFREST_TLS_INSECURE=true \
  -e PFREST_ALLOW_CREATE=true \
  -e PFREST_APPLY_CHANGES=true \
  -e AZURE_SERVICES="Dynamics365BusinessCentral,AzureActiveDirectory,AzureStorage,ServiceBus" \
  -e AZURE_REGIONS="West Europe,North Europe" \
  python:3.12-slim \
  sh -c "python -m pip install -r requirements.txt && python scripts/azure_service_tags_sync.py --apply"
```

## Docker Compose example

```yaml
version: "3.9"

services:
  azure-service-tags-sync:
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - .:/app
    environment:
      PFREST_BASE_URL: "https://pfsense.example.com:441"
      PFREST_API_TOKEN: "replace-me"
      PFREST_TLS_INSECURE: "true"
      PFREST_ALLOW_CREATE: "true"
      PFREST_APPLY_CHANGES: "true"
      AZURE_SERVICES: "AzureStorage,ServiceBus"
      AZURE_REGIONS: "West Europe,North Europe"
      AZURE_ALIAS_PREFIX: "azure_st_"
    command: ["sh", "-c", "python -m pip install -r requirements.txt && python scripts/azure_service_tags_sync.py --apply"]
```

## Sync behavior

- Aliases are updated in-place; deletions are not performed.
- By default, only existing aliases are updated.
- Set `--allow-create` or `PFREST_ALLOW_CREATE=true` to create missing aliases.

## Environment variables

- `AZURE_SERVICES`: comma-separated list of Azure services (e.g., `AzureStorage,ServiceBus`).
- `AZURE_REGIONS`: comma-separated list of regions (e.g., `West Europe,North Europe`).
- `AZURE_INCLUDE_IPV6`: set to `true` to include IPv6 prefixes (default: IPv4 only).
- `AZURE_ALIAS_PREFIX`: alias name prefix (default: `azure_st_`).
- `PFSENSE_ALIAS_MAX_LENGTH`: maximum alias name length (default: `31`).
- `PFREST_BASE_URL`: pfRest base URL (e.g., `https://pfsense:441`).
- `PFREST_API_TOKEN`: pfRest API token (sent as `x-api-key`).
- `PFREST_TLS_INSECURE`: set to `true` to skip TLS verification.
- `PFREST_UPDATE_ONLY`: set to `false` to allow creating missing aliases.
- `PFREST_ALLOW_CREATE`: set to `true` to allow creating missing aliases.
- `PFREST_APPLY_CHANGES`: set to `true` to apply firewall changes after updates.
