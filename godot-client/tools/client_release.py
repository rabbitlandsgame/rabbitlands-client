"""Package signed client updates for public GitHub Releases.

Payload files are divided into small ZIP entries (bounded extraction memory),
and the resulting ZIP is divided into assets below GitHub's 2 GiB limit.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import BinaryIO
from release_storage import PartWriter

CHUNK_BYTES = 8 * 1024 * 1024
PART_BYTES = 256 * 1024 * 1024
MAX_ANCESTORS = 100000


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def identity(repo: Path, sha: str, platform: str, public_key: Path | None,
             repository: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("client release requires a full Git commit")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("GitHub repository must be OWNER/REPO")
    shallow = subprocess.check_output(["git", "rev-parse", "--is-shallow-repository"], cwd=repo, text=True).strip()
    if shallow != "false":
        raise ValueError("fetch the full client history before packaging ancestry checks")
    ancestors = subprocess.check_output(["git", "rev-list", sha], cwd=repo, text=True).splitlines()
    if len(ancestors) > MAX_ANCESTORS:
        raise ValueError("client history exceeds the update handshake limit")
    pem = public_key.read_text(encoding="ascii") if public_key else ""
    if public_key and ("PRIVATE KEY" in pem or "PUBLIC KEY" not in pem):
        raise ValueError("update-public-key must contain a public RSA key only")
    return {"schema": 1, "commit": sha, "platform": platform,
            "ancestors": ancestors, "public_key": pem, "repository": repository}


def build_payload(stage: Path, output: Path | BinaryIO) -> tuple[int, int]:
    inventory = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        paths = sorted(path for root in ("app", "eloria-assets")
                       for path in (stage / root).rglob("*") if path.is_file())
        for index, path in enumerate(paths):
            if path.is_symlink():
                raise ValueError("release payloads cannot include symlinks")
            relative = path.relative_to(stage).as_posix()
            entry = {"path": relative, "size": path.stat().st_size, "sha256": digest(path)}
            inventory.append(entry)
            with path.open("rb") as handle:
                chunk = 0
                while data := handle.read(CHUNK_BYTES):
                    archive.writestr(f"files/{index:06d}/{chunk:06d}", data)
                    chunk += 1
        archive.writestr("inventory.json", json.dumps(inventory, separators=(",", ":")))
    return len(inventory), sum(item["size"] for item in inventory)


def split_payload(archive: Path, base_url: str, part_bytes: int = PART_BYTES) -> list[dict]:
    parts = []
    with archive.open("rb") as source:
        index = 1
        while True:
            first = source.read(min(CHUNK_BYTES, part_bytes))
            if not first:
                break
            path = archive.with_name(f"{archive.name}.{index:03d}")
            remaining = part_bytes
            sha = hashlib.sha256()
            with path.open("wb") as target:
                data = first
                while data:
                    target.write(data)
                    sha.update(data)
                    remaining -= len(data)
                    if not remaining:
                        break
                    data = source.read(min(CHUNK_BYTES, remaining))
            parts.append({"url": f"{base_url}/{path.name}", "size": path.stat().st_size,
                          "sha256": sha.hexdigest()})
            index += 1
    return parts


def export_launcher(stage: Path, metadata: dict, godot: Path, source: Path,
                    preset_text: str, preset_name: str, run_godot, logs: Path) -> None:
    project = logs / "updater-project"
    scripts = project / "src" / "updates"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("release.gd", "launcher.gd", "launch_options.gd"):
        (scripts / name).write_bytes((source / "src" / "updates" / name).read_bytes())
    (project / "data").mkdir(exist_ok=True)
    (project / "data" / "client_release.json").write_text(json.dumps(metadata), encoding="utf-8")
    branding = project / "assets" / "branding"
    branding.mkdir(parents=True, exist_ok=True)
    for name in ("rabbitlands-icon.png", "rabbitlands-icon.ico", "rabbitlands-mark-64.png"):
        shutil.copyfile(source / "assets" / "branding" / name, branding / name)
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Rabbit Lands"\nconfig/icon="res://assets/branding/rabbitlands-icon.png"\nboot_splash/image="res://assets/branding/rabbitlands-mark-64.png"\nboot_splash/bg_color=Color(0.035, 0.043, 0.055, 1)\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="Godot/app_userdata/Eloria"\nconfig/custom_user_dir_name.linuxbsd="godot/app_userdata/Eloria"\nrun/main_scene="res://main.tscn"\n'
        '[display]\nwindow/size/viewport_width=440\nwindow/size/viewport_height=100\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
    (project / "main.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://src/updates/launcher.gd" id="1"]\n'
        '[node name="Launcher" type="Node"]\nscript=ExtResource("1")\n'
        '[node name="Status" type="Label" parent="."]\ntext="Preparing game updates…"\n', encoding="utf-8")
    # The installed templates disable command-line path overrides. Embedding
    # the bootstrap's own pack prevents it loading app/RabbitLands.pck when its
    # working directory is app/, where the child game's loose assets live.
    preset_text = preset_text.replace('binary_format/embed_pck=false', 'binary_format/embed_pck=true')
    preset_text = preset_text.replace('[preset.1.options]', '[preset.1.options]\n\nbinary_format/embed_pck=true')
    (project / "export_presets.cfg").write_text(preset_text, encoding="utf-8")
    run_godot(godot, ["--headless", "--path", str(project), "--import"], logs / "updater-import.log", timeout=120)
    binary = "RabbitLands-updater.exe" if metadata["platform"] == "windows" else "RabbitLands-updater.x86_64"
    (stage / "RabbitLands-updater.pck").unlink(missing_ok=True)
    run_godot(godot, ["--headless", "--path", str(project), "--export-release", preset_name, str(stage / binary)],
              logs / "updater-export.log", timeout=120)
    if not (stage / binary).is_file():
        raise ValueError("updater export is incomplete")


def publish_artifacts(stage: Path, metadata: dict, private_key: Path,
                      godot: Path, source: Path, run_godot, logs: Path,
                      *, accept_part=None, budget=None) -> list[Path]:
    commit = metadata["commit"]
    platform = metadata["platform"]
    tag = f"client-{commit}"
    base = f'https://github.com/{metadata["repository"]}/releases/download/{tag}'
    archive = stage.parent / f"{stage.name}.update.zip"
    if accept_part is None:
        count, unpacked = build_payload(stage, archive)
        parts = split_payload(archive, base)
        size, checksum = archive.stat().st_size, digest(archive)
    else:
        with PartWriter(archive, base, PART_BYTES, accept_part, budget) as writer:
            count, unpacked = build_payload(stage, writer)
        parts, size, checksum = writer.parts, writer.size, writer.sha256
    release = {"schema": 1, "commit": commit, "platform": platform,
               "version": stage.name, "size": size,
               "unpacked_size": unpacked, "file_count": count,
               "sha256": checksum, "parts": parts}
    payload = logs / "release-payload.json"
    payload.write_text(json.dumps(release, separators=(",", ":")), encoding="utf-8")
    manifest = stage.parent / f"{stage.name}-{platform}.json"
    run_godot(godot, ["--headless", "--path", str(logs / "updater-project"), "--script",
                     str(source / "tools" / "sign_client_release.gd"), "--", "sign",
                     str(private_key.resolve()), str(payload), str(manifest)], logs / "release-sign.log", timeout=120)
    # Verify that the configured public key actually matches the signing key.
    request = logs / "verify-release.json"
    request.write_text(json.dumps({"manifest": str(manifest), "identity": metadata}), encoding="utf-8")
    run_godot(godot, ["--headless", "--path", str(logs / "updater-project"), "--script",
                     str(source / "tools" / "verify_client_release.gd"), "--", str(request)],
              logs / "release-verify.log", timeout=120)
    policy = stage.parent / f"{stage.name}-server-policy.json"
    policy.write_text(json.dumps({"schema": 1, "required_commit": commit, "enforce": True,
                                 "manifests": {platform: f"{base}/{manifest.name}"}}, indent=2), encoding="utf-8")
    instructions = stage.parent / f"{stage.name}-github-release.txt"
    assets = [manifest] + [stage.parent / part["url"].rsplit("/", 1)[1] for part in parts]
    instructions.write_text(
        f'Create public GitHub Release {tag} in {metadata["repository"]}, targeting client commit {commit}.\n'
        'Upload these assets (all download parts are under 2 GiB):\n'
        + "\n".join(str(path) for path in assets)
        + f'\n\nAfter uploads complete, copy {policy.name} to the server profile as client_updates.json.\n'
        'Merge windows/linux manifest rows if publishing both platforms. Connected players are notified within 30 seconds.\n',
        encoding="utf-8")
    if accept_part is None:
        archive.unlink()  # Players download the pieces; the unsplit archive is redundant.
    return assets + [policy, instructions]


def export_installer_helper(stage: Path, godot: Path, tools_source: Path,
                            preset_text: str, run_godot, logs: Path) -> Path:
    """Build the small setup helper; the selected game's bytes stay untouched."""
    project = logs / "installer-project"
    scripts = project / "src/updates"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tools_source / "src/updates/release.gd", scripts / "release.gd")
    shutil.copyfile(tools_source / "tools/install_client_payload.gd", project / "install.gd")
    data = project / "data"
    data.mkdir(exist_ok=True)
    shutil.copyfile(stage / "app/client-release.json", data / "client_release.json")
    shutil.copyfile(stage.parent / f"{stage.name}-windows.json", data / "install_manifest.json")
    branding = project / "assets/branding"
    branding.mkdir(parents=True, exist_ok=True)
    for name in ("rabbitlands-icon.ico", "rabbitlands-mark-64.png"):
        shutil.copyfile(stage / "app/assets/branding" / name, branding / name)
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Rabbit Lands Setup"\n'
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="Godot/app_userdata/Eloria"\n'
        'run/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
    (project / "main.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://install.gd" id="1"]\n'
        '[node name="Installer" type="Node"]\nscript=ExtResource("1")\n', encoding="utf-8")
    preset_text = preset_text.replace('binary_format/embed_pck=false', 'binary_format/embed_pck=true')
    (project / "export_presets.cfg").write_text(preset_text, encoding="utf-8")
    run_godot(godot, ["--headless", "--path", str(project), "--import"], logs / "installer-import.log", timeout=120)
    helper_hash = hashlib.sha256((project / "install.gd").read_bytes()
        + (scripts / "release.gd").read_bytes() + (data / "install_manifest.json").read_bytes()).hexdigest()[:12]
    binary = logs / f"RabbitLands-install-{helper_hash}.exe"
    run_godot(godot, ["--headless", "--path", str(project), "--export-release", "Windows Desktop", str(binary)],
              logs / "installer-export.log", timeout=120)
    if not binary.is_file():
        raise ValueError("The online installer helper export is incomplete.")
    return binary
