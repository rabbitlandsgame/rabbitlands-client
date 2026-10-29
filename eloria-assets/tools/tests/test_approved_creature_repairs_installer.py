"""Focused authority and transaction checks; no production assets are written."""
import copy
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_approved_creature_repairs as tool


class RepairInstallerTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"complete": True, "entries": [
            {"id": name, "source": {"sha256": "source"},
             "variants": [{"id": "repair-v1", "sha256": name}]}
            for name in sorted(tool.ACTORS)]}
        self.authorization = {"kind": "current_user_repair_instruction", "authorized": True,
            "count": 5, "scope": "exact_candidates_all_native_clips", "catalog_sha256": "catalog",
            "actors": sorted(tool.ACTORS), "instruction_summary": "Explicit current user instruction"}
        self.events = [{"event_id": name, "utc": "test", "actor": name, "type": "approve",
            "test_only": False, "scope": "creature_candidate_all_clips", "variant": "repair-v1",
            "catalog_sha256": "catalog", "source_sha256": "source", "candidate_sha256": name}
            for name in sorted(tool.ACTORS)]
        self.authorization["approval_events"] = {e["actor"]: {
            "event_id": e["event_id"], "event_sha256": tool.event_sha(e)} for e in self.events}

    def test_exact_current_instruction_and_real_approvals(self):
        entries = tool.approved_entries(self.catalog, self.authorization, "catalog")
        self.assertEqual(set(tool.checked_approvals(entries, self.authorization, self.events, "catalog")), tool.ACTORS)

    def test_authority_catalog_count_and_incomplete_guards(self):
        for changed in ({"authorized": False}, {"catalog_sha256": "new-unreviewed"}, {"count": 4},
                        {"kind": "queue_visibility"}, {"actors": ["skeleton"] * 5}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                tool.approved_entries(self.catalog, dict(self.authorization, **changed), "catalog")
        bad = copy.deepcopy(self.catalog); bad["complete"] = False
        with self.assertRaises(ValueError): tool.approved_entries(bad, self.authorization, "catalog")
        bad = copy.deepcopy(self.catalog); bad["entries"][0]["variants"] *= 2
        with self.assertRaises(ValueError): tool.approved_entries(bad, self.authorization, "catalog")

    def test_changed_or_synthetic_saved_approval_rejected(self):
        for changed in ({"candidate_sha256": "unreviewed"}, {"test_only": True}, {"scope": "one_clip_only"}):
            events = copy.deepcopy(self.events); events[0].update(changed)
            # Even re-pinning modified event bytes cannot satisfy approval semantics.
            auth = copy.deepcopy(self.authorization)
            auth["approval_events"][events[0]["actor"]]["event_sha256"] = tool.event_sha(events[0])
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                tool.checked_approvals(self.catalog["entries"], auth, events, "catalog")

    def test_original_node_names_rests_and_links_remain(self):
        source = {"nodes": [{"name": "hips", "children": [1]}, {"name": "head", "translation": [0, 1, 0]}]}
        candidate = copy.deepcopy(source); candidate["nodes"].append({"name": "repair-control"})
        candidate["nodes"][0]["children"].append(2)
        tool.assert_original_nodes(source, candidate)
        for replacement in ({"name": "renamed"}, {"translation": [0, 2, 0]}):
            bad = copy.deepcopy(candidate); bad["nodes"][1].update(replacement)
            with self.assertRaises(ValueError): tool.assert_original_nodes(source, bad)
        bad = copy.deepcopy(candidate); bad["nodes"][0]["children"] = [2]
        with self.assertRaises(ValueError): tool.assert_original_nodes(source, bad)

    def test_counts_referenced_instances_and_rejects_targets(self):
        doc = {"nodes": [{"mesh": 0}, {"mesh": 0}], "accessors": [{"count": 3}],
               "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 0}]},
                          {"primitives": [{"attributes": {"POSITION": 0}, "targets": [{}]}]}],
               "skins": [{"joints": [0, 1]}], "animations": [{"name": "Jog"}]}
        result = tool.counts(doc)
        self.assertEqual((result["vertices"], result["triangles"], result["joints"], result["surfaceCount"]), (6, 2, 2, 2))
        doc["meshes"][0]["primitives"][0]["targets"] = [{}]
        with self.assertRaises(ValueError): tool.counts(doc)

    def test_stale_hash_rollback_and_path_guard_backend(self):
        # Retained ignored evidence; no recursive cleanup or shared asset writes.
        root = tool.ROOT / ".local/approved-repair-installer-tests" / uuid.uuid4().hex
        root.mkdir(parents=True)
        asset = root / "asset.glb"; asset.write_bytes(b"current")
        expected = {"asset.glb": tool.digest(asset)}
        candidate = root / "candidate.glb"; candidate.write_bytes(b"approved")
        pinned = tool.digest(candidate); candidate.write_bytes(b"unreviewed changed version")
        with self.assertRaises(ValueError):
            tool.apply_transaction(root, {"asset.glb": candidate}, expected, root / ".local/stale-candidate",
                                   approved_hashes={"asset.glb": pinned})
        self.assertEqual(asset.read_bytes(), b"current")
        with self.assertRaises(ValueError):
            tool.apply_transaction(root, {"asset.glb": b"new"}, {"asset.glb": "stale"}, root / ".local/stale-runtime")
        with self.assertRaises(RuntimeError):
            tool.apply_transaction(root, {"asset.glb": b"new", "metadata.json": b"{}"},
                                   dict(expected, **{"metadata.json": None}), root / ".local/rollback", fail_after=2)
        self.assertEqual(asset.read_bytes(), b"current")
        self.assertFalse((root / "metadata.json").exists())
        with self.assertRaises(ValueError): tool.target(root, "../outside")


if __name__ == "__main__":
    unittest.main()
