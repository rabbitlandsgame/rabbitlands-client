"""Materialize immutable runner inputs without retaining a second Git blob cache."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.request import urlopen

ROOTS = ("godot-client", "eloria-assets/maps", "eloria-assets/concepts",
         "eloria-assets/fonts", "eloria-assets/tools")
PARENTS = {PurePosixPath(root).parent.as_posix() for root in ROOTS}
BATCH_BYTES = 128 * 1024**2


def selected(path):
    # Match the former cone checkout, including files immediately in its parents.
    return (PurePosixPath(path).parent.as_posix() in PARENTS
            or any(path.startswith(root + "/") for root in ROOTS))


def materialize(build_dir: Path, sha: str, git, storage) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Runner source requires a full commit ID.")
    root = build_dir.resolve()
    expected = {}
    # Do not request ls-tree --long: determining missing blob sizes hydrates the
    # very object cache this streaming checkout avoids.
    for row in git("ls-tree", "-r", "-z", sha, cwd=root).split("\0"):
        if not row:
            continue
        meta, path = row.split("\t", 1)
        if selected(path):
            mode, kind, digest = meta.split()
            if kind != "blob" or mode not in ("100644", "100755"):
                raise ValueError(f"Runner source must be a regular committed file: {path}")
            expected[path] = (mode, digest)
    if not expected:
        raise ValueError("The selected commit has no runner source files.")
    # Populate only the index. Full tracked-path and ancestry checks continue to
    # work, while no runtime blobs are fetched into the shared object store.
    git("read-tree", sha, cwd=root)
    storage.check("before source archive")
    seen, prefix, allowance = set(), None, 0
    url = f"https://codeload.github.com/rabbitlandsgame/rabbitlands-client/tar.gz/{sha}"
    try:
        with urlopen(url, timeout=60) as response:
            with tarfile.open(fileobj=response, mode="r|gz") as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                        raise ValueError("Source archive contains an unsafe path.")
                    if not path.parts:
                        continue
                    prefix = prefix or path.parts[0]
                    if path.parts[0] != prefix:
                        raise ValueError("Source archive has inconsistent roots.")
                    relative = PurePosixPath(*path.parts[1:]).as_posix()
                    if member.isdir() or relative not in expected:
                        continue
                    if relative in seen or not member.isfile():
                        raise ValueError(f"Invalid or duplicated source entry: {relative}")
                    target = root / relative
                    if not target.resolve().is_relative_to(root) or target.exists():
                        raise ValueError(f"Source archive would overwrite an existing path: {relative}")
                    if member.size > allowance:
                        allowance = max(BATCH_BYTES, member.size)
                        storage.check("source archive batch", allowance)
                    storage.budget.free_check(member.size)
                    mode, digest = expected[relative]
                    hasher = hashlib.sha1(f"blob {member.size}\0".encode("ascii"))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with archive.extractfile(member) as source, target.open("xb") as output:
                            while chunk := source.read(1024**2):
                                hasher.update(chunk)
                                output.write(chunk)
                        if hasher.hexdigest() != digest:
                            raise ValueError(f"Source archive differs from the committed Git blob: {relative}")
                    except BaseException:
                        target.unlink(missing_ok=True)
                        raise
                    os.chmod(target, 0o755 if mode == "100755" else 0o644)
                    seen.add(relative)
                    allowance -= member.size
    except (OSError, tarfile.TarError) as error:
        raise ValueError(f"Could not stream the committed runner source: {error}") from error
    missing = expected.keys() - seen
    if missing:
        raise ValueError("Source archive omitted committed inputs: " + ", ".join(sorted(missing)[:5]))
    storage.check("source archive verified")
