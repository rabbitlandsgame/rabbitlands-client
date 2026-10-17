"""The isles' light is the stub's: every package carries its <region>/world.json `environment` block verbatim.

publish_client.py copies the stub's environment (sky, sun, ambient, fog, saturation and the dawn, dusk and night
variants DayNightBinder reads) into the territory manifest and every chunk manifest. `--environment` publishes that
block alone, without a re-bake: nothing else in the package changes, and no digest covers it. These cases check that
every committed isle package agrees with its stub (a sky edited in a stub and never published, or edited in a package
by hand, fails), and that the environment publish rewrites the block and nothing else.

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_publish_client_environment.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CHECKOUT = V2.parents[3]
sys.path.insert(0, str(V2))
import frames  # noqa: E402
import publish_client as PC  # noqa: E402


@pytest.mark.parametrize("region", frames.regions(CHECKOUT))
def test_every_isle_package_carries_its_stubs_environment(region):
    out = CHECKOUT / "eloria-assets/maps/continent-v2" / region / "client"
    assert PC.environment_restamp(out, region, CHECKOUT, write=False) == [], (
        f"{region}: run publish_client.py --environment --region {region} --out {out}")


def test_the_five_shared_skies_are_now_each_their_own():
    """Landfall, Hearthcroft, Greenlight, Spindle Hill and Tollholm shared one sky and one fog."""
    seen = {}
    for region in ("landfall", "hearthcroft", "greenlight", "spindle_hill", "tollholm"):
        environment = json.loads((CHECKOUT / "eloria-assets/maps/continent-v2" / region / "world.json")
                                 .read_text(encoding="utf-8"))["environment"]
        key = json.dumps([environment["sky"]["zenith"], environment["sky"]["horizon"], environment["fog"]["color"]])
        assert key not in seen, f"{region} shares {seen.get(key)}'s sky"
        seen[key] = region


def test_every_isle_names_its_own_night_and_twilights():
    for region in frames.regions(CHECKOUT):
        variants = json.loads((CHECKOUT / "eloria-assets/maps/continent-v2" / region / "world.json")
                              .read_text(encoding="utf-8"))["environment"].get("variants", {})
        for name in ("dawn", "dusk", "night"):
            assert name in variants, f"{region} has no {name} variant"
        assert {"zenith", "horizon"} <= set(variants["night"]["sky"]), region


def _package(tmp_path, region="isle"):
    checkout = tmp_path / "checkout"
    stub = checkout / "eloria-assets/maps/continent-v2" / region / "world.json"
    stub.parent.mkdir(parents=True)
    stub.write_text(json.dumps({"environment": {"sky": {"zenith": [0.1, 0.2, 0.3]}, "saturation": 1.1}}),
                    encoding="utf-8")
    out = tmp_path / "client"
    old = {"sky": {"zenith": [0.5, 0.5, 0.5]}, "saturation": 1.3}
    territory = {"asset": {"id": region}, "environment": old, "lighting": {"markers": []},
                 "provenance": {"tool": PC.TOOL, "snapshotSha256": "abc"},
                 "streamingChunks": {"chunks": [{"id": "01_02", "manifest": "chunks/01_02/world.json"}]}}
    chunk = {"asset": {"id": f"{region}__chunk_01_02"}, "environment": old, "performance": {"glbBytes": 7}}
    PC.json_write(out / "world.json", territory)
    PC.json_write(out / "chunks/01_02/world.json", chunk)
    return checkout, out


def test_the_environment_publish_rewrites_the_block_and_nothing_else(tmp_path):
    checkout, out = _package(tmp_path)
    before = {p: json.loads(p.read_text(encoding="utf-8")) for p in out.rglob("world.json")}

    assert len(PC.environment_restamp(out, "isle", checkout, write=False)) == 2
    assert {p: json.loads(p.read_text(encoding="utf-8")) for p in out.rglob("world.json")} == before

    assert len(PC.environment_restamp(out, "isle", checkout)) == 2
    for path, old in before.items():
        new = json.loads(path.read_text(encoding="utf-8"))
        assert new["environment"] == {"sky": {"zenith": [0.1, 0.2, 0.3]}, "saturation": 1.1}
        assert {k: v for k, v in new.items() if k != "environment"} == \
            {k: v for k, v in old.items() if k != "environment"}
        assert list(new) == list(old), "the block keeps its place in the manifest"
    assert PC.environment_restamp(out, "isle", checkout) == [], "a second run changes nothing"


def test_a_package_from_elsewhere_is_refused(tmp_path):
    checkout, out = _package(tmp_path)
    territory = json.loads((out / "world.json").read_text(encoding="utf-8"))
    territory["provenance"]["tool"] = "somebody_else.py"
    PC.json_write(out / "world.json", territory)
    with pytest.raises(SystemExit, match="refused"):
        PC.environment_restamp(out, "isle", checkout)


def test_a_foreign_cell_is_refused_before_anything_is_written(tmp_path):
    checkout, out = _package(tmp_path)
    chunk_path = out / "chunks/01_02/world.json"
    chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
    chunk["asset"]["id"] = "other__chunk_01_02"
    PC.json_write(chunk_path, chunk)
    territory_before = (out / "world.json").read_bytes()
    with pytest.raises(SystemExit, match="refused"):
        PC.environment_restamp(out, "isle", checkout)
    assert (out / "world.json").read_bytes() == territory_before
