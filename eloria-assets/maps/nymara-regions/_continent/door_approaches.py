"""Authored road ends for doors that a retained structure encloses.

Door roads are routed from each territory's hub straight to the doorway. That
is right for a door in a wall that faces open ground, and wrong for the Shrine
of the Nine Lost in Verdant Stair: its door stands on the terrace of the South
Quay pavilion, whose west side is the pavilion's jade wall and whose only open
side is the north. The routed road arrived from the west, its last two
stations wet under the quay, so the bridge builder raised a nine-metre deck
that ends against the wall, while the served door tile (the terrace's north
edge) is reached from the north across plain ground.

A pin here ends the door road on the open side of such a pavilion; the retained
walking floor carries the last metres to the door and no deck is built. The
pinned end must be dry ground inside the door's own territory.

The module also holds the authored waypoints a road passes on its way: a door
road's (hub -> waypoint -> ... -> door end) and a seam road's (hub -> waypoint
-> ... -> crossing terminal). Both are routed in legs by ``route_in_legs``, so
a mountain pass climbs the switchback its valley suggests instead of taking the
router's shortest line. Waypoints obey the same rules as a pinned end: dry
ground, out of the water, inside the territory whose hub the road leaves.
"""
from __future__ import annotations
import numpy as np
import landscape as L

# (region, portal id) -> global XZ metres where the door road ends.
ROAD_ENDS = {
    # North of the South Quay pavilion. Until the roads pass (R1) the end stood on the
    # pavilion's north threshold (1206.5, 1175.5), 2 m from the river: a road end stands
    # outside its river setback now (6 m for a door road), so it moved 6 m west-north-west
    # onto dry ground 8.9 m from the water, 10.3 m from the door.
    ('verdant_stair', 'nine-lost-door'): (1201.0, 1173.0),
    # The gate undercroft stair opens east out of the Great Arch's base masonry
    # onto a pocket of level ground; a road routed to the door itself ends inside
    # the masonry, and every earlier publication reached the served tile only
    # over a bridge deck the raised road profile built 14 m above the arch. The
    # pin stands seven metres clear of the arch so the road goes round it; R1 moved
    # it 3 m east of (616.5, 589.5), out of the stream's setback (8.5 m from the water).
    ('amberwood', 'gate-undercroft-stair'): (619.0, 591.0),
}
# (region, portal id) -> (retained node, (dx, dz)): a door road end anchored on a
# retained object, for a door whose way in is that object's own stair or court.
# The pin is the object's composed pivot (the centre of its composed bounds in
# x/z) plus the territory layout's turn of (dx, dz), metres along the legacy
# source axes and never squeezed, so it keeps its place on the object however
# the retained transform turns, squeezes or grounds the layout. It needs the
# composed content (prepare_door_approaches runs after Content.load), refuses an
# object that is not retained, and is then validated and served exactly as a
# ROAD_ENDS pin: dry ground in the door's territory, within
# MAXIMUM_DOOR_DISTANCE_METRES of the door.
RETAINED_ROAD_ENDS = {
    # The Whitehorn glacier temple's door stands on its platform 4.4 m in front of
    # the facade, and the platform's stair descends to the front between right
    # -5.0 and 5.4, meeting the legacy forecourt at front 13.15 (the legacy foot
    # (99.55, 68.04, -220.98)). Routed to the door itself (design O4) the road
    # climbed onto the platform over its left flank and ran along it; pinned just
    # past the stair foot it ends there and the platform carries the last metres.
    # At front 15.5 (a first authoring) the end stood on the slope below the
    # forecourt 3.5 m under the stair's last tread, and 12.2 m from the server
    # portal on the platform (458.1, 124.2), just past door_road_end_near's reach:
    # that portal and the eyrie secret beyond it then took discovery branches that
    # the temple's solid sent 862 m and 1068 m round the mountain (offline
    # composition). At 13.5 the portal is 10.1 m away and shares this end.
    ('whitehorn_range', 'whitehorn-glacier-temple-door'): ('Landmark_glacier_temple', (0.25, 13.5)),
}
# (region, portal source map, portal target map) -> global XZ metres of dry
# ground where the discovery branch to a server-only portal is routed to; the
# branch then runs straight from there to the portal itself, a deck where the
# ground is water, and approaches from that side of the portal. The Amber Gate
# estate door opens west out of the Great Arch's base onto the stream the arch
# spans, 3 m from the undercroft stair that opens east: too close to tell the
# two apart by distance, so its branch is pinned to the dry court west of the
# stream and reaches the door over the water.
# A map pair may hold several pins (one per entrance): each serves the portal
# within MAXIMUM_DOOR_DISTANCE_METRES of it. The Sunmane camp's furniture is
# one solid at the router's 2 m cells and margins, so a branch routed straight
# to a secret marker threads whatever stands between its nearest road station
# and the marker: the banner-focus branch crossed the round tent for 15 m and
# the windmill, the spring branch (routed from the banner-focus branch's end)
# the windmill, the banner shrine and two standing stones. Pinned to the
# pocket north of the animal pen and to the open ground north of the spring,
# their routed parts cross nothing and the straight runs only the markers'
# own boxes (the banner focus stands at the pen's box edge). The mill-cache
# branch (307) took the new banner line as its nearest station and looped
# west through the pen, the spring and two tents (86 m): pinned to the pen 02
# margin north-east of the windmill it comes through the same pocket; its
# marker stands inside the windmill's box and 4 m inside round tent 06's
# footprint, which no pin avoids.
# R1 (the roads pass) keeps every pin outside its river setback: the estate pin moved
# from (600, 590), 2 m from the stream, to the west court's dry edge (6.3 m from the
# water, 11.9 m from the portal), and the spring pin from (1196, 760), 4.5 m from the
# Limestone River, 5.7 m east (8.9 m from the water, 9.9 m from its marker). The
# branch no longer runs on from a pin over water to a portal standing in it.
SERVER_ROAD_ENDS = {
    ('amberwood', 'amberwood', 'amberwood_estate'): (596.5, 588.),
    ('sunmane_steppe', 'sunmane_steppe', 'sunmane_steppe_secrets'): [(1216., 732.), (1201.5, 761.5), (1232., 734.)],
}
SERVER_ROAD_END_LEG_METRES = 2.   # a pin closer than this to its portal is the road's end itself
# (region, portal id) -> authored waypoints in continent metres: the door road is
# routed hub -> waypoint -> ... -> door end in legs, so a designed climb passes
# its overlook, refuge or shrine instead of taking the router's shortest line.
DOOR_ROAD_WAYPOINTS = {
    # R1 (2026-09-16): the Grey Moors hub's climbs out of the Moorwater valley. The hub (220, 420) stands on the
    # valley's west wall at 32 m; the barrows and crypts stand 55-90 m above it on slopes of .6-1.3, which the 4 m
    # cut and 3 m fill limits cannot grade to .45 on the router's own line (the O5 lines ran straight up them: routing
    # excess of 56, 56 and 110 m). The west trunk climbs the west wall north, crosses to the upper slope at z 294-306
    # and turns in one hairpin at (300, 342) to the warm stone and the great barrow; the east crypt stair continues
    # from there along the upper slope (412 m), so it needs no bridge. The fifth chamber shares the seam road's east
    # trunk (SEAM_ROAD_WAYPOINTS below). Found as bounded-grade paths (grade .40-.43, legs 12-36 m, every edge within
    # the limits of the ground) on the R1 candidate composition and routed there leg by leg: no leg exceeds the limits
    # but by the 8 m a leg's pinned end takes at a steep joint.
    ('grey_moors', 'warm-stone-door'): [
        (210., 360.), (216., 336.), (222., 306.), (246., 294.), (264., 306.), (288., 324.), (300., 342.), (294., 324.), (278., 308.)],
    ('grey_moors', 'great-barrow-mouth'): [
        (210., 360.), (216., 336.), (222., 306.), (246., 294.), (264., 306.), (288., 324.), (300., 342.), (294., 324.), (278., 308.)],
    ('grey_moors', 'east-crypt-stair'): [
        (210., 360.), (216., 336.), (222., 306.), (246., 294.), (264., 306.), (288., 324.), (300., 342.), (294., 324.), (278., 308.),
        (294., 312.), (306., 330.), (336., 342.)],
    ('grey_moors', 'fifth-chamber-mouth'): [
        (276., 426.), (282., 408.), (312., 426.), (324., 408.), (342., 414.), (348., 390.)],
}
# The same for a retained territory, in its source (library) metres: the plan's
# retained transform (translation and squeeze) carries them where the layout stands.
RETAINED_DOOR_ROAD_WAYPOINTS = {
    # Whitehorn Range (the legacy relief under its retained transform): the climbs
    # the old map's valley suggests, from the gate court at the south seams.
    # The temple road's stops. Authored at (70, 40), (88, -58) and (76, -192) they
    # lay inside the lower camp's footprint and 2.3-2.6 m off the bridge watch and
    # the temple rest; no hut is a solid for the router, so the road ran through
    # them and settle_roads cut their ground to its own profile (O4: 163, 168 and
    # 192 m against bases of 175.3, 174.25 and 202.7). Now:
    #   lower camp   (43.6, 27.3): on the Amberwood seam road's corridor 24 m west
    #                of the hut, which that road already grades, so the door road
    #                adds no corridor beside the camp;
    #   bridge watch (87.5, -55.7): on the watch's pad 7.9 m in front of it;
    #   temple rest  (87.5, -187.5): 8.3 m east of the hut, on the road's line
    #                from the corridor it shares below to the temple's stair foot,
    #                so the road passes the hut instead of crossing it.
    # The road ends at the stair foot (RETAINED_ROAD_ENDS); what holds its height
    # there is the glacier temple's compound footing (assemblies.placement_group),
    # not these stops: corridor_grade caps the stair foot near 196 m through the
    # road network (two offline compositions, one with a 77 m loop authored west
    # of the temple rest, which the router ran as out-and-back spurs).
    ('whitehorn_range', 'whitehorn-glacier-temple-door'): [(43.6, 27.3), (87.5, -55.7), (87.5, -187.5)],
    ('whitehorn_range', 'whitehorn-mine-adit'): [(176., 18.), (237., -26.), (200., -120.)],           # high overlook, east camp, mine yard
    ('whitehorn_range', 'snowline-cell-door'): [(237., -26.), (251., -102.)],                          # east camp, the east valley
    ('whitehorn_range', 'whitehorn-ice-cave-mouth'): [(-93., -38.)],                                  # the old west pass station
    ('whitehorn_range', 'west-watch-cave-mouth'): [(-93., -38.), (-81., -96.)],                       # west pass station, the west valley
    ('whitehorn_range', 'whitehorn-barrow-door'): [(-93., -38.), (-81., -96.), (-85., -150.)],        # ... and past the watch cave
}
# (region, connection id) -> authored waypoints in continent metres for a seam
# road: the road from that territory's hub to its side of a border crossing is
# routed hub -> waypoint -> ... -> crossing terminal in legs, so a pass climbs
# its authored switchback instead of the router's shortest line. A connection id
# is the crossing's own id, the two region ids sorted and joined by '--' (as in
# 'grey_moors--whitehorn_range'), and each of the two sides of a crossing is
# authored separately under its own region: the mountain side takes the climb
# while the other side stays a straight run to the terminal.
SEAM_ROAD_WAYPOINTS = {
    # The Moors pass. Design O2 authored four legs of switchback down the west face to a crossing at (362, 327):
    # (371, 302), (412, 364), (349, 281), (411, 377), (364, 327). R1 moved the crossing to the gentle west foot at
    # (378, 379) (make_whitehorn_plan_r1.py) and this road now leaves the gate court down the south face on the
    # switchback it shares with the Amberwood crossing's road, then runs west along the foot to its terminal
    # (387, 379): legs of 20-57 m at grades .31-.42 on the R1 candidate composition's ground, every one within
    # the 4 m cut and 3 m fill limits of the ground (a bridge-grade search, R1.md): (496, 400), (512, 420),
    # (536, 424), (484, 416), (444, 396), (392, 372), (408, 384).
    #
    # Re-authored on the R1 candidate composition's own ground (that first R1 line was found on ground the O5 roads
    # had cut 20-65 m into the face, and routed with 128 m of legs beyond the limits): out of the court west, seven
    # hairpins down the south-west face to (438, 396), then the bench loop the ground allows onto the terminal's
    # shelf -- down to (392, 372), east along the shelf to (408, 384) and back to the terminal. 395 m; routed leg by
    # leg there, no leg beyond the limits but the 8 m at three steep joints. The Amberwood crossing's road shares it
    # as far as (408, 384). The hairpin at (510, 426) keeps the line 15 m clear of shrine 00's footprint.
    ('whitehorn_range', 'grey_moors--whitehorn_range'): [
        (504., 384.), (474., 372.), (492., 402.), (510., 426.), (480., 408.), (486., 420.), (468., 408.), (438., 396.),
        (408., 378.), (392., 372.), (408., 384.)],
    # The Grey Moors side: out of the hub over the Moorwater bridge, then five traverses up the east wall to the
    # bench at 64 m and north to the terminal (369, 379); 255 m, no leg beyond the limits (O5-line excess 48 m). The
    # fifth chamber door road shares the trunk.
    ('grey_moors', 'grey_moors--whitehorn_range'): [
        (276., 426.), (282., 408.), (312., 426.), (324., 408.), (342., 414.), (348., 384.)],
    # The east pass: out of the gate court south-east down the tail, then two hairpins round the east flank
    # onto the Barrens' floor, 377 m for 84 m of descent (grades 0.13 to 0.38). Leg 2 crosses the Hornwater
    # at about (629, 418), where the ravine the river cuts is three metres deep.
    # Design O5: the first waypoint moved from (556, 394) to (544, 390). The leg to it
    # is a spur that returns north-west (the router rounds the village hill to the
    # north), and at (556, 394) its 4 m-wide corridor and 24 m shoulders reached the
    # snowline terrace's west edge 23-27 m away and cut it 8-15 m (the overlook's
    # and the stones' floating west edges).
    # R1: the second waypoint moved from (614, 406), 8.2 m from the Hornwater, to (610, 405), clear of the seam
    # road's 8 m river setback; leg 2 now crosses the river on the bridge site beside it (horn_tributary@288).
    ('whitehorn_range', 'amethyst_barrens--whitehorn_range'): [
        (544., 390.), (610., 405.), (668., 448.), (694., 433.), (692., 377.), (760., 419.), (786., 340.)],
    # The Amberwood crossing. Design O5 authored eight legs here (quoted below): out of the gate court
    # north-east over the 173 m shelf, NORTH of the village strip, down the Hornwater's west scarp beside the
    # east pass's own descent, across the river, down the tail's EAST bank, back over the river at the saddle
    # and west along the tail's southern bench to the crossing's lip: (556, 350), (596, 340), (628, 384),
    # (648, 420), (640, 452), (604, 464), (574, 464), (558, 450). R1 retired them: three stood 2-4 m from the
    # Hornwater, inside the seam road's 8 m river setback, and the line crossed the river twice 65 m apart,
    # where one bridge site per 100 m of river allows only one. The court no longer needs the bought length
    # either: corridor_grade still reconciles the network, but settle_roads now holds every road within 4 m of
    # cut and 3 m of fill of the ground it finds (world_layout.limit_corridor_earthworks), so the network cannot
    # sink the court. What the router makes of the escarpment unaided is measured in R1.md.
    #
    # This one is not scenery. The crossing at (531, 436) is 52 m from the gate court and 103 m above the
    # Amberwood roads at (516, 444), and world_layout.corridor_grade reconciles the whole connected road
    # network at 0.318 m per metre along an axis, writing the midpoint of its lower and upper envelopes. A
    # direct seam road put those Amberwood roads 124 m of corridor from the court, so the court's upper
    # envelope was 69.2 + 0.318 x 124 = 108.6 m against its own 172.8 m target and it composed at 126.1 m
    # (design O2). Authored length is what buys the head back.
    #
    # Design O3 bought it with six legs east of the court -- and ran them straight through the village on the
    # south-east slope, which settle_roads then cut to the road's own descending profile: the high overlook
    # 179.8 -> 134.9 m, the ram pit 143.2 -> 99.4, the snowline stones 173.4 -> 139.5, Structure_watch_01
    # 175.7 -> 142.7. Four of its six waypoints stood inside a village footprint. These eight legs buy the
    # same length (336 m of authored line, against O3's 179) on ground that holds nothing: the nearest
    # village footprint is 26.6 m from the line and the nearest graded road cell 17-27 m from each of the
    # four placements, which is outside road_shoulder_field's 24 m band. Replaying corridor_grade over this
    # route before the bake leaves the gate court at the same 154.1 m O3 gave it.
    #
    # Every waypoint is inside Whitehorn on dry ground of 108-175 m; the legs fall at 0.01 to 0.71 on the
    # plan's ground and the steepest 10 m window on the line, 1.56, is the Hornwater's own west scarp at
    # (583, 343), which the east pass descends beside it. The two river crossings are shallow: the northern
    # one is the east pass's own, and the southern one is the saddle at (630, 456) where the ravine is about
    # three metres deep. The crossing station itself did not move -- the ownership raster offers 27 safe
    # stations and every one of them lies on the z 422-436 line at x 397-533 (design O3 section 4).
    #
    # (558, 450) is the last leg's pin and it is not decoration. Without it the router's own A* took the
    # 51 m run from (574, 464) to the crossing terminal in a northward arc through (570, 437), 16 m from
    # Secret_horn_ram_pit's 4.5 m footprint and inside road_shoulder_field's 24 m band, and the first O4
    # bake composed the ram pit at 121.2 m against design O2's 143.2 while the other three village
    # placements came back within 2 m. Pinned, the approach stays south of the saddle and the whole line
    # keeps 33.2 m from that footprint. Measure a candidate against the ROUTED road, not the authored
    # polyline: the straight line here is 27.3 m clear where the route was 16.
    #
    # R1 then moved the crossing itself to the massif's west foot at (397, 422), where its terminal line is gentle
    # (grade .24 against 3.5 at (531, 436)). The road shares the Moors pass's descent (above) to the shelf at
    # (408, 384), then drops off the shelf's east end in two more traverses to the foot and the terminal (397, 413);
    # 459 m, routed on the R1 candidate composition's ground with no leg beyond the limits but 8 m at joints. (The
    # first R1 line, (496, 400) (512, 420) (536, 424) (484, 416) (444, 396) (396, 372) (440, 408) (412, 400), was found
    # on ground the O5 roads had cut and routed with 160 m of legs beyond the limits.)
    ('whitehorn_range', 'amberwood--whitehorn_range'): [
        (504., 384.), (474., 372.), (492., 402.), (510., 426.), (480., 408.), (486., 420.), (468., 408.), (438., 396.),
        (408., 378.), (392., 372.), (408., 384.), (414., 390.), (426., 399.), (438., 408.), (426., 405.), (414., 402.)],
    # Four Gates has four gates and had two roads. A seam road runs between its two territories' hubs by way of a
    # station on the seam that both hubs can reach, so a gate gets a road only where such a station can stand in
    # front of it (measured 2026-09-18).
    #
    # South: pinned to the seam at (519, 990) with the Mirrorwater bridged at arc 358, the Manymouth road left the
    # one bridge that joins the two halves of the delta (western_river@760, (517, 1058)) and half of Manymouth Delta
    # - 56 thousand tiles - lost its way to the hub. Pinned there with the crossing left to the model, no road
    # alignment reaches the station from the Manymouth hub at all. Kept at the model's station (449, 988) and led
    # out through the south gates by waypoints, the Four Gates road found no way west outside the wall and came
    # back through the gates, out by the west trunk and round over the Western River: 742 m where 170 would do.
    #
    # So the south gate waits for its road to be one that only has to reach the border, now that a border can be
    # crossed wherever the ground allows: it no longer has to be the one road that carries the map change.
    #
    # North: the Amberwater lies along the seam in front of the gate from (513, 690) to (543, 694), where every
    # road terminal would stand in the water, and comes off it eastward. An authored station may now stand on a
    # step of the seam, and (553, 698) - 27 m from the gate, every terminal 12.7 m or more from the water - was
    # accepted, routed and bridged over the Amberwater at arc 154 (550, 668). It still cannot be crossed: east of
    # the water the border runs along the far rim of a gully. From the bridge's south landing at 21 m the ground
    # falls to 11.8 m at z 694 and climbs back to 18.8 m at the station within four metres, so the road dropped
    # into the gully and out of it at grades to 1.75, the strip between the gully and the border was ground neither
    # hub could reach, and the gate's lanes landed on it. Every station in front of the gate stands on that rim.
    # A crossing there needs a deck across the gully (access_decks.py), not a road through it: an owner's decision.
}
# The same for a retained territory, in its source (library) metres, carried
# where the layout stands by the plan's retained transform (as the retained door
# road waypoints above). The plan phase authors the two Whitehorn passes here,
# in this frame, since the range keeps its legacy relief under such a transform:
#   ('whitehorn_range', 'grey_moors--whitehorn_range')        the Moors pass,
#       authored as a switchback climb; and
#   ('whitehorn_range', 'amethyst_barrens--whitehorn_range')  the east pass.
RETAINED_SEAM_ROAD_WAYPOINTS = {
}
MINIMUM_DRY_METRES = .8
MAXIMUM_DOOR_DISTANCE_METRES = 12.


def prepare_door_approaches(world, content):
    """Validate and expose the pinned road ends and the authored door and seam waypoints before the roads are routed."""
    saved = set(getattr(world, 'authoring_snapshots', {}))
    def validated(region, label, x, z):
        if int(world.owner_at(x, z)) != world.ids.index(region):
            raise ValueError(f'{region}:{label}: authored door road end lies outside its territory')
        height = float(world.height_at(x, z))
        if height < MINIMUM_DRY_METRES:
            raise ValueError(f'{region}:{label}: authored door road end is not dry ground ({height:.2f} m)')
        ix = int(round((x - world.x0) / (world.x[1] - world.x[0])))
        iz = int(round((z - world.z0) / (world.z[1] - world.z[0])))
        if world.water['mask'][iz, ix]:
            raise ValueError(f'{region}:{label}: authored door road end stands in water')
        return np.array([x, z], dtype=float)
    ends = {}
    for (region, portal), (x, z) in ROAD_ENDS.items():
        if region in world.ids and region not in saved:
            ends[(region, portal)] = validated(region, portal, x, z)
    retained_ends = {}
    for (region, portal), (node, (dx, dz)) in RETAINED_ROAD_ENDS.items():
        if region not in world.ids or region in saved:
            continue
        anchor = next((obj for obj in getattr(content, 'objects', ()) if obj.get('region') == region and obj.get('node') == node), None)
        if anchor is None:
            raise ValueError(f'{region}:{portal}: the door road end is anchored on {node}, which is not a retained object in {region}')
        if (region, portal) in ends:
            raise ValueError(f'{region}:{portal}: the door road end is pinned twice, in ROAD_ENDS and in RETAINED_ROAD_ENDS')
        pivot = (np.asarray(anchor['low'], dtype=float) + np.asarray(anchor['high'], dtype=float)) * .5
        transform = getattr(world, 'plan', {}).get('retained_transforms', {}).get(region)
        rx, rz = L._rotate_xz(float(dx), float(dz), L.retained_yaw_degrees(transform) if transform is not None else 0.)
        ends[(region, portal)] = validated(region, portal, pivot[0] + rx, pivot[2] + rz)
        retained_ends[(region, portal)] = {'node': node, 'offset': [float(dx), float(dz)],
                                           'pivot': pivot[[0, 2]].tolist(), 'end': ends[(region, portal)].tolist()}
    server_ends = {}
    for (region, source, target), pins in SERVER_ROAD_ENDS.items():
        if region in world.ids and region not in saved:
            pins = [pins] if not isinstance(pins, list) else pins
            server_ends[(region, source, target)] = [validated(region, f'{source}->{target}', x, z) for x, z in pins]
    def waypoints_of(authored, retained):
        """Authored road waypoints in order, from the continent frame and from a retained source frame.

        The key's second field (a portal id for a door road, a connection id
        for a seam road) names the road in every refusal.
        """
        prepared = {}
        for (region, road), points in authored.items():
            if region in world.ids and region not in saved:
                prepared[(region, road)] = [validated(region, f'{road} waypoint {index}', x, z) for index, (x, z) in enumerate(points)]
        for (region, road), points in retained.items():
            if region not in world.ids or region in saved:
                continue
            transform = getattr(world, 'plan', {}).get('retained_transforms', {}).get(region)
            if transform is None:
                raise ValueError(f"{region}:{road}: source-frame waypoints need the territory's retained transform")
            mapped = L.retained_map_xz(transform, points)
            prepared[(region, road)] = [validated(region, f'{road} waypoint {index}', x, z) for index, (x, z) in enumerate(mapped)]
        return prepared
    waypoints = waypoints_of(DOOR_ROAD_WAYPOINTS, RETAINED_DOOR_ROAD_WAYPOINTS)
    seam_waypoints = waypoints_of(SEAM_ROAD_WAYPOINTS, RETAINED_SEAM_ROAD_WAYPOINTS)
    content.door_road_ends = ends
    content.server_road_ends = server_ends
    content.door_road_waypoints = waypoints
    content.seam_road_waypoints = seam_waypoints
    world.door_approaches = {'roadEnds': {f'{region}:{portal}': point.tolist() for (region, portal), point in ends.items()},
                             'retainedRoadEnds': {f'{region}:{portal}': entry for (region, portal), entry in retained_ends.items()},
                             'serverRoadEnds': {f'{region}:{source}->{target}': [point.tolist() for point in points] for (region, source, target), points in server_ends.items()},
                             'waypoints': {f'{region}:{portal}': [point.tolist() for point in points] for (region, portal), points in waypoints.items()},
                             'seamWaypoints': {f'{region}:{connection}': [point.tolist() for point in points] for (region, connection), points in seam_waypoints.items()},
                             'policy': 'A door inside a retained pavilion gets its road on the pavilion\'s open side; the retained floor carries the last metres.'}
    return world.door_approaches


def door_road_waypoints(content, region, portal):
    """The authored waypoints a door road passes on its way from the hub, in order (none for most doors)."""
    return list(getattr(content, 'door_road_waypoints', {}).get((region, portal), []))


def seam_road_waypoints(content, region, connection_id):
    """The authored waypoints a seam road passes between the hub and the crossing terminal, in order.

    Empty for every seam but an authored pass, where the road is then routed in
    legs through them: the pass climbs its switchback instead of the router's
    shortest line to the border.
    """
    return list(getattr(content, 'seam_road_waypoints', {}).get((region, connection_id), []))


def route_in_legs(world, legs, region, own=None, width=None, public=False, name=None):
    """One road alignment routed through its authored waypoints: hub -> waypoint -> ... -> end.

    Every leg but the last drops its final station, which is the next leg's
    first, so the joints are not stations twice over. ``own`` (the retained
    solids the road may cross because they hold its start, from
    ``world.solids_at_ends``) applies to the first leg only, as it did when the
    road was one call; the later legs let the router take the solids of their
    own two ends. With two stations and no waypoints this is exactly
    ``world.route(legs[0], legs[1], region=region, own=own)``. ``width``,
    ``public`` and ``name`` reach every leg's route (its river setback, whether
    its crossings become shared bridges, and the road its claims are recorded
    under) when given.
    """
    legs = list(legs)
    extra = {key: value for key, value in (('width', width), ('public', public), ('name', name)) if value}
    parts = []
    for index, (a, b) in enumerate(zip(legs, legs[1:])):
        leg = world.route(a, b, region=region, own=own if index == 0 else None, **extra)
        parts.append(leg[:-1] if index < len(legs) - 2 else leg)
    return np.vstack(parts)


def validate_river_setbacks(world, content, door_width=1.65, seam_width=4.):
    """After river_crossings.prepare_river_crossings: every pinned road end and authored waypoint stands outside its
    road's river setback, and every authored leg whose straight line crosses a plan river has a candidate crossing
    of that river in its territory (the router then carries the leg over it on a bridge). Returns the legs that
    cross a river, with the nearest candidate to each crossing point."""
    import river_crossings as RC
    if getattr(world, 'river_water_distance', None) is None:
        return []
    policy = RC.policy_of(world)
    def check(region, label, point, width):
        setback = RC.setback_metres(policy, width)
        distance = float(RC.water_distance_at(world, point[0], point[1]))
        if distance <= setback:
            raise ValueError(f'{region}:{label}: stands {distance:.1f} m from river water, inside the {setback:g} m river setback')
    for (region, portal), point in getattr(content, 'door_road_ends', {}).items():
        check(region, f'{portal} road end', point, door_width)
    for (region, source, target), pins in getattr(content, 'server_road_ends', {}).items():
        for point in pins:
            check(region, f'{source}->{target} road end', point, door_width)
    legs = []
    for waypoints, width in ((getattr(content, 'door_road_waypoints', {}), door_width), (getattr(content, 'seam_road_waypoints', {}), seam_width)):
        for (region, road), points in waypoints.items():
            for index, point in enumerate(points):
                check(region, f'{road} waypoint {index}', point, width)
            route = [world.hub(region)] + list(points)
            for index, (a, b) in enumerate(zip(route, route[1:])):
                a, b = np.asarray(a, float), np.asarray(b, float)
                count = max(2, int(np.ceil(np.linalg.norm(b - a))) + 1)
                line = a + (b - a) * np.linspace(0., 1., count)[:, None]
                wet = RC.water_distance_at(world, line[:, 0], line[:, 1]) <= 0.
                if not wet.any():
                    continue
                crossing = line[int(np.flatnonzero(wet)[len(np.flatnonzero(wet)) // 2])]
                nearby = [c for c in world.crossing_candidates if c['region'] == region]
                if not nearby:
                    raise ValueError(f'{region}:{road}: leg {index} crosses a river where its territory offers no crossing site')
                best = min(nearby, key=lambda c: float(np.linalg.norm(np.asarray(c['centre']) - crossing)))
                legs.append({'road': f'{region}:{road}', 'leg': index, 'crossesAt': crossing.round(1).tolist(), 'nearestCandidate': best['key'],
                             'candidateMetres': round(float(np.linalg.norm(np.asarray(best['centre']) - crossing)), 1)})
    if hasattr(world, 'door_approaches'):
        world.door_approaches['riverLegs'] = legs
    return legs


def door_road_end(content, region, portal, door_point):
    """Where the road to this door ends: the pin if one exists, else the door itself."""
    pinned = getattr(content, 'door_road_ends', {}).get((region, portal))
    if pinned is None:
        return np.asarray(door_point, dtype=float)
    if np.linalg.norm(pinned - np.asarray(door_point, dtype=float)) > MAXIMUM_DOOR_DISTANCE_METRES:
        raise ValueError(f'{region}:{portal}: authored door road end is further than {MAXIMUM_DOOR_DISTANCE_METRES} m from the door')
    return pinned


def server_road_end(content, region, point, source, target):
    """The pinned dry ground a server-only portal's branch is routed to, or None.

    A map can have several entrances from the same territory; the pin serves
    the portal within its reach and the others keep the default handling.
    """
    pins = getattr(content, 'server_road_ends', {}).get((region, source, target))
    if pins is None:
        return None
    pins = [pins] if isinstance(pins, np.ndarray) else list(pins)
    point = np.asarray(point, dtype=float)
    within = [pin for pin in pins if np.linalg.norm(pin - point) <= MAXIMUM_DOOR_DISTANCE_METRES]
    if not within:
        return None
    return min(within, key=lambda pin: np.linalg.norm(pin - point))


def door_road_end_near(content, region, point):
    """A server-declared destination beside a pinned door shares the door's road end.

    The server profile names the same shrine door as an instance portal, and
    the discovery branch would otherwise run its own last metres onto the wet
    threshold and seed a deck there.
    """
    point = np.asarray(point, dtype=float)
    for (pinned_region, _), pinned in getattr(content, 'door_road_ends', {}).items():
        if pinned_region == region and np.linalg.norm(pinned - point) <= MAXIMUM_DOOR_DISTANCE_METRES:
            return pinned
    return point
