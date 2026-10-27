"""tools/prepare_underground_scenery.py over several interiors (2026-10-27: the Landfall town's rooms beside the caves).

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_interior_scenery.py -q

The packager writes one scenery config per interior map (INTERIORS). The caves' config must come out as the
single-map packager wrote it, byte for byte; the town's lists only the pieces it places. Nothing here packages a model
or writes a file: the configs are computed in memory (scenery_config), and the town is a stand-in builder module.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

CHECKOUT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(CHECKOUT / "tools"))
import prepare_underground_scenery as P  # noqa: E402

CAVES = CHECKOUT / "godot-client/data/world/underground-scenery.json"
CAVE_SOURCE = CHECKOUT / "eloria-assets/maps/continent-v2/_continent_v2/content/underground.json"


def test_the_caves_config_is_the_single_map_packagers_byte_for_byte():
    """landfall_insides' config is what the packager wrote before it learnt several interiors. The committed file
    records the cave source's hash as it was when it was written (content/underground.json has since had creature
    rows moved, which no placement reads), so the comparison takes the current source's hash in its place."""
    config = P.scenery_config("landfall_insides")
    raw = CAVES.read_bytes()
    committed = json.loads(raw)
    current = hashlib.sha256(CAVE_SOURCE.read_bytes()).hexdigest()
    assert config["sourcePlanSha256"] == current
    assert P.config_bytes(config) == raw.replace(committed["sourcePlanSha256"].encode(), current.encode())
    assert list(config["assets"]) == list(P.SELECTION)
    assert P.INTERIORS["landfall_insides"]["config"] == "godot-client/data/world/underground-scenery.json"
    assert P.INTERIORS["landfall_town"]["config"] == "godot-client/data/world/town-scenery.json"


@pytest.fixture
def stand_in(tmp_path, monkeypatch):
    """A town interior read by a stand-in builder module: three placements, one a cave piece, one a town piece, one
    cut away with its wall."""
    plan = {"map": {"id": "landfall_town", "cells": 324}, "sections": [{"id": "tavern"}]}
    path = tmp_path / "landfall_town.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    items = [{"asset": "flower_cart", "x": 10.5, "y": 20.0, "height": 0, "yaw": 90, "scale": 1},
             {"asset": "barrel_stack", "x": 12.0, "y": 22.5, "height": 0, "yaw": 0, "scale": 0.8, "outward": [0, 1],
              "wall": True, "side": "north", "cutawayWall": "Build_tavern_north_lime_plaster"},
             {"asset": "barrel_stack", "x": 14.0, "y": 22.5, "height": 0, "yaw": 0, "scale": 1}]
    builder = ModuleType("stand_in_town_builder")
    builder.load_design = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    builder.dressing = lambda section: [dict(item) for item in items]
    builder.surfaces = lambda design: {"tavern": {"floor": {"texture": "authored"}}}
    monkeypatch.setitem(sys.modules, "stand_in_town_builder", builder)
    monkeypatch.setitem(P.INTERIORS, "landfall_town", {**P.INTERIORS["landfall_town"], "plan": str(path),
                                                       "builder": "stand_in_town_builder"})
    return items


def test_a_town_config_lists_the_pieces_it_places_and_keeps_its_frame(stand_in):
    config = P.scenery_config("landfall_town")
    assert config["map"] == "landfall_town" and config["harvestPresentation"] == {}
    # the caves' pieces before the town's, each once, and nothing it does not place
    assert config["assets"] == {"barrel_stack": "res://assets/world/underground/barrel_stack.glb",
                                "flower_cart": "res://assets/world/underground/flower_cart.glb"}
    first, second, third = config["placements"]
    assert first == {"asset": "flower_cart", "position": [10.5, 0, 304.0], "yaw": 90}       # z = cells - y
    # the wall it is cut away with travels (outward, and its own wall node); the builder's flag and side stay
    assert second == {"asset": "barrel_stack", "position": [12.0, 0, 301.5], "yaw": 0, "scale": 0.8,
                      "outward": [0, 1], "cutawayWall": "Build_tavern_north_lime_plaster"}
    assert list(second) == ["asset", "position", "yaw", "scale", "outward", "cutawayWall"]
    assert "scale" not in third
    assert config["surfaces"] == {"tavern": {"floor": {"texture": "authored"}}}


def test_an_unpackaged_piece_and_a_town_piece_in_the_caves_list_are_refused(stand_in, monkeypatch):
    stand_in.append({"asset": "grand_piano", "x": 1, "y": 1, "height": 0, "yaw": 0, "scale": 1})
    with pytest.raises(ValueError, match="grand_piano"):
        P.scenery_config("landfall_town")
    stand_in.pop()
    monkeypatch.setitem(P.INTERIORS, "landfall_town", {**P.INTERIORS["landfall_town"], "assets": "all"})
    with pytest.raises(ValueError, match="flower_cart"):
        P.scenery_config("landfall_town")


def test_every_town_piece_is_a_reviewed_kit_model_and_named_once():
    from video_motion.asset import read_glb
    assert not set(P.TOWN_SELECTION) & set(P.SELECTION)
    for name, (region, slug, measure, size) in P.TOWN_SELECTION.items():
        source = CHECKOUT / P.KITS.get(region, f"godot-client/world_authoring/regions/{region}/assets/prototypes") / \
            f"kit-{slug}.glb"
        assert source.is_file(), name
        document, _blob = read_glb(source)
        assert "prepare_meshy_kit" in document["asset"].get("generator", ""), name
        assert measure in ("height", "length") and 0 < size <= 6, name


def test_a_one_interior_run_records_what_a_whole_run_would():
    """--map packages only the interior's TOWN_SELECTION pieces; reused-scenery.json then lists the SELECTION rows'
    records as they stand and every placed town piece in TOWN_SELECTION order, fresh or as on file: a whole run's list."""
    cave = [{"id": name, "sha256": "cave"} for name in list(P.SELECTION)[:3]]
    town = list(P.TOWN_SELECTION)
    on_file = cave + [{"id": town[5], "sha256": "old"}, {"id": town[0], "sha256": "stale"}]
    fresh = {town[2]: {"id": town[2], "sha256": "new"}, town[0]: {"id": town[0], "sha256": "new"}}
    records = P.scenery_records(on_file, fresh, {town[0], town[2], town[5], "barrel_stack"})
    assert records == cave + [{"id": town[0], "sha256": "new"}, {"id": town[2], "sha256": "new"},
                              {"id": town[5], "sha256": "old"}]
    # a piece no longer placed drops out; one placed but never packaged is refused
    assert P.scenery_records(on_file, {}, {town[5]}) == cave + [{"id": town[5], "sha256": "old"}]
    with pytest.raises(SystemExit, match=town[7]):
        P.scenery_records(on_file, {}, {town[7]})


def test_the_town_furniture_kit_is_packaged_at_its_own_size():
    """The lf-interiors furniture was prepared at real size; each row measures it as prepared, so packaging scales by
    one."""
    from video_motion.asset import read_glb
    rows = {name: spec for name, spec in P.TOWN_SELECTION.items() if spec[0] == "lf-interiors"}
    assert len(rows) == 35 and P.KITS["lf-interiors"].endswith("kits/lf-interiors/prototypes")
    for name, (_region, slug, measure, size) in rows.items():
        assert slug == name.replace("_", "-") + "-1"
        document, blob = read_glb(CHECKOUT / P.KITS["lf-interiors"] / f"kit-{slug}.glb")
        low, high = P.bounds(document, blob)
        extent = high - low
        assert (extent[1] if measure == "height" else max(extent[0], extent[2])) == pytest.approx(size, abs=1e-3), name
