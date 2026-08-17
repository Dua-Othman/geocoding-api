from __future__ import annotations

import math


def levenshtein(a: str, b: str, cap: float = math.inf) -> int:
    """Edit distance, capped: returns cap + 1 early once it can't stay under cap."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return int(cap) + 1
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    curr = [0] * (len(b) + 1)

    for i in range(1, len(a) + 1):
        curr[0] = i
        row_min = curr[0]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            if curr[j] < row_min:
                row_min = curr[j]
        if row_min > cap:
            return int(cap) + 1
        prev, curr = curr, prev

    return prev[len(b)]


def max_edits_for_length(length: int) -> int:
    """Edit budget by query length (Elasticsearch AUTO): short queries get none."""
    if length <= 2:
        return 0
    if length <= 5:
        return 1
    return 2
