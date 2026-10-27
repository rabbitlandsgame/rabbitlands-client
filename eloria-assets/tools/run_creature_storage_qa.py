"""Run reusable candidate qualification phases without installing any asset.

Job JSON: actor, source, candidate, preparation (packer's JSON report), output,
witness (immutable original or new source-only observations), config (original
models.json entry), actor_fixtures and native_fixtures (baseline/candidate paths
with original actor basename). imported_fixtures uses two freshly imported
res:// paths inside the caller's isolated project, with original import policy.

Run source/physical and independent Blender first; import the isolated project,
then native/imported playback. `fit` records actual Actor engine states at every
render frame and evaluates all vertices in NumPy. Run `render` only while owning
the team's GPU lease, followed by `compare`. Keep jobs, originals and outputs in
ignored storage. The script never installs a candidate or grants artistic review.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent


def child(arguments, folder, environment, timeout):
    folder.mkdir(parents=True, exist_ok=True)
    stdout, stderr = folder / "stdout.log", folder / "stderr.log"
    with stdout.open("w", encoding="utf-8") as out, stderr.open(
        "w", encoding="utf-8"
    ) as err:
        completed = subprocess.run(
            arguments,
            env=environment,
            stdout=out,
            stderr=err,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    errors = stderr.read_text(encoding="utf-8", errors="replace")
    output = stdout.read_text(encoding="utf-8", errors="replace")
    if (
        completed.returncode
        or "SCRIPT ERROR:" in errors
        or "ERROR:" in errors
        or "Traceback" in errors
    ):
        raise RuntimeError(
            f"Qualification process failed ({completed.returncode}); inspect {stdout} and {stderr}\n{errors[-2000:]}\n{output[-1000:]}"
        )
    print(output[-2000:], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument(
        "--phase",
        required=True,
        choices=(
            "source",
            "physical",
            "blender",
            "native",
            "imported",
            "fit",
            "analyze-native",
            "analyze-imported",
            "render",
            "compare",
        ),
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Prepared ignored Godot QA project with current src/data dependencies and class cache",
    )
    parser.add_argument("--godot", type=Path)
    parser.add_argument("--blender", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    job_path = args.job.resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    output = Path(job["output"])
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="2", OMP_NUM_THREADS="2")
    if os.name == "nt":
        for variable, name in (("APPDATA", "roaming"), ("LOCALAPPDATA", "local")):
            profile = output / "qa-profile" / name
            profile.mkdir(parents=True, exist_ok=True)
            environment[variable] = str(profile)
    if args.phase in ("source", "physical"):
        child(
            [
                sys.executable,
                str(TOOLS / "qualify_creature_storage.py"),
                "--job",
                str(job_path),
                "--phase",
                args.phase,
            ],
            output / (args.phase + "-process"),
            environment,
            args.timeout,
        )
    elif args.phase == "blender":
        if args.blender is None:
            parser.error("--blender is required")
        child(
            [
                str(args.blender),
                "--background",
                "--factory-startup",
                "--threads",
                "2",
                "--python",
                str(TOOLS / "check_creature_storage_blender.py"),
                "--",
                str(job_path),
            ],
            output / "blender-process",
            environment,
            args.timeout,
        )
    elif args.phase.startswith("analyze-"):
        mode = args.phase.removeprefix("analyze-")
        child(
            [
                sys.executable,
                str(TOOLS / "analyze_creature_storage_runtime.py"),
                "--job",
                str(job_path),
                "--mode",
                mode,
            ],
            output / (args.phase + "-process"),
            environment,
            args.timeout,
        )
        report = json.loads(
            (output / (mode + "-validation.json")).read_text(encoding="utf-8")
        )
        if (
            report["maximum_position_error"] > 1e-5
            or report["maximum_normal_angle_degrees"] > 0.01
        ):
            raise RuntimeError(
                "Engine source/candidate differences exceed sub-float interpolation bounds; inspect the numeric report"
            )
    elif args.phase == "compare":
        child(
            [
                sys.executable,
                str(TOOLS / "compare_creature_storage_render.py"),
                "--job",
                str(job_path),
            ],
            output / "compare-process",
            environment,
            args.timeout,
        )
        report = json.loads(
            (output / "actual-render/pixel-comparison.json").read_text(encoding="utf-8")
        )
        if not report["framing_passed"]:
            raise RuntimeError(
                "A comparison frame clips the source; recompute full-pose fit and rerender"
            )
        if (
            report["maximum_pixels_above_two_levels"] > 32
            or report["maximum_different_pixels"] > 256
            or report["maximum_mean_channel_error"] > 0.01
        ):
            raise RuntimeError(
                "Pixel differences exceed the small interpolation-edge allowance; inspect full-resolution captures before proceeding"
            )
    else:
        if args.godot is None or args.project is None:
            parser.error("--godot and --project are required")
        project = args.project.resolve()
        if ".local" not in project.parts:
            parser.error("Godot QA must use an isolated ignored .local project")
        rendering = args.phase == "render"
        script = (
            "render_creature_storage.gd" if rendering else "dump_creature_storage.gd"
        )
        command = [str(args.godot), "--path", str(project)]
        command += (
            [
                "--rendering-method",
                "forward_plus",
                "--position",
                "-10000,-10000",
                "--resolution",
                "64x64",
            ]
            if rendering
            else ["--headless"]
        )
        command += [
            "--script",
            str(ROOT / "godot-client/tests" / script),
            "--",
            str(job_path),
        ]
        if not rendering:
            command.append(args.phase)
        child(command, output / (args.phase + "-process"), environment, args.timeout)
        if args.phase == "fit":
            child(
                [
                    sys.executable,
                    str(TOOLS / "analyze_creature_storage_runtime.py"),
                    "--job",
                    str(job_path),
                    "--mode",
                    "fit",
                ],
                output / "fit-analysis-process",
                environment,
                args.timeout,
            )
    print("CREATURE_STORAGE_QA_PASS", job["actor"], args.phase)


if __name__ == "__main__":
    main()
