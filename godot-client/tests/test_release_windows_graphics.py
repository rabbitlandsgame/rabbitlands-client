"""WARP identity follows independent LUID/flags and Godot's preferred order."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_windows_graphics as graphics


def inventory(warp_index=1):
    warp = {"name": "Microsoft Basic Render Driver", "vendor_id": 0x1414, "device_id": 0x8c,
            "subsystem_id": 0, "revision": 0, "luid": "00000000:00012345", "flags": 2,
            "dedicated_video_memory": 0, "dedicated_system_memory": 0, "shared_system_memory": 8_000_000_000}
    # Same display name, different LUID/flags. Picking index zero or matching
    # a name is insufficient even when it looks like Microsoft's basic driver.
    hardware = dict(warp, flags=0, luid="00000000:00054321", dedicated_video_memory=64_000_000)
    values = [hardware, warp] if warp_index else [warp, hardware]
    return {"schema": 1, "policy": graphics.POLICY, "system_dxgi": "System32/dxgi.dll",
            "factory": "IDXGIFactory6", "enumeration": "EnumAdapterByGpuPreference(HIGH_PERFORMANCE)",
            "warp": warp, "adapters": [dict(row, index=index) for index, row in enumerate(values)]}


@pytest.mark.parametrize("index", [0, 1])
def test_selects_independently_identified_warp_even_when_names_collide(index):
    evidence = inventory(index)
    original = deepcopy(evidence)
    receipt = graphics.select_warp(evidence)
    assert receipt["selected_index"] == index
    assert receipt["selected_adapter"]["luid"] == evidence["warp"]["luid"]
    assert receipt["selected_adapter"]["flags"] & graphics.SOFTWARE
    assert evidence == original
    assert graphics.select_warp(evidence, index) == receipt


@pytest.mark.parametrize("requested", [0, -1, 2, True, "1", 1.0])
def test_explicit_wrong_or_noninteger_index_never_substitutes_hardware(requested):
    with pytest.raises(ValueError, match="Requested GPU index"):
        graphics.select_warp(inventory(), requested)


@pytest.mark.parametrize("mutation", ["software", "missing", "different-luid", "descriptor", "duplicate-luid",
                                      "wrong-order", "wrong-enumeration", "bool-schema", "missing-field", "bad-size"])
def test_missing_changed_or_ambiguous_evidence_fails_closed(mutation):
    evidence = inventory()
    if mutation == "software": evidence["warp"]["flags"] = 0
    elif mutation == "missing": evidence["adapters"].pop()
    elif mutation == "different-luid": evidence["warp"]["luid"] = "00000000:00099999"
    elif mutation == "descriptor": evidence["adapters"][1]["vendor_id"] += 1
    elif mutation == "duplicate-luid": evidence["adapters"][0]["luid"] = evidence["warp"]["luid"]
    elif mutation == "wrong-order": evidence["adapters"].reverse()
    elif mutation == "wrong-enumeration": evidence["enumeration"] = "EnumAdapters1"
    elif mutation == "bool-schema": evidence["schema"] = True
    elif mutation == "missing-field": del evidence["warp"]["device_id"]
    elif mutation == "bad-size": evidence["warp"]["dedicated_video_memory"] = -1
    with pytest.raises(ValueError):
        graphics.select_warp(evidence)


def test_native_inventory_is_queried_once_and_preserved(monkeypatch):
    evidence = inventory()
    calls = []
    monkeypatch.setattr(graphics, "enumerate_adapters", lambda: calls.append(True) or evidence)
    result = graphics.identify_warp()
    assert calls == [True]
    assert result["warp"] == evidence["warp"]
