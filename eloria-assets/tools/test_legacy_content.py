"""Serve plan CV13: the legacy content tools read the server's base content tables only.

legacy_content.read_base_only switches a server checkout's continent-v2 content overlay off for the process, and does
nothing on a checkout that has no overlay. The source checks pin where each legacy tool (and each region script that
loads server content) switches it off: before its first content loader call. The paired case runs the server's own
map loader through generate_continent_walk_proof.runtime, the gate the walk proof, publish_interior_staff and their
tests load through, on a fixture profile that has an overlay; it needs ELORIA_SERVER_ROOT naming a server checkout
with eloria/content_overlay.py, and writes no bytecode into it.

    python -m pytest eloria-assets/tools/test_legacy_content.py
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # never write __pycache__ into a server checkout
TOOLS = Path(__file__).resolve().parent
REGIONS = TOOLS.parent / "maps" / "nymara-regions"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import legacy_content  # noqa: E402

STUB_OVERLAY = "_configured = None\n\n\ndef configure(enabled):\n    global _configured\n    _configured = enabled\n"
# The content loaders of the server (eloria.maps, spawns, harvesting, npcs, interactives, questlines) and the
# relocate tool's re-export of load_maps; a legacy tool must switch the overlay off before calling any of them.
LOADERS = ("load_maps", "load_spawns", "load_harvesting", "load_npcs", "load_interactives", "load_questlines",
           "load_configured_npcs")
# Each legacy tool: the function that switches the overlay off, and how (the shared helper or the inline block).
TOOLS_SWITCHED = {
    TOOLS / "generate_continent_walk_proof.py": ("runtime", "read_base_only("),
    TOOLS / "audit_continent_geography.py": ("run", "read_base_only("),
    TOOLS / "continent_portals.py": ("load_collision", "read_base_only("),
    TOOLS / "publish_northern_content.py": ("publish", "read_base_only("),
    TOOLS / "rebuild_northern_regions.py": ("main", "read_base_only("),
    TOOLS / "rebuild_southern_regions.py": ("main", "read_base_only("),
    TOOLS / "rebuild_coastal_regions.py": ("main", "read_base_only("),
    REGIONS / "amberwood/source/rebuild_landscape.py": ("main", "content_overlay.configure(False)"),
    REGIONS / "whitehorn_range/source/rebuild_landscape.py": ("main", "content_overlay.configure(False)"),
    REGIONS / "crownwater/source/write_walk_fixture.py": ("fixtures", "content_overlay.configure(False)"),
    REGIONS / "ssarathi_ruins/source/write_walk_fixture.py": ("fixtures", "content_overlay.configure(False)"),
    REGIONS / "mirrorhold/source/test_lens_vault_access.py": (
        "test_actual_occupied_world_reaches_trigger_and_publisher_return", "content_overlay.configure(False)"),
    REGIONS / "mirrorhold/source/test_npc_post_access.py": (
        "test_occupied_world_reaches_the_exact_post_without_an_automatic_door", "content_overlay.configure(False)"),
}


def forget_eloria() -> None:
    for name in [name for name in sys.modules if name == "eloria" or name.startswith("eloria.")]:
        del sys.modules[name]


def fake_server(root: Path, overlay: bool = True) -> Path:
    package = root / "eloria"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""A fixture server package."""\n', encoding="utf-8")
    if overlay:
        (package / "content_overlay.py").write_text(STUB_OVERLAY, encoding="utf-8")
    return root


class ReadBaseOnly(unittest.TestCase):
    def setUp(self):
        forget_eloria()
        self.addCleanup(forget_eloria)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_a_checkout_with_an_overlay_is_switched_off(self):
        server = fake_server(self.root / "server")
        before = list(sys.path)
        self.assertTrue(legacy_content.read_base_only(server))
        self.assertEqual(sys.path, before, "the checkout is on sys.path only while the switch is imported")
        from eloria import content_overlay
        self.assertIs(content_overlay._configured, False)

    def test_an_older_checkout_has_nothing_to_switch(self):
        before = list(sys.path)
        self.assertFalse(legacy_content.read_base_only(fake_server(self.root / "older", overlay=False)))
        self.assertFalse(legacy_content.read_base_only(self.root / "not-a-server"))
        self.assertEqual(sys.path, before)

    def test_another_checkouts_eloria_is_left_alone(self):
        first = fake_server(self.root / "first")
        second = fake_server(self.root / "second")
        self.assertTrue(legacy_content.read_base_only(first))
        from eloria import content_overlay
        content_overlay.configure(None)
        self.assertFalse(legacy_content.read_base_only(second))
        self.assertIsNone(content_overlay._configured)


def function_source(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node)
    raise AssertionError(f"{path.name} has no function {name}")


class EveryLegacyToolSwitchesFirst(unittest.TestCase):
    def test_the_switch_comes_before_the_first_content_loader(self):
        for path, (name, switch) in TOOLS_SWITCHED.items():
            with self.subTest(tool=str(path.relative_to(TOOLS.parent))):
                body = function_source(path, name).partition(":\n")[2]  # the body, after the signature
                self.assertIn(switch, body)
                first = min((body.index(loader) for loader in LOADERS if loader in body), default=len(body))
                self.assertLess(body.index(switch), first, f"{name} loads content before it switches the overlay off")

    def test_the_geode_test_switches_off_at_import(self):
        text = (REGIONS / "amethyst_barrens/source/test_geode_working_approach.py").read_text(encoding="utf-8")
        self.assertLess(text.index("content_overlay.configure(False)"), text.index("class GeodeWorkingAccess"))

    def test_publish_interior_staff_loads_through_the_walk_proof_gate(self):
        text = (TOOLS / "publish_interior_staff.py").read_text(encoding="utf-8")
        self.assertIn("from generate_continent_walk_proof import runtime", text)
        self.assertIn("R=runtime(server)", function_source(TOOLS / "publish_interior_staff.py", "publish"))


@unittest.skipUnless(os.environ.get("ELORIA_SERVER_ROOT"), "set ELORIA_SERVER_ROOT to a server checkout with the "
                                                           "continent-v2 overlay (eloria/content_overlay.py)")
class PairedServer(unittest.TestCase):
    def test_the_walk_proof_gate_loads_the_base_map_table_only(self):
        server = Path(os.environ["ELORIA_SERVER_ROOT"]).resolve()
        if not (server / "eloria" / "content_overlay.py").is_file():
            self.skipTest(f"{server} has no continent-v2 overlay")
        forget_eloria()
        self.addCleanup(forget_eloria)
        saved_path = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved_path))
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("ELORIA_CONTENT_OVERLAY", None)
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "config" / "eloria"
            (profile / "continent-v2").mkdir(parents=True)
            (profile / "maps.txt").write_text("map | crownwater | Crownwater | maps/nymara/crownwater.elm | CW\n",
                                              encoding="utf-8")
            (profile / "continent-v2" / "maps.txt").write_text(
                "map | sw_isle | Landfall | maps/nymara/sw_isle.elm | SWI\n"
                "portal | sw_isle | 10 | 10 | crownwater | 293 | 113\n", encoding="utf-8")
            sys.path.insert(0, str(server))
            from eloria import content_overlay
            from eloria import maps as server_maps
            self.addCleanup(content_overlay.configure, None)
            content_overlay.configure(None)
            served, served_portals = server_maps.load_maps(profile / "maps.txt")
            self.assertEqual(sorted(served), ["crownwater", "sw_isle"], "the fixture overlay is read by default")
            self.assertEqual([(p.source, p.destination) for p in served_portals], [("sw_isle", "crownwater")])
            import generate_continent_walk_proof as proof
            modules = proof.runtime(server)
            self.assertFalse(content_overlay.enabled())
            legacy, legacy_portals = modules["maps"].load_maps(profile / "maps.txt")
            self.assertEqual(sorted(legacy), ["crownwater"])
            self.assertEqual(list(legacy_portals), [])


if __name__ == "__main__":
    unittest.main()
