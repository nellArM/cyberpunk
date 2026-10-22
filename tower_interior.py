"""Builds the inside of a walk-in building around the player: floor slabs, switchback stairs,
elevator landing doors and themed furniture for the nearby floors only.

Two kinds of structure share the builders through a Layout (local coordinates + a frame
that maps them to the world):
- the megatowers: the shell is one box (tower.py); the shader cuts windows and landing
  doorways inside the y-range `open_range` on the tower at `open_center` only;
- ordinary city buildings (buildings.py): above the ground-floor shop, the floors are reached
  by a stair core behind the shop; the shader opens the windows of the building in `bldg`,
  and that building's solid upper collider is swapped for a hollow shell (`shell_index`).
"""
import math
from collections import defaultdict

import numpy as np

import buildings
import config as C
import districts
import floors
from collision import overlaps
from elevator import ShaftElevator
from geometry import box_bounds, BOX_FLOATS
from i18n import L, tr
from skybridges import approach_rect

WT = 0.2                                         # enclosure wall thickness
# per theme: slab hue, ceiling light intensity
THEME_LIGHT = ((0.55, 0.55), (0.58, 0.35), (0.33, 0.25), (0.83, 0.2), (0.1, 0.08), (0.08, 0.3),
               (0.5, 0.3), (0.33, 0.45), (0.83, 0.18))
# per district: (themes, cumulative weights) of a city building's upper floors
_BUILDING_THEMES = {
    districts.DOWNTOWN: ((0, 1, 2, 3, 4), (0.45, 0.6, 0.7, 0.85, 1.0)),
    districts.CORPORATE: ((0, 1, 3), (0.6, 0.9, 1.0)),
    districts.MARKET: ((3, 4, 5), (0.4, 0.7, 1.0)),
    districts.RESIDENTIAL: ((5, 0, 3), (0.8, 0.9, 1.0)),
    districts.RUST: ((4, 5, 1), (0.6, 0.9, 1.0)),
    districts.HARBOR: ((4, 5), (0.7, 1.0)),
}


class TowerLayout:
    """A megatower: square, origin at its center, 4 m storeys from the ground (lobby = 3)."""
    has_elevator = True

    def __init__(self, t):
        self.t = t
        self.key = ("t", t.index)
        self.index = t.index
        self.Ix = self.Iz = I = t.inner                        # inner half extent of the shell (Nexus 39.5)
        self.Ex = self.Ez = t.half - 0.02                      # slabs reach (almost) the facade
        self.HX0, self.HZ0, self.HX1, self.HZ1 = t.stair_hole
        self.SX0 = SX0 = t.stair_x0                            # stair enclosure, see config
        self.XA = SX0 + C.STAIR_LAND                           # flights start
        self.XB = self.XA + C.STAIR_RUN                        # flights end / mid landing start
        self.XC = self.XB + C.STAIR_LAND                       # mid landing end
        self.Z1A, self.Z1B = C.STAIR_Z0, C.STAIR_Z0 + C.STAIR_FLIGHT_W
        self.Z2A = self.Z1B + C.STAIR_DIVIDER
        self.Z2B = self.Z2A + C.STAIR_FLIGHT_W
        # areas furniture must keep clear (stairwell + its door approach, elevator landing)
        self.RESERVED = ((SX0 - 2.0, self.Z1A - 5.0, self.XC + 1.0, self.Z2B + 1.2), (t.half - 8.0, -5.0, I, 5.0))
        c = t.column
        self.COLUMNS = [(sx * c, sz * c) for sx in (-1, 1) for sz in (-1, 1)]
        self.floors, self.roof, self.height = t.floors, t.roof, t.height
        self.level_y, self.floor_at, self.is_floor_level, self.label = t.level_y, t.floor_at, t.is_floor_level, t.label
        self.n_storeys = t.top_storey + 1
        self.name = t.name

    def bounds(self, x0, z0, x1, z1):
        t = self.t
        return x0 + t.cx, z0 + t.cz, x1 + t.cx, z1 + t.cz

    def storey(self, u):
        return u * C.FLOOR_HEIGHT, (u + 1) * C.FLOOR_HEIGHT

    def storeys_near(self, y):
        s0 = max(0, int(math.floor((y - 8.0) / C.FLOOR_HEIGHT)))
        s1 = min(self.n_storeys - 1, int(math.floor((y + 16.0) / C.FLOOR_HEIGHT)))
        return range(s0, s1 + 1)

    def slab_bottom(self, k):
        return self.level_y(k) - C.SLAB

    def theme(self, k):
        return floors.theme(k, self.t)

    def floor_seed(self, k):
        return k * 7919 + 13 + 1000003 * self.index

    def crowd_seed(self, k):
        return k * 104729 + 7 + 1000003 * self.index


class BuildingLayout:
    """The upper floors of a city building; local x across the door face, z = depth - D/2."""
    has_elevator = False

    def __init__(self, rec, index, doors=()):
        """doors: skybridge door boxes (x0, y0, z0, x1, y1, z1) in this building's facade."""
        self.rec = rec
        self.key = ("b", index)
        self.index = index
        self.doors = list(doors)
        fr = self.fr = buildings.Frame(rec)
        W, D = self.W, self.D = fr.W, fr.D
        self.Ix, self.Iz = W / 2 - C.SHOP_WALL, D / 2 - C.SHOP_WALL
        self.Ex, self.Ez = W / 2 - 0.02, D / 2 - 0.02
        core = buildings.Core(W, D)
        for name in ("SX0", "XA", "XB", "XC", "Z1A", "Z1B", "Z2A", "Z2B", "EX0", "EX1", "car", "door"):
            setattr(self, name, getattr(core, name))
        self.HX0, self.HZ0, self.HX1, self.HZ1 = core.hole
        self.levels = buildings.levels(rec.h, rec.fh)
        self.floors = len(self.levels)
        self.has_shaft = buildings.has_shaft(rec) and self.floors >= 3
        reserved = [(self.SX0 - 2.0, self.Z1A - 5.0, self.XC + 1.0, self.Z2B + 1.2)]
        self.holes = [core.hole]
        if self.has_shaft:                                     # shaft and the space in front of its door
            reserved.append((self.EX0 - 0.4, self.Z1A - 4.0, self.EX1, self.Z2B + 1.2))
            self.holes.append(self.car)
        self.RESERVED = tuple(reserved)
        self.COLUMNS = []
        self.roof = self.floors + 1
        self.height = rec.h
        self.n_storeys = self.floors if self.floors > 1 else 0
        self.name = L("{district}大樓 #{n:03d}", district=districts.NAMES[rec.district], n=int(rec.seed) % 1000)
        self.hatch = self.bounds(*core.hole)
        self.box = (rec.lx, rec.lz, rec.w, rec.d)              # identifies the base box in the shader
        self.door_zones = defaultdict(list)                    # floor -> world rects kept clear (bridge doors)
        for door in self.doors:
            self.door_zones[self.floor_at(door[1] + 0.01)].append(approach_rect(rec, door))

    def bounds(self, x0, z0, x1, z1):
        D = self.D
        return self.fr.bounds(x0, z0 + D / 2, x1, z1 + D / 2)

    def level_y(self, k):
        if k <= 1:
            return 0.0
        if k >= self.roof:
            return self.height
        return self.levels[k - 1]

    def floor_at(self, y):
        if y >= self.height - 0.5:
            return self.roof
        k = 1
        for i, ly in enumerate(self.levels):
            if y >= ly - 0.5:
                k = i + 1
        return k

    def is_floor_level(self, y):
        return True

    def label(self, k):
        if k <= 1:
            return tr("1F 商店")
        if k >= self.roof:
            return tr("RF 屋頂")
        return f"{k}F"

    def storey(self, u):
        return self.levels[u], (self.levels[u + 1] if u + 1 < self.floors else self.height)

    def storeys_near(self, y):
        return [u for u in range(self.n_storeys) if self.storey(u)[1] >= y - 8.0 and self.storey(u)[0] <= y + 16.0]

    def slab_bottom(self, k):
        L = self.level_y(k)
        return L - (0.1 if k == 2 else C.SLAB)               # 2F's slab sits right on the shop ceiling

    def theme(self, k):
        themes, cum = _BUILDING_THEMES[self.rec.district]
        return floors.pick_theme(floors._hash(k * 31 + int(self.rec.seed * 1000)), cum, themes)

    def floor_seed(self, k):
        return (int(self.rec.seed * 1000) * 7919 + k * 104729) & 0xFFFFFFFF

    def crowd_seed(self, k):
        return (int(self.rec.seed * 1000) * 15485863 + k * 7) & 0xFFFFFFFF

    def shell(self):
        """Hollow replacement for the solid upper-floors collider: four walls and the roof around the hatch."""
        r, T, S = self.rec, C.SHOP_WALL, C.SHOP_H
        x0, x1, z0, z1, h = r.lx - r.w / 2, r.lx + r.w / 2, r.lz - r.d / 2, r.lz + r.d / 2, r.h
        hx0, hz0, hx1, hz1 = self.hatch
        r0 = h - 0.5
        walls = [(x0, S, z0, x0 + T, h, z1), (x1 - T, S, z0, x1, h, z1), (x0, S, z0, x1, h, z0 + T),
                 (x0, S, z1 - T, x1, h, z1)]
        for door in self.doors:                                # skybridge doorways
            walls = [p for w in walls for p in _punch(w, door)]
        return walls + [(x0, r0, z0, hx0, h, z1), (hx1, r0, z0, x1, h, z1), (hx0, r0, z0, hx1, h, hz0),
                        (hx0, r0, hz1, hx1, h, z1)]


def _punch(w, d):
    """Wall box w minus a doorway box d that goes through it (both (x0, y0, z0, x1, y1, z1))."""
    if not overlaps(w, *d):
        return [w]
    ax = 0 if (w[3] - w[0]) > (w[5] - w[2]) else 2            # the wall runs along x or z
    out = []
    if d[ax] > w[ax]:
        p = list(w)
        p[ax + 3] = d[ax]
        out.append(p)
    if d[ax + 3] < w[ax + 3]:
        p = list(w)
        p[ax] = d[ax + 3]
        out.append(p)
    mid = list(w)
    mid[ax], mid[ax + 3] = max(w[ax], d[ax]), min(w[ax + 3], d[ax + 3])
    if d[1] > w[1]:
        p = list(mid)
        p[4] = d[1]
        out.append(p)
    if d[4] < w[4]:
        p = list(mid)
        p[1] = d[4]
        out.append(p)
    return [tuple(p) for p in out]


_TOWER_LAYOUTS = {}


def tower_layout(t):
    if t.index not in _TOWER_LAYOUTS:
        _TOWER_LAYOUTS[t.index] = TowerLayout(t)
    return _TOWER_LAYOUTS[t.index]


class _Parts:
    def __init__(self, g):
        self.g = g
        self.boxes, self.cols = [], []

    def add(self, x0, y0, z0, x1, y1, z1, kind, hue=0.0, extra=0.0, collide=False, seed=0.0):
        """Box in layout-local x/z."""
        x0, z0, x1, z1 = self.g.bounds(x0, z0, x1, z1)
        self.boxes.append(box_bounds(x0, y0, z0, x1, y1, z1, kind, hue, extra, seed))
        if collide:
            self.cols.append((x0, y0, z0, x1, y1, z1))


def _free(g, x0, z0, x1, z1, margin=0.4, zones=()):
    """Is the local rect clear of the walls, reserved areas, columns and the world-space `zones`?"""
    if x0 < -g.Ix + 1.0 or z0 < -g.Iz + 1.0 or x1 > g.Ix - 1.0 or z1 > g.Iz - 1.0:
        return False
    if zones:
        wx0, wz0, wx1, wz1 = g.bounds(x0, z0, x1, z1)
        if any(wx1 + margin > a[0] and wx0 - margin < a[2] and wz1 + margin > a[1] and wz0 - margin < a[3]
               for a in zones):
            return False
    for a0, b0, a1, b1 in g.RESERVED:
        if x1 + margin > a0 and x0 - margin < a1 and z1 + margin > b0 and z0 - margin < b1:
            return False
    for cx, cz in g.COLUMNS:
        if x1 + margin > cx - 0.6 and x0 - margin < cx + 0.6 and z1 + margin > cz - 0.6 and z0 - margin < cz + 0.6:
            return False
    return True


def _cut(rect, holes):
    """Rectangle (x0, z0, x1, z1) minus axis-aligned holes, as a few rectangles."""
    x0, z0, x1, z1 = rect
    xs = sorted({x0, x1} | {v for h in holes for v in (h[0], h[2]) if x0 < v < x1})
    zs = sorted({z0, z1} | {v for h in holes for v in (h[1], h[3]) if z0 < v < z1})
    out = []
    for za, zb in zip(zs, zs[1:]):
        row = []
        for xa, xb in zip(xs, xs[1:]):
            cx, cz = (xa + xb) / 2, (za + zb) / 2
            if any(h[0] < cx < h[2] and h[1] < cz < h[3] for h in holes):
                continue
            if row and row[-1][2] == xa:
                row[-1][2] = xb                                 # merge along x
            else:
                row.append([xa, za, xb, zb])
        for r in row:                                           # merge with an identical span of the band above
            prev = next((o for o in out if o[0] == r[0] and o[2] == r[2] and o[3] == r[1]), None)
            if prev:
                prev[3] = r[3]
            else:
                out.append(r)
    return [tuple(r) for r in out]


def build_slab(g, k):
    """Floor slab of floor k (2..N) with the stair opening (and an elevator shaft) cut out.

    It reaches (almost) the facade so there is no gap to peek through at the windows, and
    its underside is the ceiling of floor k-1, so it takes that floor's lighting.
    """
    p = _Parts(g)
    L = g.level_y(k)
    hue, light = THEME_LIGHT[g.theme(k - 1)]
    y0 = g.slab_bottom(k)
    Ex, Ez = g.Ex, g.Ez
    if g.has_elevator:                                          # megatowers: the original four pieces
        pieces = ((-Ex, -Ez, g.HX0, Ez), (g.HX1, -Ez, Ex, Ez), (g.HX0, -Ez, g.HX1, g.HZ0), (g.HX0, g.HZ1, g.HX1, Ez))
    else:
        pieces = _cut((-Ex, -Ez, Ex, Ez), g.holes)
    for b in pieces:
        p.add(b[0], y0, b[1], b[2], L, b[3], C.K_SLAB, hue, light, collide=True)
    return p


def build_storey(g, u):
    """Stair unit u (one storey): flight up, mid landing, flight back, enclosure walls."""
    SX0, XA, XB, XC, Z1A, Z1B, Z2A, Z2B = g.SX0, g.XA, g.XB, g.XC, g.Z1A, g.Z1B, g.Z2A, g.Z2B
    p = _Parts(g)
    L, top = g.storey(u)
    H = top - L
    steps = buildings.storey_steps(H)
    rise = H / (2 * steps)
    tread = C.STAIR_RUN / steps
    for i in range(1, steps + 1):
        p.add(XA + tread * (i - 1), L + rise * i - 0.3, Z1A, XA + tread * i, L + rise * i, Z1B,
              C.K_DOOR, 0.5, collide=True)
        y = L + H / 2 + rise * i
        p.add(XB - tread * i, y - 0.3, Z2A, XB - tread * (i - 1), y, Z2B, C.K_DOOR, 0.5, collide=True)
    half = L + H / 2
    p.add(XB, half - 0.3, Z1A, XC, half, Z2B, C.K_PANEL, 0.5, collide=True)          # mid landing
    p.add(XA, L, Z1B, XB, top, Z2A, C.K_PANEL, 0.5, collide=True)                    # divider
    if not g.is_floor_level(top) and top < g.height:                                  # lobby mid-height landings
        p.add(SX0, top - 0.3, Z1A, XA, top, Z2B, C.K_PANEL, 0.5, collide=True)
    # enclosure walls
    zs, zn = Z1A - WT, Z2B + WT
    p.add(SX0 - WT, L, zs, SX0, top, zn, C.K_PANEL, 0.5, collide=True)               # west
    p.add(XC, L, zs, XC + WT, top, zn, C.K_PANEL, 0.5, collide=True)                 # east
    p.add(SX0 - WT, L, Z2B, XC + WT, top, zn, C.K_PANEL, 0.5, collide=True)          # north
    if g.is_floor_level(L):                                                           # south wall with door
        dh = L + C.STAIR_DOOR_H
        p.add(XA, L, zs, XC + WT, top, Z1A, C.K_PANEL, 0.5, collide=True)
        p.add(SX0 - WT, dh, zs, XA, top, Z1A, C.K_PANEL, 0.5, collide=True)
        p.add(SX0 + 0.2, dh + 0.1, zs - 0.12, XA - 0.2, dh + 0.35, zs, C.K_EMISSIVE, 0.36, 3.0)   # exit sign
        p.add(SX0 - 0.05, L, zs - 0.06, SX0, dh, zs, C.K_EMISSIVE, 0.36, 2.0)                       # door frame
        p.add(XA, L, zs - 0.06, XA + 0.05, dh, zs, C.K_EMISSIVE, 0.36, 2.0)
    else:
        p.add(SX0 - WT, L, zs, XC + WT, top, Z1A, C.K_PANEL, 0.5, collide=True)
    # stair lighting
    ly = L + H - 0.7
    p.add(XA, ly, Z2B - 0.06, XB, ly + 0.1, Z2B, C.K_EMISSIVE, -1.0, 1.6)
    p.add(XA, ly, Z1A, XB, ly + 0.1, Z1A + 0.06, C.K_EMISSIVE, -1.0, 1.6)
    if not g.has_elevator and g.has_shaft:                      # elevator shaft west of the stairs
        E0, E1 = g.EX0, g.EX1
        d0, d1 = g.door
        dh = L + buildings.SHAFT_DOOR_H
        p.add(E0, L, zs, E0 + WT, top, zn, C.K_PANEL, 0.5, collide=True)                  # west
        p.add(E0, L, Z2B, E1, top, zn, C.K_PANEL, 0.5, collide=True)                      # north
        p.add(E0, L, zs, d0, top, Z1A, C.K_PANEL, 0.5, collide=True)                      # south, door
        p.add(d1, L, zs, E1, top, Z1A, C.K_PANEL, 0.5, collide=True)
        p.add(d0, dh, zs, d1, top, Z1A, C.K_PANEL, 0.5, collide=True)
        p.add(d0 - 0.06, L, zs - 0.06, d0, dh, zs, C.K_EMISSIVE, 0.5, 2.0)              # door frame
        p.add(d1, L, zs - 0.06, d1 + 0.06, dh, zs, C.K_EMISSIVE, 0.5, 2.0)
        p.add(d0 - 0.06, dh, zs - 0.06, d1 + 0.06, dh + 0.06, zs, C.K_EMISSIVE, 0.5, 2.0)
    return p


def build_floor(g, k):
    """Columns and themed furniture of floor k (2..N)."""
    Ix, Iz = g.Ix, g.Iz
    zones = getattr(g, "door_zones", {}).get(k, ())
    free = lambda *a: _free(g, *a, zones=zones)
    p = _Parts(g)
    L = g.level_y(k)
    ceil = g.level_y(k + 1) - C.SLAB
    rng = np.random.default_rng(g.floor_seed(k))
    th = g.theme(k)
    for cx, cz in g.COLUMNS:
        p.add(cx - 0.6, L, cz - 0.6, cx + 0.6, ceil, cz + 0.6, C.K_PANEL, 0.5, collide=True)
    if th == 0:                                                      # offices
        for gx in np.arange(-Ix + 5.5, Ix - 7.5, 7.5):
            for gz in np.arange(-Iz + 6.5, Iz - 4.5, 6.0):
                if not free(gx - 0.9, gz - 1.3, gx + 0.9, gz + 0.5):
                    continue
                p.add(gx - 0.9, L, gz - 0.45, gx + 0.9, L + 0.75, gz + 0.45, C.K_PANEL, 0.55, collide=True)
                p.add(gx - 0.35, L + 0.75, gz + 0.25, gx + 0.35, L + 1.15, gz + 0.3, C.K_EMISSIVE,
                      float(rng.choice((0.5, 0.55, 0.83))), 1.8)
                p.add(gx - 0.28, L, gz - 1.15, gx + 0.28, L + 0.5, gz - 0.6, C.K_DOOR, 0.55, collide=True)
    elif th == 1:                                                    # server farm
        for x in np.arange(-Ix + 5.5, Ix - 13.5, 4.0):
            for z0, z1 in ((-Iz + 5.5, -7.0), (7.0, Iz - 5.5)):
                if z1 - z0 > 2.0 and free(x, z0, x + 1.0, z1, 0.2):
                    p.add(x, L, z0, x + 1.0, L + 2.4, z1, C.K_SIGN, float(rng.choice((0.5, 0.58, 0.38))),
                          collide=True, seed=float(rng.uniform(0, 1000)))
                    p.add(x + 0.3, ceil - 0.25, z0, x + 0.7, ceil - 0.15, z1, C.K_EMISSIVE, 0.58, 1.2)
    elif th == 2:                                                    # hydroponic garden
        for x in np.arange(-Ix + 5.5, Ix - 13.5, 4.5):
            for z0, z1 in ((-Iz + 5.5, -6.0), (6.0, Iz - 5.5)):
                if z1 - z0 > 2.0 and free(x, z0, x + 1.4, z1, 0.2):
                    p.add(x, L, z0, x + 1.4, L + 0.6, z1, C.K_PANEL, 0.33, collide=True)
                    p.add(x + 0.1, L + 0.6, z0 + 0.1, x + 1.3, L + 1.0, z1 - 0.1, C.K_EMISSIVE, 0.33, 0.45)
                    p.add(x + 0.4, ceil - 0.6, z0, x + 1.0, ceil - 0.5, z1, C.K_EMISSIVE, 0.88, 2.5)
    elif th == 3:                                                    # lounge / club
        n = min(3, int((min(Ix, Iz) - 3.0) // 2))
        dc = max(-8.0, -min(Ix, Iz) + 1.0 + 2 * n)                   # dance floor center (Nexus: -8)
        for i in range(-n, n):
            for j in range(-n, n):
                x, z = dc + i * 2.0, dc + j * 2.0
                p.add(x + 0.05, L, z + 0.05, x + 1.95, L + 0.03, z + 1.95, C.K_EMISSIVE,
                      float(rng.choice(C.NEON_HUES)), 0.9)
        bz = min(15.0, Iz - 4.0)
        p.add(-Ix + 0.5, L, -bz, -Ix + 1.5, L + 1.1, bz, C.K_PANEL, 0.83, collide=True)          # bar
        p.add(-Ix + 0.45, L + 1.1, -bz - 0.05, -Ix + 1.55, L + 1.16, bz + 0.05, C.K_EMISSIVE, 0.83, 2.5)
        for _ in range(14):
            x, z = rng.uniform(-Ix + 5.5, Ix - 9.5), rng.uniform(-Iz + 5.5, Iz - 5.5)
            if not free(x - 1.2, z - 1.2, x + 1.2, z + 1.6) or (abs(x + 2) < 9 and abs(z + 2) < 9):
                continue
            p.add(x - 1.1, L, z - 0.45, x + 1.1, L + 0.45, z + 0.45, C.K_PANEL, 0.83, collide=True)
            p.add(x - 1.1, L, z - 0.7, x + 1.1, L + 0.9, z - 0.45, C.K_PANEL, 0.83, collide=True)
            p.add(x - 0.4, L, z + 0.8, x + 0.4, L + 0.45, z + 1.6, C.K_PANEL, 0.5, collide=True)
            p.add(x - 0.06, L + 0.45, z + 1.14, x + 0.06, L + 0.6, z + 1.26, C.K_EMISSIVE, 0.12, 4.0)
    elif th == 4:                                                    # under construction / storage
        for _ in range(40):
            s = rng.uniform(1.0, 2.2)
            x, z = rng.uniform(-Ix + 4.5, Ix - 6.5), rng.uniform(-Iz + 4.5, Iz - 6.5)
            if free(x, z, x + s, z + s):
                h = s * rng.uniform(0.6, 1.0)
                p.add(x, L, z, x + s, L + h, z + s, C.K_PANEL, 0.1, collide=True)
        for _ in range(10):
            x, z = rng.uniform(-Ix + 5.5, Ix - 9.5), rng.uniform(-Iz + 5.5, Iz - 5.5)
            if free(x - 0.3, z - 0.3, x + 0.3, z + 0.3):
                p.add(x - 0.05, L, z - 0.05, x + 0.05, L + 2.4, z + 0.05, C.K_PANEL, 0.1, collide=True)
                p.add(x - 0.25, L + 2.4, z - 0.25, x + 0.25, L + 2.7, z + 0.25, C.K_EMISSIVE, 0.11, 4.0)
        if Ix - 15.5 > -Ix + 5.5:
            for z in (-6.0, 6.0):
                p.add(-Ix + 5.5, L, z - 0.08, Ix - 15.5, L + 0.02, z + 0.08, C.K_EMISSIVE, 0.13, 1.5)
    elif th == floors.OBSERVATORY:
        _observatory(p, g, L, ceil, rng, free)
    elif th == floors.SKY_GARDEN:
        _sky_garden(p, g, L, ceil, rng, free)
    elif th == floors.SKY_BAR:
        _sky_bar(p, g, L, ceil, rng, free)
    else:                                                            # apartments: bed, sofa, table, screen
        for gx in np.arange(-Ix + 3.0, Ix - 3.0, 7.0):
            for gz in np.arange(-Iz + 3.0, Iz - 3.0, 7.0):
                if not free(gx - 2.6, gz - 2.6, gx + 2.6, gz + 2.6, 0.2):
                    continue
                hue = float(rng.choice(C.NEON_HUES))
                p.add(gx - 2.4, L, gz - 2.4, gx - 0.4, L + 0.5, gz - 1.0, C.K_PANEL, 0.6, collide=True)      # bed
                p.add(gx - 2.4, L + 0.5, gz - 2.4, gx - 1.8, L + 0.65, gz - 1.0, C.K_EMISSIVE, hue, 0.8)
                p.add(gx + 0.4, L, gz + 1.6, gx + 2.4, L + 0.45, gz + 2.4, C.K_PANEL, hue, collide=True)     # sofa
                p.add(gx + 0.4, L, gz + 2.2, gx + 2.4, L + 0.85, gz + 2.4, C.K_PANEL, hue, collide=True)
                p.add(gx + 0.9, L, gz + 0.2, gx + 1.9, L + 0.4, gz + 0.9, C.K_PANEL, 0.5, collide=True)      # table
                p.add(gx + 0.5, L + 0.6, gz - 2.45, gx + 2.3, L + 1.6, gz - 2.35, C.K_EMISSIVE,               # screen
                      float(rng.choice((0.5, 0.55, 0.83))), 1.6)
    return p


def _along_walls(I, inset, step):
    """Points (x, z, facing) along the four walls of a square interior, `inset` from them."""
    out = []
    for t in np.arange(-I + 4.0, I - 3.9, step):
        out += [(t, -I + inset, (0, -1)), (t, I - inset, (0, 1)), (-I + inset, t, (-1, 0)), (I - inset, t, (1, 0))]
    return out


def _observatory(p, g, L, ceil, rng, free):
    """Observation deck: coin telescopes and benches facing every window, glowing guide rings."""
    I = g.Ix
    for x, z, (fx, fz) in _along_walls(I, 1.4, 7.0):                 # telescopes at the glass
        if not free(x - 0.4, z - 0.4, x + 0.4, z + 0.4, 0.2):
            continue
        p.add(x - 0.1, L, z - 0.1, x + 0.1, L + 1.15, z + 0.1, C.K_PANEL, 0.5, collide=True)
        hx, hz = (0.45, 0.14) if fx else (0.14, 0.45)
        p.add(x - hx + fx * 0.15, L + 1.15, z - hz + fz * 0.15, x + hx + fx * 0.15, L + 1.4, z + hz + fz * 0.15,
              C.K_PANEL, 0.55)
        p.add(x + fx * 0.6 - 0.06, L + 1.22, z + fz * 0.6 - 0.06, x + fx * 0.6 + 0.06, L + 1.33,
              z + fz * 0.6 + 0.06, C.K_EMISSIVE, 0.5, 3.0)
    for x, z, (fx, fz) in _along_walls(I, 4.5, 9.0):                 # benches facing out
        bx, bz = (0.3, 1.0) if fx else (1.0, 0.3)
        if free(x - bx, z - bz, x + bx, z + bz, 0.3):
            p.add(x - bx, L, z - bz, x + bx, L + 0.45, z + bz, C.K_PANEL, 0.6, collide=True)
            p.add(x - bx, L + 0.45, z - bz, x + bx, L + 0.5, z + bz, C.K_EMISSIVE, 0.55, 1.0)
    for r, hue in ((I - 2.6, 0.5), (I - 6.5, 0.55)):                 # guide rings in the floor
        for x0, z0, x1, z1 in ((-r, -r, r, -r + 0.12), (-r, r - 0.12, r, r), (-r, -r, -r + 0.12, r), (r - 0.12, -r, r, r)):
            p.add(x0, L, z0, x1, L + 0.02, z1, C.K_EMISSIVE, hue, 1.4)
    for cx, cz in ((-I / 3, -I / 3), (-I / 3, I / 3)):                # info pillars (scrolling glyph signs)
        if free(cx - 0.8, cz - 0.8, cx + 0.8, cz + 0.8):
            p.add(cx - 0.6, L, cz - 0.6, cx + 0.6, L + 2.6, cz + 0.6, C.K_SIGN, 0.5, collide=True,
                  seed=float(rng.uniform(0, 1000)))
    p.add(-I + 2.0, ceil - 0.1, -0.15, I - 2.0, ceil, 0.15, C.K_EMISSIVE, -1.0, 1.4)


def _tree(p, x, z, L, top, hue, rng):
    """Garden tree: trunk, dark foliage tiers with glowing rims (as in the parks)."""
    th = min(2.4, top - L - 2.0)
    p.add(x - 0.18, L + 0.6, z - 0.18, x + 0.18, L + 0.6 + th, z + 0.18, C.K_PANEL, 0.33, collide=True)
    y = L + 0.6 + th
    for s in (2.2, 1.4):
        hh = min(s * 0.5, max(top - 0.2 - y, 0.1))
        p.add(x - s / 2, y, z - s / 2, x + s / 2, y + hh, z + s / 2, C.K_PANEL, hue)
        p.add(x - s / 2 - 0.04, y, z - s / 2 - 0.04, x + s / 2 + 0.04, y + 0.07, z + s / 2 + 0.04, C.K_EMISSIVE,
              hue, float(rng.uniform(1.2, 2.0)))
        y += hh


def _sky_garden(p, g, L, ceil, rng, free):
    """Sky garden: lawn, planters with trees, a glowing water channel and benches along the paths."""
    I = g.Ix
    p.add(-I + 1.0, L, -I + 1.0, I - 14.0, L + 0.02, I - 1.0, C.K_EMISSIVE, 0.33, 0.12)  # lawn (clear of the stairs)
    p.add(-I + 2.0, L, -0.8, I - 14.0, L + 0.04, 0.8, C.K_EMISSIVE, 0.52, 0.9)          # water channel
    for x in np.arange(-I + 5.0, I - 13.0, 7.0):
        for z in np.arange(-I + 5.0, I - 4.0, 7.0):
            if abs(z) < 3.0 or not free(x - 1.4, z - 1.4, x + 1.4, z + 1.4, 0.4):
                continue
            hue = float(rng.choice((0.33, 0.45, 0.9, 0.83)))
            p.add(x - 1.3, L, z - 1.3, x + 1.3, L + 0.6, z + 1.3, C.K_PANEL, 0.33, collide=True)
            p.add(x - 1.25, L + 0.6, z - 1.25, x + 1.25, L + 0.66, z + 1.25, C.K_EMISSIVE, 0.33, 0.6)
            if rng.random() < 0.6:
                _tree(p, x, z, L, ceil, hue, rng)
            else:
                for dx in (-0.6, 0.0, 0.6):                           # flower bed
                    p.add(x + dx - 0.15, L + 0.66, z - 0.8, x + dx + 0.15, L + 0.9, z + 0.8, C.K_EMISSIVE, hue, 1.6)
    for x in np.arange(-I + 6.0, I - 14.0, 9.0):                      # benches by the channel
        for s in (-1, 1):
            z = s * 2.2
            if free(x - 1.0, z - 0.3, x + 1.0, z + 0.3, 0.2):
                p.add(x - 1.0, L, z - 0.3, x + 1.0, L + 0.45, z + 0.3, C.K_PANEL, 0.08, collide=True)


def _sky_bar(p, g, L, ceil, rng, free):
    """Sky bar: a long bar, stools, sofa islands, a DJ booth and neon strips across the ceiling."""
    I = g.Ix
    bz = min(18.0, I - 4.0)
    p.add(-I + 1.0, L, -bz, -I + 2.2, L + 1.1, bz, C.K_PANEL, 0.83, collide=True)            # the bar
    p.add(-I + 0.95, L + 1.1, -bz - 0.05, -I + 2.25, L + 1.16, bz + 0.05, C.K_EMISSIVE, 0.83, 3.0)
    for y in (1.5, 2.1, 2.7):                                         # bottle shelves on the wall
        p.add(-I + 0.1, L + y, -bz, -I + 0.4, L + y + 0.06, bz, C.K_EMISSIVE, float(rng.choice(C.NEON_HUES)), 2.0)
    for z in np.arange(-bz + 0.8, bz - 0.5, 1.4):                    # stools
        p.add(-I + 2.6, L, z - 0.2, -I + 3.0, L + 0.8, z + 0.2, C.K_DOOR, 0.83, collide=True)
    dj = (-I / 4, -I + 4.0)                                           # DJ booth by the north glass
    if free(dj[0] - 2.0, dj[1] - 1.0, dj[0] + 2.0, dj[1] + 1.0):
        p.add(dj[0] - 2.0, L, dj[1] - 0.6, dj[0] + 2.0, L + 1.1, dj[1] + 0.6, C.K_SIGN, 0.92, collide=True,
              seed=float(rng.uniform(0, 1000)))
        p.add(dj[0] - 2.5, L, dj[1] + 1.2, dj[0] + 2.5, L + 0.03, dj[1] + 6.2, C.K_EMISSIVE,
              float(rng.choice(C.NEON_HUES)), 0.9)
    for _ in range(18):                                               # sofa islands with a table
        x, z = rng.uniform(-I + 7.0, I - 10.0), rng.uniform(-I + 6.0, I - 6.0)
        if not free(x - 1.6, z - 1.6, x + 1.6, z + 1.6, 0.6):
            continue
        hue = float(rng.choice(C.NEON_HUES))
        p.add(x - 1.4, L, z - 1.4, x + 1.4, L + 0.45, z - 0.8, C.K_PANEL, hue, collide=True)
        p.add(x - 1.4, L, z + 0.8, x + 1.4, L + 0.45, z + 1.4, C.K_PANEL, hue, collide=True)
        p.add(x - 0.5, L, z - 0.4, x + 0.5, L + 0.4, z + 0.4, C.K_PANEL, 0.5, collide=True)
        p.add(x - 0.08, L + 0.4, z - 0.08, x + 0.08, L + 0.55, z + 0.08, C.K_EMISSIVE, 0.12, 4.0)
    for k, x in enumerate(np.arange(-I + 4.0, I - 2.0, 4.0)):         # neon ceiling strips
        p.add(x - 0.06, ceil - 0.08, -I + 2.0, x + 0.06, ceil, I - 2.0, C.K_EMISSIVE, C.NEON_HUES[k % 7], 2.2)


class Interiors:
    CACHE = 48

    def __init__(self):
        self.slabs, self.storeys, self.floors = {}, {}, {}
        self.blayouts = {}
        self.shafts = {}                        # building index -> its ShaftElevator (kept while away)
        self.key = None
        self.static = ([], [])
        self._clear()

    def _clear(self):
        self.key = None
        self.elevator = None                    # the shaft elevator of the city building we are in
        self.layout = None                      # layout the interior is built for
        self.tower = None                       # its tower (megatowers only)
        self.building = None                    # its shop record index (city buildings only)
        self.floor = None                       # floor number the interior is centred on
        self.furnished = ()                     # floors whose furniture is currently built
        self.boxes = np.zeros((0, BOX_FLOATS), "f4")
        self.colliders = []
        self.open_range = (-1e9, -1e9)
        self.open_center = (1e9, 1e9)           # tower whose shell is cut open
        self.bldg = (1e9, 1e9, 0.0, 0.0)        # city building whose windows are open (cx, cz, w, d)
        self.hatch = (0.0, 0.0, 0.0, 0.0)       # its roof hatch (x0, z0, x1, z1)
        self.doors = []                         # its skybridge doorways (x0, y0, z0, x1, y1, z1)

    def dry_boxes(self):
        """Volume kept free of rain: the upper floors of the city building the player is in."""
        if self.building is None:
            return []
        r = self.layout.rec
        return [(r.lx - r.w / 2, C.SHOP_H - 0.2, r.lz - r.d / 2, r.lx + r.w / 2, r.h, r.lz + r.d / 2)]

    def floor_parts(self, k):
        """Cached furniture/columns of floor k of the current structure (boxes and colliders)."""
        return self._get(self.floors, (self.layout, k), build_floor)

    @staticmethod
    def _get(cache, key, build):
        if key not in cache:
            if len(cache) > Interiors.CACHE:
                cache.pop(next(iter(cache)))
            cache[key] = build(*key)
        return cache[key]

    def building_layout(self, rec, index, doors=()):
        if index not in self.blayouts:
            if len(self.blayouts) > 8:
                self.blayouts.pop(next(iter(self.blayouts)))
            self.blayouts[index] = BuildingLayout(rec, index, doors)
        return self.blayouts[index]

    def update(self, pos, elevators, car, shops):
        """elevators: one per tower (floors.TOWERS order); car: the elevator the player is in, or None;
        shops: the ShopManager (to find the city building the player is in)."""
        g, y, active = None, pos[1], True
        if car is not None and getattr(car, "tower", None) is None:
            car = None                          # a city building's own elevator: found below by position
        if car is not None:
            g, active, y = tower_layout(car.tower), not car.moving, car.y
        else:
            t = floors.tower_at(pos)
            if t is not None:
                g = tower_layout(t)
            else:
                bi = shops.building_at(pos)
                if bi is not None:
                    g = self.building_layout(shops.records[bi], bi, shops.bridge_doors.get(bi, ()))
                else:
                    t = floors.nearest_tower(pos)
                    g, active = tower_layout(t), pos[1] < 14.0 and t.distance(pos) < 80.0
        if not active or g.n_storeys == 0:
            self._clear()
            return

        self.layout = g
        self.tower = g.t if g.has_elevator else None
        self.building = None if g.has_elevator else g.index
        self.elevator = None
        if not g.has_elevator and g.has_shaft:
            if g.index not in self.shafts:
                self.shafts[g.index] = ShaftElevator(g)
            self.elevator = self.shafts[g.index]
        k = g.floor_at(y)
        self.floor = k
        storeys = [u for u in g.storeys_near(y) if g.has_elevator or u > 0]     # a shop builds its own unit 0
        regular = lambda ks: tuple(f for f in ks if 2 <= f <= g.floors)
        furnished = regular(range(k - 1, k + 2))
        slabs = regular(range(k - 1, k + 3))
        self.furnished = furnished
        key = (g.key, tuple(storeys), furnished, slabs)
        if key != self.key:
            self.key = key
            parts = ([self._get(self.storeys, (g, s), build_storey) for s in storeys]
                     + [self._get(self.slabs, (g, f), build_slab) for f in slabs]
                     + [self.floor_parts(f) for f in furnished])
            boxes = [b for p in parts for b in p.boxes]
            cols = [c for p in parts for c in p.cols]
            if not g.has_elevator:
                cols += g.shell()
                for b in buildings.hatch_frame_boxes(g.hatch, g.height):
                    boxes.append(box_bounds(*b, C.K_EMISSIVE, 0.13, 2.5))
            self.static = (boxes, cols)
        boxes, cols = self.static
        if g.has_elevator:                      # landing doors follow the elevator every frame
            elevator = elevators[g.t.index]
            land = _Parts(g)
            for f in furnished:
                self._landing(land, g.t, f, elevator.landing_door(f), elevator.level == f and not elevator.moving)
            boxes, cols = boxes + land.boxes, cols + land.cols
            self.open_center = (g.t.cx, g.t.cz)
            self.bldg = (1e9, 1e9, 0.0, 0.0)
        else:
            if self.elevator is not None:       # shaft landing doors follow the car
                el = self.elevator
                land = _Parts(g)
                for f in range(max(1, k - 1), min(g.floors, k + 1) + 1):
                    self._shaft_landing(land, g, f, el.landing_door(f), el.level == f and not el.moving)
                boxes, cols = boxes + land.boxes, cols + land.cols
            self.open_center = (1e9, 1e9)
            self.bldg = g.box
            self.hatch = g.hatch
            self.doors = g.doors
        self.boxes = np.array(boxes, "f4").reshape(-1, BOX_FLOATS)
        self.colliders = cols
        lo = g.level_y(max(1, k - 1))
        hi = g.level_y(min(g.roof, k + 2))
        self.open_range = (lo - 0.5, hi + 0.5)

    @staticmethod
    def _shaft_landing(p, g, k, d, here):
        """Sliding landing doors in the shaft's front wall on floor k of a city building, plus call light."""
        L = g.level_y(k)
        d0, d1 = g.door
        dc, dh = (d0 + d1) / 2, (d1 - d0) / 2
        DH = buildings.SHAFT_DOOR_H
        z0, z1 = g.Z1A - 0.15, g.Z1A - 0.05
        p.add(dc - dh - d * dh, L, z0, dc - d * dh, L + DH, z1, C.K_DOOR, 0.5, collide=True)
        p.add(dc + d * dh, L, z0, dc + dh + d * dh, L + DH, z1, C.K_DOOR, 0.5, collide=True)
        p.add(d1 + 0.15, L + 1.2, g.Z1A - WT - 0.06, d1 + 0.35, L + 1.5, g.Z1A - WT, C.K_EMISSIVE,
              0.36 if here else 0.1, 3.0)

    @staticmethod
    def _landing(p, t, k, d, here):
        """Shaft doors, lintel, neon frame and call light on floor k's east wall."""
        I = t.inner
        L = t.level_y(k)
        ed, dh = C.ELEV_DOOR_HALF, C.ELEV_DOOR_HEIGHT
        x0, x1 = I - 0.12, I
        p.add(x0, L, -ed - d * ed, x1, L + dh, -d * ed, C.K_DOOR, 0.5, collide=True)
        p.add(x0, L, d * ed, x1, L + dh, ed + d * ed, C.K_DOOR, 0.5, collide=True)
        p.cols.append((t.cx + I, L + dh, t.cz - ed, t.cx + t.half, L + C.FLOOR_HEIGHT, t.cz + ed))   # lintel
        fx = I - 0.2
        p.add(fx, L, -ed - 0.3, I, L + dh + 0.3, -ed, C.K_EMISSIVE, 0.5, 3.0)
        p.add(fx, L, ed, I, L + dh + 0.3, ed + 0.3, C.K_EMISSIVE, 0.5, 3.0)
        p.add(fx, L + dh, -ed - 0.3, I, L + dh + 0.3, ed + 0.3, C.K_EMISSIVE, 0.5, 3.0)
        p.add(I - 0.1, L + 1.2, ed + 0.6, I, L + 1.5, ed + 0.8, C.K_EMISSIVE, 0.36 if here else 0.1, 3.0)
