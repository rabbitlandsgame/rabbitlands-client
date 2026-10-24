"""Targeted source-closure and native-catalog validation fixtures."""
from pathlib import Path
import importlib.util
import json
import struct
import sys
import tempfile
import unittest

MODULE_PATH=Path(__file__).resolve().parents[1]/"tools/prepared_content_package.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC=importlib.util.spec_from_file_location("prepared_content_package",MODULE_PATH)
prepared=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepared)


def glb(document,binary=b""):
    text=json.dumps(document).encode()
    text+=b" "*((-len(text))%4)
    binary+=b"\0"*((-len(binary))%4)
    body=struct.pack("<II",len(text),0x4E4F534A)+text
    if binary: body+=struct.pack("<II",len(binary),0x004E4942)+binary
    return struct.pack("<4sII",b"glTF",2,len(body)+12)+body


def write_pck(path, rows):
    """Independent PCK4 writer; deliberately non-content MD5 directory fields."""
    header_size=104
    data=b"".join(content for _name,content in rows)
    directory=header_size+len(data)
    header=b"GDPC"+struct.pack("<4IIQQ",4,4,7,2,2,header_size,directory)+bytes(64)
    table=bytearray(struct.pack("<I",len(rows)))
    offset=0
    for name,content in rows:
        encoded=name.encode()
        encoded+=bytes((-len(encoded))%4)
        table+=struct.pack("<I",len(encoded))+encoded
        table+=struct.pack("<QQ",offset,len(content))+b"m"*16+struct.pack("<I",0)
        offset+=len(content)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(header+data+table)


class PreparedPackageTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repository=Path(self.directory.name)
        self.project=self.repository/"godot-client"
        (self.project/"assets/world").mkdir(parents=True)
        (self.repository/"eloria-assets").mkdir()

    def test_embedded_buffer_view_images_are_inventory_not_external_uris(self):
        source=self.project/"assets/world/synthetic.glb"
        source.write_bytes(glb({"asset":{"version":"2.0"},"buffers":[{"byteLength":8}],
            "bufferViews":[{"buffer":0,"byteOffset":2,"byteLength":4}],
            "images":[{"bufferView":0,"mimeType":"image/jpeg"}]},b"00JPEG00"))
        closure=prepared.Closure(self.project)
        closure.visit(source)
        self.assertEqual(set(closure.files),{"godot-client/assets/world/synthetic.glb"})
        self.assertEqual(closure.images[0]["storage"],"bufferView")
        self.assertEqual(closure.images[0]["sha256"],prepared.hashlib.sha256(b"JPEG").hexdigest())
        self.assertEqual(closure.images[0]["mime"],"image/jpeg")

    def test_external_image_import_closure_hashes_actual_remap_and_product(self):
        source=self.project/"assets/world/synthetic.glb"
        source.write_bytes(glb({"asset":{"version":"2.0"},"images":[{"uri":"external.jpg"}]}))
        product=self.project/".godot/imported/external.s3tc.ctex"
        product.parent.mkdir(parents=True)
        product.write_bytes(b"synthetic imported product")
        remap=self.project/"assets/world/external.jpg.import"
        remap.write_text('[remap]\npath="res://.godot/imported/external.s3tc.ctex"\n',encoding="utf-8")
        closure=prepared.Closure(self.project)
        closure.visit(source)
        self.assertIn("godot-client/.godot/imported/external.s3tc.ctex",closure.files)
        self.assertIn("godot-client/assets/world/external.jpg.import",closure.files)
        self.assertNotIn("godot-client/assets/world/external.jpg",closure.files)
        product.write_bytes(b"changed imported product")
        self.assertNotEqual(closure.files["godot-client/.godot/imported/external.s3tc.ctex"],prepared.digest(product))

    def test_uri_escape_and_malformed_glb_do_not_form_a_partial_job(self):
        source=self.project/"assets/world/synthetic.glb"
        source.write_bytes(glb({"asset":{"version":"2.0"},"images":[{"uri":"../../../../outside.jpg"}]}))
        with self.assertRaises(prepared.PreparedError):
            prepared.Closure(self.project).visit(source)
        source.write_bytes(glb({"asset":{"version":"2.0"}})[:-1])
        with self.assertRaises(prepared.PreparedError):
            prepared.gltf(source)

    def test_equipped_actor_uses_fit_catalog_components_not_a_composite(self):
        catalog=self.project/"data/actors"
        catalog.mkdir(parents=True)
        (catalog/"models.json").write_text(json.dumps({"models":{"luminous_male":{
            "scene":"res://body.glb","animationLibrary":"res://library.glb",
            "hairStyles":["res://unreachable-bald.glb","","","","res://fitted-hair.glb"]}}}),encoding="utf-8")
        equipment={"fitGroups":{"luminous_male":["canonical_human_male"]},"models":{},"aliases":{}}
        for slot,item in prepared.FULL_KIT_A.items():
            equipment["models"][f"{slot}:{item}"]={"scene":f"res://wrong-{slot}.glb",
                "variants":{"canonical_human_male":{"scene":f"res://fit-{slot}.glb"}}}
        (catalog/"equipment.json").write_text(json.dumps(equipment),encoding="utf-8")
        sources=prepared.resolve_equipped_actor(self.project)
        self.assertEqual(len(sources),10)
        self.assertTrue(all(f"godot-client/fit-{slot}.glb" in sources for slot in prepared.FULL_KIT_A))
        self.assertFalse(any("wrong" in source for source in sources))
        self.assertIn("godot-client/fitted-hair.glb",sources)
        self.assertNotIn("godot-client/unreachable-bald.glb",sources)

    def test_cook_job_refuses_player_profile_or_unmarked_project(self):
        job=self.repository/"job.json"
        user=self.repository/"isolated-appdata"
        targets=[("scene","godot-client/assets/world/synthetic.glb")]
        with self.assertRaises(prepared.PreparedError):
            prepared.write_job(self.project,"full","res://prepared-content/test",targets,job,user)
        (self.project/".prepared-cook-project.json").write_text('{"purpose":"disposable-native-cook"}',encoding="utf-8")
        user.mkdir()
        (user/"existing-profile").write_text("keep",encoding="utf-8")
        with self.assertRaises(prepared.PreparedError):
            prepared.write_job(self.project,"full","res://prepared-content/test",targets,job,user)
        self.assertFalse(job.exists())

    def _import_fixture(self, include_product=True):
        source=self.project/"assets/world/synthetic.glb"
        source.write_bytes(glb({"asset":{"version":"2.0"},"images":[{"uri":"external.jpg"}]}))
        product=self.project/".godot/imported/external.s3tc.ctex"
        product.parent.mkdir(parents=True)
        product.write_bytes(b"original editor product")
        remap=self.project/"assets/world/external.jpg.import"
        full=b'[remap]\npath="res://.godot/imported/external.s3tc.ctex"\n\n[deps]\nsource_file="res://assets/world/external.jpg"\n\n[params]\ncompress/mode=2\n'
        runtime=b'[remap]\npath="res://.godot/imported/external.s3tc.ctex"\n\x00'
        remap.write_bytes(full)
        stage=self.repository/"stage"
        rows=[("assets/world/external.jpg.import",runtime)]
        if include_product: rows.append((".godot/imported/external.s3tc.ctex",b"actual exported product"))
        write_pck(stage/"app/RabbitLands.pck",rows)
        (self.project/".prepared-cook-project.json").write_text('{"purpose":"disposable-native-cook"}',encoding="utf-8")
        return stage,source,remap,product,full,runtime

    def test_actual_export_snapshot_preserves_remap_nul_and_original_provenance(self):
        stage,source,remap,product,full,runtime=self._import_fixture()
        target=[("scene","godot-client/assets/world/synthetic.glb")]
        receipt=prepared.snapshot_runtime_imports(self.project,stage,target)
        self.assertEqual(remap.read_bytes(),runtime)
        self.assertEqual(product.read_bytes(),b"actual exported product")
        rows={row["path"]:row for row in receipt["records"]}
        record=rows["godot-client/assets/world/external.jpg.import"]
        self.assertEqual(record["source_sha256"],prepared.hashlib.sha256(full).hexdigest())
        self.assertEqual(record["sha256"],prepared.hashlib.sha256(runtime).hexdigest())
        self.assertNotEqual(record["source_sha256"],record["sha256"])
        job=self.repository/"job.json"
        prepared.write_job(self.project,"full","res://prepared-content/exact",target,job,self.repository/"fresh-user")
        spec=json.loads(job.read_text())["targets"][0]
        self.assertEqual(spec["runtime_import_snapshot"]["policy"],prepared.RUNTIME_IMPORT_POLICY)
        self.assertEqual(len(spec["runtime_import_snapshot"]["records"]),2)
        self.assertEqual({row["path"]:row["sha256"] for row in spec["inputs"]}[record["path"]],record["sha256"])

    def test_missing_export_product_fails_before_any_disposable_input_is_replaced(self):
        stage,source,remap,product,full,runtime=self._import_fixture(include_product=False)
        with self.assertRaises(prepared.PreparedError):
            prepared.snapshot_runtime_imports(self.project,stage,[("scene","godot-client/assets/world/synthetic.glb")])
        self.assertEqual(remap.read_bytes(),full)
        self.assertEqual(product.read_bytes(),b"original editor product")
        self.assertFalse((self.project/prepared.RUNTIME_IMPORT_MARKER).exists())

    def test_imported_job_requires_actual_runtime_snapshot_instead_of_guessing_exporter_serialization(self):
        stage,source,remap,product,full,runtime=self._import_fixture()
        with self.assertRaises(prepared.PreparedError):
            prepared.write_job(self.project,"full","res://prepared-content/exact",
                [("scene","godot-client/assets/world/synthetic.glb")],self.repository/"job.json",self.repository/"fresh-user")

    def test_package_checks_original_provenance_and_actual_final_export_separately(self):
        stage,source,remap,product,full,runtime=self._import_fixture()
        target=[("scene","godot-client/assets/world/synthetic.glb")]
        prepared.snapshot_runtime_imports(self.project,stage,target)
        closure=prepared.Closure(self.project)
        closure.visit(source)
        provenance=prepared.runtime_import_provenance(self.project,closure.files)
        generation=self.repository/"generation"
        generation.mkdir()
        payload=b"synthetic native payload"
        payload_sha=prepared.hashlib.sha256(payload).hexdigest()
        (generation/(payload_sha+".res")).write_bytes(payload)
        entry={"kind":"scene","source":"godot-client/assets/world/synthetic.glb",
            "source_digest":prepared.digest(source),"texture_token":"fixture","entry_id":"0"*64,
            "resource":"res://prepared-content/"+payload_sha+".res",
            "inputs":[{"path":name,"sha256":sha} for name,sha in sorted(closure.files.items())],
            "payloads":[{"path":"res://prepared-content/"+payload_sha+".res","sha256":payload_sha}],
            "metadata_json":json.dumps({"runtime_import_snapshot":provenance},separators=(",",":"))}
        catalog={"schema_version":1,"policy":prepared.POLICY,"entries":[entry]}
        index=generation/"index.json"
        index.write_text(json.dumps(catalog),encoding="utf-8")
        normal=self.repository/"normal/godot-client"
        (normal/"assets/world").mkdir(parents=True)
        (normal/".godot/imported").mkdir(parents=True)
        (normal/"assets/world/external.jpg.import").write_bytes(full)
        (normal/".godot/imported/external.s3tc.ctex").write_bytes(b"original editor product")
        loose=stage/"app/assets/world/synthetic.glb"
        loose.parent.mkdir(parents=True)
        loose.write_bytes(source.read_bytes())
        receipt=prepared.install_generation(index,normal,stage)
        self.assertEqual(receipt["entries"],1)
        rows=[("assets/world/external.jpg.import",runtime),
            (".godot/imported/external.s3tc.ctex",b"actual exported product"),
            ("prepared-content/index.json",index.read_bytes()),("prepared-content/"+payload_sha+".res",payload)]
        write_pck(stage/"app/RabbitLands.pck",rows)
        self.assertEqual(prepared.check_export(index,stage)["status"],"complete")
        rows[0]=("assets/world/external.jpg.import",runtime.rstrip(b"\0"))
        write_pck(stage/"app/RabbitLands.pck",rows)
        with self.assertRaises(prepared.PreparedError):prepared.check_export(index,stage)


    def test_authoritative_float_metadata_wire_survives_python_merge_unchanged(self):
        # These are full-precision Godot-style rest/clip number lexemes. The
        # outer Python parser/serializer must never interpret these numbers.
        wire='{"rigs":[{"rest":[-0.17259597778320313,0.17259597778320313,2.9802322387695313e-08],"clip":3.1415926535897931}],"runtime_import_snapshot":{}}'
        source=self.project/"assets/world/synthetic.glb"
        source.write_bytes(b"synthetic source bytes")
        generation=self.project/"prepared-content/fixture"
        generation.mkdir(parents=True)
        payload=b"synthetic native payload"
        sha=prepared.hashlib.sha256(payload).hexdigest()
        native=generation/(sha+".res")
        native.write_bytes(payload)
        entry={"kind":"scene","source":"godot-client/assets/world/synthetic.glb",
            "source_digest":prepared.digest(source),"texture_token":"fixture","entry_id":"a"*64,
            "resource":"res://prepared-content/fixture/"+sha+".res",
            "inputs":[{"path":"godot-client/assets/world/synthetic.glb","sha256":prepared.digest(source)}],
            "payloads":[{"path":"res://prepared-content/fixture/"+sha+".res","sha256":sha}],
            "metadata_json":wire}
        index=generation/"index.json"
        index.write_text(json.dumps({"schema_version":1,"policy":prepared.POLICY,"entries":[entry]}),encoding="utf-8")
        output=self.project/"prepared-content/index.json"
        prepared.merge_catalogs(self.project,[index],output)
        merged=json.loads(output.read_text(encoding="utf-8"))["entries"][0]
        self.assertEqual(merged["metadata_json"],wire)
        self.assertEqual(merged["entry_id"],entry["entry_id"])
        self.assertNotIn("metadata",merged)
        self.assertIn("rigs",prepared.entry_metadata(merged))
        self.assertNotEqual(json.dumps(json.loads(wire),separators=(",",":")),wire,
            "control proves parsing/re-serializing the metadata numbers changes their original wire lexemes")

    def test_metadata_wire_rejects_ambiguous_legacy_and_non_object_views(self):
        for entry in ({"metadata":{}},{"metadata_json":"{}","metadata":{}},
                {"metadata_json":{}},{"metadata_json":"[]"},{"metadata_json":"{bad"},
                {"metadata_json":'{"value":NaN}'},{"metadata_json":'{"value":Infinity}'}):
            with self.subTest(entry=entry),self.assertRaises(prepared.PreparedError):
                prepared.entry_metadata(entry)


if __name__=="__main__": unittest.main()
