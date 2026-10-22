# Neon City — Megatowers

[English](#english) · [中文](#中文)

---

## English

A first-person walk through a procedurally built cyberpunk city, written in Python with pygame and moderngl.
Three walk-in megatowers rise above themed districts. NEXUS TOWER has 1000 floors, HELIX SPIRE 800 and AURORA TOWER 550.
You can ride the elevators, glide off the roofs in a wingsuit, swing across streets with a grapple, take the metro,
air taxis and ferries, and take on missions for credits.

### Features

- **Megatowers**: walk-in lobbies, a stairwell on every floor, an external glass elevator to the roof helipad,
  and a feature floor every 100 floors (observatory, sky garden, sky bar).
- **City**: six districts (Downtown, Corporate, Neon Night Market, Residential, Rust District, Harbor). Every
  building has a shop on the ground floor with stairs and elevators behind the counter. Skybridges, rooftop bars,
  pools and helipads, parks and plazas, flying traffic, street traffic with signals, and thousands of pedestrians.
- **Getting around**: three metro lines (Core Line underground, Skyline elevated loop, Three Towers Line), air
  taxis between 10 stands, ferries to Neon Island and the Sea Amusement Park (Ferris wheel, drop tower).
- **Underground**: an underground mall reached by a moving walkway, and the B2 undercity ring with a black market,
  parking garage, food court and arcade.
- **Movement**: running, a rocket-boot double jump and dash, a wingsuit and a grapple hook.
- **Missions**: deliveries, weather express runs, wingsuit ring races and rooftop parkour from terminals around the city.
- **Progress**: collect data shards and finish missions to earn credits, then buy cyberware upgrades at CHROME
  clinics.
- **City map** (M): places you have visited unlock fast travel.
- **Weather and time**: a day/night cycle with clear, cloudy, rain, storm (lightning) and fog weather.
- **Two languages**: Traditional Chinese and English, switchable at any time.

### Requirements

- Python 3.8 or newer (tested with 3.12)
- A GPU with OpenGL 3.3 support
- Packages: `pygame >= 2.1.3`, `moderngl >= 5.8`, `numpy >= 1.24`

```
pip install -r requirements.txt
```

### Running

```
python main.py
```

| Option | Meaning |
| --- | --- |
| `--width W --height H` | Window size (default 1600 × 900) |
| `--fullscreen` | Full screen at the desktop resolution |
| `--msaa N` | Multisampling samples (default 4, `0` turns it off) |
| `--seed N` | City seed (default 2077) |
| `--continue` | Continue the saved game without the start screen |
| `--new` | Start over; the old save is kept as `savegame.bak.json` |
| `--lang zh` / `--lang en` | Game language: Chinese or English |

### Controls

| Key | Action |
| --- | --- |
| W A S D / mouse | Move / look |
| Shift | Run |
| Space | Jump; in the air: open / fold the wingsuit; in a flying taxi: bail out |
| Q | Double jump (rocket boots) |
| Left Ctrl | Boost dash (also speeds up the wingsuit) |
| F / right mouse | Fire / release the grapple (hooks when the crosshair shows a yellow ring) |
| E / Enter | Use elevators and taxis, talk to people, open mission terminals and clinics |
| Number keys / mouse wheel | Choose a floor in an elevator, a stand in a taxi, an item in a menu |
| J | Abandon the current mission |
| T | Teleport to the nearest megatower roof (again: the next tower) |
| R | Back to the start |
| M | City map (drag to pan, wheel to zoom, click a visited place to fast travel) |
| F5 / F6 / `[` `]` | Weather / time speed / time ±1 hour |
| **F7** | **Switch language (中文 ↔ English)** |
| F8 | Save |
| F1 / F3 | Show / hide help, debug info |
| Tab | Release the mouse |
| Esc | Close a menu / quit (saves) |

### Language

The game starts in Chinese. You can switch languages in three ways:

- press **F7** in game,
- press **L** on the start screen,
- start with `--lang en` (or `--lang zh`).

Your choice is saved in `savegame.json` and used next time, unless `--lang` says otherwise.
All text (HUD, prompts, menus, missions, the city map, and place and shop names) switches immediately.
Translations live in `i18n.py`. The Chinese text in the code is the key, and `EN` maps it to English.

### Saving

Progress is saved to `savegame.json` next to the game. That includes credits, upgrades, data shards,
mission records, unlocked places, position, time, weather and language. The game saves when you press F8,
every 2 minutes, and when you quit. Starting a new game keeps the previous save as `savegame.bak.json`.

### Project layout

| File | Contents |
| --- | --- |
| `main.py` | Game loop, input, HUD text, save / load, start screen |
| `i18n.py` | Language switching and the English translations |
| `config.py` | Global constants (towers, city layout, shops, player) |
| `renderer.py`, `shaders.py`, `geometry.py` | moderngl renderer (HDR, bloom), GLSL shaders, mesh helpers |
| `hud.py`, `citymap.py` | 2D overlay and the city map with fast travel |
| `player.py`, `collision.py` | First-person controller (boots, wingsuit, grapple) and collision |
| `city.py`, `buildings.py`, `districts.py`, `rooftops.py`, `skybridges.py`, `parks.py` | Procedural city |
| `tower.py`, `floors.py`, `tower_interior.py`, `elevator.py`, `workers.py` | Megatowers, building interiors, elevators |
| `shops.py`, `mall.py`, `undercity.py` | Shops, underground mall, B2 undercity |
| `metro.py`, `taxi.py`, `harbor.py`, `sea.py`, `rides.py` | Metro, air taxis, harbor, island and sea park, rides |
| `traffic.py`, `pedestrians.py`, `crowds.py` | Street traffic and people |
| `missions.py`, `pickups.py`, `progress.py`, `savegame.py` | Missions, data shards, upgrades, save file |
| `environment.py`, `effects.py`, `audio.py` | Weather and time, particles, procedural sound |

### License

[MIT](LICENSE) © 2026 Allen Wu

---

## 中文

用 Python（pygame + moderngl）寫成的第一人稱賽博龐克城市漫遊遊戲，城市以程序生成。
三座可以走進去的超高摩天樓聳立在各具特色的城區之上：NEXUS TOWER 1000 層、HELIX SPIRE 800 層、AURORA TOWER 550 層。
你可以搭電梯、從屋頂穿翼裝滑翔、用鉤索盪過街道、搭地鐵、空中計程車和渡輪，還能接任務賺信用點。

### 特色

- **摩天樓**：可以走進大廳，每層都有樓梯間，外牆玻璃電梯直達頂樓直升機坪，每 100 層有一個特色樓層（觀景台、空中花園、高空酒吧）。
- **城市**：六個城區（市中心、企業特區、霓虹夜市、住宅區、鏽蝕區、港灣區）。每棟建築一樓都是商店，櫃台後方有樓梯與電梯。城裡還有空中天橋、屋頂酒吧、泳池和停機坪、公園與廣場、飛行車流、有紅綠燈的地面交通，以及數千名行人。
- **交通**：三條地鐵線（地下的地心線、高架外環天際線、三塔線）、10 個招呼站之間的空中計程車、開往霓虹島與海上遊樂園（摩天輪、自由落體塔）的渡輪。
- **地下世界**：以電動步道相連的地下商場，以及 B2 地下城環道，裡面有黑市、停車場、美食街和電玩街。
- **移動**：奔跑、火箭靴二段跳與衝刺、翼裝滑翔、鉤索。
- **任務**：城市各處的任務終端提供送貨、天氣急件、翼裝穿圈賽和屋頂跑酷。
- **成長**：撿資料碎片、完成任務賺信用點，再到 CHROME 義體診所升級義體。
- **城市地圖**（M）：去過的地點可以快速移動。
- **天氣與時間**：日夜循環，天氣有晴、多雲、雨、暴雨（會打雷閃電）和霧。
- **雙語介面**：繁體中文與英文，隨時可以切換。

### 系統需求

- Python 3.8 以上（已用 3.12 測試）
- 支援 OpenGL 3.3 的顯示卡
- 套件：`pygame >= 2.1.3`、`moderngl >= 5.8`、`numpy >= 1.24`

```
pip install -r requirements.txt
```

### 執行

```
python main.py
```

| 參數 | 說明 |
| --- | --- |
| `--width W --height H` | 視窗大小（預設 1600 × 900） |
| `--fullscreen` | 以桌面解析度全螢幕 |
| `--msaa N` | 多重取樣數（預設 4，`0` 關閉） |
| `--seed N` | 城市種子（預設 2077） |
| `--continue` | 跳過開始畫面，直接繼續存檔 |
| `--new` | 重新開始，舊存檔備份為 `savegame.bak.json` |
| `--lang zh` / `--lang en` | 遊戲語言：中文或英文 |

### 操作

| 按鍵 | 功能 |
| --- | --- |
| W A S D / 滑鼠 | 移動 / 轉視角 |
| Shift | 奔跑 |
| Space | 跳躍；空中：展開 / 收起翼裝；飛行中的計程車：跳車 |
| Q | 二段跳（火箭靴） |
| 左 Ctrl | 噴射衝刺（翼裝中可加速） |
| F / 滑鼠右鍵 | 發射 / 放開鉤索（準心出現黃圈時可以勾住） |
| E / Enter | 搭電梯與計程車、跟人說話、開啟任務終端與義體診所 |
| 數字鍵 / 滾輪 | 電梯中選樓層、計程車中選目的地、選單中選項目 |
| J | 放棄目前的任務 |
| T | 傳送到最近的摩天樓頂樓（再按一次換下一棟） |
| R | 回到起點 |
| M | 城市地圖（拖曳平移、滾輪縮放、點擊去過的地點快速移動） |
| F5 / F6 / `[` `]` | 天氣 / 時間流速 / 時間 ±1 小時 |
| **F7** | **切換語言（中文 ↔ English）** |
| F8 | 存檔 |
| F1 / F3 | 顯示 / 隱藏說明、除錯資訊 |
| Tab | 釋放滑鼠 |
| Esc | 關閉選單 / 離開（會存檔） |

### 語言

遊戲預設為中文。切換語言有三種方式：

- 遊戲中按 **F7**；
- 開始畫面按 **L**；
- 啟動時加上 `--lang en`（或 `--lang zh`）。

選擇的語言會記在 `savegame.json`，下次啟動沿用（除非用 `--lang` 指定）。
所有文字（HUD、提示、選單、任務、城市地圖，以及地名與店名）都會立即切換。
翻譯放在 `i18n.py`：程式中的中文原文就是鍵值，`EN` 字典對應到英文。

### 存檔

進度存在遊戲資料夾的 `savegame.json`，內容包括信用點、義體等級、資料碎片、任務紀錄、已解鎖地點、位置、時間、天氣和語言。
按 F8、每 2 分鐘以及離開遊戲時都會自動存檔。開始新遊戲時，舊存檔會備份為 `savegame.bak.json`。

### 檔案結構

| 檔案 | 內容 |
| --- | --- |
| `main.py` | 主迴圈、輸入、HUD 文字、存讀檔、開始畫面 |
| `i18n.py` | 語言切換與英文翻譯 |
| `config.py` | 全域常數（摩天樓、城市配置、商店、玩家） |
| `renderer.py`、`shaders.py`、`geometry.py` | moderngl 繪製（HDR、光暈）、GLSL 著色器、網格工具 |
| `hud.py`、`citymap.py` | 2D 介面與可快速移動的城市地圖 |
| `player.py`、`collision.py` | 第一人稱控制（火箭靴、翼裝、鉤索）與碰撞 |
| `city.py`、`buildings.py`、`districts.py`、`rooftops.py`、`skybridges.py`、`parks.py` | 程序生成的城市 |
| `tower.py`、`floors.py`、`tower_interior.py`、`elevator.py`、`workers.py` | 摩天樓、建築內部、電梯 |
| `shops.py`、`mall.py`、`undercity.py` | 商店、地下商場、B2 地下城 |
| `metro.py`、`taxi.py`、`harbor.py`、`sea.py`、`rides.py` | 地鐵、空中計程車、港灣、霓虹島與海上遊樂園、遊樂設施 |
| `traffic.py`、`pedestrians.py`、`crowds.py` | 地面交通與人群 |
| `missions.py`、`pickups.py`、`progress.py`、`savegame.py` | 任務、資料碎片、義體升級、存檔 |
| `environment.py`、`effects.py`、`audio.py` | 天氣與時間、粒子特效、程序合成音效 |

### 授權

採用 [MIT 授權](LICENSE) © 2026 Allen Wu
