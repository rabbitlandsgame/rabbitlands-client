"""The client streams the continent-v2 isles beside each other (serve plan CV11).

    python3 -m pytest godot-client/tests/test_continent_v2_links.py -q

The isles' land links live in godot-client/data/maps/exterior_connections-continent-v2.json, written by
_continent_v2/publish_links.py from _continent_v2/crossings.json, and the stream reads them after the legacy graph.
The legacy graph, exterior_connections.json, stays the legacy publisher's: its walk proof and continent audit hold it
equal to the server's own copy, which never holds the isles' links (they are in the server's overlay).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "eloria-assets" / "maps" / "continent-v2" / "_continent_v2" / "publish_links.py"
SPEC = importlib.util.spec_from_file_location("publish_links", SOURCE)
links = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = links
SPEC.loader.exec_module(links)
ISLES = tuple(entry["id"] for entry in json.loads((ROOT / links.CATALOG).read_text(encoding="utf-8"))["entries"])


def test_the_committed_links_are_crossings_jsons():
    assert links.check(ROOT) == []


def test_the_legacy_graph_names_no_isle():
    graph = json.loads((ROOT / links.LEGACY_LINKS).read_text(encoding="utf-8"))
    for link in graph["connections"] + graph.get("visualConnections", []):
        assert not {end["map"] for end in link["ends"]} & set(ISLES), link["id"]


def test_every_isle_link_joins_two_served_isles_in_their_registry_frames():
    graph = json.loads((ROOT / links.CLIENT_LINKS).read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / links.LEGACY_LINKS).read_text(encoding="utf-8"))
    rows = json.loads((ROOT / links.REGISTRY).read_text(encoding="utf-8"))["maps"]
    assert {key: graph[key] for key in ("preloadDistance", "retainDistance", "maximumNeighbours")} == \
        {key: legacy[key] for key in ("preloadDistance", "retainDistance", "maximumNeighbours")}
    crossings = json.loads((ROOT / links.CROSSINGS).read_text(encoding="utf-8"))
    assert set(crossings["inputs"]["maps"]) == set(ISLES), "crossings cover every active served grid"
    expected = crossings["exteriorConnections"]
    assert expected, "the partition retains its traversable border links"
    assert graph["connections"] == expected
    assert len({link["id"] for link in graph["connections"]}) == len(expected)
    walk_ids = {link["id"] for link in crossings["connections"]}
    assert len(walk_ids) == len(crossings["connections"]) == 24
    walk_links = [link for link in graph["connections"] if not link.get("visualOnly", False)]
    view_links = [link for link in graph["connections"] if link.get("visualOnly", False)]
    assert {link["id"] for link in walk_links} == walk_ids
    withdrawn = set(crossings["report"]["withdrawnRoadless"])
    assert len(withdrawn) == len(view_links) == 9
    assert {link["id"] for link in view_links} == {"view--" + key.removeprefix("border--") for key in withdrawn}
    for link in graph["connections"]:
        assert link["seamless"] is True
        assert {end["map"] for end in link["ends"]} <= set(ISLES)
        for end in link["ends"]:
            row = rows[end["map"]]
            assert row["status"] == links.SERVED_STATUS
            assert end["frame"]["globalTranslation"] == row["continentGeography"]["translation"]
            assert end["frame"]["geometryMode"] == "continent-chunks-v1"
            assert end["preloadEdges"]
            if link.get("visualOnly", False):
                assert "crossingRuns" not in end and not end["portal"]
            else:
                assert end["portal"] and end["crossingRuns"]["runs"]
                assert end["crossingRuns"]["axis"] in {"x", "y"}


def fixture_checkout(tmp_path: Path, synthetic=False) -> Path:
    """A checkout holding copies of the real inputs: the catalog, the registry, both graphs, crossings.json and the
    active territory manifests (each package's served-grid hash is what the tool compares)."""
    root = tmp_path / "checkout"
    if synthetic:
        # Exercise refusals without depending on packages being republished in this checkout.
        # The real-input parameter below still verifies the committed fifteen-map publication.
        a, b = ISLES[:2]
        translations = {a: [100.0, 0.0, 200.0], b: [300.0, 0.0, 400.0]}
        settings = {"preloadDistance": 96, "retainDistance": 144, "maximumNeighbours": 4}
        ends = [{"map": region, "frame": {"globalTranslation": translations[region],
                 "geometryMode": "continent-chunks-v1"}, "crossingRuns": [[1, 2]],
                 "preloadEdges": [[0, 1]]} for region in (a, b)]
        graph = {**settings, "connections": [{"id": f"border--{a}--{b}", "seamless": True, "ends": ends}]}
        documents = {
            links.CATALOG: {"entries": [{"id": region} for region in (a, b)]},
            links.REGISTRY: {"maps": {region: {"status": links.SERVED_STATUS,
                "manifest": f"res://../packages/{region}/world.json",
                "continentGeography": {"translation": translations[region]}} for region in (a, b)}},
            links.LEGACY_LINKS: {**settings, "connections": [], "visualConnections": []},
            links.CROSSINGS: {"inputs": {"maps": {region: {"servedGridSha256": "a" * 64}
                                                       for region in (a, b)}},
                             "exteriorSettings": settings, "exteriorConnections": graph["connections"]},
            **{f"packages/{region}/world.json": {"collision": {"servedGrid": {"sha256": "a" * 64}}}
               for region in (a, b)},
        }
        for relative, document in documents.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document), encoding="utf-8")
        helper = "eloria-assets/tools/publish_continent_geography.py"
        (root / helper).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / helper, root / helper)
        assert links.main(["--checkout", str(root)]) == 0
        return root
    paths = [links.CATALOG, links.REGISTRY, links.LEGACY_LINKS, links.CLIENT_LINKS, links.CROSSINGS,
             "eloria-assets/tools/publish_continent_geography.py"]
    rows = json.loads((ROOT / links.REGISTRY).read_text(encoding="utf-8"))["maps"]
    for entry in json.loads((ROOT / links.CATALOG).read_text(encoding="utf-8"))["entries"]:
        paths.append(rows[entry["id"]]["manifest"][len("res://../"):])
    for relative in paths:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    return root


@pytest.mark.parametrize("synthetic", [False, True], ids=["committed", "isolated"])
def test_a_missing_or_edited_file_is_caught_and_written_again(tmp_path, synthetic):
    root = fixture_checkout(tmp_path, synthetic)
    committed = (root / links.CLIENT_LINKS).read_bytes()
    legacy_before = (root / links.LEGACY_LINKS).read_bytes()
    (root / links.CLIENT_LINKS).unlink()
    assert links.check(root) == [f"{links.CLIENT_LINKS} is missing; run _continent_v2/publish_links.py"]
    assert links.main(["--checkout", str(root)]) == 0
    assert (root / links.CLIENT_LINKS).read_bytes() == committed
    (root / links.CLIENT_LINKS).write_bytes(committed.replace(b'"seamless": true', b'"seamless": false', 1))
    assert "is not crossings.json's links" in links.check(root)[0]
    assert links.main(["--checkout", str(root)]) == 0 and links.check(root) == []
    # the legacy graph is never touched
    assert (root / links.LEGACY_LINKS).read_bytes() == legacy_before


def edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.mark.parametrize("case, expected", [
    ("distances", "the stream has one value for every link"),
    ("stale crossings", "run crossings_v2.py again"),
    ("preview row", "has no continent-v2-served registry row"),
    ("moved frame", "is not its registry row's"),
    ("legacy link", "the stream would hold two links for one seam"),
])
@pytest.mark.parametrize("synthetic", [False, True], ids=["committed", "isolated"])
def test_refusals_write_nothing(tmp_path, case, expected, synthetic):
    root = fixture_checkout(tmp_path, synthetic)
    crossings = json.loads((root / links.CROSSINGS).read_text(encoding="utf-8"))
    linked_region = crossings["exteriorConnections"][0]["ends"][0]["map"]
    assert linked_region in ISLES
    if case == "distances":
        edit_json(root / links.LEGACY_LINKS, lambda d: d.update(preloadDistance=240))
    elif case == "stale crossings":
        edit_json(root / links.CROSSINGS,
                  lambda d: d["inputs"]["maps"][linked_region].update(servedGridSha256="0" * 64))
    elif case == "preview row":
        edit_json(root / links.REGISTRY, lambda d: d["maps"][linked_region].update(
            status="continent-v2-client-preview"))
    elif case == "moved frame":
        def move(d):
            translation = d["maps"][linked_region]["continentGeography"]["translation"]
            translation[0] += 1.0
        edit_json(root / links.REGISTRY, move)
    elif case == "legacy link":
        def add(d):
            d["connections"].append({"id": f"{linked_region}--westhaven", "seamless": True, "ends": [
                {"map": linked_region}, {"map": "westhaven"}]})
        edit_json(root / links.LEGACY_LINKS, add)
    before = (root / links.CLIENT_LINKS).read_bytes()
    problems = links.check(root)
    assert len(problems) == 1 and expected in problems[0], problems
    assert links.main(["--checkout", str(root)]) == 1
    assert (root / links.CLIENT_LINKS).read_bytes() == before
