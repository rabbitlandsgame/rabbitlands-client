#!/usr/bin/env python3
"""Derive client camera framings from the exported landmark positions.

Each panel of the concept detail board gets a camera placed relative to the
landmark it depicts, using the client's own isometric rig convention (pitch,
yaw and orbit distance) so every capture is a framing a player can actually
reach with the in-game camera.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import terrain                                          # noqa: E402

PACKAGE = Path(__file__).resolve().parents[1]

# Explicit camera framings, given as ground-relative eye and aim points so they
# stay correct if the landform is resculpted:
#   id, (eye x, eye z, eye height), (aim x, aim z, aim height), fov, note
PLACED = [
    ("p01-caravan-road", (26.0, 46.0, 2.6), (4.0, 20.0, 7.0), 54.0,
     "crop block and riding trail with the encampment on the skyline"),
    ("p03-seasonal-market", (0.0, 20.0, 5.6), (0.0, 1.0, 3.4), 55.0,
     "seasonal market with the great hall behind"),
    ("p05-caravanserai-gate", (-6.0, 40.0, 4.4), (-1.0, 25.5, 3.6), 48.0,
     "fortified gate bay and palisade from the road"),
    ("p07-well-and-pens", (-25.0, 32.0, 3.1), (-33.0, 24.0, 1.4), 54.0,
     "well, trough and horse paddocks"),
    ("p10-market-props", (3.0, 14.8, 2.1), (8.6, 8.6, 1.4), 54.0,
     "player-scale market goods and prop language"),
    ("p02-round-tent-camp", (-25.0, -35.0, 4.0), (-33.5, -44.5, 2.2), 48.0,
     "Orun round-tent camp"),
    ("great-hall", (0.0, 26.0, 12.0), (0.0, -12.0, 7.0), 50.0,
     "the monumental central hall over the crossroads"),
]

PLACED.extend([
 ("salt-pan",(-5,-118,6),(-21,-122,0),60,"salt pan below the dune road"),
 ("desert-camp",(-10,-126,4),(-19,-113,2),58,"drovers camp on the sheltered floor beside the salt road"),
 ("cave-mouth-wind",(68,-109,3),(70,-117,2.7),58,"Wind Caves mouth from the graded watch approach"),
 ("review-west-arrival",(-51,0,1.7),(-24,0,4.5),60,"West gate on the Mirrorhold approach"),
 ("review-pasture-bridge",(-42,-28,1.7),(-26,-28,1.7),58,"bridge deck and the pasture approach"),
 ("review-cove-bridge",(-43,25,1.7),(-55,25,1.7),58,"sloping drovers bridge over the beck"),
 ("review-north-gate",(0,-29,1.7),(0,-20,4),60,"north approach with the hall as a landmark"),
 ("review-north-road",(18,-51,1.7),(8,-28,6),58,"barrows beside the road instead of underneath it"),
 ("review-service-court",(0,18,2.0),(0,5,2.0),66,"bank and craft awnings grouped in the market"),
 ("review-west-inn",(-45,1,1.7),(-45,13,2.0),62,"inn gate and horse court beside the road"),
 ("review-water-pasture",(35,42,1.7),(37,50,1.0),56,"waterhole below the grain fields"),
 ("review-dune-road",(8,-112,1.7),(8,-126,2.3),58,"menhirs frame the northern crossing"),
 ("review-overview",(105,85,125),(5,-20,0),56,"surveyed settlement and pasture layout"),
])

# id, target landmark id (or explicit target), pitch, yaw, distance, fov, note
VIEWS = [
    ("aerial-overview", (2.0, 8.0, -4.0), -38.0, 208.0, 148.0, 48.0,
     "matches the aerial overview reference"),
    ("p01-caravan-road", (2.0, 8.6, 40.0), -13.0, 6.0, 34.0, 50.0,
     "caravan road toward the encampment"),
    ("p02-round-tent-camp", "Landmark_orun_round_tent_01", -13.0, 37.0, 14.0, 48.0,
     "round-tent camp"),
    ("p03-seasonal-market", (0.0, 10.5, 3.0), -12.0, 0.0, 26.0, 55.0,
     "seasonal market with the hall behind"),
    ("p04-banner-shrine", "Landmark_orun_banner_shrine_00", -11.0, 37.0, 15.0, 46.0,
     "clan banner shrine"),
    ("p05-caravanserai-gate", "Gate_South", -13.0, 0.0, 27.0, 50.0,
     "fortified gate bay"),
    ("p06-windmill", "Landmark_sunmane_windmill_00", -12.0, 96.0, 26.0, 50.0,
     "windmill over the crop block"),
    ("p07-well-and-pens", "Landmark_sunmane_well_01", -13.0, 118.0, 17.0, 48.0,
     "well and horse paddocks"),
    ("p08-standing-stones", (-44.0, 12.0, -18.0), -7.0, 108.0, 21.0, 44.0,
     "standing stone circle against the low sun"),
    ("p09-steppe-overlook", (0.0, 9.5, -4.0), -15.0, 212.0, 88.0, 55.0,
     "rider's overlook above the encampment"),
    ("p10-market-props", (8.5, 10.2, 8.0), -14.0, 172.0, 11.0, 42.0,
     "player-scale market goods and prop language"),
    ("great-hall", "Landmark_sunmane_great_hall", -15.0, 178.0, 44.0, 50.0,
     "the monumental central hall"),
    ("gate-north", "Gate_North", -18.0, 180.0, 24.0, 50.0, "north gate approach"),
    ("caravanserai-west", "Landmark_sunmane_caravanserai_00", -19.0, 95.0, 30.0, 52.0,
     "west travel-axis caravanserai"),
    ("coast-southwest", "Landmark_sunmane_landing_00", -18.0, 40.0, 40.0, 55.0,
     "cove landing and rugged coastline"),
    ("mesa-north", (-20.0, 14.0, -66.0), -14.0, 355.0, 46.0, 55.0,
     "flat-topped mesas along the north"),
    ("burial-field", "Landmark_sunmane_burial_mound_00", -19.0, 175.0, 26.0, 50.0,
     "barrow field and sealed passage"),
    ("animal-pens", "Landmark_sunmane_animal_pen_00", -20.0, 220.0, 26.0, 52.0,
     "horse paddocks and grazing ground"),
    ("outpost-ridge", "Landmark_sunmane_outpost_02", -17.0, 230.0, 26.0, 50.0,
     "remote rider outpost"),
    ("gameplay-default", "Landmark_orun_seasonal_market_02", -60.0, 0.0, 26.0, 50.0,
     "the client's default isometric gameplay framing"),
    ("gameplay-zoomed-out", (0.0, 8.0, 0.0), -60.0, 0.0, 90.0, 50.0,
     "maximum client zoom-out over the encampment"),
    # The expansion north and east: the dune field, the salt pans, the Amethyst
    # badland and the mountain boundary that closes the world.
    ("desert-dunes", (20.0, 14.0, -92.0), -11.0, 340.0, 52.0, 55.0,
     "the dune field north of the steppe, with the range on the skyline"),
    ("desert-water-station", "Landmark_sunmane_desert_station_01", -16.0, 120.0,
     22.0, 50.0, "water station on the sand road"),
    ("desert-camp", (-16.0, 13.0, -100.0), -14.0, 150.0, 22.0, 50.0,
     "a drovers' camp between the dune trains"),
    ("salt-pan", (6.0, 13.0, -124.0), -9.0, 200.0, 44.0, 55.0,
     "the bright salt-pan floor between dune trains"),
    ("badland-spires", "Landmark_sunmane_spire_00", -12.0, 210.0, 34.0, 52.0,
     "wind-carved spires on the Amethyst badland margin"),
    ("badland-crystal", "Landmark_sunmane_cave_crystal_hollow", -12.0, 150.0,
     22.0, 48.0, "the amethyst hollow entrance in the badland"),
    ("cave-mouth-wind", "Landmark_sunmane_cave_wind_caves", -10.0, 180.0, 20.0,
     46.0, "the Wind Caves mouth off the desert road"),
    ("mountain-front", (40.0, 20.0, -120.0), -6.0, 350.0, 70.0, 58.0,
     "the Whitehorn front closing the north of the region"),
    ("mountain-outpost", "Landmark_sunmane_outpost_06", -15.0, 200.0, 30.0, 52.0,
     "the eastern watch under the range"),
    ("waystone-road", "Landmark_sunmane_waystone_02", -13.0, 150.0, 18.0, 48.0,
     "waystones marking the sand road"),
    ("east-pass", (124.0, 12.0, -22.0), -13.0, 250.0, 40.0, 54.0,
     "the eastern frontier; no exterior map link"),
]

# Panels 8 and 9 are painted at golden hour, so those two are captured under the
# declared golden-hour environment variant as well as under daylight.
GOLDEN = ["p08-standing-stones", "p09-steppe-overlook", "aerial-overview",
          "p01-caravan-road", "desert-dunes", "mountain-front",
          "badland-spires"]


def camera_position(target, pitch_degrees: float, yaw_degrees: float,
                    distance: float):
    """Mirror the client's isometric rig: orbit `target` at pitch/yaw/distance."""
    pitch = math.radians(pitch_degrees)
    yaw = math.radians(yaw_degrees)
    horizontal = math.cos(pitch) * distance
    return (target[0] + math.sin(yaw) * horizontal,
            target[1] - math.sin(pitch) * distance,
            target[2] + math.cos(yaw) * horizontal)


def resolve(manifest: dict, landform) -> list[dict]:
    positions = {entry["id"]: entry["position"] for entry in manifest["landmarks"]}
    resolved = []
    placed_ids = set()
    for identifier, eye, aim, fov, note in PLACED:
        placed_ids.add(identifier)
        resolved.append({
            "id": identifier,
            "position": [round(eye[0], 2),
                         round(landform.height_at(eye[0], eye[1]) + eye[2], 2),
                         round(eye[1], 2)],
            "target": [round(aim[0], 2),
                       round(landform.height_at(aim[0], aim[1]) + aim[2], 2),
                       round(aim[1], 2)],
            "fov": fov, "framing": "placed", "note": note,
            "golden": identifier in GOLDEN})
    for identifier, target, pitch, yaw, distance, fov, note in VIEWS:
        if identifier in placed_ids:
            continue
        if isinstance(target, str):
            found = positions.get(target)
            if found is None:
                raise KeyError("unknown landmark for view %s: %s" % (identifier, target))
            point = (found[0], found[1] + 2.4, found[2])
        else:
            point = target
        resolved.append({
            "id": identifier, "target": [round(v, 2) for v in point],
            "position": [round(v, 2) for v in camera_position(point, pitch, yaw, distance)],
            "fov": fov, "pitchDegrees": pitch, "yawDegrees": yaw,
            "distance": distance, "note": note,
            "golden": identifier in GOLDEN})
    return resolved


def main() -> int:
    manifest = json.loads((PACKAGE / "world.json").read_text())
    import settlement
    layout = settlement.compose_layout(None)
    landform = terrain.build(pads=layout.pads())
    views = resolve(manifest, landform)
    views.sort(key=lambda entry: entry["id"])
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else PACKAGE / "camera-views.json"
    destination.write_text(json.dumps({"schemaVersion": 1, "views": views}, indent=2) + "\n")
    index=[{"id":v["id"],"eye":v["position"],"target":v["target"],
            "fieldOfViewDegrees":v["fov"],"lighting":"day",
            "panel":int(v["id"][1:3]) if v["id"].startswith("p") and v["id"][1:3].isdigit()
                    else ("aerial" if v["id"]=="aerial-overview" else None)} for v in views]
    target=PACKAGE/"references/captures/index.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(index,indent=2)+"\n")
    print("wrote %d views to %s" % (len(views), destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
