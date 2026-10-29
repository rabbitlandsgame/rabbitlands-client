"""Deliver five exact, currently user-approved repairs; dry run by default.

No generation, curve rewriting, uploads or implicit approval. --authorization
is a separate current user instruction pinned to --catalog, not a fabricated
reviewer journal event. --install requires a task worktree and keeps staged
copies, original metadata/assets and transaction recovery under its .local.
Historical numeric fixtures and authoring profiles remain untouched.
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

RECEIPT = "docs/qa/creature-storage/accepted-repair-delivery.json"
MODELS = "godot-client/data/actors/models.json"
NATIVE = "godot-client/data/actors/native_asset_catalog.json"
ACTORS = {"skeleton", "tengu", "giant_wasp", "heartwood_treant", "nightweave_spider"}


def approved_entries(catalog, authorization, catalog_sha):
    require(catalog.get("complete") is True, "Repair review processing is incomplete")
    entries = catalog["entries"]
    require(len(entries) == 5 and {e["id"] for e in entries} == ACTORS,
            "Expected exactly the five reviewed repairs; duplicate/substituted actor")
    require(authorization.get("kind") == "current_user_repair_instruction"
            and authorization.get("authorized") is True
            and authorization.get("count") == 5
            and authorization.get("catalog_sha256") == catalog_sha
            and authorization.get("scope") == "exact_candidates_all_native_clips"
            and isinstance(authorization.get("instruction_summary"), str)
            and bool(authorization["instruction_summary"].strip()),
            "A current explicit instruction must pin this exact five-entry catalog")
    require(set(authorization.get("actors", [])) == ACTORS
            and len(authorization["actors"]) == 5, "Approval actor inventory differs")
    for entry in entries:
        require(len(entry["variants"]) == 1, entry["id"] + ": ambiguous approved version")
    return entries


def counts(document):
    vertices = triangles = surfaces = 0
    for node in document["nodes"]:
        if "mesh" not in node:
            continue
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            require(primitive.get("mode", 4) == 4, "Only triangle surfaces are supported")
            require(not primitive.get("targets"), "Reviewed repair unexpectedly has corrective targets")
            n = document["accessors"][primitive["attributes"]["POSITION"]]["count"]
            indices = document["accessors"][primitive["indices"]]["count"] if "indices" in primitive else n
            require(indices % 3 == 0, "Incomplete triangle surface")
            vertices += n
            triangles += indices // 3
            surfaces += 1
    return {"vertices": vertices, "triangles": triangles,
            "joints": len({j for s in document.get("skins", []) for j in s["joints"]}),
            "animations": len(document["animations"]), "surfaceCount": surfaces,
            "correctiveTargets": 0}


def checked_approvals(entries, authorization, events, catalog_sha):
    """Bind real saved approvals separately from the current human instruction."""
    pins = authorization["approval_events"]
    require(set(pins) == ACTORS, "Missing exact reviewer approval pins")
    result = {}
    for entry in entries:
        name, variant = entry["id"], entry["variants"][0]
        matches = [e for e in events if e.get("event_id") == pins[name]["event_id"]]
        require(len(matches) == 1, name + ": saved approval missing/ambiguous")
        event = matches[0]
        require(event_sha(event) == pins[name]["event_sha256"]
                and event.get("type") == "approve" and event.get("test_only") is False
                and event.get("scope") == "creature_candidate_all_clips"
                and event.get("actor") == name and event.get("variant") == variant["id"]
                and event.get("catalog_sha256") == catalog_sha
                and event.get("source_sha256") == entry["source"]["sha256"]
                and event.get("candidate_sha256") == variant["sha256"], name + ": exact approval differs")
        result[name] = {"event_id": event["event_id"], "event_sha256": event_sha(event), "utc": event["utc"]}
    return result


def assert_original_nodes(source, candidate):
    """Retain all pre-existing names/hierarchy/rests, including Skeleton's 19."""
    require(len(candidate["nodes"]) >= len(source["nodes"]), "Original nodes removed")
    for i, original in enumerate(source["nodes"]):
        new = candidate["nodes"][i]
        for key in ("name", "translation", "rotation", "scale", "matrix"):
            require(new.get(key) == original.get(key), "Original node/rest changed: " + str(i))
        require(set(original.get("children", [])) <= set(new.get("children", [])),
                "Original parent/child link removed")


def checked_evidence(entry, variant):
    pins = variant["evidence"]
    require(digest(pins["artifact_index"]) == pins["artifact_index_sha256"]
            and digest(pins["handoff"]) == pins["handoff_sha256"], "Repair evidence changed")
    index = read(pins["artifact_index"])
    rows = [r for r in index["actors"] if r["actor"] == entry["id"]]
    require(len(rows) == 1, "Missing/ambiguous independent artifact-index actor")
    row = rows[0]
    require(row["candidate"]["sha256"] == variant["sha256"]
            and row["candidate"]["bytes"] == variant["bytes"]
            and row["commented_baseline"]["sha256"] == entry["source"]["sha256"],
            "Independent reviewer artifact inventory does not bind displayed versions")
    evidence, clients = [], []
    blender_found = visual_found = False
    supplemental = row["evidence_complete_now"] is not True
    if supplemental:
        # The reviewed catalog deliberately retains the earlier index snapshot
        # and also pins Heartwood's later FINAL handoff, completed after GPU90.
        handoff = read(pins["handoff"])
        require(entry["id"] == "heartwood_treant" and handoff["sha256"] == variant["sha256"]
                and handoff["outside_positions_and_normals_exact"] is True
                and handoff["all_existing_bone_world_matrices_exact"] is True
                and handoff["placement_equal"] is True and handoff["actual_raw_client_states"] >= 380,
                "Incomplete snapshot lacks a pinned final qualification supplement")
        for item in handoff["evidence"]:
            require(digest(item["path"]) == item["sha256"], "Final Heartwood evidence changed")
            evidence.append({"kind": "final_handoff_" + Path(item["path"]).name, "sha256": item["sha256"]})
            visual_found |= Path(item["path"]).name == "preview-smoke.json"
            blender_found |= Path(item["path"]).name == "blender-summary.json"
    for item in row["evidence"]:
        if item["status"] != "exists":
            require(supplemental, "Indexed repair evidence remains incomplete")
            continue
        require(item["status"] == "exists" and digest(item["path"]) == item["sha256"],
                "Indexed evidence bytes changed: " + item["kind"])
        evidence.append({"kind": item["kind"], "sha256": item["sha256"]})
        if item["kind"].startswith("actual_client"):
            report = read(item["path"])
            if not report.get("models") or report["models"][-1]["sha256"] != variant["sha256"]:
                continue  # Older baseline-only control remains indexed, not a new-version proof.
            require(all("GlbSceneCache._build_raw" in m["load_proof"]["actual_loader"]
                        for m in report["models"]), "Expected actual raw-client loader")
            require(all(report["placement"].values())
                    and set(report["native_clips"]) == set(entry["clips"]),
                    "Actual-client placement/native inventory failed")
            capture = Path(item["path"]).parent / "client"
            require(digest(capture / "metadata.json") == report["provenance"]["metadata_sha256"]
                    and digest(capture / "states.f32") == report["provenance"]["states_sha256"],
                    "Actual-client capture payload changed")
            observed = read(capture / "metadata.json")["descriptions"]
            require(observed[0]["clips"] == observed[1]["clips"], "Native duration/loop policy differs")
            clients.append({"report_sha256": item["sha256"], "comparison_sha256": [m["sha256"] for m in report["models"]],
                            "summary": report["summary"], "scope": report["scope"]})
        blender_found |= "blender" in item["kind"] and "unchanged" not in item["kind"]
        visual_found |= "visual" in item["kind"] and item["path"].endswith(".json")
    require(clients and blender_found and visual_found, "Missing actual-client/fresh-Blender/visual proof")
    return {"artifact_index_sha256": pins["artifact_index_sha256"],
            "handoff_sha256": pins["handoff_sha256"], "files": evidence,
            "earlier_incomplete_index_snapshot_retained": supplemental,
            "actual_client_observations": clients}, row.get("caveats", [])


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

    def load(relative):
        p = target(root, relative)
        data = p.read_bytes()
        expected[relative] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    models, roster, native, close, visual = [load(p) for p in (MODELS, ROSTER, NATIVE, CLOSE_RECEIPT, VISUAL_RECEIPT)]
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
        if actor["selected_local_draft"]:
            require(name == "giant_wasp", "Only Wasp is the approved new local selection")
            config, mapping, local_metadata, owner_policy = checked_owner(owner_rows[name], actor, config, document)
            config["scene"] = config["animationLibrary"] = old_config["scene"]
            config["animationMap"] = f"res://data/animations/visually-approved/{name}.json"
            models["models"][name] = config
            map_relative = "godot-client/" + config["animationMap"].removeprefix("res://")
            require(not target(root, map_relative).exists(), "New local map destination already exists")
            expected[map_relative] = None
        require(map_relative != "godot-client/data/animations/creature.json", "Never mutate shared generic animation map")
        names = {n.get("name") for n in document["nodes"]}
        source_names = {n.get("name") for n in source_document["nodes"]}
        # Existing semantic aliases such as Heartwood's body/neck are handled
        # by Actor fallback resolution; retain them verbatim. New owner-qualified
        # Wasp aliases are checked as literal nodes by checked_owner above.
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
            policy = import_policy(policy, 30)
        else:
            require(owner_policy is not None, "Missing import policy without qualified owner")
            expected[relative + ".import"] = None
            policy = new_import_policy(owner_policy, relative)
        writes[relative + ".import"] = policy
        writes[relative], expected[relative] = candidate, before
        roster_rows[name]["sha256"] = variant["sha256"]
        roster_rows[name]["runtimeVisualAcceptance"] = acceptance
        native_matches = [section[name] for section in native.values() if isinstance(section, dict)
                          and isinstance(section.get(name), dict) and "path" in section[name]]
        require(len(native_matches) <= 1, "Ambiguous native asset catalog entry")
        if native_matches:
            native_row = native_matches[0]
        else:
            native_row = {"id": name, "name": entry["display_name"], "path": relative, "sourceSHA256": actor["sha256"]}
            native["creatures"][name] = native_row
        previous_native_sha = native_row.get("sha256")
        native_row.update(structural, sha256=variant["sha256"], path=relative, runtimeVisualAcceptance=acceptance)
        deliveries.append({"actor": name, "runtime_path": relative, "source_sha256": actor["sha256"],
            "reviewed_previous_draft_sha256": entry["source"]["sha256"], "previous_runtime_sha256": before,
            "runtime_sha256": variant["sha256"], "previous_runtime_bytes": runtime.stat().st_size,
            "runtime_bytes": variant["bytes"], "variant": variant["id"], "declared_animation_bake_fps": 30,
            "structural_counts": structural, "clips": entry["clips"], "approval_basis": actor_basis,
            "previous_delivery": predecessor, "previous_old_runtime_lineage": lineage,
            "previous_native_catalog_sha256": previous_native_sha, "owner_metadata_evidence": local_metadata,
            "preserved_roster_status": roster_rows[name]["status"], "preview_import_preserved": old_config["import"] == config["import"],
            "metrics": variant["metrics"], "retained_repair_limits": caveats, "evidence": evidence})
    receipt = {"schema_version": 1, "scope": "Five exact repair versions accepted by current user instruction. Historical proofs remain historical; no fresh numerical equivalence or FPS claim inferred from approval.",
               "input_hashes": input_hashes, "approval_counts": {"current_user_repair_instruction": 5},
               "actors": {r["actor"]: r for r in deliveries}}
    for relative, data in ((MODELS, models), (ROSTER, roster), (NATIVE, native), (CLOSE_RECEIPT, close),
                           (VISUAL_RECEIPT, visual), (RECEIPT, receipt)):
        writes[relative] = json_bytes(data)
    require(not re.search(r"[A-Za-z]:[\\/]", json.dumps(receipt)), "Public receipt contains private filesystem paths")
    require(all(digest(p) == input_hashes[k] for k, p in inputs.items()), "Input changed during qualification")
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
    summary = {"state": "validated_dry_run", "actor_count": 5, "file_count": len(writes),
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
