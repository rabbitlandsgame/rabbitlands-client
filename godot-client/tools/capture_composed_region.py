#!/usr/bin/env python3
"""Load a certified final composition for one-time region migration.

This is a bootstrap reader only. Saved scenes and their copied prototype
assets are the normal-build authority; normal builds never load composed.pkl.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import pickle
import sys


REPO = Path(__file__).resolve().parents[2]
for folder in (REPO / "eloria-assets/maps/nymara-regions/_continent",
               REPO / "eloria-assets/maps/nymara-regions/_toolkit"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Capture:
    world: object
    content: object
    objects: tuple[dict, ...]
    provenance: dict


def load(region_id: str, composed_path: Path, composition_path: Path,
         export_ledger_path: Path, published_master_path: Path,
         published_manifest_path: Path) -> Capture:
    """Return exact final objects after verifying the published master chain."""
    composed_path = composed_path.resolve()
    composition_path = composition_path.resolve()
    export_ledger_path = export_ledger_path.resolve()
    published_master_path = published_master_path.resolve()
    published_manifest_path = published_manifest_path.resolve()
    composition = json.loads(composition_path.read_text(encoding="utf-8"))
    export_ledger = json.loads(export_ledger_path.read_text(encoding="utf-8"))
    manifest = json.loads(published_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("asset", {}).get("id") != region_id:
        raise ValueError(f"Published manifest is not {region_id!r}")
    expected_master = manifest.get("singleContinentSource", {}).get("masterSha256")
    actual_master = sha256(published_master_path)
    actual_composition = sha256(composition_path)
    if expected_master != actual_master:
        raise ValueError(
            f"Published master digest mismatch: manifest={expected_master}, actual={actual_master}")
    if export_ledger.get("masterSha256") != actual_master:
        raise ValueError(
            "Export ledger master digest does not match the published master")
    if export_ledger.get("compositionSha256") != actual_composition:
        raise ValueError(
            "Export ledger composition digest does not match the supplied composition")
    with composed_path.open("rb") as stream:
        world, content = pickle.load(stream)
    if region_id not in getattr(content, "documents", {}):
        raise ValueError(f"Final composition has no source document for {region_id!r}")
    if composition.get("objects") != len(content.objects):
        raise ValueError(
            f"Composition object count mismatch: certificate={composition.get('objects')}, "
            f"pickle={len(content.objects)}")
    objects = tuple(obj for obj in content.objects if obj.get("region") == region_id)
    identities = [str(obj.get("node", "")) for obj in objects]
    if any(not identity for identity in identities) or len(identities) != len(set(identities)):
        raise ValueError(f"{region_id}: final object identities are empty or ambiguous")
    provenance = {
        "composedSha256": sha256(composed_path),
        "compositionSha256": actual_composition,
        "exportLedgerSha256": sha256(export_ledger_path),
        "publishedMasterSha256": actual_master,
        "compositionPlanSha256": composition.get("planSha256"),
        "compositionObjectCount": len(content.objects),
    }
    return Capture(world=world, content=content, objects=objects, provenance=provenance)
