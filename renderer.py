"""moderngl renderer: HDR scene pass (MSAA) -> bloom chain -> tonemapped composite -> HUD."""
import math

import moderngl
import numpy as np

import config as C
import geometry as G
import shaders as S
from harbor import WATER_Y


def setu(prog, name, value):
    try:
        u = prog[name]
    except KeyError:
        return
    if isinstance(value, np.ndarray) and value.ndim == 2:
        u.write(value.T.astype("f4").tobytes())
    else:
        u.value = value


class _Instanced:
    """Instanced mesh with a (re)writable per-instance buffer."""

    def __init__(self, ctx, prog, vbo, vfmt, vnames, nverts, ifmt, inames, floats, capacity, data=None):
        self.floats, self.capacity, self.nverts = floats, capacity, nverts
        self.buf = ctx.buffer(reserve=max(1, capacity) * floats * 4, dynamic=data is None)
        self.vao = ctx.vertex_array(prog, [(vbo, vfmt, *vnames), (self.buf, ifmt, *inames)])
        self.count = 0
        if data is not None:
            self.update(data)

    def update(self, data):
        data = np.ascontiguousarray(data, dtype="f4").reshape(-1, self.floats)
        n = min(len(data), self.capacity)
        if n:
            self.buf.write(data[:n].tobytes())
        self.count = n

    def render(self):
        if self.count:
            self.vao.render(moderngl.TRIANGLES, vertices=self.nverts, instances=self.count)


class _Stream:
    """Plain vertex stream (points or lines) rewritten every frame."""

    def __init__(self, ctx, prog, fmt, names, floats, capacity, mode):
        self.floats, self.capacity, self.mode = floats, capacity, mode
        self.buf = ctx.buffer(reserve=capacity * floats * 4, dynamic=True)
        self.vao = ctx.vertex_array(prog, [(self.buf, fmt, *names)])
        self.count = 0

    def update(self, data):
        data = np.ascontiguousarray(data, dtype="f4").reshape(-1, self.floats)
        n = min(len(data), self.capacity)
        if n:
            self.buf.write(data[:n].tobytes())
        self.count = n

    def render(self):
        if self.count:
            self.vao.render(self.mode, vertices=self.count)


class Renderer:
    def __init__(self, ctx, size, static_boxes, static_quads, car_count, msaa=4, static_rot=None):
        self.ctx = ctx
        self.size = size
        self.logk = 1.0 / math.log2(C.FAR + 1.0)

        def prog(vs, fs):
            return ctx.program(vertex_shader=S.VERSION + vs, fragment_shader=S.VERSION + S.COMMON + fs)

        self.p_box = prog(S.BOX_VS, S.BOX_FS)
        self.p_box_rot = prog(S.BOX_ROT_VS, S.BOX_FS)
        self.p_ground = prog(S.GROUND_VS, S.GROUND_FS)
        self.p_sky = prog(S.FS_VS, S.SKY_FS)
        self.p_quad = prog(S.QUAD_VS, S.QUAD_FS)
        self.p_part = prog(S.PART_VS, S.PART_FS)
        self.p_line = prog(S.LINE_VS, S.LINE_FS)
        self.p_bright = prog(S.FS_VS, S.BRIGHT_FS)
        self.p_down = prog(S.FS_VS, S.DOWN_FS)
        self.p_blur = prog(S.FS_VS, S.BLUR_FS)
        self.p_comp = prog(S.FS_VS, S.COMPOSITE_FS)
        self.p_hud = prog(S.FS_VS, S.HUD_FS)
        self.p_cloud = prog(S.CLOUD_VS, S.CLOUD_FS)
        self.scene_progs = [self.p_box, self.p_box_rot, self.p_ground, self.p_sky, self.p_quad, self.p_part,
                            self.p_line, self.p_cloud]

        cube = ctx.buffer(G.unit_cube().tobytes())
        corners = ctx.buffer(G.QUAD_CORNERS.tobytes())
        box_args = (cube, "3f 3f", ("in_pos", "in_normal"), 36, "3f 3f 4f/i", ("i_pos", "i_size", "i_params"),
                    G.BOX_FLOATS)
        quad_args = (corners, "2f", ("in_corner",), 6, "3f 3f 3f 4f/i", ("i_center", "i_right", "i_up", "i_params"),
                     G.QUAD_FLOATS)
        self.static_boxes = _Instanced(ctx, self.p_box, *box_args, len(static_boxes), static_boxes)
        self.dyn_boxes = _Instanced(ctx, self.p_box, *box_args, 8192)     # elevator, shops, tower floors, trains
        self.cars = _Instanced(ctx, self.p_box, *box_args, car_count)
        self.peds = _Instanced(ctx, self.p_box, *box_args, C.PED_MAX_BOXES)
        rot_args = (cube, "3f 3f", ("in_pos", "in_normal"), 36, "3f 3f 4f 1f/i",
                    ("i_pos", "i_size", "i_params", "i_yaw"), G.BOX_FLOATS + 1)
        static_rot = np.zeros((0, G.BOX_FLOATS + 1), "f4") if static_rot is None else static_rot
        self.rot_static = _Instanced(ctx, self.p_box_rot, *rot_args, len(static_rot), static_rot)
        self.rot_dyn = _Instanced(ctx, self.p_box_rot, *rot_args, 4096)          # metro trains
        self.static_quads = _Instanced(ctx, self.p_quad, *quad_args, len(static_quads), static_quads)
        self.dyn_quads = _Instanced(ctx, self.p_quad, *quad_args, 128)
        self.glass = _Instanced(ctx, self.p_quad, *quad_args, 64)                # elevator + taxi windows

        self.fire = _Stream(ctx, self.p_part, "3f 4f 1f", ("in_pos", "in_color", "in_size"), 8, 4000,
                            moderngl.POINTS)
        self.puffs = _Stream(ctx, self.p_part, "3f 4f 1f", ("in_pos", "in_color", "in_size"), 8, 4000,
                             moderngl.POINTS)
        self.lines = _Stream(ctx, self.p_line, "3f 4f", ("in_pos", "in_color"), 7, 8000, moderngl.LINES)

        ground = ctx.buffer(G.ground_quad(30000.0).tobytes())
        self.ground_vao = ctx.vertex_array(self.p_ground, [(ground, "2f", "in_pos")])
        self.cloud_vao = ctx.vertex_array(self.p_cloud, [(ground, "2f", "in_pos")])   # the same big quad, up high
        tri = ctx.buffer(G.FULLSCREEN_TRI.tobytes())
        self.fs_vaos = {p: ctx.vertex_array(p, [(tri, "2f", "in_pos")])
                        for p in (self.p_sky, self.p_bright, self.p_down, self.p_blur, self.p_comp, self.p_hud)}

        ctx.enable(moderngl.PROGRAM_POINT_SIZE)
        self._make_targets(msaa)

    # ---------------------------------------------------------------- targets
    def _tex(self, size):
        t = self.ctx.texture(size, 4, dtype="f2")
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        t.repeat_x = t.repeat_y = False
        return t

    def _make_targets(self, msaa):
        ctx, (w, h) = self.ctx, self.size
        self.scene_tex = self._tex((w, h))
        samples = min(msaa, ctx.max_samples) if msaa > 1 else 0
        self.fbo_ms = None
        if samples > 1:
            try:
                color = ctx.renderbuffer((w, h), 4, samples=samples, dtype="f2")
                depth = ctx.depth_renderbuffer((w, h), samples=samples)
                self.fbo_ms = ctx.framebuffer([color], depth)
            except moderngl.Error:
                self.fbo_ms = None
        if self.fbo_ms is None:
            self.fbo_scene = ctx.framebuffer([self.scene_tex], ctx.depth_renderbuffer((w, h)))
            self.fbo_draw = self.fbo_scene
        else:
            self.fbo_scene = ctx.framebuffer([self.scene_tex])
            self.fbo_draw = self.fbo_ms
        self.bloom = []
        for div in (2, 4, 8):
            s = (max(1, w // div), max(1, h // div))
            a, b = self._tex(s), self._tex(s)
            self.bloom.append((s, a, b, ctx.framebuffer([a]), ctx.framebuffer([b])))

    def set_ground_holes(self, holes):
        """Rectangles (x0, z0, x1, z1) cut out of the ground plane (up to 8)."""
        arr = np.zeros((8, 4), "f4")
        for i, h in enumerate(list(holes)[:8]):
            arr[i] = h
        try:
            self.p_ground["u_holes"].write(arr.tobytes())
        except KeyError:
            pass

    def set_ground_zones(self, zones):
        """(x0, z0, x1, z1, kind) ground areas (up to 16): kind 0 cut out (tower lobby), 1 park lawn, 2 plaza."""
        rects = np.zeros((16, 4), "f4")
        kinds = np.full(16, -1.0, "f4")
        for i, z in enumerate(list(zones)[:16]):
            rects[i], kinds[i] = z[:4], z[4]
        for name, arr in (("u_zones", rects), ("u_zone_kind", kinds)):
            try:
                self.p_ground[name].write(arr.tobytes())
            except KeyError:
                pass

    # ---------------------------------------------------------------- per-frame data
    def set_dynamic(self, dyn_boxes, cars, dyn_quads, glass, peds=(), rot=()):
        self.dyn_boxes.update(dyn_boxes)
        self.cars.update(cars)
        self.peds.update(peds)
        self.rot_dyn.update(rot)
        self.dyn_quads.update(dyn_quads)
        self.glass.update(glass)

    def set_particles(self, fire, puffs, lines):
        self.fire.update(fire)
        self.puffs.update(puffs)
        self.lines.update(lines)

    def _fs(self, prog):
        self.fs_vaos[prog].render(moderngl.TRIANGLES, vertices=3)

    # ---------------------------------------------------------------- frame
    def render(self, eye, forward, fov, time, boot, speed_fx, thrust_fx, hud_tex=None, target=None,
               tower_open=(-1e9, -1e9), tower_open_c=(1e9, 1e9), bldg=(1e9, 1e9, 0.0, 0.0),
               bldg_hatch=(0.0, 0.0, 0.0, 0.0), bldg_doors=(), env=None):
        """env: environment.Environment.uniforms() (time of day / weather); None keeps the night look."""
        ctx = self.ctx
        env = env or {"u_sun": (0.0, -1.0, 0.0, 0.0), "u_env": (0.0, 0.85, 0.25, 0.0), "u_wet": 1.0}
        w, h = self.size
        proj = G.perspective(fov, w / h, C.NEAR, C.FAR)
        view = G.look_at(eye, np.add(eye, forward))
        vp = proj @ view
        view_rot = view.copy()
        view_rot[:3, 3] = 0.0
        inv_vp_rot = np.linalg.inv(proj @ view_rot)
        for p in self.scene_progs:
            setu(p, "u_vp", vp)
            setu(p, "u_cam", tuple(float(v) for v in eye))
            setu(p, "u_time", float(time))
            setu(p, "u_logk", self.logk)
            setu(p, "u_boot", tuple(float(v) for v in boot))
        for p in self.scene_progs + [self.p_comp]:
            for name, value in env.items():
                setu(p, name, tuple(float(v) for v in value) if isinstance(value, tuple) else float(value))
        setu(self.p_sky, "u_inv_vp_rot", inv_vp_rot)
        setu(self.p_box, "u_tower_open", tuple(float(v) for v in tower_open))
        setu(self.p_box, "u_tower_open_c", tuple(float(v) for v in tower_open_c))
        setu(self.p_box, "u_bldg", tuple(float(v) for v in bldg))
        setu(self.p_box, "u_bldg_open", tuple(float(v) for v in tower_open))     # one open range for both
        setu(self.p_box, "u_bldg_hatch", tuple(float(v) for v in bldg_hatch))
        rects, ys = np.zeros((4, 4), "f4"), np.zeros((4, 2), "f4")
        for i, d in enumerate(list(bldg_doors)[:4]):
            rects[i] = (d[0], d[2], d[3], d[5])
            ys[i] = (d[1], d[4])
        for name, arr in (("u_bdoor", rects), ("u_bdoor_y", ys)):
            try:
                self.p_box[name].write(arr.tobytes())
            except KeyError:
                pass
        setu(self.p_ground, "u_city_edge", C.CITY_BLOCKS * C.BLOCK_PITCH + C.BLOCK_PITCH / 2 + 30.0)
        setu(self.p_part, "u_pscale", float(h * proj[1, 1] * 0.5))

        fbo = self.fbo_draw
        fbo.use()
        fbo.clear(0.0, 0.0, 0.0, 1.0, depth=1.0)

        # sky
        ctx.disable(moderngl.DEPTH_TEST | moderngl.BLEND)
        fbo.depth_mask = False
        self._fs(self.p_sky)
        fbo.depth_mask = True

        # opaque
        ctx.enable(moderngl.DEPTH_TEST)
        setu(self.p_ground, "u_ground_y", 0.0)
        setu(self.p_ground, "u_water", 0.0)
        self.ground_vao.render(moderngl.TRIANGLES, vertices=6)
        setu(self.p_ground, "u_ground_y", WATER_Y)                  # the sea, south of the quay
        setu(self.p_ground, "u_water", 1.0)
        self.ground_vao.render(moderngl.TRIANGLES, vertices=6)
        self.static_boxes.render()
        self.dyn_boxes.render()
        self.cars.render()
        self.peds.render()
        self.rot_static.render()
        self.rot_dyn.render()

        # transparent: alpha-blended first, additive last
        ctx.enable(moderngl.BLEND)
        fbo.depth_mask = False
        ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        self.cloud_vao.render(moderngl.TRIANGLES, vertices=6)     # cloud layer (premultiplied alpha)
        self.puffs.render()
        self.glass.render()
        ctx.blend_func = moderngl.ONE, moderngl.ONE
        self.static_quads.render()
        self.dyn_quads.render()
        self.lines.render()
        self.fire.render()
        fbo.depth_mask = True
        ctx.disable(moderngl.BLEND | moderngl.DEPTH_TEST)

        if self.fbo_ms is not None:
            ctx.copy_framebuffer(self.fbo_scene, self.fbo_ms)

        # bloom chain
        src, src_size = self.scene_tex, (w, h)
        for i, (s, a, b, fa, fb) in enumerate(self.bloom):
            fa.use()
            src.use(0)
            p = self.p_bright if i == 0 else self.p_down
            setu(p, "u_tex", 0)
            setu(p, "u_texel", (1.0 / src_size[0], 1.0 / src_size[1]))
            self._fs(p)
            setu(self.p_blur, "u_tex", 0)
            fb.use()
            a.use(0)
            setu(self.p_blur, "u_dir", (1.0 / s[0], 0.0))
            self._fs(self.p_blur)
            fa.use()
            b.use(0)
            setu(self.p_blur, "u_dir", (0.0, 1.0 / s[1]))
            self._fs(self.p_blur)
            src, src_size = a, s

        # composite
        out = target if target is not None else ctx.screen
        out.use()
        self.scene_tex.use(0)
        for i, (_, a, _, _, _) in enumerate(self.bloom):
            a.use(i + 1)
        pc = self.p_comp
        setu(pc, "u_scene", 0)
        setu(pc, "u_bloom1", 1)
        setu(pc, "u_bloom2", 2)
        setu(pc, "u_bloom3", 3)
        setu(pc, "u_speed", float(speed_fx))
        setu(pc, "u_thrust", float(thrust_fx))
        setu(pc, "u_time", float(time))
        setu(pc, "u_exposure", 1.0 - 0.3 * float(env["u_sun"][3]))
        self._fs(pc)

        if hud_tex is not None:
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            hud_tex.use(0)
            setu(self.p_hud, "u_tex", 0)
            self._fs(self.p_hud)
            ctx.disable(moderngl.BLEND)
