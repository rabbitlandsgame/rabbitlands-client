"""Immutable downloads shared by the current client release and its next draft."""
from __future__ import annotations

import re
import time

TAG = "client-assets"
NAME = re.compile(r"RabbitLands-(pkg|updater|uninstall)-([0-9a-f]{64})\.(zip\.part|exe|x86_64)")


def name(sha256: str, kind="pkg", extension="zip.part") -> str:
    result = f"RabbitLands-{kind}-{sha256}.{extension}"
    if not NAME.fullmatch(result) or (kind == "pkg") != (extension == "zip.part"):
        raise ValueError("Invalid shared download identity.")
    return result


def is_name(value: str) -> bool:
    match = NAME.fullmatch(value)
    return bool(match and (match[1] == "pkg") == (match[3] == "zip.part"))


def base(repository: str) -> str:
    return f"https://github.com/{repository}/releases/download/{TAG}"


def matches(row: dict, repository: str) -> bool:
    filename = str(row.get("url", "")).rsplit("/", 1)[-1]
    match = NAME.fullmatch(filename)
    return bool(is_name(filename) and match[2] == row.get("sha256")
                and row.get("url") == base(repository) + "/" + filename)


def validate_release(item: dict) -> dict:
    import build_release as release
    if (not item or item.get("tag_name") != TAG or item.get("draft")
            or not item.get("prerelease") or item.get("immutable")
            or item.get("author", {}).get("login") not in (release.ACCOUNT, "github-actions[bot]")):
        raise ValueError("Shared downloads require the project's mutable, published prerelease.")
    return item


def ensure(sha: str | None = None) -> dict:
    import build_release as release
    existing = release.github_release(TAG)
    if existing is None and sha is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("Shared downloads require a public client commit.")
        release.gh("release", "create", TAG, "--repo", release.REPOSITORY, "--target", sha,
                   "--prerelease", "--latest=false", "--title", "Rabbit Lands shared downloads",
                   "--notes", "Supporting files used by Rabbit Lands installers. To play, download the installer from the latest game release. This storage release is reused; it does not preserve older game versions.")
        # A newly published release may briefly be absent from the listing.
        # Re-read the same tag without creating another storage destination.
        for delay in (0, 1, 2, 4, 8):
            if delay:
                time.sleep(delay)
            existing = release.github_release(TAG)
            if existing is not None:
                break
    return validate_release(existing)


def checksum_inventory(text: str) -> dict[str, str]:
    expected = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in expected:
            raise ValueError("Invalid published checksum inventory.")
        if is_name(match[2]) and NAME.fullmatch(match[2])[2] != match[1]:
            raise ValueError("A shared download name and checksum disagree.")
        expected[match[2]] = match[1]
    return expected


def receipt_assets(item: dict) -> dict:
    rows = {}
    for row in item.get("shared_assets", []):
        if (set(row) != {"name", "size", "sha256"} or not is_name(row["name"])
                or NAME.fullmatch(row["name"])[2] != row["sha256"]
                or row["name"] in rows or not isinstance(row["size"], int)
                or not 0 < row["size"] <= 512 * 1024**2):
            raise ValueError("Invalid shared runner download.")
        rows[row["name"]] = row
    packages, helpers = item.get("shared_packages"), item.get("shared_helpers")
    if not isinstance(packages, dict) or not {"client", "engine"} <= set(packages) or not isinstance(helpers, dict) or set(helpers) != {"updater", "uninstall"}:
        raise ValueError("A shared receipt is missing required packages or helpers.")
    referenced = set()
    for package, names in packages.items():
        if not re.fullmatch(r"[a-z0-9-]{1,96}", package) or not isinstance(names, list) or not names:
            raise ValueError("Invalid shared package receipt.")
        for filename in names:
            if filename not in rows or NAME.fullmatch(filename)[1] != "pkg" or rows[filename]["size"] > 256 * 1024**2:
                raise ValueError("A shared package part is missing or invalid.")
            referenced.add(filename)
    extension = "exe" if item["platform"] == "windows" else "x86_64"
    for kind, filename in helpers.items():
        if filename not in rows or filename != name(rows[filename]["sha256"], kind, extension):
            raise ValueError("A shared bootstrap is missing or invalid.")
        referenced.add(filename)
    if referenced != set(rows):
        raise ValueError("Unreferenced shared runner download.")
    return rows


def verify_inventory(expected: dict, assets: list[dict], shared: list[dict]) -> None:
    normal = {a["name"]: a for a in assets}
    pooled = {a["name"]: a for a in shared}
    if set(normal) != {n for n in expected if not is_name(n)} | {"SHA256SUMS"}:
        raise ValueError("Published assets do not match the checksum inventory.")
    for filename, digest in expected.items():
        asset = (pooled if is_name(filename) else normal).get(filename, {})
        if asset.get("state") != "uploaded" or asset.get("digest") != "sha256:" + digest:
            raise ValueError("A release download failed checksum verification.")


def collect_unused(entries: list[dict], current_id: int, expected: dict) -> list[str]:
    """Called only after public verification and retirement of older game releases.

    An existing draft may be actively uploading files before its inventory is
    finalized. Keep everything in that case; never race its uploads.
    """
    import build_release as release
    clients = [i for i in entries if re.fullmatch(r"client-[0-9a-f]{40}", i["tag_name"])]
    if any(i.get("draft") or i["id"] != current_id for i in clients):
        return []
    pool = next((i for i in entries if i["tag_name"] == TAG), None)
    if pool is None:
        return []
    validate_release(pool)
    removed = []
    for asset in release.github_assets(pool["id"]):
        if is_name(asset["name"]) and asset["name"] not in expected:
            release.gh("api", "--method", "DELETE", f"repos/{release.REPOSITORY}/releases/assets/{asset['id']}")
            removed.append(asset["name"])
    return removed
