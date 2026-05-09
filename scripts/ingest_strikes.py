#!/usr/bin/env python3
"""Ingest Bellingcat civilian harm data and write a GeoJSON FeatureCollection.

Usage:
    python scripts/ingest_strikes.py [--output PATH]

Default output: data/ukraine_strikes.geojson
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

BELLINGCAT_URL = (
    "https://bellingcat-embeds.ams3.cdn.digitaloceanspaces.com"
    "/production/ukr/timemap/api.json"
)

_IMPACT_MAP = {
    "Residential": "residential",
    "Industrial": "industrial",
    "Energy": "energy",
    "Military": "military",
}


def _fetch_bellingcat() -> list[dict]:
    req = urllib.request.Request(BELLINGCAT_URL, headers={"User-Agent": "droneimpact/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _normalize(record: dict) -> dict | None:
    try:
        lat = float(record["latitude"])
        lon = float(record["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    impact = record.get("impact") or ""
    category = _IMPACT_MAP.get(impact, "unknown")
    return {
        "id": str(record.get("id", "")),
        "lat": lat,
        "lon": lon,
        "date": str(record.get("date", "")),
        "source": "bellingcat",
        "location_name": str(record.get("location", "")),
        "category": category,
        "description": str(record.get("description", "")),
        "confidence": 0.9,
    }


def _dedup(records: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in records:
        key = (round(r["lat"], 3), round(r["lon"], 3), r["date"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _to_feature(r: dict) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
        "properties": {
            "id": r["id"],
            "date": r["date"],
            "source": r["source"],
            "location_name": r["location_name"],
            "category": r["category"],
            "description": r["description"],
            "confidence": r["confidence"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Bellingcat strike data")
    parser.add_argument(
        "--output",
        default="data/ukraine_strikes.geojson",
        help="Output GeoJSON path (default: data/ukraine_strikes.geojson)",
    )
    args = parser.parse_args()

    print("Downloading Bellingcat data...", flush=True)
    try:
        raw = _fetch_bellingcat()
    except Exception as exc:
        print(f"ERROR: failed to download data: {exc}", file=sys.stderr)
        sys.exit(1)

    total_downloaded = len(raw)
    print(f"Downloaded: {total_downloaded} records")

    normalized = [n for r in raw if (n := _normalize(r)) is not None]
    deduped = _dedup(normalized)
    after_dedup = len(deduped)
    print(f"After deduplication: {after_dedup} records")

    collection = {
        "type": "FeatureCollection",
        "features": [_to_feature(r) for r in deduped],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False)

    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
