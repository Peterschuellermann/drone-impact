from __future__ import annotations

from pathlib import Path

import h3
import numpy as np


class PopulationIndex:
    def __init__(self, cell_data: dict[str, float], resolution: int = 8):
        self._data = cell_data
        self._resolution = resolution
        if cell_data:
            sample_cell = next(iter(cell_data))
            self._cell_area_km2 = h3.cell_area(sample_cell, unit="km^2")
        else:
            # Compute area for a placeholder cell at the given resolution
            placeholder = h3.latlng_to_cell(0.0, 0.0, resolution)
            self._cell_area_km2 = h3.cell_area(placeholder, unit="km^2")

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
                    area_km2 = h3.cell_area(h3_id, unit="km^2")
                    cell_data[h3_id] = float(pop) / area_km2
        return cls(cell_data, resolution)

    @classmethod
    def from_dict(cls, cell_dict: dict[str, float], resolution: int = 8) -> "PopulationIndex":
        return cls(cell_dict, resolution)

    def _k_for_radius(self, radius_m: float) -> int:
        cell_diameter_m = (self._cell_area_km2 ** 0.5) * 1000.0
        return max(1, int(np.ceil(radius_m / cell_diameter_m)))

    def query(self, lat: float, lon: float, radius_m: float) -> float:
        centre = h3.latlng_to_cell(lat, lon, self._resolution)
        k = self._k_for_radius(radius_m)
        neighbourhood = h3.grid_disk(centre, k)
        total = sum(self._data.get(cell, 0.0) for cell in neighbourhood)
        return float(total * self._cell_area_km2)

    def query_batch(
        self, lats: np.ndarray, lons: np.ndarray, radius_m: float
    ) -> np.ndarray:
        return np.array(
            [self.query(float(lat), float(lon), radius_m)
             for lat, lon in zip(lats, lons)],
            dtype=np.float32,
        )

    @property
    def resolution(self) -> int:
        return self._resolution

    @property
    def cell_count(self) -> int:
        return len(self._data)
