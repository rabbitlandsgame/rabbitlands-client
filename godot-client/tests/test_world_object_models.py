#!/usr/bin/env python3
"""The models the client stands on server-declared world objects.

Added 2026-08-29 for Eloria Client.

`ELORIA_MAP_OBJECTS` names a harvest node by its resource label and an
interactive by the label the server derives from its role, and nothing else.
Those two strings are therefore the whole contract between the two repositories
for what a world object looks like, and a resource whose label the registry
does not carry falls back to a bare ring on the ground - which is what the
whole harvestable layer did before the registry existed.

This reads the registry the asset generator writes, checks every model file it
names is a real GLB, and checks the server's own harvesting profile and
interactive table - with the continent-v2 overlay's rows appended, as the
server serves them - resolve through it. The server repository is optional: the
model-side checks run either way, and the two cross-repository checks skip with
a message rather than failing when it is not checked out beside the client.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
REGISTRY = CLIENT / "data/world/objects.json"
TOOLS = CLIENT.parent / "eloria-assets" / "tools"
GENERATOR = TOOLS / "build_native_world_object_glbs.py"
# The imported-model table and the bands it is held to. Imported once, here,
# so every check below reads the same table the generator writes from.
sys.path.insert(0, str(TOOLS))
import imported_world_objects as imported  # noqa: E402
# The server repository beside this one. The main checkouts are
# `rabbitlands-client` and `rabbitlands-server` (`eloria-client` and
# `eloria-server` before the move to Rabbit Lands, kept as a fallback), but a
# feature is usually worked in a pair of worktrees named `<something>` and
# `<something>-server`, and this test was silently reading the main checkout
# from whatever branch it happened to be on - so a rename made in the pair
# looked like a client that had lost its models.
NEIGHBOURS = CLIENT.parents[1]
SERVER_CANDIDATES = (NEIGHBOURS / (CLIENT.parents[0].name + "-server"),
                     NEIGHBOURS / "rabbitlands-server",
                     NEIGHBOURS / "eloria-server")
# The interactive roles the server can state. `map_object_entries` sends
# `role.replace("_", " ").title()`, so this is the label as well as the role.
ROLE_LABEL = re.compile(r"^[a-z_]+$")
# The continent-v2 overlay beside the profile's own tables. The server serves
# the landing isles from it: each content loader reads the file of the same
# name there and appends its rows after the profile's, so a resource or a role
# declared only there - Olive and Lemon are - reaches the client exactly as a
# profile one does. A server from before the isles has no such directory.
OVERLAY = "config/eloria/continent-v2"


def server_root() -> Path | None:
    variable = next((name for name in ("RABBITLANDS_SERVER_ROOT", "ELORIA_SERVER_ROOT")
                     if os.environ.get(name)), None)
    if variable:
        root = Path(os.environ[variable]).resolve()
        if not (root / "config/eloria/harvesting.txt").is_file():
            raise ValueError(f"{variable} is not a Rabbit Lands server: {root}")
        return root
    for candidate in SERVER_CANDIDATES:
        if (candidate / "config/eloria/harvesting.txt").is_file():
            return candidate
    return None


def served_table_lines(root: Path, name: str) -> list[str]:
    """The profile's table, then the continent-v2 overlay's table of that name.

    The order the server loads them in. The overlay is read whether or not
    the checkout's own settings switch it on: the switch is a deployment
    setting, and any server holding these files can be started with it on.
    """
    lines = (root / "config/eloria" / name).read_text(
        encoding="utf-8").splitlines()
    overlay = root / OVERLAY / name
    if overlay.is_file():
        lines += overlay.read_text(encoding="utf-8").splitlines()
    return lines


def glb_triangle_count(path: Path) -> int:
    """Triangles the GLB's default scene draws.

    The generator's own count, so the registry and this check cannot define a
    triangle differently (a mesh instanced twice, a primitive with no index
    list) and disagree about a model neither got wrong.
    """
    return imported.triangle_count(path)


class WorldObjectModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.harvestables = cls.registry["harvestables"]
        cls.interactives = cls.registry["interactives"]

    def test_every_declared_model_is_a_real_glb(self) -> None:
        for section in (self.harvestables, self.interactives):
            for model_id, entry in section["models"].items():
                with self.subTest(model=model_id):
                    scene = entry["scene"]
                    self.assertTrue(scene.startswith("res://"), scene)
                    path = CLIENT / scene.removeprefix("res://")
                    self.assertTrue(path.is_file(), f"{scene} is missing")
                    self.assertEqual(entry["triangles"],
                                     glb_triangle_count(path))

    def test_models_stay_inside_the_authored_triangle_band(self) -> None:
        """The band the surrounding regional landmark kit occupies.

        A node the player walks up to and stares at through a harvest loop is
        held to the refined kit's budget, not to the placeholder budget the
        bootstrap scenery was built at. A modelled node imported from the
        reviewed kits has the wider band the owner set for them, and only a
        model the imported table lists may use it - or reused underground
        scenery, which its own test holds to its recorded file.
        """
        listed = ({row.model_id for row in imported.IMPORTED_HARVESTABLES},
                  {row.model_id for row in imported.IMPORTED_INTERACTIVES})
        for section in (self.harvestables, self.interactives):
            for model_id, entry in section["models"].items():
                with self.subTest(model=model_id):
                    wide = (model_id in listed[0 if section is self.harvestables else 1]
                            or (section is self.harvestables and entry.get("reusedScenery")))
                    low, high = (imported.IMPORTED_TRIANGLE_BAND if wide
                                 else imported.PROCEDURAL_TRIANGLE_BAND)
                    self.assertGreaterEqual(entry["triangles"], low)
                    self.assertLessEqual(entry["triangles"], high)

    def test_the_imported_band_is_the_one_the_owner_set(self) -> None:
        """About 2,600 triangles for imported nodes (2026-10-02, item 17)."""
        self.assertEqual(imported.IMPORTED_TRIANGLE_BAND, (90, 2600))
        self.assertEqual(imported.PROCEDURAL_TRIANGLE_BAND, (90, 424))

    def test_imported_models_are_exactly_the_imported_table(self) -> None:
        """Each imported entry is the table's row, measured off its own file.

        A model claiming `imported` without a row would take the wide band on
        its own say-so, and a GLB swapped in without regenerating the registry
        would draw something other than what the registry measured.
        """
        claimed = {model_id for model_id, entry in self.harvestables["models"].items()
                   if entry.get("imported")}
        rows = {row.model_id: row for row in imported.IMPORTED_HARVESTABLES}
        self.assertEqual(claimed, set(rows))
        for model_id, row in rows.items():
            with self.subTest(model=model_id):
                entry = self.harvestables["models"][model_id]
                path = CLIENT / entry["scene"].removeprefix("res://")
                measured = imported.measure_glb(path)
                for key, value in measured.items():
                    self.assertEqual(entry[key], value, key)
                self.assertEqual((entry["label"], entry["kind"], entry["tier"]),
                                 (row.label, row.kind, row.tier))
                answered = self.harvestables["resources"].get(row.label)
                if row.answers_label:
                    self.assertEqual(answered, model_id,
                                     f"{row.label} should resolve to {model_id}")
                else:
                    self.assertNotEqual(answered, model_id,
                                        f"{row.label} is not swapped to {model_id} yet")

    def test_reused_scenery_models_match_their_record(self) -> None:
        """Underground minerals draw packaged scenery, not a row of the table.

        tools/prepare_underground_scenery.py writes these entries: several
        labels share one reused GLB under assets/world/underground and draw it
        in their own resource palette (mineral_appearance.gd), so they are not
        `imported` and are held instead to the file its reuse record names,
        measured as an imported model is, inside the imported band.
        """
        record = json.loads((CLIENT.parent / "eloria-assets/source/world_objects/underground/"
                             "reused-scenery.json").read_text(encoding="utf-8"))
        packaged = {asset["output"]: asset["sha256"] for asset in record["assets"]}
        models = self.harvestables["models"]
        reused = {model_id: entry for model_id, entry in models.items()
                  if entry.get("reusedScenery")}
        self.assertTrue(reused, "the underground minerals are registered")
        low, high = imported.IMPORTED_TRIANGLE_BAND
        for model_id, entry in reused.items():
            with self.subTest(model=model_id):
                self.assertNotIn("imported", entry)
                output = "godot-client/" + entry["scene"].removeprefix("res://")
                self.assertIn(output, packaged)
                path = CLIENT.parent / output
                measured = imported.measure_glb(path)
                self.assertEqual(measured["sha256"], packaged[output])
                for key, value in measured.items():
                    self.assertEqual(entry[key], value, key)
                self.assertTrue(low <= entry["triangles"] <= high)
                self.assertIn(entry["tier"], {"common", "uncommon", "rare"})
                self.assertEqual(set(entry["resourcePalette"]), {"stone", "mineral"})
                self.assertEqual(self.harvestables["resources"].get(entry["label"]), model_id)
                self.assertTrue(models[entry["replaces"]].get("retired"))
                self.assertEqual(models[entry["replaces"]]["tier"], entry["tier"])

    def test_imported_interactives_match_the_reviewed_files(self) -> None:
        models = self.interactives["models"]
        rows = {row.model_id: row for row in imported.IMPORTED_INTERACTIVES}
        self.assertEqual({key for key, value in models.items() if value.get("imported")},
                         set(rows))
        for model_id, row in rows.items():
            with self.subTest(model=model_id):
                entry = models[model_id]
                self.assertEqual(entry["label"], row.label)
                self.assertEqual(entry["source"], row.source)
                self.assertEqual(self.interactives["roles"][row.label], model_id)
                path = CLIENT / entry["scene"].removeprefix("res://")
                for key, value in imported.measure_glb(path).items():
                    self.assertEqual(entry[key], value, key)

    def test_storage_geometry_fits_its_walkable_body(self) -> None:
        import numpy as np
        scene = self.interactives["models"]["storage"]["scene"]
        path = CLIENT / scene.removeprefix("res://")
        document, binary = imported._read_glb(path)
        posed = []
        for primitive, world in imported.drawn_primitives(document):
            points = imported._floats(document, binary, primitive["attributes"]["POSITION"], 3)
            posed.append(points @ world[:3, :3].T + world[:3, 3])
        points = np.concatenate(posed)
        self.assertAlmostEqual(float(points[:, 1].min()), 0.0, places=5)
        # Random yaw and up to 1.08 runtime scale must stay in the server's
        # 3x3 collision body (0.5 m cells), leaving its approach ring open.
        self.assertLessEqual(float(np.linalg.norm(points[:, [0, 2]], axis=1).max()) * 1.08,
                             0.75)
        source_dir = CLIENT.parent / "eloria-assets/source/world_objects/storage"
        provenance = json.loads((source_dir / "provenance.json").read_text())
        self.assertEqual(provenance["model"]["sha256"], imported.measure_glb(path)["sha256"])
        material = document["materials"][0]
        for texture in (material["pbrMetallicRoughness"]["baseColorTexture"],
                        material["pbrMetallicRoughness"]["metallicRoughnessTexture"],
                        material["normalTexture"]):
            image = document["images"][document["textures"][texture["index"]]["source"]]
            self.assertIn("bufferView", image, "storage textures must travel inside the GLB")

    def test_a_swapped_label_keeps_the_model_it_replaced(self) -> None:
        """The procedural model a swap displaces stays registered and on disk.

        Map packages bake that geometry into their own scenery, and undoing the
        swap is the row's flag plus a regeneration.
        """
        for model_id, entry in self.harvestables["models"].items():
            if "replaces" not in entry:
                continue
            with self.subTest(model=model_id):
                replaced = entry["replaces"]
                self.assertIn(replaced, self.harvestables["models"])
                self.assertFalse(self.harvestables["models"][replaced].get("imported"))
                self.assertEqual(self.harvestables["models"][replaced]["label"],
                                 entry["label"])

    def test_imported_models_are_graded_to_the_procedural_kit(self) -> None:
        """No imported node draws far brighter, or darker, than its peer.

        Every procedural node multiplies its texture by a palette colour; a
        model textured elsewhere has none until it is graded, and the first
        Meshy nodes drew 2-4 times brighter than the models they replaced -
        chalk-white flint, white sage - which only the in-game shots showed.
        Each row names the procedural model it was graded against, and its
        mean surface albedo must stay inside the table's band of that one's.
        """
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is needed to decode the textures")
        models = self.harvestables["models"]
        low, high = imported.GRADE_RATIO_BAND
        for row in imported.IMPORTED_HARVESTABLES:
            with self.subTest(model=row.model_id):
                self.assertIn(row.graded_against, models)
                self.assertFalse(models[row.graded_against].get("imported"))
                peer = imported.surface_albedo(
                    CLIENT / models[row.graded_against]["scene"].removeprefix("res://"))
                own = imported.surface_albedo(
                    CLIENT / models[row.model_id]["scene"].removeprefix("res://"))
                self.assertGreaterEqual(own / peer, low, f"{own:.3f} against {peer:.3f}")
                self.assertLessEqual(own / peer, high, f"{own:.3f} against {peer:.3f}")

    def test_regenerating_the_registry_keeps_the_imported_models(self) -> None:
        """The generator writes the registry whole; this is what it writes.

        Run it into a scratch client that holds only the imported GLBs, and the
        registry it writes must be the committed one - imported nodes, swapped
        labels and all. Before the imported table existed a regeneration
        silently dropped every model it had not authored itself.
        """
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            imported_paths = []
            for directory, rows in (("harvestables", imported.IMPORTED_HARVESTABLES),
                                    ("interactives", imported.IMPORTED_INTERACTIVES)):
                for row in rows:
                    source = CLIENT / "assets/world" / directory / f"{row.model_id}.glb"
                    target = root / "assets/world" / directory / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    imported_paths.append((source, target))
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "--client", str(root)],
                capture_output=True, text=True)
            # The generator's own message says why it stopped (a GLB missing,
            # a band or a shadowed id); a bare exit status would not.
            self.assertEqual(result.returncode, 0, result.stderr)
            written = json.loads((root / "data/world/objects.json").read_text(
                encoding="utf-8"))
            for source, target in imported_paths:
                self.assertEqual(target.read_bytes(), source.read_bytes(),
                                 f"regeneration overwrote {source.name}")
        self.assertEqual(written, self.registry)

    def test_models_stand_at_a_human_scale(self) -> None:
        """Metres, not tile units: a reed bed reaches a person's waist."""
        for model_id, entry in self.harvestables["models"].items():
            with self.subTest(model=model_id):
                self.assertGreater(entry["height"], 0.1)
                self.assertLess(entry["height"], 2.0)
        for model_id, entry in self.interactives["models"].items():
            with self.subTest(model=model_id):
                self.assertGreater(entry["height"], 0.5)
                self.assertLess(entry["height"], 4.0)

    def test_every_label_resolves_to_a_declared_model(self) -> None:
        for section, key in ((self.harvestables, "resources"),
                             (self.interactives, "roles")):
            for label, model_id in section[key].items():
                with self.subTest(label=label):
                    self.assertIn(model_id, section["models"])

    def test_model_variants_are_the_table_and_name_models_of_their_label(self) -> None:
        """`harvestables.variants` (the harvest presentation, 2026-10-14) is the
        imported table's HARVEST_VARIANTS as the generator checked it, absent
        while that is empty: the client stands `variants[label][i]` on a node,
        so every id must be a model of that very label."""
        variants = self.harvestables.get("variants")
        if not imported.HARVEST_VARIANTS:
            self.assertIsNone(variants)
            return
        self.assertEqual(variants, imported.harvest_variants(self.harvestables))
        for label, ids in variants.items():
            for model_id in ids:
                with self.subTest(label=label, model=model_id):
                    self.assertEqual(self.harvestables["models"][model_id]["label"], label)

    def test_a_variant_of_another_label_or_none_is_refused(self) -> None:
        resources = self.harvestables["resources"]
        label = "Olive" if "Olive" in resources else next(iter(resources))
        own = resources[label]
        other = next(model_id for model_id, entry in self.harvestables["models"].items()
                     if entry["label"] != label)
        self.assertEqual(imported.harvest_variants(self.harvestables, {label: (own,)}),
                         {label: [own]})
        for table in ({label: (own, other)}, {label: ()}, {label: (own, own)},
                      {"Nothing The Registry Knows": (own,)}):
            with self.subTest(table=table):
                with self.assertRaises(ValueError):
                    imported.harvest_variants(self.harvestables, table)

    def test_every_server_resource_has_a_model(self) -> None:
        root = server_root()
        if root is None:
            self.skipTest("rabbitlands-server is not checked out beside the client")
        resources = [
            line.split("|")[1].strip()
            for line in served_table_lines(root, "harvesting.txt")
            if line.startswith("resource")]
        self.assertTrue(resources)
        for resource in resources:
            with self.subTest(resource=resource):
                self.assertIn(resource, self.harvestables["resources"])

    def test_every_server_interactive_role_has_a_model(self) -> None:
        root = server_root()
        if root is None:
            self.skipTest("rabbitlands-server is not checked out beside the client")
        roles = set()
        for line in served_table_lines(root, "interactives.txt"):
            if line.startswith("#") or "|" not in line:
                continue
            role = line.split("|")[4].strip()
            self.assertRegex(role, ROLE_LABEL)
            roles.add(role.replace("_", " ").title())
        self.assertTrue(roles)
        # A role is answered either by a prop in this registry or by the map
        # package: the secrets are authored into the region mesh as `Secret_*`
        # nodes on the tile the server states, so the client stands nothing on
        # one and draws no ring under it.
        authored = self.interactives.get("mapAuthored", {})
        for label in sorted(roles):
            with self.subTest(role=label):
                self.assertIn(label, set(self.interactives["roles"]) | set(authored))

    def test_a_map_authored_role_has_no_prop_of_its_own(self) -> None:
        """The two ways of answering a role are exclusive.

        A role in both would draw the client's prop on top of the map's, which
        is the failure this whole registry exists to stop.
        """
        authored = self.interactives.get("mapAuthored", {})
        self.assertTrue(authored, "at least the secrets are map-authored")
        self.assertFalse(set(authored) & set(self.interactives["roles"]))
        for label, role in authored.items():
            with self.subTest(role=label):
                self.assertRegex(role, ROLE_LABEL)
                self.assertEqual(role.replace("_", " ").title(), label)
                self.assertNotIn(role, self.interactives["models"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
