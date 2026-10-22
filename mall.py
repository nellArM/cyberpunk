"""Underground mall: a shopping passage (地下街) from the 地心線 station 霓虹市集 (0, -280) north to
a hall right under Nexus Tower, whose stairs come up through the lobby floor.

Passage: x 9..17 (two moving walkways in the middle), shops on both sides (x 3..9 and 17..23),
from the station's back wall (z -272.7) to the hall (z -40). Hall: x -30..30, z -40..20 with
shops, a food court and a fountain. Everything sits at MALL_Y (-8 m), under the street.
"""
from collections import namedtuple

import numpy as np

import config as C
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS
from pedestrians import person_boxes

Y = C.MALL_Y
Z_STATION, Z_HALL = -272.7, -40.0
SHOP_Z0, SHOP_Z1, SHOP_LEN = -248.0, -48.0, 10.0
CEIL = Y + 3.6
HALL = (-30.0, -40.0, 30.0, 20.0)
HALL_CEIL = -0.6
BELTS = ((11.2, 12.8, 1.0), (13.2, 14.8, -1.0))           # x0, x1, direction along z
BELT_Z = (-268.0, -46.0)
BELT_SPEED = 3.0

Clerk = namedtuple("Clerk", "x y z kind")


class MallData:
    def __init__(self, boxes, cols, holos, clerks, walk_loops):
        self.boxes = np.array(boxes, "f4").reshape(-1, BOX_FLOATS)
        self.colliders = cols
        self.holos = np.array(holos, "f4").reshape(-1, QUAD_FLOATS)
        self.clerks = clerks
        self.walk_loops = walk_loops


def area(pos):
    """'地下街' / '地下商場' when pos is in the passage / hall, else None."""
    x, y, z = pos
    if not (Y - 1.0 < y < Y + 6.0):
        return None
    if 3.0 < x < 23.0 and Z_STATION < z < Z_HALL:
        return "地下街"
    if HALL[0] < x < HALL[2] and HALL[1] <= z < HALL[3]:
        return "地下商場"
    return None


def belt_push(pos):
    """Speed (along z) of the moving walkway under pos, or 0."""
    x, y, z = pos
    if abs(y - Y) > 0.3 or not (BELT_Z[0] < z < BELT_Z[1]):
        return 0.0
    for x0, x1, d in BELTS:
        if x0 < x < x1:
            return d * BELT_SPEED
    return 0.0


def build_mall(rng):
    boxes, cols, holos, clerks = [], [], [], []
    P, E, F, W, K = C.K_PANEL, C.K_EMISSIVE, C.K_FLOOR, C.K_SHOP_WALL, C.K_SHOP_CEIL

    def add(x0, y0, z0, x1, y1, z1, kind, hue=0.0, extra=0.0, collide=False, seed=0.0):
        boxes.append(box_bounds(x0, y0, z0, x1, y1, z1, kind, hue, extra, seed))
        if collide:
            cols.append((x0, y0, z0, x1, y1, z1))

    # --- passage shell
    add(9.0, Y - 0.6, Z_STATION, 17.0, Y, SHOP_Z0 - 2.0, F, 0.5, collide=True)          # narrow ends
    add(9.0, Y - 0.6, SHOP_Z1 + 3.0, 17.0, Y, Z_HALL, F, 0.5, collide=True)
    add(3.0, Y - 0.6, SHOP_Z0 - 2.0, 23.0, Y, SHOP_Z1 + 3.0, F, 0.5, collide=True)      # shop stretch
    for x0, x1 in ((8.7, 9.0), (17.0, 17.3)):
        add(x0, Y, Z_STATION, x1, CEIL, SHOP_Z0 - 2.0, P, 0.5, collide=True)
        add(x0, Y, SHOP_Z1 + 3.0, x1, CEIL, Z_HALL, P, 0.5, collide=True)
    add(2.7, Y, SHOP_Z0 - 2.0, 3.0, CEIL, SHOP_Z1 + 3.0, P, 0.5, collide=True)          # outer walls
    add(23.0, Y, SHOP_Z0 - 2.0, 23.3, CEIL, SHOP_Z1 + 3.0, P, 0.5, collide=True)
    for z in (SHOP_Z0 - 2.3, SHOP_Z1 + 3.0):
        add(2.7, Y, z, 9.0, CEIL, z + 0.3, P, 0.5, collide=True)
        add(17.0, Y, z, 23.3, CEIL, z + 0.3, P, 0.5, collide=True)
    add(8.7, CEIL, Z_STATION, 17.3, CEIL + 0.4, SHOP_Z0 - 2.0, K, 0.5, 0.6)
    add(8.7, CEIL, SHOP_Z1 + 3.0, 17.3, CEIL + 0.4, Z_HALL, K, 0.5, 0.6)
    add(2.7, CEIL, SHOP_Z0 - 2.0, 23.3, CEIL + 0.4, SHOP_Z1 + 3.0, K, 0.5, 0.7)
    for x in (9.4, 16.6):                                                                 # guide lights
        add(x - 0.05, Y, Z_STATION, x + 0.05, Y + 0.02, Z_HALL, E, 0.5, 2.0)
    # moving walkways
    for x0, x1, d in BELTS:
        add(x0, Y, BELT_Z[0], x1, Y + 0.06, BELT_Z[1], P, 0.55, collide=True)
        for xe in (x0, x1 - 0.08):                                   # handrails with a glowing top
            add(xe, Y + 0.06, BELT_Z[0], xe + 0.08, Y + 0.9, BELT_Z[1], P, 0.55)
            add(xe - 0.01, Y + 0.9, BELT_Z[0], xe + 0.09, Y + 0.95, BELT_Z[1], E, 0.33 if d > 0 else 0.97, 2.0)
    holos.append(quad((13.0, Y + 2.8, Z_STATION + 1.0), (3.6, 0, 0), (0, 0.6, 0), C.Q_HOLO, 0.5, 1.5, 800))

    # --- passage shops, both sides
    k = 0
    for side, (xo, xi) in enumerate(((3.0, 9.0), (23.0, 17.0))):        # outer wall x, storefront x
        s = 1.0 if xi > xo else -1.0                                      # from the back wall toward the passage
        for z0 in np.arange(SHOP_Z0, SHOP_Z1, SHOP_LEN):
            kind = k % len(C.SHOP_TYPES)
            k += 1
            hue = C.SHOP_TYPES[kind][1]
            z1 = z0 + SHOP_LEN
            add(min(xo, xi), Y, z0 - 0.15, max(xo, xi), CEIL, z0 + 0.15, W, hue, kind, collide=True)   # partition
            add(min(xi, xi - s * 0.3), Y + 3.0, z0, max(xi, xi - s * 0.3), CEIL, z1, W, hue, kind)       # fascia
            add(min(xi, xi + s * 0.15), Y + 3.05, z0 + 1.0, max(xi, xi + s * 0.15), Y + 3.5, z1 - 1.0, C.K_SIGN,
                hue, 0.0, seed=float(rng.uniform(0, 1000)))
            for zz in (z0 + 0.2, z1 - 0.3):
                add(min(xi, xi - s * 0.1), Y, zz, max(xi, xi - s * 0.1), Y + 3.0, zz + 0.1, E, hue, 2.5)
            cx = xo + s * 1.5                                              # counter + clerk near the back
            add(min(cx, cx + s * 0.9), Y, z0 + 2.5, max(cx, cx + s * 0.9), Y + 1.05, z1 - 2.5, P, hue, collide=True)
            add(min(cx, cx + s * 0.9) - 0.02, Y + 1.05, z0 + 2.48, max(cx, cx + s * 0.9) + 0.02, Y + 1.11, z1 - 2.48,
                E, hue, 2.5)
            clerks.append(Clerk(xo + s * 0.8, Y, (z0 + z1) / 2, kind))
            for zz in (z0 + 0.4, z1 - 1.2):                                # shelves along the partitions
                add(min(xo + s * 2.8, xi - s * 1.2), Y, zz, max(xo + s * 2.8, xi - s * 1.2), Y + 1.8, zz + 0.8,
                    P, hue, collide=True)
                for y in (0.5, 1.0, 1.5):
                    add(min(xo + s * 2.8, xi - s * 1.2), Y + y, zz - 0.02, max(xo + s * 2.8, xi - s * 1.2),
                        Y + y + 0.07, zz + 0.82, E, float(rng.choice(C.NEON_HUES)), 1.4)
            add(min(xo, xo + s * 0.1), Y + 1.6, z0 + 2.0, max(xo, xo + s * 0.1), Y + 2.8, z1 - 2.0, E, hue, 0.9)  # menu
        add(min(xo, xi), Y, SHOP_Z1 - 0.15, max(xo, xi), CEIL, SHOP_Z1 + 0.15, W, 0.5, 0, collide=True)

    # --- the hall under Nexus
    hx0, hz0, hx1, hz1 = HALL
    sx0, sz0, sx1, sz1 = C.MALL_STAIR
    add(hx0, Y - 0.6, hz0, hx1, Y, hz1, F, 0.83, collide=True)
    for b in ((hx0 - 0.3, hz0 - 0.3, hx0, hz1 + 0.3), (hx1, hz0 - 0.3, hx1 + 0.3, hz1 + 0.3),
              (hx0, hz1, hx1, hz1 + 0.3), (hx0, hz0 - 0.3, 9.0, hz0), (17.0, hz0 - 0.3, hx1, hz0)):
        add(b[0], Y, b[1], b[2], HALL_CEIL, b[3], P, 0.83, collide=True)
    add(9.0, CEIL, hz0 - 0.3, 17.0, HALL_CEIL, hz0, P, 0.83, collide=True)               # over the passage mouth
    # ceiling with the stair opening
    for b in ((hx0, hz0, sx0, hz1), (sx1, hz0, hx1, hz1), (sx0, hz0, sx1, sz0), (sx0, sz1, sx1, hz1)):
        add(b[0], HALL_CEIL, b[1], b[2], -0.15, b[3], K, 0.83, 0.8)
    # stairs up into the Nexus lobby, with side walls
    n = int(round(-Y / 0.2))
    run = (sz1 - sz0) / n
    for i in range(1, n + 1):
        t = Y + 0.2 * i
        add(sx0, t - 0.3, sz0 + run * (i - 1), sx1, t, sz0 + run * i, C.K_DOOR, 0.5, collide=True)
    for x0, x1 in ((sx0 - 0.2, sx0), (sx1, sx1 + 0.2)):
        add(x0, Y, sz0, x1, 1.1, sz1, P, 0.5, collide=True)
        add(x0, 1.1, sz0, x1, 1.16, sz1, E, 0.5, 2.5)
    holos.append(quad(((sx0 + sx1) / 2, Y + 3.2, sz0 + 1.0), (2.0, 0, 0), (0, 0.5, 0), C.Q_HOLO, 0.83, 1.5, 801))
    # fountain and a hologram in the middle
    for b in ((-6, -10, 2, -9.6), (-6, -2.4, 2, -2), (-6, -9.6, -5.6, -2.4), (1.6, -9.6, 2, -2.4)):
        add(b[0], Y, b[1], b[2], Y + 0.6, b[3], P, 0.5, collide=True)
    add(-5.6, Y, -9.6, 1.6, Y + 0.35, -2.4, E, 0.5, 0.6, collide=True)
    add(-2.4, Y + 0.35, -6.4, -1.6, Y + 3.5, -5.6, E, 0.52, 2.2)
    holos.append(quad((-2.0, Y + 5.0, -6.0), (4.0, 0, 0), (0, 1.2, 0), C.Q_HOLO, 0.92, 1.3, 802))
    # food court tables and chairs
    for x in np.arange(4.0, 20.0, 4.0):
        for z in np.arange(-30.0, 12.0, 5.0):
            hue = float(rng.choice(C.NEON_HUES))
            add(x - 0.5, Y, z - 0.5, x + 0.5, Y + 0.75, z + 0.5, P, hue, collide=True)
            add(x - 0.06, Y + 0.75, z - 0.06, x + 0.06, Y + 0.95, z + 0.06, E, 0.12, 4.0)
            for dz in (-0.85, 0.85):
                add(x - 0.25, Y, z + dz - 0.25, x + 0.25, Y + 0.45, z + dz + 0.25, C.K_DOOR, hue, collide=True)
    # food stalls along the west wall
    for i, z0 in enumerate(np.arange(-38.0, 16.0, 9.0)):
        kind = (i + 1) % len(C.SHOP_TYPES)
        hue = C.SHOP_TYPES[kind][1]
        add(hx0 + 2.6, Y, z0 + 0.5, hx0 + 4.0, Y + 1.05, z0 + 8.5, P, hue, collide=True)           # counter
        add(hx0 + 2.58, Y + 1.05, z0 + 0.48, hx0 + 4.02, Y + 1.11, z0 + 8.52, E, hue, 2.5)
        add(hx0, Y + 3.2, z0 + 0.5, hx0 + 4.5, Y + 3.9, z0 + 8.5, C.K_SIGN, hue, 0.0, seed=float(rng.uniform(0, 1000)))
        clerks.append(Clerk(hx0 + 1.3, Y, z0 + 4.5, kind))
    for x in np.arange(hx0 + 6.0, hx1, 6.0):                                             # ceiling light strips
        add(x - 0.1, HALL_CEIL - 0.1, hz0 + 1.0, x + 0.1, HALL_CEIL, hz1 - 1.0, E, -1.0, 2.0)
    holos.append(quad((0.0, Y + 4.2, hz1 - 0.4), (8.0, 0, 0), (0, 1.0, 0), C.Q_HOLO, 0.5, 1.3, 803))

    # static clerk figures behind the counters
    cx = np.array([c.x for c in clerks])
    cz = np.array([c.z for c in clerks])
    m = len(clerks)
    fa = np.zeros(m, np.int64)
    fs = np.where(cx < 13.0, 1.0, -1.0)
    figs = person_boxes(cx, Y, cz, fa, fs, np.zeros(m, bool), np.zeros(m), np.ones(m),
                        np.array([C.SHOP_TYPES[c.kind][1] for c in clerks]), np.arange(m) * 13.0, np.zeros(m))
    boxes.extend(figs.tolist())
    for c in clerks:
        cols.append((c.x - 0.3, Y, c.z - 0.3, c.x + 0.3, Y + 1.8, c.z + 0.3))

    walk = [([(10.2, -265.0), (10.2, -48.0), (15.8, -48.0), (15.8, -265.0)], Y, 30),
            ([(-22.0, -35.0), (22.0, -35.0), (22.0, 15.0), (-22.0, 15.0)], Y, 25)]
    return MallData(boxes, cols, holos, clerks, walk)


def lobby_rails():
    """Back railing of the stair opening in the Nexus lobby floor (the stair side walls rise above the
    floor as the side railings; the +z end, where the stairs arrive, is open) and a sign."""
    sx0, sz0, sx1, sz1 = C.MALL_STAIR
    b = (sx0 - 0.2, 0.0, sz0 - 0.2, sx1 + 0.2, 1.1, sz0)
    boxes = [box_bounds(*b, C.K_PANEL, 0.83), box_bounds(b[0], 1.1, b[2], b[3], 1.16, b[5], C.K_EMISSIVE, 0.83, 3.0)]
    holos = [quad(((sx0 + sx1) / 2, 3.0, sz1 + 0.5), (2.2, 0, 0), (0, 0.55, 0), C.Q_HOLO, 0.83, 1.5, 804)]
    return boxes, [b], holos
