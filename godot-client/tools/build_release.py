"""Build both desktop downloads, then optionally upload a GitHub release.

Run `build_release.py build --help` or `build_release.py upload --help`.
Builds run on Windows with Godot 4.7.2, Inno Setup 6 and WSL Ubuntu-24.04.
Uploading is a separate step and creates a draft unless --publish is supplied.
"""
from __future__ import annotations

import argparse
import base64
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import client_release
import package_client

REPOSITORY = "rabbitlandsgame/rabbitlands-client"
ACCOUNT = "rabbitlandsgame"
ASSET_LIMIT = 2 * 1024**3  # GitHub requires each asset to be strictly smaller.
PART_BYTES = client_release.PART_BYTES
REPO = package_client.REPO


def run(args: list[str], *, capture: bool = False) -> str:
    try:
        result = subprocess.run(args, cwd=REPO, text=True, encoding="utf-8", errors="replace",
                                capture_output=capture, check=True)
    except subprocess.CalledProcessError as error:
        if capture and error.stderr:
            raise ValueError(error.stderr.strip()) from error
        raise
    return result.stdout.strip() if capture else ""


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def preflight(options) -> tuple[str, Path, Path]:
    if os.name != "nt":
        raise ValueError("Build both targets on Windows with Inno Setup 6 and WSL Ubuntu-24.04.")
    origin = package_client.git("remote", "get-url", "origin").strip()
    if origin != f"git@github.com:{REPOSITORY}.git":
        raise ValueError("Run from the final Rabbit Lands client checkout with its project SSH remote.")
    sha = package_client.git("rev-parse", "--verify", "--end-of-options", options.ref + "^{commit}").strip()
    key = options.update_signing_key.resolve()
    if not key.is_file():
        raise ValueError("The existing update signing key is required; see docs/client-updates.md.")
    if any(key.is_relative_to(repo) for repo in (REPO, REPO.parent / "rabbitlands-server")):
        raise ValueError("Keep the private signing key outside both repositories.")
    client_release.identity(REPO, sha, "windows", package_client.CLIENT / "data/update_public.pem", REPOSITORY)
    godot = package_client.find_godot(options.godot).resolve()
    if not run([str(godot), "--headless", "--version"], capture=True).startswith("4.7.2.stable"):
        raise ValueError("Use Godot 4.7.2-stable and its matching export templates.")
    templates = Path(os.environ["APPDATA"]) / "Godot/export_templates/4.7.2.stable"
    for name in ("windows_release_x86_64.exe", "linux_release.x86_64"):
        if not (templates / name).is_file():
            raise ValueError(f"Install both Godot 4.7.2 export templates; missing {name}.")
    iscc = package_client.find_iscc(options.iscc)
    if iscc is None:
        raise ValueError("Install Inno Setup 6 or pass --iscc <path to ISCC.exe>.")
    for module in ("numpy", "PIL", "zstandard"):
        importlib.import_module(module)
    wsl = shutil.which("wsl.exe")
    if not wsl:
        raise ValueError("Install WSL Ubuntu-24.04 for the Linux executable smoke check.")
    run([wsl, "-d", package_client.WSL_DISTRO, "--exec", "true"], capture=True)
    return sha, godot, iscc.resolve()


def initial_linux_assets(archive: Path) -> list[Path]:
    if archive.stat().st_size <= PART_BYTES:
        return [archive]
    # Keep the full local archive, but upload only its bounded parts.
    parts = client_release.split_payload(archive, "", part_bytes=PART_BYTES)
    return [archive.parent / part["url"].rsplit("/", 1)[1] for part in parts]


def platform_assets(folder: Path, sha: str, platform: str) -> tuple[list[Path], dict, Path]:
    stages = [path for path in folder.iterdir() if path.is_dir() and (path / package_client.MARKER).is_file()]
    if len(stages) != 1:
        raise ValueError(f"Expected exactly one completed {platform} package in {folder}.")
    stage = stages[0]
    identity = json.loads((stage / "app/client-release.json").read_text(encoding="utf-8"))
    if identity["commit"] != sha or identity["platform"] != platform or identity["repository"] != REPOSITORY:
        raise ValueError("The package identity does not match the selected release.")
    manifest = folder / f"{stage.name}-{platform}.json"
    signed = json.loads(manifest.read_text(encoding="utf-8"))
    payload = json.loads(base64.b64decode(signed["payload"], validate=True))
    if not signed.get("signature") or payload["commit"] != sha or payload["platform"] != platform:
        raise ValueError("The signed update manifest does not match the release.")
    assets = [manifest]
    base = f"https://github.com/{REPOSITORY}/releases/download/client-{sha}/"
    if not payload["parts"]:
        raise ValueError("An update payload must have at least one part.")
    for part in payload["parts"]:
        name = part["url"].removeprefix(base)
        suffix = r"\.pkg\.[a-z0-9-]+\.zip\.\d{3,}" if payload.get("schema") == 2 else r"\.update\.zip\.\d{3,}"
        if not part["url"].startswith(base) or not re.fullmatch(re.escape(stage.name) + suffix, name):
            raise ValueError("Unexpected update asset URL.")
        path = folder / name
        if path.stat().st_size != part["size"] or client_release.digest(path) != part["sha256"]:
            raise ValueError(f"Update part verification failed: {name}")
        assets.append(path)
    if payload.get("schema") == 2:
        alias = folder / f"RabbitLands-{platform}.json"
        if alias.read_bytes() != manifest.read_bytes():
            raise ValueError("The latest-update alias differs from the signed manifest.")
        assets.append(alias)
        for kind in ("updater", "uninstall"):
            row = payload[kind]
            path = folder / row["url"].removeprefix(base)
            if not row["url"].startswith(base) or path.parent != folder or not path.is_file() or path.stat().st_size != row["size"] or client_release.digest(path) != row["sha256"]:
                raise ValueError("A bootstrap executable failed verification.")
            assets.append(path)
    policy = json.loads((folder / f"{stage.name}-server-policy.json").read_text(encoding="utf-8"))
    if policy != {"schema": 1, "required_commit": sha, "enforce": True,
                  "manifests": {platform: base + manifest.name}}:
        raise ValueError("The server policy does not match the release.")
    if platform == "windows":
        setup = folder / f"{stage.name}-setup.exe"
        if not setup.is_file():
            raise ValueError("The Windows installer was not built.")
        receipt = folder / f"{stage.name}-setup-downloads.json"
        if receipt.is_file():
            expected = {"schema": 1, "mode": "online", "commit": sha, "manifest": manifest.name,
                        "parts": [{"name": part["url"].rsplit("/", 1)[1], "size": part["size"], "sha256": part["sha256"]}
                                  for part in payload["parts"]]}
            if json.loads(receipt.read_text(encoding="utf-8")) != expected:
                raise ValueError("The online installer downloads do not match the signed release.")
            assets.append(setup)
        else:
            assets.extend([setup, *sorted(folder.glob(f"{stage.name}-setup-*.bin"))])
    else:
        assets.extend(initial_linux_assets(folder / f"{stage.name}.tar.gz"))
    return assets, policy, stage


def inventory(root: Path, assets: list[Path]) -> list[dict]:
    rows = []
    names = set()
    for path in assets:
        path = path.resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Release assets must be files inside this build's output directory.")
        size = path.stat().st_size
        if not 0 < size < ASSET_LIMIT or path.name in names:
            raise ValueError(f"Invalid, duplicate or oversized release asset: {path.name}")
        names.add(path.name)
        rows.append({"path": path.relative_to(root.resolve()).as_posix(),
                     "size": size, "sha256": client_release.digest(path)})
    if len(rows) > 1000:
        raise ValueError("GitHub permits at most 1000 assets in a release.")
    return rows


def release_notes(sha: str, stages: dict[str, Path], linux_assets: list[Path]) -> str:
    windows, linux = stages["windows"].name, stages["linux"].name
    split = any(re.search(r"\.tar\.gz\.\d+$", path.name) for path in linux_assets)
    linux_download = f"every `{linux}.tar.gz.###` part" if split else f"`{linux}.tar.gz`"
    extract = (f"cat {linux}.tar.gz.[0-9][0-9][0-9]* | tar -xz -C ~/Games"
               if split else f"tar -xzf {linux}.tar.gz -C ~/Games")
    online = (stages["windows"].parent / f"{windows}-setup-downloads.json").is_file()
    windows_install = (
        f"Download `{windows}-setup.exe` and run it. An internet connection is required: "
        "setup downloads and verifies the matching game files automatically. "
        "Use the Rabbit Lands Start menu shortcut after installation. "
        "Installation is per user and needs no administrator rights."
        if online else
        f"Download `{windows}-setup.exe` and every accompanying `{windows}-setup-*.bin` "
        "file into the same folder. Run the setup executable, then use the Rabbit Lands "
        "Start menu shortcut. Installation is per user and needs no administrator rights.")
    return f"""# Rabbit Lands desktop downloads

Client commit: `{sha}`. Use the server settings announced for your testing round.
Only the current compiled client build is kept in GitHub Releases.

## Windows x86_64

{windows_install}

## Linux x86_64

Download {linux_download} into one folder. Extract and launch:

```sh
mkdir -p ~/Games
{extract}
cd ~/Games/{linux}
./RabbitLands.sh
```

Keep the complete game folder together. Neither platform needs Python or the
Godot editor. Use the supplied compatibility or safe-mode launcher if needed.

`SHA256SUMS` lists the SHA-256 of each download. On Linux, verify a downloaded
file with `sha256sum <filename>` against its entry before extracting. On
Windows use `Get-FileHash <filename> -Algorithm SHA256` in PowerShell.

The platform JSON manifests and `.pkg.*.zip.###` files are for the game's
signed updater, which downloads only changed packages and updates itself.
The separately downloadable `*-updater` executable can migrate an older install;
place it in the game folder and run it. Run `RabbitLands-uninstall` to remove
the installation while keeping player settings. Initial Windows installations
still use just the setup executable above.
See [installation instructions](https://github.com/{REPOSITORY}/wiki/Access-and-Installation).
"""


def build(options) -> Path:
    sha, godot, iscc = preflight(options)
    root = options.out.resolve() / f"client-{sha}"
    if any(root.is_relative_to(repo) for repo in (REPO, REPO.parent / "rabbitlands-server")):
        raise ValueError("Place release outputs outside both repositories.")
    root.mkdir(parents=True, exist_ok=False)
    for platform in ("windows", "linux"):
        folder = root / platform
        folder.mkdir()
        command = [sys.executable, str(Path(__file__).with_name("package_client.py")),
                   "--platform", platform, "--ref", sha, "--release-build", "--no-fetch", "--godot", str(godot),
                   "--out", str(folder), "--update-signing-key", str(options.update_signing_key.resolve())]
        if options.server:
            command.extend(["--server", options.server])
        if platform == "windows":
            command.extend(["--installer", "--online-installer", "--iscc", str(iscc), "--no-zip"])
        run(command)
    return assemble(root, sha)


def assemble(root: Path, sha: str) -> Path:
    """Collect two completed platform builds, including after an installer retry."""
    assets, stages, manifests = [], {}, {}
    for platform in ("windows", "linux"):
        found, policy, stage = platform_assets(root / platform, sha, platform)
        assets.extend(found)
        stages[platform] = stage
        manifests.update(policy["manifests"])
    rows = inventory(root, assets)
    sums = root / "SHA256SUMS"
    sums.write_text("".join(f"{row['sha256']}  {Path(row['path']).name}\n" for row in rows), encoding="ascii")
    rows.extend(inventory(root, [sums]))
    if len(rows) > 1000:
        raise ValueError("Too many release assets.")
    write_json(root / "client_updates.json", {"schema": 1, "required_commit": sha,
               "enforce": True, "manifests": manifests})
    (root / "RELEASE-NOTES.md").write_text(release_notes(sha, stages, assets), encoding="utf-8")
    bundle = root / "release.json"
    write_json(bundle, {"schema": 1, "repository": REPOSITORY, "commit": sha,
                       "tag": f"client-{sha}", "assets": rows})
    print(f"Release ready: {bundle}\nReview RELEASE-NOTES.md, then run this script's upload command.")
    return bundle


def gh(*args: str) -> str:
    return run(["gh", *args], capture=True)


def github_releases() -> list[dict]:
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{REPOSITORY}/releases?per_page=100"))
    return [release for page in pages for release in page]


def github_release(tag: str) -> dict | None:
    return next((release for release in github_releases() if release["tag_name"] == tag), None)


def github_assets(release_id: int) -> list[dict]:
    pages = json.loads(gh("api", "--paginate", "--slurp",
                          f"repos/{REPOSITORY}/releases/{release_id}/assets?per_page=100"))
    return [asset for page in pages for asset in page]


def asset_matches(asset: dict, row: dict) -> bool:
    return (asset.get("state") == "uploaded" and asset.get("size") == row["size"]
            and asset.get("digest") == "sha256:" + row["sha256"])


def upload_asset(tag: str, release_id: int, path: Path, row: dict, old: dict) -> None:
    for attempt in range(5):
        if asset_matches(old, row):
            return
        if old:
            # Interrupted transfers reserve names that gh's lookup omits.
            gh("api", "--method", "DELETE", f"repos/{REPOSITORY}/releases/assets/{old['id']}")
        print(f"Uploading {path.name} ({row['size']} bytes)", flush=True)
        try:
            gh("release", "upload", tag, str(path), "--repo", REPOSITORY, "--clobber")
            return
        except ValueError as error:
            network_errors = ("bad record mac", "connection", "eof", "timeout", "timed out",
                              "stream error", "http 502", "http 503", "http 504")
            if not any(message in str(error).lower() for message in network_errors):
                raise
            old = next((asset for asset in github_assets(release_id) if asset["name"] == path.name), {})
            if asset_matches(old, row):
                return  # GitHub stored it even though the response was lost.
            if attempt == 4:
                raise
            print(f"Connection interrupted; retrying {path.name} ({attempt + 2}/5).", flush=True)
            time.sleep(min(2**attempt, 8))


def upload_asset_api(release_id: int, path: Path, row: dict, old: dict) -> dict:
    """Stream one runner asset; verify the upload response without listing N pages.

    Hundreds of independent packages must not trigger a whole-release scan per
    upload. Finalization still re-reads and verifies the complete remote inventory.
    """
    if asset_matches(old, row):
        return old
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        token = gh("auth", "token", "--hostname", "github.com")
    url = f"https://uploads.github.com/repos/{REPOSITORY}/releases/{int(release_id)}/assets?name=" + urllib.parse.quote(path.name, safe="-._")
    for attempt in range(5):
        if old:
            gh("api", "--method", "DELETE", f"repos/{REPOSITORY}/releases/assets/{int(old['id'])}")
            old = {}
        try:
            print(f"Uploading {path.name} ({row['size']} bytes)", flush=True)
            with path.open("rb") as stream:
                request = urllib.request.Request(url, data=stream, method="POST", headers={
                    "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                    "Content-Type": "application/octet-stream", "Content-Length": str(row["size"]),
                    "User-Agent": "Rabbit-Lands-release", "X-GitHub-Api-Version": "2022-11-28"})
                with urllib.request.urlopen(request, timeout=3600) as response:
                    actual = json.loads(response.read(1024 * 1024))
            if actual.get("name") != path.name or not asset_matches(actual, row):
                raise ValueError(f"GitHub did not verify {path.name}; retaining the local part.")
            return actual
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in (408, 409, 422, 429, 500, 502, 503, 504):
                raise ValueError(f"GitHub upload failed for {path.name} (HTTP {error.code}).") from None
            # Recover a completed upload after a lost response, or remove its
            # interrupted starter reservation before retrying the same filename.
            old = next((asset for asset in github_assets(release_id) if asset["name"] == path.name), {})
            if asset_matches(old, row):
                return old
            if attempt == 4:
                raise ValueError(f"GitHub upload failed for {path.name}; retaining the local part.") from None
            time.sleep(min(2**attempt, 8))
    raise ValueError("GitHub upload did not complete.")


def upload(bundle: Path, publish: bool = False) -> None:
    root = bundle.resolve().parent
    data = json.loads(bundle.read_text(encoding="utf-8"))
    sha, tag = data["commit"], data["tag"]
    if (data.get("schema") != 1 or data["repository"] != REPOSITORY
            or not re.fullmatch(r"[0-9a-f]{40}", sha) or tag != f"client-{sha}"):
        raise ValueError("This is not a Rabbit Lands release bundle.")
    paths = [root / row["path"] for row in data["assets"]]
    if not paths or inventory(root, paths) != data["assets"]:
        raise ValueError("A release asset changed after the build; refusing to upload.")
    notes = root / "RELEASE-NOTES.md"
    if not notes.is_file():
        raise ValueError("Release notes are missing.")
    if gh("api", "user", "--jq", ".login").lower() != ACCOUNT:
        raise ValueError("Sign gh into rabbitlandsgame before uploading. An unrelated account cannot publish this project.")
    if gh("api", f"repos/{REPOSITORY}", "--jq", ".permissions.push") != "true":
        raise ValueError("The project account needs write access to the release repository.")
    # Require the packaged commit to be public already. Never push local history.
    if gh("api", f"repos/{REPOSITORY}/commits/{sha}", "--jq", ".sha") != sha:
        raise ValueError("Push the selected client commit before uploading its release.")
    refs = json.loads(gh("api", f"repos/{REPOSITORY}/git/matching-refs/tags/{tag}"))
    for ref in refs:
        if ref["ref"] != f"refs/tags/{tag}":
            continue
        obj = ref["object"]
        while obj["type"] == "tag":
            obj = json.loads(gh("api", f"repos/{REPOSITORY}/git/tags/{obj['sha']}"))["object"]
        if obj["type"] != "commit" or obj["sha"] != sha:
            raise ValueError("The remote release tag points to a different commit.")
    releases = github_releases()
    client_releases = [release for release in releases if re.fullmatch(r"client-[0-9a-f]{40}", release["tag_name"])]
    existing = next((release for release in client_releases if release["tag_name"] == tag), None)
    if existing and not existing["draft"]:
        raise ValueError("This client commit is already published. Build a newer commit instead of taking its downloads offline.")
    drafts = [item for item in client_releases if item["draft"]]
    if not existing and drafts:
        existing = max(drafts, key=lambda release: release["id"])
    if not existing:
        gh("release", "create", tag, "--repo", REPOSITORY, "--target", sha, "--draft",
           "--title", f"Rabbit Lands {sha[:9]}", "--notes-file", str(notes))
        existing = github_release(tag)
    else:
        # Reuse a draft only. Keep the working published downloads available
        # until their verified replacement has actually been published.
        gh("release", "edit", existing["tag_name"], "--repo", REPOSITORY, "--draft", "--tag", tag,
           "--target", sha, "--title", f"Rabbit Lands {sha[:9]}", "--notes-file", str(notes))
        existing = github_release(tag)
    if not existing or not existing["draft"]:
        raise ValueError("Could not find the expected draft release.")
    # Fetch drafts by their release ID; the tag endpoint is for published releases.
    previous = {asset["name"]: asset for asset in github_assets(existing["id"])}
    # Small calls avoid the Windows command-line length limit. Resume only when
    # GitHub's recorded digest proves that an existing upload is identical.
    for path, row in zip(paths, data["assets"]):
        upload_asset(tag, existing["id"], path, row, previous.get(path.name, {}))
    uploaded = github_assets(existing["id"])
    expected = {path.name: path.stat().st_size for path in paths}
    remote_sizes = {asset["name"]: asset["size"] for asset in uploaded}
    if any(remote_sizes.get(name) != size for name, size in expected.items()):
        raise ValueError("Remote assets do not match the bundle; the release remains a draft.")
    digests = {Path(row["path"]).name: "sha256:" + row["sha256"] for row in data["assets"]}
    if any(asset["name"] in digests and (asset.get("state") != "uploaded"
            or asset.get("digest") != digests[asset["name"]]) for asset in uploaded):
        raise ValueError("A remote download checksum differs; the release remains a draft.")
    # Prune only after every replacement download is uploaded and verified.
    for asset in uploaded:
        if asset["name"] not in expected:
            gh("api", "--method", "DELETE", f"repos/{REPOSITORY}/releases/assets/{asset['id']}")
    if {asset["name"]: asset["size"] for asset in github_assets(existing["id"])} != expected:
        raise ValueError("Old release assets could not be removed; the release remains a draft.")
    if publish:
        gh("release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--latest")
    for other in client_releases:
        if other["id"] != existing["id"] and (other["draft"] or publish):
            gh("release", "delete", other["tag_name"], "--repo", REPOSITORY, "--yes")
    print(f"{'Published' if publish else 'Draft ready'}: https://github.com/{REPOSITORY}/releases/tag/{tag}")
    print("After publication and download verification, deploy client_updates.json to the served server profile.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build", help="build signed Windows and Linux release downloads")
    builder.add_argument("--ref", default="master", help="committed client ref (default: local stable master)")
    builder.add_argument("--update-signing-key", type=Path, required=True)
    builder.add_argument("--godot", help="Godot 4.7.2 Windows console executable")
    builder.add_argument("--iscc", help="Inno Setup 6 compiler")
    builder.add_argument("--server", help="bake HOST[:PORT] into both platforms' launchers")
    builder.add_argument("--out", type=Path, default=package_client.DIST / "releases", help="release output base directory")
    uploader = commands.add_parser("upload", help="upload an existing bundle as the project account")
    uploader.add_argument("--bundle", type=Path, required=True, help="release.json printed by build")
    uploader.add_argument("--publish", action="store_true", help="publish after every asset is uploaded and checked (default: draft)")
    options = parser.parse_args()
    try:
        if options.command == "build":
            build(options)
        else:
            upload(options.bundle, options.publish)
    except (OSError, ValueError, KeyError, ImportError, package_client.PackageError, subprocess.CalledProcessError) as error:
        print(f"Release failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
