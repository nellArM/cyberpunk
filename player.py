"""First-person controller with AABB collision, free fall, rocket boots, a wingsuit and a grapple.

The boots also give short bursts on demand: a double jump (Q) and a dash (Ctrl), sharing a
few charges that come back one per cooldown. Ability numbers come from `stats` (see
progress.py; the defaults are the un-upgraded values).
"""
import math

import config as C
import progress
from collision import overlaps

BOOT_OFF, BOOT_BRAKING, BOOT_HOVER, BOOT_LANDED = 0, 1, 2, 3
BOOT_NAMES = {BOOT_OFF: "待命", BOOT_BRAKING: "噴射煞車", BOOT_HOVER: "緩降中", BOOT_LANDED: "著陸"}

GLIDE_STALL = 8.0                      # the wingsuit folds below this horizontal speed (e.g. after hitting a wall)
GRAPPLE_SPEED, GRAPPLE_ACCEL = 45.0, 60.0   # pull acceleration scales with the (upgradable) pull speed
BURST_TIME = 0.25                      # boot flame of a dash / double jump
DASH_TIME = 0.3                        # no walking drag and no gravity while dashing
GLIDE_DASH = 15.0                      # a dash in the wingsuit adds this much speed


def _approach(v, target, step):
    if v < target:
        return min(v + step, target)
    return max(v - step, target)


class Player:
    HALF_W = 0.3
    HEIGHT = 1.8
    EYE = 1.62
    STEP = 0.45            # max stair step the controller climbs / snaps down

    def __init__(self, pos, yaw=0.0):
        self.stats = progress.base_stats()
        self.wind = (0.0, 0.0)             # gusts pushing the wingsuit (set by the game in storms)
        self.reset(pos, yaw)

    def reset(self, pos, yaw=0.0, pitch=0.0):
        self.pos = [float(v) for v in pos]
        self.vel = [0.0, 0.0, 0.0]
        self.yaw = yaw
        self.pitch = pitch
        self.grounded = False
        self.boot = BOOT_OFF
        self.thrust = 0.0
        self.land_timer = 0.0
        self.support = 0.0
        self.events = []
        self.glide = False
        self.grapple = None                # anchor point while the hook pulls
        self._g_best, self._g_timer = 0.0, 0.0
        self.charges = self.stats["boost_charges"]
        self.recharge = 0.0                # until the next charge comes back
        self.burst = 0.0                   # boot flame of the last dash / double jump
        self.burst_push = (0.0, 0.0)       # horizontal direction of that burst (flame goes the other way)
        self.dash_t = 0.0

    # ---------------------------------------------------------------- view
    def look(self, dx, dy):
        self.yaw = (self.yaw + dx * C.MOUSE_SENS) % (2 * math.pi)
        self.pitch = max(-1.55, min(1.55, self.pitch - dy * C.MOUSE_SENS))

    def eye(self):
        return (self.pos[0], self.pos[1] + self.EYE, self.pos[2])

    @property
    def height_above_ground(self):
        return self.pos[1] - self.support

    @property
    def speed(self):
        return math.sqrt(self.vel[0] ** 2 + self.vel[1] ** 2 + self.vel[2] ** 2)

    # ---------------------------------------------------------------- abilities
    def toggle_glide(self):
        """Open / fold the wingsuit; returns whether it is open now."""
        if self.glide:
            self.glide = False
            return False
        if self.grounded or self.grapple is not None or self.height_above_ground < self.stats["glide_min_h"]:
            return False
        self.glide = True
        self.boot = BOOT_OFF
        fx, fz = math.sin(self.yaw), -math.cos(self.yaw)
        hs = math.hypot(self.vel[0], self.vel[2])
        if hs < 15.0:                                  # kick off forward
            self.vel[0], self.vel[2] = fx * 15.0, fz * 15.0
        return True

    def fire_grapple(self, anchor):
        self.grapple = tuple(anchor)
        self.glide = False
        self.boot = BOOT_OFF
        self.grounded = False
        self._g_best, self._g_timer = self._grapple_dist(), 0.0

    def release_grapple(self):
        self.grapple = None

    def _use_charge(self):
        self.charges -= 1
        if self.recharge <= 0.0:
            self.recharge = self.stats["boost_cooldown"]

    def double_jump(self):
        """Q: an upward burst in mid-air. Returns "" or why it did not fire (ground / busy / empty)."""
        if self.grounded:
            return "ground"
        if self.glide or self.grapple is not None:
            return "busy"
        if self.charges < 1:
            return "empty"
        self._use_charge()
        self.vel[1] = max(self.vel[1], 0.0) + self.stats["jump2_speed"]
        self.boot = BOOT_OFF                                   # re-arms for the next fall
        self.burst, self.burst_push = BURST_TIME, (0.0, 0.0)
        self.events.append("jump2")
        return ""

    def dash(self):
        """Ctrl: a horizontal burst where you look (in the wingsuit: extra speed)."""
        if self.grapple is not None:
            return "busy"
        if self.charges < 1:
            return "empty"
        self._use_charge()
        fx, fz = math.sin(self.yaw), -math.cos(self.yaw)
        v = self.vel
        if self.glide:
            hs = math.hypot(v[0], v[2])
            dx, dz = (v[0] / hs, v[2] / hs) if hs > 1e-3 else (fx, fz)
            v[0], v[2] = dx * (hs + GLIDE_DASH), dz * (hs + GLIDE_DASH)
            fx, fz = dx, dz
        else:
            s = self.stats["dash_speed"]
            v[0], v[2] = fx * s, fz * s
            if not self.grounded:
                v[1] = max(v[1], 0.0)
            self.dash_t = DASH_TIME
            self.boot = BOOT_OFF
        self.burst, self.burst_push = BURST_TIME, (fx, fz)
        self.events.append("dash")
        return ""

    def _tick_boost(self, dt):
        top = self.stats["boost_charges"]
        if self.charges < top:
            self.recharge -= dt
            if self.recharge <= 0.0:
                self.charges += 1
                self.recharge = self.stats["boost_cooldown"] if self.charges < top else 0.0
        else:
            self.charges, self.recharge = top, 0.0
        self.burst = max(0.0, self.burst - dt)
        self.dash_t = max(0.0, self.dash_t - dt)

    def _grapple_dist(self):
        ax, ay, az = self.grapple
        return math.sqrt((ax - self.pos[0]) ** 2 + (ay - 1.0 - self.pos[1]) ** 2 + (az - self.pos[2]) ** 2)

    def _pull(self, dt):
        """Reel in toward the anchor (feet end up just below it)."""
        ax, ay, az = self.grapple
        d = (ax - self.pos[0], ay - 1.0 - self.pos[1], az - self.pos[2])
        dist = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        speed = self.stats["grapple_speed"]
        accel = GRAPPLE_ACCEL * speed / GRAPPLE_SPEED
        want = min(speed, dist * 4.0)
        tgt = [c / max(dist, 1e-6) * want for c in d]
        dv = [t - v for t, v in zip(tgt, self.vel)]
        dl = math.sqrt(sum(c * c for c in dv))
        if dl > accel * dt:
            dv = [c / dl * accel * dt for c in dv]
        for i in range(3):
            self.vel[i] += dv[i]

    def _glide(self, dt):
        """Wingsuit: fly where you look; diving trades height for speed, pulling up the reverse."""
        v = self.vel
        sp = math.sin(self.pitch)
        fx, fz = math.sin(self.yaw), -math.cos(self.yaw)
        hs = math.hypot(v[0], v[2])
        target = max(18.0, min(self.stats["glide_max"], 35.0 - 30.0 * sp))
        hs = _approach(hs, target, (14.0 if target > hs else 8.0) * dt)
        dx, dz = (v[0] / max(hs, 1e-6), v[2] / max(hs, 1e-6)) if hs > 1e-3 else (fx, fz)
        k = min(1.0, 2.5 * dt)                         # the suit turns toward the view
        dx, dz = dx + (fx - dx) * k, dz + (fz - dz) * k
        dl = math.hypot(dx, dz) or 1.0
        v[0], v[2] = dx / dl * hs + self.wind[0] * dt, dz / dl * hs + self.wind[1] * dt   # gusts drift you
        if sp > 0.05 and hs > 28.0:
            vy = min(6.0, (hs - 28.0) * 0.35) * min(1.0, sp * 3.0)     # flare: climb a little
        else:
            vy = -self.stats["glide_sink"] - 22.0 * max(0.0, -sp)
        v[1] = _approach(v[1], vy, 15.0 * dt)

    # ---------------------------------------------------------------- simulation
    def update(self, dt, inp, world, dyn_boxes=()):
        self._tick_boost(dt)
        if self.grapple is not None or self.glide:
            self._special(dt, world, dyn_boxes)
            return
        vel = self.vel
        # --- horizontal intent (not while a dash carries you)
        fx, fz = math.sin(self.yaw), -math.cos(self.yaw)
        rx, rz = math.cos(self.yaw), math.sin(self.yaw)
        mf = inp.get("forward", 0) - inp.get("back", 0)
        mr = inp.get("right", 0) - inp.get("left", 0)
        wx, wz = fx * mf + rx * mr, fz * mf + rz * mr
        wl = math.hypot(wx, wz)
        if wl > 0:
            speed = self.stats["run_speed"] if inp.get("run") else C.WALK_SPEED
            wx, wz = wx / wl * speed, wz / wl * speed
        accel = C.GROUND_ACCEL if self.grounded else C.AIR_ACCEL * (2.5 if self.boot != BOOT_OFF else 1.0)
        dvx, dvz = wx - vel[0], wz - vel[2]
        dl = math.hypot(dvx, dvz)
        if dl > accel * dt:
            dvx, dvz = dvx / dl * accel * dt, dvz / dl * accel * dt
        if self.dash_t <= 0.0:
            vel[0] += dvx
            vel[2] += dvz

        if inp.get("jump") and self.grounded:
            vel[1] = C.JUMP_SPEED
            self.grounded = False

        # --- rocket boots state machine
        self.support = world.support_height(self.pos[0], self.pos[2], self.pos[1], self.HALF_W, dyn_boxes)
        h = self.pos[1] - self.support
        fall = -vel[1]
        target_thrust = 0.0
        if self.boot == BOOT_OFF and not self.grounded and fall > C.BOOT_MIN_SPEED:
            if h <= fall * fall / (2.0 * C.BOOT_BRAKE_DECEL) + C.BOOT_HOVER_ALT:
                self.boot = BOOT_BRAKING
                self.events.append("boot_on")

        if self.boot == BOOT_BRAKING:
            room = max(h - C.BOOT_HOVER_ALT * 0.5, 0.5)
            need = fall * fall / (2.0 * room) if fall > 0 else 0.0
            decel = min(max(C.BOOT_BRAKE_DECEL, need), 120.0)
            vel[1] += decel * dt
            target_thrust = min(1.5, decel / C.BOOT_BRAKE_DECEL)
            if vel[1] >= -C.BOOT_HOVER_SPEED:
                vel[1] = -C.BOOT_HOVER_SPEED
                self.boot = BOOT_HOVER
                self.events.append("hover")
        elif self.boot == BOOT_HOVER:
            vel[1] = _approach(vel[1], -C.BOOT_HOVER_SPEED, 20.0 * dt)
            target_thrust = 0.6
            if h > C.BOOT_HOVER_ALT * 3:          # drifted off a ledge: let it free-fall and re-arm
                self.boot = BOOT_OFF
        else:
            if self.boot == BOOT_LANDED:
                self.land_timer -= dt
                target_thrust = 0.5 * max(self.land_timer, 0.0) / C.BOOT_LAND_FADE
                if self.land_timer <= 0.0:
                    self.boot = BOOT_OFF
            if self.dash_t <= 0.0 or self.grounded:
                vel[1] -= C.GRAVITY * dt
            if vel[1] < 0.0:                       # quadratic air drag -> terminal velocity
                vel[1] = min(vel[1] + C.GRAVITY * (vel[1] / C.TERMINAL_VELOCITY) ** 2 * dt, 0.0)
        if self.burst > 0.0:
            target_thrust = max(target_thrust, 1.3)

        self.thrust += (target_thrust - self.thrust) * min(1.0, dt * 12.0)

        # --- integrate with collision
        self._move(dt, world, dyn_boxes)

        if self.grounded and self.boot in (BOOT_BRAKING, BOOT_HOVER):
            self.boot = BOOT_LANDED
            self.land_timer = C.BOOT_LAND_FADE
            self.events.append("landed")

    def _special(self, dt, world, dyn_boxes):
        """Grapple pull or wingsuit flight: no walking input, no boots."""
        self.support = world.support_height(self.pos[0], self.pos[2], self.pos[1], self.HALF_W, dyn_boxes)
        self.thrust += ((1.3 if self.burst > 0.0 else 0.0) - self.thrust) * min(1.0, dt * 12.0)
        if self.grapple is not None:
            self._pull(dt)
        else:
            self._glide(dt)
        self.grounded = False                                 # no step climbing / stair gluing in flight
        self._move(dt, world, dyn_boxes)
        if self.grapple is not None:
            dist = self._grapple_dist()
            if dist < self._g_best - 0.3:
                self._g_best, self._g_timer = dist, 0.0
            else:
                self._g_timer += dt
            if dist < 1.5 or self._g_timer > 0.6:          # arrived, or stuck against something
                self.grapple = None
                self.vel = [c * 0.3 for c in self.vel]
                self.events.append("grapple_done")
        elif self.grounded:
            self.glide = False
            self.vel[0] *= 0.3
            self.vel[2] *= 0.3
            self.events.append("landed")
        elif math.hypot(self.vel[0], self.vel[2]) < GLIDE_STALL:
            self.glide = False                                # stalled (hit a wall): free fall, boots armed
            self.events.append("stall")

    def _move(self, dt, world, dyn_boxes):
        hw, ht = self.HALF_W, self.HEIGHT
        p, v = self.pos, self.vel
        delta = [v[0] * dt, v[1] * dt, v[2] * dt]
        x0 = min(p[0], p[0] + delta[0]) - hw - 0.5
        x1 = max(p[0], p[0] + delta[0]) + hw + 0.5
        y0 = min(p[1], p[1] + delta[1]) - 0.5
        y1 = max(p[1], p[1] + delta[1]) + ht + 0.5
        z0 = min(p[2], p[2] + delta[2]) - hw - 0.5
        z1 = max(p[2], p[2] + delta[2]) + hw + 0.5
        boxes = world.query(x0, y0, z0, x1, y1, z1)
        boxes += [b for b in dyn_boxes if overlaps(b, x0, y0, z0, x1, y1, z1)]

        steps = max(1, int(math.ceil(max(abs(d) for d in delta) / 0.4)))
        step = [d / steps for d in delta]
        was_grounded = self.grounded
        y_start = p[1]
        self.grounded = False
        for _ in range(steps):
            for axis in (0, 2, 1):
                if step[axis] == 0.0:
                    continue
                p[axis] += step[axis]
                for b in boxes:
                    if overlaps(b, p[0] - hw, p[1], p[2] - hw, p[0] + hw, p[1] + ht, p[2] + hw):
                        if axis != 1 and was_grounded and p[1] < b[4] <= p[1] + self.STEP and not any(
                                overlaps(o, p[0] - hw, b[4], p[2] - hw, p[0] + hw, b[4] + ht, p[2] + hw)
                                for o in boxes):
                            p[1] = b[4]                    # climb a stair step / low ledge
                            continue
                        if axis == 1:
                            if step[1] < 0:
                                p[1] = b[4]
                                self.grounded = True
                            else:
                                p[1] = b[1] - ht
                        elif step[axis] > 0:
                            p[axis] = b[axis] - hw - 1e-4
                        else:
                            p[axis] = b[axis + 3] + hw + 1e-4
                        v[axis] = 0.0
                        step[axis] = 0.0
                        break
            if p[1] <= 0.0 and world.ground_solid(p[0], p[2], y_start):   # street level (not over a metro stairwell)
                p[1] = 0.0
                if v[1] < 0:
                    v[1] = 0.0
                step[1] = 0.0
                self.grounded = True
        # walking down stairs: stay glued to a surface just below instead of hopping
        if was_grounded and not self.grounded and v[1] <= 0.0:
            top = 0.0 if (p[1] <= self.STEP and world.ground_solid(p[0], p[2], y_start)) else -1e9
            for b in boxes:
                if (b[3] > p[0] - hw and b[0] < p[0] + hw and b[5] > p[2] - hw and b[2] < p[2] + hw
                        and p[1] - self.STEP <= b[4] <= p[1] + 1e-6 and b[4] > top):
                    top = b[4]
            if top > -1e8:
                p[1] = top
                v[1] = 0.0
                self.grounded = True
        limit = C.CITY_BLOCKS * C.BLOCK_PITCH + 300.0
        p[0] = max(-limit, min(limit, p[0]))
        p[2] = max(-limit, min(limit, p[2]))
