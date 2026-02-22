# Copilot Instructions

## Project summary
This repository provides a Python script that syncs Microsoft Azure Service Tags
into pfSense firewall aliases using the pfRest API. The script downloads the
latest Service Tags JSON, filters by service/region, writes `aliases.json`, and
optionally updates pfSense aliases (update-only by default).

Key paths:
- `scripts/azure_service_tags_sync.py`: main CLI and pfRest sync logic.
- `tests/`: unit and integration-style tests with mocked HTTP.
- `docker-compose.yml`: public Python image example (bind mount, no custom image).
- `requirements.txt`: Python deps (`certifi`).

## How it works (high level)
- Resolve Service Tags JSON URL via Microsoft confirmation page.
- Download JSON (prefers `certifi` CA bundle).
- Extract tags based on filters:
	- Services: match against both `systemService` and tag name prefix.
	- Regions: match specified regions; empty region is treated as global and
		included when service matches.
- Build alias names: `AZURE_ALIAS_PREFIX` + raw Azure tag name.
- Sync to pfSense via pfRest:
	- GET `/api/v2/firewall/aliases`
	- PATCH existing aliases
	- POST new aliases only when `PFREST_ALLOW_CREATE=true`
	- No deletions.

## Developer workflow
Run tests:
- `python -m unittest discover -s tests`

Local dry run:
- `python scripts/azure_service_tags_sync.py --dry-run`

## Environment variables (core)
- `AZURE_SERVICES`: comma-separated list (filters by service name).
- `AZURE_REGIONS`: comma-separated list (filters by region; global tags always allowed).
- `AZURE_INCLUDE_IPV6`: include IPv6 prefixes when `true`.
- `AZURE_ALIAS_PREFIX`: default `azure_st_`.
- `PFSENSE_ALIAS_MAX_LENGTH`: default 31.
- `PFREST_BASE_URL`: pfRest base URL.
- `PFREST_API_TOKEN`: API token for `x-api-key` header.
- `PFREST_TLS_INSECURE`: skip TLS verification for pfRest.
- `PFREST_UPDATE_ONLY`: keep update-only behavior.
- `PFREST_ALLOW_CREATE`: allow creating missing aliases.
- `PFREST_APPLY_CHANGES`: apply firewall changes after updates.

## Conventions and gotchas
- Avoid storing real IPs/tokens in repo files. Use placeholders.
- `aliases.json` is generated and should stay ignored.
- `__pycache__/` and `.venv/` should remain ignored.
- Favor small, targeted changes; keep CLI flags and env vars aligned with README.

## Current open items
- Optional: add download TLS fallback flag (`--download-tls-insecure`).
