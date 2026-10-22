"""Pedestrians (numpy, vectorised): sidewalk walkers that circle city blocks and cross at
zebra crossings on the signal phase, people strolling around the tower plaza, and park
walkers circling the walking ring of a park / plaza block (ring walkers that never cross).

Everyone walks along the x or z axis only, so the boxy people never need rotating.
Signal timing comes from traffic.signal_offset / config.SIGNAL_*, the same phases the
cars and the signal-head shader use: a pedestrian starts crossing 1-2 s after the cars
on the crossed road get red, and walks fast enough to clear the road before they get green.
"""
import math

import numpy as np

import config as C
from geometry import BOX_FLOATS
from traffic import signal_offset

WALK, IDLE, WAIT, CROSS = 0, 1, 2, 3
PARTS = 8
CROSS_TIME = 9.5                   # seconds to cross; the crossed road stays red for G + Y = 12 s
PLAZA_IN, PLAZA_OUT = 48.0, 106.0  # plaza walkers stay in this square ring around the tower
PLAZA_KEEP_OUT = 47.0              # never route through max(|x|,|z|) < this (tower base, elevator rails)

# ring corners in order of the perimeter parameter s: (-,-) (+,-) (+,+) (-,+)
_CSX = np.array([-1, 1, 1, -1])
_CSZ = np.array([-1, -1, 1, 1])
# each side starts at corner k and runs along axis _AX with sign _AS
_AX = np.array([0, 1, 0, 1])
_AS = np.array([1, 1, -1, -1])


def person_boxes(x, y, z, fa, fsg, moving, phase, h, hue, seed, umb):
    """8 K_PED boxes per person standing at (x, y, z), facing +-x (fa=0) or +-z (fa=1).

    Legs and arms swing along the facing axis with the walk phase; umb (0/1) adds an
    umbrella held in the raised right hand (zero-sized boxes when 0).
    """
    m = len(x)
    out = np.zeros((m, PARTS, BOX_FLOATS), dtype="f4")
    if m == 0:
        return out.reshape(0, BOX_FLOATS)
    fx = np.where(fa == 0, fsg, 0.0)
    fz = np.where(fa == 1, fsg, 0.0)
    lx, lz = -fz, fx
    mv = np.asarray(moving, np.float64)
    sn = np.sin(phase)
    sw = sn * 0.22 * mv

    def put(p, off_f, off_l, y0, height, size_f, size_l, part):
        out[:, p, 0] = x + fx * off_f + lx * off_l
        out[:, p, 1] = y + y0
        out[:, p, 2] = z + fz * off_f + lz * off_l
        out[:, p, 3] = np.where(fa == 0, size_f, size_l)
        out[:, p, 4] = height
        out[:, p, 5] = np.where(fa == 0, size_l, size_f)
        out[:, p, 6] = seed
        out[:, p, 7] = C.K_PED
        out[:, p, 8] = hue
        out[:, p, 9] = part

    put(0, sw, 0.11, np.maximum(sn, 0) * 0.07 * mv, 0.85 * h, 0.17, 0.15, 0)        # legs
    put(1, -sw, -0.11, np.maximum(-sn, 0) * 0.07 * mv, 0.85 * h, 0.17, 0.15, 0)
    put(2, 0.0, 0.0, 0.85 * h, 0.6 * h, 0.26, 0.44, 1)                                # torso
    put(3, 0.0, 0.0, 1.47 * h, 0.27 * h, 0.25, 0.24, 2)                               # head
    put(4, -sw * 0.7, 0.29, 0.83 * h, 0.62 * h, 0.12, 0.12, 3)                        # arms
    put(5, np.where(umb > 0, 0.12, sw * 0.7), -0.29, np.where(umb > 0, 1.05 * h, 0.83 * h),
        np.where(umb > 0, 0.42 * h, 0.62 * h), 0.12, 0.12, 3)
    put(6, 0.0, 0.0, 2.02 * h, 0.07, 1.15 * umb, 1.15 * umb, 4)                      # umbrella
    put(7, 0.12, -0.29, 1.47 * h, 0.55 * h * umb, 0.04 * umb, 0.04 * umb, 5)
    return out.reshape(-1, BOX_FLOATS)


def _corner_index(sx, sz):
    return np.where(sz < 0, np.where(sx < 0, 0, 1), np.where(sx > 0, 2, 3))


def _valid_block(bi, bj):
    B = C.PED_BLOCKS
    return (np.abs(bi) <= B) & (np.abs(bj) <= B) & ~((np.abs(bi) <= 1) & (np.abs(bj) <= 1))


def _segment_hits_core(a0, a1, fixed):
    """Does an axis-aligned segment (running coordinate a0->a1, other coordinate fixed) enter the tower core?"""
    S = PLAZA_KEEP_OUT
    return abs(fixed) < S and max(a0, a1) > -S and min(a0, a1) < S


class Pedestrians:
    def __init__(self, rng, count=C.PED_COUNT, plaza_count=C.PED_PLAZA_COUNT, park_blocks=()):
        self.rng = rng
        n_park = len(park_blocks) * C.PARK_WALKERS
        sidewalk = count
        count += n_park                                # park walkers are ring walkers too
        self.ns, self.np_ = count, plaza_count
        n = self.n = count + plaza_count

        # --- sidewalk walkers
        B = C.PED_BLOCKS
        blocks = np.array([(i, j) for i in range(-B, B + 1) for j in range(-B, B + 1)
                           if not (abs(i) <= 1 and abs(j) <= 1)])
        pick = blocks[rng.integers(len(blocks), size=sidewalk)]
        if n_park:
            pick = np.concatenate([pick, np.repeat(np.array(list(park_blocks)), C.PARK_WALKERS, axis=0)])
        self.bi, self.bj = pick[:, 0].copy(), pick[:, 1].copy()
        # lane offset from the block center: inside the 29.5-32 m sidewalk, clear of corner poles at 30.7
        self.r = np.where(rng.random(count) < 0.5, rng.uniform(29.9, 30.3, count), rng.uniform(31.1, 31.7, count))
        self.cross_ok = np.ones(count, bool)
        self.r[sidewalk:] = rng.uniform(14.5, 19.5, n_park)        # the park's walking ring (13..21 m)
        self.cross_ok[sidewalk:] = False
        self.s = rng.uniform(0, 8 * self.r)
        self.d = rng.choice([-1.0, 1.0], count)
        self.state = np.full(count, WALK)
        self.timer = np.zeros(count)
        self.cx_axis = np.zeros(count, np.int64)      # crossing: 0 moves along x, 1 along z
        self.cx_sign = np.zeros(count)
        self.wsx = np.zeros(count)                    # corner signs while waiting / crossing
        self.wsz = np.zeros(count)
        self.cprog = np.zeros(count)
        self.cdist = np.zeros(count)

        # --- plaza strollers
        self.px = np.zeros(plaza_count)
        self.pz = np.zeros(plaza_count)
        for k in range(plaza_count):
            self.px[k], self.pz[k] = self._plaza_point()
        self.ptx, self.ptz = self.px.copy(), self.pz.copy()
        self.pmx, self.pmz = self.px.copy(), self.pz.copy()
        self.pleg = np.ones(plaza_count, np.int64)
        self.pstate = np.full(plaza_count, IDLE)
        self.ptimer = rng.uniform(0, 3, plaza_count)

        # --- shared per-person data
        self.speed = rng.uniform(1.1, 1.7, n)
        self.h = rng.uniform(0.9, 1.1, n)
        self.hue = rng.choice(C.NEON_HUES, n)
        self.seed = rng.uniform(0, 1000, n)
        self.umbrella = (rng.random(n) < 0.4).astype(np.float64)
        self.phase = rng.uniform(0, 2 * math.pi, n)
        self.x = np.zeros(n)
        self.z = np.zeros(n)
        self.face_axis = np.zeros(n, np.int64)
        self.face_sign = np.ones(n)
        self.moving = np.zeros(n, bool)
        self.blocked_t = np.zeros(n)
        self.crossings = 0
        self._sidewalk_positions()
        self.x[count:], self.z[count:] = self.px, self.pz

    # ------------------------------------------------------------------ sidewalk geometry
    def _ring(self, idx):
        """World position and walking axis/sign (for d = +1) of sidewalk walkers idx on their ring."""
        r, s = self.r[idx], self.s[idx]
        side = np.floor(s / (2 * r)).astype(np.int64) % 4
        loc = s - side * 2 * r
        ax, sg = _AX[side], _AS[side]
        x = 80.0 * self.bi[idx] + r * _CSX[side] + np.where(ax == 0, sg * loc, 0.0)
        z = 80.0 * self.bj[idx] + r * _CSZ[side] + np.where(ax == 1, sg * loc, 0.0)
        return x, z, ax, sg

    def _sidewalk_positions(self):
        ns = self.ns
        idx = np.arange(ns)
        x, z, ax, sg = self._ring(idx)
        cr = self.state == CROSS
        x0 = 80.0 * self.bi + self.wsx * self.r
        z0 = 80.0 * self.bj + self.wsz * self.r
        x = np.where(cr & (self.cx_axis == 0), x0 + self.cx_sign * self.cprog, np.where(cr, x0, x))
        z = np.where(cr & (self.cx_axis == 1), z0 + self.cx_sign * self.cprog, np.where(cr, z0, z))
        self.x[:ns], self.z[:ns] = x, z
        walking = self.state == WALK
        fa = np.where(walking, ax, np.where((self.state == WAIT) | cr, self.cx_axis, self.face_axis[:ns]))
        fs = np.where(walking, sg * self.d, np.where((self.state == WAIT) | cr, self.cx_sign, self.face_sign[:ns]))
        self.face_axis[:ns], self.face_sign[:ns] = fa, fs

    # ------------------------------------------------------------------ plaza helpers
    def _plaza_point(self):
        rng = self.rng
        while True:
            x, z = rng.uniform(-PLAZA_OUT, PLAZA_OUT, 2)
            if PLAZA_IN < max(abs(x), abs(z)) < PLAZA_OUT:
                return x, z

    def _plaza_retarget(self, k):
        x, z = self.px[k], self.pz[k]
        for _ in range(20):
            tx, tz = self._plaza_point()
            if not _segment_hits_core(x, tx, z) and not _segment_hits_core(z, tz, tx):
                self.pmx[k], self.pmz[k] = tx, z               # x first
            elif not _segment_hits_core(z, tz, x) and not _segment_hits_core(x, tx, tz):
                self.pmx[k], self.pmz[k] = x, tz               # z first
            else:
                continue
            self.ptx[k], self.ptz[k] = tx, tz
            self.pleg[k] = 0
            self.pstate[k] = WALK
            return
        self.ptimer[k] = 1.0                                   # boxed in: wait and retry

    # ------------------------------------------------------------------ simulation
    def update(self, dt, time, player_pos=None):
        if dt <= 0:
            return
        rng, ns = self.rng, self.ns
        n = self.n

        # who is blocked by the player standing right in front of them
        blocked = np.zeros(n, bool)
        if player_pos is not None and player_pos[1] < 3.0:
            fx = np.where(self.face_axis == 0, self.face_sign, 0.0)
            fz = np.where(self.face_axis == 1, self.face_sign, 0.0)
            dx, dz = player_pos[0] - self.x, player_pos[2] - self.z
            ahead = dx * fx + dz * fz
            lat = np.abs(dx * fz - dz * fx)
            blocked = (ahead > 0.1) & (ahead < 1.2) & (lat < 0.6)
        self.blocked_t = np.where(blocked, self.blocked_t + dt, 0.0)
        turn = self.blocked_t > 2.0
        self.blocked_t[turn] = 0.0

        # ---- sidewalk walkers
        st = self.state
        sb = blocked[:ns]
        v = self.speed[:ns]
        walk = (st == WALK) & ~sb
        self.d[turn[:ns] & (st == WALK)] *= -1.0

        # occasional pause (window shopping)
        pause = walk & (rng.random(ns) < dt / 40.0)
        st[pause] = IDLE
        self.timer[pause] = rng.uniform(2.0, 6.0, int(pause.sum()))
        walk &= ~pause
        idle = st == IDLE
        self.timer[idle] -= dt
        st[idle & (self.timer <= 0)] = WALK

        # walk along the ring, detect corners
        r2 = 2 * self.r
        s_old = self.s
        s_new = s_old + self.d * v * dt
        k_old = np.where(self.d > 0, np.floor(s_old / r2), np.ceil(s_old / r2))
        k_new = np.where(self.d > 0, np.floor(s_new / r2), np.ceil(s_new / r2))
        corner = walk & (k_new != k_old)
        ck = k_new.astype(np.int64)                    # the corner passed sits at s = k_new * 2r
        ci = ck % 4
        csx, csz = _CSX[ci], _CSZ[ci]
        want = corner & self.cross_ok & (rng.random(ns) < C.PED_CROSS_P)
        along_x = rng.random(ns) < 0.5
        sign = np.where(along_x, csx, csz).astype(np.float64)
        nbi = np.where(along_x, self.bi + csx, self.bi)
        nbj = np.where(along_x, self.bj, self.bj + csz)
        go = want & _valid_block(nbi, nbj)
        self.s = np.where(walk, np.mod(s_new, 4 * r2), self.s)
        # start waiting at the corner
        self.s[go] = np.mod(ci[go] * r2[go] + 1e-4 * self.d[go], 4 * r2[go])
        st[go] = WAIT
        self.cx_axis[go] = np.where(along_x[go], 0, 1)
        self.cx_sign[go] = sign[go]
        self.wsx[go], self.wsz[go] = csx[go], csz[go]

        # waiting for the walk window
        wait = st == WAIT
        if wait.any():
            ix = np.where(self.wsx > 0, self.bi, self.bi - 1)
            iz = np.where(self.wsz > 0, self.bj, self.bj - 1)
            ph = np.mod(time + signal_offset(ix, iz), C.SIGNAL_CYCLE)
            # crossing along x crosses a z-running road: its cars are red while ph in [0, G+Y)
            start = np.where(self.cx_axis == 0, 0.0, C.SIGNAL_GREEN + C.SIGNAL_YELLOW) + 1.0
            ok = wait & (ph >= start) & (ph < start + 1.0)
            st[ok] = CROSS
            self.cprog[ok] = 0.0
            self.cdist[ok] = 80.0 - 2 * self.r[ok]
            self.crossings += int(ok.sum())

        # crossing
        cross = (st == CROSS) & ~sb
        self.cprog[cross] += (self.cdist[cross] / CROSS_TIME) * dt
        done = (st == CROSS) & (self.cprog >= self.cdist)
        if done.any():
            ax0 = self.cx_axis == 0
            self.bi = np.where(done & ax0, self.bi + self.cx_sign.astype(np.int64), self.bi)
            self.bj = np.where(done & ~ax0, self.bj + self.cx_sign.astype(np.int64), self.bj)
            nsx = np.where(ax0, -self.wsx, self.wsx)
            nsz = np.where(ax0, self.wsz, -self.wsz)
            self.d[done] = rng.choice([-1.0, 1.0], int(done.sum()))
            c = _corner_index(nsx, nsz)
            self.s[done] = np.mod(c[done] * 2 * self.r[done] + 1e-4 * self.d[done], 8 * self.r[done])
            st[done] = WALK
        self._sidewalk_positions()
        moving_s = ((st == WALK) | (st == CROSS)) & ~sb

        # ---- plaza strollers
        pb = blocked[ns:]
        pst = self.pstate
        pidle = pst == IDLE
        self.ptimer[pidle] -= dt
        for k in np.flatnonzero(pidle & (self.ptimer <= 0)):
            self._plaza_retarget(k)
        for k in np.flatnonzero(turn[ns:] & (pst == WALK)):
            self._plaza_retarget(k)
        pw = (pst == WALK) & ~pb
        gx = np.where(self.pleg == 0, self.pmx, self.ptx)
        gz = np.where(self.pleg == 0, self.pmz, self.ptz)
        dx, dz = gx - self.px, gz - self.pz
        dist = np.abs(dx) + np.abs(dz)                         # one of dx, dz is zero
        step = np.minimum(self.speed[ns:] * dt, dist)
        ux = np.sign(dx)
        uz = np.where(ux == 0, np.sign(dz), 0.0)
        self.px = np.where(pw, self.px + ux * step, self.px)
        self.pz = np.where(pw, self.pz + uz * step, self.pz)
        arrived = pw & (dist - step < 1e-3)
        to_target = arrived & (self.pleg == 0)
        self.pleg[to_target] = 1
        at_end = arrived & ~to_target
        pst[at_end] = IDLE
        self.ptimer[at_end] = self.rng.uniform(1.0, 5.0, int(at_end.sum()))
        has_dir = pw & (dist > 1e-3)
        self.face_axis[ns:] = np.where(has_dir, np.where(ux != 0, 0, 1), self.face_axis[ns:])
        self.face_sign[ns:] = np.where(has_dir, np.where(ux != 0, ux, uz), self.face_sign[ns:])
        self.x[ns:], self.z[ns:] = self.px, self.pz

        self.moving[:ns] = moving_s
        self.moving[ns:] = pw
        self.phase += np.where(self.moving, self.speed * dt / 0.55 * math.pi, 0.0)

    # ------------------------------------------------------------------ output
    def instances(self, eye):
        ex, ey, ez = eye
        vis = np.flatnonzero((self.x - ex) ** 2 + (self.z - ez) ** 2 + ey ** 2 < C.PED_RENDER_DIST ** 2)
        vis = vis[:C.PED_MAX_BOXES // PARTS]
        return person_boxes(self.x[vis], 0.0, self.z[vis], self.face_axis[vis], self.face_sign[vis],
                            self.moving[vis], self.phase[vis], self.h[vis], self.hue[vis], self.seed[vis],
                            self.umbrella[vis])

    def colliders_near(self, pos, radius=8.0):
        idx = np.flatnonzero((np.abs(self.x - pos[0]) < radius) & (np.abs(self.z - pos[2]) < radius))
        return [(float(self.x[i] - 0.25), 0.0, float(self.z[i] - 0.25),
                 float(self.x[i] + 0.25), float(1.75 * self.h[i]), float(self.z[i] + 0.25)) for i in idx]
