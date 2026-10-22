"""Megatower specs and floor numbering.

1F is the 12 m lobby, 2F..NF are 4 m storeys starting at 12 m, RF (N+1) is the roof.
Every floor level is a multiple of 4 m, which is what the stairwell units rely on.
Interiors are built in tower-local coordinates (origin at the tower's center) and shifted.
"""
import math

import config as C
from i18n import tr

LOBBY = 1

THEMES = ("辦公室", "伺服器農場", "水耕農場", "交誼酒廊", "施工中", "公寓",       # 公寓: city buildings only
          "觀景台", "空中花園", "高空酒吧")                                 # megatower feature floors
_THEME_CUM = (0.4, 0.6, 0.75, 0.85, 1.0)
OBSERVATORY, SKY_GARDEN, SKY_BAR = 6, 7, 8


class Tower:
    def __init__(self, index, name, cx, cz, floors, half, accent):
        self.index, self.name = index, name
        self.cx, self.cz = cx, cz
        self.floors, self.half, self.accent = floors, half, accent
        self.roof = floors + 1
        self.height = C.LOBBY_HEIGHT + (floors - 1) * C.FLOOR_HEIGHT
        self.inner = half - C.TOWER_WALL
        self.top_storey = int(round((self.height - C.FLOOR_HEIGHT) / C.FLOOR_HEIGHT))   # last unit reaches the roof
        # stairwell, local coordinates (see config)
        self.stair_x0 = half - C.STAIR_INSET
        self.stair_hole = (self.stair_x0 + C.STAIR_LAND, C.STAIR_Z0,              # slab / roof opening (x0, z0, x1, z1)
                           self.stair_x0 + 2 * C.STAIR_LAND + C.STAIR_RUN,
                           C.STAIR_Z0 + 2 * C.STAIR_FLIGHT_W + C.STAIR_DIVIDER)
        # structural columns / lobby pillars at (+-column, +-column), kept clear of the stairwell
        self.column = min(half / 2, self.stair_x0 - 3.6)
        # external elevator car, world coordinates
        self.elev_x0, self.elev_x1 = cx + half, cx + half + C.ELEV_DEPTH
        self.block = (int(round(cx / C.BLOCK_PITCH)), int(round(cz / C.BLOCK_PITCH)))

    def level_y(self, k):
        """Floor surface height of floor k."""
        if k <= LOBBY:
            return 0.0
        if k >= self.roof:
            return self.height
        return C.LOBBY_HEIGHT + (k - 2) * C.FLOOR_HEIGHT

    def floor_at(self, y):
        """The floor whose storey contains height y (a little tolerance for standing on slabs)."""
        if y < C.LOBBY_HEIGHT - 0.5:
            return LOBBY
        if y >= self.height - 0.5:
            return self.roof
        return min(self.floors, int((y - C.LOBBY_HEIGHT + 0.5) // C.FLOOR_HEIGHT) + 2)

    def is_floor_level(self, y):
        """Does a stair landing at height y open onto a floor (not a lobby mid-height landing)?"""
        return y < 0.5 or (C.LOBBY_HEIGHT - 0.5 < y < self.height - 0.5)

    def label(self, k):
        if k <= LOBBY:
            return tr("1F 大廳")
        if k >= self.roof:
            return tr("RF 頂樓")
        return f"{k}F"

    def local(self, pos):
        return pos[0] - self.cx, pos[2] - self.cz

    def contains(self, pos, margin=0.0):
        h = self.half - margin
        return abs(pos[0] - self.cx) < h and abs(pos[2] - self.cz) < h

    def distance(self, pos):
        """Horizontal distance from pos to the footprint (0 inside)."""
        dx = max(abs(pos[0] - self.cx) - self.half, 0.0)
        dz = max(abs(pos[2] - self.cz) - self.half, 0.0)
        return math.hypot(dx, dz)

    def bounds(self):
        """World AABB of the tower volume (with the elevator side)."""
        return (self.cx - self.half, 0.0, self.cz - self.half, self.elev_x1, self.height, self.cz + self.half)


TOWERS = tuple(Tower(i, *spec) for i, spec in enumerate(C.TOWER_SPECS))
NEXUS = TOWERS[0]


def tower_at(pos, margin=0.0):
    """The tower whose footprint contains pos, or None."""
    for t in TOWERS:
        if t.contains(pos, margin):
            return t
    return None


def nearest_tower(pos):
    return min(TOWERS, key=lambda t: t.distance(pos))


def _hash(k):
    h = (k * 2654435761) & 0xFFFFFFFF
    h ^= h >> 15
    return (h * 2246822519 & 0xFFFFFFFF) / 0xFFFFFFFF


def feature(k):
    """Feature theme of a megatower floor (every 100th floor: observatory, sky garden, sky bar), or None."""
    if k <= 0 or k % 100:
        return None
    return (SKY_BAR, OBSERVATORY, SKY_GARDEN)[(k // 100) % 3]


def theme(k, tower=NEXUS):
    """Theme index of a regular floor (2..N), stable per floor."""
    f = feature(k)
    if f is not None:
        return f
    return pick_theme(_hash(k + 7919 * tower.index), _THEME_CUM)


def pick_theme(r, cum, themes=None):
    """Theme for a uniform random r: the first cumulative weight above r (themes maps positions to indices)."""
    for i, c in enumerate(cum):
        if r < c:
            return themes[i] if themes else i
    return themes[-1] if themes else len(cum) - 1
