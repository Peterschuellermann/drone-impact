from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

_DEG_TO_M = 111_000.0

VALID_CATEGORIES = ("residential", "industrial", "energy", "military", "unknown")


@dataclass
class StrikeLocation:
    id: str
    lat: float
    lon: float
    date: str
    source: str
    location_name: str
    category: str
    description: str
    confidence: float


@dataclass
class StrikeHotspot:
    lat: float
    lon: float
    strike_count: int
    category: str
    location_name: str
    radius_m: float


class StrikeIndex:
    def __init__(
        self,
        strikes: list[StrikeLocation],
        kdtree: cKDTree | None,
        xy: np.ndarray | None,
        ref_cos_lat: float,
    ):
        self._strikes = strikes
        self._kdtree = kdtree
        self._xy = xy
        self._ref_cos_lat = ref_cos_lat

    @classmethod
    def load_from_file(cls, path: str | Path) -> "StrikeIndex":
        p = Path(path)
        if not p.exists():
            logger.warning("Strike locations file not found: %s — strike index will be empty", path)
            return cls([], None, None, 1.0)
        with open(p) as f:
            geojson = json.load(f)
        return cls.from_features(geojson.get("features", []))

    @classmethod
    def from_features(cls, features: list[dict]) -> "StrikeIndex":
        strikes: list[StrikeLocation] = []
        for feat in features:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates", [None, None])
            lon, lat = coords[0], coords[1]
            if lat is None or lon is None:
                continue
            category = props.get("category", "unknown")
            if category not in VALID_CATEGORIES:
                category = "unknown"
            strikes.append(StrikeLocation(
                id=str(props.get("id", "")),
                lat=float(lat),
                lon=float(lon),
                date=str(props.get("date", "")),
                source=str(props.get("source", "")),
                location_name=str(props.get("location_name", "")),
                category=category,
                description=str(props.get("description", "")),
                confidence=float(props.get("confidence", 0.0)),
            ))

        if not strikes:
            return cls([], None, None, 1.0)

        lats = np.array([s.lat for s in strikes])
        lons = np.array([s.lon for s in strikes])
        ref_cos_lat = math.cos(math.radians(float(np.mean(lats))))
        xy = np.column_stack([
            lons * _DEG_TO_M * ref_cos_lat,
            lats * _DEG_TO_M,
        ])
        kdtree = cKDTree(xy)
        return cls(strikes, kdtree, xy, ref_cos_lat)

    @property
    def count(self) -> int:
        return len(self._strikes)

    def query_bbox(
        self, south: float, west: float, north: float, east: float
    ) -> list[StrikeLocation]:
        return [
            s for s in self._strikes
            if south <= s.lat <= north and west <= s.lon <= east
        ]

    def query_radius(self, lat: float, lon: float, radius_km: float) -> list[StrikeLocation]:
        if self._kdtree is None:
            return []
        radius_m = radius_km * 1_000.0
        x = lon * _DEG_TO_M * self._ref_cos_lat
        y = lat * _DEG_TO_M
        idxs = self._kdtree.query_ball_point([x, y], radius_m)
        if not idxs:
            return []
        query_xy = np.array([[x, y]])
        pts = self._xy[idxs]
        dists = np.linalg.norm(pts - query_xy, axis=1)
        order = np.argsort(dists)
        return [self._strikes[idxs[i]] for i in order]

    def get_hotspots(
        self, min_strikes: int = 3, cluster_radius_m: float = 500.0
    ) -> list[StrikeHotspot]:
        if not self._strikes or self._xy is None:
            return []

        from collections import Counter

        assigned = [-1] * len(self._strikes)
        cluster_centers: list[np.ndarray] = []
        cluster_strikes: list[list[int]] = []

        loc_counts = Counter(s.location_name for s in self._strikes)
        order = sorted(
            range(len(self._strikes)),
            key=lambda i: -loc_counts[self._strikes[i].location_name],
        )

        for i in order:
            pt = self._xy[i]
            placed = False
            for cid, center in enumerate(cluster_centers):
                if np.linalg.norm(pt - center) <= cluster_radius_m:
                    cluster_strikes[cid].append(i)
                    assigned[i] = cid
                    placed = True
                    break
            if not placed:
                assigned[i] = len(cluster_centers)
                cluster_centers.append(pt.copy())
                cluster_strikes.append([i])

        hotspots: list[StrikeHotspot] = []
        for cid, members in enumerate(cluster_strikes):
            if len(members) < min_strikes:
                continue
            member_strikes = [self._strikes[i] for i in members]
            cat_counts = Counter(s.category for s in member_strikes)
            dominant_cat = cat_counts.most_common(1)[0][0]
            most_recent = max(member_strikes, key=lambda s: s.date)
            center = cluster_centers[cid]
            lat = center[1] / _DEG_TO_M
            lon = center[0] / (_DEG_TO_M * self._ref_cos_lat)
            pts = self._xy[members]
            radius = float(np.max(np.linalg.norm(pts - center, axis=1)))
            hotspots.append(StrikeHotspot(
                lat=lat,
                lon=lon,
                strike_count=len(members),
                category=dominant_cat,
                location_name=most_recent.location_name,
                radius_m=radius,
            ))

        hotspots.sort(key=lambda h: -h.strike_count)
        return hotspots
