"""harvest_presentation.py: how a continent-v2 harvest node is presented, from its scene marker to the package.

Owner-approved 2026-10-14 (work-output/landfall-audit-2026-10-14/harvest/FINDINGS.md 5.1-5.6): inside a harvest
grouping every visible plant or rock of that kind is harvestable, either as a PATCH NODE (the node's model is a whole
natural unit - a 3 m crop-row segment, a herb clump, a hedge segment, a seam, a kelp strand - and only its centre tile
blocks) or as PROMOTED SCENERY (a kit placement the scene already holds, a grove's olive tree, becomes the node's art:
the client stands no model of its own and binds the pick to the placed mesh). The server is unchanged: one node per
closed tile, harvested from within Chebyshev 2.

Scene markers (the `extras` of the `Gameplay/Harvestables` Marker3D nodes; region_snapshot.gd copies them into the
bake's gameplay.harvestables records). Existing keys: `authority`, `objectId` (int), `resource`, `cluster`, `zone`.
Optional presentation keys, all checked here and refused when malformed:

  variant        int >= 0       which of the resource's registry models (objects.json harvestables.variants[label],
                                taken modulo its length); absent: the client picks one from the object id
  yaw            number         degrees about +Y in the Godot/glTF frame (counter-clockwise seen from above; 0 = the
                                model as authored). Absent: the client's random yaw seeded by the object id. A row
                                segment states it so it follows its row.
  footprint      [length, width]  metres, each > 0 and <= FOOTPRINT_MAX_METRES: the patch's extent, its length along
                                the model's +X after yaw. The client picks it with a box this size instead of the
                                0.9 m cylinder, and stands the model at scale 1 (butted segments must meet).
  grouping       string         the harvest grouping id ([a-z0-9][a-z0-9_-]*, unique per map): a field, drift,
                                hedgerow, grove, band or seam. The maps draw one marker per grouping, not per node.
  groupingName   string         the grouping's display name (hover label). Optional; every node that states one must
                                state the same.
  bindPlacement  string         promoted scenery: the kit placement whose mesh is the node's art, named by its asset
                                record id (the bake's objects[].id, e.g. "landfall-kit-olive-tree-1-017"), by its
                                nodeName ("Authored_landfall_kit_olive_tree_1_017"), or by a scene node path ending
                                in either ("AuthoredAssets/landfall-kit-olive-tree-1-017"). It must resolve to exactly
                                one placement inside this territory, within BIND_MAX_METRES of the node, bound by no
                                other node.

What publish_client.py writes into the territory manifest (world.json; chunk manifests drop all three):

  harvestablesSchema  SCHEMA
  harvestables        one entry per harvest marker, sorted by objectId:
                        {"id", "objectId", "resource", "serverTile", "position",
                         + "variant", "yaw", "footprint", "grouping" when the marker states them,
                         + "bind": {"node", "assetId", "chunk", "height"} for promoted scenery}
  harvestGroupings    one entry per grouping, sorted by id:
                        {"id", "name", "resources", "centre" [x, z] territory-local metres (the mean of its nodes),
                         "centreTile" [x, y], "nodeCount", "objectIds"}

A package without these (every one published before 2026-10-14 carries `harvestables: []`) loads unchanged: the client
keeps its random yaw, one model per label, the 0.9 m pick and one map dot per node.

road_offenders() is publish_server.py's D11 check: a node whose served tile's centre lies within a road's half-width
(the scene's Roads/* curves, `paths` of kind "road", width interpolated between their points) is refused.
"""
from __future__ import annotations

import math
import re

import numpy as np

SCHEMA = "eloria-harvest-presentation-v1"
MARKER_KEYS = ("variant", "yaw", "footprint", "grouping", "groupingName", "bindPlacement")
FOOTPRINT_MAX_METRES = 12.0
#: How far (horizontally) a promoted placement's origin may stand from its node's marker: the node sits on the
#: trunk or centre tile of the thing it presents.
BIND_MAX_METRES = 3.0
GROUPING_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
FORBIDDEN_TEXT = ("|", "#", "\n", "\r")


class PresentationError(ValueError):
    """A harvest marker's presentation extras this publish will not write."""


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def marker_hints(record):
    """The presentation fields of one bake harvest record, checked and normalised (absent keys stay absent)."""
    identity = record.get("id", "?")
    hints = {}
    if "variant" in record:
        value = record["variant"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) \
                or int(value) < 0:
            raise PresentationError(f"{identity}: variant {value!r} is not an integer >= 0")
        hints["variant"] = int(value)
    if "yaw" in record:
        value = record["yaw"]
        if not _number(value):
            raise PresentationError(f"{identity}: yaw {value!r} is not a number of degrees")
        hints["yaw"] = round(float(value) % 360.0, 3)
    if "footprint" in record:
        value = record["footprint"]
        if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(_number(v) for v in value) \
                or not all(0.0 < float(v) <= FOOTPRINT_MAX_METRES for v in value):
            raise PresentationError(f"{identity}: footprint {value!r} is not [length, width] metres, each 0-"
                                    f"{FOOTPRINT_MAX_METRES:g}")
        hints["footprint"] = [round(float(v), 3) for v in value]
    if "grouping" in record:
        value = record["grouping"]
        if not isinstance(value, str) or not GROUPING_ID.match(value):
            raise PresentationError(f"{identity}: grouping {value!r} is not an id ([a-z0-9][a-z0-9_-]*)")
        hints["grouping"] = value
    if "groupingName" in record:
        value = record["groupingName"]
        if "grouping" not in hints:
            raise PresentationError(f"{identity}: groupingName without a grouping")
        if not isinstance(value, str) or not value.strip() or value != value.strip() \
                or any(mark in value for mark in FORBIDDEN_TEXT):
            raise PresentationError(f"{identity}: groupingName {value!r} is empty, padded or holds '|', '#' or a "
                                    "line break")
        hints["groupingName"] = value
    if "bindPlacement" in record:
        value = record["bindPlacement"]
        if not isinstance(value, str) or not value.strip():
            raise PresentationError(f"{identity}: bindPlacement {value!r} is not a placement id or node path")
        hints["bindPlacement"] = value.strip()
    return hints


def resolve_placement(reference, placements):
    """The one placement `reference` names: by asset record id (`authoringId`), by nodeName (`node`), or by a scene
    node path whose last segment is either. `placements` are library.json-shaped records."""
    leaf = reference.replace("\\", "/").rstrip("/").split("/")[-1]
    found = [p for p in placements if leaf in (p.get("authoringId"), p.get("node"))]
    if len(found) != 1:
        raise PresentationError(f"bindPlacement {reference!r} names {len(found)} kit placements, not one")
    return found[0]


def tile_of(position, server_origin):
    """authoring.server_tile: the served tile of a territory-local point."""
    x, _y, z = (float(v) for v in position)
    return [math.floor(x + server_origin[0]), math.floor(server_origin[1] - z)]


def package_entries(records, placements, server_origin):
    """(harvestables, harvestGroupings) for the territory manifest.

    `records` are the bake's gameplay.harvestables; `placements` the territory's published kit placements, each
    {"node", "authoringId", "position" [x, y, z] territory-local, "chunk", "top" (its highest point, metres)}; only
    a placement in this list (inside the territory window) can be bound."""
    entries, groups, bound = [], {}, {}
    seen = set()
    for record in records:
        identity = record.get("id")
        object_id = record.get("objectId")
        if type(object_id) is not int:
            raise PresentationError(f"{identity}: a harvestable marker needs an integer objectId")
        if object_id in seen:
            raise PresentationError(f"{identity}: objectId {object_id} is used by two harvest markers")
        seen.add(object_id)
        position = [round(float(v), 3) for v in record["position"]]
        entry = {"id": identity, "objectId": object_id, "resource": record.get("resource", record.get("label")),
                 "serverTile": list(record.get("serverTile") or tile_of(position, server_origin)),
                 "position": position}
        hints = marker_hints(record)
        for key in ("variant", "yaw", "footprint", "grouping"):
            if key in hints:
                entry[key] = hints[key]
        if "bindPlacement" in hints:
            placement = resolve_placement(hints["bindPlacement"], placements)
            node = placement["node"]
            if node in bound:
                raise PresentationError(f"{identity}: kit placement {node} is already bound by {bound[node]}")
            bound[node] = identity
            at = [float(v) for v in placement["position"]]
            distance = math.hypot(at[0] - position[0], at[2] - position[2])
            if distance > BIND_MAX_METRES:
                raise PresentationError(f"{identity}: kit placement {node} stands {distance:.2f} m from the node "
                                        f"(at most {BIND_MAX_METRES:g} m: the node sits on its trunk or centre tile)")
            entry["bind"] = {"node": node, "assetId": placement.get("authoringId", ""), "chunk": placement["chunk"],
                             "height": round(max(float(placement.get("top", at[1])) - at[1], 0.0), 3)}
        if "grouping" in hints:
            group = groups.setdefault(hints["grouping"], {"names": set(), "members": []})
            if "groupingName" in hints:
                group["names"].add(hints["groupingName"])
            group["members"].append(entry)
        entries.append(entry)
    entries.sort(key=lambda e: e["objectId"])
    groupings = []
    for key in sorted(groups):
        group = groups[key]
        if len(group["names"]) > 1:
            raise PresentationError(f"grouping {key}: its nodes name it {sorted(group['names'])}")
        members = sorted(group["members"], key=lambda e: e["objectId"])
        centre = np.mean([[m["position"][0], m["position"][2]] for m in members], axis=0)
        resources = sorted({str(m["resource"]) for m in members})
        name = next(iter(group["names"])) if group["names"] else (
            resources[0] if len(resources) == 1 else key.replace("-", " ").replace("_", " ").title())
        groupings.append({"id": key, "name": name, "resources": resources,
                          "centre": [round(float(centre[0]), 3), round(float(centre[1]), 3)],
                          "centreTile": tile_of([centre[0], 0.0, centre[1]], server_origin),
                          "nodeCount": len(members), "objectIds": [m["objectId"] for m in members]})
    return entries, groupings


# --- D11: no node on a road ----------------------------------------------------------------------------------------

def road_segments(paths):
    """Every road's segments in territory-local x/z, as (a, b, half-width at a, half-width at b, road id)."""
    out = []
    for path in paths or []:
        if path.get("kind") != "road":
            continue
        points = [(float(p["position"][0]), float(p["position"][2]), float(p.get("width", 0.0)) / 2.0)
                  for p in path.get("points", [])]
        if path.get("closed") and len(points) > 2:
            points.append(points[0])
        for (ax, az, ah), (bx, bz, bh) in zip(points, points[1:]):
            out.append(((ax, az), (bx, bz), ah, bh, path.get("id", "?")))
    return out


def road_clearance(x, z, segments):
    """(how far inside the nearest road band the point lies: half-width minus distance, road id); None off roads."""
    best = None
    for (ax, az), (bx, bz), ah, bh, identity in segments:
        dx, dz = bx - ax, bz - az
        length2 = dx * dx + dz * dz
        t = 0.0 if length2 <= 1e-12 else min(1.0, max(0.0, ((x - ax) * dx + (z - az) * dz) / length2))
        distance = math.hypot(x - (ax + t * dx), z - (az + t * dz))
        inside = (ah + t * (bh - ah)) - distance
        if inside > 0.0 and (best is None or inside > best[0]):
            best = (inside, identity)
    return best


def road_offenders(paths, nodes, local_of):
    """D11: every node whose served tile's centre lies within a road's half-width, as
    {"id", "tile", "road", "inside"} (metres inside the band). `nodes` are {"id", "tile"}; `local_of(tx, ty)` gives a
    tile centre in territory-local metres (frames.Frame.local)."""
    segments = road_segments(paths)
    offenders = []
    for node in nodes:
        x, z = local_of(*node["tile"])
        hit = road_clearance(x, z, segments)
        if hit is not None:
            offenders.append({"id": node["id"], "tile": list(node["tile"]), "road": hit[1],
                              "inside": round(hit[0], 3)})
    return offenders
