"""Retire published client releases outside the retained set, after the latest one is verified.

Retention schema 2 (R2 delivery, design 6.4) keeps whole releases for rollback:

- the current latest release;
- every published release newer than it (a release published as not latest
  that waits for promote, or one that was rolled back from) and every release
  whose publication time cannot be read;
- the KEEP_PREVIOUS releases published before it;
- the pinned last GitHub-hosted release (PINNED_GITHUB_HOSTED, set at the first
  R2 content release).

It deletes only published `client-<sha>` releases outside that set, then only
those shared pool downloads that no retained release's SHA256SUMS lists:
packages, parts and the updater/uninstall helpers of every retained release stay.
Drafts and the pools themselves are never deleted, and R2 is never touched (no
credential, no R2 call). Draft creation/finalization must never take working
public downloads offline.
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path
import tempfile

import build_release as release
import shared_release_assets as shared
from runner_release import authorize

# actions_release.retention_guard refuses an R2 release whose commit has less (MIN_RETENTION_SCHEMA).
RETENTION_SCHEMA = 2
KEEP_PREVIOUS = 2
# "client-<sha>" of the last GitHub-hosted release, kept while R2 releases follow it.
# Set it in the first R2 content release (R1); None keeps only latest and its neighbours.
PINNED_GITHUB_HOSTED = None
_MODULE_PIN = object()  # retention() reads PINNED_GITHUB_HOSTED when it runs, not when it was defined


def _published_at(item: dict):
    value = item.get("published_at")
    if type(value) is not str:
        return None
    try:
        when = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo is not None else None


def retention(releases: list[dict], latest: dict, *, keep_previous: int | None = None,
              pinned=_MODULE_PIN) -> tuple[list[dict], list[dict]]:
    """(retained, retired) published client releases around `latest`; drafts are in neither."""
    keep_previous = KEEP_PREVIOUS if keep_previous is None else keep_previous
    pinned = PINNED_GITHUB_HOSTED if pinned is _MODULE_PIN else pinned
    if type(keep_previous) is not int or keep_previous < 0:
        raise ValueError("Invalid number of previous releases to keep.")
    if pinned is not None and (type(pinned) is not str or not shared.CLIENT_TAG.fullmatch(pinned)):
        raise ValueError("The pinned GitHub-hosted release must be a client-<commit> tag.")
    published = [item for item in releases
                 if shared.CLIENT_TAG.fullmatch(str(item.get("tag_name", ""))) and not item.get("draft")]
    ids = [item["id"] for item in published]
    if len(set(ids)) != len(ids):
        raise ValueError("The release listing names one release twice; nothing was deleted.")
    if latest.get("id") not in ids:
        raise ValueError("The latest release is not among the published client releases; nothing was deleted.")
    anchor = _published_at(latest)
    if anchor is None:
        raise ValueError("The latest release has no readable publication time; nothing was deleted.")
    retained, older = [], []
    for item in published:
        when = _published_at(item)
        if item["id"] == latest["id"] or when is None or when >= anchor:
            retained.append(item)
        else:
            older.append((when, item))
    older.sort(key=lambda pair: pair[0], reverse=True)
    retained.extend(item for _, item in older[:keep_previous])
    retired = [item for _, item in older[keep_previous:]]
    if pinned is not None:
        if not any(item["tag_name"] == pinned for item in published):
            raise ValueError(f"The pinned last GitHub-hosted release {pinned} is not published; nothing was deleted.")
        retained.extend(item for item in retired if item["tag_name"] == pinned)
        retired = [item for item in retired if item["tag_name"] != pinned]
    return retained, retired


def inventory(item: dict, assets: dict) -> dict:
    """The verified SHA256SUMS of a published release: {name: sha256}."""
    entry = assets.get("SHA256SUMS")
    if not entry or entry.get("state") != "uploaded":
        raise ValueError(f"{item['tag_name']} has no checksum inventory; nothing was deleted.")
    with tempfile.TemporaryDirectory(prefix="rabbitlands-published-check-") as temp:
        release.gh("release", "download", item["tag_name"], "--repo", release.REPOSITORY,
                   "--pattern", "SHA256SUMS", "--dir", temp)
        sums = Path(temp) / "SHA256SUMS"
        row = {"size": sums.stat().st_size, "sha256": release.client_release.digest(sums)}
        if not release.asset_matches(entry, row):
            raise ValueError(f"The published checksum inventory of {item['tag_name']} failed verification.")
        return shared.checksum_inventory(sums.read_text(encoding="ascii"))


def prune(tag):
    if not shared.CLIENT_TAG.fullmatch(str(tag)):
        raise ValueError("Only generated client releases can be pruned.")
    authorize()
    current = release.github_release(tag)
    if not current or current["draft"] or current["author"]["login"] not in (release.ACCOUNT, "github-actions[bot]"):
        raise ValueError("The replacement must already be a published Rabbit Lands client release.")
    if str(current["id"]) != release.gh("api", f"repos/{release.REPOSITORY}/releases/latest", "--jq", ".id").strip():
        raise ValueError("Only the current latest published release may retire earlier downloads.")
    assets = {item["name"]: item for item in release.github_assets(current["id"])}
    expected = inventory(current, assets)
    pooled = []
    if any(shared.is_name(name) for name in expected):
        pooled = shared.published_inventory()
    shared.verify_inventory(expected, list(assets.values()), pooled)
    names = set(expected)
    if not all(any(name.endswith(suffix) for name in names) for suffix in
               ("-setup.exe", "-download.sh", "-windows.json", "-linux.json")) or not any(
                   name.endswith(".update.zip.001") or ".pkg.client.zip.001" in name or (shared.is_name(name) and shared.NAME.fullmatch(name)[1] == "pkg") for name in names):
        raise ValueError("The published release is missing a required platform download.")
    retained, retired = retention(release.github_releases(), current)
    # Every retained release keeps its own pool downloads, its helpers included.
    # One unreadable inventory stops the whole prune before anything is deleted.
    referenced = {name: digest for name, digest in expected.items() if shared.is_name(name)}
    for item in retained:
        if item["id"] != current["id"]:
            other = {asset["name"]: asset for asset in release.github_assets(item["id"])}
            referenced.update((name, digest) for name, digest in inventory(item, other).items()
                              if shared.is_name(name))
    removed = []
    for item in retired:
        release.gh("release", "delete", item["tag_name"], "--repo", release.REPOSITORY, "--yes")
        removed.append(item["tag_name"])
    shared.collect_unused(release.github_releases(), {item["id"] for item in retained}, referenced)
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    try:
        print("Retired published builds:", prune(parser.parse_args().tag))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Published release cleanup stopped: {error}\n")
