from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import h3
import numpy as np
from shapely.geometry import shape

from droneimpact.config import ShelteringConfig


class BuildingIndex:
    """H3-indexed building sheltering lookup.

    Pre-computes the dominant building protection class per H3 cell from OSM
    building footprints, then provides fast batch lookups of blast/frag
    reduction factors for impact coordinates.
    """

    def __init__(
        self,
        cell_class: dict[str, str],
        config: ShelteringConfig,
        resolution: int = 8,
    ):
        self._cell_class = cell_class
        self._config = config
        self._resolution = resolution

    @classmethod
    def load_from_file(
        cls,
        path: str | Path,
        config: ShelteringConfig,
        resolution: int = 8,
    ) -> BuildingIndex:
        with open(path) as f:
            geojson = json.load(f)
        return cls.from_features(geojson.get("features", []), config, resolution)

    @classmethod
    def from_features(
        cls,
        features: list[dict],
        config: ShelteringConfig,
        resolution: int = 8,
    ) -> BuildingIndex:
        tag_map = config.tag_to_class()

        cell_votes: dict[str, Counter] = {}
        for feat in features:
            props = feat.get("properties") or {}
            building_tag = props.get("building", "")
            cls_name = tag_map.get(building_tag)
            if cls_name is None:
                continue

            geom = shape(feat["geometry"])
            centroid = geom.centroid
            lat, lon = centroid.y, centroid.x
            if not (math.isfinite(lat) and math.isfinite(lon)
                    and -90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            cell = h3.latlng_to_cell(lat, lon, resolution)
            if cell not in cell_votes:
                cell_votes[cell] = Counter()
            cell_votes[cell][cls_name] += 1

        cell_class: dict[str, str] = {}
        for cell, votes in cell_votes.items():
            cell_class[cell] = votes.most_common(1)[0][0]

        return cls(cell_class, config, resolution)

    @classmethod
    def empty(cls, config: ShelteringConfig) -> BuildingIndex:
        return cls({}, config)

    def sheltering_factor_batch(
        self, lats: np.ndarray, lons: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (blast_reduction, frag_reduction) arrays of shape (N,).

        Values are 0.0 for open air (no building data) and up to 0.9 for
        reinforced concrete.
        """
        n = len(lats)
        blast_red = np.zeros(n, dtype=np.float64)
        frag_red = np.zeros(n, dtype=np.float64)

        if not self._cell_class:
            return blast_red, frag_red

        cache: dict[str, tuple[float, float]] = {}
        for i in range(n):
            lat_f, lon_f = float(lats[i]), float(lons[i])
            if not (math.isfinite(lat_f) and math.isfinite(lon_f)
                    and -90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                continue
            cell = h3.latlng_to_cell(lat_f, lon_f, self._resolution)
            cls_name = self._cell_class.get(cell)
            if cls_name is None:
                continue
            if cls_name not in cache:
                cache[cls_name] = self._config.reductions(cls_name)
            blast_red[i], frag_red[i] = cache[cls_name]

        return blast_red, frag_red

    @property
    def cell_count(self) -> int:
        return len(self._cell_class)
