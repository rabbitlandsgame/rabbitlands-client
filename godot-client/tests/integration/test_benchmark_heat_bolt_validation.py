import copy
import unittest
from benchmark_heat_bolt_validation import HeatBoltEvidenceError, validate_heat_bolt_cell


def fixture(backend="rust"):
    counts = {"bursts":1,"spell_packets":143,"movement_packets":4,"moving_target_casts":28,
              "admitted_visuals":30,"observed_releases":30,"observed_arrivals":30,"observed_expiries":20,
              "local_priority_packets":1,"selected_priority_packets":1,"combat_priority_packets":2,
              "local_priority_admitted":1,"selected_priority_admitted":1,"combat_priority_admitted":2,
              "phase_regressions":0,"external_retirements":0,"maximum_observed_live":30}
    empty = {k:0 for k in counts}
    end = {"counters":counts,"powerPackets":{str(p):15 if p<=3 else 14 for p in range(1,11)},
           "powerAdmitted":{str(p):3 for p in range(1,11)},
           "admittedBackends":{k:30 if k==backend else 0 for k in ("rust","cpp","gd")}}
    workload = {"schemaVersion":1,"kind":"synthetic_heat_bolt_packets","family":"heat_bolt",
                "castsPerBurst":143,"movingActors":16,"onFootActors":160,"burstPeriodMilliseconds":2000,
                "priorityPacketOrder":"after-normal-burst","sampleStart":{"counters":empty},"sampleEnd":end,
                "sampleCounters":{k:v for k,v in counts.items() if k!="maximum_observed_live"},
                "removedTargetProbe":{k:True for k in ("success","outsideTimedSample","spellAdmitted",
                "actorRecordRemoved","actorPresentationRemoved","finiteFlightEndpoints","effectCompleted",
                "restoredRecord","restorationReady")}}
    cell = {"spellWorkload":workload,"census":{p:{"nodes":160,"mountedActors":0} for p in ("afterSpawn","afterSample")},
            "effectiveRuntime":{"activeBackends":{"rustSpellFlights":{"active":True,"frames":10,
             "fallbacks":0,"admitted_legacy":0,"admitted_rust":30,"events":{"releases":30,"arrivals":30,"expiries":20}},
             "clientRuntime":{"native":{"cpp_spell_flight_provider":"client_runtime"}}}}}
    request = {"rust_effects":"heat_bolt" if backend=="rust" else "legacy",
               "native_presentation":"flight" if backend=="cpp" else "off"}
    return cell, request


class HeatBoltValidationTests(unittest.TestCase):
    def test_valid_native_cpp_and_gd(self):
        for backend in ("rust","cpp","gd"):
            with self.subTest(backend=backend):
                validate_heat_bolt_cell(*fixture(backend))

    def test_backend_substitution_rejected(self):
        cell, request = fixture("gd")
        request["rust_effects"]="heat_bolt"
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell(cell, request)

    def test_missing_workload_rejected(self):
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell({}, {})

    def test_lifetime_and_delta_inconsistency_rejected(self):
        cell, request = fixture()
        cell["spellWorkload"]["sampleCounters"]["observed_arrivals"] -= 1
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell(cell, request)

    def test_partial_burst_or_missing_power_rejected(self):
        cell, request = fixture()
        for key in ("spell_packets", "local_priority_admitted"):
            broken = copy.deepcopy(cell)
            broken["spellWorkload"]["sampleEnd"]["counters"][key]-=1
            broken["spellWorkload"]["sampleCounters"][key]-=1
            with self.assertRaises(HeatBoltEvidenceError):
                validate_heat_bolt_cell(broken,request)
        del cell["spellWorkload"]["sampleEnd"]["powerAdmitted"]["10"]
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell(cell,request)

    def test_fallback_and_external_cpp_provider_rejected(self):
        cell, request = fixture()
        cell["effectiveRuntime"]["activeBackends"]["rustSpellFlights"]["fallbacks"]=1
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell(cell,request)
        cell, request = fixture("cpp")
        cell["effectiveRuntime"]["activeBackends"]["clientRuntime"]["native"]["cpp_spell_flight_provider"]="external"
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell(cell,request)

    def test_removal_probe_and_mount_census_rejected(self):
        cell, request = fixture()
        cell["spellWorkload"]["removedTargetProbe"]["restorationReady"]=False
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell(cell,request)
        cell, request = fixture()
        cell["census"]["afterSample"]["mountedActors"]=1
        with self.assertRaises(HeatBoltEvidenceError):
            validate_heat_bolt_cell(cell,request)

    def test_lifetime_maximum_is_not_a_hard_tier_cap(self):
        cell, request = fixture()
        workload = cell["spellWorkload"]
        workload["sampleEnd"]["counters"]["maximum_observed_live"]=51
        for key in ("admitted_visuals","observed_releases","observed_arrivals"):
            workload["sampleEnd"]["counters"][key]=60
            workload["sampleCounters"][key]=60
        workload["sampleEnd"]["powerAdmitted"]={str(p):6 for p in range(1,11)}
        workload["sampleEnd"]["admittedBackends"]["rust"]=60
        runtime=cell["effectiveRuntime"]["activeBackends"]["rustSpellFlights"]
        runtime["admitted_rust"]=60
        runtime["events"]["releases"]=60
        runtime["events"]["arrivals"]=60
        validate_heat_bolt_cell(cell,request)


if __name__ == "__main__":
    unittest.main()
