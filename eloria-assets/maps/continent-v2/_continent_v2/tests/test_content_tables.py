"""The continent-v2 content tables: the wild spawn rows of the three isles and the server rows' other fields.

`<map>/content/spawns.json` holds every wild spawn row of a map in territory-local metres (the plans moved in from the
session scratchpad: spawn_plan_rf.json for sw_isle, adjacent_d2_rf.json for The Tollholms and The Gull Skerries), and
`_continent_v2/content/server-rows.json` holds what a server row needs besides its tile, keyed by the scene marker's
record_id: an NPC's role, body and greeting, an interactive's object id, role, target and text. publish_server.py
joins them to the markers; these tests hold the tables to the owner-accepted plans (review/island_content_plan.md,
review/serve_plan.md CV1) and to the scenes' markers, and hold sw_isle's markers to what the server rows and
"Signed Ashore" need from them (CV2): the desk's and the ferry's object ids and roles, and one tgt-*/opt-* runtime point
for each place the chapter and its side errands send a player.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
import sys

import pytest

V2 = Path(__file__).resolve().parents[2]
CHECKOUT = V2.parents[2]
sys.path.insert(0, str(CHECKOUT / "godot-client" / "tools"))
import continent_v2_territories as T  # noqa: E402
sys.path.insert(0, str(V2 / "_continent_v2"))
import underground_source  # noqa: E402

MAPS = tuple(e["id"] for e in json.loads((CHECKOUT / "godot-client/world_authoring/continent-v2/territories.json").read_text())["entries"])
ID_PREFIX = {"sw_isle": "sw-spawn-", "tollholms": "th-spawn-", "gull_skerries": "gs-spawn-"}
# The accepted plans' rosters, species by species (spawn_plan_rf.json summary.sw_isle_spawns_by_species and
# second_map_spawns_by_species; owner swaps of 2026-10-02 applied: 60 foxes to stoats, 8 beach otters to the
# existing delta_mud_crab). Every one is passive on the server (B3 notes section 4).
ROSTER = {
    "sw_isle": {
        "rabbit": 138, "hedgehog": 120, "squirrel": 107, "stoat": 91, "pheasant": 88, "gecko": 53, "shrew": 47,
        "dormouse": 47, "crown_antler_stag": 43, "magpie": 38, "chameleon": 33, "beaver": 10, "pelican": 9,
        "red_fox": 9, "mossback_boar": 8, "delta_mud_crab": 8, "mallard_duck": 7, "river_otter": 7, "raven": 6,
        "frilled_lizard": 5, "riverglass_otter": 4, "jackalope": 2, "goose": 1, "azure_axolotl": 1, "mudskipper": 1},
    "tollholms": {
        "raven": 22, "goose": 15, "frilled_lizard": 14, "crown_antler_stag": 14, "jackalope": 11,
        "coralcrest_heron": 9, "pelican": 7, "mossback_badger": 6, "mossback_boar": 5, "brambleback_boar": 5,
        "magpie": 5, "crystal_shore_crab": 5, "bronze_tide_crab": 5, "chameleon": 5, "russet_faun": 3,
        "riverglass_otter": 2},
    "gull_skerries": {"frilled_lizard": 3, "jackalope": 3, "stoat": 2, "pheasant": 1, "russet_faun": 1, "magpie": 1},
}
COUNTS = {"sw_isle": 883, "tollholms": 133, "gull_skerries": 11}
# Leash by band (content plan decision: per-spawn wild leash; sw_isle bands A-D by walking distance from the plaza;
# each adjacent map one level band and one leash).
LEASH = {"sw_isle": {"A": 15, "B": 25, "C": 35, "D": 45}, "tollholms": {"4-12": 40}, "gull_skerries": {"2-9": 45}}
# eloria-server eloria/interactives.py: the roles its loader accepts.
INTERACTIVE_ROLES = {"storage", "crafting_station", "training", "information", "water_source", "scenery_effect",
                     "portal", "secret", "gate", "cache", "waystone"}
NPC_ROLES = {"dialogue", "tutorial", "shop", "guide"}
# eloria-server eloria/npcs.py occupation_for: what an NPC marker's extras "occupation" may hold.
OCCUPATION_LIMIT = 32
OCCUPATION_FORBIDDEN = set("|#,=<>")
FORBIDDEN = ("|", "#", "\n", "\r")
# eloria-server eloria/landing.py TARGETS: the places "Signed Ashore" sends a player, which landing.json must carry
CHAPTER_TARGETS = ("olive_grove", "lemon_garden", "sage_meadow", "flint_outcrop", "bramble_edge", "resin_pines",
                   "warren", "temple_door", "lake_reeds", "causeway_mid", "ferry_quay", "pine_knoll")
# the side errands' quest rows take their x/y from these posts (questlines_draft.txt <TX:...>/<TY:...>)
QUEST_XY = {"isle_unsigned_line": "opt-north-light-court", "isle_brook_dam": "opt-castle-brook-reed",
            "isle_tideline": "opt-tideline-shell"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def spawns() -> dict[str, dict]:
    return {map_id: load(V2 / map_id / "content" / "spawns.json") for map_id in MAPS}


def rows_doc() -> dict:
    return load(V2 / "_continent_v2" / "content" / "server-rows.json")


@pytest.fixture(scope="module")
def rows() -> dict:
    return rows_doc()


def scene_markers(map_id: str) -> dict[str, dict]:
    """Every authored gameplay marker, including the scene's root RuntimePoints subtree."""
    scene = T.load_scene((CHECKOUT / "godot-client" / "world_authoring" / "regions" / map_id /
                          f"{map_id}.tscn").resolve())
    markers = {}
    for path, section in scene.nodes.items():
        if not path.startswith(("Gameplay/", "RuntimePoints/")) or not scene.script_of(section).endswith("gameplay_marker.gd"):
            continue
        props = section.properties
        record = json.loads(props["record_id"])
        assert record not in markers, f"{map_id}: two markers named {record}"
        markers[record] = {"node_name": section.attributes["name"],
                           "kind": json.loads(props.get("kind", '"landmark"')),
                           "label": json.loads(props.get("label", '""')),
                           "extras": json.loads(props["extras"]) if "extras" in props else {}}
    return markers


@pytest.fixture(scope="module")
def markers() -> dict[str, dict[str, dict]]:
    return {map_id: scene_markers(map_id) for map_id in MAPS}


def test_each_map_has_its_planned_number_of_rows(spawns):
    for map_id in MAPS:
        assert spawns[map_id]["schema"] == "eloria-continent-v2-spawns-v1"
        assert spawns[map_id]["map"] == map_id
        assert isinstance(spawns[map_id]["spawns"], list), map_id
    assert sum(len(spawns[m]["spawns"]) for m in MAPS) == 1027


def test_row_ids_are_unique_and_preserve_their_source_identity(spawns):
    ids = [r["id"] for m in MAPS for r in spawns[m]["spawns"]]
    assert len(ids) == len(set(ids))
    for map_id in MAPS:
        assert all(any(r["id"].startswith(prefix) for prefix in ID_PREFIX.values()) for r in spawns[map_id]["spawns"]), map_id


def test_every_row_has_a_leash_and_its_band_sets_it(spawns):
    for map_id in MAPS:
        for r in spawns[map_id]["spawns"]:
            assert isinstance(r["leash"], int) and not isinstance(r["leash"], bool), r["id"]
            assert 1 <= r["leash"] <= 200, r["id"]
            source = next(source for source, prefix in ID_PREFIX.items() if r["id"].startswith(prefix))
            assert r["leash"] == LEASH[source][r["band"]], r["id"]


def test_species_come_only_from_the_plan_roster(spawns):
    for source, prefix in ID_PREFIX.items():
        # A row the A3 rethemes re-typed keeps its source species in "retyped.from".
        counts = Counter(r.get("retyped", {}).get("from", r["creature"]) for m in MAPS for r in spawns[m]["spawns"]
                         if r["id"].startswith(prefix))
        assert dict(counts) == ROSTER[source], source


def test_every_row_is_a_finite_local_position_in_a_named_zone(spawns):
    for map_id in MAPS:
        for r in spawns[map_id]["spawns"]:
            # moved/retyped/pass: the Landfall A3 theme pass (a row moved off a set piece, re-typed, or added)
            assert set(r) <= {"id", "creature", "local", "leash", "zone", "band", "level", "habitat", "note",
                              "moved", "retyped", "pass"}, r["id"]
            assert len(r["local"]) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v)
                                                 for v in r["local"]), r["id"]
            assert isinstance(r["zone"], str) and r["zone"], r["id"]


def test_the_server_rows_cover_the_catalog(rows):
    assert rows["schema"] == "eloria-continent-v2-server-rows-v1"
    assert set(rows["maps"]) == set(MAPS)
    for map_id in MAPS:
        assert set(rows["maps"][map_id]) == {"npcs", "interactives"}


def test_every_npc_or_interactive_marker_has_an_entry_and_every_entry_a_marker(rows, markers):
    for map_id in MAPS:
        entries = rows["maps"][map_id]
        for kind, section in (("npc_marker", "npcs"), ("interactive", "interactives")):
            in_scene = {rid for rid, m in markers[map_id].items() if m["kind"] == kind}
            assert in_scene == set(entries[section]), (map_id, kind)


def test_npc_entries_name_their_marker_and_keep_a_body_of_its_race(rows, markers):
    for map_id in MAPS:
        for rid, entry in rows["maps"][map_id]["npcs"].items():
            marker = markers[map_id][rid]
            assert entry["name"] == marker["label"] == marker["extras"]["name"], rid
            assert entry["role"] in NPC_ROLES, rid
            body = entry["actorType"]
            assert isinstance(body, int), rid
            if "actorType" in marker["extras"]:
                # A named body may be fixed directly, including a new shopkeeper.
                assert body == marker["extras"]["actorType"], rid
            else:
                low, high = marker["extras"]["actorTypeBlock"]
                assert entry["group"] == "new" and low <= body <= high, rid
    sw = {rid: e for m in MAPS for rid,e in rows["maps"][m]["npcs"].items()}
    assert Counter(e["group"] for e in sw.values()) == {"new": 13, "re-homed": 5}
    assert sorted(e["actorType"] for e in sw.values() if e["group"] == "new") == [302, 305, 315, 323, 332, 338, 342, 348, 358, 360, 363, 375, 376]
    assert sorted(e["actorType"] for e in sw.values() if e["group"] == "re-homed") == [303, 307, 308, 310, 312]


def test_npc_occupations_are_publishable_and_names_stay_simple(markers):
    """An NPC marker's extras "occupation" is the line a client draws under the name (publish_server.py
    occupation_field, the server's eloria/npcs.py occupation_for). The owner's rule of 2026-10-14: the name stays
    simple and the job goes on that line, so no NPC marker names a person by the occupation it also carries."""
    for map_id in MAPS:
        for rid, marker in markers[map_id].items():
            if marker["kind"] != "npc_marker" or "occupation" not in marker["extras"]:
                continue
            name, occupation = marker["extras"]["name"], marker["extras"]["occupation"]
            assert isinstance(occupation, str) and occupation == " ".join(occupation.split()), rid
            assert 0 < len(occupation) <= OCCUPATION_LIMIT, rid
            assert not set(occupation) & OCCUPATION_FORBIDDEN and occupation.isprintable(), rid
            assert not (name.casefold() + " ").startswith(occupation.casefold() + " "), (rid, name, occupation)


def test_interactive_entries_are_rows_the_server_accepts(rows, markers):
    for map_id in MAPS:
        entries = rows["maps"][map_id]["interactives"]
        ids = [e["objectId"] for e in entries.values()]
        assert len(ids) == len(set(ids)), map_id
        nodes = {m["extras"]["objectId"] for m in markers[map_id].values() if m["kind"] == "harvestable"}
        for rid, entry in entries.items():
            assert entry["role"] in INTERACTIVE_ROLES, rid
            assert isinstance(entry["objectId"], int) and not 100 <= entry["objectId"] <= 335, rid
            assert entry["objectId"] not in nodes, rid
            assert entry["target"] and entry["text"], rid
    desk = rows["maps"]["landfall"]["interactives"]["landfall--obj-landing-register-desk"]
    ferry = rows["maps"]["greenlight"]["interactives"]["greenlight--obj-ferry-n10"]
    assert (desk["objectId"], desk["role"], desk["target"]) == (20, "information", "register")
    assert (ferry["objectId"], ferry["role"], ferry["target"]) == (21, "portal", "maps.txt")
    assert ferry["portal"]["destinationMap"] == "crownwater" and ferry["portal"]["oneWay"] is True


def test_no_server_field_can_break_a_row(rows):
    for map_id in MAPS:
        for section in ("npcs", "interactives"):
            for rid, entry in rows["maps"][map_id][section].items():
                for key in ("name", "role", "greeting", "target", "text"):
                    if key in entry:
                        assert not any(c in str(entry[key]) for c in FORBIDDEN), (rid, key)


def test_the_interactive_markers_carry_their_server_object_ids_and_roles(rows, markers):
    for map_id in MAPS:
        for rid, entry in rows["maps"][map_id]["interactives"].items():
            extras = markers[map_id][rid]["extras"]
            assert isinstance(extras.get("objectId"), int) and extras["objectId"] == entry["objectId"], rid
            assert extras.get("type") == entry["role"], rid


def tutorial_posts(markers):
    return {rid: m for rid, m in markers.items() if m["kind"] == "runtime_point"
            and m["extras"].get("role") in ("tutorial-target", "tutorial-option")}


def test_every_chapter_target_has_one_marker_named_for_its_post(markers):
    renamed = {entry["newMarkerId"]: entry for entry in
               load(V2 / "_continent_v2/marker-renames.json")["entries"]}
    posts = {rid:m for region in MAPS for rid,m in tutorial_posts(markers[region]).items()}
    assert len(posts) == 22   # geo.json: 12 tgt_* and 10 opt_* posts
    counts = Counter(m["extras"]["target"] for m in posts.values())
    assert all(counts[t] == 1 for t in CHAPTER_TARGETS), counts
    assert len(counts) == len(posts)
    for rid, m in posts.items():
        extras = m["extras"]
        prefix, target = extras["post"].split("_", 1)
        history = renamed[rid]
        post_name = extras["post"].replace("_", "-")
        assert m["node_name"] == rid == history["newMarkerId"], rid
        assert history["kind"] == "runtime_point" and history["oldMarkerId"] == post_name, rid
        assert history["oldNodePath"].rsplit("/", 1)[-1] == post_name and target == extras["target"], rid
        assert extras["role"] == {"tgt": "tutorial-target", "opt": "tutorial-option"}[prefix], rid
        assert extras["chapterTarget"] is (target in CHAPTER_TARGETS), rid
        assert extras.get("radius", 6) == 6, rid
    quest = {m["extras"]["questXY"]: rid for rid, m in posts.items() if "questXY" in m["extras"]}
    assert {key: renamed[rid]["oldMarkerId"] for key, rid in quest.items()} == QUEST_XY


def test_split_retains_exactly_three_authored_arrivals_and_unique_owned_marker_ids(markers):
    renamed = load(V2 / "_continent_v2/marker-renames.json")["entries"]
    all_ids = [rid for region in MAPS for rid in markers[region]]
    additions = {region + "--obj-shared-storage" for region in
                 ("landfall", "greenlight", "hearthcroft", "stagheath", "tollholm")}
    # the North Wall farm (Landfall liveliness pass): three rows of Cotton, then two of Hearthroot
    additions |= {f"landfall--harvest-{object_id}-cotton" for object_id in range(2000, 2024)}
    additions |= {f"landfall--harvest-{object_id}-hearthroot" for object_id in range(2024, 2040)}
    additions |= {door["marker"] for section in load(V2 / "_continent_v2/content/underground.json")["sections"]
                  for door in underground_source.doors(section)}
    additions.add("landfall--npc-toolkeeper-rowan-hale")
    additions.add("landfall--npc-cape-seller-mara-vell")
    # the outer isles' people (Landfall liveliness pass)
    additions |= {"greenlight--npc-causeway-warden-edda-tine", "hearthcroft--npc-crofter-oyun-tarag",
                  "tollholm--npc-toll-keeper-tobin-ware", "boarsend--npc-swineherd-gil-mast",
                  "ringholm--npc-stone-keeper-ylva-stane", "saltsound--npc-salter-ruha-sel"}
    # the isle boats (owner 2026-10-14: R5): each boat's interactive and the landing the boat from the far shore uses
    additions |= {rid for region in MAPS for rid, entry in rows_doc()["maps"][region]["interactives"].items()
                  if (entry.get("portal") or {}).get("destinationMap") in MAPS}
    additions |= {entry["portal"]["landingMarker"] for region in MAPS
                  for entry in rows_doc()["maps"][region]["interactives"].values()
                  if (entry.get("portal") or {}).get("destinationMap") in MAPS}
    assert len(all_ids) == len(set(all_ids)) == len(renamed) + len(additions)
    assert len(renamed) == 254 and set(all_ids) - additions == {entry["newMarkerId"] for entry in renamed}
    assert additions <= set(all_ids)
    for entry in renamed:
        assert entry["newMarkerId"] in markers[entry["newRegion"]]
    assert sum(m["kind"] == "spawn" for region in MAPS for m in markers[region].values()) == 3
    for region in MAPS:
        entrances = {door["marker"] for section in load(V2 / "_continent_v2/content/underground.json")["sections"]
                     for door in underground_source.doors(section) if door["map"] == region}
        assert all(rid.startswith(region+"--") or rid in entrances for rid in markers[region])


def test_isle_boats_are_pairs_that_land_on_their_landing_points(rows, markers):
    """A portal interactive bound for another isle (owner 2026-10-14: R5, the Ravenhead-Tollholm boat) names the
    boat-landing runtime point it lands on there (portal.landingMarker) and the boat that sails back
    (portal.returnBy), which names it in turn: publish_server.py's isle_boat and pair_boats, read from the scenes."""
    boats = {rid: (region, entry) for region in MAPS for rid, entry in rows["maps"][region]["interactives"].items()
             if (entry.get("portal") or {}).get("destinationMap") in MAPS}
    for rid, (region, entry) in boats.items():
        portal = entry["portal"]
        destination = portal["destinationMap"]
        assert destination != region and portal["oneWay"] is True, rid
        landing = markers[destination].get(portal["landingMarker"])
        assert landing and landing["kind"] == "runtime_point" and landing["extras"].get("role") == "boat-landing", rid
        back = boats.get(portal["returnBy"])
        assert back and back[0] == destination, rid
        assert back[1]["portal"]["destinationMap"] == region and back[1]["portal"]["returnBy"] == rid, rid
        assert entry["role"] == "portal" and entry["target"] == "maps.txt", rid
    # every boat-landing point is some boat's landing
    points = {rid for region in MAPS for rid, m in markers[region].items()
              if m["kind"] == "runtime_point" and m["extras"].get("role") == "boat-landing"}
    assert points == {entry["portal"]["landingMarker"] for _region, entry in boats.values()}
