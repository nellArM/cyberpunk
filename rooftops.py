"""Rooftop facilities on city buildings without setback tiers: bars, pools and helipads.

Each sits on the base roof (walkable, reached by the stair core / elevator) clear of the
roof hatch; `add_rooftop` appends to the city's box / collider / hologram lists and returns
(kind, extra height, helipad center or None), or None when it does not fit.
"""
import numpy as np

import buildings
import config as C
import districts as D
from geometry import box_bounds, quad
from pedestrians import person_boxes

SIZES = {"bar": (10.0, 8.0), "pool": (12.0, 8.0), "helipad": (16.0, 16.0)}


def pick_kind(rng, dk, h):
    r = rng.random()
    if dk == D.CORPORATE:
        return "helipad" if (h >= buildings.SHAFT_MIN_H and r < 0.22) else ("bar" if r > 0.9 else None)
    if dk == D.RESIDENTIAL:
        return "pool" if r < 0.25 else None
    if dk in (D.DOWNTOWN, D.MARKET):
        return "bar" if r < 0.14 else None
    return None


def add_rooftop(rng, kind, foot, h, hatch, boxes, cols, holos, seed):
    fw, fd = SIZES[kind]
    spot = buildings.place_tier(foot, hatch, fw, fd)
    if spot is None or spot[2] < fw - 1e-6 or spot[3] < fd - 1e-6:
        return None
    cx, cz = spot[0], spot[1]

    def add(x0, y0, z0, x1, y1, z1, k, hue=0.0, extra=0.0, collide=False, sd=0.0):
        b = (cx + x0, h + y0, cz + z0, cx + x1, h + y1, cz + z1)
        boxes.append(box_bounds(*b, k, hue, extra, sd))
        if collide:
            cols.append(b)

    if kind == "bar":
        hue = float(rng.choice(C.NEON_HUES))
        add(-2.0, 0.0, 2.6, 2.0, 1.1, 3.5, C.K_PANEL, hue, collide=True)                    # counter
        add(-2.05, 1.1, 2.55, 2.05, 1.16, 3.55, C.K_EMISSIVE, hue, 2.5)
        add(-2.0, 1.4, 3.8, 2.0, 2.6, 3.95, C.K_EMISSIVE, float(rng.choice(C.NEON_HUES)), 1.4)  # bottle shelf
        for a in (-1.5, -0.5, 0.5, 1.5):                                                   # stools
            add(a - 0.2, 0.0, 1.8, a + 0.2, 0.8, 2.2, C.K_DOOR, hue, collide=True)
        for x, z in ((-3.0, -1.5), (2.5, -2.0)):                                           # tables with lamps
            add(x - 0.45, 0.0, z - 0.45, x + 0.45, 1.05, z + 0.45, C.K_PANEL, hue, collide=True)
            add(x - 0.06, 1.05, z - 0.06, x + 0.06, 1.25, z + 0.06, C.K_EMISSIVE, 0.12, 4.0)
        for z in (-3.9, 3.9):                                                              # string lights
            add(-4.9, 2.6, z - 0.03, 4.9, 2.65, z + 0.03, C.K_EMISSIVE, 0.12, 2.5)
        for x in (-4.9, 4.9):
            add(x - 0.05, 0.0, -3.95, x + 0.05, 2.65, -3.85, C.K_PANEL, 0.5)
            add(x - 0.05, 0.0, 3.85, x + 0.05, 2.65, 3.95, C.K_PANEL, 0.5)
        tender = person_boxes(np.array([cx]), h, np.array([cz + 3.0]), np.array([1]), np.array([-1.0]),
                              np.zeros(1, bool), np.zeros(1), np.ones(1), np.array([hue]), np.array([seed]),
                              np.zeros(1))
        boxes.extend(tender.tolist())
        holos.append(quad((cx, h + 3.6, cz + 3.9), (2.2, 0, 0), (0, 0.6, 0), C.Q_HOLO, hue, 1.4, seed + 7))
        return kind, 3.0, None
    if kind == "pool":
        for x0, z0, x1, z1 in ((-6, -4, 6, -3.7), (-6, 3.7, 6, 4), (-6, -3.7, -5.7, 3.7), (5.7, -3.7, 6, 3.7)):
            add(x0, 0.0, z0, x1, 0.5, z1, C.K_PANEL, 0.5, collide=True)                      # rim
        add(-5.7, 0.05, -3.7, 5.7, 0.4, 3.7, C.K_EMISSIVE, 0.5, 0.7)                        # water
        add(-5.7, 0.4, -3.7, 5.7, 0.42, 3.7, C.K_EMISSIVE, 0.52, 1.6)                       # surface glints
        for x0, z0, x1, z1 in ((-6, -5.6, -3, -4.6), (-1.5, -5.6, 1.5, -4.6), (3, -5.6, 6, -4.6)):   # loungers
            add(x0, 0.0, z0, x1, 0.4, z1, C.K_PANEL, 0.08, collide=True)
        for x in (-5.4, 5.4):                                                              # planters
            add(x - 0.6, 0.0, 4.4, x + 0.6, 0.6, 5.6, C.K_PANEL, 0.33, collide=True)
            add(x - 0.55, 0.6, 4.45, x + 0.55, 0.75, 5.55, C.K_EMISSIVE, 0.33, 0.8)
        return kind, 0.8, None
    # helipad
    add(-8.0, 0.0, -8.0, 8.0, 0.06, 8.0, C.K_FLOOR, 0.12, 0.0, collide=True)
    for x0, z0, x1, z1 in ((-6, -6, 6, -5.8), (-6, 5.8, 6, 6), (-6, -5.8, -5.8, 5.8), (5.8, -5.8, 6, 5.8)):
        add(x0, 0.06, z0, x1, 0.09, z1, C.K_EMISSIVE, 0.12, 3.0)
    for x0, z0, x1, z1 in ((-2.2, -3, -1.4, 3), (1.4, -3, 2.2, 3), (-1.4, -0.4, 1.4, 0.4)):  # H
        add(x0, 0.06, z0, x1, 0.09, z1, C.K_EMISSIVE, -1.0, 2.5)
    for x in (-7.7, 7.7):                                                                   # blinking corner lights
        for z in (-7.7, 7.7):
            add(x - 0.15, 0.06, z - 0.15, x + 0.15, 0.6, z + 0.15, C.K_ANTENNA, 0.0, 0.0, sd=seed + x + z)
    return kind, 0.6, (cx, h + 0.06, cz)
