"""Time of day and weather.

The sun circles east -> zenith -> west (slightly to the south); `day` is the daylight
factor from its elevation and `dusk` peaks while it sits on the horizon. Weather kinds
have target parameters (cloud cover, rain, fog, storm) that the current values ease
toward, so changes blend over ~20 s. In auto mode the weather changes every few minutes.
Storms throw lightning (a flash, then thunder a moment later).
"""
import math
import random

from i18n import tr

KINDS = ("晴", "多雲", "雨", "暴雨", "霧")
CLEAR, CLOUDY, RAIN, STORM, FOG = range(5)
# per kind: cloud cover, rain amount (streak alpha scale), fog, storm (lightning)
TARGETS = ((0.08, 0.0, 0.0, 0.0), (0.7, 0.0, 0.12, 0.0), (0.85, 1.0, 0.25, 0.0),
           (1.0, 1.6, 0.35, 1.0), (0.45, 0.0, 1.0, 0.0))
NEXT = {CLEAR: ((CLEAR, 0.3), (CLOUDY, 0.5), (FOG, 0.2)),
        CLOUDY: ((CLEAR, 0.35), (RAIN, 0.45), (FOG, 0.2)),
        RAIN: ((CLOUDY, 0.4), (STORM, 0.35), (RAIN, 0.25)),
        STORM: ((RAIN, 0.6), (CLOUDY, 0.4)),
        FOG: ((CLEAR, 0.5), (CLOUDY, 0.5))}
SPEEDS = ((1.0 / 60.0, "正常"), (1.0, "快轉"), (0.0, "暫停"))   # game hours per real second
EASE = 8.0                                                      # seconds (time constant)


def _smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


class Environment:
    def __init__(self, hour=20.0, kind=RAIN, seed=None):
        self.rng = random.Random(seed)
        self.hour = hour
        self.speed_i = 0
        self.auto = True
        self.kind = kind
        self.cloud, self.rain, self.fog, self.storm = TARGETS[kind]
        self.wet = 1.0 if self.rain > 0.1 else 0.0
        self.flash = 0.0
        self.next_change = self.rng.uniform(180.0, 360.0)
        self._flicker = None                    # pending second flicker (seconds)
        self._thunder = []                      # [seconds until, strength]

    # ---------------------------------------------------------------- sky geometry
    @property
    def sun(self):
        a = (self.hour - 6.0) / 24.0 * 2.0 * math.pi
        x, y, z = math.cos(a), math.sin(a) * 0.92, 0.35
        n = math.sqrt(x * x + y * y + z * z)
        return x / n, y / n, z / n

    @property
    def day(self):
        return _smoothstep(-0.08, 0.25, self.sun[1])

    @property
    def dusk(self):
        y = self.sun[1]
        return math.exp(-(y / 0.12) ** 2) if y > -0.25 else 0.0

    # ---------------------------------------------------------------- control
    @property
    def speed_label(self):
        return tr(SPEEDS[self.speed_i][1])

    def cycle_speed(self):
        self.speed_i = (self.speed_i + 1) % len(SPEEDS)

    def shift_hours(self, h):
        self.hour = (self.hour + h) % 24.0

    def cycle_weather(self):
        """auto -> clear -> cloudy -> rain -> storm -> fog -> auto"""
        if self.auto:
            self.auto, self.kind = False, CLEAR
        elif self.kind == FOG:
            self.auto = True
            self.next_change = self.rng.uniform(180.0, 360.0)
        else:
            self.kind += 1

    def set_weather(self, kind, auto=False):
        self.kind, self.auto = kind, auto

    # ---------------------------------------------------------------- simulation
    def _pick_next(self):
        opts = list(NEXT[self.kind])
        if 4.0 <= self.hour <= 8.0:                               # misty mornings
            opts = [(k, w * (2.0 if k == FOG else 1.0)) for k, w in opts]
        r = self.rng.random() * sum(w for _, w in opts)
        for k, w in opts:
            r -= w
            if r <= 0:
                return k
        return opts[-1][0]

    def update(self, dt):
        """Advance; returns thunder strengths (0..1) to play this frame."""
        self.hour = (self.hour + SPEEDS[self.speed_i][0] * dt) % 24.0
        if self.auto:
            self.next_change -= dt
            if self.next_change <= 0.0:
                self.kind = self._pick_next()
                self.next_change = self.rng.uniform(180.0, 360.0)
        k = 1.0 - math.exp(-dt / EASE)
        tc, tr, tf, ts = TARGETS[self.kind]
        self.cloud += (tc - self.cloud) * k
        self.rain += (tr - self.rain) * k
        self.fog += (tf - self.fog) * k
        self.storm += (ts - self.storm) * k
        if self.rain > 0.1:
            self.wet = min(1.0, self.wet + dt / 30.0 * self.rain)
        else:
            self.wet = max(0.0, self.wet - dt / 180.0)
        # lightning
        self.flash *= math.exp(-dt * 9.0)
        if self._flicker is not None:
            self._flicker -= dt
            if self._flicker <= 0.0:
                self.flash = max(self.flash, 0.7)
                self._flicker = None
        if self.storm > 0.5 and self.rng.random() < dt * 0.12 * self.storm:
            self.flash = 1.0
            if self.rng.random() < 0.4:
                self._flicker = self.rng.uniform(0.08, 0.2)
            self._thunder.append([self.rng.uniform(0.5, 3.0), self.rng.uniform(0.5, 1.0)])
        out = []
        for t in self._thunder:
            t[0] -= dt
            if t[0] <= 0.0:
                out.append(t[1])
        self._thunder = [t for t in self._thunder if t[0] > 0.0]
        return out

    # ---------------------------------------------------------------- outputs
    def uniforms(self):
        sx, sy, sz = self.sun
        return {"u_sun": (sx, sy, sz, self.day), "u_env": (self.dusk, self.cloud, self.fog, self.flash),
                "u_wet": self.wet}

    def label(self):
        h = int(self.hour)
        m = int((self.hour - h) * 60.0)
        mode = "自動" if self.auto else "手動"
        speed = "" if self.speed_i == 0 else f" · {self.speed_label}"
        return tr("{h:02d}:{m:02d}  {kind}（{mode}）", h=h, m=m, kind=KINDS[self.kind], mode=mode) + speed
