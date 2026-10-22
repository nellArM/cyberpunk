"""Static AABB world with a 2D spatial hash for fast player collision queries.

Boxes are tuples (minx, miny, minz, maxx, maxy, maxz).
"""
import math
from collections import defaultdict


def overlaps(b, x0, y0, z0, x1, y1, z1):
    return b[3] > x0 and b[0] < x1 and b[4] > y0 and b[1] < y1 and b[5] > z0 and b[2] < z1


def ray_box(o, d, b):
    """Entry distance of the ray o + t d (t > 0) into box b, or None (also when o is inside b)."""
    t0, t1 = -math.inf, math.inf
    for i in range(3):
        if abs(d[i]) < 1e-12:
            if not (b[i] <= o[i] <= b[i + 3]):
                return None
            continue
        a = (b[i] - o[i]) / d[i]
        c = (b[i + 3] - o[i]) / d[i]
        if a > c:
            a, c = c, a
        t0, t1 = max(t0, a), min(t1, c)
        if t0 > t1:
            return None
    return t0 if t0 > 0.0 else None


class StaticWorld:
    def __init__(self, boxes, cell=32.0, holes=(), water_z=None):
        self.boxes = list(boxes)
        self.holes = list(holes)                 # (x0, z0, x1, z1) openings in the ground (metro stairs)
        self.water_z = water_z                   # no street south of this (the sea)
        self.cell = cell
        self.disabled = set()                    # indices skipped by queries (a building opened up inside)
        self.grid = defaultdict(list)
        self._index(0)

    def _index(self, first):
        cell = self.cell
        for i in range(first, len(self.boxes)):
            b = self.boxes[i]
            for ix in range(int(math.floor(b[0] / cell)), int(math.floor(b[3] / cell)) + 1):
                for iz in range(int(math.floor(b[2] / cell)), int(math.floor(b[5] / cell)) + 1):
                    self.grid[(ix, iz)].append(i)

    def add(self, boxes):
        """Append more static boxes (existing indices stay valid)."""
        first = len(self.boxes)
        self.boxes.extend(boxes)
        self._index(first)

    def query(self, x0, y0, z0, x1, y1, z1):
        c = self.cell
        ids = set()
        for ix in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
            for iz in range(int(math.floor(z0 / c)), int(math.floor(z1 / c)) + 1):
                cell = self.grid.get((ix, iz))
                if cell:
                    ids.update(cell)
        ids -= self.disabled
        bs = self.boxes
        return [bs[i] for i in ids if overlaps(bs[i], x0, y0, z0, x1, y1, z1)]

    def raycast(self, o, d, max_dist, extra=()):
        """Distance along the unit ray o + t d to the first box (or the ground plane), or None."""
        best = max_dist
        if d[1] < -1e-6:                                       # street level
            t = -o[1] / d[1]
            if 0.0 < t < best and self.ground_solid(o[0] + d[0] * t, o[2] + d[2] * t, 0.0) and o[1] >= 0.0:
                best = t
        for b in extra:
            t = ray_box(o, d, b)
            if t is not None and t < best:
                best = t
        t0 = 0.0
        while t0 < best:
            t1 = min(t0 + 16.0, best)
            p0 = [o[i] + d[i] * t0 for i in range(3)]
            p1 = [o[i] + d[i] * t1 for i in range(3)]
            lo = [min(a, b) - 0.01 for a, b in zip(p0, p1)]
            hi = [max(a, b) + 0.01 for a, b in zip(p0, p1)]
            for b in self.query(*lo, *hi):
                t = ray_box(o, d, b)
                if t is not None and t < best:
                    best = t
            t0 = t1
        return best if best < max_dist else None

    def in_hole(self, x, z):
        if self.water_z is not None and z > self.water_z:
            return True
        return any(h[0] < x < h[2] and h[1] < z < h[3] for h in self.holes)

    def ground_solid(self, x, z, y):
        """Is the y=0 ground plane a floor here (not an opening, and we are not already below it)?"""
        return y >= -0.05 and not self.in_hole(x, z)

    def support_height(self, x, z, y, hw, extra=()):
        """Highest walkable surface under the footprint centered at (x, z), at or below y."""
        top = 0.0 if self.ground_solid(x, z, y) else -1e9
        cands = self.query(x - hw, -1.0, z - hw, x + hw, y + 0.05, z + hw)
        for b in cands + [b for b in extra if overlaps(b, x - hw, -1.0, z - hw, x + hw, y + 0.05, z + hw)]:
            if top < b[4] <= y + 0.05:
                top = b[4]
        return top
