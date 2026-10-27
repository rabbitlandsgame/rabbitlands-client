"""Pure acceptance/identity tests; no engine, player profiles or asset reads."""
from pathlib import Path
import sys
import tempfile
import unittest
import io
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import interior_load_benchmark as bench


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.config = {"run_id":"fresh","qualification":False}
        self.report = {"ok":True,"configuration":self.config,"configuration_sha256":"sha",
                       "window_start":{"focused":True},"window_end":{"focused":True},
                       "timing":{"load_call_ms":12,"first_ready_ms":40},"frames":[{"focused":True}]}

    def errors(self, report=None, **kwargs):
        return bench.qualification_errors(self.report if report is None else report,self.config,"sha",
                                          {"file":"a"},kwargs.get("after",{"file":"a"}),kwargs.get("output",""))

    def test_valid_load(self):
        self.assertEqual(self.errors(),[])

    def test_missing_report(self):
        self.assertIn("fresh_report_missing",bench.qualification_errors(None,self.config,"sha",{},{},""))

    def test_old_report(self):
        self.report["configuration"] = {"run_id":"stale"}
        self.assertIn("report_run_id_mismatch",self.errors())

    def test_configuration_change(self):
        self.report["configuration_sha256"] = "other"
        self.assertIn("report_configuration_digest_mismatch",self.errors())

    def test_source_change(self):
        self.assertIn("runtime_or_import_inputs_changed",self.errors(after={"file":"b"}))

    def test_exit_zero_late_error(self):
        self.assertIn("engine_error_in_complete_log",self.errors(output="INTERIOR_DONE PASS\nERROR: leaked RID\n"))

    def test_script_error(self):
        self.assertIn("engine_error_in_complete_log",self.errors(output="SCRIPT ERROR: failed\n"))

    def test_empty_measured_work(self):
        self.report["timing"] = {}
        self.assertIn("measured_load_missing",self.errors())

    def test_unfocused_frame_rejected(self):
        self.report["frames"][0]["focused"] = False
        self.assertIn("measured_window_not_focused",self.errors())

    def test_readback_mode_requires_witness(self):
        self.config["qualification"] = True
        self.assertIn("qualification_witness_missing",self.errors())


def sample(identity,mode,start,load=200,ready=300,rss=1000):
    return {"qualified":True,"configuration":{"run_id":identity,"mode":mode,"target":"map","qualification":False},
            "runtime_inputs_sha256":"runtime","source_inputs_sha256":"assets","cache_inputs_sha256":"cache",
            "process_started_monotonic_ns":start,"report":{"timing":{"load_call_ms":load,"first_ready_ms":ready,"through_settled_ms":ready+500}},
            "process_memory":{"peak_process_rss_bytes":rss}}


class CohortTests(unittest.TestCase):
    def setUp(self):
        self.raw = [sample(str(i),"raw",i*4) for i in range(3)]
        self.native = [sample(str(i+3),"native",i*4+(1 if i != 1 else -1),150,260) for i in range(3)]

    def test_predeclared_thresholds(self):
        result = bench.compare(self.raw,self.native)
        self.assertTrue(result["pass"])
        self.assertEqual(result["orders"],["AB","BA","AB"])

    def test_reused_runs_rejected(self):
        with self.assertRaises(ValueError): bench.compare([self.raw[0]]*3,self.native)

    def test_wrong_arm_rejected(self):
        self.native[0]["configuration"]["mode"] = "raw"
        with self.assertRaises(ValueError): bench.compare(self.raw,self.native)

    def test_parse_only_cannot_qualify_timings(self):
        self.native[0]["parse_only"] = True
        with self.assertRaises(ValueError): bench.compare(self.raw,self.native)

    def test_three_pairs_required(self):
        with self.assertRaises(ValueError): bench.compare(self.raw[:2],self.native[:2])

    def test_counterbalance_required(self):
        self.native[1]["process_started_monotonic_ns"] = 6
        with self.assertRaises(ValueError): bench.compare(self.raw,self.native)

    def test_settings_must_match(self):
        self.native[0]["configuration"]["texture_skip"] = 1
        with self.assertRaises(ValueError): bench.compare(self.raw,self.native)

    def test_cross_process_input_identity(self):
        self.native[0]["runtime_inputs_sha256"] = "changed"
        with self.assertRaises(ValueError): bench.compare(self.raw,self.native)

    def test_prepared_cache_generation_must_match(self):
        self.native[0]["cache_inputs_sha256"] = "different"
        with self.assertRaises(ValueError): bench.compare(self.raw,self.native)

    def test_large_load_needs_twenty_percent(self):
        self.native[0]["report"]["timing"]["load_call_ms"] = 180
        self.native[1]["report"]["timing"]["load_call_ms"] = 180
        self.assertFalse(bench.compare(self.raw,self.native)["pass"])

    def test_small_load_allows_ten_ms(self):
        for row in self.raw: row["report"]["timing"]["load_call_ms"] = 50
        for row in self.native: row["report"]["timing"]["load_call_ms"] = 59
        self.assertTrue(bench.compare(self.raw,self.native)["pass"])

    def test_highwater_memory_limit(self):
        self.native[2]["process_memory"]["peak_process_rss_bytes"] = 1101
        self.assertFalse(bench.compare(self.raw,self.native)["peak_rss"]["pass"])

    def test_work_delayed_after_ready_rejected(self):
        for row in self.native: row["report"]["timing"]["through_settled_ms"] = 1200
        self.assertFalse(bench.compare(self.raw,self.native)["through_settled"]["pass"])


class ClosureTests(unittest.TestCase):
    def test_portable_owned_cache_path(self):
        root = bench.ROOT / ".local/interior-load-benchmark/unit-profile"
        path = bench.safe_user_path("user://map-geometry-cache/policy/blobs/a.scn",root)
        self.assertTrue(path.is_relative_to(root))

    def test_path_escape_rejected(self):
        for path in ["user://map-geometry-cache/../../secret", "user://other/a", "C:/private/a",
                     "user://map-geometry-cache/policy\\blob", "user://map-geometry-cache/C:/blob"]:
            with self.subTest(path=path), self.assertRaises(ValueError): bench.safe_user_path(path,Path("C:/fixture"))

    def test_seed_only_declared_closure_and_verify_payload(self):
        parent = bench.ROOT / ".local/interior-load-benchmark/unit-fixtures"
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root = Path(folder)
            source,destination = root/"source",root/"destination"
            policy = source/"map-geometry-cache/policy"
            (policy/"entries").mkdir(parents=True)
            (policy/"blobs").mkdir()
            blob = policy/"blobs/good.scn"
            blob.write_bytes(b"native")
            (policy/"blobs/unrelated.scn").write_bytes(b"unrelated")
            bench.write(policy/"entries/world.json",{"source":"eloria-assets/world.json","kind":"world",
                        "payloads":{"user://map-geometry-cache/policy/blobs/good.scn":bench.digest(blob)}})
            result = bench.seed_cache(source,destination,"eloria-assets/world.json")
            self.assertEqual(result["files"],2)
            self.assertFalse((destination/"map-geometry-cache/policy/blobs/unrelated.scn").exists())
            blob.write_bytes(b"corrupt")
            with self.assertRaises(ValueError): bench.seed_cache(source,root/"second","eloria-assets/world.json")


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"qualified":True,"configuration":{"run_id":"raw-witness","mode":"raw","target":"map","qualification":True},
                    "runtime_inputs_sha256":"code","source_inputs_sha256":"assets","cache_inputs_sha256":"cache",
                    "report":{"qualification":{"scene":{"digest":"same"},"views":[{"sha256":"pixel"}],"ground":[True]}}}
        self.native = __import__("copy").deepcopy(self.raw)
        self.native["configuration"].update(run_id="native-witness",mode="native")

    def test_exact_witness(self):
        self.assertTrue(bench.compare_witness(self.raw,self.native)["pass"])

    def test_changed_pixels_rejected(self):
        self.native["report"]["qualification"]["views"][0]["sha256"] = "changed"
        self.assertFalse(bench.compare_witness(self.raw,self.native)["pass"])

    def test_changed_materials_rejected(self):
        self.native["report"]["qualification"]["scene"]["digest"] = "changed"
        self.assertFalse(bench.compare_witness(self.raw,self.native)["pass"])

    def test_same_arm_witness_rejected(self):
        self.native["configuration"]["mode"] = "raw"
        with self.assertRaises(ValueError): bench.compare_witness(self.raw,self.native)

    def test_reused_witness_identity_rejected(self):
        self.native["configuration"]["run_id"] = "raw-witness"
        with self.assertRaises(ValueError): bench.compare_witness(self.raw,self.native)

    def test_missing_input_generation_rejected(self):
        self.raw.pop("cache_inputs_sha256")
        self.native.pop("cache_inputs_sha256")
        with self.assertRaises(ValueError): bench.compare_witness(self.raw,self.native)

    def test_witness_bound_to_cohort(self):
        raw = [sample(str(i),"raw",i*4) for i in range(3)]
        native = [sample(str(i+3),"native",i*4+(1 if i != 1 else -1),150,260) for i in range(3)]
        for row in raw+native:
            row.update(runtime_inputs_sha256="code",source_inputs_sha256="assets")
        self.assertTrue(bench.compare_cohort(raw,native,self.raw,self.native)["pass"])
        self.raw["configuration"]["target"] = "different"
        with self.assertRaises(ValueError): bench.compare_cohort(raw,native,self.raw,self.native)

    def test_old_witness_inputs_rejected(self):
        raw = [sample(str(i),"raw",i*4) for i in range(3)]
        native = [sample(str(i+3),"native",i*4+(1 if i != 1 else -1),150,260) for i in range(3)]
        with self.assertRaises(ValueError): bench.compare_cohort(raw,native,self.raw,self.native)


class ProductionGuards(unittest.TestCase):
    def test_unpromoted_candidate_requires_explicit_scope(self):
        with patch.object(bench,"read",side_effect=[{"maps":["production"]},{"maps":{"production":{"manifest":"res://production"}}}]):
            with self.assertRaisesRegex(ValueError,"outside the active native geometry scope"):
                bench.require_active_scope({"target":"candidate","manifest":"res://candidate"})

    def test_declared_experiment_scope_allowed(self):
        with patch.object(bench,"read",side_effect=[{"maps":["candidate"]},{"maps":{"candidate":{"manifest":"res://candidate"}}}]):
            bench.require_active_scope({"target":"candidate","manifest":"res://candidate"})

    def test_stop_only_live_owned_child_and_escalate_timeout(self):
        class Process:
            events=[]
            def poll(self):return None
            def terminate(self):self.events.append("terminate")
            def kill(self):self.events.append("kill")
            def wait(self,timeout):
                self.events.append("wait")
                if len(self.events)==2:raise bench.subprocess.TimeoutExpired("owned-godot",timeout)
                return 0
        process=Process()
        bench.stop_owned_process(process)
        self.assertEqual(process.events,["terminate","wait","kill","wait"])

    def test_completed_child_is_not_terminated(self):
        class Process:
            def poll(self):return 0
            def terminate(self):raise AssertionError("completed child must stay untouched")
        bench.stop_owned_process(Process())


class OwnedProcessSupervision(unittest.TestCase):
    class LogPath:
        def __init__(self):self.stream=io.StringIO()
        def open(self,*args,**kwargs):return self.stream
        def read_text(self,**kwargs):return self.stream.getvalue()

    class Process:
        pid=12345
        def __init__(self,events,complete=False):
            self.events=events
            self.returncode=0 if complete else None
        def poll(self):return self.returncode
        def terminate(self):
            self.events.append("terminate")
            self.returncode=-15
        def kill(self):
            self.events.append("kill")
            self.returncode=-9
        def wait(self,timeout):
            self.events.append(("wait",timeout))
            return self.returncode

    class Sampler:
        def __init__(self,events,error=None):self.events,self.error=events,error
        def sample(self):
            self.events.append("sample")
            if self.error:raise self.error
            return {"rss_bytes":123}
        def close(self):self.events.append("sampler_close")

    def supervise(self,process,sampler,log,*,sleep_error=None,clock=0.0,text=""):
        def spawn(*args,**kwargs):
            kwargs["stdout"].write(text)
            return process
        with patch.object(bench.subprocess,"Popen",side_effect=spawn), \
             patch.object(bench,"ProcessSampler",return_value=sampler), \
             patch.object(bench.time,"sleep",side_effect=sleep_error), \
             patch.object(bench.time,"monotonic",side_effect=clock if isinstance(clock,list) else None,return_value=clock):
            return bench.run_owned_engine(["owned-godot"],{},log,10)

    def test_normal_exit_closes_sampler_without_terminating_completed_child(self):
        events=[]
        log=self.LogPath()
        result=self.supervise(self.Process(events,complete=True),self.Sampler(events),log)
        self.assertEqual(result,(0,[{"rss_bytes":123}],False))
        self.assertEqual(events,[("wait",15),"sample","sampler_close"])
        self.assertTrue(log.stream.closed)

    def test_watchdog_stops_child_before_closing_sampler(self):
        events=[]
        result=self.supervise(self.Process(events),self.Sampler(events),self.LogPath(),clock=[0,11,11])
        self.assertTrue(result[2])
        self.assertNotEqual(result[0],0)
        self.assertEqual(events.count("terminate"),1)
        self.assertLess(events.index("terminate"),events.index("sampler_close"))

    def test_engine_error_stops_child_without_claiming_timeout(self):
        events=[]
        result=self.supervise(self.Process(events),self.Sampler(events),self.LogPath(),text="ERROR: engine failed\n")
        self.assertFalse(result[2])
        self.assertIn("terminate",events)
        self.assertEqual(events[-1],"sampler_close")

    def test_sampling_exception_still_stops_child_and_closes_sampler(self):
        events=[]
        log=self.LogPath()
        with self.assertRaisesRegex(RuntimeError,"sample failed"):
            self.supervise(self.Process(events),self.Sampler(events,RuntimeError("sample failed")),log)
        self.assertEqual(events,["sample","terminate",("wait",10),"sampler_close"])
        self.assertTrue(log.stream.closed)

    def test_keyboard_interrupt_cleans_up_before_benchmark_lock_release(self):
        events=[]
        process,sampler,log=self.Process(events),self.Sampler(events),self.LogPath()
        outer=self
        class Lock:
            def __enter__(self):events.append("lock_enter")
            def __exit__(self,*args):events.append("lock_exit")
        def run_locked(_args):
            return outer.supervise(process,sampler,log,sleep_error=KeyboardInterrupt())
        with patch.object(bench,"BenchmarkLock",return_value=Lock()),patch.object(bench,"_run_locked",side_effect=run_locked):
            with self.assertRaises(KeyboardInterrupt):bench.run(object())
        self.assertLess(events.index("terminate"),events.index("lock_exit"))
        self.assertLess(events.index("sampler_close"),events.index("lock_exit"))
        self.assertTrue(log.stream.closed)

    def test_sampler_initialization_failure_still_stops_child(self):
        events=[]
        log=self.LogPath()
        with patch.object(bench.subprocess,"Popen",return_value=self.Process(events)), \
             patch.object(bench,"ProcessSampler",side_effect=OSError("sampler unavailable")):
            with self.assertRaisesRegex(OSError,"sampler unavailable"):
                bench.run_owned_engine(["owned-godot"],{},log,10)
        self.assertEqual(events,["terminate",("wait",10)])
        self.assertTrue(log.stream.closed)

    def test_sampler_closes_even_if_process_cleanup_raises(self):
        events=[]
        with patch.object(bench,"stop_owned_process",side_effect=RuntimeError("cleanup failed")):
            with self.assertRaisesRegex(RuntimeError,"cleanup failed"):
                self.supervise(self.Process(events),self.Sampler(events,ValueError("sample failed")),self.LogPath())
        self.assertEqual(events[-1],"sampler_close")


if __name__ == "__main__":
    unittest.main()
