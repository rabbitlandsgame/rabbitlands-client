"""The underground platform of pass 2 (2026-10-21): doors, passages, wall veins and the archetype helpers.

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_underground_platform.py -q

The source-format tests need nothing but this checkout. The build-and-publish test builds a two-section underground
from a synthetic source with the real builder (two doors, a doorless section reached by a passage, a wall vein) into a
temporary folder and runs underground.py's publication rules on it against stand-in exterior bakes; it needs the
server checkout named by ELORIA_SERVER_ROOT (its collision code and served-grid codec) and skips without it.

Several interior sources (2026-10-27): the same built package, copied as landfall_town with a town source of building
doors (no marker; label, exit label, category), a person and a notice, publishes beside the caves without moving a
byte of theirs; the building door, id, builder and post rules refuse what they must. retarget_underground.py over both
sources keeps every source's objects.json records and writes the building doors' (with the painted door's offsets at
both ends), and with --map rewrites one interior only (no server needed).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import underground_source as S  # noqa: E402

SOURCE = HERE / "content/underground.json"
SERVER = os.environ.get("ELORIA_SERVER_ROOT")


def door(index, **extra):
    return {"map": "fakemap", "marker": f"fakemap--door-{index}", "object": 9100 + index, "tile": [10 + 10 * index, 10],
            "position": [10.5 + 10 * index, 0.0, 20.5], "returnTile": [10 + 10 * index, 5], **extra}


# --- the source format -------------------------------------------------------------------------------------------


def test_the_old_single_door_reads_as_one_door():
    section = {"id": "a", "entrance": door(0), "arrival": [5, 6], "exit": [5, 2], "exitFacing": [0, -1]}
    (only,) = S.doors(section)
    assert only["object"] == 9100 and only["arrival"] == [5, 6] and only["exit"] == [5, 2]
    assert only["exitFacing"] == [0, -1] and only["index"] == 0


def test_entrances_are_doors_each_with_its_own_arrival_and_exit():
    section = {"id": "a", "entrances": [door(0, arrival=[5, 6], exit=[5, 2]), door(1, arrival=[9, 9], exit=[9, 12])]}
    first, second = S.doors(section)
    assert (first["index"], second["index"]) == (0, 1)
    assert second["arrival"] == [9, 9] and second["exit"] == [9, 12] and second["object"] == 9101
    with pytest.raises(S.SourceError):
        S.doors({"id": "b", "entrances": [door(0)]})  # no arrival or exit
    with pytest.raises(S.SourceError):
        S.doors({**section, "entrance": door(2), "arrival": [1, 1], "exit": [1, 1]})


def design_of(*sections, passages=()):
    return {"schema": "eloria-landfall-underground-v1", "map": {"id": "m", "name": "M", "alias": "M", "cells": 100},
            "sections": list(sections), **({"passages": list(passages)} if passages else {})}


def test_passages_give_each_end_its_own_object_and_a_doorless_section_its_arrival():
    a = {"id": "a", "entrances": [door(0, arrival=[5, 6], exit=[5, 2])], "nodes": [], "rooms": [[5, 5, 4, 4]]}
    b = {"id": "b", "nodes": [], "rooms": [[50, 50, 4, 4]]}
    passage = {"object": 9200, "art": "crawl",
               "ends": [{"section": "a", "tile": [7, 7], "arrival": [6, 6]},
                        {"section": "b", "tile": [50, 52], "arrival": [50, 50], "art": "flooded", "object": 9250}]}
    design = design_of(a, b, passages=[passage])
    (normal,) = S.passages(design)
    assert [e["object"] for e in normal["ends"]] == [9200, 9250]
    assert [e["art"] for e in normal["ends"]] == ["crawl", "flooded"]
    assert normal["ends"][0]["to"] == "b" and normal["ends"][1]["to"] == "a"
    assert S.primary_arrival(design, b) == [50, 50] and S.primary_exit(design, b) == [50, 52]
    assert [kind for kind, _, _ in S.arrivals(design, a)] == ["door", "passage"]
    assert S.check(design)
    # by default the second end takes the next id
    del passage["ends"][1]["object"]
    assert [e["object"] for e in S.passages(design)[0]["ends"]] == [9200, 9201]


def test_check_refuses_an_unreached_section_a_reused_id_and_a_bad_vein():
    a = {"id": "a", "entrances": [door(0, arrival=[5, 6], exit=[5, 2])], "nodes": [[9100, "Coal", 1, 1]]}
    with pytest.raises(S.SourceError):  # a node reusing the door's id
        S.check(design_of(a))
    a["nodes"] = [[1, "Coal", 1, 1], [2, "Coal", 1, 2]]
    with pytest.raises(S.SourceError):  # nothing reaches b
        S.check(design_of(a, {"id": "b", "nodes": []}))
    a["veins"] = [{"resource": "Iron Ore", "nodes": [1, 2]}]
    with pytest.raises(S.SourceError):  # the vein names Coal nodes as Iron Ore
        S.check(design_of(a))
    a["veins"] = [{"resource": "Coal", "nodes": [1, 2]}]
    assert S.check(design_of(a)) and S.wall_nodes(a) == {1, 2}
    with pytest.raises(S.SourceError):  # both ends in one section
        S.passages(design_of(a, passages=[{"object": 5, "ends": [{"section": "a", "tile": [1, 1], "arrival": [1, 1]}] * 2}]))


def test_the_source_writer_reproduces_the_hand_laid_out_file():
    raw = SOURCE.read_bytes()
    design = json.loads(raw)
    assert S.dump(design).encode("utf-8") == raw
    annotated = copy.deepcopy(design)
    for section in annotated["sections"]:
        section["_ends"] = []
    assert S.dump(annotated).encode("utf-8") == raw
    lines = S.dump(design_of({"id": "a", "name": "A", "style": "mine", "danger": "d",
                              "entrances": [door(0, arrival=[5, 6], exit=[5, 2]), door(1, arrival=[9, 9], exit=[9, 12])],
                              "rooms": [[5, 5, 4, 4]], "links": [], "nodes": [], "spawns": []},
                             passages=[{"object": 1, "art": "crawl", "ends": []}])).splitlines()
    assert sum('"marker": "fakemap--door-' in line for line in lines) == 2
    assert all(line.count('"marker"') <= 1 for line in lines)
    assert any(line.strip().startswith('{"object": 1') for line in lines)


# --- build and publish ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not SERVER:
        pytest.skip("set ELORIA_SERVER_ROOT to a server checkout")
    sys.path.insert(0, str(Path(SERVER)))
    sys.path.insert(0, str(Path(SERVER) / "tools"))
    import build_underground as B
    import underground_authoring as A
    root = tmp_path_factory.mktemp("platform")
    cells = B.CELLS
    alpha = {"id": "alpha", "name": "Alpha Mine", "style": "mine", "danger": "Safe",
             "entrances": [door(0, arrival=[40, 40], exit=[40, 37]), door(1, arrival=[64, 42], exit=[64, 45])],
             "rooms": [[40, 40, 9, 8], [64, 42, 8, 8]], "links": [[0, 1, 5]], "nodeClearance": 1.4,
             "props": [], "nodes": [], "spawns": []}
    beta = {"id": "beta", "name": "Beta Pocket", "style": "cenote", "danger": "Damp", "rooms": [[40, 100, 9, 8]],
            "links": [], "props": [], "nodes": [], "spawns": []}
    design = {"schema": "eloria-landfall-underground-v1",
              "map": {"id": "landfall_insides", "name": "Test Underground", "alias": "TU", "cells": cells},
              "sections": [alpha, beta]}
    B.annotate(design, strict=False)
    grids = A._grids(design)
    one = A.passage_end(design, "alpha", [73, 42], "stairs", grids)
    two = A.passage_end(design, "beta", [40, 109], "flooded", grids)
    design["passages"] = [{"object": 9300, "art": "stairs",
                           "ends": [{k: one[k] for k in ("section", "tile", "arrival", "facing")},
                                    {**{k: two[k] for k in ("section", "tile", "arrival", "facing")}, "art": "flooded"}]}]
    B.annotate(design)
    A.vein(design, "alpha", "Coal", [30, 40], 3, [9401, 9402, 9403], grids=A._grids(design))
    checkout = root / "checkout"
    source = checkout / "eloria-assets/maps/continent-v2/_continent_v2/content/underground.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(S.dump(design).encode("utf-8"))
    package = root / "maps/continent-v2/landfall_insides/client"
    summary = B.build(Path(SERVER), source=source, out=package, registry=False)
    return SimpleNamespace(B=B, A=A, root=root, checkout=checkout, source=source, package=package, summary=summary,
                           design=B.load_design(source))


def publish(built, source_bytes=None, rehash=False):
    """underground.attach on the built package with stand-in exterior bakes. `rehash` gives the package the new
    source's hash: for a change that is server content only (spawns), which leaves the package as built."""
    import underground as U
    if source_bytes is not None:
        built.source.write_bytes(source_bytes)
    if rehash:
        manifest = built.package / "world.json"
        doc = json.loads(manifest.read_bytes())
        doc["provenance"]["sourceSha256"] = hashlib.sha256(built.source.read_bytes()).hexdigest()
        manifest.write_bytes((json.dumps(doc, indent=2) + "\n").encode("utf-8"))
    design = json.loads(built.source.read_bytes())
    markers = [{"id": d["marker"], "serverTile": d["tile"], "role": "underground_entrance"}
               for s in design["sections"] for d in S.doors(s)]
    ctx = SimpleNamespace(
        checkout=built.checkout, maps_root=built.root / "maps",
        bakes={"fakemap": SimpleNamespace(doc={"gameplay": {"runtimePoints": markers}})},
        frames={"fakemap": SimpleNamespace(continent=lambda x, y: (float(x), float(y)))},
        packages={"fakemap": {"polygon": [[0, 0], [400, 0], [400, 400], [0, 400]],
                              "grid": SimpleNamespace(walkable=lambda x, y: True)}},
        server=SimpleNamespace(base_resources={"Coal", "Iron Ore"},
                               creatures={"test_mole": SimpleNamespace(raw={"model": "final"},
                                                                   footprint=SimpleNamespace(is_single_tile=True))}))
    pub = SimpleNamespace(nodes=[], interactives=[], reached={"fakemap": np.ones((400, 400), dtype=bool)},
                          regions=["fakemap"], files={n: b"" for n in ("maps.txt", "spawns.txt", "harvesting.txt",
                                                                       "interactives.txt")})
    U.attach(ctx, pub)
    return pub


def test_build_writes_every_door_and_passage_end_into_the_package(built):
    manifest = json.loads((built.package / "world.json").read_text(encoding="utf-8"))
    assert built.summary["doors"] == 2 and built.summary["passages"] == 1 and built.summary["veinNodes"] == 3
    portals = {p["id"]: p for p in manifest["portals"]}
    assert set(portals) == {"alpha-exit", "alpha-exit1", "alpha-passage0-0", "beta-passage0-1"}
    assert portals["alpha-exit1"]["objectId"] == 9101 and portals["alpha-exit1"]["serverTile"] == [64, 45]
    there = portals["alpha-passage0-0"]
    assert there["destinationMap"] == "landfall_insides" and there["destinationSection"] == "beta"
    assert there["destinationTile"] == built.design["passages"][0]["ends"][1]["arrival"]
    # the beta pocket has no door: its spawn point is its passage end's arrival
    beta = next(s for s in manifest["spawnPoints"] if s["section"] == "beta")
    assert beta["serverTile"] == built.design["passages"][0]["ends"][1]["arrival"]
    # each mouth is drawn in its section's rock, styled, solid and cut away like its wall
    walls = {w["node"]: w for w in manifest["cutaway"]["walls"]}
    mouths = [name for name in walls if "_mouth" in name]
    assert any(n.startswith("Build_alpha_mouth0_") for n in mouths) and any(n.startswith("Build_beta_mouth0_") for n in mouths)
    assert all(walls[n]["section"] == n.split("_")[1] for n in mouths)
    assert set(mouths) <= set(manifest["collision"]["nodeNames"])


def test_wall_veins_stand_one_tile_into_the_rock_and_face_the_room(built):
    B = built.B
    alpha = next(s for s in built.design["sections"] if s["id"] == "alpha")
    faces = B.vein_faces(alpha)
    raw = (built.package / "collision.bin").read_bytes()
    width = int.from_bytes(raw[8:12], "little")
    half = np.frombuffer(raw[16:], dtype=np.uint8).reshape(width, width)
    coarse = half.reshape(width // 2, 2, width // 2, 2).all(axis=(1, 3))
    assert set(faces) == {9401, 9402, 9403}
    for oid, _res, x, y in alpha["nodes"]:
        face = faces[oid]
        assert not coarse[y, x] and any(coarse[y + dy, x + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        assert face["distance"] <= B.VEIN_FACE_MAX and face["inset"] == pytest.approx(face["distance"] + B.SEAM_SINK)
        # the yaw turns +Z toward the open floor: one step from the tile along it is walkable
        sx, sz = np.sin(np.radians(face["yaw"])), np.cos(np.radians(face["yaw"]))
        tx, ty = int(np.floor(x + .5 + sx * 1.5)), int(np.floor(y + .5 - sz * 1.5))
        assert coarse[ty, tx]
    # the vein nodes are three contiguous rim tiles (one eight-way connected run)
    tiles = {(x, y) for _, _, x, y in alpha["nodes"]}
    seen, stack = set(), [next(iter(tiles))]
    while stack:
        a = stack.pop()
        seen.add(a)
        stack += [b for b in tiles - seen if max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1]
    assert seen == tiles


def test_publication_rows_for_every_door_and_passage_end(built):
    pub = publish(built)
    rows = pub.underground.portals
    doors = [r for r in rows if r[0] == "fakemap"]
    assert [r[1] for r in doors] == [9100, 9101]
    passages = [r for r in rows if r[0] == r[4] == "landfall_insides" and r[1] in (9300, 9301)]
    ends = built.design["passages"][0]["ends"]
    assert passages == [["landfall_insides", 9300, *ends[0]["tile"], "landfall_insides", *ends[1]["arrival"]],
                        ["landfall_insides", 9301, *ends[1]["tile"], "landfall_insides", *ends[0]["arrival"]]]
    text = pub.files["interactives.txt"].decode()
    assert "A way leads on into Beta Pocket. Damp." in text and "A way leads on into Alpha Mine. Safe." in text
    assert pub.underground.rows == {"nodes": 3, "spawns": 0, "interactives": 6}
    sections = {s["id"]: s for s in pub.underground.metadata["sections"]}
    assert len(sections["alpha"]["doors"]) == 2 and "doors" not in sections["beta"]
    assert sections["beta"]["arrival"] == ends[1]["arrival"] and len(sections["beta"]["passageEnds"]) == 1


def test_publication_refuses_an_encounter_at_a_passage_arrival_and_a_passage_into_rock(built):
    raw = built.source.read_bytes()
    manifest = (built.package / "world.json").read_bytes()
    try:
        design = json.loads(raw)
        beta = design["sections"][1]
        x, y = design["passages"][0]["ends"][1]["arrival"]
        beta["spawns"] = [["test_mole", x, y, 2]]
        with pytest.raises(ValueError, match="too close to a safe entry"):
            publish(built, S.dump(design).encode("utf-8"), rehash=True)
    finally:
        built.source.write_bytes(raw)
        (built.package / "world.json").write_bytes(manifest)
    # a source the package was not built from is refused before any rule
    design = json.loads(raw)
    design["passages"][0]["ends"][0]["tile"] = [2, 2]
    try:
        with pytest.raises(ValueError):
            publish(built, S.dump(design).encode("utf-8"))
    finally:
        built.source.write_bytes(raw)


def test_archetypes_hit_their_bands(built):
    A, B = built.A, built.B
    sections = []
    pieces = {"pocket": A.pocket(100, 300, tiles=300, seed=1),
              "strip": A.strip_tunnel([150, 300], [260, 310], width=4, chambers=4, seed=2),
              "looped": A.looped_cavern(400, 300, columns=4, rows=4, spacing=15, seed=3),
              "mine": A.branching_mine([500, 260], 90, length=90, alcoves=8, seed=4)}
    for index, (name, piece) in enumerate(pieces.items()):
        sections.append({"id": name, "name": name, "style": "mine", "danger": "", "rooms": piece["rooms"],
                         "links": piece["links"], "props": [], "nodes": [], "spawns": [],
                         "entrances": [door(index, arrival=[int(piece["rooms"][0][0]), int(piece["rooms"][0][1])],
                                            exit=[int(piece["rooms"][0][0]), int(piece["rooms"][0][1])])]})
    design = B.annotate({"schema": "x", "map": {"id": "t", "name": "t", "alias": "t", "cells": B.CELLS},
                         "sections": sections})
    grids = A._grids(design)
    measured = {name: A.measure(design, name, grids) for name in pieces}
    assert 150 <= measured["pocket"]["walkableTiles"] <= 450 and measured["pocket"]["islands"] == 0
    assert measured["strip"]["aspect"] >= 3 and 0.1 <= measured["strip"]["corridorShare"] <= 0.45
    assert 8 <= measured["looped"]["islands"] <= 30
    alcoves = pieces["mine"]["anchors"]["alcoves"]
    assert len(alcoves) == 8 and measured["mine"]["walkableTiles"] > 500 and measured["mine"]["aspect"] >= 2
    rims = A.rim(design, "mine", grids)
    assert rims and A.suggest_anchors(design, "mine", 4, grids=grids)


# --- several interior sources: the Landfall town's building rooms beside the caves (2026-10-27) ------------------------

TOWN_BUILDER = b"# a stand-in for build_town_interiors.py: these tests hold only its hash\n"
OPEN = {"polygon": [[0, 0], [400, 0], [400, 400], [0, 400]]}


def building_door(tile, back, arrival, exit_, **extra):
    """A building door on fakemap: no marker, painted on the facade two tiles behind its tile."""
    return {"map": "fakemap", "kind": "building", "object": extra.pop("object"), "tile": list(tile),
            "position": [tile[0] + .5, 0.0, tile[1] + 2.5], "returnTile": list(back), "arrival": list(arrival),
            "exit": list(exit_), **extra}


def test_a_building_door_reads_without_a_marker_and_its_kind_is_checked():
    plain = {k: v for k, v in door(0).items() if k != "marker"}
    shop = {"id": "shop", "entrances": [{**plain, "kind": "building", "arrival": [5, 6], "exit": [5, 2],
                                         "label": "The Unlit Boat", "exitLabel": "The avenue"}]}
    (only,) = S.doors(shop)
    assert only["kind"] == "building" and "marker" not in only and only["label"] == "The Unlit Boat"
    with pytest.raises(S.SourceError):  # a cave door still needs its marker
        S.doors({"id": "cave", "entrances": [{**plain, "arrival": [5, 6], "exit": [5, 2]}]})
    with pytest.raises(S.SourceError):  # an unknown kind
        S.doors({"id": "x", "entrances": [{**plain, "kind": "tower", "arrival": [5, 6], "exit": [5, 2]}]})


@pytest.fixture(scope="module")
def town(built, tmp_path_factory):
    """The built caves and a town beside them, in a checkout of their own: the town's package is the built package
    copied as landfall_town (its geometry serves the rules as well as any), its source the caves' sections retold as a
    tavern and its upstairs: two building doors (no marker; a label, an exit label, one a category), the stairs between
    them, a person and a notice. Its provenance names a stand-in build_town_interiors.py, kept with the real
    build_underground.py in a stand-in builders' folder (underground.HERE)."""
    import shutil
    root = tmp_path_factory.mktemp("town")
    here = root / "builders"
    here.mkdir()
    (here / "build_underground.py").write_bytes((HERE / "build_underground.py").read_bytes())
    (here / "build_town_interiors.py").write_bytes(TOWN_BUILDER)
    checkout = root / "checkout"
    content = checkout / "eloria-assets/maps/continent-v2/_continent_v2/content"
    content.mkdir(parents=True)
    (content / "underground.json").write_bytes(built.source.read_bytes())
    design = json.loads(built.source.read_bytes())
    design["schema"] = "eloria-landfall-town-v1"
    design["map"] = {**design["map"], "id": "landfall_town", "name": "Landfall Town", "alias": "LFT"}
    tavern, upstairs = design["sections"]
    first, second = tavern["entrances"]
    # a post and a notice on open floor in the taproom, their rings open, clear of the ways in (the built grid)
    raw = (built.package / "collision.bin").read_bytes()
    width = int.from_bytes(raw[8:12], "little")
    coarse = np.frombuffer(raw[16:], dtype=np.uint8).reshape(width, width)
    coarse = coarse.reshape(width // 2, 2, width // 2, 2).all(axis=(1, 3))
    ways = [first["arrival"], first["exit"], second["arrival"], second["exit"]]
    clear = [(x, y) for y in range(34, 47) for x in range(33, 48)
             if coarse[y - 2:y + 3, x - 2:x + 3].all() and min(max(abs(x - a), abs(y - b)) for a, b in ways) >= 3]
    post, notice = list(clear[0]), list(clear[-1])
    tavern.update(name="The Unlit Boat", style="tavern", danger="Open to all", nodes=[], spawns=[],
                  entrances=[building_door([30, 10], [30, 5], first["arrival"], first["exit"], object=59201,
                                           category="tavern", label="The Unlit Boat", exitLabel="The avenue"),
                             building_door([40, 10], [40, 5], second["arrival"], second["exit"], object=59202,
                                           label="The yard door", exitLabel="The yard")],
                  npcs=[{"name": "Corran Orl", "role": "shop", "occupation": "Innkeeper", "actorType": 301,
                         "facing": "S", "tile": post, "greeting": "Welcome in."}],
                  interactives=[{"object": 59251, "tile": notice, "role": "information",
                                 "text": "A slate of the day's suppers."}])
    tavern.pop("veins", None)
    upstairs.update(name="The Unlit Boat, upstairs", style="tavern", danger="Guests only", nodes=[], spawns=[])
    design["passages"][0]["object"] = 59221
    maps = built.root / "maps"
    package = maps / "continent-v2/landfall_town/client"
    shutil.copytree(built.package, package)
    return SimpleNamespace(root=root, here=here, checkout=checkout, maps=maps, package=package,
                           source=content / "landfall_town.json", design=design, post=post, notice=notice)


def write_town(town, design, builder="build_town_interiors.py"):
    """Write the town source and give the town package its hash and `builder`'s."""
    town.source.write_bytes(S.dump(design).encode("utf-8"))
    manifest = town.package / "world.json"
    doc = json.loads(manifest.read_bytes())
    doc["provenance"] = {"source": "_continent_v2/content/landfall_town.json",
                         "sourceSha256": hashlib.sha256(town.source.read_bytes()).hexdigest(),
                         "builder": f"_continent_v2/{builder}",
                         "builderSha256": hashlib.sha256((town.here / builder).read_bytes()).hexdigest()}
    manifest.write_bytes((json.dumps(doc, indent=2) + "\n").encode("utf-8"))


def publish_both(town, monkeypatch, design=None, *, blocked=(), unreached=(), runtime=(), people=(), exterior=(),
                 names=(), builder="build_town_interiors.py", rebuild=True):
    """underground.attach over both sources with the stand-in fakemap: `blocked` tiles are closed on its grid,
    `unreached` ones outside its reach; `runtime` adds bake runtime points, `people` isle NPC posts, `exterior` isle
    interactives, `names` base npcs.txt names. The town source is read with underground_source (the town reader's
    format), and the stand-in builders' folder holds the builders. `rebuild` False leaves the package's provenance as
    it is (a builder changed since the build)."""
    import underground as U
    cave, building = U.SOURCES
    monkeypatch.setattr(U, "SOURCES", (cave, SimpleNamespace(**{**vars(building), "reader": "underground_source"})))
    monkeypatch.setattr(U, "HERE", town.here)
    if rebuild:
        write_town(town, copy.deepcopy(town.design) if design is None else design, builder)
    caves = json.loads((town.checkout / U.SOURCE).read_bytes())
    markers = [{"id": d["marker"], "serverTile": d["tile"], "role": "underground_entrance", "objectId": d["object"]}
               for s in caves["sections"] for d in S.doors(s)] + list(runtime)
    reached = np.ones((400, 400), dtype=bool)
    for x, y in unreached:
        reached[y, x] = False
    closed = set(blocked)
    ctx = SimpleNamespace(
        checkout=town.checkout, maps_root=town.maps,
        bakes={"fakemap": SimpleNamespace(doc={"gameplay": {"runtimePoints": markers}})},
        frames={"fakemap": SimpleNamespace(continent=lambda x, y: (float(x), float(y)),
                                           tile=lambda x, z: (int(x), int(z)))},
        packages={"fakemap": {**OPEN, "grid": SimpleNamespace(walkable=lambda x, y: (x, y) not in closed)}},
        server=SimpleNamespace(base_resources={"Coal", "Iron Ore"}, npc_lines={n.casefold(): [] for n in names},
                               creatures={"test_mole": SimpleNamespace(raw={"model": "final"},
                                                                   footprint=SimpleNamespace(is_single_tile=True))}))
    pub = SimpleNamespace(nodes=[], interactives=list(exterior), reached={"fakemap": reached}, regions=["fakemap"],
                          new_people=list(people), rehomed=[],
                          files={n: b"" for n in ("maps.txt", "spawns.txt", "harvesting.txt", "npcs.txt",
                                                  "interactives.txt")})
    U.attach(ctx, pub)
    return pub


def edited(town, change):
    design = copy.deepcopy(town.design)
    change(design)
    return design


def test_two_sources_publish_side_by_side_and_the_caves_rows_do_not_move(built, town, monkeypatch):
    import underground as U
    caves = publish(built)
    pub = publish_both(town, monkeypatch)
    assert [u.region for u in pub.interiors] == ["landfall_insides", "landfall_town"]
    assert pub.underground.region == "landfall_insides" and pub.underground.rows == caves.underground.rows
    assert pub.vendor_regions == ["fakemap", "landfall_insides", "landfall_town"]
    for name, data in pub.files.items():
        # the caves' rows first, byte for byte, then the town's under their own heading
        assert data.startswith(caves.files.get(name, b"")), name
        rest = data[len(caves.files.get(name, b"")):]
        assert not rest or rest.startswith(b"\r\n# Landfall town: building interiors.\r\n"), name
    keys = U.manifest_keys(pub)
    assert list(keys) == ["interiorMaps", "undergroundPortals", "undergroundRows", "buildingPortals", "buildingRows"]
    assert set(keys["interiorMaps"]) == {"landfall_insides", "landfall_town"}
    assert keys["undergroundPortals"] == caves.underground.portals
    assert all("landfall_town" in (row[0], row[4]) for row in keys["buildingPortals"])
    assert not any("landfall_town" in (row[0], row[4]) for row in keys["undergroundPortals"])
    assert keys["buildingRows"] == {"nodes": 0, "spawns": 0, "interactives": 7, "npcs": 1}
    assert keys["interiorMaps"]["landfall_town"]["kind"] == "building"
    assert "kind" not in keys["interiorMaps"]["landfall_insides"]
    assert [e["id"] for e in U.manifest_entries(pub)] == ["landfall_insides", "landfall_town"]
    # with the town source absent, only the caves publish, as they did before it
    assert U.manifest_keys(caves) == {"interiorMaps": {"landfall_insides": keys["interiorMaps"]["landfall_insides"]},
                                      "undergroundPortals": keys["undergroundPortals"],
                                      "undergroundRows": keys["undergroundRows"]}


def test_building_doors_people_and_notices_publish_their_labels(town, monkeypatch):
    pub = publish_both(town, monkeypatch)
    tavern = town.design["sections"][0]
    exit0, exit1 = (d["exit"] for d in tavern["entrances"])
    text = pub.files["interactives.txt"].decode()
    assert "fakemap | 59201 | 30 | 10 | portal | maps.txt | The Unlit Boat. Open to all." in text
    assert f"landfall_town | 59201 | {exit0[0]} | {exit0[1]} | portal | maps.txt | The avenue." in text
    assert "fakemap | 59202 | 40 | 10 | portal | maps.txt | The yard door. Open to all." in text
    assert f"landfall_town | 59202 | {exit1[0]} | {exit1[1]} | portal | maps.txt | The yard." in text
    assert "A way leads on into The Unlit Boat, upstairs. Guests only." in text
    (nx, ny), (px, py) = town.notice, town.post
    assert f"landfall_town | 59251 | {nx} | {ny} | information | notice | A slate of the day's suppers." in text
    npcs = pub.files["npcs.txt"].decode()
    assert (f"npc | Corran Orl | landfall_town | {px} | {py} | shop | actor_type=301,occupation=Innkeeper,facing=S | "
            "Welcome in.") in npcs
    maps = pub.files["maps.txt"].decode()
    assert "map | landfall_town | Landfall Town | maps/nymara/landfall_town.elm | LFT" in maps
    town_rows = next(u for u in pub.interiors if u.region == "landfall_town").portals
    assert ["fakemap", 59201, 30, 10, "landfall_town", *tavern["entrances"][0]["arrival"]] in town_rows
    assert ["landfall_town", 59201, *exit0, "fakemap", 30, 5] in town_rows


def test_a_building_door_on_a_blocked_or_unreached_tile_is_refused(town, monkeypatch):
    with pytest.raises(ValueError, match="not walkable"):
        publish_both(town, monkeypatch, blocked=[(30, 10)])
    with pytest.raises(ValueError, match="not walkable"):  # the return tile too
        publish_both(town, monkeypatch, blocked=[(40, 5)])
    with pytest.raises(ValueError, match="no clear approach"):
        publish_both(town, monkeypatch, blocked=[(31, 10)])
    with pytest.raises(ValueError, match="unreachable"):
        publish_both(town, monkeypatch, unreached=[(30, 10)])


def test_a_building_door_keeps_its_rules(town, monkeypatch):
    def door0(**change):
        return edited(town, lambda d: d["sections"][0]["entrances"][0].update(change))
    with pytest.raises(ValueError, match="map category"):
        publish_both(town, monkeypatch, door0(category="bakery"))
    with pytest.raises(ValueError, match="exitLabel"):
        publish_both(town, monkeypatch, door0(exitLabel=""))
    with pytest.raises(ValueError, match="painted point"):
        publish_both(town, monkeypatch, door0(position=[90.5, 0.0, 10.5]))
    with pytest.raises(ValueError, match="return tile is the door"):
        publish_both(town, monkeypatch, door0(returnTile=[30, 10]))
    with pytest.raises(ValueError, match="has no marker"):
        publish_both(town, monkeypatch, runtime=[{"id": "fakemap--boat", "serverTile": [30, 10],
                                                  "role": "underground_entrance", "objectId": 59201}])
    with pytest.raises(ValueError, match="NPC post"):
        publish_both(town, monkeypatch, people=[{"map": "fakemap", "tile": [30, 5], "name": "Nash"}])
    with pytest.raises(ValueError, match="already landfall_insides door"):  # on a cave door's tile
        publish_both(town, monkeypatch, door0(tile=[10, 10], position=[10.5, 0.0, 12.5], returnTile=[12, 5]))


def test_object_ids_are_unique_across_both_interiors_and_the_isles(town, monkeypatch):
    with pytest.raises(ValueError, match="already a door of landfall_insides"):
        publish_both(town, monkeypatch, edited(town, lambda d: d["passages"][0].update(object=9100)))
    with pytest.raises(ValueError, match="already a node of landfall_insides"):
        publish_both(town, monkeypatch,
                     edited(town, lambda d: d["sections"][0]["interactives"][0].update(object=9401)))
    with pytest.raises(ValueError, match="exterior object"):
        publish_both(town, monkeypatch, exterior=[{"map": "elsewhere", "object": 59251, "tile": [1, 1]}])


def test_each_package_is_held_to_the_builder_its_own_provenance_names(town, monkeypatch):
    with pytest.raises(ValueError, match="built by build_underground.py"):
        publish_both(town, monkeypatch, builder="build_underground.py")
    publish_both(town, monkeypatch)
    try:
        (town.here / "build_town_interiors.py").write_bytes(TOWN_BUILDER + b"# changed\n")
        with pytest.raises(ValueError, match="town interiors source or builder changed"):
            publish_both(town, monkeypatch, rebuild=False)
    finally:
        (town.here / "build_town_interiors.py").write_bytes(TOWN_BUILDER)
    # the helpers the town builder imports are pinned too (provenance.imports)
    publish_both(town, monkeypatch)
    manifest = town.package / "world.json"
    doc = json.loads(manifest.read_bytes())
    real = hashlib.sha256((town.here / "build_underground.py").read_bytes()).hexdigest()
    doc["provenance"]["imports"] = {"_continent_v2/build_underground.py": real}
    manifest.write_bytes(json.dumps(doc).encode("utf-8"))
    publish_both(town, monkeypatch, rebuild=False)
    doc["provenance"]["imports"] = {"_continent_v2/build_underground.py": "0" * 64}
    manifest.write_bytes(json.dumps(doc).encode("utf-8"))
    with pytest.raises(ValueError, match="build_underground.py, which build_town_interiors.py imports, changed"):
        publish_both(town, monkeypatch, rebuild=False)


def test_interior_people_and_notices_keep_clear_posts(town, monkeypatch):
    arrival = town.design["sections"][0]["entrances"][0]["arrival"]

    def person(**change):
        return edited(town, lambda d: d["sections"][0]["npcs"][0].update(change))

    def notice(**change):
        return edited(town, lambda d: d["sections"][0]["interactives"][0].update(change))
    with pytest.raises(ValueError, match="arrival"):  # a post closes its tile: on an arrival it bars the way in
        publish_both(town, monkeypatch, person(tile=list(arrival)))
    with pytest.raises(ValueError, match=r"post \[44, 33\]"):  # against the room's wall
        publish_both(town, monkeypatch, person(tile=[44, 33]))
    with pytest.raises(ValueError, match="already in npcs.txt"):
        publish_both(town, monkeypatch, names=["Corran Orl"])
    with pytest.raises(ValueError, match="actorType"):
        publish_both(town, monkeypatch, person(actorType=12))
    with pytest.raises(ValueError, match="stands on Corran Orl"):
        publish_both(town, monkeypatch, notice(tile=list(town.post)))
    with pytest.raises(ValueError, match="role"):
        publish_both(town, monkeypatch, notice(role="storage"))
    with pytest.raises(ValueError, match="no reached floor"):
        publish_both(town, monkeypatch, notice(tile=[5, 300]))


def test_publish_server_gives_a_smithy_station_its_trade(town, monkeypatch):
    """publish_server.station_targets on the rows underground.attach writes: a crafting station whose text names its
    trade, or that stands in the smithy, publishes that trade; a plain one keeps "crafting", a notice "notice"."""
    import publish_server as P

    def stations(style, text):
        def change(design):
            design["sections"][0]["style"] = style
            design["sections"][0]["interactives"][0].update(role="crafting_station", text=text)
        pub = publish_both(town, monkeypatch, edited(town, change))
        lines = pub.files["interactives.txt"].count(b"\r\n")
        P.station_targets(pub)
        assert pub.files["interactives.txt"].count(b"\r\n") == lines      # rewritten in place, never added
        return pub.files["interactives.txt"].decode()
    (nx, ny) = town.notice
    row = f"landfall_town | 59251 | {nx} | {ny} | crafting_station | "
    smith = "The forge is hot. Open your manufacture window to smith."
    assert f"\r\n{row}smithing | {smith}\r\n" in stations("smithy", smith)
    assert f"\r\n{row}smithing | An anvil by the hearth.\r\n" in stations("tavern", "An anvil by the hearth.")
    assert f"\r\n{row}smithing | A bench.\r\n" in stations("smithy", "A bench.")
    assert f"\r\n{row}crafting | A bench.\r\n" in stations("tavern", "A bench.")
    pub = publish_both(town, monkeypatch)
    before = pub.files["interactives.txt"]
    P.station_targets(pub)
    assert pub.files["interactives.txt"] == before and b"| information | notice | A slate" in before


# --- retarget_underground.py over both sources (2026-10-27) -------------------------------------------------------------


@pytest.fixture
def retarget_tree(tmp_path, monkeypatch):
    """A checkout for retarget_underground.py: a cave source (one cave door, one passage), a town source read by the
    real town_source.py (two building doors, a labelled stair), the town's package (the caves' is not built), and an
    objects.json holding a cave entrance, the caves' passage ends, a stale building door, a stale passage end and an
    unrelated record. Frames move every map two tiles east; every exterior tile is open and reached."""
    import retarget_underground as R
    import underground as U
    cave = design_of({"id": "a", "name": "Alpha Mine", "style": "mine", "danger": "Safe",
                      "entrances": [door(0, arrival=[5, 6], exit=[5, 2])], "rooms": [[5, 5, 4, 4]], "nodes": []},
                     {"id": "b", "name": "Beta Pocket", "style": "mine", "danger": "Damp", "rooms": [[50, 50, 4, 4]],
                      "nodes": []},
                     passages=[{"object": 9300, "art": "crawl", "ends": [{"section": "a", "tile": [7, 7], "arrival": [6, 6]},
                                                                         {"section": "b", "tile": [50, 52],
                                                                          "arrival": [50, 50]}]}])
    town = {"schema": "eloria-landfall-town-v1", "map": {"id": "landfall_town", "name": "Landfall Town", "alias": "LFT",
                                                         "cells": 324},
            "sections": [{"id": "tavern", "name": "The Unlit Boat", "style": "tavern", "danger": "Open to all",
                          "entrances": [building_door([30, 10], [30, 5], [40, 40], [40, 37], object=59201,
                                                      category="tavern", label="The Unlit Boat",
                                                      exitLabel="The avenue"),
                                        building_door([40, 10], [40, 5], [60, 40], [60, 37], object=59202,
                                                      label="The yard door", exitLabel="The yard")],
                          "rooms": [[40, 40, 8, 8]], "nodes": [], "spawns": []},
                         {"id": "upstairs", "name": "Upstairs", "style": "tavern", "danger": "Guests only",
                          "rooms": [[40, 100, 8, 8]], "nodes": [], "spawns": []}],
            "passages": [{"object": 59221, "art": "stairs_up",
                          "ends": [{"section": "tavern", "tile": [45, 45], "arrival": [44, 44],
                                    "label": "Upstairs: the guest rooms"},
                                   {"section": "upstairs", "tile": [45, 105], "arrival": [44, 104],
                                    "art": "stairs_down"}]}]}
    for d in town["sections"][0]["entrances"]:   # painted where the moved frame reads the door's tile
        d["position"] = [d["tile"][0] - 2 + .5, 0.0, d["tile"][1] + .5]
    sources = {"underground": tmp_path / "underground.json", "building": tmp_path / "landfall_town.json"}
    sources["underground"].write_bytes(S.dump(cave).encode("utf-8"))
    sources["building"].write_bytes((json.dumps(town, indent=1) + "\n").encode("utf-8"))
    here = tmp_path / "builders"
    here.mkdir()
    (here / "build_town_interiors.py").write_bytes(TOWN_BUILDER)
    checkout = tmp_path / "checkout"
    package = checkout / "eloria-assets/maps/continent-v2/landfall_town/client/world.json"
    package.parent.mkdir(parents=True)
    exits = [{"id": "tavern-exit", "objectId": 59201, "role": "portal", "serverTile": [40, 37],
              "destinationMap": "fakemap", "destinationTile": [1, 1], "label": "Out"},
             {"id": "tavern-passage0-0", "objectId": 59221, "role": "portal", "serverTile": [45, 45],
              "destinationMap": "landfall_town", "destinationTile": [44, 104], "label": "Up"}]
    package.write_bytes((json.dumps({"spawnPoints": [], "chambers": [], "portals": exits, "interactives": exits,
                                     "provenance": {"source": "_continent_v2/content/landfall_town.json",
                                                    "sourceSha256": "0" * 64,
                                                    "builder": "_continent_v2/build_town_interiors.py",
                                                    "builderSha256": hashlib.sha256(TOWN_BUILDER).hexdigest()}},
                                    indent=2) + "\n").encode("utf-8"))
    objects = checkout / "godot-client/data/world/objects.json"
    objects.parent.mkdir(parents=True)
    passage = {"passage": True, "height": 3.6, "radius": 1.6}
    objects.write_bytes((json.dumps({"schemaVersion": 1, "harvestables": {}, "interactives": {}, "authoredObjects": {
        "9100": {"entrance": True, "exteriorTile": [10, 10], "scene": "res://assets/world/underground/cave_mouth.glb",
                 "height": 3.6, "radius": 1.6, "label": "Old name"},
        "9300": {**passage, "label": "Beta Pocket"}, "9301": {**passage, "label": "Alpha Mine"},
        "59299": {"entrance": True, "building": True, "exteriorTile": [1, 1], "label": "Gone", "exitLabel": "Gone",
                  "height": 3.0, "radius": 1.2},
        "777": {**passage, "label": "Gone"}, "42": {"height": 1.0, "radius": 1.0}}}, indent=2) + "\n").encode("utf-8"))
    codes = np.ones((400, 400), dtype=np.uint16)
    reached = np.ones((400, 400), dtype=bool)

    class Grids:
        def __init__(self, *_args):
            pass

        def __call__(self, region):
            return codes, reached
    monkeypatch.setattr(R, "source_path", lambda spec: sources[spec.kind])
    monkeypatch.setattr(R, "HERE", here)
    monkeypatch.setattr(R, "Grids", Grids)
    monkeypatch.setattr(R.F, "load_source", lambda region, checkout: SimpleNamespace(
        tile=lambda x, z: (int(np.floor(x)) + 2, int(np.floor(z))), local=lambda tx, ty: (tx - 2 + .5, ty + .5)))
    return SimpleNamespace(R=R, U=U, checkout=checkout, package=package, objects=objects, sources=sources,
                           codes=codes, reached=reached)


def test_retarget_writes_building_door_records_and_keeps_every_sources_records(retarget_tree):
    t = retarget_tree
    outputs, changed, unbuilt = t.R.retarget(t.checkout)
    assert unbuilt == ["m"]                                  # the caves' package is not in this checkout
    # the cave door follows its marker; the building doors keep their tiles: the town source is written unchanged
    cave = json.loads(outputs[t.sources["underground"]])
    assert cave["sections"][0]["entrances"][0]["tile"] == [12, 20]
    assert cave["sections"][0]["entrances"][0]["returnTile"] == [12, 15]
    assert outputs[t.sources["building"]] == t.sources["building"].read_bytes()
    authored = json.loads(outputs[t.objects])["authoredObjects"]
    assert authored["9100"]["exteriorTile"] == [12, 20] and authored["9100"]["label"] == "Alpha Mine"
    assert authored["59201"] == {"entrance": True, "building": True, "exteriorTile": [30, 10],
                                 "modelOffset": [0.0, 0.0, 0.0], "label": "The Unlit Boat", "exitLabel": "The avenue",
                                 "exitOffset": [0.0, 0.0, 1.0], "category": "tavern", "height": 3.0, "radius": 1.2}
    assert "category" not in authored["59202"] and "scene" not in authored["59202"]
    # every source's passage ends keep their records; ones no source has any longer go, and so does a stale door
    assert {k for k, r in authored.items() if r.get("passage")} == {"9300", "9301", "59221", "59222"}
    # a labelled stair end is named by its own label, as the package and the server name it; an unlabelled end by
    # the section it leads into, as every cave passage end is
    assert authored["59221"]["label"] == "Upstairs: the guest rooms" and authored["59222"]["label"] == "The Unlit Boat"
    assert authored["9300"]["label"] == "Beta Pocket" and authored["9301"]["label"] == "Alpha Mine"
    assert "59299" not in authored and "777" not in authored and authored["42"] == {"height": 1.0, "radius": 1.0}
    # the town package: its exit leads to the door's return tile under the door's exit label
    package = json.loads(outputs[t.package])
    exit_ = next(p for p in package["portals"] if p["objectId"] == 59201)
    assert exit_["destinationTile"] == [30, 5] and exit_["label"] == "The avenue"
    # a labelled stair keeps its own label, as build_town_interiors.py writes it
    assert next(p for p in package["portals"] if p["objectId"] == 59221)["label"] == "Upstairs: the guest rooms"
    assert package["provenance"]["sourceSha256"] == hashlib.sha256(t.sources["building"].read_bytes()).hexdigest()
    assert changed == 2      # the portal and the interactive of door 59201


def test_retarget_refuses_a_building_door_on_closed_ground_and_a_taken_record(retarget_tree):
    t = retarget_tree
    t.codes[10, 30] = 0
    with pytest.raises(SystemExit, match="not walkable"):
        t.R.retarget(t.checkout)
    t.codes[10, 30] = 1
    t.reached[5, 40] = False
    with pytest.raises(SystemExit, match="not reached"):
        t.R.retarget(t.checkout)
    t.reached[5, 40] = True
    t.codes[10, 31] = 0
    with pytest.raises(SystemExit, match="blocked neighbours"):
        t.R.retarget(t.checkout)
    t.codes[10, 31] = 1
    objects = json.loads(t.objects.read_bytes())
    objects["authoredObjects"]["59202"] = {"entrance": True, "exteriorTile": [3, 3], "scene": "res://x.glb"}
    t.objects.write_bytes(json.dumps(objects).encode("utf-8"))
    with pytest.raises(SystemExit, match="another object's record"):
        t.R.retarget(t.checkout)


def test_retarget_puts_a_building_doors_pick_on_its_painted_door_at_both_ends(retarget_tree):
    """modelOffset: the painted point minus the door tile's centre (the exterior's metres); exitOffset: the interior
    street door one tile beyond the exit, the way exitFacing points (tile +y is world -Z)."""
    t = retarget_tree
    town = json.loads(t.sources["building"].read_bytes())
    first, second = town["sections"][0]["entrances"]
    first["position"] = [30 - 2 + .5 + .7, 121.49, 10 + .5 - 1.3]    # 0.7 m east of the tile's centre, 1.3 m behind
    first["exitFacing"] = [0, -1]
    second["exitFacing"] = [-1, 0]
    t.sources["building"].write_bytes((json.dumps(town, indent=1) + "\n").encode("utf-8"))
    outputs, _, _ = t.R.retarget(t.checkout)
    authored = json.loads(outputs[t.objects])["authoredObjects"]
    assert authored["59201"]["modelOffset"] == [0.7, 0.0, -1.3] and authored["59201"]["exitOffset"] == [0.0, 0.0, 1.0]
    assert authored["59202"]["modelOffset"] == [0.0, 0.0, 0.0] and authored["59202"]["exitOffset"] == [-1.0, 0.0, 0.0]
    assert list(authored["59201"]) == ["entrance", "building", "exteriorTile", "modelOffset", "label", "exitLabel",
                                       "exitOffset", "category", "height", "radius"]


def test_retarget_map_touches_one_interior_only(retarget_tree):
    """--map landfall_town writes the town's source, package and records and nothing of the caves' (their source is
    still read for its ids); a stale record no source owns is listed, not dropped. --map m (the caves) leaves the
    town's records alone. An unknown map is refused."""
    t = retarget_tree
    before = json.loads(t.objects.read_bytes())["authoredObjects"]
    notes = {}
    outputs, changed, unbuilt = t.R.retarget(t.checkout, only="landfall_town", notes=notes)
    assert t.sources["underground"] not in outputs and unbuilt == [] and changed == 2
    assert set(outputs) == {t.sources["building"], t.package, t.objects}
    authored = json.loads(outputs[t.objects])["authoredObjects"]
    for key in ("9100", "9300", "9301", "42"):           # the caves' door and passage ends, and an unrelated record
        assert authored[key] == before[key]
    assert authored["59201"]["building"] and authored["59221"]["label"] == "Upstairs: the guest rooms"
    assert notes == {"orphans": ["777", "59299"]} and authored["59299"] == before["59299"]
    notes = {}
    outputs, _, unbuilt = t.R.retarget(t.checkout, only="m", notes=notes)
    assert set(outputs) == {t.sources["underground"], t.objects} and unbuilt == ["m"]
    authored = json.loads(outputs[t.objects])["authoredObjects"]
    assert authored["9100"]["exteriorTile"] == [12, 20] and authored["9100"]["label"] == "Alpha Mine"
    assert "59201" not in authored and "59221" not in authored and notes == {"orphans": ["777", "59299"]}
    with pytest.raises(SystemExit, match="no interior source authors it"):
        t.R.retarget(t.checkout, only="nowhere")
    # a clash with the interior --map leaves alone is still refused
    town = json.loads(t.sources["building"].read_bytes())
    town["passages"][0]["object"] = 9300
    t.sources["building"].write_bytes(json.dumps(town).encode("utf-8"))
    with pytest.raises(SystemExit, match="another interior's too"):
        t.R.retarget(t.checkout, only="m")


def test_retarget_check_with_map_reports_and_writes_nothing(retarget_tree, monkeypatch, capsys):
    t = retarget_tree
    before = {path: path.read_bytes() for path in (t.objects, t.package, *t.sources.values())}
    monkeypatch.setattr(sys, "argv", ["retarget_underground.py", "--check", "--checkout", str(t.checkout),
                                      "--map", "landfall_town"])
    assert t.R.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert {Path(p).resolve() for p in report["stale"]} == {t.objects.resolve(), t.package.resolve()}
    assert report["orphans"] == ["777", "59299"]
    assert {path: path.read_bytes() for path in before} == before


def test_retarget_writes_pick_only_records_for_interior_interactives_and_stair_offsets(retarget_tree):
    """An interior interactive gets a pick-only record (no ring, no model) on the prop its `at` names: modelOffset from
    the tile's centre, the prop's packaged size (reused-scenery.json) unless the source gives one, its short label; a
    drawn stair's end carries the offset its package portal records. Records no source has any longer go."""
    t = retarget_tree
    town = json.loads(t.sources["building"].read_bytes())
    tavern = town["sections"][0]
    tavern["props"] = [{"asset": "anvil_stump", "at": [41.5, 42.5], "yaw": 0, "scale": 2, "blockBox": [0.4, 0.4]}]
    tavern["interactives"] = [
        {"object": 59254, "tile": [43, 42], "role": "crafting_station", "text": "The forge is hot.", "label": "The anvil",
         "at": [41.5, 42.5], "target": "smithing"},
        {"object": 59251, "tile": [36, 40], "role": "information", "text": "Over the hearth: a painting.",
         "at": [34.6, 40.5], "height": 3.0, "radius": 0.9},
        {"object": 59252, "tile": [38, 38], "role": "information", "text": "A note. Read it."}]
    t.sources["building"].write_bytes((json.dumps(town, indent=1) + "\n").encode("utf-8"))
    scenery = t.checkout / t.R.SCENERY
    scenery.parent.mkdir(parents=True)
    scenery.write_text(json.dumps({"assets": [{"id": "anvil_stump", "bounds": [[-0.45, 0, -0.4], [0.45, 0.93, 0.4]]}]}),
                       encoding="utf-8")
    package = json.loads(t.package.read_bytes())
    package["portals"][1]["modelOffset"] = [0.0, 0.0, -2.7]
    t.package.write_bytes((json.dumps(package, indent=2) + "\n").encode("utf-8"))
    objects = json.loads(t.objects.read_bytes())
    objects["authoredObjects"]["59299"] = {"interactive": True, "pickOnly": True, "label": "Gone",
                                           "modelOffset": [0, 0, 0], "height": 1, "radius": 1}
    t.objects.write_bytes((json.dumps(objects, indent=2) + "\n").encode("utf-8"))
    outputs, _, _ = t.R.retarget(t.checkout)
    authored = json.loads(outputs[t.objects])["authoredObjects"]
    # the anvil: 1.5 m west and 0.5 m south (world +Z) of tile (43, 42)'s centre, its packaged size at scale 2
    assert authored["59254"] == {"interactive": True, "pickOnly": True, "label": "The anvil",
                                 "modelOffset": [-2.0, 0.0, 0.0], "height": 1.86, "radius": 0.9}
    assert list(authored["59254"]) == ["interactive", "pickOnly", "label", "modelOffset", "height", "radius"]
    # a picture on the wall: the source's own size; the label is the text's first clause when the source gives none
    assert authored["59251"] == {"interactive": True, "pickOnly": True, "label": "Over the hearth",
                                 "modelOffset": [-1.9, 0.0, 0.0], "height": 3.0, "radius": 0.9}
    assert authored["59252"]["modelOffset"] == [0.0, 0.0, 0.0] and authored["59252"]["label"] == "A note"
    assert (authored["59252"]["height"], authored["59252"]["radius"]) == (1.8, 0.8)
    assert "59299" not in authored
    # the stair's pick stands on its flight; the other end's portal records none
    assert authored["59221"]["modelOffset"] == [0.0, 0.0, -2.7] and "modelOffset" not in authored["59222"]
    # an interactive's id may not take another object's record
    objects["authoredObjects"]["59252"] = {"entrance": True, "exteriorTile": [3, 3], "scene": "res://x.glb"}
    t.objects.write_bytes(json.dumps(objects).encode("utf-8"))
    with pytest.raises(SystemExit, match="another object's record"):
        t.R.retarget(t.checkout)
