"""The megatowers: shell, walk-in lobby, elevator rails, roof helipad."""
import numpy as np

import config as C
from geometry import box_bounds, quad, BOX_FLOATS, QUAD_FLOATS

# Nexus Tower's facade banners: (face, along, y, half width, half height, hue)
NEXUS_BANNERS = (("s", -24, 60, 8, 30, 0.83), ("s", 24, 140, 8, 40, 0.5), ("s", 0, 420, 18, 60, 0.92),
                 ("w", 10, 90, 14, 40, 0.12), ("w", -20, 300, 10, 80, 0.75), ("n", 0, 180, 20, 50, 0.55),
                 ("n", -22, 700, 8, 90, 0.83), ("e", 24, 110, 9, 45, 0.97), ("e", -24, 260, 9, 70, 0.5),
                 ("w", 0, 1200, 25, 120, 0.92), ("s", 0, 2000, 25, 150, 0.5))


class TowerData:
    def __init__(self, boxes, colliders, holos):
        self.boxes = np.array(boxes, dtype="f4").reshape(-1, BOX_FLOATS)
        self.colliders = colliders
        self.holos = np.array(holos, dtype="f4").reshape(-1, QUAD_FLOATS)


def _banners(t):
    """Banner list of a tower; the newer ones get a generated set spread over their height."""
    if t.index == 0:
        return NEXUS_BANNERS
    T, H = t.half, t.height
    hues = (t.accent, 0.83, 0.5, 0.92, 0.55, 0.75)
    out = []
    for i, (face, along, y, hh) in enumerate((("s", -0.5, 70, 30), ("w", 0.3, 140, 45), ("n", 0.0, 260, 55),
                                               ("e", 0.6, 120, 40), ("s", 0.0, 0.4 * H, 90),
                                               ("w", -0.2, 0.65 * H, 110), ("n", 0.4, 0.85 * H, 80))):
        hw = T * (0.3 if face == "e" else 0.4)          # east face keeps clear of the elevator
        out.append((face, along * T, y, hw, hh, hues[i % len(hues)]))
    return out


def build_tower(t):
    """Boxes, colliders and holograms of tower t (a floors.Tower), in world coordinates."""
    H, T, L, W = t.height, t.half, C.LOBBY_HEIGHT, C.LOBBY_WALL
    ox, oz = t.cx, t.cz
    door, door_h = C.ENTRANCE_HALF, C.ENTRANCE_HEIGHT
    ed, edh = C.ELEV_DOOR_HALF, C.ELEV_DOOR_HEIGHT
    boxes, cols, holos = [], [], []

    def shift(b):
        return (b[0] + ox, b[1], b[2] + oz, b[3] + ox, b[4], b[5] + oz)

    def solid(b, kind, hue=0.0, extra=0.0, seed=0.0, collide=True):
        b = shift(b)
        boxes.append(box_bounds(*b, kind, hue, extra, seed))
        if collide:
            cols.append(tuple(float(v) for v in b))

    def holo(center, right, up, *args):
        holos.append(quad((center[0] + ox, center[1], center[2] + oz), right, up, *args))

    # Main shaft from the lobby ceiling to the roof (its top face is the helipad). It is drawn
    # as one box; the shader opens windows/doorways near the player and the floors inside are
    # built on demand by tower_interior.py. Collision is a hollow 0.5 m shell + the roof slab.
    solid((-T, L, -T, T, H, T), C.K_TOWER, 0.5, t.accent, 1.0, collide=False)
    Wt = C.TOWER_WALL
    shell = [(-T, L, -T, -T + Wt, H, T), (-T, L, -T, T, H, -T + Wt), (-T, L, T - Wt, T, H, T),
             (T - Wt, L, -T, T, H, -ed), (T - Wt, L, ed, T, H, T)]                # east wall: elevator doorway column
    hx0, hz0, hx1, hz1 = t.stair_hole
    r0 = H - 0.5
    shell += [(-T, r0, -T, hx0, H, T), (hx1, r0, -T, T, H, T),                    # roof slab around the stair hatch
              (hx0, r0, -T, hx1, H, hz0), (hx0, r0, hz1, hx1, H, T)]
    cols += [shift(b) for b in shell]

    # Lobby floor (visual only; the ground plane is the walkable surface). extra 1 marks a lobby.
    solid((-T + W, -0.1, -T + W, T - W, 0.0, T - W), C.K_FLOOR, 0.5, 1.0, collide=False)

    # Lobby walls. South (+z) has the 12 m main entrance, east (+x) the elevator door.
    solid((-T, 0, T - W, -door, L, T), C.K_LOBBY)
    solid((door, 0, T - W, T, L, T), C.K_LOBBY)
    solid((-door, door_h, T - W, door, L, T), C.K_LOBBY)
    solid((-T, 0, -T, T, L, -T + W), C.K_LOBBY)
    solid((-T, 0, -T + W, -T + W, L, T - W), C.K_LOBBY)
    solid((T - W, 0, -T + W, T, L, -ed), C.K_LOBBY)
    solid((T - W, 0, ed, T, L, T - W), C.K_LOBBY)
    solid((T - W, edh, -ed, T, L, ed), C.K_LOBBY)

    # Reception desk, pillars, ceiling light strips.
    solid((-6, 0, -16, 6, 1.1, -14), C.K_PANEL, 0.83)
    solid((-6.05, 1.1, -16.05, 6.05, 1.18, -13.95), C.K_EMISSIVE, 0.83, 3.0, collide=False)
    pc = t.column
    for sx in (-1, 1):
        for sz in (-1, 1):
            solid((sx * pc - 1.2, 0, sz * pc - 1.2, sx * pc + 1.2, L, sz * pc + 1.2), C.K_LOBBY)
    n = int((T - 10) // 10)
    for z in range(-10 * n, 10 * n + 1, 10):                # stop short of the stairwell
        solid((-T + 6, L - 0.62, z - 0.3, t.stair_x0 - 2, L - 0.5, z + 0.3), C.K_EMISSIVE, -1.0, 2.2, collide=False)

    # Neon frame around the main entrance.
    solid((-door - 0.4, 0, T, -door, door_h + 0.4, T + 0.3), C.K_EMISSIVE, 0.83, 4.0, collide=False)
    solid((door, 0, T, door + 0.4, door_h + 0.4, T + 0.3), C.K_EMISSIVE, 0.83, 4.0, collide=False)
    solid((-door - 0.4, door_h, T, door + 0.4, door_h + 0.4, T + 0.3), C.K_EMISSIVE, 0.83, 4.0, collide=False)

    # Neon frame around the elevator door, on the lobby side of the east wall.
    x0 = T - W - 0.15
    solid((x0, 0, -ed - 0.3, T - W, edh + 0.3, -ed), C.K_EMISSIVE, 0.5, 3.0, collide=False)
    solid((x0, 0, ed, T - W, edh + 0.3, ed + 0.3), C.K_EMISSIVE, 0.5, 3.0, collide=False)
    solid((x0, edh, -ed - 0.3, T - W, edh + 0.3, ed + 0.3), C.K_EMISSIVE, 0.5, 3.0, collide=False)

    # Glowing guide rails of the external elevator, ground to roof.
    ex1 = T + C.ELEV_DEPTH
    for z in (-2.45, 2.45):
        solid((ex1 + 0.2, 0, z - 0.15, ex1 + 0.5, H, z + 0.15), C.K_EMISSIVE, 0.5, 1.6)

    # Holograms: entrance sign, lobby logo, elevator sign.
    holo((0, 9.0, T + 0.6), (7, 0, 0), (0, 2.0, 0), C.Q_HOLO, 0.83, 1.4, 11 + 100 * t.index)
    holo((0, 6.5, -T + W + 0.3), (min(12.0, T - 8.0), 0, 0), (0, 3.5, 0), C.Q_HOLO, 0.5, 1.2, 12 + 100 * t.index)
    holo((T - W - 0.3, 4.2, 0), (0, 0, 1.5), (0, 0.6, 0), C.Q_HOLO, 0.5, 1.5, 13 + 100 * t.index)

    # Giant facade banners (kept away from the elevator on the east face).
    o = T + 1.5
    for seed, (face, along, y, hw, hh, hue) in enumerate(_banners(t), 21 + 100 * t.index):
        if face == "s":
            holo((along, y, o), (hw, 0, 0), (0, hh, 0), C.Q_HOLO, hue, 1.1, seed)
        elif face == "n":
            holo((along, y, -o), (hw, 0, 0), (0, hh, 0), C.Q_HOLO, hue, 1.1, seed)
        elif face == "e":
            holo((o, y, along), (0, 0, hw), (0, hh, 0), C.Q_HOLO, hue, 1.1, seed)
        else:
            holo((-o, y, along), (0, 0, hw), (0, hh, 0), C.Q_HOLO, hue, 1.1, seed)

    return TowerData(boxes, cols, holos)
