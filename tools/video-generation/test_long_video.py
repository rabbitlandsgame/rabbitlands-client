"""Artifact-level checks for checkpointing and overlap removal; no GPU needed."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import imageio.v2 as imageio
import numpy as np

import long_video as lv
import video


class ContinuousVideoTests(unittest.TestCase):
    def setUp(self):
        video.LOCAL.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="qa-long-video-", dir=video.LOCAL)
        self.root = Path(self.temp.name).resolve()
        self.plan = {"version": 1, "title": "QA", "seconds": 1.5, "prompt": "A continuous scene",
                     "negative_prompt": "", "width": 128, "height": 128, "fps": 16,
                     "frames": 17, "overlap": 5, "steps": 2, "guidance": 5.0,
                     "conditioning_scale": 1.0, "seed": 42, "segment_prompts": {}}
        self.state = {"version": 1, "segments": [], "renders": [], "history": []}
        for number, values in enumerate((range(17), range(12, 29))):
            path = self.root / f"part-{number}.mp4"
            with imageio.get_writer(str(path), fps=16, codec="libx264", quality=10,
                                   macro_block_size=16, ffmpeg_log_level="error") as writer:
                for value in values:
                    frame = np.zeros((128, 128, 3), dtype=np.uint8)
                    frame[:, :, 0] = value * 4
                    writer.append_data(frame)
            item = {"path": path.name, "sha256": video.sha256(path),
                    "append_from": 0 if number == 0 else 5, **lv.probe(path)}
            if number == 0:
                item["source"] = True
            else:
                item["recipe"] = lv.fingerprint(lv.recipe(self.plan, number, self.state["segments"][-1]["sha256"]))
            self.state["segments"].append(item)
        self.save()

    def tearDown(self):
        assert self.root.is_relative_to(video.LOCAL.resolve())
        self.temp.cleanup()

    def save(self):
        lv.save(self.root / "plan.json", self.plan)
        lv.save(self.root / "state.json", self.state)

    def test_context_retains_exact_tail_and_masks_only_future(self):
        path = self.root / "part-0.mp4"
        inputs, masks = lv.context_inputs(path, 5, 17, 128, 128)
        with imageio.get_reader(str(path)) as reader:
            source = [frame for frame in reader]
        for index in range(5):
            np.testing.assert_array_equal(np.array(inputs[index]), source[-5 + index])
            self.assertEqual(np.max(np.array(masks[index])), 0)
        self.assertEqual(len(inputs), 17)
        self.assertEqual(np.min(np.array(masks[5])), 255)
        self.assertEqual(inputs[5].getpixel((0, 0)), (127, 127, 127))

    def test_assembly_removes_overlap_and_trims_to_exact_target(self):
        with contextlib.redirect_stdout(io.StringIO()):
            output = lv.assemble(self.root, self.plan, self.state)
        self.assertEqual(lv.probe(output)["frames"], 24)
        with imageio.get_reader(str(output)) as reader:
            values = [float(np.asarray(frame)[:, :, 0].mean()) for frame in reader]
        np.testing.assert_allclose(values, np.arange(24) * 4, atol=6)
        self.assertTrue((self.root / "part-0.mp4").exists())

    def test_completed_resume_does_not_load_model_or_create_another_render(self):
        args = argparse.Namespace(limit=None, retry_from=None)
        with contextlib.redirect_stdout(io.StringIO()):
            lv.assemble(self.root, self.plan, self.state)
            with patch.object(lv, "load_pipeline", side_effect=AssertionError("Unexpected GPU load")):
                lv.run(self.root, args, self.plan, self.state)
        self.assertEqual(len(self.state["renders"]), 1)
        self.assertEqual(len(self.state["segments"]), 2)

    def test_longer_target_reuses_existing_segments(self):
        self.plan["seconds"] = 10
        self.assertEqual(lv.valid_segments(self.root, self.plan, self.state), 2)
        self.plan["segment_prompts"]["1"] = "The subject turns its head"
        self.assertEqual(lv.valid_segments(self.root, self.plan, self.state), 1)

    def test_retry_preserves_old_takes_and_clears_dependent_checkpoints(self):
        args = argparse.Namespace(limit=1, retry_from=1)
        old = self.state["segments"][1]
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(lv, "load_pipeline", side_effect=RuntimeError("Simulated interruption")):
                with self.assertRaisesRegex(RuntimeError, "Simulated interruption"):
                    lv.run(self.root, args, self.plan, self.state)
        saved = json.loads((self.root / "state.json").read_text())
        self.assertEqual(len(saved["segments"]), 1)
        self.assertEqual(saved["history"][-1]["segments"][0]["sha256"], old["sha256"])
        self.assertEqual(video.sha256(self.root / old["path"]), old["sha256"])

    def test_modified_checkpoint_is_rejected(self):
        (self.root / "part-1.mp4").write_bytes(b"interrupted transfer")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            lv.valid_segments(self.root, self.plan, self.state)

    def test_status_is_available_while_the_runner_is_locked(self):
        from filelock import FileLock
        with FileLock(str(self.root / ".runner.lock")):
            result = subprocess.run([sys.executable, lv.__file__, "status", "--project", str(self.root)],
                                    capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["target_reached"])


if __name__ == "__main__":
    unittest.main()
