"""Data shards: glowing collectibles scattered over the city, worth credits.

They sit in parks, on rooftops and skybridges, on the piers, the island and the fun park,
in the mall, the B2 undercity, on metro platforms and in the megatowers (feature floors and
roofs). Placement is deterministic; every spot is checked to be standable against the
static world (the megatower floors are only loaded near the player, so those use known clear
spots by the elevator landing instead).
"""
import math

import numpy as np

import config as C
import floors
import harbor
import mall
import sea
import undercity
from geometry import box_bounds, BOX_FLOATS

REACH, REACH_DY = 1.6, 2.0          # pick-up distance (horizontal) and height window above the floor
HOVER = 1.0
DRAW_R, BEAM_R = 250.0, 400.0
VALUE, VALUE_HIGH = 100, 200


def standable(world, x, y, z, hw=0.3, h=1.8):
    """Can someone stand at (x, y, z): nothing in the body and a floor right under the feet?"""
    if world.query(x - hw, y + 0.05, z - hw, x + hw, y + h, z + hw):
        return False
    if abs(y) < 0.06 and world.ground_solid(x, z, 0.0):
        return True
    return any(abs(b[4] - y) < 0.06 for b in world.query(x - hw, y - 0.3, z - hw, x + hw, y + 0.04, z + hw))


def floor_near(world, x, z, y_hint, span=3.0):
    """Top of the highest walkable surface at (x, z) within y_hint +- span, or None."""
    tops = [b[4] for b in world.query(x - 0.3, y_hint - span, z - 0.3, x + 0.3, y_hint + span, z + 0.3)
            if b[4] <= y_hint + span]
    if abs(y_hint) <= span and world.ground_solid(x, z, 0.0):
        tops.append(0.0)
    return max(tops) if tops else None


def _first(world, cands):
    """First standable candidate (x, y_hint, z) -> (x, y, z) or None."""
    for x, yh, z in cands:
        y = floor_near(world, x, z, yh)
        if y is not None and standable(world, x, y, z):
            return x, y, z
    return None


def _ring(x, y, z, r, n=8):
    return [(x, y, z)] + [(x + r * math.cos(a), y, z + r * math.sin(a))
                          for a in np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)]


def build_pickups(world, records, bridges, stations, towers, seed=77):
    """List of (x, y, z, value, where): y is the floor the shard hovers above."""
    rng = np.random.default_rng(seed)
    out = []

    def put(cands, where, value=VALUE):
        p = _first(world, cands)
        if p is not None:
            out.append((*p, value, where))

    P = C.BLOCK_PITCH
    for name, i, j, _ in C.PARKS:                                    # parks and plazas: three each
        cx, cz = i * P, j * P
        for dx, dz in ((14.0, -14.0), (-14.0, 14.0), (0.0, -26.0)):
            put(_ring(cx + dx, 0.0, cz + dz, 2.5), name)
    tall = [k for k, r in enumerate(records) if r.top >= 20.0]       # rooftops
    for k in rng.choice(tall, size=min(70, len(tall)), replace=False):
        if sum(1 for o in out if o[4] == "屋頂") >= 40:
            break
        r = records[int(k)]
        put(_ring(r.lx, r.top, r.lz, min(r.w, r.d) * 0.3), "屋頂", VALUE_HIGH if r.top > 100.0 else VALUE)
    for k in rng.choice(len(bridges), size=min(10, len(bridges)), replace=False):   # skybridges
        br = bridges[int(k)]
        x0, z0, x1, z1 = br.deck
        put([((x0 + x1) / 2, (br.ya + br.yb) / 2, (z0 + z1) / 2)], "空中天橋")
    for px, _ in harbor.PIERS:                                       # piers
        put([(px, harbor.DECK_Y, harbor.PIER_END - 10.0), (px, harbor.DECK_Y, harbor.PIER_END - 14.0)], "港灣碼頭")
        put([(px, harbor.DECK_Y, C.SHORE_Z + 40.0)], "港灣碼頭")
    D = sea.DECK                                                     # island and fun park
    for x, z in ((-100.0, 1850.0), (100.0, 1850.0), (-110.0, 2050.0), (110.0, 2050.0), (0.0, 1950.0), (40.0, 2000.0)):
        put(_ring(x, D, z, 3.0), "霓虹島")
    for x, z in ((-90.0, 2430.0), (90.0, 2620.0), (0.0, 2500.0)):
        put(_ring(x, D, z, 3.0), "海上遊樂園")
    wx, wy, wz = sea.WHEEL
    put([(wx + 2.0, wy - 30.0 - 2.4, wz + 3.0 + 4.0)], "摩天輪月台")
    hx0, hz0, hx1, hz1 = mall.HALL                                   # mall
    for x, z in ((hx0 + 8.0, hz0 + 8.0), (hx1 - 8.0, hz1 - 8.0), (9.5, -120.0), (9.5, -220.0)):
        put(_ring(x, mall.Y, z, 2.0), "地下商場")
    for name, (x0, z0, x1, z1) in undercity.HALLS.items():           # B2
        put(_ring((x0 + x1) / 2, undercity.Y, (z0 + z1) / 2, 4.0), "B2 " + name)
        put(_ring(x0 + 6.0, undercity.Y, z0 + 6.0, 2.0), "B2 " + name)
    R = undercity.R
    for sx, sz in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        put(_ring(sx * R, undercity.Y, sz * R, 1.5), "B2 環道")
    for st in stations:                                              # metro platforms
        x0, z0, x1, z1 = st.platform
        put(_ring((x0 + x1) / 2, st.yf, (z0 + z1) / 2, 2.0), f"{st.name}站")
    for t in towers:                                                 # megatowers: feature floors and roofs
        for k in range(100, t.floors + 1, 100):
            out.append((t.cx + t.half - 6.0, t.level_y(k), t.cz + 3.0, VALUE_HIGH, f"{t.name} {k}F"))
        put(_ring(t.cx, t.height, t.cz - t.half * 0.5, 3.0), f"{t.name} 頂樓", VALUE_HIGH)
    return out


class Pickups:
    def __init__(self, items):
        self.items = items
        self.pos = np.array([(x, y, z) for x, y, z, _, _ in items], "f4").reshape(-1, 3)
        # outdoors a thin light beam marks them from afar; indoors (underground, tower floors) it stays short
        self.beam = [2.6 if (y < -0.5 or w.endswith("F")) else 22.0 for _, y, _, _, w in items]

    def __len__(self):
        return len(self.items)

    def touch(self, pos, collected):
        """Index of an uncollected shard within reach of the player at pos, or None."""
        if not len(self.items):
            return None
        d = np.hypot(self.pos[:, 0] - pos[0], self.pos[:, 2] - pos[2])
        dy = pos[1] - self.pos[:, 1]
        for i in np.nonzero((d < REACH) & (dy > -1.0) & (dy < REACH_DY))[0]:
            if int(i) not in collected:
                return int(i)
        return None

    def instances(self, eye, collected, t):
        if not len(self.items):
            return np.zeros((0, BOX_FLOATS), "f4")
        d = np.hypot(self.pos[:, 0] - eye[0], self.pos[:, 2] - eye[2])
        rows = []
        for i in np.nonzero((d < BEAM_R) & (np.abs(self.pos[:, 1] - eye[1]) < BEAM_R))[0]:
            if int(i) in collected:
                continue
            x, y, z = (float(v) for v in self.pos[i])
            hue = 0.5 if self.items[i][3] < VALUE_HIGH else 0.12
            if d[i] < DRAW_R:
                bob = y + HOVER + 0.15 * math.sin(t * 2.5 + i)
                s = 0.22 + 0.04 * math.sin(t * 5.0 + i)
                rows.append(box_bounds(x - s, bob - s, z - s, x + s, bob + s, z + s, C.K_EMISSIVE, hue, 4.0))
                rows.append(box_bounds(x - 0.06, bob - 0.5, z - 0.06, x + 0.06, bob + 0.5, z + 0.06, C.K_EMISSIVE, hue, 2.5))
            if self.beam[i] > 3.0 or d[i] < DRAW_R:
                rows.append(box_bounds(x - 0.04, y + 1.6, z - 0.04, x + 0.04, y + self.beam[i], z + 0.04,
                                       C.K_EMISSIVE, hue, 0.6))
        return np.array(rows, "f4").reshape(-1, BOX_FLOATS)
