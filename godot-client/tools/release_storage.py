"""Bounded disk use for disposable release runners (no signing credentials here)."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import shutil
from stat import S_ISDIR, S_ISLNK

RUNNER_BYTES = 14_000_000_000
RESERVE_BYTES = 2_000_000_000
INVENTORY_ATTEMPTS = 8


def unique_bytes(roots: list[Path], *, allow_internal_symlinks=False) -> int:
    """Count linked files once, with bounded recovery for live atomic renames.

    Rescan only a directory with vanished entries, measuring newly observed
    names before its stable prefix. Keep the largest observed size per inode
    conservatively even if deleted or replaced during this sample. A walk
    is not atomic; idle recounts, allocation reservations and physical free
    space remain separate mandatory guards.
    """
    seen = {}
    total = 0
    def walk_error(error):
        # os.walk otherwise silently skips unreadable subtrees, which would
        # understate the inventory. Only enumerated-entry lstat ENOENT retries.
        raise error

    def check_link(path):
        if not allow_internal_symlinks or not any(path.resolve().is_relative_to(root.resolve()) for root in roots if root.is_dir()):
            raise ValueError(f"Runner input link escapes its accounted roots: {path}")

    def count(path, observation):
        nonlocal total
        stat = observation
        if S_ISLNK(stat.st_mode):
            check_link(path)
        key = (stat.st_dev, stat.st_ino)
        previous = seen.get(key, 0)
        if stat.st_size > previous:
            total += stat.st_size - previous
            seen[key] = stat.st_size

    def directory_entries(directory, names):
        observed_names, regular_folders = set(), {}
        for attempt in range(INVENTORY_ATTEMPTS):
            vanished = False
            # Check new final/staging names before walking the stable prefix
            # again, so its cost cannot repeatedly outlast a transient name.
            names = sorted(names, key=lambda name: name in observed_names)
            for name in names:
                path = Path(directory) / name
                try:
                    observation = path.lstat()
                except FileNotFoundError:
                    # A prior observation stays conservatively counted. An
                    # unseen missing name requires discovery of its successor.
                    vanished |= name not in observed_names
                    regular_folders.pop(name, None)
                    continue
                observed_names.add(name)
                if S_ISLNK(observation.st_mode):
                    regular_folders.pop(name, None)
                    count(path, observation)
                elif S_ISDIR(observation.st_mode):
                    regular_folders[name] = True
                else:
                    regular_folders.pop(name, None)
                    count(path, observation)
            if not vanished:
                return list(regular_folders)
            if attempt == INVENTORY_ATTEMPTS - 1:
                raise ValueError("Runner storage inventory kept changing; cannot verify disk budget")
            # Keep inode/name observations within this sample, and discover
            # the final checksum name which replaced a transient staging file.
            # Enumeration errors propagate; they are never empty inventories.
            with os.scandir(directory) as entries:
                names = [entry.name for entry in entries]

    for root in roots:
        # Accounted roots are required inputs, unlike live descendant names.
        # Never turn a missing root into an empty successful inventory.
        observation = root.lstat()
        if root.is_file():
            count(root, observation)
            continue
        for directory, folders, files in os.walk(root, followlinks=False, onerror=walk_error):
            folders[:] = directory_entries(directory, [*folders, *files])
        root.lstat()
    return total


class DiskBudget:
    def __init__(self, roots: list[Path], *, capacity=RUNNER_BYTES, reserve=RESERVE_BYTES, allow_internal_symlinks=False):
        self.roots = [root.resolve() for root in roots]
        volumes = {}
        for root in self.roots:
            volumes.setdefault(root.stat().st_dev, root if root.is_dir() else root.parent)
        self.volumes = list(volumes.values())
        self.capacity, self.reserve = capacity, reserve
        self.allow_internal_symlinks = allow_internal_symlinks
        self.peak = 0
        self.planned_peak = 0
        self.samples = []

    def check(self, phase: str, additional: int = 0) -> None:
        used = unique_bytes(self.roots, allow_internal_symlinks=self.allow_internal_symlinks)
        self.peak = max(self.peak, used)
        self.planned_peak = max(self.planned_peak, used + additional)
        self.samples.append({"phase": phase, "bytes": used, "additional": additional})
        if used + additional > self.capacity - self.reserve:
            raise ValueError(f"Runner disk budget exceeded during {phase}: "
                             f"{used + additional:,} bytes leaves less than {self.reserve:,} bytes of margin.")
        self.free_check(additional)

    def free_check(self, additional: int = 0) -> None:
        if any(shutil.disk_usage(root).free < self.reserve + additional for root in self.volumes):
            raise ValueError("Runner has insufficient free space to preserve its disk reserve.")

    def report(self) -> dict:
        return {"capacity_bytes": self.capacity, "reserve_bytes": self.reserve,
                "peak_bytes": self.peak, "planned_peak_bytes": self.planned_peak, "samples": self.samples}


def link_file(source: Path, target: Path) -> int:
    """Fail rather than silently doubling disk use on an unsupported filesystem."""
    if source.is_symlink() or target.exists():
        raise ValueError(f"Hard-link staging requires a regular source and a new target: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, target)
    return source.stat().st_size


class PartWriter(io.RawIOBase):
    """A non-seekable archive sink; retain at most one part until acknowledged.

    `accept(path, row)` must verify the durable destination before returning.
    The local part survives failed acknowledgements. Successful parts are removed.
    ZIP uses data descriptors; ZIP64 and gzip/tar can both write without seeking.
    """
    def __init__(self, archive: Path, base_url: str, part_bytes: int, accept=None, budget=None, *, shared=False):
        super().__init__()
        if part_bytes <= 0:
            raise ValueError("Archive part size must be positive.")
        self.archive, self.base_url, self.part_bytes = archive, base_url, part_bytes
        self.accept, self.budget = accept, budget
        self.shared = shared
        self.parts = []
        self.size = 0
        self.hasher = hashlib.sha256()
        self.handle = None
        self.part_size = 0
        self.part_hasher = None
        self.failed = False

    def writable(self):
        return True

    def seekable(self):
        return False

    def tell(self):
        return self.size

    def write(self, data):
        if self.closed or self.failed:
            raise ValueError("Archive sink is closed or failed.")
        view = memoryview(data)
        count = len(view)
        while view:
            if self.handle is None:
                if self.budget:
                    self.budget.check("archive part", self.part_bytes)
                self.path = self.archive.with_name(f"{self.archive.name}.{len(self.parts) + 1:03d}")
                self.handle = self.path.open("xb")
                self.part_hasher = hashlib.sha256()
                self.part_size = 0
            piece = view[:self.part_bytes - self.part_size]
            if self.budget:
                self.budget.free_check(len(piece))
            self.handle.write(piece)
            self.part_hasher.update(piece)
            self.hasher.update(piece)
            self.part_size += len(piece)
            self.size += len(piece)
            view = view[len(piece):]
            if self.part_size == self.part_bytes:
                self._finish_part()
        return count

    def _finish_part(self):
        self.handle.close()
        self.handle = None
        if self.shared:
            import shared_release_assets as shared
            target = self.path.with_name(shared.name(self.part_hasher.hexdigest()))
            if target.exists():
                with target.open("rb") as existing:
                    if hashlib.file_digest(existing, "sha256").hexdigest() != self.part_hasher.hexdigest():
                        raise ValueError("A local shared download has conflicting bytes.")
                self.path.unlink()
            else:
                self.path.rename(target)
            self.path = target
        row = {"url": f"{self.base_url}/{self.path.name}", "size": self.part_size,
               "sha256": self.part_hasher.hexdigest()}
        try:
            if self.accept:
                self.accept(self.path, row)
                self.path.unlink()
        except BaseException:
            self.failed = True
            raise
        self.parts.append(row)

    def close(self):
        if not self.closed:
            if self.handle is not None:
                if self.failed:
                    self.handle.close()
                else:
                    self._finish_part()
            super().close()

    def __exit__(self, kind, value, traceback):
        if kind is not None:
            self.failed = True
        self.close()

    @property
    def sha256(self):
        return self.hasher.hexdigest()
