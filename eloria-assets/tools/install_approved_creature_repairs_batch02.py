"""Guarded delivery of the four exact accepted batch02 repairs; dry run default.

Mossbound Golem is explicitly excluded. The batch01 registry stays immutable.
No fitting, re-encoding, push or implicit approval occurs. --install is restricted
to a task worktree and uses the existing staged backup/rollback transaction.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from install_creature_runtime_delivery import (
    ROOT, ROSTER, RECEIPT as CLOSE_RECEIPT, apply_transaction, digest,
    glb_document, import_policy, installation_lock, json_bytes, read, require,
    save, target,
)
from install_accepted_creature_bakes import (
    OWNER_SHA, VISUAL_RECEIPT, checked_owner, new_import_policy,
    old_local_runtime_lineage, event_sha,
)
from install_approved_creature_repairs import counts, assert_original_nodes

RECEIPT = "docs/qa/creature-storage/accepted-repair-delivery-batch02.json"
BATCH01_RECEIPT = "docs/qa/creature-storage/accepted-repair-delivery.json"
MODELS = "godot-client/data/actors/models.json"
NATIVE = "godot-client/data/actors/native_asset_catalog.json"
ACTORS = {"autumn_bark_treant", "crystal_cave_spider", "storm_chimera", "ostrich"}
EXCLUDED = {"mossbound_stone_golem"}
CATALOG_SHA = "da6ecacbb3e42420d376e6530447f4aedc506d2a04309c29773928583ad1d47a"
INDEX_SHA = "531bf7e832c659258ccc7dfdd1560d4a0600ea45c44d52739db625a1fae556d8"


def approved_entries(catalog, authorization, catalog_sha):
    require(catalog_sha == CATALOG_SHA and catalog.get("complete") is True,
            "Wrong or incomplete batch02 review catalog")
    entries = catalog["entries"]
    require(len(entries) == 5 and {e["id"] for e in entries} == ACTORS | EXCLUDED,
            "Expected the unchanged five-entry reviewed catalog")
    require(authorization.get("kind") == "current_user_repair_instruction"
            and authorization.get("authorized") is True and authorization.get("count") == 4
            and authorization.get("catalog_sha256") == catalog_sha
            and authorization.get("scope") == "exact_candidates_all_native_clips"
            and isinstance(authorization.get("instruction_summary"), str)
            and bool(authorization["instruction_summary"].strip()), "Missing current exact four-actor instruction")
    require(len(authorization.get("actors", [])) == 4 and set(authorization["actors"]) == ACTORS,
            "Wrong approval inventory; rejected Golem must never be selected")
    require(authorization.get("excluded_actors") == ["mossbound_stone_golem"],
            "Explicit rejected Golem exclusion is missing")
    require(all(len(e["variants"]) == 1 for e in entries), "Ambiguous displayed candidate version")
    return [e for e in entries if e["id"] in ACTORS]


def checked_approvals(entries, authorization, events, catalog_sha):
    require(set(authorization.get("approval_events", {})) == ACTORS, "Missing exact saved approvals")
    approved = {}
    for entry in entries:
        name, variant = entry["id"], entry["variants"][0]
        pin = authorization["approval_events"][name]
        matches = [e for e in events if e.get("event_id") == pin["event_id"]]
        require(len(matches) == 1, name + ": approval missing/ambiguous")
        event = matches[0]
        require(event_sha(event) == pin["event_sha256"] and event.get("type") == "approve"
                and event.get("test_only") is False and event.get("scope") == "creature_candidate_all_clips"
                and event.get("actor") == event.get("registry_actor") == name
                and event.get("variant") == variant["id"] and event.get("catalog_sha256") == catalog_sha
                and event.get("source_sha256") == entry["source"]["sha256"]
                and event.get("candidate_sha256") == variant["sha256"], name + ": exact approved bytes differ")
        approved[name] = {"event_id": event["event_id"], "event_sha256": event_sha(event), "utc": event["utc"]}
    return approved


def validate_owner_selection(actor, owner_rows):
    require(actor["selected_local_draft"] == (actor["id"] == "storm_chimera"),
            "Unexpected owner-upgrade selection; Crystal/Ostrich retain current behavior")
    if actor["selected_local_draft"]:
        require(actor["id"] in owner_rows, "Missing qualified owner metadata")


def reviewed_owner_upgrade(row, actor, current_config, current_map, document):
    config, qualified, evidence, policy = checked_owner(row, actor, current_config, document)
    not_promoted = {"playbackSpeeds", "strideScalesWithActor", "strideMetresPerSecond",
                    "reviewStatus", "concept", "locomotionMode"}
    for key in set(current_map) | set(qualified):
        if key not in not_promoted:
            require(current_map.get(key) == qualified.get(key), "Owner action/command/loop inventory differs: " + key)
    evidence["reviewed_runtime_playback_policy_preserved"] = True
    evidence["qualified_fields_not_promoted"] = sorted(key for key in not_promoted if current_map.get(key) != qualified.get(key))
    evidence["attachment_aliases"] = config.get("attachments", {})
    return config, copy.deepcopy(current_map), evidence, policy


def update_native_catalog(native, name, relative, document, structural, acceptance, display_name, source_sha):
    matches = []
    def visit(value):
        if isinstance(value, dict):
            if value.get("path") == relative:
                matches.append(value)
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(native)
    if not matches:
        value = {"id": name, "name": display_name, "path": relative, "sourceSHA256": source_sha}
        native["creatures"][name] = value
        matches.append(value)
    previous = [row.get("sha256") for row in matches]
    for row in matches:
        row.update(structural, sha256=acceptance["appliesToSHA256"], path=relative, runtimeVisualAcceptance=acceptance)
    validation = native["validation"]["results"]
    require(relative in validation, "Missing native validation path")
    validation[relative] = {"nodes": len(document["nodes"]), "meshes": len(document["meshes"]),
                            "skins": len(document["skins"]), "animations": len(document["animations"])}
    return previous


def pinned(item):
    require(digest(item["path"]) == item["sha256"], "Evidence bytes changed: " + Path(item["path"]).name)
    if "bytes" in item:
        require(Path(item["path"]).stat().st_size == item["bytes"], "Evidence size changed")
    return read(item["path"])


def checked_evidence(entry, variant):
    pins = variant["evidence"]
    require(pins["artifact_index_sha256"] == INDEX_SHA and digest(pins["artifact_index"]) == INDEX_SHA,
            "Expected exact completed artifact-index-v008")
    require(digest(pins["handoff"]) == pins["handoff_sha256"], "Owner final handoff changed")
    index = read(pins["artifact_index"])
    require(index["complete"] is True and not index["pending"] and not index["errors"], "Independent artifact index incomplete")
    rows = [r for r in index["actors"] if r["actor"] == entry["id"]]
    require(len(rows) == 1, "Missing/ambiguous independent actor index")
    row = rows[0]
    require(row["variant_id"] == variant["id"] and row["candidate"]["sha256"] == variant["sha256"]
            and row["candidate"]["bytes"] == variant["bytes"]
            and row["commented_baseline"]["sha256"] == entry["source"]["sha256"]
            and row["active_runtime"]["sha256"] == entry["active_runtime"]["sha256"]
            and row["handoff"]["sha256"] == pins["handoff_sha256"], "Artifact lineage differs from accepted display")
    ev = row["evidence"]
    files = []
    def visit(value, kind):
        if isinstance(value, dict):
            if "path" in value and "sha256" in value:
                require(digest(value["path"]) == value["sha256"], "Indexed evidence changed: " + kind)
                files.append({"kind": kind, "sha256": value["sha256"]})
            else:
                for key, child in value.items(): visit(child, kind + "/" + key)
        elif isinstance(value, list):
            for i, child in enumerate(value): visit(child, kind + "/" + str(i))
    visit(ev, "evidence")
    client = pinned(ev["actual_client"])
    require(client["models"][0]["sha256"] == ev["client_source_sha256"]
            and client["models"][-1]["sha256"] == variant["sha256"], "Actual-client model versions differ")
    require(all("GlbSceneCache._build_raw" in m["load_proof"]["actual_loader"] for m in client["models"])
            and all(client["placement"].values()) and set(client["native_clips"]) == set(entry["clips"]),
            "Actual-client raw loader/placement/native inventory failed")
    capture = Path(ev["actual_client"]["path"]).parent / "client"
    require(digest(capture / "metadata.json") == client["provenance"]["metadata_sha256"]
            and digest(capture / "states.f32") == client["provenance"]["states_sha256"], "Client snapshot payload changed")
    metadata = read(capture / "metadata.json")
    require(metadata["descriptions"][0]["clips"] == metadata["descriptions"][1]["clips"], "Clip duration/loop policy differs")
    require(any(r["category"] == "switch_stepped" for r in metadata["records"]), "Missing stepped-switch evidence")
    if ev["client_source_sha256"] != entry["active_runtime"]["sha256"]:
        placement, job = pinned(ev["active_placement"]), pinned(ev["active_placement_job"])
        require(all(placement["comparison"].values())
                and [f["sha256"] for f in job["actor_fixtures"]] == [entry["active_runtime"]["sha256"], variant["sha256"]],
                "Active model placement has wrong fixture versions")
    require(all(row["active_placement"].values()), "Indexed active placement failed")
    blender = pinned(ev["fresh_blender"])
    if "results" in blender:
        require(blender["passed"] is True and blender["complete"] is True, "Blender aggregate incomplete")
        results = [r for r in blender["results"] if r.get("sha256") == variant["sha256"]]
        require(len(results) == 1, "Blender exact candidate absent")
        result = results[0]
        require(digest(result["report"]) == result["report_sha256"], "Blender detailed report changed")
        blender = read(result["report"])
    require(blender["sha256"] == variant["sha256"] and blender["status"] == "passed_fresh_import_finite_only"
            and blender["all_clips_finite"] is True, "Fresh Blender candidate/finite proof failed")
    visual, visual_job = pinned(ev["visual"]), pinned(ev["visual_job"])
    if "models" in visual_job:
        require(visual_job["models"][-1]["sha256"] == variant["sha256"]
                and visual["models"] == visual_job["models"] and visual["renderer"] == "forward_plus"
                and {r["clip"] for r in visual["clips"]} == set(entry["clips"]), "Actual PBR still inventory/version differs")
    else:
        require(visual["passed"] is True and variant["sha256"] in [p["sha256"] for p in visual["placements"]]
                and set(visual["source_native_clips"]) == set(entry["clips"]), "PBR fitted renderer proof failed")
    return {"artifact_index_sha256": INDEX_SHA, "handoff_sha256": pins["handoff_sha256"], "files": files,
            "actual_client_observations": [{"report_sha256": ev["actual_client"]["sha256"],
                "comparison_sha256": [m["sha256"] for m in client["models"]],
                "summary": client["summary"], "scope": client["scope"]}],
            "media_scope_preserved": True}, row["known_limits"]

def qualify(root, catalog_path, authorization_path, manifest_path, owner_path, journal_path):
    root = Path(root).resolve()
    inputs = {"catalog": Path(catalog_path), "authorization": Path(authorization_path),
              "manifest": Path(manifest_path), "owner_metadata": Path(owner_path), "journal": Path(journal_path)}
    input_hashes = {k: digest(p) for k, p in inputs.items()}
    catalog, authorization, manifest, owner = [read(inputs[k]) for k in ("catalog", "authorization", "manifest", "owner_metadata")]
    entries = approved_entries(catalog, authorization, input_hashes["catalog"])
    require(authorization["journal_sha256"] == input_hashes["journal"], "Approval journal changed")
    approvals = checked_approvals(entries, authorization,
        [json.loads(line) for line in inputs["journal"].read_text(encoding="utf-8").splitlines() if line.strip()], input_hashes["catalog"])
    require(input_hashes["owner_metadata"] == OWNER_SHA
            and owner["source_handoff_sha256"] == manifest["handoff_sha256"], "Owner handoff changed")
    actors = {a["id"]: a for a in manifest["actors"]}
    owner_rows = {a["id"]: a for a in owner["actors"]}
    expected, writes = {}, {}
    rejected = next(e for e in catalog["entries"] if e["id"] == "mossbound_stone_golem")
    rejected_relative = actors[rejected["id"]]["runtime_repository_path"]
    rejected_runtime = target(root, rejected_relative)
    require(digest(rejected_runtime) == rejected["active_runtime"]["sha256"], "Rejected Golem runtime changed")
    rejected_sha = digest(rejected_runtime)

    def load(relative):
        p = target(root, relative)
        data = p.read_bytes()
        expected[relative] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    models, roster, native, close, visual = [load(p) for p in (MODELS, ROSTER, NATIVE, CLOSE_RECEIPT, VISUAL_RECEIPT)]
    rejected_model = copy.deepcopy(models["models"]["mossbound_stone_golem"])
    rejected_roster = copy.deepcopy(next(a for a in roster["creatures"] if a["id"] == "mossbound_stone_golem"))
    generic_map = "godot-client/data/animations/creature.json"
    generic_map_sha = digest(target(root, generic_map))
    batch01_sha = digest(target(root, BATCH01_RECEIPT))
    require(not target(root, RECEIPT).exists(), "Repair receipt already exists; reconcile separately")
    expected[RECEIPT] = None
    roster_rows = {a["id"]: a for a in roster["creatures"]}
    deliveries = []
    basis = {"kind": authorization["kind"], "instruction_summary": authorization["instruction_summary"],
             "catalog_sha256": input_hashes["catalog"], "authorization_sha256": input_hashes["authorization"],
             "not_a_historical_journal_event": True}
    for entry in entries:
        name, variant = entry["id"], entry["variants"][0]
        actor = actors[name]
        candidate, reference = Path(variant["path"]), Path(entry["source"]["path"])
        require(digest(candidate) == variant["sha256"] and candidate.stat().st_size == variant["bytes"]
                and digest(reference) == entry["source"]["sha256"]
                and reference.stat().st_size == entry["source"]["bytes"], name + ": reviewed inputs changed")
        document = glb_document(candidate)
        require(document["asset"].get("extras", {}).get("rabbitlands_animation_bake_fps") == 30,
                name + ": candidate must retain reviewed 30fps declaration")
        require([a["name"] for a in document["animations"]] == entry["clips"] == actor["clips"],
                name + ": native clip order/inventory differs")
        source = Path(actor["source"])
        require(digest(source) == actor["sha256"], name + ": frozen original source changed")
        source_document = glb_document(source)
        assert_original_nodes(source_document, document)
        structural = counts(document)
        evidence, caveats = checked_evidence(entry, variant)
        relative = actor["runtime_repository_path"]
        require(relative.startswith("godot-client/assets/actors/native/creatures/") and relative.endswith(".glb"), "Unexpected runtime path")
        runtime = target(root, relative)
        before = digest(runtime)
        require(before == entry["active_runtime"]["sha256"] and runtime.stat().st_size == entry["active_runtime"]["bytes"], name + ": active catalog predecessor changed")
        predecessor = None
        for path, registry in ((VISUAL_RECEIPT, visual), (CLOSE_RECEIPT, close)):
            old = registry["actors"].get(name)
            if old and old["runtime_sha256"] == before:
                require(old["source_sha256"] == actor["sha256"], name + ": predecessor source differs")
                predecessor = {"receipt": path, "receipt_sha256": expected[path], "runtime_sha256": before}
                old["superseded_by"] = {"receipt": RECEIPT, "runtime_sha256": variant["sha256"], "reason": "Current exact-version user acceptance of repair"}
                break
        lineage = None
        if predecessor is None:
            if actor["was_installed"]:
                require(before == actor["sha256"], name + ": unknown current runtime predecessor")
            elif before != actor["historical_runtime_sha256"]:
                lineage = old_local_runtime_lineage(root, actor, before)
        require(roster_rows[name]["sha256"] == before and roster_rows[name]["file"] == relative,
                name + ": roster does not bind current runtime")
        config = models["models"][name]
        require(config["scene"] == config["animationLibrary"] == "res://" + relative.removeprefix("godot-client/"),
                name + ": scene/library destination changed")
        old_config = copy.deepcopy(config)
        map_relative = "godot-client/" + config["animationMap"].removeprefix("res://")
        mapping = load(map_relative)
        local_metadata = owner_policy = None
        validate_owner_selection(actor, owner_rows)
        if actor["selected_local_draft"]:
            require(name == "storm_chimera", "Only Storm has an approved owner-qualified upgrade")
            config, mapping, local_metadata, owner_policy = reviewed_owner_upgrade(owner_rows[name], actor, config, mapping, document)
            config["scene"] = config["animationLibrary"] = old_config["scene"]
            config["animationMap"] = f"res://data/animations/visually-approved-repairs-batch02/{name}.json"
            models["models"][name] = config
            map_relative = "godot-client/" + config["animationMap"].removeprefix("res://")
            require(not target(root, map_relative).exists(), "New local map destination already exists")
            expected[map_relative] = None
        require(map_relative != "godot-client/data/animations/creature.json", "Never mutate shared generic animation map")
        names = {n.get("name") for n in document["nodes"]}
        source_names = {n.get("name") for n in source_document["nodes"]}
        # Existing semantic aliases are handled
        # by Actor fallback resolution; retain them verbatim. New owner-qualified
        # Storm aliases are checked as literal nodes by checked_owner above.
        require(all(alias in names or (alias not in source_names and not actor["selected_local_draft"]
                    and config.get("attachments") == old_config.get("attachments"))
                    for alias in config.get("attachments", {}).values()), name + ": attachment alias removed")
        actor_basis = dict(basis, saved_reviewer_approval=approvals[name])
        acceptance = {"receipt": RECEIPT, "actor": name, "appliesToSHA256": variant["sha256"],
                      "scope": "exact_candidate_all_native_clips", "approvalBasis": actor_basis,
                      "previousAuthoringReviewStatus": mapping.get("reviewStatus")}
        mapping["reviewStatus"] = "accepted"
        mapping["runtimeVisualAcceptance"] = acceptance
        mapping["runtimeOptimization"] = {"receipt": RECEIPT, "sourceSHA256": actor["sha256"],
            "previousRuntimeSHA256": before, "runtimeSHA256": variant["sha256"], "method": "visually_accepted_creature_repair",
            "bakeFPS": 30, "previousRuntimeOptimization": mapping.get("runtimeOptimization")}
        require(map_relative not in writes, "Animation map shared by multiple repaired actors")
        writes[map_relative] = json_bytes(mapping)
        policy_path = target(root, relative + ".import")
        if policy_path.exists():
            policy = policy_path.read_bytes()
            expected[relative + ".import"] = hashlib.sha256(policy).hexdigest()
            policy = new_import_policy(owner_policy, relative) if owner_policy is not None else import_policy(policy, 30)
        else:
            require(owner_policy is not None, "Missing import policy without qualified owner")
            expected[relative + ".import"] = None
            policy = new_import_policy(owner_policy, relative)
        writes[relative + ".import"] = policy
        writes[relative], expected[relative] = candidate, before
        roster_rows[name]["sha256"] = variant["sha256"]
        roster_rows[name]["runtimeVisualAcceptance"] = acceptance
        previous_native_sha = update_native_catalog(native, name, relative, document, structural,
                                                      acceptance, entry["display_name"], actor["sha256"])
        deliveries.append({"actor": name, "runtime_path": relative, "source_sha256": actor["sha256"],
            "reviewed_previous_draft_sha256": entry["source"]["sha256"], "previous_runtime_sha256": before,
            "runtime_sha256": variant["sha256"], "previous_runtime_bytes": runtime.stat().st_size,
            "runtime_bytes": variant["bytes"], "variant": variant["id"], "declared_animation_bake_fps": 30,
            "structural_counts": structural, "clips": entry["clips"], "approval_basis": actor_basis,
            "previous_delivery": predecessor, "previous_old_runtime_lineage": lineage,
            "previous_native_catalog_sha256": previous_native_sha, "owner_metadata_evidence": local_metadata,
            "preserved_roster_status": roster_rows[name]["status"], "preview_import_preserved": old_config["import"] == config["import"],
            "metrics": variant["metrics"], "retained_repair_limits": caveats, "evidence": evidence})
    receipt = {"schema_version": 1, "scope": "Four exact batch02 repairs accepted; Mossbound Golem explicitly excluded. Historical proofs remain historical; no fresh numerical equivalence or FPS claim inferred from approval.",
               "input_hashes": input_hashes, "immutable_batch01_receipt_sha256": batch01_sha, "excluded_actors": sorted(EXCLUDED), "approval_counts": {"current_user_repair_instruction": 4},
               "excluded_runtime_held": {"actor": rejected["id"], "runtime_path": rejected_relative, "sha256": rejected_sha},
               "reviewed_generic_map_sha256_preserved": generic_map_sha,
               "actors": {r["actor"]: r for r in deliveries}}
    for relative, data in ((MODELS, models), (ROSTER, roster), (NATIVE, native), (CLOSE_RECEIPT, close),
                           (VISUAL_RECEIPT, visual), (RECEIPT, receipt)):
        writes[relative] = json_bytes(data)
    require(digest(target(root, BATCH01_RECEIPT)) == batch01_sha, "Batch01 receipt changed during qualification")
    require(digest(rejected_runtime) == rejected_sha and models["models"][rejected["id"]] == rejected_model
            and next(a for a in roster["creatures"] if a["id"] == rejected["id"]) == rejected_roster,
            "Rejected Golem model/metadata was modified")
    require(generic_map not in writes and digest(target(root, generic_map)) == generic_map_sha,
            "Shared reviewed animation map must remain unchanged")
    require(not re.search(r"[A-Za-z]:[\\/]", json.dumps(receipt)), "Public receipt contains private filesystem paths")
    require(all(digest(p) == input_hashes[k] for k, p in inputs.items()), "Input changed during qualification")
    require(not any("mossbound_stone_golem.glb" in p for p in writes), "Rejected Golem payload entered transaction")
    return writes, expected, deliveries, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    for name in ("catalog", "authorization", "manifest", "owner-metadata", "journal", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    require(".local" in output.parts and not output.exists(), "Use a new ignored .local output directory")
    if args.install:
        require((root / ".git").is_file() and output.is_relative_to(root / ".local"),
                "Installation/recovery requires a task worktree and its own .local")
    arguments = (root, args.catalog, args.authorization, args.manifest, args.owner_metadata, args.journal)
    writes, expected, rows, receipt = qualify(*arguments)
    output.mkdir(parents=True)
    summary = {"state": "validated_dry_run", "actor_count": 4, "file_count": len(writes),
               "previous_runtime_bytes": sum(r["previous_runtime_bytes"] for r in rows),
               "runtime_bytes": sum(r["runtime_bytes"] for r in rows), "actors": rows,
               "expected_before_hashes": expected, "installer_sha256": digest(__file__),
               "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    save(output / "validated-plan.json", summary)
    save(output / "prospective-public-receipt.json", receipt)
    if args.install:
        with installation_lock(root):
            writes, expected, rows, receipt = qualify(*arguments)
            apply_transaction(root, writes, expected, output,
                              approved_hashes={r["runtime_path"]: r["runtime_sha256"] for r in rows})
        summary.update(state="installed", actors=rows, expected_before_hashes=expected)
        save(output / "validated-plan.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"actors", "expected_before_hashes"}}, indent=2))


if __name__ == "__main__":
    main()

