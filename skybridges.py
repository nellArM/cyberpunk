"""Skybridges between pairs of tall city buildings facing each other across a road.

A bridge leaves building A at one of its floors and reaches building B at B's nearest floor
(a few 0.2 m steps make up the difference). Walking onto a bridge opens up the nearer
building (shops.ShopManager.building_at); the door in its facade is cut by the shader and by
the hollow shell colliders (tower_interior.BuildingLayout).
"""
import math
from collections import Counter, defaultdict, namedtuple

import buildings
import config as C
import districts as D
from geometry import box_bounds

# a, b: shop indices; axis 0 = runs along x (A west of B), 1 = along z (A north of B);
# deck: walkable rect (x0, z0, x1, z1); ya, yb: floor heights at the two ends; doors: {index: door box}
Bridge = namedtuple("Bridge", "a b axis deck ya yb doors")

ELIGIBLE = (D.DOWNTOWN, D.CORPORATE, D.MARKET)
FLY_LAYERS = (28.0, 45.0, 70.0, 100.0, 140.0, 190.0, 260.0)     # city.Traffic altitudes (+-3 m)
HALF_W = 1.6                                                    # deck half width (incl. railings)
DOOR_HALF, DOOR_H = 1.0, 2.6
APPROACH = 3.5                                                  # kept clear inside, in front of a door


def _core_rects(rec):
    """World 2D rects of a building's stair core and elevator shaft."""
    fr = buildings.Frame(rec)
    core = buildings.Core(fr.W, fr.D)
    wt = buildings.WT
    rects = [buildings.frame_bounds(fr, fr.D, core.SX0 - wt, core.Z1A - wt, core.XC + wt, core.Z2B + wt)]
    if buildings.has_shaft(rec):
        rects.append(buildings.frame_bounds(fr, fr.D, core.EX0, core.Z1A - wt, core.EX1, core.Z2B + wt))
    return rects


def approach_rect(rec, door):
    """World 2D rect just inside the facade in front of a door box."""
    x0, y0, z0, x1, y1, z1 = door
    if x1 - x0 < z1 - z0:                                       # door in an x-facing wall
        inward = 1.0 if rec.lx > (x0 + x1) / 2 else -1.0
        xa = x1 if inward > 0 else x0
        xs = (xa, xa + inward * APPROACH)
        return min(xs), z0 - 0.5, max(xs), z1 + 0.5
    inward = 1.0 if rec.lz > (z0 + z1) / 2 else -1.0
    za = z1 if inward > 0 else z0
    zs = (za, za + inward * APPROACH)
    return x0 - 0.5, min(zs), x1 + 0.5, max(zs)


def _hits(r, rects, m=0.6):
    return any(r[2] + m > a[0] and r[0] - m < a[2] and r[3] + m > a[1] and r[1] - m < a[3] for a in rects)


def build_bridges(rng, shops, boxes, cols):
    """Pick bridge sites among `shops` and append their boxes / colliders; returns the bridges."""
    P = C.BLOCK_PITCH
    by_block = defaultdict(list)
    for idx, r in enumerate(shops):
        by_block[(int(round(r.lx / P)), int(round(r.lz / P)))].append(idx)
    count = Counter()
    bridges = []
    for idx, A in enumerate(shops):
        if A.district not in ELIGIBLE or A.h < 40.0 or math.hypot(A.lx, A.lz) > 1500.0:
            continue
        bi, bj = int(round(A.lx / P)), int(round(A.lz / P))
        for axis, nb in ((0, (bi + 1, bj)), (1, (bi, bj + 1))):
            for jdx in by_block.get(nb, ()):
                B = shops[jdx]
                if B.district not in ELIGIBLE or B.h < 40.0 or count[idx] >= 2 or count[jdx] >= 2:
                    continue
                if axis == 0:
                    fa, fb = A.lx + A.w / 2, B.lx - B.w / 2
                    lo, hi = max(A.lz - A.d / 2, B.lz - B.d / 2), min(A.lz + A.d / 2, B.lz + B.d / 2)
                else:
                    fa, fb = A.lz + A.d / 2, B.lz - B.d / 2
                    lo, hi = max(A.lx - A.w / 2, B.lx - B.w / 2), min(A.lx + A.w / 2, B.lx + B.w / 2)
                if not (15.0 < fb - fa < 36.0) or hi - lo < 8.0 or rng.random() > 0.25:
                    continue
                br = _site(rng, idx, A, jdx, B, axis, fa, fb, lo, hi, bridges)
                if br is not None:
                    _build(br, fa, fb, boxes, cols)
                    bridges.append(br)
                    count[idx] += 1
                    count[jdx] += 1
    return bridges


def _site(rng, ia, A, ib, B, axis, fa, fb, lo, hi, existing):
    la = buildings.levels(A.h, A.fh)[2:]
    lb = buildings.levels(B.h, B.fh)[1:]
    top = min(A.h, B.h) - 8.0
    cands = [y for y in la if 14.0 <= y <= top and all(abs(y - f) > 5.0 for f in FLY_LAYERS)]
    rng.shuffle(cands)
    for _ in range(3):
        c = rng.uniform(lo + 3.0, hi - 3.0)
        for ya in cands:
            yb = min(lb, key=lambda y: abs(y - ya))
            if abs(yb - ya) > 2.3:
                continue
            if axis == 0:
                da = (fa - 0.5, ya, c - DOOR_HALF, fa + 0.05, ya + DOOR_H, c + DOOR_HALF)
                db = (fb - 0.05, yb, c - DOOR_HALF, fb + 0.5, yb + DOOR_H, c + DOOR_HALF)
                deck = (fa, c - HALF_W, fb, c + HALF_W)
            else:
                da = (c - DOOR_HALF, ya, fa - 0.5, c + DOOR_HALF, ya + DOOR_H, fa + 0.05)
                db = (c - DOOR_HALF, yb, fb - 0.05, c + DOOR_HALF, yb + DOOR_H, fb + 0.5)
                deck = (c - HALF_W, fa, c + HALF_W, fb)
            if _hits(approach_rect(A, da), _core_rects(A)) or _hits(approach_rect(B, db), _core_rects(B)):
                continue
            # keep away from another bridge on the same building at about the same height
            if any((ia in e.doors or ib in e.doors) and abs(e.ya - ya) < 4.0 for e in existing):
                continue
            return Bridge(ia, ib, axis, deck, ya, yb, {ia: da, ib: db})
    return None


def _build(br, fa, fb, boxes, cols):
    L = fb - fa
    ya, yb = br.ya, br.yb
    c = (br.deck[1] + br.deck[3]) / 2 if br.axis == 0 else (br.deck[0] + br.deck[2]) / 2

    def add(u0, v0, u1, v1, y0, y1, kind, hue=0.0, extra=0.0, collide=False):
        if br.axis == 0:
            b = (fa + u0, y0, c + v0, fa + u1, y1, c + v1)
        else:
            b = (c + v0, y0, fa + u0, c + v1, y1, fa + u1)
        boxes.append(box_bounds(*b, kind, hue, extra))
        if collide:
            cols.append(b)

    hue = 0.5
    n = int(round(abs(yb - ya) / 0.2))
    sg = 1.0 if yb > ya else -1.0
    us = L - 0.3 * n - 0.6                                    # steps start
    add(0.0, -1.5, us, 1.5, ya - 0.4, ya, C.K_FLOOR, hue, collide=True)
    for i in range(1, n + 1):
        t = ya + sg * 0.2 * i
        add(us + 0.3 * (i - 1), -1.5, us + 0.3 * i, 1.5, t - 0.4, t, C.K_DOOR, hue, collide=True)
    add(us + 0.3 * n, -1.5, L, 1.5, yb - 0.4, yb, C.K_FLOOR, hue, collide=True)
    lo, hi = min(ya, yb), max(ya, yb)
    for v in (-1.6, 1.5):                                     # railings with a glowing top rail
        add(0.0, v, L, v + 0.1, lo - 0.4, hi + 1.1, C.K_PANEL, hue, collide=True)
        add(0.0, v - 0.02, L, v + 0.12, hi + 1.1, hi + 1.16, C.K_EMISSIVE, 0.5, 2.5)
    add(0.0, -1.6, L, 1.6, hi + 3.0, hi + 3.12, C.K_PANEL, hue, collide=True)          # canopy
    for v in (-1.66, 1.6):
        add(0.0, v, L, v + 0.06, hi + 3.0, hi + 3.12, C.K_EMISSIVE, 0.83, 3.0)
    add(0.0, -0.8, L, 0.8, lo - 0.46, lo - 0.4, C.K_EMISSIVE, 0.5, 2.0)                # underside light
    for u in (0.4, L - 0.4):                                  # portal frames at the facades
        add(u - 0.08, -1.6, u + 0.08, 1.6, hi + 2.8, hi + 3.0, C.K_EMISSIVE, 0.83, 2.5)


def doors_by_building(bridges):
    out = defaultdict(list)
    for br in bridges:
        for idx, door in br.doors.items():
            out[idx].append(door)
    return out
