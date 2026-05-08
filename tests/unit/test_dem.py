import numpy as np
import pytest

from droneimpact.data.dem import DEMIndex, DEMOutOfBoundsError

BOUNDS = dict(west=30.0, south=47.0, east=32.0, north=49.0)


@pytest.fixture
def flat_dem():
    data = np.full((10, 10), 100.0, dtype=np.float32)
    return DEMIndex.from_array(data, **BOUNDS)


@pytest.fixture
def sloped_dem():
    # Elevation increases from south (0 m) to north (900 m) across 10 rows
    rows = np.linspace(0, 900, 10, dtype=np.float32)
    data = np.tile(rows[:, None], (1, 10))
    # Rasterio origin is top-left (north), so row 0 = north (900 m), row 9 = south (0 m)
    # Flip so row 0 = north = high elevation
    data = data[::-1].copy()
    return DEMIndex.from_array(data, **BOUNDS)


def test_flat_dem_elevation(flat_dem):
    assert flat_dem.get_elevation(48.0, 31.0) == pytest.approx(100.0, abs=0.1)


def test_flat_dem_agl(flat_dem):
    assert flat_dem.msl_to_agl(48.0, 31.0, 500.0) == pytest.approx(400.0, abs=0.1)


def test_agl_clamped_at_zero(flat_dem):
    assert flat_dem.msl_to_agl(48.0, 31.0, 50.0) == 0.0


def test_sloped_dem_north_higher(sloped_dem):
    south_elev = sloped_dem.get_elevation(47.1, 31.0)
    north_elev = sloped_dem.get_elevation(48.9, 31.0)
    assert north_elev > south_elev


def test_batch_matches_scalar(flat_dem):
    lats = np.array([47.5, 48.0, 48.5])
    lons = np.array([30.5, 31.0, 31.5])
    batch = flat_dem.get_elevation_batch(lats, lons)
    for i in range(len(lats)):
        scalar = flat_dem.get_elevation(lats[i], lons[i])
        assert batch[i] == pytest.approx(scalar, abs=0.001)


def test_out_of_bounds_raises(flat_dem):
    with pytest.raises(DEMOutOfBoundsError):
        flat_dem.get_elevation(55.0, 31.0)


def test_batch_out_of_bounds_raises(flat_dem):
    lats = np.array([48.0, 55.0])
    lons = np.array([31.0, 31.0])
    with pytest.raises(DEMOutOfBoundsError):
        flat_dem.get_elevation_batch(lats, lons)


def test_batch_agl_clamped(flat_dem):
    lats = np.array([47.5, 48.0, 48.5])
    lons = np.array([31.0, 31.0, 31.0])
    agl = flat_dem.msl_to_agl_batch(lats, lons, altitude_msl=0.0)
    assert np.all(agl == 0.0)


def test_batch_agl_positive(flat_dem):
    lats = np.array([47.5, 48.0, 48.5])
    lons = np.array([31.0, 31.0, 31.0])
    agl = flat_dem.msl_to_agl_batch(lats, lons, altitude_msl=300.0)
    assert np.all(agl == pytest.approx(200.0, abs=0.1))


def test_nodata_replaced_on_load(tmp_path):
    import rasterio
    import rasterio.transform

    tif = tmp_path / "test.tif"
    data = np.full((5, 5), -32768, dtype=np.int16)
    transform = rasterio.transform.from_bounds(30.0, 47.0, 32.0, 49.0, 5, 5)
    with rasterio.open(
        tif, "w", driver="GTiff", height=5, width=5,
        count=1, dtype="int16", crs="EPSG:4326", transform=transform,
        nodata=-32768,
    ) as dst:
        dst.write(data, 1)

    dem = DEMIndex.load_from_file(tif)
    assert dem.get_elevation(48.0, 31.0) == pytest.approx(0.0, abs=0.1)


def test_custom_nodata_replaced_on_load(tmp_path):
    """DEM with nodata=-9999 should also be handled correctly."""
    import rasterio
    import rasterio.transform

    tif = tmp_path / "custom_nodata.tif"
    data = np.full((5, 5), -9999, dtype=np.int16)
    transform = rasterio.transform.from_bounds(30.0, 47.0, 32.0, 49.0, 5, 5)
    with rasterio.open(
        tif, "w", driver="GTiff", height=5, width=5,
        count=1, dtype="int16", crs="EPSG:4326", transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)

    dem = DEMIndex.load_from_file(tif)
    assert dem.get_elevation(48.0, 31.0) == pytest.approx(0.0, abs=0.1)
