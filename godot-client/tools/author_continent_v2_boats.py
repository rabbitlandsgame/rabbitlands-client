#!/usr/bin/env python3
"""Author the continent-v2 boat network from content/boat-network.json (owner-approved 2026-10-19).

    python godot-client/tools/author_continent_v2_boats.py --check
    python godot-client/tools/author_continent_v2_boats.py --apply

The spec lists docks and routes. A dock is a pier on one map: a new trestle jetty ("pier": start/end/deck), or a
berth line along a pier the map already has ("pier": {"bridge": <bridge id>}). A route joins two docks with one
boat each way. At each end of a route, the dock's berth for the other dock gets:
  * a boat prop moored alongside the pier, bow seaward, its waterline origin at the water level (the ferry ship
    for an isle crossing, a fishing boat otherwise);
  * a harbour banner on the deck edge just seaward of the gangway;
  * the boat's interactive marker on the deck by the gangway (<map>--obj-boat-<other dock>). publish_server.py
    serves it as an object portal through server-rows.json (portal.destinationMap, landingMarker, returnBy);
  * the landing marker where the other dock's boat sets passengers down (<map>--boat-landing-<other dock>), on the
    deck 4 m shoreward of the gangway. That keeps it within the publisher's reach of the boat that sails back.
A new pier is a bridge_control "pier" deck, walkable once exported, dressed with trestle spans and a lantern. Its
deck and support surfaces are copies of Coilmere's north jetty's.

Every generated node carries "boatNetwork": <dock id> in its metadata or extras. --apply removes the previous
generation (and the resources only it used) and writes it afresh. The scenes, the server rows and each touched
map's contract counts (runtimePointCount, authoredMarkerCount) follow the spec. A route marked "existing" (the
Ravenhead-Coilmere ferry of 2026-10-14) keeps its hand-authored nodes; only its row text follows the network's
wording. Positions, deck clearance, hull draught and marker spacing are checked before anything is written.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

import continent_v2_territories as T
import repartition_continent_v2_content as RC

CHECKOUT = T.CHECKOUT
META = CHECKOUT / "eloria-assets/maps/continent-v2/_continent_v2"
SPEC = META / "content/boat-network.json"
ROWS = META / "content/server-rows.json"
REGIONS = CHECKOUT / "godot-client/world_authoring/regions"
KIT = "res://world_authoring/regions/tollholms/assets/prototypes/"
SCRIPTS = {"asset": "res://src/dev/map_authoring_region/asset_control.gd",
           "marker": "res://src/dev/map_authoring_region/gameplay_marker.gd",
           "bridge": "res://src/dev/map_authoring_region/bridge_control.gd",
           "surface": "res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd"}
# kit name, half length, half beam, keel depth below the waterline
BOATS = {"ferry": ("kit-sw-ferry-ship", 11.0, 6.47, 1.85),
         "fishing-boat-2": ("kit-fishing-boat-2", 4.5, 2.32, 1.9),
         "fishing-boat-1": ("kit-fishing-boat-1", 3.5, 1.59, 1.55)}
SPAN, SPAN_LONG, BANNER, LANTERN = ("kit-sw-trestle-pier-span", "kit-sw-trestle-pier-span-long24",
                                    "kit-harbour-banner-1", "kit-lantern-post-1")
DONOR = ("coilmere", "coilmere-north-jetty-1")
CLEARANCE = 0.4        # between the deck edge and a moored hull
SPAN_LENGTH = 9.0      # a trestle span scaled 1.125 along the deck, as Coilmere's and Ravenhead's
LONG_SPAN_BELOW = 5.5  # seabed deeper than this under a span: the 24 m piles
LANDING_BACK = 4.0     # the landing, shoreward of its gangway
LANDING_REACH = 8      # publish_server.BOAT_LANDING_REACH (tiles are metres)
FIRST_OBJECT_ID = 30
TAG = "boatNetwork"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fmt(value: float) -> str:
    return format(round(float(value), 4) + 0.0, ".10g")


def transform(rows3, origin) -> str:
    values = [v for row in rows3 for v in row] + list(origin)
    return "Transform3D(" + ", ".join(fmt(v) for v in values) + ")"


def yaw_rows(x_axis, scale_x=1.0, scale_z=1.0):
    """Basis rows (Godot writes rows) for a node whose X axis points along x_axis (x, z) in the ground plane."""
    ux, uz = x_axis
    # columns: X = (ux, 0, uz) * sx, Y = up, Z = X x Y = (-uz, 0, ux) * sz
    return [(ux * scale_x, 0.0, -uz * scale_z), (0.0, 1.0, 0.0), (uz * scale_x, 0.0, ux * scale_z)]


class Ground:
    def __init__(self):
        prov = read(META / "group-terrain-v2/terrain-provenance.json")
        self.w, self.h = prov["grid"]["gridSize"]
        self.x0, self.z0 = prov["grid"]["continentFirstVertex"]
        self.heights = np.fromfile(META / "group-terrain-v2/base-heights.f32le", "<f4").reshape(self.h, self.w)

    def __call__(self, x, z):
        fx, fz = (x - self.x0) / 2.0, (z - self.z0) / 2.0
        c, r = int(math.floor(fx)), int(math.floor(fz))
        if not (0 <= r < self.h - 1 and 0 <= c < self.w - 1):
            return -50.0
        tx, tz = fx - c, fz - r
        h00, h10 = self.heights[r, c:c + 2]; h01, h11 = self.heights[r + 1, c:c + 2]
        if tx + tz <= 1:
            return float(h00 + (h10 - h00) * tx + (h01 - h00) * tz)
        return float(h11 + (h01 - h11) * (1 - tx) + (h10 - h11) * (1 - tz))


class Dock:
    """A pier's frame: shore start S, unit direction u (seaward), left normal n, width, deck and water levels."""

    def __init__(self, ident, spec, territory, ground):
        self.id, self.spec, self.t = ident, spec, territory
        self.map = spec["map"]
        self.water = float(spec.get("water", 0.0))
        pier = spec["pier"]
        if "bridge" in pier:
            path = "Bridges/" + pier["bridge"]
            node = territory.scene.nodes[path]
            a = territory.scene.world(path + "/Start")[[0, 1, 2], 3] + territory.translation
            b = territory.scene.world(path + "/End")[[0, 1, 2], 3] + territory.translation
            self.start, self.end = np.array([a[0], a[2]]), np.array([b[0], b[2]])
            self.deck = float(max(a[1], b[1]))
            self.width = float(node.properties.get("width", "8"))
            self.new = False
        else:
            self.start, self.end = np.array(pier["start"], float), np.array(pier["end"], float)
            self.deck = float(pier["deck"])
            self.width = float(pier.get("width", 8))
            self.new = True
        d = self.end - self.start
        self.length = float(np.hypot(*d))
        self.u = d / self.length
        self.n = np.array([self.u[1], -self.u[0]])  # left of the seaward direction
        self.ground = ground

    def at(self, along, across):
        return self.start + self.u * along + self.n * across

    def side(self, berth):
        return 1.0 if berth["side"] == "left" else -1.0


def load(spec_path=SPEC):
    spec = read(spec_path)
    territories = {t.id: t for t in T.load_territories()}
    ground = Ground()
    docks = {k: Dock(k, v, territories[v["map"]], ground) for k, v in spec["docks"].items()}
    return spec, territories, ground, docks


def plan(spec, docks, ground, territories):
    """Every generated thing per map, and the problems found; nothing written."""
    shapes = {}
    for section in read(T.res_to_path(read(T.CATALOG)["partitionSpecPath"]))["sections"]:
        shapes[section["mapId"]] = unary_union([Polygon(r) for r in section["ownershipPolygons"]])
    problems, per_map = [], {}
    labels = {k: v.get("label") or territories[v["map"]].label for k, v in spec["docks"].items()}
    routes = [tuple(r["docks"]) for r in spec["routes"]]
    existing = {tuple(r["docks"]): r["existing"] for r in spec["routes"] if r.get("existing")}

    def inside(dock, point, what):
        if not shapes[dock.map].covers(Point(*point)):
            problems.append(f"{dock.id}: {what} at ({point[0]:.1f}, {point[1]:.1f}) lies outside {dock.map}")

    for dock in docks.values():
        out = per_map.setdefault(dock.map, {"assets": [], "markers": [], "bridges": [], "rows": {}})
        if dock.new:
            # the deck meets the shore at its start and clears the ground beyond the first few metres
            shore = ground(*dock.start)
            if not dock.deck - 0.7 <= shore <= dock.deck + 0.3:
                problems.append(f"{dock.id}: the shore at the pier's start is {shore:.2f} m, the deck {dock.deck} m")
            for t in np.arange(4.0, dock.length + 0.01, 1.0):
                for across in (-dock.width / 2, 0.0, dock.width / 2):
                    p = dock.at(t, across)
                    if ground(*p) > dock.deck - 0.6:
                        problems.append(f"{dock.id}: ground rises to the deck {t:.0f} m along the pier")
                        break
                else:
                    continue
                break
            for t in (0.0, dock.length):
                for across in (-dock.width / 2, dock.width / 2):
                    inside(dock, dock.at(t, across), "the pier")
            out["bridges"].append(dock)
            count = max(1, math.ceil(dock.length / SPAN_LENGTH - 0.25))
            step = dock.length / count
            for k in range(count):
                along = step * (k + 0.5)
                c = dock.at(along, 0.0)
                deep = ground(*c) < dock.water - LONG_SPAN_BELOW
                out["assets"].append({
                    "name": f"BN {labels[dock.id]} Pier Span {k + 1}", "kit": SPAN_LONG if deep else SPAN,
                    "id": f"boatnet-{dock.id}-span-{k + 1}", "dock": dock.id,
                    "transform": transform(yaw_rows(dock.u, step / 8.0, 0.8193 * dock.width / 8.0),
                                           (c[0], dock.deck, c[1])),
                    "note": f"trestle span {k + 1} of {count} on the {labels[dock.id]} pier"})
            head = dock.at(dock.length - 1.2, dock.width / 2 - 0.9)
            out["assets"].append({"name": f"BN {labels[dock.id]} Pier Lantern", "kit": LANTERN,
                                  "id": f"boatnet-{dock.id}-lantern", "dock": dock.id,
                                  "transform": transform(yaw_rows(dock.u), (head[0], dock.deck, head[1])),
                                  "note": f"a light at the head of the {labels[dock.id]} pier"})
        taken = []
        for other, berth in dock.spec["berths"].items():
            route = next((r for r in routes if set(r) == {dock.id, other}), None)
            if route is None:
                problems.append(f"{dock.id}: berth for {other} has no route")
                continue
            if route in existing:
                continue
            kit, half_len, half_beam, keel = BOATS[berth["boat"]]
            s = dock.side(berth)
            along = float(berth["along"])
            if not half_len <= along <= dock.length - 0.5:
                problems.append(f"{dock.id}: berth for {other} runs off the pier (along {along})")
            centre = dock.at(along, s * (dock.width / 2 + CLEARANCE + half_beam))
            for t in (-half_len, 0.0, half_len):
                for c in (-half_beam, 0.0, half_beam):
                    p = centre + dock.u * t + dock.n * c
                    inside(dock, p, f"the boat for {other}")
                    if not dock.spec.get("shallow") and ground(*p) > dock.water - keel - 0.2:
                        problems.append(f"{dock.id}: the boat for {other} would ground ({ground(*p):.2f} m under "
                                        f"its hull, keel {keel} m)")
                        break
                else:
                    continue
                break
            # 1 m off the centreline toward the boat, as the hand-authored ferry's (the deck edges carry railings)
            gangway = dock.at(along, s * 1.0)
            landing = dock.at(along - LANDING_BACK, s * 1.0)
            banner = dock.at(along + 3.0, s * (dock.width / 2 - 0.35))
            if math.dist(gangway, landing) > LANDING_REACH - 1:
                problems.append(f"{dock.id}: the landing from {other} is too far from its boat")
            for point, what in ((gangway, "gangway"), (landing, "landing")):
                if any(math.dist(point, q) < 1.5 for q in taken):
                    problems.append(f"{dock.id}: the {what} for {other} crowds another marker")
                taken.append(point)
            far = docks[other]
            boat_id = f"{dock.map}--obj-boat-{other}"
            landing_id = f"{dock.map}--boat-landing-{other}"
            out["assets"].append({
                "name": f"BN {labels[dock.id]} Boat To {labels[other]}", "kit": kit,
                "id": f"boatnet-{dock.id}-boat-{other}", "dock": dock.id,
                "transform": transform(yaw_rows(dock.u), (centre[0], dock.water, centre[1])),
                "note": f"the boat bound for {labels[other]}, moored on the pier's {berth['side']} side, bow seaward, "
                        f"waterline origin at the water level"})
            out["assets"].append({
                "name": f"BN {labels[dock.id]} Banner For {labels[other]}", "kit": BANNER,
                "id": f"boatnet-{dock.id}-banner-{other}", "dock": dock.id,
                # the flag (+Z) faces the boat
                "transform": transform(yaw_rows((s * dock.n[1], -s * dock.n[0])), (banner[0], dock.deck, banner[1])),
                "note": f"marks the berth of the boat bound for {labels[other]}"})
            out["markers"].append({
                "id": boat_id, "parent": "Gameplay/Interactives", "kind": "interactive", "dock": dock.id,
                "label": f"Boat to {labels[other]}", "position": (gangway[0], dock.deck, gangway[1]),
                "extras": {"authority": "server", "name": f"Boat to {labels[other]}", "type": "portal",
                           "destination": far.map, "landing": f"{far.map}--boat-landing-{dock.id}",
                           "returnBy": f"{far.map}--obj-boat-{dock.id}"}})
            out["markers"].append({
                "id": landing_id, "parent": "RuntimePoints/TerritoryPoints", "kind": "runtime_point", "dock": dock.id,
                "label": f"Boat landing (from {labels[other]})", "position": (landing[0], dock.deck, landing[1]),
                "extras": {"role": "boat-landing", "insideOwnership": True, "boat": boat_id,
                           "note": f"where the boat from {labels[other]} sets passengers down, {LANDING_BACK:g} m "
                                   f"shoreward of the gangway of the boat that sails back ({boat_id})"}})
            out["rows"][boat_id] = {
                "dock": dock.id, "other": other,
                "text": f"Bound for {labels[other]}. {spec['wording'][berth['boat']].format(here=labels[dock.id], there=labels[other])}",
                "portal": {"destinationMap": far.map, "oneWay": True, "landingMarker": f"{far.map}--boat-landing-{dock.id}",
                           "returnBy": f"{far.map}--obj-boat-{dock.id}"}}
    for (a, b), ids in existing.items():
        for here, there in ((a, b), (b, a)):
            dock = docks[here]
            per_map.setdefault(dock.map, {"assets": [], "markers": [], "bridges": [], "rows": {}})["rows"][ids[here]] = {
                "dock": here, "other": there, "existing": True,
                "text": f"Bound for {labels[there]}. "
                        f"{spec['wording']['ferry'].format(here=labels[here], there=labels[there])}"}
    return per_map, problems


# --- scene edits ----------------------------------------------------------------------------------------------------

def ext_id(text: RC.SceneText, path: str, preferred: str) -> str:
    for block in text.blocks:
        header = block.split("\n", 1)[0]
        if header.startswith("[ext_resource ") and f'path="{path}"' in header:
            return re.search(r' id="([^"]+)"', header).group(1)
    kind = "Script" if path.endswith(".gd") else "PackedScene"
    block = f'[ext_resource type="{kind}" path="{path}" id="{preferred}"]\n\n'
    last = max((i for i, b in enumerate(text.blocks) if b.startswith("[ext_resource ")), default=0)
    text.blocks.insert(last + 1, block)
    text.index()
    return preferred


def surfaces(text: RC.SceneText, donor: RC.SceneText, territories) -> tuple[str, str]:
    """The deck and support surfaces for a new pier: copies of the donor jetty's, made once per scene."""
    node = donor.blocks[donor.node_at["Bridges/" + DONOR[1]]]
    ids = []
    for role in ("deck_surface", "support_surface"):
        source = re.search(rf'(?m)^{role} = SubResource\("([^"]+)"\)', node).group(1)
        resource = next(b for b in donor.blocks if b.startswith("[sub_resource ") and f' id="{source}"' in b.split("\n", 1)[0])
        material_id = re.search(r'source_material = SubResource\("([^"]+)"\)', resource).group(1)
        material = next(b for b in donor.blocks if b.startswith("[sub_resource ") and f' id="{material_id}"' in b.split("\n", 1)[0])
        new_material, new_resource = f"bn_{role}_material", f"bn_{role}"
        if new_resource not in text.resource_ids:
            surface_script = ext_id(text, SCRIPTS["surface"], "bn_surface_script")
            m = material.replace(f' id="{material_id}"', f' id="{new_material}"', 1)
            r = resource.replace(f' id="{source}"', f' id="{new_resource}"', 1)
            r = re.sub(r'script = ExtResource\("[^"]+"\)', f'script = ExtResource("{surface_script}")', r)
            r = r.replace(f'SubResource("{material_id}")', f'SubResource("{new_material}")')
            first_node = min(i for i, b in enumerate(text.blocks) if b.startswith("[node "))
            text.blocks[first_node:first_node] = [m if m.endswith("\n\n") else m.rstrip("\n") + "\n\n",
                                                  r if r.endswith("\n\n") else r.rstrip("\n") + "\n\n"]
            text.index()
        ids.append(new_resource)
    return ids[0], ids[1]


def strip_generation(text: RC.SceneText) -> int:
    """Remove the previous generation (nodes tagged boatNetwork) and the bn_ resources nothing uses any more."""
    markers = 0
    drop = set()
    for path, i in text.node_at.items():
        if path.count("/") >= 1 and f'"{TAG}": "' in text.blocks[i] and path.rsplit("/", 1)[0] in (
                "AuthoredAssets", "Bridges", "Gameplay/Interactives", "RuntimePoints/TerritoryPoints"):
            drop.update(text.subtree(path))
            markers += path.startswith(("Gameplay/", "RuntimePoints/"))
    text.blocks = [b for i, b in enumerate(text.blocks) if i not in drop]
    while True:
        # a node's header can use a resource (instance=ExtResource); a resource's own header names only itself
        used = {rid for b in text.blocks
                for _, rid in RC.REF.findall(b if b.startswith("[node ") else (b.split("\n", 1)[1] if "\n" in b else ""))}
        unused = {i for i, b in enumerate(text.blocks) if b.startswith(("[ext_resource ", "[sub_resource "))
                  and (rid := re.search(r' id="([^"]+)"', b.split("\n", 1)[0]).group(1)).startswith("bn_")
                  and rid not in used}
        if not unused:
            break
        text.blocks = [b for i, b in enumerate(text.blocks) if i not in unused]
    text.index()
    return markers


def dict_text(values: dict) -> str:
    lines = []
    for key, value in values.items():
        lines.append(f'"{key}": {json.dumps(value, ensure_ascii=False)}')
    return "{\n" + ",\n".join(lines) + "\n}"


def write_scene(text: RC.SceneText, plan_map: dict, donor: RC.SceneText, territory, object_ids: dict, approval: str):
    """Add the plan's nodes to a scene the previous generation has already been stripped from."""
    tx, tz = territory.translation[0], territory.translation[2]
    asset_script = ext_id(text, SCRIPTS["asset"], "bn_asset_script")
    marker_script = ext_id(text, SCRIPTS["marker"], "bn_marker_script")
    blocks = []
    for dock in plan_map["bridges"]:
        deck, support = surfaces(text, donor, None)
        bridge_script = ext_id(text, SCRIPTS["bridge"], "bn_bridge_script")
        name = f"boatnet-{dock.id}-pier"
        meta = {TAG: dock.id, "approval": approval, "deck": f"{dock.spec.get('label') or territory.label} pier",
                "inside_ownership": True, "note": dock.spec.get("note", ""), "type": "pier"}
        blocks.append(f'[node name="{name}" type="Node3D" parent="Bridges"]\nscript = ExtResource("{bridge_script}")\n'
                      f'bridge_id = "{name}"\nmetadata = {dict_text(meta)}\nwidth = {fmt(dock.width)}\narch = 0\n'
                      f'water_clearance = 0.85\ndeck_surface = SubResource("{deck}")\nsupport_surface = SubResource("{support}")\n'
                      f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)\n\n')
        for end, point in (("Start", dock.start), ("End", dock.end)):
            blocks.append(f'[node name="{end}" type="Marker3D" parent="Bridges/{name}"]\n'
                          f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {fmt(point[0] - tx)}, {fmt(dock.deck)}, '
                          f'{fmt(point[1] - tz)})\n\n')
    for asset in plan_map["assets"]:
        glb = KIT + asset["kit"] + ".glb"
        glb_id = ext_id(text, glb, "bn_" + asset["kit"].replace("-", "_"))
        local = re.sub(r"^(Transform3D\((?:[^,]+, ){9})([^,]+), ([^,]+), ([^)]+)\)$",
                       lambda m: f"{m.group(1)}{fmt(float(m.group(2)) - tx)}, {m.group(3)}, {fmt(float(m.group(4)) - tz)})",
                       asset["transform"])
        meta = {TAG: asset["dock"], "note": asset["note"]}
        blocks.append(f'[node name="{asset["name"]}" type="Node3D" parent="AuthoredAssets"]\n'
                      f'script = ExtResource("{asset_script}")\nasset_id = "{asset["id"]}"\n'
                      f'node_name = "Authored_{asset["id"].replace("-", "_")}"\n'
                      f'catalog_asset_id = "tollholms:{asset["kit"]}"\nscene_path = "{glb}"\n'
                      f'collision_role = "{"none" if asset["kit"] in (BANNER,) else "solid"}"\n'
                      f'metadata = {dict_text(meta)}\nmetadata/map_authoring_asset_wrapper = true\ntransform = {local}\n\n')
        blocks.append(f'[node name="Content" parent="AuthoredAssets/{asset["name"]}" instance=ExtResource("{glb_id}")]\n'
                      f'metadata/map_asset_id = "tollholms:{asset["kit"]}"\nmetadata/map_asset_scene = "{glb}"\n\n')
    added = 0
    for marker in plan_map["markers"]:
        extras = {**marker["extras"], TAG: marker["dock"]}
        if marker["kind"] == "interactive":
            extras = {"authority": "server", "name": extras["name"], "objectId": object_ids[marker["id"]],
                      **{k: v for k, v in extras.items() if k not in ("authority", "name")}}
        x, y, z = marker["position"]
        blocks.append(f'[node name="{marker["id"]}" type="Marker3D" parent="{marker["parent"]}"]\ngizmo_extents = 0.8\n'
                      f'script = ExtResource("{marker_script}")\nrecord_id = "{marker["id"]}"\nkind = "{marker["kind"]}"\n'
                      f'label = "{marker["label"]}"\nextras = {dict_text(extras)}\n'
                      f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {fmt(x - tx)}, {fmt(y)}, {fmt(z - tz)})\n\n')
        added += 1
    if blocks:
        if not text.blocks[-1].endswith("\n\n"):
            text.blocks[-1] = text.blocks[-1].rstrip("\n") + "\n\n"
        text.blocks.extend(blocks)
        text.blocks[-1] = text.blocks[-1].rstrip("\n") + "\n"
    text.index()
    return added


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--plan", action="store_true", help="print the plan and its problems; write nothing")
    parser.add_argument("--spec", type=Path, default=SPEC, help="the network spec (default: content/boat-network.json)")
    args = parser.parse_args(argv)
    spec, territories, ground, docks = load(args.spec)
    per_map, problems = plan(spec, docks, ground, territories)
    if args.plan or problems:
        summary = {m: {"assets": len(p["assets"]), "markers": len(p["markers"]), "piers": len(p["bridges"]),
                       "rows": sorted(p["rows"])} for m, p in sorted(per_map.items())}
        print(json.dumps({"maps": summary, "problems": problems}, indent=1))
        if problems:
            return 1
        if args.plan:
            return 0
    rows = read(ROWS)
    outputs = {}
    donor = RC.SceneText(territories[DONOR[0]].scene.path)
    for map_id, p in sorted(per_map.items()):
        territory = territories[map_id]
        table = rows["maps"].setdefault(map_id, {"npcs": {}, "interactives": {}})["interactives"]
        # the previous generation: every boat row but the hand-authored ones the spec keeps
        keep = {k for k, v in p["rows"].items() if v.get("existing")}
        generated = {k for k in table if "--obj-boat-" in k and k not in keep}
        scene = RC.SceneText(territory.scene.path)
        removed = strip_generation(scene)
        used = {int(v["objectId"]) for k, v in table.items() if k not in generated and "objectId" in v}
        used |= {int(v) for v in re.findall(r'"objectId": (\d+)', scene.text())}
        object_ids, next_id = {}, FIRST_OBJECT_ID
        for boat_id in sorted(k for k, v in p["rows"].items() if not v.get("existing")):
            while next_id in used:
                next_id += 1
            object_ids[boat_id] = next_id
            used.add(next_id)
        for key in generated:
            del table[key]
        for boat_id, row in p["rows"].items():
            if row.get("existing"):
                table[boat_id]["text"] = row["text"]
                continue
            table[boat_id] = {"objectId": object_ids[boat_id], "role": "portal", "target": "maps.txt",
                              "text": row["text"], "portal": row["portal"], "source": spec["approval"]}
        if p["markers"] or p["assets"] or p["bridges"] or removed or scene.text() != scene.original:
            added = write_scene(scene, p, donor, territory, object_ids, spec["approval"])
            if scene.text() != scene.original:
                outputs[scene.path] = scene.text().encode("utf-8")
            spec_path = REGIONS / map_id / "region-authoring-spec.json"
            authoring = read(spec_path)
            gameplay = authoring["gameplay"]
            points = sum(1 for b in scene.blocks if b.startswith("[node ") and re.search(r'(?m)^kind = "runtime_point"', b))
            before = (gameplay.get("runtimePointCount"), gameplay.get("authoredMarkerCount"))
            gameplay["runtimePointCount"] = points
            if "authoredMarkerCount" in gameplay:
                gameplay["authoredMarkerCount"] += added - removed
            if before != (gameplay.get("runtimePointCount"), gameplay.get("authoredMarkerCount")):
                outputs[spec_path] = (json.dumps(authoring, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    rows_blob = (json.dumps(rows, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    if rows_blob != ROWS.read_bytes():
        outputs[ROWS] = rows_blob
    stale = [str(path.relative_to(CHECKOUT)) for path, blob in outputs.items() if path.read_bytes() != blob]
    if args.check:
        print(json.dumps({"stale": stale}, indent=1))
        return 1 if stale else 0
    for path, blob in outputs.items():
        path.write_bytes(blob)
    print(json.dumps({"written": stale}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
