"""Check publication boundaries without credentials or cloud requests."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


SOURCE = Path(os.environ.get("RL_BROWSER_UPLOAD_SOURCE", Path(__file__).resolve().parents[1] / "tools/upload_browser_assets.py"))
SPEC = importlib.util.spec_from_file_location("browser_asset_upload_under_test", SOURCE)
upload_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upload_tool)


class ClientError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


exceptions = types.ModuleType("botocore.exceptions")
exceptions.ClientError = ClientError
sdk_modules = {"botocore": types.ModuleType("botocore"), "botocore.exceptions": exceptions}


class FakeBucket:
    def __init__(self, head=None, missing="404", corrupt_after_put=False):
        self.head = head
        self.missing = missing
        self.corrupt_after_put = corrupt_after_put
        self.puts = []
        self.heads = []

    def head_object(self, **arguments):
        self.heads.append(arguments)
        if self.head is None:
            raise ClientError(self.missing)
        return self.head

    def put_object(self, **arguments):
        arguments["Body"] = arguments["Body"].read()
        self.puts.append(arguments)
        self.head = {"ContentLength": len(arguments["Body"]), "Metadata": arguments["Metadata"],
                     "ContentType": arguments["ContentType"], "CacheControl": arguments["CacheControl"]}
        if self.corrupt_after_put:
            self.head["ContentLength"] += 1


class BrowserAssetUploadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stage = Path(self.temporary.name)
        (self.stage / "site").mkdir()
        (self.stage / "assets").mkdir()

        def payload(body, extension):
            digest = hashlib.sha256(body).hexdigest()
            name = digest + "." + extension
            (self.stage / "assets" / name).write_bytes(body)
            return {"file": name, "sha256": digest, "bytes": len(body)}

        self.wasm = payload(b"\0asm\1\0\0\0", "wasm")
        self.part = payload(b"package", "bin")
        self.archive = payload(b"compressed art", "zip")
        self.manifest = {"schema": 1, "wasm": self.wasm, "pack": {"parts": [self.part]},
                         "archives": [self.archive], "groups": {"map:one": {"archives": [self.archive]}}}
        (self.stage / "site/godot-cpp-LICENSE.md").write_text("MIT license fixture\n")
        self.save_manifest()
        self.sdk = mock.patch.dict(sys.modules, sdk_modules)
        self.sdk.start()
        self.addCleanup(self.sdk.stop)

    def save_manifest(self):
        (self.stage / "site/browser-assets.json").write_text(json.dumps(self.manifest))

    def rows(self):
        self.save_manifest()
        return upload_tool.payloads(self.stage)

    def test_whitelist_deduplicates_groups_and_excludes_unlisted_files(self):
        (self.stage / "assets/private-trial.bin").write_bytes(b"unlisted output")
        rows = self.rows()
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["file"] for row in rows},
                         {self.wasm["file"], self.part["file"], self.archive["file"], "godot-cpp-LICENSE.md"})
        self.assertEqual({row["content_type"] for row in rows},
                         {"application/wasm", "application/octet-stream", "application/zip", "text/markdown; charset=utf-8"})

    def test_malformed_paths_hashes_and_lengths_are_rejected(self):
        original = copy.deepcopy(self.manifest)
        for change in [{"file": "../private.bin"}, {"sha256": "g" * 64}, {"bytes": True},
                       {"bytes": 0}, {"bytes": 64 * 1024 * 1024 + 1}]:
            with self.subTest(change=change):
                self.manifest = copy.deepcopy(original)
                self.manifest["wasm"].update(change)
                with self.assertRaises(ValueError):
                    self.rows()

    def test_inconsistent_duplicates_are_rejected(self):
        self.manifest["archives"].append({**self.wasm, "bytes": self.wasm["bytes"] + 1})
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.rows()

    def test_source_size_and_same_length_corruption_are_rejected(self):
        path = self.stage / "assets" / self.part["file"]
        for replacement in [b"short", b"PACKAGE"]:
            with self.subTest(replacement=replacement):
                path.write_bytes(replacement)
                with self.assertRaises(ValueError):
                    self.rows()

    def test_complete_validation_precedes_client_creation(self):
        # Even a corrupt final row must prevent the first cloud connection.
        (self.stage / "assets" / self.archive["file"]).write_bytes(b"bad")
        with mock.patch.object(sys, "argv", ["upload", "--stage", str(self.stage), "--credentials", "unused.json",
                                            "--receipt", str(self.stage / "unused-receipt.json")]), \
                mock.patch.object(upload_tool, "client_from_file") as connect:
            with self.assertRaises(ValueError):
                upload_tool.main()
            connect.assert_not_called()

    def test_put_commits_the_verified_bytes_headers_and_digest_then_checks_head(self):
        for row in self.rows():
            with self.subTest(key=row["key"]):
                client = FakeBucket()
                result = upload_tool.upload(client, "fixture-bucket", row)
                self.assertTrue(result["uploaded"])
                self.assertEqual(len(client.puts), 1)
                put = client.puts[0]
                self.assertEqual(put["Body"], row["source"].read_bytes())
                self.assertEqual(put["ContentLength"], row["bytes"])
                self.assertEqual(put["Metadata"], {"sha256": row["sha256"]})
                self.assertEqual(put["ContentType"], row["content_type"])
                self.assertEqual(len(client.heads), 2)
                self.assertEqual("immutable" in put["CacheControl"], row["key"].startswith("browser/assets/"))

    def test_matching_remote_objects_resume_without_rewriting(self):
        row = self.rows()[0]
        client = FakeBucket()
        upload_tool.upload(client, "fixture-bucket", row)
        client.puts.clear()
        result = upload_tool.upload(client, "fixture-bucket", row)
        self.assertFalse(result["uploaded"])
        self.assertEqual(client.puts, [])

    def test_remote_mismatch_never_overwrites_any_existing_object(self):
        row = self.rows()[0]
        initial = FakeBucket()
        upload_tool.upload(initial, "fixture-bucket", row)
        for change in [{"ContentLength": row["bytes"] + 1}, {"Metadata": {"sha256": "0" * 64}},
                       {"ContentType": "text/plain"}, {"CacheControl": "no-store"}]:
            with self.subTest(change=change):
                client = FakeBucket({**initial.head, **change})
                with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                    upload_tool.upload(client, "fixture-bucket", row)
                self.assertEqual(client.puts, [])

    def test_remote_post_write_mismatch_is_a_failure(self):
        client = FakeBucket(corrupt_after_put=True)
        with self.assertRaisesRegex(ValueError, "Remote verification failed"):
            upload_tool.upload(client, "fixture-bucket", self.rows()[0])
        self.assertEqual(len(client.puts), 1)

    def test_denied_head_is_not_treated_as_a_missing_object(self):
        client = FakeBucket(missing="AccessDenied")
        with self.assertRaises(ClientError):
            upload_tool.upload(client, "fixture-bucket", self.rows()[0])
        self.assertEqual(client.puts, [])


if __name__ == "__main__":
    unittest.main()
