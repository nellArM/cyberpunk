"""Office workers (and residents) walking around the furnished floors near the player, in the
megatowers and in the city buildings' upper floors.

Each floor gets a 1 m navigation grid (over the interior's world rectangle) built from its
furniture colliders; workers pick a nearby free cell, BFS a 4-connected path to it (so every
leg is axis-aligned and the boxy people never need rotating), walk there, stand and "work"
for a while, then repeat. They stop for the player and re-route if blocked for more than 2 s.
"""
import math
from collections import deque

import numpy as np

from pedestrians import person_boxes

MARGIN = 0.35                            # clearance kept around furniture
# per floor theme: office, servers, garden, lounge, construction, flats, observatory, sky garden, sky bar
COUNTS = (30, 6, 10, 25, 8, 8, 18, 14, 40)
SUIT_HUES = (0.6, 0.55, 0.65, 0.75, 0.83)
GOAL_RANGE = 25
TOWER_AREA = 79.0 * 79.0                 # building floors get people in proportion to their area


def interior_rect(g):
    """World (x0, z0, x1, z1) of a layout's walkable interior."""
    return g.bounds(-g.Ix, -g.Iz, g.Ix, g.Iz)


def nav_grid(colliders, g):
    """free[i, j] for the cell at world x = x0 + i + 0.5, z = z0 + j + 0.5 of the interior (1 m cells)."""
    ox, oz, x1, z1 = interior_rect(g)
    nx, nz = int(round(x1 - ox)), int(round(z1 - oz))
    free = np.ones((nx, nz), bool)
    free[0, :] = free[-1, :] = free[:, 0] = free[:, -1] = False          # stay off the facade
    rects = [(b[0], b[2], b[3], b[5]) for b in colliders]
    rects.append(g.bounds(g.SX0 - 0.6, g.HZ0 - 0.6, g.HX1 + 0.6, g.HZ1 + 0.6))  # stairwell
    for x0, z0, x1, z1 in rects:
        i0 = max(0, int(math.floor(x0 - MARGIN - ox)))
        i1 = min(nx - 1, int(math.ceil(x1 + MARGIN - ox)) - 1)
        j0 = max(0, int(math.floor(z0 - MARGIN - oz)))
        j1 = min(nz - 1, int(math.ceil(z1 + MARGIN - oz)) - 1)
        if i0 <= i1 and j0 <= j1:
            free[i0:i1 + 1, j0:j1 + 1] = False
    return free


def bfs_path(free, start, goal, avoid=None):
    """Cells from start (exclusive) to goal, compressed to the corners; None if unreachable."""
    NX, NZ = free.shape
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c == goal:
            break
        i, j = c
        for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= n[0] < NX and 0 <= n[1] < NZ and n not in prev and free[n] and n != avoid:
                prev[n] = c
                q.append(n)
    if goal not in prev:
        return None
    cells = []
    c = goal
    while c != start:
        cells.append(c)
        c = prev[c]
    cells.reverse()
    corners = [cell for a, cell, b in zip([start] + cells, cells, cells[1:] + [None])
               if b is None or (b[0] - cell[0], b[1] - cell[1]) != (cell[0] - a[0], cell[1] - a[1])]
    return corners


class FloorCrowd:
    def __init__(self, g, k, colliders):
        """g: the floor's layout (tower_interior)."""
        self.k = k
        self.y = g.level_y(k)
        self.ox, self.oz = interior_rect(g)[:2]               # world x/z of cell (0, 0)'s corner
        self.free = nav_grid(colliders, g)
        self.NX, self.NZ = self.free.shape
        self.rng = rng = np.random.default_rng(g.crowd_seed(k))
        cells = np.argwhere(self.free)
        n = COUNTS[g.theme(k)]
        if not g.has_elevator:
            n = max(2, int(round(n * self.NX * self.NZ / TOWER_AREA * 1.5)))
        n = min(n, len(cells))
        pick = cells[rng.choice(len(cells), n, replace=False)]
        self.n = n
        self.ci = pick[:, 0].copy()
        self.cj = pick[:, 1].copy()
        self.x = (self.ox + self.ci + 0.5).astype(np.float64)
        self.z = (self.oz + self.cj + 0.5).astype(np.float64)
        self.path = [[] for _ in range(n)]
        self.wait = rng.uniform(0.0, 4.0, n)
        self.speed = rng.uniform(1.0, 1.5, n)
        self.h = rng.uniform(0.92, 1.08, n)
        self.hue = rng.choice(SUIT_HUES, n)
        self.seed = rng.uniform(0, 1000, n)
        self.phase = rng.uniform(0, 2 * math.pi, n)
        self.face_axis = rng.integers(0, 2, n)
        self.face_sign = rng.choice([-1.0, 1.0], n)
        self.moving = np.zeros(n, bool)
        self.blocked_t = np.zeros(n)
        self.travelled = 0.0

    def _cell_of(self, x, z):
        return (int(math.floor(x - self.ox)), int(math.floor(z - self.oz)))

    def _plan(self, i, avoid=None):
        rng = self.rng
        start = self._cell_of(self.x[i], self.z[i])
        for _ in range(8):
            gi = int(np.clip(start[0] + rng.integers(-GOAL_RANGE, GOAL_RANGE + 1), 1, self.NX - 2))
            gj = int(np.clip(start[1] + rng.integers(-GOAL_RANGE, GOAL_RANGE + 1), 1, self.NZ - 2))
            if not self.free[gi, gj] or (gi, gj) == start:
                continue
            corners = bfs_path(self.free, start, (gi, gj), avoid)
            if corners:
                self.path[i] = [(self.ox + a + 0.5, self.oz + b + 0.5) for a, b in corners]
                dx, dz = self.path[i][0][0] - self.x[i], self.path[i][0][1] - self.z[i]
                ax = 0 if abs(dx) >= abs(dz) else 1                 # turn toward the new route now
                self.face_axis[i] = ax
                self.face_sign[i] = math.copysign(1.0, dx if ax == 0 else dz)
                return
        self.wait[i] = 1.0                                  # nowhere to go right now

    def update(self, dt, player_pos=None):
        blocked = np.zeros(self.n, bool)
        avoid = None
        if player_pos is not None and abs(player_pos[1] - self.y) < 1.5:
            fx = np.where(self.face_axis == 0, self.face_sign, 0.0)
            fz = np.where(self.face_axis == 1, self.face_sign, 0.0)
            dx, dz = player_pos[0] - self.x, player_pos[2] - self.z
            ahead = dx * fx + dz * fz
            walking = np.array([bool(p) for p in self.path])          # wants to move (may be stopped)
            blocked = walking & (ahead > 0.1) & (ahead < 1.2) & (np.abs(dx * fz - dz * fx) < 0.6)
            avoid = self._cell_of(player_pos[0], player_pos[2])
        for i in range(self.n):
            if blocked[i]:
                self.blocked_t[i] += dt
                if self.blocked_t[i] > 2.0:                 # re-route around the player
                    self.blocked_t[i] = 0.0
                    self._snap(i)
                    self._plan(i, avoid)
                continue
            self.blocked_t[i] = 0.0
            path = self.path[i]
            if not path:
                self.moving[i] = False
                self.wait[i] -= dt
                if self.wait[i] <= 0.0:
                    self._plan(i)
                continue
            tx, tz = path[0]
            dx, dz = tx - self.x[i], tz - self.z[i]
            dist = abs(dx) + abs(dz)
            step = self.speed[i] * dt
            if dist > 1e-6:
                ax = 0 if abs(dx) >= abs(dz) else 1
                self.face_axis[i] = ax
                self.face_sign[i] = math.copysign(1.0, dx if ax == 0 else dz)
            if step >= dist:
                self.x[i], self.z[i] = tx, tz
                path.pop(0)
                self.travelled += dist
                if not path:
                    self.wait[i] = self.rng.uniform(3.0, 10.0)
            else:
                if abs(dx) >= abs(dz):
                    self.x[i] += math.copysign(step, dx)
                else:
                    self.z[i] += math.copysign(step, dz)
                self.travelled += step
            self.moving[i] = True
        self.moving &= ~blocked
        self.phase += np.where(self.moving, self.speed * dt / 0.55 * math.pi, 0.0)

    def _snap(self, i):
        """Stop at the nearest cell center so the next path starts axis-aligned."""
        ci, cj = self._cell_of(self.x[i], self.z[i])
        if 0 <= ci < self.NX and 0 <= cj < self.NZ and self.free[ci, cj]:
            self.x[i], self.z[i] = self.ox + ci + 0.5, self.oz + cj + 0.5
        self.path[i] = []

    def boxes(self):
        return person_boxes(self.x, self.y, self.z, self.face_axis, self.face_sign, self.moving, self.phase,
                            self.h, self.hue, self.seed, np.zeros(self.n))


class OfficeWorkers:
    def __init__(self):
        self.crowds = {}

    @property
    def count(self):
        return sum(c.n for c in self.crowds.values())

    def update(self, dt, interior, player_pos):
        g = interior.layout
        wanted = {(g.key, k) for k in interior.furnished} if g is not None else set()
        for key in list(self.crowds):
            if key not in wanted:
                del self.crowds[key]
        for key in wanted:
            if key not in self.crowds:
                self.crowds[key] = FloorCrowd(g, key[1], interior.floor_parts(key[1]).cols)
        for c in self.crowds.values():
            c.update(dt, player_pos)

    def instances(self):
        if not self.crowds:
            return np.zeros((0, 10), "f4")
        return np.concatenate([c.boxes() for c in self.crowds.values()])

    def colliders_near(self, pos, radius=8.0):
        out = []
        for c in self.crowds.values():
            if abs(pos[1] - c.y) > 3.0:
                continue
            for i in np.flatnonzero((np.abs(c.x - pos[0]) < radius) & (np.abs(c.z - pos[2]) < radius)):
                out.append((float(c.x[i] - 0.25), c.y, float(c.z[i] - 0.25),
                            float(c.x[i] + 0.25), c.y + 1.75 * float(c.h[i]), float(c.z[i] + 0.25)))
        return out
