"""Optional, verified build products. No credentials or complete game copies.

Cache keys describe committed inputs, not dates or client revisions. A miss is
always a normal build. Packages are reused only after comparing the actual new
stage with a signed inventory and checking every part at its durable destination.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil

import client_release
import runner_source

SCHEMA = 1


def input_key(git, sha: str, platform: str) -> str:
    rows = []
    for row in git("ls-tree", "-r", "-z", sha).split("\0"):
        if not row:
            continue
        _, path = row.split("\t", 1)
        if not runner_source.selected(path):
            continue
        # Game scripts are rebuilt into the PCK every time. Keep helper scripts
        # in the key because cached native updaters contain those scripts.
        if path.startswith("godot-client/src/") and path.endswith((".gd", ".gd.uid")):
            if not path.startswith("godot-client/src/updates/"):
                continue
        if path.startswith(("godot-client/tests/", "godot-client/docs/")):
            continue
        rows.append(row)
    if not rows:
        raise ValueError("No committed asset inputs found for the build cache.")
    digest = hashlib.sha256("\0".join(sorted(rows)).encode()).hexdigest()
    return f"rl-assets-v{SCHEMA}-{platform}-{digest}"


class AssetCache:
    def __init__(self, root: Path, key: str):
        if root.is_symlink() or root.resolve() == Path(root.resolve().anchor):
            raise ValueError("Asset cache must be a disposable runner directory.")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.key = key
        self.hit = False
        self.reused_packages = self.built_packages = 0
        self.previous = {}
        self.sidecar_inputs = {}
        try:
            state = json.loads((self.root / "state.json").read_text())
            if state["key"] != key or state["schema"] != SCHEMA:
                raise ValueError("Asset input key changed")
            actual = self.inventory()
            if actual != state["files"]:
                raise ValueError("Cached file checksums changed")
            self.hit = True
        except (OSError, ValueError, KeyError, TypeError):
            # Only this explicitly supplied cache directory is disposable.
            self.reset()

    def inventory(self):
        files = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                raise ValueError("Asset cache contains a link")
            relative = path.relative_to(self.root).as_posix()
            if path.is_file() and relative != "state.json":
                files[relative] = {"size": path.stat().st_size, "sha256": client_release.digest(path)}
        return files

    def reset(self):
        for path in self.root.iterdir():
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_junction():
                path.rmdir()
            elif path.is_dir():
                if not path.resolve().is_relative_to(self.root):
                    raise ValueError("Cache cleanup escaped its runner directory")
                shutil.rmtree(path)

    @property
    def vram(self):
        return self.root / "vram"

    def restore_imports(self, project):
        self.sidecar_inputs = {p.relative_to(project).as_posix(): client_release.digest(p)
            for p in project.rglob("*.import") if ".godot" not in p.relative_to(project).parts}
        # Fresh source archives do not contain Godot-generated .import files.
        # Without these, Godot would choose new UIDs and reimport cached assets.
        index = self.root / "sidecars.json"
        if index.is_file():
            for relative, entry in json.loads(index.read_text()).items():
                sidecar = project / relative
                cached = self.root / "sidecars" / relative
                if (not sidecar.resolve().is_relative_to(project.resolve())
                        or not cached.resolve().is_relative_to(self.root / "sidecars")
                        or not relative.endswith(".import")):
                    raise ValueError("Unsafe cached import path")
                source = sidecar.with_suffix("")
                if (source.is_file() and client_release.digest(source) == entry["source_sha256"]
                        and self.sidecar_inputs.get(relative) == entry["input_sha256"]):
                    sidecar.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(cached, sidecar)
        imported = self.root / "imported"
        if imported.is_dir():
            target = project / ".godot/imported"
            target.parent.mkdir(exist_ok=True)
            imported.rename(target)

    def retain_imports(self, project):
        sidecars = self.root / "sidecars"
        if sidecars.exists():
            shutil.rmtree(sidecars)
        index = {}
        for path in project.rglob("*.import"):
            relative = path.relative_to(project).as_posix()
            source = path.with_suffix("")
            if ".godot" in path.relative_to(project).parts or not source.is_file():
                continue
            cached = sidecars / relative
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, cached)
            index[relative] = {"source_sha256": client_release.digest(source),
                               "input_sha256": self.sidecar_inputs.get(relative)}
        (self.root / "sidecars.json").write_text(json.dumps(index), encoding="utf-8")
        imported = project / ".godot/imported"
        if imported.is_dir():
            imported.rename(self.root / "imported")

    def packages(self, public: bytes, platform: str, repository: str):
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        try:
            envelope = json.loads((self.root / "manifest.json").read_text())
            raw = base64.b64decode(envelope["payload"], validate=True)
            signature = base64.b64decode(envelope["signature"], validate=True)
            serialization.load_pem_public_key(public).verify(signature, raw, padding.PKCS1v15(), hashes.SHA256())
            payload = json.loads(raw)
            if (payload["schema"] != 2 or payload["platform"] != platform
                    or payload["repository"] != repository):
                raise ValueError("Cached release identity changed")
            self.previous = {p["id"]: p for p in payload["packages"]}
        except (OSError, ValueError, KeyError, TypeError, InvalidSignature):
            self.previous = {}
        return self.previous

    def finish(self, manifest: bytes):
        (self.root / "manifest.json").write_bytes(manifest)
        # DDS quality scratch is never useful to a subsequent build.
        work = self.vram / "_work"
        if work.exists():
            shutil.rmtree(work)
        (self.root / "state.json").write_text(json.dumps({"schema": SCHEMA, "key": self.key,
            "files": self.inventory()}, sort_keys=True), encoding="utf-8")

    def report(self):
        return {"hit": self.hit, "key": self.key, "reused_packages": self.reused_packages,
                "built_packages": self.built_packages}
