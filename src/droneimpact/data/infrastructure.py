from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point, shape

from droneimpact.config import InfraConfig

CATEGORIES = ("power_plant", "hospital", "water_works", "bridge", "school")

_DEG_TO_M = 111_000.0


class InfrastructureIndex:
    def __init__(
        self,
        kdtrees: dict[str, cKDTree],
        coords_deg: dict[str, np.ndarray],
        ref_cos_lat: float,
        config: InfraConfig,
    ):
        self._kdtrees = kdtrees
        self._coords_deg = coords_deg
        self._ref_cos_lat = ref_cos_lat
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
        by_cat: dict[str, list[tuple[float, float]]] = {cat: [] for cat in CATEGORIES}
        all_lats: list[float] = []
        for feat in features:
            cat = (feat.get("properties") or {}).get("category")
            if cat in by_cat:
                geom = shape(feat["geometry"])
                c = geom.centroid
                by_cat[cat].append((c.x, c.y))  # lon, lat
                all_lats.append(c.y)

        ref_cos_lat = math.cos(math.radians(np.mean(all_lats))) if all_lats else 1.0

        kdtrees: dict[str, cKDTree] = {}
        coords_deg: dict[str, np.ndarray] = {}
        for cat, pts in by_cat.items():
            if pts:
                arr = np.array(pts)  # (N, 2) [lon, lat]
                coords_deg[cat] = arr
                xy = np.column_stack([
                    arr[:, 0] * _DEG_TO_M * ref_cos_lat,
                    arr[:, 1] * _DEG_TO_M,
                ])
                kdtrees[cat] = cKDTree(xy)
        return cls(kdtrees, coords_deg, ref_cos_lat, config)

    def penalty(self, lat: float, lon: float) -> float:
        radius = self._config.penalty_radius_m
        x = lon * _DEG_TO_M * self._ref_cos_lat
        y = lat * _DEG_TO_M
        worst = 0.0
        for cat in CATEGORIES:
            if cat not in self._kdtrees:
                continue
            weight = getattr(self._config.weights, cat, 0.0)
            dist, _ = self._kdtrees[cat].query([x, y])
            worst = max(worst, weight * max(0.0, 1.0 - dist / radius))
        return min(worst, self._config.max_penalty)

    def penalty_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        radius = self._config.penalty_radius_m
        pts = np.column_stack([
            lons * _DEG_TO_M * self._ref_cos_lat,
            lats * _DEG_TO_M,
        ])
        worst = np.zeros(len(lats), dtype=np.float64)
        for cat in CATEGORIES:
            if cat not in self._kdtrees:
                continue
            weight = getattr(self._config.weights, cat, 0.0)
            dists, _ = self._kdtrees[cat].query(pts)
            penalties = weight * np.maximum(0.0, 1.0 - dists / radius)
            np.maximum(worst, penalties, out=worst)
        return np.minimum(worst, self._config.max_penalty).astype(np.float32)
