from __future__ import annotations

import pytest

from droneimpact.data.strikes import StrikeIndex, StrikeLocation


def _feat(id: str, lon: float, lat: float, **props) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": id,
            "date": props.get("date", "2023-01-01"),
            "source": props.get("source", "bellingcat"),
            "location_name": props.get("location_name", "Kyiv"),
            "category": props.get("category", "residential"),
            "description": props.get("description", ""),
            "confidence": props.get("confidence", 0.9),
        },
    }


_FEATURES_5 = [
    _feat("1", 30.5, 50.5, category="residential"),
    _feat("2", 30.6, 50.6, category="industrial"),
    _feat("3", 36.0, 49.0, category="energy"),
    _feat("4", 25.0, 47.0, category="military"),
    _feat("5", 32.0, 48.5, category="unknown"),
]


def test_empty_index():
    idx = StrikeIndex.from_features([])
    assert idx.count == 0


def test_from_features_count():
    idx = StrikeIndex.from_features(_FEATURES_5)
    assert idx.count == 5


def test_query_bbox_inside():
    idx = StrikeIndex.from_features(_FEATURES_5)
    results = idx.query_bbox(south=48.0, west=28.0, north=51.0, east=33.0)
    ids = {s.id for s in results}
    assert "1" in ids
    assert "2" in ids
    assert "5" in ids
    assert "3" not in ids
    assert "4" not in ids


def test_query_bbox_excludes_outside():
    idx = StrikeIndex.from_features(_FEATURES_5)
    results = idx.query_bbox(south=48.0, west=28.0, north=51.0, east=33.0)
    assert all(28.0 <= s.lon <= 33.0 and 48.0 <= s.lat <= 51.0 for s in results)


def test_query_radius_sorted_by_distance():
    features = [
        _feat("near", 30.0, 50.0),
        _feat("mid", 30.1, 50.0),
        _feat("far", 30.5, 50.0),
    ]
    idx = StrikeIndex.from_features(features)
    results = idx.query_radius(lat=50.0, lon=30.0, radius_km=100.0)
    assert [s.id for s in results] == ["near", "mid", "far"]


def test_query_radius_excludes_beyond_range():
    features = [
        _feat("a", 30.0, 50.0),
        _feat("b", 31.0, 50.0),
    ]
    idx = StrikeIndex.from_features(features)
    results = idx.query_radius(lat=50.0, lon=30.0, radius_km=50.0)
    ids = {s.id for s in results}
    assert "a" in ids
    assert "b" not in ids


def test_get_hotspots_clusters_nearby():
    features = [
        _feat("a", 30.000, 50.000, category="residential", location_name="Kyiv"),
        _feat("b", 30.001, 50.000, category="residential", location_name="Kyiv"),
        _feat("c", 30.000, 50.001, category="residential", location_name="Kyiv"),
        _feat("iso", 35.0, 45.0, category="military", location_name="Other"),
    ]
    idx = StrikeIndex.from_features(features)
    hotspots = idx.get_hotspots(min_strikes=2, cluster_radius_m=500.0)
    assert len(hotspots) == 1
    h = hotspots[0]
    assert h.strike_count == 3
    assert h.category == "residential"


def test_get_hotspots_isolated_excluded():
    features = [
        _feat("a", 30.000, 50.000, category="residential", location_name="Kyiv"),
        _feat("b", 30.001, 50.000, category="residential", location_name="Kyiv"),
        _feat("c", 30.000, 50.001, category="residential", location_name="Kyiv"),
        _feat("iso", 35.0, 45.0, category="military", location_name="Other"),
    ]
    idx = StrikeIndex.from_features(features)
    hotspots = idx.get_hotspots(min_strikes=2, cluster_radius_m=500.0)
    location_names = {h.location_name for h in hotspots}
    assert "Other" not in location_names


def test_get_hotspots_sorted_by_count():
    features = [
        _feat("a1", 30.000, 50.000, location_name="A"),
        _feat("a2", 30.001, 50.000, location_name="A"),
        _feat("a3", 30.000, 50.001, location_name="A"),
        _feat("b1", 34.000, 50.000, location_name="B"),
        _feat("b2", 34.001, 50.000, location_name="B"),
    ]
    idx = StrikeIndex.from_features(features)
    hotspots = idx.get_hotspots(min_strikes=2, cluster_radius_m=500.0)
    assert hotspots[0].strike_count >= hotspots[-1].strike_count


def test_load_from_file_missing_returns_empty():
    idx = StrikeIndex.load_from_file("/nonexistent/path/ukraine_strikes.geojson")
    assert idx.count == 0


def test_query_radius_empty_index():
    idx = StrikeIndex.from_features([])
    results = idx.query_radius(lat=50.0, lon=30.0, radius_km=100.0)
    assert results == []


def test_strike_location_fields():
    idx = StrikeIndex.from_features([_feat("x", 30.0, 50.0, category="energy", confidence=0.8)])
    assert idx.count == 1
    s = idx.query_bbox(49.0, 29.0, 51.0, 31.0)[0]
    assert isinstance(s, StrikeLocation)
    assert s.id == "x"
    assert s.category == "energy"
    assert s.confidence == pytest.approx(0.8)
