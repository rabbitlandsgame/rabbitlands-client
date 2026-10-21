#!/usr/bin/env python3
"""Build Landfall's disjoint underground sections from one authored plan and a theme table.

One authored plan (content/underground.json) drives the rock shell, tile collision, markers and minimap of the
shared interior map `landfall_insides`. Its sections (caves) are separated by unfloored, blocked blackspace (keep 15+
tiles between caves). Resources and creatures are server-owned and use the reviewed runtime models.

Retired with the procedural generators on 2026-10-16; the owner re-enabled it on 2026-10-20 for the Cenote Deeps
and again the same day for the Landfall underground programme (13 caves in three waves). It runs only with
--owner-approved. Every section is drawn the way the Cenote Deeps was: the builder draws only the shell (floor,
a low rock face round every wall ring, pools with banks, daylight shafts); the rocks, ruins, plants and lamps are
reviewed Meshy kit pieces that tools/prepare_underground_scenery.py packages and places from dressing(), which also
decides what they block here.

PLATFORM API (waves 2 and 3 build on this)
------------------------------------------
The map frame: `map.cells` in the source (480 since the programme; the four first caves kept their tiles when it
grew from 240). Server tile (x, y) is world (x, h, CELLS - y) (`world()`); nothing else may hardcode the size.

A section in the source holds:
  id, name, danger, style (a THEMES key), entrance {map, marker, object, tile, position, returnTile} on ONE line
  (retarget_underground.py rewrites it by text), arrival [x, y], exit [x, y],
  exitFacing [dx, dy]                  optional: the wall the way out is set into (default [0, -1])
  rooms [[x, y, rx, ry], ...]          room 0 is the safe entry chamber; the way out (exit) sits at its edge
  links [[a, b, width, [[x, y], ...]]]  passages between rooms, optionally winding through waypoints; links that
                                        close a loop leave rock pillars (holes in the outline): they are walled,
                                        dressed and cut away like any wall (see `wall_rings`, cutaway below)
  pools [[x, y, rx, ry], ...]          sunk water (unfloored); its colour is the theme's water tint
  shafts [[x, y, r], ...]              daylight shafts (a single legacy `shaft` [x, y, r] is still read)
  wallRockSpacing                      metres between wall rocks (default: the theme's `spacing`)
  nodeClearance                        optional radius (tiles) kept free of wall rocks round every node
  props [{asset, at, yaw, scale, block, height, palette, light, clearWall}, ...]
                                       kit scenery (assets: tools/prepare_underground_scenery.py SELECTION).
                                       block = radius (tiles) closed on the walk grid; clearWall = radius kept free
                                       of wall rocks (doorways, set pieces against a wall); light = a glowing piece
                                       lit with the theme's `glow`; palette = MineralAppearance {stone, mineral}
  nodes [[objectId, resource, x, y], ...]   server harvest nodes (tile blocked; a 4-neighbour must be reached)
  spawns [[creature, x, y, leash], ...]     server encounters (leash 1-8, >= leash + 20 tiles from the arrival)
  ledges [{terrace: [x, y, rx, ry] | polygon: [[x, y], ...], height, ramps: [[x0, y0, x1, y1, width], ...]}]
                                       optional walkable terraces with ramps (the owner's experiment, 2026-10-20: the
                                       Rimewater Ice Caves only); see LEDGES below. Without it a section is flat at 0 m.

THE THEME TABLE (THEMES): every section names one in `style`. A theme sets
  shape         room outline: 'lobes' (water-worn, rounded joints), 'chisel' (a mine's cut lobes) or
                'boxes' (cut-stone rooms with rounded corners)
  floor, rock, bed, bank   the shell's glTF materials (amberwood toolkit MaterialSpec names): the walk floor, the
                rock face and roof, a pool's bed and its bank
  wallHeight    the rock face's height (metres) before its ragged wobble
  margin        floor (tiles) kept unwalkable inside every wall ring, so actors clear the proud wall rocks
  spacing       default metres between wall rocks
  wallRocks     the kit pieces set into the face: (asset, proud) where proud is the piece's half depth (metres) and
                about a third of it stands proud of the face; a dict entry may add align=True (the piece's +X runs
                along the wall, e.g. a dyke)
  rockPalette   optional MineralAppearance palette for every wall rock (the veined crags' ore colour)
  lampColour    optional colour every lamp of the section shines (KIT_LIGHTS gives each lamp asset its own)
  glow          the light of a prop marked `light` (colour, energy, range, height)
  surfaces      the runtime styling, written per section into underground-scenery.json `surfaces` by the
                packager and applied by godot-client/src/world/underground_scenery.gd:
                  floor {texture: a LookProfile class texture, tint}, rockLift (the face's albedo multiplier
                  toward its wall rocks' colour, or null), water {deep, clear, glow} (cenote_water.gdshader)
  minimap       floor, edge and water colours on the minimap
Adding a theme: add its entry here (and any new texture to TEXTURE_RECIPES), package its kit pieces in the
packager's SELECTION, then build and run the layout check.

CUTAWAY: walls are `Build_<section>_<facing>` meshes cut away by facing (manifest cutaway.walls). A rock pillar's
faces are `Build_<section>_pillar<h>_<run>` runs (6 m at most); their cutaway entry carries `centre`, and the client
drops a run while it stands near the player on the camera's side (cutaway.props rules), as it does the wall rocks.
The rocks set into a pillar carry the pillar's outward direction (out of the rock), the perimeter's carry the
cave's (out of the room).

LEDGES (a section's `ledges`): each is a terrace, flat at `height` metres (a wavy ellipse like a room, or a polygon,
clipped to the cave and its pools), reached by straight ramps that climb from the floor at (x0, y0) toward (x1, y1),
planar from 0 m at the foot to the terrace's height where the ramp's centre line meets the terrace, flat beyond. The
walk floor (`Walk_`), the EWCG half cells (heightEncoding) and the served tiles (ESCG-v2 codes) all take their height
from ledge_heights(), so the client's walk surface and the server's climb agree. Every drop (a terrace's or a ramp's
edge above the floor) gets a rock face, `Build_<section>_ledge<i>`, styled and sectioned like the walls but never cut
away, and closes the half cells within LEDGE_CLEAR of it: the floor below and the terrace above meet only on a ramp,
and a terrace stands higher than the 1 m climb. Props without a `height` and wall rocks stand on the ledge under them.
"""
from __future__ import annotations
import argparse
from array import array
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw
from shapely import constrained_delaunay_triangles
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parents[3]
TOOLKIT = CHECKOUT/'eloria-assets/maps/nymara-regions/_toolkit'
sys.path.insert(0,str(TOOLKIT))
from amberwood import gltf as G, mesh as M, materials as MAT, textures as T

SOURCE = HERE/'content/underground.json'
# The map's frame, from the source: server tile (x, y) is world (x, h, CELLS - y).
CELLS = json.loads(SOURCE.read_text(encoding='utf-8'))['map']['cells']
# Floor and pool UVs keep the phase they had in the 240-tile frame, so a cave the map grew around keeps its texture
# placement exactly (world z moved by CELLS - 240).
UV_FRAME = 240


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+"\n",encoding='utf-8',newline='\n')


# Lamps among the kit pieces: colour, energy, range, height of the flame (metres, before the placement's scale).
KIT_LIGHTS={'jade_lantern_pole':([1,.74,.42],1.6,13,2.3),'jade_lantern_shrine':([.55,1,.72],1.3,10,1.6),
            'incense_brazier':([1,.58,.28],2.0,11,1.4),
            'iron_lantern':([1,.70,.40],1.6,12,2.1),'amber_lantern':([1,.72,.42],1.5,11,2.2),
            'candle_stake':([1,.66,.34],.9,7,1.35),'wisp_lantern':([.56,.82,1],1.2,10,1.9)}

# The theme table (see the module docstring). Cenote values are the Cenote Deeps' as built on 2026-10-20.
THEMES = {
    'cenote': {
        'shape': 'lobes', 'floor': 'verdant_wet_limestone', 'rock': 'verdant_limestone_cliff',
        'bed': 'verdant_mossy_stone', 'bank': 'verdant_wet_limestone', 'wallHeight': 4.2, 'margin': 1.0,
        'spacing': 4.0,
        'wallRocks': (('mossy_crag_1',2.0),('mossy_boulder_2',1.3),('mossy_crag_2',2.2),('mossy_boulder_1',1.0),
                      ('mossy_boulder_3',1.2),('mossy_boulder_2',1.3)),
        'rockPalette': None, 'lampColour': None, 'glow': ([.42,1,.72],1.0,8,1.0),
        # wet limestone gravel, greened by the moss; the dark cliff texture lifted toward the crags' cream
        'surfaces': {'floor': {'texture': 'coastal_gravel', 'tint': [.58,.66,.54]}, 'rockLift': [2.1,2.0,1.75],
                     'water': None},
        'minimap': {'floor': (66,80,62), 'edge': (118,128,98), 'water': (44,122,112)},
    },
    # A worked mine: grey veined crags with warm ore along the walls, packed earth underfoot (Lantern Mine).
    'mine': {
        'shape': 'chisel', 'floor': 'packed_earth', 'rock': 'cliff_rock', 'bed': 'cliff_rock', 'bank': 'cliff_rock',
        'wallHeight': 4.6, 'margin': 1.0, 'spacing': 3.4,
        'wallRocks': (('veined_crag_1',1.9),('veined_boulder_3',1.2),('veined_crag_2',2.1),('veined_boulder_1',1.0),
                      ('veined_crag_4',2.2),('veined_boulder_5',1.3)),
        'rockPalette': {'stone': '#77736c', 'mineral': '#e0a64c'}, 'lampColour': None,
        'glow': ([1,.72,.40],1.0,8,1.0),
        'surfaces': {'floor': {'texture': 'packed_earth', 'tint': [.66,.60,.52]}, 'rockLift': [1.55,1.5,1.42],
                     'water': {'deep': [.03,.07,.08], 'clear': [.10,.17,.17], 'glow': [.02,.02,.01]}},
        'minimap': {'floor': (78,72,62), 'edge': (128,116,96), 'water': (52,78,84)},
    },
    # The same kit deeper down: darker stone, copper ore, a colder floor (Pinebrow Deep Workings).
    'deep_mine': {
        'shape': 'chisel', 'floor': 'packed_earth', 'rock': 'cliff_rock', 'bed': 'cliff_rock', 'bank': 'cliff_rock',
        'wallHeight': 4.8, 'margin': 1.0, 'spacing': 3.2,
        'wallRocks': (('veined_crag_2',2.1),('veined_boulder_5',1.3),('veined_crag_4',2.2),('veined_boulder_3',1.2),
                      ('veined_crag_1',1.9),('veined_boulder_1',1.0)),
        'rockPalette': {'stone': '#56534f', 'mineral': '#c9733a'}, 'lampColour': None,
        'glow': ([1,.62,.34],1.0,8,1.0),
        'surfaces': {'floor': {'texture': 'packed_earth', 'tint': [.50,.47,.44]}, 'rockLift': [1.3,1.27,1.24],
                     'water': {'deep': [.02,.05,.06], 'clear': [.07,.12,.13], 'glow': [.01,.015,.01]}},
        'minimap': {'floor': (62,59,56), 'edge': (110,100,88), 'water': (40,62,70)},
    },
    # A barrow: cut-stone chambers walled with drystone and moor boulders, flagstones underfoot (Boarsend).
    'barrow': {
        'shape': 'boxes', 'floor': 'ashlar', 'rock': 'grey_drystone', 'bed': 'grey_moor_granite',
        'bank': 'grey_moor_granite', 'wallHeight': 3.2, 'margin': 1.0, 'spacing': 3.2,
        'wallRocks': ({'asset': 'drystone_dyke', 'proud': .6, 'align': True},('coastal_boulders_1',2.0),
                      {'asset': 'drystone_dyke', 'proud': .6, 'align': True},('moor_stone_3',1.0),
                      ('coastal_boulders_3',1.9),{'asset': 'drystone_dyke', 'proud': .6, 'align': True}),
        'rockPalette': None, 'lampColour': None, 'glow': ([.56,.82,1],1.0,8,1.0),
        'surfaces': {'floor': {'texture': 'flagstone', 'tint': [.60,.62,.60]}, 'rockLift': [1.45,1.45,1.45],
                     'water': {'deep': [.02,.04,.05], 'clear': [.06,.11,.13], 'glow': [.0,.01,.02]}},
        'minimap': {'floor': (72,72,68), 'edge': (124,124,112), 'water': (40,60,70)},
    },
    # A warren: earthen burrows lined with roots, stumps and mossy stones; daylight through burrow holes.
    'warren': {
        'shape': 'lobes', 'floor': 'packed_earth', 'rock': 'packed_earth', 'bed': 'packed_earth',
        'bank': 'packed_earth', 'wallHeight': 3.0, 'margin': .6, 'spacing': 2.5,
        'wallRocks': (('mossy_boulder_3',1.2),{'asset': 'hollow_log', 'proud': .7, 'align': True},('mossy_stump_1',.8),
                      ('mossy_boulder_2',1.3),('bog_oak_stump',1.0),('mossy_boulder_1',1.0)),
        'rockPalette': None, 'lampColour': None, 'glow': ([1,.78,.5],.9,7,1.0),
        'surfaces': {'floor': {'texture': 'tilled_soil', 'tint': [.62,.52,.40]}, 'rockLift': [1.0,.9,.78],
                     'water': {'deep': [.04,.05,.03], 'clear': [.12,.13,.07], 'glow': [.01,.01,.0]}},
        'minimap': {'floor': (86,72,52), 'edge': (150,128,92), 'water': (60,70,44)},
    },
    # A geode: one vast amethyst-lined hall with bubble chambers in violet lamp light (the Amethyst Geode).
    'geode': {
        'shape': 'lobes', 'floor': 'amethyst_barrens_dust', 'rock': 'amethyst_storm_rock',
        'bed': 'amethyst_crystal_field', 'bank': 'amethyst_storm_rock', 'wallHeight': 4.8, 'margin': 1.0,
        'spacing': 2.8,
        'wallRocks': (('veined_crag_1',1.9),('veined_boulder_2',1.3),('veined_crag_2',2.1),('veined_boulder_4',1.0),
                      ('veined_crag_4',2.2),('crystal_vent_2',1.3)),
        'rockPalette': None, 'lampColour': [.74,.52,1], 'glow': ([.70,.45,1],1.2,9,1.0),
        'surfaces': {'floor': {'texture': 'coastal_gravel', 'tint': [.50,.45,.58]}, 'rockLift': [1.05,.95,1.2],
                     'water': {'deep': [.07,.03,.13], 'clear': [.22,.10,.36], 'glow': [.04,.01,.07]}},
        'minimap': {'floor': (66,52,82), 'edge': (150,116,178), 'water': (90,60,140)},
    },
    # --- wave 3 themes ---
    # Ice caves: glacier blocks, ice shards and snow-capped rock in cold blue lamp light over packed snow; the only
    # theme with walkable ledges (the Rimewater Ice Caves' `ledges`).
    'ice': {
        'shape': 'lobes', 'floor': 'snow_pack', 'rock': 'glacier_ice', 'bed': 'glacier_ice', 'bank': 'snow_pack',
        'wallHeight': 5.2, 'margin': 1.0, 'spacing': 3.2,
        'wallRocks': (('glacier_block',2.2),('snowcap_boulder_1',2.0),('ice_shards',1.4),('snowy_boulder_2',1.6),
                      ('glacier_block',2.2),('ice_shards_2',.8)),
        'rockPalette': None, 'lampColour': [.62,.82,1], 'glow': ([.55,.85,1],1.1,9,1.0),
        'surfaces': {'floor': {'texture': 'beach_sand', 'tint': [.80,.87,.94]}, 'rockLift': [1.12,1.18,1.28],
                     'water': {'deep': [.05,.12,.18], 'clear': [.42,.62,.74], 'glow': [.04,.07,.10]}},
        'minimap': {'floor': (116,140,156), 'edge': (190,222,238), 'water': (120,190,220)},
    },
    # Catacombs: a cross of cut-stone halls under a serpent temple, walled with serpent friezes, stelae and pillars,
    # temple flagstones underfoot, candle and brazier light with a jade glow.
    'catacomb': {
        'shape': 'boxes', 'floor': 'verdant_terrace_stone', 'rock': 'verdant_limestone_cliff',
        'bed': 'verdant_mossy_stone', 'bank': 'verdant_terrace_stone', 'wallHeight': 3.6, 'margin': 1.0,
        'spacing': 3.0,
        'wallRocks': ({'asset': 'serpent_frieze', 'proud': .5, 'align': True},('serpent_obelisk',1.1),
                      {'asset': 'serpent_frieze', 'proud': .5, 'align': True},('serpent_pillar',1.2),
                      {'asset': 'serpent_frieze', 'proud': .5, 'align': True},('serpent_rubble',1.6)),
        'rockPalette': None, 'lampColour': None, 'glow': ([.55,1,.72],1.0,8,1.0),
        'surfaces': {'floor': {'texture': 'flagstone', 'tint': [.60,.64,.54]}, 'rockLift': [1.35,1.45,1.3],
                     'water': {'deep': [.02,.06,.04], 'clear': [.10,.20,.14], 'glow': [.01,.03,.02]}},
        'minimap': {'floor': (84,78,60), 'edge': (170,160,120), 'water': (50,90,70)},
    },
    # Vaults: square marble halls lined with arcades, lit cool white by obelisk lamps and daylight on mirrors.
    'vault': {
        'shape': 'boxes', 'floor': 'veined_marble', 'rock': 'pale_ashlar', 'bed': 'veined_marble',
        'bank': 'pale_ashlar', 'wallHeight': 4.6, 'margin': 1.0, 'spacing': 4.4,
        'wallRocks': ({'asset': 'colonnade_arch', 'proud': .55, 'align': True},),
        'rockPalette': None, 'lampColour': None, 'glow': ([.70,.86,1],1.2,9,1.0),
        'surfaces': {'floor': {'texture': 'flagstone', 'tint': [.68,.70,.78]}, 'rockLift': [1.4,1.42,1.5],
                     'water': {'deep': [.03,.08,.16], 'clear': [.35,.55,.80], 'glow': [.04,.08,.14]}},
        'minimap': {'floor': (74,76,92), 'edge': (160,166,196), 'water': (96,150,190)},
    },
}

# The toolkit texture each shell material needs (seeds as materials.py / the first builder used them).
TEXTURE_RECIPES = {
    'ashlar': lambda: T.ashlar(512,seed=53), 'packed_earth': lambda: T.packed_earth(512,seed=223),
    'rubble_stone': lambda: T.rubble_stone(512,seed=61), 'cliff_rock': lambda: T.cliff_rock(512,seed=67),
    'verdant_mossy_stone': lambda: T.verdant_mossy_stone(512,seed=617),
    'verdant_wet_limestone': lambda: T.verdant_wet_limestone(512,seed=619),
    'verdant_limestone_cliff': lambda: T.verdant_limestone_cliff(512,seed=631),
    'water_cenote': lambda: T.water_surface(512,seed=683,tone='cenote'),
    'grey_drystone': lambda: T.grey_drystone(512,seed=643), 'grey_moor_granite': lambda: T.grey_moor_granite(512,seed=619),
    'amethyst_barrens_dust': lambda: T.amethyst_barrens_dust(512,seed=501),
    'amethyst_storm_rock': lambda: T.amethyst_storm_rock(512,seed=523),
    'amethyst_crystal_field': lambda: T.amethyst_crystal_field(512,seed=509),
    # wave 3
    'snow_pack': lambda: T.snow_pack(512,seed=401), 'glacier_ice': lambda: T.glacier_ice(512,seed=409),
    'verdant_terrace_stone': lambda: T.verdant_terrace_stone(512,seed=613),
    'veined_marble': lambda: T.veined_marble(512,seed=421), 'pale_ashlar': lambda: T.pale_ashlar(512,seed=431),
}
# wave 3: the vaults' obelisk lamps shine cool white (colour, energy, range, flame height as KIT_LIGHTS)
KIT_LIGHTS['obelisk_lamp']=([.86,.92,1],1.4,11,3.0)


def theme_of(section):
    return THEMES[section['style']]


def shafts_of(section):
    """The section's daylight shafts [[x, y, r], ...] (a legacy single `shaft` is one)."""
    if 'shafts' in section: return [list(s) for s in section['shafts']]
    return [list(section['shaft'])] if 'shaft' in section else []


def wall_rocks(theme):
    """The theme's wall rocks as dicts {asset, proud, align}."""
    return [rock if isinstance(rock,dict) else {'asset':rock[0],'proud':rock[1]} for rock in theme['wallRocks']]


def outline(section):
    rooms=[]
    shape=theme_of(section)['shape']
    for index,(x,y,rx,ry) in enumerate(section['rooms']):
        if shape=='boxes':
            rooms.append(box(x-rx,y-ry,x+rx,y+ry).buffer(-1).buffer(1))
        elif shape=='lobes':
            # Water-worn limestone: lower, broader lobes than the mine's chisel marks.
            points=[]
            for i in range(96):
                angle=i*math.tau/96
                waviness=(1+.07*math.sin(angle*4+index*1.7)+.045*math.cos(angle*7+index*.6)
                          +.02*math.sin(angle*13+index*2.3))
                points.append((x+rx*waviness*math.cos(angle),y+ry*waviness*math.sin(angle)))
            rooms.append(Polygon(points))
        else:
            points=[]
            for i in range(64):
                angle=i*math.tau/64
                waviness=1+.045*math.sin(angle*5+index*.8)+.025*math.cos(angle*9+index)
                points.append((x+rx*waviness*math.cos(angle),y+ry*waviness*math.sin(angle)))
            rooms.append(Polygon(points))
    # A link may wind through waypoints: [a, b, width, [[x, y], ...]].
    passages = [LineString([section['rooms'][link[0]][:2],*(link[3] if len(link)>3 else []),
                            section['rooms'][link[1]][:2]]).buffer(link[2]/2)
                for link in section['links']]
    result=unary_union(rooms+passages)
    if shape=='lobes':
        result=result.buffer(1.2).buffer(-1.2)  # round the joints where tunnels meet chambers
    if result.geom_type!='Polygon':
        raise SystemExit(f'{section.get("id","?")}: rooms and links must make one connected cave')
    return result


def wall_rings(poly):
    """The outline's wall rings as (ring, pillar): the outer wall first, then each rock pillar a loop leaves."""
    return [(poly.exterior,False)]+[(ring,True) for ring in poly.interiors]


def into_rock(ring,pillar,dx,dy,length):
    """The unit normal (tile units) from the floor into the rock across an edge of `ring` running (dx, dy)."""
    if pillar:  # the rock is inside the ring
        return (-dy/length,dx/length) if ring.is_ccw else (dy/length,-dx/length)
    return (dy/length,-dx/length) if ring.is_ccw else (-dy/length,dx/length)


def wavy_ellipse(x,y,rx,ry,phase=0.):
    return Polygon([(x+rx*(1+.06*math.sin(a*3+phase)+.03*math.cos(a*7+phase))*math.cos(a),
                     y+ry*(1+.06*math.sin(a*3+phase)+.03*math.cos(a*7+phase))*math.sin(a))
                    for a in (i*math.tau/72 for i in range(72))])


def pools(section):
    """The section's standing water: wavy ellipses [x, y, rx, ry], reaching under the walls they touch."""
    shapes=[wavy_ellipse(*pool[:4],phase=index*1.3) for index,pool in enumerate(section.get('pools',[]))]
    if not shapes: return None
    return unary_union(shapes).intersection(outline(section).buffer(2.0))


# Half cells closer than this (metres) to a ledge's drop are closed (see LEDGES in the module docstring).
LEDGE_CLEAR=.45
_LEDGES={}


def _polygonal(geometry):
    """The polygon parts of a shapely result (an intersection may leave lines and points), slivers dropped."""
    parts=[g for g in getattr(geometry,'geoms',[geometry]) if g.geom_type in ('Polygon','MultiPolygon')]
    parts=[p for g in parts for p in getattr(g,'geoms',[g]) if p.area>1e-4]
    return unary_union(parts) if parts else Polygon()


def ledge_parts(section):
    """A section's ledges as (pieces, raised, drops, edges): pieces [(polygon, ledge index, height, ramp)] are
    disjoint, ramp None for a flat piece or (x0, y0, ux, uy, edge) for a slope standing height * along / edge; raised
    is their union; drops the (Multi)LineString where raised ground meets the floor (walls, ramp feet and the edges
    pieces share excluded); edges the same drops as [(LineString, piece number)], each on the piece it bounds."""
    key=section['id']+json.dumps(section.get('ledges',[]),sort_keys=True)+json.dumps(section['rooms'])
    if key in _LEDGES: return _LEDGES[key]
    shape=outline(section); water=pools(section)
    room=shape if water is None else shape.difference(water)
    pieces=[]; feet=[]
    for index,ledge in enumerate(section.get('ledges',[])):
        height=float(ledge['height'])
        terrace=Polygon(ledge['polygon']) if 'polygon' in ledge else wavy_ellipse(*ledge['terrace'],phase=index*.9)
        terrace=_polygonal(terrace.intersection(room))
        pieces.append((terrace,index,height,None))
        for x0,y0,x1,y1,width in ledge.get('ramps',[]):
            length=math.hypot(x1-x0,y1-y0); ux,uy=(x1-x0)/length,(y1-y0)/length; nx,ny=-uy,ux
            centre=LineString([(x0,y0),(x1,y1)])
            inside=centre.intersection(terrace)
            if inside.is_empty or terrace.contains(Point(x0,y0)):
                raise SystemExit(f'{section["id"]}: ledge {index} ramp {[x0,y0,x1,y1]} must climb from the floor into its terrace')
            edge=min(centre.project(Point(c)) for g in getattr(inside,'geoms',[inside]) for c in g.coords)
            span=4*(length+width)
            def band(a,b):
                return Polygon([(x0+ux*a+nx*span,y0+uy*a+ny*span),(x0+ux*b+nx*span,y0+uy*b+ny*span),
                                (x0+ux*b-nx*span,y0+uy*b-ny*span),(x0+ux*a-nx*span,y0+uy*a-ny*span)])
            rect=centre.buffer(width/2,cap_style='flat').intersection(room).difference(terrace)
            pieces.append((_polygonal(rect.intersection(band(-span,edge))),index,height,(x0,y0,ux,uy,edge)))
            flat=_polygonal(rect.intersection(band(edge,span)))
            if not flat.is_empty: pieces.append((flat,index,height,None))
            feet.append(LineString([(x0+nx*width/2,y0+ny*width/2),(x0-nx*width/2,y0-ny*width/2)]))
    raised=unary_union([p for p,*_ in pieces])
    if abs(raised.area-sum(p.area for p,*_ in pieces))>.01:
        raise SystemExit(f'{section["id"]}: ledges and ramps overlap')
    # Each piece's own boundary, less what it shares with another piece (their overlay can differ by a hair, so a
    # shared edge is judged within 0.1 mm), the cave's walls and the ramps' feet: so every drop knows its piece.
    walls=unary_union([shape.exterior,*shape.interiors]).buffer(.05)
    feet=unary_union(feet).buffer(.05) if feet else None
    edges=[]
    for k,(polygon,*_) in enumerate(pieces):
        line=polygon.boundary.difference(walls)
        others=[p for j,(p,*_) in enumerate(pieces) if j!=k]
        if others: line=line.difference(unary_union(others).buffer(1e-4))
        if feet is not None: line=line.difference(feet)
        edges+=[(part,k) for part in getattr(line,'geoms',[line]) if part.geom_type=='LineString' and part.length>1e-3]
    drops=unary_union([line for line,_ in edges]) if edges else LineString()
    _LEDGES[key]=(pieces,raised,drops,edges)
    return _LEDGES[key]


def piece_height(height,ramp,x,y):
    """The walk height (metres) of one ledge piece at points x, y."""
    x=np.asarray(x,dtype=float); y=np.asarray(y,dtype=float)
    if ramp is None: return np.full(np.broadcast(x,y).shape,height)
    x0,y0,ux,uy,edge=ramp
    return height*np.clip(((x-x0)*ux+(y-y0)*uy)/edge,0,1)


def ledge_heights(section,x,y):
    """The walk height (metres) at points x, y (tile units) of a section: its ledges' terraces and ramps, else 0."""
    from shapely import intersects_xy
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    heights=np.zeros(x.shape)
    if not section.get('ledges'): return heights
    for polygon,_,height,ramp in ledge_parts(section)[0]:
        inside=intersects_xy(polygon,x,y)
        heights[inside]=piece_height(height,ramp,x[inside],y[inside])
    return heights


def dressing(section):
    """The section's reused scenery, as placements in tile units: the source's props, then rocks along every wall.

    Each is {asset, x, y, height, yaw, scale, block, wall}: `block` is the radius (tiles) it takes from the walk
    grid; `wall` marks a rock set into the rock face, whose `outward` (world X/Y/Z) the client's cutaway judges it by:
    near the player on a wall facing the camera it drops out (the manifest's cutaway `props`). A perimeter rock's
    outward points out of the cave, a pillar rock's out of its pillar.
    """
    theme=theme_of(section)
    items=[]
    ledged=bool(section.get('ledges'))  # props and wall rocks stand on the ledge under them
    for prop in section.get('props',[]):
        x,y=prop['at']
        ground=round(float(ledge_heights(section,x,y)),3) if ledged else 0
        items.append({'asset':prop['asset'],'x':x,'y':y,'height':prop.get('height',ground),'yaw':prop.get('yaw',0),
                      'scale':prop.get('scale',1),'block':prop.get('block',0),'wall':False,
                      **({'palette':prop['palette']} if 'palette' in prop else {}),
                      **({'light':True} if prop.get('light') else {})})
    keep_out=[(p['at'][0],p['at'][1],p['clearWall']) for p in section.get('props',[]) if p.get('clearWall')]
    if section.get('nodeClearance'):
        # harvest nodes against a wall stand in front of the low rock face, not inside a wall rock
        keep_out+=[(nx+.5,ny+.5,section['nodeClearance']) for _,_,nx,ny in section['nodes']]
    rocks=wall_rocks(theme)
    step=section.get('wallRockSpacing',theme['spacing'])
    k0=0
    for ring,pillar in wall_rings(outline(section)):
        count=int(ring.length//step)
        for j in range(count):
            k=k0+j
            d=j*step+(k*7919%10)*.08
            p=ring.interpolate(d); q=ring.interpolate(d+.5)
            dx,dy=q.x-p.x,q.y-p.y; length=max(.01,math.hypot(dx,dy))
            nx,ny=into_rock(ring,pillar,dx,dy,length)
            rock=rocks[(k*5+k//3)%len(rocks)]
            proud=rock['proud']
            scale=.85+(k*37%30)/100
            # Set the rock into the face so about a third of it stands proud of the wall.
            x,y=p.x+nx*proud*scale*.45,p.y+ny*proud*scale*.45
            if any(math.hypot(x-cx,y-cy)<r for cx,cy,r in keep_out): continue
            yaw=round(math.degrees(math.atan2(dy,dx)))%360 if rock.get('align') else k*137%360
            outward=[round(-nx,3),0,round(ny,3)] if pillar else [round(nx,3),0,round(-ny,3)]
            sunk=round(-.3+float(ledge_heights(section,p.x-nx*.3,p.y-ny*.3)),3) if ledged else -.3
            items.append({'asset':rock['asset'],'x':round(x,2),'y':round(y,2),'height':sunk,'yaw':yaw,
                          'scale':round(scale,2),'block':0,'wall':True,'outward':outward,
                          **({'palette':theme['rockPalette']} if theme.get('rockPalette') else {})})
        k0+=count
    return items


def section_bounds(section):
    """A section's id, name and world-space X/Z bounds (metres, 2 m clear of its walls) for the client."""
    x0,y0,x1,y1=outline(section).buffer(2).bounds
    return {'id':section['id'],'name':section['name'],
            'bounds':{'min':[round(x0,2),round(CELLS-y1,2)],'max':[round(x1,2),round(CELLS-y0,2)]}}


def flat_triangles(polygon,height):
    """Upward-facing triangles covering `polygon` (holes respected) at `height`, as world-space vertex triples."""
    result=[]
    for tri in constrained_delaunay_triangles(polygon).geoms:
        p=list(tri.exterior.coords)[:3]
        a,b,c=[world(x,y,height) for x,y in p]
        if np.cross(np.subtract(b,a),np.subtract(c,a))[1]<0:
            a,b,c=c,b,a
        result.append((a,b,c))
    return result


FACE_OUT=dict(east=[1,0,0],west=[-1,0,0],south=[0,0,-1],north=[0,0,1])
CENOTE_WATER=-.45  # the pools' surface, below the walk floor at 0
CENOTE_BED=-1.9
ROOF=8.5
PILLAR_RUN=6.0  # metres: the longest run of a pillar's face judged as one cutaway piece


def facing_name(nx,ny):
    return ('east' if nx>0 else 'west') if abs(nx)>abs(ny) else ('south' if ny>0 else 'north')


def facing_quad(corners,toward,material):
    """A quad wound so its normal points along the world-space vector `toward`."""
    normal=np.cross(np.subtract(corners[1],corners[0]),np.subtract(corners[2],corners[0]))
    return M.quad(corners if np.dot(normal,toward)>=0 else corners[::-1],material=material)


def surface_triangles(polygon,heights):
    """Upward-facing triangles covering `polygon` with each corner at heights(x, y) metres (a planar ledge piece)."""
    result=[]
    for tri in constrained_delaunay_triangles(polygon).geoms:
        p=list(tri.exterior.coords)[:3]
        a,b,c=[world(x,y,float(heights(x,y))) for x,y in p]
        if np.cross(np.subtract(b,a),np.subtract(c,a))[1]<0:
            a,b,c=c,b,a
        result.append((a,b,c))
    return result


def ledge_geometry(section,add):
    """A section's ledges: their terraces and ramps on the walk floor, and a rock face down every drop."""
    theme=theme_of(section); ident=section['id']
    pieces,_,_,edges=ledge_parts(section)
    for polygon,_,height,ramp in pieces:
        for a,b,c in surface_triangles(polygon,lambda x,y,h=height,r=ramp:piece_height(h,r,x,y)):
            add(M.quad([a,b,c,c],material=theme['floor']).drop_degenerate(),f'Walk_{ident}')
    run=0.
    for line,k in edges:
        polygon,index,height,ramp=pieces[k]
        coords=list(line.coords)
        for a,b in zip(coords,coords[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy)
            if length<1e-3: continue
            nx,ny=-dy/length,dx/length  # out of the piece, toward the floor below (flipped if it points in)
            mx,my=(a[0]+b[0])/2,(a[1]+b[1])/2
            if polygon.contains(Point(mx+nx*.01,my+ny*.01)): nx,ny=-nx,-ny
            ha,hb=(float(piece_height(height,ramp,*point)) for point in (a,b))
            if max(ha,hb)<.02: continue
            corners=[world(*a,-.15),world(*b,-.15),world(*b,hb),world(*a,ha)]
            face=facing_quad(corners,(nx,0,-ny),theme['rock'])
            uvs=[[run*.3,0],[(run+length)*.3,0],[(run+length)*.3,hb*.3],[run*.3,ha*.3]]
            face.uvs=np.array(uvs if np.allclose(face.positions[0],corners[0]) else uvs[::-1])
            add(face,f'Build_{ident}_ledge{index}')
            run+=length


def section_geometry(section,add,lights,chambers,wall_faces,pillars):
    """A section's shell in its theme: floor and rock faces (perimeter and pillars), sunk pools with banks, shafts."""
    theme=theme_of(section)
    ident=section['id']; poly=outline(section); water=pools(section)
    floor=poly.difference(water) if water is not None else poly
    if section.get('ledges'):
        floor=floor.difference(ledge_parts(section)[1])
    for a,b,c in flat_triangles(floor,0):
        add(M.quad([a,b,c,c],material=theme['floor']).drop_degenerate(),f'Walk_{ident}')
    if section.get('ledges'):
        ledge_geometry(section,add)
    for a,b,c in flat_triangles(poly,ROOF):
        add(M.quad([c,b,a,a],material=theme['rock']).drop_degenerate(),f'Roof_{ident}')
    # A low, ragged rock face: the kit rocks set into it (dressing()) are the walls' skyline.
    height=theme['wallHeight']
    boundary=list(poly.exterior.coords); count=len(boundary)-1
    ccw=poly.exterior.is_ccw; perimeter=0.
    def top(i): return height+.5*math.sin(i%count*.11)+.25*math.sin(i%count*.37)
    for i,(a,b) in enumerate(zip(boundary,boundary[1:])):
        dx,dy=b[0]-a[0],b[1]-a[1]; length=max(.01,math.hypot(dx,dy))
        nx,ny=(dy/length,-dx/length) if ccw else (-dy/length,dx/length)
        ring=[world(*a,-.15),world(*b,-.15),world(*b,top(i+1)),world(*a,top(i))]
        facing=facing_name(nx,ny)
        bucket=f'Build_{ident}_{facing}'
        wall_faces[bucket]=FACE_OUT[facing]
        face=M.quad(ring,material=theme['rock'])
        face.uvs=np.array([[perimeter*.3,0],[(perimeter+length)*.3,0],
                           [(perimeter+length)*.3,top(i+1)*.3],[perimeter*.3,top(i)*.3]])
        add(face,bucket)
        perimeter+=length
    # Rock pillars (the holes a looping layout leaves): the same face, facing the floor round each pillar, in runs
    # of at most PILLAR_RUN metres the cutaway judges like wall rocks (near the player, on the camera's side).
    for h,(ring,_) in enumerate(wall_rings(poly)[1:]):
        coords=list(ring.coords); count=len(coords)-1
        run=0; run_length=0.; run_facing=None; perimeter=0.
        for i,(a,b) in enumerate(zip(coords,coords[1:])):
            dx,dy=b[0]-a[0],b[1]-a[1]; length=max(.01,math.hypot(dx,dy))
            nx,ny=into_rock(ring,True,dx,dy,length)
            facing=facing_name(-nx,-ny)
            if run_facing is not None and (facing!=run_facing or run_length>=PILLAR_RUN):
                run+=1; run_length=0.
            run_facing=facing
            bucket=f'Build_{ident}_pillar{h}_{run}'
            entry=pillars.setdefault(bucket,{'normal':np.zeros(2),'points':[]})
            entry['normal']+=np.array([-nx,-ny])*length
            entry['points'].append(((a[0]+b[0])/2,(a[1]+b[1])/2,length))
            def lift(j): return height+.5*math.sin(j%count*.11+h)+.25*math.sin(j%count*.37+h)
            corners=[world(*a,-.15),world(*b,-.15),world(*b,lift(i+1)),world(*a,lift(i))]
            face=facing_quad(corners,(-nx,0,ny),theme['rock'])
            uvs=[[perimeter*.3,0],[(perimeter+length)*.3,0],[(perimeter+length)*.3,lift(i+1)*.3],[perimeter*.3,lift(i)*.3]]
            # facing_quad may reverse the corners: the UVs follow them
            face.uvs=np.array(uvs if np.allclose(face.positions[0],corners[0]) else uvs[::-1])
            add(face,bucket)
            run_length+=length; perimeter+=length
    if water is not None:
        for part in getattr(water,'geoms',[water]):
            for a,b,c in flat_triangles(part,CENOTE_WATER):
                add(M.quad([a,b,c,c],material='water_cenote').drop_degenerate(),f'Water_{ident}')
            for a,b,c in flat_triangles(part,CENOTE_BED):
                add(M.quad([a,b,c,c],material=theme['bed']).drop_degenerate(),f'Pool_{ident}')
            # The bank drops from the floor's edge to the bed, facing the water.
            edge=list(part.exterior.coords); inner_ccw=part.exterior.is_ccw; run=0.
            for a,b in zip(edge,edge[1:]):
                dx,dy=b[0]-a[0],b[1]-a[1]; length=max(.01,math.hypot(dx,dy))
                ix,iy=(-dy/length,dx/length) if inner_ccw else (dy/length,-dx/length)
                bank=facing_quad([world(*a,.02),world(*b,.02),world(*b,CENOTE_BED),world(*a,CENOTE_BED)],
                                 (ix,0,-iy),theme['bank'])
                bank.uvs=np.array([[run*.3,0],[(run+length)*.3,0],[(run+length)*.3,.6],[run*.3,.6]])
                add(bank,f'Bank_{ident}')
                run+=length
    for index,(sx,sy,radius) in enumerate(shafts_of(section)):
        # Daylight through an opening in the roof: an open, faintly lit column.
        def rim(angle,r,h): return world(sx+r*math.cos(angle),sy+r*math.sin(angle),h)
        for i in range(28):
            a0,a1=i*math.tau/28,(i+1)*math.tau/28
            add(M.quad([rim(a0,radius,.1),rim(a1,radius,.1),rim(a1,radius*.72,15),rim(a0,radius*.72,15)],
                       material='light_shaft'),f'Shaft_{ident}')
        lights.append({'id':f'{ident}-daylight'+(f'-{index}' if index else ''),'position':list(world(sx,sy,9)),
                       'color':[.92,.96,.84],'energyHint':4.0 if radius>=5 else round(1.2+radius*.55,2),
                       'rangeHint':26 if radius>=5 else round(10+radius*3)})
    for index,(x,y,rx,ry) in enumerate(section['rooms']):
        chambers.append({'id':f'{ident}-{index}','section':ident,'position':list(world(x,y)),
                         'radius':min(rx,ry),'name':section['name']})
    lamp=0
    for item in dressing(section):
        light=KIT_LIGHTS.get(item['asset'])
        if light is not None and theme.get('lampColour'):
            light=(theme['lampColour'],*light[1:])
        if light is None and item.get('light'):
            light=theme['glow']  # a glowing growth
        if light is None: continue
        colour,energy,reach,flame=light
        lift=item['height'] if section.get('ledges') else 0  # a lamp on a ledge shines from it
        lights.append({'id':f'{ident}-lamp-{lamp}','position':list(world(item['x'],item['y'],flame*item['scale']+lift)),
                       'color':colour,'energyHint':energy,'rangeHint':reach})
        lamp+=1
    # The way out: a dark passage mouth; the arch over it is kit scenery.
    x,y=section['exit']
    if 'exitFacing' in section:
        # set into the wall the exit faces ([dx, dy] from the exit tile into its passage), not toward -y
        fx,fy=section['exitFacing']; cx,cy=x+fx*1.2,y+fy*1.2
        add(M.quad([world(cx+fy*1.7,cy-fx*1.7,.01),world(cx-fy*1.7,cy+fx*1.7,.01),world(cx-fy*1.7,cy+fx*1.7,3.3),
                    world(cx+fy*1.7,cy-fx*1.7,3.3)],material='exit_dark'),f'Props_{ident}')
    else:
        add(M.quad([world(x-1.7,y-1.2,.01),world(x+1.7,y-1.2,.01),world(x+1.7,y-1.2,3.3),world(x-1.7,y-1.2,3.3)],
                   material='exit_dark'),f'Props_{ident}')


def world(x,y,height=0):
    return (x,height,CELLS-y)


def build_geometry(design, textures):
    builder=G.GltfBuilder(generator='Eloria Landfall underground builder; shared original interior kit')
    root=G.Node('Landfall_Underground')
    parts=defaultdict(list)
    lights=[]; chambers=[]; hidden=[]; wall_faces={}; pillars={}
    def add(piece,bucket): parts[(bucket,piece.material)].append(piece)
    for section in design['sections']:
        section_geometry(section,add,lights,chambers,wall_faces,pillars)
    used={m for _,m in parts}
    MAT.register_gltf_materials(builder,textures,only=used-{'exit_dark','light_shaft'})
    builder.add_material(G.Material('exit_dark',base_color=(.008,.009,.011,1),double_sided=True))
    if 'light_shaft' in used:
        builder.add_material(G.Material('light_shaft',base_color=(.95,.97,.82,.10),emissive=(.45,.48,.38),
                                        alpha_mode='BLEND',double_sided=True))
    all_meshes=[]; collision_nodes=[];walls=[]
    for (bucket,material),pieces in sorted(parts.items()):
        piece=M.merge(pieces,material=material).drop_degenerate().sanitise_normals()
        if bucket.startswith(('Walk_','Roof_','Water_','Pool_')):
            piece.uvs=(piece.positions[:,[0,2]]-[0,CELLS-UV_FRAME])*.22
        name=f'{bucket}_{material}'
        builder.add_mesh(name,piece,with_tangents=True); root.add(G.Node(name,mesh=name))
        all_meshes.append(piece)
        if bucket.startswith('Roof'): hidden.append(name)
        # A ledge's drop is styled and sectioned as a wall (by its name) but stands: no cutaway, no wall collision.
        if bucket.startswith('Build') and not bucket.rsplit('_',1)[-1].startswith('ledge'):
            # Each wall names its cave, so the client keeps another cave's walls hidden (`sectioned`).
            section=max((s['id'] for s in design['sections'] if bucket.startswith(f"Build_{s['id']}_")),key=len)
            collision_nodes.append(name)
            if bucket in pillars:
                entry=pillars[bucket]; n=entry['normal']/max(1e-9,np.linalg.norm(entry['normal']))
                total=sum(w for _,_,w in entry['points'])
                cx=sum(px*w for px,_,w in entry['points'])/total; cy=sum(py*w for _,py,w in entry['points'])/total
                walls.append({'node':name,'outward':[round(float(n[0]),3),0,round(float(-n[1]),3)],'section':section,
                              'centre':[round(cx,2),round(CELLS-cy,2)]})
            else:
                walls.append({'node':name,'outward':wall_faces[bucket],'section':section})
    builder.add_node(root)
    bounds=M.merge(all_meshes).bounds()
    return builder,lights,chambers,hidden,collision_nodes,bounds,walls


def masks(design,strict=True):
    """The walk grid: half-metre cells (`half`) and served tiles (`coarse`). `strict` refuses a large cut-off pocket;
    a layout preview passes False to see it."""
    from shapely import contains_xy
    cells=design['map']['cells']; size=cells*2
    x,y=np.meshgrid((np.arange(size)+.5)*.5,(np.arange(size)+.5)*.5)
    half=np.zeros((size,size),dtype=bool)
    for section in design['sections']:
        theme=theme_of(section); shape=outline(section)
        # Cell corners must fit on the authored floor. Blackspace has no geometry at all.
        half |= contains_xy(shape.buffer(-.4),x,y)
        # The wall rocks stand proud of the face (every ring, pillars too): keep the theme's margin clear.
        half &= ~(contains_xy(shape,x,y) & ~contains_xy(shape.buffer(-theme['margin']),x,y))
        water=pools(section)
        if water is not None:
            half &= ~contains_xy(water.buffer(.4),x,y)
        for item in dressing(section):
            if item['block']>0:
                half &= ~((x-item['x'])**2+(y-item['y'])**2<item['block']**2)
        for _,_,nx,ny in section['nodes']:
            half[ny*2:ny*2+2,nx*2:nx*2+2]=False
        if section.get('ledges'):
            # A ledge's drops: no half cell within LEDGE_CLEAR of one, so below and above meet only on a ramp.
            from shapely import dwithin, points
            x0,y0,x1,y1=(int(v) for v in shape.buffer(1).bounds)
            window=(slice(y0*2,(y1+1)*2),slice(x0*2,(x1+1)*2))
            half[window]&=~dwithin(ledge_parts(section)[2],points(x[window],y[window]),LEDGE_CLEAR)
    coarse=half.reshape(cells,2,cells,2).all(axis=(1,3))
    # Props, pools and pillars can pinch off a scrap of floor, and publication refuses a stranded pocket: close
    # whatever the arrival cannot reach (the server's four-way steps on the coarse grid); refuse a large one.
    from scipy import ndimage
    for section in design['sections']:
        x0,y0,x1,y1=(int(v) for v in outline(section).buffer(1).bounds)
        window=coarse[y0:y1+1,x0:x1+1]
        labels,_=ndimage.label(window)
        ax,ay=section['arrival']
        stranded=window&(labels!=labels[ay-y0,ax-x0])
        if stranded.sum()>12 and strict:
            ys,xs=np.nonzero(stranded)
            raise SystemExit(f'{section["id"]}: {int(stranded.sum())} floor tiles are cut off from the arrival, '
                             f'e.g. ({xs[0]+x0},{ys[0]+y0}): a prop, pool or pillar closes a passage')
        if stranded.sum()<=12:
            half[y0*2:(y1+1)*2,x0*2:(x1+1)*2]&=~np.repeat(np.repeat(stranded,2,0),2,1)
    coarse=half.reshape(cells,2,cells,2).all(axis=(1,3))
    return half,coarse


def walk_codes(design,half,coarse):
    """The walk grid's heights: EWCG bytes per half cell (heightEncoding: -0.1 m + 0.1 m a unit) and ESCG-v2 codes per
    served tile (50 mm a code above -100 m). A flat cave stands at 0 m (byte 1, code 2000); a section with `ledges`
    takes its terraces' and ramps' heights from ledge_heights(), at each cell's and each tile's centre."""
    walk=half.astype(np.uint8)
    codes=np.where(coarse,2000,0).astype(np.uint16)
    for section in design['sections']:
        if not section.get('ledges'): continue
        x0,y0,x1,y1=(int(v) for v in outline(section).buffer(1).bounds)
        ys,xs=np.mgrid[y0*2:(y1+1)*2,x0*2:(x1+1)*2]
        cell=ledge_heights(section,(xs+.5)*.5,(ys+.5)*.5)
        window=(slice(y0*2,(y1+1)*2),slice(x0*2,(x1+1)*2))
        walk[window]=np.where(half[window],np.round((cell+.1)/.1),0).astype(np.uint8)
        ys,xs=np.mgrid[y0:y1+1,x0:x1+1]
        tile=ledge_heights(section,xs+.5,ys+.5)
        window=(slice(y0,y1+1),slice(x0,x1+1))
        codes[window]=np.where(coarse[window],2000+np.round(tile/.05),0).astype(np.uint16)
    return walk,codes


def surfaces(design):
    """Each section's runtime surface styling (underground-scenery.json `surfaces`, by section id)."""
    return {s['id']:{'theme':s['style'],**theme_of(s)['surfaces']} for s in design['sections']}


def build(server):
    sys.path.insert(0,str(server)); from eloria import served_grid as SG
    design=json.loads(SOURCE.read_text(encoding='utf-8')); ident=design['map']['id']; cells=design['map']['cells']
    if cells!=CELLS: raise SystemExit('the source changed while building')
    ids=[s['id'] for s in design['sections']]
    if len(set(ids))!=len(ids): raise SystemExit('section ids must be unique')
    out=HERE.parent/ident/'client';out.mkdir(parents=True,exist_ok=True)
    needed={theme_of(s)[k] for s in design['sections'] for k in ('floor','rock','bed','bank')}|{'water_cenote'}
    textures={name:TEXTURE_RECIPES[name]() for name in sorted(needed)}
    builder,lights,chambers,hidden,collision_nodes,bounds,walls=build_geometry(design,textures)
    builder.write_glb(str(out/'world.glb'))
    half,coarse=masks(design)
    walk,codes=walk_codes(design,half,coarse)
    ew=struct.pack('<4sHHII',b'EWCG',2,0,cells*2,cells*2)+walk.tobytes()
    (out/'collision.bin').write_bytes(ew)
    grid=SG.ServedGrid(cells,cells,array('H',codes.ravel()))
    (out/'served-grid.escg.gz').write_bytes(SG.encode_file(grid))
    coordinate={'metresPerTile':1.,'serverOrigin':[0,cells],'serverCells':[cells,cells],
                'origin':[0,0,0],'walkingHeight':0.,'invertServerY':True,'serverStorageVersion':1,'serverTileMin':[0,0]}
    nodes=[];exits=[];spawns=[]
    for i,section in enumerate(design['sections']):
        spawns.append({'id':section['id'],'name':section['name'],'section':section['id'],'default':i==0,
                       'position':list(world(*section['arrival'],.05)),'serverTile':section['arrival'],'rotationDegrees':180})
        for oid,res,x,y in section['nodes']:
            ground=float(ledge_heights(section,x+.5,y+.5)) if section.get('ledges') else 0
            nodes.append({'id':f'{section["id"]}-{oid}','objectId':oid,'resource':res,'serverTile':[x,y],
                          'position':list(world(x+.5,y+.5,ground)),'section':section['id'],'authority':'server'})
        exits.append({'id':f'{section["id"]}-exit','objectId':section['entrance']['object'],
                      'role':'portal','position':list(world(*section['exit'])),'serverTile':section['exit'],
                      'destinationMap':section['entrance']['map'],'destinationTile':section['entrance']['returnTile'],
                      'label':f'Leave {section["name"]}'})
    pixels=3  # minimap pixels per tile
    manifest={'schemaVersion':'1.1.0','assetVersion':'1.0.0',
              'asset':{'id':ident,'name':design['map']['name'],'glb':'world.glb','units':'meters',
                       'coordinateSystem':{'handedness':'right','upAxis':'Y','northAxis':'-Z'},'origin':[0,0,0],
                       'bounds':{'min':bounds[0].tolist(),'max':bounds[1].tolist()},'interiorClass':'insides','parentRegion':'landfall','serverCells':cells},
              'coordinateTransform':coordinate,'serverCells':[cells,cells],'spawnPoints':spawns,
              'chambers':chambers,'harvestables':nodes,'portals':exits,'interactives':exits,
              'navigation':{'surfaceNodePrefixes':['Walk_'],'authority':'server','defaultSpawn':spawns[0]['id']},
              'collision':{'binary':'collision.bin','format':'EWCG-v2','width':cells*2,'height':cells*2,
                           'cellMetres':.5,'originMetres':[0,cells],'heightEncoding':{'origin':-.1,'step':.1},'gridAlignment':'tile-centres-v1',
                           'sha256':sha(out/'collision.bin'),'nodeNames':collision_nodes,
                           'servedGrid':{'binary':'served-grid.escg.gz','format':'ESCG-v2','sha256':sha(out/'served-grid.escg.gz'),
                                         'unitMetres':.05,'climbMetres':1.,'originMetres':-100.,'width':cells,'height':cells}},
              'environment':{'profile':'cave-interior','backgroundColor':'#000000',
                             'ambient':{'color':'#acb3bf','energy':.55,'skyContribution':0},
                             'sun':{'energy':.25,'color':'#ffe4c0','shadows':False},
                             'fog':{'enabled':False},'tonemap':{'mode':'filmic','exposure':1.1}},
              'lighting':{'markers':lights},
              # A wall cuts away only while the camera looks nearly straight through it (owner 2026-10-20: the
              # convention's 0.2 took too much of a cave away); wall rocks fade instead of hiding.
              'cutaway':{'hideNodes':hidden,'walls':walls,'facingThreshold':.6,
                         # Rocks set into a wall drop out within 12 m of the player while their wall faces the
                         # camera within 60 degrees (owner 2026-10-20: between hiding whole sides and fading only
                         # the one in front). A rock pillar's face runs (walls with a `centre`) follow the same rule.
                         'props':{'facingThreshold':.5,'radiusMetres':12},
                         'reason':'The shared interior roof and camera-facing wall cutaway convention'},
              # One cave at a time: the client draws only the section the player stands in (SecretSections).
              'sectioned':True,'sections':[section_bounds(s) for s in design['sections']],
              'minimap':{'file':'minimap.webp','image':'minimap.webp','northUp':True,'worldMin':[0,0],'worldMax':[cells,cells],
                         'imageSize':[cells*pixels,cells*pixels]},
              'provenance':{'source':'_continent_v2/content/underground.json','sourceSha256':sha(SOURCE),
                            'builder':'_continent_v2/build_underground.py','builderSha256':sha(__file__)}}
    write_json(out/'world.json',manifest)
    # Images go to the content-addressed pool, as every published map's do (eloria-assets/tools/shared_images.py).
    sys.path.insert(0,str(CHECKOUT/'eloria-assets/tools'))
    import shared_images
    moved=shared_images.externalise(out/'world.glb',dry_run=False)
    shared_images.record_manifest(out/'world.glb',moved['uris'],dry_run=False)
    image=Image.new('RGB',(cells*pixels,cells*pixels),'black');draw=ImageDraw.Draw(image)
    for section in design['sections']:
        poly=outline(section); colours=theme_of(section)['minimap']
        draw.polygon([(x*pixels,y*pixels) for x,y in poly.exterior.coords],fill=colours['floor'],outline=colours['edge'],width=2)
        for ring in poly.interiors:
            draw.polygon([(x*pixels,y*pixels) for x,y in ring.coords],fill=(0,0,0),outline=colours['edge'],width=2)
        water=pools(section)
        for part in getattr(water,'geoms',[water]) if water is not None else []:
            clipped=part.intersection(poly)
            for piece in getattr(clipped,'geoms',[clipped]):
                if piece.geom_type=='Polygon' and not piece.is_empty:
                    draw.polygon([(x*pixels,y*pixels) for x,y in piece.exterior.coords],fill=colours['water'])
        if section.get('ledges'):
            # terraces and ramps a shade lighter, their drops in the edge colour
            _,raised,drops,_=ledge_parts(section)
            for part in getattr(raised,'geoms',[raised]):
                draw.polygon([(x*pixels,y*pixels) for x,y in part.exterior.coords],fill=tuple(min(255,v+22) for v in colours['floor']))
            for line in getattr(drops,'geoms',[drops]):
                if line.geom_type=='LineString':
                    draw.line([(x*pixels,y*pixels) for x,y in line.coords],fill=colours['edge'],width=2)
        for _,res,x,y in section['nodes']: draw.ellipse((x*pixels-2,y*pixels-2,x*pixels+2,y*pixels+2),fill=(158,179,162))
        x,y=section['exit'];draw.rectangle((x*pixels-4,y*pixels-4,x*pixels+4,y*pixels+4),fill=(232,185,94))
    image.save(out/'minimap.webp',lossless=True)
    # The procedural entrance models stay retired: each door's art is reused Meshy scenery (objects.json),
    # which this builder no longer writes; retarget_underground.py keeps those records' tiles and labels.
    registry=json.loads((CHECKOUT/'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))
    if registry['maps'].get(ident,{}).get('coordinateTransform')!=coordinate:
        raise SystemExit(f'registry.json has no {ident} row with this frame; publish it first')
    print(json.dumps({'map':ident,'sections':len(design['sections']),'nodes':len(nodes),'monsters':sum(len(s['spawns']) for s in design['sections']),
                      'walkableTiles':int(coarse.sum()),'glbBytes':(out/'world.glb').stat().st_size,'imagesShared':moved['moved']}))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--server',type=Path,required=True)
    ap.add_argument('--owner-approved',metavar='NOTE',
                    help="the owner's approval for this rebuild (the generator was retired on 2026-10-16)")
    args=ap.parse_args()
    if not args.owner_approved:
        raise RuntimeError('build_underground.py is retired: procedural models and generators were archived on 2026-10-16. '
                           'See docs/procedural-model-archive.md. It rebuilds only with --owner-approved "<who, when, what>" '
                           '(the owner re-enabled it on 2026-10-20 for the Cenote Deeps and the Landfall underground '
                           'programme). No outputs were written.')
    build(args.server.resolve())
