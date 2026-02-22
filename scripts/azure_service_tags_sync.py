#!/usr/bin/env python3
"""Fetch Azure Service Tags and sync pfSense alias definitions.

This script fetches the Azure Service Tags JSON, filters it, writes alias
definitions to a JSON file, and optionally syncs aliases into pfSense via pfRest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_CONFIRMATION_URL = (
    "https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519"
)
USER_AGENT = "azure-service-tags-sync/0.2"
DEFAULT_ALIAS_PREFIX = "azure_service_tag_"
DEFAULT_MAX_ALIAS_LENGTH = 31


@dataclass(frozen=True)
class AliasDefinition:
    name: str
    alias_type: str
    addresses: list[str]
    description: str
    source_tag: str
    service: str
    region: str


class ServiceTagError(RuntimeError):
    pass


def download_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=build_download_ssl_context()
        ) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ServiceTagError(f"Failed to download {url}: {exc}") from exc


def resolve_service_tags_url(source_url: str) -> str:
    if source_url.lower().endswith(".json"):
        return source_url

    html = download_text(source_url)
    match = re.search(r"https://download\.microsoft\.com/[^\"']+ServiceTags_[^\"']+\.json", html)
    if not match:
        raise ServiceTagError(
            "Could not locate ServiceTags JSON link on confirmation page. "
            "Provide a direct JSON URL with --source-url."
        )
    return match.group(0)


def load_service_tags(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ServiceTagError("Service Tags JSON is invalid.") from exc


def normalize_alias_name(name: str, max_len: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if len(cleaned) <= max_len:
        return cleaned
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:6]
    trim_len = max_len - len(digest) - 1
    return f"{cleaned[:trim_len]}_{digest}"


def normalize_filter_value(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]", "", value.lower())
    return cleaned


def parse_env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def extract_aliases(
    data: dict[str, Any],
    service_filters: Iterable[str],
    region_filters: Iterable[str],
    include_ipv6: bool,
    name_prefix: str,
    max_name_length: int,
) -> list[AliasDefinition]:
    values = data.get("values", [])
    aliases: list[AliasDefinition] = []
    used_names: set[str] = set()

    services = {normalize_filter_value(svc) for svc in service_filters}
    regions = {normalize_filter_value(reg) for reg in region_filters}

    for entry in values:
        name = entry.get("name", "")
        properties = entry.get("properties", {})
        name_service = name.split(".")[0].strip() if name else ""
        service = (properties.get("systemService") or name_service).strip()
        region = (properties.get("region") or _region_from_name(name)).strip()

        service_candidates = {
            normalize_filter_value(service),
            normalize_filter_value(name_service),
        }
        if services and not service_candidates.intersection(services):
            continue
        region_value = normalize_filter_value(region) if region else "global"
        if regions and region and region_value not in regions:
            continue

        prefixes = list(properties.get("addressPrefixes", []))
        if not include_ipv6:
            prefixes = [p for p in prefixes if ":" not in p]
        if not prefixes:
            continue

        alias_name = f"{name_prefix}{name}"
        alias_name = normalize_alias_name(alias_name, max_name_length)
        if alias_name in used_names:
            alias_name = normalize_alias_name(
                f"{alias_name}_{hashlib.sha1(name.encode()).hexdigest()[:4]}",
                max_name_length,
            )
        used_names.add(alias_name)

        aliases.append(
            AliasDefinition(
                name=alias_name,
                alias_type="network",
                addresses=sorted(prefixes),
                description=f"Azure Service Tag {name}",
                source_tag=name,
                service=service,
                region=region,
            )
        )

    return aliases


def _region_from_name(name: str) -> str:
    if "." not in name:
        return ""
    return name.split(".", 1)[1]


def build_output_payload(aliases: list[AliasDefinition], source_url: str) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": source_url,
        "aliases": [
            {
                "name": alias.name,
                "type": alias.alias_type,
                "addresses": alias.addresses,
                "description": alias.description,
                "service_tag": alias.source_tag,
                "service": alias.service,
                "region": alias.region,
            }
            for alias in aliases
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def build_ssl_context(tls_insecure: bool) -> ssl.SSLContext:
    if not tls_insecure:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def build_download_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ModuleNotFoundError:
        return ssl.create_default_context()


def pfrest_request(
    method: str,
    base_url: str,
    endpoint: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
    tls_insecure: bool = False,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    data = None
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "x-api-key": api_key,
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=build_ssl_context(tls_insecure)
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ServiceTagError(f"pfRest request failed ({method} {endpoint}): {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ServiceTagError("pfRest returned invalid JSON.") from exc


def normalize_pfrest_addresses(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item for item in re.split(r"[\s,]+", value) if item]
    return [str(value)]


def sync_pfsense_aliases(
    aliases: list[AliasDefinition],
    base_url: str,
    api_key: str,
    tls_insecure: bool,
    update_only: bool,
    apply_changes: bool,
) -> dict[str, int]:
    response = pfrest_request(
        "GET",
        base_url,
        "/api/v2/firewall/aliases?limit=0",
        api_key,
        tls_insecure=tls_insecure,
    )
    existing_aliases = response.get("data", [])
    existing_by_name = {alias.get("name"): alias for alias in existing_aliases}

    results = {"updated": 0, "created": 0, "skipped": 0, "unchanged": 0}

    for alias in aliases:
        desired_addresses = sorted(alias.addresses)
        payload = {
            "name": alias.name,
            "type": alias.alias_type,
            "descr": alias.description,
            "address": desired_addresses,
        }
        existing = existing_by_name.get(alias.name)
        if existing:
            current_addresses = sorted(
                normalize_pfrest_addresses(existing.get("address"))
            )
            current_descr = existing.get("descr") or ""
            current_type = existing.get("type") or ""
            if (
                current_addresses == desired_addresses
                and current_descr == alias.description
                and current_type == alias.alias_type
            ):
                results["unchanged"] += 1
                continue
            payload["id"] = existing.get("id")
            pfrest_request(
                "PATCH",
                base_url,
                "/api/v2/firewall/alias",
                api_key,
                payload=payload,
                tls_insecure=tls_insecure,
            )
            results["updated"] += 1
            continue
        if update_only:
            results["skipped"] += 1
            continue
        pfrest_request(
            "POST",
            base_url,
            "/api/v2/firewall/alias",
            api_key,
            payload=payload,
            tls_insecure=tls_insecure,
        )
        results["created"] += 1

    if apply_changes:
        pfrest_request(
            "POST",
            base_url,
            "/api/v2/firewall/apply",
            api_key,
            payload={"dry_run": False},
            tls_insecure=tls_insecure,
        )

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Azure Service Tags and generate pfSense alias definitions."
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_CONFIRMATION_URL,
        help="Azure Service Tags confirmation page or direct JSON URL.",
    )
    parser.add_argument(
        "--output",
        default="aliases.json",
        help="Path to write alias definitions JSON.",
    )
    parser.add_argument(
        "--service",
        action="append",
        default=None,
        help="Filter by Azure systemService (repeatable).",
    )
    parser.add_argument(
        "--region",
        action="append",
        default=None,
        help="Filter by region (repeatable).",
    )
    parser.add_argument(
        "--include-ipv6",
        action="store_true",
        default=parse_env_bool("AZURE_INCLUDE_IPV6", False),
        help="Include IPv6 prefixes (default: IPv4 only).",
    )
    parser.add_argument(
        "--name-prefix",
        default=os.getenv("AZURE_ALIAS_PREFIX", DEFAULT_ALIAS_PREFIX),
        help="Prefix for pfSense alias names.",
    )
    parser.add_argument(
        "--max-name-length",
        type=int,
        default=parse_env_int("PFSENSE_ALIAS_MAX_LENGTH", DEFAULT_MAX_ALIAS_LENGTH),
        help="Maximum alias name length.",
    )
    parser.add_argument(
        "--pfrest-base-url",
        default=os.getenv("PFREST_BASE_URL", ""),
        help="pfRest base URL (e.g., https://pfsense:441).",
    )
    parser.add_argument(
        "--pfrest-api-token",
        default=os.getenv("PFREST_API_TOKEN", ""),
        help="pfRest API token for x-api-key authentication.",
    )
    parser.add_argument(
        "--pfrest-tls-insecure",
        action="store_true",
        default=parse_env_bool("PFREST_TLS_INSECURE", False),
        help="Disable TLS verification for pfRest.",
    )
    parser.add_argument(
        "--update-only",
        action="store_true",
        default=parse_env_bool("PFREST_UPDATE_ONLY", True),
        help="Only update existing aliases (default: true).",
    )
    parser.add_argument(
        "--allow-create",
        action="store_true",
        default=parse_env_bool("PFREST_ALLOW_CREATE", False),
        help="Allow creating missing aliases in pfSense.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=parse_env_bool("PFREST_APPLY_CHANGES", False),
        help="Apply firewall changes after updates.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write output; just report counts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service_filters = (
        args.service if args.service is not None else parse_env_list("AZURE_SERVICES")
    )
    region_filters = (
        args.region if args.region is not None else parse_env_list("AZURE_REGIONS")
    )
    try:
        resolved_url = resolve_service_tags_url(args.source_url)
        raw_json = download_text(resolved_url)
        data = load_service_tags(raw_json)
        aliases = extract_aliases(
            data,
            service_filters=service_filters,
            region_filters=region_filters,
            include_ipv6=args.include_ipv6,
            name_prefix=args.name_prefix,
            max_name_length=args.max_name_length,
        )
    except ServiceTagError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Resolved URL: {resolved_url}\n"
        f"Service tags: {len(data.get('values', []))}\n"
        f"Aliases generated: {len(aliases)}"
    )

    if args.dry_run:
        return 0

    payload = build_output_payload(aliases, resolved_url)
    output_path = Path(args.output)
    write_json(output_path, payload)
    print(f"Wrote alias definitions to {output_path.resolve()}")

    if args.pfrest_base_url and args.pfrest_api_token:
        update_only = args.update_only and not args.allow_create
        results = sync_pfsense_aliases(
            aliases=aliases,
            base_url=args.pfrest_base_url,
            api_key=args.pfrest_api_token,
            tls_insecure=args.pfrest_tls_insecure,
            update_only=update_only,
            apply_changes=args.apply,
        )
        print(
            "pfSense sync results: "
            f"{results['updated']} updated, "
            f"{results['created']} created, "
            f"{results['skipped']} skipped, "
            f"{results['unchanged']} unchanged"
        )
    elif args.pfrest_base_url or args.pfrest_api_token:
        print(
            "Skipping pfSense sync (both --pfrest-base-url and --pfrest-api-token are required)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
