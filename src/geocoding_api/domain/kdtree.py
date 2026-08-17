from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Generic, TypeVar

from .geo import chord_to_km, km_to_chord, to_unit_vector

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SpatialPoint(Generic[T]):
    lat: float
    lon: float
    item: T


@dataclass(frozen=True, slots=True)
class NearestResult(Generic[T]):
    item: T
    distance_km: float


@dataclass(slots=True)
class _TreeNode:
    idx: int
    axis: int
    left: "_TreeNode | None"
    right: "_TreeNode | None"


class SphericalKdTree(Generic[T]):
    """k-d tree over points projected onto the unit sphere.

    Chord distance ranks the same as great-circle distance, so plain 3D
    math stays correct near the antimeridian and the poles.
    """

    def __init__(self, points: list[SpatialPoint[T]]) -> None:
        self._items = [p.item for p in points]
        self._xyz: list[tuple[float, float, float]] = [
            to_unit_vector(p.lat, p.lon) for p in points
        ]
        indices = list(range(len(points)))
        self._root = self._build(indices, 0, len(indices), 0)

    @property
    def size(self) -> int:
        return len(self._items)

    def nearest(
        self, lat: float, lon: float, k: int, max_radius_km: float = math.inf
    ) -> list[NearestResult[T]]:
        if k <= 0 or self._root is None:
            return []
        q = to_unit_vector(lat, lon)
        radius_chord = km_to_chord(max_radius_km) if math.isfinite(max_radius_km) else 2.0
        radius_chord_sq = radius_chord * radius_chord
        best: list[tuple[int, float]] = []  # (idx, dist_sq), sorted ascending

        def worst_allowed() -> float:
            if len(best) < k:
                return radius_chord_sq
            return min(radius_chord_sq, best[-1][1])

        def visit(node: _TreeNode | None) -> None:
            if node is None:
                return
            x, y, z = self._xyz[node.idx]
            dist_sq = (q[0] - x) ** 2 + (q[1] - y) ** 2 + (q[2] - z) ** 2

            if dist_sq <= worst_allowed():
                pos = next((i for i, b in enumerate(best) if dist_sq < b[1]), None)
                if pos is None:
                    best.append((node.idx, dist_sq))
                else:
                    best.insert(pos, (node.idx, dist_sq))
                if len(best) > k:
                    best.pop()

            diff = q[node.axis] - self._xyz[node.idx][node.axis]
            near, far = (node.left, node.right) if diff <= 0 else (node.right, node.left)
            visit(near)
            # only cross the split if something closer could be on the far side
            if diff * diff <= worst_allowed():
                visit(far)

        visit(self._root)
        return [
            NearestResult(item=self._items[idx], distance_km=chord_to_km(math.sqrt(dist_sq)))
            for idx, dist_sq in best
        ]

    def _build(self, indices: list[int], lo: int, hi: int, depth: int) -> _TreeNode | None:
        # quickselect the median instead of sorting every level: O(n log n) build
        if lo >= hi:
            return None
        axis = depth % 3
        mid = (lo + hi) // 2
        _select(indices, lo, hi - 1, mid, key=lambda i: self._xyz[i][axis])
        return _TreeNode(
            idx=indices[mid],
            axis=axis,
            left=self._build(indices, lo, mid, depth + 1),
            right=self._build(indices, mid + 1, hi, depth + 1),
        )


def _select(arr: list[int], lo: int, hi: int, k: int, key) -> None:
    """Quickselect: put the k-th smallest (by key) at index k, like C++ nth_element."""
    while lo < hi:
        mid = (lo + hi) // 2
        if key(arr[mid]) < key(arr[lo]):
            arr[lo], arr[mid] = arr[mid], arr[lo]
        if key(arr[hi]) < key(arr[lo]):
            arr[lo], arr[hi] = arr[hi], arr[lo]
        if key(arr[hi]) < key(arr[mid]):
            arr[mid], arr[hi] = arr[hi], arr[mid]
        pivot = key(arr[mid])

        i, j = lo, hi
        while i <= j:
            while key(arr[i]) < pivot:
                i += 1
            while key(arr[j]) > pivot:
                j -= 1
            if i <= j:
                arr[i], arr[j] = arr[j], arr[i]
                i += 1
                j -= 1

        if k <= j:
            hi = j
        elif k >= i:
            lo = i
        else:
            return
