"""Old-growth tree authoring for Amberwood.

Trees are grown, not stamped: a recursive branch skeleton drives tapered tube
geometry, buttress roots are lofted from the trunk base, and the canopy is
built from leaf-cluster cards placed on the branch tips that actually exist.
Nothing here is a coloured sphere or a pair of crossed planes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import mesh as M
from .noise import Rng


@dataclass
class TreeProfile:
    """Art-directable species description.

    Branch counts are explicit per level rather than emergent, so the triangle
    budget of a species is predictable and the silhouette stays authored.
    """
    name: str
    height: float = 16.0
    trunk_radius: float = 0.62
    trunk_segments: int = 9
    trunk_sides: int = 10
    lean: float = 0.10
    wander: float = 0.20
    taper: float = 0.42
    first_branch: float = 0.34
    children: tuple[int, ...] = (7, 3, 2)   # primaries, per-primary, per-secondary, ...
    branch_pitch: tuple[float, float] = (0.55, 1.15)
    branch_length: float = 0.46
    branch_radius: float = 0.55
    branch_droop: float = 0.22
    cluster_size: tuple[float, float] = (1.9, 3.1)
    clusters_per_tip: int = 2
    cluster_planes: int = 3
    root_count: int = 7
    root_spread: float = 1.9
    root_rise: float = 0.42
    bark_material: str = "bark_oak"
    foliage_material: str = "foliage_amber"
    foliage: bool = True
    broken_top: bool = False
    canopy_bias: float = 1.0
    max_clusters: int = 90


@dataclass
class _Branch:
    path: np.ndarray
    radii: np.ndarray
    level: int
    tip_direction: np.ndarray
    tip_length: float


PROFILES: dict[str, TreeProfile] = {}


def register(profile: TreeProfile) -> TreeProfile:
    PROFILES[profile.name] = profile
    return profile


# -- species ---------------------------------------------------------------
register(TreeProfile(
    name="amber_oak", height=17.0, trunk_radius=0.66, first_branch=0.32,
    children=(6, 4, 3), cluster_size=(1.5, 2.3), clusters_per_tip=3,
    root_count=7, bark_material="bark_oak", foliage_material="foliage_amber",
    canopy_bias=1.05, max_clusters=118))

register(TreeProfile(
    name="gold_oak", height=20.5, trunk_radius=0.80, first_branch=0.30,
    children=(7, 4, 3), cluster_size=(1.6, 2.5), clusters_per_tip=3,
    root_count=8, bark_material="bark_oak", foliage_material="foliage_gold",
    canopy_bias=1.15, max_clusters=132))

register(TreeProfile(
    name="rust_maple", height=13.5, trunk_radius=0.46, first_branch=0.38,
    children=(5, 4, 3), branch_pitch=(0.45, 0.95), cluster_size=(1.3, 2.0),
    clusters_per_tip=3, root_count=5, bark_material="bark_dark",
    foliage_material="foliage_rust", canopy_bias=0.90, max_clusters=46))

register(TreeProfile(
    name="pale_birch", height=14.5, trunk_radius=0.30, trunk_sides=8,
    first_branch=0.52, children=(6, 4), branch_pitch=(0.70, 1.25),
    branch_droop=0.34, cluster_size=(1.15, 1.75), clusters_per_tip=3,
    root_count=4, root_spread=1.1, taper=0.30, bark_material="bark_pale",
    foliage_material="foliage_gold", canopy_bias=0.80, max_clusters=54))

register(TreeProfile(
    name="dark_holly", height=8.5, trunk_radius=0.28, first_branch=0.28,
    children=(5, 4), cluster_size=(1.0, 1.5), clusters_per_tip=3, root_count=4,
    root_spread=0.9, bark_material="bark_dark", foliage_material="foliage_green",
    canopy_bias=0.85, max_clusters=46))

register(TreeProfile(
    name="understory_hazel", height=5.6, trunk_radius=0.16, trunk_sides=7,
    trunk_segments=6, first_branch=0.18, children=(5, 2),
    branch_pitch=(0.75, 1.30), cluster_size=(1.0, 1.6), clusters_per_tip=2,
    cluster_planes=2, root_count=3, root_spread=0.55, taper=0.34,
    bark_material="bark_dark", foliage_material="foliage_rust",
    canopy_bias=0.7, max_clusters=30))

register(TreeProfile(
    name="sapling", height=2.4, trunk_radius=0.07, trunk_sides=6, trunk_segments=4,
    first_branch=0.30, children=(4,), cluster_size=(0.40, 0.62),
    clusters_per_tip=2, cluster_planes=2, root_count=0, taper=0.30,
    bark_material="bark_pale", foliage_material="foliage_green",
    canopy_bias=0.6, max_clusters=12))

register(TreeProfile(
    name="dead_snag", height=11.0, trunk_radius=0.52, first_branch=0.42,
    children=(5, 2), branch_pitch=(0.65, 1.30), branch_length=0.34,
    root_count=6, taper=0.22, bark_material="bark_dark", foliage=False,
    broken_top=True))

register(TreeProfile(
    name="burnt_snag", height=8.0, trunk_radius=0.40, first_branch=0.36,
    children=(4, 2), branch_pitch=(0.75, 1.35), branch_length=0.30,
    root_count=4, taper=0.18, bark_material="bark_dark", foliage=False,
    broken_top=True))

register(TreeProfile(
    name="great_oak", height=27.0, trunk_radius=1.55, trunk_sides=13,
    trunk_segments=10, first_branch=0.26, children=(8, 4, 3, 2),
    branch_length=0.50, cluster_size=(2.3, 3.4), clusters_per_tip=3,
    root_count=11, root_spread=4.2, root_rise=0.85, taper=0.44,
    bark_material="bark_oak", foliage_material="foliage_amber",
    canopy_bias=1.30, max_clusters=210))

register(TreeProfile(
    name="dark_pine", height=15.0, trunk_radius=0.40, trunk_sides=8,
    first_branch=0.22, children=(9, 3), branch_pitch=(1.05, 1.45),
    branch_length=0.32, branch_droop=0.30, cluster_size=(0.85, 1.35),
    clusters_per_tip=3, root_count=4, taper=0.16, bark_material="bark_dark",
    foliage_material="foliage_green", canopy_bias=0.55, max_clusters=50))


# --------------------------------------------------------------------------
# skeleton
# --------------------------------------------------------------------------

def _grow_branch(start: np.ndarray, direction: np.ndarray, length: float, radius: float,
                 level: int, profile: TreeProfile, rng: Rng,
                 out: list[_Branch], segments: int = 4) -> None:
    direction = direction / max(np.linalg.norm(direction), 1e-9)
    points = [start.copy()]
    radii = [radius]
    current = direction.copy()
    step = length / segments
    for i in range(segments):
        t = (i + 1) / segments
        current = current + np.array([0.0, -profile.branch_droop * step * 0.5, 0.0])
        current = current + rng.normal(0.0, profile.wander * 0.35, 3)
        current /= max(np.linalg.norm(current), 1e-9)
        points.append(points[-1] + current * step)
        radii.append(radius * (1.0 - 0.76 * t) + 0.012)
    path = np.array(points)
    out.append(_Branch(path, np.array(radii), level, current, length))

    if level >= len(profile.children):
        return
    count = int(profile.children[level])
    if count <= 0:
        return
    golden = math.pi * (3.0 - math.sqrt(5.0))
    phase = float(rng.uniform(0.0, math.pi * 2.0))
    for i in range(count):
        t = 0.40 + 0.58 * (i + 0.5) / count
        index = min(int(t * segments), segments)
        origin = path[index]
        parent_radius = radii[index]
        if parent_radius < 0.030:
            continue
        azimuth = phase + golden * i + float(rng.normal(0.0, 0.30))
        pitch = float(rng.uniform(*profile.branch_pitch)) * (0.80 + 0.22 * level)
        axis = current
        reference = np.array([0.0, 1.0, 0.0]) if abs(axis[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        side = np.cross(axis, reference)
        side /= max(np.linalg.norm(side), 1e-9)
        other = np.cross(axis, side)
        offset = side * math.cos(azimuth) + other * math.sin(azimuth)
        child = axis * math.cos(pitch) + offset * math.sin(pitch)
        _grow_branch(origin, child,
                     length * profile.branch_length * float(rng.uniform(0.78, 1.18)),
                     parent_radius * profile.branch_radius * float(rng.uniform(0.85, 1.10)),
                     level + 1, profile, rng, out,
                     segments=max(2, segments - 2))


def _grow_trunk(profile: TreeProfile, rng: Rng) -> list[_Branch]:
    branches: list[_Branch] = []
    segments = profile.trunk_segments
    lean_azimuth = float(rng.uniform(0.0, math.pi * 2.0))
    lean = np.array([math.cos(lean_azimuth), 0.0, math.sin(lean_azimuth)]) * profile.lean
    points = [np.zeros(3)]
    radii = [profile.trunk_radius]
    direction = np.array([0.0, 1.0, 0.0])
    height = profile.height * (0.72 if profile.broken_top else 1.0)
    step = height / segments
    for i in range(segments):
        t = (i + 1) / segments
        direction = direction + lean * 0.12 + rng.normal(0.0, profile.wander * 0.16, 3) \
            * np.array([1.0, 0.25, 1.0])
        direction /= max(np.linalg.norm(direction), 1e-9)
        points.append(points[-1] + direction * step)
        shape = (1.0 - t) ** 0.62
        radii.append(profile.trunk_radius * (profile.taper + (1.0 - profile.taper) * shape))
    path = np.array(points)
    radii_array = np.array(radii)
    radii_array[0] *= 1.55
    if len(radii_array) > 1:
        radii_array[1] *= 1.18
    branches.append(_Branch(path, radii_array, 0, direction, height))

    primaries = int(profile.children[0]) if profile.children else 0
    start_index = max(1, int(profile.first_branch * segments))
    golden = math.pi * (3.0 - math.sqrt(5.0))
    phase = float(rng.uniform(0.0, math.pi * 2.0))
    for i in range(primaries):
        # spread primaries up the usable length of the trunk, not per segment
        fraction = (i + 0.5) / primaries
        index = int(round(start_index + fraction * (segments - start_index)))
        index = min(max(index, 1), segments)
        t = index / segments
        azimuth = phase + golden * i + float(rng.normal(0.0, 0.26))
        pitch = float(rng.uniform(*profile.branch_pitch)) * (1.22 - 0.55 * t)
        offset = np.array([math.cos(azimuth), 0.0, math.sin(azimuth)])
        child = np.array([0.0, 1.0, 0.0]) * math.cos(pitch) + offset * math.sin(pitch)
        length = height * profile.branch_length * (1.20 - 0.50 * t) \
            * float(rng.uniform(0.82, 1.18))
        radius = radii_array[index] * profile.branch_radius * float(rng.uniform(0.85, 1.12))
        if radius < 0.040 or length < 0.4:
            continue
        _grow_branch(path[index], child, length, radius, 1, profile, rng, branches,
                     segments=5)
    return branches


def _buttress_roots(profile: TreeProfile, rng: Rng) -> M.Mesh:
    """Lofted buttress roots that flow out of the trunk and sink into the ground."""
    if profile.root_count <= 0:
        return M.Mesh(material=profile.bark_material)
    parts = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    phase = float(rng.uniform(0.0, math.pi * 2.0))
    for i in range(profile.root_count):
        azimuth = phase + golden * i + float(rng.normal(0.0, 0.22))
        direction = np.array([math.cos(azimuth), 0.0, math.sin(azimuth)])
        spread = profile.root_spread * float(rng.uniform(0.7, 1.35))
        rise = profile.root_rise * float(rng.uniform(0.7, 1.3))
        points = []
        radii = []
        steps = 6
        for s in range(steps):
            t = s / (steps - 1)
            lateral = direction * spread * (t ** 0.75)
            wobble = np.array([math.cos(azimuth + 1.6), 0.0, math.sin(azimuth + 1.6)]) \
                * math.sin(t * 3.4) * spread * 0.14
            y = rise * (1.0 - t) ** 1.9 - 0.12 * t
            points.append(lateral + wobble + np.array([0.0, y, 0.0]))
            radii.append(profile.trunk_radius * (0.46 * (1.0 - t) ** 0.8 + 0.05))
        root = M.tube(np.array(points), radii, segments=6, cap_end=False,
                      uv_scale=0.55, material=profile.bark_material,
                      radial_profile=lambda k, n: 1.0 + 0.24 * math.cos(k / n * math.pi * 4.0))
        parts.append(root)
    merged = M.merge(parts, profile.bark_material)
    merged.recompute_normals(72.0)
    return merged


def _leaf_cluster(center: np.ndarray, radius: float, normal: np.ndarray, rng: Rng,
                  planes: int, material: str) -> M.Mesh:
    """A cluster card set: several bent quads crossed around the branch tip.

    Bending each card and randomising its axis stops the canopy from reading as
    flat intersecting planes when the camera comes level with it.
    """
    parts = []
    axis = normal / max(np.linalg.norm(normal), 1e-9)
    for plane in range(planes):
        angle = math.pi * plane / planes + float(rng.uniform(-0.25, 0.25))
        reference = np.array([0.0, 1.0, 0.0]) if abs(axis[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        side = np.cross(axis, reference)
        side /= max(np.linalg.norm(side), 1e-9)
        other = np.cross(axis, side)
        u = side * math.cos(angle) + other * math.sin(angle)
        v = np.cross(axis, u)
        v /= max(np.linalg.norm(v), 1e-9)
        tilt = float(rng.uniform(-0.35, 0.35))
        v = v * math.cos(tilt) + axis * math.sin(tilt)
        # atlas cell selection
        cell_u = 0.5 * int(rng.integers(0, 2))
        cell_v = 0.5 * int(rng.integers(0, 2))
        positions, uvs, indices = [], [], []
        rows, cols = 2, 2
        bend = radius * float(rng.uniform(0.20, 0.42))
        for r in range(rows + 1):
            for c in range(cols + 1):
                fu = c / cols
                fv = r / rows
                local = u * (fu - 0.5) * 2.0 * radius + v * (fv - 0.5) * 2.0 * radius
                curve = -axis * bend * ((fu - 0.5) ** 2 + (fv - 0.5) ** 2) * 4.0
                positions.append(center + local + curve)
                uvs.append([cell_u + fu * 0.5, cell_v + fv * 0.5])
        for r in range(rows):
            for c in range(cols):
                a = r * (cols + 1) + c
                b = a + 1
                d = a + cols + 1
                e = d + 1
                indices.extend([a, d, e, a, e, b])
        card = M.Mesh(np.asarray(positions), np.zeros((len(positions), 3)),
                      np.asarray(uvs), None, np.asarray(indices, np.int64), material)
        card.recompute_normals(180.0)
        # Face the normals outward from the cluster centre so lighting reads as
        # volume rather than as flat cards. A vertex sitting exactly on the
        # centre has no outward direction, so it falls back to the card axis -
        # a zero-length normal would ship as a shading error.
        outward = card.positions - center
        lengths = np.linalg.norm(outward, axis=1, keepdims=True)
        safe = lengths > 1e-5
        card.normals = np.where(safe, outward / np.maximum(lengths, 1e-9),
                                axis[None, :])
        parts.append(card)
    return M.merge(parts, material)


def build_tree(profile: TreeProfile | str, seed: int = 0,
               detail: str = "high",
               canopy_floor: float = 0.0) -> tuple[M.Mesh, M.Mesh]:
    """Return (wood, foliage) meshes for one tree, origin at the ground contact.

    `canopy_floor` is the height, as a fraction of the tree's own height, below
    which no leaf cluster is emitted. The lowest branches droop and their tips
    carry clusters, so foliage settles well below where the branch attaches -
    on a 17 m oak whose first branch is at 5.4 m, leaves reach the floor and
    the stand reads as hedge rather than woodland. Raising this clears the
    trunk without touching the crown. Default 0.0 leaves the tree unchanged.
    """
    if isinstance(profile, str):
        profile = PROFILES[profile]
    rng = Rng(seed)
    branches = _grow_trunk(profile, rng)
    # Same expression `_grow_trunk` uses, so the floor is a fraction of the
    # trunk actually built rather than of the nominal profile height.
    tree_height = profile.height * (0.72 if profile.broken_top else 1.0)

    detail_scale = {"high": 1.0, "mid": 0.55, "low": 0.28}[detail]
    wood_parts = []
    for branch in branches:
        sides = profile.trunk_sides if branch.level == 0 else (6 if branch.level == 1 else 4)
        if detail == "mid":
            sides = max(4, int(sides * 0.7))
        elif detail == "low":
            # at the far tier the silhouette does the work, not the cross-section
            sides = max(5, int(sides * 0.55)) if branch.level == 0 else 4
        # the far tier keeps only the trunk and its primaries; the canopy does
        # the reading at that distance, and the twig geometry does not
        if detail == "low" and branch.level >= 2:
            continue
        if detail == "mid" and branch.level >= 4:
            continue
        profile_fn = None
        if branch.level == 0:
            def profile_fn(k, n, _rng=Rng(seed + 991)):
                return 1.0 + 0.11 * math.cos(k / n * math.pi * 6.0) \
                    + 0.05 * math.cos(k / n * math.pi * 10.0 + 1.1)
        wood_parts.append(M.tube(branch.path, branch.radii, segments=sides,
                                 cap_end=branch.level == 1, uv_scale=0.9,
                                 material=profile.bark_material,
                                 radial_profile=profile_fn))
    if detail == "high":
        wood_parts.append(_buttress_roots(profile, rng))
    wood = M.merge(wood_parts, profile.bark_material)
    wood.recompute_normals(70.0)

    foliage = M.Mesh(material=profile.foliage_material)
    if profile.foliage:
        deepest = max(b.level for b in branches)
        tips = [b for b in branches if b.level == deepest]
        if len(tips) < 4:
            tips = [b for b in branches if b.level >= max(1, deepest - 1)]
        per_tip = max(1, int(round(profile.clusters_per_tip * detail_scale)))
        planes = profile.cluster_planes if detail == "high" else 2
        budget = int(profile.max_clusters * (1.0 if detail == "high"
                                             else (0.45 if detail == "mid" else 0.17)))
        budget = max(budget, 4)
        # even sampling of the tip set keeps the crown balanced when trimmed
        wanted = min(budget, len(tips) * per_tip)
        stride = max(1, int(math.ceil(len(tips) * per_tip / max(wanted, 1))))
        clusters = []
        emitted = 0
        slot = 0
        radius_gain = {"high": 1.0, "mid": 1.45, "low": 2.55}[detail]
        for branch in tips:
            for k in range(per_tip):
                slot += 1
                if slot % stride:
                    continue
                if emitted >= budget:
                    break
                t = 0.5 + 0.5 * (k + 0.5) / per_tip
                index = min(int(t * (branch.path.shape[0] - 1)), branch.path.shape[0] - 1)
                base = branch.path[index]
                jitter = rng.normal(0.0, branch.tip_length * 0.20, 3)
                outward = branch.tip_direction * branch.tip_length * 0.25 * profile.canopy_bias
                center = base + jitter + outward
                if canopy_floor > 0.0 and center[1] < canopy_floor * tree_height:
                    continue
                radius = float(rng.uniform(*profile.cluster_size)) * radius_gain
                clusters.append(_leaf_cluster(center, radius, branch.tip_direction, rng,
                                              planes, profile.foliage_material))
                emitted += 1
            if emitted >= budget:
                break
        foliage = M.merge(clusters, profile.foliage_material)
    return wood, foliage


def fallen_log(length: float = 7.5, radius: float = 0.55, seed: int = 0,
               material: str = "bark_dark") -> M.Mesh:
    """A toppled trunk with a torn root plate and a broken end."""
    rng = Rng(seed)
    points = []
    radii = []
    steps = 9
    for i in range(steps):
        t = i / (steps - 1)
        points.append([t * length,
                       radius * (0.85 + 0.12 * math.sin(t * 5.0)) + float(rng.normal(0, 0.03)),
                       math.sin(t * 2.1) * length * 0.06])
        radii.append(radius * (1.0 - 0.42 * t) * float(rng.uniform(0.94, 1.06)))
    log = M.tube(np.array(points), radii, segments=9, cap_start=True, cap_end=True,
                 uv_scale=0.8, material=material,
                 radial_profile=lambda k, n: 1.0 + 0.13 * math.cos(k / n * math.pi * 5.0))
    parts = [log]
    # root plate: a torn disc of roots standing at the butt end
    for i in range(9):
        angle = math.pi * 2.0 * i / 9 + float(rng.uniform(-0.2, 0.2))
        reach = radius * float(rng.uniform(1.5, 3.0))
        path = np.array([
            [0.0, radius * 0.85, 0.0],
            [-reach * 0.35, radius * 0.85 + reach * 0.45, math.cos(angle) * reach * 0.35],
            [-reach * 0.55, radius * 0.85 + reach * 0.92, math.cos(angle) * reach * 0.62],
        ])
        path[:, 2] += math.sin(angle) * reach * 0.35
        parts.append(M.tube(path, [radius * 0.30, radius * 0.20, radius * 0.08], segments=6,
                            cap_end=True, uv_scale=0.7, material=material))
    # a few stubs of broken limbs
    for i in range(4):
        t = float(rng.uniform(0.25, 0.9))
        angle = float(rng.uniform(0, math.pi * 2))
        base = np.array([t * length, radius * 0.9, math.sin(t * 2.1) * length * 0.06])
        direction = np.array([float(rng.uniform(-0.3, 0.3)), abs(float(rng.normal(0.7, 0.25))),
                              math.sin(angle)])
        direction /= np.linalg.norm(direction)
        stub_length = float(rng.uniform(0.5, 1.4))
        parts.append(M.tube(np.array([base, base + direction * stub_length]),
                            [radius * 0.26, radius * 0.10], segments=6, cap_end=True,
                            uv_scale=0.8, material=material))
    merged = M.merge(parts, material)
    merged.recompute_normals(70.0)
    return merged


def stump(radius: float = 0.7, height: float = 0.9, seed: int = 0,
          material: str = "bark_dark") -> M.Mesh:
    rng = Rng(seed)
    body = M.cylinder(radius * 1.3, radius, height, 11, uv_scale=0.9, material=material,
                      radial_profile=lambda k, n: 1.0 + 0.16 * math.cos(k / n * math.pi * 5.0))
    parts = [body]
    for i in range(5):
        angle = math.pi * 2.0 * i / 5 + float(rng.uniform(-0.3, 0.3))
        direction = np.array([math.cos(angle), -0.08, math.sin(angle)])
        path = np.array([[0.0, 0.12, 0.0], direction * radius * 1.6 + np.array([0, 0.05, 0]),
                         direction * radius * 2.6 + np.array([0, -0.05, 0])])
        parts.append(M.tube(path, [radius * 0.34, radius * 0.20, radius * 0.07], segments=6,
                            cap_end=True, uv_scale=0.7, material=material))
    merged = M.merge(parts, material)
    merged.recompute_normals(70.0)
    return merged
