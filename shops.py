"""Ground-floor shops: wall colliders with a door gap, and interiors furnished near the player.

Every city building's lowest SHOP_H metres is a shop. The building box itself is drawn
hollow by the shader (door hole + interior shading of the faces seen from inside); this
module only adds the furniture, which exists solely within SHOP_NEAR of the player.
"""
import math
from collections import defaultdict, namedtuple

import numpy as np

import buildings
import config as C
import skybridges
from buildings import Core, Frame
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS
from i18n import L
from tower_interior import BuildingLayout, build_storey

# district: districts.py index; top: highest point (tiers, antennas); fh: upper storey height;
# upper_col: index of the solid upper-floors collider in the city collider list
ShopRecord = namedtuple("ShopRecord", "lx lz w d h face kind seed name district top fh upper_col")


def shop_name(kind, seed):
    return L("{shop} #{n:03d}", shop=C.SHOP_TYPES[kind][0], n=int(seed) % 1000)


def shell_colliders(lx, lz, w, d, h, face):
    """Upper floors as one box, plus four 0.3 m ground-floor walls with a door in `face`."""
    T, S, dh, dy = C.SHOP_WALL, C.SHOP_H, C.SHOP_DOOR_HALF, C.SHOP_DOOR_H
    x0, x1, z0, z1 = lx - w / 2, lx + w / 2, lz - d / 2, lz + d / 2
    cols = [(x0, S, z0, x1, h, z1)]
    walls = {C.FACE_PX: (x1 - T, x1), C.FACE_NX: (x0, x0 + T), C.FACE_PZ: (z1 - T, z1), C.FACE_NZ: (z0, z0 + T)}
    for f, (a, b) in walls.items():
        if f in (C.FACE_PX, C.FACE_NX):
            if f != face:
                cols.append((a, 0.0, z0, b, S, z1))
            else:
                cols += [(a, 0.0, z0, b, S, lz - dh), (a, 0.0, lz + dh, b, S, z1), (a, dy, lz - dh, b, S, lz + dh)]
        else:
            if f != face:
                cols.append((x0, 0.0, a, x1, S, b))
            else:
                cols += [(x0, 0.0, a, lx - dh, S, b), (lx + dh, 0.0, a, x1, S, b), (lx - dh, dy, a, lx + dh, S, b)]
    return cols


class Interior:
    def __init__(self, rec, index):
        self.rec = rec
        self.boxes, self.colliders, self.quads = [], [], []
        fr = Frame(rec)
        core = Core(fr.W, fr.D)
        S = C.SHOP_H
        W, D = min(fr.W, C.SHOP_MAX_W), min(fr.D, C.SHOP_MAX_D)
        hue = C.SHOP_TYPES[rec.kind][1]
        rng = np.random.default_rng(int(rec.seed * 1000) & 0xFFFFFFFF)
        seed = rec.seed

        def add(a0, b0, a1, b1, y0, y1, kind, h=hue, extra=0.0, collide=False):
            x0, z0, x1, z1 = fr.bounds(a0, b0, a1, b1)
            self.boxes.append(box_bounds(x0, y0, z0, x1, y1, z1, kind, h, extra, seed))
            if collide:
                self.colliders.append((x0, y0, z0, x1, y1, z1))

        def holo(a, b, y, half_w, half_h, h=hue, inten=1.0, on_side_wall=False):
            x, z = fr.f(a, b)
            right = fr.depth if on_side_wall else fr.right
            self.quads.append(quad((x, y, z), tuple(c * half_w for c in right), (0.0, half_h, 0.0),
                                   C.Q_HOLO, h, inten, float(rng.uniform(0, 1000))))

        # wall the shop off from the rest of the ground floor; the back wall has the staff door
        # to the stair core up to the building's upper floors (buildings.py)
        # (tall buildings: also the elevator door)
        g = BuildingLayout(rec, index)
        upper = g.n_storeys > 0
        shaft = upper and g.has_shaft
        if D < fr.D - 0.5:
            gaps = []
            if upper:
                gaps.append((core.SX0, core.XA, C.STAIR_DOOR_H, 0.36))
            if shaft:
                gaps.append((core.door[0], core.door[1], buildings.SHAFT_DOOR_H, 0.5))
            a = -W / 2 - 0.3
            for g0, g1, dh, sign_hue in sorted(gaps):
                add(a, D, g0, D + 0.3, 0.0, S, C.K_SHOP_WALL, hue, rec.kind, collide=True)
                add(g0, D, g1, D + 0.3, dh, S, C.K_SHOP_WALL, hue, rec.kind, collide=True)
                add(g0 + 0.15, D - 0.04, g1 - 0.15, D, dh + 0.1, dh + 0.35, C.K_EMISSIVE, sign_hue, 3.0)
                a = g1
            add(a, D, W / 2 + 0.3, D + 0.3, 0.0, S, C.K_SHOP_WALL, hue, rec.kind, collide=True)
        if W < fr.W - 0.5:
            add(W / 2, 0.0, W / 2 + 0.3, D, 0.0, S, C.K_SHOP_WALL, hue, rec.kind, collide=True)
            add(-W / 2 - 0.3, 0.0, -W / 2, D, 0.0, S, C.K_SHOP_WALL, hue, rec.kind, collide=True)

        aw = W / 2 - 0.45                                       # usable half width
        # ceiling with light grid + two light strips (2F's slab sits right on top of it)
        add(-W / 2, 0.0, W / 2, D, S - 0.12, S - 0.1, C.K_SHOP_CEIL, hue, 0.55)
        for a in (-W / 4, W / 4):
            add(a - 0.12, 0.6, a + 0.12, D - 0.6, S - 0.2, S - 0.12, C.K_EMISSIVE, -1.0, 2.2)
        # counter, clerk, menu
        cb0 = max(D - 3.2, D * 0.55)
        ca = min(aw - 0.4, 4.0)
        add(-ca, cb0, ca, cb0 + 0.8, 0.0, 1.05, C.K_PANEL, hue, collide=True)
        add(-ca - 0.02, cb0 - 0.02, ca + 0.02, cb0 + 0.82, 1.05, 1.11, C.K_EMISSIVE, hue, 2.5)
        bk = min(cb0 + 1.5, D - 0.5)
        self.clerk = fr.f(0.0, bk)
        add(-0.25, bk - 0.15, 0.25, bk + 0.15, 0.0, 1.2, C.K_PANEL, float(rng.random()), collide=True)
        add(-0.17, bk - 0.17, 0.17, bk + 0.17, 1.25, 1.6, C.K_PANEL, hue)
        add(-0.15, bk - 0.19, 0.15, bk - 0.16, 1.4, 1.47, C.K_EMISSIVE, hue, 4.0)     # visor facing the door
        holo(-1.0 if shaft else 0.0, D - 0.08, 3.3, min(2.4, aw), 0.8, inten=1.3)     # menu, clear of the doors
        shelf_a1 = min(ca, core.door[0] - 0.3) if shaft else ca

        front = cb0 - 1.2                                       # free floor: b in [1.8, front]
        palette = C.NEON_HUES
        kind = rec.kind
        if kind == 0:                                           # convenience store: shelves + fridges
            for i, b in enumerate(np.arange(2.2, front - 0.6, 2.6)[:6]):
                for a0, a1 in ((-aw + 0.3, -1.0), (1.0, aw - 0.3)):
                    if a1 - a0 < 0.8:
                        continue
                    add(a0, b, a1, b + 0.6, 0.0, 1.8, C.K_PANEL, hue, collide=True)
                    for y in (0.5, 1.0, 1.5):
                        add(a0 + 0.05, b - 0.02, a1 - 0.05, b + 0.62, y, y + 0.08, C.K_EMISSIVE,
                            float(rng.choice(palette)), 1.6)
            if front > 2.5:
                add(-aw, 1.8, -aw + 0.35, front, 0.2, 2.3, C.K_EMISSIVE, 0.52, 1.4, collide=True)
        elif kind == 1:                                         # ramen: stools, lanterns
            for a in np.arange(-ca + 0.5, ca - 0.3, 1.0):
                add(a - 0.2, cb0 - 0.75, a + 0.2, cb0 - 0.35, 0.0, 0.7, C.K_DOOR, hue, collide=True)
                add(a - 0.22, cb0 - 0.77, a + 0.22, cb0 - 0.33, 0.7, 0.76, C.K_EMISSIVE, 0.0, 2.0)
            for a in np.linspace(-aw * 0.6, aw * 0.6, 3):
                for b in np.arange(1.5, cb0, 3.0)[:4]:
                    add(a - 0.25, b - 0.25, a + 0.25, b + 0.25, 3.6, 4.3, C.K_EMISSIVE, 0.0, 3.0)
            holo(-W / 2 + 0.08, D * 0.4, 2.2, min(1.5, D * 0.3), 0.9, 0.03, on_side_wall=True)
        elif kind == 2:                                         # cyber clinic: chair, scanner arch, screens
            bc = min(max(2.5, front * 0.6), front)
            add(-0.5, bc - 1.0, 0.5, bc + 1.0, 0.0, 0.6, C.K_DOOR, hue, collide=True)
            add(-0.45, bc + 0.6, 0.45, bc + 1.0, 0.6, 1.4, C.K_PANEL, hue, collide=True)
            for a in (-1.0, 1.0):
                add(a - 0.06, bc - 0.06, a + 0.06, bc + 0.06, 0.0, 2.4, C.K_EMISSIVE, hue, 3.0)
            add(-1.06, bc - 0.06, 1.06, bc + 0.06, 2.34, 2.46, C.K_EMISSIVE, hue, 3.0)
            for s in (-1, 1):
                holo(s * (W / 2 - 0.08), bc, 2.2, 1.0, 0.7, inten=1.2, on_side_wall=True)
        elif kind == 3:                                         # bar: stools, bottle shelves, tables
            for a in np.arange(-ca + 0.5, ca - 0.3, 1.1):
                add(a - 0.2, cb0 - 0.75, a + 0.2, cb0 - 0.35, 0.0, 0.8, C.K_DOOR, hue, collide=True)
            for y in (1.5, 2.1, 2.7):
                add(-ca, D - 0.35, shelf_a1, D - 0.1, y, y + 0.06, C.K_EMISSIVE, float(rng.choice(palette)), 2.0)
            for a in (-aw * 0.5, aw * 0.5):
                for b in np.arange(2.2, front - 1.0, 3.0)[:3]:
                    add(a - 0.45, b - 0.45, a + 0.45, b + 0.45, 0.0, 1.05, C.K_PANEL, hue, collide=True)
                    add(a - 0.06, b - 0.06, a + 0.06, b + 0.06, 1.05, 1.25, C.K_EMISSIVE, 0.12, 4.0)
        elif kind == 4:                                         # electronics: display tables
            for a in np.linspace(-aw * 0.55, aw * 0.55, max(1, min(4, int(W // 4)))):
                for b in np.arange(2.2, front - 1.0, 2.8)[:5]:
                    add(a - 0.8, b - 0.45, a + 0.8, b + 0.45, 0.0, 0.95, C.K_PANEL, hue, collide=True)
                    for k in (-0.45, 0.0, 0.45):
                        add(a + k - 0.12, b - 0.12, a + k + 0.12, b + 0.12, 0.95, 1.2, C.K_EMISSIVE,
                            float(rng.choice(palette)), 3.0)
        else:                                                   # cafe: tables + chairs + lamps
            for a in np.linspace(-aw * 0.6, aw * 0.6, max(1, min(4, int(W // 3.5)))):
                for b in np.arange(2.2, front - 0.8, 2.6)[:5]:
                    add(a - 0.45, b - 0.45, a + 0.45, b + 0.45, 0.0, 0.75, C.K_PANEL, hue, collide=True)
                    add(a - 0.05, b - 0.05, a + 0.05, b + 0.05, 0.75, 0.95, C.K_EMISSIVE, 0.1, 4.0)
                    for s in (-1, 1):
                        add(a + s * 0.7 - 0.22, b - 0.22, a + s * 0.7 + 0.22, b + 0.22, 0.0, 0.48,
                            C.K_DOOR, hue, collide=True)
        self.footprint = (rec.lx - rec.w / 2, rec.lz - rec.d / 2, rec.lx + rec.w / 2, rec.lz + rec.d / 2)
        if upper:                                               # first flight of the stair core (0 m -> 2F)
            ground = build_storey(g, 0)
            self.boxes += ground.boxes
            self.colliders += ground.cols


class ShopManager:
    CELL = 64.0

    def __init__(self, records):
        self.records = records
        self.grid = defaultdict(list)
        c = self.CELL
        for i, r in enumerate(records):
            for ix in range(int(math.floor((r.lx - r.w / 2) / c)), int(math.floor((r.lx + r.w / 2) / c)) + 1):
                for iz in range(int(math.floor((r.lz - r.d / 2) / c)), int(math.floor((r.lz + r.d / 2) / c)) + 1):
                    self.grid[(ix, iz)].append(i)
        self.cache = {}
        self.active = ()
        self.boxes = np.zeros((0, BOX_FLOATS), "f4")
        self.quads = np.zeros((0, QUAD_FLOATS), "f4")
        self.colliders = []
        self.footprints = []
        self.bridges, self.bridge_doors = [], {}

    @staticmethod
    def _dist(r, x, z):
        dx = max(abs(x - r.lx) - r.w / 2, 0.0)
        dz = max(abs(z - r.lz) - r.d / 2, 0.0)
        return math.hypot(dx, dz)

    def nearby(self, x, z, radius):
        c = self.CELL
        ids = set()
        for ix in range(int(math.floor((x - radius) / c)), int(math.floor((x + radius) / c)) + 1):
            for iz in range(int(math.floor((z - radius) / c)), int(math.floor((z + radius) / c)) + 1):
                ids.update(self.grid.get((ix, iz), ()))
        return sorted(i for i in ids if self._dist(self.records[i], x, z) <= radius)

    def _current_index(self, pos):
        if not -1.0 < pos[1] < C.SHOP_H - 1.0:            # not from the metro / undercity below
            return None
        for i in self.nearby(pos[0], pos[2], 0.0):
            r = self.records[i]
            if abs(pos[0] - r.lx) < r.w / 2 - 0.2 and abs(pos[2] - r.lz) < r.d / 2 - 0.2:
                return i
        return None

    def set_bridges(self, bridges):
        self.bridges = list(bridges)
        self.bridge_doors = skybridges.doors_by_building(self.bridges)

    def building_at(self, pos):
        """Index of the city building whose walls enclose pos (any floor, or standing on its roof),
        or whose skybridge pos is on (the nearer end), or None."""
        if pos[1] < -1.0:                                   # below street level (metro, mall, undercity)
            return None
        for i in self.nearby(pos[0], pos[2], 0.0):
            r = self.records[i]
            if abs(pos[0] - r.lx) < r.w / 2 - 0.05 and abs(pos[2] - r.lz) < r.d / 2 - 0.05 and pos[1] < r.h + 3.0:
                return i
        for br in self.bridges:
            x0, z0, x1, z1 = br.deck
            # reach 1 m into both buildings so there is no gap at the facades
            ex, ez = (1.0, 0.0) if br.axis == 0 else (0.0, 1.0)
            if (x0 - ex <= pos[0] <= x1 + ex and z0 - ez <= pos[2] <= z1 + ez
                    and min(br.ya, br.yb) - 1.0 < pos[1] < max(br.ya, br.yb) + 3.0):
                u = (pos[0] - x0) / (x1 - x0) if br.axis == 0 else (pos[2] - z0) / (z1 - z0)
                return br.a if u < 0.5 else br.b
        return None

    def current(self, pos):
        """The shop record the player is standing in, or None."""
        i = self._current_index(pos)
        return None if i is None else self.records[i]

    def clerk_near(self, pos, reach=3.5):
        """The shop whose clerk is within reach of the player, or None."""
        i = self._current_index(pos)
        inside = self.cache.get(i)
        if inside and math.hypot(pos[0] - inside.clerk[0], pos[2] - inside.clerk[1]) < reach:
            return self.records[i]
        return None

    def update(self, pos):
        x, z = pos[0], pos[2]
        ids = tuple(self.nearby(x, z, C.SHOP_NEAR)) if pos[1] < 60.0 else ()
        for i in ids:
            if i not in self.cache:
                self.cache[i] = Interior(self.records[i], i)
        for i in [i for i in self.cache if self._dist(self.records[i], x, z) > C.SHOP_FORGET]:
            del self.cache[i]
        if ids == self.active:
            return
        self.active = ids
        shops = [self.cache[i] for i in ids]
        boxes = [b for s in shops for b in s.boxes]
        quads = [q for s in shops for q in s.quads]
        self.boxes = np.array(boxes, "f4").reshape(-1, BOX_FLOATS)
        self.quads = np.array(quads, "f4").reshape(-1, QUAD_FLOATS)
        self.colliders = [c for s in shops for c in s.colliders]
        self.footprints = [s.footprint for s in shops]
