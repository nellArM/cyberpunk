"""B2 undercity: a square ring passage under the 地心線 loop (centerline R = 240, 8 m wide,
floor at y = -16), reached from each of the four 地心線 platforms through a side door, a short
passage, 40 steps down and a corridor. Four halls open off the inside of the ring:
暗巷黑市 (north), 地下停車場 (east), 地下美食街 (south), 地下電玩街 (west). Moving walkways run
both ways along every side.

It lies below the metro tunnels (about -9.6 m) and the mall (-8 m), so nothing intersects.
"""
import math
from collections import namedtuple

import numpy as np

import config as C
import metro
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS
from i18n import tr
from pedestrians import person_boxes

Y = C.UNDERCITY_Y
R = C.UNDERCITY_R
HW = 4.0                                    # ring half width
CEIL = Y + 4.5
STAIR_Y = C.MALL_Y                          # the platforms' floor level (-8)
HALLS = {                                   # name: (x0, z0, x1, z1) inside the ring
    "暗巷黑市": (-200.0, -R + HW, -40.0, -200.0),
    "地下停車場": (180.0, -120.0, R - HW, 120.0),
    "地下美食街": (40.0, 200.0, 200.0, R - HW),
    "地下電玩街": (-R + HW, 40.0, -196.0, 160.0),
}
Talker = namedtuple("Talker", "x y z name line")


class UndercityData:
    def __init__(self, boxes, cols, holos, talkers, walk_loops, belts, connectors):
        self.boxes = np.array(boxes, "f4").reshape(-1, BOX_FLOATS)
        self.colliders = cols
        self.holos = np.array(holos, "f4").reshape(-1, QUAD_FLOATS)
        self.talkers = talkers
        self.walk_loops = walk_loops
        self.belts = belts                  # (x0, z0, x1, z1, dx, dz) at floor Y
        self.connectors = connectors        # world rects (x0, z0, x1, z1) of the station passages


def _ring_sides():
    """(x0, z0, x1, z1) floor rects of the ring's four sides (N, E, S, W)."""
    o, i = R + HW, R - HW
    return [(-o, -o, o, -i), (i, -i, o, i), (-o, i, o, o), (-o, -i, -i, i)]


def in_ring(x, z):
    return any(a <= x <= c and b <= z <= d for a, b, c, d in _ring_sides())


_DATA = None


def area(pos):
    x, y, z = pos
    if not (Y - 1.0 < y < CEIL + 1.0) and not (STAIR_Y - 9.0 < y < STAIR_Y + 1.0):
        return None
    if Y - 1.0 < y < CEIL + 1.0:
        for name, (a, b, c, d) in HALLS.items():
            if a <= x <= c and b <= z <= d:
                return tr("地下城・{name}", name=name)
        if in_ring(x, z):
            return "地下城環道"
    if _DATA is not None and any(a <= x <= c and b <= z <= d for a, b, c, d in _DATA.connectors) and y < -4.0:
        return "地下城連通道"
    return None


def belt_push(pos):
    if _DATA is None or abs(pos[1] - Y) > 0.3:
        return 0.0, 0.0
    for x0, z0, x1, z1, dx, dz in _DATA.belts:
        if x0 < pos[0] < x1 and z0 < pos[2] < z1:
            return dx, dz
    return 0.0, 0.0


def build_undercity(rng):
    global _DATA
    boxes, cols, holos, talkers, belts, connectors = [], [], [], [], [], []
    P, E, F, W, K = C.K_PANEL, C.K_EMISSIVE, C.K_FLOOR, C.K_SHOP_WALL, C.K_SHOP_CEIL

    def add(x0, y0, z0, x1, y1, z1, kind, hue=0.0, extra=0.0, collide=False, seed=0.0):
        boxes.append(box_bounds(x0, y0, z0, x1, y1, z1, kind, hue, extra, seed))
        if collide:
            cols.append((x0, y0, z0, x1, y1, z1))

    def wall_x(x0, x1, z, gaps, y0=Y, y1=CEIL, hue=0.83):
        """A wall along x at z (0.3 thick, from z) with (a0, a1) openings."""
        xs = [x0] + [v for g in sorted(gaps) for v in g] + [x1]
        for a, b in zip(xs[0::2], xs[1::2]):
            if b > a:
                add(a, y0, z, b, y1, z + 0.3, P, hue, collide=True)

    def wall_z(z0, z1, x, gaps, y0=Y, y1=CEIL, hue=0.83):
        zs = [z0] + [v for g in sorted(gaps) for v in g] + [z1]
        for a, b in zip(zs[0::2], zs[1::2]):
            if b > a:
                add(x, y0, a, x + 0.3, y1, b, P, hue, collide=True)

    def talker(x, z, face, hue, name, line):
        fig = person_boxes(np.array([x]), Y, np.array([z]), np.array([face[0]]), np.array([face[1]]),
                           np.zeros(1, bool), np.zeros(1), np.ones(1), np.array([hue]),
                           np.array([float(rng.uniform(0, 1000))]), np.zeros(1))
        boxes.extend(fig.tolist())
        cols.append((x - 0.3, Y, z - 0.3, x + 0.3, Y + 1.8, z + 0.3))
        talkers.append(Talker(x, Y, z, name, line))

    # ---------------------------------------------------------------- connectors from the platforms
    line = metro.LINES[0]
    path = metro.PolyPath(line["verts"])
    ring_gaps = {"N": [], "E": [], "S": [], "W": []}
    for side, a, name, _ in metro.line_stops(path, line):
        fr = path.frames[side].shifted(a)
        d0, d1 = C.UNDERCITY_DOOR_MALL if name == C.MALL_STATION else C.UNDERCITY_DOOR
        b_ring = abs(fr.c[0]) + abs(fr.c[1]) - (R + HW)                # b of the ring's outer edge (stations on an axis)

        def box(a0, b0, a1, b1, y0, y1, kind, hue=0.5, extra=0.0, collide=False):
            x0, z0, x1, z1 = fr.bounds(a0, b0, a1, b1)
            add(x0, y0, z0, x1, y1, z1, kind, hue, extra, collide)

        n = int(round((STAIR_Y - Y) / 0.2))                           # 40 steps
        b_stair = 12.0
        b_low = b_stair + 0.3 * n                                     # 24
        box(d0, 7.3, d1, b_stair, STAIR_Y - 0.6, STAIR_Y, F, 0.5, collide=True)          # upper passage
        box(d0, 7.3, d1, b_stair, STAIR_Y + 3.4, STAIR_Y + 3.8, K, 0.5, 0.6)
        for i in range(1, n + 1):
            t = STAIR_Y - 0.2 * i
            box(d0, b_stair + 0.3 * (i - 1), d1, b_stair + 0.3 * i, t - 0.3, t, C.K_DOOR, 0.83, collide=True)
        box(d0, b_low, d1, b_ring, Y - 0.6, Y, F, 0.5, collide=True)                     # lower corridor
        box(d0, b_low, d1, b_ring, CEIL, CEIL + 0.4, K, 0.5, 0.6)
        box(d0, b_stair, d1, b_low, STAIR_Y + 3.4, STAIR_Y + 3.8, P, 0.5)                 # over the stairs
        for a0, a1 in ((d0 - 0.3, d0), (d1, d1 + 0.3)):                                   # side walls
            box(a0, 7.3, a1, b_ring, Y, STAIR_Y + 3.8, P, 0.5, collide=True)
        for a_ in (d0 + 0.05, d1 - 0.11):                                                  # guide lights
            box(a_, 7.3, a_ + 0.06, b_ring, Y + 0.0, Y + 0.02, E, 0.83, 2.0)
            box(a_, 7.3, a_ + 0.06, b_stair, STAIR_Y, STAIR_Y + 0.02, E, 0.83, 2.0)
        connectors.append(fr.bounds(d0 - 0.3, 7.3, d1 + 0.3, b_ring))
        cx0, cz0, cx1, cz1 = fr.bounds(d0, b_ring - 1.0, d1, b_ring)
        key = "N" if fr.n[1] > 0.5 else "S" if fr.n[1] < -0.5 else "E" if fr.n[0] < -0.5 else "W"
        ring_gaps[key].append((cx0, cx1) if key in "NS" else (cz0, cz1))
        x, z = fr.world((d0 + d1) / 2, b_ring - 2.0)
        holos.append(quad((x, Y + 3.2, z), tuple(0.0 if abs(v) < 0.5 else 2.0 * abs(v) for v in (fr.f[0], 0.0, fr.f[1])),
                          (0, 0.45, 0), C.Q_HOLO, 0.5, 1.5, 950 + side))
        sx, sz = fr.world((d0 + d1) / 2, 8.0)
        holos.append(quad((sx, STAIR_Y + 2.8, sz), tuple(0.0 if abs(v) < 0.5 else 1.6 * abs(v) for v in (fr.f[0], 0.0, fr.f[1])),
                          (0, 0.4, 0), C.Q_HOLO, 0.83, 1.5, 960 + side))

    # ---------------------------------------------------------------- the ring
    o, i = R + HW, R - HW
    sides = _ring_sides()
    for b in sides:
        add(b[0], Y - 0.6, b[1], b[2], Y, b[3], F, 0.83, collide=True)
        add(b[0], CEIL, b[1], b[2], CEIL + 0.4, b[3], K, 0.83, 0.55)
    halls_open = {"N": [(HALLS["暗巷黑市"][0], HALLS["暗巷黑市"][2])], "E": [(HALLS["地下停車場"][1], HALLS["地下停車場"][3])],
                  "S": [(HALLS["地下美食街"][0], HALLS["地下美食街"][2])], "W": [(HALLS["地下電玩街"][1], HALLS["地下電玩街"][3])]}
    wall_x(-o, o, -o - 0.3, ring_gaps["N"])                                              # outer walls
    wall_x(-o, o, o, ring_gaps["S"])
    wall_z(-o, o, o, ring_gaps["E"])
    wall_z(-o, o, -o - 0.3, ring_gaps["W"])
    wall_x(-i, i, -i, halls_open["N"])                                                   # inner walls
    wall_x(-i, i, i - 0.3, halls_open["S"])
    wall_z(-i, i, i - 0.3, halls_open["E"])
    wall_z(-i, i, -i, halls_open["W"])
    for k, (x0, z0, x1, z1) in enumerate(sides):                                         # neon trims + walkways
        along_x = (x1 - x0) > (z1 - z0)
        if along_x:
            zc = (z0 + z1) / 2
            for z in (z0 + 0.3, z1 - 0.36):
                add(x0, CEIL - 0.3, z, x1, CEIL - 0.24, z + 0.06, E, C.NEON_HUES[k], 2.2)
            for (a0, a1), d in (((zc - 1.6, zc - 0.1), 1.0), ((zc + 0.1, zc + 1.6), -1.0)):
                bx0, bx1 = x0 + 8.0, x1 - 8.0
                add(bx0, Y, a0, bx1, Y + 0.06, a1, P, 0.55, collide=True)
                for e in (a0, a1 - 0.08):
                    add(bx0, Y + 0.06, e, bx1, Y + 0.9, e + 0.08, P, 0.55)
                    add(bx0, Y + 0.9, e - 0.01, bx1, Y + 0.95, e + 0.09, E, 0.33 if d > 0 else 0.97, 2.0)
                belts.append((bx0, a0, bx1, a1, d * 3.0, 0.0))
        else:
            xc = (x0 + x1) / 2
            for x in (x0 + 0.3, x1 - 0.36):
                add(x, CEIL - 0.3, z0, x + 0.06, CEIL - 0.24, z1, E, C.NEON_HUES[k], 2.2)
            for (a0, a1), d in (((xc - 1.6, xc - 0.1), 1.0), ((xc + 0.1, xc + 1.6), -1.0)):
                bz0, bz1 = z0 + 8.0, z1 - 8.0
                add(a0, Y, bz0, a1, Y + 0.06, bz1, P, 0.55, collide=True)
                for e in (a0, a1 - 0.08):
                    add(e, Y + 0.06, bz0, e + 0.08, Y + 0.9, bz1, P, 0.55)
                    add(e - 0.01, Y + 0.9, bz0, e + 0.09, Y + 0.95, bz1, E, 0.33 if d > 0 else 0.97, 2.0)
                belts.append((a0, bz0, a1, bz1, 0.0, d * 3.0))

    # ---------------------------------------------------------------- halls
    for name, (x0, z0, x1, z1) in HALLS.items():
        add(x0, Y - 0.6, z0, x1, Y, z1, F, 0.5, collide=True)
        dim = 0.25 if name == "暗巷黑市" else 0.7
        add(x0, CEIL, z0, x1, CEIL + 0.4, z1, K, 0.83 if name != "暗巷黑市" else 0.0, dim)
    # hall walls (the side facing the ring is open)
    mx0, mz0, mx1, mz1 = HALLS["暗巷黑市"]
    wall_x(mx0, mx1, mz1, [])
    wall_z(mz0, mz1, mx0 - 0.3, [])
    wall_z(mz0, mz1, mx1, [])
    gx0, gz0, gx1, gz1 = HALLS["地下停車場"]
    wall_z(gz0, gz1, gx0 - 0.3, [])
    wall_x(gx0, gx1, gz0 - 0.3, [])
    wall_x(gx0, gx1, gz1, [])
    fx0, fz0, fx1, fz1 = HALLS["地下美食街"]
    wall_x(fx0, fx1, fz0 - 0.3, [])
    wall_z(fz0, fz1, fx0 - 0.3, [])
    wall_z(fz0, fz1, fx1, [])
    ax0, az0, ax1, az1 = HALLS["地下電玩街"]
    wall_z(az0, az1, ax1, [])
    wall_x(ax0, ax1, az0 - 0.3, [])
    wall_x(ax0, ax1, az1, [])

    # 暗巷黑市: two rows of tarp stalls, crates, red lamps, dealers
    k = 0
    for row_z, face in ((mz1 - 5.0, -1.0), (mz0 + 13.0, 1.0)):
        for x in np.arange(mx0 + 8.0, mx1 - 6.0, 12.0):
            hue = float(rng.choice((0.0, 0.97, 0.05, 0.83)))
            add(x - 3.0, Y, row_z - 1.5, x + 3.0, Y + 1.0, row_z + 1.5, P, 0.05, collide=True)
            add(x - 3.6, Y + 2.8, row_z - 2.6, x + 3.6, Y + 3.1, row_z + 2.6, C.K_SIGN, hue, seed=float(rng.uniform(0, 1000)))
            for xx in (x - 3.4, x + 3.4):
                add(xx - 0.06, Y, row_z - 0.06, xx + 0.06, Y + 2.8, row_z + 0.06, P, 0.5)
            add(x - 0.15, Y + 2.3, row_z - 0.15, x + 0.15, Y + 2.6, row_z + 0.15, E, 0.0, 4.0)        # red lamp
            for _ in range(int(rng.integers(2, 5))):                                       # crates
                cx, cz = x + rng.uniform(-2.5, 2.5), row_z + face * rng.uniform(2.5, 4.0)
                s = rng.uniform(0.7, 1.2)
                add(cx - s / 2, Y, cz - s / 2, cx + s / 2, Y + s, cz + s / 2, P, 0.08, collide=True)
            talker(x, row_z - face * 2.4, (1, face), hue, "黑市攤販", C.BLACKMARKET_LINES[k % len(C.BLACKMARKET_LINES)])
            k += 1
    holos.append(quad(((mx0 + mx1) / 2, Y + 3.6, mz1 - 0.4), (6.0, 0, 0), (0, 0.6, 0), C.Q_HOLO, 0.0, 1.4, 970))

    # 地下停車場: pillar grid, parked cars, bay lines, lane arrows, a ramp to a closed gate
    for x in np.arange(gx0 + 6.0, gx1, 12.0):
        for z in np.arange(gz0 + 6.0, gz1, 12.0):
            add(x - 0.45, Y, z - 0.45, x + 0.45, CEIL, z + 0.45, P, 0.5, collide=True)
            add(x - 0.47, Y + 1.0, z - 0.47, x + 0.47, Y + 1.3, z + 0.47, E, 0.12, 2.0)
    for x in (gx0 + 3.0, gx0 + 21.0, gx0 + 33.0):
        for z in np.arange(gz0 + 1.5, gz1 - 2.0, 3.0):
            add(x - 2.5, Y, z - 0.04, x + 2.5, Y + 0.02, z + 0.04, E, -1.0, 0.8)
            if rng.random() < 0.7:
                hue = float(rng.choice(C.NEON_HUES))
                add(x - 2.2, Y + 0.25, z + 0.35, x + 2.2, Y + 1.15, z + 2.35, C.K_VEHICLE, hue, 1.0, collide=True)
                add(x - 1.0, Y + 1.15, z + 0.55, x + 1.3, Y + 1.75, z + 2.15, C.K_VEHICLE, hue, 0.0, collide=True)
    for z in np.arange(gz0 + 6.0, gz1 - 4.0, 8.0):                                         # lane arrows
        add(gx0 + 11.5, Y, z, gx0 + 12.5, Y + 0.02, z + 3.0, E, 0.12, 1.5)
    add(gx1 - 14.0, Y, gz1 - 18.0, gx1 - 6.0, Y + 0.02, gz1 - 2.0, E, 0.12, 0.6)          # the ramp (closed)
    add(gx1 - 14.0, Y, gz1 - 2.3, gx1 - 6.0, Y + 3.5, gz1 - 2.0, C.K_DOOR, 0.12, 0.0, collide=True)
    holos.append(quad((gx0 + 2.0, Y + 3.0, 0.0), (0, 0, 1.6), (0, 1.0, 0), C.Q_HOLO, 0.55, 1.6, 971))

    # 地下美食街: stalls on the back wall (north, z0), tables toward the ring
    for j, x in enumerate(np.arange(fx0 + 8.0, fx1 - 6.0, 14.0)):
        kind = j % len(C.SHOP_TYPES)
        hue = C.SHOP_TYPES[kind][1]
        add(x - 4.0, Y, fz0 + 3.5, x + 4.0, Y + 1.05, fz0 + 4.5, P, hue, collide=True)
        add(x - 4.05, Y + 1.05, fz0 + 3.45, x + 4.05, Y + 1.11, fz0 + 4.55, E, hue, 2.5)
        add(x - 4.0, Y + 3.0, fz0, x + 4.0, Y + 3.9, fz0 + 0.5, C.K_SIGN, hue, seed=float(rng.uniform(0, 1000)))
        talker(x, fz0 + 2.2, (1, 1.0), hue, C.SHOP_TYPES[kind][0], C.SHOP_TYPES[kind][2])
    for x in np.arange(fx0 + 6.0, fx1 - 4.0, 5.0):
        for z in np.arange(fz0 + 9.0, fz1 - 5.0, 5.0):
            add(x - 0.5, Y, z - 0.5, x + 0.5, Y + 0.75, z + 0.5, P, 0.12, collide=True)
            add(x - 0.06, Y + 0.75, z - 0.06, x + 0.06, Y + 0.95, z + 0.06, E, 0.12, 4.0)

    # 地下電玩街: rows of glowing cabinets on a neon floor
    for x in np.arange(ax0 + 5.0, ax1 - 3.0, 2.0):
        for z in np.arange(az0 + 4.0, az1 - 3.0, 2.0):
            add(x + 0.05, Y, z + 0.05, x + 1.95, Y + 0.02, z + 1.95, E, float(rng.choice(C.NEON_HUES)), 0.35)
    for x in np.arange(ax0 + 6.0, ax1 - 4.0, 6.0):
        for z in np.arange(az0 + 6.0, az1 - 5.0, 1.6):
            hue = float(rng.choice(C.NEON_HUES))
            add(x - 0.6, Y, z - 0.6, x + 0.6, Y + 1.9, z + 0.6, C.K_SIGN, hue, collide=True,
                seed=float(rng.uniform(0, 1000)))
    talker(ax1 - 3.0, (az0 + az1) / 2, (0, -1.0), 0.83, "電玩街店長", "投幣機台全部免費試玩，破關紀錄會貼在霓虹牆上！")
    holos.append(quad((ax1 - 0.4, Y + 3.4, (az0 + az1) / 2), (0, 0, 5.0), (0, 0.6, 0), C.Q_HOLO, 0.75, 1.5, 972))

    walk = [([(-R - 2.6, -R - 2.6), (R + 2.6, -R - 2.6), (R + 2.6, R + 2.6), (-R - 2.6, R + 2.6)], Y, 30),
            ([(-R + 2.6, -R + 2.6), (-R + 2.6, R - 2.6), (R - 2.6, R - 2.6), (R - 2.6, -R + 2.6)], Y, 30),
            ([(mx0 + 4.0, mz0 + 8.0), (mx1 - 4.0, mz0 + 8.0), (mx1 - 4.0, mz1 - 9.5), (mx0 + 4.0, mz1 - 9.5)], Y, 15),
            ([(gx0 + 12.0, gz0 + 4.0), (gx0 + 12.0, gz1 - 4.0), (gx0 + 27.0, gz1 - 4.0), (gx0 + 27.0, gz0 + 4.0)], Y, 10)]
    _DATA = UndercityData(boxes, cols, holos, talkers, walk, belts, connectors)
    return _DATA
