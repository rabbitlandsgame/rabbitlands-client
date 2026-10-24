"""Publish only the exact desktop release verified by this workflow, then prune.

Separate from finalization so a failed publication/cleanup job can be retried
without rebuilding either platform or attempting to finalize a public release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import time

import actions_release
import build_release as release
import package_client as package
import prune_published_release
import shared_release_assets as shared


def rows(items):
    result = {}
    for row in items:
        if (set(row) != {"name", "size", "sha256"}
                or not re.fullmatch(r"[A-Za-z0-9_.-]+", row["name"])
                or type(row["size"]) is not int or not 0 < row["size"] < release.ASSET_LIMIT
                or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
                or row["name"] in result):
            raise ValueError("Invalid verified release inventory.")
        result[row["name"]] = row
    return result


def publish(receipt: Path) -> str:
    sha = actions_release.workflow_commit()
    data = json.loads(receipt.read_text())
    if (data.get("schema") != 1 or data.get("repository") != release.REPOSITORY
            or data.get("commit") != sha or type(data.get("release_id")) is not int
            or data["release_id"] <= 0):
        raise ValueError("Publication requires this workflow's verified release receipt.")
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
        remote = {r["name"]: r for r in release.github_assets(pool["id"])}
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    try:
        publish(parser.parse_args().receipt)
    except (OSError, ValueError, package.PackageError) as error:
        parser.exit(1, f"Release publication stopped: {error}\n")
