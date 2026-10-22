"""Street-level traffic (numpy, vectorised): cars that follow each other, obey the
traffic lights and stop for the player. Also builds the traffic-signal posts.

Signal timing is shared with the shader (shaders.BOX_FS, kind K_SIGNAL): each
intersection (ix, iz) runs a SIGNAL_CYCLE where x-bound traffic gets green+yellow
first, then z-bound traffic, shifted by signal_offset(ix, iz).
"""
import numpy as np

import config as C
from geometry import box, BOX_FLOATS

G, Y = C.SIGNAL_GREEN, C.SIGNAL_YELLOW
GREEN, YELLOW, RED = 0, 1, 2

# car types: length, width, body height, cabin height, cabin length fraction, speed range
_TYPES = (
    (4.6, 1.9, 0.7, 0.5, 0.5, (14.0, 20.0)),     # sedan
    (5.2, 2.0, 1.0, 0.7, 0.72, (12.0, 17.0)),    # van
    (11.0, 2.5, 1.7, 1.0, 0.92, (10.0, 13.0)),   # bus
)


def signal_offset(ix, iz):
    return np.mod(np.asarray(ix) * 3 + np.asarray(iz) * 5, 6) * 4.0


def signal_state(time, axis, ix, iz):
    """GREEN / YELLOW / RED for traffic moving along `axis` (0 = x) at intersection (ix, iz)."""
    ph = np.mod(time + signal_offset(ix, iz), C.SIGNAL_CYCLE)
    q = np.where(np.asarray(axis) == 0, ph, ph - (G + Y))
    return np.where((q >= 0) & (q < G), GREEN, np.where((q >= G) & (q < G + Y), YELLOW, RED))


def _roads():
    """Road indices r (centerline 40 + 80 r) inside the traffic area."""
    n = C.CITY_BLOCKS + 1
    return [r for r in range(-n, n) if abs(40 + 80 * r) < C.GROUND_TRAFFIC_EXTENT]


def build_signals():
    """Four signal posts per intersection; NE/SW heads govern x traffic, NW/SE govern z."""
    boxes, cols = [], []
    roads = _roads()
    for ix in roads:
        for iz in roads:
            X, Z = 40.0 + 80 * ix, 40.0 + 80 * iz
            if max(abs(X), abs(Z)) < C.PLAZA_HALF:
                continue
            off = int(signal_offset(ix, iz)) // 4
            for sx in (-1, 1):
                for sz in (-1, 1):
                    px, pz = X + sx * 9.3, Z + sz * 9.3
                    axis = 0 if sx * sz > 0 else 1
                    boxes.append(box(px, 0.0, pz, 0.22, 5.4, 0.22, C.K_PANEL, 0.5))
                    boxes.append(box(px, 4.0, pz, 0.5, 1.4, 0.5, C.K_SIGNAL, 0.0, axis + 2 * off))
                    cols.append((px - 0.15, 0.0, pz - 0.15, px + 0.15, 5.4, pz + 0.15))
    return boxes, cols


class GroundTraffic:
    BRAKE = 6.0          # comfortable deceleration used to plan stops
    MAX_BRAKE = 12.0
    ACCEL = 4.0
    MIN_GAP = 2.0

    def __init__(self, rng, count=C.GROUND_TRAFFIC_COUNT):
        E = C.GROUND_TRAFFIC_EXTENT
        roads = [r for r in _roads() if r not in (-1, 0)]       # those two roads run under the tower plaza
        lanes = [(a, r, s, m) for a in (0, 1) for r in roads for s in (-1, 1) for m in (2.0, 6.0)]
        per, rest = divmod(count, len(lanes))
        cols = {k: [] for k in ("axis", "road", "dir", "c", "lane", "t")}
        for li, (a, r, s, m) in enumerate(lanes):
            n = per + (1 if li < rest else 0)
            if n == 0:
                continue
            spacing = 2 * E / n
            t = -E + spacing * (np.arange(n) + 0.5) + rng.uniform(-0.3, 0.3, n) * spacing
            # drive on the right: +x traffic uses the +z side, +z traffic uses the -x side
            c = 40.0 + 80.0 * r + s * m * (1.0 if a == 0 else -1.0)
            for k, v in (("axis", a), ("road", r), ("dir", s), ("c", c), ("lane", li)):
                cols[k].append(np.full(n, v))
            cols["t"].append(t)
        self.axis = np.concatenate(cols["axis"]).astype(np.int64)
        self.road = np.concatenate(cols["road"]).astype(np.int64)
        self.dir = np.concatenate(cols["dir"]).astype(np.float64)
        self.lane_c = np.concatenate(cols["c"]).astype(np.float64)
        self.lane = np.concatenate(cols["lane"]).astype(np.int64)
        self.t = np.concatenate(cols["t"])
        self.count = n = len(self.t)

        kind = np.digitize(rng.random(n), [0.65, 0.92])
        spec = np.array([t[:5] for t in _TYPES])[kind]
        self.L, self.W, self.body_h, self.cab_h, self.cab_f = spec.T
        lo = np.array([t[5][0] for t in _TYPES])[kind]
        hi = np.array([t[5][1] for t in _TYPES])[kind]
        self.vmax = rng.uniform(lo, hi)
        self.v = self.vmax * rng.uniform(0.3, 1.0, n)
        self.braking = np.zeros(n, bool)

        # 3 boxes per car: body (lights), cabin (glass), chassis (dark)
        self.data = np.zeros((n * 3, BOX_FLOATS), dtype="f4")
        D = self.data.reshape(n, 3, BOX_FLOATS)
        ax0 = self.axis == 0
        hue = rng.choice(C.NEON_HUES, n)
        seed = rng.uniform(0, 1000, n)
        parts = (
            (0.3, self.body_h, self.L, self.W, C.K_VEHICLE),
            (0.3 + self.body_h, self.cab_h, self.L * self.cab_f, self.W * 0.9, C.K_VEHICLE),
            (0.0, np.full(n, 0.35), self.L - 0.5, self.W - 0.1, C.K_PANEL),
        )
        for i, (base, height, length, width, kd) in enumerate(parts):
            D[:, i, 1] = base
            D[:, i, 3] = np.where(ax0, length, width)
            D[:, i, 4] = height
            D[:, i, 5] = np.where(ax0, width, length)
            D[:, i, 6] = seed
            D[:, i, 7] = kd
            D[:, i, 8] = hue if kd == C.K_VEHICLE else 0.0
        self.top = 0.3 + self.body_h + self.cab_h
        self._write()

    # ------------------------------------------------------------------ simulation
    def update(self, dt, time, player_pos=None):
        if dt <= 0:
            return
        s, t, L = self.dir, self.t, self.L
        front = t + s * L / 2
        # next stop line ahead (a line passed by < 0.5 m still counts, so overshoot stays stopped)
        k = np.where(s > 0,
                     np.ceil((front - 0.5 - (40.0 - C.STOP_LINE)) / 80.0),
                     np.floor((front + 0.5 - (40.0 + C.STOP_LINE)) / 80.0))
        line = 40.0 + 80.0 * k - s * C.STOP_LINE
        dist = s * (line - front)
        k = k.astype(np.int64)
        ix = np.where(self.axis == 0, k, self.road)
        iz = np.where(self.axis == 0, self.road, k)
        state = signal_state(time, self.axis, ix, iz)
        stop = (state == RED) | ((state == YELLOW) & (dist > 8.0))
        gap = np.where(stop, dist + self.MIN_GAP, np.inf)

        # car following: leader = next car further along in the same lane
        along = s * t
        order = np.lexsort((along, self.lane))
        lane_s, along_s, L_s = self.lane[order], along[order], L[order]
        lead = np.full(self.count, np.inf)
        same = lane_s[1:] == lane_s[:-1]
        lead[:-1] = np.where(same, along_s[1:] - along_s[:-1] - (L_s[1:] + L_s[:-1]) / 2, np.inf)
        gap_lead = np.empty(self.count)
        gap_lead[order] = lead
        gap = np.minimum(gap, gap_lead)

        # yield to a pedestrian (the player) standing in the lane ahead
        if player_pos is not None and player_pos[1] < 3.0:
            px, pz = player_pos[0], player_pos[2]
            p_along = np.where(self.axis == 0, px, pz)
            p_lat = np.where(self.axis == 0, pz, px)
            ahead = s * (p_along - t) - L / 2 - 0.4
            hit = (np.abs(p_lat - self.lane_c) < self.W / 2 + 0.7) & (ahead > -1.0) & (ahead < 30.0)
            gap = np.where(hit, np.minimum(gap, np.maximum(ahead, 0.0)), gap)

        v_des = np.minimum(self.vmax, np.sqrt(2.0 * self.BRAKE * np.maximum(gap - self.MIN_GAP, 0.0)))
        self.braking = (v_des < self.v - 0.3) | ((self.v < 0.5) & (v_des < 0.5))
        self.v = np.maximum(self.v + np.clip(v_des - self.v, -self.MAX_BRAKE * dt, self.ACCEL * dt), 0.0)
        E = C.GROUND_TRAFFIC_EXTENT
        self.t = np.mod(t + s * self.v * dt + E, 2 * E) - E
        self._write()

    def _write(self):
        n = self.count
        D = self.data.reshape(n, 3, BOX_FLOATS)
        ax0 = self.axis == 0
        s, t, c = self.dir, self.t, self.lane_c
        cab = t - s * (self.L * (1.0 - self.cab_f) * 0.3)          # cabin sits slightly to the rear
        for i, along in ((0, t), (1, cab), (2, t)):
            D[:, i, 0] = np.where(ax0, along, c)
            D[:, i, 2] = np.where(ax0, c, along)
        D[:, 0, 9] = s * np.where(self.braking, 2.0, 1.0)          # lights: direction, brake flag
        D[:, 1, 9] = 0.0

    def colliders_near(self, pos, radius=20.0):
        D = self.data.reshape(self.count, 3, BOX_FLOATS)
        x, z, sx, sz = D[:, 0, 0], D[:, 0, 2], D[:, 0, 3], D[:, 0, 5]
        idx = np.flatnonzero((np.abs(x - pos[0]) < radius) & (np.abs(z - pos[2]) < radius))
        return [(float(x[i] - sx[i] / 2), 0.0, float(z[i] - sz[i] / 2),
                 float(x[i] + sx[i] / 2), float(self.top[i]), float(z[i] + sz[i] / 2)) for i in idx]
