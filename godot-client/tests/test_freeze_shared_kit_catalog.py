"""Shared palette identities preserve the pinned authored kit, including dressing."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import freeze_continent_v2_terrain as F
import freeze_shared_kit_catalog as K


def test_shared_bindings_replay_and_preserve_repair_roles():
    blob = K.build(F.GitInputs(F.CHECKOUT))
    assert blob == (F.CHECKOUT / K.OUTPUT).read_bytes()
    document = json.loads(blob)
    assert document["sourcePlacements"] == 17401
    assert len(document["models"]) == 537
    repair = [record for path, record in document["models"].items()
              if "causeway-support-" in path or "causeway-joint-" in path]
    assert len(repair) == 267
    assert all(record["collisionRole"] == "none" for record in repair)
    assert all(record["catalogAssetId"] for record in document["models"].values())
    for path in document["models"]:
        assert (F.CHECKOUT / F.git_path(path)).is_file()


def test_modal_identity_ties_are_stable():
    assert K.most_common({"z": 3, "a": 3, "b": 2}) == "a"
