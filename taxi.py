"""Air taxis between stands on the megatower roofs and in parks / plazas.

Every stand has its own taxi parked in its home slot; a taxi that brought a passenger
elsewhere lands in that stand's visitor slot and flies home empty once the passenger is out.
A flight climbs vertically to a cruise altitude that clears everything along the way, turns,
cruises straight, then descends vertically onto the pad. Taxis are rotated boxes (same
pipeline as the metro cars) with glass quads for windows; the player rides seated.
"""
import math

import numpy as np

import config as C
from geometry import box_bounds, quad

ROT_FLOATS = 11
V_SPEED, H_SPEED, ACCEL = 200.0, 90.0, 20.0
TURN_RATE = 1.2                       # rad/s
CLEARANCE = 30.0                      # above the highest obstacle along the route
CORRIDOR = 30.0                       # obstacles this close to the route count
SLOT = 3.2                            # home slot at stand x - SLOT, visitor slot at x + SLOT
RETURN_DELAY = 3.0
L, W = 2.4, 1.2                       # half length / half width of the hull
FLOOR = 0.8                           # cabin floor above the pad
ROOF = 3.0
HUES = (0.12, 0.5, 0.83, 0.92, 0.55, 0.97, 0.33, 0.75)

# local parts (u0, v0, u1, v1, y0, y1, kind, hue (None = taxi hue), extra); u forward, v left
_PARTS = [
    (-L, -W, L, W, 0.35, FLOOR, C.K_VEHICLE, None, 1.0),                       # hull with head/tail lamps
    (-1.9, -1.05, 1.9, -0.85, 0.0, 0.12, C.K_PANEL, 0.5, 0.0),                # skids
    (-1.9, 0.85, 1.9, 1.05, 0.0, 0.12, C.K_PANEL, 0.5, 0.0),
    (-0.1, -1.0, 0.1, 1.0, 0.12, 0.35, C.K_PANEL, 0.5, 0.0),
    (-2.2, -1.0, 2.2, 1.0, 0.3, 0.35, C.K_EMISSIVE, None, 3.0),               # underglow
    (-1.7, -W, 1.7, W, ROOF, ROOF + 0.15, C.K_PANEL, None, 0.0),              # cabin roof
    (-0.5, -0.15, 0.5, 0.15, ROOF + 0.15, ROOF + 0.55, C.K_SIGN, 0.12, 0.0),  # TAXI sign
    (-1.55, -0.6, -1.1, 0.6, FLOOR, FLOOR + 0.45, C.K_PANEL, None, 0.0),      # rear bench
]
for _u in (-1.65, 1.65):                                                      # cabin pillars
    for _v in (-1.15, 1.15):
        _PARTS.append((_u - 0.06, _v - 0.06, _u + 0.06, _v + 0.06, FLOOR, ROOF, C.K_PANEL, None, 0.0))


def _thrusters(power):
    return [(u - 0.25, v - 0.25, u + 0.25, v + 0.25, 0.3, 0.7, C.K_EMISSIVE, 0.08, 1.2 + 4.0 * power)
            for u in (-1.9, 1.9) for v in (-1.35, 1.35)]


class Stand:
    def __init__(self, index, name, x, y, z):
        self.index, self.name, self.x, self.y, self.z = index, name, x, y, z

    def slot(self, k):
        return (self.x + (SLOT if k else -SLOT), self.y, self.z)


class Obstacles:
    """Footprints (x0, z0, x1, z1) and top heights of everything a taxi must fly over."""

    def __init__(self, rects):
        a = np.array(rects, "f8").reshape(-1, 5)
        self.x0, self.z0, self.x1, self.z1, self.top = a.T

    def max_top(self, p, q, buffer=CORRIDOR):
        """Highest obstacle within `buffer` of the segment p -> q (x, z)."""
        px, pz = p
        dx, dz = q[0] - px, q[1] - pz
        n = max(2, int(math.hypot(dx, dz) / 10.0) + 2)          # sample every <= 10 m (buffer is 30 m)
        t = np.linspace(0.0, 1.0, n)
        sx, sz = px + dx * t, pz + dz * t
        best = 0.0
        x0, z0, x1, z1 = self.x0 - buffer, self.z0 - buffer, self.x1 + buffer, self.z1 + buffer
        near = ((x1 > min(sx.min(), sx.max())) & (x0 < max(sx.min(), sx.max()))
                & (z1 > min(sz.min(), sz.max())) & (z0 < max(sz.min(), sz.max())))
        for i in np.flatnonzero(near):
            if np.any((sx > x0[i]) & (sx < x1[i]) & (sz > z0[i]) & (sz < z1[i])):
                best = max(best, self.top[i])
        return best


class Taxi:
    def __init__(self, home, hue):
        self.home = home                      # Stand
        self.hue = hue
        self.stand, self.slot_k = home, 0     # where it is parked (None while flying)
        self.x, self.y, self.z = home.slot(0)
        self.heading = 0.0                    # angle of the forward direction: (cos, sin) in (x, z)
        self.legs = []                        # [(target x, y, z, speed limit)]
        self.v = 0.0
        self.vel = (0.0, 0.0, 0.0)
        self.dest = None
        self.passenger = False
        self.return_t = None                  # seconds until it flies home empty
        self.power = 0.0

    # ---------------------------------------------------------------- geometry
    @property
    def f(self):
        return (math.cos(self.heading), math.sin(self.heading))

    def world(self, u, v):
        f = self.f
        n = (-f[1], f[0])
        return self.x + f[0] * u + n[0] * v, self.z + f[1] * u + n[1] * v

    def seat(self):
        x, z = self.world(-0.2, 0.0)
        return [x, self.y + FLOOR, z]

    @property
    def parked(self):
        return self.stand is not None

    def bounds(self):
        r = math.hypot(L, W) + 0.3
        return (self.x - r, self.y - 0.2, self.z - r, self.x + r, self.y + ROOF + 0.6, self.z + r)

    # ---------------------------------------------------------------- flight
    def plan(self, dest, cruise, slot_k):
        tx, ty, tz = dest.slot(slot_k)
        self.legs = [(self.x, cruise, self.z, V_SPEED), (tx, cruise, tz, H_SPEED), (tx, ty, tz, V_SPEED)]
        self.dest, self.dest_slot = dest, slot_k
        self.stand = None
        self.v = 0.0
        self.return_t = None

    def eta(self):
        """Rough seconds to touchdown."""
        t, x, y, z = 0.0, self.x, self.y, self.z
        for lx, ly, lz, vmax in self.legs:
            d = math.sqrt((lx - x) ** 2 + (ly - y) ** 2 + (lz - z) ** 2)
            t += d / vmax + vmax / ACCEL
            x, y, z = lx, ly, lz
        return t

    def update(self, dt):
        """Advance; returns the heading change this frame (riders turn with the cabin)."""
        h0 = self.heading
        px, py, pz = self.x, self.y, self.z
        if self.legs:
            tx, ty, tz, vmax = self.legs[0]
            dx, dy, dz = tx - self.x, ty - self.y, tz - self.z
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            # face along the cruise during climb and cruise, back to +x for the landing
            if len(self.legs) == 3:
                cx, cz = self.legs[1][0] - self.x, self.legs[1][2] - self.z
                want = math.atan2(cz, cx) if math.hypot(cx, cz) > 1.0 else self.heading
            elif len(self.legs) == 2:
                want = math.atan2(dz, dx) if math.hypot(dx, dz) > 1.0 else self.heading
            else:
                want = 0.0
            turn = (want - self.heading + math.pi) % (2 * math.pi) - math.pi
            self.heading += max(-TURN_RATE * dt, min(TURN_RATE * dt, turn))
            self.heading = (self.heading + math.pi) % (2 * math.pi) - math.pi
            # hold the cruise until the nose points the right way
            limit = vmax if (len(self.legs) != 2 or abs(turn) < 0.05) else 0.0
            self.v = max(min(self.v + ACCEL * dt, limit, math.sqrt(2.0 * ACCEL * d)), 0.0)
            step = min(d, self.v * dt)
            if d > 1e-6:
                self.x += dx / d * step
                self.y += dy / d * step
                self.z += dz / d * step
            if d - step < 0.02 and (len(self.legs) != 1 or abs(self.heading) < 0.01):
                self.x, self.y, self.z = tx, ty, tz
                self.legs.pop(0)
                self.v = 0.0
                if not self.legs:
                    self.heading = 0.0
                    self.stand, self.slot_k = self.dest, self.dest_slot
                    if not self.passenger and self.stand is not self.home:
                        self.return_t = RETURN_DELAY
            self.power += (1.0 - self.power) * min(1.0, dt * 3.0)
        else:
            self.power += (0.0 - self.power) * min(1.0, dt * 2.0)
        self.vel = ((self.x - px) / dt, (self.y - py) / dt, (self.z - pz) / dt) if dt > 0 else (0.0, 0.0, 0.0)
        return (self.heading - h0 + math.pi) % (2 * math.pi) - math.pi

    # ---------------------------------------------------------------- render data
    def _parts(self):
        return _PARTS + _thrusters(self.power)

    def instances(self):
        parts = self._parts()
        f = self.f
        n = (-f[1], f[0])
        yaw = math.atan2(-f[1], f[0])
        out = np.zeros((len(parts), ROT_FLOATS), "f4")
        for i, (u0, v0, u1, v1, y0, y1, kind, hue, extra) in enumerate(parts):
            uc, vc = (u0 + u1) / 2, (v0 + v1) / 2
            out[i] = (self.x + f[0] * uc + n[0] * vc, self.y + y0, self.z + f[1] * uc + n[1] * vc,
                      u1 - u0, y1 - y0, v1 - v0, 7.0, kind, self.hue if hue is None else hue, extra, yaw)
        return out

    def glass_quads(self):
        f = self.f
        n = (-f[1], f[0])
        hh = (ROOF - FLOOR) / 2
        cy = self.y + FLOOR + hh
        out = []
        for u, v, along in ((1.65, 0.0, n), (-1.65, 0.0, n), (0.0, 1.15, f), (0.0, -1.15, f)):
            x, z = self.world(u, v)
            half = 1.15 if along is n else 1.65
            out.append(quad((x, cy, z), (along[0] * half, 0.0, along[1] * half), (0.0, hh, 0.0), C.Q_GLASS, self.hue, 1.0))
        return out

    def colliders(self):
        """Hull and roof while parked (always axis-aligned then)."""
        return [(self.x - L, self.y, self.z - W, self.x + L, self.y + FLOOR, self.z + W),
                (self.x - 1.7, self.y + ROOF, self.z - W, self.x + 1.7, self.y + ROOF + 0.15, self.z + W)]


class TaxiFleet:
    def __init__(self, stands, obstacles):
        """stands: (name, x, y, z); obstacles: Obstacles."""
        self.stands = [Stand(i, *s) for i, s in enumerate(stands)]
        self.obstacles = obstacles
        self.taxis = [Taxi(s, HUES[i % len(HUES)]) for i, s in enumerate(self.stands)]
        self.rider = None                     # the taxi the player sits in

    # ---------------------------------------------------------------- queries
    def stand_near(self, pos, reach=8.0):
        for s in self.stands:
            if abs(pos[1] - s.y) < 2.5 and math.hypot(pos[0] - s.x, pos[2] - s.z) < reach:
                return s
        return None

    def parked_at(self, stand):
        for t in self.taxis:
            if t.stand is stand and t is not self.rider:
                return t
        return None

    def cruise_alt(self, a, b):
        top = self.obstacles.max_top((a[0], a[2]), (b[0], b[2]))
        return max(a[1], b[1], top) + CLEARANCE

    # ---------------------------------------------------------------- control
    def send(self, taxi, dest):
        slot = 0 if dest is taxi.home else 1
        tx, ty, tz = dest.slot(slot)
        taxi.plan(dest, self.cruise_alt((taxi.x, taxi.y, taxi.z), (tx, ty, tz)), slot)

    def summon(self, stand):
        """Bring this stand's taxi home; returns its ETA in seconds (None if it is already here)."""
        t = self.taxis[stand.index]
        if t.parked and t.stand is stand:
            return None
        if t.parked and t is not self.rider:
            self.send(t, stand)
        return t.eta()

    def board(self, taxi):
        self.rider = taxi
        taxi.passenger = True
        taxi.return_t = None

    def leave(self):
        """Passenger gets out; returns where to stand (beside the cabin, on the pad)."""
        t = self.rider
        self.rider = None
        t.passenger = False
        if t.parked and t.stand is not t.home:
            t.return_t = RETURN_DELAY
        x, z = t.world(0.0, -(W + 1.2))
        return [x, t.y, z]

    def bail_out(self):
        """Jump out mid-flight: returns (position, velocity)."""
        t = self.rider
        self.rider = None
        t.passenger = False
        x, z = t.world(0.0, -(W + 0.8))
        if t.parked and t.stand is not t.home:   # still flying: it lands at the destination, then goes home
            t.return_t = RETURN_DELAY
        return [x, t.y + FLOOR, z], list(t.vel)

    def update(self, dt):
        dyaw = 0.0
        for t in self.taxis:
            if t.return_t is not None and t is not self.rider:
                t.return_t -= dt
                if t.return_t <= 0.0:
                    self.send(t, t.home)
            d = t.update(dt)
            if t is self.rider:
                dyaw = d
            elif t.parked and t.stand is not t.home and t.return_t is None and not t.passenger:
                t.return_t = RETURN_DELAY       # dropped off (e.g. after a bail-out): go home
        return dyaw

    # ---------------------------------------------------------------- render data
    def instances(self, eye, radius=6000.0):
        rows = [t.instances() for t in self.taxis
                if (t.x - eye[0]) ** 2 + (t.z - eye[2]) ** 2 < radius ** 2]
        return np.concatenate(rows) if rows else np.zeros((0, ROT_FLOATS), "f4")

    def glass_quads(self, eye, radius=600.0):
        return [q for t in self.taxis if (t.x - eye[0]) ** 2 + (t.y - eye[1]) ** 2 + (t.z - eye[2]) ** 2 < radius ** 2
                for q in t.glass_quads()]

    def colliders_near(self, pos, radius=20.0):
        return [c for t in self.taxis if t.parked and t is not self.rider
                and abs(t.x - pos[0]) < radius and abs(t.z - pos[2]) < radius and abs(t.y - pos[1]) < radius
                for c in t.colliders()]

    def dry_boxes(self):
        return [t.bounds() for t in self.taxis]


def stand_decor(stands):
    """Pad markings and an AIR TAXI sign for the ground-level stands (roofs have helipads)."""
    boxes, holos = [], []
    for i, (name, x, y, z) in enumerate(stands):
        if y > 1.0:
            continue
        x0, x1, z0, z1 = x - SLOT - 3.2, x + SLOT + 3.2, z - 2.6, z + 2.6
        for b in ((x0, z0 - 0.15, x1, z0), (x0, z1, x1, z1 + 0.15), (x0 - 0.15, z0, x0, z1), (x1, z0, x1 + 0.15, z1),
                  (x - 0.08, z0, x + 0.08, z1)):
            boxes.append(box_bounds(b[0], y, b[1], b[2], y + 0.03, b[3], C.K_EMISSIVE, 0.12, 2.5))
        boxes.append(box_bounds(x - 0.08, y, z1 + 0.6, x + 0.08, y + 3.2, z1 + 0.76, C.K_PANEL, 0.5))
        holos.append(quad((x, y + 3.8, z1 + 0.7), (1.6, 0, 0), (0, 0.55, 0), C.Q_HOLO, 0.12, 1.5, 600 + i))
    return boxes, holos
