# Azure Service Tags → pfSense Aliases

This repo contains a script that fetches Microsoft Azure Service Tags and syncs
pfSense-friendly alias definitions using pfRest.

## What it does

- Downloads the latest Service Tags JSON from Microsoft.
- Filters by service/region.
- Builds aliases named `azure_service_tag_<AzureTagName>`.
- Writes alias definitions to `aliases.json`.
- Optionally updates pfSense aliases via pfRest (update-only by default).

## Quick start

```bash
python3 -m pip install -r requirements.txt
python3 scripts/azure_service_tags_sync.py --dry-run
```

## Common options

- `--service AzureCloud` (repeatable)
- `--region westeurope` (repeatable)
- `--include-ipv6`
- `--output aliases.json`
- `--pfrest-base-url https://pfsense:441`
- `--pfrest-api-token <token>`
- `--pfrest-tls-insecure`
- `--allow-create`
- `--apply`

## Sync behavior

- Aliases are updated in-place; deletions are not performed.
- By default, only existing aliases are updated.
- Set `--allow-create` or `PFREST_ALLOW_CREATE=true` to create missing aliases.

## Environment variables

- `AZURE_SERVICES`: comma-separated list of Azure services (e.g., `AzureStorage,ServiceBus`).
- `AZURE_REGIONS`: comma-separated list of regions (e.g., `West Europe,North Europe`).
- `AZURE_INCLUDE_IPV6`: set to `true` to include IPv6 prefixes (default: IPv4 only).
- `AZURE_ALIAS_PREFIX`: alias name prefix (default: `azure_service_tag_`).
- `PFSENSE_ALIAS_MAX_LENGTH`: maximum alias name length (default: `31`).
- `PFREST_BASE_URL`: pfRest base URL (e.g., `https://pfsense:441`).
- `PFREST_API_TOKEN`: pfRest API token (sent as `x-api-key`).
- `PFREST_TLS_INSECURE`: set to `true` to skip TLS verification.
- `PFREST_UPDATE_ONLY`: set to `false` to allow creating missing aliases.
- `PFREST_ALLOW_CREATE`: set to `true` to allow creating missing aliases.
- `PFREST_APPLY_CHANGES`: set to `true` to apply firewall changes after updates.
