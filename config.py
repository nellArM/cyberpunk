"""Global constants for Neon City."""

# --- Megatowers ----------------------------------------------------------
# (name, center x, center z, floors, half footprint, accent hue; 0 = Nexus' cyan/magenta)
# The two newer towers each fill one city block (buildable half 29.5 m incl. the elevator).
TOWER_SPECS = (
    ("NEXUS TOWER", 0.0, 0.0, 1000, 40.0, 0.0),
    ("AURORA TOWER", 240.0, -240.0, 550, 24.0, 0.12),
    ("HELIX SPIRE", -320.0, 320.0, 800, 24.0, 0.38),
)
FLOOR_HEIGHT = 4.0
FLOORS = 1000                             # Nexus Tower
LOBBY_HEIGHT = 12.0                       # 1F lobby is triple height; 2F.. are 4 m each
TOWER_HEIGHT = LOBBY_HEIGHT + (FLOORS - 1) * FLOOR_HEIGHT   # Nexus: 4008 m roof (helipad level)
TOWER_HALF = 40.0                         # Nexus: 80 x 80 m footprint
TOWER_WALL = 0.5                          # shell thickness above the lobby
SLAB = 0.3                                # floor slab thickness
LOBBY_WALL = 1.0
ENTRANCE_HALF = 6.0                       # main door is 12 m wide
ENTRANCE_HEIGHT = 6.0

# --- Stairwell (switchback stairs, one 4 m storey per unit, 0 m .. roof) ---
# Tower-local x measured from the east facade: Nexus landing x in [28, 29.4], flights to 32.4, mid landing to 33.8
STAIR_INSET = 12.0
STAIR_LAND = 1.4
STAIR_RUN = 3.0                           # 10 steps x 0.3 m
STAIR_STEPS = 10
STAIR_Z0 = 8.0                            # flight 1 z in [8, 9.5], divider, flight 2 z in [9.7, 11.2]
STAIR_FLIGHT_W = 1.5
STAIR_DIVIDER = 0.2
STAIR_DOOR_H = 2.5

# --- Elevator (external glass car on the east facade) --------------------
ELEV_DEPTH = 4.0                          # car spans local x in [half, half + 4]
ELEV_Z_HALF = 2.0                         # car spans local z in [-2, 2]
ELEV_CAR_HEIGHT = 3.6
ELEV_DOOR_HALF = 1.0                      # door opening z in [-1, 1]
ELEV_DOOR_HEIGHT = 3.0
ELEV_SPEED = 120.0                        # m/s cruise  -> ~40 s ride
ELEV_ACCEL = 15.0
ELEV_DOOR_TIME = 1.2

# --- City layout ---------------------------------------------------------
BLOCK_PITCH = 80.0                        # road centerlines at 40 + 80k
ROAD_HALF = 8.0
CITY_BLOCKS = 36                          # blocks in each direction (~2.9 km), sprawl lights beyond
PLAZA_HALF = 112.0
TRAFFIC_COUNT = 800                       # flying cars

# --- Districts, parks and plazas ------------------------------------------
DOWNTOWN_BLOCKS = 5                       # max(|i|, |j|) <= this is downtown; outside, one district per quadrant
# (name, block i, block j, kind) - these blocks hold no buildings
PARKS = (
    ("霓虹公園", -5, 1, "park"),
    ("星塵公園", 2, 4, "park"),
    ("零點廣場", -2, -4, "plaza"),
    ("回聲廣場", 5, 2, "plaza"),
)
PARK_WALKERS = 40                         # strollers per park / plaza

# --- Underground mall: passage from this 地心線 station (0, -280) north to a hall under Nexus ---
MALL_STATION = "霓虹市集"
MALL_DOOR = (10.5, 14.5)                  # opening in that platform's back wall (station-local a = world x)
MALL_STAIR = (-12.0, -30.0, -9.0, -18.0)  # stairs hall -> Nexus lobby (x0, z0, x1, z1), rising toward +z
MALL_Y = -8.0

# --- B2 undercity: a square ring passage under the 地心線 loop, reached from each station ---
UNDERCITY_Y = -16.0
UNDERCITY_R = 240.0                       # ring centerline (it is 8 m wide)
UNDERCITY_DOOR = (10.5, 14.5)             # extra opening in each 地心線 platform's back wall (station-local a)
UNDERCITY_DOOR_MALL = (-14.5, -10.5)      # ... at 霓虹市集, whose (10.5, 14.5) door leads to the mall
BLACKMARKET_LINES = (
    "義體零件，不問來源。要的話現金交易。",
    "假身分晶片，今天打八折，掃描器保證看不出來。",
    "這把電子鎖破解器能開任何門……大概。",
    "噓——巡邏無人機剛過去，快選。",
    "上一手主人？別問。保固是不可能有的。",
)
PARK_LINES = (
    "射中三個霓虹氣球，送你一隻全像貓！",
    "摩天輪轉一圈兩分半，頂上看得到整座城。",
    "自由落體塔六十公尺，敢不敢？",
)

# --- Harbor (south edge): block row HARBOR_ROW is the waterfront, open sea beyond SHORE_Z ---
HARBOR_ROW = 14
SHORE_Z = 1180.0                          # quay edge; the boulevard at z = 1160, promenade 1170.5..1180
CONTAINER_BLOCKS = range(-12, -4)         # harbor blocks (i, HARBOR_ROW) that are container yards

# --- Ground traffic ------------------------------------------------------
GROUND_TRAFFIC_COUNT = 9000
GROUND_TRAFFIC_EXTENT = 1000.0            # cars drive (and wrap) inside +-1 km (~40 m apart per lane)
STOP_LINE = 11.4                          # front bumper stops this far from an intersection center
SIGNAL_CYCLE = 24.0                       # x-axis green+yellow, then z-axis green+yellow
SIGNAL_GREEN = 10.0
SIGNAL_YELLOW = 2.0

# --- Pedestrians ---------------------------------------------------------
PED_COUNT = 8000                          # sidewalk walkers in blocks |i|,|j| <= PED_BLOCKS
PED_PLAZA_COUNT = 150                     # strollers around the tower
PED_BLOCKS = 12
PED_CROSS_P = 0.3                         # chance to cross the street at a corner
PED_RENDER_DIST = 350.0
PED_MAX_BOXES = 24000                     # 8 boxes per visible pedestrian

# --- Ground-floor shops --------------------------------------------------
SHOP_H = 5.0
SHOP_DOOR_HALF = 1.5
SHOP_DOOR_H = 3.2
SHOP_WALL = 0.3
SHOP_MAX_W = 18.0                         # big buildings get a partitioned shop of at most W x D
SHOP_MAX_D = 14.0
SHOP_NEAR = 45.0                          # interiors are furnished within this radius
SHOP_FORGET = 120.0
# (name, hue, clerk line) - order must match shopAccent() in shaders.BOX_FS
SHOP_TYPES = (
    ("NEON MART 便利商店", 0.52, "歡迎光臨！合成飯糰今天買一送一。"),
    ("電脳拉麵", 0.03, "來碗豚骨拉麵嗎？叉燒是實驗室培養的，很新鮮。"),
    ("CHROME 義體診所", 0.38, "想換條新手臂？保固三年，保證不含病毒。"),
    ("SYNTH BAR", 0.78, "來杯霓虹琴通寧？今晚的 DJ 是 AI。"),
    ("GIGA 電子", 0.6, "最新神經介面晶片，插上就能下載功夫。"),
    ("BYTE CAFÉ", 0.08, "一杯拿鐵，三倍咖啡因，加一點量子奶泡。"),
)

# --- Player --------------------------------------------------------------
SPAWN = (0.0, 0.0, 100.0)
GRAVITY = 15.0
TERMINAL_VELOCITY = 120.0
WALK_SPEED = 5.5
RUN_SPEED = 11.0
JUMP_SPEED = 6.5
GROUND_ACCEL = 60.0
AIR_ACCEL = 4.0
MOUSE_SENS = 0.0022

# --- Rocket boots --------------------------------------------------------
BOOT_MIN_SPEED = 15.0                     # only fires on real falls
BOOT_BRAKE_DECEL = 25.0                   # 120 m/s -> triggers ~310 m up
BOOT_HOVER_ALT = 20.0                     # braking ends this high above ground
BOOT_HOVER_SPEED = 3.0                    # slow final descent
BOOT_LAND_FADE = 0.9

# --- Rendering -----------------------------------------------------------
NEAR = 0.1
FAR = 40000.0
FOV = 75.0
FOV_FALL_BONUS = 18.0

# Box instance kinds (must match shaders.BOX_FS)
K_CITY, K_TOWER, K_PANEL, K_EMISSIVE, K_FLOOR = 0, 1, 2, 3, 4
K_SIGN, K_LOBBY, K_ANTENNA, K_VEHICLE, K_DOOR = 5, 6, 7, 8, 9
K_SIGNAL, K_SHOP_CEIL, K_SHOP_WALL, K_PED, K_SLAB, K_TRAIN = 10, 11, 12, 13, 14, 15

# Shop door faces (encoded in a city box's `extra` as face + 10 * shop_type)
FACE_PX, FACE_NX, FACE_PZ, FACE_NZ = 1, 2, 3, 4

# Quad (hologram) modes
Q_HOLO, Q_GLASS, Q_GAUGE = 0, 1, 2

NEON_HUES = (0.83, 0.5, 0.92, 0.12, 0.75, 0.55, 0.97)
