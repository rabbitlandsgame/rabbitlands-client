"""Finalize two small runner receipts; no multi-gigabyte artifacts are downloaded."""
import argparse
import json
from pathlib import Path
import re

import build_release as release
import shared_release_assets as shared
from runner_release import authorize
from full_optimization_package import validate_proof


def finalize(receipts: list[Path], out: Path) -> str:
    data = [json.loads(path.read_text(encoding="utf-8")) for path in receipts]
    if len(data) != 2 or {item.get("platform") for item in data} != {"windows", "linux"}:
        raise ValueError("Provide one completed receipt for each platform.")
    sha, release_id = data[0]["commit"], data[0]["release_id"]
    if len({item.get("update_schema", 1) for item in data}) != 1:
        raise ValueError("Both platform receipts must use the same update format.")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Runner commit must be a full public commit ID.")
    rows, stages, shared_rows, helpers = {}, {}, {}, {}
    pooled = data[0].get("shared_storage") == 1
    if any((item.get("shared_storage") == 1) != pooled for item in data):
        raise ValueError("Both platforms must use the same asset storage.")
    pool_id = data[0].get("shared_release_id") if pooled else None
    for item in data:
        if (item.get("schema") != 1 or item["repository"] != release.REPOSITORY
                or item["commit"] != sha or item["release_id"] != release_id):
            raise ValueError("Runner receipts do not describe the same release.")
        platform = item["platform"]
        validate_proof(item.get("optimizations"), sha, platform)
        stage = item["stage"]
        if not re.fullmatch(f"RabbitLands-{platform.title()}-[0-9]{{8}}-{sha[:9]}", stage):
            raise ValueError("Unexpected runner stage name.")
        stages[platform] = stage
        packaged = item.get("update_schema", 1) == 2
        if pooled:
            if not packaged or item.get("shared_release_id") != pool_id or not isinstance(pool_id, int) or pool_id <= 0:
                raise ValueError("Platform receipts use different shared downloads.")
            for name, row in shared.receipt_assets(item).items():
                if name in shared_rows and shared_rows[name] != row:
                    raise ValueError("Shared platform checksums disagree.")
                shared_rows[name] = row
            helpers[platform] = item["shared_helpers"]
        allowed = re.compile(re.escape(stage) + (
            r"(?:-windows\.json|-setup\.exe|-(?:updater|uninstall)\.exe|\.pkg\.[a-z0-9-]+\.zip\.\d{3,}|\.update\.zip\.\d{3,})" if platform == "windows" else
            r"(?:-linux\.json|-download\.sh|-(?:updater|uninstall)\.x86_64|\.pkg\.[a-z0-9-]+\.zip\.\d{3,}|\.update\.zip\.\d{3,}|\.tar\.gz\.\d{3,})"))
        names = set()
        for row in item["assets"]:
            if (set(row) != {"name", "size", "sha256"} or not (allowed.fullmatch(row["name"]) or (packaged and row["name"] == f"RabbitLands-{platform}.json"))
                    or row["name"] in rows or not 0 < row["size"] < release.ASSET_LIMIT
                    or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
                raise ValueError("Invalid, duplicated or unexpected runner download.")
            rows[row["name"]] = row
            names.add(row["name"])
        required = {f"{stage}-{platform}.json",
                    f"{stage}-setup.exe" if platform == "windows" else f"{stage}-download.sh"}
        if not pooled:
            required.add(f"{stage}.pkg.client.zip.001" if packaged else f"{stage}.update.zip.001")
        if packaged and not pooled:
            extension = "exe" if platform == "windows" else "x86_64"
            required.update({f"RabbitLands-{platform}.json", f"{stage}.pkg.engine.zip.001",
                             f"{stage}-updater.{extension}", f"{stage}-uninstall.{extension}"})
        if packaged:
            required.add(f"RabbitLands-{platform}.json")
        if platform == "linux" and not pooled:
            required.add(f"{stage}.tar.gz.001")
        if not required <= names:
            raise ValueError("A runner receipt is missing required downloads.")
    if len(rows) + 1 > 1000:
        raise ValueError("Too many release assets.")
    if len(shared_rows) > 1000:
        raise ValueError("Too many shared release assets.")
    optimization_proofs = {item["platform"]: item["optimizations"] for item in data}
    if len({proof["coverage_sha256"] for proof in optimization_proofs.values()}) != 1 \
            or len({proof["native_source_digest"] for proof in optimization_proofs.values()}) != 1:
        raise ValueError("Desktop platforms qualified different native sources or prepared coverage plans.")
    authorize()
    if release.gh("api", f"repos/{release.REPOSITORY}/commits/{sha}", "--jq", ".sha") != sha:
        raise ValueError("Runner source commit is not public.")
    draft = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{release_id}"))
    if not draft["draft"] or draft["author"]["login"] not in (release.ACCOUNT, "github-actions[bot]"):
        raise ValueError("Runner finalization requires the project's draft.")
    remote = {asset["name"]: asset for asset in release.github_assets(release_id)}
    if any(not release.asset_matches(remote.get(name, {}), row) for name, row in rows.items()):
        raise ValueError("A runner download is missing or failed checksum verification; keeping previous files.")
    if pooled:
        shared.validate_release(json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{pool_id}")))
        remote_pool = {a["name"]: a for a in release.github_assets(pool_id)}
        if any(not release.asset_matches(remote_pool.get(name, {}), row) for name, row in shared_rows.items()):
            raise ValueError("A shared download failed checksum verification; keeping previous files.")
    tag = f"client-{sha}"
    refs = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/matching-refs/tags/{tag}"))
    for ref in refs:
        if ref["ref"] == f"refs/tags/{tag}":
            obj = ref["object"]
            while obj["type"] == "tag":
                obj = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/tags/{obj['sha']}"))["object"]
            if obj["type"] != "commit" or obj["sha"] != sha:
                raise ValueError("The release tag points to another source commit.")
    out.mkdir(parents=True, exist_ok=False)
    sums = out / "SHA256SUMS"
    sums.write_text("".join(f"{row['sha256']}  {name}\n" for name, row in sorted((rows | shared_rows).items())), encoding="ascii")
    checksum = {"size": sums.stat().st_size, "sha256": release.client_release.digest(sums)}
    release.upload_asset(draft["tag_name"], release_id, sums, checksum, remote.get(sums.name, {}))
    rows[sums.name] = {"name": sums.name, **checksum}
    # Re-read after the checksum upload; only then retag the draft and prune.
    actual = release.github_assets(release_id)
    remote = {asset["name"]: asset for asset in actual}
    if any(not release.asset_matches(remote.get(name, {}), row) for name, row in rows.items()):
        raise ValueError("Final checksum verification failed; keeping previous files.")
    if pooled:
        remote_pool = {a["name"]: a for a in release.github_assets(pool_id)}
        if any(not release.asset_matches(remote_pool.get(name, {}), row) for name, row in shared_rows.items()):
            raise ValueError("Final shared checksum verification failed; keeping previous files.")
    base = f"https://github.com/{release.REPOSITORY}/releases/download/{tag}"
    windows, linux = stages["windows"], stages["linux"]
    notes = out / "RELEASE-NOTES.md"
    notes.write_text(f'''# Rabbit Lands desktop downloads

Client commit: `{sha}`. Only the current compiled client is kept in Releases.

## Windows x86_64

Download the Windows installer, `{windows}-setup.exe`, from **Assets** below and run it.
Setup downloads and verifies the prepared game files. Installation is per user.

## Linux x86_64

Download the Linux helper, `{linux}-download.sh`, from **Assets** below and run:

```sh
sh ./{linux}-download.sh
~/Games/{linux}/RabbitLands.sh
```

The helper requires `curl`, `sha256sum` and `tar`, verifies every download and the
complete archive, and reuses verified downloads when retrying. Pass another parent
folder as its first argument. An existing game folder will not be overwritten.

Neither platform needs Python or the Godot editor. `SHA256SUMS` lists all file hashes.
The platform JSON manifests and `.pkg.*.zip.###` packages support signed updates.
The updater checks installed files and downloads only changed packages. It also
verifies and replaces its own executable when needed. Run the installed
`RabbitLands-uninstall` executable (or Windows Installed apps) to remove the game;
player settings are kept.

Existing installations from before package updates can migrate by downloading
the platform's `*-updater` executable from this release into their game folder
and running it once. Fresh Windows installations still need just the setup file.
See [installation instructions](https://github.com/{release.REPOSITORY}/wiki/Access-and-Installation).
''', encoding="utf-8", newline="\n")
    if pooled:
        text = notes.read_text()
        start, end = text.index("```sh"), text.index("Neither platform needs")
        text = text[:start] + f'''```sh
sh ./{linux}-download.sh
~/Games/RabbitLands/RabbitLands-updater.x86_64
```

The helper needs `curl` and `sha256sum`. It verifies the native updater, which
downloads the required game packages. Pass another parent folder as its first
argument. Existing installations reuse their matching packages.

''' + text[end:]
        text = text.replace("the platform's `*-updater` executable from this release into their game folder",
            "the platform's updater linked below into their game folder")
        text += "\n## Standalone helpers\n\n"
        for platform, names in helpers.items():
            text += "\n" + platform.title() + ": " + ", ".join(
                f"[{kind}]({shared.base(release.REPOSITORY)}/{name})" for kind, name in names.items()) + ".\n"
        text = text.replace("`.pkg.*.zip.###` packages", "checksum-named ZIP packages")
        text += "\nSupporting package files live in one shared downloads release. Only changed checksums are uploaded; the latest playable release is still the only retained game version.\n"
        notes.write_text(text, encoding="utf-8", newline="\n")
    release.gh("release", "edit", draft["tag_name"], "--repo", release.REPOSITORY, "--draft", "--tag", tag,
               "--target", sha, "--title", f"Rabbit Lands {sha[:9]}", "--notes-file", str(notes))
    for asset in actual:
        if asset["name"] not in rows:
            release.gh("api", "--method", "DELETE", f"repos/{release.REPOSITORY}/releases/assets/{asset['id']}")
    final = release.github_assets(release_id)
    if {asset["name"] for asset in final} != set(rows):
        raise ValueError("Previous build cleanup is incomplete; the release remains a draft.")
    for other in release.github_releases():
        if other["id"] != release_id and other.get("draft") and re.fullmatch(r"client-[0-9a-f]{40}", other["tag_name"]):
            release.gh("release", "delete", other["tag_name"], "--repo", release.REPOSITORY, "--yes")
    release.write_json(out / "client_updates.json", {"schema": 1, "required_commit": sha, "enforce": True,
        "manifests": {platform: f"{base}/{stage}-{platform}.json" for platform, stage in stages.items()}})
    release.write_json(out / "runner-release.json", {"schema": 1, "repository": release.REPOSITORY, "commit": sha, "release_id": release_id,
        "optimizations": optimization_proofs,
        "assets": list(rows.values()), "shared_assets": list(shared_rows.values()), "shared_release_id": pool_id,
        "transfer": {key: sum(i.get("transfer", {}).get(key, 0) for i in data) for key in ("uploaded_bytes", "reused_bytes")}})
    url = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{release_id}"))["html_url"]
    print(f"Draft verified: {url}")
    return url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--linux", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    finalize([args.windows, args.linux], args.out)
