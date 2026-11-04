"""W2-UD-01: the release descriptor ships in a package of its own.
AT-C3: actor VRAM sidecars ship in texture packages of their own, and every existing path keeps its package.

Tiny Python fixtures only: no Godot import, export, network or engine run.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

CLIENT = Path(__file__).resolve().parents[1]
CHECKOUT = CLIENT.parent
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


# --- AT-C3: actor VRAM sidecars ----------------------------------------------------------------------------------

def reference_package_id(relative: str) -> str:
    """asset_packages.package_id as it was before AT-C3 (stage-A tip fc2ee701), kept verbatim so a later edit
    cannot move an existing file to another package unnoticed."""
    parts = relative.split("/")
    if relative in ("app/RabbitLands.exe", "app/RabbitLands.x86_64"):
        return "engine"
    if relative in P.RELEASE_DESCRIPTOR_PATHS:
        return P.RELEASE_DESCRIPTOR_PACKAGE
    if relative == "app/RabbitLands.pck":
        return "client"
    if relative.startswith("app/prepared-world/") and len(parts) >= 4:
        variant = hashlib.sha256(parts[2].encode()).hexdigest()[:16]
        prefix = "prepared-world-" + variant
        if len(parts) == 4 and parts[3] == "catalog.json":
            return prefix + "-catalog"
        if "blobs" in parts[3:-1]:
            group, slots = prefix + "-blobs", 128
        else:
            group, slots = prefix + "-metadata", 8
    elif relative.startswith("app/assets/actors/"):
        group, slots = "actors-" + "-".join(parts[3:5]), 16
    elif relative.startswith("eloria-assets/maps/"):
        group = "map-" + parts[2]
        if "/vram/" in relative and relative.endswith(".evt"):
            group, slots = group + "-textures", 128
        elif relative.endswith(".json"):
            group, slots = group + "-metadata", 8
        else:
            slots = 8
    elif relative.startswith("app/assets/audio/"):
        group, slots = "audio", 8
    elif relative.startswith("app/assets/"):
        group, slots = "assets-" + parts[2], 8
    else:
        group, slots = "records", 8
    group = re.sub(r"[^a-z0-9-]", "-", group.lower())[:72].strip("-")
    bucket = int(hashlib.sha256(relative.encode()).hexdigest()[:8], 16) % slots
    return f"{group}-{bucket:02d}"


def sidecar(folder, sha, recipe="base"):
    return f"app/assets/actors/native/{folder}/vram/{sha}.{recipe}.evt"


def test_actor_sidecars_get_a_texture_group_per_actor_folder():
    shas = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(400)]
    for folder, group in (("creatures", "actors-native-creatures-textures"),
                          ("creatures/basic_expansion", "actors-native-creatures-textures"),
                          ("races", "actors-native-races-textures"), ("hair/fitted", "actors-native-hair-textures"),
                          ("mounts", "actors-native-mounts-textures"),
                          ("equipment", "actors-native-equipment-textures")):
        ids = {P.package_id(sidecar(folder, sha)) for sha in shas}
        ids.add(P.package_id(f"app/assets/actors/native/{folder}/vram/index.json"))
        assert all(re.fullmatch(group + r"-\d\d", name) for name in ids), (folder, sorted(ids)[:3])
        assert len(ids) == P.ACTOR_TEXTURE_BUCKETS == 32, "bounded: 32 buckets per actor folder group"
        # The installed updater accepts ids of [a-z0-9-], at most 96 characters.
        assert all(re.fullmatch(r"[a-z0-9-]{1,96}", name) for name in ids)


def test_only_files_in_a_sidecar_folder_move():
    for relative in ("app/assets/actors/native/creatures/wolf.glb",
                     "app/assets/actors/native/creatures/vram.glb",
                     "app/assets/actors/native/vram/loose.evt",
                     "app/assets/actors/vram/x.evt",
                     "app/assets/actors/native/creatures/wolf.vram/x.evt",
                     "app/assets/world/props/vram/" + "a" * 64 + ".base.evt",
                     "eloria-assets/maps/landfall/shared-assets/vram/" + "a" * 64 + ".base.evt"):
        assert P.package_id(relative) == reference_package_id(relative), relative


def tracked_stage_paths() -> list[str]:
    """Every tracked file of this checkout at the path it is staged under (godot-client/<x> -> app/<x>)."""
    result = subprocess.run(["git", "-C", str(CHECKOUT), "ls-files", "-z", "--", "godot-client/assets",
                             "godot-client/data", "godot-client/schemas", "eloria-assets"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("needs the client's git checkout")
    paths = []
    for item in result.stdout.decode("utf-8").split("\0"):
        if item.startswith("godot-client/"):
            paths.append("app/" + item.removeprefix("godot-client/"))
        elif item:
            paths.append(item)
    return paths


def test_every_existing_path_keeps_its_package():
    paths = tracked_stage_paths()
    assert len(paths) > 10000, "the walk saw the whole tree"
    paths += ["app/RabbitLands.exe", "app/RabbitLands.x86_64", "app/RabbitLands.pck", "app/client-release.json",
              "app/data/client_release.json", "app/prepared-world/" + "a" * 64 + "/catalog.json",
              "app/prepared-world/" + "a" * 64 + "/geometry/policy/blobs/" + "b" * 64 + ".bin"]
    moved = [path for path in paths if P.package_id(path) != reference_package_id(path)]
    assert moved == [], moved[:10]


def actor_stage(stage, sidecars=True, evt=b"sidecar", glb=b"glb"):
    put(stage, "app/RabbitLands.exe", b"engine")
    put(stage, "app/RabbitLands.pck", b"pack")
    put(stage, DESCRIPTOR, identity("a"))
    for index in range(12):
        put(stage, f"app/assets/actors/native/creatures/beast-{index:02d}.glb", glb + b"%d" % index)
        put(stage, f"app/assets/actors/native/races/race-{index:02d}.glb", glb + b"race %d" % index)
    if sidecars:
        for folder in ("creatures", "creatures/basic_expansion", "races"):
            entries = {}
            for index in range(10):
                sha = hashlib.sha256(f"{folder}{index}".encode()).hexdigest()
                put(stage, sidecar(folder, sha), evt + sha.encode())
                entries[sha] = {"file": f"{sha}.base.evt"}
            put(stage, f"app/assets/actors/native/{folder}/vram/index.json", json.dumps({"images": entries}).encode())
    return stage


def test_adding_actor_sidecars_adds_texture_packages_and_changes_no_other(tmp_path):
    without = {row["id"]: row for row in build(actor_stage(tmp_path / "without", sidecars=False))}
    with_sidecars = {row["id"]: row for row in build(actor_stage(tmp_path / "with"))}
    added = sorted(set(with_sidecars) - set(without))
    assert added and all(re.fullmatch(r"actors-native-(creatures|races)-textures-\d\d", name) for name in added)
    assert set(without) <= set(with_sidecars)
    assert all(with_sidecars[name]["sha256"] == row["sha256"] for name, row in without.items()), \
        "a GLB package changed when sidecars were added"
    for name in added:
        assert all("/vram/" in entry["path"] for entry in with_sidecars[name]["files"])


def test_a_sidecar_change_moves_only_texture_packages_and_a_code_change_none(tmp_path):
    first = build(actor_stage(tmp_path / "first"))
    changes = changed(first, build(actor_stage(tmp_path / "second", evt=b"re-encoded")))
    assert changes and all("-textures-" in name for name in changes), "a sidecar change moves no GLB package"
    third = actor_stage(tmp_path / "third")
    put(third, "app/RabbitLands.pck", b"next pack")
    assert changed(first, build(third)) == ["client"], "a code-only release downloads no sidecar"
    glb_changes = changed(first, build(actor_stage(tmp_path / "fourth", glb=b"cooked")))
    assert glb_changes and all("-textures-" not in name for name in glb_changes), \
        "a GLB-only release re-downloads no sidecar"


# --- W2-UD-06: split PCK content packs ---------------------------------------------------------------------------

import pck_split  # noqa: E402

CONTENT_PACK_NAMES = ("audio", "video", *(f"equipment-textures-{i}" for i in range(4)),
                      *(f"textures-{i}" for i in range(2)))


def test_each_content_pack_is_a_package_of_its_own():
    for name in CONTENT_PACK_NAMES:
        assert P.package_id(f"app/packs/{name}.pck") == f"pck-{name}"
        # The installed updater accepts ids of [a-z0-9-], at most 96 characters.
        assert re.fullmatch(r"[a-z0-9-]{1,96}", P.package_id(f"app/packs/{name}.pck"))
    assert P.package_id("app/packs/" + "a" * 63 + ".pck") == "pck-" + "a" * 63
    assert P.package_id("app/RabbitLands.pck") == "client"
    # Only exact app/packs/<lowercase id>.pck files; neighbours keep their packages.
    for neighbour in ("app/packs/audio.json", "app/packs/sub/audio.pck", "app/packs/Audio.pck",
                      "app/packs/audio.pck.part", "app/packs/-audio.pck", "app/packs/" + "a" * 64 + ".pck",
                      "eloria-assets/packs/audio.pck", "app/assets/packs/audio.pck", "app/data/packs/audio.pck"):
        assert P.package_id(neighbour) == reference_package_id(neighbour), neighbour


def _fixture_monolith(path, code=b"GDSC v1", texture=b"GST2 world"):
    files = {"project.godot": b'config_version=5\n[application]\nconfig/name="Fixture"\n',
             "src/main.gdc": code, "src/main.gd.remap": b'[remap]\n\npath="res://src/main.gdc"\n',
             "data/table.json": b'{"rows": 1}',
             "assets/world.png.import": b'[remap]\n\npath="res://.godot/imported/world.png-1.ctex"\n',
             ".godot/imported/world.png-1.ctex": texture,
             "assets/audio/hit.wav.import": b'[remap]\n\npath="res://.godot/imported/hit.wav-2.sample"\n',
             ".godot/imported/hit.wav-2.sample": b"RIFF hit",
             "assets/ui/start_screen/01-a.ogv": b"OggS video"}
    for index in range(8):
        files[f"assets/equipment/canonical_{index}.jpg.import"] = (
            b'[remap]\n\npath.s3tc="res://.godot/imported/canonical_%d.jpg-3.s3tc.ctex"\n' % index)
        files[f".godot/imported/canonical_{index}.jpg-3.s3tc.ctex"] = b"GST2 gear %d" % index
    pck_split.write_pack(path, {name: pck_split.Source(data=data) for name, data in files.items()},
                         fmt=4, version=(4, 7, 2))
    return path


def split_stage(stage, commit="a", **monolith):
    """release_stage with the exported pack split as package_client splits it."""
    release_stage(stage, commit=commit)
    (stage / "app/RabbitLands.pck").unlink()
    exported = _fixture_monolith(stage.parent / f"{stage.name}.monolith.pck", **monolith)
    pck_split.split(exported, stage / "app", stage / "app/RabbitLands.pck")
    exported.unlink()
    return stage


def test_a_split_stage_packages_each_pack_once(tmp_path):
    stage = split_stage(tmp_path / "RabbitLands-Windows-20261104-aaaaaaaaa")
    packages = {row["id"]: row for row in build(stage)}
    packs = sorted(path.name for path in (stage / "app/packs").iterdir())
    assert {"audio.pck", "video.pck"} <= set(packs)
    for name in packs:
        row = packages["pck-" + name.removesuffix(".pck")]
        assert [entry["path"] for entry in row["files"]] == [f"app/packs/{name}"] and row["file_count"] == 1
    assert [entry["path"] for entry in packages["client"]["files"]] == ["app/RabbitLands.pck"]
    listed = [entry["path"] for row in packages.values() for entry in row["files"]]
    staged = sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file())
    assert sorted(listed) == staged and len(listed) == len(set(listed))


def test_after_the_split_a_code_only_release_downloads_no_content_pack(tmp_path):
    first = build(split_stage(tmp_path / "first"), shared=True)
    previous = {row["id"]: row for row in first}
    reused = []
    second = build(split_stage(tmp_path / "second", commit="b", code=b"GDSC v2 with one changed script"),
                   shared=True, previous_packages=previous,
                   reuse_package=lambda row: reused.append(row["id"]) or True)
    assert changed(first, second) == ["client", "release-descriptor"]
    assert {name for name in previous if name.startswith("pck-")} <= set(reused)


def test_a_texture_change_moves_its_own_content_pack_and_the_core(tmp_path):
    first = build(split_stage(tmp_path / "first"))
    second = build(split_stage(tmp_path / "second", texture=b"GST2 world, repainted"))
    texture_pack = pck_split.classify(".godot/imported/world.png-1.ctex")[0]
    # The core lists each pack's size and sha256 in data/content_packs.json, and
    # it changes in every release anyway (it embeds the commit).
    assert changed(first, second) == sorted(["client", "pck-" + texture_pack])
