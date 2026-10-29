"""Prepare/install exact visually accepted bakes; no fitting or re-encoding.

Default is a dry run. 191 selections are explicit: 89 saved button approvals,
one Mossbound Golem acceptance comment, and 101 exact versions authorized by a
CURRENT user instruction. Queue visibility alone NEVER authorizes installation.
The group authorization JSON is a separate current instruction, not a fabricated
historical journal event. Fourteen unapproved entries and the already-installed
accepted tortoise remain unchanged. Fifteen new local selections use their
hash-bound owner-qualified metadata; shared generic animation maps are untouched.

Required inputs: --catalog (full ordered archive), --current-catalog, --manifest,
--journal, --visibility, --group-authorization, --owner-metadata, --output.
--root selects the target worktree. --install is the only write authorization.
No historical profiles/fixtures are changed. Recovery uses the existing guarded
transaction implementation, retaining original assets/metadata and SHA manifests.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

from install_creature_runtime_delivery import (
    ROOT, ROSTER, RECEIPT as CLOSE_RECEIPT, apply_transaction, digest,
    glb_document, import_policy, installation_lock, json_bytes, read, require,
    save, target,
)

VISUAL_RECEIPT = "docs/qa/creature-storage/visually-accepted-delivery.json"
OWNER_SHA = "6e8acd3687c28b15147701c8c095c63146c5168bcc3d24818c70b7ab888ccd5e"
GROUP_REASON = "Remaining close-alternative tail waived by user after reviewing first 30"
HELD = {"cobra", "crystal_cave_spider", "giant_wasp", "nightweave_spider", "ostrich", "penguin", "saltmarsh_crocodile", "sapphire_peafowl", "skeleton", "snow_yeti", "storm_chimera", "tengu", "two_headed_giant", "viridian_basilisk"}
LEGACY_SCOPE = "Hash-bound legacy actual-client captures: direct finite sampled poses/defaults/RESET/held ends and first-tick switch observations. These are not a continuous-time bound, stepped-crossfade-run proof, GPU/VFX parity proof or new numeric acceptance threshold. Visual acceptance is authoritative for the exact displayed bytes."


def event_sha(event):
    return hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def select_versions(catalog, events, visibility, authorization, expected=(89, 1, 101)):
    """Classify authority without turning a queue filter into a user approval."""
    entries = {e["id"]: e for e in catalog["entries"]}
    require(len(entries) == len(catalog["entries"]), "Duplicate archived creature ID")
    chosen = {}
    buttons = [e for e in events if e.get("type") == "approve" and e.get("test_only") is False]
    require(len(buttons) == len({e["actor"] for e in buttons}) == expected[0], "Saved approval inventory changed; reconcile exact versions")
    for event in buttons:
        require(event.get("scope") == "creature_candidate_all_clips", "Approval has a different scope")
        chosen[event["actor"]] = {"pin": event, "basis": {"kind": "saved_button_approval", "event_id": event["event_id"], "event_sha256": event_sha(event), "utc": event["utc"]}}
    comments = [e for e in events if e.get("type") == "comment" and e.get("test_only") is False and e.get("actor") == "mossbound_stone_golem" and str(e.get("text", "")).lower().startswith("approved as alternative to the current")]
    require(len(comments) == expected[1], "Missing exact Mossbound Golem acceptance comment")
    for event in comments:
        require(event["actor"] not in chosen, "Acceptance comment already counted as button approval")
        chosen[event["actor"]] = {"pin": event, "basis": {"kind": "saved_explicit_acceptance_comment", "event_id": event["event_id"], "event_sha256": event_sha(event), "utc": event["utc"], "repair_note_retained": True}}
    group = [r for r in visibility["hidden"] if r["reason"] == GROUP_REASON]
    require(len(group) == len({r["actor"] for r in group}) == expected[2], "Group membership changed")
    require(authorization.get("kind") == "current_user_group_instruction" and authorization.get("authorized") is True and authorization.get("variant") == "zero-bake" and authorization.get("count") == expected[2], "Queue visibility is not approval; provide the explicit current group instruction")
    for row in group:
        require(row["actor"] not in chosen, "Group instruction overlaps saved explicit approvals")
        chosen[row["actor"]] = {"pin": row, "basis": {"kind": "current_user_group_instruction", "instruction_summary": authorization["instruction_summary"], "not_a_historical_journal_event": True}}
    require(len(chosen) == sum(expected), "Wrong accepted selection count")
    for name, selection in chosen.items():
        pin = selection["pin"]
        require(pin["variant"] == "zero-bake", name + ": unsupported accepted variant")
        entry = entries[name]
        require(entry["source"]["sha256"] == pin["source_sha256"], name + ": acceptance source differs from archived catalog")
        versions = [v for v in entry["variants"] if v["id"] == pin["variant"] and v["sha256"] == pin["candidate_sha256"]]
        require(len(versions) == 1, name + ": accepted exact version is absent/ambiguous in archive")
        selection.update(entry=entry, variant=versions[0])
    return chosen


def checked_owner(row, actor, current_config, candidate_document):
    require(row["selected_model_sha256"] == actor["sha256"], actor["id"] + ": owner selected source differs")
    for path_field, hash_field in (("selected_model_path", "selected_model_sha256"), ("profile_path", "profile_sha256"), ("source_inventory_path", "source_inventory_sha256")):
        require(digest(row[path_field]) == row[hash_field], actor["id"] + ": owner source/profile/inventory changed")
    stages = row["qualified_map_and_registry_candidates"]
    require(len(stages) == 1, actor["id"] + ": owner metadata selection is ambiguous")
    stage = stages[0]
    require(digest(stage["stage_receipt"]) == stage["stage_receipt_sha256"] and digest(stage["animation_map_path"]) == stage["animation_map_sha256"], actor["id"] + ": owner stage/map bytes changed")
    require(read(stage["animation_map_path"]) == stage["animation_map"], actor["id"] + ": embedded qualified map differs")
    config = copy.deepcopy(stage["registry_entry"])
    require(config.get("import") == current_config.get("import"), actor["id"] + ": qualified metadata changes accepted appearance scale/facing/placement")
    names = {n.get("name") for n in candidate_document["nodes"]}
    require(all(name in names for name in config.get("attachments", {}).values()), actor["id"] + ": qualified attachment absent from accepted payload")
    staged_source = Path(stage["qualified_project"]) / config["scene"].removeprefix("res://")
    require(digest(staged_source) == actor["sha256"], actor["id"] + ": qualified policy source differs from selected source")
    policy_path = Path(str(staged_source) + ".import")
    policy = policy_path.read_bytes()
    return config, copy.deepcopy(stage["animation_map"]), {"owner_profile_sha256": row["profile_sha256"], "owner_stage_receipt_sha256": stage["stage_receipt_sha256"], "owner_map_sha256": stage["animation_map_sha256"], "owner_source_inventory_sha256": row["source_inventory_sha256"], "owner_import_policy_sha256": digest(policy_path)}, policy


def new_import_policy(owner_policy, relative):
    """Keep qualified params, never isolated UIDs or imported-cache remaps."""
    text = owner_policy.decode("utf-8")
    section = re.search(r"(?ms)^\[params\]\r?\n(.*?)(?=^\[|\Z)", text)
    require(section is not None, "Qualified policy has no params")
    params = section.group(1)
    require(not re.search(r'"[A-Za-z]:[\\/]', params), "Qualified import params contain a private absolute path")
    source = "res://" + relative.removeprefix("godot-client/")
    fresh = '[remap]\nimporter="scene"\nimporter_version=1\ntype="PackedScene"\n\n[deps]\nsource_file=' + json.dumps(source) + '\n\n[params]\n' + params
    return import_policy(fresh.encode("utf-8"), 30)


def old_local_runtime_lineage(root, actor, current_sha):
    """A local updated selection can replace a losslessly packed OLD runtime."""
    matches = []
    for path in (root / "docs/qa/creature-storage").rglob(actor["id"] + ".json"):
        receipt = read(path)
        final = receipt.get("candidate_sha256", receipt.get("runtime_sha256"))
        if receipt.get("source_sha256") == actor["historical_runtime_sha256"] and final == current_sha:
            matches.append({"receipt": str(path.relative_to(root)).replace("\\", "/"), "receipt_sha256": digest(path),
                            "historical_runtime_sha256": actor["historical_runtime_sha256"], "packed_old_runtime_sha256": current_sha})
    require(len(matches) == 1, actor["id"] + ": unexpected current old-runtime hash has no unique exact-storage predecessor receipt")
    return matches[0]


def qualify(root, inputs):
    paths = {key: Path(value).resolve() for key, value in inputs.items()}
    hashes = {key: digest(path) for key, path in paths.items()}
    catalog, current, manifest, visibility, authorization, owner = [read(paths[k]) for k in ("catalog", "current_catalog", "manifest", "visibility", "group_authorization", "owner_metadata")]
    events = [json.loads(line) for line in paths["journal"].read_text(encoding="utf-8").splitlines() if line.strip()]
    require(hashes["owner_metadata"] == OWNER_SHA and owner["source_handoff_sha256"] == manifest["handoff_sha256"], "Owner metadata/handoff selection changed")
    require(authorization["catalog_sha256"] == hashes["catalog"] and authorization["visibility_sha256"] == hashes["visibility"], "Current user group instruction does not pin this exact archive/visibility cohort")
    selected = select_versions(catalog, events, visibility, authorization)
    actors = {a["id"]: a for a in manifest["actors"]}
    require(set(actors) - set(selected) - {"crystalback_tortoise"} == HELD, "Unapproved set differs; never install a newly generated unaccepted version")
    require(not any(e.get("id") == "crystalback_tortoise" for e in [s["entry"] for s in selected.values()]), "Previously installed tortoise must remain separate")
    current_entries = {e["id"]: e for e in current["entries"]}
    models = read(root / "godot-client/data/actors/models.json")
    roster = read(root / ROSTER)
    roster_rows = {a["id"]: a for a in roster["creatures"]}
    owner_rows = {a["id"]: a for a in owner["actors"]}
    close = read(root / CLOSE_RECEIPT)
    tortoise = actors["crystalback_tortoise"]
    require(tortoise["status"] == "accepted_v2_installed" and digest(target(root, tortoise["runtime_repository_path"])) == tortoise["sha256"], "Already-accepted tortoise changed; reconcile separately")
    writes, expected, rows = {}, {}, []
    notes = {}
    for event in events:
        if event.get("type") == "comment" and event.get("test_only") is False:
            notes.setdefault(event["actor"], []).append({"event_id": event["event_id"], "event_sha256": event_sha(event), "candidate_sha256": event["candidate_sha256"]})

    def metadata(relative, payload):
        require(relative not in writes, "Shared metadata collision: " + relative)
        destination = target(root, relative)
        writes[relative] = payload
        expected[relative] = digest(destination) if destination.exists() else None

    for name, selection in selected.items():
        entry, variant, basis = selection["entry"], selection["variant"], selection["basis"]
        actor = actors[name]
        source = Path(entry["source"]["path"])
        candidate = Path(variant["path"])
        source_sha, candidate_sha = actor["sha256"], variant["sha256"]
        require(entry["source"]["sha256"] == digest(source) == source_sha, name + ": displayed frozen source changed")
        require(digest(candidate) == candidate_sha and candidate.stat().st_size == variant["bytes"], name + ": accepted bytes changed; do not substitute a newer bake")
        if name in current_entries:
            same_id = [v for v in current_entries[name]["variants"] if v["id"] == "zero-bake"]
            require(any(v["sha256"] == candidate_sha for v in same_id), name + ": currently offered variant differs from the accepted exact version")
        relative = actor["runtime_repository_path"]
        require(relative.startswith("godot-client/assets/actors/native/creatures/") and relative.endswith(".glb"), "Unexpected runtime path")
        runtime = target(root, relative)
        before = digest(runtime)
        old_local_lineage = None
        predecessor = close["actors"].get(name)
        if predecessor and predecessor["runtime_sha256"] == before:
            require(predecessor["source_sha256"] == source_sha, name + ": current close delivery has a different source")
            current_basis = "previous_conservative_close_delivery"
        elif actor["was_installed"] and before == source_sha:
            current_basis = "frozen_installed_selection"
        elif not actor["was_installed"] and before == actor["historical_runtime_sha256"]:
            current_basis = "original_runtime_before_local_selection"
        elif not actor["was_installed"]:
            old_local_lineage = old_local_runtime_lineage(root, actor, before)
            current_basis = "losslessly_packed_old_runtime_before_local_selection"
        else:
            raise ValueError(name + ": current runtime SHA is not an authorized known predecessor (" + before + ")")
        require(roster_rows[name]["sha256"] == before, name + ": active roster/current runtime disagree")
        config = models["models"][name]
        require("godot-client/" + config["scene"].removeprefix("res://") == relative and config["animationLibrary"] == config["scene"], name + ": active scene/library paths differ")
        document = glb_document(candidate)
        require(document["asset"].get("extras", {}).get("rabbitlands_animation_bake_fps") == 30, name + ": accepted zero-bake must declare 30fps")
        require(all(not p.get("targets") for m in document["meshes"] for p in m["primitives"]), name + ": accepted zero-bake still has corrective targets")
        require([a["name"] for a in document["animations"]] == actor["clips"] == entry["clips"], name + ": native clip inventory/order changed")
        evidence_paths = {key: Path(value) for key, value in variant["evidence"].items() if key in {"build_report", "client_report", "blender_report"}}
        require(set(evidence_paths) == {"build_report", "client_report", "blender_report"}, name + ": incomplete exact-version evidence")
        build, client, blender = [read(evidence_paths[key]) for key in ("build_report", "client_report", "blender_report")]
        require(build.get("sha256") == candidate_sha, name + ": bake report belongs to other bytes")
        sampled = next(v for v in entry["variants"] if v["id"] == "sampled-30")
        require(build["source_sha256"] == sampled["sha256"] == digest(sampled["path"]), name + ": bake-to-sampled source chain differs")
        sampling = read(sampled["evidence"]["build_report"])
        require(sampling["source_sha256"] == source_sha and sampling["candidate_sha256"] == sampled["sha256"] and sampling["fps"] == 30, name + ": sampling source lineage changed")
        require([m["sha256"] for m in client["models"]] == [source_sha, candidate_sha], name + ": actual-client proof is not full displayed source to accepted payload")
        require(all("GlbSceneCache._build_raw" in m["load_proof"]["actual_loader"] for m in client["models"]), name + ": proof is not the raw actual-client loader")
        require(set(client["native_clips"]) == set(actor["clips"]) and all(client["placement"].values()), name + ": native inventory/placement gate failed")
        capture = evidence_paths["client_report"].parent / "client"
        require(digest(capture / "metadata.json") == client["provenance"]["metadata_sha256"] and digest(capture / "states.f32") == client["provenance"]["states_sha256"], name + ": client capture bytes changed")
        observed = read(capture / "metadata.json")["descriptions"]
        require(observed[0]["clips"] == observed[1]["clips"], name + ": native durations/loop policies differ")
        require(blender["sha256"] == blender["expected_sha256"] == candidate_sha and blender["status"] == "passed_fresh_import_finite_only" and blender["all_clips_finite"] is True, name + ": exact fresh Blender finite-state proof failed")
        require({c["name"] for c in blender["source_inventory"]["clips"]} == set(actor["clips"]), name + ": Blender omitted clips")
        evidence = {key + "_sha256": digest(path) for key, path in evidence_paths.items()}
        evidence["sampling_report_sha256"] = digest(sampled["evidence"]["build_report"])
        evidence["client_probe_sha256"] = client["provenance"]["probe_sha256"]
        evidence["client_checker_sha256"] = client["provenance"]["checker_sha256"]
        evidence["blender_validator_sha256"] = blender["validator_sha256"]
        old_map_path = "godot-client/" + config["animationMap"].removeprefix("res://")
        mapping = read(target(root, old_map_path))
        local_metadata = None
        owner_policy = None
        if actor["selected_local_draft"]:
            config, mapping, local_metadata, owner_policy = checked_owner(owner_rows[name], actor, config, document)
            config["scene"] = config["animationLibrary"] = "res://" + relative.removeprefix("godot-client/")
            config["animationMap"] = f"res://data/animations/visually-approved/{name}.json"
            models["models"][name] = config
        map_relative = "godot-client/" + config["animationMap"].removeprefix("res://")
        require(map_relative != "godot-client/data/animations/creature.json", name + ": must not mutate shared generic map")
        previous_review = mapping.get("reviewStatus")
        acceptance = {"receipt": VISUAL_RECEIPT, "actor": name, "appliesToSHA256": candidate_sha,
                      "scope": "exact_candidate_all_native_clips", "approvalBasis": basis,
                      "previousAuthoringReviewStatus": previous_review, "repairNoteEvents": notes.get(name, [])}
        mapping["reviewStatus"] = "accepted"
        mapping["runtimeVisualAcceptance"] = acceptance
        previous_optimization = mapping.get("runtimeOptimization")
        mapping["runtimeOptimization"] = {"receipt": VISUAL_RECEIPT, "actor": name, "sourceSHA256": source_sha,
                                           "previousRuntimeSHA256": before, "runtimeSHA256": candidate_sha,
                                           "method": "visually_accepted_offline_corrective_bake", "bakeFPS": 30,
                                           "previousRuntimeOptimization": previous_optimization}
        metadata(map_relative, json_bytes(mapping))
        policy_path = target(root, relative + ".import")
        if policy_path.exists():
            policy = import_policy(policy_path.read_bytes(), 30)
        else:
            require(owner_policy is not None, name + ": missing import policy without a qualified owner stage")
            policy = new_import_policy(owner_policy, relative)
        metadata(relative + ".import", policy)
        writes[relative], expected[relative] = candidate, before
        roster_rows[name]["sha256"] = candidate_sha
        roster_rows[name]["runtimeVisualAcceptance"] = acceptance
        if predecessor and predecessor["runtime_sha256"] == before:
            predecessor["superseded_by"] = {"receipt": VISUAL_RECEIPT, "runtime_sha256": candidate_sha,
                                            "reason": "Exact-version visual acceptance or explicit current user group instruction"}
        rows.append({"actor": name, "runtime_path": relative, "source_sha256": source_sha, "previous_runtime_sha256": before,
                     "runtime_sha256": candidate_sha, "previous_runtime_basis": current_basis,
                     "previous_runtime_exact_storage_lineage": old_local_lineage,
                     "was_installed_selection": actor["was_installed"], "new_local_selection": actor["selected_local_draft"],
                     "previous_runtime_bytes": runtime.stat().st_size, "runtime_bytes": candidate.stat().st_size,
                     "declared_animation_bake_fps": 30, "corrective_targets": 0, "clips": actor["clips"],
                     "approval_basis": basis, "repair_note_events": notes.get(name, []), "legacy_client_measurements": client["summary"],
                     "legacy_client_scope": LEGACY_SCOPE, "blender_scope": "Exact bytes freshly imported; every native clip finite at recorded samples. No equivalence or artistic approval inferred from Blender alone.",
                     "evidence": evidence, "local_metadata_evidence": local_metadata})
    require(sum(r["new_local_selection"] for r in rows) == 15, "Expected exactly 15 newly accepted local selections")
    held = [{"actor": name, "runtime_sha256": digest(target(root, actors[name]["runtime_repository_path"])),
             "repair_note_events": notes.get(name, []), "reason": "No exact-version acceptance; current runtime unchanged"} for name in sorted(HELD)]
    receipt = {"schema_version": 1, "scope": "Exact visually accepted alternatives. Current user instruction separately authorizes the 101-entry 30fps group; no historical journal approvals were fabricated. Historical profiles/fixtures are immutable.",
               "input_hashes": hashes, "approval_counts": {"saved_button_approval": 89, "saved_explicit_acceptance_comment": 1, "current_user_group_instruction": 101},
               "actors": {r["actor"]: r for r in rows}, "held_unapproved": held,
               "previously_accepted_tortoise": "Already installed; omitted from transaction"}
    metadata("godot-client/data/actors/models.json", json_bytes(models))
    metadata(ROSTER, json_bytes(roster))
    metadata(CLOSE_RECEIPT, json_bytes(close))
    metadata(VISUAL_RECEIPT, json_bytes(receipt))
    require(all(digest(path) == hashes[key] for key, path in paths.items()), "An input ledger/catalog changed during qualification; retry a stable snapshot")
    return writes, expected, rows, receipt


def self_test():
    def entry(name, sha):
        return {"id": name, "source": {"sha256": "s"}, "variants": [{"id": "zero-bake", "sha256": sha}]}
    catalog = {"entries": [entry("button", "a"), entry("mossbound_stone_golem", "b"), entry("group", "c")]}
    events = [{"type": "approve", "scope": "creature_candidate_all_clips", "test_only": False, "actor": "button", "variant": "zero-bake", "source_sha256": "s", "candidate_sha256": "a", "event_id": "1", "utc": "test"},
              {"type": "comment", "test_only": False, "actor": "mossbound_stone_golem", "variant": "zero-bake", "source_sha256": "s", "candidate_sha256": "b", "event_id": "2", "utc": "test", "text": "approved as alternative to the current, repair note retained"}]
    visibility = {"hidden": [{"actor": "group", "reason": GROUP_REASON, "variant": "zero-bake", "source_sha256": "s", "candidate_sha256": "c"}]}
    auth = {"kind": "current_user_group_instruction", "authorized": True, "variant": "zero-bake", "count": 1, "instruction_summary": "Current explicit user request"}
    selected = select_versions(catalog, events, visibility, auth, expected=(1, 1, 1))
    require(len(selected) == 3 and selected["group"]["basis"]["not_a_historical_journal_event"], "Authority classification failed")
    for bad_auth in ({}, dict(auth, authorized=False)):
        try: select_versions(catalog, events, visibility, bad_auth, expected=(1, 1, 1))
        except ValueError: pass
        else: raise AssertionError("Queue visibility became approval")
    bad = copy.deepcopy(events); bad[0]["candidate_sha256"] = "unaccepted-new-version"
    try: select_versions(catalog, bad, visibility, auth, expected=(1, 1, 1))
    except ValueError: pass
    else: raise AssertionError("Unaccepted version substituted")
    policy = new_import_policy(b'[remap]\nuid="uid://private"\npath="res://.godot/old.scn"\n[params]\nanimation/fps=1536\nmeshes/force_disable_compression=true\n', "godot-client/assets/actors/native/creatures/control.glb")
    require(b'uid://' not in policy and b'.godot/' not in policy and b'animation/fps=30' in policy and b'force_disable_compression=true' in policy, "New policy copied isolated cache/UID or lost qualified params")
    return {"passed": True, "checks": ["separate button/comment/current-group authority", "queue filter alone never approves", "stale exact-version pin rejected", "new policy preserves params but strips isolated UIDs/cache"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    for name in ("catalog", "current-catalog", "manifest", "journal", "visibility", "group-authorization", "owner-metadata", "output"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2)); return
    keys = ("catalog", "current_catalog", "manifest", "journal", "visibility", "group_authorization", "owner_metadata")
    require(all(getattr(args, key) is not None for key in keys) and args.output is not None, "Provide all catalog/authority/metadata inputs and a new output directory")
    root, output = args.root.resolve(), args.output.resolve()
    require(".local" in output.parts and not output.exists(), "Use a new ignored .local output directory")
    if args.install:
        require((root / ".git").is_file() and output.is_relative_to(root / ".local"), "Install only in a task-specific Git worktree with local recovery output")
    inputs = {key: getattr(args, key) for key in keys}
    writes, expected, rows, receipt = qualify(root, inputs)
    output.mkdir(parents=True)
    summary = {"state": "validated_dry_run", "actors": len(rows), "new_local_selections": 15, "file_count": len(writes),
               "previous_runtime_bytes": sum(r["previous_runtime_bytes"] for r in rows), "runtime_bytes": sum(r["runtime_bytes"] for r in rows),
               "approval_counts": receipt["approval_counts"], "installer_sha256": digest(__file__),
               "input_hashes": receipt["input_hashes"], "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    save(output / "validated-plan.json", dict(summary, deliveries=rows, expected_before_hashes=expected))
    save(output / "prospective-public-receipt.json", receipt)
    if args.install:
        with installation_lock(root):
            writes, expected, rows, receipt = qualify(root, inputs)
            apply_transaction(root, writes, expected, output, approved_hashes={r["runtime_path"]: r["runtime_sha256"] for r in rows})
        summary["state"] = "installed"
        save(output / "validated-plan.json", dict(summary, deliveries=rows, expected_before_hashes=expected))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
