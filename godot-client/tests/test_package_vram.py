#!/usr/bin/env python3
"""The packager stages and checks the VRAM texture sidecars
(tools/package_client.py stage_vram_textures / check_vram_textures).

    python3 godot-client/tests/test_package_vram.py -v

The check cases run on a scratch stage holding a copy of tests/fixtures/vram
with its committed sidecars. The staging case runs the real tool, which needs
the Godot 4.7.2 editor binary plus numpy and Pillow; without them it skips.

StageCommittedMaps walks this checkout's committed maps the way the packager
does, so a manifest naming a file that is not in the commit fails here in
seconds instead of after the packager's half-hour import and export. CI runs
it twice: with the rest of this file in the protocol-tests job, and on its own
as the package-map-walk job, which no failing protocol-tests step can skip. It
runs git in the checkout, so protocol-tests first marks the checkout a safe
directory: in that job's container git runs as root, the runner owns the
checkout, and git refuses a repository someone else owns.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
CLIENT = TESTS.parent
CHECKOUT = CLIENT.parent
FIXTURE = TESTS / "fixtures" / "vram"
sys.path.insert(0, str(CLIENT / "tools"))
sys.path.insert(0, str(TESTS))

import package_client as packager  # noqa: E402
from test_build_vram_textures import GODOT, SKIP_ENCODE  # noqa: E402

MAP = Path("eloria-assets") / "maps" / "vram_fixture"


class Check(unittest.TestCase):
    def setUp(self):
        self.stage = Path(tempfile.mkdtemp(prefix="vram-package-check-"))
        shutil.copytree(FIXTURE, self.stage / MAP, ignore=shutil.ignore_patterns("*.py", "report.json"))
        self.vram = self.stage / MAP / "shared-assets" / "vram"
        self.index = json.loads((self.vram / "index.json").read_text(encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.stage, ignore_errors=True)

    def _write_index(self):
        (self.vram / "index.json").write_text(json.dumps(self.index), encoding="utf-8")

    def test_committed_fixture_passes(self):
        packager.check_vram_textures(self.stage)

    def test_a_changed_sidecar_fails(self):
        entry = next(iter(self.index["images"].values()))
        path = self.vram / entry["file"]
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF
        path.write_bytes(bytes(data))
        with self.assertRaisesRegex(packager.PackageError, "sha256 differs"):
            packager.check_vram_textures(self.stage)

    def test_an_image_without_sidecar_or_reason_fails(self):
        sha = next(iter(self.index["images"]))
        del self.index["images"][sha]
        self._write_index()
        with self.assertRaisesRegex(packager.PackageError, "no sidecar and no exclusion reason"):
            packager.check_vram_textures(self.stage)

    def test_a_missing_sidecar_fails(self):
        entry = next(iter(self.index["images"].values()))
        (self.vram / entry["file"]).unlink()
        with self.assertRaisesRegex(packager.PackageError, "listed in the index but missing"):
            packager.check_vram_textures(self.stage)

    def test_a_stray_file_fails(self):
        (self.vram / "report.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(packager.PackageError, "not named by the index"):
            packager.check_vram_textures(self.stage)

    def test_an_unstaged_external_image_fails(self):
        manifest = json.loads((self.stage / MAP / "world.json").read_text(encoding="utf-8"))
        uri = next(iter(manifest["externalResources"]))
        (self.stage / MAP / uri).unlink()
        with self.assertRaisesRegex(packager.PackageError, "is not in the package"):
            packager.check_vram_textures(self.stage)

    def test_no_index_at_all_fails(self):
        shutil.rmtree(self.vram)
        with self.assertRaisesRegex(packager.PackageError, "no sidecar and no exclusion reason"):
            packager.check_vram_textures(self.stage)

    @staticmethod
    def write_glb(path, document):
        raw = json.dumps(document).encode("utf-8")
        raw += b" " * (-len(raw) % 4)
        path.write_bytes(b"glTF" + struct.pack("<II", 2, 20 + len(raw))
                         + struct.pack("<II", len(raw), 0x4E4F534A) + raw)

    def canonicalize_sources(self):
        """One raw image copy; the original policy directory keeps only VRAM files."""
        path = self.stage / MAP / "world.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        renamed = {}
        for uri in manifest["externalResources"]:
            old = self.stage / MAP / uri
            new_uri = "../canonical/" + old.name
            new = self.stage / MAP / new_uri
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            renamed[uri] = new_uri
        manifest["externalResources"] = {renamed[uri]: sha for uri, sha in manifest["externalResources"].items()}
        manifest["externalImagePolicies"] = {uri: ["shared-assets"] for uri in renamed.values()}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        glb = self.stage / MAP / "world.glb"
        document = packager.gltf_document(glb)
        for image in document["images"]:
            if "uri" not in image:
                continue
            image["uri"] = renamed[image["uri"]]
            image.setdefault("extras", {})[packager.TEXTURE_POLICY_DIRECTORY_KEY] = "shared-assets"
        self.write_glb(glb, document)
        return manifest, document

    def test_canonical_sources_keep_their_original_sidecar_directory(self):
        self.canonicalize_sources()
        self.assertEqual(list(self.vram.parent.iterdir()), [self.vram])
        packager.check_vram_textures(self.stage)

    def test_a_changed_canonical_source_fails_its_original_hash(self):
        manifest, _ = self.canonicalize_sources()
        source = self.stage / MAP / next(iter(manifest["externalResources"]))
        source.write_bytes(source.read_bytes() + b"changed")
        with self.assertRaisesRegex(packager.PackageError, "source sha256 differs"):
            packager.check_vram_textures(self.stage)

    def test_canonical_directory_sidecars_cannot_replace_the_original_policy(self):
        self.canonicalize_sources()
        shutil.copytree(self.vram, self.stage / MAP.parent / "canonical/vram")
        shutil.rmtree(self.vram)
        with self.assertRaisesRegex(packager.PackageError, "no sidecar and no exclusion reason.*shared-assets"):
            packager.check_vram_textures(self.stage)

    def test_a_descriptor_cannot_silently_change_its_declared_policy(self):
        _, document = self.canonicalize_sources()
        next(image for image in document["images"] if "uri" in image)["extras"][packager.TEXTURE_POLICY_DIRECTORY_KEY] = "../canonical"
        self.write_glb(self.stage / MAP / "world.glb", document)
        with self.assertRaisesRegex(packager.PackageError, "policy directory disagrees"):
            packager.check_vram_textures(self.stage)

    def test_policy_metadata_must_name_a_declared_image_inside_the_asset_tree(self):
        manifest, _ = self.canonicalize_sources()
        path = self.stage / MAP / "world.json"
        uri = next(iter(manifest["externalResources"]))
        for invalid in ([], "shared-assets", ["../../../../outside"], ["C:/outside"], ["%2e%2e/outside"]):
            with self.subTest(invalid=invalid):
                manifest["externalImagePolicies"][uri] = invalid
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(packager.PackageError):
                    packager.check_vram_textures(self.stage)
        manifest["externalImagePolicies"][uri] = ["shared-assets"]
        manifest["externalImagePolicies"]["not-declared.png"] = ["shared-assets"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(packager.PackageError, "undeclared image"):
            packager.check_vram_textures(self.stage)

    def test_policy_descriptors_reject_encoded_paths(self):
        _, document = self.canonicalize_sources()
        next(image for image in document["images"] if "uri" in image)["extras"][packager.TEXTURE_POLICY_DIRECTORY_KEY] = "%73hared-assets"
        self.write_glb(self.stage / MAP / "world.glb", document)
        with self.assertRaisesRegex(packager.PackageError, "unsafe rl_texture_policy_directory"):
            packager.check_vram_textures(self.stage)

    def test_prototype_only_policy_is_checked_even_without_a_world_resource(self):
        manifest, document = self.canonicalize_sources()
        pool = self.stage / "eloria-assets/maps/_shared/meshes"
        pool.mkdir(parents=True)
        resources = {"../../canonical/" + Path(uri).name: sha
                     for uri, sha in manifest["externalResources"].items()}
        policies = {uri: ["../../vram_fixture/shared-assets"] for uri in resources}
        for image in document["images"]:
            if "uri" not in image:
                continue
            image["uri"] = "../../canonical/" + Path(image["uri"]).name
            image["extras"][packager.TEXTURE_POLICY_DIRECTORY_KEY] = "../../vram_fixture/shared-assets"
        self.write_glb(pool / "prototype.glb", document)
        (pool / "index.json").write_text(json.dumps({"prototypes": {"prototype": {
            "images": resources, "imagePolicies": policies}}}), encoding="utf-8")
        (self.stage / MAP / "world.json").unlink()
        packager.check_vram_textures(self.stage)
        (self.vram / "index.json").unlink()
        with self.assertRaisesRegex(packager.PackageError, "no sidecar and no exclusion reason"):
            packager.check_vram_textures(self.stage)

    def test_road_only_style_keeps_its_source_fallback_without_a_new_sidecar(self):
        path = self.stage / MAP / "world.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        raw = self.stage / MAP / "road-only.png"
        raw.write_bytes(b"source pixels")
        sha = hashlib.sha256(raw.read_bytes()).hexdigest()
        metadata = self.stage / MAP / "roads.json"
        metadata.write_text(json.dumps({"schema": "rabbitlands-road-terrain-blend-v1",
            "resources": {raw.name: sha}, "externalImagePolicies": {raw.name: ["original-road-policy"]},
            "styles": [{"externalResources": {raw.name: sha}, "material_document": {"images": [{
                "uri": raw.name, "extras": {packager.TEXTURE_POLICY_DIRECTORY_KEY: "original-road-policy"}}]}}]}),
            encoding="utf-8")
        manifest["roadGround"] = {"metadata": metadata.name,
                                  "sha256": hashlib.sha256(metadata.read_bytes()).hexdigest()}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertFalse((self.stage / MAP / "original-road-policy").exists())
        packager.check_vram_textures(self.stage)


class SharedPools(unittest.TestCase):
    """share_identical_sidecars: a sidecar two pools hold ships once, from the
    primary pool, and the other pool's index names it there ("pool")."""

    PRIMARY = "eloria-assets/maps/vram_fixture/shared-assets"

    def setUp(self):
        self.stage = Path(tempfile.mkdtemp(prefix="vram-package-shared-"))
        for name in ("vram_fixture", "second"):
            shutil.copytree(FIXTURE, self.stage / "eloria-assets" / "maps" / name,
                            ignore=shutil.ignore_patterns("*.py", "report.json"))
        self.primary = self.stage / self.PRIMARY / "vram"
        self.second = self.stage / "eloria-assets" / "maps" / "second" / "shared-assets" / "vram"

    def tearDown(self):
        shutil.rmtree(self.stage, ignore_errors=True)

    def snapshot(self, folder):
        return {p.name: p.read_bytes() for p in folder.iterdir()}

    def test_the_second_pool_names_the_primary_files(self):
        before = self.snapshot(self.primary)
        index = json.loads((self.second / "index.json").read_text(encoding="utf-8"))
        shared = packager.share_identical_sidecars(self.stage, self.PRIMARY)
        self.assertEqual(shared["files"], 4)
        self.assertEqual(shared["directories"], ["eloria-assets/maps/second/shared-assets"])
        self.assertEqual(shared["bytes"], sum(len(data) for name, data in before.items() if name != "index.json"))
        self.assertEqual(self.snapshot(self.primary), before, "the primary pool is never touched")
        self.assertEqual(sorted(p.name for p in self.second.iterdir()), ["index.json"])
        after = json.loads((self.second / "index.json").read_text(encoding="utf-8"))
        for sha, entry in after["images"].items():
            self.assertEqual(entry.pop("pool"), "../../vram_fixture/shared-assets")
            self.assertEqual(entry, index["images"][sha], "the entry keeps everything else, its roles too")
        self.assertEqual(after["excluded"], index["excluded"])
        packager.check_vram_textures(self.stage)
        self.assertEqual(packager.share_identical_sidecars(self.stage, self.PRIMARY)["files"], 0, "idempotent")

    def test_only_the_same_encode_is_shared(self):
        index = json.loads((self.second / "index.json").read_text(encoding="utf-8"))
        sha, entry = next(iter(index["images"].items()))
        path = self.second / entry["file"]
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF
        path.write_bytes(bytes(data))
        entry["sha256"] = hashlib.sha256(bytes(data)).hexdigest()
        other_sha, other = list(index["images"].items())[1]
        other["roles"] = other.get("roles", []) + ["emissive"]
        (self.second / "index.json").write_text(json.dumps(index), encoding="utf-8")
        shared = packager.share_identical_sidecars(self.stage, self.PRIMARY)
        after = json.loads((self.second / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(shared["files"], 3)
        self.assertNotIn("pool", after["images"][sha])
        self.assertTrue(path.is_file(), "a different encode keeps its own file")
        self.assertIn("pool", after["images"][other_sha], "other roles still share the bytes")
        self.assertEqual(after["images"][other_sha]["roles"], other["roles"])
        packager.check_vram_textures(self.stage)

    def test_a_changed_primary_file_fails_the_check(self):
        packager.share_identical_sidecars(self.stage, self.PRIMARY)
        victim = next(p for p in self.primary.iterdir() if p.suffix == ".evt")
        data = bytearray(victim.read_bytes())
        data[-1] ^= 0xFF
        victim.write_bytes(bytes(data))
        with self.assertRaisesRegex(packager.PackageError, "sha256 differs"):
            packager.check_vram_textures(self.stage)

    def test_without_the_primary_pool_nothing_moves(self):
        shutil.rmtree(self.primary)
        before = self.snapshot(self.second)
        self.assertEqual(packager.share_identical_sidecars(self.stage, self.PRIMARY),
                         {"files": 0, "bytes": 0, "directories": []})
        self.assertEqual(self.snapshot(self.second), before)

    def test_packager_and_client_agree_on_the_key(self):
        client = (CLIENT / "src" / "world" / "vram_textures.gd").read_text(encoding="utf-8")
        self.assertIn('source.has("pool")', client)
        self.assertEqual(packager.PRIMARY_SIDECAR_POOL,
                         "eloria-assets/" + client.split('const SHARED_ASSETS := "res://../eloria-assets/')[1]
                         .split('"')[0])


# Stands in for tools/build_vram_textures.py in StagePooled: copies the fixture's committed sidecars into every
# pool of --out-root, as the real tool encodes the same images to the same files.
FAKE_TOOL = """
import shutil, sys
from pathlib import Path
out = Path(sys.argv[sys.argv.index("--out-root") + 1])
for pool in sorted(out.rglob("shared-assets")):
    shutil.copytree(sys.argv[-1], pool / "vram", dirs_exist_ok=True)
    (pool / "vram" / "report.json").write_text(pool.as_posix(), encoding="utf-8")
"""


class StagePooled(unittest.TestCase):
    """The share step follows the commit being packaged: it runs only when that commit's client declares that it
    reads "pool" entries (vram_textures.gd INDEX_FEATURES); packaging an older client ships every pool's own files.
    The smoke launch then also decodes one pooled sidecar from where it ships."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-package-pooled-"))
        self.build = self.scratch / "build"
        self.stage = self.scratch / "stage"
        self.logs = self.scratch / "logs"
        self.logs.mkdir()
        for pool in (packager.PRIMARY_SIDECAR_POOL, "eloria-assets/maps/second/shared-assets"):
            shutil.copytree(FIXTURE / "shared-assets", self.stage / pool, ignore=shutil.ignore_patterns("vram"))
        self.tool = self.scratch / "fake_build_vram_textures.py"
        self.tool.write_text(FAKE_TOOL, encoding="utf-8")
        self.client = self.build / "godot-client" / "src" / "world" / "vram_textures.gd"
        self.client.parent.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def stage_with(self, client_text):
        self.client.write_text(client_text, encoding="utf-8")
        original = packager.subprocess.run

        def run(command, **kwargs):
            return original(command + [str(FIXTURE / "shared-assets" / "vram")], **kwargs)
        packager.subprocess.run = run
        try:
            return packager.stage_vram_textures(self.build, self.stage, Path("godot"), self.scratch / "cache",
                                                self.logs, tool=self.tool)
        finally:
            packager.subprocess.run = original

    def second_index(self):
        path = self.stage / "eloria-assets/maps/second/shared-assets/vram/index.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_current_client_declares_the_feature(self):
        text = (CLIENT / "src" / "world" / "vram_textures.gd").read_text(encoding="utf-8")
        self.assertIsNotNone(packager.POOL_FEATURE.search(text))

    def test_a_client_that_reads_pool_entries_gets_them(self):
        self.stage_with((CLIENT / "src" / "world" / "vram_textures.gd").read_text(encoding="utf-8"))
        self.assertEqual(packager.pooled_sidecar_directory(self.stage), "eloria-assets/maps/second/shared-assets")
        self.assertTrue(all("pool" in entry for entry in self.second_index()["images"].values()))
        packager.check_vram_textures(self.stage)
        reports = sorted(p.name for p in self.logs.glob("vram-report-*.json"))
        self.assertEqual(reports, ["vram-report-maps__nymara-regions___continent__shared-assets.json",
                                   "vram-report-maps__second__shared-assets.json"],
                         "each pool's quality report keeps its own log file")

    def test_an_older_client_gets_every_pool_whole(self):
        old = 'const SHARED_ASSETS := "res://../eloria-assets/maps/vram_fixture/shared-assets"\n'
        staged = self.stage_with(old)
        self.assertIsNone(packager.pooled_sidecar_directory(self.stage))
        self.assertFalse(any("pool" in entry for entry in self.second_index()["images"].values()))
        self.assertEqual(staged["files"], 10, "both pools ship their index and four sidecars")
        packager.check_vram_textures(self.stage)

    def test_the_smoke_launch_asks_for_and_requires_the_pool_line(self):
        seen = {}
        lines = {"text": packager.VRAM_SELF_TEST_OK + " entries=4\n"}

        def fake_godot(binary, args, log_path, timeout=0, env=None):
            seen["env"] = dict(env or {})
            return lines["text"]
        original = packager.run_godot
        packager.run_godot = fake_godot
        app = self.scratch / "pkg" / "app"
        app.mkdir(parents=True)
        platform = {"binary": "RabbitLands.exe"}
        try:
            packager.smoke_launch(app, self.logs, platform, vram_textures=True)
            self.assertNotIn("ELORIA_VRAM_SELF_TEST_POOL", seen["env"])
            with self.assertRaisesRegex(packager.PackageError, "a sidecar another pool ships"):
                packager.smoke_launch(app, self.logs, platform, vram_textures=True,
                                      pool_test="eloria-assets/maps/second/shared-assets")
            self.assertEqual(seen["env"]["ELORIA_VRAM_SELF_TEST_POOL"],
                             "res://../eloria-assets/maps/second/shared-assets")
            lines["text"] += packager.VRAM_SELF_TEST_POOL_OK + " pooled=4 of 4 format=bc7\n"
            packager.smoke_launch(app, self.logs, platform, vram_textures=True,
                                  pool_test="eloria-assets/maps/second/shared-assets")
        finally:
            packager.run_godot = original


class StageExternalResources(unittest.TestCase):
    """externalResources names its files as keys, relative to the GLB: the
    continent's shared images live outside every package folder and used to
    be left out of the package, so every chunk failed its resource check."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="vram-package-stage-ext-"))
        chunk = self.repo / "eloria-assets" / "maps" / "region" / "chunks" / "a"
        shared = self.repo / "eloria-assets" / "maps" / "_continent" / "shared-assets"
        chunk.mkdir(parents=True)
        shared.mkdir(parents=True)
        (shared / "abc.png").write_bytes(b"\x89PNG fixture")
        (chunk / "world.glb").write_bytes(b"glTF")
        self.manifest = {"asset": {"glb": "world.glb"},
                         "externalResources": {"../../../_continent/shared-assets/abc.png": "0" * 64}}
        (chunk / "world.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        git = ["git", "-C", str(self.repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid"]
        subprocess.run(git[:3] + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "fixture"], check=True)
        self.stage = self.repo.parent / (self.repo.name + "-stage")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.stage, ignore_errors=True)

    def test_shared_images_are_staged(self):
        packager.stage_eloria_assets(self.repo, self.stage)
        self.assertTrue((self.stage / "eloria-assets/maps/_continent/shared-assets/abc.png").is_file())
        self.assertTrue((self.stage / "eloria-assets/maps/region/chunks/a/world.glb").is_file())

    def test_an_untracked_external_image_fails_the_stage(self):
        chunk = self.repo / "eloria-assets" / "maps" / "region" / "chunks" / "a"
        self.manifest["externalResources"]["../../../_continent/shared-assets/missing.png"] = "1" * 64
        (chunk / "world.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                        "commit", "-q", "-am", "missing"], check=True)
        with self.assertRaisesRegex(packager.PackageError, "externalResources -> .*missing.png is not in the commit"):
            packager.stage_eloria_assets(self.repo, self.stage)


def _git(*args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", *args], cwd=CHECKOUT, input=data, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {CHECKOUT}:\n"
                             + result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def _batch_contents(output: bytes):
    """The object contents in `git cat-file --batch` output, in request order."""
    at = 0
    while at < len(output):
        end = output.index(b"\n", at)
        header = output[at:end].split()
        if len(header) != 3:
            raise AssertionError(f"git cat-file --batch: {output[at:end]!r}")
        size = int(header[2])
        yield output[end + 1:end + 1 + size]
        at = end + 1 + size + 1


@unittest.skipUnless((CHECKOUT / ".git").exists(), "needs the client's git checkout")
class StageCommittedMaps(unittest.TestCase):
    """The packager's map walk over this checkout's committed maps: every file a
    shipped manifest names must be in the commit. The packager itself runs this
    walk only after its half-hour import and export.

    396 legacy chunk manifests once stopped it there: each carried a copy of its
    territory's minimap block, naming a chunks/<x>_<z>/minimap.webp that no tool
    writes and nothing reads (the client frames and draws the map from the
    territory's own block and picture)."""

    @classmethod
    def setUpClass(cls):
        # packager.tracked() would fail with a bare CalledProcessError; say why
        # git cannot read the checkout (in a CI container: dubious ownership).
        _git("rev-parse", "--verify", "-q", "HEAD")

    def test_chunk_manifests_carry_no_minimap_block(self):
        # build_continent.py export_geometry still copies the block into each
        # chunk: pop "minimap" there at the next geometry export, when the
        # certificates that pin that file are re-issued anyway. Do not commit
        # pictures beside the chunks instead.
        # Read from the index, so a sparse checkout still checks every chunk.
        listing = _git("ls-files", "-s", "-z", "--", "eloria-assets/maps").decode("utf-8")
        chunks = [(meta.split()[1], path) for meta, path in (line.split("\t", 1) for line in listing.split("\0") if line)
                  if path.endswith("/world.json") and path.split("/")[-3] == "chunks"]
        self.assertTrue(chunks, "the checkout has no chunk manifests")
        blobs = _git("cat-file", "--batch", data="".join(f"{sha}\n" for sha, _ in chunks).encode("ascii"))
        carrying = [path for (_, path), text in zip(chunks, _batch_contents(blobs)) if "minimap" in json.loads(text)]
        self.assertEqual(carrying[:5], [], f"{len(carrying)} chunk manifests copy their territory's minimap block")

    def test_every_file_a_shipped_manifest_names_is_committed(self):
        manifests = [path for path in packager.tracked(CHECKOUT, "eloria-assets/maps") if path.endswith("/world.json")]
        absent = [path for path in manifests if not (CHECKOUT / path).is_file()]
        if absent:
            # The walk skips a manifest it cannot read, so it would pass here
            # without checking it.
            self.skipTest(f"{len(absent)} map manifests are not checked out (a sparse checkout?), e.g. {absent[0]}")
        # Stage the maps as main() does on this branch. drop_preview_maps first
        # rewrites the build tree's registry without its preview rows, and the
        # walk then reads that registry as a client source, so run it on a
        # scratch copy and show the walk the copy. Each served continent-v2 map
        # stages as its client package only (its territory manifest names no
        # master GLB).
        scratch = Path(tempfile.mkdtemp(prefix="package-committed-maps-"))
        stage = scratch / "stage"
        registry_file = CHECKOUT / packager.REGISTRY_FILE
        dropped_file = scratch / "build" / packager.REGISTRY_FILE
        dropped_file.parent.mkdir(parents=True)
        shutil.copyfile(registry_file, dropped_file)
        read_text = Path.read_text
        staged: set[str] = set()
        # Post-copy checks read the staged world manifests and fully verify
        # their road field closure. Materialize only that small required set;
        # record all other selected files without copying the full map GLBs.
        required = set(manifests)
        for relative in manifests:
            data = json.loads((CHECKOUT / relative).read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "roadGround" in data:
                required.update(path.relative_to(CHECKOUT.resolve()).as_posix() for path in
                                packager.road_dependencies(CHECKOUT, CHECKOUT / relative, data["roadGround"]))

        def copy_file(source: Path, target: Path) -> int:
            relative = target.relative_to(stage).as_posix()
            staged.add(relative)
            if relative in required:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            return 0

        def read_dropped_registry(path: Path, *args, **kwargs) -> str:
            return read_text(dropped_file if path == registry_file else path, *args, **kwargs)

        try:
            with mock.patch.object(packager, "copy_file", copy_file), mock.patch.object(packager, "log"):
                previews = packager.drop_preview_maps(scratch / "build")
                served = packager.read_served_v2_packages(scratch / "build")
                with mock.patch.object(Path, "read_text", read_dropped_registry):
                    packager.stage_eloria_assets(CHECKOUT, stage, previews, served)
            registry = json.loads(dropped_file.read_text(encoding="utf-8"))
        except packager.PackageError as error:
            self.fail(str(error))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        # A walk that read nothing would pass as well: every map manifest the
        # packaged registry names must have been staged.
        named = {match.group(1) for entry in registry.get("maps", {}).values() if isinstance(entry, dict)
                 for match in [packager.ASSET_REF.search(str(entry.get("manifest", "")))] if match}
        self.assertTrue(named, "the registry names no map manifests")
        self.assertEqual(sorted(named - staged)[:5], [], f"{len(named - staged)} registry manifests were not staged")


class SelfTestLine(unittest.TestCase):
    def test_packager_and_client_agree_on_the_line(self):
        client = (CLIENT / "src" / "world" / "vram_textures.gd").read_text(encoding="utf-8")
        self.assertIn(packager.VRAM_SELF_TEST_OK, client)
        self.assertIn("ELORIA_VRAM_SELF_TEST", client)
        self.assertIn(packager.VRAM_SELF_TEST_POOL_OK, client)
        self.assertIn('SELF_TEST_POOL_ENVIRONMENT := "ELORIA_VRAM_SELF_TEST_POOL"', client)


RECORDING_TOOL = """
import json, shutil, sys
from pathlib import Path
args = sys.argv[1:]
Path(args[args.index("--out-root") + 1]).mkdir(parents=True, exist_ok=True)
(Path(args[args.index("--out-root") + 1]) / "argv.json").write_text(json.dumps(args), encoding="utf-8")
if "--scenery-out-root" in args:
    vram = Path(args[args.index("--scenery-out-root") + 1]) / "underground" / "vram"
    shutil.copytree(sys.argv[-1], vram, dirs_exist_ok=True)
    (vram / "report.json").write_text("{}", encoding="utf-8")
"""


class SceneryAndUnskip(unittest.TestCase):
    """Landfall Town's shell images ship sidecars although maps/_shared/images is skipped, and its scenery GLBs'
    embedded images ship sidecars loose beside them in app/assets/world (build_vram_textures.py --unskip-map,
    --scenery-config; world_object_images.gd reads them)."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-package-scenery-"))
        self.build = self.scratch / "build"
        self.stage = self.scratch / "stage"
        self.app = self.stage / "app"
        self.logs = self.scratch / "logs"
        self.logs.mkdir()
        self.tool = self.scratch / "recording_tool.py"
        self.tool.write_text(RECORDING_TOOL, encoding="utf-8")
        for config in packager.SCENERY_SIDECAR_CONFIGS:
            (self.build / config).parent.mkdir(parents=True, exist_ok=True)
            (self.build / config).write_text("{}", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def stage_with(self, app_dir):
        original = packager.subprocess.run

        def run(command, **kwargs):
            return original(command + [str(FIXTURE / "shared-assets" / "vram")], **kwargs)
        with mock.patch.object(packager.subprocess, "run", run):
            staged = packager.stage_vram_textures(self.build, self.stage, Path("godot"), self.scratch / "cache",
                                                  self.logs, tool=self.tool, app_dir=app_dir)
        argv = json.loads((self.stage / "eloria-assets" / "maps" / "argv.json").read_text(encoding="utf-8"))
        (self.stage / "eloria-assets" / "maps" / "argv.json").unlink()
        return staged, argv

    def test_the_town_s_shell_images_are_unskipped(self):
        _, argv = self.stage_with(None)
        self.assertIn("_shared/images", argv)
        self.assertEqual(argv[argv.index("--unskip-map") + 1], "continent-v2/landfall_town")
        self.assertNotIn("--scenery-config", argv, "no scenery sidecars without an app/ to put them in")

    def test_scenery_sidecars_ship_loose_beside_the_glbs(self):
        staged, argv = self.stage_with(self.app)
        self.assertEqual(argv[argv.index("--scenery-config") + 1],
                         str(self.build / packager.SCENERY_SIDECAR_CONFIGS[0]))
        self.assertEqual(argv[argv.index("--scenery-out-root") + 1], str(self.app / "assets" / "world"))
        vram = self.app / "assets" / "world" / "underground" / "vram"
        self.assertFalse((vram / "report.json").exists(), "the quality report goes to the logs, not app/")
        self.assertTrue((self.logs / "vram-report-app__assets__world__underground.json").is_file())
        self.assertEqual(staged["sceneryFiles"], 5, "the index and four sidecars")
        packager.check_scenery_vram_textures(self.app)
        (vram / "stray.evt").write_bytes(b"x")
        with self.assertRaises(packager.PackageError):
            packager.check_scenery_vram_textures(self.app)
        (vram / "stray.evt").unlink()
        index = json.loads((vram / "index.json").read_text(encoding="utf-8"))
        first = next(iter(index["images"].values()))
        (vram / first["file"]).write_bytes(b"changed")
        with self.assertRaises(packager.PackageError):
            packager.check_scenery_vram_textures(self.app)


# --- actor sidecars (AT-C3) -------------------------------------------------------------------------------------

ACTOR_FIXTURE = TESTS / "fixtures" / "actor_vram"
REAL_TOOL = CLIENT / "tools" / "build_vram_textures.py"

# Stands in for the commit's tools/build_vram_textures.py --actor-dir (it sits at that path in a scratch build tree):
# plans the build tree's actor GLBs with the real tool's own readers and writes per-directory indexes of fake .evt
# files, accepting every image a material samples (with its roles) and excluding the others. The real encode is
# covered by test_build_vram_textures.py ActorBuild and by ActorStageReal below.
FAKE_ACTOR_TOOL = r"""
import hashlib, importlib.util, json, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("real_vram_tool", os.environ["REAL_VRAM_TOOL"])
real = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real)
args = sys.argv[1:]
def values(flag):
    return [args[i + 1] for i, arg in enumerate(args) if arg == flag]
cache = Path(values("--cache")[0])
cache.mkdir(parents=True, exist_ok=True)
(cache / "argv.json").write_text(json.dumps(args), encoding="utf-8")
if os.environ.get("FAKE_ACTOR_TOOL_FAIL"):
    print("[00:00:00] FAILED: the fake encoder broke")
    sys.exit(1)
client = Path(__file__).resolve().parents[1]
actors = client / "assets" / "actors"
retired_index = client / "data" / "assets" / "retired_procedural_models.json"
retired = {(client / "assets" / p).resolve() for p in json.loads(retired_index.read_text(encoding="utf-8"))["runtimePaths"]}
out_root = Path(values("--actor-out-root")[0])
plans = {}
glbs = 0
for name in values("--actor-dir"):
    for glb in sorted((actors / "native" / name).rglob("*.glb")):
        if glb.resolve() in retired:
            continue
        glbs += 1
        chunks = real.glb_chunks(glb)
        roles = real.image_roles(chunks[0])
        for index, sha, _ in real.embedded_images(glb, cache / "_extract", chunks):
            plans.setdefault(glb.parent, {}).setdefault(sha, set()).update(real.role_names(roles.get(index, set())))
summary = {"encoded": 0, "cached": 0, "actorGlbs": glbs, "actorImages": 0, "actorAccepted": 0, "actorExcluded": {},
           "actorGpuBytes": 0, "actorFileBytes": 0, "directories": {}}
for directory, images in sorted(plans.items()):
    target = out_root / directory.relative_to(actors) / "vram"
    target.mkdir(parents=True, exist_ok=True)
    index = {"schema": 1, "recipeVersion": 1, "images": {}, "excluded": {}}
    for sha, roles in sorted(images.items()):
        summary["actorImages"] += 1
        if not roles:
            index["excluded"][sha] = "no_material_role"
            summary["actorExcluded"]["no_material_role"] = summary["actorExcluded"].get("no_material_role", 0) + 1
            continue
        data = b"EVT1 fake sidecar " + sha.encode()
        (target / f"{sha}.base.evt").write_bytes(data)
        index["images"][sha] = {"file": f"{sha}.base.evt", "recipe": "base", "format": "bc7", "width": 64,
                                "height": 64, "mipmaps": 7, "gpuBytes": 5472, "rawBytes": 5620,
                                "fileBytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                "roles": sorted(roles)}
        summary["actorAccepted"] += 1
        summary["actorGpuBytes"] += 5472
        summary["actorFileBytes"] += len(data)
    (target / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    (target / "report.json").write_text("{}", encoding="utf-8")
    summary["directories"][str(target)] = {"sidecars": len(index["images"])}
print("[00:00:00] fake actor encode")
print(json.dumps(summary, indent=1))
"""


def _actor_build_tree(root: Path, tool_text: str | None = FAKE_ACTOR_TOOL) -> Path:
    """A scratch build tree shaped like the repository: godot-client/ holding the actor fixture's assets and data,
    and tools/build_vram_textures.py (the fake above, or the real tool when tool_text is None)."""
    client = root / "godot-client"
    shutil.copytree(ACTOR_FIXTURE / "assets", client / "assets")
    shutil.copytree(ACTOR_FIXTURE / "data", client / "data")
    (client / "tools").mkdir(parents=True)
    if tool_text is None:
        shutil.copyfile(REAL_TOOL, client / "tools" / "build_vram_textures.py")
        shutil.copyfile(CLIENT / "tools" / "vram_encode.gd", client / "tools" / "vram_encode.gd")
    else:
        (client / "tools" / "build_vram_textures.py").write_text(tool_text, encoding="utf-8")
    return root


def _stage_actor_glbs(build: Path, app: Path) -> None:
    """The actor GLBs as stage_loose_client_files stages them: every tracked file loose, rl_heads and the retired
    model included (they ship; they only get no sidecars)."""
    shutil.copytree(build / "godot-client" / "assets" / "actors", app / "assets" / "actors")


class ActorSidecarStage(unittest.TestCase):
    """stage_actor_vram_textures runs the commit's tool once per package, for the actor folders, into app/."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-actor-stage-")).resolve()
        self.build = _actor_build_tree(self.scratch / "build")
        self.stage = self.scratch / "stage"
        self.app = self.stage / "app"
        self.logs = self.scratch / "logs"
        self.logs.mkdir()
        self.cache = self.scratch / "cache"
        _stage_actor_glbs(self.build, self.app)
        self.env = mock.patch.dict(packager.os.environ, {"REAL_VRAM_TOOL": str(REAL_TOOL)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.scratch, ignore_errors=True)

    def run_stage(self, **options):
        with mock.patch.object(packager, "log"):
            return packager.stage_actor_vram_textures(self.build, self.stage, Path("godot.exe"), self.cache,
                                                      self.logs, self.app, **options)

    def argv(self):
        return json.loads((self.cache / "argv.json").read_text(encoding="utf-8"))

    def test_one_run_of_the_commit_s_tool_into_app_assets_actors(self):
        receipt = self.run_stage()
        argv = self.argv()
        self.assertEqual([argv[i + 1] for i, arg in enumerate(argv) if arg == "--actor-dir"],
                         list(packager.ACTOR_SIDECAR_DIRS))
        self.assertEqual(argv[argv.index("--actor-out-root") + 1], str(self.app / "assets" / "actors"))
        self.assertEqual(argv[argv.index("--cache") + 1], str(self.cache), "the map run's cache: actors use _actors/")
        self.assertEqual(argv[argv.index("--godot") + 1], "godot.exe")
        for absent in ("--maps", "--out-root", "--link-output", "--cache-budget-bytes", "--floors", "--procs"):
            self.assertNotIn(absent, argv, "a local package: no runner storage, map floors, the tool's procs")
        native = self.app / "assets" / "actors" / "native"
        indexes = sorted(p.parent.parent.relative_to(native).as_posix() for p in native.rglob("vram/index.json"))
        self.assertEqual(indexes, ["creatures", "creatures/basic_expansion", "equipment", "hair", "hair/fitted",
                                   "mounts", "races"])
        self.assertFalse(list(native.rglob("report.json")), "the quality reports go to the logs, not app/")
        self.assertEqual(sorted(p.name for p in self.logs.glob("vram-report-app__*.json")),
                         sorted("vram-report-app__assets__actors__native__" + d.replace("/", "__") + ".json"
                                for d in indexes))
        self.assertEqual(receipt, json.loads((self.logs / "actor-vram-textures.json").read_text(encoding="utf-8")))
        self.assertEqual(receipt["dirs"], list(packager.ACTOR_SIDECAR_DIRS))
        self.assertEqual(receipt["selfTest"], "assets/actors/native/races")
        self.assertEqual(receipt["summary"]["actorGlbs"], 8, "rl_heads and the retired model are never planned")
        self.assertEqual(sorted(receipt["families"]), sorted(packager.ACTOR_SIDECAR_DIRS))
        files = [p for p in native.rglob("vram/*") if p.is_file()]
        self.assertEqual((receipt["files"], receipt["bytes"]), (len(files), sum(p.stat().st_size for p in files)))
        self.assertEqual(receipt["families"]["creatures"]["indexes"], 2)
        self.assertEqual(receipt["sidecars"], 14)
        self.assertTrue((self.logs / "actor-vram-textures.log").is_file())
        self.assertFalse(list((self.build / "godot-client" / "assets").rglob("vram")), "the build tree is untouched")

    def test_the_staged_result_passes_both_checks(self):
        self.run_stage()
        with mock.patch.object(packager, "log"):
            packager.check_loose_vram_textures(self.app)
            coverage = packager.check_actor_vram_coverage(self.build, self.app, packager.ACTOR_SIDECAR_DIRS)
        self.assertEqual((coverage["glbs"], coverage["directories"], coverage["images"], coverage["sidecars"]),
                         (8, 7, 15, 14))
        self.assertEqual(coverage["excluded"], {"no_material_role": 1})
        self.assertEqual(coverage["families"]["races"], {"glbs": 2, "images": 3, "sidecars": 3, "excluded": {}})

    def test_owner_floors_procs_and_phasing_reach_the_tool(self):
        floors = {"normal_mean_deg": 1.5, "normal_p99_deg": 8.0}
        with mock.patch.object(packager, "ACTOR_SIDECAR_FLOORS", floors):
            receipt = self.run_stage(dirs=("races", "hair", "mounts", "equipment"), procs=1, measure_procs=2)
        argv = self.argv()
        self.assertEqual(json.loads(argv[argv.index("--floors") + 1]), floors)
        self.assertEqual((argv[argv.index("--procs") + 1], argv[argv.index("--measure-procs") + 1]), ("1", "2"))
        self.assertNotIn("creatures", [argv[i + 1] for i, arg in enumerate(argv) if arg == "--actor-dir"])
        self.assertEqual(receipt["floors"], floors)
        self.assertFalse((self.app / "assets/actors/native/creatures/vram").exists(), "phase A ships no creatures")
        with mock.patch.object(packager, "log"):
            packager.check_actor_vram_coverage(self.build, self.app, ("races", "hair", "mounts", "equipment"))

    def test_a_folder_the_build_tree_lacks_is_skipped(self):
        shutil.rmtree(self.build / "godot-client/assets/actors/native/mounts")
        receipt = self.run_stage()
        self.assertEqual(receipt["skipped"], ["mounts"])
        self.assertNotIn("mounts", [a for i, a in enumerate(self.argv()) if i and self.argv()[i - 1] == "--actor-dir"])

    def test_a_runner_build_links_into_the_stage_within_its_budget(self):
        storage = mock.Mock()
        storage.budget.capacity, storage.budget.reserve, storage.budget.roots = 10 * 1024**3, 1024**3, [self.scratch]
        with mock.patch.object(packager, "STORAGE", storage):
            self.run_stage()
        argv = self.argv()
        self.assertIn("--link-output", argv)
        self.assertGreater(int(argv[argv.index("--cache-budget-bytes") + 1]), 0)

    def test_a_failed_tool_fails_the_package_with_its_log(self):
        with mock.patch.dict(packager.os.environ, {"FAKE_ACTOR_TOOL_FAIL": "1"}):
            with self.assertRaisesRegex(packager.PackageError, "(?s)--actor-dir failed.*fake encoder broke"):
                self.run_stage()

    def test_no_summary_is_a_failure(self):
        for text in ("[00:00:00] done\n", "", "{\n \"encoded\": \n"):
            with self.assertRaises(packager.PackageError):
                packager._tool_summary(text)
        self.assertEqual(packager._tool_summary('{\n "a": {\n  "b": 1\n }\n}\n'), {"a": {"b": 1}})
        self.assertEqual(packager._tool_summary('[t] x {\n{\n "a": 2\n}\n'), {"a": 2})


class ActorSidecarChecks(unittest.TestCase):
    """check_loose_vram_textures and check_actor_vram_coverage on a staged actor result."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-actor-check-")).resolve()
        self.build = _actor_build_tree(self.scratch / "build")
        self.app = self.scratch / "stage" / "app"
        _stage_actor_glbs(self.build, self.app)
        with mock.patch.dict(packager.os.environ, {"REAL_VRAM_TOOL": str(REAL_TOOL)}), \
                mock.patch.object(packager, "log"):
            packager.stage_actor_vram_textures(self.build, self.scratch / "stage", Path("godot.exe"),
                                               self.scratch / "cache", self.scratch, self.app)
        self.native = self.app / "assets" / "actors" / "native"
        self.races = self.native / "races" / "vram"
        self.index = json.loads((self.races / "index.json").read_text(encoding="utf-8"))
        self.log = mock.patch.object(packager, "log")
        self.log.start()

    def tearDown(self):
        self.log.stop()
        shutil.rmtree(self.scratch, ignore_errors=True)

    def write_index(self):
        (self.races / "index.json").write_text(json.dumps(self.index), encoding="utf-8")

    def check(self, dirs=packager.ACTOR_SIDECAR_DIRS):
        packager.check_loose_vram_textures(self.app)
        return packager.check_actor_vram_coverage(self.build, self.app, dirs)

    def test_a_changed_sidecar_fails(self):
        entry = next(iter(self.index["images"].values()))
        (self.races / entry["file"]).write_bytes(b"changed")
        with self.assertRaisesRegex(packager.PackageError, "sha256 differs from the index"):
            self.check()

    def test_an_entry_without_its_sha256_is_a_build_problem(self):
        # Not a KeyError traceback out of the packager: a reported sidecar problem.
        del next(iter(self.index["images"].values()))["sha256"]
        self.write_index()
        with self.assertRaisesRegex(packager.PackageError, "sha256 differs from the index"):
            packager.check_loose_vram_textures(self.app)

    def test_a_missing_sidecar_fails(self):
        entry = next(iter(self.index["images"].values()))
        (self.races / entry["file"]).unlink()
        with self.assertRaisesRegex(packager.PackageError, "listed in the index but missing"):
            self.check()

    def test_a_stray_file_fails(self):
        (self.races / "report.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(packager.PackageError, "not named by the index"):
            self.check()

    def test_a_sidecar_folder_without_its_index_fails(self):
        (self.races / "index.json").unlink()
        with self.assertRaisesRegex(packager.PackageError, "sidecar folder without its index.json"):
            packager.check_loose_vram_textures(self.app)
        with self.assertRaisesRegex(packager.PackageError, "3 embedded images and no vram/index.json"):
            packager.check_actor_vram_coverage(self.build, self.app, packager.ACTOR_SIDECAR_DIRS)

    def test_an_index_naming_a_file_outside_its_folder_fails(self):
        sha, entry = next(iter(self.index["images"].items()))
        for name in ("../" + entry["file"], "sub/" + entry["file"], "C:" + entry["file"], "index.json"):
            with self.subTest(name=name):
                self.index["images"][sha] = dict(entry, file=name)
                self.write_index()
                with self.assertRaisesRegex(packager.PackageError, "unsafe sidecar file"):
                    packager.check_loose_vram_textures(self.app)

    def test_a_coverage_gap_fails(self):
        sha = next(iter(self.index["images"]))
        entry = self.index["images"].pop(sha)
        (self.races / entry["file"]).unlink()
        self.write_index()
        with self.assertRaisesRegex(packager.PackageError, f"races: embedded image {sha[:12]} has no sidecar"):
            self.check()

    def test_an_exclusion_with_a_reason_is_coverage(self):
        sha = next(iter(self.index["images"]))
        entry = self.index["images"].pop(sha)
        (self.races / entry["file"]).unlink()
        self.index["excluded"][sha] = "quality: psnr 28.6 < 30.0 at mip 3"
        self.write_index()
        coverage = self.check()
        self.assertEqual(coverage["excluded"], {"no_material_role": 1, "quality": 1})
        self.index["excluded"][sha] = " "
        self.write_index()
        with self.assertRaisesRegex(packager.PackageError, "no sidecar and no exclusion reason"):
            self.check()

    def test_a_sidecar_for_other_roles_fails(self):
        sha, entry = next((s, e) for s, e in self.index["images"].items() if e["roles"] == ["normal"])
        entry["roles"] = ["base"]
        self.write_index()
        with self.assertRaisesRegex(packager.PackageError, r"is for \['base'\], its GLBs sample it as \['normal'\]"):
            self.check()

    def test_an_index_entry_no_glb_embeds_fails(self):
        self.index["excluded"]["f" * 64] = "no_material_role"
        self.write_index()
        with self.assertRaisesRegex(packager.PackageError, "names ffffffffffff, which no GLB in that folder embeds"):
            self.check()

    def test_a_changed_staged_glb_fails(self):
        # The staged bytes, not the build tree's, are what the client hashes.
        shutil.copyfile(self.native / "races" / "human_male.glb", self.native / "creatures" / "wolf.glb")
        with self.assertRaisesRegex(packager.PackageError, "creatures: embedded image .* has no sidecar"):
            self.check()

    def test_an_index_outside_the_planned_folders_fails(self):
        shutil.copytree(self.races, self.native / "rl_heads" / "hair" / "vram")
        with self.assertRaisesRegex(packager.PackageError, "rl_heads/hair: an actor sidecar index outside"):
            self.check()
        shutil.rmtree(self.native / "rl_heads" / "hair" / "vram")
        with self.assertRaisesRegex(packager.PackageError, "native/creatures: an actor sidecar index outside"):
            self.check(dirs=("races", "hair", "mounts", "equipment"))

    def test_retired_and_rl_head_glbs_need_no_sidecar(self):
        coverage = self.check()
        self.assertEqual(coverage["families"]["creatures"]["glbs"], 2, "wolf and fox; not the retired beast")
        retired = json.loads((self.build / "godot-client/data/assets/retired_procedural_models.json")
                             .read_text(encoding="utf-8"))
        retired["runtimePaths"] = []
        (self.build / "godot-client/data/assets/retired_procedural_models.json").write_text(
            json.dumps(retired), encoding="utf-8")
        with self.assertRaisesRegex(packager.PackageError, "creatures: embedded image"):
            self.check()

    def test_an_unreadable_glb_fails(self):
        (self.native / "hair" / "short.glb").write_bytes(b"glTF\x02\x00\x00\x00")
        with self.assertRaisesRegex(packager.PackageError, "hair/short.glb: cannot read its images"):
            self.check()

    def test_the_self_test_folder_prefers_races_then_the_next_folder_with_a_sidecar(self):
        dirs = packager.ACTOR_SIDECAR_DIRS
        self.assertEqual(packager.actor_self_test_directory(self.app, dirs), "assets/actors/native/races")
        self.index["images"] = {}
        self.write_index()
        self.assertEqual(packager.actor_self_test_directory(self.app, dirs), "assets/actors/native/creatures")
        self.assertEqual(packager.actor_self_test_directory(self.app, ("races",)), None)


class ActorGlbReader(unittest.TestCase):
    """The coverage check's ranged reader finds exactly the images build_vram_textures.py plans."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-actor-reader-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def planned(self, glb):
        return [(index, sha) for index, sha, _ in packager.vram_tool.embedded_images(glb, self.scratch / "x")]

    def test_it_agrees_with_the_tool_on_every_fixture_glb(self):
        glbs = sorted((ACTOR_FIXTURE / "assets").rglob("*.glb"))
        self.assertGreaterEqual(len(glbs), 9)
        for glb in glbs:
            with self.subTest(glb=glb.name):
                document, images = packager._glb_embedded_images(glb)
                self.assertEqual(images, self.planned(glb))
                self.assertEqual(document, packager.vram_tool.glb_json(glb))

    @unittest.skipUnless((CHECKOUT / ".git").exists(), "needs the client's git checkout")
    def test_it_agrees_with_the_tool_on_real_actor_glbs(self):
        native = CLIENT / "assets" / "actors" / "native"
        sample = [path for name in ("races", "mounts", "hair/fitted") for path in sorted((native / name).glob("*.glb"))[:3]]
        sample += sorted((native / "creatures").glob("*.glb"))[:3] + sorted((native / "equipment").rglob("*.glb"))[:3]
        sample = [path for path in sample if path.is_file()]
        if not sample:
            self.skipTest("no actor GLBs checked out")
        for glb in sample:
            with self.subTest(glb=glb.name):
                self.assertEqual(packager._glb_embedded_images(glb)[1], self.planned(glb))

    def test_an_rlcz_envelope_reads_as_its_glb(self):
        source = ACTOR_FIXTURE / "assets/actors/native/creatures/wolf.glb"
        envelope = self.scratch / "wolf.glb"
        try:
            encoded = packager.creature_compression.encode(source.read_bytes())
        except packager.creature_compression.PayloadError as error:  # no zstandard module
            self.skipTest(str(error))
        envelope.write_bytes(encoded)
        self.assertEqual(envelope.read_bytes()[:4], packager.vram_tool.RLCZ_MAGIC)
        self.assertEqual(packager._glb_embedded_images(envelope), packager._glb_embedded_images(source))

    def test_malformed_files_raise(self):
        source = (ACTOR_FIXTURE / "assets/actors/native/races/human_male.glb").read_bytes()
        length = struct.unpack_from("<I", source, 12)[0]
        document = json.loads(source[20:20 + length])
        view = document["bufferViews"][document["images"][-1]["bufferView"]]
        inside_last_image = 20 + length + 8 + view.get("byteOffset", 0) + view["byteLength"] // 2
        # The BIN chunk declared shorter than the last image's view, its bytes still in the file.
        short_bin = bytearray(source)
        struct.pack_into("<I", short_bin, 20 + length, inside_last_image - (20 + length + 8))
        cases = {"not a glb": b"PNG not a glb", "truncated json": source[:40],
                 "truncated image": source[:inside_last_image], "view past the bin chunk": bytes(short_bin)}
        for label, data in cases.items():
            with self.subTest(label):
                path = self.scratch / (label.replace(" ", "_") + ".glb")
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    packager._glb_embedded_images(path)


class ActorSmoke(unittest.TestCase):
    """The smoke launch asks for and requires the actor self-test line when actor sidecars ship."""

    LINE = "actor_images self_test ok entries=50 format=bc7 mips=10 decompress=ok"

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-actor-smoke-"))
        self.app = self.scratch / "pkg" / "app"
        self.app.mkdir(parents=True)
        self.lines = packager.VRAM_SELF_TEST_OK + " entries=4 format=bc7 mips=7\n"
        self.seen = {}

        def fake_godot(binary, args, log_path, timeout=0, env=None, **kwargs):
            self.seen["env"] = dict(env or {})
            return self.lines
        self.patch = mock.patch.object(packager, "run_godot", fake_godot)
        self.patch.start()
        self.quiet = mock.patch.object(packager, "log")
        self.quiet.start()

    def tearDown(self):
        self.quiet.stop()
        self.patch.stop()
        shutil.rmtree(self.scratch, ignore_errors=True)

    def smoke(self, **options):
        packager.smoke_launch(self.app, self.scratch, {"binary": "RabbitLands.exe"}, vram_textures=True, **options)

    def test_without_actor_sidecars_nothing_is_asked(self):
        self.smoke()
        self.assertNotIn(packager.ACTOR_VRAM_SELF_TEST_VARIABLE, self.seen["env"])

    def test_the_line_is_asked_for_and_required(self):
        with self.assertRaisesRegex(packager.PackageError, "did not decode and decompress an actor sidecar"):
            self.smoke(actor_test="assets/actors/native/races")
        self.assertEqual(self.seen["env"]["ELORIA_ACTOR_VRAM_SELF_TEST"], "assets/actors/native/races")
        for bad in ("actor_images self_test failed index=missing",
                    "actor_images self_test ok entries=50 format=bc7 mips=10 decompress=failed",
                    "actor_images self_test ok entries=0 format=bc7 mips=10 decompress=ok",
                    "actor_images self_test ok entries=50 format=bc7 mips=0 decompress=ok",
                    "actor_images self_test ok entries=50 format=bc7 mips=10 decompress=okay"):
            with self.subTest(bad=bad):
                self.lines = packager.VRAM_SELF_TEST_OK + " entries=4\n" + bad + "\n"
                with self.assertRaisesRegex(packager.PackageError, "actor sidecar"):
                    self.smoke(actor_test="assets/actors/native/races")
        self.lines = packager.VRAM_SELF_TEST_OK + " entries=4\n" + self.LINE + "\n"
        self.smoke(actor_test="assets/actors/native/races")

    def test_an_unsafe_folder_is_refused_before_launching(self):
        for bad in ("../assets/actors/native/races", "assets/actors/native/races; rm -rf /", "assets/world/x",
                    "assets/actors/native/../../../x", "assets/actors/native/races dir"):
            with self.subTest(bad=bad):
                self.seen.clear()
                with self.assertRaisesRegex(packager.PackageError, "not an app-relative actor folder"):
                    self.smoke(actor_test=bad)
                self.assertNotIn("env", self.seen)


class ActorSidecarDecision(unittest.TestCase):
    """--actor-vram-textures: off by default and refused for releases until the release switch (schedule 1.1 #20)."""

    def setUp(self):
        self.build = Path(tempfile.mkdtemp(prefix="vram-actor-decide-")).resolve()
        self.reader = self.build / packager.ACTOR_VRAM_READER
        self.reader.parent.mkdir(parents=True)
        self.reader.write_text('print("actor_images self_test ok entries=%d ...")\n', encoding="utf-8")
        self.tool = self.build / packager.ACTOR_VRAM_TOOL
        self.tool.parent.mkdir(parents=True)
        self.tool.write_text('parser.add_argument("--actor-dir", action="append")\n', encoding="utf-8")
        self.quiet = mock.patch.object(packager, "log")
        self.quiet.start()

    def tearDown(self):
        self.quiet.stop()
        shutil.rmtree(self.build, ignore_errors=True)

    def decide(self, requested, no_vram=False, release_build=False, runner=False):
        return packager.actor_sidecar_dirs(self.build, requested, no_vram=no_vram, release_build=release_build,
                                           runner=runner)

    def test_not_release_enabled_yet(self):
        self.assertFalse(packager.ACTOR_SIDECARS_RELEASE_ENABLED, "release-enable only with AT-C4 and the smoke line")

    def test_off_unless_asked(self):
        self.assertEqual(self.decide(None), ())
        self.assertEqual(self.decide(False), ())
        self.assertEqual(self.decide(None, release_build=True, runner=True), (), "a runner build is unaffected")
        self.assertEqual(self.decide(True), packager.ACTOR_SIDECAR_DIRS)

    def test_a_release_or_runner_build_cannot_ask_yet(self):
        for kind in ({"release_build": True}, {"runner": True}):
            with self.subTest(**kind):
                with self.assertRaisesRegex(packager.PackageError, "not release-enabled yet"):
                    self.decide(True, **kind)

    def test_asking_without_vram_sidecars_fails(self):
        with self.assertRaisesRegex(packager.PackageError, "needs the VRAM sidecars"):
            self.decide(True, no_vram=True)

    def test_a_commit_without_the_reader_or_the_actor_mode_cannot_ship_them(self):
        self.reader.write_text("extends GLTFDocumentExtension\n", encoding="utf-8")
        self.assertIn("actor_images.gd", packager.actor_sidecar_support(self.build))
        with self.assertRaisesRegex(packager.PackageError, "has no actor sidecar reader"):
            self.decide(True)
        self.reader.write_text('"actor_images self_test ok"', encoding="utf-8")
        self.tool.write_text("# no actor mode\n", encoding="utf-8")
        with self.assertRaisesRegex(packager.PackageError, "has no actor mode"):
            self.decide(True)
        self.tool.unlink()
        self.assertIn("AT-C1", packager.actor_sidecar_support(self.build))

    def test_once_release_enabled_they_are_the_default_where_the_commit_has_them(self):
        with mock.patch.object(packager, "ACTOR_SIDECARS_RELEASE_ENABLED", True):
            self.assertEqual(self.decide(None, release_build=True, runner=True), packager.ACTOR_SIDECAR_DIRS)
            self.assertEqual(self.decide(False, release_build=True), ())
            self.assertEqual(self.decide(None, no_vram=True), (), "macOS and --no-vram-textures ship none")
            self.reader.unlink()
            self.assertEqual(self.decide(None), (), "an older commit is packaged without them")

    def test_rl_heads_can_never_be_a_sidecar_folder(self):
        with mock.patch.object(packager, "ACTOR_SIDECAR_DIRS", ("races", "rl_heads")):
            with self.assertRaisesRegex(packager.PackageError, "never planned"):
                self.decide(None)

    def test_the_command_line_offers_both_switches(self):
        text = (CLIENT / "tools" / "package_client.py").read_text(encoding="utf-8")
        self.assertIn('"--actor-vram-textures"', text)
        self.assertIn('"--no-actor-vram-textures"', text)


class ActorSelfTestLine(unittest.TestCase):
    """The packager and the client agree on the actor self-test variable and line (actor_images.gd, AT-C2)."""

    def test_the_variable_is_the_one_hardware_tier_documents(self):
        tier = (CLIENT / "src" / "runtime" / "hardware_tier.gd").read_text(encoding="utf-8")
        self.assertIn(f'const ACTOR_VRAM_SELF_TEST_VARIABLE := "{packager.ACTOR_VRAM_SELF_TEST_VARIABLE}"', tier)

    def test_the_client_prints_the_line_the_smoke_launch_requires(self):
        client = (CLIENT / "src" / "actors" / "actor_images.gd").read_text(encoding="utf-8")
        if packager.ACTOR_VRAM_SELF_TEST_OK not in client:
            self.skipTest("the actor sidecar reader (AT-C2) is not in this tree yet")
        for token in ("entries=", "format=", "mips=", "decompress="):
            self.assertIn(token, client)


@unittest.skipIf(SKIP_ENCODE, SKIP_ENCODE or "")
class ActorStageReal(unittest.TestCase):
    """The real tool, one encoder process, on the actor fixture: what a package stages passes every check."""

    def test_stage_check_and_rerun(self):
        scratch = Path(tempfile.mkdtemp(prefix="vram-actor-real-")).resolve()
        try:
            build = _actor_build_tree(scratch / "build", tool_text=None)
            stage = scratch / "stage"
            app = stage / "app"
            logs = scratch / "logs"
            logs.mkdir()
            _stage_actor_glbs(build, app)
            with mock.patch.object(packager, "log"):
                receipt = packager.stage_actor_vram_textures(build, stage, GODOT, scratch / "cache", logs, app,
                                                             procs=1, measure_procs=2)
                packager.check_loose_vram_textures(app)
                coverage = packager.check_actor_vram_coverage(build, app, packager.ACTOR_SIDECAR_DIRS)
            self.assertEqual(receipt["summary"]["actorGlbs"], 8)
            self.assertEqual((coverage["images"], coverage["sidecars"]), (15, 11))
            self.assertEqual(coverage["excluded"], {"size_not_multiple_of_4": 1, "role_conflict": 1,
                                                    "no_material_role": 1, "quality": 1})
            self.assertEqual(receipt["sidecars"], 11)
            self.assertEqual(receipt["selfTest"], "assets/actors/native/races")
            self.assertGreater(receipt["summary"]["encoded"], 0)
            self.assertFalse(list(app.rglob("report.json")))
            self.assertFalse(list((build / "godot-client" / "assets").rglob("vram")))
            self.assertTrue(list((scratch / "cache" / "_actors").glob("*.evt")), "actor encodes live in _actors/")
            # A second package from the same cache encodes nothing and stages the same indexes.
            first = {p.relative_to(app).as_posix(): p.read_bytes() for p in app.rglob("vram/index.json")}
            shutil.rmtree(stage)
            _stage_actor_glbs(build, app)
            with mock.patch.object(packager, "log"):
                again = packager.stage_actor_vram_textures(build, stage, GODOT, scratch / "cache", logs, app,
                                                           procs=1, measure_procs=2)
            self.assertEqual(again["summary"]["encoded"], 0)
            self.assertEqual({p.relative_to(app).as_posix(): p.read_bytes() for p in app.rglob("vram/index.json")},
                             first)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


@unittest.skipIf(SKIP_ENCODE, SKIP_ENCODE or "")
class Stage(unittest.TestCase):
    def test_stage_builds_checks_and_ships_only_index_and_sidecars(self):
        scratch = Path(tempfile.mkdtemp(prefix="vram-package-stage-"))
        try:
            build = scratch / "build"
            stage = scratch / "stage"
            logs = scratch / "logs"
            logs.mkdir()
            shutil.copytree(FIXTURE, build / MAP, ignore=shutil.ignore_patterns("vram", "*.py"))
            shutil.copytree(build / MAP, stage / MAP)
            staged = packager.stage_vram_textures(build, stage, GODOT, scratch / "cache", logs,
                                                  tool=CLIENT / "tools" / "build_vram_textures.py")
            vram = stage / MAP / "shared-assets" / "vram"
            self.assertEqual(sorted(p.suffix for p in vram.iterdir()), [".evt"] * 4 + [".json"])
            self.assertEqual(staged["files"], 5)
            self.assertTrue(any(logs.glob("vram-report-*.json")), "the quality report goes to the logs")
            self.assertFalse((build / MAP / "shared-assets" / "vram").exists(),
                             "nothing is written into the build worktree")
            packager.check_vram_textures(stage)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
