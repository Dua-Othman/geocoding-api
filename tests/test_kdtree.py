import random

import pytest

from geocoding_api.domain.geo import haversine_km
from geocoding_api.domain.kdtree import SpatialPoint, SphericalKdTree


def test_matches_brute_force_haversine_ranking_on_random_points():
    rng = random.Random(42)
    points = [
        SpatialPoint(lat=rng.uniform(-90, 90), lon=rng.uniform(-180, 180), item=i)
        for i in range(400)
    ]
    tree = SphericalKdTree(points)

    for _ in range(30):
        q_lat = rng.uniform(-90, 90)
        q_lon = rng.uniform(-180, 180)
        expected = sorted(
            ((p.item, haversine_km(q_lat, q_lon, p.lat, p.lon)) for p in points),
            key=lambda pair: pair[1],
        )[:5]
        actual = tree.nearest(q_lat, q_lon, 5)

        assert [r.item for r in actual] == [item for item, _ in expected]
        for result, (_, distance) in zip(actual, expected):
            assert result.distance_km == pytest.approx(distance, abs=1e-6)


def test_handles_the_antimeridian_correctly():
    tree = SphericalKdTree(
        [
            SpatialPoint(lat=0, lon=179.9, item="east-side"),
            SpatialPoint(lat=0, lon=-179.9, item="west-side"),
            SpatialPoint(lat=0, lon=170, item="far"),
        ]
    )
    # Query sits at lon 179.99: "west-side" is just across the antimeridian,
    # ~12 km away — a naive lat/lon-Euclidean tree would rank it last.
    results = tree.nearest(0, 179.99, 3)
    assert [r.item for r in results] == ["east-side", "west-side", "far"]
    assert results[1].distance_km < 15


def test_handles_points_near_the_pole():
    tree = SphericalKdTree(
        [
            SpatialPoint(lat=89.9, lon=0, item="a"),
            SpatialPoint(lat=89.9, lon=180, item="b"),
        ]
    )
    # Longitudes differ by 180° but both points are ~11 km from the pole.
    assert len(tree.nearest(89.95, 90, 2, 20)) == 2


def test_enforces_the_radius_cutoff():
    tree = SphericalKdTree(
        [
            SpatialPoint(lat=0, lon=0, item="near"),
            SpatialPoint(lat=0, lon=10, item="far"),
        ]
    )
    results = tree.nearest(0, 0.05, 5, 100)
    assert [r.item for r in results] == ["near"]


def test_returns_fewer_than_k_results_when_the_dataset_is_small():
    tree = SphericalKdTree([SpatialPoint(lat=1, lon=1, item="only")])
    assert len(tree.nearest(0, 0, 5)) == 1
    assert SphericalKdTree([]).nearest(0, 0, 5) == []
