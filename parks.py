"""Parks and plazas on whole city blocks (config.PARKS).

Park: lawn with a 13..21 m walking ring (drawn by the ground shader), glowing neon trees,
benches, lamps, a hologram statue and an air-taxi pad in the middle.
Plaza: paving, a fountain, a bench ring, food carts, a giant hologram screen, a taxi pad.
Items that would overlap `reserved` boxes (metro station stairs) are left out.
"""
import numpy as np

import config as C
from collision import overlaps
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS

LAWN = C.BLOCK_PITCH / 2 - C.ROAD_HALF - 2.5          # 29.5: the block inside its sidewalk
TREE_HUES = (0.33, 0.45, 0.5, 0.9, 0.83)


class ParkData:
    def __init__(self, boxes, cols, holos, stands, zones):
        self.boxes = np.array(boxes, "f4").reshape(-1, BOX_FLOATS)
        self.colliders = cols
        self.holos = np.array(holos, "f4").reshape(-1, QUAD_FLOATS)
        self.stands = stands                  # (name, x, y, z) air-taxi stands on the ground
        self.zones = zones                    # (x0, z0, x1, z1, kind) for the ground shader


def build_parks(reserved=()):
    boxes, cols, holos, stands, zones = [], [], [], [], []
    for pi, (name, i, j, kind) in enumerate(C.PARKS):
        cx, cz = i * C.BLOCK_PITCH, j * C.BLOCK_PITCH
        rng = np.random.default_rng(4242 + pi)
        res = [b for b in reserved if overlaps(b, cx - LAWN, -1.0, cz - LAWN, cx + LAWN, 30.0, cz + LAWN)]

        def clear(x0, z0, x1, z1, m=0.6):
            return not any(overlaps(b, cx + x0 - m, -1.0, cz + z0 - m, cx + x1 + m, 30.0, cz + z1 + m) for b in res)

        def add(x0, y0, z0, x1, y1, z1, k, hue=0.0, extra=0.0, collide=False, seed=0.0):
            b = (cx + x0, y0, cz + z0, cx + x1, y1, cz + z1)
            boxes.append(box_bounds(*b, k, hue, extra, seed))
            if collide:
                cols.append(b)

        def bench(x, z, along_x):
            if not clear(x - 1.0, z - 1.0, x + 1.0, z + 1.0):
                return
            hx, hz = (0.9, 0.3) if along_x else (0.3, 0.9)
            add(x - hx, 0.0, z - hz, x + hx, 0.45, z + hz, C.K_PANEL, 0.5, collide=True)
            add(x - hx, 0.45, z - hz, x + hx, 0.5, z + hz, C.K_EMISSIVE, 0.5, 1.2)

        def lamp(x, z, hue):
            if clear(x - 0.3, z - 0.3, x + 0.3, z + 0.3):
                add(x - 0.08, 0.0, z - 0.08, x + 0.08, 4.0, z + 0.08, C.K_PANEL, 0.5, collide=True)
                add(x - 0.3, 4.0, z - 0.3, x + 0.3, 4.2, z + 0.3, C.K_EMISSIVE, hue, 3.0)

        if kind == "park":
            zones.append((cx - LAWN, cz - LAWN, cx + LAWN, cz + LAWN, 1))
            # trees in the outer band (22..28 m) and the inner band (7..11 m), not on the spokes
            for band, step in (((23.0, 28.0), 4.2), ((7.5, 10.5), 3.4)):
                for x in np.arange(-band[1], band[1] + 0.1, step):
                    for z in np.arange(-band[1], band[1] + 0.1, step):
                        r = max(abs(x), abs(z))
                        if not (band[0] <= r <= band[1]) or min(abs(x), abs(z)) < 3.0 or rng.random() < 0.25:
                            continue
                        x1, z1 = x + rng.uniform(-0.6, 0.6), z + rng.uniform(-0.6, 0.6)
                        near_statue = abs(x1 - 14.0) < 3.8 and abs(z1 + 24.5) < 3.8
                        if near_statue or not clear(x1 - 2.0, z1 - 2.0, x1 + 2.0, z1 + 2.0):
                            continue
                        th = rng.uniform(2.6, 3.6)
                        hue = float(rng.choice(TREE_HUES))
                        add(x1 - 0.22, 0.0, z1 - 0.22, x1 + 0.22, th, z1 + 0.22, C.K_PANEL, 0.33, collide=True)
                        y = th
                        for s in (rng.uniform(2.6, 3.4), rng.uniform(1.8, 2.4), rng.uniform(0.9, 1.3)):
                            hh = s * 0.55                    # dark foliage tiers, each with a glowing rim
                            add(x1 - s / 2, y, z1 - s / 2, x1 + s / 2, y + hh, z1 + s / 2, C.K_PANEL, hue)
                            add(x1 - s / 2 - 0.04, y, z1 - s / 2 - 0.04, x1 + s / 2 + 0.04, y + 0.07, z1 + s / 2 + 0.04,
                                C.K_EMISSIVE, hue, float(rng.uniform(1.2, 2.0)))
                            y += hh
            for a in (-6.0, 6.0):                                   # benches facing the ring
                for s in (-1, 1):
                    bench(a, s * 11.8, True)
                    bench(s * 11.8, a, False)
            for x in (-21.6, 21.6):
                for z in (-21.6, 21.6):
                    lamp(x, z, 0.45)
            # hologram statue on a plinth between the trees
            add(14.0 - 1.2, 0.0, -24.5 - 1.2, 14.0 + 1.2, 0.8, -24.5 + 1.2, C.K_PANEL, 0.83, collide=True)
            holos.append(quad((cx + 14.0, 3.6, cz - 24.5), (1.4, 0, 0), (0, 2.8, 0), C.Q_HOLO, 0.83, 1.4, 500 + pi))
            stands.append((name, cx, 0.0, cz))
        else:
            zones.append((cx - LAWN, cz - LAWN, cx + LAWN, cz + LAWN, 2))
            # fountain: square basin, glowing water, a column of light
            for x0, z0, x1, z1 in ((-5, -5, 5, -4.5), (-5, 4.5, 5, 5), (-5, -4.5, -4.5, 4.5), (4.5, -4.5, 5, 4.5)):
                add(x0, 0.0, z0, x1, 0.6, z1, C.K_PANEL, 0.5, collide=True)
            add(-4.5, 0.0, -4.5, 4.5, 0.35, 4.5, C.K_EMISSIVE, 0.5, 0.6, collide=True)
            add(-0.5, 0.35, -0.5, 0.5, 4.5, 0.5, C.K_EMISSIVE, 0.52, 2.2)
            holos.append(quad((cx, 7.5, cz), (2.5, 0, 0), (0, 2.0, 0), C.Q_HOLO, 0.5, 1.2, 520 + pi))
            for a in (-6.0, 6.0):
                for s in (-1, 1):
                    bench(a, s * 11.5, True)
                    bench(s * 11.5, a, False)
            for x, z in ((-24.5, -24.5), (24.5, -24.5), (-24.5, 24.5)):  # food carts
                if not clear(x - 2.0, z - 2.0, x + 2.0, z + 2.0):
                    continue
                hue = float(rng.choice(C.NEON_HUES))
                add(x - 1.2, 0.0, z - 0.6, x + 1.2, 1.1, z + 0.6, C.K_PANEL, hue, collide=True)
                add(x - 1.25, 1.1, z - 0.65, x + 1.25, 1.16, z + 0.65, C.K_EMISSIVE, hue, 2.5)
                for px in (-1.1, 1.1):
                    add(x + px - 0.05, 1.1, z - 0.05, x + px + 0.05, 2.4, z + 0.05, C.K_PANEL, 0.5)
                add(x - 1.5, 2.4, z - 1.0, x + 1.5, 2.7, z + 1.0, C.K_SIGN, hue, 0.0, seed=float(rng.uniform(0, 1000)))
            # giant hologram screen on two pillars at the north edge
            for px in (-8.5, 8.5):
                if clear(px - 0.4, -26.4, px + 0.4, -25.6):
                    add(px - 0.4, 0.0, -26.4, px + 0.4, 10.0, -25.6, C.K_PANEL, 0.5, collide=True)
            holos.append(quad((cx, 7.0, cz - 26.0), (8.0, 0, 0), (0, 3.0, 0), C.Q_HOLO, 0.92, 1.3, 540 + pi))
            for x, z in ((-21.0, -21.0), (21.0, -21.0), (-21.0, 21.0)):     # (+, +) corner: taxi pad
                lamp(x, z, 0.12)
            stands.append((name, cx + 23.0, 0.0, cz + 23.0))
    return ParkData(boxes, cols, holos, stands, zones)
