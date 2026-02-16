#!/usr/bin/env python3
"""
Utility script to inspect the distribution metadata for a single film within a cohort.

Usage:

    python scripts/inspect_distribution.py --cohort 8 --slug pulse-2001 [--query "&decade=2000"]

Reads API host/key from the same env vars as the frontend:
  - NEXT_PUBLIC_API_BASE_URL (defaults to http://127.0.0.1:8000)
  - NEXT_PUBLIC_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

from pathlib import Path


def load_env_from_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return values


def build_url(base: str, cohort_id: str, extra_query: str | None) -> str:
    parsed = urllib.parse.urlparse(base)
    path = parsed.path.rstrip("/") + f"/cohorts/{cohort_id}/rankings"
    # Default query params match the web app (bayesian strategy, 500 row window).
    query = urllib.parse.parse_qs(parsed.query)
    query["strategy"] = ["bayesian"]
    query["limit"] = ["500"]
    query["result_limit"] = ["500"]
    if extra_query:
        extra = urllib.parse.parse_qs(extra_query.lstrip("&?"))
        for key, values in extra.items():
            query[key] = values
    encoded_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(path=path, query=encoded_query))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, help="Cohort ID to query")
    parser.add_argument("--slug", required=True, help="Film slug to inspect")
    parser.add_argument(
        "--query",
        default="",
        help="Optional extra query string (e.g., '&decade=2000&watchers_min=5')",
    )
    args = parser.parse_args(argv)

    env_values = {}
    dotenv_path = Path("apps/web/.env.local")
    if dotenv_path.exists():
        env_values.update(load_env_from_file(dotenv_path))
    env_values.update(os.environ)

    api_base = env_values.get("NEXT_PUBLIC_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    api_key = env_values.get("NEXT_PUBLIC_API_KEY")
    if not api_key:
        sys.stderr.write("Error: NEXT_PUBLIC_API_KEY is not set.\n")
        return 1

    url = build_url(api_base, args.cohort, args.query)
    req = urllib.request.Request(url, headers={"X-Api-Key": api_key})
    try:
        with urllib.request.urlopen(req) as response:
            payload = json.load(response)
    except Exception as exc:
        sys.stderr.write(f"Request failed: {exc}\n")
        return 1

    items = payload.get("items") or []
    film = next((entry for entry in items if entry.get("slug") == args.slug), None)
    if not film:
        sys.stderr.write(f"No film with slug '{args.slug}' in this response.\n")
        return 1
    json.dump(film, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
