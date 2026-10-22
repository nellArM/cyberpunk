"""Missions handed out by terminals around the city.

Kinds:
  delivery  carry a package to a place on the map before the time runs out (the route may take
            the elevator, the metro, a taxi, the ferry ... whatever is fastest)
  weather   the same in a storm or thick fog (the weather turns when you take it, and turns back after)
  race      wingsuit ring race: get to the start roof, jump, fly through the rings in order
  parkour   rooftop run: reach the roof checkpoints in order without touching the street

Races and parkour routes are generated once (deterministic) and checked against the static
world: ring-to-ring flight paths are clear, roof checkpoints are standable. A failed race or
run puts you back to "go to the start" instead of ending the mission.
"""
import math
import random
from collections import namedtuple

import numpy as np

import buildings
import config as C
import environment as E
import pickups
import sea
import undercity
from geometry import box_bounds, quad, BOX_FLOATS
from i18n import L, tr

Terminal = namedtuple("Terminal", "id name x y z")             # kiosk position (feet); its screen faces +z
Offer = namedtuple("Offer", "id kind title desc data")
TERM_REACH = 3.2
DEST_REACH, DEST_DY = 3.5, 3.0
RING_R = 7.0                     # visual radius; a ring counts within RING_HIT of its center
RING_HIT = 8.0
CHECK_REACH, CHECK_DY = 3.5, 2.5
DEST_CATS = ("tower", "metro", "taxi", "park", "harbor", "mall", "undercity", "sea", "sky")
GOLD, CYAN, RED = 0.12, 0.5, 0.97

# (id, name, where the kiosk should stand, offers: kind or (kind, extra))
TERMINALS = (
    ("t_plaza", "NEXUS 廣場", (14.0, 0.0, 96.0), ("delivery", "race")),
    ("t_harbor", "港灣步道", (30.0, 0.0, C.SHORE_Z - 5.5), ("delivery", ("weather", E.STORM), "parkour")),
    ("t_park", "霓虹公園", (-394.0, 0.0, 104.0), ("delivery", "parkour")),
    ("t_echo", "回聲廣場", (406.0, 0.0, 184.0), ("delivery", "race")),
    ("t_corp", "企業特區", (640.0, 0.0, -671.0), ("delivery", "race")),
    ("t_rust", "鏽蝕區", (-640.0, 0.0, 609.0), ("delivery", ("weather", E.STORM), "parkour")),
    ("t_b2", "B2 暗巷黑市", (-150.0, undercity.Y, -212.0), ("delivery",)),
    ("t_island", "霓虹島", (14.0, sea.DECK, 1836.0), ("delivery", ("weather", E.FOG))),
)
JUMP_GAP, JUMP_UP = 8.0, 2.5    # parkour: a roof-to-roof jump at most this wide / this much up
HOOK_GAP, HOOK_UP = 26.0, 6.0    # ... or across a road with the grapple (then Q over the edge)
RACE_NAMES = {"t_plaza": "NEXUS 俯衝", "t_echo": "回聲天際線", "t_corp": "企業峽谷"}
PARKOUR_NAMES = {"t_harbor": "港灣屋頂", "t_park": "夜市屋頂", "t_rust": "鏽蝕屋頂"}


def fmt_time(s):
    s = max(0.0, s)
    return f"{int(s // 60)}:{s % 60:04.1f}"


def bearing(pl, x, y, z):
    """Where (x, y, z) is relative to the player: e.g. "右前方 520 m · 上方 230 m"."""
    dx, dz = x - pl.pos[0], z - pl.pos[2]
    d = math.hypot(dx, dz)
    a = (math.atan2(dx, -dz) - pl.yaw + math.pi) % (2.0 * math.pi) - math.pi        # 0 ahead, + to the right
    names = ("前方", "右前方", "右方", "右後方", "後方", "左後方", "左方", "左前方")
    side = names[int(round(a / (math.pi / 4))) % 8]
    dy = y - pl.pos[1]
    vert = tr(" · 上方 {d:.0f} m", d=dy) if dy > 5 else (tr(" · 下方 {d:.0f} m", d=-dy) if dy < -5 else "")
    return tr("{side} {d:.0f} m", side=side, d=d) + vert


def _clear(world, a, b, offsets=((0, 0, 0), (3, 0, 0), (-3, 0, 0), (0, 0, 3), (0, 0, -3), (0, 2.5, 0), (0, -2.5, 0))):
    """Is the flight path a -> b free of static boxes (a few parallel rays)?"""
    d = [b[i] - a[i] for i in range(3)]
    L = math.sqrt(sum(c * c for c in d))
    if L < 1e-6:
        return True
    u = [c / L for c in d]
    for o in offsets:
        p = [a[i] + o[i] for i in range(3)]
        if world.raycast(p, u, L) is not None:
            return False
    return True


# ---------------------------------------------------------------- route generation
def race_route(world, records, near, rng):
    """(start point on a tall roof, [ring centers]) for a wingsuit race near `near`, or None."""
    nx, nz = near
    cands = [k for k, r in enumerate(records) if 140.0 <= r.top <= 280.0 and buildings.has_shaft(r)
             and math.hypot(r.lx - nx, r.lz - nz) < 900.0 and r.lz < C.SHORE_Z - 100.0]
    cands.sort(key=lambda k: math.hypot(records[k].lx - nx, records[k].lz - nz))
    for k in cands[:30]:
        r = records[k]
        start = pickups._first(world, pickups._ring(r.lx, r.top, r.lz, min(r.w, r.d) * 0.25))
        if start is None:
            continue
        n_rings = max(6, min(10, int((r.top - 20.0 - 30.0) / 18.0) + 1))
        for _ in range(16):
            rings = _fly(world, start, n_rings, rng)
            if rings:
                return start, rings
    return None


def _fly(world, start, n, rng):
    """Random walk of ring centers from the roof: 120 m apart, 18 m lower each, turning <= 45 deg."""
    heading = rng.uniform(0.0, 2.0 * math.pi)
    sx, sy, sz = start
    prev = (sx, sy + 1.5, sz)
    rings = []
    y = sy - 22.0
    first = True
    for _ in range(n):
        if first:                                                # off the roof: any direction
            turns = [k * math.pi / 4 for k in range(8)]
            rng.shuffle(turns)
        else:                                                    # prefer straight on, then gentle turns
            tail = [0.35, -0.35, 0.7, -0.7]
            rng.shuffle(tail)
            turns = [0.0] + tail
        ok = False
        for dt in turns:
            h = heading + dt
            step = 80.0 if first else 120.0
            p = (prev[0] + math.sin(h) * step, y, prev[2] - math.cos(h) * step)
            lim = C.CITY_BLOCKS * C.BLOCK_PITCH - 100.0
            if not (-lim < p[0] < lim and -lim < p[2] < C.SHORE_Z + 300.0):
                continue
            if _clear(world, prev, p) and world.raycast(p, (0.0, -1.0, 0.0), 12.0) is None:
                heading, prev, ok = h, p, True
                break
        if not ok:
            return None
        rings.append(prev)
        y -= 18.0
        first = False
    return rings


def parkour_route(world, records, near, rng, n=8):
    """Roof checkpoints [(x, y, z)] hopping between neighbouring buildings near `near`, or None."""
    nx, nz = near
    grid = {}
    for k, r in enumerate(records):
        grid.setdefault((int(r.lx // 80), int(r.lz // 80)), []).append(k)

    def nearby(r):
        cx, cz = int(r.lx // 80), int(r.lz // 80)
        return [k for i in (-1, 0, 1) for j in (-1, 0, 1) for k in grid.get((cx + i, cz + j), ())]

    roofs = {}

    def roof(k):
        """A standable spot on the main roof (the building's height; some have a taller structure on top,
        reaching `top`), not on a tank or a hatch; cached."""
        if k not in roofs:
            r = records[k]
            s = min(r.w, r.d)
            roofs[k] = None
            for ref in dict.fromkeys((r.h, r.top)):
                for x, _, z in pickups._ring(r.lx, ref, r.lz, s * 0.15, 8) + pickups._ring(r.lx, ref, r.lz, s * 0.3, 12)[1:]:
                    y = pickups.floor_near(world, x, z, ref, span=0.5)
                    if y is not None and abs(y - ref) < 0.3 and pickups.standable(world, x, y, z):
                        roofs[k] = (x, y, z)
                        break
                if roofs[k] is not None:
                    break
        return roofs[k]

    def gap(a, b):
        gx = max(0.0, abs(a.lx - b.lx) - (a.w + b.w) / 2)
        gz = max(0.0, abs(a.lz - b.lz) - (a.d + b.d) / 2)
        return math.hypot(gx, gz)

    def inside(r, x, z):
        return abs(x - r.lx) < r.w / 2 and abs(z - r.lz) < r.d / 2

    def straight(ra, pa, rb, pb):
        """Nothing stands in the way along the straight line pa -> pb on either roof."""
        L = math.hypot(pb[0] - pa[0], pb[2] - pa[2])
        for i in range(1, int(L / 0.5)):
            t = i * 0.5 / L
            x, z = pa[0] + (pb[0] - pa[0]) * t, pa[2] + (pb[2] - pa[2]) * t
            for r, y in ((ra, pa[1]), (rb, pb[1])):
                if inside(r, x, z) and world.query(x - 0.35, y + 0.1, z - 0.35, x + 0.35, y + 1.8, z + 0.35):
                    return False
        return True

    starts = [k for k, r in enumerate(records) if 12.0 <= r.h <= 60.0 and math.hypot(r.lx - nx, r.lz - nz) < 450.0]
    starts.sort(key=lambda k: math.hypot(records[k].lx - nx, records[k].lz - nz))
    for k0 in starts[:120]:
        p0 = roof(k0)
        if p0 is None:
            continue
        chain, pts = [k0], [p0]
        heading = None
        while len(chain) < n:
            cur, cy = records[chain[-1]], pts[-1][1]
            opts = []
            for k in nearby(cur):
                b = records[k]
                if k in chain or not 12.0 <= b.h <= 90.0:
                    continue
                g, dist = gap(cur, b), math.hypot(b.lx - cur.lx, b.lz - cur.lz)
                if g > HOOK_GAP or dist < 12.0:
                    continue
                h = math.atan2(b.lx - cur.lx, -(b.lz - cur.lz))
                turn = 0.0 if heading is None else abs((h - heading + math.pi) % (2 * math.pi) - math.pi)
                if turn > 2.0:
                    continue
                opts.append((turn + rng.uniform(0.0, 0.8), k, h, g))
            opts.sort()
            for _, k, h, g in opts:
                p = roof(k)
                if p is None or not 12.0 <= p[1] <= 90.0 or p[1] < cy - 15.0:
                    continue
                # a jump (double jump helps), or a road crossing with the grapple (then Q over the edge)
                if ((g <= JUMP_GAP and p[1] - cy <= JUMP_UP) or (g <= HOOK_GAP and p[1] - cy <= HOOK_UP)) \
                        and straight(cur, pts[-1], b, p):
                    chain.append(k)
                    pts.append(p)
                    heading = h
                    break
            else:
                break
        if len(chain) == n:
            return pts
    return None


# ---------------------------------------------------------------- terminals
def build_terminals(world):
    """(terminals, boxes, holos, colliders): glowing kiosks at standable spots."""
    terms, boxes, holos, cols = [], [], [], []
    for tid, name, (x, y, z), _ in TERMINALS:
        spot = None
        for cx, cy, cz in pickups._ring(x, y, z, 3.0, 12):
            yy = pickups.floor_near(world, cx, cz, cy)
            if (yy is not None and abs(yy - cy) < 1.0 and pickups.standable(world, cx, yy, cz, hw=0.7, h=2.6)
                    and pickups.standable(world, cx, yy, cz + 2.0)):
                spot = (cx, yy, cz)
                break
        if spot is None:
            continue
        x, y, z = spot
        terms.append(Terminal(tid, name, x, y, z))
        col = (x - 0.5, y, z - 0.3, x + 0.5, y + 2.2, z + 0.3)
        cols.append(col)
        boxes.append(box_bounds(*col, C.K_PANEL, GOLD))
        boxes.append(box_bounds(x - 0.42, y + 1.0, z + 0.3, x + 0.42, y + 1.85, z + 0.34, C.K_SIGN, GOLD, 0.0, 400.0))
        boxes.append(box_bounds(x - 0.55, y + 2.2, z - 0.35, x + 0.55, y + 2.3, z + 0.35, C.K_EMISSIVE, GOLD, 4.0))
        boxes.append(box_bounds(x - 0.9, y, z + 1.2, x + 0.9, y + 0.03, z + 2.8, C.K_EMISSIVE, GOLD, 1.2))
        if y > -0.5:                                                   # a beacon above the street
            boxes.append(box_bounds(x - 0.08, y + 2.3, z - 0.08, x + 0.08, y + 45.0, z + 0.08, C.K_EMISSIVE, GOLD, 1.0))
        holos.append(quad((x, y + 3.1, z), (0.8, 0.0, 0.0), (0.0, 0.5, 0.0), C.Q_HOLO, GOLD, 1.6, 700.0 + len(terms)))
    return terms, boxes, holos, cols


# ---------------------------------------------------------------- active missions
class Delivery:
    kind = "delivery"

    def __init__(self, offer, term, dest, weather=None):
        self.id, self.title = offer.id, offer.title
        self.dest = dest
        self.weather = weather
        x, y, z, _ = dest.tp
        d = math.hypot(x - term.x, z - term.z)
        dy = abs(y - term.y)
        extra = 0.0
        if dest.cat == "sea" or term.z > C.SHORE_Z + 100.0:
            extra += 120.0                                       # ferry waits
        if y < -0.5 or term.y < -0.5:
            extra += 60.0                                        # stairs down / up
        limit = 45.0 + d / 14.0 + dy / 25.0 + extra
        if weather is not None:
            limit *= 1.1
        self.limit = self.left = limit
        self.reward = int(round((limit * 3.0 + d * 0.15) * (1.8 if weather is not None else 1.0), -1))
        self.hint = _hint(dest)
        self.elapsed = 0.0

    def update(self, dt, pl, prev):
        self.left -= dt
        self.elapsed += dt
        x, y, z, _ = self.dest.tp
        if math.hypot(pl.pos[0] - x, pl.pos[2] - z) < DEST_REACH and abs(pl.pos[1] - y) < DEST_DY:
            return ("done", tr("送達「{name}」！剩餘 {left}", name=self.dest.name, left=fmt_time(self.left)),
                    self.reward, self.elapsed)
        if self.left <= 0.0:
            return ("fail", tr("超過時限，貨物沒送到"), 0, None)
        return None

    def target(self):
        x, y, z, _ = self.dest.tp
        return x, y, z

    def hud(self, pl):
        x, y, z = self.target()
        col = (255, 90, 90) if self.left < 20.0 else (255, 230, 140)
        lines = [(f"{self.title}  →  {tr(self.dest.name)}", (255, 215, 80)),
                 (tr("剩餘 {left}   報酬 ${reward:,}", left=fmt_time(self.left), reward=self.reward), col),
                 (bearing(pl, x, y, z) + (tr("   提示：{hint}", hint=self.hint) if self.hint else ""), (220, 235, 255))]
        return lines

    def instances(self, eye, t):
        x, y, z = self.target()
        return _beacon(x, y, z, GOLD, indoor=(y < -0.5 or self.dest.cat == "sky"), t=t)

    def map_marks(self):
        x, y, z = self.target()
        return [("point", x, z)]


class RingRace:
    kind = "race"

    def __init__(self, offer, best):
        self.id, self.title = offer.id, offer.title
        self.start, self.rings = offer.data
        self.best = best
        self.reset("")

    def reset(self, why):
        self.state = "approach"                                # approach -> ready -> run
        self.next = 0
        self.elapsed = 0.0
        self.why = why

    def update(self, dt, pl, prev):
        sx, sy, sz = self.start
        if self.state == "approach":
            if math.hypot(pl.pos[0] - sx, pl.pos[2] - sz) < 6.0 and abs(pl.pos[1] - sy) < 2.5:
                self.state, self.why = "ready", ""
                return ("info", tr("到達起點！跳下去，在空中按 Space 展開翼裝，穿過第一個圈"), 0, None)
            return None
        if self.state == "run":
            self.elapsed += dt
        a = (prev[0], prev[1] + 0.9, prev[2])
        b = (pl.pos[0], pl.pos[1] + 0.9, pl.pos[2])
        if _seg_dist(self.rings[self.next], a, b) < RING_HIT:
            self.next += 1
            if self.state == "ready":
                self.state = "run"
            if self.next == len(self.rings):
                return ("done", tr("{title} 完成！時間 {t}", title=self.title, t=fmt_time(self.elapsed)), 0,
                        self.elapsed)
            return ("ring", "", 0, None)
        if self.state == "run" and pl.grounded:
            self.reset("著陸了 — 回到起點屋頂再試一次")
            return ("info", tr("著陸了！回到起點屋頂再試一次（J 放棄任務）"), 0, None)
        if self.state == "ready" and pl.grounded and pl.pos[1] < sy - 3.0:
            self.reset("")
        return None

    def target(self):
        return self.start if self.state == "approach" else self.rings[self.next]

    def hud(self, pl):
        x, y, z = self.target()
        best = tr("   最佳 {t}", t=fmt_time(self.best)) if self.best else ""
        if self.state == "approach":
            l2 = tr(self.why or "到起點屋頂（搭樓內電梯、爬樓梯或用鉤索）")
            return [(tr("{title}（翼裝穿圈賽）", title=self.title), (120, 230, 255)), (l2 + best, (255, 230, 140)),
                    (bearing(pl, x, y, z), (220, 235, 255))]
        if self.state == "ready":
            return [(tr("{title}（翼裝穿圈賽）", title=self.title), (120, 230, 255)),
                    (tr("跳下屋頂，Space 展開翼裝 — 穿過第一個圈開始計時") + best, (255, 230, 140)),
                    (bearing(pl, x, y, z), (220, 235, 255))]
        return [(tr("{title}  圈 {n}/{total}", title=self.title, n=self.next + 1, total=len(self.rings)),
                 (120, 230, 255)),
                (tr("時間 {t}", t=fmt_time(self.elapsed)) + best, (255, 230, 140)),
                (bearing(pl, x, y, z) + tr("   Ctrl 衝刺加速"), (220, 235, 255))]

    def instances(self, eye, t):
        rows = []
        if self.state == "approach":
            rows += _beacon(*self.start, CYAN, t=t)
        pts = [self.start] + list(self.rings)
        for i in range(self.next, len(self.rings)):
            c, p = pts[i + 1], pts[i]
            nxt = i == self.next and self.state != "approach"
            rows += _ring(c, (c[0] - p[0], c[1] - p[1], c[2] - p[2]), GOLD if nxt else CYAN, 4.0 if nxt else 1.2)
        return rows

    def map_marks(self):
        return [("route", [(p[0], p[2]) for p in [self.start] + list(self.rings)]),
                ("point",) + (self.target()[0], self.target()[2])]


class Parkour:
    kind = "parkour"

    def __init__(self, offer, best):
        self.id, self.title = offer.id, offer.title
        self.points = offer.data
        self.best = best
        self.reset("")

    def reset(self, why):
        self.state, self.next, self.elapsed, self.why = "approach", 0, 0.0, why

    def update(self, dt, pl, prev):
        if self.state == "run":
            self.elapsed += dt
            if pl.grounded and -0.5 < pl.pos[1] < 0.5:
                self.reset("掉到街上了 — 回到第一個屋頂再試一次")
                return ("info", tr("掉到街上了！回到第一個屋頂再試一次（J 放棄任務）"), 0, None)
        x, y, z = self.points[self.next]
        if math.hypot(pl.pos[0] - x, pl.pos[2] - z) < CHECK_REACH and abs(pl.pos[1] - y) < CHECK_DY:
            self.next += 1
            if self.state == "approach":
                self.state, self.why = "run", ""
                return ("info", tr("開跑！依序跳到每個發光檢查點，別碰到街面"), 0, None)
            if self.next == len(self.points):
                return ("done", tr("{title} 完成！時間 {t}", title=self.title, t=fmt_time(self.elapsed)), 0,
                        self.elapsed)
            return ("ring", "", 0, None)
        return None

    def target(self):
        return self.points[self.next]

    def hud(self, pl):
        x, y, z = self.target()
        best = tr("   最佳 {t}", t=fmt_time(self.best)) if self.best else ""
        if self.state == "approach":
            return [(tr("{title}（屋頂跑酷）", title=self.title), (255, 140, 220)),
                    (tr(self.why or "到第一個屋頂檢查點（樓內樓梯直通屋頂）") + best, (255, 230, 140)),
                    (bearing(pl, x, y, z), (220, 235, 255))]
        return [(tr("{title}  檢查點 {n}/{total}", title=self.title, n=self.next + 1, total=len(self.points)),
                 (255, 140, 220)),
                (tr("時間 {t}", t=fmt_time(self.elapsed)) + best, (255, 230, 140)),
                (bearing(pl, x, y, z) + tr("   Q 二段跳 · Ctrl 衝刺 · F 鉤索"), (220, 235, 255))]

    def instances(self, eye, t):
        rows = []
        for i in range(self.next, len(self.points)):
            x, y, z = self.points[i]
            if i == self.next:
                rows += _beacon(x, y, z, 0.88, t=t, height=60.0)
            else:
                rows.append(box_bounds(x - 0.15, y, z - 0.15, x + 0.15, y + 6.0, z + 0.15, C.K_EMISSIVE, 0.88, 1.2))
        return rows

    def map_marks(self):
        return [("route", [(p[0], p[2]) for p in self.points]), ("point", self.target()[0], self.target()[2])]


def _hint(dest):
    x, y, z, _ = dest.tp
    if dest.cat == "sky":
        return "搭塔內電梯（數字鍵輸入樓層）"
    if dest.cat == "sea":
        return "港灣主碼頭搭渡輪"
    if dest.cat == "undercity":
        return "地心線月台旁的通道往下到 B2"
    if dest.cat == "mall":
        return "霓虹市集站旁的地下街"
    if dest.cat == "metro":
        return "地鐵站月台"
    if y > 5.0:
        return "在屋頂：電梯、鉤索或空中計程車"
    return ""


def _seg_dist(c, a, b):
    """Distance from point c to segment a-b."""
    ab = [b[i] - a[i] for i in range(3)]
    L2 = sum(v * v for v in ab)
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, sum((c[i] - a[i]) * ab[i] for i in range(3)) / L2))
    return math.sqrt(sum((c[i] - (a[i] + ab[i] * t)) ** 2 for i in range(3)))


def _beacon(x, y, z, hue, indoor=False, t=0.0, height=300.0):
    h = 3.2 if indoor else height
    pulse = 2.0 + 1.0 * math.sin(t * 4.0)
    rows = [box_bounds(x - 0.25, y, z - 0.25, x + 0.25, y + h, z + 0.25, C.K_EMISSIVE, hue, pulse)]
    for x0, z0, x1, z1 in ((-2.0, -2.0, 2.0, -1.85), (-2.0, 1.85, 2.0, 2.0), (-2.0, -2.0, -1.85, 2.0), (1.85, -2.0, 2.0, 2.0)):
        rows.append(box_bounds(x + x0, y + 0.02, z + z0, x + x1, y + 0.06, z + z1, C.K_EMISSIVE, hue, 3.0))
    return rows


def _ring(c, n, hue, glow, beads=16):
    """A ring of glowing beads around c, facing direction n."""
    L = math.sqrt(sum(v * v for v in n)) or 1.0
    n = [v / L for v in n]
    up = (0.0, 1.0, 0.0) if abs(n[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = [up[1] * n[2] - up[2] * n[1], up[2] * n[0] - up[0] * n[2], up[0] * n[1] - up[1] * n[0]]
    ul = math.sqrt(sum(v * v for v in u)) or 1.0
    u = [v / ul for v in u]
    w = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    rows = []
    s = 0.45
    for k in range(beads):
        a = 2.0 * math.pi * k / beads
        p = [c[i] + RING_R * (math.cos(a) * u[i] + math.sin(a) * w[i]) for i in range(3)]
        rows.append(box_bounds(p[0] - s, p[1] - s, p[2] - s, p[0] + s, p[1] + s, p[2] + s, C.K_EMISSIVE, hue, glow))
    return rows


class Missions:
    def __init__(self, world, records, seed=2077):
        self.terminals, self.boxes, self.holos, self.colliders = build_terminals(world)
        world.add(self.colliders)
        self.dests = []
        self.rng = random.Random(seed)
        self.offers = {}
        for n, (tid, name, _, kinds) in enumerate(TERMINALS):
            gen = np.random.default_rng(seed * 100 + n)            # each terminal's routes stand on their own
            term = next((t for t in self.terminals if t.id == tid), None)
            if term is None:
                continue
            offers = []
            for kind in kinds:
                kind, extra = kind if isinstance(kind, tuple) else (kind, None)
                if kind == "delivery":
                    offers.append(Offer(f"{tid}_delivery", "delivery", L("送貨"), L("把包裹送到地圖上的指定地點（限時）"),
                                        None))
                elif kind == "weather":
                    label = L("暴雨急件") if extra == E.STORM else L("濃霧急件")
                    offers.append(Offer(f"{tid}_weather", "weather", label,
                                        L("天氣立刻轉為{kind}，限時送件，報酬 ×1.8", kind=E.KINDS[extra]), extra))
                elif kind == "race":
                    r = race_route(world, records, (term.x, term.z), gen)
                    if r is not None:
                        offers.append(Offer(f"{tid}_race", "race", L("翼裝穿圈賽「{name}」", name=RACE_NAMES[tid]),
                                            L("從 {h:.0f} m 屋頂起跳，穿過 {n} 個圈", h=r[0][1], n=len(r[1])), r))
                elif kind == "parkour":
                    r = parkour_route(world, records, (term.x, term.z), gen)
                    if r is not None:
                        offers.append(Offer(f"{tid}_parkour", "parkour", L("屋頂跑酷「{name}」", name=PARKOUR_NAMES[tid]),
                                            L("{n} 個屋頂檢查點，碰到街面就重來", n=len(r)), r))
            self.offers[tid] = offers
        self.active = None
        self.term = None                      # where the active mission was taken
        self.weather_backup = None            # (kind, auto) to restore after a weather mission

    def set_destinations(self, pois):
        """Delivery targets: the map's places (their fast-travel spots are known to be standable)."""
        self.dests = [p for p in pois if p.cat in DEST_CATS]

    # ---------------------------------------------------------------- terminals
    def terminal_near(self, pos):
        for t in self.terminals:
            if math.hypot(pos[0] - t.x, pos[2] - (t.z + 1.2)) < TERM_REACH and abs(pos[1] - t.y) < 2.0:
                return t
        return None

    def menu_lines(self, term, prog):
        lines = [tr("任務終端・{name}        信用點 ${credits:,}", name=term.name, credits=prog.credits)]
        for i, o in enumerate(self.offers.get(term.id, ())):
            best = prog.best(o.id)
            tag = tr("   最佳 {t}", t=fmt_time(best)) if best else ""
            if o.kind in ("race", "parkour"):
                pay = f"${self.race_reward(o, prog):,}"
            else:
                pay = tr("報酬依距離")
            lines.append(tr("{i}   {title} — {desc}（{pay}）", i=i + 1, title=o.title, desc=o.desc, pay=pay) + tag)
        lines.append(tr("數字鍵接任務 · E / Esc 離開") if self.active is None else tr("已有進行中的任務（J 放棄）"))
        return lines

    @staticmethod
    def race_reward(offer, prog):
        base = 450 if offer.kind == "race" else 350
        return base + (400 if prog.done(offer.id) == 0 else 0)

    def start(self, term, index, pl, env, prog):
        """Take offer `index` at terminal `term`; returns a message."""
        if self.active is not None:
            return tr("已有進行中的任務（J 放棄）")
        offers = self.offers.get(term.id, ())
        if not 0 <= index < len(offers):
            return ""
        o = offers[index]
        if o.kind in ("delivery", "weather"):
            far = [p for p in self.dests
                   if 400.0 < math.hypot(p.tp[0] - term.x, p.tp[2] - term.z) < 2500.0]
            if not far:
                return tr("目前沒有可送的地點")
            dest = self.rng.choice(far)
            weather = o.data if o.kind == "weather" else None
            self.active = Delivery(o, term, dest, weather)
            if weather is not None:
                self.weather_backup = (env.kind, env.auto)
                env.set_weather(weather)
            msg = tr("接下「{title}」：送到 {dest}，限時 {t}", title=o.title, dest=dest.name,
                     t=fmt_time(self.active.limit))
        elif o.kind == "race":
            self.active = RingRace(o, prog.best(o.id))
            msg = tr("接下{title}：先到起點屋頂（{h:.0f} m）", title=o.title, h=o.data[0][1])
        else:
            self.active = Parkour(o, prog.best(o.id))
            msg = tr("接下{title}：先到第一個屋頂檢查點", title=o.title)
        self.term = term
        return msg

    def _finish(self, env):
        if self.weather_backup is not None:
            env.set_weather(self.weather_backup[0], self.weather_backup[1])
            self.weather_backup = None
        self.active = None
        self.term = None

    def abort(self, env):
        if self.active is None:
            return ""
        title = self.active.title
        self._finish(env)
        return tr("已放棄任務「{title}」", title=title)

    def update(self, dt, pl, prev, env, prog):
        """Advance the active mission; returns (kind, text, reward) for the game to show, or None."""
        m = self.active
        if m is None:
            return None
        ev = m.update(dt, pl, prev)
        if ev is None:
            return None
        kind, text, reward, seconds = ev
        if kind == "done":
            if m.kind in ("race", "parkour"):
                reward = self.race_reward(next(o for os_ in self.offers.values() for o in os_ if o.id == m.id), prog)
            new_best = prog.record(m.id, seconds if m.kind in ("race", "parkour") else None)
            if new_best and prog.done(m.id) > 1:
                reward += 100
                text += tr("（新紀錄！+$100）")
            prog.earn(reward)
            self._finish(env)
            prog.save()
            return "done", text, reward
        if kind == "fail":
            self._finish(env)
            return "fail", text, 0
        return kind, text, 0

    # ---------------------------------------------------------------- drawing
    def hud(self, pl):
        return self.active.hud(pl) if self.active is not None else None

    def instances(self, eye, t):
        if self.active is None:
            return np.zeros((0, BOX_FLOATS), "f4")
        return np.array(self.active.instances(eye, t), "f4").reshape(-1, BOX_FLOATS)

    def map_marks(self):
        return self.active.map_marks() if self.active is not None else []
