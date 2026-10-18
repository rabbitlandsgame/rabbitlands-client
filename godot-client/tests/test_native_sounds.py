#!/usr/bin/env python3
"""Guard completeness, source integrity, audible levels and license delivery."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import tempfile
import unittest
import wave
import sys
from pathlib import Path
import numpy as np

CLIENT = Path(__file__).resolve().parents[1]
AUDIO = CLIENT / "assets/audio"
SOURCE = CLIENT.parent / "eloria-assets/source/audio"
sys.path.insert(0, str(CLIENT / 'tools'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class NativeSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((AUDIO / "catalog.json").read_text(encoding="utf-8"))
        cls.provenance = json.loads((AUDIO / "provenance.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))

    def test_catalog_covers_gameplay_and_every_surface(self):
        required = {"civic_crowd", "waterfall", "rain", "footstep", "combat_hit", "combat_miss", "harvest_start", "harvest_gather", "item_pickup", "spell_cast", "world_effect", "ui_click", "ui_close", "level_up"}
        required.update(f"footstep_{s}_{i}" for s in ("dirt", "grass", "stone", "wood", "sand", "snow") for i in range(1, 4))
        self.assertEqual({s["name"] for s in self.catalog["sounds"]}, required)
        self.assertEqual(len(self.catalog["sounds"]), len(required))
        self.assertEqual(len(self.catalog["music"]), 39)
        self.assertTrue({"settlement", "wilds", "depths"} <= {s["name"] for s in self.catalog["music"]})
        files = {s["file"] for s in self.catalog["sounds"] + self.catalog["music"]}
        self.assertEqual(files, {p.name for p in AUDIO.iterdir() if p.suffix in {".wav", ".ogg"}})

    def test_all_audio_has_intact_licensed_originals_and_provenance(self):
        self.assertEqual(self.provenance["sources"], self.manifest["sources"])
        records = {a["file"]: a for a in self.provenance["assets"]}
        originals = {a["file"]: a for a in self.manifest["assets"]}
        entries = self.catalog["sounds"] + self.catalog["music"]
        self.assertEqual(set(records), {s["file"] for s in entries})
        for entry in entries:
            with self.subTest(file=entry["file"]):
                record = records[entry["file"]]
                self.assertEqual(entry["sha256"], digest(AUDIO / entry["file"]))
                self.assertEqual(entry["sha256"], record["sha256"])
                self.assertEqual(record["original_sha256"], digest(SOURCE / record["original"]))
                self.assertEqual(record["original_sha256"], originals[entry["file"]]["original_sha256"])
                self.assertEqual(record["source"], entry["source"])
                self.assertTrue(record["changes"])
                source = self.provenance["sources"][record["source"]]
                self.assertIn(source["license"], {"CC0-1.0", "CC-BY-3.0", "CC-BY-4.0"})
                self.assertTrue(source["download_url"].startswith("https://"))
                self.assertEqual(len(source["download_sha256"]), 64)

    def test_music_program_has_playable_choices_and_uses_every_new_selection(self):
        programs = json.loads((AUDIO / 'music-program.json').read_text(encoding='utf-8'))['programs']
        known = {m['name'] for m in self.catalog['music']}
        used = {name for pool in programs.values() for name in pool['tracks']}
        self.assertTrue(used <= known)
        self.assertTrue({m['name'] for m in self.catalog['music'] if m.get('review_id')} <= used)
        for pool in programs.values():
            self.assertTrue(pool['tracks'])
        self.assertTrue(programs['aftermath']['once'])

    def test_wavs_are_playable_audible_and_do_not_clip(self):
        for sound in self.catalog["sounds"]:
            with self.subTest(sound=sound["name"]):
                with wave.open(str(AUDIO / sound["file"]), "rb") as wav:
                    self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 44100))
                    self.assertGreater(wav.getnframes(), 1000)
                    self.assertAlmostEqual(wav.getnframes() / 44100, sound["seconds"], delta=0.001)
                    samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float) / 32767
                self.assertGreater(float(np.sqrt(np.mean(samples ** 2))), 0.005)
                self.assertLessEqual(float(np.abs(samples).max()), 0.7)

    def test_footsteps_keep_soft_edges_and_distinct_variants(self):
        for surface in ("dirt", "grass", "stone", "wood", "sand", "snow"):
            variants = []
            for i in range(1, 4):
                path = AUDIO / f"footstep_{surface}_{i}.wav"
                variants.append(digest(path))
                with wave.open(str(path), "rb") as wav:
                    samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float) / 32767
                self.assertLess(float(np.abs(samples[:44]).max()), 0.025)
                self.assertLess(float(np.abs(samples[-220:]).max()), 0.025)
                self.assertLessEqual(float(np.abs(samples).max()), 0.451)
                power = np.abs(np.fft.rfft(samples)) ** 2
                frequencies = np.fft.rfftfreq(len(samples), 1 / 44100)
                self.assertLess(float(power[frequencies > 4000].sum() / power.sum()), 0.035,
                                "repeated steps should not have a piercing treble edge")
            self.assertEqual(len(set(variants)), 3)

    def test_attribution_and_full_licenses_accompany_every_creator(self):
        credits = (AUDIO / "CREDITS.txt").read_text(encoding="utf-8")
        for source in self.provenance["sources"].values():
            for key in ("creator", "title", "url", "license_url"):
                self.assertIn(source[key], credits)
            license_text = (AUDIO / "licenses" / (source["license"] + ".txt")).read_text(encoding="utf-8")
            expected = ("Creative Commons Attribution 4.0 International Public License"
                        if source["license"] == "CC-BY-4.0" else "Creative Commons Legal Code")
            self.assertIn(expected, license_text)
        waterfall = next(a for a in self.provenance["assets"] if a["name"] == "waterfall")
        self.assertEqual(self.provenance["sources"][waterfall["source"]]["license"], "CC-BY-3.0")
        self.assertIn(waterfall["changes"], credits)
        self.assertIn("The Cynic Project / pixelsphere.org / cynicmusic.com", credits)

    def test_package_copies_credits_and_rejects_missing_licenses(self):
        spec = importlib.util.spec_from_file_location("audio_package", CLIENT / "tools/package_client.py")
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        self.assertIn("assets/audio/*.txt", package.EXPORT_PRESETS)
        self.assertIn("assets/audio/licenses/*.txt", package.EXPORT_PRESETS)
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            app = stage / "app"
            import shutil
            target = app / "assets/audio"
            target.mkdir(parents=True)
            for name in ("CREDITS.txt", "provenance.json"):
                shutil.copyfile(AUDIO / name, target / name)
            shutil.copytree(AUDIO / "licenses", target / "licenses")
            package.stage_audio_credits(app, stage)
            self.assertEqual((stage / "AUDIO-CREDITS.txt").read_bytes(), (AUDIO / "CREDITS.txt").read_bytes())
            (target / "licenses/CC-BY-3.0.txt").unlink()
            with self.assertRaises(package.PackageError):
                package.stage_audio_credits(app, stage)

if __name__ == "__main__":
    unittest.main(verbosity=2)
