"""Publish only the exact desktop release verified by this workflow.

Separate from finalization so a failed publication/cleanup job can be retried
without rebuilding either platform or attempting to finalize a public release.

`publish` serves desktop-release.yml: it publishes as latest, then prunes.
desktop-release-r2.yml publishes in two steps (design 4.2): `publish_r2` adds
the signed pointers and publishes as **not latest**, so /releases/latest (what
released games read) is unchanged until the R2 pointers are live; `promote_r2`
then checks that both live R2 pointers are byte-equal to this release's pointer
assets, makes it latest and prunes with the retained set. Neither holds an R2
credential or writes to R2; promote only reads the public custom domain.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import time

import actions_release
import build_release as release
import finalize_runner_release as finalizer
import package_client as package
import prune_published_release
import shared_release_assets as shared
from full_optimization_package import validate_proof

rows = finalizer.asset_rows
PLATFORMS = finalizer.PLATFORMS
CONFIRM_DELAYS = (0, 1, 2, 4, 8)
LIVE_DELAYS = (0, 2, 5)


def publish(receipt: Path) -> str:
    sha = actions_release.workflow_commit()
    data = json.loads(receipt.read_text())
    if (data.get("schema") != 1 or "kind" in data or data.get("repository") != release.REPOSITORY
            or data.get("commit") != sha or type(data.get("release_id")) is not int
            or data["release_id"] <= 0):
        raise ValueError("Publication requires this workflow's verified release receipt.")
    if set(data.get("optimizations", {})) != {"windows", "linux"}:
        raise ValueError("Publication requires full optimization proof for both desktop platforms.")
    for platform, proof in data["optimizations"].items():
        validate_proof(proof, sha, platform)
    if len({proof["coverage_sha256"] for proof in data["optimizations"].values()}) != 1 \
            or len({proof["native_source_digest"] for proof in data["optimizations"].values()}) != 1:
        raise ValueError("Platform optimization source/coverage proofs do not match.")
    expected, pooled = rows(data["assets"]), rows(data["shared_assets"])
    required = {"SHA256SUMS", "RabbitLands-windows.json", "RabbitLands-linux.json"}
    for platform, suffixes in (("Windows", ("setup.exe", "windows.json")),
                               ("Linux", ("download.sh", "linux.json"))):
        for suffix in suffixes:
            matches = [n for n in expected if re.fullmatch(
                rf"RabbitLands-{platform}-[0-9]{{8}}-{sha[:9]}-{re.escape(suffix)}", n)]
            if len(matches) != 1:
                raise ValueError("Verified receipt is missing a platform installer or manifest.")
            required.add(matches[0])
    if set(expected) != required or not pooled or any(
            not shared.is_name(n) or shared.NAME.fullmatch(n)[2] != r["sha256"] for n, r in pooled.items()):
        raise ValueError("Verified receipt contains unexpected or missing downloads.")
    pool_id = data.get("shared_release_id")
    if type(pool_id) is not int or pool_id <= 0 or pool_id == data["release_id"]:
        raise ValueError("Verified receipt is missing its shared download release.")
    actions_release.runner_release.authorize()
    release_id, tag = data["release_id"], f"client-{sha}"
    endpoint = f"repos/{release.REPOSITORY}/releases/{release_id}"
    current = json.loads(release.gh("api", endpoint))
    if (current.get("tag_name") != tag or current.get("target_commitish") != sha
            or current.get("author", {}).get("login") not in (release.ACCOUNT, "github-actions[bot]")):
        raise ValueError("The verified release tag, source or owner changed before publication.")
    # A manually selected older branch must not replace a newer working build.
    latest = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/latest"))
    if current["draft"]:
        old = re.fullmatch(r"client-([0-9a-f]{40})", latest.get("tag_name", ""))
        if old and old[1] not in package.git("rev-list", sha).splitlines():
            raise ValueError("Select a source commit containing the current published client before publishing automatically.")
    elif latest.get("id") != release_id:
        raise ValueError("A different release is now latest; refusing to replace it on a retry.")
    refs = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/matching-refs/tags/{tag}"))
    for ref in refs:
        if ref["ref"] == "refs/tags/" + tag:
            obj = ref["object"]
            for _ in range(16):
                if obj["type"] != "tag":
                    break
                obj = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/tags/{obj['sha']}"))["object"]
            if obj["type"] != "commit" or obj["sha"] != sha:
                raise ValueError("The release tag no longer points to the verified client commit.")

    def verify_downloads():
        actual = {r["name"]: r for r in release.github_assets(release_id)}
        if set(actual) != set(expected) or any(not release.asset_matches(actual[n], r) for n, r in expected.items()):
            raise ValueError("Installer release checksum verification failed; keeping earlier published downloads.")
        pool = shared.validate_release(json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{pool_id}")))
        remote = shared.verify_storage(pooled, data["shared_release_ids"]) if "shared_release_ids" in data else {r["name"]: r for r in release.github_assets(pool["id"])}
        if "shared_release_ids" in data and data["shared_release_ids"].get(shared.TAG) != pool_id:
            raise ValueError("Legacy helper storage identity changed.")
        if any(not release.asset_matches(remote.get(n, {}), r) for n, r in pooled.items()):
            raise ValueError("Shared download checksum verification failed; keeping earlier published downloads.")

    verify_downloads()
    if current["draft"]:
        release.gh("release", "edit", tag, "--repo", release.REPOSITORY, "--draft=false", "--prerelease=false", "--latest")
    # Publishing can precede latest-release metadata becoming visible briefly.
    for delay in (0, 1, 2, 4, 8):
        if delay:
            time.sleep(delay)
        current = json.loads(release.gh("api", endpoint))
        latest = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/latest"))
        if (not current.get("draft") and not current.get("prerelease")
                and current.get("tag_name") == tag and latest.get("id") == release_id):
            break
    else:
        raise ValueError("Could not confirm the verified release is public and latest. Previous releases were kept; rerun this publish job.")
    url = f"https://github.com/{release.REPOSITORY}/releases/tag/{tag}"
    try:
        verify_downloads()
    except ValueError as error:
        raise ValueError(f"{url} is published, but public download verification failed. Previous releases were kept. {error}") from error
    print(f"Published and verified: {url}", flush=True)
    # GITHUB_TOKEN publications do not trigger release-event workflows. Invoke
    # the same verified cleanup here, inside the release concurrency group.
    try:
        removed = prune_published_release.prune(tag)
    except (OSError, ValueError) as error:
        raise ValueError(f"{url} is published; previous-release cleanup failed. Rerun this publish job. {error}") from error
    print(f"Retired {len(removed)} previous published client release(s).", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(f"\nPublished [Rabbit Lands {sha[:9]}]({url}) after both platforms and all downloads passed verification. "
                         f"Retired {len(removed)} previous compiled release(s).\n")
    return url


# --- desktop-release-r2.yml: publish (not latest) and promote (R2-A7) ---------------------------

def commit_public_key(commit: str) -> bytes:
    import release_manifest as rm
    return rm.commit_public_key(package.REPO, commit)


def check_pointer(data: bytes, *, platform: str, commit: str, release_id: int, item: dict,
                  public_pem: bytes) -> dict:
    """A canonical forward pointer of this draft naming its verified manifest; returns its asset row."""
    import desktop_r2 as r2
    import release_manifest as rm
    signed, value = rm.verify(data, public_pem, limit=r2.MAX_POINTER_BYTES)
    r2.validate_pointer(value, platform=platform)
    target = value["target"]
    if (r2.pointer_bytes(value, platform=platform) != signed or value["rollback"] is not False
            or value["release_id"] != release_id or target["commit"] != commit
            or target["version"] != item["version"] or target["manifest_sequence"] != item["sequence"]
            or target["manifest"]["sha256"] != item["manifest_sha256"]
            or target["manifest"]["size"] != item["manifest_bytes"]):
        raise ValueError(f"The {platform} pointer is not a forward pointer of this release to its signed manifest.")
    return finalizer.asset_row(r2.pointer_asset_name(platform), len(data), r2.sha256_hex(data))


def _r2_receipt(receipt: Path, commit: str, release_id: int) -> dict:
    data = finalizer.load_r2_receipt(receipt, commit=commit, release_id=release_id)
    if any(item["schema"] != 3 for item in data["platforms"].values()):
        raise ValueError("Signed R2 pointers name schema-3 manifests only.")
    return data


def _release_record(release_id: int) -> dict:
    return json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{release_id}"))


def _latest() -> dict:
    return json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/latest"))


def _check_identity(current: dict, tag: str, commit: str) -> None:
    if (current.get("tag_name") != tag or current.get("target_commitish") != commit
            or current.get("author", {}).get("login") not in finalizer.AUTHORS):
        raise ValueError("The verified release tag, source or owner changed before publication.")


def _latest_is_ancestor(latest: dict, commit: str) -> None:
    # A manually selected older branch must not replace a newer working build.
    old = re.fullmatch(r"client-([0-9a-f]{40})", latest.get("tag_name", ""))
    if old and old[1] not in package.git("rev-list", commit).splitlines():
        raise ValueError("Select a source commit containing the current published client.")


def _verify_r2_downloads(data: dict, release_id: int, pointer_rows: dict | None = None) -> dict:
    """The release holds exactly its verified files (plus, when given, these exact pointers); pools verified."""
    expected, pointers = data["assets"], set(data["pointers"].values())
    actual = {asset["name"]: asset for asset in release.github_assets(release_id)}
    extra = set(actual) - set(expected)
    if not set(expected) <= set(actual) or not extra <= pointers or (pointer_rows is not None and extra != pointers):
        raise ValueError("The release inventory differs from the verified receipt; keeping earlier published "
                         "downloads.")
    checked = [*expected.items(), *(pointer_rows or {}).items()]
    if any(not release.asset_matches(actual[name], row) for name, row in checked):
        raise ValueError("Release checksum verification failed; keeping earlier published downloads.")
    shared.verify_storage(data["shared_assets"], data["shared_release_ids"])  # raises on any mismatch
    return actual


def _step_summary(text: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(text)


def publish_r2(*, commit: str, release_id: int, receipt: Path, pointers: Path,
               public_pem: bytes | None = None) -> str:
    """Upload this run's signed pointers, then publish the verified draft as not latest.

    /releases/latest (what released games read) must still name the previous
    release afterwards. Re-running replaces this release's own pointers (for
    example after a stale pointer: the job re-signs with a higher sequence).
    """
    import desktop_r2 as r2
    data = _r2_receipt(receipt, commit, release_id)
    public_pem = commit_public_key(commit) if public_pem is None else public_pem
    folder, names = Path(pointers), data["pointers"]
    if sorted(path.name for path in folder.iterdir()) != sorted(names.values()):
        raise ValueError("The pointer folder must hold exactly the two platform pointers.")
    files, pointer_rows = {}, {}
    for platform in PLATFORMS:
        path = folder / names[platform]
        if path.is_symlink() or not path.is_file() or path.stat().st_size > r2.MAX_POINTER_BYTES:
            raise ValueError(f"The {platform} pointer is not a small regular file.")
        files[platform] = path
        pointer_rows[names[platform]] = check_pointer(path.read_bytes(), platform=platform, commit=commit,
                                                      release_id=release_id, item=data["platforms"][platform],
                                                      public_pem=public_pem)
    actions_release.runner_release.authorize()
    tag = data["tag"]
    current = _release_record(release_id)
    _check_identity(current, tag, commit)
    finalizer.check_tag(tag, commit)
    latest = _latest()
    if latest.get("id") == release_id:
        raise ValueError("This release is already GitHub latest; publish never changes a promoted release.")
    if current.get("draft"):
        _latest_is_ancestor(latest, commit)
    elif current.get("prerelease"):
        raise ValueError("The release was changed to a prerelease after publication; refusing to continue.")
    previous = latest.get("id")
    actual = _verify_r2_downloads(data, release_id)
    for platform in PLATFORMS:
        name = names[platform]
        release.upload_asset(tag, release_id, files[platform], pointer_rows[name], actual.get(name, {}))
    _verify_r2_downloads(data, release_id, pointer_rows)
    if current.get("draft"):
        release.gh("release", "edit", tag, "--repo", release.REPOSITORY, "--draft=false", "--prerelease=false",
                   "--latest=false")
    for delay in CONFIRM_DELAYS:
        if delay:
            time.sleep(delay)
        current = _release_record(release_id)
        if not current.get("draft") and not current.get("prerelease") and current.get("tag_name") == tag:
            break
    else:
        raise ValueError("Could not confirm the verified release is public. Rerun this publish job.")
    url = f"https://github.com/{release.REPOSITORY}/releases/tag/{tag}"
    latest = _latest()
    if latest.get("id") != previous:
        raise ValueError(f"{url} is published, but GitHub latest changed during publication (it must stay "
                         f"{previous} until promote). Mark the previous release latest again "
                         "(gh release edit <tag> --latest) before anything else.")
    try:
        _verify_r2_downloads(data, release_id, pointer_rows)
    except ValueError as error:
        raise ValueError(f"{url} is published (not latest), but download verification failed. {error}") from error
    print(f"Published (not latest) and verified: {url}", flush=True)
    _step_summary(f"\nPublished [Rabbit Lands {commit[:9]}]({url}) as **not latest** with signed pointers; GitHub "
                  "latest is unchanged.\n")
    return url


def _live(http, url: str, limit: int) -> bytes:
    """An anonymous GET through the custom domain (what players read); retried on transport errors and 5xx."""
    import upload_desktop_assets as up
    failure = "no response"
    for delay in LIVE_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            response = http.request("GET", url, limit=limit, headers=up.UPDATER_HEADERS)
        except up.UploadError as error:
            failure = error.code
            continue
        if response.status == 200:
            return response.body
        failure = f"HTTP {response.status}"
        if response.status < 500:
            break
    raise ValueError(f"{url} is not readable anonymously ({failure}).")


def promote_r2(*, commit: str, release_id: int, receipt: Path, public_pem: bytes | None = None,
               http=None) -> str:
    """GitHub latest only after both live R2 pointers are byte-equal to this release's pointer assets
    and the R2 manifest copies they name are live; then prune with the retained set."""
    import desktop_r2 as r2
    import upload_desktop_assets as up
    data = _r2_receipt(receipt, commit, release_id)
    public_pem = commit_public_key(commit) if public_pem is None else public_pem
    http = up.Http() if http is None else http
    actions_release.runner_release.authorize()
    tag = data["tag"]
    current = _release_record(release_id)
    _check_identity(current, tag, commit)
    if current.get("draft") or current.get("prerelease"):
        raise ValueError("Promote needs the release the publish job published (not a draft or prerelease).")
    finalizer.check_tag(tag, commit)
    actual = _verify_r2_downloads(data, release_id)
    pointer_rows = {}
    with tempfile.TemporaryDirectory(prefix="rabbitlands-pointers-") as temp:
        for platform in PLATFORMS:
            name, item = data["pointers"][platform], data["platforms"][platform]
            if name not in actual:
                raise ValueError(f"The release has no {platform} pointer; rerun the publish job.")
            release.gh("release", "download", tag, "--repo", release.REPOSITORY, "--pattern", name, "--dir", temp)
            path = Path(temp) / name
            if not path.is_file() or path.stat().st_size > r2.MAX_POINTER_BYTES:
                raise ValueError(f"The {platform} pointer asset could not be read.")
            pointer = path.read_bytes()
            # the asset listing must hold these exact bytes: checked below, before any write
            pointer_rows[name] = check_pointer(pointer, platform=platform, commit=commit, release_id=release_id,
                                               item=item, public_pem=public_pem)
            if _live(http, r2.pointer_url(platform), r2.MAX_POINTER_BYTES) != pointer:
                raise ValueError(f"The live R2 {platform} pointer is not byte-equal to this release's pointer asset. "
                                 f"Run the local publish for {tag} first; GitHub latest is unchanged.")
            manifest = _live(http, r2.manifest_url(platform, item["manifest_sha256"]), item["manifest_bytes"])
            if r2.sha256_hex(manifest) != item["manifest_sha256"]:
                raise ValueError(f"The R2 copy of the {platform} manifest is not the signed manifest.")
    _verify_r2_downloads(data, release_id, pointer_rows)
    latest = _latest()
    url = f"https://github.com/{release.REPOSITORY}/releases/tag/{tag}"
    if latest.get("id") != release_id:
        _latest_is_ancestor(latest, commit)
        release.gh("release", "edit", tag, "--repo", release.REPOSITORY, "--latest")
        for delay in CONFIRM_DELAYS:
            if delay:
                time.sleep(delay)
            if _latest().get("id") == release_id:
                break
        else:
            raise ValueError(f"Could not confirm that {url} is GitHub latest. Nothing was pruned; rerun this "
                             "promote job.")
    print(f"Promoted to GitHub latest: {url}", flush=True)
    try:
        removed = prune_published_release.prune(tag)
    except (OSError, ValueError) as error:
        raise ValueError(f"{url} is GitHub latest; retiring releases outside the retained set failed. Rerun this "
                         f"promote job. {error}") from error
    print(f"Retired {len(removed)} release(s) outside the retained set.", flush=True)
    setup = [p for p in PLATFORMS if data["e2e"].get(p, {}).get("setup_exe") == "skipped-disk"] \
        if isinstance(data.get("e2e"), dict) else []
    _step_summary(f"\nPromoted [Rabbit Lands {commit[:9]}]({url}) to GitHub latest after both live R2 pointers "
                  f"matched its pointer assets. Retired {len(removed)} release(s) outside the retained set.\n"
                  + ("\nReminder: the Windows setup.exe e2e was skipped; the local pre-promote setup check "
                     "must have passed.\n" if setup else ""))
    return url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    try:
        publish(parser.parse_args().receipt)
    except (OSError, ValueError, package.PackageError) as error:
        parser.exit(1, f"Release publication stopped: {error}\n")
