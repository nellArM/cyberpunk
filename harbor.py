"""The harbor on the city's south edge: quay with promenade, piers, a lighthouse, container
cranes over the water, a container yard, moored and moving boats.

The sea starts at config.SHORE_Z: the ground shader draws it as water 1.2 m below the street
(collision treats it as a hole), so anyone falling in is fished out by main.py.
"""
import math

import numpy as np

import config as C
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS

SHORE = C.SHORE_Z
WATER_Y = -1.2
EXTENT = C.CITY_BLOCKS * C.BLOCK_PITCH + C.BLOCK_PITCH / 2
PIERS = ((-400.0, 3.0), (0.0, 7.0), (400.0, 3.0))       # (center x, half width)
PIER_END = SHORE + 120.0
DECK_Y = 0.6
CRANES = (-900.0, -780.0, -660.0, -540.0)
LIGHTHOUSE = (400.0, PIER_END + 4.0)
BOAT_LANES = (1340.0, 1420.0, 1520.0, 1650.0, 2800.0)             # clear of 霓虹島 and the park


class HarborData:
    def __init__(self, boxes, cols, holos, obstacles, stand, walk_loops):
        self.boxes = np.array(boxes, "f4").reshape(-1, BOX_FLOATS)
        self.colliders = cols
        self.holos = np.array(holos, "f4").reshape(-1, QUAD_FLOATS)
        self.obstacles = obstacles            # (x0, z0, x1, z1, top) for taxi routes
        self.stand = stand                    # (name, x, y, z) air-taxi stand on the main pier
        self.walk_loops = walk_loops          # crowds.LaneCrowd loops on the promenade


def in_water(x, z):
    """Is (x, z) open water (not on a pier)?"""
    if z <= SHORE:
        return False
    return not any(abs(x - px) < hw and z < PIER_END for px, hw in PIERS)


def build_harbor(rng):
    boxes, cols, holos, obstacles = [], [], [], []

    def add(x0, y0, z0, x1, y1, z1, kind, hue=0.0, extra=0.0, collide=False, seed=0.0):
        boxes.append(box_bounds(x0, y0, z0, x1, y1, z1, kind, hue, extra, seed))
        if collide:
            cols.append((x0, y0, z0, x1, y1, z1))

    # quay wall down to the water, railing with gaps at the piers, lamps
    add(-EXTENT, -3.0, SHORE, EXTENT, 0.0, SHORE + 0.4, C.K_PANEL, 0.5, collide=True)
    add(-EXTENT, -0.06, SHORE + 0.4, EXTENT, 0.0, SHORE + 0.45, C.K_EMISSIVE, 0.5, 2.0)
    gaps = sorted((px - hw, px + hw) for px, hw in PIERS)
    x = -EXTENT
    for g0, g1 in gaps + [(EXTENT, EXTENT)]:
        if g0 > x:
            add(x, 0.0, SHORE - 0.25, g0, 1.1, SHORE - 0.1, C.K_PANEL, 0.5, collide=True)
            add(x, 1.1, SHORE - 0.27, g0, 1.15, SHORE - 0.08, C.K_EMISSIVE, 0.5, 2.2)
        x = g1
    for lx in np.arange(-1200.0, 1200.1, 25.0):
        if any(abs(lx - px) < hw + 1.0 for px, hw in PIERS):
            continue
        add(lx - 0.08, 0.0, SHORE - 1.3, lx + 0.08, 4.5, SHORE - 1.14, C.K_PANEL, 0.5, collide=True)
        add(lx - 0.3, 4.5, SHORE - 1.5, lx + 0.3, 4.7, SHORE - 0.94, C.K_EMISSIVE, 0.12, 3.0)

    # piers: a step up, deck on piles, railings, lamps, bollards, moored boats
    for px, hw in PIERS:
        add(px - hw, 0.0, SHORE - 0.8, px + hw, 0.3, SHORE, C.K_DOOR, 0.5, collide=True)
        add(px - hw, DECK_Y - 0.4, SHORE, px + hw, DECK_Y, PIER_END, C.K_FLOOR, 0.08, collide=True)
        for z in np.arange(SHORE + 6.0, PIER_END, 12.0):
            for sx in (-1, 1):
                add(px + sx * (hw - 0.4) - 0.3, -3.0, z - 0.3, px + sx * (hw - 0.4) + 0.3, DECK_Y - 0.4, z + 0.3,
                    C.K_PANEL, 0.5)
        for sx in (-1, 1):
            rx = px + sx * hw
            add(min(rx, rx - sx * 0.12), DECK_Y, SHORE, max(rx, rx - sx * 0.12), DECK_Y + 1.1, PIER_END,
                C.K_PANEL, 0.5, collide=True)
            add(min(rx, rx - sx * 0.12), DECK_Y + 1.1, SHORE, max(rx, rx - sx * 0.12), DECK_Y + 1.15, PIER_END,
                C.K_EMISSIVE, 0.55, 2.5)
        if px == 0.0:                                      # the main pier: gangway to the ferry
            for a0, a1 in ((px - hw, px - 4.0), (px + 4.0, px + hw)):
                add(a0, DECK_Y, PIER_END - 0.12, a1, DECK_Y + 1.1, PIER_END, C.K_PANEL, 0.5, collide=True)
            add(px - 4.3, DECK_Y, PIER_END - 0.3, px + 4.3, DECK_Y + 0.03, PIER_END, C.K_EMISSIVE, 0.5, 3.0)
        else:
            add(px - hw, DECK_Y, PIER_END - 0.12, px + hw, DECK_Y + 1.1, PIER_END, C.K_PANEL, 0.5, collide=True)
        for z in np.arange(SHORE + 15.0, PIER_END, 22.0):
            for sx in (-1, 1):
                lx = px + sx * (hw - 0.5)
                add(lx - 0.07, DECK_Y, z - 0.07, lx + 0.07, DECK_Y + 4.0, z + 0.07, C.K_PANEL, 0.5, collide=True)
                add(lx - 0.25, DECK_Y + 4.0, z - 0.25, lx + 0.25, DECK_Y + 4.15, z + 0.25, C.K_EMISSIVE, 0.55, 3.0)
        for z in np.arange(SHORE + 20.0, PIER_END - 10.0, 34.0):             # moored boats alongside
            sx = 1 if rng.random() < 0.5 else -1
            bx = px + sx * (hw + 3.0)
            hue = float(rng.choice(C.NEON_HUES))
            add(bx - 2.2, WATER_Y - 0.6, z - 7.0, bx + 2.2, WATER_Y + 1.2, z + 7.0, C.K_VEHICLE, hue, 1.0)
            add(bx - 1.5, WATER_Y + 1.2, z - 1.0, bx + 1.5, WATER_Y + 3.2, z + 3.5, C.K_VEHICLE, hue, 0.0)
            add(bx - 2.25, WATER_Y + 0.0, z - 7.05, bx + 2.25, WATER_Y + 0.1, z + 7.05, C.K_EMISSIVE, hue, 3.0)
    stand = ("港灣碼頭", 0.0, DECK_Y, SHORE + 80.0)

    # lighthouse at the end of the east pier
    lx, lz = LIGHTHOUSE
    add(lx - 3.5, -3.0, lz - 3.5, lx + 3.5, DECK_Y, lz + 3.5, C.K_PANEL, 0.5, collide=True)
    add(lx - 2.0, DECK_Y, lz - 2.0, lx + 2.0, 24.0, lz + 2.0, C.K_PANEL, 0.97, collide=True)
    for y in (6.0, 12.0, 18.0):
        add(lx - 2.05, y, lz - 2.05, lx + 2.05, y + 1.2, lz + 2.05, C.K_EMISSIVE, 0.97, 1.6)
    add(lx - 1.5, 24.0, lz - 1.5, lx + 1.5, 27.0, lz + 1.5, C.K_EMISSIVE, 0.14, 6.0)
    add(lx - 1.8, 27.0, lz - 1.8, lx + 1.8, 27.5, lz + 1.8, C.K_PANEL, 0.5, collide=True)
    add(lx - 0.3, 27.5, lz - 0.3, lx + 0.3, 30.0, lz + 0.3, C.K_ANTENNA, 0.0, 0.0, seed=3.0)
    obstacles.append((lx - 4.0, lz - 4.0, lx + 4.0, lz + 4.0, 30.0))

    # container cranes on the quay in front of the container yard, booms over the water
    for cx in CRANES:
        for sx in (-1, 1):
            for z in (SHORE - 9.0, SHORE - 1.0):
                add(cx + sx * 7.0 - 0.6, 0.0, z - 0.6, cx + sx * 7.0 + 0.6, 42.0, z + 0.6, C.K_PANEL, 0.1, collide=True)
        add(cx - 7.6, 42.0, SHORE - 10.0, cx + 7.6, 45.0, SHORE, C.K_PANEL, 0.1, collide=True)        # cross beam
        add(cx - 1.2, 42.0, SHORE - 30.0, cx + 1.2, 44.5, SHORE + 50.0, C.K_PANEL, 0.1, collide=True)  # boom
        add(cx - 1.25, 41.9, SHORE - 30.0, cx + 1.25, 42.0, SHORE + 50.0, C.K_EMISSIVE, 0.1, 2.0)
        add(cx - 0.3, 44.5, SHORE + 49.4, cx + 0.3, 45.6, SHORE + 50.0, C.K_ANTENNA, 0.0, 0.0, seed=cx)
        add(cx - 1.5, 30.0, SHORE + 18.0, cx + 1.5, 32.0, SHORE + 21.0, C.K_PANEL, 0.12)               # trolley
        obstacles.append((cx - 8.0, SHORE - 31.0, cx + 8.0, SHORE + 51.0, 46.0))

    # container yard on the harbor blocks reserved for it
    pal = (0.0, 0.08, 0.55, 0.6, 0.33, 0.12, 0.97)
    hb = C.BLOCK_PITCH / 2 - C.ROAD_HALF - 2.5
    for i in C.CONTAINER_BLOCKS:
        bx, bz = i * C.BLOCK_PITCH, C.HARBOR_ROW * C.BLOCK_PITCH
        for row, z in enumerate(np.arange(bz - hb + 1.5, bz + hb - 2.6, 3.0)):
            if row % 5 == 4:
                continue                                                      # aisle
            for x in np.arange(bx - hb + 0.5, bx + hb - 12.2, 13.6):
                n = int(rng.integers(1, 5))
                for k in range(n):
                    add(x, 2.6 * k, z, x + 12.2, 2.6 * (k + 1) - 0.05, z + 2.44, C.K_PANEL, float(rng.choice(pal)))
                cols.append((x, 0.0, z, x + 12.2, 2.6 * n, z + 2.44))
        obstacles.append((bx - hb, bz - hb, bx + hb, bz + hb, 11.0))

    # floating holograms over the water
    for k, (hx, hz, hw, hh) in enumerate(((-250.0, 1360.0, 22.0, 9.0), (260.0, 1420.0, 18.0, 8.0), (0.0, 1560.0, 30.0, 12.0))):
        holos.append(quad((hx, 20.0 + hh, hz), (hw, 0, 0), (0, hh, 0), C.Q_HOLO, float(rng.choice(C.NEON_HUES)),
                          1.2, 700 + k))
    # promenade strollers (east of the cranes)
    walk = [([(-480.0, SHORE - 7.0), (650.0, SHORE - 7.0), (650.0, SHORE - 4.0), (-480.0, SHORE - 4.0)], 0.0, 50)]
    return HarborData(boxes, cols, holos, obstacles, stand, walk)


class Boats:
    """Boats cruising back and forth on lanes out at sea (dynamic boxes)."""

    def __init__(self, rng, count=24):
        self.n = count
        self.lane = rng.choice(BOAT_LANES, count) + rng.uniform(-6, 6, count)
        self.dir = rng.choice([-1.0, 1.0], count)
        self.speed = rng.uniform(6.0, 14.0, count)
        self.x = rng.uniform(-EXTENT, EXTENT, count)
        self.hue = rng.choice(C.NEON_HUES, count)
        self.length = rng.uniform(10.0, 22.0, count)

    def update(self, dt):
        self.x += self.dir * self.speed * dt
        e = EXTENT + 200.0
        self.x = (self.x + e) % (2 * e) - e

    def instances(self):
        n = self.n
        out = np.zeros((n, 3, BOX_FLOATS), "f4")
        L = self.length
        out[:, 0] = np.stack([self.x, np.full(n, WATER_Y - 0.6), self.lane, L, np.full(n, 1.8), np.full(n, 4.2),
                              np.zeros(n), np.full(n, C.K_VEHICLE), self.hue, self.dir], 1)
        out[:, 1] = np.stack([self.x - self.dir * L * 0.1, np.full(n, WATER_Y + 1.2), self.lane, L * 0.35,
                              np.full(n, 2.2), np.full(n, 3.0), np.zeros(n), np.full(n, C.K_VEHICLE), self.hue,
                              np.zeros(n)], 1)
        out[:, 2] = np.stack([self.x, np.full(n, WATER_Y + 0.05), self.lane, L + 0.1, np.full(n, 0.1), np.full(n, 4.3),
                              np.zeros(n), np.full(n, C.K_EMISSIVE), self.hue, np.full(n, 3.0)], 1)
        return out.reshape(-1, BOX_FLOATS)
