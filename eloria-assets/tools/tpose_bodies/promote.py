"""Promotion with the existing gate unchanged, plus Rest_Pose/appearance evidence.

The current gate lives in generate_models/meshy_to_client/promote.py, not in
rigged_races/promote.py. Extract its pure checks verbatim rather than modifying
the unversioned pipeline or hard-coding an obsolete copy of its contract.
"""

from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from audit import ROOT, WORKTREE, g, digest
from verify import verify


def legacy_check(candidate, target):
    path = ROOT / "generate_models/meshy_to_client/promote.py"
    tree = ast.parse(path.read_text())
    required = {"HEAD_TOLERANCE", "SOCKETS", "REGIONS", "rig_of", "check"}
    kept = []
    for n in tree.body:
        if (
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name in required
        ):
            kept.append(n)
        elif isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in required for t in n.targets
        ):
            kept.append(n)
    ns = {"np": np, "Path": Path, "glbkit": g}
    exec(compile(ast.Module(body=kept, type_ignores=[]), str(path), "exec"), ns)
    old = ns["rig_of"](target)
    new = ns["rig_of"](candidate)
    return {
        "gate": str(path),
        "gate_sha256": digest(path),
        "old": old,
        "new": new,
        "errors": ns["check"](new, old),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--review", type=Path, required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--canonical-rest-migration",
        action="store_true",
        help="Explicitly replace the old per-body Head-height contract with exact shared Rest_Pose and engine socket evidence",
    )
    a = ap.parse_args()
    target = WORKTREE / "godot-client/assets/actors/native/races" / (a.slug + ".glb")
    if not WORKTREE.name.startswith("wt-") or not (WORKTREE / ".git").is_file():
        raise ValueError("Promotion requires an isolated worktree")
    before = digest(target)
    mh = digest(a.model)
    r = legacy_check(a.model, target)
    r["model_sha256"] = mh
    r["target_before_sha256"] = before
    r["legacy_errors"] = list(r["errors"])
    result = verify(a.model, a.library, target, ("Walk", "Run_Female"))
    r["validation"] = result
    r["errors"] += result["errors"]
    review = json.loads(a.review.read_text())
    r["review"] = review
    if review.get("model_sha256") != mh or not review.get("accepted"):
        r["errors"].append("Visual review missing/stale")
    if review.get("library_sha256") != digest(a.library):
        r["errors"].append("Reviewed library missing/stale")
    engine = []
    if not review.get("captures"):
        r["errors"].append("No engine captures")
    for capture in review.get("captures", []):
        if digest(Path(capture["path"])) != capture["sha256"]:
            r["errors"].append("Capture changed after review")
        evidence = json.loads(Path(capture["path"] + ".json").read_text())
        engine.append(evidence)
        if evidence.get("model_sha256") != mh or evidence.get(
            "library_sha256"
        ) != digest(a.library):
            r["errors"].append("Engine capture uses a different model/library")
        if evidence.get("bones") != 77:
            r["errors"].append("Engine skeleton differs from canonical contract")
    if a.canonical_rest_migration:
        # Keep the original gate result verbatim. Only its explicitly identified
        # height rule is superseded: old body heights cannot all equal Rest_Pose.
        # No missing joint, weight, hierarchy or deformation error is waived.
        config = json.loads(
            (WORKTREE / "godot-client/data/actors/models.json").read_text()
        )["models"][a.slug]
        fit = json.loads(a.model.with_suffix(".hair-fit.json").read_text())
        equipment = json.loads(
            (WORKTREE / "godot-client/data/actors/equipment.json").read_text()
        )
        expected = r["new"]["head_y"] / float(equipment["canonicalHeadRestY"])
        if config.get("hairFit") != fit:
            r["errors"].append(
                "Canonical migration requires installed hairFit metadata"
            )
        if not any(
            any(h["name"].startswith("AppearanceHair_") for h in e["hair_attachments"])
            and all(
                np.allclose(
                    e.get("hair_fit", {}).get(k, [0, 0, 0]),
                    fit[k],
                    rtol=1e-6,
                    atol=1e-7,
                )
                for k in ("scale", "offset")
            )
            for e in engine
        ):
            r["errors"].append("Canonical migration requires fitted hair capture")
        if not any(
            e["equipment"].get("native", 0) >= 4
            and e["equipment"].get("fallback", 1) == 0
            for e in engine
        ):
            r["errors"].append(
                "Canonical migration requires actual native socket/skinned equipment capture"
            )
        if any(abs(e["rig_fit_scale"] - expected) > 1e-5 for e in engine):
            r["errors"].append("Engine rig_fit_scale does not match canonical Head")
        r["errors"] = [e for e in r["errors"] if not e.startswith("Head rest Y ")]
        r["canonical_rest_migration"] = {
            "reason": "User requires exact shared Rest_Pose, replacing incompatible per-body rest heights",
            "old_head_y": r["old"]["head_y"],
            "new_head_y": r["new"]["head_y"],
            "engine_rig_fit_scale": expected,
            "legacy_height_errors": [
                e for e in r["legacy_errors"] if e.startswith("Head rest Y ")
            ],
        }
    # The original strict rig report is still run as a separate implementation.
    rig_json = a.model.with_suffix(".rig-report.json")
    strict_reference = target
    if a.canonical_rest_migration:
        # Iterating a migration must not turn an intermediate body's omitted
        # weights into the definition of an unused canonical bone. The original
        # shipped snapshot remains the weight contract; current names/order and
        # the live library Rest_Pose are independently checked above.
        strict_reference = WORKTREE / "tpose-body-build/in" / (a.slug + ".glb")
        manifest = json.loads(
            (WORKTREE / "tpose-body-build/reports/inputs.json").read_text()
        )
        record = next(
            v
            for v in manifest.values()
            if Path(v["snapshot"]).resolve() == strict_reference.resolve()
        )
        if digest(strict_reference) != record["sha256"]:
            raise RuntimeError("Original shipped weight reference changed")
    r["strict_reference"] = str(strict_reference)
    r["strict_reference_sha256"] = digest(strict_reference)
    cmd = [
        sys.executable,
        str(ROOT / "rigged_races/tools/rig_report.py"),
        str(a.model),
        "--reference",
        str(strict_reference),
        "--strict",
        "--mitts",
        "--json",
        str(rig_json),
    ]
    check = subprocess.run(cmd, capture_output=True, text=True)
    r["rig_report_stdout"] = check.stdout
    r["rig_report_stderr"] = check.stderr
    if check.returncode:
        r["errors"].append("rig_report.py --strict failed")
    required = {
        "body",
        "eyes",
        "eyebrows",
        "scalp",
        "wardrobe_shirt",
        "wardrobe_pants",
        "wardrobe_boots",
        "wardrobe_head_band",
        "wardrobe_head_cap",
    }
    if a.slug in ("mycelari_female", "mycelari_male"):
        required.remove("eyebrows")  # User approved source bare brows.
    d, _ = g.read(a.model)
    present = {n.get("name") for n in d["nodes"] if "mesh" in n}
    if required - present:
        r["errors"].append("Missing surfaces " + str(sorted(required - present)))
    sr = json.loads(a.model.with_suffix(".surfaces.json").read_text())
    if not sr.get("geometry_preserved") or sr.get("output_sha256") != mh:
        r["errors"].append("Geometry-preservation evidence missing/stale")
    r["written"] = False
    if not r["errors"] and a.write:
        if digest(target) != before or digest(a.model) != mh:
            raise RuntimeError("Concurrent asset edit; nothing overwritten")
        shutil.copyfile(a.model, target)
        if digest(target) != mh:
            raise RuntimeError("Promoted asset hash mismatch")
        r["written"] = True
        r["target"] = str(target)
    dest = WORKTREE / "tpose-body-build/reports" / (a.slug + "_promotion.json")
    dest.write_text(json.dumps(r, indent=2) + "\n")
    print(
        json.dumps(
            {
                "slug": a.slug,
                "errors": r["errors"],
                "written": r["written"],
                "report": str(dest),
            },
            indent=2,
        )
    )
    raise SystemExit(bool(r["errors"]))


if __name__ == "__main__":
    main()
