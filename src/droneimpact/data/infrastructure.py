from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from droneimpact.config import InfraConfig

CATEGORIES = ("power_plant", "hospital", "water_works", "bridge", "school")


class InfrastructureIndex:
    def __init__(
        self,
        trees: dict[str, STRtree],
        coords: dict[str, np.ndarray],
        config: InfraConfig,
    ):
        self._trees = trees
        self._coords = coords
        self._config = config

    @classmethod
    def load_from_file(cls, path: str | Path, config: InfraConfig) -> "InfrastructureIndex":
        with open(path) as f:
            geojson = json.load(f)
        return cls.from_features(geojson.get("features", []), config)

    @classmethod
    def from_features(
        cls, features: list[dict], config: InfraConfig
    ) -> "InfrastructureIndex":
        by_cat: dict[str, list[Point]] = {cat: [] for cat in CATEGORIES}
        for feat in features:
            cat = (feat.get("properties") or {}).get("category")
            if cat in by_cat:
                geom = shape(feat["geometry"])
                by_cat[cat].append(geom.centroid)

        trees: dict[str, STRtree] = {}
        coords: dict[str, np.ndarray] = {}
        for cat, pts in by_cat.items():
            if pts:
                trees[cat] = STRtree(pts)
                coords[cat] = np.array([[p.x, p.y] for p in pts])  # [lon, lat]
        return cls(trees, coords, config)

    def _nearest_dist_m(self, lon: float, lat: float, category: str) -> float:
        if category not in self._trees:
            return math.inf
        pt = Point(lon, lat)
        # shapely 2.x: nearest() returns an integer index into the input geometries
        idx = self._trees[category].nearest(pt)
        if idx is None:
            return math.inf
        nearest_lonlat = self._coords[category][idx]  # [lon, lat]
        dlat = (nearest_lonlat[1] - lat) * 111_000.0
        dlon = (nearest_lonlat[0] - lon) * 111_000.0 * math.cos(math.radians(lat))
        return math.sqrt(dlat ** 2 + dlon ** 2)

    def penalty(self, lat: float, lon: float) -> float:
        radius = self._config.penalty_radius_m
        total = 0.0
        for cat in CATEGORIES:
            weight = getattr(self._config.weights, cat, 0.0)
            dist = self._nearest_dist_m(lon, lat, cat)
            total += weight * max(0.0, 1.0 - dist / radius)
        return min(total, self._config.max_penalty)

    def penalty_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        return np.array(
            [self.penalty(float(lat), float(lon)) for lat, lon in zip(lats, lons)],
            dtype=np.float32,
        )
