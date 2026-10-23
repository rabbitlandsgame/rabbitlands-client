"""Keep the latest published compiled client after its replacement is public.

Draft creation/finalization must never take working public downloads offline.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile

import build_release as release
from runner_release import authorize


def prune(tag):
    if not re.fullmatch(r"client-[0-9a-f]{40}", tag):
        raise ValueError("Only generated client releases can be pruned.")
    authorize()
    current = release.github_release(tag)
    if not current or current["draft"] or current["author"]["login"] not in (release.ACCOUNT, "github-actions[bot]"):
        raise ValueError("The replacement must already be a published Rabbit Lands client release.")
    if str(current["id"]) != release.gh("api", f"repos/{release.REPOSITORY}/releases/latest", "--jq", ".id").strip():
        raise ValueError("Only the current latest published release may retire earlier downloads.")
    assets = {item["name"]: item for item in release.github_assets(current["id"])}
    with tempfile.TemporaryDirectory(prefix="rabbitlands-published-check-") as temp:
        release.gh("release", "download", tag, "--repo", release.REPOSITORY,
                   "--pattern", "SHA256SUMS", "--dir", temp)
        sums = Path(temp) / "SHA256SUMS"
        row = {"size": sums.stat().st_size, "sha256": release.client_release.digest(sums)}
        if not release.asset_matches(assets.get("SHA256SUMS", {}), row):
            raise ValueError("The published checksum inventory failed verification.")
        expected = {}
        for line in sums.read_text(encoding="ascii").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
            if not match or match[2] in expected:
                raise ValueError("Invalid published checksum inventory.")
            expected[match[2]] = match[1]
    if set(assets) != set(expected) | {"SHA256SUMS"} or not all(
        assets[name].get("state") == "uploaded" and assets[name].get("digest") == "sha256:" + digest
        for name, digest in expected.items()):
        raise ValueError("Published assets do not match the verified checksum inventory.")
    names = set(expected)
    if not all(any(name.endswith(suffix) for name in names) for suffix in
               ("-setup.exe", "-download.sh", "-windows.json", "-linux.json")) or not any(
                   name.endswith(".update.zip.001") or ".pkg.client.zip.001" in name for name in names):
        raise ValueError("The published release is missing a required platform download.")
    removed = []
    for other in release.github_releases():
        if (other["id"] != current["id"] and not other["draft"]
                and re.fullmatch(r"client-[0-9a-f]{40}", other["tag_name"])
                and other.get("published_at", "") < current["published_at"]):
            release.gh("release", "delete", other["tag_name"], "--repo", release.REPOSITORY, "--yes")
            removed.append(other["tag_name"])
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    try:
        print("Retired published builds:", prune(parser.parse_args().tag))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Published release cleanup stopped: {error}\n")
