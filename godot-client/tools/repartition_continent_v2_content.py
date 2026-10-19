#!/usr/bin/env python3
"""Move authored continent-v2 content across changed borders; retire, re-ground or keep what new ground meets.

    python godot-client/tools/repartition_continent_v2_content.py --plan            # survey, write the decisions
    python godot-client/tools/repartition_continent_v2_content.py --check           # refuse unless applied
    python godot-client/tools/repartition_continent_v2_content.py --apply

The decisions are recorded in the partition's plan-amendments.json ("sceneContent") so they can be reviewed:
  retire   node paths removed with their children (retired decks, their structures and the road pieces on them,
           water props stranded on new land, seabed rocks the new ground buries deeper than 3 m, mirrored patches
           whose other half is now the only one);
  reground top-level asset wrappers on new land that stood on a retired deck: their origin y drops to the ground;
  moves    are not recorded: every remaining positioned node (asset wrappers, markers, water regions, bridges,
           ground regions whose clip lies wholly in another map) belongs to the map that owns its continent position,
           and moves there with its children and the resources it uses, re-framed by the translation difference.
  merges   plan-amendments "mergedMaps" {retired: successor}: run while the retired map is still in the catalog.
           Every subtree of the retired scene under a structural node both scenes share (AuthoredAssets, Roads,
           Bridges, Ground/Regions, Gameplay/*, RuntimePoints/*, Terrain/Patches) moves into the successor. Road
           curves are re-framed point by point. The retired id is rewritten as a whole word in the moved blocks
           (marker, road and landmark ids: retired--x becomes successor--x), harvestable object ids that collide
           with the successor's are shifted past its highest, and its spawn rows and server rows fold into the
           successor's. Renamed marker ids are reported (--apply writes them to the merge record).
Scenes are edited as text, block by block; nothing else in a scene changes. --check rebuilds every edit in memory
and refuses unless the scenes already hold them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

import continent_v2_territories as T

CHECKOUT = T.CHECKOUT
SCRIPTS = "res://src/dev/map_authoring_region/"
POSITIONED = {"asset_control.gd", "gameplay_marker.gd", "water_region_control.gd"}
REF = re.compile(r'(ExtResource|SubResource)\("([^"\n]+)"\)')
DECK_STRUCTURE = re.compile(r"(Causeway Arch Span|causeway-support-span|causeway-joint-deck|^lv_b22l|^lv_b14bay)")
WATER_PROP = re.compile(r"(buoy|rowing-boat|Kelp)", re.I)
SEABED_ROCK = re.compile(r"(Coastal Boulders|Coastal Rock|Beach Rocks|Sea Stack)")
# road pieces that ran along a retired deck (B13's islet road, R32's piece on B14)
DECK_ROADS = {"saltsound--b13-ne-islet--0", "hearthcroft--r32-1--1"}


HARVEST_KIND = re.compile(r'(?m)^kind = "harvestable"')
IDENTITY = re.compile(r'(?m)^(record_id|asset_id|path_id|region_id|patch_id|bridge_id|transform) = ')


def word(old: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])")


def structural(block: str) -> bool:
    """A grouping node: no instance, no identity and no transform of its own."""
    return " instance=" not in block.split("\n", 1)[0] and not IDENTITY.search(block)


def merge_moves(src, dst):
    """The subtrees of a merged scene to move: those whose parent is a structural node the successor also has."""
    shared = {p for p, i in src.node_at.items()
              if p in dst.node_at and (p == "." or (structural(src.blocks[i]) and structural(dst.blocks[dst.node_at[p]])))}
    moves = []
    for path in sorted(src.node_at, key=lambda p: (p.count("/"), p)):
        if path in shared or any(path.startswith(m + "/") for m in moves):
            continue
        parent = path.rsplit("/", 1)[0] if "/" in path else "."
        if parent not in shared:
            raise ValueError(f"{src.path.name}:{path} has no place in {dst.path.name}")
        moves.append(path)
    return moves


def harvest_ids(text) -> list[int]:
    return [int(v) for b in text.blocks if HARVEST_KIND.search(b) for v in re.findall(r'"objectId": (\d+)', b)]


def shift_curve(block: str, dx: float, dz: float) -> str:
    """Re-frame a Curve3D: its points are (in, out, position) triples; only positions move."""
    match = re.search(r'"points": PackedVector3Array\(([^)]*)\)', block)
    values = [v.strip() for v in match.group(1).split(",")]
    if len(values) % 9:
        raise ValueError("a Curve3D point list is not (in, out, position) triples")
    for k in range(0, len(values), 9):
        values[k + 6] = format(round(float(values[k + 6]) + dx, 4), ".10g")
        values[k + 8] = format(round(float(values[k + 8]) + dz, 4), ".10g")
    return block[:match.start(1)] + ", ".join(values) + block[match.end(1):]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class SceneText:
    """A .tscn as blocks; node blocks addressed by their node path."""

    def __init__(self, path: Path):
        self.path = path
        self.original = path.read_bytes().decode("utf-8")
        self.blocks = re.split(r"(?m)(?=^\[)", self.original)
        self.index()

    def index(self):
        self.node_at = {}
        self.resource_ids = set()
        for i, block in enumerate(self.blocks):
            header = block.split("\n", 1)[0]
            if header.startswith("[node "):
                name = re.search(r'name="((?:[^"\\]|\\.)*)"', header).group(1)
                parent = re.search(r'parent="((?:[^"\\]|\\.)*)"', header)
                path = "." if parent is None else name if parent.group(1) == "." else parent.group(1) + "/" + name
                self.node_at[path] = i
            elif header.startswith(("[ext_resource ", "[sub_resource ")):
                self.resource_ids.add(re.search(r' id="([^"]+)"', header).group(1))

    def subtree(self, path):
        return [i for p, i in self.node_at.items() if p == path or p.startswith(path + "/")]

    def text(self):
        return "".join(self.blocks)


def transform_origin_set(block, x=None, y=None, z=None, add=(0.0, 0.0, 0.0)):
    match = re.search(r"(?m)^transform = Transform3D\(([^)]*)\)$", block)
    values = [v.strip() for v in match.group(1).split(",")]
    for k, v in ((9, x), (10, y), (11, z)):
        if v is not None:
            values[k] = format(v, ".10g")
    for k, d in zip((9, 10, 11), add):
        if d:
            values[k] = format(float(values[k]) + d, ".10g")
    return block[:match.start(1)] + ", ".join(values) + block[match.end(1):]


def ground_sampler(meta):
    prov = read(meta / "group-terrain-v2/terrain-provenance.json")
    w, h = prov["grid"]["gridSize"]; first = np.asarray(prov["grid"]["continentFirstVertex"], float)
    heights = np.fromfile(meta / "group-terrain-v2/base-heights.f32le", "<f4").reshape(h, w)
    v1prov = read(meta / "group-terrain/terrain-provenance.json")
    w1, h1 = v1prov["grid"]["gridSize"]; first1 = np.asarray(v1prov["grid"]["continentFirstVertex"], float)
    v1 = np.fromfile(meta / "group-terrain/base-heights.f32le", "<f4").reshape(h1, w1)

    def sample(grid, origin, x, z):
        fx, fz = (np.array([x, z]) - origin) / 2.0
        c, r = int(np.floor(fx)), int(np.floor(fz))
        if not (0 <= r < grid.shape[0] - 1 and 0 <= c < grid.shape[1] - 1):
            return None
        tx, tz = fx - c, fz - r
        h00, h10 = grid[r, c:c + 2]; h01, h11 = grid[r + 1, c:c + 2]
        if tx + tz <= 1:
            return float(h00 + (h10 - h00) * tx + (h01 - h00) * tz)
        return float(h11 + (h01 - h11) * (1 - tx) + (h10 - h11) * (1 - tz))
    return (lambda x, z: sample(heights, first, x, z)), (lambda x, z: sample(v1, first1, x, z))


def survey(territories, partition, amend):
    """Propose the recorded decisions: retire and reground lists."""
    meta = partition.parent
    plan = read(meta / "partition-inputs/source-plan.json")
    retired_decks = {d["id"]: LineString(d["approvedPolyline"]) for d in plan["approvedDecks"]
                     if d["id"] in amend.get("retireDecks", {})}
    ground, ground_v1 = ground_sampler(meta)
    owners = amend["patchOwners"]
    retire, reground = {}, {}
    for t in territories:
        for path, n in t.scene.nodes.items():
            script = t.scene.script_of(n).rsplit("/", 1)[-1] if t.scene.script_of(n) else ""
            name = path.rsplit("/", 1)[-1]
            if script == "bridge_control.gd":
                bridge_id = json.loads(n.properties.get("bridge_id", '""'))
                if re.match(r"(b13|b14|b22|b24)-|knob-quay-01$", bridge_id) or bridge_id == "b14-bay":
                    retire[f"{t.id}:{path}"] = f"retired deck {bridge_id}"
                continue
            if script == "path_control.gd" and n.attributes.get("parent") == "Roads":
                if json.loads(n.properties.get("path_id", '""')) in DECK_ROADS:
                    retire[f"{t.id}:{path}"] = "road piece on a retired deck"
                continue
            if script == "terrain_patch.gd":
                patch = json.loads(n.properties.get("patch_id", '""'))
                if t.id not in owners.get(patch, [t.id]):
                    retire[f"{t.id}:{path}"] = f"patch {patch} now belongs to {owners[patch]}"
                continue
            if script != "asset_control.gd" or n.attributes.get("parent") != "AuthoredAssets":
                continue
            m = t.scene.world(path)
            x, y, z = m[0, 3] + t.translation[0], m[1, 3], m[2, 3] + t.translation[2]
            p = Point(x, z)
            near_deck = any(d.distance(p) < 14 for d in retired_decks.values())
            g2, g1 = ground(x, z), ground_v1(x, z)
            new_land = g2 is not None and g2 > 0 and (g1 is None or g1 <= 0)
            if near_deck and DECK_STRUCTURE.search(name):
                retire[f"{t.id}:{path}"] = "structure of a retired deck"
            elif new_land and WATER_PROP.search(name):
                retire[f"{t.id}:{path}"] = "water prop stranded on new land"
            elif new_land and SEABED_ROCK.search(name) and y < g2 - 3.0:
                retire[f"{t.id}:{path}"] = f"seabed rock buried {g2 - y:.1f} m by new ground"
            elif new_land and y > g2 + 0.5:
                reground[f"{t.id}:{path}"] = round(g2, 3)
            elif g2 is not None and g1 is not None and g2 < g1 - 1.0 and y > g2 + 1.0:
                # ground v2 sank this ground (the north-east stub): its props would hang over the sea
                retire[f"{t.id}:{path}"] = f"prop on ground sunk {g1 - g2:.1f} m by ground v2"
    return {"retire": dict(sorted(retire.items())), "reground": dict(sorted(reground.items()))}


def build(territories, spec, amend):
    shapes = [(s["mapId"], unary_union([Polygon(r) for r in s["ownershipPolygons"]])) for s in spec["sections"]]

    def owner(x, z):
        point = Point(x, z)
        return next((rid for rid, shape in shapes if shape.covers(point)), None)

    content = amend["sceneContent"]
    texts = {t.id: SceneText(t.scene.path) for t in territories}
    by_id = {t.id: t for t in territories}
    report = {"retired": 0, "regrounded": 0, "moved": {}}
    # 1. retire (removed at once, per scene, so later edits index the remaining blocks)
    retired_paths = {}
    merged = amend.get("mergedMaps", {})
    for key in content["retire"]:
        rid, path = key.split(":", 1)
        if rid not in texts and rid in merged:
            continue
        retired_paths.setdefault(rid, set()).add(path)
    for rid, paths in retired_paths.items():
        text = texts[rid]
        drop = {i for path in paths if path in text.node_at for i in text.subtree(path)}
        text.blocks = [b for i, b in enumerate(text.blocks) if i not in drop]
        text.index()
    # 2. reground (transform y of a top-level asset wrapper)
    for key, y in content["reground"].items():
        rid, path = key.split(":", 1)
        if rid not in texts and rid in merged:
            continue
        text = texts[rid]; i = text.node_at[path]
        text.blocks[i] = transform_origin_set(text.blocks[i], y=y)
        report["regrounded"] += 1
    # 3. moves: positioned top-level nodes owned elsewhere; a merged map's whole content
    moves = []
    offsets = {}
    report["renamedMarkers"] = {}
    for src_id, dst_id in merged.items():
        if src_id not in texts:
            continue
        have, mine = harvest_ids(texts[dst_id]), harvest_ids(texts[src_id])
        every = {int(v) for v in re.findall(r'"objectId": (\d+)', texts[dst_id].text())}
        offset = max(have) + 1 - min(mine) if have and mine and set(have) & set(mine) else 0
        if every & {v + offset for v in mine}:
            raise ValueError(f"{src_id}: its harvestable object ids would collide in {dst_id}")
        offsets[src_id] = offset
        moves += [(src_id, path, dst_id) for path in merge_moves(texts[src_id], texts[dst_id])]
    for t in territories:
        if t.id in merged:
            continue
        text = texts[t.id]
        for path, n in t.scene.nodes.items():
            if path.count("/") != 1 and not path.startswith(("Gameplay/", "RuntimePoints/", "Ground/Regions/")):
                continue
            if path not in text.node_at or path in retired_paths.get(t.id, ()):
                continue
            script = t.scene.script_of(n).rsplit("/", 1)[-1] if t.scene.script_of(n) else ""
            if script == "asset_control.gd" and n.attributes.get("parent") != "AuthoredAssets":
                continue
            if script in POSITIONED:
                m = t.scene.world(path); x, z = m[0, 3] + t.translation[0], m[2, 3] + t.translation[2]
            elif script == "bridge_control.gd":
                ends = [t.scene.world(path + "/" + c)[[0, 2], 3] + t.translation[[0, 2]] for c in ("Start", "End")]
                x, z = np.mean(ends, axis=0)
            elif script == "ground_region_control.gd" and path.startswith("Ground/Regions/"):
                clip = n.properties.get("clip_polygon")
                if not clip:
                    continue
                ring = np.asarray(T._numbers(clip, "PackedVector2Array")).reshape(-1, 2)
                m = t.scene.world(path); basis = m[np.ix_([0, 2], [0, 2])]
                world = ring @ basis.T + m[[0, 2], 3] + t.translation[[0, 2]]
                poly = Polygon(world)
                mine = dict(shapes)[t.id]
                if poly.intersection(mine).area > 1e-3:
                    continue
                c = poly.representative_point(); x, z = c.x, c.y
            else:
                continue
            target = owner(x, z)
            if target is None:
                raise ValueError(f"{t.id}:{path} lies outside every section")
            if target != t.id:
                moves.append((t.id, path, target))
    for src, path, dst in moves:
        s, d = texts[src], texts[dst]
        indices = sorted(s.subtree(path))
        blocks = [s.blocks[i] for i in indices]
        delta = by_id[src].translation - by_id[dst].translation
        if src in merged:
            # the successor's ids: retired--x becomes successor--x; colliding harvestables shift past its highest
            offset = offsets[src]
            retag = word(src)
            harvest = bool(HARVEST_KIND.search(blocks[0]))

            def renumber(text):
                if not (offset and harvest):
                    return text
                text = re.sub(r'(--harvest-)(\d+)(?=-)', lambda m: f"{m.group(1)}{int(m.group(2)) + offset}", text)
                return re.sub(r'("objectId": )(\d+)', lambda m: f"{m.group(1)}{int(m.group(2)) + offset}", text)
            renamed = [renumber(retag.sub(dst, b)) for b in blocks]
            for before, after in zip(blocks, renamed):
                old = re.search(r'(?m)^record_id = "([^"]+)"', before)
                new = re.search(r'(?m)^record_id = "([^"]+)"', after)
                if old and old.group(1) != new.group(1):
                    report["renamedMarkers"][old.group(1)] = new.group(1)
            blocks = renamed
            path = (path.rsplit("/", 1)[0] + "/" if "/" in path else "") + \
                re.search(r'name="((?:[^"\\]|\\.)*)"', blocks[0].split("\n", 1)[0]).group(1)
        prefix = f"a3_{src}_"
        # resources the moved blocks use, recursively
        needed, pending = set(), [rid for b in blocks for _, rid in REF.findall(b)]
        resources = {}
        for i, block in enumerate(s.blocks):
            header = block.split("\n", 1)[0]
            if header.startswith(("[ext_resource ", "[sub_resource ")):
                resources[re.search(r' id="([^"]+)"', header).group(1)] = block
        while pending:
            rid = pending.pop()
            if rid in needed:
                continue
            needed.add(rid)
            pending += [r for _, r in REF.findall(resources[rid])]

        def rename(text):
            return REF.sub(lambda m: f'{m.group(1)}("{prefix}{m.group(2)}")' if m.group(2) in needed else m.group(0), text)
        new_resources = []
        for rid in sorted(needed, key=lambda r: not resources[r].startswith("[ext_resource")):
            if prefix + rid in d.resource_ids:
                continue
            block = resources[rid].replace(f' id="{rid}"', f' id="{prefix}{rid}"', 1)
            new_resources.append(rename(block))
            d.resource_ids.add(prefix + rid)
        top = indices[0]
        name = path.rsplit("/", 1)[-1]
        parent = path.rsplit("/", 1)[0] if "/" in path else "."
        taken = set(d.node_at)
        new_name = name
        while (new_name if parent == "." else f"{parent}/{new_name}") in taken:
            new_name += "-a3"
        asset_ids = set(re.findall(r'(?m)^asset_id = "([^"]*)"', "".join(d.blocks)))
        moved = []
        for i, block in zip(indices, blocks):
            block = rename(re.sub(r' unique_id=\d+', '', block, count=1))
            if i == top:
                block = block.replace(f'name="{name}"', f'name="{new_name}"', 1)
                aid = re.search(r'(?m)^asset_id = "([^"]*)"', block)
                if aid and aid.group(1) in asset_ids:
                    block = block.replace(aid.group(0), f'asset_id = "{aid.group(1)}-a3"', 1)
                if re.search(r"(?m)^transform = Transform3D\(", block):
                    block = transform_origin_set(block, add=(float(delta[0]), 0.0, float(delta[2])))
                elif re.search(r'(?m)^curve = SubResource\("([^"]+)"\)', block):
                    curve = re.search(r'(?m)^curve = SubResource\("([^"]+)"\)', block).group(1)
                    at = next(k for k, b in enumerate(new_resources) if f' id="{curve}"' in b.split("\n", 1)[0])
                    new_resources[at] = shift_curve(new_resources[at], float(delta[0]), float(delta[2]))
                else:
                    raise ValueError(f"{src}:{path}: a moved node needs an explicit transform")
            elif new_name != name:
                old_parent = f"{parent}/{name}" if parent != "." else name
                new_parent = f"{parent}/{new_name}" if parent != "." else new_name
                block = re.sub(r'parent="' + re.escape(old_parent) + r'(?=["/])', 'parent="' + new_parent, block, count=1)
            moved.append(block if block.endswith("\n\n") else block.rstrip("\n") + "\n\n")
        # out of the source first, then into the destination; both re-indexed before the next move
        gone = set(indices)
        s.blocks = [b for i, b in enumerate(s.blocks) if i not in gone]
        s.index()
        # Godot lists every ext_resource before any sub_resource: each kind joins the end of its own run
        first_node = min(d.node_at.values())
        subs = [b for b in new_resources if b.startswith("[sub_resource ")]
        exts = [b for b in new_resources if b.startswith("[ext_resource ")]
        d.blocks[first_node:first_node] = subs
        last_ext = max((i for i, b in enumerate(d.blocks[:first_node]) if b.startswith("[ext_resource ")), default=0)
        d.blocks[last_ext + 1:last_ext + 1] = exts
        d.blocks.extend(moved)
        d.index()
        report["moved"].setdefault(f"{src}->{dst}", 0)
        report["moved"][f"{src}->{dst}"] += 1
    report["retired"] = len(content["retire"])
    return texts, report


def content_tables(territories, spec, merged=None):
    """The per-map content files follow the same rule: spawn rows move to the map owning their continent position
    (local re-framed by the translation difference, their source record carried); a new map gets an empty spawns
    table and empty server rows. Returns {path: bytes} for the files that change."""
    shapes = [(s["mapId"], unary_union([Polygon(r) for r in s["ownershipPolygons"]])) for s in spec["sections"]]

    def owner(x, z):
        point = Point(x, z)
        return next((rid for rid, shape in shapes if shape.covers(point)), None)
    root = CHECKOUT / "eloria-assets/maps/continent-v2"
    by_id = {t.id: t for t in territories}
    tables = {}
    for t in territories:
        path = root / t.id / "content/spawns.json"
        tables[t.id] = read(path) if path.exists() else {
            "schema": "eloria-continent-v2-spawns-v1", "map": t.id,
            "about": "Pinned original spawn rows, partitioned by exact continent position. local remains the source "
                     "of truth.", "source": {"originalSources": {}}, "spawns": []}
    original = {rid: json.dumps(table, sort_keys=True) for rid, table in tables.items()}
    for rid, table in tables.items():
        keep = []
        for row in table["spawns"]:
            tx, tz = by_id[rid].translation[[0, 2]]
            x, z = row["local"][0] + tx, row["local"][1] + tz
            target = owner(x, z)
            if target is None:
                raise ValueError(f"{rid}: spawn row {row['id']} lies outside every section")
            if target == rid:
                keep.append(row)
                continue
            moved = dict(row)
            dx, dz = by_id[target].translation[[0, 2]]
            moved["local"] = [x - dx, z - dz]
            tables[target]["spawns"].append(moved)
            sources = table.get("source", {}).get("originalSources", {})
            tables[target].setdefault("source", {}).setdefault("originalSources", {}).update(
                {k: v for k, v in sources.items() if k not in tables[target]["source"]["originalSources"]})
        table["spawns"] = keep
    out = {}
    for rid, table in tables.items():
        if json.dumps(table, sort_keys=True) != original[rid] or not (root / rid / "content/spawns.json").exists():
            out[root / rid / "content/spawns.json"] = (json.dumps(table, indent=1, ensure_ascii=False) + "\n").encode()
    rows_path = root / "_continent_v2/content/server-rows.json"
    rows = read(rows_path)
    folded = [rid for rid in (merged or {}) if rid in rows["maps"]]
    for rid in folded:
        # a merged map's server rows join its successor's (none may collide)
        for kind, items in rows["maps"].pop(rid).items():
            target = rows["maps"].setdefault(merged[rid], {}).setdefault(kind, {})
            if set(items) & set(target):
                raise ValueError(f"{rid}: server {kind} rows collide in {merged[rid]}")
            target.update(items)
    missing = [t.id for t in territories if t.id not in rows["maps"] and t.id not in (merged or {})]
    if missing or folded:
        for rid in missing:
            rows["maps"][rid] = {"npcs": {}, "interactives": {}}
        rows["maps"] = dict(sorted(rows["maps"].items()))
        out[rows_path] = (json.dumps(rows, indent=1, ensure_ascii=False) + "\n").encode()
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    catalog = read(T.CATALOG)
    spec_path = T.res_to_path(catalog["partitionSpecPath"])
    partition = spec_path.parent
    spec = read(spec_path)
    amend_path = partition / "plan-amendments.json"
    amend = read(amend_path)
    territories = T.load_territories()
    if args.plan:
        proposal = survey(territories, partition, amend)
        recorded = amend.get("sceneContent") or {}
        # applied decisions leave the scenes, so a later survey finds only new ones: add those to the record,
        # never drop or change a recorded decision
        added = {k: sorted(set(proposal[k]) - set(recorded.get(k, {}))) for k in proposal}
        amend["sceneContent"] = {k: dict(sorted({**proposal[k], **recorded.get(k, {})}.items())) for k in proposal}
        print(json.dumps({"added": {k: len(v) for k, v in added.items()}}, indent=1))
        amend_path.write_text(json.dumps(amend, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({k: len(v) for k, v in amend["sceneContent"].items()}, indent=1))
        return 0
    texts, report = build(territories, spec, amend)
    changed = [t for t in texts.values() if t.text() != t.original]
    files = content_tables(territories, spec, amend.get("mergedMaps"))
    if args.check:
        print(json.dumps({"pending": [t.path.name for t in changed] + [str(p.relative_to(CHECKOUT)) for p in files],
                          **report}, indent=1))
        return 1 if changed or files else 0
    for t in changed:
        t.path.write_bytes(t.text().encode("utf-8"))
    for path, raw in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    print(json.dumps({"written": [t.path.name for t in changed] + [str(p.relative_to(CHECKOUT)) for p in files],
                      **report}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
