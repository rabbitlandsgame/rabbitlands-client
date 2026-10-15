"""_continent_v2/publish_server.py end to end, on a fixture client checkout and a fixture server tree.

The client fixture is two isles, "landfall" and "tollholm", on test_export_collision's shared terrain (flat ground at
10 m, a blocked lake on landfall, and a plateau at 104.8 m on tollholm that no walker reaches), meeting along
continent x 100, which a road crosses. It has everything frames.py and the publisher read: the catalog, the stubs,
the authoring specs, the registry rows, the bakes (with their markers: the arrival, two home points, the desk and
the ferry, two harvest nodes, the five re-homed people and one new one, Signed Ashore's twelve targets and a quest
post), the packages export_collision.py wrote (and their manifests), the content tables and crossings_v2.py's
crossings.json. The server fixture is a copy of the server checkout named by ELORIA_SERVER_ROOT (its code, its base
tables, Crownwater's vendored grid and the vendored manifest) whose generate_nymara_maps.py registers the two
fixture isles, as the server workflow will before the real --apply. The copy is the tree the serve plan's stages
start from, whichever stage the checkout has reached: it leaves out M2's eloria/landing.py and M3's eloria/home.py
(chapter_code adds a stand-in for the first), and takes M1's publication of the isles back out of the copied content
and collision manifests. Each test runs the publisher as a command, the way it is run for real, so the server's own
sync vendors the grids.

Without ELORIA_SERVER_ROOT these tests skip.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TESTS))
import frames as F  # noqa: E402
import export_collision as X  # noqa: E402
import publish_server as P  # noqa: E402

SERVER = os.environ.get("ELORIA_SERVER_ROOT")
pytestmark = pytest.mark.skipif(not SERVER, reason="set ELORIA_SERVER_ROOT to a server checkout with "
                                                   "eloria/served_grid.py and eloria/content_overlay.py")
CELLS = 72
SW = F.Frame("landfall", "Landfall", (34, 34), (CELLS, CELLS), (70.0, 0.0, 30.0))
TH = F.Frame("tollholm", "The Tollholms", (34, 34), (CELLS, CELLS), (130.0, 0.0, 30.0))
POLYGONS = {"landfall": [[40.0, 0.0], [100.0, 0.0], [100.0, 60.0], [40.0, 60.0]],
            "tollholm": [[100.0, 0.0], [160.0, 0.0], [160.0, 60.0], [100.0, 60.0]]}
FRAMES = {"landfall": SW, "tollholm": TH}
V2 = "eloria-assets/maps/continent-v2"
REHOMED = {"Gate Warden Ilyon": ("guide", 308), "Wayfinder Nesh": ("tutorial", 307),
           "Ferryman Caldus": ("dialogue", 310), "Register Clerk Hemmen": ("dialogue", 312),
           "Bettany Orl": ("shop", 303)}
TARGETS = P.LANDING_TARGETS
LAKE = (50.5, 45.5)                 # inside test_export_collision's lake: blocked
PLATEAU = (148.5, 10.5)             # on the 104.8 m plateau: open, never reached


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8", newline="\n")


def local(frame, gx, gz):
    return [gx - frame.translation[0], 10.0, gz - frame.translation[2]]


def record(frame, identity, gx, gz, **extra):
    position = local(frame, gx, gz)
    return {"id": identity, "position": position, "serverTile": list(frame.tile(position[0], position[2])), **extra}


def transform(frame):
    return {"metresPerTile": 1.0, "serverOrigin": list(frame.origin), "serverCells": list(frame.cells),
            "origin": [0, 0, 0], "invertServerY": True, "serverStorageVersion": 1, "serverTileMin": [0, 0]}


def server_block(frame):
    return {"origin": list(frame.origin), "cells": list(frame.cells),
            "collisionOriginMetres": list(frame.collision_origin)}


# --- the server fixture ------------------------------------------------------------------------------------------------

PROFILE_FILES = ("maps.txt", "npcs.txt", "harvesting.txt", "interactives.txt", "spawns.txt", "questlines.txt",
                 "exterior_connections.json", "creatures.txt", "client_content_manifest.json")
REGISTER = """

# test_publish_server.py: the fixture isles, as the server workflow registers the real ones before --apply
REGIONS = REGIONS + ("landfall", "tollholm")
MAP_TILES_WIDE_BY_NAME.update({"landfall": 12, "tollholm": 12})
ARRIVAL_TILES.update(%s)
"""
# The code a later stage brings (publish_server.STAGE_CODE): the fixture server is copied without it.
LATER_STAGE_CODE = ("landing.py", "home.py")


def manifest_bytes(data):
    """client_content_manifest.json as the publisher writes it (and requires it to re-serialize)."""
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8").replace(b"\n", b"\r\n")


def unpublish(root):
    """Take M1's publication of the isles back out of the copied server tree: the maps the manifest's continentV2
    block names and the block itself, and those maps' entries in the vendored collision manifest (whose grids are not
    copied). A checkout the isles were never published into is left as it is."""
    content = root / "config" / "eloria" / "client_content_manifest.json"
    raw = content.read_bytes()
    data = json.loads(raw)
    assert manifest_bytes(data) == raw, "the server's manifest no longer re-serializes as the publisher writes it"
    block = data.pop(P.MANIFEST_BLOCK, None)
    if block is None:
        return
    isles = set(block["maps"])
    data["maps"] = [entry for entry in data["maps"] if entry.get("id") not in isles]
    content.write_bytes(manifest_bytes(data))
    collision = root / "tools" / "collision" / "manifest.json"
    vendored = json.loads(collision.read_text(encoding="utf-8"))
    vendored["maps"] = [entry for entry in vendored["maps"] if entry.get("map") not in isles]
    collision.write_text(json.dumps(vendored, indent=2) + "\n", encoding="utf-8")   # as the server's sync writes it


def make_server(root, arrivals, register=True):
    real = Path(SERVER)
    shutil.copytree(real / "eloria", root / "eloria",
                    ignore=shutil.ignore_patterns("__pycache__", *LATER_STAGE_CODE))
    (root / "tools" / "collision").mkdir(parents=True)
    for path in (real / "tools").glob("*.py"):
        shutil.copy2(path, root / "tools" / path.name)
    for name in ("crownwater.escg.gz", "manifest.json"):
        shutil.copy2(real / "tools" / "collision" / name, root / "tools" / "collision" / name)
    (root / "config" / "eloria").mkdir(parents=True)
    for name in PROFILE_FILES:
        shutil.copy2(real / "config" / "eloria" / name, root / "config" / "eloria" / name)
    unpublish(root)
    if register:
        maps = root / "tools" / "generate_nymara_maps.py"
        maps.write_text(maps.read_text(encoding="utf-8") + REGISTER % repr(arrivals), encoding="utf-8")
    return root


# --- the client fixture ------------------------------------------------------------------------------------------------

def sw_points():
    """landfall's markers on flat 10 m ground, three metres apart so no tile's ring meets another's."""
    keepers = ["Fixture Keeper"] + list(REHOMED)
    npcs = []
    for name, gx in zip(keepers, (57.5, 82.5, 85.5, 88.5, 91.5, 94.5)):
        identity = "npc-" + name.lower().replace(" ", "-")
        extra = {"name": name, "label": name}
        if name in REHOMED:
            extra["actorType"] = REHOMED[name][1]
        else:
            extra["actorTypeBlock"] = [374, 377]
            extra["occupation"] = "Fixture Warden"     # the line a client draws under the name
        npcs.append(record(SW, identity, gx, 42.5, **extra))
    targets = []
    spots = [(gx, gz) for gz in (45.5, 48.5) for gx in (82.5, 85.5, 88.5, 91.5, 94.5, 97.5)]
    for key, (gx, gz) in zip(TARGETS, spots):
        if key == "temple_door":
            gx, gz = 82.5, 42.5          # on Gate Warden Ilyon's post: the publisher gives it an approach
        extra = {"role": "tutorial-target", "target": key}
        if key == "ferry_quay":
            extra["radius"] = 6
        targets.append(record(SW, "tgt-" + key.replace("_", "-"), gx, gz, **extra))
    gameplay = {
        "spawnPoints": [record(SW, "sw-isle-arrival", 60.5, 27.5, default=True)],
        "harvestables": [record(SW, "harvest-100-sage", 66.5, 42.5, objectId=100, resource="Sage", label="Sage"),
                         record(SW, "harvest-101-olive", 57.5, 45.5, objectId=101, resource="Olive", label="Olive")],
        "npcMarkers": npcs,
        "interactives": [record(SW, "obj-desk", 60.5, 42.5, objectId=20, type="information"),
                         record(SW, "obj-ferry", 63.5, 42.5, objectId=21, type="portal")],
        "runtimePoints": [record(SW, "runtime-home-beam", 63.5, 27.5),
                          record(SW, "runtime-home-respawn", 66.5, 27.5),
                          record(SW, "runtime-ferry-n10", 63.5, 42.5),
                          record(SW, "opt-quest-post", 60.5, 45.5, role="tutorial-option", target="quest_post")]
        + targets,
    }
    return gameplay


def bake_doc(frame, gameplay, scene):
    return {"regionId": frame.region, "server": {**server_block(frame), "metresPerTile": 1},
            "continentTranslation": list(frame.translation), "coordinateSpace": "territory-local",
            "sources": {"scene": {"path": scene, "sha256": None}}, "gameplay": gameplay}


SPAWNS = {"landfall": [("sw-1", "rabbit", 63.5, 45.5, 15), ("sw-2", "hedgehog", 66.5, 45.5, 25),
                      ("sw-3", "squirrel", 57.5, 48.5, 15)],
          "tollholm": [("th-1", "rabbit", 130.5, 40.5, 40), ("th-pocket", "rabbit", *PLATEAU, 40)]}
QUESTLINES = """# fixture template

[quest]
key: fixture_errand
id: 26
tier: 1
title: A Fixture Errand
region: landfall
start: Fixture Keeper
summary: Walk to the post.
offer: Walk to the post and come back.
accepted: Go on.
complete: Thank you.
repeat: Again?
reward_xp: overall=1600
reward_gold: 200
[stage]
kind: visit
npc: Fixture Keeper
map: landfall
x: <TX:opt-quest-post>
y: <TY:opt-quest-post>
objective: Walk to the post.
prompt: The post is north of the desk.
done: You found it.
xp: overall=100
[/stage]
[/quest]
"""


def make_client(root, codec, bakes_root, spawns=SPAWNS):
    """The client checkout, its bakes (outside it) and the packages export_collision.py writes."""
    import test_export_collision as TE
    entries = []
    for region, frame in FRAMES.items():
        scene = f"godot-client/world_authoring/regions/{region}/{region}.tscn"
        (root / scene).parent.mkdir(parents=True, exist_ok=True)
        (root / scene).write_text(f"[gd_scene]\n; fixture {region}\n", encoding="utf-8", newline="\n")
        spec = f"godot-client/world_authoring/regions/{region}/region-authoring-spec.json"
        write_json(root / spec, {"server": server_block(frame), "continentTranslation": list(frame.translation)})
        write_json(root / V2 / region / "world.json",
                   {"server": server_block(frame),
                    "continentGeography": {"translation": list(frame.translation),
                                           "ownershipPolygon": POLYGONS[region]}})
        entries.append({"id": region, "label": frame.label, "manifestPath": f"res://../{V2}/{region}/world.json",
                        "publishedManifestPath": f"res://../{V2}/{region}/client/world.json",
                        "scenePath": "res://" + scene[len("godot-client/"):],
                        "authoringSpecPath": "res://" + spec[len("godot-client/"):]})
        rows = [{"id": i, "creature": c, "local": local(frame, gx, gz)[::2], "leash": leash, "zone": "z", "band": "A"}
                for i, c, gx, gz, leash in spawns[region]]
        write_json(root / V2 / region / "content" / "spawns.json",
                   {"schema": "eloria-continent-v2-spawns-v1", "map": region, "spawns": rows})
    write_json(root / "godot-client/world_authoring/continent-v2/territories.json", {"entries": entries})
    write_json(root / "godot-client/data/maps/registry.json", {"maps": {
        region: {"manifest": f"res://../{V2}/{region}/client/world.json", "coordinateTransform": transform(frame),
                 "continentGeography": {"translation": list(frame.translation), "serverCells": list(frame.cells)}}
        for region, frame in FRAMES.items()}})
    write_json(root / X.PLAN, {"frame": {"seaLevel": 0.0}, "water": {"seaLevel": 0.0},
                              "seams": {"openSeams": [{"between": ["landfall", "tollholm"]}], "moles": []},
                              "approvedRoutes": [{"id": "R1", "type": "road",
                                                  "approvedPolyline": [[90.0, 27.5], [110.0, 27.5]],
                                                  "byTerritory": [{"territory": "landfall"},
                                                                  {"territory": "tollholm"}]}]})
    gameplay = {"landfall": sw_points(),
                "tollholm": {"spawnPoints": [record(TH, "th-arrival", 130.5, 21.5, default=True)]}}
    shas, spawn_local = {}, {}
    for region, frame in FRAMES.items():
        scene = f"godot-client/world_authoring/regions/{region}/{region}.tscn"
        doc = bake_doc(frame, gameplay[region], scene)
        doc["sources"]["scene"]["sha256"] = P.sha256_file(root / scene)
        path = bakes_root / region / "continent-authoring.json"
        write_json(path, doc)
        shas[region] = P.sha256_file(path)
        point = gameplay[region]["spawnPoints"][0]["position"]
        spawn_local[region] = (point[0], point[2])
    territories = []
    for region, frame in FRAMES.items():
        heights, origin = TE.terrain(frame)
        extra = {}
        if region == "landfall":
            (lx, lz), (rx, rz), level = TE.LAKE
            extra["lakes"] = [{"id": "lake", "center": [lx - 70.0, lz - 30.0], "radii": [rx, rz], "level": level}]
        territories.append(X.Territory(region=region, frame=frame, polygon=POLYGONS[region], heights=heights,
                                       terrain_origin=origin, spawn=spawn_local[region],
                                       sources={"snapshotSha256": shas[region], "sceneSha256": "0" * 64}, **extra))
    work = root.parent / (root.name + "-export")
    _report, sidecars = X.run(territories, [("landfall", "tollholm")], codec, work, root / V2, log=lambda *_: None)
    for region, frame in FRAMES.items():
        spawn = gameplay[region]["spawnPoints"][0]
        write_json(root / V2 / region / "client" / "world.json", {
            "coordinateTransform": transform(frame),
            "spawnPoints": [{"default": True, "id": spawn["id"], "position": spawn["position"],
                             "serverTile": spawn["serverTile"]}],
            "continentGeography": {"translation": list(frame.translation), "ownershipPolygon": POLYGONS[region]},
            "collision": sidecars[region]["collision"], "provenance": {"snapshotSha256": shas[region]}})
    content = root / V2 / "_continent_v2" / "content"
    rows = {"schema": "eloria-continent-v2-server-rows-v1", "maps": {
        "landfall": {"npcs": {}, "interactives": {
            "obj-desk": {"objectId": 20, "role": "information", "target": "register",
                         "text": "The fixture register lies open."},
            "obj-ferry": {"objectId": 21, "role": "portal", "target": "maps.txt", "text": "The fixture ferry.",
                          "portal": {"destinationMap": "crownwater", "oneWay": True}}}},
        "tollholm": {"npcs": {}, "interactives": {}}}}
    for npc in gameplay["landfall"]["npcMarkers"]:
        name = npc["name"]
        role, body = REHOMED.get(name, ("dialogue", 376))
        rows["maps"]["landfall"]["npcs"][npc["id"]] = {
            "name": name, "group": "re-homed" if name in REHOMED else "new", "role": role, "actorType": body,
            "greeting": "Welcome to the fixture." if name not in REHOMED else f"{name} keeps the old greeting."}
    write_json(content / "server-rows.json", rows)
    tables = json.loads((Path(HERE) / "content" / "server-tables.json").read_text(encoding="utf-8"))
    tables["maps"] = [m for m in tables["maps"] if m["id"] in FRAMES]
    tables["holdBack"] = {"why": "fixture pocket", "map": "tollholm", "spawns": ["th-pocket"], "nodes": []}
    tables["homes"] = {"landfall": {"arrival": "sw-isle-arrival", "beam": "runtime-home-beam",
                                   "respawn": "runtime-home-respawn", "underworld": "runtime-home-respawn"}}
    tables["landing"].update(map="landfall", arrival="runtime-home-beam", register="obj-desk", ferry="obj-ferry", ferryPoint="runtime-ferry-n10")
    write_json(content / "server-tables.json", tables)
    (content / "questlines.txt").write_text(QUESTLINES, encoding="utf-8", newline="\n")
    return root


def run(script, *args, cwd=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("ELORIA_CONTENT_OVERLAY", None)
    return subprocess.run([sys.executable, "-B", str(HERE / script), *map(str, args)], capture_output=True,
                          text=True, env=env, cwd=cwd)


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    root = tmp_path_factory.mktemp("publish_server")
    codec = X.server_codec(SERVER)
    client = make_client(root / "client", codec, root / "bakes")
    arrivals = {region: tuple(json.loads((client / V2 / region / "client" / "world.json").read_text())
                              ["spawnPoints"][0]["serverTile"]) for region in FRAMES}
    server = make_server(root / "server", arrivals)
    result = run("crossings_v2.py", "--server", server, "--checkout", client)
    assert result.returncode == 0, result.stderr + result.stdout
    return root


@pytest.fixture
def tree(template, tmp_path):
    for name in ("client", "server", "bakes"):
        shutil.copytree(template / name, tmp_path / name)
    return tmp_path


def publish(tree, mode, *extra, stage="m1"):
    args = ["--server", tree / "server", "--checkout", tree / "client", mode, "--stage", stage]
    for region in FRAMES:
        args += ["--bake", f"{region}={tree / 'bakes' / region}"]
    return run("publish_server.py", *args, *extra)


LANDING_STUB = '''"""test_publish_server.py: a stand-in for the chapter's eloria/landing.py (the serve plan's M2 code)."""
import json
from types import SimpleNamespace


def load_layout(path):
    doc = json.loads(open(path, encoding="utf-8").read())
    return SimpleNamespace(targets=doc["targets"], cast=doc["cast"])
'''


def chapter_code(tree):
    """The M2 server tree: the chapter's eloria/landing.py (a stand-in that parses landing.json)."""
    (tree / "server" / "eloria" / "landing.py").write_text(LANDING_STUB, encoding="utf-8", newline="\n")


def outputs(tree):
    """SHA-256 of every file the publisher writes."""
    server = tree / "server"
    paths = sorted((server / "config/eloria/continent-v2").iterdir())
    paths += [server / "config/eloria/client_content_manifest.json", server / "tools/collision/manifest.json",
              *[server / "tools/collision" / f"{r}.escg.gz" for r in FRAMES],
              tree / "client" / P.DEFAULT_RECORD]
    return {p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def overlay(tree, name):
    return (tree / "server/config/eloria/continent-v2" / name).read_bytes()


def test_apply_and_check_preserve_server_owned_service_npcs(tree):
    directory = tree / "server/config/eloria/continent-v2"
    directory.mkdir(parents=True, exist_ok=True)
    services = b"npc | Service Keeper | landfall | 5 | 5 | dialogue | actor_type=311 | Welcome.\r\n"
    path = directory / "service_npcs.txt"
    path.write_bytes(services)
    result = publish(tree, "--apply")
    assert result.returncode == 0, result.stderr + result.stdout
    assert path.read_bytes() == services
    result = publish(tree, "--check")
    assert result.returncode == 0, result.stderr + result.stdout
    assert path.read_bytes() == services


def test_apply_check_and_a_byte_identical_rerun(tree):
    before = (tree / "server/config/eloria/client_content_manifest.json").read_bytes()
    result = publish(tree, "--apply")
    assert result.returncode == 0, result.stderr + result.stdout
    first = outputs(tree)
    assert set(name for name in first if "continent-v2" in name and "config" in name) == \
        {f"server/config/eloria/continent-v2/{name}" for name in P.FILES if name != "questlines.txt"}
    check = publish(tree, "--check")
    assert check.returncode == 0, check.stderr + check.stdout
    assert json.loads(check.stdout)["check"] == "clean"
    again = publish(tree, "--apply")
    assert again.returncode == 0, again.stderr
    assert outputs(tree) == first
    # Every overlay file is CRLF and the README says what it is.
    for name in P.stage_files("m1"):
        data = overlay(tree, name)
        assert data.count(b"\r\n") == data.count(b"\n") > 0, name
    assert b"do not hand-edit" in overlay(tree, "README")
    # The manifest keeps every byte it had and gains the isles' entries and the continentV2 block.
    after = json.loads((tree / "server/config/eloria/client_content_manifest.json").read_text(encoding="utf-8"))
    original = json.loads(before)
    assert [m for m in after["maps"] if m["id"] not in FRAMES] == original["maps"]
    assert {k: v for k, v in after.items() if k not in ("maps", "continentV2")} == \
        {k: v for k, v in original.items() if k != "maps"}
    isles = {m["id"]: m for m in after["maps"] if m["id"] in FRAMES}
    assert isles["landfall"]["server_cells"] == CELLS and isles["landfall"]["serverStorageVersion"] == 1
    assert {"server_tile": [isles["landfall"]["portals"][-1]["server_tile"][0],
                            isles["landfall"]["portals"][-1]["server_tile"][1]],
            "destination": "crownwater"} == isles["landfall"]["portals"][-1]
    assert after["continentV2"]["heldBack"] == ["th-pocket"]
    # The vendored grids are the packages' bytes.
    for region in FRAMES:
        assert (tree / "server/tools/collision" / f"{region}.escg.gz").read_bytes() == \
            (tree / "client" / V2 / region / "client" / "served-grid.escg.gz").read_bytes()


def test_catalog_retirements_remove_only_stale_grids_and_check_orphan_blobs(tree):
    retired = ["sw_isle", "tollholms", "gull_skerries"]  # Exact historical retirement inputs.
    catalog_path = tree / "client" / F.CATALOG
    catalog = json.loads(catalog_path.read_text())
    catalog["retiredMapIds"] = retired
    write_json(catalog_path, catalog)
    collision = tree / "server/tools/collision"
    manifest_path = collision / "manifest.json"
    before = json.loads(manifest_path.read_text())
    legacy_rows = before["maps"][:]
    legacy_grid = (collision / "crownwater.escg.gz").read_bytes()
    before["maps"] += [{"map": region, "historical": True} for region in retired]
    write_json(manifest_path, before)
    for region in retired:
        (collision / f"{region}.escg.gz").write_bytes(b"retired historical fixture")

    result = publish(tree, "--apply")
    assert result.returncode == 0, result.stderr + result.stdout
    after = json.loads(manifest_path.read_text())
    assert [row for row in after["maps"] if row["map"] not in FRAMES] == legacy_rows
    assert not set(retired).intersection(row["map"] for row in after["maps"])
    assert all(not (collision / f"{region}.escg.gz").exists() for region in retired)
    assert (collision / "crownwater.escg.gz").read_bytes() == legacy_grid
    assert publish(tree, "--check").returncode == 0

    # A leftover blob must be refused even if no manifest row names it.
    orphan = collision / f"{retired[0]}.escg.gz"
    orphan.write_bytes(b"orphan retired fixture")
    check = publish(tree, "--check")
    assert check.returncode == 1, check.stderr + check.stdout
    assert f"tools/collision/{retired[0]}.escg.gz (retired)" in json.loads(check.stdout)["differences"]
    assert orphan.exists(), "check must not mutate the served directory"


@pytest.mark.parametrize("values", [["../outside"], ["landfall"]])
def test_retirement_metadata_refuses_unsafe_or_active_ids(tmp_path, values):
    write_json(tmp_path / F.CATALOG, {"retiredMapIds": values})
    with pytest.raises(P.PublishError):
        P.retired_maps(SimpleNamespace(checkout=tmp_path), ["landfall"])


@pytest.mark.parametrize("failure", [None, "blocked", "unreached", "height_mismatch", "missing_grid", "in_owner_unreached"])
def test_harvest_ring_uses_only_identical_reached_canonical_off_owner_cells(failure):
    source = F.Frame("landfall", "Landfall", (0, 4), (5, 5), (0, 0, 0))
    neighbour = F.Frame("tollholm", "Tollholm", (1, 4), (5, 5), (0, 0, 0))
    codes = {region: np.full((5, 5), 222, dtype=np.uint16) for region in (source.region, neighbour.region)}
    reached = {region: np.ones((5, 5), bool) for region in codes}
    # Harvest body is closed; a seam-strip alias is not reachable on the
    # source map, but its exact physical cell is reachable on its owner.
    codes[source.region][2, 1] = 0
    reached[source.region][2, 2] = False
    if failure == "blocked":
        codes[neighbour.region][2, 3] = 0
    elif failure == "unreached":
        reached[neighbour.region][2, 3] = False
    elif failure == "height_mismatch":
        codes[neighbour.region][2, 3] += 1
    elif failure == "missing_grid":
        del codes[neighbour.region]
    elif failure == "in_owner_unreached":
        reached[source.region][2, 0] = False
    polygons = {source.region: [[0, -1], [2, -1], [2, 4], [0, 4]],
                neighbour.region: [[2, -1], [4, -1], [4, 4], [2, 4]]}
    checker = P.Checker(codes, reached, {source.region: source, neighbour.region: neighbour}, polygons)
    assert checker.ring(source.region, [1, 2], "node", 247, body=True) is (failure is None)
    assert bool(checker.failures) is (failure is not None)


def test_the_rows_say_what_the_markers_and_tables_say(tree):
    chapter_code(tree)
    result = publish(tree, "--apply", stage="m2")
    assert result.returncode == 0, result.stderr + result.stdout
    text = {name: overlay(tree, name).decode("utf-8") for name in P.FILES}
    maps = text["maps.txt"]
    assert "map | landfall | Landfall | maps/nymara/landfall.elm | LANDFALL\r\n" in maps
    desk = SW.tile(*local(SW, 60.5, 42.5)[::2])
    ferry = SW.tile(*local(SW, 63.5, 42.5)[::2])
    assert f"portal | landfall | 21 | {ferry[0]} | {ferry[1]} | crownwater | 293 | 113\r\n" in maps
    lanes = [line for line in maps.splitlines() if line.startswith("portal |") and "crownwater" not in line]
    assert len(lanes) == 2 * 60
    assert f"landfall | 20 | {desk[0]} | {desk[1]} | information | register | The fixture register lies open." \
        in text["interactives.txt"]
    spawns = [line for line in text["spawns.txt"].splitlines() if line.startswith("spawn |")]
    assert len(spawns) == 4 and all(line.split(" | ")[-1].startswith("leash:") for line in spawns)
    assert not any(" | 148 " in line or "th-pocket" in line for line in spawns)   # held back
    assert "resource | Olive | 1 | 6 | 3.5 | -" in text["harvesting.txt"]
    assert "node | landfall | 101 |" in text["harvesting.txt"]
    assert "npc | Fixture Keeper | landfall |" in text["npcs.txt"] and "Ilyon" not in text["npcs.txt"]
    assert " | dialogue | actor_type=376,occupation=Fixture Warden | Welcome to the fixture." in text["npcs.txt"]
    home = [line for line in text["home_npcs.txt"].splitlines() if line.startswith("npc |")]
    assert len(home) == 5 and all(" | landfall | " in line for line in home)
    landing = json.loads(text["landing.json"])
    post = SW.tile(*local(SW, 82.5, 42.5)[::2])
    assert landing["targets"]["temple_door"]["tile"] == list(post)
    assert landing["targets"]["temple_door"]["approach"] != list(post)
    assert landing["targets"]["ferry_quay"]["radius"] == 6
    assert landing["objects"] == {"register": {"map":"landfall","id":20}, "ferry": {"map":"landfall","id":21}}
    assert sorted(c["name"] for c in landing["cast"]) == sorted(REHOMED)
    homes = json.loads(text["homes.json"])["homes"]["landfall"]
    assert homes["underworld"] == homes["respawn"]
    quest = SW.tile(*local(SW, 60.5, 45.5)[::2])
    assert f"x: {quest[0]}\r\ny: {quest[1]}\r\n" in text["questlines.txt"]
    links = json.loads(text["exterior_connections.json"])
    assert [c["id"] for c in links["connections"]] == ["landfall--tollholm"]


def edit_json(path, change):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    change(data)
    write_json(path, data)


def move_bake_record(tree, region, section, identity, gx, gz):
    path = tree / "bakes" / region / "continent-authoring.json"

    def change(doc):
        frame = FRAMES[region]
        for item in doc["gameplay"][section]:
            if item["id"] == identity:
                item.update(record(frame, identity, gx, gz))
    edit_json(path, change)


def refused(result, words):
    assert result.returncode == 1, result.stdout
    assert words in result.stderr, result.stderr


def test_a_blocked_row_is_refused(tree):
    """A harvest node moved into the lake: the bake no longer matches the package, so re-export the fixture's
    package provenance by pointing it at the edited bake (the collision does not depend on the markers)."""
    move_bake_record(tree, "landfall", "harvestables", "harvest-101-olive", *LAKE)
    restamp(tree, "landfall")
    refused(publish(tree, "--check"), "rows fail the checks")


def restamp(tree, region):
    """Point the package and its collision block at the edited bake (markers do not change the grid)."""
    sha = P.sha256_file(tree / "bakes" / region / "continent-authoring.json")

    def change(doc):
        doc["provenance"]["snapshotSha256"] = sha
        doc["collision"]["sourceSnapshotSha256"] = sha
    edit_json(tree / "client" / V2 / region / "client" / "world.json", change)
    for other in FRAMES:        # every package's record of the run names the re-pointed bake
        edit_json(tree / "client" / V2 / other / "client" / "world.json",
                  lambda doc: doc["collision"]["groupExport"]["maps"][region].update(snapshotSha256=sha))


def test_a_node_on_a_road_is_refused(tree):
    """D11: the bake's road paths (the scene's Roads/* curves) at their saved widths; a node's tile centre within a
    road's half-width is refused and named, whatever its ring."""
    sage = local(SW, 66.5, 42.5)

    def change(doc):
        doc["paths"] = [{"id": "fixture-road", "kind": "road", "closed": False, "points": [
            {"position": [sage[0] - 8.0, 10.0, sage[2] + 1.0], "width": 4.0},
            {"position": [sage[0] + 8.0, 10.0, sage[2] + 1.0], "width": 4.0}]}]
    edit_json(tree / "bakes" / "landfall" / "continent-authoring.json", change)
    restamp(tree, "landfall")
    result = publish(tree, "--check")
    refused(result, "rows fail the checks")
    assert "on road fixture-road" in result.stderr and "(D11)" in result.stderr


def test_an_unreachable_row_is_refused_unless_it_is_held_back(tree):
    edit_json(tree / "client" / V2 / "tollholm" / "content" / "spawns.json",
              lambda doc: doc["spawns"][0].update(local=local(TH, *PLATEAU)[::2]))
    result = publish(tree, "--check")
    refused(result, "rows fail the checks")
    assert "not reached" in result.stderr and "th-1" in result.stderr


def test_a_name_that_carries_its_occupation_is_refused(tree):
    """Names stay simple (owner, 2026-10-14): the job goes on the occupation line, not into the name."""
    path = tree / "bakes" / "landfall" / "continent-authoring.json"
    edit_json(path, lambda doc: next(npc for npc in doc["gameplay"]["npcMarkers"]
                                     if npc["name"] == "Fixture Keeper").update(occupation="Fixture"))
    restamp(tree, "landfall")
    refused(publish(tree, "--check"), "keep the name simple")


def test_a_moved_person_keeps_their_occupation(tree):
    path = tree / "bakes" / "landfall" / "continent-authoring.json"
    edit_json(path, lambda doc: next(npc for npc in doc["gameplay"]["npcMarkers"]
                                     if npc["name"] == "Bettany Orl").update(occupation="Innkeeper"))
    restamp(tree, "landfall")
    refused(publish(tree, "--check"), "a move keeps the occupation")


def test_an_inline_comment_is_refused(tree):
    path = tree / "client" / V2 / "_continent_v2" / "content" / "server-rows.json"
    edit_json(path, lambda doc: doc["maps"]["landfall"]["npcs"]["npc-fixture-keeper"].update(
        greeting="Welcome. # not a comment to the loader"))
    refused(publish(tree, "--check"), "holds '|', '#' or a line break")


def test_an_unwalkable_ferry_landing_is_refused(tree):
    sys.path.insert(0, str(Path(SERVER) / "tools"))
    import authored_collision as A
    grid = A.read_grid(Path(SERVER) / "tools" / "collision" / "crownwater.escg.gz")
    heights = np.frombuffer(bytes(grid.heights), np.uint8).reshape(grid.cells, grid.cells)
    y, x = (int(v) for v in np.argwhere((heights & 0x3F) == 0)[0])
    geography = tree / "server" / "eloria" / "continent_geography.py"
    text = geography.read_text(encoding="utf-8")
    assert text.count("'arrival': [293, 113]") == 1
    geography.write_text(text.replace("'arrival': [293, 113]", f"'arrival': [{x}, {y}]"), encoding="utf-8")
    refused(publish(tree, "--check"), "arrival copies disagree")
    manifest = tree / "server" / "config" / "eloria" / "client_content_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for item in data["maps"]:
        if item["id"] == "crownwater":
            item["arrival"] = [x, y]
    data["continentGeography"]["regions"]["crownwater"]["arrival"] = [x, y]
    manifest.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").replace("\n", "\r\n").encode())
    refused(publish(tree, "--check"), "the landing is not walkable")


def test_a_hand_edit_shows_in_check(tree):
    assert publish(tree, "--apply").returncode == 0
    path = tree / "server/config/eloria/continent-v2/spawns.txt"
    path.write_bytes(path.read_bytes() + b"spawn | landfall | rabbit | 40 | 40 | leash:5\r\n")
    result = publish(tree, "--check")
    assert result.returncode == 1
    assert json.loads(result.stdout)["differences"] == ["config/eloria/continent-v2/spawns.txt"]


def test_a_stale_crossings_document_is_refused(tree):
    path = tree / "client" / P.V2 / "_continent_v2" / "crossings.json"
    edit_json(path, lambda doc: doc["inputs"]["maps"]["tollholm"].update(servedGridSha256="1" * 64))
    refused(publish(tree, "--check"), "crossings.json is stale for tollholm")


def test_a_bake_from_another_scene_is_refused(tree):
    scene = tree / "client" / "godot-client/world_authoring/regions/landfall/landfall.tscn"
    scene.write_text(scene.read_text(encoding="utf-8") + "; edited\n", encoding="utf-8", newline="\n")
    refused(publish(tree, "--check"), "re-bake it")


def test_catalog_frames_register_the_isles_without_a_static_tool_list(tree):
    maps = tree / "server" / "tools" / "generate_nymara_maps.py"
    shutil.copy2(Path(SERVER) / "tools" / "generate_nymara_maps.py", maps)
    result = publish(tree, "--apply")
    assert result.returncode == 0, result.stderr


# --- the serve plan's stages -----------------------------------------------------------------------------------------

def test_m1_leaves_the_errands_out_and_m2_adds_them(tree):
    """questlines.txt goes live the moment it exists; before M2's region gate and isle cast the errands' givers stand
    only at Four Gates, so M1 does not serve it. The record is the same at every stage."""
    errands = tree / "server/config/eloria/continent-v2/questlines.txt"
    assert publish(tree, "--apply").returncode == 0
    assert not errands.exists()
    record = (tree / "client" / P.DEFAULT_RECORD).read_bytes()
    block = json.loads((tree / "server/config/eloria/client_content_manifest.json").read_text(encoding="utf-8"))
    assert block["continentV2"]["stage"] == "m1" and "questlines.txt" not in block["continentV2"]["overlay"]["files"]
    assert json.loads(publish(tree, "--check").stdout)["check"] == "clean"
    refused(publish(tree, "--check", stage="m2"), "needs ['eloria/landing.py']")
    chapter_code(tree)
    check = publish(tree, "--check", stage="m2")
    assert check.returncode == 1
    assert "config/eloria/continent-v2/questlines.txt" in json.loads(check.stdout)["differences"]
    result = publish(tree, "--apply", stage="m2")
    assert result.returncode == 0, result.stderr
    assert errands.read_bytes().count(b"\r\n") > 0
    assert json.loads(publish(tree, "--check", stage="m2").stdout)["check"] == "clean"
    assert (tree / "client" / P.DEFAULT_RECORD).read_bytes() == record
    back = publish(tree, "--check")
    assert "config/eloria/continent-v2/questlines.txt (not served at m1)" in json.loads(back.stdout)["differences"]
    removed = publish(tree, "--apply")
    assert json.loads(removed.stdout)["removed"] == ["config/eloria/continent-v2/questlines.txt"]
    assert not errands.exists() and (tree / "client" / P.DEFAULT_RECORD).read_bytes() == record
    refused(publish(tree, "--check", stage="m3"), "eloria/home.py")


def test_the_record_holds_only_isle_facts(tree):
    """The M2 tree adds the chapter's parser and another workflow may edit a base table: neither is an isle input,
    so the client's record and --check stay clean (the server's loader counts go to the summary)."""
    assert publish(tree, "--apply").returncode == 0
    record = json.loads((tree / "client" / P.DEFAULT_RECORD).read_text(encoding="utf-8"))
    assert "serverLoaders" not in record
    assert set(record["ferries"][0]) == {"map", "object", "trigger", "destination", "landing"}
    assert record["server"]["stages"]["m1"]["files"] == list(P.stage_files("m1"))
    assert record["server"]["stages"]["m2"]["files"] == list(P.FILES)
    chapter_code(tree)
    base = tree / "server/config/eloria/spawns.txt"
    base.write_bytes(base.read_bytes() + b"\r\n# another workflow's comment\r\n")
    check = publish(tree, "--check")
    assert check.returncode == 0, check.stdout + check.stderr
    summary = json.loads(check.stdout)
    assert summary["check"] == "clean" and summary["serverLoaders"]["landingParser"].startswith("eloria.landing")
    assert summary["ferries"][0]["landingCopies"]


def test_npc_posts_are_closed_in_the_reach(tree, codec_):
    """The server blocks the tile an NPC stands on: the record's reach is the served union reach with the six
    fixture posts closed, which here (flat ground round every post) is the open reach less the posts."""
    assert publish(tree, "--apply").returncode == 0
    record = json.loads((tree / "client" / P.DEFAULT_RECORD).read_text(encoding="utf-8"))
    codes, arrivals = {}, {}
    for region in FRAMES:
        package = tree / "client" / V2 / region / "client"
        grid = codec_.served_grid.decode_file((package / "served-grid.escg.gz").read_bytes())
        codes[region] = np.frombuffer(grid.codes, np.uint16).reshape(grid.height, grid.width).copy()
        arrivals[region] = json.loads((package / "world.json").read_text())["spawnPoints"][0]["serverTile"]
    crossings = json.loads((tree / "client" / P.V2 / "_continent_v2" / "crossings.json").read_text(encoding="utf-8"))
    open_reach = P.union_reach(codes, arrivals, [tuple(r) for r in crossings["portals"]], 20)
    assert record["maps"]["landfall"]["npcPosts"] == 6
    assert record["maps"]["landfall"]["servedReachTiles"] == int(open_reach["landfall"].sum()) - 6
    # and the checker judges a post by its open ground, its ring by the reach
    frame_table = {"landfall": SW}
    flat = np.full((CELLS, CELLS), 2200, np.uint16)
    walk = flat.copy()
    walk[40, 40] = 0
    reached = np.ones((CELLS, CELLS), bool)
    reached[40, 40] = False
    polygon = [[0.0, 0.0], [200.0, 0.0], [200.0, 100.0], [0.0, 100.0]]
    checker = P.Checker({"landfall": walk}, {"landfall": reached}, frame_table, {"landfall": polygon},
                        ground={"landfall": flat})
    assert checker.ring("landfall", (40, 40), "npc", "post", post=True)
    assert not checker.ring("landfall", (41, 40), "spawn", "beside the post")
    assert "blocked [[40, 40]]" in checker.failures[0]["problems"][0]


@pytest.fixture(scope="module")
def codec_():
    return X.server_codec(SERVER)


def test_packages_from_two_export_runs_are_refused(tree):
    path = tree / "client" / V2 / "tollholm" / "client" / "world.json"
    edit_json(path, lambda doc: doc["collision"]["groupExport"]["maps"]["landfall"].update(
        servedGridSha256="1" * 64))
    refused(publish(tree, "--check"), "exported in another run")


# --- the isle boats (owner 2026-10-14: R5, the Ravenhead-Tollholm boat) -----------------------------------------------

BOATS = {"landfall": {"boat": ("obj-boat", 72.5, 33.5), "landing": ("runtime-boat-landing", 72.5, 36.5)},
         "tollholm": {"boat": ("th-obj-boat", 136.5, 30.5), "landing": ("th-runtime-boat-landing", 136.5, 33.5)}}


def add_boats(tree, *, change_rows=None):
    """A boat each way between the fixture isles: on each map the boat (a portal interactive, object 23) and the
    boat-landing runtime point the other map's boat lands on; the bakes re-pointed, the server rows added."""
    for region, frame in FRAMES.items():
        boat, landing = BOATS[region]["boat"], BOATS[region]["landing"]

        def change(doc, frame=frame, boat=boat, landing=landing):
            doc["gameplay"].setdefault("interactives", []).append(
                record(frame, boat[0], boat[1], boat[2], objectId=23, type="portal"))
            doc["gameplay"].setdefault("runtimePoints", []).append(
                record(frame, landing[0], landing[1], landing[2], role=P.BOAT_LANDING_ROLE))
        edit_json(tree / "bakes" / region / "continent-authoring.json", change)
        restamp(tree, region)

    def rows(doc):
        for region, other in (("landfall", "tollholm"), ("tollholm", "landfall")):
            doc["maps"][region]["interactives"][BOATS[region]["boat"][0]] = {
                "objectId": 23, "role": "portal", "target": "maps.txt", "text": f"The fixture boat to {other}.",
                "portal": {"destinationMap": other, "oneWay": True, "landingMarker": BOATS[other]["landing"][0],
                           "returnBy": BOATS[other]["boat"][0]}}
        if change_rows:
            change_rows(doc)
    edit_json(tree / "client" / V2 / "_continent_v2" / "content" / "server-rows.json", rows)


def tile_of(region, part):
    _identity, gx, gz = BOATS[region][part]
    return list(FRAMES[region].tile(*local(FRAMES[region], gx, gz)[::2]))


def test_isle_boats_sail_both_ways_and_land_beside_the_boat_back(tree):
    add_boats(tree)
    result = publish(tree, "--apply")
    assert result.returncode == 0, result.stderr + result.stdout
    maps = overlay(tree, "maps.txt").decode("utf-8")
    objects = overlay(tree, "interactives.txt").decode("utf-8")
    for region, other in (("landfall", "tollholm"), ("tollholm", "landfall")):
        trigger, landing = tile_of(region, "boat"), tile_of(other, "landing")
        assert (f"portal | {region} | 23 | {trigger[0]} | {trigger[1]} | {other} | {landing[0]} | {landing[1]}\r\n"
                in maps)
        assert f"{region} | 23 | {trigger[0]} | {trigger[1]} | portal | maps.txt | The fixture boat to {other}." \
            in objects
    manifest = json.loads((tree / "server/config/eloria/client_content_manifest.json").read_text(encoding="utf-8"))
    block = manifest["continentV2"]
    # the exit ferry stays the only ferry; the boats are listed apart, one entry each way
    assert [f["destination"] for f in block["ferries"]] == ["crownwater"]
    assert {(b["map"], b["object"], b["destination"], b["returnBy"]) for b in block["boats"]} == {
        ("landfall", 23, "tollholm", "th-obj-boat"), ("tollholm", 23, "landfall", "obj-boat")}
    for b in block["boats"]:
        assert b["trigger"] == tile_of(b["map"], "boat") and b["landing"] == tile_of(b["destination"], "landing")
    entries = {m["id"]: m for m in manifest["maps"]}
    assert {"server_tile": tile_of("tollholm", "boat"), "destination": "landfall"} in entries["tollholm"]["portals"]
    record_doc = json.loads((tree / "client" / P.DEFAULT_RECORD).read_text(encoding="utf-8"))
    assert record_doc["boats"] == block["boats"]
    # a boat is an object portal: no land link, so the land pairs are what crossings.json says
    links = json.loads(overlay(tree, "exterior_connections.json").decode("utf-8"))
    assert [c["id"] for c in links["connections"]] == ["landfall--tollholm"]
    summary = json.loads(result.stdout)
    assert len(summary["boats"]) == 2 and summary["serverLoaders"]["interactives"] >= 2
    assert json.loads(publish(tree, "--check").stdout)["check"] == "clean"


def test_a_boat_without_its_way_back_is_refused(tree):
    def change(doc):
        doc["maps"]["tollholm"]["interactives"]["th-obj-boat"]["portal"]["returnBy"] = "obj-desk"
    add_boats(tree, change_rows=change)
    # landfall's boat names th-obj-boat, which names the desk back: the pair is broken, whichever end is read first
    refused(publish(tree, "--check"), "portal.returnBy 'th-obj-boat' is not a boat on tollholm that sails back to "
                                      "landfall and names obj-boat as its way back")


def test_a_boat_needs_its_landing_point(tree):
    def change(doc):
        doc["maps"]["landfall"]["interactives"]["obj-boat"]["portal"]["landingMarker"] = "th-arrival"
    add_boats(tree, change_rows=change)
    refused(publish(tree, "--check"), "tollholm has no boat-landing runtime point 'th-arrival'")
    edit_json(tree / "client" / V2 / "_continent_v2" / "content" / "server-rows.json",
              lambda doc: doc["maps"]["landfall"]["interactives"]["obj-boat"]["portal"].pop("landingMarker"))
    refused(publish(tree, "--check"), "an isle boat needs portal.landingMarker")


def test_a_boat_landing_in_the_sea_or_far_from_the_boat_back_is_refused(tree):
    add_boats(tree)
    move_bake_record(tree, "landfall", "runtimePoints", "runtime-boat-landing", 88.5, 8.5)    # the sea inlet
    edit_json(tree / "bakes" / "landfall" / "continent-authoring.json", lambda doc: next(
        r for r in doc["gameplay"]["runtimePoints"] if r["id"] == "runtime-boat-landing").update(
            role=P.BOAT_LANDING_ROLE))
    restamp(tree, "landfall")
    result = publish(tree, "--check")
    refused(result, "rows fail the checks")
    assert '"boat landing"' in result.stderr and "blocked" in result.stderr and "tiles from the boat back" \
        in result.stderr
    move_bake_record(tree, "landfall", "runtimePoints", "runtime-boat-landing", 72.5, 33.5)  # on the boat back
    edit_json(tree / "bakes" / "landfall" / "continent-authoring.json", lambda doc: next(
        r for r in doc["gameplay"]["runtimePoints"] if r["id"] == "runtime-boat-landing").update(
            role=P.BOAT_LANDING_ROLE))
    restamp(tree, "landfall")
    result = publish(tree, "--check")
    refused(result, "rows fail the checks")
    assert "it is interactive 23's tile" in result.stderr
