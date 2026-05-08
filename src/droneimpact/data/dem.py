from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform


class DEMOutOfBoundsError(ValueError):
    pass


class DEMIndex:
    def __init__(self, data: np.ndarray, transform, crs=None):
        self._data = data.astype(np.float32)
        self._transform = transform
        self._crs = crs
        self._rows, self._cols = self._data.shape

    @classmethod
    def load_from_file(cls, path: str | Path) -> "DEMIndex":
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            nodata = src.nodata
            if nodata is not None:
                data = np.where(data == nodata, 0.0, data)
            return cls(data, src.transform, src.crs)

    @classmethod
    def from_array(
        cls,
        data: np.ndarray,
        west: float,
        south: float,
        east: float,
        north: float,
    ) -> "DEMIndex":
        transform = rasterio.transform.from_bounds(
            west, south, east, north, data.shape[1], data.shape[0]
        )
        return cls(data, transform)

    def _latlon_to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
        # rasterio transform maps pixel (col, row) → (x=lon, y=lat)
        col, row = ~self._transform * (lon, lat)
        if not (-0.5 <= row <= self._rows - 0.5 and -0.5 <= col <= self._cols - 0.5):
            raise DEMOutOfBoundsError(
                f"Coordinate ({lat:.4f}, {lon:.4f}) is outside DEM bounds"
            )
        return float(row), float(col)

    def _bilinear(self, row: float, col: float) -> float:
        row = max(0.0, min(row, self._rows - 1.0))
        col = max(0.0, min(col, self._cols - 1.0))
        r0 = int(np.floor(row))
        c0 = int(np.floor(col))
        r1 = min(r0 + 1, self._rows - 1)
        c1 = min(c0 + 1, self._cols - 1)
        dr = row - r0
        dc = col - c0

        return float(
            (1 - dr) * (1 - dc) * self._data[r0, c0]
            + (1 - dr) * dc * self._data[r0, c1]
            + dr * (1 - dc) * self._data[r1, c0]
            + dr * dc * self._data[r1, c1]
        )

    def get_elevation(self, lat: float, lon: float) -> float:
        row, col = self._latlon_to_pixel(lat, lon)
        return self._bilinear(row, col)

    def get_elevation_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        lats = np.asarray(lats, dtype=np.float64)
        lons = np.asarray(lons, dtype=np.float64)

        # Vectorised pixel coordinates
        cols, rows = ~self._transform * (lons, lats)

        # Bounds check
        oob = (
            (rows < -0.5) | (rows > self._rows - 0.5)
            | (cols < -0.5) | (cols > self._cols - 0.5)
        )
        if np.any(oob):
            idx = int(np.argmax(oob))
            raise DEMOutOfBoundsError(
                f"Coordinate ({lats[idx]:.4f}, {lons[idx]:.4f}) is outside DEM bounds"
            )

        rows = np.clip(rows, 0.0, self._rows - 1.0)
        cols = np.clip(cols, 0.0, self._cols - 1.0)

        r0 = np.floor(rows).astype(np.int32)
        c0 = np.floor(cols).astype(np.int32)
        r1 = np.minimum(r0 + 1, self._rows - 1)
        c1 = np.minimum(c0 + 1, self._cols - 1)
        dr = rows - r0
        dc = cols - c0

        return (
            (1 - dr) * (1 - dc) * self._data[r0, c0]
            + (1 - dr) * dc * self._data[r0, c1]
            + dr * (1 - dc) * self._data[r1, c0]
            + dr * dc * self._data[r1, c1]
        ).astype(np.float32)

    def msl_to_agl(self, lat: float, lon: float, altitude_msl: float) -> float:
        return max(0.0, altitude_msl - self.get_elevation(lat, lon))

    def msl_to_agl_batch(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
        altitude_msl: float,
    ) -> np.ndarray:
        terrain = self.get_elevation_batch(lats, lons)
        return np.maximum(0.0, altitude_msl - terrain)
