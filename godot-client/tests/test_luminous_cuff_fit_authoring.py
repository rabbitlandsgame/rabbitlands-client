"""Regression coverage for the Luminous-female cuff pass, now retired history.

The pass installed four Luminous-female leg/boot variants and the canonical
Warded Boots base scene. The race programme's P7 cleanup (2026-10) deleted
every variants/luminous_female scene and every old-male base scene, because no
body resolved to them any more; the manifests are marked retired and their
reviewed outputs stay as history. The authoring tool's own guards are still
checked here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "eloria-assets/tools"
sys.path.insert(0, str(TOOLS))

import author_luminous_cuff_fit as cuff


MANIFEST = cuff.DEFAULT_MANIFEST
DERIVED_MANIFEST = (
    ROOT / "eloria-assets/qa/luminous-female-cuff-derived-propagation.json")
CLASS_MANIFEST = ROOT / "eloria-assets/qa/class-equipment-fit-baseline.json"
EQUIPMENT = ROOT / "godot-client/data/actors/equipment.json"
CATALOG = ROOT / "godot-client/data/actors/native_asset_catalog.json"
MODELS = ROOT / "godot-client/data/actors/models.json"
FACE_MASKS = ROOT / "godot-client/assets/actors/native/face_masks/manifest.json"
CANONICAL_WARDED_BOOTS = (
    ROOT / "godot-client/assets/actors/native/equipment/"
    "arcane_fantasy_boots_01.glb")
CANONICAL_WARDED_BOOTS_MANIFEST = (
    ROOT / "eloria-assets/qa/canonical-warded-boots-fit.json")
# The installed Human female body. The cuff pass produced it until the
# 2026-10-05 Human regeneration replaced it with a new Meshy body
# (eloria-assets/tools/pack_human_body.py); the manifest records that mapping
# under installation.retiredMappings.
HUMAN_FEMALE_BODY = (
    ROOT / "godot-client/assets/actors/native/races/luminous_female.glb")
# The four equipment outputs the pass installed, deleted in P7 (2026-10).
RETIRED_OUTPUTS = {
    "arcanistLegs": (
        ROOT / "godot-client/assets/actors/native/equipment/variants/"
        "luminous_female/arcane_leg_armor_01.glb"),
    "arcanistBoots": (
        ROOT / "godot-client/assets/actors/native/equipment/variants/"
        "luminous_female/arcane_fantasy_boots_01.glb"),
    "rangerLegs": (
        ROOT / "godot-client/assets/actors/native/equipment/variants/"
        "luminous_female/rugged_ranger_legwear_04.glb"),
    "rangerBoots": (
        ROOT / "godot-client/assets/actors/native/equipment/variants/"
        "luminous_female/frontier_boots_01.glb"),
}
EXPECTED_BINDINGS = {
    "4:179": (
        "res://assets/actors/native/equipment/variants/luminous_female/"
        "arcane_leg_armor_01.glb"),
    "6:192": (
        "res://assets/actors/native/equipment/variants/luminous_female/"
        "arcane_fantasy_boots_01.glb"),
    "4:230": (
        "res://assets/actors/native/equipment/variants/luminous_female/"
        "rugged_ranger_legwear_04.glb"),
    "6:224": (
        "res://assets/actors/native/equipment/variants/luminous_female/"
        "frontier_boots_01.glb"),
}


def _manifest() -> dict:
    return cuff.load_manifest(MANIFEST)


def test_canonical_warded_boots_fit_is_retired_with_its_output():
    manifest = json.loads(
        CANONICAL_WARDED_BOOTS_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["status"] == "retired"
    assert not CANONICAL_WARDED_BOOTS.exists()
    equipment = json.loads(EQUIPMENT.read_text(encoding="utf-8"))
    assert equipment["models"]["6:192"]["scene"] == (
        equipment["models"]["6:192"]["variants"]["canonical_human_male"]["scene"])
    # The reviewed contract stays as history.
    assert manifest["contract"]["additionalPerFrameOperations"] == 0
    assert manifest["contract"]["drawsBefore"] == manifest["contract"]["drawsAfter"]
    assert manifest["contract"]["materialsBefore"] == manifest["contract"]["materialsAfter"]
    assert manifest["contract"]["jointsBefore"] == manifest["contract"]["jointsAfter"]
    assert manifest["output"]["outputVertices"] == 1296
    assert manifest["output"]["outputTriangles"] == 1049


def test_manifest_preserves_historical_inputs_and_zero_runtime_cost():
    manifest = _manifest()
    assert manifest["schema"] == "eloria-luminous-female-cuff-fit-v2"
    assert manifest["status"] == "retired"
    assert manifest["authority"]["sourceSHA256"] == (
        "39a4dbc151d6f04813fa843803ef5e8c71eca61e59b700d9c876274a9c7f9d66")
    assert manifest["authority"]["hiddenOverlapRangeMm"] == pytest.approx(
        [1.93677412328858, 4.89287166927216], abs=1e-12)
    assert manifest["contract"] == {
        "selectedHiddenOverlapMm": 3.0,
        "arcanistRadialInsetMm": 1.5,
        "openHiddenBoundary": True,
        "capTriangles": 0,
        "maximumInfluences": 4,
        "additionalDraws": 0,
        "additionalMaterials": 0,
        "additionalBones": 0,
        "perFrameOperations": 0,
    }
    installation = manifest["installation"]
    assert installation["mode"] == "reviewed-byte-copy"
    assert installation["inputsAreHistorical"] is True
    assert installation["productionConfigChanged"] is False
    evidence = manifest["authoringEvidence"]
    assert evidence["deterministicRuns"] == 2
    assert evidence["byteIdentical"] is True
    verifier_text = (ROOT / evidence["toolPath"]).read_text(encoding="utf-8")
    verifier_text = verifier_text.replace("\r\n", "\n").replace("\r", "\n")
    verifier_hash = hashlib.sha256(verifier_text.encode("utf-8")).hexdigest()
    assert verifier_hash == evidence["verifierToolCanonicalLfSHA256"]
    assert evidence["producerToolGitCommit"] == (
        "c29866f34aab26ffeaad728b9574a96a441c7747")
    assert evidence["producerToolGitBlob"] == (
        "fa5bf59cb1560fa66549bc9a4752695c7e017c1d")
    assert evidence["producerToolSHA256"] == (
        "61e783a8ccb531f3f143d19ecb5d5222348e72340a1036c8b5aac579b1b1e3e2")

    inputs = manifest["inputs"]
    snapshot = "2df789a02abc591cc8730758cb6d4526f3efaa17"
    git_sources = {
        "body": "01b08fe18c8d0b5f7fd38555a75b6e5682d69500",
        "rangerLegs": "0e378eb9c3edb803761f556ccb782cc781009315",
        "rangerBoots": "d38c00b92212a0de61db28e8dd06d4da14fb7f5a",
    }
    for key, blob_oid in git_sources.items():
        provenance = inputs[key]["provenance"]
        assert provenance["kind"] == "git-tree-snapshot"
        assert provenance["commit"] == snapshot
        assert provenance["blobOID"] == blob_oid
        assert provenance["path"] == inputs[key]["pathAtCapture"]

    class_manifest = json.loads(CLASS_MANIFEST.read_text(encoding="utf-8"))
    for key in ("arcanistLegs", "arcanistBoots"):
        source = inputs[key]
        provenance = source["provenance"]
        assert provenance["kind"] == "producer-manifest-output"
        assert provenance["manifest"] == (
            "eloria-assets/qa/class-equipment-fit-baseline.json")
        assert provenance["section"] == "output"
        assert class_manifest[provenance["section"]][provenance["key"]] == (
            source["sourceSHA256"])

    equipment_spec = inputs["equipmentConfig"]
    assert equipment_spec["sourceSHA256"] == (
        "0ec6117ee7be83be48b2b5e9929e19a5e9f1926331d723587a03f066aa3d01e1")
    assert equipment_spec["provenance"] == {
        "kind": "git-tree-snapshot",
        "commit": "c29866f34aab26ffeaad728b9574a96a441c7747",
        "path": "godot-client/data/actors/equipment.json",
        "blobOID": "30c6585b669858e47747e6e9d6f306c41f9a38fb",
    }
    assert equipment_spec["semanticBindings"] == EXPECTED_BINDINGS
    # The live registry no longer carries the retired canonical_luminous_female
    # group, so a rerun of the pass is refused at its binding check.
    with pytest.raises(ValueError, match="binding is missing"):
        cuff.validate_equipment_config(EQUIPMENT, equipment_spec)


def test_equipment_validation_rejects_cuff_binding_drift():
    # A synthetic registry in the layout the pass authored against.
    manifest = _manifest()
    bindings = manifest["inputs"]["equipmentConfig"]["semanticBindings"]
    equipment = {"models": {
        slot: {"variants": {"canonical_luminous_female": {"scene": scene}}}
        for slot, scene in bindings.items()}}
    assert cuff.validate_equipment_bindings(equipment, bindings) == bindings
    equipment["models"]["4:179"]["variants"][
        "canonical_luminous_female"]["scene"] = "res://wrong/legs.glb"
    with pytest.raises(ValueError, match="4:179"):
        cuff.validate_equipment_bindings(equipment, bindings)
    del equipment["models"]["6:192"]["variants"]["canonical_luminous_female"]
    with pytest.raises(ValueError, match="6:192/canonical_luminous_female"):
        cuff.validate_equipment_bindings(equipment, bindings)


def test_every_cuff_mapping_is_retired_and_its_output_deleted():
    manifest = _manifest()
    installation = manifest["installation"]
    assert installation["mappings"] == []
    retired = installation["retiredMappings"]
    assert [item["inputKey"] for item in retired] == [
        "body", "arcanistLegs", "arcanistBoots", "rangerLegs", "rangerBoots"]
    reviewed = manifest["reviewedOutputs"]
    for item in retired:
        key = item["inputKey"]
        assert item["reviewedOutputKey"] == key
        assert item["retiredAt"] and item["reason"]
        assert reviewed[key]["installed"] is False
        if key == "body":
            assert ROOT / item["targetPath"] == HUMAN_FEMALE_BODY
            assert cuff.digest(HUMAN_FEMALE_BODY) != reviewed["body"]["outputSHA256"]
        else:
            assert ROOT / item["targetPath"] == RETIRED_OUTPUTS[key]
            assert not RETIRED_OUTPUTS[key].exists(), key
    assert not (ROOT / "godot-client/assets/actors/native/equipment/"
                "variants/luminous_female").is_dir()

    # The reviewed geometry stays as history.
    assert reviewed["body"]["geometry"] == {
        "sourceVertices": 4828,
        "outputVertices": 4601,
        "sourceTriangles": 6733,
        "outputTriangles": 6432,
        "boundaryEdges": 114,
        "boundaryVertices": 124,
    }
    assert reviewed["arcanistLegs"]["geometry"]["boundaryEdges"] == 36
    assert reviewed["rangerLegs"]["geometry"]["visibleBreeches"][
        "boundaryVertices"] == 70
    # The cut opened 327 lining boundary vertices; all of them were sealed in
    # the cut plane so the paired lining stayed one closed solid.
    lining = reviewed["rangerLegs"]["geometry"]["pairedLegBacking"]
    assert lining["cutBoundaryVertices"] == 327
    assert lining["boundaryEdges"] == lining["boundaryVertices"] == 0
    assert lining["sealTriangles"] == lining["cutBoundaryEdges"] == 327
    assert reviewed["rangerBoots"]["geometry"]["pairedBootBacking"][
        "boundaryVertices"] == 215
    assert reviewed["rangerBoots"]["removedComponentLabels"] == []
    assert cuff.SEALED_RANGER_LININGS == ("GeneratedLegBackingWithBoots",)


def test_installed_body_metadata_tracks_the_installed_bytes():
    installed_hash = cuff.digest(HUMAN_FEMALE_BODY)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    race = catalog["races"]["luminous_female"]
    assert race["sha256"] == installed_hash
    # The regenerated body (2026-10-05): vertices are the ones its surfaces
    # actually use, since all seven body surfaces share one position buffer.
    assert race["vertices"] == 18198
    assert race["triangles"] == 23491
    models = json.loads(MODELS.read_text(encoding="utf-8"))
    assert models["models"]["luminous_female"]["skinPalette"][
        "sourceSHA256"] == installed_hash
    masks = json.loads(FACE_MASKS.read_text(encoding="utf-8"))
    assert masks["luminous_female"]["modelSHA256"] == installed_hash


def test_derived_female_cuff_propagation_is_retired_by_the_race_rebase():
    propagation = json.loads(DERIVED_MANIFEST.read_text(encoding="utf-8"))
    assert propagation["schema"] == (
        "eloria-luminous-female-cuff-derived-propagation-v1")
    # Every derived female race was rebased onto the regenerated Human body
    # (rebase_race_body.py, sharedBodyShape v3), whose own pants and boots it
    # now carries byte for byte below the neck. No installed body carries the
    # cuffed template's surfaces any more, so the propagation lists none.
    assert propagation["status"] == "retired"
    assert propagation["assets"] == {}
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["races"]
    derived = sorted(slug for slug in catalog
                     if slug.endswith("_female") and slug != "luminous_female")
    assert len(derived) == 7
    for slug in derived:
        shape = catalog[slug]["sharedBodyShape"]
        assert shape["version"] >= 3, slug
        assert shape["template"] == "luminous_female", slug
        assert shape["templateSHA256"] == cuff.digest(HUMAN_FEMALE_BODY), slug

    # The record of how the propagation was authored stays valid history.
    contract = propagation["contract"]
    assert contract["selectedHiddenOverlapMm"] == 3.0
    assert contract["openHiddenBoundary"] is True
    assert contract["capTriangles"] == 0
    assert contract["preserveAdditionalPantsPrimitives"] is True
    assert [contract[name] for name in (
        "additionalDraws", "additionalMaterials", "additionalBones",
        "perFrameOperations")] == [0, 0, 0, 0]

    evidence = propagation["authoringEvidence"]
    tool_text = (ROOT / evidence["toolPath"]).read_text(encoding="utf-8")
    tool_text = tool_text.replace("\r\n", "\n").replace("\r", "\n")
    assert hashlib.sha256(tool_text.encode("utf-8")).hexdigest() == (
        evidence["toolCanonicalLfSHA256"])
    assert evidence["deterministicRuns"] == 2
    assert evidence["byteIdentical"] is True


def test_historical_body_provenance_is_valid_without_baseline_binary():
    body_spec = _manifest()["inputs"]["body"]
    asset_hash = "a" * 64
    provenance = {
        "schema": "eloria-canonical-body-provenance-v1",
        "canonicalRace": "luminous_female",
        "assetSHA256": asset_hash,
        "canonicalSourceSHA256": body_spec["acceptedSourceSHA256"][0],
        "producer": "test neck-only authoring fixture",
        "inheritedSemanticMeshes": {
            name: value["sha256"]
            for name, value in body_spec["semanticMeshes"].items()
        },
    }
    cuff.validate_body_provenance_record(
        provenance, body_spec, actual_hash=asset_hash)
    invalid = copy.deepcopy(provenance)
    invalid["inheritedSemanticMeshes"]["wardrobe_pants"] = "0" * 64
    with pytest.raises(ValueError, match="surface roster changed"):
        cuff.validate_body_provenance_record(
            invalid, body_spec, actual_hash=asset_hash)


def test_installed_body_is_rejected_as_a_second_pass_source():
    inputs = _manifest()["inputs"]
    with pytest.raises(ValueError, match="Body semantic surface"):
        cuff.validate_body_source(HUMAN_FEMALE_BODY, inputs["body"])


def test_authoring_refuses_a_production_output_path():
    prospective = (ROOT / "godot-client/assets/actors/native/races/"
                   "cuff-fit-output")
    with pytest.raises(ValueError, match="Refusing production output"):
        cuff.validate_output_path(prospective)
