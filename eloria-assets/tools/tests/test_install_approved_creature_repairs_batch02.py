"""Exact authority, owner-policy and native-catalog guards for batch02."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_approved_creature_repairs_batch02 as tool


def fixtures():
    entries = [{"id": actor, "source": {"sha256": "source-" + actor},
                "variants": [{"id": "repair", "sha256": "candidate-" + actor}]} for actor in sorted(tool.ACTORS | tool.EXCLUDED)]
    events = [{"event_id": actor, "utc": "now", "type": "approve", "test_only": False,
               "scope": "creature_candidate_all_clips", "actor": actor, "registry_actor": actor,
               "variant": "repair", "catalog_sha256": tool.CATALOG_SHA,
               "source_sha256": "source-" + actor, "candidate_sha256": "candidate-" + actor} for actor in sorted(tool.ACTORS)]
    authorization = {"kind": "current_user_repair_instruction", "authorized": True, "count": 4,
                     "scope": "exact_candidates_all_native_clips", "catalog_sha256": tool.CATALOG_SHA,
                     "instruction_summary": "Install four; reject Golem", "actors": sorted(tool.ACTORS),
                     "excluded_actors": sorted(tool.EXCLUDED),
                     "approval_events": {e["actor"]: {"event_id": e["event_id"], "event_sha256": tool.event_sha(e)} for e in events}}
    return {"complete": True, "entries": entries}, authorization, events


class Batch02Guards(unittest.TestCase):
    def test_exact_four_and_golem_exclusion(self):
        catalog, authorization, events = fixtures()
        entries = tool.approved_entries(catalog, authorization, tool.CATALOG_SHA)
        self.assertEqual({e["id"] for e in entries}, tool.ACTORS)
        self.assertEqual(set(tool.checked_approvals(entries, authorization, events, tool.CATALOG_SHA)), tool.ACTORS)
        authorization["actors"][0] = "mossbound_stone_golem"
        with self.assertRaisesRegex(ValueError, "rejected Golem"):
            tool.approved_entries(catalog, authorization, tool.CATALOG_SHA)

    def test_missing_approval_is_not_inferred_from_catalog(self):
        catalog, authorization, events = fixtures()
        entries = tool.approved_entries(catalog, authorization, tool.CATALOG_SHA)
        with self.assertRaisesRegex(ValueError, "approval missing"):
            tool.checked_approvals(entries, authorization, events[:-1], tool.CATALOG_SHA)

    def test_changed_candidate_sha_rejected(self):
        catalog, authorization, events = fixtures()
        entries = tool.approved_entries(catalog, authorization, tool.CATALOG_SHA)
        entries[0]["variants"][0]["sha256"] = "different version"
        with self.assertRaisesRegex(ValueError, "approved bytes differ"):
            tool.checked_approvals(entries, authorization, events, tool.CATALOG_SHA)

    def test_owner_selection_is_only_storm(self):
        tool.validate_owner_selection({"id": "ostrich", "selected_local_draft": False}, {})
        tool.validate_owner_selection({"id": "storm_chimera", "selected_local_draft": True}, {"storm_chimera": {}})
        for actor in ({"id": "ostrich", "selected_local_draft": True}, {"id": "storm_chimera", "selected_local_draft": False}):
            with self.assertRaisesRegex(ValueError, "owner-upgrade"):
                tool.validate_owner_selection(actor, {})

    def test_reviewed_speed_and_stride_preserved_but_aliases_qualified(self):
        current_map = {"actions": {"walk": "Walk"}, "commands": {"1": "walk"}, "loopingClips": ["Walk"],
                       "playbackSpeeds": {"walk": 1.15, "run": 1.25}}
        owner_map = copy.deepcopy(current_map)
        owner_map.update(playbackSpeeds={"walk": 1.0, "run": 1.0}, strideMetresPerSecond={"walk": .7})
        owner_config = {"attachments": {"head": "qualified_head"}}
        with patch.object(tool, "checked_owner", return_value=(owner_config, owner_map, {}, b"policy")):
            config, mapping, evidence, policy = tool.reviewed_owner_upgrade({}, {}, {}, current_map, {})
        self.assertEqual(mapping, current_map)
        self.assertNotIn("strideMetresPerSecond", mapping)
        self.assertEqual(config["attachments"], {"head": "qualified_head"})
        self.assertTrue(evidence["reviewed_runtime_playback_policy_preserved"])
        owner_map["actions"]["walk"] = "Other"
        with patch.object(tool, "checked_owner", return_value=(owner_config, owner_map, {}, b"policy")):
            with self.assertRaisesRegex(ValueError, "action/command/loop"):
                tool.reviewed_owner_upgrade({}, {}, {}, current_map, {})

    def test_all_native_matching_paths_and_validation_updated(self):
        path = "godot-client/assets/actors/native/creatures/test.glb"
        native = {"creatures": {"test": {"path": path, "sha256": "old"}},
                  "other": [{"path": path, "sha256": "stale"}], "validation": {"results": {path: {"nodes": 72}}}}
        document = {"nodes": [{}] * 101, "meshes": [{}], "skins": [{}], "animations": [{}] * 7}
        previous = tool.update_native_catalog(native, "test", path, document, {"joints": 99},
                                              {"appliesToSHA256": "new"}, "Test", "source")
        self.assertEqual(previous, ["old", "stale"])
        self.assertEqual(native["other"][0]["sha256"], "new")
        self.assertEqual(native["validation"]["results"][path], {"nodes": 101, "meshes": 1, "skins": 1, "animations": 7})


if __name__ == "__main__":
    unittest.main()
