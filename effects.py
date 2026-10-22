"""CPU particle effects (numpy): boot flames, smoke, ground dust, rain and wind streaks."""
import math

import numpy as np

import config as C


def _interp_cols(t, stops, table):
    return np.stack([np.interp(t, stops, table[:, k]) for k in range(table.shape[1])], axis=1)


def _in_boxes(p, boxes):
    """Which points p (n x 3) lie inside any of the (x0, y0, z0, x1, y1, z1) boxes."""
    inside = np.zeros(len(p), bool)
    for x0, y0, z0, x1, y1, z1 in boxes:
        inside |= ((p[:, 0] > x0) & (p[:, 0] < x1) & (p[:, 1] > y0) & (p[:, 1] < y1)
                   & (p[:, 2] > z0) & (p[:, 2] < z1))
    return inside


class _Pool:
    def __init__(self, cap):
        self.pos = np.zeros((cap, 3), np.float32)
        self.vel = np.zeros((cap, 3), np.float32)
        self.age = np.zeros(cap, np.float32)
        self.life = np.ones(cap, np.float32)
        self.alive = np.zeros(cap, bool)

    def spawn(self, pos, vel, life):
        free = np.flatnonzero(~self.alive)[:len(pos)]
        n = len(free)
        if n:
            self.pos[free] = pos[:n]
            self.vel[free] = vel[:n]
            self.life[free] = life[:n]
            self.age[free] = 0.0
            self.alive[free] = True

    def step(self, dt, drag, accel=(0.0, 0.0, 0.0)):
        a = self.alive
        if not a.any():
            return
        self.vel[a] *= math.exp(-drag * dt)
        self.vel[a] += np.asarray(accel, np.float32) * dt
        self.pos[a] += self.vel[a] * dt
        self.age[a] += dt
        self.alive &= self.age < self.life

    def render(self, stops, colors, size_stops, sizes, origin=(0.0, 0.0, 0.0)):
        a = np.flatnonzero(self.alive)
        out = np.empty((len(a), 8), np.float32)
        if len(a):
            t = self.age[a] / self.life[a]
            out[:, 0:3] = self.pos[a] + np.asarray(origin, np.float32)
            out[:, 3:7] = _interp_cols(t, stops, colors)
            out[:, 7] = np.interp(t, size_stops, sizes)
        return out


class Fire:
    """Twin exhaust jets, simulated relative to the player's feet so they stay attached at any speed."""
    STOPS = [0.0, 0.1, 0.3, 0.6, 1.0]
    COLORS = np.array([[1.0, 1.4, 3.5, 0.9], [3.0, 1.9, 0.8, 0.9], [2.6, 0.8, 0.15, 0.7],
                       [1.0, 0.2, 0.04, 0.35], [0.2, 0.05, 0.02, 0.0]], np.float32)

    def __init__(self, rng):
        self.rng = rng
        self.pool = _Pool(4000)
        self.acc = 0.0

    def update(self, dt, thrust, yaw, speed, push=None):
        """push: (dx, dz) direction of a dash; the jets then blow back against it."""
        rng = self.rng
        if thrust > 0.02:
            self.acc += 1100.0 * thrust * dt
            n = int(self.acc)
            self.acc -= n
            if n:
                side = rng.choice((-0.16, 0.16), n)
                rx, rz = math.cos(yaw), math.sin(yaw)
                fx, fz = math.sin(yaw), -math.cos(yaw)
                pos = np.empty((n, 3), np.float32)
                pos[:, 0] = rx * side + fx * 0.06
                pos[:, 1] = 0.1
                pos[:, 2] = rz * side + fz * 0.06
                pos += rng.normal(0.0, 0.03, (n, 3))
                k = 0.6 + 0.4 * min(thrust, 1.2)
                vel = np.empty((n, 3), np.float32)
                vel[:, 0] = rng.normal(0.0, 1.4, n)
                vel[:, 1] = -(16.0 + 16.0 * rng.random(n)) * k
                vel[:, 2] = rng.normal(0.0, 1.4, n)
                if push is not None and (push[0] or push[1]):
                    vel[:, 0] -= push[0] * 20.0 * k
                    vel[:, 2] -= push[1] * 20.0 * k
                    vel[:, 1] *= 0.35
                life =(0.16 + 0.28 * rng.random(n)) * (0.7 + 0.3 * min(thrust, 1.2))
                self.pool.spawn(pos, vel, life)
        else:
            self.acc = 0.0
        # oncoming air bends the plume back up toward the boots
        self.pool.step(dt, 2.0, (0.0, min(speed, 60.0) * 0.35, 0.0))

    def render_data(self, feet):
        return self.pool.render(self.STOPS, self.COLORS, [0.0, 0.3, 1.0], [0.09, 0.26, 0.5], feet)


class Smoke:
    """World-space exhaust smoke: leaves a trail behind the falling player."""
    STOPS = [0.0, 0.08, 0.4, 1.0]
    COLORS = np.array([[0.9, 0.4, 0.12, 0.0], [0.35, 0.17, 0.08, 0.35],
                       [0.07, 0.065, 0.07, 0.25], [0.05, 0.05, 0.055, 0.0]], np.float32)

    def __init__(self, rng):
        self.rng = rng
        self.pool = _Pool(1500)
        self.acc = 0.0

    def update(self, dt, thrust, feet, vel):
        rng = self.rng
        if thrust > 0.05:
            self.acc += 90.0 * thrust * dt
            n = int(self.acc)
            self.acc -= n
            if n:
                pos = np.asarray(feet, np.float32) + np.array([0.0, -1.5, 0.0], np.float32) \
                    + rng.normal(0.0, 0.4, (n, 3)).astype(np.float32)
                v = np.asarray(vel, np.float32) * 0.15 + rng.normal(0.0, 1.5, (n, 3)).astype(np.float32)
                v[:, 1] -= 8.0
                self.pool.spawn(pos, v, 2.5 + 1.5 * rng.random(n))
        self.pool.step(dt, 1.2, (0.0, 0.8, 0.0))

    def render_data(self):
        return self.pool.render(self.STOPS, self.COLORS, [0.0, 0.3, 1.0], [0.6, 3.5, 6.0])


class Dust:
    """Ground dust blown outward by the boots as the player nears the ground."""
    STOPS = [0.0, 0.15, 1.0]
    COLORS = np.array([[0.5, 0.3, 0.18, 0.45], [0.16, 0.14, 0.14, 0.35], [0.1, 0.09, 0.1, 0.0]], np.float32)

    def __init__(self, rng):
        self.rng = rng
        self.pool = _Pool(2500)
        self.acc = 0.0

    def _emit(self, n, x, ground, z, strength):
        rng = self.rng
        ang = rng.uniform(0.0, 2.0 * math.pi, n)
        r = rng.uniform(0.3, 2.0, n)
        c, s = np.cos(ang), np.sin(ang)
        pos = np.stack([x + c * r, np.full(n, ground + 0.25), z + s * r], 1).astype(np.float32)
        sp = (8.0 + 14.0 * rng.random(n)) * (0.4 + 0.6 * strength)
        vel = np.stack([c * sp, 0.5 + 2.0 * rng.random(n), s * sp], 1).astype(np.float32)
        self.pool.spawn(pos, vel, 1.2 + 1.4 * rng.random(n))

    def update(self, dt, thrust, x, z, ground, height):
        if thrust > 0.05 and height < 25.0:
            strength = 1.0 - height / 25.0
            self.acc += 320.0 * thrust * strength * dt
            n = int(self.acc)
            self.acc -= n
            if n:
                self._emit(n, x, ground, z, strength)
        self.pool.step(dt, 1.0, (0.0, -0.5, 0.0))

    def burst(self, x, z, ground):
        self._emit(400, x, ground, z, 1.0)

    def render_data(self):
        return self.pool.render(self.STOPS, self.COLORS, [0.0, 1.0], [0.6, 4.5])


class Streaks:
    """Rain plus wind streak lines in a box that wraps around the camera.

    Each particle has a world velocity; drawing it as a segment along its velocity
    relative to the camera gives correct motion streaks while falling at 120 m/s.
    """

    def __init__(self, rng, n_rain=2600, n_wind=500):
        self.L_rain, self.L_wind = 44.0, 90.0
        self.rain = rng.uniform(-self.L_rain / 2, self.L_rain / 2, (n_rain, 3)).astype(np.float32)
        self.rain_v = np.tile(np.array([1.5, -17.0, 0.8], np.float32), (n_rain, 1))
        self.rain_v += rng.normal(0.0, 0.6, (n_rain, 3)).astype(np.float32)
        self.wind = rng.uniform(-self.L_wind / 2, self.L_wind / 2, (n_wind, 3)).astype(np.float32)

    def update(self, dt, cam_vel):
        cv = np.asarray(cam_vel, np.float32)
        h = self.L_rain / 2
        self.rain += (self.rain_v - cv) * dt
        self.rain = (self.rain + h) % self.L_rain - h
        h = self.L_wind / 2
        self.wind += -cv * dt
        self.wind = (self.wind + h) % self.L_wind - h

    @staticmethod
    def _segments(rel, rv, cam, k, max_len, color, alpha):
        n = len(rel)
        speed = np.linalg.norm(rv, axis=1, keepdims=True) + 1e-4
        kk = np.minimum(k, max_len / speed)
        head = rel + cam
        out = np.zeros((n * 2, 7), np.float32)
        out[0::2, 0:3] = head
        out[1::2, 0:3] = head - rv * kk
        out[0::2, 3:6] = color
        out[1::2, 3:6] = color
        out[0::2, 6] = alpha
        return out, head

    def render_data(self, cam, cam_vel, wind_amount, thrust, cars=(), rooms=(), boxes=(), rain_amount=1.0,
                    cloud_y=1e9):
        """cars: (x0, y0, z0, x1, y1, z1) elevator cars, free of rain and wind streaks.
        rooms: (x0, z0, x1, z1) footprints of nearby shops; no rain below their ceilings.
        boxes: (x0, y0, z0, x1, y1, z1) volumes kept dry (towers, metro cars). Never rains underground,
        nor above the cloud layer; rain_amount (0 dry .. ~1.6 downpour) scales the streaks."""
        cam = np.asarray(cam, np.float32)
        cv = np.asarray(cam_vel, np.float32)
        fade = 1.0 - np.max(np.abs(self.rain), axis=1) / (self.L_rain / 2)
        rain, head = self._segments(self.rain, self.rain_v - cv, cam, 0.03, 6.0,
                                    np.array([0.55, 0.65, 0.85], np.float32), 0.3 * fade * rain_amount)
        # no rain inside the towers, the elevator cars, shops or metro cars
        inside = _in_boxes(head, cars) | _in_boxes(head, boxes)
        low = head[:, 1] < C.SHOP_H
        for x0, z0, x1, z1 in rooms:
            inside |= low & (head[:, 0] > x0) & (head[:, 0] < x1) & (head[:, 2] > z0) & (head[:, 2] < z1)
        inside |= (head[:, 1] < 0.0) | (head[:, 1] > cloud_y)
        rain[0::2, 6][inside] = 0.0
        parts = [rain]
        if wind_amount > 0.01:
            fade = 1.0 - np.max(np.abs(self.wind), axis=1) / (self.L_wind / 2)
            t = min(thrust, 1.0) * 0.6
            color = np.array([0.8, 0.85, 1.0], np.float32) * (1.0 - t) + np.array([1.0, 0.5, 0.15], np.float32) * t
            rv = np.broadcast_to(-cv, self.wind.shape)
            wind, head = self._segments(self.wind, rv, cam, 0.06, 10.0, color, 0.6 * wind_amount * fade)
            wind[0::2, 6][_in_boxes(head, cars)] = 0.0
            parts.append(wind)
        return np.concatenate(parts)
