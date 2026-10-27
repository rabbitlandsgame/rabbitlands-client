"""publish_server.py's continentV2 block and interior station targets, on stand-ins (no server checkout needed).

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_publish_server_block.py -q

manifest_block writes the keys it owns (OWNED_BLOCK_KEYS) and carries every other key of the server's block over as
it stands (publish_npc_metadata.py's npcMetadataAmendments); the record's hash of the block stays isle facts only.
station_targets gives an interior crafting station the trade its text or its section's style names.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import publish_server as P  # noqa: E402
import underground as U  # noqa: E402

AMENDMENTS = [{"tool": "eloria-assets/maps/continent-v2/_continent_v2/publish_npc_metadata.py", "region": "landfall",
               "addedNpcMarkers": ["landfall--npc-cape-seller-mara-vell"], "scope": "added NPC rows only"}]


def interior(region, kind, rows):
    return SimpleNamespace(region=region, kind=kind, metadata={"name": region}, rows=rows,
                           portals=[[region, 1, 2, 3, "landfall", 4, 5]])


def stand_ins(*interiors):
    ctx = SimpleNamespace(frames={}, packages={}, bakes={}, crossings_sha256="c" * 64)
    pub = SimpleNamespace(files={name: name.encode() for name in P.FILES}, map_rows=[], catalog={}, arrivals={},
                          ferries=[], boats=[], held=[], spawns=[], nodes=[], new_people=[], rehomed=[],
                          interactives=[], interiors=list(interiors))
    return ctx, pub


def test_the_block_carries_over_the_keys_another_tool_wrote():
    caves = interior("landfall_insides", "underground", {"nodes": 1, "spawns": 2, "interactives": 3})
    town = interior("landfall_town", "building", {"nodes": 0, "spawns": 0, "interactives": 4, "npcs": 5})
    ctx, pub = stand_ins(caves, town)
    owned = P.manifest_block(ctx, pub, "m4")
    assert list(owned) == [key for key in P.OWNED_BLOCK_KEYS if key in owned]
    assert "npcMetadataAmendments" not in owned            # the record hashes isle facts only
    existing = {**{key: "stale" for key in owned}, "npcMetadataAmendments": AMENDMENTS, "laterTool": {"a": [1]}}
    before = copy.deepcopy(existing)
    block = P.manifest_block(ctx, pub, "m4", existing)
    assert list(block) == [*owned, "npcMetadataAmendments", "laterTool"]
    assert {key: block[key] for key in owned} == owned     # every owned key is this run's, never the old value
    assert block["npcMetadataAmendments"] == AMENDMENTS and block["laterTool"] == {"a": [1]}
    block["laterTool"]["a"].append(2)
    assert existing == before                              # carried as copies


def test_an_owned_key_this_run_does_not_write_is_dropped_not_carried():
    """With the town source absent, a stale buildingPortals of an earlier run is this tool's: it goes."""
    caves = interior("landfall_insides", "underground", {"nodes": 1, "spawns": 2, "interactives": 3})
    ctx, pub = stand_ins(caves)
    existing = {"buildingPortals": [["old"]], "buildingRows": {"npcs": 9}, "npcMetadataAmendments": AMENDMENTS}
    block = P.manifest_block(ctx, pub, "m4", existing)
    assert "buildingPortals" not in block and "buildingRows" not in block
    assert block["undergroundPortals"] == caves.portals and block["npcMetadataAmendments"] == AMENDMENTS
    assert {spec.portals for spec in U.SOURCES} | {spec.rows for spec in U.SOURCES} <= set(P.OWNED_BLOCK_KEYS)


def test_a_key_the_block_writes_must_be_listed_as_owned(monkeypatch):
    ctx, pub = stand_ins()
    monkeypatch.setattr(U, "manifest_keys", lambda pub: {"surprise": 1})
    with pytest.raises(P.PublishError, match="surprise"):
        P.manifest_block(ctx, pub, "m4")


@pytest.mark.parametrize("text, style, trade", [
    ("The forge is hot. Open your manufacture window to smith.", "smithy", "smithing"),
    ("The forge is hot. Open your manufacture window to smith.", "tavern", "smithing"),
    ("The anvil rings.", "house", "smithing"),
    ("The furnace is ready to smelt.", "smithy", "smelting"),
    ("An alchemy table.", "magic", "alchemy"),
    ("A bench of tools.", "smithy", "smithing"),
    ("A bench of tools.", "shop", None),
])
def test_a_station_takes_the_trade_its_text_or_its_room_names(text, style, trade):
    assert P.station_target({"text": text}, {"style": style}) == trade


def test_station_targets_rewrites_only_the_default_rows_it_owns():
    design = {"sections": [
        {"id": "smithy", "style": "smithy", "interactives": [
            {"object": 59260, "tile": [10, 11], "role": "crafting_station",
             "text": "The forge is hot. Open your manufacture window to smith."},
            {"object": 59261, "tile": [12, 11], "role": "information", "text": "A smith's ledger."}]},
        {"id": "shop", "style": "shop", "interactives": [
            {"object": 59262, "tile": [40, 41], "role": "crafting_station", "text": "A bench of tools."}]}]}
    rows = ["landfall_town | 59260 | 10 | 11 | crafting_station | crafting | The forge is hot. Open your manufacture "
            "window to smith.",
            "landfall_town | 59261 | 10 | 11 | information | notice | A smith's ledger.",
            "landfall_town | 59262 | 40 | 41 | crafting_station | crafting | A bench of tools."]
    head = b"base | 1 | 2 | 3 | crafting_station | crafting | An isle bench.\r\n"
    data = head + ("\r\n# Landfall town: building interiors.\r\n" + "\r\n".join(rows) + "\r\n").encode()
    spec = SimpleNamespace(**{**vars(U.SOURCES[1]), "reader": "underground_source"})
    pub = SimpleNamespace(files={"interactives.txt": data},
                          interiors=[SimpleNamespace(region="landfall_town", spec=spec, design=design)])
    P.station_targets(pub)
    assert pub.files["interactives.txt"] == data.replace(b"59260 | 10 | 11 | crafting_station | crafting",
                                                         b"59260 | 10 | 11 | crafting_station | smithing")
    # a row that is not as underground.py writes it is refused, not silently left as "crafting"
    pub.files["interactives.txt"] = data.replace(b"59260 | 10 | 11", b"59260 | 10 | 12")
    with pytest.raises(P.PublishError, match="59260"):
        P.station_targets(pub)
