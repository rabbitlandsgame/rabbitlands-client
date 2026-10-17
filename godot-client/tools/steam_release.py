"""Validate prepared Steam depots and generate SteamPipe VDFs (preview by default).

This command never logs in, uploads, or sets a Steam branch live.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

LAYOUT = {
    "windows": ("app/client-release.json", "app/RabbitLands.exe", "app"),
    "linux": ("app/client-release.json", "app/RabbitLands.x86_64", "app"),
    "macos": ("Rabbit Lands.app/Contents/Resources/client-release.json", "Rabbit Lands.app", ""),
}


def quoted(value):
    text = str(value).replace("\\", "/")
    if any(c in text for c in ('"', '\n', '\r', '\0')):
        raise ValueError("Invalid character in SteamPipe value.")
    return '"' + text + '"'


def positive_id(value):
    text = str(value)
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise ValueError("Steam App and Depot IDs must be assigned positive numeric IDs.")
    return text


def validate(stage: Path, platform: str, expected: str):
    if not re.fullmatch("[0-9a-f]{40}", expected):
        raise ValueError("Select one full Git commit for every platform.")
    stage = stage.resolve(strict=True)
    metadata_path, executable, _ = LAYOUT[platform]
    metadata = json.loads((stage / metadata_path).read_text())
    public_key_path = (stage / metadata_path).parent / "data/update_public.pem"
    if (metadata.get("commit") != expected or metadata.get("platform") != platform
            or metadata.get("distribution") != "steam" or expected not in metadata.get("ancestors", [])):
        raise ValueError("All depots must contain Steam builds of the same selected commit.")
    for path in stage.rglob("*"):
        relative = path.relative_to(stage)
        if any(part.lower() in {".git", ".local", "migration"} for part in relative.parts):
            raise ValueError("Private/build-only directory in Steam depot.")
        if path.is_symlink() and not path.resolve().is_relative_to(stage):
            raise ValueError("Steam depot link escapes its content root.")
        if path == public_key_path and path.is_file():
            public_key = path.read_text(encoding="ascii")
            if ("PRIVATE KEY" in public_key or "PUBLIC KEY" not in public_key
                    or public_key != metadata.get("public_key")):
                raise ValueError("The packaged public key differs from its embedded identity.")
            continue
        if path.is_file() and (path.suffix.lower() in {".pem", ".p12", ".pfx", ".key"}
                or "updater" in path.name.lower() or path.name.lower() == "steam_appid.txt"):
            raise ValueError("Signing material, GitHub updater or development App ID file in Steam depot.")
    if platform != "macos" and not (stage / executable).is_file():
        raise ValueError("Steam executable is missing.")
    if platform == "macos" and not (stage / executable / "Contents/MacOS/RabbitLands").is_file():
        raise ValueError("macOS bundle entry point is missing.")
    if platform == "macos":
        if sys.platform != "darwin":
            raise ValueError("Validate notarized macOS content on a Mac before including it in a Steam upload.")
        app = stage / executable
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        subprocess.run(["xcrun", "stapler", "validate", str(app)], check=True)
        subprocess.run(["spctl", "--assess", "--type", "execute", str(app)], check=True)
    return stage


def prepare(app_id, depots, commit, out: Path, *, upload=False):
    app_id = positive_id(app_id)
    if not depots or not {"windows", "linux"}.issubset(depots):
        raise ValueError("Prepare a complete Windows + Linux app build; macOS is optional until validated.")
    ids, validated = set(), {}
    for platform, (depot_id, stage) in depots.items():
        depot_id = positive_id(depot_id)
        if depot_id in ids:
            raise ValueError("Each platform requires its own depot ID.")
        ids.add(depot_id)
        validated[platform] = (depot_id, validate(stage, platform, commit))
    out = out.resolve()
    if any(out.is_relative_to(stage) for _, stage in validated.values()):
        raise ValueError("SteamPipe scripts/cache must be outside all shipped content roots.")
    out.mkdir(parents=True, exist_ok=False)
    lines = ['"AppBuild"', '{', f'  "AppID" {quoted(app_id)}',
             f'  "Desc" {quoted("Rabbit Lands " + commit)}',
             f'  "BuildOutput" {quoted(out / "cache")}',
             f'  "Preview" "{0 if upload else 1}"', '  "SetLive" ""', '  "Depots"', '  {']
    launch = {}
    for platform, (depot_id, stage) in validated.items():
        name = f"depot-{platform}.vdf"
        (out / name).write_text('\n'.join(['"DepotBuildConfig"', '{', f'  "DepotID" {quoted(depot_id)}',
            f'  "ContentRoot" {quoted(stage)}', '  "FileMapping"', '  {',
            '    "LocalPath" "*"', '    "DepotPath" "."', '    "Recursive" "1"', '  }',
            '  "FileExclusion" ".eloria-package"', '}']) + '\n', encoding="utf-8")
        lines.append(f"    {quoted(depot_id)} {quoted(name)}")
        launch[platform] = {"depot_id": depot_id, "executable": LAYOUT[platform][1],
                            "working_directory": LAYOUT[platform][2], "arguments": ""}
    lines += ['  }', '}']
    (out / "app-build.vdf").write_text('\n'.join(lines) + '\n', encoding="utf-8")
    (out / "steamworks-launch-settings.json").write_text(json.dumps(launch, indent=2) + '\n')
    return out / "app-build.vdf"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--upload-config", action="store_true", help="emit Preview=0; still does not upload or set live")
    for platform in LAYOUT:
        parser.add_argument(f"--{platform}-depot")
        parser.add_argument(f"--{platform}-stage", type=Path)
    options = parser.parse_args()
    depots = {}
    for platform in LAYOUT:
        depot, stage = getattr(options, platform + "_depot"), getattr(options, platform + "_stage")
        if bool(depot) != bool(stage):
            parser.error(f"--{platform}-depot and --{platform}-stage are required together")
        if depot:
            depots[platform] = (depot, stage)
    try:
        print(prepare(options.app_id, depots, options.commit, options.out, upload=options.upload_config))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Steam configuration failed: {error}\n")


if __name__ == "__main__":
    main()
