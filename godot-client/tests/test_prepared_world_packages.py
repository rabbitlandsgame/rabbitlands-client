"""Tiny Python fixtures only: no Godot import, build, network or engine run."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import asset_packages as P
import client_release


def put(stage, relative, content):
    path = stage / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def world_tree(stage, compatibility="a" * 64):
    prefix = f"app/prepared-world/{compatibility}"
    payload = b"first native mesh bytes"
    digest = hashlib.sha256(payload).hexdigest()
    blob = f"{prefix}/geometry/{'b' * 64}/blobs/{digest}.scn"
    entry = f"{prefix}/geometry/{'b' * 64}/entries/{'c' * 64}.json"
    catalog = f"{prefix}/catalog.json"
    put(stage, blob, payload)
    put(stage, entry, json.dumps({"blob": digest}, sort_keys=True).encode())
    put(stage, catalog, json.dumps({"entry": entry}, sort_keys=True).encode())
    put(stage, "app/RabbitLands.pck", b"code release one")
    put(stage, "app/client-release.json", b'{"commit":"one"}')
    return prefix, blob, entry, catalog


def test_nested_caches_keep_payloads_and_metadata_out_of_client_package():
    prefix = "app/prepared-world/" + "a" * 64
    catalog = P.package_id(prefix + "/catalog.json")
    assert catalog.endswith("-catalog") and catalog != "client"
    for kind, extension in (("geometry", "scn"), ("collision", "rlc"), ("paving", "res")):
        blob = P.package_id(f"{prefix}/{kind}/{'b' * 64}/blobs/{'c' * 64}.{extension}")
        entry = P.package_id(f"{prefix}/{kind}/{'b' * 64}/entries/{'d' * 64}.json")
        assert "-blobs-" in blob and "-metadata-" in entry
        assert len({catalog, blob, entry, "client"}) == 4
        assert len(blob) <= 96 and set(blob) <= set("abcdefghijklmnopqrstuvwxyz0123456789-")
    assert P.package_id(prefix + "/catalog.json") != P.package_id(prefix.replace("a" * 64, "e" * 64) + "/catalog.json")


def test_code_only_release_reuses_identical_world_package_records(tmp_path):
    first_stage, second_stage = tmp_path / "first", tmp_path / "second"
    world_tree(first_stage)
    first = P.build(first_stage, "https://example.invalid/shared", shared=True)
    shutil.copytree(first_stage, second_stage)
    put(second_stage, "app/RabbitLands.pck", b"code release two")
    put(second_stage, "app/client-release.json", b'{"commit":"two"}')
    previous = {row["id"]: row for row in first}
    reused = []
    second = P.build(second_stage, "https://example.invalid/shared", shared=True,
                     previous_packages=previous,
                     reuse_package=lambda row: reused.append(row["id"]) or True)
    world_ids = {row["id"] for row in first if row["id"].startswith("prepared-world-")}
    assert set(reused) == world_ids
    for row in second:
        if row["id"] in world_ids:
            assert row is previous[row["id"]]
            assert row["sha256"] == previous[row["id"]]["sha256"]
        else:
            assert row["id"] == "client" and row["sha256"] != previous["client"]["sha256"]


def test_changed_blob_updates_only_its_buckets_and_drops_obsolete_inventory(tmp_path):
    before_stage, after_stage = tmp_path / "before", tmp_path / "after"
    prefix, old_blob, entry, catalog = world_tree(before_stage)
    old_group = P.package_id(old_blob)
    # An independent blob in another fixed bucket represents an unchanged map.
    for index in range(1000):
        content = f"unchanged native object {index}".encode()
        digest = hashlib.sha256(content).hexdigest()
        survivor = f"{prefix}/collision/{'b' * 64}/blobs/{digest}.rlc"
        if P.package_id(survivor) != old_group:
            break
    put(before_stage, survivor, content)
    before = {row["id"]: row for row in P.build(before_stage, "https://example.invalid/before")}
    shutil.copytree(before_stage, after_stage)
    (after_stage / old_blob).unlink()
    changed = b"changed native mesh bytes"
    digest = hashlib.sha256(changed).hexdigest()
    new_blob = f"{prefix}/geometry/{'b' * 64}/blobs/{digest}.scn"
    put(after_stage, new_blob, changed)
    put(after_stage, entry, json.dumps({"blob": digest}, sort_keys=True).encode())
    put(after_stage, catalog, json.dumps({"entry": entry, "updated": digest}, sort_keys=True).encode())
    after = {row["id"]: row for row in P.build(after_stage, "https://example.invalid/after")}
    allowed = {old_group, P.package_id(new_blob), P.package_id(entry), P.package_id(catalog)}
    changed_groups = {name for name in before.keys() | after.keys()
                      if before.get(name, {}).get("sha256") != after.get(name, {}).get("sha256")}
    assert changed_groups <= allowed
    assert after[P.package_id(survivor)]["sha256"] == before[P.package_id(survivor)]["sha256"]
    files = {item["path"]: item for row in after.values() for item in row["files"]}
    assert old_blob not in files and files[new_blob]["sha256"] == digest
    # The existing updater's matches() hashes each listed path. Its signed
    # inventory continues to distinguish corruption at the unchanged path.
    put(after_stage, survivor, b"corrupt local bytes")
    assert client_release.digest(after_stage / survivor) != files[survivor]["sha256"]


def test_package_count_and_streamed_part_bounds_stay_bounded(tmp_path, monkeypatch):
    groups = set()
    for compatibility in ("a" * 64, "b" * 64):
        prefix = f"app/prepared-world/{compatibility}"
        groups.add(P.package_id(prefix + "/catalog.json"))
        for index in range(2048):
            digest = hashlib.sha256(str(index).encode()).hexdigest()
            for kind, extension in (("geometry", "scn"), ("collision", "rlc"), ("paving", "res")):
                groups.add(P.package_id(f"{prefix}/{kind}/policy/blobs/{digest}.{extension}"))
                groups.add(P.package_id(f"{prefix}/{kind}/policy/entries/{digest}.json"))
    assert len(groups) <= 2 * (1 + 8 + 128) < 850
    monkeypatch.setattr(client_release, "PART_BYTES", 1024)
    stage = tmp_path / "small"
    put(stage, "app/prepared-world/compat/geometry/policy/blobs/mesh.scn",
        hashlib.shake_256(b"incompressible small fixture").digest(4096))
    packages = P.build(stage, "https://example.invalid/parts")
    assert len(packages) == 1 and len(packages[0]["parts"]) > 1
    assert all(part["size"] <= 1024 for part in packages[0]["parts"])
