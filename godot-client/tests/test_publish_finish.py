"""The pass a publisher runs on the package it has just written.

`eloria-assets/tools/publish_finish.py` is what makes a republished map arrive
shared, externalised and quantised instead of waiting for someone to run the
three tree-wide passes by hand. Four properties decide whether a publisher can
trust it:

  * it adopts the pool. A prop the pool already holds is named, not copied,
    even where the publisher wrote it once - that is the whole difference
    between a scoped pass and the tree-wide one.
  * it pools what the publisher repeated, so a region's own kit does not ship
    once per chunk while it waits for the next tree-wide run.
  * the figures a manifest records about its own GLB follow the file.
    audit_continent.py and _continent_v2/tests/test_publish_client_geometry.py
    read them back and compare, so a pass that shrinks a GLB and leaves them
    alone publishes a package that fails its own contracts. That includes the
    props it moved out: a streamed cell states the prototypes its chunk draws,
    which the client's chunk budget counts once while any resident cell does.
  * running it again changes nothing, so a publisher may call it unconditionally.

A region master past 90 MiB continues in sibling part files, which are ordinary
glTF external buffers; reading one as though every view lived in the GLB's own
binary is how 1,150 meshes across four masters came to be repacked from the
wrong bytes, so the reader is checked here too.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
REPO = CLIENT.parent
TOOLS = REPO / "eloria-assets" / "tools"
TOOL = TOOLS / "publish_finish.py"
sys.path.insert(0, str(TOOLS))
import shared_meshes as SM  # noqa: E402

PROP_TRIANGLES = 400


def prop(seed: float = 0.0) -> tuple[dict, bytes]:
    """One mesh, placed twice, with normals to quantise and indices to keep."""
    positions = b"".join(struct.pack("<3f", seed + i, seed + i * 0.5, seed - i)
                         for i in range(3 * PROP_TRIANGLES))
    normals = struct.pack("<3f", 0.0, 1.0, 0.0) * (3 * PROP_TRIANGLES)
    indices = struct.pack("<%dH" % (3 * PROP_TRIANGLES), *range(3 * PROP_TRIANGLES))
    binary = positions + normals + indices
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [{"name": "Oak_a", "mesh": 0, "translation": [1, 0, 0]},
                  {"name": "Oak_b", "mesh": 0, "translation": [9, 0, 0]}],
        "meshes": [{"name": "prop", "primitives": [
            {"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}]}],
        "materials": [{"name": "bark", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3 * PROP_TRIANGLES, "type": "VEC3",
             "min": [0, 0, 0], "max": [1, 1, 1]},
            {"bufferView": 1, "componentType": 5126, "count": 3 * PROP_TRIANGLES, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": 3 * PROP_TRIANGLES, "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(normals)},
            {"buffer": 0, "byteOffset": len(positions) + len(normals), "byteLength": len(indices)},
        ],
        "buffers": [{"byteLength": len(binary)}],
    }
    return document, binary


class PublishFinishTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="publish-finish-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.env = dict(os.environ, ELORIA_MAPS_ROOT=str(self.root))

    # --- a package to finish -------------------------------------------------

    def package(self, name: str, cells: int = 2, factor: float | None = None,
                seed: float = 0.0) -> Path:
        """A streamed package: a parent manifest and `cells` chunks of one prop."""
        package = self.root / "nymara-regions" / name
        chunks = []
        for cell in range(cells):
            identifier = "%02d_00" % cell
            chunk = package / "chunks" / identifier
            chunk.mkdir(parents=True)
            document, binary = prop(seed)
            (chunk / "world.glb").write_bytes(SM.write_glb(document, binary))
            (chunk / "world.json").write_text(json.dumps({
                "asset": {"id": f"{name}__chunk_{identifier}", "glb": "world.glb"},
                "performance": {"glbBytes": 1, "nodes": 99, "meshes": 99},
            }, indent=2) + "\n", encoding="utf-8")
            chunks.append({"id": identifier, "manifest": f"chunks/{identifier}/world.json",
                           "glbBytes": 1, "geometryResidentBytes": 5, "estimatedResidentBytes": 105,
                           "sharedResourceResidentBytes": {"deadbeef": 100}})
        (package / "world.json").write_text(json.dumps({
            "asset": {"id": name, "glb": "world.glb"},
            "streamingChunks": {"maximumResidentBytes": 268435456, "chunks": chunks},
        }, indent=2) + "\n", encoding="utf-8")
        if factor is not None:
            (package / "publication.json").write_text(
                json.dumps({"geometryResidentFactor": factor}) + "\n", encoding="utf-8")
        return package

    def finish(self, *paths) -> str:
        done = subprocess.run([sys.executable, str(TOOL), *[str(p) for p in paths]],
                              capture_output=True, text=True, env=self.env, cwd=str(REPO))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def pool(self) -> list[Path]:
        return sorted((self.root / "_shared" / "meshes").glob("*.glb"))

    # --- the properties ------------------------------------------------------

    def test_it_pools_what_the_publisher_repeated(self):
        package = self.package("town")
        self.finish(package)
        self.assertEqual(len(self.pool()), 1, "the prop in both cells becomes one prototype")
        for cell in ("00_00", "01_00"):
            chunk = package / "chunks" / cell
            document, _ = SM.read_glb(chunk / "world.glb")
            self.assertEqual(document.get("meshes", []), [], "the copy left the package")
            self.assertEqual([node["name"] for node in document["nodes"]], ["Oak_a", "Oak_b"])
            manifest = json.loads((chunk / "world.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest[SM.MANIFEST_KEY]), 1)
            for uri, digest in manifest[SM.MANIFEST_KEY].items():
                target = (chunk / uri).resolve()
                self.assertEqual(SM.sha256(target.read_bytes()), digest, "the recorded sha is the file's")

    def test_it_adopts_a_prototype_the_pool_already_holds(self):
        self.finish(self.package("town"))
        pooled = self.pool()
        # A second package the publisher writes later, holding the same prop
        # once: the tree-wide rule would leave it embedded.
        single = self.package("hamlet", cells=1)
        self.finish(single)
        self.assertEqual(self.pool(), pooled, "no second prototype for the same prop")
        document, _ = SM.read_glb(single / "chunks" / "00_00" / "world.glb")
        self.assertEqual(document.get("meshes", []), [])
        self.assertIn(SM.PROTOTYPE_FIELD, document["nodes"][0]["extras"][SM.EXTRAS_KEY])

    def test_a_distinct_prop_in_one_file_stays_embedded(self):
        single = self.package("lonely", cells=1, seed=17.0)
        self.finish(single)
        self.assertEqual(self.pool(), [], "nothing else holds it, so a prototype would only cost")
        document, _ = SM.read_glb(single / "chunks" / "00_00" / "world.glb")
        self.assertEqual(len(document["meshes"]), 1)

    def test_recorded_figures_follow_the_files(self):
        import publish_finish as PF
        for name, factor, expected in (("town", None, PF.LEGACY_RESIDENT_FACTOR), ("declared", 2.5, 2.5)):
            package = self.package(name, factor=factor)
            self.finish(package)
            index = json.loads((self.root / "_shared" / "meshes" / "index.json").read_text(encoding="utf-8"))
            manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
            for cell in manifest["streamingChunks"]["chunks"]:
                chunk = package / Path(cell["manifest"]).parent
                size = (chunk / "world.glb").stat().st_size
                self.assertEqual(cell["glbBytes"], size, f"{name}: the figure is the shipped GLB's")
                self.assertEqual(cell["geometryResidentBytes"], math.ceil(expected * size), name)
                child = json.loads((chunk / "world.json").read_text(encoding="utf-8"))
                drawn = {Path(uri).stem for uri in child[SM.MANIFEST_KEY]}
                self.assertEqual(len(drawn), 1, name)
                self.assertEqual(cell["sharedMeshResidentBytes"],
                                 {key: math.ceil(expected * index["prototypes"][key]["bytes"]) for key in drawn},
                                 f"{name}: the prop it moved out, at the cell's own factor")
                self.assertEqual(list(cell).index("sharedMeshResidentBytes"),
                                 list(cell).index("sharedResourceResidentBytes") + 1,
                                 "written beside the image figures, not wherever")
                self.assertEqual(cell["estimatedResidentBytes"],
                                 cell["geometryResidentBytes"]
                                 + sum(cell["sharedResourceResidentBytes"].values())
                                 + sum(cell["sharedMeshResidentBytes"].values()), name)
                self.assertEqual(child["performance"]["glbBytes"], size, name)
                self.assertEqual(child["performance"]["meshes"], 0, "the meshes moved to the pool")
                self.assertEqual(child["performance"]["nodes"], 2, name)

    def test_a_cell_counts_the_prototypes_its_chunk_draws(self):
        """What the client's budget counts for a pooled prop: one entry per
        prototype a chunk names, sized from the pool's index, and nothing for a
        chunk that draws none. A prototype placed twice is still one mesh."""
        package = self.package("town", cells=3, factor=5.0)
        lonely = package / "chunks" / "02_00" / "world.glb"
        lonely.write_bytes(SM.write_glb(*prop(17.0)))
        self.finish(package)
        index = json.loads((self.root / "_shared" / "meshes" / "index.json").read_text(encoding="utf-8"))
        (identity, entry), = index["prototypes"].items()
        cells = {cell["id"]: cell for cell in json.loads(
            (package / "world.json").read_text(encoding="utf-8"))["streamingChunks"]["chunks"]}
        for shared in ("00_00", "01_00"):
            self.assertEqual(cells[shared]["sharedMeshResidentBytes"], {identity: 5 * entry["bytes"]},
                             "both placements draw the one prototype, counted once")
        self.assertNotIn("sharedMeshResidentBytes", cells["02_00"], "its prop stayed embedded")
        self.assertEqual(cells["02_00"]["estimatedResidentBytes"],
                         cells["02_00"]["geometryResidentBytes"] + 100)

    def test_the_index_figure_wins_and_the_file_stands_in(self):
        """The pool's index is what the packager checks a prototype against; a
        prototype it does not list yet is sized from its file."""
        import publish_finish as PF
        pool = self.root / "_shared" / "meshes"
        pool.mkdir(parents=True)
        (pool / ("a" * 64 + ".glb")).write_bytes(b"x" * 300)
        (pool / ("b" * 64 + ".glb")).write_bytes(b"x" * 700)
        (pool / "index.json").write_text(json.dumps({"prototypes": {"a" * 64: {"bytes": 1000}}}),
                                         encoding="utf-8")
        chunk = self.root / "maps" / "chunks" / "00_00"
        chunk.mkdir(parents=True)
        child = {SM.MANIFEST_KEY: {os.path.relpath(pool / f"{key * 64}.glb", chunk).replace("\\", "/"): "0"
                                   for key in "abc"}}
        self.assertEqual(PF.prototype_figures(child, chunk / "world.json", 1.0, {}),
                         {"a" * 64: 1000, "b" * 64: 700},
                         "the index's bytes, else the file's; a missing file draws nothing and costs nothing")
        self.assertEqual(PF.prototype_figures(child, chunk / "world.json", 5.0, {}),
                         {"a" * 64: 5000, "b" * 64: 3500})

    def test_a_publication_record_keeps_the_manifest_estimate(self):
        package = self.package("sw_isle", factor=1.0)
        (package / "publication.json").write_text(json.dumps(
            {"geometryResidentFactor": 1.0, "estimatedResidentMiB": {"00_00": 0.0, "01_00": 0.0}},
            indent=1) + "\n", encoding="utf-8")
        self.finish(package)
        record = json.loads((package / "publication.json").read_text(encoding="utf-8"))
        manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
        self.assertEqual(record["estimatedResidentMiB"],
                         {cell["id"]: round(cell["estimatedResidentBytes"] / 1048576, 1)
                          for cell in manifest["streamingChunks"]["chunks"]})
        self.assertEqual(SM.manifest_indent((package / "publication.json").read_text(encoding="utf-8")), 1)

    def test_the_figures_a_publisher_declares_win(self):
        import publish_finish as PF
        self.assertEqual(PF.resident_factor(self.root, 2.5), 2.5,
                         "a publisher that has not written publication.json yet says so itself")
        self.assertEqual(PF.resident_factor(self.root), PF.LEGACY_RESIDENT_FACTOR)
        self.assertEqual(PF.LEGACY_RESIDENT_FACTOR, 1.0, "owner call 2026-10-16: legacy maps count 1 x their GLB")

    def test_normals_are_quantised_and_the_geometry_is_kept(self):
        package = self.package("town")
        before = (package / "chunks" / "00_00" / "world.glb").stat().st_size
        self.finish(package)
        prototype, binary = SM.read_glb(self.pool()[0])
        attributes = prototype["meshes"][0]["primitives"][0]["attributes"]
        normal = prototype["accessors"][attributes["NORMAL"]]
        self.assertEqual(normal["componentType"], 5120, "a unit normal is stored as bytes")
        self.assertTrue(normal["normalized"])
        position = prototype["accessors"][attributes["POSITION"]]
        self.assertEqual(position["componentType"], 5126, "positions keep their floats")
        original, source = prop()
        self.assertEqual(SM.accessor_bytes(prototype, binary, attributes["POSITION"]),
                         SM.accessor_bytes(original, source, 0), "positions are byte-identical")
        self.assertLess((package / "chunks" / "00_00" / "world.glb").stat().st_size, before)

    def test_running_it_again_changes_nothing(self):
        package = self.package("town")
        self.finish(package)
        stamp = {path: path.read_bytes() for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.finish(package)
        after = {path: path.read_bytes() for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(sorted(stamp), sorted(after), "no file appears or disappears")
        for path, data in stamp.items():
            self.assertEqual(data, after[path], f"{path.relative_to(self.root)} changed on a second run")

    def test_a_manifest_keeps_its_own_shape(self):
        package = self.package("town")
        narrow = package / "chunks" / "00_00" / "world.json"
        narrow.write_bytes(json.dumps(json.loads(narrow.read_text(encoding="utf-8")),
                                      indent=1).encode("utf-8") + b"\n")
        self.finish(package)
        self.assertEqual(SM.manifest_indent(narrow.read_text(encoding="utf-8")), 1,
                         "continent-v2 writes one space and must keep it")
        self.assertEqual(SM.manifest_indent(
            (package / "chunks" / "01_00" / "world.json").read_text(encoding="utf-8")), 2)

    def test_pooling_a_new_prop_keeps_the_references_already_named(self):
        """A file that already places pooled props and gains a new repeated one
        must still name every prototype it places: a reference the manifest
        drops draws nothing in the client, and the packager does not ship it."""
        package = self.package("town")
        self.finish(package)
        first = {path.stem for path in self.pool()}
        for cell in ("00_00", "01_00"):
            glb = package / "chunks" / cell / "world.glb"
            glb.write_bytes(SM.write_glb(*with_prop(*SM.read_glb(glb), seed=31.0)))
        self.finish(package)
        self.assertEqual(len(self.pool()), 2, "the new prop is pooled too")
        for cell in ("00_00", "01_00"):
            chunk = package / "chunks" / cell
            document, _ = SM.read_glb(chunk / "world.glb")
            placed = {node["extras"][SM.EXTRAS_KEY][SM.PROTOTYPE_FIELD] for node in document["nodes"]}
            self.assertTrue(first < placed, "the old placements still name the first prototype")
            manifest = json.loads((chunk / "world.json").read_text(encoding="utf-8"))
            named = {Path(uri).stem for uri in manifest[SM.MANIFEST_KEY]}
            self.assertEqual(named, placed, f"{cell}: the manifest names exactly what the file places")


def with_prop(document: dict, binary: bytes, seed: float) -> tuple[dict, bytes]:
    """`document` with prop(seed) added as one more placed mesh."""
    extra, extra_binary = prop(seed)
    document = json.loads(json.dumps(document))
    packed = bytearray(binary)
    packed.extend(b"\0" * ((-len(packed)) % 4))
    base = len(packed)
    packed.extend(extra_binary)
    views = len(document.setdefault("bufferViews", []))
    for view in extra["bufferViews"]:
        document["bufferViews"].append(dict(view, byteOffset=base + view["byteOffset"]))
    accessors = len(document.setdefault("accessors", []))
    for accessor in extra["accessors"]:
        document["accessors"].append(dict(accessor, bufferView=views + accessor["bufferView"]))
    materials = len(document.setdefault("materials", []))
    document["materials"] += extra["materials"]
    primitive = extra["meshes"][0]["primitives"][0]
    document.setdefault("meshes", []).append({"name": "rock", "primitives": [{
        "attributes": {key: accessors + value for key, value in primitive["attributes"].items()},
        "indices": accessors + primitive["indices"], "material": materials + primitive["material"]}]})
    document["nodes"].append({"name": "Rock", "mesh": len(document["meshes"]) - 1})
    document["scenes"][0]["nodes"].append(len(document["nodes"]) - 1)
    document["buffers"] = [{"byteLength": len(packed)}]
    return document, bytes(packed)


class PartFileReaderTest(unittest.TestCase):
    """A GLB whose binary continues in a sibling part file."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="publish-finish-parts-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def split(self) -> tuple[Path, bytes]:
        """Write the prop with its indices in an external buffer, as dump_glb does."""
        document, binary = prop()
        views = document["bufferViews"]
        tail = binary[views[2]["byteOffset"]:]
        head = binary[:views[2]["byteOffset"]]
        views[2] = {"buffer": 1, "byteOffset": 0, "byteLength": len(tail)}
        document["buffers"] = [{"byteLength": len(head)}, {"uri": "world.part1.bin", "byteLength": len(tail)}]
        path = self.root / "world.glb"
        path.write_bytes(SM.write_glb(document, head))
        (self.root / "world.part1.bin").write_bytes(tail)
        return path, tail

    def test_a_view_in_a_part_file_is_read_from_it(self):
        path, tail = self.split()
        document, binary = SM.read_glb(path)
        self.assertEqual(len(document["buffers"]), 1, "the parts are folded into one binary")
        self.assertEqual(SM.view_bytes(document, binary, 2), tail,
                         "the indices come from the part file, not from the GLB at that offset")
        self.assertEqual(SM.accessor_bytes(document, binary, 2), tail)

    def test_writing_it_whole_removes_the_orphaned_part(self):
        path, _ = self.split()
        document, binary = SM.read_glb(path)
        SM.write_package_glb(path, SM.write_glb(document, binary))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["world.glb"],
                         "a part file the GLB no longer names would ship as dead weight")

    def test_a_file_that_cannot_fit_is_refused(self):
        with self.assertRaises(ValueError):
            SM.write_package_glb(self.root / "huge.glb", b"x" * (SM.PACKAGE_FILE_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
