"""Elevators: the external glass car on each megatower's east facade (lobby <-> roof), and the
shaft elevator inside tall city buildings (1F <-> top floor). Both share the motion and door
state machine of ElevatorBase; stops are floor numbers."""
import math

import buildings
import config as C
import floors
from geometry import box_bounds, quad

GROUND = floors.LOBBY                           # stops are floor numbers 1 .. max_stop


class ElevatorBase:
    CAR_H = C.ELEV_CAR_HEIGHT

    def __init__(self, level_y, floor_at, label, max_stop, top):
        self.level_y, self.floor_at, self.label = level_y, floor_at, label
        self.max_stop = max_stop
        self.top = top
        self.y = 0.0
        self.level = GROUND
        self.target = GROUND
        self.state = "idle"          # idle (doors open) / closing / moving / opening
        self.door = 1.0              # 0 closed .. 1 open
        self.speed = 0.0
        self._from = self._to = self._s = 0.0

    # ---------------------------------------------------------------- queries
    @property
    def moving(self):
        return self.state == "moving"

    def contains(self, pos):
        return self.in_footprint(pos) and self.y - 0.5 <= pos[1] <= self.y + self.CAR_H

    def floor_number(self):
        return self.floor_at(self.y + 0.01)

    def progress(self):
        return self.y / self.top

    def landing_door(self, k):
        """Open fraction of the landing (shaft) door on floor k: it follows the car door while parked there."""
        return self.door if (self.level == k and self.state != "moving") else 0.0

    def lobby_door(self):
        return self.landing_door(GROUND)

    # ---------------------------------------------------------------- control
    def request(self, level):
        level = max(GROUND, min(self.max_stop, int(level)))
        if self.state == "idle" and level != self.level:
            self.target = level
            self.state = "closing"
            return True
        return False

    def update(self, dt):
        """Advance the car; returns its vertical displacement this frame."""
        prev = self.y
        if self.state == "closing":
            self.door = max(0.0, self.door - dt / C.ELEV_DOOR_TIME)
            if self.door == 0.0:
                self.state = "moving"
                self._from = self.y
                self._to = self.level_y(self.target)
                self._s = 0.0
                self.speed = 0.0
        elif self.state == "moving":
            total = abs(self._to - self._from)
            v_stop = math.sqrt(2.0 * C.ELEV_ACCEL * max(total - self._s, 0.0))
            self.speed = max(min(self.speed + C.ELEV_ACCEL * dt, C.ELEV_SPEED, v_stop), 1.0)
            self._s = min(total, self._s + self.speed * dt)
            self.y = self._from + math.copysign(self._s, self._to - self._from)
            if self._s >= total:
                self.state = "opening"
                self.level = self.target
                self.speed = 0.0
        elif self.state == "opening":
            self.door = min(1.0, self.door + dt / C.ELEV_DOOR_TIME)
            if self.door == 1.0:
                self.state = "idle"
        return self.y - prev


class Elevator(ElevatorBase):
    """A megatower's external glass car on the east facade."""
    ZH = C.ELEV_Z_HALF

    def __init__(self, tower):
        super().__init__(tower.level_y, tower.floor_at, tower.label, tower.roof, tower.height)
        self.tower = tower
        self.X0, self.X1 = tower.elev_x0, tower.elev_x1
        self.cz = tower.cz

    def in_footprint(self, pos):
        return self.X0 + 0.05 < pos[0] < self.X1 and -self.ZH < pos[2] - self.cz < self.ZH

    def car_bounds(self):
        """Volume of the car (kept dry of rain / wind streaks)."""
        return (self.X0 - 0.1, self.y - 0.5, self.cz - self.ZH - 0.3,
                self.X1 + 0.3, self.y + self.CAR_H + 0.4, self.cz + self.ZH + 0.3)

    def landing_zone(self, pos):
        """Floor number of the landing the player stands at (inside the tower), or None."""
        t = self.tower
        if not t.contains(pos):
            return None
        x, z = t.local(pos)
        inner = t.half - (C.LOBBY_WALL if pos[1] < C.LOBBY_HEIGHT else C.TOWER_WALL)
        if not (abs(x) < inner and abs(z) < inner and x > inner - 6.0 and abs(z) < 4.0):
            return None
        k = t.floor_at(pos[1])
        if k >= t.roof or abs(pos[1] - t.level_y(k)) > 1.0:
            return None
        return k

    # ---------------------------------------------------------------- geometry
    def _parts(self):
        """(bounds, kind, hue, extra, collide) for every piece of the car and lobby shaft doors."""
        x0, x1, zh, cy, ch = self.X0, self.X1, self.ZH, self.y, self.CAR_H
        ed, edh = C.ELEV_DOOR_HALF, C.ELEV_DOOR_HEIGHT
        d = self.door
        parts = [
            ((x0, cy - 0.3, -zh, x1, cy, zh), C.K_FLOOR, 0.5, 0.0, True),
            ((x0, cy + ch, -zh, x1, cy + ch + 0.3, zh), C.K_PANEL, 0.5, 0.0, True),
            ((x0 + 0.5, cy + ch - 0.05, -1.5, x1 - 0.5, cy + ch, 1.5), C.K_EMISSIVE, -1.0, 2.5, False),
            ((x0, cy, -zh - 0.2, x1, cy + ch, -zh), C.K_PANEL, 0.5, 0.0, True),
            ((x0, cy, zh, x1, cy + ch, zh + 0.2), C.K_PANEL, 0.5, 0.0, True),
            ((x1, cy, -zh - 0.2, x1 + 0.15, cy + ch, zh + 0.2), None, 0, 0, True),  # glass (drawn as a quad)
            ((x0, cy, -zh, x0 + 0.2, cy + ch, -ed), C.K_PANEL, 0.5, 0.0, True),
            ((x0, cy, ed, x0 + 0.2, cy + ch, zh), C.K_PANEL, 0.5, 0.0, True),
            ((x0, cy + edh, -ed, x0 + 0.2, cy + ch, ed), C.K_PANEL, 0.5, 0.0, True),
            # sliding car doors
            ((x0 + 0.2, cy, -ed - d * ed, x0 + 0.3, cy + edh, -d * ed), C.K_DOOR, 0.5, 0.0, True),
            ((x0 + 0.2, cy, d * ed, x0 + 0.3, cy + edh, ed + d * ed), C.K_DOOR, 0.5, 0.0, True),
            # neon trim so the car reads as a moving light from far away
            ((x0, cy - 0.45, -zh - 0.2, x1 + 0.2, cy - 0.3, zh + 0.2), C.K_EMISSIVE, 0.83, 4.0, False),
            ((x1, cy + ch, -zh - 0.2, x1 + 0.2, cy + ch + 0.15, zh + 0.2), C.K_EMISSIVE, 0.5, 4.0, False),
            ((x1, cy, -zh - 0.25, x1 + 0.2, cy + ch, -zh - 0.1), C.K_EMISSIVE, 0.5, 3.0, False),
            ((x1, cy, zh + 0.1, x1 + 0.2, cy + ch, zh + 0.25), C.K_EMISSIVE, 0.5, 3.0, False),
        ]
        # lobby-side shaft doors (inside the east wall), open only while the car waits at ground
        ld = self.lobby_door()
        lx = self.X0 - C.LOBBY_WALL
        parts.append(((lx, 0.0, -ed - ld * ed, lx + 0.12, edh, -ld * ed), C.K_DOOR, 0.5, 0.0, True))
        parts.append(((lx, 0.0, ld * ed, lx + 0.12, edh, ed + ld * ed), C.K_DOOR, 0.5, 0.0, True))
        cz = self.cz                                    # parts are listed with z relative to the tower center
        return [((b[0], b[1], b[2] + cz, b[3], b[4], b[5] + cz), k, h, e, c) for b, k, h, e, c in parts]

    def colliders(self):
        return [tuple(b) for b, _, _, _, c in self._parts() if c]

    def instances(self):
        return [box_bounds(*b, k, h, e) for b, k, h, e, _ in self._parts() if k is not None]

    def glass_quads(self):
        cy = self.y + self.CAR_H * 0.5
        return [quad((self.X1 + 0.08, cy, self.cz), (0.0, 0.0, self.ZH + 0.1), (0.0, self.CAR_H * 0.5, 0.0),
                     C.Q_GLASS, 0.5, 1.0)]

    def gauge_quads(self):
        return [quad((self.X0 + 2.6, self.y + 1.9, self.cz - self.ZH + 0.03), (0.25, 0.0, 0.0), (0.0, 0.9, 0.0),
                     C.Q_GAUGE, 0.5, self.progress())]


class ShaftElevator(ElevatorBase):
    """The elevator of a tall city building (tower_interior.BuildingLayout g): a closed car in the
    shaft west of the stair core, doors facing the building front (-z local), 1F .. top floor."""
    CAR_H = buildings.SHAFT_CAR_H

    def __init__(self, g):
        super().__init__(g.level_y, g.floor_at, g.label, g.floors, max(g.level_y(g.floors), 1.0))
        self.g = g
        self.rect = g.bounds(*g.car)                   # world (x0, z0, x1, z1) of the car

    def in_footprint(self, pos):
        x0, z0, x1, z1 = self.rect
        return x0 + 0.05 < pos[0] < x1 - 0.05 and z0 + 0.05 < pos[2] < z1 - 0.05

    def car_bounds(self):
        x0, z0, x1, z1 = self.rect
        return (x0, self.y - 0.5, z0, x1, self.y + self.CAR_H + 0.4, z1)

    def landing_zone(self, pos):
        """Floor number of the landing the player stands at (in front of the shaft door), or None."""
        g = self.g
        d0, d1 = g.door
        x0, z0, x1, z1 = g.bounds(d0 - 0.5, g.Z1A - buildings.WT - 2.5, d1 + 0.5, g.Z1A - buildings.WT)
        if not (x0 < pos[0] < x1 and z0 < pos[2] < z1):
            return None
        k = g.floor_at(pos[1])
        if k > g.floors or abs(pos[1] - g.level_y(k)) > 1.0:
            return None
        return k

    def _parts(self):
        g, y, H, d = self.g, self.y, self.CAR_H, self.door
        cx0, cz0, cx1, cz1 = g.car
        d0, d1 = g.door
        dc, dh = (d0 + d1) / 2, (d1 - d0) / 2
        DH = buildings.SHAFT_DOOR_H
        local = [
            ((cx0, y - 0.25, cz0, cx1, y, cz1), C.K_FLOOR, 0.5, 0.0, True),
            ((cx0, y + H, cz0, cx1, y + H + 0.15, cz1), C.K_PANEL, 0.5, 0.0, True),
            ((cx0 + 0.5, y + H - 0.05, cz0 + 0.6, cx1 - 0.5, y + H, cz1 - 0.6), C.K_EMISSIVE, -1.0, 2.2, False),
            ((cx0, y, cz1 - 0.1, cx1, y + H, cz1), C.K_PANEL, 0.5, 0.0, True),
            ((cx0, y, cz0, cx0 + 0.1, y + H, cz1), C.K_PANEL, 0.5, 0.0, True),
            ((cx1 - 0.1, y, cz0, cx1, y + H, cz1), C.K_PANEL, 0.5, 0.0, True),
            ((cx0, y, cz0, d0, y + H, cz0 + 0.1), C.K_PANEL, 0.5, 0.0, True),
            ((d1, y, cz0, cx1, y + H, cz0 + 0.1), C.K_PANEL, 0.5, 0.0, True),
            ((d0, y + DH, cz0, d1, y + H, cz0 + 0.1), C.K_PANEL, 0.5, 0.0, True),
            ((cx1 - 0.12, y + 1.0, cz0 + 0.6, cx1 - 0.1, y + 1.6, cz0 + 0.9), C.K_EMISSIVE, 0.5, 3.0, False),  # panel
            # sliding car doors
            ((dc - dh - d * dh, y, cz0 + 0.1, dc - d * dh, y + DH, cz0 + 0.2), C.K_DOOR, 0.5, 0.0, True),
            ((dc + d * dh, y, cz0 + 0.1, dc + dh + d * dh, y + DH, cz0 + 0.2), C.K_DOOR, 0.5, 0.0, True),
        ]
        out = []
        for b, k, h, e, c in local:
            x0, z0, x1, z1 = g.bounds(b[0], b[2], b[3], b[5])
            out.append(((x0, b[1], z0, x1, b[4], z1), k, h, e, c))
        return out

    def colliders(self):
        return [tuple(b) for b, _, _, _, c in self._parts() if c]

    def instances(self):
        return [box_bounds(*b, k, h, e) for b, k, h, e, _ in self._parts()]

    def glass_quads(self):
        return []

    def gauge_quads(self):
        return []
