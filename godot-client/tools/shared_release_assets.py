"""Immutable downloads shared by the current client release and its next draft."""
from __future__ import annotations

import re
import time

TAG = "client-assets"
STORAGE_TAG = re.compile(r"client-assets(?:-[0-9a-f])?")
ASSET_LIMIT = 1000
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


def storage_tag(filename: str) -> str:
    """Keep bootstrap helpers at their legacy URLs; spread packages by hash."""
    if not is_name(filename):
        raise ValueError("Invalid shared download identity.")
    identity = NAME.fullmatch(filename)
    return TAG + "-" + identity[2][0] if identity[1] == "pkg" else TAG


def download_url(repository: str, filename: str) -> str:
    return f"https://github.com/{repository}/releases/download/{storage_tag(filename)}/{filename}"


def matches(row: dict, repository: str) -> bool:
    filename = str(row.get("url", "")).rsplit("/", 1)[-1]
    match = NAME.fullmatch(filename)
    return bool(is_name(filename) and match[2] == row.get("sha256")
                and row.get("url") in (base(repository) + "/" + filename, download_url(repository, filename)))


def validate_release(item: dict, tag: str = TAG) -> dict:
    import build_release as release
    if (not STORAGE_TAG.fullmatch(tag) or not item or item.get("tag_name") != tag or item.get("draft")
            or not item.get("prerelease") or item.get("immutable")
            or item.get("author", {}).get("login") not in (release.ACCOUNT, "github-actions[bot]")):
        raise ValueError("Shared downloads require the project's mutable, published prerelease.")
    return item


def ensure(sha: str | None = None, *, tag: str = TAG) -> dict:
    import build_release as release
    if not STORAGE_TAG.fullmatch(tag):
        raise ValueError("Invalid shared storage tag.")
    existing = release.github_release(tag)
    if existing is None and sha is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("Shared downloads require a public client commit.")
        release.gh("release", "create", tag, "--repo", release.REPOSITORY, "--target", sha,
                   "--prerelease", "--latest=false", "--title", "Rabbit Lands shared downloads",
                   "--notes", "Supporting files used by Rabbit Lands installers. To play, download the installer from the latest game release. This storage release is reused; it does not preserve older game versions.")
        # A newly published release may briefly be absent from the listing.
        # Re-read the same tag without creating another storage destination.
        for delay in (0, 1, 2, 4, 8):
            if delay:
                time.sleep(delay)
            existing = release.github_release(tag)
            if existing is not None:
                break
    return validate_release(existing, tag)


def verify_storage(rows: dict, release_ids: dict) -> dict:
    """Verify each immutable download at its declared deterministic destination.

    Pool IDs in a runner receipt are untrusted. Resolve their tags and owners,
    reject duplicate IDs, enforce capacity per pool, then check actual bytes.
    Never satisfy a missing shard download with a legacy duplicate elsewhere.
    """
    import json
    import build_release as release
    if (not isinstance(release_ids, dict) or not release_ids
            or any(not STORAGE_TAG.fullmatch(tag) or type(value) is not int or value <= 0
                   for tag, value in release_ids.items())
            or len(set(release_ids.values())) != len(release_ids)):
        raise ValueError("Invalid shared storage release identities.")
    grouped = {}
    for filename, row in rows.items():
        tag = storage_tag(filename)
        if tag not in release_ids:
            raise ValueError("Shared storage is missing a required destination.")
        grouped.setdefault(tag, {})[filename] = row
    if any(len(group) > ASSET_LIMIT for group in grouped.values()):
        raise ValueError("Too many assets for a shared storage release.")
    result = {}
    for tag, pool_id in release_ids.items():
        validate_release(json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{pool_id}")), tag)
        actual = {asset["name"]: asset for asset in release.github_assets(pool_id)}
        if len(actual) > ASSET_LIMIT:
            raise ValueError("Shared storage exceeds GitHub's asset limit.")
        for filename, row in grouped.get(tag, {}).items():
            if not release.asset_matches(actual.get(filename, {}), row):
                raise ValueError("A shared download failed destination checksum verification.")
            result[filename] = actual[filename]
    return result


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


class Storage:
    """Lazily load each pool once; never scan all assets per upload."""
    def __init__(self, sha: str):
        self.sha = sha
        self.pools, self.inventories = {}, {}

    @property
    def ids(self):
        return {tag: pool["id"] for tag, pool in self.pools.items()}

    def pool(self, tag=TAG):
        import build_release as release
        if tag not in self.pools:
            self.pools[tag] = ensure(self.sha, tag=tag)
            self.inventories[tag] = {a["name"]: a for a in release.github_assets(self.pools[tag]["id"])}
        return self.pools[tag], self.inventories[tag]

    def destination(self, filename):
        return self.pool(storage_tag(filename))

    def upload(self, path, row):
        import build_release as release
        pool, previous = self.destination(path.name)
        old = previous.get(path.name, {})
        if not old and len(previous) >= ASSET_LIMIT:
            raise ValueError(f"Shared storage {pool['tag_name']} is full; preserve published downloads and reclaim verified unused uploads before retrying.")
        actual = release.upload_asset_api(pool["id"], path, row, old, immutable=True)
        previous[path.name] = actual
        return actual


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
    removed = []
    for pool in entries:
        if not STORAGE_TAG.fullmatch(pool["tag_name"]):
            continue
        validate_release(pool, pool["tag_name"])
        for asset in release.github_assets(pool["id"]):
            if is_name(asset["name"]) and asset["name"] not in expected:
                release.gh("api", "--method", "DELETE", f"repos/{release.REPOSITORY}/releases/assets/{asset['id']}")
                removed.append(asset["name"])
    return removed


def published_inventory():
    """Read legacy and partitioned stores when checking an existing release."""
    import build_release as release
    result = {}
    for pool in release.github_releases():
        if STORAGE_TAG.fullmatch(pool["tag_name"]):
            validate_release(pool, pool["tag_name"])
            for asset in release.github_assets(pool["id"]):
                prior = result.get(asset["name"])
                if prior and (prior.get("digest"), prior.get("size")) != (asset.get("digest"), asset.get("size")):
                    raise ValueError("Conflicting duplicate shared download.")
                result[asset["name"]] = asset
    return list(result.values())
