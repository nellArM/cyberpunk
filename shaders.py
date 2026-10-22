"""GLSL 3.30 sources. Fragment shaders are prefixed with VERSION + COMMON.

All scene shaders write a logarithmic depth (writeDepth) so that a 0.1 m
near plane and a 40 km far plane coexist without z-fighting.
"""

import config as C

VERSION = "#version 330 core\n"
CLOUD_Y = 1300.0                  # the cloud layer (environment / weather)

COMMON = r"""
uniform vec3 u_cam;
uniform float u_time;
uniform float u_logk;
uniform vec4 u_boot;          // xyz = rocket boot flame position, w = intensity
uniform vec4 u_sun;           // xyz = direction to the sun, w = daylight 0..1 (environment.py)
uniform vec4 u_env;           // x = dusk glow, y = cloud cover, z = fog, w = lightning flash
uniform float u_wet;          // 0 dry .. 1 soaked streets

const float FOG_A = 0.0012;   // fog density at ground level (clear weather)
const float FOG_B = 1.0 / 170.0;
const float CLOUD_H = @CLOUD_Y@;   // height of the cloud layer: above it the sky is clear

// Cloud cover as seen from height y (the layer only hides the sky / sun from below).
float cloudBelow(float y) {
    return u_env.y * (1.0 - smoothstep(CLOUD_H - 40.0, CLOUD_H + 120.0, y));
}

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}
float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float hash13(vec3 p3) {
    p3 = fract(p3 * 0.1031);
    p3 += dot(p3, p3.zyx + 31.32);
    return fract((p3.x + p3.y) * p3.z);
}
float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash12(i);
    float b = hash12(i + vec2(1.0, 0.0));
    float c = hash12(i + vec2(0.0, 1.0));
    float d = hash12(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}
vec3 neon(float hue) {
    return hue < 0.0 ? vec3(1.0) : hsv2rgb(vec3(hue, 0.85, 1.0));
}

// Sky radiance in direction d: the neon-polluted night sky, blue day, a dusk glow toward the sun;
// clouds and fog flatten it to grey, lightning washes it out.
vec3 skyColor(vec3 d) {
    float day = u_sun.w, cloud = cloudBelow(u_cam.y), fogk = u_env.z;
    vec3 zenith = mix(vec3(0.003, 0.003, 0.014), vec3(0.09, 0.2, 0.5), day);
    vec3 horizon = mix(vec3(0.17, 0.04, 0.16), vec3(0.5, 0.58, 0.72), day);
    vec3 glow = mix(vec3(0.35, 0.08, 0.12) * 0.6, vec3(0.12, 0.1, 0.09), day);
    vec3 below = mix(vec3(0.035, 0.01, 0.045), vec3(0.16, 0.18, 0.22), day);
    vec3 grey = mix(vec3(0.15, 0.045, 0.14), vec3(0.42, 0.44, 0.48), day);   // overcast (city glow at night)
    zenith = mix(zenith, grey * 0.75, cloud * mix(0.2, 0.8, day));
    horizon = mix(horizon, grey, clamp(cloud * 0.5 * day + fogk * 0.5, 0.0, 1.0));
    vec3 c;
    if (d.y >= 0.0) c = mix(horizon, zenith, pow(clamp(d.y, 0.0, 1.0), 0.4)) + glow * exp(-d.y * 40.0);
    else c = mix(horizon + glow, below, clamp(-d.y * 4.0, 0.0, 1.0));
    vec2 hs = normalize(u_sun.xz + vec2(1e-5));
    vec2 hd = normalize(d.xz + vec2(1e-5));
    float toward = max(dot(hs, hd), 0.0);
    c += vec3(1.0, 0.36, 0.14) * u_env.x * (0.2 + 0.8 * pow(toward, 3.0)) * exp(-abs(d.y) * 5.0) * (1.0 - 0.6 * cloud);
    c += vec3(0.55, 0.6, 0.85) * u_env.w * 1.6;
    return c;
}

// Light from the sun and the open sky on a surface with normal n at p (none underground).
vec3 daylight(vec3 n, vec3 p) {
    float day = u_sun.w;
    vec3 sd = normalize(u_sun.xyz);
    float cloud = cloudBelow(p.y);
    float sunVis = (1.0 - 0.85 * cloud) * smoothstep(-0.05, 0.12, sd.y);
    vec3 sunCol = mix(vec3(1.0, 0.45, 0.2), vec3(1.0, 0.95, 0.86), smoothstep(0.0, 0.4, sd.y));
    vec3 sky = mix(vec3(0.32, 0.4, 0.55), vec3(0.48, 0.49, 0.52), cloud);
    vec3 l = sunCol * max(dot(n, sd), 0.0) * 2.4 * sunVis + sky * (0.55 + 0.45 * n.y) * day;
    l += vec3(0.7, 0.75, 1.0) * u_env.w * 2.5 * (0.4 + 0.6 * max(n.y, 0.0));
    return l * smoothstep(-1.5, -0.3, p.y);
}

// Analytic exponential height fog (thick smog at street level, clear at 4 km; much more in fog).
float fogFactor(vec3 p) {
    vec3 d = p - u_cam;
    float dist = length(d);
    vec3 rd = d / max(dist, 1e-4);
    float fa = FOG_A * (1.0 + 7.0 * u_env.z);
    float fb = FOG_B / (1.0 + 1.5 * u_env.z);
    float k = fa * exp(-u_cam.y * fb);
    float fog;
    if (abs(rd.y) < 1e-4) fog = k * dist;
    else fog = k * (1.0 - exp(-dist * rd.y * fb)) / (rd.y * fb);
    float f = 1.0 - exp(-max(fog, 0.0));
    return max(f, smoothstep(7000.0, 26000.0, dist));
}
vec3 applyFog(vec3 col, vec3 p) {
    return mix(col, skyColor(normalize(p - u_cam)), fogFactor(p));
}

// Anti-aliased line of half-width w around d == 0, energy preserving when tiny.
float aaLine(float d, float w) {
    float fw = fwidth(d);
    float aw = max(w, fw * 1.5);
    return (1.0 - smoothstep(aw * 0.5, aw, d)) * (w / aw);
}

vec3 bootLight(vec3 p, vec3 n) {
    if (u_boot.w <= 0.0) return vec3(0.0);
    vec3 L = u_boot.xyz - p;
    float d2 = dot(L, L);
    float nd = max(dot(n, L * inversesqrt(d2 + 1e-4)), 0.0);
    return vec3(1.0, 0.42, 0.12) * u_boot.w * 30.0 * nd / (4.0 + d2);
}

void writeDepth(float logz) {
    gl_FragDepth = log2(logz) * u_logk;
}
"""

COMMON = COMMON.replace("@CLOUD_Y@", f"{CLOUD_Y:.1f}")

# ---------------------------------------------------------------------------
BOX_VS = r"""
in vec3 in_pos;
in vec3 in_normal;
in vec3 i_pos;
in vec3 i_size;
in vec4 i_params;
uniform mat4 u_vp;
uniform vec3 u_cam;
out vec3 v_world;                // pattern-space position (== world for axis-aligned boxes)
out vec3 v_wpos;                 // true world position
flat out vec3 v_campat;          // camera in pattern space
out vec3 v_normal;
out vec3 v_local;
flat out vec3 v_center;
flat out vec3 v_size;
flat out vec4 v_params;
out float v_logz;
void main() {
    vec3 wp = i_pos + in_pos * i_size;
    v_world = wp;
    v_wpos = wp;
    v_campat = u_cam;
    v_normal = in_normal;
    v_local = in_pos;
    v_center = i_pos;
    v_size = i_size;
    v_params = i_params;
    gl_Position = u_vp * vec4(wp, 1.0);
    v_logz = 1.0 + gl_Position.w;
}
"""

BOX_ROT_VS = r"""
in vec3 in_pos;
in vec3 in_normal;
in vec3 i_pos;
in vec3 i_size;
in vec4 i_params;
in float i_yaw;
uniform mat4 u_vp;
uniform vec3 u_cam;
out vec3 v_world;
out vec3 v_wpos;
flat out vec3 v_campat;
out vec3 v_normal;
out vec3 v_local;
flat out vec3 v_center;
flat out vec3 v_size;
flat out vec4 v_params;
out float v_logz;
void main() {
    // box local axes x/z are rotated by i_yaw about +y: local x -> (c, -s), local z -> (s, c)
    vec3 lp = in_pos * i_size;
    float c = cos(i_yaw);
    float s = sin(i_yaw);
    v_wpos = i_pos + vec3(c * lp.x + s * lp.z, lp.y, -s * lp.x + c * lp.z);
    v_world = i_pos + lp;                                   // patterns live in the unrotated frame
    vec3 d = u_cam - i_pos;
    v_campat = i_pos + vec3(c * d.x - s * d.z, d.y, s * d.x + c * d.z);
    v_normal = in_normal;
    v_local = in_pos;
    v_center = i_pos;
    v_size = i_size;
    v_params = i_params;
    gl_Position = u_vp * vec4(v_wpos, 1.0);
    v_logz = 1.0 + gl_Position.w;
}
"""

BOX_FS = r"""
in vec3 v_world;
in vec3 v_wpos;
flat in vec3 v_campat;
in vec3 v_normal;
in vec3 v_local;
flat in vec3 v_center;
flat in vec3 v_size;
flat in vec4 v_params;
in float v_logz;
out vec4 f_color;

uniform vec2 u_tower_open;                       // y-range where the tower's windows/doorways are open
uniform vec2 u_tower_open_c;                     // ... on the tower centered here (x, z)
uniform vec4 u_bldg;                             // city building the player is in: base box (cx, cz, w, d)
uniform vec2 u_bldg_open;                        // y-range where its windows are open
uniform vec4 u_bldg_hatch;                       // its roof hatch (x0, z0, x1, z1)
uniform vec4 u_bdoor[4];                         // its skybridge doorways (x0, z0, x1, z1) ...
uniform vec2 u_bdoor_y[4];                       // ... and their (y0, y1)
const float HOLE_XA = @HXA@;                     // stair hatch x range, measured in from the east facade
const float HOLE_XB = @HXB@;
const float HOLE_Z0 = @HZ0@;
const float HOLE_Z1 = @HZ1@;
const float LOBBY_H = @LOBBY_H@;
const vec4 MALL_STAIR = vec4(@MSTAIR@);                // (x0, z0, x1, z1) opening in the Nexus lobby floor
// daylight albedo per box kind (city buildings 0 and megatowers 1 set theirs per face; lights get none)
const float DAY_ALB[16] = float[16](0.0, 0.0, 0.16, 0.0, 0.16, 0.0, 0.1, 0.15, 0.2, 0.14, 0.1, 0.0, 0.04,
                                   0.3, 0.04, 0.22);
const float ELEV_DOOR_HALF = @EDH@;
const float ELEV_DOOR_H = @EDHT@;
const float SHOP_H = @SHOP_H@;
const float DOOR_HALF = @DOOR_HALF@;
const float DOOR_H = @DOOR_H@;
const float CYCLE = @CYCLE@;
const float GREEN = @GREEN@;
const float YELLOW = @YELLOW@;

// Accent colour per shop type, matching config.SHOP_TYPES hues.
vec3 shopAccent(int t) {
    if (t == 0) return vec3(0.6, 0.95, 1.0);     // convenience store
    if (t == 1) return vec3(1.0, 0.35, 0.15);    // ramen
    if (t == 2) return vec3(0.3, 1.0, 0.6);      // cyber clinic
    if (t == 3) return vec3(0.75, 0.3, 1.0);     // bar
    if (t == 4) return vec3(0.25, 0.55, 1.0);    // electronics
    return vec3(1.0, 0.65, 0.3);                 // cafe
}

// Faces of a building box seen from inside its ground floor.
vec3 shopInterior(int t, vec3 n, bool side, float u, float yl, float seed, float faceId, float fres) {
    vec3 acc = shopAccent(t);
    if (n.y < -0.5) {                            // floor (box bottom seen from above)
        vec2 p = v_world.xz / 1.2;
        vec2 tl = abs(fract(p) - 0.5) * 1.2;
        vec3 c = vec3(0.03, 0.031, 0.036) + acc * 0.015 + vec3(0.01) * hash12(floor(p));
        c *= 1.0 - 0.6 * max(aaLine(tl.x, 0.02), aaLine(tl.y, 0.02));
        return c + acc * 0.05 * fres;
    }
    if (!side || yl > SHOP_H - 0.1) return vec3(0.015);
    float pu = u / 2.0;
    vec3 c = (vec3(0.03, 0.03, 0.035) + acc * 0.05) * (1.0 - 0.35 * aaLine(abs(fract(pu + 0.5) - 0.5) * 2.0, 0.02));
    c += acc * 2.2 * aaLine(abs(yl - 4.55), 0.05);
    c += acc * 1.2 * aaLine(abs(yl - 0.12), 0.04);
    float ph = hash13(vec3(floor(pu), seed, faceId));
    if (ph > 0.55 && abs(fract(pu) - 0.5) < 0.32 && yl > 1.5 && yl < 3.3)
        c += hsv2rgb(vec3(fract(ph * 7.0), 0.6, 1.0)) * 0.7;      // posters / screens
    return c;
}

// Outside of the door face, ground floor: lit display windows and a neon door frame.
vec3 storefront(int t, float u, float cu, float yl, float seed) {
    vec3 acc = shopAccent(t);
    float du = abs(u - cu);
    vec3 c = vec3(0.02, 0.02, 0.025);
    if (yl > 0.4 && yl < DOOR_H) {               // display windows: dark glass, glowing goods
        float q = (u - cu) / 2.5;
        vec2 g = vec2((u - cu) / 0.55, yl / 0.6);
        vec2 f = abs(fract(g) - 0.5);
        float item = step(0.5, hash13(vec3(floor(g), seed))) * step(f.x, 0.32) * step(f.y, 0.3);
        vec3 ic = hsv2rgb(vec3(fract(hash13(vec3(floor(g), seed + 2.0)) * 0.3 + seed), 0.55, 1.0));
        c = acc * 0.1 + vec3(0.02) + mix(acc, ic, 0.5) * item * 0.8;
        c += acc * 0.6 * aaLine(abs(fract(yl / 0.6) - 0.02), 0.02);              // shelf edges
        c *= 1.0 - 0.85 * aaLine(abs(fract(q) - 0.5) * 2.5, 0.06);
    }
    c += acc * 3.0 * aaLine(abs(du - DOOR_HALF), 0.07) * step(yl, DOOR_H + 0.07);
    c += acc * 3.0 * aaLine(abs(yl - DOOR_H), 0.07) * step(du, DOOR_HALF + 0.07);
    return c;
}

// Storey height of a city building's upper floors (buildings.floor_height computes the same).
float cityFloorH(float seed) {
    return 3.4 + 0.2 * floor(fract(seed * 0.7548777) * 7.0);
}

// Window mask (0..1) of a city building facade: one row per upper floor, above the shop.
float cityWindow(float u, float yl, float seed) {
    vec2 f = fract(vec2(u / (2.2 + hash11(seed * 3.31) * 2.2), (yl - SHOP_H) / cityFloorH(seed)));
    float wx = smoothstep(0.1, 0.16, f.x) * (1.0 - smoothstep(0.84, 0.9, f.x));
    float wy = smoothstep(0.2, 0.26, f.y) * (1.0 - smoothstep(0.8, 0.86, f.y));
    return wx * wy;
}

vec3 windowColor(float pal, float hue, float h2) {
    if (pal < 0.45) return mix(vec3(0.55, 0.8, 1.3), vec3(1.1, 1.0, 0.85), h2);
    if (pal < 0.8) return mix(vec3(1.4, 0.65, 0.22), vec3(1.25, 0.95, 0.55), h2);
    return hsv2rgb(vec3(hue + h2 * 0.12, 0.65, 1.5));
}

// p: tower-local roof position, tHalf: half footprint (markings are laid out for 40 and scaled)
vec3 helipad(vec2 p, float moon, float tHalf) {
    float s = tHalf / 40.0;
    vec3 c = vec3(0.025, 0.026, 0.032) * (0.6 + moon) + vec3(0.015) * vnoise(p * 0.7);
    float r = length(p);
    float sq = max(abs(p.x), abs(p.y));
    // touchdown square and circle
    c += vec3(0.9, 0.9, 1.0) * 0.5 * aaLine(abs(sq - 30.0 * s), 0.15);
    c += vec3(1.0, 0.75, 0.1) * 3.0 * aaLine(abs(r - 18.0 * s), 0.9);
    c += vec3(1.0, 0.75, 0.1) * 1.2 * aaLine(abs(r - 20.5 * s), 0.25);
    // big "H"
    float inH = step(abs(p.x), 7.0 * s) * step(abs(p.y), 10.0 * s);
    float bars = max(step(4.5 * s, abs(p.x)), step(abs(p.y), 1.3 * s));
    c = mix(c, vec3(1.8, 1.8, 1.9), inH * bars);
    // chasing lights around the circle
    float rc = 23.0 * s;
    float a = atan(p.y, p.x) / 6.2831853 + 0.5;
    float k = fract(a * 36.0);
    float dotC = 1.0 - smoothstep(0.25, 0.4, length(vec2((k - 0.5) * 6.2831853 * rc / 36.0, r - rc)));
    float chase = step(fract(a - u_time * 0.4), 0.3);
    c += vec3(0.2, 1.0, 0.9) * dotC * (0.4 + 4.0 * chase);
    // blinking edge lights - the roof has no railing at all
    float edge = tHalf - sq;
    float along = abs(p.x) > abs(p.y) ? p.y : p.x;
    float kk = fract(along / 5.0);
    float dotE = 1.0 - smoothstep(0.25, 0.4, length(vec2((kk - 0.5) * 5.0, edge - 0.7)));
    float blink = step(0.5, fract(u_time * 0.8 + along * 0.004));
    c += vec3(3.0, 0.25, 0.08) * dotE * (0.25 + blink);
    c += vec3(1.0, 0.2, 0.1) * 0.6 * aaLine(edge, 0.12);
    // hazard frame around the stair hatch (an opening, not a wall)
    vec2 hc = vec2(2.0 * tHalf - HOLE_XA - HOLE_XB, HOLE_Z0 + HOLE_Z1) * 0.5;
    vec2 hq = abs(p - hc) - vec2(HOLE_XA - HOLE_XB, HOLE_Z1 - HOLE_Z0) * 0.5;
    float sd = max(hq.x, hq.y);
    if (sd > 0.0 && sd < 0.6)
        c = mix(vec3(0.02), vec3(2.2, 1.5, 0.1), step(0.5, fract((p.x + p.y) / 0.8)));
    return c;
}

void main() {
    vec3 n = normalize(v_normal);
    int kind = int(v_params.y + 0.5);
    float seed = v_params.x;
    float hue = v_params.z;
    float extra = v_params.w;
    bool side = abs(n.y) < 0.5;
    float u, cu, hsu;
    if (abs(n.x) > 0.5) { u = v_world.z; cu = v_center.z; hsu = v_size.z * 0.5; }
    else { u = v_world.x; cu = v_center.x; hsu = v_size.x * 0.5; }
    float y = v_world.y;
    float yl = y - v_center.y;
    float edgeU = hsu - abs(u - cu);
    float edgeTop = v_center.y + v_size.y - y;
    float faceId = n.x + 2.0 * n.z + 3.0 * n.y;
    vec3 V = normalize(v_world - v_campat);
    float moon = max(dot(n, vec3(-0.37, 0.58, -0.73)), 0.0);
    float fres = pow(1.0 - clamp(dot(-V, n), 0.0, 1.0), 4.0);
    vec3 col = vec3(0.0);
    float albedo = 0.05;
    float dayAlb = 0.0;                    // how much daylight the surface reflects (set per kind below)
    vec3 lightN = n;

    if (kind == 0) {                       // ---------------- city building with ground-floor shop
        int code = int(extra + 0.5);       // door face + 10 * shop type + 100 * district
        int face = code - (code / 10) * 10;
        int stype = (code / 10) - (code / 100) * 10;
        int dk = code / 100;
        bool doorFace = side && (face == 1 ? n.x > 0.5 : face == 2 ? n.x < -0.5 :
                                 face == 3 ? n.z > 0.5 : face == 4 ? n.z < -0.5 : false);
        if (doorFace && abs(u - cu) < DOOR_HALF && yl < DOOR_H) discard;
        // the base box of the building the player is in: windows / roof hatch open near the player
        bool active = v_center.y < 0.1 && abs(v_center.x - u_bldg.x) < 0.01 && abs(v_center.z - u_bldg.y) < 0.01
                      && abs(v_size.x - u_bldg.z) < 0.01 && abs(v_size.z - u_bldg.w) < 0.01;
        bool bopen = active && y > u_bldg_open.x && y < u_bldg_open.y;
        if (bopen && n.y > 0.5 && v_world.x > u_bldg_hatch.x && v_world.x < u_bldg_hatch.z
            && v_world.z > u_bldg_hatch.y && v_world.z < u_bldg_hatch.w) discard;
        if (bopen && side && yl > SHOP_H + 0.05 && cityWindow(u, yl, seed) > 0.5) discard;
        if (active && side) {
            for (int i = 0; i < 4; i++) {
                vec4 r = u_bdoor[i];
                vec2 dy = u_bdoor_y[i];
                if (dy.y > dy.x && y > dy.x && y < dy.y && v_world.x > r.x && v_world.x < r.z
                    && v_world.z > r.y && v_world.z < r.w) discard;
            }
        }
        bool fromInside = face > 0 && dot(V, n) > 0.0;
        col = vec3(0.016, 0.017, 0.028) * (0.6 + 0.9 * moon);
        float hasNeon = step(0.4, hash11(seed * 2.17));
        if (fromInside && active && yl > SHOP_H - 0.1) {   // upper floors seen from inside
            if (side) {
                float fy = fract((yl - SHOP_H) / cityFloorH(seed));
                col = vec3(0.022, 0.024, 0.032) + vec3(0.1, 0.5, 0.6) * 0.4 * aaLine(abs(fy - 0.04) * 4.0, 0.02);
            } else {                       // top floor ceiling
                vec2 f = abs(fract(v_world.xz / 3.0) - 0.5);
                float panel = (1.0 - smoothstep(0.3, 0.34, f.x)) * (1.0 - smoothstep(0.12, 0.16, f.y));
                col = vec3(0.02) + vec3(0.85) * panel * 0.4;
            }
            lightN = -n;
            albedo = 0.1;
            dayAlb = 0.06;
        } else if (fromInside) {           // the face's inward side: flip the normal for lighting
            col = shopInterior(stype, n, side, u, yl, seed, faceId, pow(1.0 - clamp(dot(V, n), 0.0, 1.0), 4.0));
            lightN = -n;
            albedo = 0.1;
        } else if (doorFace && yl < SHOP_H) {
            col = storefront(stype, u, cu, yl, seed);
            dayAlb = 0.1;
        } else if (side) {
            dayAlb = 0.22;
            col += vec3(0.05, 0.012, 0.06) * exp(-max(y, 0.0) / 20.0) * (1.0 - u_sun.w);  // street glow
            float floorH = cityFloorH(seed);                  // window rows = the walk-in floors above the shop
            float colW = 2.2 + hash11(seed * 3.31) * 2.2;
            vec2 g = vec2(u / colW, (yl - SHOP_H) / floorH);
            vec2 cell = floor(g);
            vec2 f = fract(g);
            float litP = 0.12 + 0.5 * hash11(seed * 5.71);
            float pal = hash11(seed * 9.91);
            if (dk == 1) { pal *= 0.44; litP = min(litP * 1.3, 0.75); hasNeon *= 0.3; }      // corporate: cool, busy
            else if (dk == 2) { pal = 0.8 + pal * 0.2; litP = min(litP * 1.4, 0.8); hasNeon = 1.0; }   // night market
            else if (dk == 3) { pal = 0.45 + pal * 0.34; }                                  // residential: warm
            else if (dk == 4) { pal = 0.45 + pal * 0.34; litP *= 0.45; hasNeon *= 0.5; }    // rust belt: dim
            else if (dk == 5) {                                                             // harbor warehouses
                pal = 0.45 + pal * 0.2; litP *= 0.35; hasNeon *= 0.4;
                col += vec3(0.02, 0.03, 0.035) * step(0.5, fract(u * 1.25));                // corrugated ribs
            }
            litP *= mix(1.0, 0.3, u_sun.w);                                                 // lights off by day
            float lit = step(hash13(vec3(cell, seed * 1.37 + faceId * 7.0)), litP);
            vec3 wc = windowColor(pal, hue, hash13(vec3(cell.yx, seed + faceId)));
            wc *= 0.5 + 0.9 * hash13(vec3(cell, seed + 3.0));
            if (dk == 4) { wc *= 0.6; col += vec3(0.05, 0.022, 0.01) * (0.5 + 0.5 * vnoise(v_world.xy * 0.3 + v_world.zy * 0.3)); }
            float wx = smoothstep(0.1, 0.16, f.x) * (1.0 - smoothstep(0.84, 0.9, f.x));
            float wy = smoothstep(0.2, 0.26, f.y) * (1.0 - smoothstep(0.8, 0.86, f.y));
            float win = wx * wy;
            vec3 dark = vec3(0.012, 0.014, 0.024) + skyColor(reflect(V, n)) * (0.02 + 0.12 * fres);
            vec3 pattern = mix(dark * win, wc, lit * win);
            vec3 avgc = (dark * (1.0 - litP) + windowColor(pal, hue, 0.5) * 0.95 * litP) * 0.33;
            float fade = smoothstep(0.25, 0.75, max(fwidth(g.x), fwidth(g.y)));
            col += mix(pattern, avgc, fade);
            vec3 nc = neon(hue) * 3.0;
            col += nc * hasNeon * aaLine(edgeU, 0.3);
            col += nc * step(0.3, hash11(seed * 4.41)) * aaLine(edgeTop, 0.5);
        } else if (n.y > 0.5) {
            dayAlb = 0.25;
            vec2 d2 = v_size.xz * 0.5 - abs(v_world.xz - v_center.xz);
            col += neon(hue) * 2.5 * hasNeon * aaLine(min(d2.x, d2.y), 0.4);
            vec2 q = v_world.xz / 5.0;                     // rooftop beacons and AC lights
            float on = step(0.93, hash13(vec3(floor(q), seed)));
            float dotv = 1.0 - smoothstep(0.12, 0.25, length(fract(q) - 0.5));
            vec3 lc = mix(vec3(3.0, 0.5, 0.3), vec3(0.6, 1.5, 2.5), hash12(floor(q) + 3.0));
            col += lc * mix(on * dotv, 0.07 * 0.15, smoothstep(0.3, 0.9, fwidth(q.x)));
        }
        albedo = 0.04;
    } else if (kind == 1) {                // ---------------- a megatower (extra = accent hue, 0 for Nexus)
        vec2 pw = v_world.xz - v_center.xz;                // tower-local
        float tHalf = v_size.x * 0.5;
        bool inHole = pw.x > tHalf - HOLE_XA && pw.x < tHalf - HOLE_XB && pw.y > HOLE_Z0 && pw.y < HOLE_Z1;
        if (!side && inHole) discard;                      // stairwell: lobby ceiling and roof hatch
        bool open = y > u_tower_open.x && y < u_tower_open.y && distance(v_center.xz, u_tower_open_c) < 1.0;
        bool inner = dot(V, n) > 0.0;
        if (open && n.x > 0.5 && abs(pw.y) < ELEV_DOOR_HALF && y > LOBBY_H
            && mod(y - LOBBY_H, 4.0) < ELEV_DOOR_H) discard;   // landing doorways next to the player
        if (side && inner) {               // the curtain wall seen from inside a floor
            vec2 f = fract(vec2(u / 1.6, y / 4.0));
            if (open && f.y > 0.14 && f.x > 0.08) discard;     // glass: see the city
            col = vec3(0.02, 0.022, 0.03) + vec3(0.1, 0.5, 0.6) * 0.5 * aaLine(abs(f.y - 0.14) * 4.0, 0.02);
            lightN = -n;
            dayAlb = 0.05;
        } else if (!side && inner) {       // roof seen from the top floor: ceiling lights
            vec2 f = abs(fract(v_world.xz / 3.0) - 0.5);
            float panel = (1.0 - smoothstep(0.3, 0.34, f.x)) * (1.0 - smoothstep(0.12, 0.16, f.y));
            col = vec3(0.02) + vec3(0.85) * panel * 0.5;
            lightN = -n;
        } else if (side) {
            float fl = y / 4.0;
            float g = u / 1.6;
            vec2 cell = floor(vec2(g, fl));
            vec2 f = fract(vec2(g, fl));
            float slab = 1.0 - step(0.14, f.y);
            float mull = 1.0 - step(0.08, f.x);
            vec3 glass = vec3(0.006, 0.01, 0.022) + skyColor(reflect(V, n)) * (0.03 + 0.35 * fres);
            float zone = hash12(vec2(floor(fl / 12.0), faceId));
            float litP = (0.04 + 0.3 * zone * zone) * mix(1.0, 0.3, u_sun.w);
            dayAlb = 0.16;
            float lit = step(hash13(vec3(cell, faceId * 17.0)), litP);
            vec3 wc = mix(vec3(0.45, 0.75, 1.25), vec3(1.0, 0.95, 0.85), hash13(vec3(cell.y, faceId, 3.0)));
            wc *= 0.4 + 0.6 * hash13(vec3(cell, 9.0));
            float win = (1.0 - slab) * (1.0 - mull);
            vec3 pat = glass * (1.0 - slab * 0.7) + wc * lit * win;
            vec3 avgc = glass * 0.8 + vec3(0.6, 0.8, 1.1) * 0.7 * litP * 0.78;
            float fade = smoothstep(0.3, 0.8, max(fwidth(g), fwidth(fl)));
            col = mix(pat, avgc, fade);
            col += vec3(0.2, 0.9, 1.0) * 4.0 * aaLine(edgeU, 1.2);                      // corners
            vec3 spine = extra > 0.0 ? neon(extra) * 1.2 : vec3(1.0, 0.15, 0.7);
            col += spine * 3.0 * aaLine(abs(u - cu), 0.7)                                 // spine
                   * (0.7 + 0.3 * sin(y * 0.02 - u_time * 3.0));
            float ring = abs(mod(y + 200.0, 400.0) - 200.0);                              // every 100 floors
            col += vec3(0.6, 0.9, 1.0) * 5.0 * aaLine(ring, 1.5);
            float pulse = fract(y / (v_center.y + v_size.y) * 3.0 - u_time * 0.08);      // rising light pulse
            col += vec3(0.3, 0.9, 1.0) * 4.0 * aaLine(edgeU, 2.0)
                   * smoothstep(0.0, 0.01, pulse) * (1.0 - smoothstep(0.01, 0.05, pulse));
            col += vec3(0.9, 0.5, 0.3) * 0.15 * exp(-max(y - 12.0, 0.0) / 25.0);         // street glow
        } else if (n.y > 0.5) {
            col = helipad(pw, moon, tHalf);
            dayAlb = 0.22;
        } else {
            vec2 t = abs(fract(v_world.xz / 6.0) - 0.5) * 6.0;                           // lobby ceiling
            col = vec3(0.03, 0.032, 0.04) + vec3(0.1, 0.5, 0.7) * 0.4 * max(aaLine(t.x, 0.04), aaLine(t.y, 0.04));
        }
        albedo = 0.06;
    } else if (kind == 2) {                // ---------------- interior panel
        float seam = aaLine(abs(fract(u / 1.5 + 0.5) - 0.5) * 1.5, 0.03);
        col = vec3(0.05, 0.055, 0.072) * (0.8 + 0.6 * moon) * (1.0 - 0.4 * seam);
        col += vec3(0.06, 0.07, 0.09) * fres;
        if (side) col += neon(hue) * 2.0 * aaLine(abs(yl - 1.0), 0.04);
        albedo = 0.12;
    } else if (kind == 3) {                // ---------------- emissive light / neon tube
        col = neon(hue) * extra;
    } else if (kind == 4) {                // ---------------- polished floor
        if (extra > 0.5 && !side && length(v_center.xz) < 1.0 && v_world.x > MALL_STAIR.x && v_world.x < MALL_STAIR.z
            && v_world.z > MALL_STAIR.y && v_world.z < MALL_STAIR.w) discard;   // Nexus lobby: stairs down to the mall
        col = vec3(0.025, 0.027, 0.035);
        if (n.y > 0.5) {
            vec2 p = v_world.xz;
            vec2 t = abs(fract(p / 3.0) - 0.5) * 3.0;
            col += vec3(0.08, 0.09, 0.12) * fres;
            col += vec3(0.2, 0.8, 1.0) * 0.5 * max(aaLine(t.x, 0.04), aaLine(t.y, 0.04));
            if (extra > 0.5) {             // tower lobby only: guide line from entrance to elevator
                p -= v_center.xz;
                float e = v_size.x * 0.5 - 1.0;                // lobby floor half extent + wall - 2 m
                float path = (p.y > 0.0 && p.y < e) ? aaLine(abs(p.x), 0.15) : 0.0;
                path = max(path, (p.x > 0.0 && p.x < e) ? aaLine(abs(p.y), 0.15) : 0.0);
                float flow = 0.5 + 0.5 * sin((p.x - p.y) * 0.8 - u_time * 6.0);
                col += vec3(0.2, 1.0, 0.9) * 3.0 * path * (0.4 + 0.6 * flow);
                col += vec3(1.0, 0.2, 0.7) * 2.0 * aaLine(abs(length(p - vec2(0.0, -15.0)) - 9.0), 0.08);
            }
        }
        albedo = 0.1;
    } else if (kind == 5) {                // ---------------- neon glyph sign
        vec3 nc = neon(hue);
        if (!side || hsu < 0.6) {
            col = nc * 0.8;
        } else {
            float scroll = hash11(seed) > 0.6 ? u_time * 1.5 : 0.0;
            vec2 q = vec2((u - cu + hsu) / 1.2, (yl + scroll) / 1.4);
            vec2 cell = floor(q);
            vec2 f = fract(q);
            float inside = step(0.12, f.x) * step(f.x, 0.88) * step(0.1, f.y) * step(f.y, 0.9);
            vec2 sg = floor((f - vec2(0.12, 0.1)) / vec2(0.76, 0.8) * vec2(3.0, 4.0));
            float glyph = inside * step(0.45, hash13(vec3(sg + cell * 7.0, seed)));
            float fade = smoothstep(0.3, 0.8, fwidth(q.x));
            glyph = mix(glyph, 0.35, fade);
            float flick = step(0.04, hash12(vec2(floor(u_time * 12.0), seed)));
            float border = max(aaLine(edgeU, 0.12), aaLine(min(yl, edgeTop), 0.12));
            col = nc * (0.12 + glyph * 2.8 * flick) + nc * border * 3.0;
        }
        albedo = 0.0;
    } else if (kind == 6) {                // ---------------- lobby curtain wall / pillars
        if (side) {
            col = vec3(0.015, 0.02, 0.035) + skyColor(reflect(V, n)) * (0.1 + 0.6 * fres);
            col += vec3(0.9, 0.6, 0.35) * 0.25 * smoothstep(12.0, 2.0, yl);
            col += vec3(0.2, 0.9, 1.0) * 2.5 * aaLine(abs(fract(u / 4.0 + 0.5) - 0.5) * 4.0, 0.08);
            col += vec3(0.2, 0.9, 1.0) * 3.0 * aaLine(edgeTop, 0.25);
        } else {
            col = vec3(0.03);
        }
        albedo = 0.08;
    } else if (kind == 7) {                // ---------------- antenna
        col = vec3(0.03, 0.03, 0.035);
        if (edgeTop < 1.2) col = vec3(3.0, 0.1, 0.05) * (step(0.5, fract(u_time * 0.7 + seed)) + 0.08);
    } else if (kind == 8) {                // ---------------- flying car
        // extra: +-1 driving direction (+-2 while braking); 0 marks a cabin (glass, no lights)
        bool alongX = v_size.x > v_size.z;
        float fwd = (alongX ? v_local.x : v_local.z) * sign(extra);
        col = vec3(0.02, 0.022, 0.03) + skyColor(reflect(V, n)) * 0.2;
        vec3 nc = neon(hue);
        if (abs(extra) > 0.5) {
            bool lamps = v_local.y > 0.3 && v_local.y < 0.7;
            if (fwd > 0.49 && lamps) col = vec3(7.0, 6.5, 5.5);
            if (fwd < -0.49 && lamps) col = abs(extra) > 1.5 ? vec3(9.0, 0.4, 0.25) : vec3(3.0, 0.2, 0.12);
            if (v_local.y < 0.06) col = nc * 4.0;
            if (side && abs(v_local.y - 0.55) < 0.04) col += nc * 2.0;
        } else if (side && v_local.y > 0.1 && v_local.y < 0.92) {
            col = vec3(0.02, 0.03, 0.05) + skyColor(reflect(V, n)) * 0.35 + nc * 0.06;
        }
    } else if (kind == 10) {               // ---------------- traffic signal head
        float axis = mod(extra, 2.0);
        float ph = mod(u_time + floor(extra / 2.0 + 0.01) * 4.0, CYCLE);
        float q = axis < 0.5 ? ph : ph - (GREEN + YELLOW);
        int lit = (q >= 0.0 && q < GREEN) ? 2 : ((q >= GREEN && q < GREEN + YELLOW) ? 1 : 0);
        col = vec3(0.025, 0.025, 0.03);
        if (side) {
            for (int i = 0; i < 3; i++) {                  // red (top), yellow, green (bottom)
                float d = length(vec2(u - cu, yl - v_size.y * (0.78 - 0.28 * float(i))));
                float lamp = 1.0 - smoothstep(0.12, 0.16, d);
                vec3 lc = i == 0 ? vec3(5.0, 0.25, 0.1) : (i == 1 ? vec3(5.0, 3.0, 0.2) : vec3(0.3, 5.0, 1.6));
                col += lc * lamp * (i == lit ? 1.0 : 0.04);
            }
        }
    } else if (kind == 13) {               // ---------------- pedestrian (extra = body part)
        int part = int(extra + 0.5);
        vec3 nc = neon(hue);
        vec3 jacket = hsv2rgb(vec3(hue, 0.55, 0.16)) + vec3(0.015) + skyColor(reflect(V, n)) * 0.12 * fres;
        vec3 skin = mix(vec3(0.16, 0.1, 0.07), vec3(0.45, 0.3, 0.22), hash11(seed * 3.1));
        if (part == 0) {                   // leg: dark trousers, glowing soles
            col = vec3(0.018, 0.018, 0.024);
            if (yl < 0.07) col = nc * 2.5;
        } else if (part == 1) {            // torso: jacket with neon chest band and trims
            col = jacket;
            if (side) col += nc * 2.2 * aaLine(abs(yl - v_size.y * 0.62), 0.025) + nc * 1.2 * aaLine(edgeU, 0.02);
        } else if (part == 2) {            // head: skin, hair (some dyed neon), optional visor
            col = skin;
            if (n.y > 0.5 || yl > v_size.y * 0.82)
                col = hash11(seed * 5.3) > 0.75 ? nc * 0.6 : vec3(0.012);
            else if (side && hash11(seed * 7.7) > 0.5 && abs(yl - v_size.y * 0.55) < v_size.y * 0.09)
                col = neon(fract(hue + 0.5)) * 3.0;
        } else if (part == 3) {            // arm: sleeve, hand at the end
            col = yl < 0.09 ? skin : jacket;
        } else if (part == 4) {            // umbrella canopy with a glowing rim
            float e = min(v_size.x * (0.5 - abs(v_local.x)), v_size.z * (0.5 - abs(v_local.z)));
            col = side ? nc * 3.0 : nc * (n.y < 0.0 ? 0.7 : 0.25) + vec3(0.015) + nc * 3.5 * aaLine(e, 0.04);
        } else {                           // umbrella handle
            col = vec3(0.03);
        }
        albedo = 0.1;
    } else if (kind == 15) {               // ---------------- metro car body (extra 0 wall, 1 roof)
        vec3 lc = neon(hue);
        bool alongX = v_size.x > v_size.z;
        float lu = alongX ? v_local.x * v_size.x : v_local.z * v_size.z;
        bool inside = dot(V, n) > 0.0;
        if (extra < 0.5) {
            if (side && yl > 0.95 && yl < 2.1 && abs(fract(lu / 2.0) - 0.5) < 0.38) discard;   // windows
            if (inside) {
                col = vec3(0.1, 0.105, 0.115) + lc * 0.8 * aaLine(abs(yl - 2.3), 0.03);
                lightN = -n;
            } else {
                col = vec3(0.16, 0.17, 0.19) * (0.5 + 0.5 * moon) + skyColor(reflect(V, n)) * (0.1 + 0.5 * fres);
                col += lc * 3.0 * aaLine(abs(yl - 0.35), 0.06) + lc * 2.0 * aaLine(abs(yl - 2.35), 0.03);
            }
        } else {
            col = inside ? vec3(0.12, 0.125, 0.135) : vec3(0.05, 0.052, 0.06) + skyColor(reflect(V, n)) * 0.2 * fres;
            if (!inside && n.y > 0.5) {
                vec2 d2 = v_size.xz * 0.5 - abs(v_world.xz - v_center.xz);
                col += lc * 2.5 * aaLine(min(d2.x, d2.y), 0.06);
            }
        }
        albedo = 0.12;
    } else if (kind == 14) {               // ---------------- tower floor slab
        if (n.y > 0.5) {                   // floor tiles
            vec2 t = abs(fract(v_world.xz / 2.0) - 0.5) * 2.0;
            col = (vec3(0.028, 0.03, 0.036) + neon(hue) * 0.012) * (1.0 - 0.5 * max(aaLine(t.x, 0.02), aaLine(t.y, 0.02)));
            col += vec3(0.05, 0.06, 0.08) * fres;
        } else if (n.y < -0.5) {           // ceiling of the storey below
            if (y < LOBBY_H) {             // 2F slab doubles as the lobby ceiling
                vec2 t = abs(fract(v_world.xz / 6.0) - 0.5) * 6.0;
                col = vec3(0.03, 0.032, 0.04) + vec3(0.1, 0.5, 0.7) * 0.4 * max(aaLine(t.x, 0.04), aaLine(t.y, 0.04));
            } else {
                vec2 f = abs(fract(v_world.xz / 3.0) - 0.5);
                float panel = (1.0 - smoothstep(0.3, 0.34, f.x)) * (1.0 - smoothstep(0.12, 0.16, f.y));
                col = vec3(0.02) + (vec3(0.85) + neon(hue) * 0.4) * panel * extra;
            }
        } else {
            col = vec3(0.03);
        }
        albedo = 0.1;
    } else if (kind == 12) {               // ---------------- shop partition wall (extra = shop type)
        col = shopInterior(int(extra + 0.5), n, side, u, yl, seed, faceId, fres);
        albedo = 0.1;
    } else if (kind == 11) {               // ---------------- shop ceiling (light grid underneath)
        col = vec3(0.02);
        if (n.y < -0.5) {
            vec2 f = abs(fract(v_world.xz / 2.5) - 0.5);
            float panel = (1.0 - smoothstep(0.32, 0.36, f.x)) * (1.0 - smoothstep(0.18, 0.22, f.y));
            col = vec3(0.03) + (vec3(0.9) + neon(hue) * 0.5) * panel * extra * 1.1;
        }
    } else {                               // ---------------- elevator door (9)
        col = vec3(0.07, 0.075, 0.09) * (0.7 + 0.5 * moon) + vec3(0.1, 0.12, 0.15) * fres;
        col += neon(hue) * 2.5 * max(aaLine(edgeU, 0.05), aaLine(abs(yl - 1.6), 0.03));
        albedo = 0.12;
    }

    if (kind > 1 && kind < 16) dayAlb = DAY_ALB[kind];
    col += dayAlb * daylight(lightN, v_wpos);
    col += bootLight(v_wpos, lightN) * albedo * 6.0;
    col = applyFog(col, v_wpos);
    f_color = vec4(col, 1.0);
    writeDepth(v_logz);
}
"""

for _token, _value in (("@SHOP_H@", C.SHOP_H), ("@DOOR_HALF@", C.SHOP_DOOR_HALF), ("@DOOR_H@", C.SHOP_DOOR_H),
                       ("@CYCLE@", C.SIGNAL_CYCLE), ("@GREEN@", C.SIGNAL_GREEN), ("@YELLOW@", C.SIGNAL_YELLOW),
                       ("@HXA@", C.STAIR_INSET - C.STAIR_LAND),
                       ("@HXB@", C.STAIR_INSET - 2 * C.STAIR_LAND - C.STAIR_RUN), ("@HZ0@", C.STAIR_Z0),
                       ("@HZ1@", C.STAIR_Z0 + 2 * C.STAIR_FLIGHT_W + C.STAIR_DIVIDER),
                       ("@LOBBY_H@", C.LOBBY_HEIGHT), ("@EDH@", C.ELEV_DOOR_HALF),
                       ("@EDHT@", C.ELEV_DOOR_HEIGHT)):
    BOX_FS = BOX_FS.replace(_token, f"{float(_value):.4f}")
BOX_FS = BOX_FS.replace("@MSTAIR@", ", ".join(f"{v:.4f}" for v in C.MALL_STAIR))

# ---------------------------------------------------------------------------
GROUND_VS = r"""
in vec2 in_pos;
uniform mat4 u_vp;
uniform float u_ground_y;                               // 0 for the streets, below for the sea pass
out vec3 v_world;
out float v_logz;
void main() {
    v_world = vec3(in_pos.x, u_ground_y, in_pos.y);
    gl_Position = u_vp * vec4(v_world, 1.0);
    v_logz = 1.0 + gl_Position.w;
}
"""

GROUND_FS = r"""
in vec3 v_world;
in float v_logz;
uniform float u_city_edge;
uniform vec4 u_holes[8];                                // (x0, z0, x1, z1) metro stairwell openings
uniform vec4 u_zones[16];                               // (x0, z0, x1, z1) special ground areas
uniform float u_zone_kind[16];                          // 0 tower lobby (own floor), 1 park, 2 plaza, -1 unused
uniform float u_water;                                  // 1: drawing the sea south of the quay
const float SHORE = @SHORE@;
out vec4 f_color;

// Night sea: wind ripples reflecting the sky glow, city lights smeared across the water near the quay.
vec3 seaColor(vec2 p, vec3 V) {
    float t = u_time;
    vec2 q = p * 0.06;
    float a = vnoise(q + vec2(t * 0.12, t * 0.08));
    float b = vnoise(q * 2.9 - vec2(t * 0.17, -t * 0.11));
    vec3 nrm = normalize(vec3((a - 0.5) * 0.4 + (b - 0.5) * 0.25, 1.0, (b - 0.5) * 0.4 - (a - 0.5) * 0.2));
    float fres = pow(1.0 - max(-V.y, 0.0), 4.0);
    vec3 col = vec3(0.003, 0.01, 0.018) + skyColor(reflect(V, nrm)) * (0.06 + 0.85 * fres);
    float near = exp(-(p.y - SHORE) / 220.0);
    float lane = vnoise(vec2(p.x * 0.09, t * 0.3 + p.y * 0.004));
    float glints = smoothstep(0.62, 0.9, lane) * (0.5 + 0.5 * b);
    vec3 lc = mix(vec3(1.0, 0.25, 0.8), vec3(0.2, 0.9, 1.0), step(0.5, vnoise(vec2(floor(p.x / 18.0), 3.0))));
    col += lc * glints * near * 0.9;
    col += vec3(0.4, 0.8, 1.0) * 0.6 * aaLine(p.y - SHORE - 0.6, 0.25) * (0.6 + 0.4 * a);   // foam line
    return col;
}

// Lawn with a neon-edged walking ring (13..21 m from the center) and paths out to the sidewalks.
vec3 parkGround(vec2 q, float n1, float n2) {
    float r = max(abs(q.x), abs(q.y));
    vec3 c = vec3(0.012, 0.03, 0.02) * (0.6 + 0.8 * n1) + vec3(0.0, 0.02, 0.01) * n2;
    bool path = (r > 13.0 && r < 21.0) || (min(abs(q.x), abs(q.y)) < 1.6 && r > 21.0);
    if (path) {
        c = vec3(0.035, 0.034, 0.04) * (0.8 + 0.4 * n2);
        float e = r > 21.0 ? abs(min(abs(q.x), abs(q.y)) - 1.6) : min(abs(r - 13.0), abs(r - 21.0));
        c += vec3(0.2, 1.0, 0.6) * 1.4 * aaLine(e, 0.08);
    }
    return c;
}

// Paving with glowing concentric rings around the fountain.
vec3 plazaGround(vec2 q, float n2) {
    vec2 t = abs(fract(q / 2.5) - 0.5) * 2.5;
    vec3 c = vec3(0.04, 0.038, 0.045) * (0.8 + 0.4 * n2);
    c *= 1.0 - 0.4 * max(aaLine(t.x, 0.03), aaLine(t.y, 0.03));
    float r = length(q);
    c += vec3(1.0, 0.6, 0.2) * 1.6 * aaLine(abs(r - 9.0), 0.1) + vec3(0.3, 0.8, 1.0) * 1.2 * aaLine(abs(r - 16.0), 0.08);
    c += vec3(1.0, 0.2, 0.7) * 0.8 * aaLine(abs(r - 24.0), 0.06) * (0.6 + 0.4 * sin(atan(q.y, q.x) * 12.0 - u_time * 2.0));
    return c;
}

void main() {
    vec2 p = v_world.xz;
    if (u_water > 0.5) {                                   // the sea pass
        if (p.y < SHORE) discard;
        vec3 Vw = normalize(v_world - u_cam);
        vec3 sea = seaColor(p, Vw) + bootLight(v_world, vec3(0.0, 1.0, 0.0)) * 0.2
                 + vec3(0.02, 0.05, 0.07) * daylight(vec3(0.0, 1.0, 0.0), vec3(0.0));
        f_color = vec4(applyFog(sea, v_world), 1.0);
        writeDepth(v_logz);
        return;
    }
    if (p.y > SHORE) discard;                              // street level ends at the quay
    for (int i = 0; i < 8; i++) {
        vec4 h = u_holes[i];
        if (p.x > h.x && p.x < h.z && p.y > h.y && p.y < h.w) discard;
    }
    int zk = -1;
    vec2 zc = vec2(0.0);
    for (int i = 0; i < 16; i++) {
        vec4 r = u_zones[i];
        if (u_zone_kind[i] > -0.5 && p.x > r.x && p.x < r.z && p.y > r.y && p.y < r.w) {
            zk = int(u_zone_kind[i] + 0.5);
            zc = (r.xy + r.zw) * 0.5;
            break;
        }
    }
    if (zk == 0) discard;                                  // tower lobbies have their own floor
    vec3 V = normalize(v_world - u_cam);
    vec2 rdist = abs(fract((p - 40.0) / 80.0 + 0.5) - 0.5) * 80.0;   // distance to road centerlines
    float ext = max(abs(p.x), abs(p.y));
    float n1 = vnoise(p * 0.15);
    float n2 = vnoise(p * 1.3);
    vec3 col;
    float wet;
    vec3 dalb = vec3(0.13);                                // daylight albedo
    if (ext < 112.0) {                                     // tower plaza
        dalb = vec3(0.16);
        vec2 t = abs(fract(p / 4.0) - 0.5) * 4.0;
        col = vec3(0.03, 0.03, 0.04) * (0.8 + 0.4 * n2);
        col += vec3(0.1, 0.6, 0.9) * 0.35 * max(aaLine(t.x, 0.04), aaLine(t.y, 0.04));
        col += vec3(1.0, 0.15, 0.75) * 2.5 * aaLine(abs(ext - 46.0), 0.25);
        col += vec3(0.2, 0.9, 1.0) * 1.5 * aaLine(abs(ext - 52.0), 0.12);
        if (p.y > 40.0) {
            float flow = 0.5 + 0.5 * sin(p.y * 0.6 + u_time * 5.0);
            col += vec3(0.2, 0.9, 1.0) * 2.0 * aaLine(abs(abs(p.x) - 6.5), 0.12) * (0.5 + 0.5 * flow);
        }
        wet = 0.55;
    } else if (ext > u_city_edge) {                        // endless low-rise sprawl, lights only
        float rd = min(rdist.x, rdist.y);
        col = vec3(0.01, 0.009, 0.014) * (0.6 + 0.8 * n1);
        col += vec3(1.0, 0.55, 0.2) * 0.7 * aaLine(rd, 1.2);
        vec2 ad = abs(fract((p - 40.0) / 640.0 + 0.5) - 0.5) * 640.0;
        col += vec3(0.2, 0.8, 1.0) * 1.3 * aaLine(ad.x, 2.5) + vec3(1.0, 0.2, 0.7) * 1.3 * aaLine(ad.y, 2.5);
        vec2 q = p / 7.0;
        vec2 cell = floor(q);
        float lit = step(0.9, hash12(cell));
        vec3 lc = mix(vec3(1.3, 0.7, 0.3), vec3(0.5, 0.8, 1.4), hash12(cell + 7.0));
        float dotv = 1.0 - smoothstep(0.2, 0.35, length(fract(q) - 0.5));
        float fade = smoothstep(0.3, 1.0, fwidth(q.x));
        col += lc * mix(lit * dotv * 2.0, 0.05, fade) * step(10.5, rd);
        col *= smoothstep(u_city_edge, u_city_edge + 60.0, ext) * 0.8 + 0.2;
        wet = 0.15;
        dalb = vec3(0.09);
    } else {
        float rd = min(rdist.x, rdist.y);
        if (rd < 8.0) {                                    // road, lit by sodium street lamps
            col = vec3(0.014, 0.014, 0.018) * (0.7 + 0.6 * n2);
            col += vec3(1.0, 0.55, 0.22) * 0.025 * smoothstep(8.0, 4.0, abs(rd - 6.0) + 2.0);
            if (!(rdist.x < 8.0 && rdist.y < 8.0)) {
                bool alongZ = rdist.x < rdist.y;
                float along = alongZ ? p.y : p.x;
                float acr = alongZ ? p.x : p.y;
                float other = alongZ ? rdist.y : rdist.x;           // distance to the crossing road
                if (other < 11.6) {                                 // zebra crossing + stop line
                    col += vec3(0.5) * step(8.4, other) * step(other, 10.6) * step(0.5, fract(acr / 1.1));
                    col += vec3(0.7) * aaLine(abs(other - 11.3), 0.15);
                } else {
                    col += vec3(1.0, 0.7, 0.1) * 0.9 * aaLine(abs(rd - 0.2), 0.07);
                    col += vec3(0.7) * aaLine(abs(rd - 4.0), 0.1) * step(0.5, fract(along / 6.0));
                }
                col += vec3(0.2, 0.8, 1.0) * 1.8 * aaLine(abs(rd - 7.6), 0.1);
            }
            wet = 0.7;
            dalb = vec3(0.075, 0.075, 0.085) * (0.8 + 0.4 * n2);
        } else if (rd < 10.5) {                            // sidewalk
            col = vec3(0.04, 0.04, 0.05) * (0.8 + 0.4 * n2);
            col += vec3(1.0, 0.2, 0.7) * 0.8 * aaLine(abs(rd - 8.15), 0.08);
            wet = 0.45;
            dalb = vec3(0.17);
        } else if (zk == 1) {
            col = parkGround(p - zc, n1, n2);
            wet = 0.2;
            dalb = vec3(0.06, 0.13, 0.05) * (0.7 + 0.6 * n1);
        } else if (zk == 2) {
            col = plazaGround(p - zc, n2);
            wet = 0.5;
            dalb = vec3(0.2, 0.19, 0.17);
        } else {
            col = vec3(0.03, 0.03, 0.035);
            wet = 0.3;
        }
    }
    float puddle = smoothstep(0.55, 0.7, n1) * u_wet;          // puddles only after rain
    wet = mix(wet * mix(0.2, 1.0, u_wet), 1.0, puddle);
    col += dalb * daylight(vec3(0.0, 1.0, 0.0), v_world) * (1.0 - 0.5 * puddle);
    float fres = pow(1.0 - max(-V.y, 0.0), 5.0);
    vec3 refl = skyColor(reflect(V, vec3(0.0, 1.0, 0.0)));
    col = col * (1.0 - puddle * 0.5) + refl * (0.04 + 0.9 * fres) * wet;
    col += bootLight(v_world, vec3(0.0, 1.0, 0.0)) * 0.3;
    col = applyFog(col, v_world);
    f_color = vec4(col, 1.0);
    writeDepth(v_logz);
}
"""

GROUND_FS = GROUND_FS.replace("@SHORE@", f"{float(C.SHORE_Z):.4f}")

# ---------------------------------------------------------------------------
FS_VS = r"""
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

SKY_FS = r"""
in vec2 v_uv;
uniform mat4 u_inv_vp_rot;
out vec4 f_color;
void main() {
    vec4 p = u_inv_vp_rot * vec4(v_uv * 2.0 - 1.0, 1.0, 1.0);
    vec3 d = normalize(p.xyz / p.w);
    vec3 col = skyColor(d);
    float day = u_sun.w, cloud = cloudBelow(u_cam.y);
    if (d.y > 0.0) {
        float night = (1.0 - day) * (1.0 - 0.85 * cloud);
        vec3 q = floor(d * 700.0);
        float h = hash13(q);
        float star = step(0.9985, h) * (0.4 + 0.6 * hash13(q + 1.0));
        star *= 0.6 + 0.4 * sin(u_time * 3.0 + h * 100.0);
        col += vec3(0.8, 0.85, 1.0) * star * smoothstep(0.05, 0.3, d.y) * 1.5 * night;
        vec3 md = normalize(-u_sun.xyz + vec3(0.0, 0.25, 0.0));        // the moon rides opposite the sun
        float m = dot(d, md);
        col += vec3(0.9, 0.85, 1.0) * 2.5 * smoothstep(0.9993, 0.9995, m) * night;
        col += vec3(0.5, 0.3, 0.7) * pow(max(m, 0.0), 300.0) * 0.6 * night;
        float cl = vnoise(d.xz / max(d.y, 0.05) * 1.5 + u_time * 0.01);
        vec3 band = mix(vec3(0.18, 0.05, 0.2), vec3(0.62, 0.64, 0.68), day);
        col = mix(col, band, cl * (0.2 + 0.5 * cloud) * smoothstep(0.4, 0.0, d.y));
    }
    vec3 sd = normalize(u_sun.xyz);                                    // the sun (can set below the horizon)
    float s = dot(d, sd);
    float vis = (1.0 - 0.9 * cloud) * smoothstep(-0.04, 0.02, d.y);
    vec3 sc = mix(vec3(4.0, 1.6, 0.6), vec3(6.0, 5.6, 5.0), smoothstep(0.0, 0.35, sd.y));
    col += sc * smoothstep(0.99955, 0.9997, s) * vis;
    col += mix(vec3(1.0, 0.45, 0.2), vec3(1.0, 0.9, 0.75), smoothstep(0.0, 0.35, sd.y)) * pow(max(s, 0.0), 40.0) * 0.6 * vis;
    f_color = vec4(col, 1.0);
}
"""

# --------------------------------------------------------------- cloud layer
CLOUD_VS = r"""
in vec2 in_pos;
uniform mat4 u_vp;
uniform vec3 u_cam;
out vec3 v_world;
out float v_logz;
void main() {
    v_world = vec3(in_pos.x + u_cam.x, @CLOUD_Y@, in_pos.y + u_cam.z);   // follows the camera
    gl_Position = u_vp * vec4(v_world, 1.0);
    v_logz = 1.0 + gl_Position.w;
}
"""

CLOUD_FS = r"""
in vec3 v_world;
in float v_logz;
out vec4 f_color;
float fbm(vec2 p) {
    float s = 0.0, a = 0.5;
    for (int i = 0; i < 5; i++) {
        s += a * vnoise(p);
        p = p * 2.03 + vec2(17.1, 9.3);
        a *= 0.5;
    }
    return s;
}
void main() {
    float cover = u_env.y;
    if (cover < 0.02) discard;
    vec2 q = v_world.xz * 0.0011 + u_time * vec2(0.006, 0.0025);
    float n = fbm(q);
    float th = mix(0.85, 0.3, cover);
    float a = smoothstep(th, th + 0.25, n) * mix(0.55, 0.97, cover);
    float dist = length(v_world - u_cam);
    a *= 1.0 - smoothstep(9000.0, 28000.0, dist);
    if (a < 0.003) discard;
    float day = u_sun.w;
    vec3 sd = normalize(u_sun.xyz);
    bool above = u_cam.y > v_world.y;
    // top: sunlit (warm at dusk); underside: darker; at night the city glow tints the underside
    vec3 lit = mix(vec3(1.0, 0.55, 0.35), vec3(1.0, 0.98, 0.95), smoothstep(0.0, 0.35, sd.y)) * (0.25 + 0.95 * day);
    vec3 night = above ? vec3(0.05, 0.05, 0.09) : vec3(0.16, 0.05, 0.15);
    vec3 col = mix(night, lit, day);
    if (!above) col *= 0.55 + 0.25 * (1.0 - n);
    col *= 0.8 + 0.35 * n;
    col += vec3(0.8, 0.85, 1.0) * u_env.w * 2.0;
    col = mix(col, skyColor(normalize(v_world - u_cam)), smoothstep(4000.0, 24000.0, dist));
    f_color = vec4(col * a, a);
    writeDepth(v_logz);
}
"""
CLOUD_VS = CLOUD_VS.replace("@CLOUD_Y@", f"{CLOUD_Y:.1f}")

# ---------------------------------------------------------------------------
QUAD_VS = r"""
in vec2 in_corner;
in vec3 i_center;
in vec3 i_right;
in vec3 i_up;
in vec4 i_params;
uniform mat4 u_vp;
out vec2 v_uv;
flat out vec4 v_params;
flat out vec2 v_dims;
out vec3 v_world;
out float v_logz;
void main() {
    vec3 wp = i_center + in_corner.x * i_right + in_corner.y * i_up;
    v_uv = in_corner * 0.5 + 0.5;
    v_params = i_params;
    v_dims = vec2(length(i_right), length(i_up)) * 2.0;
    v_world = wp;
    gl_Position = u_vp * vec4(wp, 1.0);
    v_logz = 1.0 + gl_Position.w;
}
"""

QUAD_FS = r"""
in vec2 v_uv;
flat in vec4 v_params;
flat in vec2 v_dims;
in vec3 v_world;
in float v_logz;
out vec4 f_color;
void main() {
    float seed = v_params.x;
    int mode = int(v_params.y + 0.5);
    float hue = v_params.z;
    float inten = v_params.w;
    vec2 px = v_uv * v_dims;
    float border = max(aaLine(min(px.x, v_dims.x - px.x), 0.25), aaLine(min(px.y, v_dims.y - px.y), 0.25));
    vec3 nc = hsv2rgb(vec3(hue, 0.75, 1.0));
    float fog = fogFactor(v_world);

    if (mode == 1) {                       // elevator glass (premultiplied alpha)
        float frame = max(aaLine(min(px.x, v_dims.x - px.x), 0.05), aaLine(min(px.y, v_dims.y - px.y), 0.05));
        float streak = aaLine(abs(fract((px.x + px.y * 0.6) / 3.0 + 0.5) - 0.5) * 3.0, 0.12);
        vec3 col = vec3(0.05, 0.1, 0.14) + vec3(0.6, 0.8, 1.0) * streak * 0.12;
        float a = 0.08 + streak * 0.03 + frame * 0.8;
        col += vec3(0.2, 0.9, 1.0) * 3.0 * frame;
        f_color = vec4(col * a, a);
    } else if (mode == 2) {                // floor gauge inside the car (additive)
        float fill = step(v_uv.y, inten);
        float ticks = aaLine(abs(fract(v_uv.y * 10.0 + 0.5) - 0.5) * v_dims.y / 10.0, 0.01);
        float head = aaLine(abs(v_uv.y - inten) * v_dims.y, 0.02);
        vec3 col = nc * (0.08 + fill * 1.2) + vec3(0.8) * ticks * 0.6 + nc * border * 2.0 + vec3(3.0) * head;
        f_color = vec4(col, 1.0);
    } else {                               // hologram advert (additive)
        vec3 nc2 = hsv2rgb(vec3(fract(hue + 0.15), 0.7, 1.0));
        float content;
        if (hash11(seed * 3.7) < 0.55) {
            vec2 q = (px - 1.0) / vec2(2.2, 2.6);
            q.y += u_time * (0.5 + hash11(seed));
            vec2 cell = floor(q);
            vec2 f = fract(q);
            vec2 sg = floor(f * vec2(4.0, 5.0));
            float on = step(0.5, hash13(vec3(sg + cell * 13.0, seed)));
            on *= step(0.1, f.x) * step(f.x, 0.9) * step(0.08, f.y) * step(f.y, 0.92);
            content = on * step(0.25, hash12(vec2(cell.x, seed)));
            content = mix(content, 0.3, smoothstep(0.3, 0.8, fwidth(q.x * 4.0)));
        } else {
            vec2 c = (v_uv - 0.5) * v_dims / min(v_dims.x, v_dims.y);
            float r = length(c);
            float a = atan(c.y, c.x);
            content = aaLine(abs(r - 0.38), 0.02);
            content += aaLine(abs(r - 0.29), 0.012) * step(0.5, fract(a * 3.0 / 6.2831853 + u_time * 0.3));
            float s = 0.15 * (1.0 + 0.1 * sin(u_time * 2.0));
            float tri = max(abs(c.x) * 0.866 + c.y * 0.5, -c.y) - s;
            content += (1.0 - smoothstep(-0.005, 0.005, tri)) * 0.8;
        }
        float scan = 0.75 + 0.25 * sin(px.y * 8.0 - u_time * 6.0);
        float flick = 0.8 + 0.2 * step(0.08, hash12(vec2(floor(u_time * 15.0), seed)));
        vec3 col = (nc * content * 2.2 + nc2 * border * 2.5 + nc * 0.06) * scan * flick * inten;
        f_color = vec4(col * (1.0 - fog), 1.0);
    }
    if (mode == 1) f_color *= (1.0 - fog);
    writeDepth(v_logz);
}
"""

# ---------------------------------------------------------------------------
PART_VS = r"""
in vec3 in_pos;
in vec4 in_color;
in float in_size;
uniform mat4 u_vp;
uniform float u_pscale;
out vec4 v_color;
out float v_logz;
void main() {
    gl_Position = u_vp * vec4(in_pos, 1.0);
    v_logz = 1.0 + gl_Position.w;
    gl_PointSize = clamp(in_size * u_pscale / max(gl_Position.w, 0.05), 1.0, 400.0);
    v_color = in_color;
}
"""

PART_FS = r"""
in vec4 v_color;
in float v_logz;
out vec4 f_color;
void main() {
    vec2 c = gl_PointCoord * 2.0 - 1.0;
    float r2 = dot(c, c);
    if (r2 > 1.0) discard;
    float a = (1.0 - r2);
    a = a * a * v_color.a;
    f_color = vec4(v_color.rgb * a, a);
    writeDepth(v_logz);
}
"""

LINE_VS = r"""
in vec3 in_pos;
in vec4 in_color;
uniform mat4 u_vp;
out vec4 v_color;
out float v_logz;
void main() {
    gl_Position = u_vp * vec4(in_pos, 1.0);
    v_logz = 1.0 + gl_Position.w;
    v_color = in_color;
}
"""

LINE_FS = r"""
in vec4 v_color;
in float v_logz;
out vec4 f_color;
void main() {
    f_color = vec4(v_color.rgb * v_color.a, v_color.a);
    writeDepth(v_logz);
}
"""

# --------------------------------------------------------------- post-process
BRIGHT_FS = r"""
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_texel;
out vec4 f_color;
void main() {
    vec3 c = texture(u_tex, v_uv + u_texel * vec2(-0.5, -0.5)).rgb;
    c += texture(u_tex, v_uv + u_texel * vec2(0.5, -0.5)).rgb;
    c += texture(u_tex, v_uv + u_texel * vec2(-0.5, 0.5)).rgb;
    c += texture(u_tex, v_uv + u_texel * vec2(0.5, 0.5)).rgb;
    c = min(c * 0.25, vec3(60.0));
    float l = max(max(c.r, c.g), c.b);
    f_color = vec4(c * max(l - 0.9, 0.0) / max(l, 1e-4), 1.0);
}
"""

DOWN_FS = r"""
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_texel;
out vec4 f_color;
void main() {
    vec3 c = texture(u_tex, v_uv + u_texel * vec2(-0.5, -0.5)).rgb;
    c += texture(u_tex, v_uv + u_texel * vec2(0.5, -0.5)).rgb;
    c += texture(u_tex, v_uv + u_texel * vec2(-0.5, 0.5)).rgb;
    c += texture(u_tex, v_uv + u_texel * vec2(0.5, 0.5)).rgb;
    f_color = vec4(c * 0.25, 1.0);
}
"""

BLUR_FS = r"""
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_dir;
out vec4 f_color;
void main() {
    vec3 c = texture(u_tex, v_uv).rgb * 0.2270270270;
    c += texture(u_tex, v_uv + u_dir * 1.3846153846).rgb * 0.3162162162;
    c += texture(u_tex, v_uv - u_dir * 1.3846153846).rgb * 0.3162162162;
    c += texture(u_tex, v_uv + u_dir * 3.2307692308).rgb * 0.0702702703;
    c += texture(u_tex, v_uv - u_dir * 3.2307692308).rgb * 0.0702702703;
    f_color = vec4(c, 1.0);
}
"""

COMPOSITE_FS = r"""
in vec2 v_uv;
uniform sampler2D u_scene;
uniform sampler2D u_bloom1;
uniform sampler2D u_bloom2;
uniform sampler2D u_bloom3;
uniform float u_speed;     // 0..1 free-fall intensity
uniform float u_thrust;    // 0..1.5 rocket boot thrust
uniform float u_exposure;  // lower by day so the sunlit city does not blow out
out vec4 f_color;

vec3 aces(vec3 x) {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

void main() {
    vec2 uv = v_uv;
    vec2 c = uv - 0.5;
    float ca = 0.0015 + u_speed * 0.006 + u_thrust * 0.003;
    vec3 col;
    col.r = texture(u_scene, uv - c * ca).r;
    col.g = texture(u_scene, uv).g;
    col.b = texture(u_scene, uv + c * ca).b;
    vec3 bloom = texture(u_bloom1, uv).rgb * 0.5 + texture(u_bloom2, uv).rgb * 0.7 + texture(u_bloom3, uv).rgb * 0.9;
    col += bloom * 0.55;
    float flick = 0.85 + 0.15 * sin(u_time * 43.0) * sin(u_time * 17.0);
    col += vec3(1.0, 0.4, 0.08) * u_thrust * 0.45 * pow(clamp(1.0 - uv.y * 1.7, 0.0, 1.0), 2.0) * flick;
    col += vec3(0.8, 0.85, 1.0) * u_env.w * 0.12;                // lightning
    col = aces(col * 1.05 * u_exposure);
    float vig = 1.0 - dot(c, c) * (0.8 + u_speed * 1.8);
    col *= clamp(vig, 0.0, 1.0);
    col = pow(col, vec3(1.0 / 2.2));
    col *= 0.975 + 0.025 * sin(gl_FragCoord.y * 3.14159);
    col += (hash12(gl_FragCoord.xy + fract(u_time) * 913.0) - 0.5) * 0.025;
    f_color = vec4(col, 1.0);
}
"""

HUD_FS = r"""
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 f_color;
void main() {
    f_color = texture(u_tex, v_uv);
}
"""
