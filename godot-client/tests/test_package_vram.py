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
        for invalid in ([], "shared-assets", ["../../../../outside"], ["C:/outside"]):
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

        def copy_file(source: Path, target: Path) -> int:
            staged.add(target.relative_to(stage).as_posix())
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
