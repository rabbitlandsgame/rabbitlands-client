"""The ground a trail road runs through, from a layout's `land` block.

build_trail.py walks only the route network; this module shapes everything
round it, and the water and gaps the network crosses. A layout without a
`land` block (the Harrowcrag Road) keeps the builder's own crag-and-river
terrain. TRAIL_FORMAT.md lists the keys.

All functions take plan coordinates (x east, y south, metres) as numpy arrays
of any shape. The land itself needs a regular lattice (it blurs the road's
level); the masks and the carving are pointwise, so the collision cells and
the mesh quads read the same features the lattice was carved with.
"""
from __future__ import annotations

import math
import zlib

import numpy as np


def seeded(name: str) -> int:
    return zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def value_noise(px, py, scale, seed, octaves=3):
    rng = np.random.default_rng(seed)
    out = np.zeros_like(px, dtype=np.float64)
    amp, freq = 1.0, 1.0 / scale
    for _ in range(octaves):
        grid = rng.standard_normal((int(600 * freq) + 4, int(600 * freq) + 4))
        fx, fy = (px + 60) * freq, (py + 60) * freq
        x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = smooth(fx - x0), smooth(fy - y0)
        a = grid[y0, x0] * (1 - tx) + grid[y0, x0 + 1] * tx
        b = grid[y0 + 1, x0] * (1 - tx) + grid[y0 + 1, x0 + 1] * tx
        out += amp * (a * (1 - ty) + b * ty)
        amp *= 0.5
        freq *= 2.0
    return out


def box_blur(a, r):
    for axis in (0, 1):
        pad = np.pad(a, [(r, r) if i == axis else (0, 0) for i in range(2)], mode="edge")
        cs = np.insert(np.cumsum(pad, axis=axis), 0, 0, axis=axis)
        n = a.shape[axis]
        a = (np.take(cs, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
             - np.take(cs, np.arange(0, n), axis=axis)) / (2 * r + 1)
    return a


def polyline(px, py, points):
    """(distance to a polyline, the third coordinate interpolated at the nearest point).

    Points are [x, y] or [x, y, level]; the level is 0 where none is given."""
    best = np.full(px.shape, 1e9)
    level = np.zeros(px.shape)
    for a, b in zip(points, points[1:]):
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        la = a[2] if len(a) > 2 else 0.0
        lb = b[2] if len(b) > 2 else 0.0
        dx, dy = bx - ax, by - ay
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
        d = np.hypot(px - (ax + t * dx), py - (ay + t * dy))
        take = d < best
        best = np.where(take, d, best)
        level = np.where(take, la + (lb - la) * t, level)
    return best, level


def ellipse_k(px, py, at, rx, ry, rot=0.0):
    r = math.radians(rot)
    dx, dy = px - at[0], py - at[1]
    u = dx * math.cos(r) + dy * math.sin(r)
    v = -dx * math.sin(r) + dy * math.cos(r)
    return np.hypot(u / rx, v / ry)


def in_rect(px, py, at, half, rot=0.0):
    r = math.radians(rot)
    dx, dy = px - at[0], py - at[1]
    u = dx * math.cos(r) + dy * math.sin(r)
    v = -dx * math.sin(r) + dy * math.cos(r)
    return (np.abs(u) <= half[0]) & (np.abs(v) <= half[1])


class Land:
    """A layout's `land` block as functions of plan position."""

    def __init__(self, layout):
        self.layout = layout
        self.spec = layout.data["land"]
        self.name = layout.data.get("id") or layout.data.get("_route", "trail")
        self.water_mode = "waterLevel" in self.spec
        self.water_level = float(self.spec.get("waterLevel", 0.0))

    def seed(self, tag):
        return seeded(f"{self.name}:{tag}")

    def noise(self, px, py, scale, tag, octaves=3):
        return value_noise(px, py, scale, self.seed(tag), octaves)

    # ------------------------------------------------------------ before the road
    def base(self, px, py, step, elev, owner):
        """The land before the road is carved in, on a regular lattice of `step` metres."""
        s = self.spec
        W, H = self.layout.W, self.layout.H
        hills = s.get("hills", 4.0)
        edge = np.minimum.reduce([px, py, W - px, H - py])
        if self.water_mode:
            land = s["floor"] + 0.3 * hills * self.noise(px, py, 40, "floor")
            if "shore" in s:
                rise = smooth((70 - edge + 22 * self.noise(px, py, 45, "shore", 3)) / 34)
                land = land + rise * (s["shore"] - s["floor"] + 2.0 * self.noise(px, py, 18, "shore2", 2))
        else:
            # the land round the road follows the road's own level, smoothed, so a climbing
            # road climbs a hillside and does not cut a trench
            e_route = elev.copy()
            r = max(2, int(18 / step))
            for _ in range(3):
                e_route = box_blur(e_route, r)
            land = (e_route + s.get("banks", 6.0) + hills * self.noise(px, py, 60, "hills")
                    + 0.45 * hills * self.noise(px, py, 18, "hills2"))
            land = land + np.clip(30 - edge, 0, None) * s.get("frame", 0.55)
        for wall in s.get("walls", []):
            t = (70 - px) / 70 if wall["side"] == "west" else (px - (W - 70)) / 70
            land = land + wall["height"] * smooth(t + 0.12 * self.noise(px, py, 30, "wall" + wall["side"])) ** 1.4
        for i, m in enumerate(s.get("massifs", []) + s.get("islands", [])):
            k = ellipse_k(px, py, m["at"], m["rx"], m["ry"], m.get("rot", 0)) + 0.05 * self.noise(px, py, 16, f"mesa{i}")
            top = m["top"] + 0.6 * self.noise(px, py, 10, f"mesatop{i}", 2)
            fall = m.get("fall", 9.0)
            t = np.clip((k - 1.0) * min(m["rx"], m["ry"]) / fall, 0, 1) ** 0.6
            land = np.maximum(land, top * (1 - t) + land * t)
        for pit in s.get("pits", []):
            rr = np.hypot(px - pit["at"][0], py - pit["at"][1])
            prof = np.array(pit["profile"], float)
            R, r0, n = pit["r"], pit["inner"], pit["benches"]
            ring = np.clip((rr - r0) / (R - r0) * n, 0, n - 1e-6)
            idx = np.floor(ring)
            level = np.interp(r0 + (idx + 0.5) * (R - r0) / n, prof[:, 0], prof[:, 1])
            nxt = np.interp(r0 + (idx + 1.5) * (R - r0) / n, prof[:, 0], prof[:, 1])
            wall_t = smooth((ring - idx - 0.86) / 0.14)
            bench = np.where(rr < r0, prof[0, 1], level + (nxt - level) * wall_t) + 0.25 * self.noise(px, py, 9, "bench", 2)
            land = np.where(rr < R, bench, np.maximum(land, prof[-1, 1] + 1.0))
        if s.get("paddies"):
            land = np.where(self.bunds(px, py), np.maximum(land, self.water_level + 0.5), land)
        return land

    def bunds(self, px, py):
        a = math.radians(8)
        u = px * math.cos(a) + py * math.sin(a)
        v = -px * math.sin(a) + py * math.cos(a)
        return (np.mod(u, 34) < 2.8) | (np.mod(v, 26) < 2.8)

    def mesa(self, px, py):
        """Where a massif's flat top is (for its own ground)."""
        out = np.zeros(px.shape, bool)
        for i, m in enumerate(self.spec.get("massifs", [])):
            k = ellipse_k(px, py, m["at"], m["rx"], m["ry"], m.get("rot", 0)) + 0.05 * self.noise(px, py, 16, f"mesa{i}")
            out |= k < 1.0
        return out

    # ------------------------------------------------------------ what the road crosses
    def crossing(self, px, py):
        out = np.zeros(px.shape, bool)
        for c in self.spec.get("crossings", []):
            out |= in_rect(px, py, c["at"], c["half"], c.get("rot", 0))
        return out

    def features(self, px, py):
        """Pointwise masks: lakes, rivers, canals, crevasses, mounds; and which of them close the ground."""
        s = self.spec
        keep = self.crossing(px, py)
        lake = np.zeros(px.shape, bool)
        lake_deep = np.zeros(px.shape, bool)
        lake_level = np.full(px.shape, np.nan)
        lake_floor = np.full(px.shape, np.nan)
        for i, lk in enumerate(s.get("lakes", [])):
            k = ellipse_k(px, py, lk["at"], lk["rx"], lk["ry"], lk.get("rot", 0)) + 0.08 * self.noise(px, py, 8, f"lake{i}", 2)
            inside = k < 1.0
            lake |= inside
            if lk.get("deep", True):
                lake_deep |= inside
            lake_level = np.where(inside, lk["level"], lake_level)
            lake_floor = np.where(inside, lk["level"] - (0.6 + (1 - k)) if lk.get("deep", True)
                                  else lk["level"] - lk.get("depth", 0.3), lake_floor)
        river = np.zeros(px.shape, bool)
        river_bank = np.full(px.shape, 1e9)
        river_level = np.full(px.shape, np.nan)
        dry = np.zeros(px.shape, bool)
        for i, rv in enumerate(s.get("rivers", [])):
            d, level = polyline(px, py, rv["points"])
            half = rv["width"] / 2 * (1 + 0.15 * self.noise(px, py, 20, f"river{i}", 2))
            if self.water_mode and not any(len(p) > 2 for p in rv["points"]):
                level = np.full(px.shape, self.water_level)
            if rv.get("dry"):
                dry |= d < half + 1.5
                continue
            wet = d < half
            river |= wet
            river_level = np.where(wet, level, river_level)
            river_bank = np.where(d - half < river_bank, d - half, river_bank)
        canal = np.zeros(px.shape, bool)
        for cn in s.get("canals", []):
            d, _ = polyline(px, py, cn["points"])
            canal |= d < cn["width"] / 2
        crev = np.zeros(px.shape, bool)
        crev_depth = np.zeros(px.shape)
        for i, cv in enumerate(s.get("crevasses", [])):
            d, _ = polyline(px, py, cv["points"])
            half = cv["width"] / 2 * (1 + 0.3 * self.noise(px, py, 10, f"crev{i}", 2))
            inside = d < half
            crev |= inside
            crev_depth = np.maximum(crev_depth, np.where(inside, cv["depth"] * np.sqrt(np.clip(1 - (d / half) ** 2, 0.05, 1)), 0))
        dome = np.zeros(px.shape)
        for m in s.get("mounds", []):
            rr = np.hypot(px - m["at"][0], py - m["at"][1]) / m["r"]
            h = m["h"] * np.sqrt(np.clip(1 - rr * rr, 0, None))
            if m.get("split"):
                h = np.where(np.abs(py - m["at"][1]) < 3.0, h * 0.12, h)
            dome = np.maximum(dome, h)
        deep = ((lake_deep | river | canal | crev) & ~keep) | (dome >= 0.6)
        return {"keep": keep, "lake": lake, "lakeDeep": lake_deep, "lakeLevel": lake_level, "lakeFloor": lake_floor,
                "river": river, "riverLevel": river_level, "riverBank": river_bank, "dry": dry, "canal": canal,
                "crevasse": crev, "crevasseDepth": crev_depth, "dome": dome, "deep": deep}

    # ------------------------------------------------------------ after the road
    def carve(self, px, py, height, walk):
        """Mounds, lakes, rivers, canals and crevasses cut into the carved ground."""
        f = self.features(px, py)
        keep_walk = walk & f["keep"]
        h = height + f["dome"]
        h = np.where(f["lake"] & ~keep_walk, np.minimum(h, f["lakeFloor"]), h)
        if self.water_mode:
            bed = self.spec["floor"] - 2.0
            h = np.where(f["river"] & ~keep_walk, np.minimum(h, bed), h)
        else:
            surf = np.where(np.isnan(f["riverLevel"]), 0.0, f["riverLevel"])
            near, level = self._river_near(px, py)
            h = np.where(f["river"] & ~keep_walk, np.minimum(h, surf - 1.6), h)
            bank = (near > 0) & (near < 6) & ~walk
            h = np.where(bank, np.minimum(h, level + 0.4 + near * 0.8), h)
        h = np.where(f["dry"] & ~walk, h - 1.5, h)
        if self.water_mode:
            h = np.where(f["canal"] & ~keep_walk, np.minimum(h, self.spec["floor"] - 3.0), h)
        h = np.where(f["crevasse"] & ~keep_walk, h - f["crevasseDepth"], h)
        return h, f

    def _river_near(self, px, py):
        """Distance beyond the nearest wet river's edge and its level there (land rivers)."""
        near = np.full(px.shape, 1e9)
        level = np.zeros(px.shape)
        for i, rv in enumerate(self.spec.get("rivers", [])):
            if rv.get("dry"):
                continue
            d, lv = polyline(px, py, rv["points"])
            half = rv["width"] / 2 * (1 + 0.15 * self.noise(px, py, 20, f"river{i}", 2))
            e = d - half
            take = e < near
            near = np.where(take, e, near)
            level = np.where(take, lv, level)
        return near, level

    # ------------------------------------------------------------ water to draw
    def water_bodies(self):
        """[(kind, data)]: a level plane, lake ellipses, river polylines with levels."""
        out = []
        s = self.spec
        if self.water_mode:
            out.append(("plane", {"level": self.water_level}))
        for lk in s.get("lakes", []):
            out.append(("lake", lk))
        for rv in s.get("rivers", []):
            if rv.get("dry"):
                continue
            if self.water_mode and not any(len(p) > 2 for p in rv["points"]):
                continue                                  # under the plane already
            out.append(("river", rv))
        return out
