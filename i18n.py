"""Game language: 中文 (the source text) or English.

The Chinese text in the code is the key: tr("已移動到 {name}", name=poi.name) looks the template up in
EN when the language is English, then formats it. String arguments that are known names (districts,
stations, shops ...) are translated too, so data tables keep their Chinese names. Names built once
at startup (map places, taxi stands, buildings, mission offers) are L objects, which render in the
language current at the time they are shown.
"""

LANGS = ("zh", "en")
LANG_NAMES = {"zh": "中文", "en": "English"}
LANG = "zh"


def set_lang(code):
    global LANG
    if code in LANGS:
        LANG = code
    return LANG


def toggle():
    return set_lang(LANGS[(LANGS.index(LANG) + 1) % len(LANGS)])


def _arg(v):
    if isinstance(v, L):
        return str(v)
    if LANG == "en" and isinstance(v, str):
        return EN.get(v, v)
    return v


def tr(s, /, **kw):
    """s (a Chinese template, or an L) in the current language, formatted with kw."""
    if isinstance(s, L):
        return str(s)
    t = EN.get(s, s) if LANG == "en" else s
    if not kw:
        return t
    return t.format(**{k: _arg(v) for k, v in kw.items()})


class L:
    """A display name from a template, rendered in the current language each time it is shown."""
    __slots__ = ("template", "kw")

    def __init__(self, template, /, **kw):
        self.template, self.kw = template, kw

    def __str__(self):
        return tr(self.template, **self.kw)

    def __format__(self, spec):
        return format(str(self), spec)

    def __repr__(self):
        return f"L({self.template!r}, {self.kw!r})"


EN = {
    # ------------------------------------------------------------------ help panel (F1)
    "WASD 移動 · 滑鼠 轉視角 · Shift 奔跑 · Space 跳躍（空中再按 Space：展開 / 收起翼裝）":
        "WASD move · Mouse look · Shift run · Space jump (Space again in the air: open / fold the wingsuit)",
    "Q 二段跳 · 左 Ctrl 噴射衝刺（翼裝中衝刺加速）— 共用噴射次數，用完要等冷卻":
        "Q double jump · Left Ctrl boost dash (speeds up the wingsuit) — both use boost charges, which recharge",
    "F 或右鍵：發射鉤索（準心出現黃圈時可勾住），再按一次放開；地下車站與地下商場禁用翼裝和鉤索":
        "F / right mouse: grapple (hooks when the crosshair shows a yellow ring), again to let go; "
        "no wingsuit or grapple underground",
    "任務：走到地圖上的任務終端按 E 接任務（送貨、天氣急件、翼裝穿圈賽、屋頂跑酷），J 放棄":
        "Missions: press E at a mission terminal (delivery, weather express, wingsuit ring race, rooftop parkour), "
        "J to abandon",
    "資料碎片：城市各處發光的碎片，撿到換信用點；CHROME 義體診所對店員按 E 升級義體":
        "Data shards: glowing shards around the city are worth credits; press E at a CHROME clinic clerk to upgrade",
    "E 搭乘 / 呼叫電梯、計程車、跟店員說話 · T 傳送到最近的頂樓（在頂樓再按 T 換下一棟）· R 回到起點":
        "E ride / call elevators and taxis, talk to clerks · T teleport to the nearest roof (again: next tower) "
        "· R back to start",
    "電梯內：數字鍵輸入樓層（滾輪 ±1，Shift ±10），E / Enter 出發；60 m 以上的建築櫃台後方也有電梯":
        "In an elevator: type a floor (wheel ±1, Shift ±10), E / Enter to go; buildings over 60 m have one "
        "behind the counter",
    "每棟建築一樓都是商店，櫃台後方的員工門通往樓梯與電梯；有些高樓之間有空中天橋":
        "Every building has a shop on 1F; the staff door behind the counter leads to the stairs and elevator; "
        "skybridges link some towers",
    "地鐵：地心線（地下）、天際線（高架外環）、三塔線（NEXUS → HELIX → 霓虹公園 → AURORA）":
        "Metro: Core Line (underground), Skyline (elevated outer loop), Three Towers Line "
        "(NEXUS → HELIX → Neon Park → AURORA)",
    "地下商場：霓虹市集站月台旁的地下街（電動步道）直通 NEXUS 大廳地下":
        "Underground mall: the underground street (moving walkway) by the Neon Market platform leads under "
        "the NEXUS lobby",
    "B2 地下城：地心線四站月台旁的通道往下走，環道上有黑市、停車場、美食街、電玩街":
        "B2 Undercity: passages beside the four Core Line platforms lead down to a ring with a black market, "
        "parking, food court and arcade",
    "渡輪：港灣主碼頭 → 霓虹島 → 海上遊樂園（摩天輪、自由落體塔可以搭）· 大樓每 100 層有特色樓層":
        "Ferry: main harbor pier → Neon Island → Sea Amusement Park (Ferris wheel, drop tower) "
        "· towers have a feature floor every 100 floors",
    "空中計程車：頂樓、廣場、公園、港灣碼頭、企業特區停機坪；車內按數字（0 = 第 10 站），Space 跳車":
        "Air taxis: roofs, plazas, parks, harbor pier, corporate helipad; in the cab press a number "
        "(0 = 10th stand), Space to bail out",
    "城區：市中心、企業特區（東北）、霓虹夜市（西北）、住宅區（東南）、鏽蝕區（西南）、港灣（南岸 z~1180）":
        "Districts: Downtown, Corporate (NE), Neon Night Market (NW), Residential (SE), Rust District (SW), "
        "Harbor (south shore, z~1180)",
    "M 城市地圖：去過的地點可直接點擊快速移動（解鎖進度自動存檔）":
        "M city map: click a place you have visited to fast travel (unlocks are saved automatically)",
    "F5 切換天氣（自動／晴／多雲／雨／暴雨／霧）· F6 時間流速（正常／快轉／暫停）· [ ] 調整時間 ±1 小時":
        "F5 weather (auto / clear / cloudy / rain / storm / fog) · F6 time speed (normal / fast / paused) "
        "· [ ] time ±1 hour",
    "F8 存檔（離開時與每 2 分鐘也會自動存檔）· Tab 釋放滑鼠 · F1 顯示/隱藏說明 · F3 除錯資訊 · Esc 離開":
        "F8 save (also autosaves on quit and every 2 minutes) · Tab release mouse · F1 show / hide help "
        "· F3 debug · Esc quit",
    "F7 切換語言（中文 / English）": "F7 switch language (中文 / English)",

    # ------------------------------------------------------------------ save, start screen, language
    "已存檔 {t}": "Saved {t}",
    "存檔失敗（無法寫入 savegame.json）": "Save failed (cannot write savegame.json)",
    "存檔：{when} · {place}": "Saved: {when} · {place}",
    "（時間不明）": "(unknown time)",
    "信用點 ${credits:,} · 資料碎片 {shards}/{total} · 已解鎖地點 {found}/{places}":
        "Credits ${credits:,} · Data shards {shards}/{total} · Places unlocked {found}/{places}",
    "[1] 繼續遊戲（讀取存檔）": "[1] Continue (load the save)",
    "[2] 新遊戲（重置進度，舊檔備份為 savegame.bak.json）": "[2] New game (resets progress; the old save is kept as savegame.bak.json)",
    "!再按一次 2 確認重置 — 進度會從頭開始": "!Press 2 again to confirm — progress starts over",
    "Esc 離開": "Esc Quit",
    "已讀取存檔，歡迎回來": "Save loaded — welcome back",
    "新遊戲開始！舊存檔已備份為 savegame.bak.json": "New game! The old save was backed up as savegame.bak.json",
    "語言：中文": "Language: English",

    # ------------------------------------------------------------------ clinic upgrades
    "{shop} — 義體升級        信用點 ${credits:,}": "{shop} — Cyberware upgrades        Credits ${credits:,}",
    "Lv{lv}（已滿級）": "Lv{lv} (max)",
    "數字鍵購買 · E / Esc 離開 · 撿資料碎片、做任務賺信用點":
        "Number keys to buy · E / Esc to leave · Earn credits with data shards and missions",
    "義體升級完成": "Upgrade installed",
    "{name} 已經升到最高級": "{name}: already at the max level",
    "信用點不足：{name} Lv{lv} 要 ${price:,}（目前 ${credits:,}）":
        "Not enough credits: {name} Lv{lv} costs ${price:,} (you have ${credits:,})",
    "{name} 升級到 Lv{lv}！（-${price:,}）": "{name} upgraded to Lv{lv}! (-${price:,})",
    "翼裝": "Wingsuit",
    "鉤索": "Grapple",
    "跑速": "Run speed",
    "火箭靴": "Rocket boots",
    "最高速、滑翔距離、最低展開高度": "top speed, glide distance, minimum deploy height",
    "射程、收線速度": "range, reel speed",
    "奔跑速度": "running speed",
    "噴射次數、冷卻、衝刺與二段跳力道": "boost charges, cooldown, dash and double jump power",
    "最高速": "Top speed",
    "下沉": "Sink",
    "展開高度": "Deploy height",
    "射程": "Range",
    "收線": "Reel",
    "奔跑": "Run",
    "噴射": "Charges",
    "次": "",
    "冷卻": "Cooldown",
    "衝刺": "Dash",
    "二段跳": "Double jump",

    # ------------------------------------------------------------------ actions
    "任務進行中不能{what}（J 放棄任務）": "Can't {what} during a mission (J to abandon)",
    "傳送": "teleport",
    "快速移動": "fast travel",
    "回到起點": "return to the start",
    "地下區域禁止使用鉤索": "No grapple underground",
    "這裡不能用鉤索": "The grapple can't be used here",
    "鉤索射程 {r:.0f} m 內沒有可勾住的東西": "Nothing to hook within the grapple's {r:.0f} m range",
    "地下區域禁止使用翼裝": "No wingsuit underground",
    "翼裝展開！往下看加速、往上看拉升": "Wingsuit out! Look down to speed up, look up to pull up",
    "太低了，展不開翼裝（Q 二段跳可以再往上）": "Too low to open the wingsuit (Q double jump gains height)",
    "二段跳要在空中用 — 先按 Space 跳起來": "Double jump works in the air — press Space to jump first",
    "噴射次數用完了，{s:.1f} 秒後回復一次": "Out of boost charges — the next one is back in {s:.1f} s",
    "二段跳！": "Double jump!",
    "噴射衝刺！": "Boost dash!",
    "已傳送到 {name} 頂樓直升機坪（{h:.0f} m）": "Teleported to the {name} rooftop helipad ({h:.0f} m)",
    "飛行中… 按 Space 可以跳車": "In flight… press Space to bail out",
    "已經在 {name}": "Already at {name}",
    "起飛！前往 {name}，約 {s:.0f} 秒": "Taking off! To {name}, about {s:.0f} s",
    "已下車：{name}": "Got out: {name}",
    "電梯運行中…": "The elevator is moving…",
    "關門中，前往 {floor}…": "Doors closing, going to {floor}…",
    "電梯已在此樓層，請進入": "The elevator is on this floor — step in",
    "已呼叫電梯到 {floor}，請稍候…": "Elevator called to {floor}, please wait…",
    "電梯運行中，請稍候…": "The elevator is busy, please wait…",
    "上車了——按數字鍵選擇目的地": "Aboard — press a number key to pick a destination",
    "已呼叫 {name} 的計程車，約 {s:.0f} 秒後抵達": "Taxi called to {name}, arriving in about {s:.0f} s",
    "計程車就在這裡": "The taxi is right here",
    "頂樓在大樓外側，無法呼叫電梯——請從樓梯口走下 {n}F":
        "The elevator can't be called up here — take the stairwell down to {n}F",
    "店員：「{line}」": "Clerk: \"{line}\"",
    "{who}：「{line}」": "{who}: \"{line}\"",
    "「{name}」尚未造訪 — 先去一次才能快速移動": "\"{name}\" not visited yet — go there once to unlock fast travel",
    "已移動到 {name}": "Moved to {name}",
    "目前沒有進行中的任務": "No active mission",
    "跳車！空中按 Space 展開翼裝": "Bailed out! Press Space in the air to open the wingsuit",
    "天氣：{w}": "Weather: {w}",
    "時間流速：{s}": "Time speed: {s}",
    "時間：{t}": "Time: {t}",
    "發現新地點：{name}（M 地圖可快速移動）": "New place found: {name} (fast travel from the M map)",
    "落水了！被港務人員打撈上岸": "Splash! The harbor crew fished you out",
    "地下區域禁止使用翼裝與鉤索": "No wingsuit or grapple underground",
    "+${value} 資料碎片（{n}/{total}）· 信用點 ${credits:,}": "+${value} data shard ({n}/{total}) · Credits ${credits:,}",
    "任務完成  +${reward:,}": "Mission complete  +${reward:,}",
    "任務失敗": "Mission failed",

    # ------------------------------------------------------------------ metro
    "{line} 列車行駛中 → 下一站：{st}": "{line} train running → next stop: {st}",
    "{line}・{st}站到了 — 車門開啟中（{s:.0f} 秒後發車）": "{line} · {st} Station — doors open (departs in {s:.0f} s)",
    "{line}・{st}站 — 車門關閉中，請小心": "{line} · {st} Station — doors closing, stand clear",
    "列車即將離站": "the train is leaving",
    "車門開啟中，請上車": "doors open, step aboard",
    "列車進站中": "the train is arriving",
    "下一班約 {s:.0f} 秒": "next train in about {s:.0f} s",
    "{line}・{st}站（{kind}月台）— {when}": "{line} · {st} Station ({kind} platform) — {when}",
    "往下走到地下月台": "walk down to the underground platform",
    "爬樓梯上高架月台": "climb the stairs to the elevated platform",
    "{line}・{st}站 入口 — {where}": "{line} · {st} Station entrance — {where}",
    "{line}・{st}站": "{line} · {st} Station",
    "地下": "Underground",
    "高架": "Elevated",
    "地心線": "Core Line",
    "天際線": "Skyline",
    "三塔線": "Three Towers Line",
    "霓虹市集": "Neon Market",
    "零號碼頭": "Pier Zero",
    "鏽蝕街": "Rust Street",
    "量子廣場": "Quantum Square",
    "雲端廣場": "Cloud Square",
    "浮光橋": "Floating Light Bridge",
    "天秤塔": "Libra Tower",
    "極光台": "Aurora Terrace",
    "NEXUS 塔前": "NEXUS Tower Gate",
    "HELIX 螺旋塔": "HELIX Spire",
    "AURORA 極光塔": "AURORA Tower",

    # ------------------------------------------------------------------ HUD status panel
    "空中計程車": "Air taxi",
    "所在：{where}": "Area: {where}",
    "（雲層上方）": " (above the clouds)",
    "高度 {y:8.1f} m    {where}": "Altitude {y:8.1f} m    {where}",
    "垂直速度 {vy:+7.1f} m/s": "Vertical speed {vy:+7.1f} m/s",
    "火箭靴：{state}   推力 {pct:3d}%": "Rocket boots: {state}   Thrust {pct:3d}%",
    "信用點 ${credits:,}   資料碎片 {n}/{total}": "Credits ${credits:,}   Data shards {n}/{total}",
    "時間 {t}": "Time {t}",
    "   回復 {s:.1f} s": "   recharge {s:.1f} s",
    "噴射 {n}/{top}（Q 二段跳 / Ctrl 衝刺）": "Boost {n}/{top} (Q double jump / Ctrl dash)",
    "待命": "Standby",
    "噴射煞車": "Retro-braking",
    "緩降中": "Hovering",
    "著陸": "Landed",
    "{h:02d}:{m:02d}  {kind}（{mode}）": "{h:02d}:{m:02d}  {kind} ({mode})",
    "晴": "Clear",
    "多雲": "Cloudy",
    "雨": "Rain",
    "暴雨": "Storm",
    "霧": "Fog",
    "自動": "auto",
    "手動": "manual",
    "正常": "Normal",
    "快轉": "Fast",
    "暫停": "Paused",

    # ------------------------------------------------------------------ prompts
    "按數字鍵選擇目的地（左下清單） · [E] 下車": "Press a number key to pick a destination (list at lower left) · [E] Get out",
    "飛往 {name} — 約 {s:.0f} 秒 · Space 跳車": "Flying to {name} — about {s:.0f} s · Space to bail out",
    " · 每 100 層有特色樓層": " · a feature floor every 100 floors",
    "目的樓層：{typed}（數字鍵 / 滾輪）  [E] 前往 {dest}": "Floor: {typed} (number keys / wheel)  [E] Go to {dest}",
    " — 看看玻璃外的城市": " — enjoy the view through the glass",
    "電梯運行中 → {floor}": "Elevator moving → {floor}",
    "電梯已到達，請進入": "The elevator has arrived — step in",
    "[E] 呼叫電梯到 {floor}（電梯目前在 {at}）": "[E] Call the elevator to {floor} (it is at {at})",
    "空中計程車招呼站・{name} — [E] 上車": "Air taxi stand · {name} — [E] Board",
    "空中計程車招呼站・{name} — [E] 呼叫計程車": "Air taxi stand · {name} — [E] Call a taxi",
    "頂樓在大樓外側，無法呼叫電梯——請從黃黑框的樓梯口走下 {n}F":
        "The elevator can't be called up here — take the yellow-black stairwell down to {n}F",
    "{name} {h:.0f} m 頂樓直升機坪 — 沒有圍牆，邊緣直接就是天空（T 換下一棟）":
        "{name} {h:.0f} m rooftop helipad — no railing, the edge drops straight into the sky (T: next tower)",
    "樓梯間 {floor} — 往上 / 往下走即可換樓層": "Stairwell {floor} — walk up / down to change floors",
    "樓梯間 {floor} — 往上走一路通到屋頂": "Stairwell {floor} — it goes all the way up to the roof",
    "{name} 屋頂（{h:.0f} m）— 黃黑框是樓梯口": "{name} roof ({h:.0f} m) — the yellow-black frame is the stairwell",
    "任務終端・{name} — [E] 查看任務": "Mission terminal · {name} — [E] View missions",
    "數字鍵接任務 · E 關閉": "Number keys to take a mission · E to close",
    "[E] {name} — 升級義體（信用點 ${credits:,}）": "[E] {name} — Upgrade cyberware (Credits ${credits:,})",
    "數字鍵購買升級 · E 關閉": "Number keys to buy upgrades · E to close",
    "[E] 跟「{name}」的店員說話": "[E] Talk to the clerk at {name}",
    "「{name}」營業中 — 櫃台後方的員工門通往樓上": "{name} is open — the staff door behind the counter leads upstairs",
    "電動步道 — 地下街通往 NEXUS 地下商場與霓虹市集站":
        "Moving walkway — the underground street links the NEXUS Underground Mall and Neon Market Station",
    "電動步道 — 地下城環道連接地心線四站": "Moving walkway — the undercity ring links the four Core Line stations",
    "[E] 跟{name}說話": "[E] Talk to {name}",
    "自由落體塔 — 抓緊！": "Drop tower — hold on!",
    "摩天輪 — 轉一圈約兩分半，看看整座城": "Ferris wheel — one turn takes two and a half minutes; take in the whole city",
    "渡輪停靠中 → {dest}（{s:.0f} 秒後開船）": "Ferry docked → {dest} (leaves in {s:.0f} s)",
    "渡輪航行中 → {dest}": "Ferry under way → {dest}",

    # ------------------------------------------------------------------ banners
    "翼裝滑翔  {kmh:.0f} km/h   {vy:+.1f} m/s": "Wingsuit  {kmh:.0f} km/h   {vy:+.1f} m/s",
    "鉤索收線中  {v:.0f} m/s": "Reeling in  {v:.0f} m/s",
    "火箭靴點火！減速中": "Rocket boots firing! Braking",
    "緩降中…  離地 {h:4.1f} m": "Hovering down…  {h:4.1f} m above ground",
    "安全著陸": "Safe landing",
    "自由落體  {v:.0f} m/s": "Free fall  {v:.0f} m/s",
    "歡迎光臨  {name}": "Welcome to  {name}",
    "空中計程車 — 目的地": "Air taxi — destinations",
    "（這裡）": " (here)",

    # ------------------------------------------------------------------ floors and buildings
    "1F 大廳": "1F Lobby",
    "RF 頂樓": "RF Roof",
    "1F 商店": "1F Shop",
    "RF 屋頂": "RF Roof",
    "{district}大樓 #{n:03d}": "{district} Building #{n:03d}",
    "{name} 頂樓": "{name} Roof",
    "辦公室": "Offices",
    "伺服器農場": "Server Farm",
    "水耕農場": "Hydroponic Farm",
    "交誼酒廊": "Lounge",
    "施工中": "Under Construction",
    "公寓": "Apartments",
    "觀景台": "Observatory",
    "空中花園": "Sky Garden",
    "高空酒吧": "Sky Bar",

    # ------------------------------------------------------------------ places
    "市中心": "Downtown",
    "企業特區": "Corporate District",
    "霓虹夜市": "Neon Night Market",
    "住宅區": "Residential",
    "鏽蝕區": "Rust District",
    "港灣區": "Harbor District",
    "霓虹公園": "Neon Park",
    "星塵公園": "Stardust Park",
    "零點廣場": "Zero Point Plaza",
    "回聲廣場": "Echo Plaza",
    "NEXUS 廣場": "NEXUS Plaza",
    "NEXUS 廣場（起點）": "NEXUS Plaza (start)",
    "企業特區 停機坪": "Corporate District Helipad",
    "港灣碼頭": "Harbor Pier",
    "港灣步道": "Harbor Promenade",
    "燈塔碼頭": "Lighthouse Pier",
    "貨櫃碼頭": "Container Docks",
    "NEXUS 地下商場": "NEXUS Underground Mall",
    "地下街": "Underground Street",
    "地下商場": "Underground Mall",
    "渡輪碼頭（往霓虹島）": "Ferry Pier (to Neon Island)",
    "霓虹島": "Neon Island",
    "海上遊樂園": "Sea Amusement Park",
    "地下城・{name}": "Undercity · {name}",
    "地下城環道": "Undercity Ring",
    "地下城連通道": "Undercity Passage",
    "暗巷黑市": "Back-Alley Black Market",
    "地下停車場": "Underground Parking",
    "地下美食街": "Underground Food Court",
    "地下電玩街": "Underground Arcade",
    "B2 暗巷黑市": "B2 Back-Alley Black Market",
    "任務終端・{name}": "Mission terminal · {name}",
    "{name} 大廳入口": "{name} lobby entrance",
    "計程車・{name}": "Taxi · {name}",
    "{name} {k}F {theme}": "{name} {k}F {theme}",

    # ------------------------------------------------------------------ city map
    "起點廣場": "Start plaza",
    "摩天樓": "Megatowers",
    "地鐵站": "Metro stations",
    "計程車招呼站": "Taxi stands",
    "公園／廣場": "Parks / plazas",
    "港灣": "Harbor",
    "B2 地下城": "B2 Undercity",
    "海上": "At sea",
    "大樓特色樓層": "Feature floors",
    "任務終端": "Mission terminals",
    "點擊快速移動": "Click to fast travel",
    "尚未造訪 — 先去一次才能快速移動": "Not visited yet — go there once to unlock fast travel",
    "城市地圖": "City Map",
    "渡輪航線": "Ferry route",
    "地心線（地下）": "Core Line (underground)",
    "已解鎖 {found}/{total} 個地點": "{found}/{total} places unlocked",
    "資料碎片 {n}/{total}": "Data shards {n}/{total}",
    "◎ 任務目標": "◎ Mission target",
    "滾輪 縮放（{zoom:.0f}×）· 拖曳 平移 · 點擊地點 快速移動 · M / Esc 關閉":
        "Wheel zoom ({zoom:.0f}×) · Drag to pan · Click a place to fast travel · M / Esc to close",

    # ------------------------------------------------------------------ shops and people
    "{shop} #{n:03d}": "{shop} #{n:03d}",
    "NEON MART 便利商店": "NEON MART Convenience Store",
    "電脳拉麵": "Cyber Ramen",
    "CHROME 義體診所": "CHROME Cyberware Clinic",
    "GIGA 電子": "GIGA Electronics",
    "歡迎光臨！合成飯糰今天買一送一。": "Welcome! Synthetic rice balls are buy one, get one free today.",
    "來碗豚骨拉麵嗎？叉燒是實驗室培養的，很新鮮。": "Tonkotsu ramen? The chashu is lab-grown and very fresh.",
    "想換條新手臂？保固三年，保證不含病毒。": "Need a new arm? Three-year warranty, guaranteed virus-free.",
    "來杯霓虹琴通寧？今晚的 DJ 是 AI。": "A neon gin and tonic? Tonight's DJ is an AI.",
    "最新神經介面晶片，插上就能下載功夫。": "The latest neural interface chip — plug it in and download kung fu.",
    "一杯拿鐵，三倍咖啡因，加一點量子奶泡。": "One latte, triple caffeine, with a little quantum foam.",
    "黑市攤販": "Black-market dealer",
    "義體零件，不問來源。要的話現金交易。": "Cyberware parts, no questions asked. Cash only.",
    "假身分晶片，今天打八折，掃描器保證看不出來。": "Fake ID chips, 20% off today. Scanners will never tell.",
    "這把電子鎖破解器能開任何門……大概。": "This lock cracker opens any door… probably.",
    "噓——巡邏無人機剛過去，快選。": "Shh — a patrol drone just passed. Pick quickly.",
    "上一手主人？別問。保固是不可能有的。": "The previous owner? Don't ask. There's no warranty.",
    "電玩街店長": "Arcade manager",
    "投幣機台全部免費試玩，破關紀錄會貼在霓虹牆上！": "Every cabinet is free to play — high scores go up on the neon wall!",
    "海景餐廳": "Seaview Restaurant",
    "今天的炭烤合成龍蝦配霓虹海鹽，不吃可惜。": "Today's grilled synth-lobster with neon sea salt — don't miss it.",
    "射氣球": "Balloon Shooting",
    "套圈圈": "Ring Toss",
    "抓娃娃": "Claw Machine",
    "霓虹棉花糖": "Neon Cotton Candy",
    "全像算命": "Hologram Fortunes",
    "電子彈珠": "Electro Pinball",
    "射中三個霓虹氣球，送你一隻全像貓！": "Pop three neon balloons and win a hologram cat!",
    "摩天輪轉一圈兩分半，頂上看得到整座城。": "The Ferris wheel takes two and a half minutes — you can see the whole city from the top.",
    "自由落體塔六十公尺，敢不敢？": "The drop tower is sixty meters. Dare you?",

    # ------------------------------------------------------------------ missions
    "前方": "ahead",
    "右前方": "ahead right",
    "右方": "right",
    "右後方": "behind right",
    "後方": "behind",
    "左後方": "behind left",
    "左方": "left",
    "左前方": "ahead left",
    " · 上方 {d:.0f} m": " · {d:.0f} m up",
    " · 下方 {d:.0f} m": " · {d:.0f} m down",
    "{side} {d:.0f} m": "{d:.0f} m {side}",
    "送達「{name}」！剩餘 {left}": "Delivered to {name}! {left} to spare",
    "超過時限，貨物沒送到": "Time's up — the package didn't make it",
    "剩餘 {left}   報酬 ${reward:,}": "Time left {left}   Reward ${reward:,}",
    "   提示：{hint}": "   Hint: {hint}",
    "到達起點！跳下去，在空中按 Space 展開翼裝，穿過第一個圈":
        "At the start! Jump, press Space in the air for the wingsuit and fly through the first ring",
    "{title} 完成！時間 {t}": "{title} complete! Time {t}",
    "著陸了 — 回到起點屋頂再試一次": "Landed — back to the start roof to try again",
    "著陸了！回到起點屋頂再試一次（J 放棄任務）": "Landed! Back to the start roof to try again (J to abandon)",
    "   最佳 {t}": "   Best {t}",
    "到起點屋頂（搭樓內電梯、爬樓梯或用鉤索）": "Get to the start roof (building elevator, stairs or grapple)",
    "{title}（翼裝穿圈賽）": "{title} (wingsuit ring race)",
    "跳下屋頂，Space 展開翼裝 — 穿過第一個圈開始計時": "Jump off, Space for the wingsuit — the clock starts at the first ring",
    "{title}  圈 {n}/{total}": "{title}  Ring {n}/{total}",
    "   Ctrl 衝刺加速": "   Ctrl to dash",
    "掉到街上了 — 回到第一個屋頂再試一次": "Fell to the street — back to the first roof to try again",
    "掉到街上了！回到第一個屋頂再試一次（J 放棄任務）": "Fell to the street! Back to the first roof to try again (J to abandon)",
    "開跑！依序跳到每個發光檢查點，別碰到街面": "Go! Reach each glowing checkpoint in order without touching the street",
    "{title}（屋頂跑酷）": "{title} (rooftop parkour)",
    "到第一個屋頂檢查點（樓內樓梯直通屋頂）": "Get to the first roof checkpoint (the building stairs go up to the roof)",
    "{title}  檢查點 {n}/{total}": "{title}  Checkpoint {n}/{total}",
    "   Q 二段跳 · Ctrl 衝刺 · F 鉤索": "   Q double jump · Ctrl dash · F grapple",
    "搭塔內電梯（數字鍵輸入樓層）": "take the tower elevator (type the floor number)",
    "港灣主碼頭搭渡輪": "take the ferry from the main harbor pier",
    "地心線月台旁的通道往下到 B2": "go down to B2 through the passage beside a Core Line platform",
    "霓虹市集站旁的地下街": "the underground street beside Neon Market Station",
    "地鐵站月台": "a metro platform",
    "在屋頂：電梯、鉤索或空中計程車": "on a roof: elevator, grapple or air taxi",
    "送貨": "Delivery",
    "把包裹送到地圖上的指定地點（限時）": "Deliver a package to a place on the map (timed)",
    "暴雨急件": "Storm express",
    "濃霧急件": "Fog express",
    "天氣立刻轉為{kind}，限時送件，報酬 ×1.8": "The weather turns to {kind} at once; timed delivery, reward ×1.8",
    "翼裝穿圈賽「{name}」": "Ring race: {name}",
    "從 {h:.0f} m 屋頂起跳，穿過 {n} 個圈": "Jump from a {h:.0f} m roof and fly through {n} rings",
    "屋頂跑酷「{name}」": "Parkour: {name}",
    "{n} 個屋頂檢查點，碰到街面就重來": "{n} roof checkpoints; touch the street and start over",
    "NEXUS 俯衝": "NEXUS Dive",
    "回聲天際線": "Echo Skyline",
    "企業峽谷": "Corporate Canyon",
    "港灣屋頂": "Harbor Rooftops",
    "夜市屋頂": "Night Market Rooftops",
    "鏽蝕屋頂": "Rust Rooftops",
    "任務終端・{name}        信用點 ${credits:,}": "Mission terminal · {name}        Credits ${credits:,}",
    "報酬依距離": "pay by distance",
    "{i}   {title} — {desc}（{pay}）": "{i}   {title} — {desc} ({pay})",
    "數字鍵接任務 · E / Esc 離開": "Number keys to take a mission · E / Esc to leave",
    "已有進行中的任務（J 放棄）": "A mission is already running (J to abandon)",
    "目前沒有可送的地點": "No delivery destinations right now",
    "接下「{title}」：送到 {dest}，限時 {t}": "Mission taken — {title}: deliver to {dest} within {t}",
    "接下{title}：先到起點屋頂（{h:.0f} m）": "Mission taken — {title}: first get to the start roof ({h:.0f} m)",
    "接下{title}：先到第一個屋頂檢查點": "Mission taken — {title}: first get to the first roof checkpoint",
    "已放棄任務「{title}」": "Mission abandoned: {title}",
    "（新紀錄！+$100）": " (New record! +$100)",
}
