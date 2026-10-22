"""Moving platforms you can ride: ferries, Ferris wheel gondolas, the drop tower; plus a carousel.

A Platform is a set of boxes around a moving origin. Whoever stands on one of its floor
parts is carried by the platform's displacement each frame (main.py), the same way the
elevators carry their passengers; only translation, so floors stay level.
"""
import math

import numpy as np

import config as C
from geometry import box_bounds, BOX_FLOATS
from i18n import tr


class Platform:
    def __init__(self, pos):
        self.pos = list(pos)
        self.prev = list(pos)

    def parts(self):
        """(x0, y0, z0, x1, y1, z1 relative to pos, kind, hue, extra, collide, floor)"""
        return []

    def _world(self):
        x, y, z = self.pos
        for b, k, h, e, c, f in self.parts():
            yield (b[0] + x, b[1] + y, b[2] + z, b[3] + x, b[4] + y, b[5] + z), k, h, e, c, f

    def delta(self):
        return [a - b for a, b in zip(self.pos, self.prev)]

    def step(self, dt):
        self.prev = list(self.pos)
        self.update(dt)

    def update(self, dt):
        pass

    def floors(self):
        return [b for b, _, _, _, _, f in self._world() if f]

    def colliders(self):
        return [b for b, _, _, _, c, _ in self._world() if c]

    def instances(self):
        return [box_bounds(*b, k, h, e) for b, k, h, e, _, _ in self._world() if k is not None]

    def near(self, p, r):
        return abs(self.pos[0] - p[0]) < r and abs(self.pos[1] - p[1]) < r and abs(self.pos[2] - p[2]) < r


def _move_1d(s, v, target, vmax, accel, dt):
    """Accelerate toward target, braking in time; returns (s, v, arrived)."""
    d = target - s
    dist = abs(d)
    if dist < 1e-3:
        return target, 0.0, True
    v = min(v + accel * dt, vmax, math.sqrt(2.0 * accel * dist) + 0.05)
    step = min(dist, v * dt)
    return s + math.copysign(step, d), v, step >= dist - 1e-6


class Ferry(Platform):
    """Double-ended ferry shuttling along z between two docks (no turning)."""
    L, W = 15.0, 4.5                    # half length (z), half width (x)
    DWELL, SPEED, ACCEL = 15.0, 12.0, 1.2

    def __init__(self, x, za, zb, names, hue):
        """za / zb: center z when docked at either end (A to the north / -z, B to the south / +z)."""
        super().__init__((x, 0.0, za))
        self.za, self.zb, self.names, self.hue = za, zb, names, hue
        self.at = 0                     # dock index (0 = A, 1 = B) while docked, else destination
        self.docked = True
        self.timer = self.DWELL
        self.v = 0.0

    def update(self, dt):
        if self.docked:
            self.timer -= dt
            if self.timer <= 0.0:
                self.docked = False
                self.at = 1 - self.at
        else:
            target = self.zb if self.at == 1 else self.za
            self.pos[2], self.v, done = _move_1d(self.pos[2], self.v, target, self.SPEED, self.ACCEL, dt)
            if done:
                self.docked, self.timer, self.v = True, self.DWELL, 0.0

    def status(self):
        """(text for the HUD) about where it goes next."""
        if self.docked:
            return tr("渡輪停靠中 → {dest}（{s:.0f} 秒後開船）", dest=self.names[1 - self.at], s=max(self.timer, 0))
        return tr("渡輪航行中 → {dest}", dest=self.names[self.at])

    def parts(self):
        L, W, hue = self.L, self.W, self.hue
        P, E = C.K_PANEL, C.K_EMISSIVE
        out = [((-W, -1.6, -L, W, 0.2, L), C.K_VEHICLE, hue, 1.0, False, False),          # hull
               ((-W, 0.2, -L, W, 0.6, L), C.K_FLOOR, 0.08, 0.0, True, True),               # deck
               ((-W - 0.05, -0.2, -L - 0.05, W + 0.05, 0.0, L + 0.05), E, hue, 3.0, False, False)]
        for sx in (-1, 1):                                                               # side railings
            x0, x1 = (W - 0.12, W) if sx > 0 else (-W, -W + 0.12)
            out.append(((x0, 0.6, -L, x1, 1.7, L), P, 0.5, 0.0, True, False))
            out.append(((x0 - 0.02, 1.7, -L, x1 + 0.02, 1.76, L), E, hue, 2.5, False, False))
        open_end = (-1 if self.at == 0 else 1) if self.docked else 0                    # the end at the dock
        for sz in (-1, 1):                                                               # end gates
            if sz != open_end:
                z0, z1 = (L - 0.12, L) if sz > 0 else (-L, -L + 0.12)
                out.append(((-W, 0.6, z0, W, 1.7, z1), C.K_DOOR, hue, 0.0, True, False))
        for x in (-W + 0.3, W - 0.3):                                                    # cabin roof on pillars
            for z in (-7.0, 7.0):
                out.append(((x - 0.12, 0.6, z - 0.12, x + 0.12, 3.4, z + 0.12), P, 0.5, 0.0, True, False))
        out.append(((-W, 3.4, -8.0, W, 3.6, 8.0), P, hue, 0.0, True, False))
        for x0, z0, x1, z1 in ((-W - 0.05, -8.05, W + 0.05, -7.9), (-W - 0.05, 7.9, W + 0.05, 8.05),    # roof rim
                               (-W - 0.05, -8.05, -W + 0.1, 8.05), (W - 0.1, -8.05, W + 0.05, 8.05)):
            out.append(((x0, 3.35, z0, x1, 3.42, z1), E, hue, 3.0, False, False))
        for x in (-1.8, 1.8):                                                            # cabin light strips
            out.append(((x - 0.08, 3.32, -6.0, x + 0.08, 3.38, 6.0), E, -1.0, 1.2, False, False))
        for z in (-5.0, -2.0, 1.0, 4.0):                                                 # benches
            out.append(((-3.2, 0.6, z, -0.6, 1.05, z + 0.6), P, hue, 0.0, True, False))
            out.append(((0.6, 0.6, z, 3.2, 1.05, z + 0.6), P, hue, 0.0, True, False))
        return out


class Gondola(Platform):
    """An open Ferris wheel gondola; its gate (on +z) opens near the bottom."""
    H = 1.4

    def __init__(self, pos, hue):
        super().__init__(pos)
        self.hue = hue
        self.gate_open = False

    def parts(self):
        H, P, hue = self.H, C.K_PANEL, self.hue
        out = [((-H, -0.25, -H, H, 0.0, H), C.K_FLOOR, hue, 0.0, True, True),
               ((-H, 2.4, -H, H, 2.55, H), P, hue, 0.0, True, False),                    # roof
               ((-0.08, 2.55, -0.08, 0.08, 2.4 + 0.15, 0.08), P, 0.5, 0.0, False, False),
               ((-H - 0.03, -0.3, -H - 0.03, H + 0.03, -0.25, H + 0.03), C.K_EMISSIVE, hue, 3.0, False, False)]
        for x0, z0, x1, z1 in ((-H, -H, H, -H + 0.08), (-H, -H, -H + 0.08, H), (H - 0.08, -H, H, H)):
            out.append(((x0, 0.0, z0, x1, 1.1, z1), P, 0.5, 0.0, True, False))
        if not self.gate_open:
            out.append(((-H, 0.0, H - 0.08, H, 1.1, H), C.K_DOOR, hue, 0.0, True, False))
        for x in (-H, H - 0.08):                                                          # corner posts
            for z in (-H, H - 0.08):
                out.append(((x, 1.1, z, x + 0.08, 2.4, z + 0.08), P, 0.5, 0.0, False, False))
        return out


class FerrisWheel:
    """Gondolas on a vertical wheel in the x-y plane (they hang in front of it, at +z)."""
    N, R, PERIOD = 12, 30.0, 150.0
    HANG = 2.4                         # gondola floor below its pivot on the rim
    FRONT = 3.0                        # gondola center in front of the wheel plane

    def __init__(self, center):
        self.cx, self.cy, self.cz = center
        self.phase = 0.0
        self.gondolas = [Gondola(self._pos(i), C.NEON_HUES[i % len(C.NEON_HUES)]) for i in range(self.N)]

    def _angle(self, i):
        return self.phase + 2.0 * math.pi * i / self.N

    def _pos(self, i):
        a = self._angle(i)
        return (self.cx + self.R * math.cos(a), self.cy + self.R * math.sin(a) - self.HANG, self.cz + self.FRONT)

    @property
    def board_y(self):
        return self.cy - self.R - self.HANG

    def update(self, dt):
        self.phase = (self.phase + 2.0 * math.pi * dt / self.PERIOD) % (2.0 * math.pi)
        for i, g in enumerate(self.gondolas):
            g.prev = list(g.pos)
            g.pos = list(self._pos(i))
            a = (self._angle(i) + math.pi / 2) % (2.0 * math.pi)                         # 0 at the bottom
            g.gate_open = min(a, 2.0 * math.pi - a) < math.radians(7.0)

    def arm_instances(self):
        """Hangers from the rim to each gondola roof."""
        out = []
        for g in self.gondolas:
            x, y, z = g.pos
            out.append(box_bounds(x - 0.08, y + 2.55, self.cz, x + 0.08, y + self.HANG + 0.1, self.cz + 0.16,
                                  C.K_PANEL, 0.5))
            out.append(box_bounds(x - 0.08, y + 2.55, self.cz, x + 0.08, y + 2.7, z, C.K_PANEL, 0.5))
        return out


class DropTower(Platform):
    """A ring car around a 65 m column: waits at the bottom, climbs, holds, drops, brakes."""
    BOTTOM, TOP = 0.9, 60.0
    HALF, HOLE = 3.5, 1.3

    def __init__(self, x, z):
        super().__init__((x, self.BOTTOM, z))
        self.state, self.timer, self.v = "wait", 10.0, 0.0

    def update(self, dt):
        y = self.pos[1]
        if self.state == "wait":
            self.timer -= dt
            if self.timer <= 0.0:
                self.state = "up"
        elif self.state == "up":
            self.pos[1] = min(self.TOP, y + 4.0 * dt)
            if self.pos[1] >= self.TOP:
                self.state, self.timer = "hold", 3.0
        elif self.state == "hold":
            self.timer -= dt
            if self.timer <= 0.0:
                self.state, self.v = "drop", 0.0
        elif self.state == "drop":
            h = y - self.BOTTOM
            if self.v * self.v / (2.0 * 25.0) >= h - 1.0:                                 # brake for the bottom
                self.v = max(1.0, self.v - 25.0 * dt)
            else:
                self.v += 12.0 * dt
            self.pos[1] = max(self.BOTTOM, y - self.v * dt)
            if self.pos[1] <= self.BOTTOM + 1e-6:
                self.state, self.timer, self.v = "wait", 10.0, 0.0

    @property
    def open(self):
        return self.state == "wait"

    def parts(self):
        Hf, h, P, E = self.HALF, self.HOLE, C.K_PANEL, C.K_EMISSIVE
        out = []
        for x0, z0, x1, z1 in ((-Hf, -Hf, Hf, -h), (-Hf, h, Hf, Hf), (-Hf, -h, -h, h), (h, -h, Hf, h)):
            out.append(((x0, -0.3, z0, x1, 0.0, z1), C.K_FLOOR, 0.92, 0.0, True, True))
        out.append(((-Hf - 0.05, -0.36, -Hf - 0.05, Hf + 0.05, -0.3, Hf + 0.05), E, 0.92, 4.0, False, False))
        for x0, z0, x1, z1 in ((-Hf, -Hf, Hf, -Hf + 0.08), (-Hf, -Hf, -Hf + 0.08, Hf), (Hf - 0.08, -Hf, Hf, Hf)):
            out.append(((x0, 0.0, z0, x1, 1.2, z1), P, 0.5, 0.0, True, False))
        if not self.open:                                                                 # gate on +z
            out.append(((-Hf, 0.0, Hf - 0.08, Hf, 1.2, Hf), C.K_DOOR, 0.92, 0.0, True, False))
        for x in (-1.6, 0.0, 1.6):                                                        # seats against the column
            out.append(((x - 0.5, 0.0, h + 0.1, x + 0.5, 0.5, h + 0.7), P, 0.92, 0.0, True, False))
        return out


class Carousel:
    """Decorative horses circling (boxes only)."""

    def __init__(self, center, r=6.0, n=10):
        self.cx, self.cy, self.cz = center
        self.r, self.n, self.phase = r, n, 0.0

    def update(self, dt):
        self.phase = (self.phase + dt * 0.5) % (2.0 * math.pi)

    def instances(self):
        out = []
        for i in range(self.n):
            a = self.phase + 2.0 * math.pi * i / self.n
            x, z = self.cx + self.r * math.cos(a), self.cz + self.r * math.sin(a)
            bob = 0.4 * math.sin(a * 3.0 + self.phase * 4.0)
            hue = C.NEON_HUES[i % len(C.NEON_HUES)]
            out.append(box_bounds(x - 0.05, self.cy, z - 0.05, x + 0.05, self.cy + 3.2, z + 0.05, C.K_EMISSIVE, 0.12, 2.0))
            out.append(box_bounds(x - 0.6, self.cy + 1.1 + bob, z - 0.25, x + 0.6, self.cy + 1.7 + bob, z + 0.25,
                                  C.K_PANEL, hue))
            out.append(box_bounds(x + 0.4, self.cy + 1.6 + bob, z - 0.15, x + 0.75, self.cy + 2.1 + bob, z + 0.15,
                                  C.K_PANEL, hue))
        return out


class Rides:
    """All moving platforms and decorations at sea."""

    def __init__(self, ferries, wheel, tower, carousel):
        self.ferries, self.wheel, self.tower, self.carousel = ferries, wheel, tower, carousel
        self.platforms = ferries + wheel.gondolas + [tower]

    def update(self, dt):
        for f in self.ferries:
            f.step(dt)
        self.wheel.update(dt)
        self.tower.step(dt)
        self.carousel.update(dt)

    def carry(self, pl):
        """Move the player with the platform they stand on; returns that platform or None."""
        if not pl.grounded:
            return None
        x, y, z = pl.pos
        for p in self.platforms:
            if not p.near(pl.pos, 40.0):
                continue
            for b in p.floors():
                if b[0] - 0.05 < x < b[3] + 0.05 and b[2] - 0.05 < z < b[5] + 0.05 and abs(y - (b[4] - (p.pos[1] - p.prev[1]))) < 0.3:
                    d = p.delta()
                    pl.pos[0] += d[0]
                    pl.pos[1] += d[1]
                    pl.pos[2] += d[2]
                    return p
        return None

    def under(self, pos):
        """The platform whose floor the feet at pos are on (without moving anyone), or None."""
        x, y, z = pos
        for p in self.platforms:
            if p.near(pos, 40.0) and any(b[0] - 0.05 < x < b[3] + 0.05 and b[2] - 0.05 < z < b[5] + 0.05
                                         and abs(y - b[4]) < 0.3 for b in p.floors()):
                return p
        return None

    def colliders_near(self, pos, r=60.0):
        return [c for p in self.platforms if p.near(pos, r) for c in p.colliders()]

    def instances(self, eye, r=2500.0):
        rows = []
        for p in self.platforms:
            if p.near(eye, r):
                rows += p.instances()
        if self.wheel.gondolas[0].near(eye, r):
            rows += self.wheel.arm_instances()
        if abs(self.carousel.cx - eye[0]) < r and abs(self.carousel.cz - eye[2]) < r:
            rows += self.carousel.instances()
        return np.array(rows, "f4").reshape(-1, BOX_FLOATS)

    def ferry_near(self, pos, r=25.0):
        """A ferry the player is on or next to, for the HUD."""
        for f in self.ferries:
            if abs(pos[0] - f.pos[0]) < f.W + r and abs(pos[2] - f.pos[2]) < f.L + r and -2.0 < pos[1] < 6.0:
                return f
        return None
