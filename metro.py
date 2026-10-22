"""City metro: an underground loop (地心線), an elevated loop (天際線) and the elevated
三塔線 linking the three megatowers.

Each line is a closed rectilinear polygon following road centerlines: straight sides joined
by quarter-circle curves of radius CURVE_R at the intersections (the two square loops at +-R
are the special case `square(R)`). The perimeter parameter s runs along straight side k, then
the curve into side k+1. Each side has a local frame (a along the line, b toward the inside of
the loop, a = 0 at the side's midpoint); stations sit on the inner side of a straight.
Curved structure and the trains are rotated boxes (shaders.BOX_ROT_VS); the player rides
inside a car, with walking physics solved in the car's own frame.
"""
import bisect
import math
from collections import namedtuple

import numpy as np

import config as C
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS
from pedestrians import person_boxes


def square(R, names, land_b=14.0):
    """Vertices and stops (x, z, name, land_b) of a square loop at +-R with a station mid-side."""
    verts = ((-R, -R), (R, -R), (R, R), (-R, R))
    mids = ((0.0, -R), (R, 0.0), (0.0, R), (-R, 0.0))
    return verts, tuple((x, z, n, land_b) for (x, z), n in zip(mids, names))


_U_VERTS, _U_STOPS = square(280.0, ("霓虹市集", "零號碼頭", "鏽蝕街", "量子廣場"))
_E_VERTS, _E_STOPS = square(600.0, ("雲端廣場", "浮光橋", "天秤塔", "極光台"))
LINES = (
    dict(name="地心線", kind="underground", hue=0.5, yf=-8.0, speed=22.0, trains=1, cars=3,
         verts=_U_VERTS, stops=_U_STOPS),
    dict(name="天際線", kind="elevated", hue=0.83, yf=9.0, speed=26.0, trains=2, cars=3,
         verts=_E_VERTS, stops=_E_STOPS),
    # Nexus plaza (south edge) -> Helix Spire (east side) -> Neon Park -> Aurora Tower (west side).
    # Tower-side stations pull their skybridge in (land_b 11) to stay clear of the 48 m towers.
    dict(name="三塔線", kind="elevated", hue=0.12, yf=9.0, speed=26.0, trains=3, cars=3,
         verts=((360.0, 120.0), (-280.0, 120.0), (-280.0, 440.0), (-440.0, 440.0), (-440.0, -120.0),
                (200.0, -120.0), (200.0, -360.0), (360.0, -360.0)),
         stops=((0.0, 120.0, "NEXUS 塔前", 14.0), (-280.0, 330.0, "HELIX 螺旋塔", 11.0),
                (-440.0, 80.0, "霓虹公園", 14.0), (200.0, -240.0, "AURORA 極光塔", 11.0))),
)
KIND_LABEL = {"underground": "地下", "elevated": "高架"}

CURVE_R = 24.0                     # corner radius: the curve stays within the intersection / road width
ARC_PIECES = 12
CURVE_SPEED = 12.0
CAR_LEN, CAR_GAP, CAR_HALF_W, CAR_H = 14.0, 1.0, 1.7, 2.6
DOORS = (-3.5, 3.5)
DOOR_HALF = 0.8
DWELL, DOOR_TIME = 15.0, 1.5
ACCEL, BRAKE = 1.3, 1.3
ROT_FLOATS = BOX_FLOATS + 1        # box instance + yaw

Station = namedtuple("Station", "line index name kind s yf platform entrance block")


class Frame:
    """A straight side: center c, direction f, inner normal n = f turned left (toward the inside
    of the loop), half length h (corner to corner) and the turn into the next side: +1 toward
    the inside (convex corner), -1 away from it (concave corner)."""

    def __init__(self, c, f, h, turn=1):
        self.c, self.f, self.h, self.turn = c, f, h, turn
        self.n = (-f[1], f[0])

    def shifted(self, a):
        """The same side with a = 0 moved to a (station builders work around a = 0)."""
        return Frame(self.world(a, 0.0), self.f, self.h, self.turn)

    def world(self, a, b):
        return (self.c[0] + self.f[0] * a + self.n[0] * b, self.c[1] + self.f[1] * a + self.n[1] * b)

    def bounds(self, a0, b0, a1, b1):
        xa, za = self.world(a0, b0)
        xb, zb = self.world(a1, b1)
        return min(xa, xb), min(za, zb), max(xa, xb), max(za, zb)

    def local(self, x, z):
        dx, dz = x - self.c[0], z - self.c[1]
        return dx * self.f[0] + dz * self.f[1], dx * self.n[0] + dz * self.n[1]


def yaw_of(h):
    """Box yaw whose local +x points along heading h (local +z then points to (-h_z, h_x))."""
    return math.atan2(-h[1], h[0])


class PolyPath:
    """Closed rectilinear loop through `verts` (interior on the left of travel, i.e. on n):
    per side a straight of length 2h - 2rc, then a quarter arc into the next side."""

    def __init__(self, verts, rc=CURVE_R):
        self.rc = rc
        m = len(verts)
        area = sum(verts[i][0] * verts[(i + 1) % m][1] - verts[(i + 1) % m][0] * verts[i][1] for i in range(m))
        assert area > 0, "loop vertices must run with the inside on the left (n side)"
        self.frames, self.starts, self.straights = [], [], []
        s = 0.0
        self.arc = math.pi * rc / 2
        for k in range(m):
            (ax, az), (bx, bz), (nx, nz) = verts[k], verts[(k + 1) % m], verts[(k + 2) % m]
            L = math.hypot(bx - ax, bz - az)
            f = ((bx - ax) / L, (bz - az) / L)
            L2 = math.hypot(nx - bx, nz - bz)
            f2 = ((nx - bx) / L2, (nz - bz) / L2)
            turn = 1 if (f2[0], f2[1]) == (-f[1], f[0]) else -1
            fr = Frame(((ax + bx) / 2, (az + bz) / 2), f, L / 2, turn)
            self.frames.append(fr)
            self.starts.append(s)
            self.straights.append(L - 2 * rc)
            s += L - 2 * rc + self.arc
        self.P = s

    def _side(self, s):
        s %= self.P
        k = bisect.bisect_right(self.starts, s) - 1
        return k, s - self.starts[k]

    def s_of(self, k, a):
        """Perimeter position of the point a along straight k."""
        return self.starts[k] + a + self.frames[k].h - self.rc

    def in_arc(self, s):
        k, t = self._side(s)
        return t >= self.straights[k]

    def dist_to_curve(self, s):
        """Distance from s to the start of the next curve (0 while on a curve)."""
        k, t = self._side(s)
        return max(self.straights[k] - t, 0.0)

    def at(self, s):
        """(x, z, heading, inner normal) at perimeter position s."""
        k, t = self._side(s)
        fr = self.frames[k]
        if t < self.straights[k]:
            x, z = fr.world(-fr.h + self.rc + t, 0.0)
            h = fr.f
        else:
            phi = (t - self.straights[k]) / self.rc
            x, z, h = arc_point(fr, self.rc, phi, 0.0)
        return x, z, h, (-h[1], h[0])

    def project(self, x, z):
        """Perimeter position of a point near a straight section, else None."""
        for k, fr in enumerate(self.frames):
            a, b = fr.local(x, z)
            if abs(a) <= fr.h - self.rc and abs(b) < 2.3:
                return self.s_of(k, a)
        return None

    def locate(self, x, z):
        """(side, a) of the straight point nearest to a point on the line."""
        best = None
        for k, fr in enumerate(self.frames):
            a, b = fr.local(x, z)
            if abs(a) <= fr.h - self.rc and (best is None or abs(b) < best[2]):
                best = (k, a, abs(b))
        return best[0], best[1]


def arc_point(fr, rc, phi, b):
    """Point at angle phi along the curve after side `fr`, offset b toward the inside; and heading.
    A concave corner (turn -1) curves away from the inside: its center lies on the -n side."""
    f, n, sg = fr.f, fr.n, fr.turn
    cx, cz = fr.world(fr.h - rc, sg * rc)              # curve center
    r = rc - sg * b
    sp, cp = math.sin(phi), math.cos(phi)
    x = cx + r * (f[0] * sp - sg * n[0] * cp)
    z = cz + r * (f[1] * sp - sg * n[1] * cp)
    h = (f[0] * cp + sg * n[0] * sp, f[1] * cp + sg * n[1] * sp)
    return x, z, h


def _split(a0, a1, gaps):
    """[a0, a1] minus the (g0, g1) gaps."""
    out, x = [], a0
    for g0, g1 in sorted(gaps):
        out.append((x, g0))
        x = g1
    out.append((x, a1))
    return [(p, q) for p, q in out if q > p]


class MetroStatic:
    def __init__(self):
        self.boxes, self.colliders, self.quads, self.rot = [], [], [], []
        self.holes, self.stations = [], []
        self.skip_blocks = set()

    def add(self, fr, a0, b0, a1, b1, y0, y1, kind, hue=0.0, extra=0.0, collide=False):
        x0, z0, x1, z1 = fr.bounds(a0, b0, a1, b1)
        self.boxes.append(box_bounds(x0, y0, z0, x1, y1, z1, kind, hue, extra))
        if collide:
            self.colliders.append((x0, y0, z0, x1, y1, z1))

    def add_arc(self, fr, b0, b1, y0, y1, kind, hue=0.0, extra=0.0, collide=False):
        """A curved strip (lateral range b0..b1) around the corner after side `fr`, as rotated boxes."""
        rc = CURVE_R
        dphi = (math.pi / 2) / ARC_PIECES
        bc, width = (b0 + b1) / 2, b1 - b0
        for i in range(ARC_PIECES):
            x, z, h = arc_point(fr, rc, (i + 0.5) * dphi, bc)
            length = max(rc - fr.turn * bc, 0.5) * dphi * 1.08 + 0.05
            yaw = yaw_of(h)
            self.rot.append([x, y0, z, length, y1 - y0, width, 0.0, kind, hue, extra, yaw])
            if collide:                                  # flat pieces only: AABB of the rotated rectangle
                c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
                hx, hz = c * length / 2 + s * width / 2, s * length / 2 + c * width / 2
                self.colliders.append((x - hx, y0, z - hz, x + hx, y1, z + hz))

    def sign(self, fr, a, b, y, half_w, half_h, hue, inten=1.3, seed=0.0):
        x, z = fr.world(a, b)
        self.quads.append(quad((x, y, z), (fr.f[0] * half_w, 0.0, fr.f[1] * half_w), (0.0, half_h, 0.0),
                               C.Q_HOLO, hue, inten, seed))

    # ------------------------------------------------------------------ underground
    def underground_side(self, fr, yf, hue, stop_as):
        P, E = C.K_PANEL, C.K_EMISSIVE
        ft, ceil0 = yf - 1.2, yf + 3.4                           # track pit floor, tunnel ceiling
        end = fr.h - CURVE_R
        self.add(fr, -end, -2.8, end, 2.8, ft - 0.4, ft, P, hue, collide=True)
        for a0, a1 in _split(-end, end, [(a - 28.3, a + 28.3) for a in stop_as]):
            self.add(fr, a0, -2.8, a1, -2.5, ft, ceil0, P, hue, collide=True)
            self.add(fr, a0, 2.5, a1, 2.8, ft, ceil0, P, hue, collide=True)
            self.add(fr, a0, -2.8, a1, 2.8, ceil0, ceil0 + 0.4, P, hue, collide=True)
            self.add(fr, a0, -2.5, a1, -2.45, yf + 1.8, yf + 1.9, E, hue, 1.5)
        # curved tunnel into the next side
        self.add_arc(fr, -2.8, 2.8, ft - 0.4, ft, P, hue, collide=True)
        self.add_arc(fr, -2.8, 2.8, ceil0, ceil0 + 0.4, P, hue)
        self.add_arc(fr, -2.8, -2.5, ft, ceil0, P, hue)
        self.add_arc(fr, 2.5, 2.8, ft, ceil0, P, hue)
        self.add_arc(fr, -2.5, -2.45, yf + 1.8, yf + 1.9, E, hue, 1.5)

    def underground_station(self, fr, yf, hue, seed, side_doors=()):
        """side_doors: (a0, a1) of further openings in the platform's back wall (mall / undercity)."""
        P, E, F, K = C.K_PANEL, C.K_EMISSIVE, C.K_FLOOR, C.K_SHOP_CEIL
        ft, top = yf - 1.2, yf + 6.0
        self.add(fr, -28, 1.9, 28, 7.0, ft, yf, F, hue, collide=True)                    # platform
        self.add(fr, -28, 1.9, 28, 2.2, yf, yf + 0.02, E, 0.13, 2.0)                    # edge line
        self.add(fr, -28.3, -3.3, 28.3, -3.0, ft, top, P, hue, collide=True)            # track-side wall
        gaps = [(-1.5, 1.5)] + list(side_doors)                                          # back wall + passages
        for a0, a1 in _split(-28.3, 28.3, gaps):
            self.add(fr, a0, 7.0, a1, 7.3, yf, top, P, hue, collide=True)
        for a0, a1 in gaps:
            self.add(fr, a0, 7.0, a1, 7.3, yf + 3.0, top, P, hue, collide=True)
        for a0, a1 in ((-28.3, -28.0), (28.0, 28.3)):                                     # ends with tunnel mouths
            self.add(fr, a0, 2.5, a1, 7.3, ft, top, P, hue, collide=True)
            self.add(fr, a0, -3.3, a1, -2.5, ft, top, P, hue, collide=True)
            self.add(fr, a0, -2.5, a1, 2.5, yf + 3.4, top, P, hue, collide=True)
        self.add(fr, -28.3, -3.3, 28.3, 7.3, top, top + 0.4, K, hue, 0.7)               # ceiling
        for a in (-18.0, -8.0, 8.0, 18.0):
            self.add(fr, a - 1.2, 5.6, a + 1.2, 6.3, yf, yf + 0.45, P, hue, collide=True)
        self.sign(fr, 0.0, -2.95, yf + 3.6, 6.0, 0.8, hue, seed=seed)
        # passage and straight stairs up into the station block
        self.add(fr, -1.5, 7.3, 1.5, 11.0, yf - 0.6, yf, F, hue, collide=True)
        self.add(fr, -1.5, 7.3, 1.5, 11.0, yf + 3.0, yf + 3.4, K, hue, 0.7, collide=True)
        self.add(fr, -1.8, 7.3, -1.5, 11.0, yf, yf + 3.4, P, hue, collide=True)
        self.add(fr, 1.5, 7.3, 1.8, 11.0, yf, yf + 3.4, P, hue, collide=True)
        n = int(round(-yf / 0.2))
        for i in range(1, n + 1):
            t = yf + 0.2 * i
            self.add(fr, -1.5, 11.0 + 0.3 * (i - 1), 1.5, 11.0 + 0.3 * i, t - 0.3, t, C.K_DOOR, hue, collide=True)
        end = 11.0 + 0.3 * n
        self.add(fr, -1.5, 11.0, 1.5, end, yf - 0.6, yf, P, hue)
        self.add(fr, -1.8, 11.0, -1.5, end + 0.3, yf, 1.0, P, hue, collide=True)         # shaft walls + railing
        self.add(fr, 1.5, 11.0, 1.8, end + 0.3, yf, 1.0, P, hue, collide=True)
        self.add(fr, -1.8, 10.7, 1.8, 11.0, yf + 3.0, 1.0, P, hue, collide=True)
        # entrance canopy on the street
        self.add(fr, -2.4, 10.6, 2.4, end + 1.0, 3.2, 3.45, K, hue, 0.8)
        self.add(fr, -2.45, 10.55, 2.45, end + 1.05, 3.45, 3.5, E, hue, 2.5)
        for a, b in ((-2.3, 10.7), (2.3, 10.7), (-2.3, end + 0.9), (2.3, end + 0.9)):
            self.add(fr, a - 0.08, b - 0.08, a + 0.08, b + 0.08, 0.0, 3.2, P, hue, collide=True)
        self.sign(fr, 0.0, end + 1.1, 4.2, 2.2, 0.5, hue, 1.6, seed + 1)
        self.holes.append(fr.bounds(-1.5, 11.0, 1.5, end))
        return fr.bounds(-28, 1.9, 28, 7.0), fr.world(0.0, end + 2.0)

    # ------------------------------------------------------------------ elevated
    def elevated_side(self, fr, yf, hue, stop_as):
        P, E = C.K_PANEL, C.K_EMISSIVE
        top, bot = yf - 0.6, yf - 1.4                             # deck
        end = fr.h - CURVE_R
        self.add(fr, -end, -2.5, end, 2.5, bot, top, P, hue, collide=True)
        self.add(fr, -end, -2.8, end, -2.5, top, top + 1.0, P, hue, collide=True)
        for a0, a1 in _split(-end, end, [(a - 25.0, a + 25.0) for a in stop_as]):
            self.add(fr, a0, 2.5, a1, 2.8, top, top + 1.0, P, hue, collide=True)
        for b in (-0.75, 0.75):
            self.add(fr, -end, b - 0.06, end, b + 0.06, top, top + 0.08, E, hue, 1.5)
        self.add(fr, -end, -2.8, end, -2.7, top + 1.0, top + 1.08, E, hue, 2.5)
        # mid-block piers: block centers (multiples of the pitch) along the road
        ax = 0 if fr.f[0] != 0 else 1
        c_al, sg = fr.c[ax], fr.f[ax]
        lo, hi = c_al - (fr.h - 20.0), c_al + (fr.h - 20.0)
        P_ = C.BLOCK_PITCH
        for m in np.arange(math.ceil(min(lo, hi) / P_) * P_, max(lo, hi) + 1e-6, P_):
            a = (m - c_al) * sg
            self.add(fr, a - 0.6, -0.6, a + 0.6, 0.6, 0.0, bot, P, hue, collide=True)
        # curve into the next side
        self.add_arc(fr, -2.5, 2.5, bot, top, P, hue, collide=True)
        self.add_arc(fr, -2.8, -2.5, top, top + 1.0, P, hue)
        self.add_arc(fr, 2.5, 2.8, top, top + 1.0, P, hue)
        for b in (-0.75, 0.75):
            self.add_arc(fr, b - 0.06, b + 0.06, top, top + 0.08, E, hue, 1.5)
        self.add_arc(fr, -2.8, -2.7, top + 1.0, top + 1.08, E, hue, 2.5)

    def elevated_station(self, fr, yf, hue, seed, land_b=14.0):
        """Station around a = 0 of `fr`; the skybridge reaches b = land_b, where a 3 m landing
        and the stairs down (running along +a) start."""
        P, E, F, K = C.K_PANEL, C.K_EMISSIVE, C.K_FLOOR, C.K_SHOP_CEIL
        rail = 1.1
        self.add(fr, -25, 1.9, 25, 6.5, yf - 1.0, yf, F, hue, collide=True)               # platform
        self.add(fr, -25, 1.9, 25, 2.2, yf, yf + 0.02, E, 0.13, 2.0)
        for a0, a1 in _split(-25.0, 25.0, [(-1.5, 1.5)]):
            self.add(fr, a0, 6.5, a1, 6.7, yf, yf + rail, P, hue, collide=True)
        self.add(fr, -25.2, 1.9, -25.0, 6.7, yf, yf + rail, P, hue, collide=True)
        self.add(fr, 25.0, 1.9, 25.2, 6.7, yf, yf + rail, P, hue, collide=True)
        self.add(fr, -25, 1.9, 25, 6.7, yf + 3.4, yf + 3.7, K, hue, 0.7)                 # canopy
        self.add(fr, -25.05, 6.6, 25.05, 6.75, yf + 3.7, yf + 3.75, E, hue, 2.5)
        for a in (-24.0, -12.0, 12.0, 24.0):
            self.add(fr, a - 0.1, 6.45, a + 0.1, 6.65, yf, yf + 3.4, P, hue, collide=True)
        for a in (-18.0, -8.0, 8.0, 18.0):
            self.add(fr, a - 1.2, 5.3, a + 1.2, 6.1, yf, yf + 0.45, P, hue, collide=True)
        self.sign(fr, 0.0, 4.3, yf + 4.4, 5.0, 0.7, hue, seed=seed)
        # skybridge over the lanes and sidewalk, landing, stairs down into the block
        L = land_b
        self.add(fr, -1.5, 6.5, 1.5, L, yf - 0.6, yf, F, hue, collide=True)
        self.add(fr, -1.7, 6.7, -1.5, L, yf, yf + rail, P, hue, collide=True)
        self.add(fr, 1.5, 6.7, 1.7, L, yf, yf + rail, P, hue, collide=True)
        self.add(fr, -1.5, L, 1.5, L + 3.0, yf - 0.6, yf, F, hue, collide=True)
        self.add(fr, -1.7, L, -1.5, L + 3.2, yf, yf + rail, P, hue, collide=True)
        self.add(fr, -1.7, L + 3.0, 1.5, L + 3.15, yf, yf + rail, P, hue, collide=True)
        self.add(fr, -0.3, L + 1.2, 0.3, L + 1.8, 0.0, yf - 0.6, P, hue, collide=True)
        n = int(round(yf / 0.2))
        for i in range(1, n + 1):
            t = yf - 0.2 * i
            a0, a1 = 1.5 + 0.3 * (i - 1), 1.5 + 0.3 * i
            self.add(fr, a0, L, a1, L + 3.0, t - 0.3, t, C.K_DOOR, hue, collide=True)
            self.add(fr, a0, L - 0.15, a1, L, t, t + rail, P, hue, collide=True)
            self.add(fr, a0, L + 3.0, a1, L + 3.15, t, t + rail, P, hue, collide=True)
        foot = 1.5 + 0.3 * n
        self.sign(fr, foot - 1.0, L - 0.2, 3.0, 1.6, 0.45, hue, 1.6, seed + 1)
        return fr.bounds(-25, 1.9, 25, 6.5), fr.world(foot + 1.5, L + 1.5)


def line_stops(path, line):
    """(side, a, name, land_b) of each stop of a line, in travel order."""
    stops = [(*path.locate(x, z), name, lb) for x, z, name, lb in line["stops"]]
    return sorted(stops, key=lambda st: path.s_of(st[0], st[1]))


def build_metro():
    m = MetroStatic()
    for li, line in enumerate(LINES):
        yf, hue = line["yf"], line["hue"]
        path = PolyPath(line["verts"])
        stops = line_stops(path, line)
        for k, fr in enumerate(path.frames):
            stop_as = [a for side, a, _, _ in stops if side == k]
            if line["kind"] == "underground":
                m.underground_side(fr, yf, hue, stop_as)
            else:
                m.elevated_side(fr, yf, hue, stop_as)
        for k, (side, a, name, land_b) in enumerate(stops):
            fr = path.frames[side].shifted(a)
            seed = li * 10.0 + k
            if line["kind"] == "underground":
                doors = [C.MALL_DOOR, C.UNDERCITY_DOOR_MALL] if name == C.MALL_STATION else [C.UNDERCITY_DOOR]
                platform, entrance = m.underground_station(fr, yf, hue, seed, doors)
            else:
                platform, entrance = m.elevated_station(fr, yf, hue, seed, land_b)
            bx, bz = fr.world(0.0, 40.0)
            block = (int(round(bx / C.BLOCK_PITCH)), int(round(bz / C.BLOCK_PITCH)))
            m.skip_blocks.add(block)
            m.stations.append(Station(li, k, name, line["kind"], path.s_of(side, a), yf,
                                      platform, entrance, block))
    m.boxes = np.array(m.boxes, "f4").reshape(-1, BOX_FLOATS)
    m.quads = np.array(m.quads, "f4").reshape(-1, QUAD_FLOATS)
    m.rot = np.array(m.rot, "f4").reshape(-1, ROT_FLOATS)
    return m


# ---------------------------------------------------------------------------- trains
def _car_template(hue):
    """Local parts of one car: (u0, v0, u1, v1, y0, y1, kind, hue, extra, collide), y relative to the floor.
    u runs along the car (forward), v toward the platform side."""
    P, T, E = C.K_PANEL, C.K_TRAIN, C.K_EMISSIVE
    L, W, H = CAR_LEN / 2, CAR_HALF_W, CAR_H
    t = [(-L, -W, L, W, -0.5, 0.0, P, 0.0, 0.0, True),                     # floor
         (-L, -W, L, W, H, H + 0.4, T, hue, 1.0, True),                     # roof
         (-L, -W, L, -W + 0.15, 0.0, H, T, hue, 0.0, True),                 # outer wall
         (-L, -W, -L + 0.15, W, 0.0, H, T, hue, 0.0, True),                 # end walls
         (L - 0.15, -W, L, W, 0.0, H, T, hue, 0.0, True),
         (-L + 0.5, -W + 0.4, L - 0.5, W - 0.4, -0.9, -0.5, P, 0.0, 0.0, False),   # undercarriage
         (-6.0, -W + 0.15, 6.0, -W + 0.65, 0.0, 0.45, P, hue, 0.0, True),   # benches
         (-2.4, W - 0.65, 2.4, W - 0.15, 0.0, 0.45, P, hue, 0.0, True),
         (-6.0, -0.3, 6.0, 0.3, H - 0.1, H, E, -1.0, 2.2, False)]           # ceiling light
    for u in (-1.2, 1.2):
        t.append((u - 0.05, -0.05, u + 0.05, 0.05, 0.0, H, E, hue, 2.0, False))
    # inner (platform-side) wall with two door openings
    edges = [-L] + [x for c in DOORS for x in (c - DOOR_HALF, c + DOOR_HALF)] + [L]
    for u0, u1 in zip(edges[0::2], edges[1::2]):
        t.append((u0, W - 0.15, u1, W, 0.0, H, T, hue, 0.0, True))
    for c in DOORS:
        t.append((c - DOOR_HALF, W - 0.15, c + DOOR_HALF, W, 2.2, H, T, hue, 0.0, True))
    return np.array(t, dtype=object)


def _transform(parts, cx, cz, f, n, yf):
    """Local (u, v) boxes -> world AABBs (x0, y0, z0, x1, y1, z1); exact only for axis-aligned cars."""
    u0, v0, u1, v1 = (parts[:, i].astype(float) for i in range(4))
    xa, za = cx + f[0] * u0 + n[0] * v0, cz + f[1] * u0 + n[1] * v0
    xb, zb = cx + f[0] * u1 + n[0] * v1, cz + f[1] * u1 + n[1] * v1
    return np.stack([np.minimum(xa, xb), yf + parts[:, 4].astype(float), np.minimum(za, zb),
                     np.maximum(xa, xb), yf + parts[:, 5].astype(float), np.maximum(za, zb)], 1)


def _rotated(cx, cz, f, n, yf, uc, vc, su, sv, y0, height, seed, kind, hue, extra):
    """Rotated instances for local boxes centred at (uc, vc) of a car at (cx, cz) heading f."""
    m = len(uc)
    b = np.zeros((m, ROT_FLOATS), "f4")
    b[:, 0] = cx + f[0] * uc + n[0] * vc
    b[:, 1] = yf + y0
    b[:, 2] = cz + f[1] * uc + n[1] * vc
    b[:, 3] = su
    b[:, 4] = height
    b[:, 5] = sv
    b[:, 6] = seed
    b[:, 7] = kind
    b[:, 8] = hue
    b[:, 9] = extra
    b[:, 10] = yaw_of(f)
    return b


class Train:
    def __init__(self, line, li, path, s, next_station, phase):
        self.line, self.li, self.path = line, li, path
        self.s = s
        self.v = 0.0
        self.next = next_station
        self.state, self.timer, self.door = "dwell", phase, 1.0
        self.frames = []
        self.update_frames()

    @property
    def P(self):
        return self.path.P

    def car_offsets(self):
        n = self.line["cars"]
        step = CAR_LEN + CAR_GAP
        return [((n - 1) / 2 - j) * step for j in range(n)]          # front car first

    def update_frames(self):
        self.frames = [self.path.at(self.s + off) for off in self.car_offsets()]

    @property
    def half_len(self):
        return (self.line["cars"] * (CAR_LEN + CAR_GAP) - CAR_GAP) / 2

    def on_curve(self, ahead=0.0):
        """Is any part of the train (optionally looking `ahead` metres further) on a curve?"""
        span = 2 * self.half_len + ahead
        return any(self.path.in_arc(self.s - self.half_len + d) for d in np.arange(0.0, span + 0.1, 5.0))


class Trains:
    def __init__(self, stations):
        self.stations = stations
        self.paths = [PolyPath(line["verts"]) for line in LINES]
        self.stop_s = [[s.s for s in stations if s.line == li] for li in range(len(LINES))]
        self.trains = []
        self.templates = {}
        for li, line in enumerate(LINES):
            self.templates[li] = _car_template(line["hue"])
            st = [s for s in stations if s.line == li]
            for t in range(line["trains"]):
                k = (t * len(st)) // line["trains"]
                self.trains.append(Train(line, li, self.paths[li], st[k].s, k,
                                         DWELL * (0.3 + 0.6 * t / max(1, line["trains"]))))

    def station_s(self, li, k):
        return self.stop_s[li][k]

    # ------------------------------------------------------------------ simulation
    def _curve_limit(self, tr):
        """Speed allowed now so that the whole train is at CURVE_SPEED while on a curve."""
        if tr.on_curve():
            return CURVE_SPEED
        dist = tr.path.dist_to_curve(tr.s + tr.half_len)       # front of the train to the next curve
        return math.sqrt(CURVE_SPEED ** 2 + 2 * BRAKE * max(dist, 0.0))

    def update(self, dt, player_pos=None, riding=None):
        for tr in self.trains:
            line, P = tr.line, tr.P
            if tr.state == "run":
                target = self.station_s(tr.li, tr.next)
                dist = (target - tr.s) % P
                v_des = min(line["speed"], math.sqrt(2 * BRAKE * dist), self._curve_limit(tr))
                # keep clear of the train ahead and of a player standing on the track
                for other in self.trains:
                    if other is not tr and other.li == tr.li:
                        gap = (other.s - tr.s) % P - tr.half_len - other.half_len
                        v_des = min(v_des, math.sqrt(2 * BRAKE * max(gap - 40.0, 0.0)))
                ps = None
                if riding is None and player_pos is not None and abs(player_pos[1] - line["yf"] - 0.7) < 2.3:
                    ps = tr.path.project(player_pos[0], player_pos[2])
                if ps is not None:
                    gap = (ps - (tr.s + tr.half_len)) % P
                    if gap < 400.0:
                        v_des = min(v_des, math.sqrt(2 * 4.0 * max(gap - 6.0, 0.0)))
                if tr.v < v_des:
                    tr.v = min(v_des, tr.v + ACCEL * dt)
                else:
                    tr.v = max(v_des, tr.v - 4.0 * dt)
                step = tr.v * dt
                if dist <= max(step, 0.02) and dist < 1.0:
                    tr.s = target
                    tr.v = 0.0
                    tr.state = "opening"
                else:
                    tr.s = (tr.s + min(step, dist)) % P
            elif tr.state == "opening":
                tr.door = min(1.0, tr.door + dt / DOOR_TIME)
                if tr.door >= 1.0:
                    tr.state, tr.timer = "dwell", DWELL
            elif tr.state == "dwell":
                tr.timer -= dt
                if tr.timer <= 0.0:
                    tr.state = "closing"
            elif tr.state == "closing":
                tr.door = max(0.0, tr.door - dt / DOOR_TIME)
                if tr.door <= 0.0:
                    tr.state = "run"
                    tr.next = (tr.next + 1) % len(self.stop_s[tr.li])
            tr.update_frames()

    # ------------------------------------------------------------------ riding
    def locate(self, pos):
        """(train, car, u, v, dy, f) if pos is inside a car."""
        for ti, tr in enumerate(self.trains):
            yf = tr.line["yf"]
            if not (yf - 0.1 <= pos[1] <= yf + CAR_H):
                continue
            for j, (x, z, f, n) in enumerate(tr.frames):
                dx, dz = pos[0] - x, pos[2] - z
                u, v = dx * f[0] + dz * f[1], dx * n[0] + dz * n[1]
                if abs(u) < CAR_LEN / 2 - 0.1 and abs(v) < CAR_HALF_W - 0.1:
                    return ti, j, u, v, pos[1] - yf, f
        return None

    def carry(self, ride):
        """New world position and yaw change for a rider located before this frame's update."""
        ti, j, u, v, dy, f_old = ride
        tr = self.trains[ti]
        x, z, f, n = tr.frames[j]
        pos = (x + f[0] * u + n[0] * v, tr.line["yf"] + dy, z + f[1] * u + n[1] * v)
        ang = lambda d: math.atan2(d[0], -d[1])
        dyaw = (ang(f) - ang(f_old) + math.pi) % (2 * math.pi) - math.pi
        return pos, dyaw

    def local_colliders(self, tr, j):
        """Collidable parts of car j in its own frame: x = along the car, z = toward the doors."""
        parts = self._parts(tr, j, tr.door)
        yf = tr.line["yf"]
        return [(float(p[0]), yf + float(p[4]), float(p[1]), float(p[2]), yf + float(p[5]), float(p[3]))
                for p in parts if p[9]]

    def ride_step(self, player, dt, inp, ride, empty_world):
        """Run the player's walking physics inside the car's frame, then map back to the world."""
        ti, j = ride[0], ride[1]
        tr = self.trains[ti]
        x, z, f, n = tr.frames[j]
        rot = math.atan2(f[0], -f[1]) - math.pi / 2            # world yaw of the car's local +x, minus +x's yaw
        p, v = player.pos, player.vel
        dx, dz = p[0] - x, p[2] - z
        p[0], p[2] = dx * f[0] + dz * f[1], dx * n[0] + dz * n[1]
        v[0], v[2] = v[0] * f[0] + v[2] * f[1], v[0] * n[0] + v[2] * n[1]
        player.yaw -= rot
        player.update(dt, inp, empty_world, self.local_colliders(tr, j))
        u, w = p[0], p[2]
        p[0], p[2] = x + f[0] * u + n[0] * w, z + f[1] * u + n[1] * w
        vu, vw = v[0], v[2]
        v[0], v[2] = f[0] * vu + n[0] * vw, f[1] * vu + n[1] * vw
        player.yaw += rot

    # ------------------------------------------------------------------ output
    def _parts(self, tr, j, door):
        parts = self.templates[tr.li]
        hue = tr.line["hue"]
        extra = []
        W = CAR_HALF_W
        for c in DOORS:
            o = DOOR_HALF * door
            extra.append((c - DOOR_HALF - o, W - 0.25, c - o, W - 0.15, 0.0, 2.2, C.K_DOOR, hue, 0.0, True))
            extra.append((c + o, W - 0.25, c + DOOR_HALF + o, W - 0.15, 0.0, 2.2, C.K_DOOR, hue, 0.0, True))
        L = CAR_LEN / 2
        if j == 0:
            extra += [(L, -1.2, L + 0.05, -0.6, 0.4, 0.7, C.K_EMISSIVE, -1.0, 6.0, False),
                      (L, 0.6, L + 0.05, 1.2, 0.4, 0.7, C.K_EMISSIVE, -1.0, 6.0, False)]
        if j == tr.line["cars"] - 1:
            extra += [(-L - 0.05, -1.2, -L, -0.6, 0.4, 0.7, C.K_EMISSIVE, 0.0, 4.0, False),
                      (-L - 0.05, 0.6, -L, 1.2, 0.4, 0.7, C.K_EMISSIVE, 0.0, 4.0, False)]
        return np.concatenate([parts, np.array(extra, dtype=object)])

    def instances(self, eye, radius=1500.0):
        """Rotated box instances (ROT_FLOATS each) for every car and its passengers."""
        out = []
        for ti, tr in enumerate(self.trains):
            yf = tr.line["yf"]
            for j, (x, z, f, n) in enumerate(tr.frames):
                if (x - eye[0]) ** 2 + (z - eye[2]) ** 2 > radius ** 2:
                    continue
                parts = self._parts(tr, j, tr.door)
                u0, v0, u1, v1, y0, y1 = (parts[:, i].astype(float) for i in range(6))
                out.append(_rotated(x, z, f, n, yf, (u0 + u1) / 2, (v0 + v1) / 2, u1 - u0, v1 - v0,
                                    y0, y1 - y0, ti * 10 + j, parts[:, 6].astype(float),
                                    parts[:, 7].astype(float), parts[:, 8].astype(float)))
                out.append(self._riders(ti, j, x, z, f, n, yf))
        return np.concatenate(out) if out else np.zeros((0, ROT_FLOATS), "f4")

    @staticmethod
    def _riders(ti, j, x, z, f, n, yf):
        """A few standing passengers holding on near the poles (fixed per car), rotated with it."""
        spots = ((-5.0, -0.7), (1.6, 0.3), (5.2, 0.9)) if (ti + j) % 2 == 0 else ((-1.6, -0.4), (4.5, -0.8))
        m = len(spots)
        lu = np.array([s[0] for s in spots])
        lv = np.array([s[1] for s in spots])
        boxes = person_boxes(lu, 0.0, lv, np.ones(m, int), np.ones(m), np.zeros(m, bool), np.zeros(m),
                             np.ones(m), np.array(C.NEON_HUES)[(np.arange(m) + j) % 7],
                             np.arange(m) * 37.0 + ti * 11 + j, np.zeros(m))
        return _rotated(x, z, f, n, yf, boxes[:, 0], boxes[:, 2], boxes[:, 3], boxes[:, 5], boxes[:, 1],
                        boxes[:, 4], boxes[:, 6], boxes[:, 7], boxes[:, 8], boxes[:, 9])

    def colliders_near(self, pos, radius=25.0):
        """World AABB colliders of nearby cars that are axis-aligned (i.e. on a straight, e.g. at a station)."""
        out = []
        for tr in self.trains:
            yf = tr.line["yf"]
            if abs(pos[1] - yf) > 6.0:
                continue
            for j, (x, z, f, n) in enumerate(tr.frames):
                if abs(x - pos[0]) > radius or abs(z - pos[2]) > radius or abs(f[0] * f[1]) > 1e-6:
                    continue
                parts = self._parts(tr, j, tr.door)
                wb = _transform(parts, x, z, f, n, yf)
                out += [tuple(map(float, b)) for b, p in zip(wb, parts) if p[9]]
        return out

    def car_boxes_near(self, pos, radius=60.0):
        """Bounding boxes of nearby cars (to keep rain out of them)."""
        out = []
        for tr in self.trains:
            yf = tr.line["yf"]
            for x, z, f, n in tr.frames:
                if abs(x - pos[0]) < radius and abs(z - pos[2]) < radius:
                    hx = abs(f[0]) * CAR_LEN / 2 + abs(n[0]) * CAR_HALF_W
                    hz = abs(f[1]) * CAR_LEN / 2 + abs(n[1]) * CAR_HALF_W
                    out.append((x - hx, yf - 0.5, z - hz, x + hx, yf + CAR_H + 0.4, z + hz))
        return out

    # ------------------------------------------------------------------ info for the HUD
    def eta(self, st):
        """Seconds until a train has its doors open at station st (0 = doors open now)."""
        best = None
        for tr in self.trains:
            if tr.li != st.line:
                continue
            if tr.state != "run" and tr.next == st.index:
                return 0.0 if tr.state in ("opening", "dwell") else None
            dist = (st.s - tr.s) % tr.P
            stops = sum(1 for s in self.stop_s[tr.li] if 0.5 < (s - tr.s) % tr.P < dist - 0.5)
            t = dist / (0.75 * tr.line["speed"]) + stops * (DWELL + 2 * DOOR_TIME)
            if tr.state != "run":
                t += max(tr.timer, 0.0) + DOOR_TIME
            best = t if best is None else min(best, t)
        return best
