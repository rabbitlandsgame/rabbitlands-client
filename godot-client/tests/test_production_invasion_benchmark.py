"""Production-cohort evidence checks; no engine, GPU or large asset reads."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_crowd_benchmark_runner as base
support, runner = base.support, base.runner


def steady_evidence(data, request):
    required = request["mode"] == "windowed" and request["renderer"] == "gl_compatibility"
    state = {"frameCap": request["fps_cap"], "vsyncMode": 0, "warmingRequired": required,
             "arrivalPending": False, "arrivalVisible": False, "headWarmupActive": False,
             "cameraWarmup": {"active": False, "view": 240, "views": 240, "frames_per_view": 2, "timed_out": False}}
    cell = data["cells"][0]
    cell["pacing"] = {"preSample": copy.deepcopy(state), "afterSample": copy.deepcopy(state)}
    for observed in (data, cell["effectiveRuntime"]): observed["effectiveSettings"]["vsyncMode"] = 0
    if "preSample" not in cell["census"]:
        cell["census"]["preSample"] = copy.deepcopy(cell["census"]["afterSpawn"])
    for census in cell["census"].values():
        built = census["builtBodies"]
        census.update(visibleBuiltBodies=built, inFrustumBuiltBodies=built,
                      bodyTierFull=built, bodyTierHalf=0, bodyTierQuarter=0, bodyTierPaused=0)


def fixture(remote=300):
    data, request = base.performance_fixture()
    name = f"production-undead-{remote}"
    request.update(cells=name, map="twinbrook")
    profiles = [{"model": species, **profile, "health": health, "scale": 1.0}
                for (species, profile), health in zip(support.UNDEAD_SPECIES.items(), (400, 262, 1088))]
    data.update(map="twinbrook", centreTile=[453, 168],
                creatureCohort={"id": "twinbrook-onslaught-v1", "profiles": profiles, "sourceWaveMaximum": 500},
                creatureFootprints={str(p["actorType"]): p["footprint"] for p in profiles},
                prewarmed={"creatureModels": list(support.UNDEAD_SPECIES)})
    cell = data["cells"][0]
    counts = {species: remote // 3 + int(index < remote % 3)
              for index, species in enumerate(support.UNDEAD_SPECIES)}
    active = (remote + 2) // 3
    names = list(support.UNDEAD_SPECIES)
    def species(indices):
        return {name: sum(names[index % 3] == name for index in indices) for name in names}
    cell.update(id=name, count=remote + 1, creatureCount=remote, cohort="twinbrook-onslaught-v1",
                populationScope="remote_creatures_plus_one_player", speciesCounts=counts,
                stressAboveDefaultServerCaps=remote > 160, combatDriver="melee_only",
                plan={"active": active, "moving": (active + 1) // 2, "fighting": active // 2},
                activitySpecies={"active": species(range(active)), "moving": species(range(0, active, 2)),
                                 "fighting": species(range(1, active, 2))})
    for boundary in cell["census"].values():
        boundary.update(nodes=remote + 1, deferred=remote + 1 - boundary["builtBodies"],
                        productionUndead={"remoteCreatures": remote, "localPlayers": 1,
                                          "species": counts.copy(), "invalidProfiles": 0,
                                          "aliveRemoteCreatures": remote, "invalidHealth": 0})
    for metric in ("actorRecords", "actorNodes"):
        cell["summary"][metric] = base.distribution([float(remote + 1)] * 60)
    steady_evidence(data, request)
    return data, request


def gauntlet_report():
    data, request = base.performance_fixture()
    fixture = support.gauntlet_fixture()
    request.update(cells=support.GAUNTLET_CELL, map=fixture["map"])
    species = {p["model"]: p["count"] for p in fixture["profiles"]}
    data.update(map=fixture["map"], centreTile=fixture["centreTile"],
                creatureFootprints={str(p["actorType"]): p["footprint"] for p in fixture["profiles"]},
                creatureCohort={"id": "resinroad-sounder-w5-pulse3-v1", "fixture": "res://" + support.GAUNTLET_FIXTURE,
                               "fixtureSha256": support.sha256_file(Path(support.__file__).resolve().parents[2] / support.GAUNTLET_FIXTURE),
                               "profiles": fixture["profiles"], "wave": fixture["wave"], "qualification": fixture["qualification"],
                               "waveCentreTile": fixture.get("waveCentreTile"), "observer": fixture.get("observer")},
                prewarmed={"creatureModels": list(species)})
    cell = data["cells"][0]
    cell.update(id=support.GAUNTLET_CELL, count=22, creatureCount=21, cohort="resinroad-sounder-w5-pulse3-v1",
                populationScope="remote_creatures_plus_one_player", speciesCounts=species,
                positionScope="exact_authored_spawn_tiles", combatDriver="scripted_melee_only",
                plan={"active": 21, "moving": 0, "fighting": 21},
                activitySpecies={"active": species, "moving": {}, "fighting": species})
    for boundary in cell["census"].values():
        boundary.update(nodes=22, builtBodies=22, deferred=0,
                        authoredGauntlet={"remoteCreatures": 21, "localPlayers": 1, "species": species, "invalidProfiles": 0,
                                          "aliveRemoteCreatures": 21, "invalidHealth": 0})
    for metric in ("actorRecords", "actorNodes"):
        cell["summary"][metric] = base.distribution([22.] * 60)
    steady_evidence(data, request)
    return data, request


class ProductionInvasion(unittest.TestCase):
    def test_authored_gauntlet_selector_map_census_and_activity(self):
        name = support.GAUNTLET_CELL
        self.assertEqual(support.selected_cells(name), [name])
        self.assertNotIn(name, support.selected_cells("all"))
        args = runner.parser().parse_args(["--godot", sys.executable, "--cells", name])
        support.configure_settings_profile(args)
        self.assertEqual((args.map, args.centre), ("resin_road_gauntlet", ",".join(str(v) for v in support.gauntlet_fixture()["centreTile"])))
        for flags in (["--map", "landfall"], ["--centre", "1,2"], ["--cells", name + ",empty"]):
            args = runner.parser().parse_args(["--godot", sys.executable, "--cells", name, *flags])
            with self.assertRaises(support.EvidenceError): support.configure_settings_profile(args)
        data, request = gauntlet_report()
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for mutate in (lambda d: d["creatureCohort"].update(fixtureSha256="0"*64),
                       lambda d: d["creatureCohort"]["wave"].update(pulse=2),
                       lambda d: d["cells"][0].update(count=21),
                       lambda d: d["cells"][0]["plan"].update(moving=1),
                       lambda d: d["cells"][0]["census"]["afterSample"]["authoredGauntlet"].update(invalidProfiles=1)):
            bad = copy.deepcopy(data)
            mutate(bad)
            with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")

    def test_new_creature_cohorts_reject_dead_or_invalid_health_census(self):
        for factory, census_key, remote in ((fixture, "productionUndead", 300),
                                             (gauntlet_report, "authoredGauntlet", 21)):
            data, request = factory()
            self.assertTrue(support.validate_report(data, request, "")["valid"])
            for boundary in ("afterSpawn", "afterSample"):
                for field, value in (("aliveRemoteCreatures", remote - 1), ("invalidHealth", 1)):
                    bad = copy.deepcopy(data)
                    bad["cells"][0]["census"][boundary][census_key][field] = value
                    with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")

    def test_cohort_footprint_table_and_actual_built_body_census(self):
        for factory in (fixture, gauntlet_report):
            data, request = factory()
            bad = copy.deepcopy(data)
            bad["creatureFootprints"][next(iter(bad["creatureFootprints"]))] = [9, 9]
            with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")
            for sample in data["cells"][0]["census"].values():
                built = sample["builtBodies"]
                sample.update(visibleBuiltBodies=built, inFrustumBuiltBodies=built,
                              bodyTierFull=built, bodyTierHalf=0, bodyTierQuarter=0, bodyTierPaused=0)
            self.assertTrue(support.validate_report(data, request, "")["valid"])
            for field in ("visibleBuiltBodies", "inFrustumBuiltBodies", "bodyTierFull"):
                bad = copy.deepcopy(data)
                bad["cells"][0]["census"]["afterSample"][field] += 1
                with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")

    def test_pacing_warming_and_required_body_evidence_rejects_faults(self):
        for factory in (fixture, gauntlet_report):
            data, request = factory()
            request["renderer"] = "gl_compatibility"
            data["renderingMethod"] = "gl_compatibility"
            for observed in (data, data["cells"][0]["effectiveRuntime"]):
                observed["effectiveSettings"]["renderer"] = "gl_compatibility"
            steady_evidence(data, request)
            self.assertTrue(support.validate_report(data, request, "")["valid"])
            for boundary in ("preSample", "afterSample"):
                for field, value in (("vsyncMode", 1), ("frameCap", 60), ("arrivalVisible", True)):
                    bad = copy.deepcopy(data)
                    bad["cells"][0]["pacing"][boundary][field] = value
                    with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")
                for field, value in (("active", True), ("view", 239), ("frames_per_view", 1), ("timed_out", True)):
                    bad = copy.deepcopy(data)
                    bad["cells"][0]["pacing"][boundary]["cameraWarmup"][field] = value
                    with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")
            for field in ("visibleBuiltBodies", "inFrustumBuiltBodies", "bodyTierFull", "bodyTierHalf", "bodyTierQuarter", "bodyTierPaused"):
                bad = copy.deepcopy(data)
                del bad["cells"][0]["census"]["afterSample"][field]
                with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")
            for boundary in (data, data["cells"][0]["effectiveRuntime"]):
                bad = copy.deepcopy(boundary)
                bad["effectiveSettings"]["vsyncMode"] = 1
                with self.assertRaises(support.EvidenceError):
                    support.validate_runtime(bad, request, "gl_compatibility", "low", 60, "boundary")

    def test_both_performance_profiles_require_every_graphics_flag(self):
        for profile in support.PERFORMANCE_PROFILES:
            data, request = fixture()
            request.update(settings_profile=profile, fps_cap=support.PERFORMANCE_PROFILES[profile])
            runtime = data["cells"][0]["effectiveRuntime"]
            runtime["effectiveSettings"]["frameCap"] = request["fps_cap"]
            runtime["effectiveSettings"]["renderScale"] = support.PERFORMANCE_RENDER_SCALES[profile]
            support.validate_runtime(runtime, request, "forward_plus", "low", 60, "valid")
            for field, value in (("clothBudget", 8), ("shadowsPreference", True), ("sunShadowsEnabled", True),
                                 ("particlesEnabled", False), ("decorativeGrass", True), ("nameDistanceMetres", 40)):
                bad = copy.deepcopy(runtime)
                bad["effectiveSettings"][field] = value
                with self.assertRaises(support.EvidenceError): support.validate_runtime(bad, request, "forward_plus", "low", 60, "bad")

    def test_gauntlet_requires_a_creature_body_in_the_sample_view(self):
        data, request = gauntlet_report()
        minimum = support.gauntlet_fixture()["observer"]["minimumExpectedInFrustumCreatures"] + 1
        for boundary in ("preSample", "afterSample"):
            for visible in (1, 2, minimum - 1):
                bad = copy.deepcopy(data)
                bad["cells"][0]["census"][boundary]["inFrustumBuiltBodies"] = visible
                with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")
            data["cells"][0]["census"][boundary]["inFrustumBuiltBodies"] = minimum
        self.assertTrue(support.validate_report(data, request, "")["valid"])

    def test_scale50_profile_changes_only_render_scale_from_performance60(self):
        profile = "performance-60-scale50"
        args = runner.parser().parse_args(["--godot", sys.executable, "--settings-profile", profile])
        support.configure_settings_profile(args)
        self.assertEqual((args.quality, args.fps_cap, args.body_cap), ("low", 60, 60))
        for system, variable in (("Linux", "XDG_DATA_HOME"), ("Windows", "APPDATA")):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base.write_project(root)
                texts = {}
                for name in ("performance", "performance-60", profile):
                    fresh = root / name
                    fresh.mkdir()
                    texts[name] = support.seed_settings_profile(name, root, fresh, {variable: str(fresh)}, system)["content"]
                self.assertEqual(texts[profile], texts["performance-60"].replace("render_scale=0.75\n", "render_scale=0.5\n"))
                self.assertEqual(texts["performance-60"], texts["performance"].replace("fps_limit=30\n", "fps_limit=60\n"))
        data, request = fixture()
        request.update(settings_profile=profile, fps_cap=60)
        runtime = data["cells"][0]["effectiveRuntime"]
        runtime["effectiveSettings"].update(frameCap=60, renderScale=.5)
        support.validate_runtime(runtime, request, "forward_plus", "low", 60, "valid")
        for scale in (.75, 1.0):
            runtime["effectiveSettings"]["renderScale"] = scale
            with self.assertRaises(support.EvidenceError): support.validate_runtime(runtime, request, "forward_plus", "low", 60, "bad")
        for flags in (["--fps-cap", "30"], ["--body-cap", "160"], ["--quality", "high"], ["--tuning", "cloth=8"]):
            args = runner.parser().parse_args(["--godot", sys.executable, "--settings-profile", profile, *flags])
            with self.assertRaises(support.EvidenceError): support.configure_settings_profile(args)

    def test_authored_gauntlet_json_is_in_source_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / support.GAUNTLET_FIXTURE
            fixture.parent.mkdir(parents=True)
            fixture.write_text('{"fixture":1}')
            self.assertIn(fixture, support.source_files(root))
            before = support.hash_files(support.source_files(root)[1:], root)
            fixture.write_text('{"fixture":2}')
            self.assertNotEqual(before["sha256"], support.hash_files(support.source_files(root)[1:], root)["sha256"])

    def test_performance60_seed_differs_only_in_frame_cap_and_rejects_overrides(self):
        for system in ("Linux", "Windows"):
            args = runner.parser().parse_args(["--godot", sys.executable, "--settings-profile", "performance-60"])
            support.configure_settings_profile(args, system)
            self.assertEqual((args.quality, args.fps_cap, args.body_cap), ("low", 60, 60))
            support.configure_settings_profile(args, system)
        for flags in (["--quality", "high"], ["--fps-cap", "30"], ["--body-cap", "160"], ["--tuning", "cloth=8"]):
            args = runner.parser().parse_args(["--godot", sys.executable, "--settings-profile", "performance-60", *flags])
            with self.assertRaises(support.EvidenceError): support.configure_settings_profile(args)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base.write_project(root)
            texts = {}
            for profile in ("performance", "performance-60"):
                fresh = root / profile
                fresh.mkdir()
                metadata = support.seed_settings_profile(profile, root, fresh, {"XDG_DATA_HOME": str(fresh)}, "Linux")
                texts[profile] = metadata["content"]
            self.assertEqual(texts["performance-60"], texts["performance"].replace("fps_limit=30\n", "fps_limit=60\n"))

    def test_performance60_requires_actual_matching_graphics_and_frame_cap(self):
        data, request = fixture()
        request.update(settings_profile="performance-60", fps_cap=60)
        data["measurement"]["fpsCap"] = 60
        for state in data["cells"][0]["pacing"].values(): state["frameCap"] = 60
        for observed in (data, data["cells"][0]["effectiveRuntime"]):
            observed["effectiveSettings"].update(frameCap=60, clothBudget=0, shadowsPreference=False,
                                                  sunShadowsEnabled=False, particlesEnabled=True,
                                                  decorativeGrass=False, nameDistanceMetres=20.0)
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for field, value in (("renderScale", 1.0), ("textureQuality", "full"), ("frameCap", 30),
                             ("clothBudget", 8), ("decorativeGrass", True), ("nameDistanceMetres", 40)):
            bad = copy.deepcopy(data)
            bad["cells"][0]["effectiveRuntime"]["effectiveSettings"][field] = value
            with self.assertRaises(support.EvidenceError): support.validate_report(bad, request, "")

    def test_selectors_are_separate_and_pin_authored_map(self):
        self.assertEqual(support.selected_cells("production-undead"), support.UNDEAD_CELLS)
        self.assertFalse(set(support.UNDEAD_CELLS) & set(support.selected_cells("all")))
        args = runner.parser().parse_args(["--godot", sys.executable, "--settings-profile", "performance",
                                           "--cells", "production-undead-160"])
        support.configure_settings_profile(args, system="Linux")
        self.assertEqual((args.map, args.centre, args.fps_cap, args.body_cap), ("twinbrook", "453,168", 30, 60))
        for flags in (["--map", "landfall"], ["--centre", "675,186"],
                      ["--cells", "s2-invasion-160,production-undead-160"]):
            bad = runner.parser().parse_args(["--godot", sys.executable, "--cells", "production-undead-160", *flags])
            with self.assertRaises(support.EvidenceError):
                support.configure_settings_profile(bad)

    def test_each_population_validates_as_remote_creatures_plus_one_player(self):
        for count in (160, 300, 500):
            data, request = fixture(count)
            self.assertTrue(support.validate_report(data, request, "")["valid"])
        self.assertEqual(fixture()[0]["cells"][0]["activitySpecies"]["active"],
                         {"zombie": 34, "skeleton": 33, "drowned_lich_king": 33})

    def test_actual_profile_population_and_prewarm_tampering_are_rejected(self):
        data, request = fixture()
        for field, value in (("count", 300), ("creatureCount", 299), ("combatDriver", "mixed"),
                             ("stressAboveDefaultServerCaps", False),
                             ("speciesCounts", {"zombie": 300})):
            bad = copy.deepcopy(data)
            bad["cells"][0][field] = value
            with self.assertRaises(support.EvidenceError):
                support.validate_report(bad, request, "")
        for field, value in (("remoteCreatures", 299), ("localPlayers", 0), ("invalidProfiles", 1)):
            bad = copy.deepcopy(data)
            bad["cells"][0]["census"]["afterSample"]["productionUndead"][field] = value
            with self.assertRaises(support.EvidenceError):
                support.validate_report(bad, request, "")
        for where in ("centre", "prewarm", "activity", "footprint"):
            bad = copy.deepcopy(data)
            if where == "centre": bad["centreTile"] = [675, 186]
            if where == "prewarm": bad["prewarmed"]["creatureModels"].append("shrew")
            if where == "activity": bad["cells"][0]["activitySpecies"]["active"] = {"zombie": 100}
            if where == "footprint": bad["creatureCohort"]["profiles"][2]["footprint"] = [1, 1]
            with self.assertRaises(support.EvidenceError):
                support.validate_report(bad, request, "")

    def test_external_catalog_images_and_alias_world_are_in_asset_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, maps = root / "app", root / "eloria-assets/maps"
            (client / "data/maps").mkdir(parents=True)
            maps.mkdir(parents=True)
            (maps / "world.json").write_text('{}')
            (maps / "map.webp").write_bytes(b'picture-one')
            (maps / "room.webp").write_bytes(b'picture-two')
            (client / "data/maps/registry.json").write_text(json.dumps({"maps": {
                "canonical": {"manifest": "res://../eloria-assets/maps/world.json"},
                "alias": {"alias": "canonical"}}}))
            catalog = {"maps": {"canonical": {"path": "res://../eloria-assets/maps/map.webp", "sections": {
                "secret": {"path": "res://../eloria-assets/maps/room.webp"}}}}}
            path = client / "data/maps/map-backgrounds.json"
            path.write_text(json.dumps(catalog))
            files = support.asset_files(client, ["alias"])
            self.assertTrue({maps / "world.json", maps / "map.webp", maps / "room.webp"} <= set(files))
            (maps / "room.webp").unlink()
            with self.assertRaises(support.EvidenceError): support.asset_files(client, ["alias"])


if __name__ == "__main__":
    unittest.main()
