"""Aggregate existing validation evidence after final guarded promotion."""

import json
from audit import WORKTREE, HERE, digest, g


def run():
    base = WORKTREE / "tpose-body-build"
    catalog = json.loads(
        (WORKTREE / "godot-client/data/actors/native_asset_catalog.json").read_text()
    )
    library = (
        WORKTREE
        / "godot-client/assets/actors/native/shared/Universal_Animation_Library.glb"
    )
    result = {
        "scope": "16 own-source race bodies and five shared animation clips; isolated worktree delivery",
        "library_sha256": digest(library),
        "animation_clips_changed": [
            "Idle_Subtle",
            "Walk",
            "Jog",
            "Run_Female",
            "Fighting_Idle",
        ],
        "animation_clips_preserved": 157,
        "checks": {
            "body_asset_tests": "15 passed",
            "godot_animation_looping": "passed",
            "engine_import_exit_code": 0,
            "engine_captures": "All 16 bodies, appearance, fitted hair and native gear; pilot cycles and installed-resource checks",
        },
        "limitations": [
            "Existing armor sleeve envelopes remain displaced; body/socket validation does not certify equipment art fit.",
            "Equipment tests: three failures also occur with original shipped bodies; an older boot additionally lies 13 mm below the new grounded body in the static authoring check. Equipment refit remains necessary.",
            "Ssarathi male has approximately 30-31 mm p99 upper-leg edge extension in Jog and Run_Female. Rendered cycles were inspected without an open tear.",
            "Ssarathi tails follow pelvis with a 12-hop feather and have no independent tail animation.",
            "Generic hair/headwear/armor can intersect retained horns, crystals or mushrooms; small source collar texture boundaries remain visible.",
            "Godot editor import reports existing equipment image MIME and sandbox cache warnings; no GDScript parse errors were found.",
        ],
        "bodies": [],
    }
    for slug, entry in catalog["races"].items():
        path = WORKTREE / entry["path"]
        promotion = json.loads((base / f"reports/{slug}_promotion.json").read_text())
        validation = json.loads((base / f"reports/{slug}_validation.json").read_text())
        surfaces = json.loads((base / f"out/{slug}.surfaces.json").read_text())
        sha = digest(path)
        assert promotion["written"] and not promotion["errors"], slug
        assert (
            sha
            == promotion["model_sha256"]
            == validation["sha256"]
            == surfaces["output_sha256"]
            == entry["sha256"]
        ), slug
        assert (
            validation["library_sha256"] == result["library_sha256"]
            and not validation["errors"]
        ), slug
        assert {r["clip"] for r in validation["replay"]} == set(
            result["animation_clips_changed"]
        ), slug
        result["bodies"].append(
            {
                "slug": slug,
                "path": entry["path"],
                "sha256": sha,
                "source": entry["source"],
                "source_sha256": entry["sourceSHA256"],
                "joints": entry["joints"],
                "triangles": entry["triangles"],
                "surfaces": entry["surfaces"],
                "omissions": surfaces["omitted"],
                "rest_max_matrix_error": validation["rest_max_matrix_error"],
                "inverse_bind_max_error": validation["inverse_bind_max_error"],
                "warnings": validation["warnings"],
                "clips": [
                    {
                        "name": c["clip"],
                        "frames": c["frames"],
                        "p99_edge_extension_mm": c["edge_gain_m_percentiles"][2] * 1000,
                        "max_edge_extension_mm": c["worst"]["gain_m"] * 1000,
                        "min_vertex_y_m": c["minimum_vertex_y_m"],
                        "loop_max_delta_m": c["loop_max_vertex_delta_m"],
                    }
                    for c in validation["replay"]
                ],
            }
        )
    (HERE / "validation_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Verified promoted body/library/report hashes:", len(result["bodies"]))


if __name__ == "__main__":
    run()
