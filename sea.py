"""Out at sea, south of the harbor (all on the x = 0 axis, decks at y = 0.6 like the piers):
霓虹島 (an artificial island with a ferry station, a seafood terrace, neon trees and a giant
hologram) and 海上遊樂園 (a floating amusement park: Ferris wheel, drop tower, carousel,
game stalls). Two double-ended ferries link the harbor pier, the island and the park.
"""
import math
from collections import namedtuple

import numpy as np

import config as C
import harbor
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS
from pedestrians import person_boxes
from rides import Carousel, DropTower, FerrisWheel, Ferry, Rides

DECK = harbor.DECK_Y
ISLAND = (-150.0, 1800.0, 150.0, 2100.0)
ISLAND_DOCKS = ((-6.0, 1760.0, 6.0, 1800.0), (-6.0, 2100.0, 6.0, 2140.0))
PARK = (-120.0, 2400.0, 120.0, 2640.0)
PARK_DOCK = (-6.0, 2360.0, 6.0, 2400.0)
WHEEL = (-50.0, 36.0, 2560.0)                    # Ferris wheel center
TOWER = (60.0, 2470.0)                           # drop tower
CAROUSEL = (40.0, 2585.0)
# where someone who fell in the water is put back (with the city quay)
RESCUE = ((0.0, DECK, 1835.0), (0.0, DECK, 2075.0), (0.0, DECK, 2412.0))

Talker = namedtuple("Talker", "x y z name line")


class SeaData:
    def __init__(self, boxes, cols, holos, talkers, walk_loops, obstacles, rides):
        self.boxes = np.array(boxes, "f4").reshape(-1, BOX_FLOATS)
        self.colliders = cols
        self.holos = np.array(holos, "f4").reshape(-1, QUAD_FLOATS)
        self.talkers = talkers
        self.walk_loops = walk_loops
        self.obstacles = obstacles
        self.rides = rides


def area(pos):
    x, y, z = pos
    if y < -1.0:
        return None
    if ISLAND[0] <= x <= ISLAND[2] and ISLAND_DOCKS[0][1] <= z <= ISLAND_DOCKS[1][3]:
        return "霓虹島"
    if PARK[0] <= x <= PARK[2] and PARK_DOCK[1] <= z <= PARK[3]:
        return "海上遊樂園"
    return None


def build_sea(rng):
    boxes, cols, holos, talkers, obstacles = [], [], [], [], []
    P, E, F = C.K_PANEL, C.K_EMISSIVE, C.K_FLOOR

    def add(x0, y0, z0, x1, y1, z1, kind, hue=0.0, extra=0.0, collide=False, seed=0.0):
        boxes.append(box_bounds(x0, y0, z0, x1, y1, z1, kind, hue, extra, seed))
        if collide:
            cols.append((x0, y0, z0, x1, y1, z1))

    def deck(rect, hue, gaps):
        """A floating deck with a railing round its edge, open where `gaps` (x0, x1, edge) meet docks."""
        x0, z0, x1, z1 = rect
        add(x0, -3.0, z0, x1, DECK, z1, F, hue, collide=True)
        add(x0 - 0.05, DECK - 0.3, z0 - 0.05, x1 + 0.05, DECK - 0.2, z1 + 0.05, E, hue, 3.0)
        for edge, (a0, a1) in (("n", (x0, x1)), ("s", (x0, x1))):
            z = z0 if edge == "n" else z1 - 0.12
            xs = [a0] + [v for g0, g1, e in gaps if e == edge for v in (g0, g1)] + [a1]
            for p0, p1 in zip(xs[0::2], xs[1::2]):
                add(p0, DECK, z, p1, DECK + 1.1, z + 0.12, P, 0.5, collide=True)
                add(p0, DECK + 1.1, z - 0.02, p1, DECK + 1.15, z + 0.14, E, hue, 2.2)
        for x in (x0, x1 - 0.12):
            add(x, DECK, z0, x + 0.12, DECK + 1.1, z1, P, 0.5, collide=True)
            add(x - 0.02, DECK + 1.1, z0, x + 0.14, DECK + 1.15, z1, E, hue, 2.2)

    def dock(rect, hue):
        x0, z0, x1, z1 = rect
        add(x0, -3.0, z0, x1, DECK, z1, F, 0.08, collide=True)
        for x in (x0, x1 - 0.12):
            add(x, DECK, z0, x + 0.12, DECK + 1.1, z1, P, 0.5, collide=True)
            add(x - 0.02, DECK + 1.1, z0, x + 0.14, DECK + 1.15, z1, E, hue, 2.5)
        for z in np.arange(z0 + 3.0, z1, 8.0):
            for x in (x0 + 0.5, x1 - 0.5):
                add(x - 0.07, DECK, z - 0.07, x + 0.07, DECK + 3.8, z + 0.07, P, 0.5, collide=True)
                add(x - 0.25, DECK + 3.8, z - 0.25, x + 0.25, DECK + 3.95, z + 0.25, E, hue, 3.0)

    def lamp(x, z, hue):
        add(x - 0.08, DECK, z - 0.08, x + 0.08, DECK + 4.2, z + 0.08, P, 0.5, collide=True)
        add(x - 0.3, DECK + 4.2, z - 0.3, x + 0.3, DECK + 4.4, z + 0.3, E, hue, 3.0)

    def tree(x, z, hue):
        th = rng.uniform(2.8, 3.8)
        add(x - 0.22, DECK, z - 0.22, x + 0.22, DECK + th, z + 0.22, P, 0.33, collide=True)
        y = DECK + th
        for s in (rng.uniform(2.6, 3.4), rng.uniform(1.8, 2.4), rng.uniform(0.9, 1.3)):
            hh = s * 0.55
            add(x - s / 2, y, z - s / 2, x + s / 2, y + hh, z + s / 2, P, hue)
            add(x - s / 2 - 0.04, y, z - s / 2 - 0.04, x + s / 2 + 0.04, y + 0.07, z + s / 2 + 0.04, E, hue,
                float(rng.uniform(1.2, 2.0)))
            y += hh

    def bench(x, z, along_x=True):
        hx, hz = (0.9, 0.3) if along_x else (0.3, 0.9)
        add(x - hx, DECK, z - hz, x + hx, DECK + 0.45, z + hz, P, 0.5, collide=True)

    def clerk(x, z, face, hue, name, line):
        fig = person_boxes(np.array([x]), DECK, np.array([z]), np.array([face[0]]), np.array([face[1]]),
                           np.zeros(1, bool), np.zeros(1), np.ones(1), np.array([hue]),
                           np.array([float(rng.uniform(0, 1000))]), np.zeros(1))
        boxes.extend(fig.tolist())
        cols.append((x - 0.3, DECK, z - 0.3, x + 0.3, DECK + 1.8, z + 0.3))
        talkers.append(Talker(x, DECK, z, name, line))

    # ------------------------------------------------------------------ 霓虹島
    ix0, iz0, ix1, iz1 = ISLAND
    deck(ISLAND, 0.5, [(-6.0, 6.0, "n"), (-6.0, 6.0, "s")])
    for d in ISLAND_DOCKS:
        dock(d, 0.5)
    for z0 in (iz0 + 0.5, iz1 - 14.0):                                 # ferry shelters at both docks
        for x in (-9.0, 9.0):
            for z in (z0, z0 + 13.0):
                add(x - 0.15, DECK, z - 0.15, x + 0.15, DECK + 4.0, z + 0.15, P, 0.5, collide=True)
        add(-9.5, DECK + 4.0, z0 - 0.5, 9.5, DECK + 4.3, z0 + 13.5, C.K_SHOP_CEIL, 0.5, 0.8)
        add(-9.6, DECK + 3.95, z0 - 0.6, 9.6, DECK + 4.0, z0 + 13.6, E, 0.5, 3.0)
        for x in (-6.5, 6.5):
            bench(x, z0 + 6.5, False)
    holos.append(quad((0.0, DECK + 6.0, iz0 + 14.5), (5.0, 0, 0), (0, 0.8, 0), C.Q_HOLO, 0.5, 1.5, 900))
    # boardwalk lights and neon trees around a central lawn
    for x in np.arange(ix0 + 12.0, ix1 - 11.0, 18.0):
        for z in (iz0 + 24.0, iz1 - 24.0):
            if abs(x) > 12.0:
                lamp(x, z, 0.5)
    for k in range(40):
        a = 2.0 * math.pi * k / 40.0
        x, z = 70.0 * math.cos(a), (iz0 + iz1) / 2 + 85.0 * math.sin(a)
        if abs(x) > 8.0 or abs(z - (iz0 + iz1) / 2) < 60.0:
            tree(x, z, float(rng.choice((0.33, 0.45, 0.5, 0.9, 0.83))))
    cz = (iz0 + iz1) / 2
    add(-3.0, DECK, cz - 3.0, 3.0, DECK + 1.2, cz + 3.0, P, 0.83, collide=True)               # hologram plinth
    add(-3.05, DECK + 1.2, cz - 3.05, 3.05, DECK + 1.3, cz + 3.05, E, 0.83, 3.0)
    holos.append(quad((0.0, DECK + 14.0, cz), (6.0, 0, 0), (0, 12.0, 0), C.Q_HOLO, 0.83, 1.4, 901))
    holos.append(quad((0.0, DECK + 14.0, cz), (0, 0, 6.0), (0, 12.0, 0), C.Q_HOLO, 0.5, 1.4, 902))
    for a in range(8):
        r = 14.0
        x, z = r * math.cos(a * math.pi / 4), cz + r * math.sin(a * math.pi / 4)
        bench(x, z, abs(math.sin(a * math.pi / 4)) > 0.7)
    # seafood terrace on the east side, facing the open sea
    tx, tz = 105.0, cz
    add(tx - 12.0, DECK, tz - 15.0, tx + 12.0, DECK + 0.2, tz + 15.0, F, 0.08, collide=True)
    for x in (tx - 11.5, tx + 11.5):
        for z in (tz - 14.5, tz + 14.5):
            add(x - 0.2, DECK + 0.2, z - 0.2, x + 0.2, DECK + 4.5, z + 0.2, P, 0.5, collide=True)
    add(tx - 12.2, DECK + 4.5, tz - 15.2, tx + 12.2, DECK + 4.8, tz + 15.2, C.K_SHOP_CEIL, 0.08, 1.0)
    add(tx - 12.3, DECK + 4.45, tz - 15.3, tx + 12.3, DECK + 4.5, tz + 15.3, E, 0.08, 3.0)
    add(tx + 7.0, DECK + 0.2, tz - 8.0, tx + 8.0, DECK + 1.3, tz + 8.0, P, 0.08, collide=True)  # counter
    add(tx + 6.95, DECK + 1.3, tz - 8.05, tx + 8.05, DECK + 1.36, tz + 8.05, E, 0.08, 2.5)
    clerk(tx + 9.2, tz, (0, -1.0), 0.08, "海景餐廳", "今天的炭烤合成龍蝦配霓虹海鹽，不吃可惜。")
    for x in np.arange(tx - 9.0, tx + 4.0, 3.5):
        for z in np.arange(tz - 11.0, tz + 12.0, 4.5):
            add(x - 0.5, DECK + 0.2, z - 0.5, x + 0.5, DECK + 0.95, z + 0.5, P, 0.08, collide=True)
            add(x - 0.06, DECK + 0.95, z - 0.06, x + 0.06, DECK + 1.15, z + 0.06, E, 0.12, 4.0)
    holos.append(quad((tx, DECK + 6.0, tz - 15.4), (5.0, 0, 0), (0, 0.9, 0), C.Q_HOLO, 0.08, 1.5, 903))

    # ------------------------------------------------------------------ 海上遊樂園
    px0, pz0, px1, pz1 = PARK
    deck(PARK, 0.92, [(-6.0, 6.0, "n")])
    dock(PARK_DOCK, 0.92)
    for x in (-8.0, 8.0):                                               # entrance arch
        add(x - 0.5, DECK, pz0 + 3.0, x + 0.5, DECK + 9.0, pz0 + 4.0, P, 0.92, collide=True)
        add(x - 0.55, DECK, pz0 + 2.95, x + 0.55, DECK + 9.0, pz0 + 3.0, E, 0.92, 3.0)
    add(-8.5, DECK + 9.0, pz0 + 3.0, 8.5, DECK + 10.5, pz0 + 4.0, C.K_SIGN, 0.92, seed=11.0)
    holos.append(quad((0.0, DECK + 12.5, pz0 + 3.5), (6.0, 0, 0), (0, 1.2, 0), C.Q_HOLO, 0.92, 1.6, 910))

    # Ferris wheel: rim, spokes, hub, A-frame legs, boarding platform with stairs
    wx, wy, wz = WHEEL
    R = FerrisWheel.R
    for k in range(64):
        a = 2.0 * math.pi * k / 64
        x, y = wx + R * math.cos(a), wy + R * math.sin(a)
        add(x - 0.7, y - 0.7, wz - 0.35, x + 0.7, y + 0.7, wz + 0.35, P, 0.5)
        if k % 2 == 0:
            add(x - 0.25, y - 0.25, wz + 0.35, x + 0.25, y + 0.25, wz + 0.45, E, C.NEON_HUES[k % 7], 4.0)
    for k in range(12):
        a = 2.0 * math.pi * k / 12 + math.pi / 12
        for t in np.arange(2.5, R - 1.0, 2.5):
            x, y = wx + t * math.cos(a), wy + t * math.sin(a)
            add(x - 0.2, y - 0.2, wz - 0.2, x + 0.2, y + 0.2, wz + 0.2, P, 0.5)
            add(x - 0.08, y - 0.08, wz + 0.2, x + 0.08, y + 0.08, wz + 0.28, E, 0.5, 2.5)
    add(wx - 1.5, wy - 1.5, wz - 2.5, wx + 1.5, wy + 1.5, wz + 1.0, P, 0.92)
    add(wx - 1.6, wy - 1.6, wz + 1.0, wx + 1.6, wy + 1.6, wz + 1.1, E, 0.92, 4.0)
    for lz in (wz - 2.5, wz + 5.6):
        for sx in (-1, 1):
            for t in np.linspace(0.0, 1.0, 16):
                x = wx + sx * 18.0 * (1.0 - t)
                y = DECK + (wy - DECK) * t
                add(x - 0.45, y - 0.9, lz - 0.45, x + 0.45, y + 0.9, lz + 0.45, P, 0.5, collide=t < 0.2)
    obstacles.append((wx - 33.0, wz - 6.0, wx + 33.0, wz + 10.0, wy + R + 6.0))
    by = FerrisWheel(WHEEL).board_y
    fz = wz + FerrisWheel.FRONT + 1.5
    add(wx - 3.0, -3.0, fz, wx + 3.0, by, fz + 4.5, F, 0.92, collide=True)                    # boarding deck
    nsteps = int(round((by - DECK) / 0.2))
    for i in range(1, nsteps + 1):                                                           # stairs up to it
        t = DECK + 0.2 * i
        z1 = fz + 4.5 + 0.3 * (nsteps - i + 1)
        add(wx - 1.5, t - 0.3, z1 - 0.3, wx + 1.5, t, z1, C.K_DOOR, 0.92, collide=True)
    for x in (wx - 3.0, wx + 2.88):
        add(x, by, fz, x + 0.12, by + 1.1, fz + 4.5, P, 0.5, collide=True)
    holos.append(quad((wx, by + 3.5, fz + 4.4), (2.4, 0, 0), (0, 0.5, 0), C.Q_HOLO, 0.92, 1.5, 911))

    # drop tower column with light bands and a crown
    dx, dz = TOWER
    add(dx - 1.0, DECK, dz - 1.0, dx + 1.0, 66.0, dz + 1.0, P, 0.92, collide=True)
    for y in np.arange(4.0, 64.0, 6.0):
        add(dx - 1.05, y, dz - 1.05, dx + 1.05, y + 0.4, dz + 1.05, E, 0.92, 3.0)
    add(dx - 2.5, 66.0, dz - 2.5, dx + 2.5, 67.5, dz + 2.5, C.K_SIGN, 0.92, seed=12.0)
    add(dx - 0.3, 67.5, dz - 0.3, dx + 0.3, 70.0, dz + 0.3, C.K_ANTENNA, 0.0, 0.0, seed=13.0)
    add(dx - 4.5, DECK, dz - 4.5, dx + 4.5, DECK + 0.05, dz + 4.5, E, 0.92, 1.2)
    obstacles.append((dx - 5.0, dz - 5.0, dx + 5.0, dz + 5.0, 72.0))

    # carousel base and canopy
    cx, cz2 = CAROUSEL
    add(cx - 8.0, DECK, cz2 - 8.0, cx + 8.0, DECK + 0.3, cz2 + 8.0, F, 0.12, collide=True)
    add(cx - 0.5, DECK + 0.3, cz2 - 0.5, cx + 0.5, DECK + 5.0, cz2 + 0.5, P, 0.12, collide=True)
    add(cx - 8.5, DECK + 5.0, cz2 - 8.5, cx + 8.5, DECK + 5.8, cz2 + 8.5, C.K_SIGN, 0.12, seed=14.0)
    for a in range(8):
        x, z = cx + 7.6 * math.cos(a * math.pi / 4), cz2 + 7.6 * math.sin(a * math.pi / 4)
        add(x - 0.12, DECK + 0.3, z - 0.12, x + 0.12, DECK + 5.0, z + 0.12, E, 0.12, 2.0)

    # game stalls along both long sides, string lights, benches
    kinds = ("射氣球", "套圈圈", "抓娃娃", "霓虹棉花糖", "全像算命", "電子彈珠")
    for i, (x, sx) in enumerate([(px0 + 4.0, 1)] * 3 + [(px1 - 4.0, -1)] * 3):
        z = pz0 + 40.0 + (i % 3) * 60.0
        hue = C.NEON_HUES[i % 7]
        c0, c1 = sorted((x + sx * 1.0, x + sx * 3.0))                   # counter on the open (inner) side
        add(c0, DECK, z - 4.0, c1, DECK + 1.0, z + 4.0, P, hue, collide=True)
        add(c0, DECK + 1.0, z - 4.05, c1, DECK + 1.06, z + 4.05, E, hue, 2.5)
        add(x - 3.5, DECK + 3.4, z - 4.5, x + 3.5, DECK + 3.8, z + 4.5, C.K_SIGN, hue, seed=float(20 + i))
        for xx in (x - 3.2, x + 3.2):
            for zz in (z - 4.3, z + 4.3):
                add(xx - 0.08, DECK, zz - 0.08, xx + 0.08, DECK + 3.4, zz + 0.08, P, 0.5)
        clerk(x - sx * 1.0, z, (0, float(sx)), hue, kinds[i], C.PARK_LINES[i % len(C.PARK_LINES)])
    for x in np.arange(px0 + 20.0, px1 - 19.0, 20.0):
        lamp(x, pz0 + 20.0, 0.92)
        lamp(x, pz1 - 20.0, 0.92)
    for z in np.arange(pz0 + 30.0, pz1 - 20.0, 40.0):
        add(px0 + 10.0, DECK + 4.0, z - 0.03, px1 - 10.0, DECK + 4.05, z + 0.03, E, 0.12, 2.5)
        bench(-15.0, z, True)
        bench(15.0, z, True)

    # ------------------------------------------------------------------ ferries and rides
    pier_end = harbor.PIER_END
    ferries = [Ferry(0.0, pier_end + Ferry.L, ISLAND_DOCKS[0][1] - Ferry.L, ("港灣碼頭", "霓虹島"), 0.5),
               Ferry(0.0, ISLAND_DOCKS[1][3] + Ferry.L, PARK_DOCK[1] - Ferry.L, ("霓虹島", "海上遊樂園"), 0.92)]
    rides = Rides(ferries, FerrisWheel(WHEEL), DropTower(*TOWER), Carousel((cx, DECK + 0.3, cz2)))

    walk = [([(-120.0, iz0 + 15.0), (120.0, iz0 + 15.0), (120.0, iz1 - 15.0), (-120.0, iz1 - 15.0)], DECK, 30),
            ([(-95.0, pz0 + 20.0), (95.0, pz0 + 20.0), (95.0, pz1 - 15.0), (-95.0, pz1 - 15.0)], DECK, 35)]
    return SeaData(boxes, cols, holos, talkers, walk, obstacles, rides)
