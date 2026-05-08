"""Extract infrastructure features from an OSM PBF file into GeoJSON.

Requires pyosmium: pip install osmium
"""
from __future__ import annotations

import json
import sys

import osmium

INFRA_TAGS = {
    "power": {"plant", "substation"},
    "amenity": {"hospital", "clinic", "school", "university"},
    "man_made": {"water_works", "pumping_station", "storage_tank"},
    "waterway": {"dam"},
    "railway": {"station", "yard"},
}

CATEGORY_MAP = {
    ("power", "plant"): "power_plant",
    ("power", "substation"): "power_plant",
    ("amenity", "hospital"): "hospital",
    ("amenity", "clinic"): "hospital",
    ("amenity", "school"): "school",
    ("amenity", "university"): "school",
    ("man_made", "water_works"): "water_works",
    ("man_made", "pumping_station"): "water_works",
    ("man_made", "storage_tank"): "fuel_storage",
    ("waterway", "dam"): "dam",
    ("railway", "station"): "railway",
    ("railway", "yard"): "railway",
}


def _classify(tags) -> str | None:
    for key, values in INFRA_TAGS.items():
        val = tags.get(key)
        if val and val in values:
            if key == "man_made" and val == "storage_tank":
                substance = tags.get("substance", tags.get("content", ""))
                if substance not in ("fuel", "oil", "gas", "diesel", "gasoline"):
                    return None
            return CATEGORY_MAP.get((key, val))
    if tags.get("bridge") == "yes" and (tags.get("highway") or tags.get("railway")):
        return "bridge"
    return None


class InfraHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.features: list[dict] = []

    def node(self, n):
        cat = _classify(n.tags)
        if cat and n.location.valid():
            self._add_feature(n.location.lon, n.location.lat, n.tags, cat, n.id, "node")

    def way(self, w):
        cat = _classify(w.tags)
        if cat and w.nodes:
            try:
                lons = [n.lon for n in w.nodes if n.location.valid()]
                lats = [n.lat for n in w.nodes if n.location.valid()]
                if lons and lats:
                    centroid_lon = sum(lons) / len(lons)
                    centroid_lat = sum(lats) / len(lats)
                    self._add_feature(centroid_lon, centroid_lat, w.tags, cat, w.id, "way")
            except osmium.InvalidLocationError:
                pass

    def _add_feature(self, lon, lat, tags, category, osm_id, osm_type):
        self.features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 6), round(lat, 6)],
            },
            "properties": {
                "osm_id": osm_id,
                "osm_type": osm_type,
                "category": category,
                "name": tags.get("name", ""),
            },
        })


def main(pbf_path: str, output_path: str) -> None:
    handler = InfraHandler()
    handler.apply_file(pbf_path, locations=True)

    geojson = {
        "type": "FeatureCollection",
        "features": handler.features,
    }

    with open(output_path, "w") as f:
        json.dump(geojson, f)

    print(f"  Extracted {len(handler.features)} infrastructure features")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.osm.pbf> <output.geojson>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
