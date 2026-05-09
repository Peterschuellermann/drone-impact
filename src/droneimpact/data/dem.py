from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
import rasterio.windows


class DEMOutOfBoundsError(ValueError):
    pass


class DEMIndex:
    def __init__(
        self,
        data: np.ndarray | None,
        transform,
        crs=None,
        *,
        file_path: str | None = None,
        nodata: float | None = None,
        rows: int = 0,
        cols: int = 0,
    ):
        self._data = np.ascontiguousarray(data) if data is not None else None
        self._transform = transform
        self._crs = crs
        self._file_path = file_path
        self._dataset = None
        self._dataset_pid: int | None = None
        self._nodata = nodata
        if data is not None:
            self._rows, self._cols = data.shape
        else:
            self._rows = rows
            self._cols = cols

    def _open_dataset(self):
        pid = os.getpid()
        if self._dataset is not None and self._dataset_pid == pid:
            return self._dataset
        if self._dataset is not None:
            try:
                self._dataset.close()
            except Exception:
                pass
        self._dataset = rasterio.open(self._file_path)
        self._dataset_pid = pid
        return self._dataset

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_dataset"] = None
        state["_dataset_pid"] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def __del__(self):
        if getattr(self, "_dataset", None) is not None:
            try:
                self._dataset.close()
            except Exception:
                pass

    @classmethod
    def load_from_file(cls, path: str | Path) -> "DEMIndex":
        resolved = str(Path(path).resolve())
        with rasterio.open(resolved) as dataset:
            return cls(
                data=None,
                transform=dataset.transform,
                crs=dataset.crs,
                file_path=resolved,
                nodata=dataset.nodata,
                rows=dataset.height,
                cols=dataset.width,
            )

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

    def _read_block(self, r0: int, c0: int, r1: int, c1: int) -> np.ndarray:
        ds = self._open_dataset()
        window = rasterio.windows.Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
        block = ds.read(1, window=window).astype(np.float32)
        if self._nodata is not None:
            block = np.where(block == self._nodata, 0.0, block)
        return block

    def _latlon_to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
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

        if self._data is not None:
            block = self._data
            lr0, lc0, lr1, lc1 = r0, c0, r1, c1
        else:
            block = self._read_block(r0, c0, r1, c1)
            lr0, lc0, lr1, lc1 = 0, 0, r1 - r0, c1 - c0

        return float(
            (1 - dr) * (1 - dc) * block[lr0, lc0]
            + (1 - dr) * dc * block[lr0, lc1]
            + dr * (1 - dc) * block[lr1, lc0]
            + dr * dc * block[lr1, lc1]
        )

    def get_elevation(self, lat: float, lon: float) -> float:
        row, col = self._latlon_to_pixel(lat, lon)
        return self._bilinear(row, col)

    def get_elevation_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        lats = np.asarray(lats, dtype=np.float64)
        lons = np.asarray(lons, dtype=np.float64)

        cols, rows = ~self._transform * (lons, lats)

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

        if self._data is not None:
            data = self._data
            lr0, lc0, lr1, lc1 = r0, c0, r1, c1
        else:
            min_r, min_c = int(r0.min()), int(c0.min())
            max_r, max_c = int(r1.max()), int(c1.max())
            data = self._read_block(min_r, min_c, max_r, max_c)
            lr0 = r0 - min_r
            lc0 = c0 - min_c
            lr1 = r1 - min_r
            lc1 = c1 - min_c

        return (
            (1 - dr) * (1 - dc) * data[lr0, lc0]
            + (1 - dr) * dc * data[lr0, lc1]
            + dr * (1 - dc) * data[lr1, lc0]
            + dr * dc * data[lr1, lc1]
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
