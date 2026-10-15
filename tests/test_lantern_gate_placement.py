"""The shipped and prototype gate transforms stay reproducible from terrain."""
import importlib.util
import json
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
SOURCE = CLIENT / "prototypes/last-lantern"


def load_source(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shipped_gates_match_the_terrain_authoring():
    author = load_source("art_authoring")
    builder = load_source("build_map")
    expected = author.gate_placements(builder)
    for package in (SOURCE / "package", CLIENT / "eloria-assets/maps/lantern-reach"):
        actual = json.loads((package / "art.json").read_text(encoding="utf-8"))
        assert actual["gatePlacements"] == expected
