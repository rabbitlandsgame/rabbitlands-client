"""Register the stand-alone harvest models in godot-client/data/world/objects.json; never generates models.

The seven Meshy models (owner request 2026-11-15) are rows of imported_world_objects.IMPORTED_HARVESTABLES that answer
their labels. The procedural registry generator that used to write imported rows is retired, so this writes the same
entries it would (imported_world_objects.imported_entries: scene, label, kind, tier, the client's measure of the file,
imported, source), plus `replaces` (the label's retired procedural model, which stays registered) and the label's
`resources` entry. `harvestables.variants` is left alone: laid-out nodes keep their patch variants.

Each installed file must match its provenance record (eloria-assets/source/world_objects/harvest-standalones/
provenance.json) before anything is written. --check compares the registry with what this would write.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "godot-client"
REGISTRY = CLIENT / "data/world/objects.json"
HARVESTABLE_DIR = "assets/world/harvestables"
sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
import imported_world_objects as IWO  # noqa: E402


def rows() -> dict[str, IWO.ImportedHarvestable]:
    record = json.loads((ROOT / IWO.HARVEST_STANDALONES).read_text(encoding="utf-8"))
    table = {row.model_id: row for row in IWO.IMPORTED_HARVESTABLES}
    selected = {}
    for asset in record["assets"]:
        row = table.get(asset["id"])
        if row is None or not row.answers_label or row.stands_alone or row.label != asset["label"]:
            raise SystemExit(f"{asset['id']}: no answering IMPORTED_HARVESTABLES row for {asset['label']}")
        path = CLIENT / HARVESTABLE_DIR / f"{row.model_id}.glb"
        if IWO.measure_glb(path) != asset["model"]:
            raise SystemExit(f"{path} does not match its provenance record")
        if row.model_id in IWO.variant_ids():
            raise SystemExit(f"{row.model_id} must not be a patch variant (it would move laid-out nodes' picks)")
        selected[row.model_id] = (row, asset["replacesRetired"])
    return selected


def registry(current: dict) -> dict:
    catalog = json.loads(json.dumps(current))
    harvest = catalog["harvestables"]
    models, resources = harvest["models"], harvest["resources"]
    selected = rows()
    measured = IWO.imported_entries(CLIENT, HARVESTABLE_DIR)
    for model_id, (row, retired) in selected.items():
        replaced = models.get(retired, {})
        if not replaced.get("retired") or replaced.get("imported") or replaced.get("label") != row.label:
            raise SystemExit(f"{model_id}: {retired} is not {row.label}'s retired procedural model")
        if resources.get(row.label) not in (retired, model_id):
            raise SystemExit(f"{row.label} already resolves to {resources.get(row.label)}")
        entry = dict(measured[model_id])
        entry["replaces"] = retired
        models[model_id] = entry
        resources[row.label] = model_id
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = REGISTRY.read_bytes()
    written = (json.dumps(registry(json.loads(raw)), indent=2) + "\n").encode()
    if args.check:
        print(json.dumps({"mode": "check", "current": written == raw}))
        return int(written != raw)
    REGISTRY.write_bytes(written)
    print(json.dumps({"mode": "apply", "changed": written != raw}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
