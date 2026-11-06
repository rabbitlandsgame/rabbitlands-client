"""Finalize two small runner receipts; no multi-gigabyte artifacts are downloaded.

`finalize` serves desktop-release.yml (runner receipts). `finalize_r2` serves
desktop-release-r2.yml: signed manifests, content artifacts and e2e receipts.
"""
import argparse
import json
import os
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
    partitioned = "shared_release_ids" in data[0]
    pool_ids = {}
    if any(("shared_release_ids" in item) != partitioned for item in data):
        raise ValueError("Both platforms must use the same storage layout.")
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
        packaged = shared.packaged(item.get("update_schema", 1))
        if pooled:
            if partitioned:
                if not isinstance(item["shared_release_ids"], dict):
                    raise ValueError("Invalid shared storage release identities.")
                for storage_tag, storage_id in item["shared_release_ids"].items():
                    if storage_tag in pool_ids and pool_ids[storage_tag] != storage_id:
                        raise ValueError("Platform shared storage destinations disagree.")
                    pool_ids[storage_tag] = storage_id
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
    if not partitioned and len(shared_rows) > 1000:
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
        if partitioned:
            if pool_ids.get(shared.TAG) != pool_id:
                raise ValueError("Legacy helper storage identity changed.")
        shared.validate_release(json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{pool_id}")))
        remote_pool = shared.verify_storage(shared_rows, pool_ids) if partitioned else {a["name"]: a for a in release.github_assets(pool_id)}
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
        remote_pool = shared.verify_storage(shared_rows, pool_ids) if partitioned else {a["name"]: a for a in release.github_assets(pool_id)}
        if any(not release.asset_matches(remote_pool.get(name, {}), row) for name, row in shared_rows.items()):
            raise ValueError("Final shared checksum verification failed; keeping previous files.")
    base = f"https://github.com/{release.REPOSITORY}/releases/download/{tag}"
    windows, linux = stages["windows"], stages["linux"]
    notes = out / "RELEASE-NOTES.md"
    notes.write_text(f'''# Rabbit Lands desktop downloads

Client commit: `{sha}`. Releases keep the latest build and the two before it for rollback.

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
        text += ("\nSupporting package files use shared downloads storage. Only changed checksums are uploaded; "
                 "the files of every retained release stay available.\n")
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
        **({"shared_release_ids": pool_ids} if partitioned else {}),
        "transfer": {key: sum(i.get("transfer", {}).get(key, 0) for i in data) for key in ("uploaded_bytes", "reused_bytes")}})
    url = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{release_id}"))["html_url"]
    print(f"Draft verified: {url}")
    return url


# --- desktop-release-r2.yml (R2-A7) ----------------------------------------------------------
#
# Inputs are the run's artifacts, each digest-checked by the workflow against
# its producer: the signed manifests (envelopes), the content artifacts
# (content-P) and the e2e receipts. GitHub rows (the draft's manifests and
# installers, the CI packages, the helpers and ci-source content parts) are
# checked by GitHub inventory. R2 rows are never looked up on GitHub or R2 here:
# each must be a row of the dispatched content set in content-P, whose SHA-256
# the signed manifest binds. There is no R2 call and no R2 credential.

PLATFORMS = ("windows", "linux")
AUTHORS = (release.ACCOUNT, "github-actions[bot]")
R2_RECEIPT_KIND = "rabbitlands-desktop-r2-release"
R2_RECEIPT_SCHEMA = 1
# desktop_release_ci.E2E.run_all, in order; each must pass (setup.exe may be skipped for disk).
E2E_STEPS = ("updater-row", "install-started", "installed", "installed-files", "smoke-legacy", "startup-legacy",
             "smoke-legacy-clean", "smoke-human-testing", "startup-human-testing", "smoke-human-testing-clean",
             "recheck")
E2E_PLATFORM_STEPS = {"windows": ("setup-exe",), "linux": ("download-sh-content", "download-sh-run")}
INSTALLERS = {"windows": "setup.exe", "linux": "download.sh"}
MAX_RECORD_BYTES = 64 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_ASSET_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def asset_rows(items) -> dict:
    """{name: {name, size, sha256}} of a verified inventory; refuses anything else."""
    result = {}
    for row in items if type(items) is list else [None]:
        if (not isinstance(row, dict) or set(row) != {"name", "size", "sha256"}
                or type(row["name"]) is not str or not _ASSET_NAME.fullmatch(row["name"])
                or type(row["size"]) is not int or not 0 < row["size"] < release.ASSET_LIMIT
                or type(row["sha256"]) is not str or not _SHA256.fullmatch(row["sha256"])
                or row["name"] in result):
            raise ValueError("Invalid verified release inventory.")
        result[row["name"]] = row
    return result


def asset_row(name: str, size, sha256) -> dict:
    return asset_rows([{"name": name, "size": size, "sha256": sha256}])[name]


def _record(path: Path, limit: int = MAX_RECORD_BYTES):
    import desktop_r2 as r2
    path = Path(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"{path.name} is missing or too large.")
    value = r2._parse_json(path.read_bytes())
    if value is None:
        raise ValueError(f"{path.name} is not strict JSON.")
    return value


def _merge(target: dict, key: str, row: dict) -> None:
    if target.setdefault(key, row) != row:
        raise ValueError("One download is named with two identities.")


def check_tag(tag: str, sha: str) -> None:
    """An existing tag (annotated tags followed) must point at `sha`."""
    refs = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/matching-refs/tags/{tag}"))
    for ref in refs:
        if ref["ref"] == f"refs/tags/{tag}":
            obj = ref["object"]
            for _ in range(16):
                if obj["type"] != "tag":
                    break
                obj = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/tags/{obj['sha']}"))["object"]
            if obj["type"] != "commit" or obj["sha"] != sha:
                raise ValueError("The release tag points to another source commit.")


def signed_manifests(envelopes: Path, commit: str, public_pem: bytes) -> dict:
    """{platform: (name, envelope bytes, release)}: sign.json's two manifests, verified with the commit's key."""
    import desktop_r2 as r2
    import release_manifest as rm
    envelopes = Path(envelopes)
    record = _record(envelopes / "sign.json")
    platforms = record.get("platforms") if isinstance(record, dict) else None
    if not isinstance(platforms, dict) or record.get("commit") != commit or set(platforms) != set(PLATFORMS):
        raise ValueError("The envelopes artifact is not this commit's signed release.")
    result = {}
    for platform in PLATFORMS:
        row = platforms[platform]
        name = row.get("manifest") if isinstance(row, dict) else None
        if type(name) is not str or not re.fullmatch(
                rf"RabbitLands-{platform.title()}-[0-9]{{8}}-{commit[:9]}-{platform}\.json", name):
            raise ValueError(f"The envelopes artifact names no valid {platform} manifest.")
        data = (envelopes / name).read_bytes()
        alias = (envelopes / f"RabbitLands-{platform}.json").read_bytes()
        if r2.sha256_hex(data) != row.get("sha256") or alias != data:
            raise ValueError(f"The {platform} manifest or its alias differs from the one signed in this run.")
        _, value = rm.verify(data, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
        version = name[:-len(f"-{platform}.json")]
        if (not shared.packaged(value.get("schema")) or value.get("bootstrap_schema") != rm.BOOTSTRAP_SCHEMA
                or value.get("repository") != release.REPOSITORY or value.get("commit") != commit
                or value.get("platform") != platform or value.get("version") != version):
            raise ValueError(f"The signed {platform} manifest is not this commit's package release.")
        r2.validate_manifest_additions(value, platform=platform)
        content = value["content"]
        if (row.get("source") != content["source"] or row.get("set_sha256") != content["set"]["sha256"]
                or row.get("sequence") != value["sequence"] or row.get("schema") != value["schema"]):
            raise ValueError(f"sign.json and the signed {platform} manifest disagree.")
        if content["source"] == "r2" and value["schema"] != rm.SCHEMA_CODEC:
            raise ValueError(f"The {platform} manifest names R2 content without schema 3.")
        result[platform] = (name, data, value)
    return result


def check_content(directory: Path, release_value: dict) -> dict:
    """content-P is the dispatched set of this manifest, and its packages are the manifest's content rows."""
    import desktop_r2 as r2
    import desktop_release_ci as ci
    platform, content = release_value["platform"], release_value["content"]
    source, digest = content["source"], content["set"]["sha256"]
    path = Path(directory) / "set.json"
    data = path.read_bytes() if path.is_file() and path.stat().st_size <= r2.MAX_SET_BYTES else b""
    if r2.sha256_hex(data) != digest:
        raise ValueError(f"The {platform} content artifact is not the set the manifest names.")
    content_set = r2.parse_set_bytes(data)
    if (content_set.get("kind") != r2.SET_KIND or content_set.get("set_schema") != r2.SET_SCHEMA
            or content_set.get("source") != source or content_set.get("repository") != release.REPOSITORY
            or content_set.get("commit") != release_value["commit"] or content_set.get("platform") != platform
            or content_set.get("version") != release_value["version"] or content_set.get("optional_packages")):
        raise ValueError(f"The {platform} content set is for another release.")
    record = _record(Path(directory) / "verified.json")
    if (not isinstance(record, dict) or record.get("kind") != ci.CONTENT_KIND or record.get("source") != source
            or record.get("platform") != platform or record.get("commit") != release_value["commit"]
            or record.get("set_sha256") != digest or (source == "ci" and record.get("uploaded") is not True)):
        raise ValueError(f"The {platform} content artifact is not a finished content check of this set.")
    expected = {package["id"]: package for package in content_set.get("packages") or []}
    rows = {package["id"]: package for package in release_value["packages"] if package["id"] not in r2.CI_PACKAGE_IDS}
    if len(expected) != len(content_set.get("packages") or []) or rows != expected:
        raise ValueError(f"The {platform} manifest's content packages are not exactly the dispatched set's.")
    return content_set


def manifest_rows(release_value: dict) -> tuple[dict, dict]:
    """(GitHub pool rows by name, R2 rows by key) of every download a verified manifest names."""
    import desktop_r2 as r2
    import release_manifest as rm
    platform, source = release_value["platform"], release_value["content"]["source"]
    pool, hosted = {}, {}
    for package in release_value["packages"]:
        content = package["id"] not in r2.CI_PACKAGE_IDS
        for part in package["parts"]:
            if content and source == "r2" and r2.part_url_matches(part, "r2"):
                key = r2.part_key(part["sha256"])
                _merge(hosted, key, {"key": key, "size": part["size"], "sha256": part["sha256"]})
                continue
            name = str(part.get("url", "")).rsplit("/", 1)[-1]
            identity = shared.NAME.fullmatch(name) if shared.is_name(name) else None
            if (source == "r2" and content) or not identity or identity[1] != "pkg" \
                    or identity[2] != part["sha256"] or part["url"] != shared.download_url(release.REPOSITORY, name):
                raise ValueError(f"A {platform} download is neither an R2 part of an r2 set nor a GitHub pool part.")
            _merge(pool, name, asset_row(name, part["size"], part["sha256"]))
    for kind in rm.HELPER_KINDS:
        row = release_value.get(kind)
        problem = rm.helper_row_problem(row, kind, platform)
        if problem:
            raise ValueError(f"The {platform} {kind} row is not a legacy helper download ({problem}).")
        name = row["url"].rsplit("/", 1)[1]
        _merge(pool, name, asset_row(name, row["size"], row["sha256"]))
    return pool, hosted


def check_e2e(directory: Path, release_value: dict) -> dict:
    """The e2e receipt of the shipped combination: every required step passed (setup.exe may skip for disk)."""
    import desktop_r2 as r2
    import desktop_release_ci as ci
    platform = release_value["platform"]
    path = Path(directory) / "e2e.json"
    record = _record(path)
    if (not isinstance(record, dict) or record.get("kind") != ci.E2E_KIND or record.get("schema") != 1
            or record.get("platform") != platform or record.get("commit") != release_value["commit"]
            or record.get("version") != release_value["version"] or type(record.get("steps")) is not list):
        raise ValueError(f"The {platform} e2e receipt is not this release's.")
    steps = {}
    for step in record["steps"]:
        name = step.get("step") if isinstance(step, dict) else None
        if type(name) is not str or name in steps:
            raise ValueError(f"The {platform} e2e receipt repeats or omits a step name.")
        steps[name] = step
    setup = "not-run"
    for name in (*E2E_STEPS, *E2E_PLATFORM_STEPS[platform]):
        step = steps.get(name)
        if name == "setup-exe" and step is not None and step.get("ok") is None and step.get("skipped") == "disk":
            setup = "skipped-disk"
            continue
        if step is None or step.get("ok") is not True:
            raise ValueError(f"The {platform} e2e step {name} did not pass.")
        if name == "setup-exe":
            setup = "passed"
    if any(step.get("ok") is not True for name, step in steps.items() if name != "setup-exe"):
        raise ValueError(f"A {platform} e2e step did not pass.")
    runtime = steps["startup-human-testing"].get("runtime")
    if not isinstance(runtime, dict) or runtime.get("native_available") is not True or runtime.get("mode") != "rust":
        raise ValueError(f"The {platform} opt-in profile did not run the CI-built native runtime.")
    return {"receipt_sha256": r2.sha256_hex(path.read_bytes()), "steps": len(steps), "setup_exe": setup,
            "seconds": record.get("seconds") if type(record.get("seconds")) in (int, float) else None}


def pool_release_ids(rows: dict) -> dict:
    """{storage tag: release id} of the pools that hold `rows`, each a valid project prerelease."""
    needed = {shared.storage_tag(name) for name in rows}
    found = {}
    for item in release.github_releases():
        tag = item.get("tag_name")
        if tag in needed:
            if tag in found:
                raise ValueError("Two shared storage releases use one tag.")
            found[tag] = shared.validate_release(item, tag)["id"]
    if set(found) != needed:
        raise ValueError("Shared storage is missing a required destination.")
    return found


def r2_notes(sha: str, versions: dict, sources: dict, helpers: dict, *, r2_sums: bool) -> str:
    """`r2_sums`: this release carries R2-SHA256SUMS (R2 content, or only the schema-3 manifest copies)."""
    import desktop_r2 as r2
    windows, linux = versions["windows"], versions["linux"]
    hosted = [platform.title() for platform in PLATFORMS if sources[platform] == "r2"]
    origin = (f"{' and '.join(hosted)} game content downloads from `{r2.DESKTOP_ASSETS}`. Other"
              if hosted else "Game content")
    text = f'''# Rabbit Lands desktop downloads

Client commit: `{sha}`. Releases keep the latest build and the two before it for rollback.

## Windows x86_64

Download the Windows installer, `{windows}-setup.exe`, from **Assets** below and run it.
Setup downloads and verifies the game files. Installation is per user.

Close Rabbit Lands, then run this setup; it converts your existing folder. If setup
is interrupted or a shortcut says to use the original installer, run this setup again.

## Linux x86_64

Download the Linux helper, `{linux}-download.sh`, from **Assets** below and run:

```sh
sh ./{linux}-download.sh
~/Games/RabbitLands/RabbitLands-updater.x86_64
```

The helper needs `curl` and `sha256sum`. It verifies the native updater, which
downloads the required game packages. Pass another parent folder as its first
argument.

If the helper says `Use its original installer`, that folder comes from a release
before the signing key change. Run that game's old uninstaller first, or pass another
parent folder to the helper, and expect a full download.

## Downloads and verification

{origin} packages, the engine, the native runtime and the updater download from
this project's shared GitHub downloads. The updater checks every file against the signed platform
manifest before it is used, downloads only changed packages, and verifies and
replaces its own executable when needed. `SHA256SUMS` lists this release's GitHub
files{" and `R2-SHA256SUMS` its R2 objects" if r2_sums else ""}. Neither platform
needs Python or the Godot editor. Run the installed `RabbitLands-uninstall`
executable (or Windows Installed apps) to remove the game; player settings are kept.
See [installation instructions](https://github.com/{release.REPOSITORY}/wiki/Access-and-Installation).

## Standalone helpers

These stop with `Use its original installer` on a folder from before the signing key
change. On Windows, run setup instead. On Linux, follow the steps above.
'''
    for platform, names in helpers.items():
        text += "\n" + platform.title() + ": " + ", ".join(
            f"[{kind}]({shared.base(release.REPOSITORY)}/{name})" for kind, name in names.items()) + ".\n"
    return text


def setup_row(folder: Path, name: str) -> dict:
    """The asset row of the Windows installers artifact's only file, `name` (setup.exe)."""
    files = sorted(path.name for path in folder.iterdir()) if folder.is_dir() and not folder.is_symlink() else []
    setup = folder / name
    if files != [name] or setup.is_symlink() or not setup.is_file():
        raise ValueError("The Windows installers artifact must hold exactly this release's setup.exe.")
    return asset_row(name, setup.stat().st_size, release.client_release.digest(setup))


def finalize_r2(*, commit: str, release_id: int, envelopes: Path, content: dict, e2e: dict, out: Path,
                installers: dict, public_pem: bytes | None = None) -> str:
    """Verify the R2 workflow's draft against its signed manifests, then write SHA256SUMS,
    R2-SHA256SUMS, notes, client_updates.json and runner-release.json (publish/promote input).

    installers: {"windows": the digest-checked installers-windows artifact folder}. The
    draft's setup.exe must equal its bytes (design Q18); download.sh is rebuilt here."""
    import desktop_r2 as r2
    import linux_download_helper
    import release_manifest as rm
    if type(commit) is not str or not _COMMIT.fullmatch(commit) or type(release_id) is not int or release_id <= 0:
        raise ValueError("Finalization needs the dispatched commit and the draft's release ID.")
    if set(content) != set(PLATFORMS) or set(e2e) != set(PLATFORMS):
        raise ValueError("Provide the content artifact and the e2e receipt of each platform.")
    if not isinstance(installers, dict) or set(installers) != {"windows"}:
        raise ValueError("Provide the Windows installers artifact.")
    out = Path(out)
    if out.exists():
        raise ValueError("The release verification folder must not exist yet.")
    tag = f"client-{commit}"
    public_pem = rm.commit_public_key(release.REPO, commit) if public_pem is None else public_pem
    signed = signed_manifests(envelopes, commit, public_pem)
    rows, pool_rows, hosted, platforms, proofs, qualification, helpers = {}, {}, {}, {}, {}, {}, {}
    for platform, (name, data, value) in signed.items():
        content_set = check_content(content[platform], value)
        proofs[platform] = check_e2e(e2e[platform], value)
        qualification[platform] = content_set.get("qualification")
        pool, objects = manifest_rows(value)
        for key, row in pool.items():
            _merge(pool_rows, key, row)
        for key, row in objects.items():
            _merge(hosted, key, row)
        source, digest = value["content"]["source"], r2.sha256_hex(data)
        if source == "r2":
            set_key = r2.set_key(platform, value["content"]["set"]["sha256"])
            set_bytes = (Path(content[platform]) / "set.json").stat().st_size
            _merge(hosted, set_key, {"key": set_key, "size": set_bytes, "sha256": value["content"]["set"]["sha256"]})
        if value["schema"] == rm.SCHEMA_CODEC:
            # publish copies this exact envelope to R2 before the pointer that names it
            manifest_key = r2.manifest_key(platform, digest)
            _merge(hosted, manifest_key, {"key": manifest_key, "size": len(data), "sha256": digest})
        for asset in (name, f"RabbitLands-{platform}.json"):
            rows[asset] = asset_row(asset, len(data), digest)
        installer = f"{value['version']}-{INSTALLERS[platform]}"
        if platform == "linux":
            # download.sh is a pure function of the signed updater row and envelope: bind its bytes here
            script = linux_download_helper.bootstrap_script(value["updater"], json.loads(data)).encode("utf-8")
            rows[installer] = asset_row(installer, len(script), r2.sha256_hex(script))
        else:
            # setup.exe is not reproducible here: bind the draft's asset to the bytes of the
            # installers artifact, which the workflow checked against the installers job's digest.
            rows[installer] = setup_row(Path(installers["windows"]), installer)
        helpers[platform] = {kind: value[kind]["url"].rsplit("/", 1)[1] for kind in rm.HELPER_KINDS}
        platforms[platform] = {"version": value["version"], "manifest": name, "manifest_sha256": digest,
                               "manifest_bytes": len(data), "schema": value["schema"], "sequence": value["sequence"],
                               "source": source, "set_sha256": value["content"]["set"]["sha256"],
                               "installer": installer}
    if len(rows) + 4 > shared.ASSET_LIMIT:
        raise ValueError("Too many release assets.")
    authorize()
    if release.gh("api", f"repos/{release.REPOSITORY}/commits/{commit}", "--jq", ".sha") != commit:
        raise ValueError("Runner source commit is not public.")
    draft = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{release_id}"))
    if (not draft.get("draft") or draft.get("tag_name") != tag
            or draft.get("author", {}).get("login") not in AUTHORS):
        raise ValueError("Finalization requires this commit's draft of the project's account or this workflow.")
    others = sorted(item["tag_name"] for item in release.github_releases()
                    if item.get("draft") and item["id"] != release_id
                    and shared.CLIENT_TAG.fullmatch(str(item.get("tag_name", ""))))
    if others:
        raise ValueError(f"Another client draft exists ({others[0]}); finalization removes no other release.")
    check_tag(tag, commit)
    remote = {asset["name"]: asset for asset in release.github_assets(release_id)}
    if any(not release.asset_matches(remote.get(name, {}), row) for name, row in rows.items()):
        raise ValueError("A draft download is missing or failed checksum verification; keeping previous files.")
    pool_ids = pool_release_ids(pool_rows)
    shared.verify_storage(pool_rows, pool_ids)
    out.mkdir(parents=True, exist_ok=False)
    if hosted:
        r2_sums = out / shared.R2_SUMS
        r2_sums.write_text("".join(f"{row['sha256']}  {key}\n" for key, row in sorted(hosted.items())),
                           encoding="ascii", newline="\n")
        if shared.r2_checksum_inventory(r2_sums.read_text(encoding="ascii")) != {
                key: row["sha256"] for key, row in hosted.items()}:
            raise ValueError("The R2 checksum inventory does not round-trip.")
        row = asset_row(r2_sums.name, r2_sums.stat().st_size, release.client_release.digest(r2_sums))
        release.upload_asset(tag, release_id, r2_sums, row, remote.get(r2_sums.name, {}))
        rows[r2_sums.name] = row
    sums = out / "SHA256SUMS"
    sums.write_text("".join(f"{row['sha256']}  {name}\n" for name, row in sorted((rows | pool_rows).items())),
                    encoding="ascii", newline="\n")
    row = asset_row(sums.name, sums.stat().st_size, release.client_release.digest(sums))
    release.upload_asset(tag, release_id, sums, row, remote.get(sums.name, {}))
    rows[sums.name] = row
    # Re-read after the checksum uploads; only then retag the draft and remove stale files.
    actual = release.github_assets(release_id)
    remote = {asset["name"]: asset for asset in actual}
    if any(not release.asset_matches(remote.get(name, {}), row) for name, row in rows.items()):
        raise ValueError("Final checksum verification failed; keeping previous files.")
    shared.verify_storage(pool_rows, pool_ids)
    notes = out / "RELEASE-NOTES.md"
    notes.write_text(r2_notes(commit, {p: v["version"] for p, v in platforms.items()},
                              {p: v["source"] for p, v in platforms.items()}, helpers, r2_sums=bool(hosted)),
                     encoding="utf-8", newline="\n")
    release.gh("release", "edit", tag, "--repo", release.REPOSITORY, "--draft", "--tag", tag, "--target", commit,
               "--title", f"Rabbit Lands {commit[:9]}", "--notes-file", str(notes))
    for asset in actual:
        if asset["name"] not in rows:
            release.gh("api", "--method", "DELETE", f"repos/{release.REPOSITORY}/releases/assets/{asset['id']}")
    if {asset["name"] for asset in release.github_assets(release_id)} != set(rows):
        raise ValueError("Previous build cleanup is incomplete; the release remains a draft.")
    base = f"https://github.com/{release.REPOSITORY}/releases/download/{tag}"
    release.write_json(out / "client_updates.json", {
        "schema": 1, "required_commit": commit, "enforce": True,
        "manifests": {platform: f"{base}/{item['manifest']}" for platform, item in platforms.items()}})
    receipt = {"kind": R2_RECEIPT_KIND, "schema": R2_RECEIPT_SCHEMA, "repository": release.REPOSITORY,
               "commit": commit, "release_id": release_id, "tag": tag,
               "assets": [rows[name] for name in sorted(rows)],
               "shared_assets": [pool_rows[name] for name in sorted(pool_rows)],
               "shared_release_ids": pool_ids, "pointers": {p: r2.pointer_asset_name(p) for p in PLATFORMS},
               "platforms": platforms, "r2_objects": len(hosted), "e2e": proofs, "qualification": qualification}
    release.write_json(out / "runner-release.json", receipt)
    url = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{release_id}"))["html_url"]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(f"\nDraft `{tag}` verified: {len(rows)} release files, {len(pool_rows)} shared downloads, "
                         f"{len(hosted)} R2 objects (`R2-SHA256SUMS`).\n")
            if proofs["windows"]["setup_exe"] != "passed":
                output.write("\nThe Windows setup.exe end-to-end install was skipped for runner disk space: run the "
                             "local pre-promote setup check before approving `desktop-promote`.\n")
    print(f"Draft verified: {url}")
    return url


def load_r2_receipt(path: Path, *, commit: str, release_id: int) -> dict:
    """runner-release.json of finalize_r2 for this commit and draft, strictly checked (publish, promote)."""
    import desktop_r2 as r2
    data = _record(path)
    if (not isinstance(data, dict) or data.get("kind") != R2_RECEIPT_KIND or data.get("schema") != R2_RECEIPT_SCHEMA
            or data.get("repository") != release.REPOSITORY or data.get("commit") != commit
            or type(data.get("release_id")) is not int or data["release_id"] != release_id
            or data.get("tag") != f"client-{commit}"):
        raise ValueError("Publication requires this workflow's verified R2 release receipt.")
    assets, pooled = asset_rows(data.get("assets")), asset_rows(data.get("shared_assets"))
    pool_ids = data.get("shared_release_ids")
    if (not isinstance(pool_ids, dict) or not pool_ids or len(set(pool_ids.values())) != len(pool_ids)
            or any(not shared.STORAGE_TAG.fullmatch(tag) or type(value) is not int or value <= 0
                   for tag, value in pool_ids.items())
            or shared.TAG not in pool_ids):
        raise ValueError("The receipt's shared storage identities are invalid.")
    if (not pooled or any(not shared.is_name(name) or shared.NAME.fullmatch(name)[2] != row["sha256"]
                          or shared.storage_tag(name) not in pool_ids for name, row in pooled.items())):
        raise ValueError("The receipt's shared downloads are invalid.")
    if data.get("pointers") != {p: r2.pointer_asset_name(p) for p in PLATFORMS} or "SHA256SUMS" not in assets \
            or any(shared.is_pointer_name(name) or shared.is_name(name) for name in assets):
        raise ValueError("The receipt's release inventory is invalid.")
    platforms = data.get("platforms")
    if not isinstance(platforms, dict) or set(platforms) != set(PLATFORMS):
        raise ValueError("The receipt does not describe both desktop platforms.")
    for platform, item in platforms.items():
        if not isinstance(item, dict):
            raise ValueError("The receipt does not describe both desktop platforms.")
        version = item.get("version")
        row = {"sha256": item.get("manifest_sha256"), "size": item.get("manifest_bytes")}
        if (type(version) is not str or item.get("manifest") != f"{version}-{platform}.json"
                or not re.fullmatch(rf"RabbitLands-{platform.title()}-[0-9]{{8}}-{commit[:9]}", version)
                or item.get("installer") != f"{version}-{INSTALLERS[platform]}" or item["installer"] not in assets
                or any(name not in assets or {key: assets[name][key] for key in row} != row
                       for name in (item["manifest"], f"RabbitLands-{platform}.json"))
                or not shared.packaged(item.get("schema")) or item.get("source") not in ("r2", "ci")
                or type(item.get("sequence")) is not int):
            raise ValueError(f"The receipt's {platform} release is invalid.")
    return {**data, "assets": assets, "shared_assets": pooled}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--linux", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    finalize([args.windows, args.linux], args.out)
