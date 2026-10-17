"""Install verified release tools into one fresh, disposable hosted-runner folder."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

GODOT_BASE = "https://github.com/godotengine/godot-builds/releases/download/4.7.2-stable/"
# SHA-256 and byte sizes from the official, immutable GitHub release assets.
DOWNLOADS = {
    "windows": (GODOT_BASE + "Godot_v4.7.2-stable_win64.exe.zip", 86013866,
                "731980f9608d61333e5baf54a2ef17210acc7a538446c0cb9969f002aca1e953"),
    "linux": (GODOT_BASE + "Godot_v4.7.2-stable_linux.x86_64.zip", 77860424,
              "cadd3204e728a35d3f13adb7fd0d7902636b79f6b95c40c265eb73b6c35329e4"),
    "templates": (GODOT_BASE + "Godot_v4.7.2-stable_export_templates.tpz", 1281349702,
                  "f298490b8d44d934be425a5a65a51bf15f422428b229a06a6e11d9ffea248011"),
    "inno": ("https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe",
             10592232, "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"),
}


def download(spec: tuple[str, int, str], target: Path) -> None:
    url, size, checksum = spec
    print(f"Downloading verified tool: {url.rsplit('/', 1)[-1]}", flush=True)
    digest, count = hashlib.sha256(), 0
    request = urllib.request.Request(url, headers={"User-Agent": "Rabbit-Lands-release-builder"})
    # Opening first establishes ownership; an existing file is never deleted.
    with target.open("xb") as output:
        try:
            with urllib.request.urlopen(request, timeout=120) as source:
                while chunk := source.read(1024**2):
                    count += len(chunk)
                    if count > size:
                        raise ValueError("Tool download is larger than its pinned size.")
                    digest.update(chunk)
                    output.write(chunk)
            if count != size or digest.hexdigest() != checksum:
                raise ValueError("Tool download failed its pinned size or SHA-256 check.")
        except BaseException:
            output.close()
            target.unlink(missing_ok=True)
            raise


def extract_member(archive: Path, member: str, target: Path) -> None:
    # Extract only an explicitly named member, never a whole archive tree.
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source, source.open(member) as entry, target.open("xb") as output:
        shutil.copyfileobj(entry, output, 1024**2)


def install(platform: str, root: Path) -> dict:
    if (platform == "windows") != (os.name == "nt"):
        raise ValueError("Run each hosted platform build on its native operating system.")
    root.mkdir(parents=True, exist_ok=False)
    godot_name = ("Godot_v4.7.2-stable_win64.exe" if platform == "windows"
                  else "Godot_v4.7.2-stable_linux.x86_64")
    godot = root / godot_name
    editor_zip = root / "editor.zip"
    download(DOWNLOADS[platform], editor_zip)
    extract_member(editor_zip, godot_name, godot)
    editor_zip.unlink()
    if platform == "linux":
        godot.chmod(0o755)

    # Keep templates and Godot's own build-time data inside the accounted root.
    data = root / "data"
    template_dir = data / ("Godot" if platform == "windows" else "godot") / "export_templates/4.7.2.stable"
    template = "windows_release_x86_64.exe" if platform == "windows" else "linux_release.x86_64"
    templates_zip = root / "templates.tpz"
    download(DOWNLOADS["templates"], templates_zip)
    extract_member(templates_zip, "templates/" + template, template_dir / template)
    templates_zip.unlink()
    config = {"godot": godot, "env": {"APPDATA" if platform == "windows" else "XDG_DATA_HOME": str(data)}}
    if platform == "windows":
        installer = root / "inno-installer.exe"
        download(DOWNLOADS["inno"], installer)
        inno = root / "inno"
        subprocess.run([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                        "/SP-", "/CURRENTUSER", "/NOICONS", f"/DIR={inno}"], check=True)
        installer.unlink()
        config["iscc"] = inno / "ISCC.exe"
        if not config["iscc"].is_file():
            raise ValueError("Inno Setup 6 installation did not provide ISCC.exe.")
    return config
