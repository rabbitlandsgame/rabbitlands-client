"""One deterministic continental surface; territory borders never enter the field.

Coordinates are global metres, x east / z south / y up. All sampling functions
broadcast NumPy inputs, including scalars. River profiles carry surveyed downhill
water levels; broad valley shoulders are cut first and channel beds last. This is
an authored geographic model, not an erosion or atmospheric simulation.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np

PLAN_PATH = Path(__file__).with_name("diagonal-plan.json")
# Artist-facing sRGB swatches; converted to linear reflectance at export.
BIOME_COLORS = {
    "grassland": (0.39, 0.47, 0.25),
    "woodland": (0.34, 0.41, 0.20),
    "heath": (0.37, 0.39, 0.30),
    "steppe": (0.60, 0.55, 0.33),
    "badland": (0.53, 0.47, 0.41),
    "wetland": (0.31, 0.40, 0.27),
    "limestone": (0.46, 0.50, 0.35),
    "rock": (0.48, 0.49, 0.45),
    "snow": (0.84, 0.87, 0.85),
    "sand": (0.64, 0.59, 0.44),
}


@lru_cache(maxsize=1)
def load_plan():
    """Read the authored plan. Treat the cached result as immutable."""
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _coords(x, z):
    return np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(z, dtype=np.float64))


def smoothstep(low, high, value):
    t = np.clip((np.asarray(value) - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash(ix, iz, seed):
    # Unsigned arithmetic is deliberate; masking avoids platform-sized integers.
    with np.errstate(over="ignore"):
        h = ix.astype(np.uint64) * np.uint64(374761393)
        h = h + iz.astype(np.uint64) * np.uint64(668265263) + np.uint64(seed * 2654435761)
        h = (h ^ (h >> np.uint64(13))) * np.uint64(1274126177)
        h = h ^ (h >> np.uint64(16))
    return (h & np.uint64(0xFFFFFF)).astype(np.float64) / 16777215.0


def _noise(x, z, scale, seed):
    x, z = x / scale, z / scale
    ix, iz = np.floor(x), np.floor(z)
    tx, tz = x - ix, z - iz
    tx = tx * tx * tx * (tx * (tx * 6 - 15) + 10)
    tz = tz * tz * tz * (tz * (tz * 6 - 15) + 10)
    a = _hash(ix, iz, seed) * (1 - tx) + _hash(ix + 1, iz, seed) * tx
    b = _hash(ix, iz + 1, seed) * (1 - tx) + _hash(ix + 1, iz + 1, seed) * tx
    return (a * (1 - tz) + b * tz) * 2 - 1


@lru_cache(maxsize=64)
def _curved_points(points, closed=False):
    """Catmull-Rom horizontal curves; attributes remain monotone between controls."""
    p = np.asarray(points, dtype=np.float64)
    out = []
    count = len(p) if closed else len(p) - 1
    for i in range(count):
        a, b = p[i], p[(i + 1) % len(p)]
        before = p[(i - 1) % len(p)] if closed or i else a * 2 - b
        after = p[(i + 2) % len(p)] if closed or i + 2 < len(p) else b * 2 - a
        for t in np.arange(6, dtype=float) / 6:
            position = 0.5 * ((2 * a[:2]) + (-before[:2] + b[:2]) * t
                              + (2 * before[:2] - 5 * a[:2] + 4 * b[:2] - after[:2]) * t * t
                              + (-before[:2] + 3 * a[:2] - 3 * b[:2] + after[:2]) * t * t * t)
            out.append(np.concatenate((position, a[2:] + t * (b[2:] - a[2:]))))
    out.append(p[0] if closed else p[-1])
    return np.asarray(out)


def curved_points(points, closed=False):
    """Sampled authored curves, also shared by the water and road exporters."""
    return _curved_points(tuple(tuple(p) for p in points), closed)


def _polyline_field(x, z, points, already_sampled=False):
    """Distance to line and linearly interpolated point attributes at nearest point."""
    points = np.asarray(points, dtype=np.float64) if already_sampled else curved_points(points)
    closest = np.full(x.shape, np.inf)
    nearest = np.zeros(x.shape, dtype=int)
    attrs = [np.zeros(x.shape, dtype=np.float64) for _ in range(points.shape[1] - 2)]
    for segment, (a, b) in enumerate(zip(points[:-1], points[1:])):
        dx, dz = b[0] - a[0], b[1] - a[1]
        t = np.clip(((x - a[0]) * dx + (z - a[1]) * dz) / max(dx * dx + dz * dz, 1e-9), 0, 1)
        d2 = (x - a[0] - t * dx) ** 2 + (z - a[1] - t * dz) ** 2
        use = d2 < closest
        closest = np.minimum(closest, d2)
        nearest = np.where(use, segment, nearest)
        for i in range(len(attrs)):
            attrs[i] = np.where(use, a[i + 2] + t * (b[i + 2] - a[i + 2]), attrs[i])
    if already_sampled:
        # Editor snapshots already contain the exact rendered samples. Their
        # Y and width values are linear on each saved span; legacy neighbour
        # smoothing would move those authored attributes off their preview.
        return (np.sqrt(closest), *attrs)
    # Extend the surveyed attributes smoothly across a bend. Choosing only
    # the nearest straight segment otherwise introduces small diagonal steps
    # in bank elevation even when the river's centreline is continuous. The
    # blend tends to zero on that centreline, preserving its hydraulic levels.
    bandwidth = np.maximum(closest * .12, 1e-12)
    sums = [np.zeros_like(value) for value in attrs]
    weights = np.zeros_like(closest)
    for offset in (-2, -1, 0, 1, 2):
        index = nearest + offset
        valid = (index >= 0) & (index < len(points) - 1)
        index = np.clip(index, 0, len(points) - 2)
        a, b = points[index], points[index + 1]
        dx, dz = b[..., 0] - a[..., 0], b[..., 1] - a[..., 1]
        projected = ((x-a[..., 0])*dx+(z-a[..., 1])*dz)/np.maximum(dx*dx+dz*dz, 1e-9)
        t = np.clip(projected, 0, 1)
        d2 = (x-a[..., 0]-t*dx)**2+(z-a[..., 1]-t*dz)**2
        weight = np.exp(-np.maximum(0, d2-closest)/bandwidth) * valid
        weights += weight
        # Local tangent extrapolation keeps a straight downhill reach planar;
        # clamping each tiny segment would introduce a repeated stair profile.
        attribute_t = np.where(index == 0, np.maximum(0, projected), projected)
        attribute_t = np.where(index == len(points)-2, np.minimum(1, attribute_t), attribute_t)
        for i in range(len(attrs)):
            sums[i] += weight * (a[..., i+2]+attribute_t*(b[..., i+2]-a[..., i+2]))
    attrs = [value / weights for value in sums]
    return (np.sqrt(closest), *attrs)


def river_field(x, z, river):
    """Distance, hydraulic level and interpolated half-width for a river."""
    fields = _polyline_field(x, z, river["points"], river.get("authoredSampled", False))
    if len(fields) >= 3:
        return fields[0], fields[1], fields[2]
    return fields[0], fields[1], np.broadcast_to(float(river["width"]), np.asarray(fields[0]).shape)


def river_points(river):
    """Exact centreline samples used by fields, water, crossings and audits."""
    if river.get("authoredSampled", False):
        return np.asarray(river["points"], dtype=np.float64)
    return curved_points(river["points"])


def coastline_distance(x, z, plan=None):
    """Signed distance to mainland coast, positive inland; islands are separate."""
    plan = load_plan() if plan is None else plan
    x, z = _coords(x, z)
    points = curved_points(plan["coastline"], closed=True)[:-1]
    inside = np.zeros(x.shape, dtype=bool)
    minimum = np.full(x.shape, np.inf)
    for a, b in zip(points, np.roll(points, -1, axis=0)):
        dx, dz = b - a
        t = np.clip(((x - a[0]) * dx + (z - a[1]) * dz) / (dx * dx + dz * dz), 0, 1)
        minimum = np.minimum(minimum, (x - a[0] - dx * t) ** 2 + (z - a[1] - dz * t) ** 2)
        if abs(dz) > 1e-12:
            crosses = ((a[1] > z) != (b[1] > z)) & (x < a[0] + (z - a[1]) * dx / dz)
            inside ^= crosses
    # Broad low-amplitude irregularity avoids a visibly polygonal shoreline.
    irregularity = 6.5 * _noise(x, z, 82, plan["seed"] + 41)
    return np.sqrt(minimum) * np.where(inside, 1.0, -1.0) + irregularity


def _ellipse_distance(x, z, shape):
    dx, dz = x - shape["center"][0], z - shape["center"][1]
    angle = shape.get("angle", 0)
    u = dx * np.cos(angle) + dz * np.sin(angle)
    v = -dx * np.sin(angle) + dz * np.cos(angle)
    rx, rz = shape["radii"]
    return np.sqrt((u / rx) ** 2 + (v / rz) ** 2)


def _natural_height(x, z, plan):
    coast = coastline_distance(x, z, plan)
    inland = smoothstep(-8, 100, coast)
    # Shelf and shore profile meet sea level continuously, with no rectangular base.
    h = 23 * np.tanh(coast / 94)
    h += inland * (3.2 * _noise(x, z, 235, plan["seed"]) + 1.1 * _noise(x, z, 67, plan["seed"] + 1))
    for ridge in plan["ridges"]:
        # Integrating overlapping segments produces a continuous ridge without
        # the diagonal attribute discontinuities of nearest-segment projection.
        p = curved_points(ridge["points"])
        chain = np.zeros_like(h)
        for a, b in zip(p[:-1], p[1:]):
            mid = (a + b) * 0.5
            ds = np.hypot(b[0] - a[0], b[1] - a[1])
            distance2 = (x - mid[0]) ** 2 + (z - mid[1]) ** 2
            height, width = mid[2], mid[3]
            crest = np.exp(-distance2 / width ** 2) / width
            shoulder_width = width * ridge["foothill_width"]
            shoulder = np.exp(-distance2 / shoulder_width ** 2) / shoulder_width
            chain += height * ds / np.sqrt(np.pi) * (crest + ridge["foothill_height"] * shoulder)
        long_variation = 1 + 0.08 * _noise(x, z, 130, plan["seed"] + 9)
        h += inland * chain * long_variation
    # A basin floor leading to the delta, with a broad upper shoulder.
    floodplain = np.exp(-(((x - 510) / 340) ** 2 + ((z - 1075) / 235) ** 2))
    h = h * (1 - floodplain * 0.66)
    # Islands rise from the same shelf. Smooth ellipses are warped at landscape scale.
    for island in plan["islands"]:
        r = _ellipse_distance(x, z, island) + 0.12 * _noise(x, z, 47, plan["seed"] + 51)
        island_h = island["height"] * (1 - r * r)
        h = np.maximum(h, island_h)
    return h


def cuts_relief(river):
    """Whether this river carves a legacy relief source instead of standing under it.

    ``height_at`` lays a relief source over the drained ground, which paints out the bed of any
    river that runs inside the source's weight: a mountain valley cannot hold water there. A river
    that declares ``"cuts_relief": true`` is drained a second time, after the relief sources and the
    basins, so its bed and valley are cut into the old heightfield rather than buried by it. Every
    other river is drained once, before the relief, exactly as it always was.
    """
    return bool(river.get("cuts_relief", False))


def _drainage_height(x, z, h, plan, rivers=None, lakes=None):
    """Grade the valleys and cut the beds of ``rivers`` (the plan's own by default) and ``lakes``.

    The two selections exist for ``cuts_relief``: the first pass takes the ordinary rivers and the
    lakes, the second (after the relief) takes the carving rivers and no lake. Both passes only ever
    lower the ground, so a carving tributary cannot fill the river it joins.
    """
    rivers = plan["rivers"] if rivers is None else rivers
    lakes = plan.get("lakes", []) if lakes is None else lakes
    # First grade valleys, then cut beds. Doing this in two passes prevents a
    # tributary shoulder from filling its receiving river at a confluence.
    fields = []
    for river in rivers:
        distance, level, width = river_field(x, z, river)
        valley = river["valley_width"]
        blend = 1 - smoothstep(width, valley, distance)
        valley_target = level + river["bank_height"] + 0.035 * distance
        h = np.minimum(h, h * (1 - blend) + valley_target * blend)
        fields.append((river, distance, level, width))
    for river, distance, level, width in fields:
        # A low bank shelf gives a river somewhere to flood before its valley
        # rises. The former narrow bed blend climbed straight into the four-
        # metre valley shoulder, making the two banks read as parallel walls.
        # Centreline levels/depth and the authored drainage remain unchanged.
        shelf = river.get("bank_shelf_width", np.maximum(10.0, width * 1.5))
        shelf_height = min(river["bank_height"], river.get("bank_shelf_height", 0.65))
        terrace_end = width + shelf
        join = np.maximum(18.0, width * 1.5)
        bed = level - river["depth"] * (1 - smoothstep(0, width, distance))
        bank = level + shelf_height * smoothstep(width, terrace_end, distance)
        profile = np.where(distance <= width, bed, bank)
        blend = 1 - smoothstep(terrace_end, terrace_end + join, distance)
        h = h * (1 - blend) + np.minimum(h, profile) * blend
    for lake in lakes:
        r = _ellipse_distance(x, z, lake)
        blend = 1 - smoothstep(0.8, 1.55, r)
        bed = lake["level"] - lake["depth"] * (1 - smoothstep(0, 1.3, r))
        h = h * (1 - blend) + np.minimum(h, bed) * blend
    return h


def retained_affine(transform):
    """A retained transform as (translation[3], scale_xz[2], about_xz[2]): a list is one rigid translation of the
    whole source layout; a dict carries 'translation' and may squeeze the layout north-south ('squeeze_z', a factor
    in (0, 1], about the source row 'about_z'), so a source whose crown would stand beyond the world's edge at
    full length keeps its crown inside it. Optional 'datum': 'ground' stands each compound on the composed relief."""
    if isinstance(transform, dict):
        translation = np.asarray(transform["translation"], float)
        scale = np.array([float(transform.get("squeeze_x", 1.0)), float(transform.get("squeeze_z", 1.0))])
        about = np.array([float(transform.get("about_x", 0.0)), float(transform.get("about_z", 0.0))])
    else:
        translation = np.asarray(transform, float); scale = np.ones(2); about = np.zeros(2)
    if translation.shape != (3,) or not np.isfinite(translation).all():
        raise ValueError("retained transform: the translation must contain three finite metres")
    if not (0.0 < scale[0] <= 1.0 and 0.0 < scale[1] <= 1.0):
        raise ValueError("retained transform: squeeze_x and squeeze_z must lie in (0, 1]")
    return translation, scale, about


def retained_yaw_degrees(transform):
    """The layout's turn about its 'about' point, degrees, positive from north towards east on the map
    (a dict's 'yaw_degrees'; a list transform never turns)."""
    yaw = float(transform.get("yaw_degrees", 0.0)) if isinstance(transform, dict) else 0.0
    if not np.isfinite(yaw):
        raise ValueError("retained transform: yaw_degrees must be finite")
    return yaw


def _rotate_xz(dx, dz, degrees):
    """Turn offsets about the origin: the map's x east, z south, so a positive angle turns north towards east."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return dx * c - dz * s, dx * s + dz * c


def retained_map_xz(transform, points):
    """Source-frame xz points carried to continent metres by a retained transform: squeezed about its
    'about' point, turned by 'yaw_degrees' about the same point, then translated."""
    translation, scale, about = retained_affine(transform)
    points = np.asarray(points, float)
    d = (points - about) * scale
    rx, rz = _rotate_xz(d[..., 0], d[..., 1], retained_yaw_degrees(transform))
    return np.stack([rx, rz], axis=-1) + about + translation[[0, 2]]


def retained_unmap_xz(transform, x, z):
    """Continent metres back to the source frame: the inverse of retained_map_xz, on arrays."""
    translation, scale, about = retained_affine(transform)
    qx, qz = x - translation[0] - about[0], z - translation[2] - about[1]
    rx, rz = _rotate_xz(qx, qz, -retained_yaw_degrees(transform))
    return about[0] + rx / scale[0], about[1] + rz / scale[1]


@lru_cache(maxsize=4)
def _relief_samples(name):
    data = np.load(PLAN_PATH.with_name(name) if "/" not in name else PLAN_PATH.parent / name)
    return (np.asarray(data["x"], float), np.asarray(data["z"], float), np.asarray(data["height"], float))


def _relief_height(x, z, source):
    """(height, weight) of a sampled relief source at global x, z: bilinear inside its crop, whole there, and
    beyond the crop's edge the edge's own height continues as a shoulder fading out over ``feather`` metres.

    An optional authored ``mask`` narrows that rectangle to a leaf shape: the weight returned is the crop's
    times the mask's, so the old heightfield fades along the authored outline instead of its own crop edge.
    """
    sx, sz, sh = _relief_samples(source["samples"])
    tx, ty, tz = source["translation"]
    # The same squeeze and turn the territory's retained transform carries,
    # so the relief stands under the layout it was surveyed with.
    lx, lz = retained_unmap_xz(source, x, z)
    x0, z0, x1, z1 = source.get("crop", [sx[0], sz[0], sx[-1], sz[-1]])
    # Distance outside the crop rectangle (Euclidean, so the shoulder rounds the corners).
    outside = np.hypot(np.maximum(np.maximum(x0 - lx, lx - x1), 0.0), np.maximum(np.maximum(z0 - lz, lz - z1), 0.0))
    weight = 1.0 - smoothstep(0.0, float(source.get("feather", 40.0)), outside)
    mask = _relief_mask_weight(x, z, source)
    if mask is not None:
        weight = weight * mask
    cx = np.clip(lx, max(x0, sx[0]), min(x1, sx[-1])); cz = np.clip(lz, max(z0, sz[0]), min(z1, sz[-1]))
    ix = np.clip(np.searchsorted(sx, cx) - 1, 0, len(sx) - 2); iz = np.clip(np.searchsorted(sz, cz) - 1, 0, len(sz) - 2)
    fx = (cx - sx[ix]) / (sx[ix + 1] - sx[ix]); fz = (cz - sz[iz]) / (sz[iz + 1] - sz[iz])
    h = (sh[iz, ix] * (1 - fx) * (1 - fz) + sh[iz, ix + 1] * fx * (1 - fz)
         + sh[iz + 1, ix] * (1 - fx) * fz + sh[iz + 1, ix + 1] * fx * fz)
    # A knee in the source's own heights: above it the relief keeps only
    # ``above_scale`` of its rise, blended in over ``knee_width`` either side,
    # so a surveyed bowl's rim walls stand above its floor without towering.
    if source.get("knee") is not None:
        knee = float(source["knee"]); above = float(source.get("above_scale", 0.5))
        width = float(source.get("knee_width", 10.0))
        t = smoothstep(knee - width, knee + width, h)
        h = h * (1 - t) + (knee + (h - knee) * above) * t
    # Vertical exaggeration about a pivot in the source's own heights: the
    # base (a gate court) keeps its level while the relief above it grows.
    pivot = float(source.get("pivot", 0.0))
    h = pivot + (h - pivot) * float(source.get("scale", 1.0))
    return h + ty, weight


def relief_outline(source):
    """The four continent-metre corners [x, z] of a relief source's crop rectangle, in the
    order x0z0, x1z0, x1z1, x0z1, carried by the source's own translation and squeeze.

    This is the ground the source owns whole, before the ``feather`` shoulder outside it.
    Without a "crop" the source owns its entire sampled extent, the rectangle
    ``_relief_height`` falls back to; a crop reaching past that extent still owns the
    ground it names, the edge sample's height continuing underneath. The plan editor draws
    this polygon rather than repeating the retained transform's arithmetic of its own.
    A source that also declares a ``mask`` owns only the part of this rectangle inside that
    leaf; ``relief_mask_outline`` returns it.
    """
    crop = source.get("crop")
    if crop is None:
        sx, sz, _ = _relief_samples(source["samples"])
        crop = [sx[0], sz[0], sx[-1], sz[-1]]
    x0, z0, x1, z1 = (float(value) for value in crop)
    corners = retained_map_xz(source, [[x0, z0], [x1, z0], [x1, z1], [x0, z1]])
    return [[float(x), float(z)] for x, z in corners]


def _relief_id(source):
    """A relief source named for a complaint: its authored name, else the samples it reads."""
    for key in ("name", "samples"):
        value = source.get(key) if isinstance(source, dict) else None
        if isinstance(value, str) and value.strip():
            return f"relief source {value!r}"
    return "unnamed relief source"


def _relief_mask(source):
    """A relief source's authored mask as (polygon, feather), or None when it declares none.

    The polygon's points are ``[x, z]`` in continent metres, not in the source's own surveyed
    frame: the leaf is drawn over the composed map, where its shape is judged, so moving the
    source's translation moves the heightfield under a mask that stays where it was drawn.
    """
    mask = source.get("mask")
    if mask is None:
        return None
    if not isinstance(mask, dict):
        raise ValueError(f"{_relief_id(source)}: 'mask' must be an object with a 'polygon' and a 'feather', "
                         f"not {mask!r}")
    points = mask.get("polygon")
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise ValueError(f"{_relief_id(source)}: the mask 'polygon' needs at least 3 [x, z] points in continent "
                         f"metres, not {len(points) if isinstance(points, (list, tuple)) else points!r}")
    for point in points:
        if not (isinstance(point, (list, tuple)) and len(point) == 2 and all(_is_number(value) for value in point)):
            raise ValueError(f"{_relief_id(source)}: {point!r} is not a finite [x, z] mask point")
    feather = mask.get("feather", 0.0)
    if not _is_number(feather) or feather < 0.0:
        raise ValueError(f"{_relief_id(source)}: the mask 'feather' must be a distance in metres of at least 0, "
                         f"not {feather!r}")
    return np.asarray(points, dtype=np.float64), float(feather)


def _relief_mask_weight(x, z, source):
    """How much of a masked relief source each point takes: one inside the authored polygon, fading to
    nothing over its ``feather`` metres outside it. Straight edges between the authored vertices and
    even-odd containment, the rule a polygon terrain edit follows (``_polygon_inside`` below). ``None``
    when the source carries no mask, which leaves its crop weight exactly as it was."""
    mask = _relief_mask(source)
    if mask is None:
        return None
    points, feather = mask
    x, z = _coords(x, z)
    # Only the points the leaf plus its feather can reach pay for its geometry. The composed
    # grid is continental and one mask covers a corner of it, so this window is the saving.
    (x0, z0), (x1, z1) = points.min(axis=0) - feather, points.max(axis=0) + feather
    near = (x >= x0) & (x <= x1) & (z >= z0) & (z <= z1)
    weight = np.zeros(x.shape)
    if near.any():
        outside = np.where(_polygon_inside(x[near], z[near], points), 0.0,
                           _segment_distance(x[near], z[near], points, closed=True))
        weight[near] = (1.0 - smoothstep(0.0, feather, outside) if feather > 0
                        else np.where(outside > 0.0, 0.0, 1.0))
    return weight


def relief_mask_outline(source):
    """A relief source's authored mask polygon as ``[[x, z], ...]`` in continent metres, or None when
    the source declares no mask and its crop rectangle alone decides the ground it owns. The plan
    editor draws this leaf over the rectangle ``relief_outline`` gives it."""
    mask = _relief_mask(source)
    return None if mask is None else [[float(x), float(z)] for x, z in mask[0]]


# Authored corrections over the modelled ground. "smooth" is deliberately not in v1:
# a smoothing pass reads its neighbours, which a broadcast point sampler cannot do.
TERRAIN_EDIT_OPS = ("raise", "lower", "flatten", "ramp")
TERRAIN_EDIT_SHAPES = ("circle", "polyline", "polygon")
TERRAIN_EDIT_KEYS = ("id", "name", "op", "shape", "amount", "target", "heights", "feather", "strength")
TERRAIN_EDIT_STATISTICS = ("min", "max", "mean")
TERRAIN_EDIT_STEP = 2.0  # The composed sampling interval; targets are measured on it.


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value)


def _edit_id(edit):
    identity = edit.get("id") if isinstance(edit, dict) else None
    return f"terrain edit {identity!r}" if isinstance(identity, str) else "unnamed terrain edit"


def _edit_number(edit, key, default=None, low=None, high=None):
    """One authored scalar of a terrain edit; every complaint names the edit."""
    value = edit.get(key, default)
    if not _is_number(value):
        raise ValueError(f"{_edit_id(edit)}: {key!r} must be a finite number, not {value!r}")
    value = float(value)
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f"{_edit_id(edit)}: {key!r} must lie in "
                         f"[{'-inf' if low is None else low}, {'inf' if high is None else high}], not {value}")
    return value


def _edit_shape(edit):
    """The edit's single shape as (kind, definition)."""
    shape = edit.get("shape")
    if not isinstance(shape, dict) or len(shape) != 1 or set(shape) - set(TERRAIN_EDIT_SHAPES):
        raise ValueError(f"{_edit_id(edit)}: 'shape' must hold exactly one of "
                         f"{list(TERRAIN_EDIT_SHAPES)}, not {sorted(shape) if isinstance(shape, dict) else shape!r}")
    return next(iter(shape.items()))


def _segment_distance(x, z, points, closed=False):
    """Least distance to a chain of straight segments between the authored vertices.

    Terrain edits join their points with straight lines, unlike the rivers and roads that
    run through ``curved_points``: the editor draws exactly these segments.
    """
    points = np.asarray(points, dtype=np.float64)
    pairs = zip(points, np.roll(points, -1, axis=0)) if closed else zip(points[:-1], points[1:])
    closest = np.full(np.shape(x), np.inf)
    for a, b in pairs:
        dx, dz = b[0] - a[0], b[1] - a[1]
        t = np.clip(((x - a[0]) * dx + (z - a[1]) * dz) / max(dx * dx + dz * dz, 1e-9), 0.0, 1.0)
        closest = np.minimum(closest, (x - a[0] - t * dx) ** 2 + (z - a[1] - t * dz) ** 2)
    return np.sqrt(closest)


def _polygon_inside(x, z, points):
    """Even-odd containment, the rule ``coastline_distance`` uses for the mainland."""
    points = np.asarray(points, dtype=np.float64)
    inside = np.zeros(np.shape(x), dtype=bool)
    for a, b in zip(points, np.roll(points, -1, axis=0)):
        if abs(b[1] - a[1]) > 1e-12:
            inside ^= ((a[1] > z) != (b[1] > z)) & (x < a[0] + (z - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
    return inside


def _edit_distance(x, z, edit):
    """Metres outside the edit's shape: zero on and inside it, growing outward."""
    kind, data = _edit_shape(edit)
    if kind == "circle":
        centre = np.asarray(data["center"], dtype=np.float64)
        return np.maximum(np.hypot(x - centre[0], z - centre[1]) - float(data["radius"]), 0.0)
    if kind == "polyline":
        return np.maximum(_segment_distance(x, z, data["points"]) - float(data["width"]) / 2.0, 0.0)
    return np.where(_polygon_inside(x, z, data["points"]), 0.0,
                    _segment_distance(x, z, data["points"], closed=True))


def _edit_weight(x, z, edit):
    """How much of the edit each point takes: one inside the shape, fading over the
    feather outside it, times the edit's strength. A feather of zero is a hard edge."""
    feather = _edit_number(edit, "feather", 0.0, low=0.0)
    strength = _edit_number(edit, "strength", 1.0, low=0.0, high=1.0)
    x, z = _coords(x, z)
    x0, z0, x1, z1 = _edit_bounds(edit)
    # Only the points the shape can reach pay for its geometry. One edit is metres wide
    # and the composed grid is continental, so this window is most of the saving.
    near = (x >= x0 - feather) & (x <= x1 + feather) & (z >= z0 - feather) & (z <= z1 + feather)
    weight = np.zeros(x.shape)
    if near.any():
        outside = _edit_distance(x[near], z[near], edit)
        weight[near] = (1.0 - smoothstep(0.0, feather, outside) if feather > 0
                        else np.where(outside > 0.0, 0.0, 1.0))
    return weight * strength


def _edit_target(edit):
    """The metres a flatten settles on; the editor resolves statistics before saving."""
    target = edit.get("target")
    if isinstance(target, str):
        raise ValueError(f"{_edit_id(edit)}: the flatten 'target' {target!r} must be resolved to metres by "
                         "resolve_terrain_edit_targets before the ground is evaluated")
    return _edit_number(edit, "target")


def _edit_bounds(edit):
    """[x0, z0, x1, z1] around the shape itself, before its feather."""
    kind, data = _edit_shape(edit)
    if kind == "circle":
        centre = np.asarray(data["center"], dtype=np.float64)
        radius = float(data["radius"])
        return [centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius]
    points = np.asarray(data["points"], dtype=np.float64)
    margin = float(data["width"]) / 2.0 if kind == "polyline" else 0.0
    return [points[:, 0].min() - margin, points[:, 1].min() - margin,
            points[:, 0].max() + margin, points[:, 1].max() + margin]


def _edit_samples(edit, step=TERRAIN_EDIT_STEP):
    """Composed-grid points inside the shape, for measuring the ground there."""
    x0, z0, x1, z1 = _edit_bounds(edit)
    x, z = np.meshgrid(np.arange(x0, x1 + step, step), np.arange(z0, z1 + step, step))
    outside = _edit_distance(x, z, edit)
    # A shape finer than the sampling grid still deserves a reading: take its nearest points.
    inside = outside <= 0.0 if (outside <= 0.0).any() else outside <= outside.min()
    return x[inside], z[inside]


def _ramp_heights(edit):
    """A ramp's per-vertex surface heights, one finite number per polyline point."""
    kind, data = _edit_shape(edit)
    if kind != "polyline":
        raise ValueError(f"{_edit_id(edit)}: a ramp runs along a polyline, not a {kind}")
    heights = edit.get("heights")
    if (not isinstance(heights, list) or len(heights) != len(data["points"])
            or not all(_is_number(value) for value in heights)):
        raise ValueError(f"{_edit_id(edit)}: a ramp needs one finite height in metres per polyline point in "
                         f"'heights', not {heights!r}")
    return np.asarray(heights, dtype=np.float64)


def _ramp_surface(x, z, edit):
    """The ramp's own surface under each point: its 'heights' interpolated along the nearest straight segment of
    the polyline, the segment ``_segment_distance`` measures the band from, so the surface is level beyond the
    first and last vertex and continuous at every inner vertex."""
    heights = _ramp_heights(edit)
    points = np.asarray(_edit_shape(edit)[1]["points"], dtype=np.float64)
    closest = np.full(np.shape(x), np.inf)
    surface = np.zeros(np.shape(x))
    for a, b, low, high in zip(points[:-1], points[1:], heights[:-1], heights[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        t = np.clip(((x - a[0]) * dx + (z - a[1]) * dz) / max(dx * dx + dz * dz, 1e-9), 0.0, 1.0)
        distance = (x - a[0] - t * dx) ** 2 + (z - a[1] - t * dz) ** 2
        nearer = distance < closest
        closest = np.where(nearer, distance, closest)
        surface = np.where(nearer, low + (high - low) * t, surface)
    return surface


def _terrain_edit_height(x, z, h, plan):
    """Apply the plan's authored terrain edits, in list order, to a composed ground."""
    for edit in plan.get("terrain_edits") or []:
        op = edit.get("op")
        if op not in TERRAIN_EDIT_OPS:
            raise ValueError(f"{_edit_id(edit)}: unknown op {op!r}; v1 carries "
                             f"{list(TERRAIN_EDIT_OPS)} and deliberately no 'smooth'")
        weight = _edit_weight(x, z, edit)
        if op == "flatten":
            h = h * (1 - weight) + _edit_target(edit) * weight
        elif op == "ramp":
            # Only the points the ramp reaches pay for the per-segment surface.
            px, pz = _coords(x, z)
            touched = np.broadcast_to(weight > 0, px.shape)
            _ramp_heights(edit)
            if touched.any():
                surface = np.zeros(px.shape)
                surface[touched] = _ramp_surface(px[touched], pz[touched], edit)
                h = h * (1 - weight) + surface * weight
        else:
            amount = _edit_number(edit, "amount", low=0.0)
            h = h + amount * weight if op == "raise" else h - amount * weight
    return h


def validate_terrain_edits(plan):
    """Every problem with the plan's authored terrain edits; empty means safe to compose.

    The plan editor calls this on each change and before saving, so problems name their
    edit and describe the fix rather than the rule they broke.
    """
    edits = plan.get("terrain_edits") or []
    if not isinstance(edits, list):
        return ["'terrain_edits' must be a list of edits"]
    bounds = plan.get("bounds")
    problems, seen = [], set()
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            problems.append(f"terrain edit {index}: each edit must be an object")
            continue
        identity = edit.get("id")
        where = _edit_id(edit) if isinstance(identity, str) and identity.strip() else f"terrain edit {index}"
        if not isinstance(identity, str) or not identity.strip():
            problems.append(f"{where}: needs a non-empty string 'id'")
        elif identity in seen:
            problems.append(f"{where}: duplicate id; every edit needs its own")
        seen.add(identity if isinstance(identity, str) else index)
        unknown = sorted(set(edit) - set(TERRAIN_EDIT_KEYS))
        if unknown:
            problems.append(f"{where}: unknown key(s) {unknown}; v1 carries {list(TERRAIN_EDIT_KEYS)}")
        op = edit.get("op")
        if op == "smooth":
            problems.append(f"{where}: op 'smooth' is deliberately not part of v1; "
                            f"use one of {list(TERRAIN_EDIT_OPS)}")
        elif op not in TERRAIN_EDIT_OPS:
            problems.append(f"{where}: 'op' must be one of {list(TERRAIN_EDIT_OPS)}, not {op!r}")
        elif op == "flatten":
            target = edit.get("target")
            if not (_is_number(target) or (isinstance(target, str) and target in TERRAIN_EDIT_STATISTICS)):
                problems.append(f"{where}: flatten needs a 'target' in metres or one of "
                                f"{list(TERRAIN_EDIT_STATISTICS)}, not {target!r}")
        elif op == "ramp":
            pass  # its 'heights' are checked against the polyline's points below
        elif not _is_number(edit.get("amount")) or edit["amount"] < 0:
            problems.append(f"{where}: {op} needs a positive 'amount' in metres, not {edit.get('amount')!r}")
        if "heights" in edit and op != "ramp":
            problems.append(f"{where}: 'heights' belongs to a ramp; a {op} does not read it")
        feather = edit.get("feather", 0.0)
        if not _is_number(feather) or feather < 0:
            problems.append(f"{where}: 'feather' must be a distance in metres of at least 0, not {feather!r}")
            feather = 0.0
        if "strength" in edit and not (_is_number(edit["strength"]) and 0.0 <= edit["strength"] <= 1.0):
            problems.append(f"{where}: 'strength' must lie between 0 and 1, not {edit['strength']!r}")
        shape = edit.get("shape")
        if not isinstance(shape, dict) or len(shape) != 1 or set(shape) - set(TERRAIN_EDIT_SHAPES):
            problems.append(f"{where}: 'shape' must hold exactly one of {list(TERRAIN_EDIT_SHAPES)}, "
                            f"not {sorted(shape) if isinstance(shape, dict) else shape!r}")
            continue
        kind, data = next(iter(shape.items()))
        if not isinstance(data, dict):
            problems.append(f"{where}: the {kind} must be an object")
            continue
        if kind == "circle":
            points = [data.get("center")]
            if not _is_number(data.get("radius")) or data["radius"] <= 0:
                problems.append(f"{where}: the circle needs a 'radius' greater than 0, not {data.get('radius')!r}")
        else:
            least = 2 if kind == "polyline" else 3
            points = data.get("points")
            if not isinstance(points, list) or len(points) < least:
                problems.append(f"{where}: the {kind} needs at least {least} points, "
                                f"not {len(points) if isinstance(points, list) else points!r}")
                points = points if isinstance(points, list) else []
            if kind == "polyline" and (not _is_number(data.get("width")) or data["width"] <= 0):
                problems.append(f"{where}: the polyline needs a 'width' greater than 0, not {data.get('width')!r}")
        if op == "ramp":
            heights = edit.get("heights")
            if kind != "polyline":
                problems.append(f"{where}: a ramp runs along a polyline whose 'heights' give its surface at each "
                                f"point, not a {kind}")
            elif (not isinstance(heights, list) or len(heights) != len(points)
                    or not all(_is_number(value) for value in heights)):
                problems.append(f"{where}: a ramp needs one finite height in metres per polyline point in "
                                f"'heights' ({len(points)} here), not {heights!r}")
        for point in points:
            if not (isinstance(point, (list, tuple)) and len(point) == 2 and all(_is_number(v) for v in point)):
                problems.append(f"{where}: {point!r} is not a finite [x, z] point")
            elif bounds and not (bounds[0] - feather <= point[0] <= bounds[2] + feather
                                 and bounds[1] - feather <= point[1] <= bounds[3] + feather):
                problems.append(f"{where}: point {list(point)} lies outside the plan bounds "
                                f"{list(bounds)} by more than its {feather} m feather")
    return problems


def resolve_terrain_edit_targets(plan):
    """A copy of the plan whose flatten targets are all metres.

    "min", "max" and "mean" become that statistic of the natural ground, which is the
    plan with every terrain edit removed, sampled on the composed 2 m grid inside the
    shape and rounded to 0.1 m. Numbers are kept. The editor resolves before saving, so a
    stored plan never asks the composer to measure the ground it is about to change.
    """
    resolved = copy.deepcopy(plan)
    natural = dict(resolved, terrain_edits=[])
    for edit in resolved.get("terrain_edits") or []:
        target = edit.get("target")
        if edit.get("op") != "flatten" or not isinstance(target, str):
            continue
        if target not in TERRAIN_EDIT_STATISTICS:
            raise ValueError(f"{_edit_id(edit)}: unknown flatten target {target!r}; use metres or "
                             f"{list(TERRAIN_EDIT_STATISTICS)}")
        x, z = _edit_samples(edit)
        edit["target"] = round(float(getattr(np, target)(height_at(x, z, natural))), 1)
    return resolved


# The owner's road rules (2026-09-16): a road crosses a river only on a bridge at the locally shortest crossing,
# square to the flow and at a narrow reach; bridges on one river stand at least 100 m apart along it; a road
# travelling in a river's direction keeps to the bank outside a setback. river_crossings.py finds the sites and
# world_layout.py routes through them. The plan's "crossing_policy" may override any of these defaults.
CROSSING_POLICY_DEFAULTS = {
    "minimum_spacing_metres": 100.0,          # two bridge sites on one river, along its curved centreline
    "local_window_metres": 40.0,              # a site is the cheapest crossing within this reach either way along the river
    "perpendicular_tolerance_degrees": 15.0,  # the span stands within this of square to the flow
    "sample_metres": 2.0,                     # cross sections along each river's centreline
    "landing_metres": 12.0,                   # the approach length over which the approach grade absorbs a bank rise
    "approach_grade": 0.35,
    "deck_clearance_metres": 0.85,            # a deck over the water surface
    "maximum_approach_metres": 6.0,           # a site needing more unabsorbed bank rise is only a leg's last resort
    "setback_minimum_metres": 6.0,            # a road keeps max(this, its half width + the margin) from river water
    "setback_margin_metres": 4.0,
    "bank_shelf_metres": 16.0,                # beyond the setback, up to this far from the water, a road pays the shelf penalty
    "bank_shelf_penalty": 4.0,                # per metre of alignment, on top of flat ground's 1
    "confluence_metres": 20.0,                # no site this close to another river's channel edge
    "seam_metres": 12.0,                      # no site whose span or landings come this close to a territory seam
    "footing_weight": 0.999,                  # no site across the rigid core of a settlement footing (an assembly)
    "bridge_cost_metres": 60.0,               # a new bridge costs this much alignment on top of its own length
    "shared_bridge_factor": 0.25,             # a bridge a public road already crosses costs this share of it
    "deck_landing_metres": 6.0,               # a deck is its span plus at most this much landing on each bank
    "deck_lift_metres": 0.3,                  # a deck stands at most this far over dry ground
    "maximum_pier_metres": 8.0,               # the tallest pier the audit accepts outside a designed deck
}
CROSSING_POLICY_LIMITS = {
    "minimum_spacing_metres": (0.0, 1000.0), "local_window_metres": (2.0, 500.0),
    "perpendicular_tolerance_degrees": (0.0, 45.0), "sample_metres": (0.5, 10.0), "landing_metres": (1.0, 60.0),
    "approach_grade": (0.05, 1.0), "deck_clearance_metres": (0.0, 5.0), "maximum_approach_metres": (0.0, 100.0),
    "setback_minimum_metres": (0.0, 40.0), "setback_margin_metres": (0.0, 40.0), "bank_shelf_metres": (0.0, 100.0),
    "bank_shelf_penalty": (0.0, 100.0), "confluence_metres": (0.0, 200.0), "seam_metres": (0.0, 100.0),
    "footing_weight": (0.0, 1.0), "bridge_cost_metres": (0.0, 1000.0), "shared_bridge_factor": (0.0, 1.0),
    "deck_landing_metres": (0.0, 24.0), "deck_lift_metres": (0.0, 5.0), "maximum_pier_metres": (0.0, 100.0),
}


def validate_crossing_policy(plan):
    """Every problem with the plan's "crossing_policy"; empty means the policy (with its defaults) is usable."""
    policy = plan.get("crossing_policy")
    if policy is None:
        return []
    if not isinstance(policy, dict):
        return ["'crossing_policy' must be an object of named numbers"]
    problems = []
    for key, value in policy.items():
        if key not in CROSSING_POLICY_DEFAULTS:
            problems.append(f"crossing_policy: unknown key {key!r}; known keys are {sorted(CROSSING_POLICY_DEFAULTS)}")
            continue
        low, high = CROSSING_POLICY_LIMITS[key]
        if not _is_number(value) or not low <= float(value) <= high:
            problems.append(f"crossing_policy: {key!r} must be a number in [{low}, {high}], not {value!r}")
    return problems


def crossing_policy(plan):
    """The plan's crossing policy merged over CROSSING_POLICY_DEFAULTS, all floats; refuses a policy with problems."""
    problems = validate_crossing_policy(plan)
    if problems:
        raise ValueError("; ".join(problems))
    merged = dict(CROSSING_POLICY_DEFAULTS)
    merged.update({key: float(value) for key, value in (plan.get("crossing_policy") or {}).items()})
    return merged


# What an authored crossing may overrule: a deck that cannot sit at water level between high banks, a retained
# solid beside a routed landing, and standing nearer a territory seam than the policy prefers. It may never
# overrule "two territories" - a span in two territories would be exported in halves - nor water, a lake, the
# sea, a settlement footing or a wet landing.
AUTHORED_CROSSING_WAIVERS = ("deck lifts over its banks", "retained solid", "territory seam")


def validate_authored_crossings(plan):
    """Every problem with the plan's "authored_crossings": designed crossings of a plan river at sections the crossing
    model excludes only for reasons in AUTHORED_CROSSING_WAIVERS (a deck that cannot sit at water level between high
    banks, or a retained solid beside a routed landing). Each entry is {"river": a plan river id, "arcMetres": metres
    along its curved centreline, "note": why the crossing is designed}. Empty means usable."""
    entries = plan.get("authored_crossings")
    if entries is None:
        return []
    if not isinstance(entries, list):
        return ["'authored_crossings' must be a list of {river, arcMetres, note}"]
    rivers = {river.get("id") for river in plan.get("rivers", [])}
    problems = []
    for index, entry in enumerate(entries):
        label = f"authored_crossings[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"river", "arcMetres", "note"}:
            problems.append(f"{label}: must be an object with exactly river, arcMetres and note")
            continue
        if entry["river"] not in rivers:
            problems.append(f"{label}: {entry['river']!r} is not a plan river")
        if not _is_number(entry["arcMetres"]) or float(entry["arcMetres"]) < 0:
            problems.append(f"{label}: arcMetres must be metres along the river, not {entry['arcMetres']!r}")
        if not isinstance(entry["note"], str) or not entry["note"].strip():
            problems.append(f"{label}: the note must say why the crossing is designed")
    return problems


def validate_designed_decks(plan):
    """Every problem with the plan's "designed_decks": the support-module and retained decks allowed to stand
    elevated. Each entry is {"name": exact node name, or a family ending in "*", "module": who builds or registers
    it, "note": why it stands}; names are unique."""
    decks = plan.get("designed_decks")
    if decks is None:
        return []
    if not isinstance(decks, list):
        return ["'designed_decks' must be a list of {name, module, note} entries"]
    problems, seen = [], set()
    for index, entry in enumerate(decks):
        if not isinstance(entry, dict):
            problems.append(f"designed deck {index}: each entry must be an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip() or "*" in name[:-1]:
            problems.append(f"designed deck {index}: 'name' must be a node name, or a family ending in one '*', not {name!r}")
        elif name in seen:
            problems.append(f"designed deck {name!r}: listed twice")
        else:
            seen.add(name)
        for key in ("module", "note"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                problems.append(f"designed deck {name!r}: needs a non-empty string {key!r}")
        unknown = sorted(set(entry) - {"name", "module", "note"})
        if unknown:
            problems.append(f"designed deck {name!r}: unknown key(s) {unknown}")
    return problems


def designed_deck_entry(plan, name):
    """The designed_decks entry naming this node (exactly, or by a family "prefix*"), or None."""
    problems = validate_designed_decks(plan)
    if problems:
        raise ValueError("; ".join(problems))
    for entry in plan.get("designed_decks") or []:
        pattern = entry["name"]
        if pattern == name or (pattern.endswith("*") and name.startswith(pattern[:-1])):
            return entry
    return None


def require_designed_deck(plan, name, module):
    """Refuse an elevated deck the plan does not name in designed_decks (or names under another module). A plan
    without a designed_decks list predates the rule and refuses nothing (None)."""
    if "designed_decks" not in (plan or {}):
        return None
    entry = designed_deck_entry(plan, name)
    if entry is None:
        raise ValueError(f"{name}: {module} builds an elevated deck that diagonal-plan.json's designed_decks does not name")
    if entry["module"] != module:
        raise ValueError(f"{name}: designed_decks names it under {entry['module']!r}, not {module!r}")
    return entry


def height_at(x, z, plan=None):
    """Evaluate the shared ground height without reference to territory ownership."""
    plan = load_plan() if plan is None else plan
    x, z = _coords(x, z)
    carving = [river for river in plan["rivers"] if cuts_relief(river)]
    h = _drainage_height(x, z, _natural_height(x, z, plan), plan,
                         rivers=[river for river in plan["rivers"] if not cuts_relief(river)])
    # Legacy relief sources: a territory's old map relief placed by its retained
    # transform replaces the plan landform inside a crop that leaves the old
    # map's edge walls out, feathered at the crop's edge and damped by the coast.
    # An authored mask polygon narrows that crop to a leaf, feathered on its own.
    for source in plan.get("relief_sources", []):
        relief, weight = _relief_height(x, z, source)
        weight = weight * smoothstep(-8, float(source.get("coast_feather", 60.0)), coastline_distance(x, z, plan))
        h = h * (1 - weight) + relief * weight
    # Dry basins (cirques, corries, hanging hollows): an ellipse carved into
    # the crest after drainage, its floor rising as a shallow bowl toward the
    # rim and feathered over it; no water stands in it.
    for basin in plan.get("basins", []):
        r = _ellipse_distance(x, z, basin)
        blend = 1 - smoothstep(basin.get("rim", 0.85), basin.get("feather", 1.5), r)
        floor = basin["floor"] + basin.get("bowl", 6.0) * np.clip(r, 0, 1.5) ** 2
        h = h * (1 - blend) + np.minimum(h, floor) * blend
    # A river that declares "cuts_relief" is drained here instead, over the composed
    # relief: the mountain torrent cuts its gorge through the old heightfield rather
    # than standing on it. Authored corrections and footings still come after it.
    if carving:
        h = _drainage_height(x, z, h, plan, rivers=carving, lakes=())
    # Authored corrections on the modelled ground, in the plan's own list order: an
    # editor's raised knoll, lowered hollow or flattened shelf, each weighted by its
    # shape and feathered outside it. Foundations still settle their pads last.
    h = _terrain_edit_height(x, z, h, plan)
    for pad in plan.get("foundations", []):
        distance = np.hypot(x - pad["center"][0], z - pad["center"][1])
        blend = 1 - smoothstep(pad["radius"], pad["radius"] + pad.get("feather", 24), distance)
        h = h * (1 - blend) + pad["elevation"] * blend
    return h


def water_fields(x=None, z=None, height=None, plan=None):
    """Return water definitions, or sampled mask/surface/depth and river distance.

    Calling without coordinates returns the plan's rivers, lakes and sea level.
    ``surface`` is sea level outside channels; ``mask`` decides where to render.
    River widths in the plan are half-widths, measured from the centreline.
    """
    plan = load_plan() if plan is None else plan
    if x is None and z is None:
        return {key: plan[key] for key in ("rivers", "lakes", "sea_level")}
    if x is None or z is None:
        raise ValueError("Supply both x and z, or neither.")
    x, z = _coords(x, z)
    h = height_at(x, z, plan) if height is None else np.broadcast_to(height, x.shape)
    level = np.full(x.shape, float(plan["sea_level"]))
    river_mask = np.zeros(x.shape, dtype=bool)
    minimum = np.full(x.shape, np.inf)
    for river in plan["rivers"]:
        distance, profile, width = river_field(x, z, river)
        in_channel = distance <= width
        level = np.maximum(level, np.where(in_channel, profile, plan["sea_level"]))
        river_mask |= in_channel
        minimum = np.minimum(minimum, distance)
    for lake in plan.get("lakes", []):
        in_lake = _ellipse_distance(x, z, lake) <= 1.0
        level = np.maximum(level, np.where(in_lake, lake["level"], plan["sea_level"]))
        river_mask |= in_lake
    mask = h < level - 0.015
    return {"mask": mask, "surface": level, "depth": np.maximum(0, level - h),
            "river_mask": river_mask & mask, "sea_mask": (h < plan["sea_level"] - 0.015) & ~river_mask,
            "river_distance": minimum}


def snowline_at(x, z, plan=None):
    """The height above which snow lies: a latitude line, lowered over a relief source that declares an
    alpine climate (``snowline_drop`` metres, carried by the source's own weight, so by its crop, its feather
    and its mask alike), so an old mountain map keeps its snow at its own heights without its seams turning
    into cliffs."""
    plan = load_plan() if plan is None else plan
    x, z = _coords(x, z)
    snowline = 131 + smoothstep(250, 850, z) * 82
    for source in plan.get("relief_sources", []):
        drop = float(source.get("snowline_drop", 0.0))
        if drop:
            snowline = snowline - drop * _relief_height(x, z, source)[1]
    return snowline


def biome_weights(x, z, height=None, plan=None):
    """Smooth material/plant community weights; no named-region boundary masks."""
    plan = load_plan() if plan is None else plan
    x, z = _coords(x, z)
    h = height_at(x, z, plan) if height is None else np.broadcast_to(height, x.shape)
    wobble = 21 * _noise(x, z, 128, plan["seed"] + 67)
    # The dry lee is east of the spine. Southern maritime warmth closes that
    # rain shadow gradually before the limestone coast.
    spine_x = 390 + z * 0.57
    dry = smoothstep(-45, 270, x - spine_x + wobble) * (1 - smoothstep(820, 1260, z))
    warm = smoothstep(700, 1430, z + wobble)
    cold = 1 - smoothstep(95, 610, z)
    woodland = np.exp(-(((x - 475 + wobble) / 300) ** 2 + ((z - 580) / 285) ** 2))
    moor = np.exp(-(((x - 210) / 250) ** 2 + ((z - 440 + wobble) / 330) ** 2))
    mineral = np.exp(-(((x - 980) / 255) ** 2 + ((z - 390 + wobble) / 235) ** 2)) * dry
    water = water_fields(x, z, height=h, plan=plan)
    damp = (1 - smoothstep(9, 67, water["river_distance"])) * (1 - smoothstep(22, 85, h))
    delta = np.exp(-(((x - 510) / 250) ** 2 + ((z - 1140) / 235) ** 2))
    limestone = warm * smoothstep(740, 1170, x) * smoothstep(15, 95, h)
    snowline = snowline_at(x, z, plan)
    snow = smoothstep(snowline - 9, snowline + 16, h + _noise(x, z, 70, plan["seed"] + 71) * 4)
    rock = smoothstep(67, 142, h) * (1 - snow)
    sand = (1 - smoothstep(1.0, 8.5, h)) * (1 - smoothstep(35, 105, water["river_distance"])) * 0.5
    sand = np.maximum(sand, (1 - smoothstep(0.4, 7.0, h)) * 0.8)
    scores = {
        "grassland": np.full(x.shape, 0.70) * (1 - dry * 0.4),
        "woodland": woodland * 1.9 * (1 - dry) + warm * (1 - dry) * 0.68,
        "heath": moor * 1.6 * (0.7 + 0.3 * cold),
        "steppe": dry * 2.3 * (1 - mineral * 0.4),
        "badland": mineral * 2.4,
        "wetland": (damp * 1.5 + delta * 0.6) * (1 - dry * 0.6),
        "limestone": limestone * 1.5,
        "rock": rock * 2.0,
        "snow": snow * 20.0,
        "sand": sand,
    }
    total = np.sum(np.stack(list(scores.values()), axis=-1), axis=-1)
    return {name: value / total for name, value in scores.items()}


def terrain_color(x, z, height=None, plan=None):
    """Linear RGB vertex colours in [0, 1], with broad restrained soil variation."""
    plan = load_plan() if plan is None else plan
    x, z = _coords(x, z)
    weights = biome_weights(x, z, height=height, plan=plan)
    rgb = sum(weights[name][..., None] * np.asarray(color)**2.2 for name, color in BIOME_COLORS.items())
    variation = 1 + 0.047 * _noise(x, z, 39, plan["seed"] + 81) + 0.022 * _noise(x, z, 13, plan["seed"] + 82)
    return np.clip(rgb * variation[..., None], 0, 1)


def vegetation_fields(x, z, height=None, plan=None):
    """Reusable regional ecology controls for deterministic object scattering."""
    plan = load_plan() if plan is None else plan
    x, z = _coords(x, z)
    h = height_at(x, z, plan) if height is None else np.broadcast_to(height, x.shape)
    weights = biome_weights(x, z, height=h, plan=plan)
    water = water_fields(x, z, height=h, plan=plan)
    grove = 0.35 + 0.65 * smoothstep(-0.4, 0.6, _noise(x, z, 49, plan["seed"] + 92))
    density = (weights["woodland"] * 1.45 + weights["wetland"] * 0.35 + weights["limestone"] * 0.55) * grove
    density *= 1 - smoothstep(105, 157, h)
    density = np.where(water["mask"] | (h < 0.7), 0.0, np.clip(density, 0, 0.8))
    return {"tree_density": density, "wetness": weights["wetland"],
            "deciduous": weights["woodland"], "conifer": weights["rock"] * (1 - weights["snow"]),
            "dryness": weights["steppe"] + weights["badland"]}


if __name__ == "__main__":
    # Plan-editor support only; importing this module stays free of side effects.
    import argparse

    parser = argparse.ArgumentParser(description="Authored terrain edits of a continent plan.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-terrain-edits", nargs="?", const=str(PLAN_PATH), metavar="PLAN",
                       help="report every problem with a plan's terrain edits (default: the committed plan)")
    group.add_argument("--resolve-terrain-edits", nargs=2, metavar=("PLAN_IN", "PLAN_OUT"),
                       help="write a copy of a plan whose flatten targets are all metres")
    arguments = parser.parse_args()
    if arguments.check_terrain_edits:
        checked = Path(arguments.check_terrain_edits)
        found = validate_terrain_edits(json.loads(checked.read_text(encoding="utf-8")))
        print("\n".join(found + [f"{checked}: {len(found) or 'no'} problem{'' if len(found) == 1 else 's'}"]))
        raise SystemExit(1 if found else 0)
    source, destination = (Path(path) for path in arguments.resolve_terrain_edits)
    authored = json.loads(source.read_text(encoding="utf-8"))
    remaining = validate_terrain_edits(authored)
    if remaining:
        print("\n".join(remaining))
        raise SystemExit(f"{source}: fix these problems before resolving its targets")
    settled = resolve_terrain_edit_targets(authored)
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(settled, indent=2) + "\n")
    print(f"{destination}: {len(settled.get('terrain_edits') or [])} terrain edits, every target in metres")
