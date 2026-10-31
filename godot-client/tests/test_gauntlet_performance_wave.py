"""Keep the offline gauntlet cohort tied to one actual published pulse."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import unittest

from test_trail_gauntlet_package import Grid


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "godot-client/tests/fixtures/gauntlet_performance_wave.json"


def read_json(path):
    return json.loads(path.read_text())


def fields(block):
    return dict(re.findall(r"^([a-z_]+):\s*([^\n]+)", block, re.M))


class AuthoredGauntletPulseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = read_json(FIXTURE)
        cls.evidence = cls.fixture["evidence"]
        cls.manifest = read_json(ROOT / cls.evidence["clientManifest"])
        cls.design = read_json(ROOT / cls.evidence["design"])
        cls.section = next(row for row in cls.manifest["gauntlet"]["sections"]
                           if row["id"] == cls.fixture["wave"]["section"])

    def test_canonical_map_and_preserved_authored_wave_centre(self):
        fixture = self.fixture
        registry = read_json(ROOT / "godot-client/data/maps/registry.json")
        registry = registry.get("maps", registry)
        row = registry[fixture["map"]]
        self.assertNotIn("alias", row)
        self.assertEqual(row["manifest"], "res://../" + self.evidence["clientManifest"])
        self.assertEqual(fixture["waveCentreTile"], self.section["centre"])
        self.assertNotEqual(fixture["centreTile"], fixture["waveCentreTile"])

    def test_observer_is_unused_published_walkable_tile_beside_the_pack(self):
        fixture, observer = self.fixture, self.fixture["observer"]
        centre = fixture["centreTile"]
        mouth = next(row for row in self.section["mouths"] if row["id"] == observer["mouth"])
        self.assertEqual(observer["positionScope"], "unused_published_mouth_spawn_tile")
        self.assertIn(centre, mouth["spawnTiles"])
        self.assertNotIn(centre, [row["tile"] for row in fixture["actors"]])
        manifest = ROOT / self.evidence["clientManifest"]
        served = self.manifest["collision"]["servedGrid"]
        path = manifest.parent / served["binary"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), served["sha256"])
        grid = Grid(path)
        self.assertTrue(grid.open(*centre))
        self.assertEqual(grid.codes[centre[1]][centre[0]], observer["servedGridCode"])
        nearby = [row for row in fixture["actors"] if row["mouth"] == observer["mouth"]]
        self.assertEqual(observer["nearbyActorIds"], [row["actorId"] for row in nearby])
        self.assertEqual(observer["minimumExpectedInFrustumCreatures"], len(nearby))
        self.assertGreaterEqual(len(nearby), 7)
        for actor in nearby:
            tile = actor["tile"]
            self.assertLessEqual(math.dist(centre, tile), observer["nearbyMaxDistanceMetres"])
            self.assertTrue(grid.open(*tile))
            self.assertEqual(grid.codes[tile[1]][tile[0]], observer["servedGridCode"])

    def test_exact_single_pulse_population_and_party_scaling(self):
        fixture, wave = self.fixture, self.fixture["wave"]
        band = next(row for row in self.design["bands"] if row["id"] == wave["band"])
        variant = next(row for row in band["waves"][wave["section"]]
                       if row["id"] == wave["variant"])
        pulse = variant["pulses"][wave["pulse"] - 1]
        self.assertEqual(wave["partyScale"], self.design["partyScale"][str(wave["partySize"])])
        self.assertEqual(wave["releaseAliveFraction"], self.design["pulse"]["releaseAliveFraction"])
        self.assertEqual(wave["releaseSeconds"], self.design["pulse"]["releaseSeconds"])
        self.assertEqual(len(fixture["spawnGroups"]), len(pulse["groups"]))
        expected = Counter()
        for group, (creature, count, shape) in zip(fixture["spawnGroups"], pulse["groups"]):
            wanted = count if shape == "leader" else math.floor(count * wave["partyScale"] + .5)
            expected[creature] += wanted
            self.assertEqual(group["creature"], creature)
            self.assertEqual(group["shape"], shape)
            self.assertEqual(group["partyBase"], 0 if shape == "leader" else count)
            self.assertEqual(group["count"], wanted)
            self.assertEqual(group["levelFactor"], self.design["shapes"][shape])
        actual = Counter(row["profile"] for row in fixture["actors"])
        self.assertEqual(actual, expected)
        self.assertEqual(sum(actual.values()), wave["totalCreatures"])
        self.assertEqual({p["creature"]: p["count"] for p in fixture["profiles"]}, dict(actual))
        self.assertEqual(actual, {"mire_goblin": 20, "giant_amber_moth": 1})

    def test_authored_spawn_tiles_are_unique_and_named_mouths_match(self):
        mouths = {row["id"]: row["spawnTiles"] for row in self.section["mouths"]}
        groups = {row["id"]: row for row in self.fixture["spawnGroups"]}
        seen_ids, seen_tiles = {self.fixture["localActorId"]}, {tuple(self.fixture["centreTile"])}
        for actor in self.fixture["actors"]:
            self.assertNotIn(actor["actorId"], seen_ids)
            self.assertNotIn(tuple(actor["tile"]), seen_tiles)
            self.assertIn(actor["tile"], mouths[actor["mouth"]])
            self.assertEqual(actor["profile"], groups[actor["spawnGroup"]]["creature"])
            seen_ids.add(actor["actorId"])
            seen_tiles.add(tuple(actor["tile"]))

    def test_current_retained_models_and_import_scales(self):
        models = read_json(ROOT / self.evidence["models"])
        retired = read_json(ROOT / self.evidence["retirementPolicy"])
        roster = {row["id"]: row for row in read_json(ROOT / self.evidence["currentModelRoster"])["creatures"]}
        for profile in self.fixture["profiles"]:
            model = models["models"][profile["model"]]
            self.assertEqual(models["actorTypes"][str(profile["actorType"])], profile["model"])
            self.assertFalse(model.get("retired", False))
            self.assertNotIn(profile["actorType"], retired["retiredActorTypes"])
            self.assertNotIn(profile["model"], retired["retiredActorModels"])
            self.assertEqual(profile["scene"], model["scene"])
            self.assertNotIn(profile["scene"].removeprefix("res://assets/"), retired["runtimePaths"])
            self.assertEqual(profile["modelImportScale"], model["import"]["scale"])
            path = ROOT / "godot-client" / profile["scene"].removeprefix("res://")
            self.assertTrue(path.with_suffix(path.suffix + ".import").is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), profile["sceneSha256"])
            self.assertEqual(roster[profile["model"]]["sha256"], profile["sceneSha256"])
            self.assertIn("current", roster[profile["model"]]["status"])
            self.assertEqual(profile["scale"], 1.0, "server DTO scale must not repeat the import scale")
            self.assertEqual(profile["footprint"], [1, 1])

    def test_exact_served_groups_when_server_checkout_is_available(self):
        path = ROOT / self.evidence["serverSpawnGroups"]
        if not path.is_file():
            self.skipTest("server checkout is optional for client-only source tests")
        blocks = {fields(block)["spawn_name"]: block for block in
                  re.findall(r"\[spawn\](.*?)\[/spawn\]", path.read_text(), re.S)}
        for group in self.fixture["spawnGroups"]:
            block = blocks[group["id"]]
            meta = fields(block.split("[monster]", 1)[0])
            self.assertEqual(meta["map_id"], "./maps/nymara/" + self.fixture["map"] + ".elm")
            self.assertEqual(int(meta["pulse"]), self.fixture["wave"]["pulse"])
            self.assertEqual(int(meta.get("party_base", 0)), group["partyBase"])
            self.assertEqual(float(meta.get("level_factor", 1.0)), group["levelFactor"])
            monsters = [fields(row) for row in re.findall(r"\[monster\](.*?)\[/monster\]", block, re.S)]
            expected = [(row["type"], [int(row["x_pos"]), int(row["y_pos"])]) for row in monsters]
            actual = [(row["profile"], row["tile"]) for row in self.fixture["actors"]
                      if row["spawnGroup"] == group["id"]]
            self.assertEqual(actual, expected)
            self.assertEqual(int(meta["min"]), len(expected))
            self.assertEqual(int(meta["max"]), len(expected))

    def test_server_actor_scale_and_footprint_when_available(self):
        path = ROOT / self.evidence["serverCreatures"]
        if not path.is_file():
            self.skipTest("server checkout is optional for client-only source tests")
        creatures = {fields(block)["type"]: fields(block) for block in
                     re.findall(r"\[monster\](.*?)\[/monster\]", path.read_text(), re.S)}
        for profile in self.fixture["profiles"]:
            creature = creatures[profile["creature"]]
            shape = creature.get("footprint", "1").split("x")
            footprint = [int(shape[0]), int(shape[-1])]
            self.assertEqual(profile["actorType"], int(creature["actor_type"]))
            self.assertEqual(profile["scale"], float(creature.get("scale", 1.0)))
            self.assertEqual(profile["footprint"], footprint)
            self.assertEqual(profile["health"], int(creature["material_points"]))


if __name__ == "__main__":
    unittest.main()
