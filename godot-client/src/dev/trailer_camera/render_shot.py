"""Render a trailer shot with Godot Movie Maker at a chosen resolution.

Godot 4.7's Movie Maker records at the project's base viewport size
(display/window/size/viewport_width and _height, 1280x720 in project.godot),
not at the window size, and scales every frame down to it. This writes a
temporary godot-client/override.cfg with the wanted size, runs the trailer
camera scene under Movie Maker, and removes the override again. It refuses to run when an override.cfg is already there,
because other tooling uses that file.

    python godot-client/src/dev/trailer_camera/render_shot.py \
        godot-client/src/dev/trailer_camera/shots/landfall_north_gate.json \
        .local/video-generation/trailer-camera/renders/landfall_north_gate.avi

The output's extension picks Movie Maker's writer: .avi (MJPEG at Godot's
default quality, 0.75; the writer does not read a quality from override.cfg)
or .png (a numbered lossless PNG sequence plus a .wav). Afterwards <out>.trailer.json says how
many leading frames are setup and preroll to trim (framesDrawnBeforeShot);
--trim deletes those frames and the trailing ones from a PNG sequence.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

CLIENT = pathlib.Path(__file__).resolve().parents[3]
SCENE = "res://src/dev/trailer_camera/trailer_camera.tscn"
OVERRIDE = CLIENT / "override.cfg"


def godot_executable(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("GODOT"),
                      str(CLIENT / "Godot_v4.7.2-stable_win64.exe")):
        if candidate and pathlib.Path(candidate).exists():
            return candidate
    sys.exit("No Godot 4.7.2 executable: pass --godot or set GODOT.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("shot", help="shot file (res:// or a path)")
    parser.add_argument("out", help="movie file: .avi or .png")
    parser.add_argument("--size", default="2560x1440", help="WIDTHxHEIGHT (default 2560x1440)")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--godot", help="Godot 4.7.2 executable (default: $GODOT, then the one beside project.godot)")
    parser.add_argument("--trim", action="store_true", help="delete head and tail frames of a PNG sequence")
    arguments = parser.parse_args()

    width, height = (int(value) for value in arguments.size.lower().split("x"))
    out = pathlib.Path(arguments.out).resolve()
    if out.suffix.lower() not in (".avi", ".png"):
        sys.exit("The output must end in .avi or .png.")
    out.parent.mkdir(parents=True, exist_ok=True)
    shot = arguments.shot
    if not shot.startswith("res://"):
        shot = str(pathlib.Path(shot).resolve())
    if OVERRIDE.exists():
        sys.exit(f"{OVERRIDE} already exists (other tooling writes it); move it aside first.")

    OVERRIDE.write_text(
        "; Written by src/dev/trailer_camera/render_shot.py for one render; it removes it again.\n"
        "[display]\n\n"
        f"window/size/viewport_width={width}\n"
        f"window/size/viewport_height={height}\n",
        encoding="utf-8")
    log = out.with_name(out.name + ".log")
    command = [godot_executable(arguments.godot), "--path", str(CLIENT),
               "--resolution", f"{width}x{height}", "--write-movie", str(out),
               "--fixed-fps", str(arguments.fps), "--log-file", str(log), SCENE,
               "--", f"--shot={shot}"]
    print(" ".join(command), flush=True)
    try:
        code = subprocess.call(command)
    finally:
        OVERRIDE.unlink(missing_ok=True)
    sidecar = out.with_name(out.name + ".trailer.json")
    if code != 0 or not sidecar.exists():
        print(f"Godot exited {code}; see {log}", file=sys.stderr)
        return code or 1
    summary = json.loads(sidecar.read_text(encoding="utf-8"))
    head = int(summary["framesDrawnBeforeShot"])
    frames = int(summary["shotFrames"])
    print(f"shot frames {head}..{head + frames - 1} of the movie ({frames} frames at {summary['fps']:.0f} fps); "
          f"trim the first {head}.")
    if arguments.trim and out.suffix.lower() == ".png":
        sequence = sorted(out.parent.glob(out.stem + "[0-9]*.png"))
        for index, frame in enumerate(sequence):
            if index < head or index >= head + frames:
                frame.unlink()
        print(f"kept {frames} PNG frames; the .wav still starts at the head")
    elif out.suffix.lower() == ".avi":
        # Every MJPEG frame is a key frame, so a stream copy cuts exactly.
        start = head / float(summary["fps"])
        print(f'trim: ffmpeg -ss {start:.6f} -i "{out}" -frames:v {frames} -an -c copy '
              f'"{out.with_stem(out.stem + "_shot")}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
