"""People walking round fixed axis-aligned loops (mall corridor and hall, harbor promenade).

Each loop is a closed list of points with axis-aligned legs at a fixed height; walkers move
along it in either direction, pause now and then, and stop for the player in front of them.
"""
import math

import numpy as np

import config as C
from pedestrians import person_boxes


class LaneCrowd:
    def __init__(self, rng, loops):
        """loops: [(points [(x, z), ...] closed, y, count)]"""
        self.rng = rng
        self.loops = []
        ids, ys = [], []
        for li, (pts, y, n) in enumerate(loops):
            segs, s = [], 0.0
            for (x0, z0), (x1, z1) in zip(pts, pts[1:] + pts[:1]):
                L = abs(x1 - x0) + abs(z1 - z0)
                segs.append((s, L, x0, z0, x1, z1))
                s += L
            self.loops.append((segs, s))
            ids += [li] * n
            ys += [y] * n
        n = self.n = len(ids)
        self.li = np.array(ids, np.int64)
        self.y = np.array(ys, np.float64)
        self.P = np.array([self.loops[i][1] for i in ids])
        self.s = rng.uniform(0, 1, n) * self.P
        self.d = rng.choice([-1.0, 1.0], n)
        self.speed = rng.uniform(1.0, 1.5, n)
        self.wait = np.zeros(n)
        self.h = rng.uniform(0.9, 1.1, n)
        self.hue = rng.choice(C.NEON_HUES, n)
        self.seed = rng.uniform(0, 1000, n)
        self.umb = np.zeros(n)
        self.phase = rng.uniform(0, 2 * math.pi, n)
        self.x, self.z = np.zeros(n), np.zeros(n)
        self.fa = np.zeros(n, np.int64)
        self.fs = np.ones(n)
        self.moving = np.zeros(n, bool)
        self._place()

    def _place(self):
        for i in range(self.n):
            segs, P = self.loops[self.li[i]]
            s = self.s[i] % P
            for s0, L, x0, z0, x1, z1 in segs:
                if s < s0 + L or (s0, L) == segs[-1][:2]:
                    t = (s - s0) / L if L > 0 else 0.0
                    self.x[i], self.z[i] = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
                    ax = 0 if x1 != x0 else 1
                    self.fa[i] = ax
                    self.fs[i] = math.copysign(1.0, ((x1 - x0) if ax == 0 else (z1 - z0)) * self.d[i])
                    break

    def update(self, dt, player_pos=None):
        if dt <= 0:
            return
        blocked = np.zeros(self.n, bool)
        if player_pos is not None:
            fx = np.where(self.fa == 0, self.fs, 0.0)
            fz = np.where(self.fa == 1, self.fs, 0.0)
            dx, dz = player_pos[0] - self.x, player_pos[2] - self.z
            ahead = dx * fx + dz * fz
            blocked = ((ahead > 0.1) & (ahead < 1.2) & (np.abs(dx * fz - dz * fx) < 0.6)
                       & (np.abs(player_pos[1] - self.y) < 1.5))
        self.wait = np.maximum(self.wait - dt, 0.0)
        pause = (self.wait <= 0) & (self.rng.random(self.n) < dt / 25.0)
        self.wait[pause] = self.rng.uniform(1.5, 5.0, int(pause.sum()))
        go = (self.wait <= 0) & ~blocked
        self.s = np.where(go, (self.s + self.d * self.speed * dt) % self.P, self.s)
        self.moving = go
        self.phase += np.where(go, self.speed * dt / 0.55 * math.pi, 0.0)
        self._place()

    def instances(self, eye, radius=150.0):
        vis = np.flatnonzero((self.x - eye[0]) ** 2 + (self.z - eye[2]) ** 2 + (self.y - eye[1]) ** 2 < radius ** 2)
        return person_boxes(self.x[vis], self.y[vis], self.z[vis], self.fa[vis], self.fs[vis], self.moving[vis],
                            self.phase[vis], self.h[vis], self.hue[vis], self.seed[vis], self.umb[vis])

    def colliders_near(self, pos, radius=8.0):
        idx = np.flatnonzero((np.abs(self.x - pos[0]) < radius) & (np.abs(self.z - pos[2]) < radius)
                             & (np.abs(self.y - pos[1]) < 3.0))
        return [(float(self.x[i] - 0.25), float(self.y[i]), float(self.z[i] - 0.25), float(self.x[i] + 0.25),
                 float(self.y[i] + 1.75 * self.h[i]), float(self.z[i] + 0.25)) for i in idx]
