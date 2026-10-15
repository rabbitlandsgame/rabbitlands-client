"""The ground side of a secret: the prop a region places and the record the
server reads to make it a way in.

`dress(build, terrain, design, seed)` runs in a region build after its
landmarks exist. For each secret whose entrance is on the region it finds
open, walkable ground near the landmark or point the design names, places
the entrance prop there, and records an interactive of kind `secret` in the
region manifest: the server tools turn that into a use-to-enter portal, with
the key item if the design asks for one.

`dress_interior(combined, design, insides_map, seed)` does the same for a
secret whose door is on one of the region's insides maps, inside the space the
design names.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import terrain as TER
from regionbuild import Placement, RegionBuild
import secretrooms as SR


def _fits(t: TER.Terrain, x: float, z: float, sea_level: float, *, natural: bool = True,
          clearance: float = 1.2, mask: bool = True) -> bool:
    """Open ground for a prop: inside the map, dry, level, unblocked in a cross
    of `clearance` metres (by the terrain mask when `mask`), and (when
    `natural`) not on authored paving."""
    if not (t.x0 + 8 < x < t.x0 + t.size_x - 8 and t.z0 + 8 < z < t.z0 + t.size_z - 8):
        return False
    for sx, sz in ((x, z), (x + clearance, z), (x - clearance, z), (x, z + clearance), (x, z - clearance)):
        if mask and bool(t.blocked_at(sx, sz)):
            return False
        if float(t.height_at(sx, sz)) < sea_level + DRY_MARGIN:
            return False
        if float(t.slope_at(sx, sz)) > 0.9:
            return False
        if natural and int(t.surface_at(sx, sz)) in TER.AUTHORED_SURFACES:
            return False
    return True


DRY_MARGIN = 0.3  # the flooded ruins stand this little above their water
FAR_REACH = 60.0  # a giant tree or a stone ring can block the ground for 30 m around


def footprints(build: RegionBuild) -> np.ndarray:
    """(x, z, radius) of every colliding placement, sized as the walk grids
    size them: a structure blocks 0.62 of its half-extent, a tree 0.16."""
    radii: dict[str, float] = {}
    rows = []
    for placement in getattr(build, "placements", ()):
        if not getattr(placement, "collides", False):
            continue
        key = placement.mesh
        if key not in radii:
            item = build.meshes.get(key)
            bounds = getattr(item, "bounds", None)
            if bounds is None:
                radii[key] = -1.0
            else:
                low, high = bounds()
                radii[key] = float(max(abs(low[0]), abs(high[0]), abs(low[2]), abs(high[2])))
        if radii[key] < 0:
            continue
        factor = 0.16 if placement.kind in ("tree", "foliage") else 0.62
        radius = min(max(radii[key] * placement.scale * factor, 0.40), 11.0)
        px, _, pz = placement.position
        rows.append((float(px), float(pz), radius))
    return np.array(rows, dtype=float) if rows else np.zeros((0, 3))


def _clear_of(prints: np.ndarray, x: float, z: float, margin: float) -> bool:
    if len(prints) == 0:
        return True
    return bool(np.all(np.hypot(prints[:, 0] - x, prints[:, 1] - z) > prints[:, 2] + margin))


def _site(t: TER.Terrain, x: float, z: float, sea_level: float, reach: float = 14.0,
          prints: np.ndarray | None = None, prefer_near: bool = False):
    """Where the prop stands: natural ground near the anchor first; failing
    that paved ground with room around it (a grate or a slab in a square,
    never in a three-metre lane); failing that the same further out. Towns
    and temples pave everything near their landmarks, which is where most of
    the entrances want to be.

    Some kits use the terrain's blocked mask to keep buildings and trees off
    a precinct (Ssarathi masks 104 m around its temple) though players walk
    all over it. When the mask leaves nothing, the last passes ignore it and
    ask the placements themselves for room, the way the walk grids do."""
    passes = [(True, 1.2, reach, True), (False, 2.6, reach, True),
              (True, 1.2, FAR_REACH, True), (False, 2.6, FAR_REACH, True)]
    if prints is not None:
        passes += [(True, 1.2, reach, False), (False, 2.6, reach, False),
                   (True, 1.2, FAR_REACH, False), (False, 2.6, FAR_REACH, False)]
    if prefer_near and prints is not None:
        passes.sort(key=lambda p:p[2]>reach)
    for natural, clearance, far, mask in passes:
        def ok(cx, cz):
            if not _fits(t, cx, cz, sea_level, natural=natural, clearance=clearance, mask=mask):
                return False
            return mask or _clear_of(prints, cx, cz, 2.0)
        if ok(x, z):
            return x, z
        ring = 3.0
        while ring <= far:
            for index in range(12):
                angle = math.tau * index / 12.0
                cx, cz = x + math.cos(angle) * ring, z + math.sin(angle) * ring
                if ok(cx, cz):
                    return cx, cz
            ring += 3.0
    return None


def resolve_anchor(build: RegionBuild, at, offset=(0.0, 0.0)):
    if isinstance(at, str):
        for landmark in build.landmarks:
            if landmark.get("id") == at:
                px, _, pz = landmark["position"]
                return float(px) + offset[0], float(pz) + offset[1]
        # Some kits collect their landmark list from the placements only at
        # the end of the build; the placements themselves are there already.
        for placement in getattr(build, "placements", ()):
            if getattr(placement, "landmark", None) == at:
                px, _, pz = placement.position
                return float(px) + offset[0], float(pz) + offset[1]
        raise KeyError(f"no landmark {at!r} to hang a secret on")
    return float(at[0]) + offset[0], float(at[1]) + offset[1]


def dress(build: RegionBuild, t: TER.Terrain, design, seed: int, *, sea_level: float = 0.0,
          server_origin=None) -> list[dict]:
    """Place every entrance the region owns. Returns the interactive records."""
    region = design.REGION
    palette = getattr(design, "PROP_PALETTE", None)
    prints = footprints(build)
    out = []
    for index, secret in enumerate(design.SECRETS):
        if secret.door_map:
            continue
        ax, az = resolve_anchor(build, secret.at, secret.offset)
        site = _site(t,ax,az,sea_level,prints=prints,prefer_near=secret.prefer_near)
        if site is None:
            build.notes.append(f"secret {secret.id}: no open ground within {FAR_REACH:.0f} m of {secret.at}; "
                               "entrance not placed")
            continue
        x, z = site
        y = float(t.height_at(x, z))
        key = f"Secret_{secret.id.replace('-', '_')}"
        if key not in build.meshes:
            build.meshes[key] = SR.entrance_prop(secret.entrance, palette, seed=seed + index)
        build.place(Placement(node=key, mesh=key, position=(round(x, 3), round(y - 0.05, 3), round(z, 3)),
                              rotation_y=(seed * 0.37 + index * 1.7) % math.tau, scale=1.0,
                              collides=True, kind="prop"))
        t.mark_blocked_disc((x, z), 0.9)
        t.tree_block |= np.hypot(t.gx - x, t.gz - z) < 5.0
        prints = np.vstack([prints, [[x, z, 1.5]]]) if len(prints) else np.array([[x, z, 1.5]])
        if secret.kind == "mouth":
            target_map, target_spawn, label = secret.links[0]
        else:
            target_map, target_spawn, label = f"{region}_secrets", secret.id, secret.name
        record = {"id": f"secret-{secret.id}", "kind": "secret", "secret": secret.id,
                  "name": secret.name, "label": SR.label_for(secret), "prop": secret.entrance,
                  "key": secret.key, "destinationMap": target_map, "destinationSpawn": target_spawn,
                  "position": [round(x, 2), round(y, 2), round(z, 2)], "authority": "server"}
        if server_origin is not None:
            record["serverTile"] = [int(round(x + server_origin[0])), int(round(server_origin[1] - z))]
        build.interactives.append(record)
        secret.door_position = record["position"]
        out.append(record)
    return out


def materials(design) -> set[str]:
    """The materials a region must pin for its entrance props.

    Props take everything from the design's PROP_PALETTE. A kit that checks
    its pin through `base_material` cannot take a name ending in the ground
    suffix (scorched_ground is a material of its own, not a copy of a
    "scorched"), so such kits set a `dark` palette entry instead.
    """
    kinds = {s.entrance for s in design.SECRETS if not s.door_map}
    return SR.prop_materials(kinds, getattr(design, "PROP_PALETTE", None))


def dress_interior(combined, design, insides_map: str, seed: int) -> list[dict]:
    """Entrances that stand inside one of the region's insides maps."""
    region = design.REGION
    out = []
    for index, secret in enumerate(design.SECRETS):
        if secret.door_map != insides_map:
            continue
        space = combined.spaces.get(secret.door_space)
        if space is None:
            raise KeyError(f"secret {secret.id}: insides map {insides_map} has no space {secret.door_space!r}")
        x = (space["x0"] + space["x1"]) * 0.5 + secret.offset[0]
        z = (space["z0"] + space["z1"]) * 0.5 + secret.offset[1]
        y = float(space["floor"])
        prop = SR.entrance_prop(secret.entrance, getattr(design, "PROP_PALETTE", None), seed=seed + index)
        combined.group.add(prop.translate(x, y, z))
        if secret.kind == "mouth":
            target_map, target_spawn = secret.links[0][0], secret.links[0][1]
        else:
            target_map, target_spawn = f"{region}_secrets", secret.id
        record = {"id": f"secret-{secret.id}", "kind": "secret", "secret": secret.id,
                  "name": secret.name, "label": SR.label_for(secret), "prop": secret.entrance,
                  "key": secret.key, "destinationMap": target_map, "destinationSpawn": target_spawn,
                  "position": [round(x, 2), round(y, 2), round(z, 2)], "space": secret.door_space,
                  "authority": "server"}
        combined.interactives.append(record)
        out.append(record)
    return out
