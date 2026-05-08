from __future__ import annotations

import functools
import math

import numpy as np
from pyproj import Transformer


@functools.lru_cache(maxsize=512)
def _make_transformers(origin_lat: float, origin_lon: float):
    # Local azimuthal equidistant projection centred on origin
    proj_str = (
        f"+proj=aeqd +lat_0={origin_lat} +lon_0={origin_lon} "
        "+units=m +ellps=WGS84"
    )
    to_enu = Transformer.from_crs("EPSG:4326", proj_str, always_xy=True)
    to_wgs = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True)
    return to_enu, to_wgs


def _rounded_origin(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 4), round(lon, 4)


def wgs84_to_enu(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    to_enu, _ = _make_transformers(*_rounded_origin(origin_lat, origin_lon))
    east, north = to_enu.transform(lon, lat)
    return float(east), float(north)


def enu_to_wgs84(east_m: float, north_m: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    _, to_wgs = _make_transformers(*_rounded_origin(origin_lat, origin_lon))
    lon, lat = to_wgs.transform(east_m, north_m)
    return float(lat), float(lon)


def wgs84_to_enu_batch(
    lats: np.ndarray,
    lons: np.ndarray,
    origin_lat: float,
    origin_lon: float,
) -> np.ndarray:
    to_enu, _ = _make_transformers(*_rounded_origin(origin_lat, origin_lon))
    east, north = to_enu.transform(lons, lats)
    return np.stack([east, north], axis=1)


def enu_to_wgs84_batch(
    east_north: np.ndarray,
    origin_lat: float,
    origin_lon: float,
) -> np.ndarray:
    _, to_wgs = _make_transformers(*_rounded_origin(origin_lat, origin_lon))
    lon, lat = to_wgs.transform(east_north[:, 0], east_north[:, 1])
    return np.stack([lat, lon], axis=1)


def bearing_to_enu_angle_rad(heading_deg: float) -> float:
    return math.radians(90.0 - heading_deg)
