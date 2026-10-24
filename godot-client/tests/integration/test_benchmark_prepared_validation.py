import copy
from types import SimpleNamespace
import unittest

from benchmark_prepared_validation import configure_prepared_request, validate_prepared


class PreparedValidationTests(unittest.TestCase):
    def raw(self):
        return {"preparedNodePolicy": "retain", "preparedContent": {
            "mode": "raw", "active": False, "hits": 0, "consumed_entries": [], "misses": {"disabled": 2}}}

    def native(self):
        value = self.raw()
        value["preparedNodePolicy"] = "lazy-source-v1"
        value["preparedContent"].update(mode="require-pilot", active=True, hits=2, consumed_entries=[{
            "entry_id": "verified-entry", "kind": "world", "source": "eloria-assets/maps/pilot/world.json",
            "texture_token": "full-policy", "node_policy": "lazy-source-v1", "hits": 2}])
        return value

    def test_raw_real_snapshot_and_historical_marker(self):
        validate_prepared(self.raw(), {"prepared_content": "raw", "prepared_node_policy": "retain"}, "cell")
        validate_prepared({"preparedContent": {"status": "not_implemented"}}, {}, "historical")

    def test_new_requests_reject_historical_or_missing_actual_policy(self):
        for actual in ({"preparedContent": {"status": "not_implemented"}},
                       {"preparedContent": self.raw()["preparedContent"]}):
            with self.assertRaises(ValueError):
                validate_prepared(actual, {"prepared_content": "raw", "prepared_node_policy": "retain"}, "cell")

    def test_exact_native_policy_and_unrelated_zero_hit_start(self):
        request = {"prepared_content": "require-pilot", "prepared_node_policy": "lazy-source-v1"}
        validate_prepared(self.native(), request, "pilot")
        actual = self.raw()
        actual["preparedNodePolicy"] = "lazy-source-v1"
        actual["preparedContent"]["mode"] = "require-pilot"
        validate_prepared(actual, request, "before-pilot")

    def test_counter_inventory_and_policy_corruptions_fail_closed(self):
        request = {"prepared_content": "require-pilot", "prepared_node_policy": "lazy-source-v1"}
        def active(a): a["preparedContent"]["active"] = False
        def hits(a): a["preparedContent"]["hits"] = 3
        def boolean(a): a["preparedContent"]["hits"] = True
        def duplicate(a): a["preparedContent"]["consumed_entries"] *= 2
        def policy(a): a["preparedContent"]["consumed_entries"][0]["node_policy"] = "retain"
        def texture(a): a["preparedContent"]["consumed_entries"][0]["texture_token"] = ""
        for mutation in (active, hits, boolean, duplicate, policy, texture):
            with self.subTest(mutation=mutation.__name__):
                actual = copy.deepcopy(self.native())
                mutation(actual)
                with self.assertRaises(ValueError): validate_prepared(actual, request, "pilot")

    def test_raw_rejects_real_native_hits_and_unused_lazy_request(self):
        actual = self.native()
        actual["preparedNodePolicy"] = "retain"
        actual["preparedContent"]["mode"] = "raw"
        actual["preparedContent"]["consumed_entries"][0]["node_policy"] = "retain"
        with self.assertRaises(ValueError):
            validate_prepared(actual, {"prepared_content": "raw", "prepared_node_policy": "retain"}, "raw")
        with self.assertRaises(ValueError):
            configure_prepared_request(SimpleNamespace(prepared_content="raw", prepared_node_policy="lazy-source-v1"))
        configure_prepared_request(SimpleNamespace(prepared_content="require-pilot", prepared_node_policy="lazy-source-v1"))


if __name__ == "__main__": unittest.main()
