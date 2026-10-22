"""City districts: downtown in the middle, one themed district per quadrant around it.

Blocks are (i, j) with centers at (80 i, 80 j); -z is north. Boundaries are jittered per block
so they do not run along perfectly straight roads.
"""
import math

import config as C

DOWNTOWN, CORPORATE, MARKET, RESIDENTIAL, RUST, HARBOR = range(6)
NAMES = ("市中心", "企業特區", "霓虹夜市", "住宅區", "鏽蝕區", "港灣區")


def _hash(i, j, salt):
    h = ((i * 73856093) ^ (j * 19349663) ^ (salt * 83492791)) & 0xFFFFFFFF
    h = (h * 2654435761) & 0xFFFFFFFF
    h ^= h >> 13
    return (h * 2246822519 & 0xFFFFFFFF) / 0xFFFFFFFF


def district(i, j):
    """District index of block (i, j)."""
    if j >= C.HARBOR_ROW:
        return HARBOR                                          # the waterfront row (water beyond)
    d = max(abs(i), abs(j)) + (_hash(i, j, 1) - 0.5) * 1.6
    if d <= C.DOWNTOWN_BLOCKS + 0.5:
        return DOWNTOWN
    a = math.atan2(-j, i) + (_hash(i, j, 2) - 0.5) * 0.3     # 0 east, pi/2 north
    if 0.0 <= a < math.pi / 2:
        return CORPORATE                                       # north-east
    if a >= math.pi / 2:
        return MARKET                                          # north-west
    if a < -math.pi / 2:
        return RUST                                            # south-west
    return RESIDENTIAL                                         # south-east


def district_at(x, z):
    return district(int(round(x / C.BLOCK_PITCH)), int(round(z / C.BLOCK_PITCH)))


def water_blocks():
    """Blocks under the sea (no buildings)."""
    R = C.CITY_BLOCKS
    return {(i, j) for i in range(-R, R + 1) for j in range(C.HARBOR_ROW + 1, R + 1)}


def container_blocks():
    return {(i, C.HARBOR_ROW) for i in C.CONTAINER_BLOCKS}


def park_blocks():
    return {(i, j) for _, i, j, _ in C.PARKS}


def park_at(x, z, margin=0.0):
    """(name, kind, center x, center z) of the park / plaza containing (x, z), or None."""
    for name, i, j, kind in C.PARKS:
        cx, cz = i * C.BLOCK_PITCH, j * C.BLOCK_PITCH
        h = C.BLOCK_PITCH / 2 - C.ROAD_HALF + margin
        if abs(x - cx) < h and abs(z - cz) < h:
            return name, kind, cx, cz
    return None
