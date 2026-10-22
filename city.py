"""Procedural cyberpunk city: buildings, neon signs, holograms and flying traffic."""
import math

import numpy as np

import buildings
import config as C
import districts as D
import rooftops
import skybridges
from geometry import box, quad, BOX_FLOATS, QUAD_FLOATS
from shops import ShopRecord, shell_colliders, shop_name

# per district: building hues, (first, second) setback tier chances, min height for a first tier,
# antenna chance, advert hologram chance, glyph signs per building (lo, hi), shop type weights
_STYLE = {
    D.DOWNTOWN: (C.NEON_HUES, (0.55, 0.4), 60.0, 0.4, 0.2, (0, 3), None),
    D.CORPORATE: ((0.55, 0.6, 0.5, 0.83), (0.8, 0.6), 60.0, 0.3, 0.35, (0, 2), (0.2, 0.1, 0.15, 0.1, 0.25, 0.2)),
    D.MARKET: (C.NEON_HUES, (0.0, 0.0), 1e9, 0.1, 0.3, (2, 6), (0.1, 0.3, 0.05, 0.3, 0.05, 0.2)),
    D.RESIDENTIAL: ((0.08, 0.12, 0.97, 0.83), (0.2, 0.0), 60.0, 0.2, 0.05, (0, 2), None),
    D.RUST: ((0.06, 0.08, 0.1, 0.5), (0.3, 0.0), 30.0, 0.8, 0.03, (0, 3), None),
    D.HARBOR: ((0.08, 0.55, 0.12, 0.5), (0.0, 0.0), 1e9, 0.3, 0.05, (0, 2), (0.15, 0.3, 0.05, 0.3, 0.05, 0.15)),
}


class CityData:
    def __init__(self, boxes, colliders, holos, shops, helipads, bridges):
        self.boxes = np.array(boxes, dtype="f4").reshape(-1, BOX_FLOATS)
        self.colliders = colliders
        self.holos = np.array(holos, dtype="f4").reshape(-1, QUAD_FLOATS)
        self.shops = shops
        self.helipads = helipads              # (pad center (x, y, z), shop index) of rooftop helipads
        self.bridges = bridges                # skybridges.Bridge


def _door_face(rng, lx, lz, cx, cz):
    """Open the shop toward the street: the face pointing away from the block center."""
    dx, dz = lx - cx, lz - cz
    xf = C.FACE_PX if dx > 0 else C.FACE_NX
    zf = C.FACE_PZ if dz > 0 else C.FACE_NZ
    if abs(dx) > abs(dz) + 1.0:
        return xf
    if abs(dz) > abs(dx) + 1.0:
        return zf
    if abs(dx) < 1.0:                       # whole-block building: every face is on a street
        return int(rng.integers(1, 5))
    return xf if rng.random() < 0.5 else zf


def _lots(rng, cx, cz, hb):
    """Split a block (half size hb) into 1, 2 or 4 lots: (center x, center z, width, depth)."""
    r = rng.random()
    if r < 0.3:
        return [(cx, cz, 2 * hb, 2 * hb)]
    gap = 2.0
    w = hb - gap / 2
    off = w / 2 + gap / 2
    if r < 0.65:
        if rng.random() < 0.5:
            return [(cx - off, cz, w, 2 * hb), (cx + off, cz, w, 2 * hb)]
        return [(cx, cz - off, 2 * hb, w), (cx, cz + off, 2 * hb, w)]
    return [(cx + sx * off, cz + sz * off, w, w) for sx in (-1, 1) for sz in (-1, 1)]


def _face_point(face, lx, lz, w, d, offset, along):
    """Point on a building face (0:+x 1:-x 2:+z 3:-z), pushed out by offset; returns pos, tangent."""
    if face == 0:
        return (lx + w / 2 + offset, lz + along), (0.0, 0.0, 1.0), d
    if face == 1:
        return (lx - w / 2 - offset, lz + along), (0.0, 0.0, 1.0), d
    if face == 2:
        return (lx + along, lz + d / 2 + offset), (1.0, 0.0, 0.0), w
    return (lx + along, lz - d / 2 - offset), (1.0, 0.0, 0.0), w


def _height(rng, dk, dist):
    hmax = 25.0 + 520.0 * math.exp(-dist / 650.0)
    if dk == D.CORPORATE:
        return 70.0 + (hmax * 1.4 - 10.0) * rng.random() ** 0.9
    if dk == D.MARKET:
        return 8.0 + 24.0 * rng.random() ** 1.3
    if dk == D.RESIDENTIAL:
        return 40.0 + 85.0 * rng.random() ** 1.2
    if dk == D.RUST:
        return 12.0 + 70.0 * rng.random() ** 1.8
    if dk == D.HARBOR:                                   # warehouses
        return 9.0 + 12.0 * rng.random()
    h = 10.0 + (hmax - 10.0) * rng.random() ** 1.6
    if dist < 1500 and rng.random() < 0.03:
        h *= 1.8
    return h


def _free_spot(rng, foot, size, avoid, tries=8):
    """Random (x, z) center for a size x size box on a roof foot (x0, z0, x1, z1), clear of `avoid` rects."""
    x0, z0, x1, z1 = foot
    for _ in range(tries):
        x, z = rng.uniform(x0 + size, x1 - size), rng.uniform(z0 + size, z1 - size)
        if all(x + size / 2 + 0.5 < a0 or x - size / 2 - 0.5 > a1 or z + size / 2 + 0.5 < b0 or z - size / 2 - 0.5 > b1
               for a0, b0, a1, b1 in avoid):
            return x, z
    return None


def _building(rng, lx, lz, lw, ld, cx, cz, dist, dk, boxes, cols, holos, shops, helipads):
    hues, tier_p, tier_min, antenna_p, holo_p, n_signs, kind_w = _STYLE[dk]
    inset = rng.uniform(0.5, 3.5)
    w, d = max(lw - 2 * inset, 6.0), max(ld - 2 * inset, 6.0)
    h = _height(rng, dk, dist)
    hue = float(rng.choice(hues))
    seed = float(rng.uniform(0, 1000))

    # The base box doubles as the ground-floor shop: the shader cuts the door and shades
    # faces seen from inside as the interior; its bottom face (raised 3 cm) is the shop floor.
    # Above the shop are the building's walk-in upper floors (buildings.py / tower_interior.py).
    face = _door_face(rng, lx, lz, cx, cz)
    if kind_w is None:
        kind = int(rng.integers(len(C.SHOP_TYPES)))
    else:
        kind = int(rng.choice(len(C.SHOP_TYPES), p=kind_w))
    boxes.append(box(lx, 0.03, lz, w, h - 0.03, d, C.K_CITY, hue, face + 10 * kind + 100 * dk, seed))
    upper_col = len(cols)                               # shell_colliders lists the solid upper floors first
    cols.extend(shell_colliders(lx, lz, w, d, h, face))
    rec = ShopRecord(lx, lz, w, d, h, face, kind, seed, shop_name(kind, seed), dk, h,
                     buildings.floor_height(seed), upper_col)
    hatch = buildings.hatch_world(buildings.Frame(rec))
    foot = (lx - w / 2, lz - d / 2, lx + w / 2, lz + d / 2)

    # Stepped setback tiers, kept clear of the roof hatch above the stair core.
    top, cw, cd, tx, tz = h, w, d, lx, lz
    tiers = 0
    while tiers < 2 and top > (tier_min if tiers == 0 else 160) and rng.random() < tier_p[tiers]:
        cw *= rng.uniform(0.55, 0.8)
        cd *= rng.uniform(0.55, 0.8)
        th = top * rng.uniform(0.15, 0.4)
        if tiers == 0:
            spot = buildings.place_tier(foot, hatch, cw, cd)
            if spot is None:
                break
            tx, tz, cw, cd = spot
        boxes.append(box(tx, top, tz, cw, th, cd, C.K_CITY, hue, 0.0, float(rng.uniform(0, 1000))))
        cols.append((tx - cw / 2, top, tz - cd / 2, tx + cw / 2, top + th, tz + cd / 2))
        top += th
        tiers += 1
    tier_rect = (tx - cw / 2, tz - cd / 2, tx + cw / 2, tz + cd / 2) if tiers else None
    peak = top

    # rooftop bar / pool / helipad on a free base roof
    facility = None
    if tiers == 0 and dist < 1800 and w >= 16 and d >= 16 and h - C.SHOP_H >= buildings.MIN_UPPER:
        kind_r = rooftops.pick_kind(rng, dk, h)
        if kind_r is not None:
            facility = rooftops.add_rooftop(rng, kind_r, foot, h, hatch, boxes, cols, holos, seed)
    if facility is not None:
        peak = h + facility[1]
        if facility[2] is not None:
            helipads.append((facility[2], len(shops)))
    elif top > (20 if dk == D.RUST else 100) and rng.random() < antenna_p:
        ah = rng.uniform(8, 45)
        boxes.append(box(tx, top, tz, 0.8, ah, 0.8, C.K_ANTENNA, 0.0, 0.0, seed))
        peak = top + ah

    # Rust district: water tanks and tin shacks on the (walkable) base roof.
    if dk == D.RUST and h > 14:
        avoid = [hatch] + ([tier_rect] if tier_rect else [])
        for _ in range(int(rng.integers(1, 4))):
            s = rng.uniform(2.0, 3.5)
            spot = _free_spot(rng, foot, s, avoid)
            if spot is None:
                continue
            x, z = spot
            sh = rng.uniform(1.8, 3.2)
            boxes.append(box(x, h, z, s, sh, s, C.K_PANEL, 0.08, 0.0, seed))
            cols.append((x - s / 2, h, z - s / 2, x + s / 2, h + sh, z + s / 2))
            if rng.random() < 0.5:
                boxes.append(box(x, h + sh, z, s * 0.9, 0.12, s * 0.9, C.K_EMISSIVE, 0.08, 1.2))
            avoid.append((x - s / 2, z - s / 2, x + s / 2, z + s / 2))
            peak = max(peak, h + sh)
    shops.append(rec._replace(top=peak))

    # Vertical neon glyph signs.
    lo_h = 10.0 if dk == D.MARKET else 18.0
    if h > lo_h:
        for _ in range(int(rng.integers(*n_signs))):
            sf = int(rng.integers(4))
            (px, pz), tan, fw = _face_point(sf, lx, lz, w, d, 0.45, 0.0)
            sw = rng.uniform(2.5, max(2.6, min(6.0, fw * 0.5)))
            smin = 3.0 if dk == D.MARKET else 8.0
            sh = rng.uniform(smin, max(smin + 0.1, min(32.0, h - 6.0 if dk == D.MARKET else h - 8.0)))
            sy = rng.uniform(5.5, max(5.6, h - sh - 2.0))          # above the shop front
            (px, pz), tan, _ = _face_point(sf, lx, lz, w, d, 0.45, rng.uniform(-(fw - sw) / 2, (fw - sw) / 2))
            sx, sz = (0.5, sw) if sf < 2 else (sw, 0.5)
            boxes.append(box(px, sy, pz, sx, sh, sz, C.K_SIGN, float(rng.choice(C.NEON_HUES)), 0.0,
                             float(rng.uniform(0, 1000))))

    # Shop front: glyph sign above the door and a neon strip under the first-floor line.
    fi = face - 1                                   # _face_point uses 0:+x 1:-x 2:+z 3:-z
    shop_hue = C.SHOP_TYPES[kind][1]
    (px, pz), tan, fw = _face_point(fi, lx, lz, w, d, 0.25, 0.0)
    sw = min(7.0, fw - 1.0)
    sx, sz = (0.4, sw) if fi < 2 else (sw, 0.4)
    boxes.append(box(px, 3.5, pz, sx, 1.1, sz, C.K_SIGN, shop_hue, 0.0, seed + 0.5))
    (px, pz), tan, fw = _face_point(fi, lx, lz, w, d, 0.1, 0.0)
    sx, sz = (0.2, fw * 0.95) if fi < 2 else (fw * 0.95, 0.2)
    boxes.append(box(px, 4.75, pz, sx, 0.2, sz, C.K_EMISSIVE, shop_hue, 2.5))

    # Holographic advert floating off a face.
    if h > (25 if dk == D.MARKET else 50) and dist < 1200 and rng.random() < holo_p:
        hf = int(rng.integers(4))
        _, _, fw = _face_point(hf, lx, lz, w, d, 0.0, 0.0)
        hw = rng.uniform(5.0, max(5.1, min(14.0, fw * 0.45)))
        hh = rng.uniform(8.0, max(8.1, min(25.0, h * 0.3)))
        lo, hi = hh + 10.0, h - hh - 5.0
        if hi > lo:
            (px, pz), tan, _ = _face_point(hf, lx, lz, w, d, 2.5, 0.0)
            cy = rng.uniform(lo, hi)
            right = (tan[0] * hw, 0.0, tan[2] * hw)
            holos.append(quad((px, cy, pz), right, (0.0, hh, 0.0), C.Q_HOLO,
                              float(rng.choice(C.NEON_HUES)), float(rng.uniform(0.7, 1.2)),
                              float(rng.uniform(0, 1000))))


def build_city(rng, skip_blocks=()):
    """skip_blocks: (i, j) block indices left empty (metro station plazas, towers, parks)."""
    boxes, cols, holos, shops, helipads = [], [], [], [], []
    R, P = C.CITY_BLOCKS, C.BLOCK_PITCH
    hb = P / 2 - C.ROAD_HALF - 2.5          # leave a 2.5 m sidewalk
    skip = set(skip_blocks) | D.water_blocks() | D.container_blocks()
    for i in range(-R, R + 1):
        for j in range(-R, R + 1):
            if (abs(i) <= 1 and abs(j) <= 1) or (i, j) in skip:
                continue                    # tower plaza, metro station plazas, parks, the sea, container yards
            cx, cz = i * P, j * P
            dist = math.hypot(cx, cz)
            dk = D.district(i, j)
            if dk == D.MARKET:              # always four small lots
                rng.random()
                w = hb - 1.0
                off = w / 2 + 1.0
                lots = [(cx + sx * off, cz + sz * off, w, w) for sx in (-1, 1) for sz in (-1, 1)]
            elif (dk == D.CORPORATE and rng.random() < 0.6) or (dk == D.HARBOR and rng.random() < 0.5):
                lots = [(cx, cz, 2 * hb, 2 * hb)]                  # whole-block headquarters / warehouse
            else:
                lots = _lots(rng, cx, cz, hb)
            for lx, lz, lw, ld in lots:
                _building(rng, lx, lz, lw, ld, cx, cz, dist, dk, boxes, cols, holos, shops, helipads)
    bridges = skybridges.build_bridges(np.random.default_rng(rng.integers(1 << 30)), shops, boxes, cols)
    return CityData(boxes, cols, holos, shops, helipads, bridges)


class Traffic:
    """Flying cars streaming along the road grid at several altitude layers."""

    def __init__(self, rng, count=C.TRAFFIC_COUNT):
        self.count = count
        lanes = [k for k in range(-C.CITY_BLOCKS - 1, C.CITY_BLOCKS + 1) if k not in (-1, 0)]
        self.extent = C.CITY_BLOCKS * C.BLOCK_PITCH + 60.0
        self.axis = rng.integers(0, 2, count)
        dirs = rng.choice([-1.0, 1.0], count)
        self.lane = 40.0 + C.BLOCK_PITCH * rng.choice(lanes, count) + dirs * rng.uniform(2.0, 5.5, count)
        self.speed = dirs * rng.uniform(25.0, 70.0, count)
        self.t = rng.uniform(-self.extent, self.extent, count)
        alt = rng.choice([28.0, 45.0, 70.0, 100.0, 140.0, 190.0, 260.0], count) + rng.uniform(-3, 3, count)
        self.data = np.zeros((count, BOX_FLOATS), dtype="f4")
        along_x = self.axis == 0
        self.data[:, 1] = alt
        self.data[:, 3] = np.where(along_x, 4.5, 2.0)
        self.data[:, 4] = 1.2
        self.data[:, 5] = np.where(along_x, 2.0, 4.5)
        self.data[:, 6] = rng.uniform(0, 1000, count)
        self.data[:, 7] = C.K_VEHICLE
        self.data[:, 8] = rng.choice(C.NEON_HUES, count)
        self.data[:, 9] = dirs
        self.update(0.0)

    def update(self, dt):
        e = self.extent
        self.t = (self.t + self.speed * dt + e) % (2 * e) - e
        along_x = self.axis == 0
        self.data[:, 0] = np.where(along_x, self.t, self.lane)
        self.data[:, 2] = np.where(along_x, self.lane, self.t)
