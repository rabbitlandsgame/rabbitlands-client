"""Guarded delivery of 116 worthwhile installed close-match creature selections.

Default is a dry run. --install is required to replace files. This deliberately
does not install local drafts, 30 Hz proposals or zero-corrective bakes. Two
numerically qualified choices (Moss Bear/Leafwing Owl) are held because they have
negative/zero raw savings. It keeps
historical fixtures/receipts and every authored review status unchanged.

Inputs: the private close-install audit plan, frozen retrofit manifest, and the
fresh Blender final-summary.json. The plan's report hashes pin actual-client
measurements; Blender is a fresh-import/finite-state check, not an equivalence
or artistic acceptance claim. No runtime FPS improvement is inferred.

Example (from the integration worktree, after reviewing the dry-run report):
 python eloria-assets/tools/install_creature_runtime_delivery.py --root . \
   --plan PRIVATE_PLAN.json --manifest MANIFEST.json --blender-index SUMMARY.json \
   --output .local/runtime-delivery-install/dry-run

Repeat with a NEW --output directory and --install only when installation is
authorized. Originals, metadata and SHA manifests are retained under --output.
All changes are staged before replacement; a failed commit restores only files
whose bytes still match this transaction, preserving conflicting external edits.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = "docs/qa/creature-storage/runtime-delivery.json"
ROSTER = "eloria-assets/source/model-development-roster.json"
POLAR_STALE_ROSTER = "9a9cb6c5d838ad64abcba073f412d6e0db8dbec4f29593d7f617a1eeecf6fc2d"
STATIC_PROOFS = {
    "geometry/topology/UVs/normals/tangents/colors",
    "all morph POSITION/NORMAL/TANGENT fields",
    "all skin influence sets and inverse binds",
    "node hierarchy/rest/defaults",
    "materials/texture metadata/embedded image bytes",
    "clip order/names/metadata/channel order",
    "all sampler endpoint bits",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(json_bytes(value))


def target(root, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "Invalid repository path")
    path = (root / relative).resolve()
    require(path.is_relative_to(root), "Destination leaves requested worktree")
    return path


def glb_document(path):
    with Path(path).open("rb") as stream:
        header = stream.read(20)
        magic, version, size, count, kind = struct.unpack("<IIIII", header)
        require((magic, version, size, kind) == (0x46546C67, 2, Path(path).stat().st_size, 0x4E4F534A), "Invalid GLB")
        return json.loads(stream.read(count))


def import_policy(data, fps):
    """Change only the params animation/fps line; preserve all other bytes."""
    text = data.decode("utf-8")
    section = re.search(r"(?ms)^\[params\]\r?\n(.*?)(?=^\[|\Z)", text)
    require(section is not None, "Import policy has no [params]")
    body = section.group(1)
    matches = list(re.finditer(r"(?m)^animation/fps\s*=\s*[^\r\n]+", body))
    require(len(matches) <= 1, "Duplicate import FPS policy")
    if matches:
        match = matches[0]
        changed = body[:match.start()] + f"animation/fps={fps}" + body[match.end():]
    else:
        changed = f"animation/fps={fps}" + ("\r\n" if "\r\n" in text else "\n") + body
    return (text[:section.start(1)] + changed + text[section.end(1):]).encode("utf-8")


def qualify(root, plan_path, manifest_path, blender_index_path):
    plan, manifest, blender = map(read, (plan_path, manifest_path, blender_index_path))
    require(digest(manifest_path) == plan["manifest_sha256"], "Frozen manifest differs from audit")
    actors = {a["id"]: a for a in manifest["actors"]}
    installed = [a for a in plan["actors"] if a["was_installed"]]
    require(len(installed) == len({a["actor"] for a in installed}) == 118, "Expected exactly 118 numerically qualified installed selections")
    held = [a for a in installed if a["raw_saved_bytes"] <= 0]
    require({a["actor"] for a in held} == {"moss_bear", "leafwing_owl"}, "Unexpected non-saving selections; reconcile the plan")
    selected = [a for a in installed if a["raw_saved_bytes"] > 0]
    require(len(selected) == 116, "Expected exactly 116 positive-saving selections")
    models = read(root / "godot-client/data/actors/models.json")["models"]
    roster = read(root / ROSTER)
    roster_actors = {a["id"]: a for a in roster["creatures"]}
    blender_rows = {(a["actor"], a["variant"]): a for a in blender["variants"]}
    receipt_path = root / RECEIPT
    receipt = read(receipt_path) if receipt_path.exists() else {"schema_version": 1, "actors": {}}
    require(receipt.get("schema_version") == 1 and isinstance(receipt.get("actors"), dict), "Existing delivery registry has an incompatible schema")
    writes, expected, deliveries = {}, {}, []

    def metadata(relative, content):
        path = target(root, relative)
        if relative in writes:
            require(writes[relative] == content, "Conflicting shared metadata update: " + relative)
        writes[relative] = content
        expected[relative] = digest(path) if path.exists() else None

    for row in selected:
        name = row["actor"]
        actor = actors[name]
        require(actor["was_installed"] is True and not actor["selected_local_draft"] and not row["selected_local_draft"], name + ": local drafts cannot be installed")
        allowed_issues = ["active roster SHA differs from frozen source"] if name == "crystal_polar_bear" else []
        require(not row["issues"] or row["issues"] == allowed_issues, name + ": unresolved audit issue")
        source = Path(row["private"]["source_path"])
        candidate = Path(row["private"]["candidate_path"])
        relative = actor["runtime_repository_path"]
        require(relative == row["runtime_repository_path"] and relative.startswith("godot-client/assets/actors/native/creatures/") and relative.endswith(".glb"), name + ": unexpected runtime destination")
        runtime = target(root, relative)
        source_sha, candidate_sha = row["source_sha256"], row["candidate_sha256"]
        require(source.resolve() == Path(actor["source"]).resolve(), name + ": different frozen source path")
        require(digest(source) == actor["sha256"] == source_sha == digest(runtime), name + ": source/current runtime hash changed")
        require(digest(candidate) == candidate_sha, name + ": candidate changed")
        require(source.stat().st_size == row["source_bytes"] and candidate.stat().st_size == row["candidate_bytes"] < source.stat().st_size, name + ": size mismatch or no raw saving")
        config = models[name]
        require("godot-client/" + config["scene"].removeprefix("res://") == relative and config["animationLibrary"] == config["scene"], name + ": active model paths changed")
        old_roster = roster_actors[name]["sha256"]
        require(old_roster == source_sha or (name == "crystal_polar_bear" and old_roster == POLAR_STALE_ROSTER), name + ": unexpected active roster version")
        fps = row["candidate_fps"]
        require(fps in (120, 240), name + ": only close120/240 deliveries are in scope")
        document = glb_document(candidate)
        require(document["asset"].get("extras", {}).get("rabbitlands_animation_bake_fps") == fps, name + ": candidate declared cadence changed")
        require([a["name"] for a in document["animations"]] == actor["clips"], name + ": clip order/inventory changed")
        build_path, client_path = Path(row["private"]["build_report"]), Path(row["private"]["client_report"])
        require(digest(build_path) == row["build_report_sha256"] and digest(client_path) == row["client_report_sha256"], name + ": audited evidence changed")
        build, client = read(build_path), read(client_path)
        require(build["source_sha256"] == client["models"][0]["sha256"] == source_sha and build["candidate_sha256"] == client["models"][1]["sha256"] == candidate_sha, name + ": source/candidate evidence lineage differs")
        require(Path(build["candidate_path"]).resolve() == candidate.resolve() and build["fps"] == fps, name + ": build recipe differs")
        require(STATIC_PROOFS.issubset(set(build["structural_proof"]["preserved"])), name + ": static preservation is not certified")
        require(set(client["placement"]) >= {"actor_global_equal", "model_global_equal", "selection_equal"} and all(client["placement"].values()) and set(client["native_clips"]) == set(actor["clips"]), name + ": placement/native clip gate failed")
        require(set(client["summary"]) >= {"all", "default", "clip", "held_end", "switch", "RESET"} and client["all_directed_switch_pairs"] == len(actor["clips"]) * (len(actor["clips"]) - 1), name + ": missing client state categories or directed switches")
        measured = client["summary"]["all"]
        require(measured["maximum_position_mm"] <= 1 and measured["maximum_normal_degrees"] <= .5, name + ": approved close budget exceeded")
        require(all("GlbSceneCache._build_raw" in m["load_proof"]["actual_loader"] for m in client["models"]), name + ": different client loader scope")
        for field in ("vertices", "surfaces", "bones", "blend_buffer_bytes"):
            require(client["models"][0][field] == client["models"][1][field], name + ": native geometry/palette footprint changed")
        client_meta = client_path.parent / "client/metadata.json"
        client_states = client_path.parent / "client/states.f32"
        require(digest(client_meta) == client["provenance"]["metadata_sha256"] and digest(client_states) == client["provenance"]["states_sha256"], name + ": client capture payload changed")
        imported = blender_rows[(name, f"close-{fps}")]
        require(imported["status"] == "passed_fresh_import_finite_only" and imported["sha256"] == candidate_sha and imported["source_sha256"] == source_sha and Path(imported["path"]).resolve() == candidate.resolve(), name + ": Blender index is not bound to selected close bytes")
        blender_path = Path(imported["report"])
        require(digest(blender_path) == imported["report_sha256"], name + ": Blender report changed")
        fresh = read(blender_path)
        require(fresh["status"] == "passed_fresh_import_finite_only" and fresh["all_clips_finite"] is True and fresh["sha256"] == fresh["expected_sha256"] == candidate_sha and Path(fresh["path"]).resolve() == candidate.resolve() and fresh["validator_sha256"] == imported["validator_sha256"], name + ": fresh Blender finite-state gate failed")
        require({a["name"] for a in fresh["source_inventory"]["clips"]} == set(actor["clips"]), name + ": Blender omitted native clips")
        policy_relative = relative + ".import"
        policy_path = target(root, policy_relative)
        require(policy_path.exists(), name + ": no authored import policy")
        metadata(policy_relative, import_policy(policy_path.read_bytes(), fps))
        map_relative = "godot-client/" + config["animationMap"].removeprefix("res://")
        mapping = read(target(root, map_relative))
        review_status = copy.deepcopy(mapping.get("reviewStatus"))
        runtime_receipt = {"receipt": RECEIPT, "actor": name, "sourceSHA256": source_sha,
                           "runtimeSHA256": candidate_sha, "method": "close_match_animation_resampling",
                           "bakeFPS": fps, "artisticAcceptanceChanged": False}
        if "runtimeOptimization" in mapping and mapping["runtimeOptimization"] != runtime_receipt:
            runtime_receipt["previousRuntimeOptimization"] = mapping["runtimeOptimization"]
        mapping["runtimeOptimization"] = runtime_receipt
        require(mapping.get("reviewStatus") == review_status, name + ": authored review status changed")
        metadata(map_relative, json_bytes(mapping))
        roster_actors[name]["sha256"] = candidate_sha
        delivery = {"actor": name, "runtime_path": relative, "source_sha256": source_sha,
                    "runtime_sha256": candidate_sha, "source_bytes": row["source_bytes"], "runtime_bytes": row["candidate_bytes"],
                    "declared_animation_bake_fps": fps, "method": "close_match_animation_resampling",
                    "was_installed": True, "selected_local_draft": False, "artistic_acceptance_changed": False,
                    "preserved_reviewStatus": review_status, "preserved_roster_status": roster_actors[name].get("status"),
                    "limits": {"maximum_position_mm": 1.0, "maximum_normal_degrees": .5},
                    "measured": measured, "clips": actor["clips"], "placement_equal": True,
                    "static_preservation": sorted(STATIC_PROOFS),
                    "source_lossless_receipt": row.get("retained_lossless_lineage"),
                    "evidence": {"build_report_sha256": row["build_report_sha256"], "client_report_sha256": row["client_report_sha256"],
                                 "client_probe_sha256": client["provenance"]["probe_sha256"], "client_checker_sha256": client["provenance"]["checker_sha256"],
                                 "blender_report_sha256": imported["report_sha256"], "blender_validator_sha256": imported["validator_sha256"]},
                    "blender_scope": "Fresh import; every clip sampled and finite. Not a source/candidate equivalence or artistic acceptance claim.",
                    "client_scope": "Raw actual-client Actor; finite independent samples/defaults/RESET/held ends/all directed switches. Not a continuous-time bound or GPU appearance/FPS claim."}
        if old_roster != source_sha:
            delivery["roster_metadata_reconciliation"] = {"previous_roster_sha256": old_roster, "observed_original_runtime_sha256": source_sha}
        receipt["actors"][name] = delivery
        deliveries.append(delivery)
        writes[relative] = candidate
        expected[relative] = source_sha
    receipt["source_manifest_sha256"] = digest(manifest_path)
    receipt["held_qualified_no_raw_saving"] = [{"actor": a["actor"], "source_sha256": a["source_sha256"],
                                               "candidate_sha256": a["candidate_sha256"], "raw_saved_bytes": a["raw_saved_bytes"],
                                               "reason": "No positive raw GLB saving; original retained and candidate available for review"} for a in held]
    receipt["scope"] = "Explicit close-match deliveries of previously installed selections only. Historical numeric fixtures and lossless receipts remain immutable; no new artistic acceptance."
    metadata(ROSTER, json_bytes(roster))
    metadata(RECEIPT, json_bytes(receipt))
    return writes, expected, deliveries


@contextlib.contextmanager
def installation_lock(root):
    path = root / ".local/runtime-delivery-install.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0"); stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def apply_transaction(root, writes, expected, output, fail_after=None, approved_hashes=None):
    """Back up/stage everything before touching any destination; recover on error."""
    require(output.is_relative_to(root / ".local"), "Install recovery output must stay under target worktree/.local")
    operations = []
    for relative, content in writes.items():
        destination = target(root, relative)
        observed = digest(destination) if destination.exists() else None
        require(observed == expected[relative], "Concurrent destination edit before staging: " + relative)
        backup, staged = output / "backups" / relative, output / "staged" / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, Path):
            require(approved_hashes is not None and relative in approved_hashes, "Candidate copy has no approved SHA256")
            require(digest(content) == approved_hashes[relative], "Candidate changed after qualification")
            shutil.copy2(content, staged)
            require(digest(staged) == approved_hashes[relative], "Staging copy differs from approved bytes")
        else:
            staged.write_bytes(content)
        if destination.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup)
            require(digest(backup) == observed, "Recovery copy differs")
        operations.append({"path": relative, "before_sha256": observed, "after_sha256": digest(staged),
                           "backup": str(backup) if observed is not None else None, "staged": str(staged)})
    save(output / "recovery-manifest.json", {"root": str(root), "operations": operations})
    completed = []
    try:
        for operation in operations:
            destination = target(root, operation["path"])
            observed = digest(destination) if destination.exists() else None
            require(observed == operation["before_sha256"], "Concurrent destination edit at commit: " + operation["path"])
            require(digest(operation["staged"]) == operation["after_sha256"], "Staged bytes changed before commit")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(operation["staged"], destination)
            completed.append(operation)
            require(digest(destination) == operation["after_sha256"], "Committed bytes differ")
            save(output / "transaction.json", {"state": "committing", "committed": [a["path"] for a in completed]})
            if fail_after is not None and len(completed) == fail_after:
                raise RuntimeError("Injected rollback test")
    except Exception as error:
        conflicts = []
        for operation in reversed(completed):
            destination = target(root, operation["path"])
            if not destination.exists() or digest(destination) != operation["after_sha256"]:
                conflicts.append(operation["path"])
                continue
            if operation["backup"] is None:
                destination.unlink()  # One verified new file inside requested root.
            else:
                recovery = output / "rollback" / operation["path"]
                recovery.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(operation["backup"], recovery)
                require(digest(recovery) == operation["before_sha256"], "Rollback bytes differ")
                os.replace(recovery, destination)
        save(output / "transaction.json", {"state": "rollback_conflict" if conflicts else "rolled_back", "error": str(error), "conflicts": conflicts})
        raise
    save(output / "transaction.json", {"state": "installed", "files": len(operations), "operations": operations})


def self_test():
    base = ROOT / ".local/runtime-delivery-installer-tests" / uuid.uuid4().hex
    root = base / "root"; root.mkdir(parents=True)
    one, two = root / "one", root / "two"
    one.write_bytes(b"first"); two.write_bytes(b"second")
    expected = {"one": digest(one), "two": digest(two)}
    try:
        apply_transaction(root, {"one": b"changed", "two": b"changed2"}, expected, root / ".local/rollback-test", fail_after=1)
    except RuntimeError:
        pass
    require(one.read_bytes() == b"first" and two.read_bytes() == b"second", "Rollback did not restore originals")
    apply_transaction(root, {"one": b"changed", "two": b"changed2"}, expected, root / ".local/success-test")
    require(one.read_bytes() == b"changed" and two.read_bytes() == b"changed2", "Transaction failed")
    try:
        apply_transaction(root, {"one": b"bad"}, {"one": "0" * 64}, root / ".local/conflict-test")
    except ValueError:
        pass
    else:
        raise AssertionError("Stale source accepted")
    candidate = base / "candidate"
    candidate.write_bytes(b"approved candidate")
    pinned = digest(candidate)
    apply_transaction(root, {"one": candidate}, {"one": digest(one)}, root / ".local/copy-test", approved_hashes={"one": pinned})
    require(one.read_bytes() == b"approved candidate", "Approved file copy failed")
    candidate.write_bytes(b"changed after validation")
    try:
        apply_transaction(root, {"one": candidate}, {"one": digest(one)}, root / ".local/changed-candidate-test", approved_hashes={"one": pinned})
    except ValueError:
        pass
    else:
        raise AssertionError("Changed candidate accepted")
    require(one.read_bytes() == b"approved candidate", "Rejected candidate changed runtime")
    try:
        apply_transaction(root, {"new": b"temporary new file"}, {"new": None}, root / ".local/new-file-rollback-test", fail_after=1)
    except RuntimeError:
        pass
    require(not (root / "new").exists(), "Rollback did not restore original absence")
    policy = b'[remap]\r\npath="keep"\r\n[params]\r\nanimation/fps=3072.0\r\nmeshes/ensure_tangents=true\r\n'
    require(import_policy(policy, 240) == policy.replace(b"animation/fps=3072.0", b"animation/fps=240"), "Policy changed unrelated bytes")
    try:
        target(root, "../outside")
    except ValueError:
        pass
    else:
        raise AssertionError("Destination escaped root")
    return {"passed": True, "checks": ["injected failure rollback", "verified successful replacement", "stale destination rejection", "approved file-copy SHA guard", "changed candidate rejection before runtime write", "new-file rollback restores absence", "FPS-only import policy edit", "destination confinement"], "evidence": str(base)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--blender-index", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2)); return
    if not all((args.plan, args.manifest, args.blender_index, args.output)):
        parser.error("--plan, --manifest, --blender-index and a new --output directory are required")
    root, output = args.root.resolve(), args.output.resolve()
    require(".local" in output.parts and not output.exists(), "Use a new ignored .local output directory")
    if args.install:
        require(output.is_relative_to(root / ".local"), "Install recovery output must be inside target worktree/.local")
        require((root / ".git").is_file(), "Installation requires a task-specific Git worktree; do not modify the primary checkout")
    writes, expected, deliveries = qualify(root, args.plan, args.manifest, args.blender_index)
    output.mkdir(parents=True)
    summary = {"state": "validated_dry_run", "actor_count": len(deliveries), "file_count": len(writes),
               "held_qualified_no_raw_saving": ["moss_bear", "leafwing_owl"],
               "source_bytes": sum(a["source_bytes"] for a in deliveries), "runtime_bytes": sum(a["runtime_bytes"] for a in deliveries),
               "saved_bytes": sum(a["source_bytes"] - a["runtime_bytes"] for a in deliveries),
               "actors": deliveries, "expected_before_hashes": expected,
               "input_hashes": {"plan": digest(args.plan), "manifest": digest(args.manifest), "blender_index": digest(args.blender_index)},
               "installer_sha256": digest(__file__), "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    save(output / "validated-plan.json", summary)
    if args.install:
        with installation_lock(root):
            # Re-qualify under the transaction lock; no preflight result can
            # authorize replacing bytes changed while it was being reviewed.
            writes, expected, deliveries = qualify(root, args.plan, args.manifest, args.blender_index)
            approved_hashes = {a["runtime_path"]: a["runtime_sha256"] for a in deliveries}
            apply_transaction(root, writes, expected, output, approved_hashes=approved_hashes)
            summary["actors"] = deliveries
            summary["expected_before_hashes"] = expected
        summary["state"] = "installed"
        save(output / "validated-plan.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("actors", "expected_before_hashes")}, indent=2))


if __name__ == "__main__":
    main()
