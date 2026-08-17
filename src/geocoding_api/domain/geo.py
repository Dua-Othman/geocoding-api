from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def to_unit_vector(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    """lat/lon → 3D point on the unit sphere, where straight-line distance
    ranks the same as surface distance — no antimeridian or pole issues."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_lat = math.cos(lat)
    return (cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat))


def chord_to_km(chord: float) -> float:
    """chord length → great-circle km"""
    return 2 * math.asin(min(chord, 2) / 2) * EARTH_RADIUS_KM


def km_to_chord(km: float) -> float:
    """great-circle km → chord length"""
    theta = km / EARTH_RADIUS_KM
    if theta >= math.pi:
        return 2.0
    return 2 * math.sin(theta / 2)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """reference implementation — tests use it to cross-check the tree"""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * math.asin(min(1.0, math.sqrt(a))) * EARTH_RADIUS_KM
