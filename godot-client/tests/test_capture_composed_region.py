from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace

import pytest


TOOL = Path(__file__).resolve().parents[1] / "tools/capture_composed_region.py"
SPEC = importlib.util.spec_from_file_location("capture_composed_region", TOOL)
assert SPEC and SPEC.loader
C = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = C
SPEC.loader.exec_module(C)


def fixture(tmp_path: Path):
    master = tmp_path / "continent.glb"
    master.write_bytes(b"published master bytes")
    content = SimpleNamespace(
        documents={"amethyst_barrens": ({"nodes": []}, b"")},
        objects=[
            {"region": "amethyst_barrens", "node": "A"},
            {"region": "sunmane_steppe", "node": "B"},
        ],
    )
    composed = tmp_path / "composed.pkl"
    with composed.open("wb") as stream:
        pickle.dump((SimpleNamespace(), content), stream)
    composition = tmp_path / "composition.json"
    composition.write_text(json.dumps({
        "objects": 2, "planSha256": "a" * 64,
    }), encoding="utf-8")
    ledger = tmp_path / "export.json"
    ledger.write_text(json.dumps({
        "masterSha256": C.sha256(master),
        "compositionSha256": C.sha256(composition),
    }), encoding="utf-8")
    manifest = tmp_path / "world.json"
    manifest.write_text(json.dumps({
        "asset": {"id": "amethyst_barrens"},
        "singleContinentSource": {"masterSha256": C.sha256(master)},
    }), encoding="utf-8")
    return composed, composition, ledger, master, manifest


def test_capture_requires_published_master_and_selects_exact_region_objects(tmp_path):
    composed, composition, ledger, master, manifest = fixture(tmp_path)

    captured = C.load(
        "amethyst_barrens", composed, composition, ledger, master, manifest)

    assert [entry["node"] for entry in captured.objects] == ["A"]
    assert captured.provenance == {
        "composedSha256": C.sha256(composed),
        "compositionSha256": C.sha256(composition),
        "exportLedgerSha256": C.sha256(ledger),
        "publishedMasterSha256": C.sha256(master),
        "compositionPlanSha256": "a" * 64,
        "compositionObjectCount": 2,
    }


def test_capture_fails_closed_when_published_master_changed(tmp_path):
    composed, composition, ledger, master, manifest = fixture(tmp_path)
    master.write_bytes(b"different bytes")

    with pytest.raises(ValueError, match="Published master digest mismatch"):
        C.load("amethyst_barrens", composed, composition, ledger, master, manifest)


def test_capture_fails_closed_when_export_ledger_names_another_composition(tmp_path):
    composed, composition, ledger, master, manifest = fixture(tmp_path)
    document = json.loads(ledger.read_text(encoding="utf-8"))
    document["compositionSha256"] = "0" * 64
    ledger.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="Export ledger composition digest"):
        C.load("amethyst_barrens", composed, composition, ledger, master, manifest)
