"""Render independent candidate actors in actual Godot instances."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, subprocess, json
from audit import WORKTREE, HERE

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*")
    p.add_argument("--prefix", default="finalbatch")
    a = p.parse_args()
    roster = json.loads(
        (WORKTREE / "godot-client/data/actors/native_asset_catalog.json").read_text()
    )["races"]

    def capture(slug):
        base = WORKTREE / "tpose-body-build"
        for name, clip, angle, hair, tints, head, gear in [
            ("walk", "Walk", "gameplay", "no", "no", "0", "no"),
            ("appearance", "Idle_Subtle", "front", "no", "yes", "3", "no"),
            ("hair", "Idle_Subtle", "side", "yes", "no", "0", "no"),
            ("gear", "Walk", "gameplay", "yes", "no", "0", "yes"),
        ]:
            out = base / f"preview/{a.prefix}_{slug}_{name}.png"
            cmd = [
                "godot",
                "--path",
                str(WORKTREE / "godot-client"),
                "--script",
                "res://tests/tpose_body_preview.gd",
                "--log-file",
                str(out.with_suffix(".engine.log")),
                "--",
                "--slug",
                slug,
                "--model",
                str(base / f"out/{slug}.glb"),
                "--library",
                str(base / "out/Universal_Animation_Library.glb"),
                "--hair-fit",
                str(base / f"out/{slug}.hair-fit.json"),
                "--out",
                str(out),
                "--clip",
                clip,
                "--angle",
                angle,
                "--hair",
                hair,
                "--tints",
                tints,
                "--head",
                head,
                "--gear",
                gear,
            ]
            result = subprocess.run(
                cmd,
                cwd=WORKTREE,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out.with_suffix(".log").write_text(result.stdout + result.stderr)
            if result.returncode or not out.with_suffix(".png.json").exists():
                raise RuntimeError(slug + " render failed: " + result.stderr[-500:])
        return slug

    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed(
            [
                pool.submit(capture, s)
                for s in roster
                if (not a.only or s in a.only) and s != "luminous_female"
            ]
        ):
            print("CAPTURED", future.result(), flush=True)
