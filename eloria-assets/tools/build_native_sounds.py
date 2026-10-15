#!/usr/bin/env python3
"""Build licensed audio from source/audio/manifest.json and retained originals.

No network is needed. Requires numpy, scipy and FFmpeg (on PATH, --ffmpeg,
or from the optional imageio_ffmpeg package). Licenses and credits ship with
the output. This replaces the former synthesized placeholder generator.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import wave
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfiltfilt

REPO = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPO / "eloria-assets/source/audio"
DEFAULT_OUTPUT = REPO / "godot-client/assets/audio"
SAMPLE_RATE = 44100

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def find_ffmpeg(explicit: str | None) -> str:
    if explicit:
        return explicit
    if executable := shutil.which("ffmpeg"):
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("Install FFmpeg or provide --ffmpeg.")

def decode(path: Path, executable: str, channels: int) -> np.ndarray:
    result = subprocess.run([executable, "-nostdin", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", str(channels), "-ar", str(SAMPLE_RATE), "-"], check=True, capture_output=True)
    return np.frombuffer(result.stdout, dtype="<f4").reshape(-1, channels).copy()

def process(samples: np.ndarray, settings: dict) -> np.ndarray:
    start = round(float(settings.get("start", 0)) * SAMPLE_RATE)
    stop = start + round(float(settings["duration"]) * SAMPLE_RATE) if "duration" in settings else len(samples)
    samples = samples[start:stop].astype(np.float64)
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError("empty or non-finite source audio")
    samples -= samples.mean(axis=0)
    if settings.get("trim_silence"):
        energy = np.max(np.abs(samples), axis=1)
        audible = np.flatnonzero(energy > energy.max() * 0.008)
        if not len(audible):
            raise ValueError("silent source audio")
        padding = round(0.012 * SAMPLE_RATE)
        samples = samples[max(0, audible[0] - padding):min(len(samples), audible[-1] + padding + 1)]
    if settings.get("lowpass"):
        samples = sosfiltfilt(butter(4, float(settings["lowpass"]), fs=SAMPLE_RATE, output="sos"), samples, axis=0)
    if settings.get("crossfade"):
        count = min(round(float(settings["crossfade"]) * SAMPLE_RATE), len(samples) // 4)
        ramp = np.linspace(0.0, 1.0, count)[:, None]
        seam = samples[-count:] * (1.0 - ramp) + samples[:count] * ramp
        samples = np.concatenate([seam, samples[count:-count]])
    for key, at_start in (("fade_in", True), ("fade_out", False)):
        count = min(round(float(settings.get(key, 0)) * SAMPLE_RATE), len(samples) // 2)
        if count:
            ramp = np.linspace(0.0, 1.0, count)[:, None] ** 2
            if at_start:
                samples[:count] *= ramp
            else:
                samples[-count:] *= ramp[::-1]
    peak = float(np.max(np.abs(samples)))
    if peak < 1e-7:
        raise ValueError("silent processed audio")
    return samples / peak * float(settings["peak"])

def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = np.round(np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(samples.shape[1]); handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE); handle.writeframes(pcm.tobytes())

def describe_changes(asset: dict) -> str:
    s = asset["processing"]
    changes = ["Converted to 44.1 kHz", "stereo Ogg Vorbis" if asset["kind"] == "music" else "mono 16-bit PCM WAV", "level adjusted"]
    if "duration" in s:
        changes.append(f"excerpt from {s.get('start', 0)} to {s.get('start', 0) + s['duration']} seconds")
    if s.get("trim_silence"): changes.append("leading/trailing silence trimmed")
    if s.get("lowpass"): changes.append(f"low-pass filtered at {s['lowpass']} Hz")
    if s.get("crossfade"): changes.append(f"{s['crossfade']}-second overlap crossfade for looping")
    if s.get("fade_in") or s.get("fade_out"): changes.append("short attack/release fades")
    return "; ".join(changes) + "."

def credits_text(manifest: dict) -> str:
    lines = ["ELORIA AUDIO CREDITS", "", "Music and sound effects by the creators listed below.", "The audio retains its individual source licenses; it is not covered by", "Eloria's original-asset license. Credits do not imply creator endorsement.", "", "CC0 1.0 Universal: https://creativecommons.org/publicdomain/zero/1.0/", "CC BY 3.0 Unported: https://creativecommons.org/licenses/by/3.0/", "", "The CC BY recording and its adaptation may be reused under that license.", "Retain attribution, license and source links, and identify further changes.", "Do not impose additional legal restrictions or effective technological", "measures on that recording. Full license texts accompany these credits.", ""]
    for source_id, source in manifest["sources"].items():
        used = [a for a in manifest["assets"] if a["source"] == source_id]
        if not used: continue
        lines += [source["title"], "Creator: " + source["creator"], "Source: " + source["url"], "License: " + source["license"] + " - " + source["license_url"], "Source notice: " + source["attribution_notice"]]
        for a in used: lines += ["  " + a["file"], "    " + describe_changes(a)]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def build(output: Path, executable: str) -> dict:
    manifest = json.loads((SOURCE_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    catalog = {"schema": "eloria.sounds/1", "sampleRate": SAMPLE_RATE, "credits": "CREDITS.txt", "provenance": "provenance.json", "sounds": [], "music": []}
    provenance = {"schema": "eloria.audio-provenance/1", "sources": manifest["sources"], "assets": []}
    if output.resolve() != DEFAULT_OUTPUT.resolve():
        shutil.copytree(DEFAULT_OUTPUT / "licenses", output / "licenses", dirs_exist_ok=True)
    for a in manifest["assets"]:
        original = (SOURCE_DIRECTORY / a["original"]).resolve()
        if not original.is_relative_to(SOURCE_DIRECTORY.resolve()):
            raise ValueError("source path escapes retained audio directory")
        if sha256(original) != a["original_sha256"]:
            raise ValueError("source hash changed: " + a["original"])
        samples = process(decode(original, executable, int(a["processing"].get("channels", 1))), a["processing"])
        target = output / a["file"]
        if a["kind"] == "music":
            subprocess.run([executable, "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ac", "2", "-ar", str(SAMPLE_RATE), "-i", "-", "-c:a", "libvorbis", "-q:a", "5", "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", str(target)], input=samples.astype("<f4").tobytes(), check=True)
        else:
            write_wav(target, samples)
        entry = {"name": a["name"].removeprefix("music_") if a["kind"] == "music" else a["name"], "file": a["file"], "seconds": round(len(samples) / SAMPLE_RATE, 3), "source": a["source"], "sha256": sha256(target)}
        catalog["music" if a["kind"] == "music" else "sounds"].append(entry)
        provenance["assets"].append({**a, "sha256": entry["sha256"], "changes": describe_changes(a)})
        print(f"{target.name}: {entry['seconds']} seconds")
    for filename, content in (("catalog.json", catalog), ("provenance.json", provenance)):
        (output / filename).write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    (output / "CREDITS.txt").write_text(credits_text(manifest), encoding="utf-8")
    return catalog

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ffmpeg", help="FFmpeg executable path")
    args = parser.parse_args()
    catalog = build(args.out, find_ffmpeg(args.ffmpeg))
    print(f"Built {len(catalog['sounds'])} sounds and {len(catalog['music'])} music tracks with credits and licenses.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
