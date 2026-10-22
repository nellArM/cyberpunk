"""Mesh data, instance record helpers and camera matrices."""
import math

import numpy as np


def unit_cube():
    """36 vertices (pos3, normal3); x,z in [-0.5, 0.5], y in [0, 1]."""
    faces = [
        ((1, 0, 0), [(0.5, 0, -0.5), (0.5, 1, -0.5), (0.5, 1, 0.5), (0.5, 0, 0.5)]),
        ((-1, 0, 0), [(-0.5, 0, 0.5), (-0.5, 1, 0.5), (-0.5, 1, -0.5), (-0.5, 0, -0.5)]),
        ((0, 1, 0), [(-0.5, 1, -0.5), (-0.5, 1, 0.5), (0.5, 1, 0.5), (0.5, 1, -0.5)]),
        ((0, -1, 0), [(-0.5, 0, 0.5), (-0.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5)]),
        ((0, 0, 1), [(0.5, 0, 0.5), (0.5, 1, 0.5), (-0.5, 1, 0.5), (-0.5, 0, 0.5)]),
        ((0, 0, -1), [(-0.5, 0, -0.5), (-0.5, 1, -0.5), (0.5, 1, -0.5), (0.5, 0, -0.5)]),
    ]
    out = []
    for n, quad in faces:
        for i in (0, 1, 2, 0, 2, 3):
            out.append((*quad[i], *n))
    return np.array(out, dtype="f4")


QUAD_CORNERS = np.array([(-1, -1), (1, -1), (1, 1), (-1, -1), (1, 1), (-1, 1)], dtype="f4")
FULLSCREEN_TRI = np.array([(-1, -1), (3, -1), (-1, 3)], dtype="f4")


def ground_quad(extent):
    e = extent
    return np.array([(-e, -e), (e, -e), (e, e), (-e, -e), (e, e), (-e, e)], dtype="f4")


# --- instance records ------------------------------------------------------
# Box instance: center x, base y, center z, size xyz, seed, kind, hue, extra
BOX_FLOATS = 10
# Quad instance: center3, right3 (half extent), up3 (half extent), seed, mode, hue, intensity
QUAD_FLOATS = 13


def box(cx, y0, cz, sx, sy, sz, kind, hue=0.0, extra=0.0, seed=0.0):
    return [cx, y0, cz, sx, sy, sz, seed, kind, hue, extra]


def box_bounds(x0, y0, z0, x1, y1, z1, kind, hue=0.0, extra=0.0, seed=0.0):
    return box((x0 + x1) * 0.5, y0, (z0 + z1) * 0.5, x1 - x0, y1 - y0, z1 - z0, kind, hue, extra, seed)


def quad(center, right, up, mode, hue=0.5, intensity=1.0, seed=0.0):
    return [*center, *right, *up, seed, mode, hue, intensity]


# --- matrices (row-major, column vectors; transpose before upload) --------
def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) * 0.5)
    m = np.zeros((4, 4), dtype=np.float64)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def look_at(eye, target, up=(0.0, 1.0, 0.0)):
    eye = np.asarray(eye, dtype=np.float64)
    f = np.asarray(target, dtype=np.float64) - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.identity(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[0, 3], m[1, 3], m[2, 3] = -s.dot(eye), -u.dot(eye), f.dot(eye)
    return m


def direction(yaw, pitch):
    """yaw 0 looks toward -z, positive yaw turns right (+x)."""
    cp = math.cos(pitch)
    return (math.sin(yaw) * cp, math.sin(pitch), -math.cos(yaw) * cp)
