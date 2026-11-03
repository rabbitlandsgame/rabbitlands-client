"""W2-UD-01: the release descriptor ships in a package of its own.

Tiny Python fixtures only: no Godot import, export, network or engine run.
"""
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import asset_packages as P

DESCRIPTOR = "app/client-release.json"
DATA_DESCRIPTOR = "app/data/client_release.json"


def put(stage, relative, content):
    path = stage / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def identity(commit):
    return json.dumps({"schema": 1, "commit": commit * 40, "platform": "windows",
                       "distribution": "github", "ancestors": [commit * 40]}).encode()


def release_stage(stage, commit="a", pack=b"exported pack"):
    """The shape package_client stages: both descriptor copies sit beside the
    records they used to share packages with."""
    put(stage, "app/RabbitLands.exe", b"engine")
    put(stage, "app/RabbitLands.pck", pack)
    put(stage, DESCRIPTOR, identity(commit))
    put(stage, DATA_DESCRIPTOR, identity(commit))
    for index in range(24):
        # Enough loose records that every records bucket holds neighbours.
        put(stage, f"app/data/records/table-{index:02d}.json", b"record %d" % index)
    put(stage, "app/schemas/item.schema.json", b"{}")
    put(stage, "app/assets/actors/native/creatures/rabbit.glb", b"rabbit")
    put(stage, "app/assets/audio/music/login.ogg", b"music")
    put(stage, "eloria-assets/maps/landfall/world.json", b"world")
    put(stage, "eloria-assets/world/_shared/images/" + "0" * 64 + ".jpg", b"image")
    return stage


def build(stage, **options):
    return P.build(stage, "https://example.invalid/" + stage.name, **options)


def changed(before, after):
    old = {row["id"]: row["sha256"] for row in before}
    new = {row["id"]: row["sha256"] for row in after}
    assert set(old) == set(new), "A grouping change moved files between packages."
    return sorted(name for name in new if new[name] != old[name])


def test_both_descriptor_copies_map_to_one_unbucketed_package():
    assert P.package_id(DESCRIPTOR) == P.package_id(DATA_DESCRIPTOR) == "release-descriptor"
    assert P.package_id("app/RabbitLands.pck") == "client"
    assert P.package_id("app/RabbitLands.exe") == P.package_id("app/RabbitLands.x86_64") == "engine"
    # Neighbours keep their buckets; only exact descriptor paths move.
    for neighbour in ("app/data/client_release.json.bak", "app/data/benchmark_profile.json",
                      "app/client-release.json.sig", "app/data/records/client_release.json",
                      "eloria-assets/client-release.json"):
        assert P.package_id(neighbour) != "release-descriptor", neighbour
    # The installed updater accepts ids of [a-z0-9-], at most 96 characters.
    assert re.fullmatch(r"[a-z0-9-]{1,96}", P.RELEASE_DESCRIPTOR_PACKAGE)


def test_descriptor_package_holds_exactly_the_descriptor_files(tmp_path):
    stage = release_stage(tmp_path / "RabbitLands-Windows-20261102-aaaaaaaaa")
    packages = {row["id"]: row for row in build(stage)}
    descriptor = packages["release-descriptor"]
    paths = [entry["path"] for entry in descriptor["files"]]
    assert sorted(paths) == sorted([DESCRIPTOR, DATA_DESCRIPTOR])
    assert descriptor["file_count"] == 2 and len(descriptor["parts"]) == 1
    assert [entry["path"] for entry in packages["client"]["files"]] == ["app/RabbitLands.pck"]
    # Every staged file is in exactly one package.
    listed = [entry["path"] for row in packages.values() for entry in row["files"]]
    staged = sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file())
    assert sorted(listed) == staged and len(listed) == len(set(listed))
    part = stage.parent / descriptor["parts"][0]["url"].rsplit("/", 1)[1]
    assert part.name == stage.name + ".pkg.release-descriptor.zip.001"
    with zipfile.ZipFile(part) as archive:
        inventory = json.loads(archive.read("inventory.json"))
        assert inventory == descriptor["files"]
        for index, path in enumerate(paths):
            assert archive.read(f"files/{index:06d}/000000") == (stage / path).read_bytes()


def test_stages_that_differ_only_in_the_descriptor_differ_in_exactly_one_package(tmp_path):
    first = build(release_stage(tmp_path / "first"))
    again = build(release_stage(tmp_path / "again"))
    assert changed(first, again) == [], "Package bytes are not deterministic."
    second = build(release_stage(tmp_path / "second", commit="b"))
    assert changed(first, second) == ["release-descriptor"]


def test_a_code_only_release_changes_only_the_pack_and_the_descriptor(tmp_path):
    first = build(release_stage(tmp_path / "first"), shared=True)
    previous = {row["id"]: row for row in first}
    reused = []
    stage = release_stage(tmp_path / "second", commit="b", pack=b"next exported pack")
    second = build(stage, shared=True, previous_packages=previous,
                   reuse_package=lambda row: reused.append(row["id"]) or True)
    assert changed(first, second) == ["client", "release-descriptor"]
    # Shared publication reuses every other package record and its uploads.
    assert sorted(reused) == sorted(set(previous) - {"client", "release-descriptor"})
    for row in second:
        if row["id"] in reused:
            assert row is previous[row["id"]]


def test_a_stage_without_the_loose_data_copy_still_isolates_the_descriptor(tmp_path):
    first_stage = release_stage(tmp_path / "first")
    (first_stage / DATA_DESCRIPTOR).unlink()
    second_stage = tmp_path / "second"
    shutil.copytree(first_stage, second_stage)
    put(second_stage, DESCRIPTOR, identity("b"))
    first, second = build(first_stage), build(second_stage)
    rows = {row["id"]: row for row in second}
    assert [entry["path"] for entry in rows["release-descriptor"]["files"]] == [DESCRIPTOR]
    assert changed(first, second) == ["release-descriptor"]
