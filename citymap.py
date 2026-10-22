"""City map (M) with fast travel to places the player has already been to.

Places (POI) are the megatower lobbies, metro stations, air-taxi stands, parks and plazas,
harbor spots and the underground mall. Walking within VISIT_RADIUS of one unlocks fast travel
to it; unlocked ids are kept in savegame.json next to this file.

The base map (districts, buildings, sea, piers, metro lines, skybridges) is drawn once into
a few pygame surfaces (a small mipmap chain); the view, icons, the player and the taxis are
drawn on top every frame while the map is open.
"""
import colorsys
import math
import os
from collections import namedtuple

import pygame

import config as C
import districts as D
import floors
import harbor
import mall
import savegame
import sea
import undercity
from i18n import L, tr

POI = namedtuple("POI", "id name cat x z tp")       # tp: (x, y, z, yaw) where fast travel puts the player
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "savegame.json")
VISIT_RADIUS, VISIT_DY = 25.0, 6.0
START = "plaza"
EXTENT = 2960.0                                       # the map covers +-EXTENT metres
LEVELS = (1024, 2048, 4096)                           # base map resolutions (px)
ZOOMS = (1.0, 2.0, 4.0, 8.0)

DISTRICT_RGB = {D.DOWNTOWN: (46, 44, 66), D.CORPORATE: (34, 50, 78), D.MARKET: (70, 34, 68),
                D.RESIDENTIAL: (72, 54, 34), D.RUST: (64, 40, 28), D.HARBOR: (38, 52, 58)}
CAT_STYLE = {                                         # (label, color, shape)
    "plaza": ("起點廣場", (255, 255, 255), "circle"),
    "tower": ("摩天樓", (255, 70, 210), "square"),
    "metro": ("地鐵站", None, "circle"),
    "taxi": ("計程車招呼站", (255, 210, 60), "diamond"),
    "park": ("公園／廣場", (90, 230, 120), "circle"),
    "harbor": ("港灣", (80, 220, 255), "triangle"),
    "mall": ("地下商場", (190, 120, 255), "square"),
    "undercity": ("B2 地下城", (255, 90, 90), "square"),
    "sea": ("海上", (255, 150, 80), "triangle"),
    "sky": ("大樓特色樓層", (140, 255, 220), "diamond"),
    "mission": ("任務終端", (255, 200, 60), "square"),
}
# megatower feature floors listed on the map: (tower index, floor)
FEATURE_POIS = ((0, 400), (0, 900), (1, 500), (2, 600), (2, 800))


def _hue_rgb(h, s=0.75, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def build_pois(towers, stations, lines, stands, terminals=()):
    pois = [POI(START, "NEXUS 廣場（起點）", "plaza", *C.SPAWN[::2], (*C.SPAWN, 0.0))]
    for t in terminals:                               # mission kiosks: stand in front of the screen (+z)
        pois.append(POI(f"term_{t.id}", L("任務終端・{name}", name=t.name), "mission", t.x, t.z,
                        (t.x, t.y, t.z + 2.0, 0.0)))
    for t in towers:
        pois.append(POI(f"tower{t.index}", L("{name} 大廳入口", name=t.name), "tower", t.cx, t.cz,
                        (t.cx, 0.0, t.cz + t.half + 3.0, 0.0)))
    for st in stations:
        x0, z0, x1, z1 = st.platform
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        pois.append(POI(f"st{st.line}_{st.index}", L("{line}・{st}站", line=lines[st.line]['name'], st=st.name),
                        "metro", cx, cz, (cx, st.yf, cz, 0.0)))
    for s in stands:
        pois.append(POI(f"taxi{s.index}", L("計程車・{name}", name=s.name), "taxi", s.x, s.z,
                        (s.x + 1.5, s.y, s.z + 4.5, 0.0)))
    for name, i, j, kind in C.PARKS:
        cx, cz = i * C.BLOCK_PITCH, j * C.BLOCK_PITCH
        # on the south path spoke, outside the strollers' walking ring
        pois.append(POI(f"park{i}_{j}", name, "park", cx, cz, (cx, 0.0, cz + 24.0, math.pi)))
    S = C.SHORE_Z
    pois += [POI("harbor_walk", "港灣步道", "harbor", 0.0, S - 5.5, (0.0, 0.0, S - 5.5, math.pi)),
             POI("harbor_light", "燈塔碼頭", "harbor", harbor.LIGHTHOUSE[0], harbor.PIER_END - 6.0,
                 (harbor.LIGHTHOUSE[0], harbor.DECK_Y, harbor.PIER_END - 6.0, math.pi)),
             POI("harbor_yard", "貨櫃碼頭", "harbor", -700.0, S - 5.0, (-700.0, 0.0, S - 5.0, math.pi)),
             POI("mall_hall", "NEXUS 地下商場", "mall", 20.0, 12.0, (20.0, mall.Y, 12.0, math.pi)),
             POI("mall_street", "地下街", "mall", 9.5, -150.0, (9.5, mall.Y, -150.0, math.pi))]
    D2 = sea.DECK
    pois += [POI("ferry_pier", "渡輪碼頭（往霓虹島）", "sea", 0.0, harbor.PIER_END - 8.0,
                 (0.0, D2, harbor.PIER_END - 8.0, math.pi)),
             POI("island", "霓虹島", "sea", 0.0, 1950.0, (0.0, D2, 1830.0, math.pi)),
             POI("funpark", "海上遊樂園", "sea", 0.0, 2520.0, (0.0, D2, 2412.0, math.pi))]
    Y = undercity.Y
    pois += [POI("uc_market", L("地下城・{name}", name="暗巷黑市"), "undercity", -120.0, -214.0, (-120.0, Y, -214.0, 0.0)),
             POI("uc_garage", L("地下城・{name}", name="地下停車場"), "undercity", 192.0, 0.0, (192.0, Y, 0.0, 0.0)),
             POI("uc_food", L("地下城・{name}", name="地下美食街"), "undercity", 118.5, 206.5, (118.5, Y, 206.5, 0.0)),
             POI("uc_arcade", L("地下城・{name}", name="地下電玩街"), "undercity", -233.0, 100.0,
                 (-233.0, Y, 100.0, 0.0))]
    for ti, k in FEATURE_POIS:
        t = towers[ti]
        if k > t.floors:
            continue
        name = L("{name} {k}F {theme}", name=t.name, k=k, theme=floors.THEMES[floors.theme(k, t)])
        pois.append(POI(f"sky{ti}_{k}", name, "sky", t.cx + 4.0 * (ti + 1) - 2.0, t.cz,
                        (t.cx + t.half - 6.0, t.level_y(k), t.cz - 3.0, -math.pi / 2)))
    return pois


class CityMap:
    def __init__(self, pois, records, towers, paths, lines, bridges):
        self.pois = pois
        self.discovered = {START}
        self._load()
        self.open = False
        self.center = [0.0, 0.0]
        self.zoom_i = 1
        self.rect = pygame.Rect(0, 0, 1, 1)           # screen area of the map (set by draw)
        self.hover = None
        self._view_key, self._view = None, None
        self.levels = self._render_base(records, towers, paths, lines, bridges)

    # ---------------------------------------------------------------- unlock + save
    def _load(self):
        ids = savegame.load(SAVE_PATH).get("discovered", [])
        known = {p.id for p in self.pois}
        if isinstance(ids, list):
            self.discovered |= {i for i in ids if i in known}

    def reset(self):
        self.discovered = {START}

    def _save(self):
        savegame.merge(SAVE_PATH, discovered=sorted(self.discovered))

    def visit(self, pos):
        """Unlock the places around pos; returns the newly found POIs."""
        new = [p for p in self.pois if p.id not in self.discovered
               and math.hypot(pos[0] - p.tp[0], pos[2] - p.tp[2]) < VISIT_RADIUS and abs(pos[1] - p.tp[1]) < VISIT_DY]
        if new:
            self.discovered |= {p.id for p in new}
            self._save()
        return new

    def unlocked(self, poi):
        return poi.id in self.discovered

    # ---------------------------------------------------------------- base map
    def _render_base(self, records, towers, paths, lines, bridges):
        N = LEVELS[-1]
        s = N / (2 * EXTENT)
        base = pygame.Surface((N, N))
        base.fill((14, 14, 22))

        def px(x, z):
            return (x + EXTENT) * s, (z + EXTENT) * s

        def rect(x0, z0, x1, z1):
            a, b = px(x0, z0)
            c, d = px(x1, z1)
            return pygame.Rect(int(a), int(b), max(1, int(c - a + 0.5)), max(1, int(d - b + 0.5)))

        P = C.BLOCK_PITCH
        hb = P / 2 - C.ROAD_HALF
        parks = {(i, j): kind for _, i, j, kind in C.PARKS}
        R = C.CITY_BLOCKS
        for i in range(-R, R + 1):
            for j in range(-R, C.HARBOR_ROW + 1):
                cx, cz = i * P, j * P
                if (i, j) in parks:
                    col = (34, 84, 46) if parks[(i, j)] == "park" else (84, 76, 56)
                elif abs(i) <= 1 and abs(j) <= 1:
                    col = (40, 40, 62)                                # the tower plaza
                else:
                    col = DISTRICT_RGB[D.district(i, j)]
                base.fill(col, rect(cx - hb, cz - hb, cx + hb, cz + hb))
        base.fill((40, 40, 62), rect(-112, -112, 112, 112))
        for r in records:                                             # building footprints
            c = DISTRICT_RGB[r.district]
            lit = min(255, int(c[0] * 1.9)), min(255, int(c[1] * 1.9)), min(255, int(c[2] * 1.9))
            base.fill(lit, rect(r.lx - r.w / 2, r.lz - r.d / 2, r.lx + r.w / 2, r.lz + r.d / 2))
        for i in C.CONTAINER_BLOCKS:                                  # container yard stripes
            cx, cz = i * P, C.HARBOR_ROW * P
            for z in range(int(cz - 28), int(cz + 28), 6):
                base.fill((90, 70, 50), rect(cx - 28, z, cx + 28, z + 3))
        base.fill((10, 26, 48), rect(-EXTENT, C.SHORE_Z, EXTENT, EXTENT))   # the sea
        for px_, hw in harbor.PIERS:
            base.fill((120, 110, 90), rect(px_ - hw, C.SHORE_Z, px_ + hw, harbor.PIER_END))
        for r_, col in ((sea.ISLAND, (60, 110, 120)), (sea.PARK, (120, 60, 120))):          # 霓虹島, 海上遊樂園
            base.fill(col, rect(*r_))
        for d in sea.ISLAND_DOCKS + (sea.PARK_DOCK,):
            base.fill((120, 110, 90), rect(*d))
        pygame.draw.line(base, (255, 150, 80), px(0.0, harbor.PIER_END), px(0.0, sea.PARK_DOCK[1]), 2)  # ferry
        wx, _, wz = sea.WHEEL
        pygame.draw.circle(base, (255, 120, 220), [int(v) for v in px(wx, wz)], max(2, int(8 * s)), 2)
        for t in towers:
            acc = _hue_rgb(t.accent) if t.accent > 0 else (255, 70, 210)
            base.fill(acc, rect(t.cx - t.half, t.cz - t.half, t.cx + t.half, t.cz + t.half))
            base.fill((20, 20, 30), rect(t.cx - t.half + 4, t.cz - t.half + 4, t.cx + t.half - 4, t.cz + t.half - 4))
        for br in bridges:                                            # skybridges
            x0, z0, x1, z1 = br.deck
            base.fill((140, 230, 255), rect(x0, z0, x1, z1))
        for path, line in zip(paths, lines):                          # metro lines
            pts = [px(*path.at(d)[:2]) for d in range(0, int(path.P) + 8, 8)]
            col = _hue_rgb(line["hue"])
            if line["kind"] == "underground":
                col = tuple(int(c * 0.65) for c in col)
            pygame.draw.lines(base, col, True, pts, 5)
        mx0, mz0, mx1, mz1 = 3.0, mall.Z_STATION, 23.0, mall.Z_HALL      # the mall (dashed outline)
        hx0, hz0, hx1, hz1 = mall.HALL
        for x0, z0, x1, z1 in ((mx0, mz0, mx1, mz1), (hx0, hz0, hx1, hz1)):
            pygame.draw.rect(base, (190, 120, 255), rect(x0, z0, x1, z1), 2)
        o = undercity.R                                                # B2 ring, halls, connectors
        pygame.draw.rect(base, (255, 90, 90), rect(-o, -o, o, o), 3)
        for x0, z0, x1, z1 in undercity.HALLS.values():
            pygame.draw.rect(base, (255, 90, 90), rect(x0, z0, x1, z1), 2)
        levels = {N: base}
        for n in LEVELS[:-1]:
            levels[n] = pygame.transform.smoothscale(base, (n, n))
        return levels

    # ---------------------------------------------------------------- view
    def show(self, pos):
        self.open = True
        self.center = [pos[0], pos[2]]
        self.zoom_i = 1

    @property
    def zoom(self):
        return ZOOMS[self.zoom_i]

    def _scale(self):
        """Screen pixels per metre."""
        return self.rect.width / (2 * EXTENT) * self.zoom

    def to_screen(self, x, z):
        s = self._scale()
        return (self.rect.centerx + (x - self.center[0]) * s, self.rect.centery + (z - self.center[1]) * s)

    def to_world(self, sx, sy):
        s = self._scale()
        return (self.center[0] + (sx - self.rect.centerx) / s, self.center[1] + (sy - self.rect.centery) / s)

    def _clamp(self):
        half = EXTENT / self.zoom
        for k in (0, 1):
            self.center[k] = max(-EXTENT + half, min(EXTENT - half, self.center[k]))

    def zoom_at(self, mouse, steps):
        wx, wz = self.to_world(*mouse)
        self.zoom_i = max(0, min(len(ZOOMS) - 1, self.zoom_i + (1 if steps > 0 else -1)))
        s = self._scale()                                              # keep the point under the mouse
        self.center = [wx - (mouse[0] - self.rect.centerx) / s, wz - (mouse[1] - self.rect.centery) / s]
        self._clamp()

    def pan(self, dx, dy):
        s = self._scale()
        self.center[0] -= dx / s
        self.center[1] -= dy / s
        self._clamp()

    def poi_at(self, mouse, reach=11.0):
        best, bd = None, reach
        for p in self.pois:
            sx, sy = self.to_screen(p.x, p.z)
            d = math.hypot(sx - mouse[0], sy - mouse[1])
            if d < bd and self.rect.collidepoint(sx, sy):
                best, bd = p, d
        return best

    # ---------------------------------------------------------------- drawing
    def draw(self, surf, fonts, scale, player, taxis, line_hues, mouse, objectives=(), shards=None):
        """objectives: the active mission's ("point", x, z) / ("route", [(x, z), ...]) marks;
        shards: (collected, total) for the legend."""
        font, small = fonts
        w, h = surf.get_size()
        surf.fill((4, 5, 12, 235))
        side = int(min(h - 90 * scale, w - 400 * scale))
        self.rect = pygame.Rect(0, 0, side, side)
        self.rect.center = (w // 2 + int(120 * scale), h // 2 + int(10 * scale))
        self._clamp()

        # base map window
        n = next(n for n in LEVELS if n >= side * self.zoom) if side * self.zoom <= LEVELS[-1] else LEVELS[-1]
        img = self.levels[n]
        k = n / (2 * EXTENT)
        half = EXTENT / self.zoom * k
        src = pygame.Rect(int((self.center[0] + EXTENT) * k - half), int((self.center[1] + EXTENT) * k - half),
                          max(1, int(2 * half)), max(1, int(2 * half)))
        src = src.clip(img.get_rect())
        key = (n, tuple(src), side)
        if key != self._view_key:                       # rescale only when the view changed
            self._view_key = key
            self._view = pygame.transform.smoothscale(img.subsurface(src), (side, side)) if src.width < side * 2 \
                else pygame.transform.scale(img.subsurface(src), (side, side))
        surf.blit(self._view, self.rect)
        pygame.draw.rect(surf, (0, 220, 255), self.rect, 2)
        clip = surf.get_clip()
        surf.set_clip(self.rect)

        # live taxis
        for t in taxis:
            sx, sy = self.to_screen(t.x, t.z)
            pygame.draw.circle(surf, (255, 220, 80), (int(sx), int(sy)), max(2, int(2.5 * scale)))
        # places
        self.hover = self.poi_at(mouse)
        r = max(4, int(5 * scale))
        for p in self.pois:
            sx, sy = self.to_screen(p.x, p.z)
            label, col, shape = CAT_STYLE[p.cat]
            if col is None:
                col = _hue_rgb(line_hues[int(p.id[2])])
            self._icon(surf, shape, col, int(sx), int(sy), r + (2 if p is self.hover else 0), self.unlocked(p))
        if self.zoom >= 2.0:
            for p in self.pois:
                if self.unlocked(p) and p is not self.hover:
                    sx, sy = self.to_screen(p.x, p.z)
                    self._label(surf, small, p.name, (int(sx) + r + 3, int(sy)), (220, 230, 245))
        # the active mission: route and target
        for mark in objectives:
            if mark[0] == "route" and len(mark[1]) > 1:
                pts = [self.to_screen(x, z) for x, z in mark[1]]
                pygame.draw.lines(surf, (255, 200, 60), False, pts, 2)
                for x, y in pts:
                    pygame.draw.circle(surf, (255, 200, 60), (int(x), int(y)), max(2, int(3 * scale)))
        for mark in objectives:
            if mark[0] == "point":
                sx, sy = self.to_screen(mark[1], mark[2])
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.008)
                rr = int((9 + 5 * pulse) * scale)
                pygame.draw.circle(surf, (0, 0, 0), (int(sx), int(sy)), rr + 2, 3)
                pygame.draw.circle(surf, (255, 220, 60), (int(sx), int(sy)), rr, 3)
                pygame.draw.circle(surf, (255, 240, 160), (int(sx), int(sy)), max(3, int(4 * scale)))
        # the player
        px_, pz_ = self.to_screen(player.pos[0], player.pos[2])
        fx, fz = math.sin(player.yaw), -math.cos(player.yaw)
        a = 11 * scale
        tri = [(px_ + fx * a, pz_ + fz * a), (px_ - fx * a * 0.6 - fz * a * 0.55, pz_ - fz * a * 0.6 + fx * a * 0.55),
               (px_ - fx * a * 0.6 + fz * a * 0.55, pz_ - fz * a * 0.6 - fx * a * 0.55)]
        pygame.draw.polygon(surf, (0, 0, 0), [(x + 1, y + 1) for x, y in tri])
        pygame.draw.polygon(surf, (255, 60, 90), tri)
        surf.set_clip(clip)

        # hover tooltip
        if self.hover is not None:
            p = self.hover
            sx, sy = self.to_screen(p.x, p.z)
            state = tr("點擊快速移動") if self.unlocked(p) else tr("尚未造訪 — 先去一次才能快速移動")
            col = (120, 255, 200) if self.unlocked(p) else (255, 150, 120)
            r1 = self._label(surf, font, p.name, (int(sx) + r + 8, int(sy) - int(12 * scale)), (255, 255, 255), box=True)
            self._label(surf, small, state, (r1.left, r1.bottom + int(18 * scale)), col)

        # legend + controls
        x, y = int(24 * scale), int(30 * scale)
        self._label(surf, font, tr("城市地圖"), (x, y), (0, 220, 255))
        y += int(40 * scale)
        cats = {}
        for p in self.pois:
            cats.setdefault(p.cat, [0, 0])
            cats[p.cat][0] += 1
            cats[p.cat][1] += self.unlocked(p)
        for cat, (label, col, shape) in CAT_STYLE.items():
            if cat not in cats:
                continue
            col = col or (120, 200, 255)
            self._icon(surf, shape, col, x + 6, y, r, True)
            self._label(surf, small, f"{tr(label)}  {cats[cat][1]}/{cats[cat][0]}", (x + 20, y), (225, 230, 245))
            y += int(26 * scale)
        y += int(10 * scale)
        pygame.draw.line(surf, (255, 150, 80), (x, y), (x + 14, y), 2)
        self._label(surf, small, tr("渡輪航線"), (x + 20, y), (225, 230, 245))
        y += int(24 * scale)
        for line, hue in zip(("地心線（地下）", "天際線", "三塔線"), line_hues):
            pygame.draw.line(surf, _hue_rgb(hue), (x, y), (x + 14, y), 4)
            self._label(surf, small, tr(line), (x + 20, y), (225, 230, 245))
            y += int(24 * scale)
        y += int(10 * scale)
        for name, i in (("市中心", D.DOWNTOWN), ("企業特區", D.CORPORATE), ("霓虹夜市", D.MARKET),
                        ("住宅區", D.RESIDENTIAL), ("鏽蝕區", D.RUST), ("港灣區", D.HARBOR)):
            c = DISTRICT_RGB[i]
            pygame.draw.rect(surf, tuple(min(255, int(v * 1.9)) for v in c), (x, y - 6, 14, 12))
            self._label(surf, small, tr(name), (x + 20, y), (225, 230, 245))
            y += int(24 * scale)
        found = len(self.discovered)
        self._label(surf, small, tr("已解鎖 {found}/{total} 個地點", found=found, total=len(self.pois)),
                    (x, y + int(10 * scale)), (255, 215, 80))
        if shards is not None:
            self._label(surf, small, tr("資料碎片 {n}/{total}", n=shards[0], total=shards[1]), (x, y + int(34 * scale)),
                        (120, 240, 255))
        if objectives:
            self._label(surf, small, tr("◎ 任務目標"), (x, y + int(58 * scale)), (255, 220, 60))
        help_ = tr("滾輪 縮放（{zoom:.0f}×）· 拖曳 平移 · 點擊地點 快速移動 · M / Esc 關閉", zoom=self.zoom)
        self._label(surf, small, help_, (self.rect.centerx, self.rect.bottom + int(18 * scale)), (200, 210, 230),
                    anchor="center")

    @staticmethod
    def _icon(surf, shape, col, x, y, r, filled):
        width = 0 if filled else 2
        if not filled:
            col = tuple(int(c * 0.7) for c in col)
        if shape == "square":
            pygame.draw.rect(surf, (0, 0, 0), (x - r - 1, y - r - 1, 2 * r + 2, 2 * r + 2), 0 if filled else 1)
            pygame.draw.rect(surf, col, (x - r, y - r, 2 * r, 2 * r), width)
        elif shape == "diamond":
            pts = [(x, y - r - 1), (x + r + 1, y), (x, y + r + 1), (x - r - 1, y)]
            pygame.draw.polygon(surf, col, pts, width)
        elif shape == "triangle":
            pygame.draw.polygon(surf, col, [(x, y - r - 1), (x + r + 1, y + r), (x - r - 1, y + r)], width)
        else:
            if filled:
                pygame.draw.circle(surf, (0, 0, 0), (x, y), r + 1)
            pygame.draw.circle(surf, col, (x, y), r, width)

    @staticmethod
    def _label(surf, font, text, pos, color, box=False, anchor="midleft"):
        text = tr(text)                                 # place names (str or L) in the current language
        img = font.render(text, True, color)
        rect = img.get_rect(**{anchor: pos})
        if box:
            pygame.draw.rect(surf, (6, 8, 22, 230), rect.inflate(14, 8), border_radius=4)
            pygame.draw.rect(surf, (0, 220, 255), rect.inflate(14, 8), 1, border_radius=4)
        else:
            surf.blit(font.render(text, True, (0, 0, 0)), rect.move(1, 1))
        surf.blit(img, rect)
        return rect
