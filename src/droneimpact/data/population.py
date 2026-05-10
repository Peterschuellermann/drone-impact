from __future__ import annotations

import math
import threading
from collections import OrderedDict
from pathlib import Path

import h3
import numpy as np

_DEFAULT_CACHE_MAX = 10_000


class PopulationIndex:
    """H3-indexed population lookup.

    ``_data`` stores **population counts** (persons per cell), not density.
    ``query()`` sums population counts directly without area multiplication.
    """

    def __init__(self, cell_data: dict[str, float], resolution: int = 8,
                 cache_max: int = _DEFAULT_CACHE_MAX):
        self._data = cell_data
        self._resolution = resolution
        edge_m = h3.average_hexagon_edge_length(resolution, unit="m")
        self._cell_diameter_m = edge_m * math.sqrt(3)
        self._disk_cache: OrderedDict[str, float] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_max = cache_max

    @classmethod
    def load_from_file(cls, path: str | Path, resolution: int = 8) -> "PopulationIndex":
        import fiona

        cell_data: dict[str, float] = {}
        with fiona.open(path) as src:
            for feature in src:
                props = feature["properties"]
                h3_id = props.get("h3")
                pop = props.get("population")
                if h3_id and pop and pop > 0:
                    cell_data[h3_id] = float(pop)
        return cls(cell_data, resolution)

    @classmethod
    def from_dict(cls, cell_dict: dict[str, float], resolution: int = 8) -> "PopulationIndex":
        """Create index from ``{h3_cell: population_count}``."""
        return cls(cell_dict, resolution)

    def _k_for_radius(self, radius_m: float) -> int:
        return max(1, int(np.ceil(radius_m / self._cell_diameter_m)))

    def _disk_population(self, centre: str, k: int) -> float:
        key = f"{centre}:{k}"
        with self._cache_lock:
            cached = self._disk_cache.get(key)
            if cached is not None:
                self._disk_cache.move_to_end(key)
                return cached
        neighbourhood = h3.grid_disk(centre, k)
        total = sum(self._data.get(cell, 0.0) for cell in neighbourhood)
        with self._cache_lock:
            if len(self._disk_cache) >= self._cache_max:
                self._disk_cache.popitem(last=False)
            self._disk_cache[key] = total
        return total

    def query(self, lat: float, lon: float, radius_m: float) -> float:
        centre = h3.latlng_to_cell(lat, lon, self._resolution)
        k = self._k_for_radius(radius_m)
        return float(self._disk_population(centre, k))

    def latlng_to_cells(
        self, lats: np.ndarray, lons: np.ndarray,
    ) -> list[str]:
        result = []
        for i in range(len(lats)):
            lat_f, lon_f = float(lats[i]), float(lons[i])
            if not (math.isfinite(lat_f) and math.isfinite(lon_f)
                    and -90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                lat_f, lon_f = 0.0, 0.0
            result.append(h3.latlng_to_cell(lat_f, lon_f, self._resolution))
        return result

    def query_batch(
        self, lats: np.ndarray, lons: np.ndarray, radius_m: float
    ) -> np.ndarray:
        cells = self.latlng_to_cells(lats, lons)
        return self.query_batch_cells(cells, radius_m)

    def query_batch_cells(
        self, cells: list[str], radius_m: float,
    ) -> np.ndarray:
        k = self._k_for_radius(radius_m)
        unique_cells = set(cells)
        cell_pop = {c: self._disk_population(c, k) for c in unique_cells}

        result = np.empty(len(cells), dtype=np.float32)
        for i, c in enumerate(cells):
            result[i] = cell_pop[c]
        return result

    @property
    def resolution(self) -> int:
        return self._resolution

    @property
    def cell_count(self) -> int:
        return len(self._data)
