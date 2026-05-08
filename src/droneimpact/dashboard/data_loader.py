from __future__ import annotations

import json
import os


def _find_data_path(relative: str) -> str | None:
    candidates = [
        relative,
        os.path.join("data", os.path.basename(relative)),
        os.path.join("data", "fixtures", os.path.basename(relative)),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def load_kontur_population(path: str = "data/fixtures/kontur_population_ukraine.geojson") -> dict | None:
    resolved = _find_data_path(path)
    if resolved is None:
        return None
    with open(resolved) as f:
        return json.load(f)


def load_osm_infrastructure(path: str = "data/fixtures/osm_poi_ukraine.geojson") -> dict | None:
    resolved = _find_data_path(path)
    if resolved is None:
        return None
    with open(resolved) as f:
        return json.load(f)
