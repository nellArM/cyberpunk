"""Neon City - first-person walk through a cyberpunk city with three walk-in megatowers
(1000, 550 and 800 floors), themed districts, parks, a harbor, an underground mall, skybridges,
three metro lines and air taxis.

Controls: WASD move, mouse look, Shift run, Space jump (in the air: wingsuit), Q double jump,
Left Ctrl dash, F / right mouse grapple, E use elevator / taxi / talk / mission terminal / clinic,
in the elevator: digits or mouse wheel pick a floor, E/Enter go; in a taxi: digits pick a stand,
Space bails out mid-flight; J abandon mission, T teleport to a roof (again: next tower), R respawn,
F7 language (中文 / English), F8 save, Tab release mouse, F1 help, F3 debug, Esc quit (saves).

Start with --continue / --new to skip the start screen (continue the save / start over);
--lang zh / en picks the language (otherwise the saved one, else Chinese).
"""
import argparse
import math
import random
import time

import moderngl
import numpy as np
import pygame

import buildings
import citymap
import config as C
import districts
import environment
import floors
import i18n
import mall
import progress
import savegame
from audio import Audio
from citymap import CityMap, build_pois
from crowds import LaneCrowd
from environment import Environment
from harbor import Boats, build_harbor, in_water
import sea
import undercity
from sea import build_sea
from city import Traffic, build_city
from collision import StaticWorld
from effects import Dust, Fire, Smoke, Streaks
from elevator import GROUND, Elevator
from floors import TOWERS
from geometry import direction
from hud import Hud
from i18n import L, tr
from metro import KIND_LABEL, LINES, Trains, build_metro
from missions import Missions
from parks import build_parks
from pedestrians import Pedestrians
from pickups import Pickups, build_pickups
from player import BOOT_BRAKING, BOOT_HOVER, BOOT_LANDED, BOOT_NAMES, BOOT_OFF, Player
from renderer import Renderer
from shaders import CLOUD_Y
from shops import ShopManager
from taxi import Obstacles, TaxiFleet, stand_decor
from tower import build_tower
from tower_interior import Interiors
from traffic import GroundTraffic, build_signals
from workers import OfficeWorkers

UNDERGROUND_Y = -0.5                    # below this (metro stations, mall): no wingsuit, no grapple
AUTOSAVE = 120.0                        # seconds between automatic saves
CLINIC = 2                              # SHOP_TYPES index of the CHROME cyberware clinic

HELP = [
    "WASD 移動 · 滑鼠 轉視角 · Shift 奔跑 · Space 跳躍（空中再按 Space：展開 / 收起翼裝）",
    "Q 二段跳 · 左 Ctrl 噴射衝刺（翼裝中衝刺加速）— 共用噴射次數，用完要等冷卻",
    "F 或右鍵：發射鉤索（準心出現黃圈時可勾住），再按一次放開；地下車站與地下商場禁用翼裝和鉤索",
    "任務：走到地圖上的任務終端按 E 接任務（送貨、天氣急件、翼裝穿圈賽、屋頂跑酷），J 放棄",
    "資料碎片：城市各處發光的碎片，撿到換信用點；CHROME 義體診所對店員按 E 升級義體",
    "E 搭乘 / 呼叫電梯、計程車、跟店員說話 · T 傳送到最近的頂樓（在頂樓再按 T 換下一棟）· R 回到起點",
    "電梯內：數字鍵輸入樓層（滾輪 ±1，Shift ±10），E / Enter 出發；60 m 以上的建築櫃台後方也有電梯",
    "每棟建築一樓都是商店，櫃台後方的員工門通往樓梯與電梯；有些高樓之間有空中天橋",
    "地鐵：地心線（地下）、天際線（高架外環）、三塔線（NEXUS → HELIX → 霓虹公園 → AURORA）",
    "地下商場：霓虹市集站月台旁的地下街（電動步道）直通 NEXUS 大廳地下",
    "B2 地下城：地心線四站月台旁的通道往下走，環道上有黑市、停車場、美食街、電玩街",
    "渡輪：港灣主碼頭 → 霓虹島 → 海上遊樂園（摩天輪、自由落體塔可以搭）· 大樓每 100 層有特色樓層",
    "空中計程車：頂樓、廣場、公園、港灣碼頭、企業特區停機坪；車內按數字（0 = 第 10 站），Space 跳車",
    "城區：市中心、企業特區（東北）、霓虹夜市（西北）、住宅區（東南）、鏽蝕區（西南）、港灣（南岸 z~1180）",
    "M 城市地圖：去過的地點可直接點擊快速移動（解鎖進度自動存檔）",
    "F5 切換天氣（自動／晴／多雲／雨／暴雨／霧）· F6 時間流速（正常／快轉／暫停）· [ ] 調整時間 ±1 小時",
    "F8 存檔（離開時與每 2 分鐘也會自動存檔）· Tab 釋放滑鼠 · F1 顯示/隱藏說明 · F3 除錯資訊 · Esc 離開",
    "F7 切換語言（中文 / English）",
]                                       # (Chinese text is the key; tr() shows it in the current language)


class Game:
    def __init__(self, args):
        i18n.set_lang(getattr(args, "lang", None) or savegame.load(citymap.SAVE_PATH).get("lang") or "zh")
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        req = (args.width, args.height)
        if args.fullscreen:
            flags |= pygame.FULLSCREEN
            req = (0, 0)
        try:
            pygame.display.set_mode(req, flags, vsync=1)
        except pygame.error:
            pygame.display.set_mode(req, flags)
        pygame.display.set_caption("Neon City — Megatowers")
        self.size = pygame.display.get_surface().get_size()
        self.ctx = moderngl.create_context()

        t0 = time.perf_counter()
        rng = np.random.default_rng(args.seed)
        self.metro = build_metro()
        parks = build_parks(self.metro.colliders)
        skip = self.metro.skip_blocks | {t.block for t in TOWERS[1:]} | districts.park_blocks()
        city = build_city(rng, skip)
        towers = [build_tower(t) for t in TOWERS]
        harbor = build_harbor(np.random.default_rng(args.seed + 1))
        self.mall = mall.build_mall(np.random.default_rng(args.seed + 2))
        self.sea = build_sea(np.random.default_rng(args.seed + 3))
        self.uc = undercity.build_undercity(np.random.default_rng(args.seed + 4))
        rail_boxes, rail_cols, rail_holos = mall.lobby_rails()
        signal_boxes, signal_cols = build_signals()
        signal_boxes = np.array(signal_boxes, dtype="f4").reshape(-1, city.boxes.shape[1])
        tower_cols = [c for td in towers for c in td.colliders]
        # city colliders come first: ShopRecord.upper_col indexes into this list
        self.world = StaticWorld(city.colliders + tower_cols + signal_cols + self.metro.colliders + parks.colliders
                                 + harbor.colliders + self.mall.colliders + rail_cols + self.sea.colliders
                                 + self.uc.colliders,
                                 holes=self.metro.holes + [C.MALL_STAIR], water_z=C.SHORE_Z)
        # people you can talk to (E): mall clerks, island / park stall keepers, undercity dealers
        self.talkers = ([(c.x, c.y, c.z, C.SHOP_TYPES[c.kind][0], C.SHOP_TYPES[c.kind][2]) for c in self.mall.clerks]
                        + [tuple(t) for t in self.sea.talkers] + [tuple(t) for t in self.uc.talkers])
        self.traffic = Traffic(rng)
        self.ground = GroundTraffic(rng)
        self.peds = Pedestrians(rng, park_blocks=[(i, j) for _, i, j, _ in C.PARKS])
        self.crowd = LaneCrowd(rng, self.mall.walk_loops + harbor.walk_loops + self.sea.walk_loops
                               + self.uc.walk_loops)
        self.boats = Boats(rng)
        self.shops = ShopManager(city.shops)
        self.shops.set_bridges(city.bridges)
        self.elevators = [Elevator(t) for t in TOWERS]
        self.dry = [(t.cx - t.half - 0.5, -1.0, t.cz - t.half - 0.5, t.cx + t.half + 0.5, t.height,
                     t.cz + t.half + 0.5) for t in TOWERS]                  # no rain inside the towers
        self.trains = Trains(self.metro.stations)
        stands = ([(L("{name} 頂樓", name=t.name), t.cx, t.height, t.cz) for t in TOWERS]
                  + [("NEXUS 廣場", -80.0, 0.0, 80.0)] + parks.stands + [harbor.stand])
        pads = [(c, i) for c, i in city.helipads if city.shops[i].district == districts.CORPORATE
                and buildings.has_shaft(city.shops[i]) and min(city.shops[i].w, city.shops[i].d) >= 30.0]
        if pads:                                                            # 10th stand: a corporate rooftop
            (px, py, pz), _ = min(pads, key=lambda p: math.hypot(p[0][0], p[0][2]))
            stands.append(("企業特區 停機坪", px, py, pz))
        obstacles = Obstacles([(r.lx - r.w / 2, r.lz - r.d / 2, r.lx + r.w / 2, r.lz + r.d / 2, r.top)
                               for r in city.shops]
                              + [(t.cx - t.half, t.cz - t.half, t.elev_x1 + 0.5, t.cz + t.half, t.height)
                                 for t in TOWERS] + harbor.obstacles + self.sea.obstacles)
        self.taxis = TaxiFleet(stands, obstacles)
        self.missions = Missions(self.world, city.shops, seed=args.seed)      # adds the kiosks to the world
        self.pickups = Pickups(build_pickups(self.world, city.shops, city.bridges, self.metro.stations, TOWERS))
        self.citymap = CityMap(build_pois(TOWERS, self.metro.stations, LINES, self.taxis.stands,
                                          self.missions.terminals), city.shops, TOWERS,
                               self.trains.paths, LINES, city.bridges)
        self.missions.set_destinations(self.citymap.pois)
        self.map_drag = None              # [press position, distance dragged] while panning the map
        decor_boxes, decor_holos = stand_decor(stands)
        decor_boxes = np.array(decor_boxes + rail_boxes, "f4").reshape(-1, city.boxes.shape[1])
        decor_holos = np.array(decor_holos + rail_holos, "f4").reshape(-1, city.holos.shape[1])
        static_boxes = np.concatenate([city.boxes] + [td.boxes for td in towers]
                                      + [signal_boxes, self.metro.boxes, parks.boxes, decor_boxes, harbor.boxes,
                                         self.mall.boxes, self.sea.boxes, self.uc.boxes,
                                         np.array(self.missions.boxes, "f4").reshape(-1, city.boxes.shape[1])])
        static_quads = np.concatenate([city.holos] + [td.holos for td in towers]
                                      + [self.metro.quads, parks.holos, decor_holos, harbor.holos, self.mall.holos,
                                         self.sea.holos, self.uc.holos,
                                         np.array(self.missions.holos, "f4").reshape(-1, city.holos.shape[1])])
        self.renderer = Renderer(self.ctx, self.size, static_boxes, static_quads,
                                 self.traffic.count + self.ground.count * 3, args.msaa, static_rot=self.metro.rot)
        self.renderer.set_ground_holes(self.metro.holes)
        lobbies = [(t.cx - t.half + 0.5, t.cz - t.half + 0.5, t.cx + t.half - 0.5, t.cz + t.half - 0.5, 0)
                   for t in TOWERS]                                         # lobbies have their own floor
        self.renderer.set_ground_zones(lobbies + parks.zones)
        print(f"[city] {len(static_boxes)} boxes, {len(self.world.boxes)} colliders, {len(city.shops)} shops, "
              f"{len(city.bridges)} skybridges, {len(city.helipads)} helipads, "
              f"{self.ground.count} cars, {self.peds.n} pedestrians, built in {time.perf_counter() - t0:.2f}s")

        self.player = Player(C.SPAWN, yaw=0.0)
        self.fire, self.smoke, self.dust = Fire(rng), Smoke(rng), Dust(rng)
        self.streaks = Streaks(rng)
        self.audio = Audio()
        self.hud = Hud(self.ctx, self.size)
        self.env = Environment(seed=args.seed)          # 20:00, raining, weather changes on its own

        self.time = 0.0
        self.show_help = True
        self.debug = False
        self.message, self.message_t = "", 0.0
        self.prev_eye = None
        self.cam_vel = np.zeros(3)
        self.hud_timer = 0.0
        self.fps = 0.0
        self.riding = False
        self.shop = None
        self.welcome_t = 0.0
        self.interior = Interiors()
        self.workers = OfficeWorkers()
        self.ride = None                  # metro car the player stands in
        self.ride_world = StaticWorld([])
        self.floor_input = ""
        self.aim = None                   # distance to what the grapple would hit
        self.on_ride = None               # the ferry / gondola / drop tower car the player stands on
        self.dyn = []                     # last frame's dynamic colliders (for the grapple ray)
        self.menu = None                  # ("clinic", shop) / ("terminal", terminal) while a menu is open
        self.menu_at = None
        self.banner_msg, self.banner_col, self.banner_t = "", (255, 255, 255), 0.0
        self.progress = progress.Progress(lambda: citymap.SAVE_PATH)
        self.seed = args.seed
        self.safe = (tuple(C.SPAWN), 0.0)  # last spot the player stood still on solid ground: (pos, yaw)
        self.autosave_t = AUTOSAVE
        self.saved_msg = ""
        self.title = None                 # start screen state while it is shown
        start = getattr(args, "start", "continue")
        data = savegame.load(citymap.SAVE_PATH)
        if start == "new":
            self.new_game()
        elif data and start == "ask":
            self.title = {"data": data, "confirm": False}
        elif data:
            self.apply_save(data)
        self.set_grab(True)

    # ---------------------------------------------------------------- save / load
    def place_label(self):
        """Where the player is, for the save summary (district / area / floor)."""
        self.hud_state()
        return self.place

    def save_game(self, auto=False):
        pl, env = self.player, self.env
        (x, y, z), yaw = self.safe
        kind, auto_w = self.missions.weather_backup or (env.kind, env.auto)
        ok = savegame.merge(citymap.SAVE_PATH, discovered=sorted(self.citymap.discovered), **self.progress.fields(),
                            player={"pos": [round(x, 3), round(y, 3), round(z, 3)], "yaw": round(yaw, 4)},
                            world={"hour": round(env.hour, 3), "kind": kind, "auto": auto_w, "speed": env.speed_i},
                            saved_at=time.strftime("%Y-%m-%d %H:%M"), place=self.place_label(), lang=i18n.LANG)
        if not auto:
            self.flash(tr("已存檔 {t}", t=time.strftime('%H:%M')) if ok else tr("存檔失敗（無法寫入 savegame.json）"))
        return ok

    def apply_save(self, data):
        """Continue a saved game: progress, places, position, time and weather."""
        self.progress.load(data)
        pl = self.player
        pl.stats = self.progress.stats()
        p = data.get("player", {})
        try:
            pos = [float(v) for v in p.get("pos", ())]
            yaw = float(p.get("yaw", 0.0))
            lim = C.CITY_BLOCKS * C.BLOCK_PITCH + 300.0
            if len(pos) == 3 and all(math.isfinite(v) for v in pos) and abs(pos[0]) < lim and -lim < pos[2] < 3000.0 \
                    and -40.0 < pos[1] < 4100.0:
                pl.reset(pos, yaw=yaw)
                self.safe = (tuple(pos), yaw)
        except (TypeError, ValueError, AttributeError):
            pass
        w = data.get("world", {})
        env = self.env
        try:
            env.hour = float(w.get("hour", env.hour)) % 24.0
            kind = int(w.get("kind", env.kind))
            if 0 <= kind < len(environment.KINDS):
                env.set_weather(kind, bool(w.get("auto", True)))
                env.cloud, env.rain, env.fog, env.storm = environment.TARGETS[kind]   # no 20 s blend on load
                env.wet = 1.0 if env.rain > 0.1 else 0.0
            env.speed_i = int(w.get("speed", 0)) % len(environment.SPEEDS)
        except (TypeError, ValueError, AttributeError):
            pass
        self.prev_eye = None

    def new_game(self):
        """Start over (the old save is kept as savegame.bak.json)."""
        savegame.reset(citymap.SAVE_PATH)
        self.missions.abort(self.env)
        self.citymap.reset()
        self.progress.reset()
        self.env = Environment(seed=self.seed)
        pl = self.player
        pl.stats = self.progress.stats()
        pl.reset(C.SPAWN, yaw=0.0)
        self.safe = (tuple(C.SPAWN), 0.0)
        self.prev_eye = None

    def title_lines(self):
        d = self.title["data"]
        shards = d.get("shards", [])
        disc = d.get("discovered", [])
        lines = ["NEON CITY",
                 tr("存檔：{when} · {place}", when=d.get('saved_at', tr('（時間不明）')), place=d.get('place', '')),
                 tr("信用點 ${credits:,} · 資料碎片 {shards}/{total} · 已解鎖地點 {found}/{places}",
                    credits=int(d.get('credits', 0) or 0), shards=len(shards) if isinstance(shards, list) else 0,
                    total=len(self.pickups), found=len(disc) if isinstance(disc, list) else 0,
                    places=len(self.citymap.pois)),
                 "",
                 tr("[1] 繼續遊戲（讀取存檔）"),
                 tr("[2] 新遊戲（重置進度，舊檔備份為 savegame.bak.json）"),
                 f"[L] 語言 / Language: {i18n.LANG_NAMES[i18n.LANG]}"]
        if self.title["confirm"]:
            lines.append(tr("!再按一次 2 確認重置 — 進度會從頭開始"))
        lines.append(tr("Esc 離開"))
        return lines

    def title_key(self, ev):
        """Input on the start screen; returns False to quit."""
        if ev.key == pygame.K_ESCAPE:
            return False
        self.hud_timer = 0.0                            # show the change right away
        if ev.unicode == "1" or ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.apply_save(self.title["data"])
            self.title = None
            self.flash(tr("已讀取存檔，歡迎回來"), 3.0)
        elif ev.unicode == "2":
            if self.title["confirm"]:
                self.title = None
                self.new_game()
                self.flash(tr("新遊戲開始！舊存檔已備份為 savegame.bak.json"), 4.0)
            else:
                self.title["confirm"] = True
        elif ev.key == pygame.K_l:
            self.toggle_language()
        else:
            self.title["confirm"] = False
        return True

    def toggle_language(self):
        """中文 <-> English; the choice is kept in the save file."""
        i18n.toggle()
        savegame.merge(citymap.SAVE_PATH, lang=i18n.LANG)
        self.flash(tr("語言：中文"), 2.5)
        self.hud_timer = 0.0

    # ---------------------------------------------------------------- menus (clinic upgrades, mission terminals)
    def open_menu(self, kind, what):
        self.menu = (kind, what)
        self.menu_at = tuple(self.player.pos)

    def menu_lines(self):
        kind, what = self.menu
        if kind == "terminal":
            return self.missions.menu_lines(what, self.progress)
        pr = self.progress
        lines = [tr("{shop} — 義體升級        信用點 ${credits:,}", shop=what.name, credits=pr.credits)]
        for i, k in enumerate(progress.ORDER):
            name = tr(progress.UPGRADES[k][0])
            lv, price = pr.levels[k], pr.price(k)
            cost = f"Lv{lv} → Lv{lv + 1}  ${price:,}" if price else tr("Lv{lv}（已滿級）", lv=lv)
            lines.append(f"{i + 1}   {name}  {cost}   {progress.describe(k, lv)}")
        lines.append(tr("數字鍵購買 · E / Esc 離開 · 撿資料碎片、做任務賺信用點"))
        return lines

    def menu_digit(self, ch):
        kind, what = self.menu
        i = int(ch) - 1
        if kind == "terminal":
            msg = self.missions.start(what, i, self.player, self.env, self.progress)
            if msg:
                self.flash(msg, 4.0)
                if self.missions.active is not None:
                    self.menu = None
        elif 0 <= i < len(progress.ORDER):
            ok, msg = self.progress.buy(progress.ORDER[i])
            self.flash(msg, 3.0)
            if ok:
                self.player.stats = self.progress.stats()
                self.show_banner(tr("義體升級完成"), (120, 255, 200), 2.0)

    def show_banner(self, text, color, seconds):
        self.banner_msg, self.banner_col, self.banner_t = text, color, seconds

    def mission_lock(self, what):
        """Teleports are off while a mission runs; returns True (and says so) if locked."""
        if self.missions.active is not None:
            self.flash(tr("任務進行中不能{what}（J 放棄任務）", what=what), 3.0)
            return True
        return False

    # ---------------------------------------------------------------- input
    def set_grab(self, on):
        self.grabbed = on
        pygame.event.set_grab(on)
        pygame.mouse.set_visible(not on)
        pygame.mouse.get_rel()

    def flash(self, text, seconds=2.5):
        self.message, self.message_t = text, seconds

    def all_elevators(self):
        """The megatowers' elevators plus the elevator of the city building the player is in."""
        el = self.interior.elevator
        return self.elevators + ([el] if el is not None else [])

    def car(self):
        """The elevator whose car the player stands in, or None."""
        for el in self.all_elevators():
            if el.contains(self.player.pos):
                return el
        return None

    def near_landing(self):
        """(elevator, floor number) of the elevator landing the player stands at, or None."""
        for el in self.all_elevators():
            k = el.landing_zone(self.player.pos)
            if k is not None:
                return el, k
        return None

    def underground(self):
        """Below street level: metro stations, their passages and the mall. No wingsuit or grapple here."""
        return self.player.pos[1] < UNDERGROUND_Y

    def grapple_toggle(self):
        pl = self.player
        if pl.grapple is not None:
            pl.release_grapple()
        elif self.underground():
            self.flash(tr("地下區域禁止使用鉤索"))
        elif self.taxis.rider is not None or self.car() is not None or self.ride is not None:
            self.flash(tr("這裡不能用鉤索"))
        elif self.aim is None:
            self.flash(tr("鉤索射程 {r:.0f} m 內沒有可勾住的東西", r=pl.stats['grapple_range']))
        else:
            eye, fwd = pl.eye(), direction(pl.yaw, pl.pitch)
            pl.fire_grapple(tuple(eye[i] + fwd[i] * self.aim for i in range(3)))

    def glide_toggle(self):
        pl = self.player
        if self.car() is not None or self.ride is not None:
            return
        if self.underground() and not pl.glide:
            self.flash(tr("地下區域禁止使用翼裝"))
            return
        if pl.toggle_glide():
            self.flash(tr("翼裝展開！往下看加速、往上看拉升"), 3.0)
        elif not pl.glide and not pl.grounded and pl.height_above_ground < pl.stats["glide_min_h"]:
            self.flash(tr("太低了，展不開翼裝（Q 二段跳可以再往上）"))

    def boost(self, kind):
        """Q double jump / Ctrl dash from the rocket boots."""
        pl = self.player
        if self.taxis.rider is not None or self.car() is not None or self.ride is not None or self.citymap.open:
            return
        why = pl.double_jump() if kind == "jump" else pl.dash()
        if why == "ground":
            self.flash(tr("二段跳要在空中用 — 先按 Space 跳起來"))
        elif why == "empty":
            self.flash(tr("噴射次數用完了，{s:.1f} 秒後回復一次", s=pl.recharge))
        elif why == "":
            self.show_banner(tr("二段跳！") if kind == "jump" else tr("噴射衝刺！"), (255, 170, 70), 0.6)

    def on_roof(self):
        """The tower whose roof (or the air just above it) the player is on, or None."""
        p = self.player.pos
        for t in TOWERS:
            if t.height - 0.5 <= p[1] < t.height + 30.0 and t.distance(p) < 10.0:
                return t
        return None

    def near_roof_elevator(self):
        """The tower whose roof-level elevator spot the player stands next to, or None."""
        p = self.player.pos
        for t in TOWERS:
            if t.height - 1.0 < p[1] < t.height + 30.0 and math.hypot(p[0] - t.cx - t.half, p[2] - t.cz) < 9.0:
                return t
        return None

    def target_floor(self, el):
        """Destination chosen in car el: typed number, else lobby <-> roof."""
        if self.floor_input:
            return max(GROUND, min(el.max_stop, int(self.floor_input)))
        return el.max_stop if el.level == GROUND else GROUND

    def teleport_roof(self):
        """To the nearest tower's helipad; from a roof, on to the next tower's."""
        if self.mission_lock("傳送"):
            return
        self.leave_taxi()
        t = self.on_roof()
        t = TOWERS[(t.index + 1) % len(TOWERS)] if t is not None else floors.nearest_tower(self.player.pos)
        self.player.reset((t.cx, t.height, t.cz + 25.0 * t.half / 40.0), yaw=math.pi)
        self.flash(tr("已傳送到 {name} 頂樓直升機坪（{h:.0f} m）", name=t.name, h=t.height))

    def leave_taxi(self):
        """Drop out of the taxi without ceremony (before teleports)."""
        if self.taxis.rider is not None:
            self.taxis.bail_out()

    def taxi_destination(self, digit):
        taxi = self.taxis.rider
        stands = self.taxis.stands
        k = (int(digit) - 1) % 10                       # 1..9, 0 = 10th
        if not 0 <= k < len(stands):
            return
        if not taxi.parked:
            self.flash(tr("飛行中… 按 Space 可以跳車"))
        elif stands[k] is taxi.stand:
            self.flash(tr("已經在 {name}", name=stands[k].name))
        else:
            self.taxis.send(taxi, stands[k])
            self.flash(tr("起飛！前往 {name}，約 {s:.0f} 秒", name=stands[k].name, s=taxi.eta()))

    def interact(self):
        if self.menu is not None:
            self.menu = None
            return
        el = self.car()
        landing = self.near_landing()
        roof_t = self.near_roof_elevator()
        rider = self.taxis.rider
        stand = self.taxis.stand_near(self.player.pos) if rider is None else None
        if rider is not None:
            if rider.parked:
                self.player.reset(self.taxis.leave(), yaw=self.player.yaw, pitch=self.player.pitch)
                self.flash(tr("已下車：{name}", name=rider.stand.name))
            else:
                self.flash(tr("飛行中… 按 Space 可以跳車"))
        elif el is not None:
            if el.state != "idle":
                self.flash(tr("電梯運行中…"))
                return
            target = self.target_floor(el)
            self.floor_input = ""
            if target == el.level:
                self.flash(tr("已經在 {name}", name=el.label(target)))
            elif el.request(target):
                self.flash(tr("關門中，前往 {floor}…", floor=el.label(target)))
        elif landing is not None:
            el, level = landing
            if el.level == level and el.state in ("idle", "opening"):
                self.flash(tr("電梯已在此樓層，請進入"))
            elif el.request(level):
                self.flash(tr("已呼叫電梯到 {floor}，請稍候…", floor=el.label(level)))
            else:
                self.flash(tr("電梯運行中，請稍候…"))
        elif stand is not None:
            taxi = self.taxis.parked_at(stand)
            if taxi is not None:
                self.taxis.board(taxi)
                self.flash(tr("上車了——按數字鍵選擇目的地"), 3.5)
            else:
                eta = self.taxis.summon(stand)
                self.flash(tr("已呼叫 {name} 的計程車，約 {s:.0f} 秒後抵達", name=stand.name, s=eta) if eta
                           else tr("計程車就在這裡"))
        elif roof_t is not None:
            self.flash(tr("頂樓在大樓外側，無法呼叫電梯——請從樓梯口走下 {n}F", n=roof_t.floors))
        else:
            p = self.player.pos
            shop = self.shops.clerk_near(p)
            talker = self.talker_near(p)
            term = self.missions.terminal_near(p)
            if term is not None:
                self.open_menu("terminal", term)
            elif shop is not None and shop.kind == CLINIC:
                self.open_menu("clinic", shop)
                self.flash(tr("店員：「{line}」", line=C.SHOP_TYPES[shop.kind][2]), 4.0)
            elif shop is not None:
                self.flash(tr("店員：「{line}」", line=C.SHOP_TYPES[shop.kind][2]), 4.0)
            elif talker is not None:
                self.flash(tr("{who}：「{line}」", who=talker[3], line=talker[4]), 4.0)

    def talker_near(self, p, reach=3.5):
        """(x, y, z, name, line) of someone to talk to within reach, or None."""
        return next((t for t in self.talkers if abs(p[1] - t[1]) < 2.0 and math.hypot(p[0] - t[0], p[2] - t[2]) < reach),
                    None)

    # ---------------------------------------------------------------- city map
    def toggle_map(self):
        cm = self.citymap
        if cm.open:
            cm.open = False
            self.map_drag = None
            self.set_grab(True)
        else:
            cm.show(self.player.pos)
            self.set_grab(False)

    def fast_travel(self, poi):
        if not self.citymap.unlocked(poi):
            self.flash(tr("「{name}」尚未造訪 — 先去一次才能快速移動", name=poi.name), 3.0)
            return
        if self.mission_lock("快速移動"):
            return
        self.leave_taxi()
        pl = self.player
        x, y, z, yaw = poi.tp
        pl.reset((x, y, z), yaw=yaw)                    # also folds the wingsuit / drops the grapple
        self.prev_eye = None
        self.toggle_map()
        self.flash(tr("已移動到 {name}", name=poi.name), 3.0)

    def map_event(self, ev):
        """Input while the map is open (M / Esc close it)."""
        cm = self.citymap
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_m, pygame.K_ESCAPE):
            self.toggle_map()
        elif ev.type == pygame.MOUSEWHEEL:
            cm.zoom_at(pygame.mouse.get_pos(), ev.y)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.map_drag = [ev.pos, 0.0]
        elif ev.type == pygame.MOUSEMOTION and self.map_drag is not None and ev.buttons[0]:
            cm.pan(*ev.rel)
            self.map_drag[1] += abs(ev.rel[0]) + abs(ev.rel[1])
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.map_drag is not None:
            moved = self.map_drag[1]
            self.map_drag = None
            if moved < 6:                               # a click, not a drag
                poi = cm.poi_at(ev.pos)
                if poi is not None:
                    self.fast_travel(poi)

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if self.title is not None:                  # start screen: continue / new game
                if ev.type == pygame.KEYDOWN and not self.title_key(ev):
                    return False
                continue
            if self.citymap.open:
                self.map_event(ev)
                continue
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if self.menu is not None:
                        self.menu = None
                        continue
                    return False
                if ev.key == pygame.K_m:
                    self.menu = None
                    self.toggle_map()
                elif ev.key == pygame.K_TAB:
                    self.set_grab(not self.grabbed)
                elif ev.key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.interact()
                elif self.menu is not None and ev.unicode.isdigit() and ev.unicode != "0":
                    self.menu_digit(ev.unicode)
                elif ev.key == pygame.K_q:
                    self.boost("jump")
                elif ev.key == pygame.K_LCTRL:
                    self.boost("dash")
                elif ev.key == pygame.K_j:
                    msg = self.missions.abort(self.env)
                    self.flash(msg or tr("目前沒有進行中的任務"))
                elif ev.key == pygame.K_F8:
                    self.save_game()
                elif ev.key == pygame.K_F7:
                    self.toggle_language()
                elif self.car() is not None and ev.unicode.isdigit():
                    self.floor_input = (self.floor_input + ev.unicode).lstrip("0")[:4]
                elif self.taxis.rider is not None and ev.unicode.isdigit():
                    self.taxi_destination(ev.unicode)
                elif ev.key == pygame.K_SPACE and self.taxis.rider is not None and not self.taxis.rider.parked:
                    pos, vel = self.taxis.bail_out()
                    self.player.pos[:], self.player.vel[:] = pos, vel
                    self.flash(tr("跳車！空中按 Space 展開翼裝"), 3.0)
                elif ev.key == pygame.K_SPACE and self.taxis.rider is None and not self.player.grounded:
                    self.glide_toggle()
                elif ev.key == pygame.K_f:
                    self.grapple_toggle()
                elif ev.key == pygame.K_BACKSPACE:
                    self.floor_input = self.floor_input[:-1]
                elif ev.key == pygame.K_t:
                    self.teleport_roof()
                elif ev.key == pygame.K_r:
                    if not self.mission_lock("回到起點"):
                        self.leave_taxi()
                        self.player.reset(C.SPAWN, yaw=0.0)
                elif ev.key == pygame.K_F5:
                    self.env.cycle_weather()
                    self.flash(tr("天氣：{w}", w=self.env.label()))
                elif ev.key == pygame.K_F6:
                    self.env.cycle_speed()
                    self.flash(tr("時間流速：{s}", s=self.env.speed_label))
                elif ev.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
                    self.env.shift_hours(-1.0 if ev.key == pygame.K_LEFTBRACKET else 1.0)
                    self.flash(tr("時間：{t}", t=self.env.label()))
                elif ev.key == pygame.K_F1:
                    self.show_help = not self.show_help
                elif ev.key == pygame.K_F3:
                    self.debug = not self.debug
            elif ev.type == pygame.MOUSEWHEEL and self.car() is not None:
                el = self.car()
                step = 10 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
                base = int(self.floor_input) if self.floor_input else el.level
                self.floor_input = str(max(GROUND, min(el.max_stop, base + ev.y * step)))
            elif ev.type == pygame.MOUSEBUTTONDOWN and not self.grabbed:
                self.set_grab(True)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                self.grapple_toggle()
            elif ev.type == pygame.MOUSEMOTION and self.grabbed:
                dx, dy = ev.rel
                if abs(dx) < 400 and abs(dy) < 400:
                    self.player.look(dx, dy)
        return True

    # ---------------------------------------------------------------- update
    def update(self, dt):
        self.time += dt
        self.message_t = max(0.0, self.message_t - dt)
        keys = pygame.key.get_pressed()
        inp = {
            "forward": keys[pygame.K_w], "back": keys[pygame.K_s],
            "left": keys[pygame.K_a], "right": keys[pygame.K_d],
            "run": keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT], "jump": keys[pygame.K_SPACE],
        }
        if self.citymap.open or self.title is not None:  # standing still while reading the map / start screen
            inp = {}
        pl = self.player
        prev = tuple(pl.pos)
        self.banner_t = max(0.0, self.banner_t - dt)
        st = self.env.storm                             # storm gusts push the wingsuit around
        pl.wind = (st * 7.0 * math.sin(self.time * 0.61), st * 7.0 * math.cos(self.time * 0.43)) if st > 0.3 else (0.0, 0.0)
        for strength in self.env.update(dt):            # thunder, a moment after each lightning flash
            self.audio.thunder(strength)
        for poi in self.citymap.visit(pl.pos):
            self.flash(tr("發現新地點：{name}（M 地圖可快速移動）", name=poi.name), 3.5)

        # a car carries whoever stands on its floor
        self.riding = False
        for el in self.all_elevators():
            riding = el.in_footprint(pl.pos) and abs(pl.pos[1] - el.y) < 0.75
            dy = el.update(dt)
            if riding:
                pl.pos[1] += dy
                self.riding = True
        # air taxi: a seated passenger moves and turns with the cabin, no walking physics
        dyaw = self.taxis.update(dt)
        seated = self.taxis.rider is not None
        if seated:
            pl.pos[:] = self.taxis.rider.seat()
            pl.vel[:] = [0.0, 0.0, 0.0]
            pl.yaw += dyaw
        # metro: whoever stands in a car moves (and turns) with it
        self.ride = None if seated else self.trains.locate(pl.pos)
        self.trains.update(dt, pl.pos, self.ride)
        if self.ride is not None:
            new_pos, dyaw = self.trains.carry(self.ride)
            pl.pos[:] = new_pos
            pl.yaw += dyaw

        self.shops.update(pl.pos)
        car = self.car()
        self.interior.update(pl.pos, self.elevators, car, self.shops)       # (only tower cars matter here)
        b = self.interior.building                      # its solid upper floors become a hollow shell
        self.world.disabled = {self.shops.records[b].upper_col} if b is not None else set()
        self.workers.update(dt, self.interior, pl.pos)
        self.crowd.update(dt, pl.pos)
        self.boats.update(dt)
        rides = self.sea.rides
        rides.update(dt)                                # ferries, Ferris wheel, drop tower carry their riders
        self.on_ride = rides.carry(pl) if (self.ride is None and not seated) else None
        self.dyn = ([c for el in self.all_elevators() for c in el.colliders()] + self.shops.colliders
                    + self.ground.colliders_near(pl.pos) + self.peds.colliders_near(pl.pos) + self.interior.colliders
                    + self.workers.colliders_near(pl.pos) + self.trains.colliders_near(pl.pos)
                    + self.taxis.colliders_near(pl.pos) + self.crowd.colliders_near(pl.pos)
                    + rides.colliders_near(pl.pos))
        if self.ride is None and not seated:
            if pl.grounded:                             # moving walkways (mall passage, undercity ring)
                pl.pos[2] += mall.belt_push(pl.pos) * dt
                bx, bz = undercity.belt_push(pl.pos)
                pl.pos[0] += bx * dt
                pl.pos[2] += bz * dt
            pl.update(dt, inp, self.world, self.dyn)
        elif self.ride is not None:     # aboard: walk in the car's own frame, it may be turning on a curve
            self.trains.ride_step(pl, dt, inp, self.ride, self.ride_world)
        if in_water(pl.pos[0], pl.pos[2]) and pl.pos[1] < -0.4:      # fell into the sea: back to the nearest dock
            self.dust.burst(pl.pos[0], pl.pos[2], -1.2)
            spots = [(pl.pos[0], 0.0, C.SHORE_Z - 3.0)] + list(sea.RESCUE)
            spot = min(spots, key=lambda s: math.hypot(s[0] - pl.pos[0], s[2] - pl.pos[2]))
            pl.reset(spot, yaw=pl.yaw)
            self.flash(tr("落水了！被港務人員打撈上岸"), 3.0)
        self._progress_step(dt, prev, seated)
        # what the grapple would hit
        fwd = direction(pl.yaw, pl.pitch)
        if self.underground() and (pl.glide or pl.grapple is not None):     # e.g. dropped down a stairwell
            pl.glide = False
            pl.release_grapple()
            self.flash(tr("地下區域禁止使用翼裝與鉤索"))
        self.aim = None
        if not seated and not self.underground():
            self.aim = self.world.raycast(pl.eye(), fwd, pl.stats["grapple_range"], self.interior.colliders)
            if self.aim is not None and pl.eye()[1] + fwd[1] * self.aim < UNDERGROUND_Y:
                self.aim = None                         # no hooking onto anything below street level
        self.ground.update(dt, self.time, pl.pos)
        self.peds.update(dt, self.time, pl.pos)

        shop = self.shops.current(pl.pos)
        if shop is not None and shop is not self.shop:
            self.welcome_t = 3.0
        self.shop = shop
        self.welcome_t = max(0.0, self.welcome_t - dt)

        for ev in pl.events:
            if ev == "landed":
                self.dust.burst(pl.pos[0], pl.pos[2], pl.support)
        pl.events.clear()

        self.traffic.update(dt)
        fall = max(0.0, -pl.vel[1]) if not self.riding else 0.0
        rush = pl.speed if (pl.glide or pl.grapple is not None) else fall       # wingsuit / grapple speed
        self.speed_fx = max(0.0, min(1.0, (rush - 20.0) / 100.0))
        feet = tuple(pl.pos)
        self.fire.update(dt, pl.thrust, pl.yaw, fall, push=pl.burst_push if pl.burst > 0.0 else None)
        self.smoke.update(dt, pl.thrust, feet, pl.vel)
        self.dust.update(dt, pl.thrust, pl.pos[0], pl.pos[2], pl.support, pl.height_above_ground)

        # camera with shake
        amp = 0.025 * self.speed_fx + 0.05 * min(pl.thrust, 1.5)
        t = self.time
        shake = (amp * (math.sin(t * 37.1) * 0.6 + math.sin(t * 61.7) * 0.4),
                 amp * (math.sin(t * 43.3) * 0.6 + math.sin(t * 71.9) * 0.4),
                 amp * (math.sin(t * 53.9) * 0.6 + math.sin(t * 29.3) * 0.4))
        eye = np.add(pl.eye(), shake)
        if self.prev_eye is not None and dt > 0:
            v = (eye - self.prev_eye) / dt
            self.cam_vel = v if np.linalg.norm(v) < 400.0 else np.zeros(3)
        self.prev_eye = eye
        self.eye = eye
        self.streaks.update(dt, self.cam_vel)

        car = self.car()
        flying = seated and not self.taxis.rider.parked
        self.audio.update(dt, self.speed_fx * 0.9 + (0.25 * abs(car.speed) / C.ELEV_SPEED if car else 0.0),
                          pl.thrust / 1.2, 0.35 if ((car and car.moving) or flying) else self._train_hum())

    def _progress_step(self, dt, prev, seated):
        """Shards, the active mission, menus walking out of reach, the safe spot and autosaves."""
        pl = self.player
        if self.title is not None:
            return
        i = self.pickups.touch(pl.pos, self.progress.shards)
        if i is not None:
            value = self.pickups.items[i][3]
            self.progress.shards.add(i)
            self.progress.earn(value)
            self.progress.save()
            self.flash(tr("+${value} 資料碎片（{n}/{total}）· 信用點 ${credits:,}", value=value,
                          n=len(self.progress.shards), total=len(self.pickups), credits=self.progress.credits), 3.0)
        ev = self.missions.update(dt, pl, prev, self.env, self.progress)
        if ev is not None:
            kind, text, reward = ev
            if kind == "done":
                self.show_banner(tr("任務完成  +${reward:,}", reward=reward), (120, 255, 160), 4.0)
                self.flash(text, 5.0)
            elif kind == "fail":
                self.show_banner(tr("任務失敗"), (255, 90, 90), 3.0)
                self.flash(text, 5.0)
            elif kind == "info":
                self.flash(text, 4.0)
        if self.menu is not None and math.dist(self.menu_at, pl.pos) > 4.0:
            self.menu = None
        steady = (pl.grounded and not seated and self.ride is None and self.on_ride is None and self.car() is None
                  and not pl.glide and pl.grapple is None and math.hypot(pl.vel[0], pl.vel[2]) < 12.0
                  and self.sea.rides.under(pl.pos) is None)
        if steady:
            self.safe = (tuple(pl.pos), pl.yaw)
        self.autosave_t -= dt
        if self.autosave_t <= 0.0:
            if steady and self.missions.active is None:
                self.save_game(auto=True)
                self.autosave_t = AUTOSAVE
            else:
                self.autosave_t = 5.0                   # try again a little later

    def _train_hum(self):
        if self.ride is None:
            return 0.0
        train = self.trains.trains[self.ride[0]]
        return 0.15 + 0.3 * train.v / train.line["speed"]

    def metro_status(self):
        """(prompt, banner) about the metro around the player, or ("", "")."""
        pl = self.player
        if self.ride is not None:
            train = self.trains.trains[self.ride[0]]
            line = train.line
            st = [s for s in self.metro.stations if s.line == train.li][train.next]
            if train.state == "run":
                return tr("{line} 列車行駛中 → 下一站：{st}", line=line['name'], st=st.name), ""
            if train.state in ("opening", "dwell"):
                return (tr("{line}・{st}站到了 — 車門開啟中（{s:.0f} 秒後發車）", line=line['name'], st=st.name,
                           s=max(train.timer, 0)), tr(st.name))
            return tr("{line}・{st}站 — 車門關閉中，請小心", line=line['name'], st=st.name), ""
        for st in self.metro.stations:
            x0, z0, x1, z1 = st.platform
            if x0 < pl.pos[0] < x1 and z0 < pl.pos[2] < z1 and abs(pl.pos[1] - st.yf) < 2.0:
                eta = self.trains.eta(st)
                if eta is None:
                    when = tr("列車即將離站")
                elif eta <= 0.0:
                    when = tr("車門開啟中，請上車")
                elif eta < 12.0:
                    when = tr("列車進站中")
                else:
                    when = tr("下一班約 {s:.0f} 秒", s=eta)
                return tr("{line}・{st}站（{kind}月台）— {when}", line=LINES[st.line]['name'], st=st.name,
                          kind=KIND_LABEL[st.kind], when=when), ""
            ex, ez = st.entrance
            if math.hypot(pl.pos[0] - ex, pl.pos[2] - ez) < 8.0 and abs(pl.pos[1]) < 2.0:
                where = tr("往下走到地下月台") if st.kind == "underground" else tr("爬樓梯上高架月台")
                return tr("{line}・{st}站 入口 — {where}", line=LINES[st.line]['name'], st=st.name, where=where), ""
        return "", ""

    # ---------------------------------------------------------------- HUD
    def hud_state(self):
        pl = self.player
        y = pl.pos[1]
        car = self.car()
        taxi = self.taxis.rider
        roof_t = self.on_roof()
        t = getattr(car, "tower", None) if car is not None else floors.tower_at(pl.pos)   # a megatower
        g = self.interior.layout if self.interior.building is not None else None    # city building
        if taxi is not None:
            floor_label = tr("空中計程車")
        elif mall.area(pl.pos):                          # (the hall lies under Nexus Tower)
            floor_label = "B1 " + tr(mall.area(pl.pos))
        elif undercity.area(pl.pos):
            floor_label = "B2 " + tr(undercity.area(pl.pos))
        elif sea.area(pl.pos):
            floor_label = tr("所在：{where}", where=sea.area(pl.pos))
        elif t is not None:
            k = t.floor_at(y)
            floor_label = t.label(k)
            if 2 <= k <= t.floors and car is None:
                floor_label += f" — {tr(floors.THEMES[floors.theme(k, t)])}"
                if floors.feature(k) is not None and y > CLOUD_Y:
                    floor_label += tr("（雲層上方）")
        elif roof_t is not None and roof_t.contains(pl.pos, -1.0):
            floor_label = roof_t.label(roof_t.roof)
        elif g is not None:
            k = g.floor_at(y)
            floor_label = g.label(k)
            if 2 <= k <= g.floors:
                floor_label += f" — {tr(floors.THEMES[g.theme(k)])}"
        elif y < -0.5:
            floor_label = tr("地下")
        else:
            park = districts.park_at(pl.pos[0], pl.pos[2])
            floor_label = tr("所在：{where}", where=park[0] if park
                             else districts.NAMES[districts.district_at(pl.pos[0], pl.pos[2])])
        self.place = floor_label                        # (for the save summary)
        if g is not None and t is None:
            title, top, top_label = f"{g.name}  ·  {g.floors} F", g.height, f"{g.floors}F"
        else:
            shown = t or roof_t or floors.nearest_tower(pl.pos)
            title, top, top_label = f"{shown.name}  ·  {shown.floors} F", shown.height, f"{shown.floors}F"
        boot_on = pl.boot != BOOT_OFF
        if car is not None:
            vy = car.speed * (1 if car.level_y(car.target) > car.y else -1)
        elif taxi is not None:
            vy = taxi.vel[1]
        else:
            vy = pl.vel[1]
        info = [
            (title, (255, 70, 210)),
            (tr("高度 {y:8.1f} m    {where}", y=y, where=floor_label), (235, 245, 255)),
            (tr("垂直速度 {vy:+7.1f} m/s", vy=vy), (255, 90, 120) if pl.vel[1] < -50 else (235, 245, 255)),
            (tr("火箭靴：{state}   推力 {pct:3d}%", state=BOOT_NAMES[pl.boot], pct=int(pl.thrust * 100)),
             (255, 160, 60) if boot_on else (150, 230, 255)),
            (self._boost_label(), (255, 190, 110) if pl.charges < pl.stats["boost_charges"] else (150, 230, 255)),
            (tr("信用點 ${credits:,}   資料碎片 {n}/{total}", credits=self.progress.credits,
                n=len(self.progress.shards), total=len(self.pickups)), (255, 215, 80)),
            (tr("時間 {t}", t=self.env.label()), (200, 215, 255)),
        ]

        prompt = ""
        landing = self.near_landing()
        stand = self.taxis.stand_near(pl.pos) if taxi is None else None
        local = t.local(pl.pos) if t is not None else None
        in_core = False
        if g is not None and t is None:
            x0, z0, x1, z1 = g.bounds(g.SX0 - 0.3, g.Z1A - 0.3, g.HX1, g.HZ1)
            in_core = x0 < pl.pos[0] < x1 and z0 < pl.pos[2] < z1
        if taxi is not None:
            if taxi.parked:
                prompt = tr("按數字鍵選擇目的地（左下清單） · [E] 下車")
            else:
                prompt = tr("飛往 {name} — 約 {s:.0f} 秒 · Space 跳車", name=taxi.dest.name, s=taxi.eta())
        elif car is not None:
            if car.state == "idle":
                dest = car.label(self.target_floor(car))
                typed = self.floor_input or "—"
                hint = tr(" · 每 100 層有特色樓層") if getattr(car, "tower", None) else ""
                prompt = tr("目的樓層：{typed}（數字鍵 / 滾輪）  [E] 前往 {dest}", typed=typed, dest=dest) + hint
            else:
                view = tr(" — 看看玻璃外的城市") if getattr(car, "tower", None) else ""
                prompt = tr("電梯運行中 → {floor}", floor=car.label(car.target)) + view
        elif landing is not None:
            el, level = landing
            if el.level == level and el.state in ("idle", "opening"):
                prompt = tr("電梯已到達，請進入")
            else:
                prompt = tr("[E] 呼叫電梯到 {floor}（電梯目前在 {at}）", floor=el.label(level),
                            at=el.label(el.floor_number()))
        elif stand is not None:
            here = self.taxis.parked_at(stand)
            prompt = (tr("空中計程車招呼站・{name} — [E] 上車", name=stand.name) if here is not None
                      else tr("空中計程車招呼站・{name} — [E] 呼叫計程車", name=stand.name))
        elif roof_t is not None:
            if self.near_roof_elevator() is roof_t and self.elevators[roof_t.index].level != roof_t.roof:
                prompt = tr("頂樓在大樓外側，無法呼叫電梯——請從黃黑框的樓梯口走下 {n}F", n=roof_t.floors)
            else:
                prompt = tr("{name} {h:.0f} m 頂樓直升機坪 — 沒有圍牆，邊緣直接就是天空（T 換下一棟）",
                            name=roof_t.name, h=roof_t.height)
        elif (local is not None and t.stair_x0 - 0.3 < local[0] < t.stair_hole[2]
              and C.STAIR_Z0 - 0.3 < local[1] < t.stair_hole[3]):
            prompt = tr("樓梯間 {floor} — 往上 / 往下走即可換樓層", floor=t.label(k))
        elif in_core:
            prompt = tr("樓梯間 {floor} — 往上走一路通到屋頂", floor=g.label(g.floor_at(y)))
        elif g is not None and y >= g.height - 0.5:
            prompt = tr("{name} 屋頂（{h:.0f} m）— 黃黑框是樓梯口", name=g.name, h=g.height)
        elif self.missions.terminal_near(pl.pos) is not None:
            term = self.missions.terminal_near(pl.pos)
            prompt = (tr("任務終端・{name} — [E] 查看任務", name=term.name) if self.menu is None
                      else tr("數字鍵接任務 · E 關閉"))
        elif self.shop is not None:
            if self.shops.clerk_near(pl.pos) and self.shop.kind == CLINIC:
                prompt = (tr("[E] {name} — 升級義體（信用點 ${credits:,}）", name=self.shop.name,
                             credits=self.progress.credits) if self.menu is None
                          else tr("數字鍵購買升級 · E 關閉"))
            elif self.shops.clerk_near(pl.pos):
                prompt = tr("[E] 跟「{name}」的店員說話", name=self.shop.name)
            else:
                prompt = tr("「{name}」營業中 — 櫃台後方的員工門通往樓上", name=self.shop.name)
        elif mall.belt_push(pl.pos):
            prompt = tr("電動步道 — 地下街通往 NEXUS 地下商場與霓虹市集站")
        elif any(undercity.belt_push(pl.pos)):
            prompt = tr("電動步道 — 地下城環道連接地心線四站")
        elif self.talker_near(pl.pos) is not None:
            prompt = tr("[E] 跟{name}說話", name=self.talker_near(pl.pos)[3])
        elif self.sea.rides.ferry_near(pl.pos) is not None:
            prompt = self.sea.rides.ferry_near(pl.pos).status()
        elif self.on_ride is self.sea.rides.tower:
            prompt = tr("自由落體塔 — 抓緊！")
        elif self.on_ride is not None:
            prompt = tr("摩天輪 — 轉一圈約兩分半，看看整座城")
        metro_prompt, metro_banner = self.metro_status()
        if metro_prompt and not prompt:
            prompt = metro_prompt
        if self.message_t > 0:
            prompt = self.message

        banner, bcolor = "", (255, 255, 255)
        if self.banner_t > 0.0:
            banner, bcolor = self.banner_msg, self.banner_col
        elif pl.glide:
            hs = math.hypot(pl.vel[0], pl.vel[2])
            banner, bcolor = tr("翼裝滑翔  {kmh:.0f} km/h   {vy:+.1f} m/s", kmh=hs * 3.6, vy=pl.vel[1]), (120, 230, 255)
        elif pl.grapple is not None:
            banner, bcolor = tr("鉤索收線中  {v:.0f} m/s", v=pl.speed), (255, 220, 90)
        elif pl.boot == BOOT_BRAKING:
            banner, bcolor = tr("火箭靴點火！減速中"), (255, 140, 40)
        elif pl.boot == BOOT_HOVER:
            banner, bcolor = tr("緩降中…  離地 {h:4.1f} m", h=pl.height_above_ground), (255, 190, 90)
        elif pl.boot == BOOT_LANDED:
            banner, bcolor = tr("安全著陸"), (120, 255, 200)
        elif -pl.vel[1] > 25 and not self.riding:
            banner, bcolor = tr("自由落體  {v:.0f} m/s", v=-pl.vel[1]), (255, 80, 140)
        elif car is not None and car.moving:
            banner, bcolor = car.label(car.floor_number()), (90, 230, 255)
        elif self.shop is not None and self.welcome_t > 0:
            banner, bcolor = tr("歡迎光臨  {name}", name=self.shop.name), (255, 230, 120)
        elif metro_banner:
            banner, bcolor = metro_banner, (120, 240, 255)

        debug = []
        if self.debug:
            p = pl.pos
            debug = [f"FPS {self.fps:5.1f}", f"pos {p[0]:8.1f} {p[1]:8.1f} {p[2]:8.1f}",
                     f"ground {pl.support:6.1f}  h {pl.height_above_ground:7.1f}",
                     "elevators " + "  ".join(f"{e.state}/{e.level}F/{e.y:.0f}m" for e in self.elevators),
                     f"interior {self.interior.layout.name if self.interior.layout else '-'} "
                     f"floor={self.interior.floor} boxes={len(self.interior.boxes)} "
                     f"colliders={len(self.interior.colliders)} workers={self.workers.count}",
                     "taxis " + " ".join(("P" if tx.parked else "F") + str(tx.stand.index if tx.parked else tx.dest.index)
                                         for tx in self.taxis.taxis),
                     "trains " + "  ".join(f"{t.line['name']}:{t.state}/{t.v:.0f}m/s" for t in self.trains.trains),
                     f"cars {self.ground.count}  stopped {int((self.ground.v < 0.5).sum())}  "
                     f"shops furnished {len(self.shops.active)}",
                     f"pedestrians {self.peds.n}  waiting {int((self.peds.state == 2).sum())}  "
                     f"crossing {int((self.peds.state == 3).sum())}",
                     f"particles fire {int(self.fire.pool.alive.sum())} smoke {int(self.smoke.pool.alive.sum())} "
                     f"dust {int(self.dust.pool.alive.sum())}"]
        if taxi is not None:                    # the help panel lists the taxi stands
            panel = [tr("空中計程車 — 目的地")] + [f"{i + 1}   {tr(s.name)}" + (tr("（這裡）") if s is taxi.stand else "")
                                             for i, s in enumerate(self.taxis.stands)]
        elif self.menu is not None:
            panel = self.menu_lines()
        else:
            panel = [tr(line) for line in HELP] if self.show_help else []
        aim = "" if taxi is not None else (f"{self.aim:.0f} m" if self.aim is not None else "—")
        return info, y / top, top_label, prompt, banner, bcolor, panel, debug, aim

    def _boost_label(self):
        pl = self.player
        top = pl.stats["boost_charges"]
        wait = tr("   回復 {s:.1f} s", s=pl.recharge) if pl.charges < top else ""
        return tr("噴射 {n}/{top}（Q 二段跳 / Ctrl 衝刺）", n=pl.charges, top=top) + wait

    # ---------------------------------------------------------------- draw
    def draw(self, dt):
        pl, els = self.player, self.all_elevators()
        r = self.renderer
        el_boxes = np.array([b for el in els for b in el.instances()], "f4").reshape(-1, 10)
        dyn_boxes = np.concatenate([el_boxes, self.shops.boxes, self.boats.instances(),
                                    self.sea.rides.instances(self.eye)])
        cars = np.concatenate([self.traffic.data, self.ground.data])
        quads = np.concatenate([np.array([q for el in els for q in el.gauge_quads()], "f4").reshape(-1, 13),
                                self.shops.quads])
        dyn_boxes = np.concatenate([dyn_boxes, self.interior.boxes,
                                    self.pickups.instances(self.eye, self.progress.shards, self.time),
                                    self.missions.instances(self.eye, self.time)])
        people = np.concatenate([self.peds.instances(self.eye), self.workers.instances(),
                                 self.crowd.instances(self.eye)])
        glass = [q for el in els for q in el.glass_quads()] + self.taxis.glass_quads(self.eye)
        rot = np.concatenate([self.trains.instances(self.eye), self.taxis.instances(self.eye)])
        r.set_dynamic(dyn_boxes, cars, quads, glass, people, rot)
        puffs = np.concatenate([self.smoke.render_data(), self.dust.render_data()])
        lines = self.streaks.render_data(self.eye, self.cam_vel, self._wind_amount(), pl.thrust,
                                         [el.car_bounds() for el in els] + self.taxis.dry_boxes(), self.shops.footprints,
                                         self.dry + self.interior.dry_boxes()
                                         + list(self.trains.car_boxes_near(self.eye)),
                                         rain_amount=self.env.rain, cloud_y=CLOUD_Y)
        if pl.grapple is not None:                      # the grapple line, from the hand to the anchor
            fx, fz = math.sin(pl.yaw), -math.cos(pl.yaw)          # forward; right is (-fz, fx)
            hand = (pl.pos[0] + fx * 0.3 - fz * 0.3, pl.pos[1] + 1.2, pl.pos[2] + fz * 0.3 + fx * 0.3)
            rope = np.array([[*hand, 1.0, 0.85, 0.3, 0.9], [*pl.grapple, 1.0, 0.85, 0.3, 0.9]], "f4")
            lines = np.concatenate([lines, rope])
        r.set_particles(self.fire.render_data(tuple(pl.pos)), puffs, lines)

        self.hud_timer -= dt
        if self.citymap.open:                           # the map is redrawn every frame (dragging)
            state = self.hud_state()
            hues = [line["hue"] for line in LINES]
            mouse = pygame.mouse.get_pos()
            marks = self.missions.map_marks()
            shards = (len(self.progress.shards), len(self.pickups))
            self.hud.update(*state, map_view=lambda surf, fonts, scale: self.citymap.draw(
                surf, fonts, scale, pl, self.taxis.taxis, hues, mouse, marks, shards))
            self.hud_timer = 0.0
        elif self.hud_timer <= 0.0:
            self.hud_timer = 0.1
            self.hud.update(*self.hud_state(), mission=self.missions.hud(pl),
                            title=self.title_lines() if self.title is not None else None)

        boot = (pl.pos[0], pl.pos[1] - 0.6, pl.pos[2], pl.thrust * (0.85 + 0.15 * random.random()))
        fwd = direction(pl.yaw, pl.pitch)
        fov = C.FOV + C.FOV_FALL_BONUS * self.speed_fx
        r.render(self.eye, fwd, fov, self.time, boot, self.speed_fx, pl.thrust, self.hud.tex,
                 tower_open=self.interior.open_range, tower_open_c=self.interior.open_center,
                 bldg=self.interior.bldg, bldg_hatch=self.interior.hatch, bldg_doors=self.interior.doors,
                 env=self.env.uniforms())

    def _wind_amount(self):
        s = float(np.linalg.norm(self.cam_vel))
        t = max(0.0, min(1.0, (s - 18.0) / 72.0))
        return t * t * (3 - 2 * t)

    def run(self):
        clock = pygame.time.Clock()
        running = True
        while running:
            dt = min(clock.tick(240) / 1000.0, 0.05)
            self.fps = clock.get_fps()
            running = self.handle_events()
            self.update(dt)
            self.draw(dt)
            pygame.display.flip()
        if self.title is None:                          # (quitting from the start screen keeps the save as is)
            self.save_game(auto=True)
        pygame.quit()


def main():
    ap = argparse.ArgumentParser(description="Neon City — cyberpunk megatower walk")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--msaa", type=int, default=4, help="0 disables multisampling")
    ap.add_argument("--seed", type=int, default=2077)
    ap.add_argument("--lang", choices=i18n.LANGS, help="game language: zh (中文) or en (English); F7 switches in game")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--continue", dest="start", action="store_const", const="continue",
                   help="continue the saved game without the start screen")
    g.add_argument("--new", dest="start", action="store_const", const="new",
                   help="start over (the old save is kept as savegame.bak.json)")
    ap.set_defaults(start="ask")
    Game(ap.parse_args()).run()


if __name__ == "__main__":
    main()
