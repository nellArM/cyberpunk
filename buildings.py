"""Upper floors of ordinary city buildings: storey heights, the stair core and its roof hatch.

Every building's ground floor is a shop (shops.py, 18 x 14 m at the front). A switchback
stair core sits right behind the shop's back partition wall; its "staff only" door is behind
the counter. Building-local frame (shared with shops._Frame): x = a across the door face
(+-W/2), z = b - D/2, so the door face is at z = -D/2 and the core's doors face -z.
"""
import math

import numpy as np

import config as C

WT = 0.2                                  # enclosure wall thickness (as in tower_interior)
CORE_B = 14.3                             # core starts behind the shop's back wall (b 14.0 .. 14.3)
CORE_LEN = 2 * C.STAIR_LAND + C.STAIR_RUN + 2 * WT          # 6.2 m along x
CORE_DEPTH = 2 * C.STAIR_FLIGHT_W + C.STAIR_DIVIDER + 2 * WT  # 3.6 m along z
MIN_UPPER = 2.5                           # buildings need this much above the shop to have upper floors
SHAFT_MIN_H = 60.0                        # taller buildings also get an elevator next to the stairs
SHAFT_W = 3.0                             # elevator shaft width (outer), west of the stair core
SHAFT_DOOR_HALF, SHAFT_DOOR_H = 0.8, 2.6
SHAFT_CAR_H = 2.8


class Frame:
    """Shop-local frame of a city building: door at b=0, depth b grows inward, a runs across the door face."""

    def __init__(self, rec):
        lx, lz, w, d = rec.lx, rec.lz, rec.w, rec.d
        if rec.face == C.FACE_PX:
            self.W, self.D, self.f = d, w, lambda a, b: (lx + w / 2 - b, lz + a)
            self.right = (0.0, 0.0, 1.0)
        elif rec.face == C.FACE_NX:
            self.W, self.D, self.f = d, w, lambda a, b: (lx - w / 2 + b, lz - a)
            self.right = (0.0, 0.0, -1.0)
        elif rec.face == C.FACE_PZ:
            self.W, self.D, self.f = w, d, lambda a, b: (lx - a, lz + d / 2 - b)
            self.right = (-1.0, 0.0, 0.0)
        else:
            self.W, self.D, self.f = w, d, lambda a, b: (lx + a, lz - d / 2 + b)
            self.right = (1.0, 0.0, 0.0)

        x0, z0 = self.f(0.0, 0.0)
        x1, z1 = self.f(0.0, 1.0)
        self.depth = (x1 - x0, 0.0, z1 - z0)                   # unit vector pointing into the shop

    def bounds(self, a0, b0, a1, b1):
        xa, za = self.f(a0, b0)
        xb, zb = self.f(a1, b1)
        return min(xa, xb), min(za, zb), max(xa, xb), max(za, zb)


def floor_height(seed):
    """Storey height of a building's upper floors; shaders.BOX_FS computes the same from the box seed."""
    f = np.float32(seed) * np.float32(0.7548777)
    fr = f - np.floor(f)
    return 3.4 + 0.2 * float(np.floor(fr * np.float32(7.0)))


def levels(h, fh):
    """Floor surface heights: 1F (shop) at 0, 2F at SHOP_H, then every fh; the roof (h) is not included.
    The last storey (top floor to roof) is fh .. 2 fh tall."""
    ys = [0.0]
    if h - C.SHOP_H < MIN_UPPER:
        return ys
    ys.append(C.SHOP_H)
    while ys[-1] + 2 * fh <= h + 1e-6:
        ys.append(ys[-1] + fh)
    return ys


class Core:
    """Stair core geometry in building-local coordinates (same names as tower_interior's layouts)."""

    def __init__(self, W, D):
        x0 = min(4.4, W / 2 - 0.3 - CORE_LEN)                   # outer west edge of the enclosure
        self.SX0 = x0 + WT
        self.XA = self.SX0 + C.STAIR_LAND
        self.XB = self.XA + C.STAIR_RUN
        self.XC = self.XB + C.STAIR_LAND
        self.Z1A = CORE_B + WT - D / 2
        self.Z1B = self.Z1A + C.STAIR_FLIGHT_W
        self.Z2A = self.Z1B + C.STAIR_DIVIDER
        self.Z2B = self.Z2A + C.STAIR_FLIGHT_W
        self.hole = (self.XA, self.Z1A, self.XC, self.Z2B)        # slab / roof opening (x0, z0, x1, z1)
        # elevator shaft (tall buildings): outer x EX0..EX1 sharing the core's west wall, same depth;
        # the car runs inside (car), its door faces -z like the stair door
        self.EX0, self.EX1 = x0 - SHAFT_W, x0
        self.car = (self.EX0 + WT, self.Z1A, self.EX1 - WT, self.Z2B)
        ec = (self.EX0 + self.EX1) / 2
        self.door = (ec - SHAFT_DOOR_HALF, ec + SHAFT_DOOR_HALF)


def has_shaft(rec):
    return rec.h >= SHAFT_MIN_H


def frame_bounds(fr, D, x0, z0, x1, z1):
    """World (x0, z0, x1, z1) of a building-local rectangle."""
    return fr.bounds(x0, z0 + D / 2, x1, z1 + D / 2)


def hatch_world(fr):
    """World rectangle of the roof hatch above the stair core."""
    core = Core(fr.W, fr.D)
    return frame_bounds(fr, fr.D, *core.hole)


def place_tier(foot, hatch, cw, cd, margin=1.0):
    """Center and size of a setback tier of size cw x cd on a roof foot (x0, z0, x1, z1) so it keeps
    clear of the hatch: keep it centered if it fits, else move it to the largest free side."""
    x0, z0, x1, z1 = foot
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    hx0, hz0, hx1, hz1 = hatch[0] - margin, hatch[1] - margin, hatch[2] + margin, hatch[3] + margin
    if cx + cw / 2 <= hx0 or cx - cw / 2 >= hx1 or cz + cd / 2 <= hz0 or cz - cd / 2 >= hz1:
        return cx, cz, cw, cd
    best = None
    for side in ("w", "e", "n", "s"):
        if side == "w":
            room = hx0 - x0
            w, d = min(cw, room), cd
            c = (x0 + room / 2, cz)
        elif side == "e":
            room = x1 - hx1
            w, d = min(cw, room), cd
            c = (hx1 + room / 2, cz)
        elif side == "n":
            room = hz0 - z0
            w, d = cw, min(cd, room)
            c = (cx, z0 + room / 2)
        else:
            room = z1 - hz1
            w, d = cw, min(cd, room)
            c = (cx, hz1 + room / 2)
        if w > 3.0 and d > 3.0 and (best is None or w * d > best[2] * best[3]):
            best = (c[0], c[1], w, d)
    return best                                                    # None: no tier fits


def hatch_frame_boxes(hatch, y):
    """Yellow/black hazard frame around a roof hatch: (x0, y0, z0, x1, y1, z1) strips."""
    x0, z0, x1, z1 = hatch
    t = 0.25
    return [(x0 - t, y, z0 - t, x1 + t, y + 0.04, z0), (x0 - t, y, z1, x1 + t, y + 0.04, z1 + t),
            (x0 - t, y, z0, x0, y + 0.04, z1), (x1, y, z0, x1 + t, y + 0.04, z1)]


def storey_steps(rise):
    """Steps per flight for a storey of this rise (each step at most 0.25 m)."""
    return max(C.STAIR_STEPS, int(math.ceil(rise / 2 / 0.25 - 1e-9)))
