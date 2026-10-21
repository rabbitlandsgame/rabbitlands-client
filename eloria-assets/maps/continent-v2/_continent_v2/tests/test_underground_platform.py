"""The underground platform of pass 2 (2026-10-21): doors, passages, wall veins and the archetype helpers.

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_underground_platform.py -q

The source-format tests need nothing but this checkout. The build-and-publish test builds a two-section underground
from a synthetic source with the real builder (two doors, a doorless section reached by a passage, a wall vein) into a
temporary folder and runs underground.py's publication rules on it against stand-in exterior bakes; it needs the
server checkout named by ELORIA_SERVER_ROOT (its collision code and served-grid codec) and skips without it.
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
