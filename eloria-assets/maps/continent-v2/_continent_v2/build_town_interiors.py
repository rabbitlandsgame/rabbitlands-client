#!/usr/bin/env python3
"""Build the Landfall Town interiors (`landfall_town`): the room shells of the town's shops, tavern, homes and keep.

OWNER-APPROVED GENERATOR. Procedural generators were retired on 2026-10-16. The owner approved this builder on
2026-10-27 (chat: "Implement your plan": the Landfall town interiors plan, whose room shells are drawn by a builder);
it runs only with --owner-approved "<who, when, what>" and draws SHELLS ONLY: floors, straight walls with a top cap
and trim bands, partition walls with flat doorway openings, window quads, wall and floor decals, stair art and the lit
street doors. Furniture and dressing are reviewed Meshy kit scenery placed from dressing() by the scenery packager
(tools/prepare_underground_scenery.py), as in the caves.

It is a separate entrypoint beside build_underground.py, which it imports and never changes: the cave package's
provenance pins that file's hash. Both maps share the cave builder's conventions (walk grid, served grid, collision,
cutaway, sectioned sections, provenance) so the interior publication handles both.

SOURCE: content/landfall_town.json, read and checked by town_source.py (its docstring has the format). The map's
frame is the source's `map.cells` (324): server tile (x, y) is world (x, h, cells - y) (`world()`), and the source's
compass is the map's: south is -y, the side the default camera stands on (world +Z), so a south wall is the one the
cutaway drops first. A wall stands on a row of tiles: room edges lie on tile-row centres (x.5).

THE THEME TABLE (THEMES): a section's `style` sets its wall height, partition height (the fallback, should fading
partitions not read: lower it), wall and partition thickness, the walk grid's wall margin, the street door's width
and height, the doorway lintel, the window sill and head, the trim bands and the stair material; the default floor
and wall surfaces when a section names none.

SURFACES (the single table to swap art in): every floor, wall, trim and decal surface id maps to its texture repeat
and its placeholder. The builder takes the codex texture under godot-client/src/world/look/textures/interior/
(<id>.png, <id with hyphens>.png, or .jpg/.webp) when the art role has published it, else the placeholder (a class
texture under godot-client/src/world/look/textures/ or a flat colour). Every floor carries a texture (a flat colour is
an 8 x 8 image) because the client tints a floor's own texture (surfaces() says 'authored'). provenance.surfaces says
which file or placeholder each package surface came from.

WHAT IS DRAWN, PER SECTION (mesh node `<bucket>_<material>`):
  Walk_<s>        each room's floor in its surface (a stairwell cut out)
  Roof_<s>        the ceiling at wall height (always hidden by the cutaway)
  Build_<s>_<side>   the outer walls facing `side`: face, top cap (wall_cap, mitred at the corners), trim bands, and
                  on them the windows (the art role's leaded glazing, the theme's `window` picture, or a flat pane
                  until it is published; the timber frame, sill, centre mullion and transom drawn over it), wall decals and the lit street doors (soft daylight, the theme's door size);
                  cut away by facing (cutaway.walls, threshold 0.35)
  Part_<s>_<k>    partition walls (full height): a solid piece between rooms with both faces in their rooms' surfaces,
                  cap, trims, the doorway openings with timber jamb linings, casings on both faces, soffits and
                  lintels. Never cut by facing: each is its own small node; cutaway.partitions lists them (node,
                  section, rooms, centre, along, normal) and the runtime hides a partition standing between the camera
                  and the player, with every prop whose `cutawayWall` names it (props against a partition, dressing())
  Build_<s>_stair<k>   a flight of stairs up to an opening (stairs_up passage ends) or to a shut plank door
                  (sealedStairs): lit treads with nosings, shaded risers, timber stringers, handrails on newels and
                  balusters where floor lies beside it; set against an outer wall and cut away with it
  Stair_<s>_<k>   a stairwell down (stairs_down passage ends): treads and sides darkening with depth (SHADES, never
                  black), a dark passage under a lintel at its foot and a handrail on both sides; never cut
  Door_<s>        at each street door, on the floor: a timber threshold and the daylight spilling in (a generated soft
                  picture, PICTURES); not cut, so a door reads with its wall gone
  Decal_<s>       floor decals (rugs, inlays)
Surface textures repeat (the glTF sampler 0); decal textures, wall and floor alike, clamp to their edge
(DECAL_SAMPLER), as single pictures.
Props that name a `wall` carry that wall's outward direction (dressing()), so the cutaway drops them with it.

WALK GRID: half-metre cells are open on the floor at least the theme's margin from an outer wall or a partition's
centre line, outside every stair's footprint (+0.4 m) and every prop's block (a circle) or blockBox (a rectangle
turned by yaw); a served tile is open when its four cells are. A doorway centred on a tile centre and 2.4 m wide
leaves one open tile through its wall. The builder closes scraps of STRANDED_MAX tiles or fewer cut off from a
section's arrival and refuses a larger pocket; it refuses a doorway that leaves no open tile, a door exit, arrival or
passage end that is blocked or not reached, an NPC post that is not open with all eight neighbours open and reached
or that stands on a way in or out, and an interactive with no reached approach.

MANIFEST (world.json): spawnPoints (each section's primary arrival, facing into the room), chambers (one per room,
named from roomNames; radius one metre short of the room's longer half extent, so the music sync's padded square
covers the whole room), spaces (each room's exact rectangle, by name, for the music zones: classified by the name
alone, so a name without a music keyword is covered by its chamber only), portals and interactives (each door's
exit, labelled with its exitLabel; each passage end, with its drawn stair's `modelOffset` from the end tile,
stair_offset(); the source's interior interactives), environment and camera from
the source, lighting.markers (the source's lights and lamp props), cutaway, sectioned + sections, interiorClass
"insides", parentRegion "landfall", provenance (source, this builder and the helpers it imports, each with its sha256;
the surfaces' files; the approval note).

    python eloria-assets/maps/continent-v2/_continent_v2/build_town_interiors.py --server ../rabbitlands-server \\
        --owner-approved "<who, when, what>"
"""
from __future__ import annotations

import argparse
from array import array
from collections import defaultdict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw
from shapely import constrained_delaunay_triangles, contains_xy
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_underground as B  # noqa: E402  the cave builder's helpers; never edited (its hash pins the caves)
import town_source as TS  # noqa: E402

G, M = B.G, B.M
CHECKOUT = B.CHECKOUT
SOURCE = HERE/'content/landfall_town.json'
TEXTURES = CHECKOUT/'godot-client/src/world/look/textures'
INTERIOR_TEXTURES = TEXTURES/'interior'
REGISTRY = CHECKOUT/'godot-client/data/maps/registry.json'


def _source_cells(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))['map']['cells']
    except (OSError, KeyError, ValueError):
        return 324


# The map's frame, from the source: server tile (x, y) is world (x, h, CELLS - y). build() sets the frame of the source
# it builds while it runs (a scratch source may have its own), and restores this one.
CELLS = _source_cells(SOURCE)
_FRAME = {'cells': CELLS}


def world(x, y, height=0):
    return (x, height, _FRAME['cells']-y)


def world_dir(direction):
    """A tile direction (dx, dy) as a world vector [x, 0, z] (tile +y is world -Z)."""
    return [round(float(direction[0]), 3), 0, round(float(-direction[1]), 3)]


sha = B.sha
write_json = B.write_json

# --- the theme table ---------------------------------------------------------------------------------------------

_BASE = {'floor': 'oak_planks', 'walls': 'lime_plaster', 'wallHeight': 3.4, 'partitionHeight': 3.4, 'margin': .55,
         'wallThickness': .3, 'partitionThickness': .24, 'doorWidth': 2.0, 'doorHeight': 2.6, 'doorwayTop': 2.5,
         'windowSill': 1.0, 'windowHead': 2.3, 'trim': ((0., .16), (3.08, 3.3)), 'stairs': 'oak_planks',
         'stairRail': 'timber_band', 'window': 'window_leaded'}
THEMES = {
    'tavern': {**_BASE},
    'shop': {**_BASE},
    'magic': {**_BASE, 'floor': 'cobalt_tile'},
    'smithy': {**_BASE, 'floor': 'packed_earth', 'walls': 'soot_brick', 'wallHeight': 3.6, 'partitionHeight': 3.6,
               'trim': ((0., .16), (3.28, 3.5))},
    'house': {**_BASE, 'wallHeight': 3.2, 'partitionHeight': 3.2, 'doorWidth': 1.6, 'doorHeight': 2.4,
              'doorwayTop': 2.3, 'windowHead': 2.2, 'trim': ((0., .14), (2.9, 3.1))},
    # the keep's street door is the size of its painted facade door (about 2.4 x 3.2 m), not a gateway
    'castle': {**_BASE, 'floor': 'limestone_flagstone', 'walls': 'ashlar_wall', 'wallHeight': 4.6,
               'partitionHeight': 4.6, 'wallThickness': .5, 'partitionThickness': .4, 'doorWidth': 2.4,
               'doorHeight': 3.2, 'doorwayTop': 3.3, 'windowSill': 1.4, 'windowHead': 3.6,
               'trim': ((0., .24), (4.16, 4.44)), 'stairs': 'limestone_flagstone', 'stairRail': 'ashlar_wall',
               'window': 'window_leaded_tall'},
}
assert set(THEMES) == set(TS.STYLES)

# --- surfaces: the one table to swap art in ----------------------------------------------------------------------

# surface id -> repeat (metres one texture tile covers), placeholder (a class texture file under TEXTURES, or an RGB
# flat colour) and roughness. A codex file under INTERIOR_TEXTURES replaces the placeholder (surface_file()).
SURFACES = {
    'oak_planks': {'repeat': 2.4, 'placeholder': (138, 94, 56), 'roughness': .88},
    'limestone_flagstone': {'repeat': 3.2, 'placeholder': 'flagstone-paving.png', 'roughness': .92},
    'cobalt_tile': {'repeat': 2.0, 'placeholder': (66, 96, 156), 'roughness': .6},
    'packed_earth': {'repeat': 3.0, 'placeholder': 'packed-earth-path.png', 'roughness': 1.},
    'lime_plaster': {'repeat': 3.0, 'placeholder': (228, 218, 194), 'roughness': .95},
    'soot_brick': {'repeat': 2.4, 'placeholder': (86, 64, 54), 'roughness': .95},
    'ashlar_wall': {'repeat': 3.0, 'placeholder': (186, 176, 154), 'roughness': .95},
    'timber_band': {'repeat': 2.0, 'placeholder': (96, 62, 38), 'roughness': .9},
}
# a decal's placeholder colour, by id prefix (the codex art replaces it)
DECAL_PLACEHOLDERS = (('banner_', (128, 44, 42)), ('rug_', (142, 56, 42)), ('map_', (216, 198, 152)),
                      ('star_', (38, 46, 82)), ('botanical_', (224, 214, 186)), ('painting_', (58, 52, 44)),
                      ('book_', (196, 170, 128)))
# A decal is one picture, not a tile: its texture samples CLAMP_TO_EDGE (33071), so a banner's or a rug's far edge
# never bleeds in along the near one at low mip levels. The surfaces keep the builder's REPEAT sampler 0 (10497).
# The other single pictures (the window glazing, WINDOW_ART; the door's daylight spill, PICTURES) clamp too.
DECAL_SAMPLER = {'magFilter': 9729, 'minFilter': 9987, 'wrapS': 33071, 'wrapT': 33071}
MAX_TEXTURE = 1024
# Shaded copies of a surface (`<surface><suffix>`): the same texture under a darker base colour, for stair risers and
# the deeper treads and sides of a stairwell, so a flight reads as steps (lit treads, shadowed risers) and a stairwell
# as a stair going down into dimness rather than a black pit.
SHADES = {'_shade': .58, '_dusk': .34}
# The window glazing (the art role's codex pictures under INTERIOR_TEXTURES, 2026-10-27: leaded quarries over hazy,
# day-neutral daylight, mid-value and never near white): the theme's `window` names one; it fills each window quad as
# one picture (stretched to the quad, clamped), matte and never emissive, so a window reads as glass by day and is no
# lamp at night; the builder's frame, sill, centre mullion and transom stand over it. Until the picture is published a
# window is a flat pane (window_glass).
WINDOW_ART = ('window_leaded', 'window_leaded_tall')
WINDOW_MATERIAL = dict(base_color=(.92, .92, .9, 1), roughness=.45)
# the shell's own flat materials
FLAT = {
    'wall_cap': dict(base_color=(.21, .17, .14, 1), roughness=.95),
    # the street door's daylight: warm and soft, well short of white (the keep's 3 x 3.6 m door blew out, 2026-10-27)
    'door_daylight': dict(base_color=(.74, .66, .5, 1), emissive=(.3, .25, .17), roughness=.9),
    'window_glass': dict(base_color=(.5, .54, .55, 1), emissive=(.05, .045, .035), roughness=.25),
    'stair_dark': dict(base_color=(.008, .009, .011, 1), double_sided=True),
    'iron': dict(base_color=(.11, .11, .12, 1), metallic=.6, roughness=.55),
}
# generated pictures (an RGBA image the builder draws, not art): the daylight spilling in at a street door, fading
# from the threshold into the room and to its sides
PICTURES = ('door_spill',)
assert set(TS.FLOORS) | set(TS.WALLS) <= set(SURFACES)

# minimap colours
MINIMAP = {'oak_planks': (124, 88, 56), 'limestone_flagstone': (136, 130, 118), 'cobalt_tile': (66, 92, 146),
           'packed_earth': (108, 90, 68), 'wall': (232, 220, 196), 'partition': (196, 182, 156),
           'stairs': (120, 196, 232), 'passage': (120, 196, 232)}

# Stair art: width across, depth from the wall, steps and the rise of each (metres).
STAIRS = {'stairs_up': {'width': 1.8, 'depth': 2.6, 'steps': 8, 'rise': .2},
          'stairs_down': {'width': 1.8, 'depth': 2.0, 'steps': 6, 'rise': .25}}
# a tread's nosing (metres down its front edge) and a handrail's height above the treads' nosing line
NOSING = .04
RAIL_HEIGHT = .9
# the top of the low dark passage at a stairwell's foot (metres; the well's far face is wall above it)
WELL_PASSAGE = -.85
# Scraps of floor at most this many tiles cut off from a section's arrival are closed; a larger pocket is refused.
STRANDED_MAX = 6
# the width of a doorway's casing boards (metres)
CASING = .12
# a prop marked `light` (a glowing piece) shines warm: colour, energy, range, height above its foot (before scale)
PROP_GLOW = ([1, .72, .42], 1.0, 7, 1.0)
CUTAWAY_THRESHOLD = .35


def theme_of(section):
    return THEMES[section['style']]


def surface_file(surface):
    """The codex texture published for a surface or decal id (INTERIOR_TEXTURES), or None."""
    for stem in dict.fromkeys((surface, surface.replace('_', '-'))):
        for suffix in ('.png', '.jpg', '.jpeg', '.webp'):
            path = INTERIOR_TEXTURES/f'{stem}{suffix}'
            if path.is_file():
                return path
    return None


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, 'PNG', optimize=False)
    return buffer.getvalue()


def _relative(path):
    try:
        return Path(path).resolve().relative_to(CHECKOUT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _has_alpha(image):
    return image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info)


def surface_image(surface, placeholder):
    """(PNG bytes, alpha, provenance) for a surface or decal: its codex texture when published (re-encoded only when
    it is not a PNG or is larger than MAX_TEXTURE), else the placeholder (a class texture at 512, or an 8 x 8 flat
    colour)."""
    path = surface_file(surface)
    if path is not None:
        data = path.read_bytes()
        image = Image.open(io.BytesIO(data))
        alpha = _has_alpha(image)
        record = {'file': _relative(path), 'sha256': hashlib.sha256(data).hexdigest()}
        if path.suffix.lower() == '.png' and max(image.size) <= MAX_TEXTURE:
            return data, alpha, record
        image = image.convert('RGBA' if alpha else 'RGB')
        if max(image.size) > MAX_TEXTURE:
            scale = MAX_TEXTURE/max(image.size)
            image = image.resize((max(1, round(image.size[0]*scale)), max(1, round(image.size[1]*scale))),
                                 Image.LANCZOS)
            record['resized'] = list(image.size)
        return _png(image), alpha, record
    if isinstance(placeholder, str):
        source = TEXTURES/placeholder
        image = Image.open(source).convert('RGB').resize((512, 512), Image.LANCZOS)
        return _png(image), False, {'placeholder': _relative(source), 'sha256': sha(source)}
    return _png(Image.new('RGB', (8, 8), tuple(placeholder))), False, \
        {'placeholder': '#%02x%02x%02x' % tuple(placeholder)}


def decal_placeholder(image_id):
    return next(colour for prefix, colour in DECAL_PLACEHOLDERS if image_id.startswith(prefix))


def shaded(name):
    """(surface, factor) for a shaded surface name `<surface><suffix>` (SHADES), else None."""
    for suffix, factor in SHADES.items():
        if name.endswith(suffix) and name[:-len(suffix)] in SURFACES:
            return name[:-len(suffix)], factor
    return None


def window_art(theme=None):
    """The material a theme's windows take: its `window` glazing picture (WINDOW_ART) once the art role has published
    it under INTERIOR_TEXTURES, else the flat pane 'window_glass'."""
    art = (theme or _BASE)['window']
    return art if surface_file(art) is not None else 'window_glass'


def door_spill_image(size=64):
    """The daylight on the floor inside a street door, as an RGBA picture: u across the door, v from the threshold
    (top row) into the room; warm, fading with distance and toward both sides (never a hard pale rectangle)."""
    v = np.linspace(0, 1, size)[:, None]
    u = np.linspace(-1, 1, size)[None, :]
    side = np.clip((1-np.abs(u))/.45, 0, 1)
    alpha = .34*(1-v)**1.6*(side*side*(3-2*side))
    pixels = np.zeros((size, size, 4), dtype=np.uint8)
    pixels[..., :3] = (255, 228, 178)
    pixels[..., 3] = np.round(alpha*255).astype(np.uint8)
    return _png(Image.fromarray(pixels, 'RGBA'))


def register_materials(builder, used):
    """Every material the shell uses: surfaces (and their SHADES) and decals with their images, the painted window,
    the generated pictures, the flat ones. Returns the surfaces' provenance {id: {file | placeholder, sha256?}}."""
    record = {}
    def surface(name):
        if name not in record:
            spec = SURFACES[name]
            data, alpha, record[name] = surface_image(name, spec['placeholder'])
            builder.add_image(name, data)
        return 'MASK' if surface_image_alpha(name) else 'OPAQUE'
    for name in sorted(used):
        if name in SURFACES:
            alpha = surface(name)
            builder.add_material(G.Material(name, roughness=SURFACES[name]['roughness'], base_color_texture=name,
                                            alpha_mode=alpha))
        elif shaded(name):
            base, factor = shaded(name)
            alpha = surface(base)
            builder.add_material(G.Material(name, roughness=SURFACES[base]['roughness'], base_color_texture=base,
                                            base_color=(factor, factor, factor, 1), alpha_mode=alpha))
        elif name.startswith('decal_'):
            image_id = name[len('decal_'):]
            data, alpha, record[name] = surface_image(image_id, decal_placeholder(image_id))
            builder.add_image(name, data)
            builder.add_material(G.Material(name, roughness=.92, base_color_texture=name,
                                            alpha_mode='MASK' if alpha else 'OPAQUE'))
        elif name in WINDOW_ART:
            data, alpha, record[name] = surface_image(name, None)
            builder.add_image(name, data)
            builder.add_material(G.Material(name, **WINDOW_MATERIAL, base_color_texture=name))
        elif name in PICTURES:
            builder.add_image(name, door_spill_image())
            builder.add_material(G.Material(name, base_color_texture=name, emissive=(.16, .13, .09),
                                            alpha_mode='BLEND', roughness=1.))
            record[name] = {'generated': 'build_town_interiors.door_spill_image'}
        elif name in FLAT:
            builder.add_material(G.Material(name, **FLAT[name]))
        else:
            raise SystemExit(f'no material {name!r} in SURFACES, SHADES, PICTURES or FLAT')
    clamp_decals(builder)
    return record


_ALPHA = {}


def surface_image_alpha(name):
    """Whether a surface's published art carries alpha (cached; a placeholder never does)."""
    if name not in _ALPHA:
        path = surface_file(name)
        if path is None:
            _ALPHA[name] = False
        else:
            with Image.open(path) as image:
                _ALPHA[name] = _has_alpha(image)
    return _ALPHA[name]


def clamp_decals(builder):
    """Give every single-picture texture (a decal's image `decal_<id>`, the painted window, the generated PICTURES)
    the DECAL_SAMPLER, added once after the builder's REPEAT sampler 0; surface textures keep sampler 0. Runs after
    every material is registered."""
    decals = {index for index, image in enumerate(builder._images)
              if image['name'].startswith('decal_') or image['name'] in (*WINDOW_ART, *PICTURES)}
    if not decals:
        return
    builder._samplers.append(dict(DECAL_SAMPLER))
    for texture in builder._textures:
        if texture['source'] in decals:
            texture['sampler'] = len(builder._samplers) - 1


# --- the source ----------------------------------------------------------------------------------------------------


def annotate(design):
    """Check the source (town_source.check) and give every section `_ends` (the passage ends in it) and `_arrival`
    (its primary arrival). Keys starting with `_` are never written back."""
    try:
        TS.check(design)
    except TS.SourceError as error:
        raise SystemExit(f'town source: {error}')
    for section in design['sections']:
        section['_ends'] = TS.passage_ends(design, section['id'])
        section['_arrival'] = TS.primary_arrival(design, section)
    return design


def load_design(path=None):
    """The source (content/landfall_town.json, or `path`), checked and annotated."""
    return annotate(TS.load(path or SOURCE))


def _annotated(section):
    if '_ends' not in section:
        raise SystemExit(f'{section.get("id", "?")}: load the source with build_town_interiors.load_design()')
    return section


def surfaces(design):
    """Each section's runtime surface styling (the scenery config's `surfaces`, by section id): the shell keeps its own
    floor textures (one per room), untinted; no rock lift, no water."""
    return {s['id']: {'theme': s['style'], 'floor': {'texture': 'authored', 'tint': [1, 1, 1]}, 'rockLift': None,
                      'water': None} for s in design['sections']}


# a prop that names a `wall` stands at most this far (tiles) from that outer wall
WALL_PROP_REACH = 2.5


def _wall_node(section, prop):
    """The cutaway node of the outer wall a `wall` prop stands against: the nearest run on that side (all of a side's
    nodes drop together); refused when the prop stands farther than WALL_PROP_REACH from any."""
    x, y = prop['at']
    def gap(run):
        (ax, ay), (bx, by) = run['a'], run['b']
        cx = min(max(x, min(ax, bx)), max(ax, bx))
        cy = min(max(y, min(ay, by)), max(ay, by))
        return math.hypot(x-cx, y-cy)
    runs = [run for run in outer_walls(section) if run['side'] == prop['wall']]
    best = min(runs, key=gap) if runs else None
    if best is None or gap(best) > WALL_PROP_REACH:
        raise SystemExit(f'{section["id"]}: {prop["asset"]} at {prop["at"]} names the {prop["wall"]} wall but stands '
                         f'against no outer wall on that side (within {WALL_PROP_REACH} tiles)')
    material = TS.wall_of(section, best['room']) or theme_of(section)['walls']
    return f'Build_{section["id"]}_{prop["wall"]}_{material}'


# A prop stands against a partition when its back is within this gap (metres) of the partition's face and it faces
# away from it (a piece's +Z, its front), or hangs on it (raised at least PARTITION_HUNG metres)
PARTITION_PROP_GAP = .35
PARTITION_HUNG = 1.0


def _partition_node(section, prop):
    """The partition node a prop stands against or hangs on (`Part_<s>_<k>_<its room's surface>`), or None: the
    client hides it with that partition (cutaway.partitions), as an outer-wall prop drops with its wall."""
    x, y = prop['at']
    angle = math.radians(prop.get('yaw', 0))
    front = (math.sin(angle), -math.cos(angle))   # a piece's +Z in tile units (tile +y is world -Z)
    if 'blockBox' in prop:
        depth = prop['blockBox'][1]
    else:
        depth = prop.get('block', 0)
    half = theme_of(section)['partitionThickness']/2
    hung = prop.get('height', 0) >= PARTITION_HUNG
    for k, part in enumerate(partitions(section)):
        (ax, ay), (dx, dy), (nx, ny) = part['a'], part['along'], part['normal']
        u = (x-ax)*dx+(y-ay)*dy
        s = (x-ax)*nx+(y-ay)*ny
        if not any(u0-.2 <= u <= u1+.2 for u0, u1 in part['solid']):
            continue
        away = (front[0]*nx+front[1]*ny)*(1 if s > 0 else -1)
        if abs(s)-half-depth <= PARTITION_PROP_GAP and (away >= .7 or (hung and abs(s)-half <= PARTITION_PROP_GAP)):
            room = part['rooms'][0] if s > 0 else part['rooms'][1]
            material = TS.wall_of(section, room) or theme_of(section)['walls']
            return f'Part_{section["id"]}_{k}_{material}'
    return None


def dressing(section):
    """The section's reused scenery, as placements in tile units: {asset, x, y, height, yaw, scale, block, blockBox?,
    wall, side?, outward?, cutawayWall?, palette?, light?}. A prop against a wall (`wall`) carries its outward direction
    (world) and its wall's cutaway node (`cutawayWall`), so the client's cutaway drops it with that wall; a prop against
    a partition (_partition_node) carries the partition's node as its `cutawayWall`, so it hides with the partition."""
    items = []
    for prop in section.get('props', []):
        x, y = prop['at']
        item = {'asset': prop['asset'], 'x': x, 'y': y, 'height': prop.get('height', 0), 'yaw': prop.get('yaw', 0),
                'scale': prop.get('scale', 1), 'block': prop.get('block', 0), 'wall': 'wall' in prop}
        if 'blockBox' in prop:
            item['blockBox'] = list(prop['blockBox'])
        if 'wall' in prop:
            item['side'] = prop['wall']
            item['outward'] = world_dir(TS.SIDE_TILE[prop['wall']])
            item['cutawayWall'] = _wall_node(section, prop)
        else:
            node = _partition_node(section, prop)
            if node is not None:
                item['cutawayWall'] = node
        if 'palette' in prop:
            item['palette'] = prop['palette']
        if prop.get('light'):
            item['light'] = True
        items.append(item)
    return items


def blocked_by(item, x, y):
    """True where a placement blocks the walk grid at points x, y (tile units): inside its blockBox (half extents
    along its own X and Z, turned by yaw) or its block radius."""
    if 'blockBox' in item:
        hx, hy = item['blockBox']
        angle = math.radians(item['yaw'])
        # a piece's +X runs along tile (cos, sin) and its +Z along tile (sin, -cos) (tile +y is world -Z)
        dx, dy = x-item['x'], y-item['y']
        along = dx*math.cos(angle)+dy*math.sin(angle)
        across = dx*math.sin(angle)-dy*math.cos(angle)
        return (np.abs(along) < hx) & (np.abs(across) < hy)
    if item['block'] > 0:
        return (x-item['x'])**2+(y-item['y'])**2 < item['block']**2
    return np.zeros(np.broadcast(x, y).shape, dtype=bool)


# --- layout: outline, outer walls, partitions, features ------------------------------------------------------------

_CACHE = {}


def _cached(kind, section, make):
    key = (kind, json.dumps([section.get('id'), section['rooms'], section['links'], section.get('style')]))
    if key not in _CACHE:
        _CACHE[key] = make()
    return _CACHE[key]


def _straight(coords):
    """A closed ring's corners with the collinear points between them dropped."""
    points = [tuple(p) for p in coords[:-1]]
    result = []
    for i, p in enumerate(points):
        a, c = points[i-1], points[(i+1) % len(points)]
        if abs((p[0]-a[0])*(c[1]-p[1])-(p[1]-a[1])*(c[0]-p[0])) > 1e-9:
            result.append(p)
    return result


def outline(section):
    """The section's floor: the union of its rooms, one polygon with sharp corners (counter-clockwise, no holes)."""
    def make():
        shape = unary_union([box(*room) for room in TS.rooms(section)])
        if shape.geom_type != 'Polygon':
            raise SystemExit(f'{section["id"]}: its rooms must make one connected floor')
        if shape.interiors:
            raise SystemExit(f'{section["id"]}: its rooms enclose blackspace (a courtyard): rooms must make a floor '
                             'without holes')
        return orient(Polygon(_straight(list(shape.exterior.coords))), 1.0)
    return _cached('outline', section, make)


def _side_of(normal):
    return next(side for side, d in TS.SIDE_TILE.items() if d == normal)


def outer_walls(section):
    """The outer walls as runs [{a, b, side, room, u0, oa, ob}]: from tile point a to b (counter-clockwise), the
    compass side the wall faces out to, the room it bounds, the run's start along the ring (metres, for texture
    continuity) and the cap's outer corners' offsets from a and b (mitred at the ring's corners)."""
    def make():
        corners = list(outline(section).exterior.coords)[:-1]
        count = len(corners)
        thickness = theme_of(section)['wallThickness']
        normals = []
        for i in range(count):
            (ax, ay), (bx, by) = corners[i], corners[(i+1) % count]
            length = math.hypot(bx-ax, by-ay)
            normals.append((round((by-ay)/length), round(-(bx-ax)/length)))  # out of the floor (counter-clockwise)
        def mitre(i):  # the cap's outer corner at ring corner i (between edges i-1 and i)
            n1, n2 = normals[i-1], normals[i]
            dot = n1[0]*n2[0]+n1[1]*n2[1]
            return ((n1[0]+n2[0])*thickness/(1+dot), (n1[1]+n2[1])*thickness/(1+dot))
        boxes = TS.rooms(section)
        runs = []
        travelled = 0.
        for i in range(count):
            a, b = corners[i], corners[(i+1) % count]
            n = normals[i]
            horizontal = n[1] != 0
            lo, hi = (min(a[0], b[0]), max(a[0], b[0])) if horizontal else (min(a[1], b[1]), max(a[1], b[1]))
            cuts = {lo, hi}
            for x0, y0, x1, y1 in boxes:
                for value in ((x0, x1) if horizontal else (y0, y1)):
                    if lo < value < hi:
                        cuts.add(value)
            cuts = sorted(cuts)
            forward = (b[0] > a[0]) if horizontal else (b[1] > a[1])
            pieces = list(zip(cuts, cuts[1:]))
            if not forward:
                pieces = [(q, p) for p, q in reversed(pieces)]
            for j, (p, q) in enumerate(pieces):
                start = (p, a[1]) if horizontal else (a[0], p)
                end = (q, a[1]) if horizontal else (a[0], q)
                mid = ((start[0]+end[0])/2-n[0]*.01, (start[1]+end[1])/2-n[1]*.01)
                room = TS.room_of(section, *mid)
                if room is None:
                    raise SystemExit(f'{section["id"]}: an outer wall at {start}-{end} bounds no room')
                oa = mitre(i) if j == 0 else (n[0]*thickness, n[1]*thickness)
                ob = mitre((i+1) % count) if j == len(pieces)-1 else (n[0]*thickness, n[1]*thickness)
                length = math.hypot(end[0]-start[0], end[1]-start[1])
                runs.append({'a': start, 'b': end, 'side': _side_of(n), 'normal': n, 'room': room, 'u0': travelled,
                             'oa': oa, 'ob': ob, 'length': length})
                travelled += length
        return runs
    return _cached('outer', section, make)


def side_segment(section, room, side):
    """A room's side as (a, b): west to east for south and north, south to north for west and east."""
    x0, y0, x1, y1 = TS.rooms(section)[room]
    return {'south': ((x0, y0), (x1, y0)), 'north': ((x0, y1), (x1, y1)),
            'west': ((x0, y0), (x0, y1)), 'east': ((x1, y0), (x1, y1))}[side]


def _on_outer(section, a, b):
    """True when the straight span a-b lies along the outline's outer wall (sampled every 5 cm)."""
    ring = outline(section).exterior
    steps = max(2, int(math.hypot(b[0]-a[0], b[1]-a[1])/.05)+1)
    return all(ring.distance(Point(a[0]+(b[0]-a[0])*t/steps, a[1]+(b[1]-a[1])*t/steps)) < 1e-6
               for t in range(steps+1))


def partitions(section):
    """The section's partition walls, one per pair of rooms sharing a wall: {rooms (i, j), a, b (its ends, tile
    points, low to high), along (unit), normal (unit, toward room i), length, openings [(o0, o1, link)] (metres from a,
    sorted), solid [(u0, u1)] (the wall pieces between them)}. A link's doorway is centred on its point, else on the
    tile centre nearest the middle of the shared wall."""
    def make():
        sid = section['id']
        count = len(section['rooms'])
        result = []
        for i in range(count):
            for j in range(i+1, count):
                wall = TS.shared_wall(section, i, j)
                if wall is None:
                    continue
                (ax, ay), (bx, by) = wall
                length = math.hypot(bx-ax, by-ay)
                along = ((bx-ax)/length, (by-ay)/length)
                normal = (-along[1], along[0])
                probe = ((ax+bx)/2+normal[0]*.01, (ay+by)/2+normal[1]*.01)
                if TS.room_of(section, *probe) != i:
                    normal = (-normal[0], -normal[1])
                openings = []
                for index, link in enumerate(section['links']):
                    if {link[0], link[1]} != {i, j}:
                        continue
                    width = link[2]
                    if len(link) == 4:
                        cx, cy = link[3][0]
                        offset = (cx-ax)*normal[0]+(cy-ay)*normal[1]
                        if abs(offset) > 1e-6:
                            raise SystemExit(f'{sid}: link {index}: its doorway point {link[3][0]} is not on the '
                                             f'wall rooms {i} and {j} share ({wall[0]}-{wall[1]})')
                        centre = (cx-ax)*along[0]+(cy-ay)*along[1]
                    else:
                        start = ax if along[0] else ay
                        centre = math.floor(start+length/2)+.5-start
                    o0, o1 = centre-width/2, centre+width/2
                    if o0 < -1e-6 or o1 > length+1e-6:
                        raise SystemExit(f'{sid}: link {index}: its doorway ({width} m) runs off the wall rooms {i} '
                                         f'and {j} share ({wall[0]}-{wall[1]})')
                    openings.append((max(0., o0), min(length, o1), index))
                openings.sort()
                for (p0, p1, k0), (q0, q1, k1) in zip(openings, openings[1:]):
                    if q0 < p1+.3:
                        raise SystemExit(f'{sid}: links {k0} and {k1} open into each other')
                solid, cursor = [], 0.
                for o0, o1, _ in openings:
                    if o0-cursor > 1e-6:
                        solid.append((cursor, o0))
                    cursor = o1
                if length-cursor > 1e-6:
                    solid.append((cursor, length))
                result.append({'rooms': (i, j), 'a': (ax, ay), 'b': (bx, by), 'along': along, 'normal': normal,
                               'length': length, 'openings': openings, 'solid': solid})
        return result
    return _cached('partitions', section, make)


def _partition_lines(section):
    """The partitions' solid pieces as centre lines (tile units), for the walk grid."""
    lines = []
    for part in partitions(section):
        (ax, ay), (dx, dy) = part['a'], part['along']
        lines += [LineString([(ax+dx*u0, ay+dy*u0), (ax+dx*u1, ay+dy*u1)]) for u0, u1 in part['solid']]
    return lines


def _shortened(section, k):
    """How much partition k's ends stop short (metres at a, at b): a partition ending against another one running
    through that point (a T) stops at its face, so the caps do not overlap."""
    parts = partitions(section)
    part = parts[k]
    ring = outline(section).exterior
    half = theme_of(section)['partitionThickness']/2
    cuts = []
    for end in (part['a'], part['b']):
        cut = 0.
        if ring.distance(Point(end)) > 1e-6:
            collinear = any(other is not part and other['along'] == part['along'] and end in (other['a'], other['b'])
                            and abs((end[0]-other['a'][0])*other['normal'][0]
                                    +(end[1]-other['a'][1])*other['normal'][1]) < 1e-9
                            for other in parts)
            crossing = any(other['along'] != part['along']
                           and LineString([other['a'], other['b']]).distance(Point(end)) < 1e-9 for other in parts)
            if crossing and not collinear:
                cut = half
        cuts.append(cut)
    return tuple(cuts)


def stairs(section):
    """Every stair the section draws: its passage ends with building art (stairs_up, stairs_down) and its sealed
    stairs, as {kind ('passage' | 'sealed'), art, centre (the end tile's centre, or a point in front of a sealed
    stair), facing (unit tile direction into the wall), distance (centre to the wall face), footprint (Polygon),
    end?}."""
    _annotated(section)
    def make():
        sid = section['id']
        ring = outline(section).exterior
        result = []
        def face_distance(cx, cy, facing):
            ray = LineString([(cx, cy), (cx+facing[0]*80, cy+facing[1]*80)])
            hit = ray.intersection(ring)
            points = [c for g in getattr(hit, 'geoms', [hit]) if not g.is_empty for c in g.coords]
            if not points:
                return None
            return min(math.hypot(px-cx, py-cy) for px, py in points)
        for end in section['_ends']:
            if end['art'] not in STAIRS:
                raise SystemExit(f'{sid}: passage {end["passage"]} end {end["end"]}: the town draws stairs_up and '
                                 f'stairs_down, not {end["art"]!r}')
            cx, cy = end['tile'][0]+.5, end['tile'][1]+.5
            if end['facing']:
                facing = tuple(end['facing'])
            else:
                facing = min(TS.SIDE_TILE.values(), key=lambda f: face_distance(cx, cy, f) or 1e9)
            distance = face_distance(cx, cy, facing)
            if distance is None:
                raise SystemExit(f'{sid}: passage {end["passage"]} end {end["end"]}: its facing meets no outer wall')
            result.append({'kind': 'passage', 'art': end['art'], 'centre': (cx, cy), 'facing': facing,
                           'distance': distance, 'end': end})
        for index, stair in enumerate(section.get('sealedStairs', [])):
            a, b = side_segment(section, stair['room'], stair['side'])
            fx, fy = a[0]+(b[0]-a[0])*stair['at'], a[1]+(b[1]-a[1])*stair['at']
            facing = TS.SIDE_TILE[stair['side']]
            distance = STAIRS['stairs_up']['depth']+1.
            result.append({'kind': 'sealed', 'art': 'stairs_up', 'centre': (fx-facing[0]*distance,
                                                                             fy-facing[1]*distance),
                           'facing': facing, 'distance': distance, 'index': index})
        lines = _partition_lines(section)
        for stair in result:
            spec = STAIRS[stair['art']]
            (cx, cy), (ux, uy), d = stair['centre'], stair['facing'], stair['distance']
            vx, vy, w = -uy, ux, spec['width']/2
            a0 = d-spec['depth']
            stair['footprint'] = Polygon([(cx+ux*a0+vx*w, cy+uy*a0+vy*w), (cx+ux*d+vx*w, cy+uy*d+vy*w),
                                          (cx+ux*d-vx*w, cy+uy*d-vy*w), (cx+ux*a0-vx*w, cy+uy*a0-vy*w)])
            where = (f'{sid}: passage {stair["end"]["passage"]} end {stair["end"]["end"]}' if stair['kind'] == 'passage'
                     else f'{sid}: sealed stair {stair["index"]}')
            if not outline(section).buffer(1e-6).covers(stair['footprint']):
                raise SystemExit(f'{where}: the stair does not fit on the floor')
            if any(stair['footprint'].buffer(-1e-6).intersects(line) for line in lines):
                raise SystemExit(f'{where}: the stair runs through a partition')
            wall_a = (cx+ux*d+vx*w, cy+uy*d+vy*w)
            wall_b = (cx+ux*d-vx*w, cy+uy*d-vy*w)
            if not _on_outer(section, wall_a, wall_b):
                raise SystemExit(f'{where}: the stair must stand against a straight outer wall')
        return result
    key = ('stairs', json.dumps([section['id'], section['rooms'], section['links'], section.get('sealedStairs', []),
                                 [[e['tile'], e['facing'], e['art']] for e in section['_ends']]]))
    if key not in _CACHE:
        _CACHE[key] = make()
    return _CACHE[key]


# --- geometry ------------------------------------------------------------------------------------------------------


def face(corners, toward, material, uvs):
    """A quad whose normal points along `toward` (world), its UVs following its corners."""
    piece = B.facing_quad(corners, toward, material)
    piece.uvs = np.array(uvs if np.allclose(piece.positions[0], corners[0]) else uvs[::-1], dtype=np.float64)
    return piece


def repeat_of(material):
    return SURFACES.get(material, {}).get('repeat', 2.)


def upright(a, b, h0, h1, toward, material, u0=0.):
    """A vertical quad over the tile points a to b from h0 to h1 metres, facing the tile direction `toward`; u runs
    along it from u0 (metres), v up it, both at the material's repeat."""
    r = repeat_of(material)
    length = math.hypot(b[0]-a[0], b[1]-a[1])
    return face([world(*a, h0), world(*b, h0), world(*b, h1), world(*a, h1)], world_dir(toward), material,
                [[u0/r, -h0/r], [(u0+length)/r, -h0/r], [(u0+length)/r, -h1/r], [u0/r, -h1/r]])


def level(points, height, material, up=True):
    """A horizontal quad over four tile points at `height`, facing up (or down), its UVs planar in world X/Z."""
    r = repeat_of(material)
    corners = [world(x, y, height) for x, y in points]
    return face(corners, (0, 1 if up else -1, 0), material, [[c[0]/r, c[2]/r] for c in corners])


def picture(corners, toward, material):
    """A quad showing one whole image (a decal): corners bottom-left, bottom-right, top-right, top-left."""
    return face(corners, toward, material, [[0, 1], [1, 1], [1, 0], [0, 0]])


def floor_triangles(polygon, height, material, up=True):
    """Triangles covering `polygon` (holes respected) at `height`, facing up (or down), as one degenerate quad each,
    UVs planar."""
    r = repeat_of(material)
    pieces = []
    for tri in constrained_delaunay_triangles(polygon).geoms:
        a, b, c = [world(x, y, height) for x, y in list(tri.exterior.coords)[:3]]
        if (np.cross(np.subtract(b, a), np.subtract(c, a))[1] < 0) == up:
            a, b, c = c, b, a
        piece = M.quad([a, b, c, c], material=material).drop_degenerate()
        piece.uvs = np.array([[p[0]/r, p[2]/r] for p in (a, b, c, c)], dtype=np.float64)
        pieces.append(piece)
    return pieces


def _offset(point, direction, amount):
    return (point[0]+direction[0]*amount, point[1]+direction[1]*amount)


def trims(add, bucket, a, b, inward, theme, u0=0., heights=None):
    """The timber trim bands (skirting, top band) along a wall face a-b, standing 3 cm proud toward `inward`."""
    for h0, h1 in heights or theme['trim']:
        p, q = _offset(a, inward, .03), _offset(b, inward, .03)
        add(upright(p, q, h0, h1, inward, 'timber_band', u0), bucket)
        add(level([a, b, q, p], h1, 'timber_band'), bucket)


def outer_wall_geometry(section, add, walls):
    theme = theme_of(section)
    sid, height = section['id'], theme['wallHeight']
    for run in outer_walls(section):
        bucket = f'Build_{sid}_{run["side"]}'
        walls[bucket] = world_dir(run['normal'])
        inward = (-run['normal'][0], -run['normal'][1])
        material = TS.wall_of(section, run['room']) or theme['walls']
        a, b = run['a'], run['b']
        add(upright(a, b, 0, height, inward, material, run['u0']), bucket)
        add(level([a, b, _offset(b, run['ob'], 1), _offset(a, run['oa'], 1)], height, 'wall_cap'), bucket)
        trims(add, bucket, a, b, inward, theme, run['u0'])


def partition_geometry(section, add, notes):
    theme = theme_of(section)
    sid = section['id']
    height, half, top = theme['partitionHeight'], theme['partitionThickness']/2, theme['doorwayTop']
    for k, part in enumerate(partitions(section)):
        bucket = f'Part_{sid}_{k}'
        (ax, ay), (dx, dy), (nx, ny) = part['a'], part['along'], part['normal']
        i, j = part['rooms']
        sides = ((1, (nx, ny), TS.wall_of(section, i) or theme['walls']),
                 (-1, (-nx, -ny), TS.wall_of(section, j) or theme['walls']))
        cut_a, cut_b = _shortened(section, k)
        def P(u, s):
            return (ax+dx*u+nx*s, ay+dy*u+ny*s)
        jambs = {o for o0, o1, _ in part['openings'] for o in (o0, o1)}
        for u0, u1 in part['solid']:
            v0 = u0+(cut_a if u0 < 1e-9 else 0)
            v1 = u1-(cut_b if u1 > part['length']-1e-9 else 0)
            for sign, toward, material in sides:
                add(upright(P(v0, sign*half), P(v1, sign*half), 0, height, toward, material, v0), bucket)
                trims(add, bucket, P(v0, sign*half), P(v1, sign*half), toward, theme, v0)
            add(level([P(v0, -half), P(v1, -half), P(v1, half), P(v0, half)], height, 'wall_cap'), bucket)
            # the doorways' jambs: timber linings (not a sliver of plaster), each facing into its opening
            if any(abs(u0-o) < 1e-9 for o in jambs):
                add(upright(P(u0, half), P(u0, -half), 0, top, (-dx, -dy), 'timber_band'), bucket)
            if any(abs(u1-o) < 1e-9 for o in jambs):
                add(upright(P(u1, -half), P(u1, half), 0, top, (dx, dy), 'timber_band'), bucket)
        low, high = cut_a, part['length']-cut_b
        for o0, o1, _ in part['openings']:
            for sign, toward, material in sides:
                add(upright(P(o0, sign*half), P(o1, sign*half), top, height, toward, material, o0), bucket)
                trims(add, bucket, P(o0, sign*half), P(o1, sign*half), toward, theme, o0,
                      heights=[h for h in theme['trim'] if h[0] >= top])
                # the casing round the doorway on this face: two jamb boards and a head board, standing 2 cm proud
                # (a board is left out where the opening runs to the partition's end)
                face_at = sign*(half+.02)
                for e0, e1 in ((o0-CASING, o0), (o1, o1+CASING)):
                    if e0 >= low-1e-6 and e1 <= high+1e-6:
                        add(upright(P(e0, face_at), P(e1, face_at), 0, top, toward, 'timber_band', e0), bucket)
                add(upright(P(max(low, o0-CASING), face_at), P(min(high, o1+CASING), face_at), top, top+CASING,
                            toward, 'timber_band', o0), bucket)
            add(level([P(o0, -half), P(o1, -half), P(o1, half), P(o0, half)], height, 'wall_cap'), bucket)
            add(level([P(o0, -half), P(o1, -half), P(o1, half), P(o0, half)], top, 'timber_band', up=False), bucket)
        mid = part['length']/2
        cx, cy = ax+dx*mid, ay+dy*mid
        notes.append({'bucket': bucket, 'section': sid, 'rooms': [i, j],
                      'centre': [round(cx, 2), round(_FRAME['cells']-cy, 2)], 'along': world_dir((dx, dy)),
                      'normal': world_dir((nx, ny))})


def _door_frame(add, bucket, centre, along, inward, width, bottom, top, inset):
    """A timber frame round an opening on a wall: two jambs and a head, standing `inset` metres proud."""
    w = width/2
    for sign in (-1, 1):
        p = _offset(_offset(centre, along, sign*(w+.07)), inward, inset)
        a, b = _offset(p, along, -.07), _offset(p, along, .07)
        add(upright(a, b, bottom, top+.14, inward, 'timber_band'), bucket)
    p = _offset(centre, inward, inset)
    add(upright(_offset(p, along, -(w+.14)), _offset(p, along, w+.14), top, top+.14, inward, 'timber_band'), bucket)


def door_geometry(section, add):
    """Each street door: a lit doorway in the wall its exit faces, a timber frame, and daylight on the floor."""
    theme = theme_of(section)
    sid = section['id']
    spans = []
    for door in TS.doors(section):
        fx, fy = door['exitFacing']
        cx, cy = door['exit'][0]+.5, door['exit'][1]+.5
        wall = (cx+fx, cy+fy)
        along, inward = (-fy, fx), (-fx, -fy)
        w = theme['doorWidth']/2
        where = f'{sid}: entrance {door["index"]}'
        if not _on_outer(section, _offset(wall, along, -(w+.2)), _offset(wall, along, w+.2)):
            raise SystemExit(f'{where}: the street door must stand in a straight outer wall one tile beyond its exit '
                             f'{door["exit"]} (exitFacing {door["exitFacing"]})')
        side = _side_of((fx, fy))
        bucket = f'Build_{sid}_{side}'
        p = _offset(wall, inward, .025)
        a, b = _offset(p, along, -w), _offset(p, along, w)
        add(face([world(*a, 0), world(*b, 0), world(*b, theme['doorHeight']), world(*a, theme['doorHeight'])],
                 world_dir(inward), 'door_daylight', [[0, 1], [1, 1], [1, 0], [0, 0]]), bucket)
        _door_frame(add, bucket, wall, along, inward, theme['doorWidth'], 0, theme['doorHeight'], .045)
        # on the floor (never cut away, so the doorway still reads with its wall gone): a timber threshold along the
        # wall and the daylight spilling in, a soft picture fading into the room and to both sides
        sill = _offset(wall, inward, .2)
        add(level([_offset(wall, along, -(w+.08)), _offset(wall, along, w+.08), _offset(sill, along, w+.08),
                   _offset(sill, along, -(w+.08))], .02, 'timber_band'), f'Door_{sid}')
        add(upright(_offset(sill, along, -(w+.08)), _offset(sill, along, w+.08), 0, .02, inward, 'timber_band'),
            f'Door_{sid}')
        far = _offset(wall, inward, 2.6)
        corners = [_offset(wall, along, -(w+.2)), _offset(wall, along, w+.2), _offset(far, along, w+.9),
                   _offset(far, along, -(w+.9))]
        add(face([world(*p, .012) for p in corners], (0, 1, 0), 'door_spill', [[0, 0], [1, 0], [1, 1], [0, 1]]),
            f'Door_{sid}')
        spans.append((side, wall, along, w))
    return spans


def window_geometry(section, add, doors):
    """Each window: the theme's glazing picture (window_art(): one whole picture per quad) or, until it is published,
    a flat pane; the timber frame, sill, centre mullion and transom over it either way."""
    theme = theme_of(section)
    sid = section['id']
    sill, head = theme['windowSill'], theme['windowHead']
    glazing = window_art(theme)
    for index, window in enumerate(section.get('windows', [])):
        where = f'{sid}: window {index}'
        a, b = side_segment(section, window['room'], window['side'])
        centre = (a[0]+(b[0]-a[0])*window['at'], a[1]+(b[1]-a[1])*window['at'])
        side = window['side']
        n = TS.SIDE_TILE[side]
        along, inward = (-n[1], n[0]), (-n[0], -n[1])
        w = window['width']/2
        if not _on_outer(section, _offset(centre, along, -(w+.15)), _offset(centre, along, w+.15)):
            raise SystemExit(f'{where}: a window goes in an outer wall (this span is a partition, a corner or off '
                             'the room)')
        for door_side, wall, door_along, dw in doors:
            if door_side == side and abs((centre[0]-wall[0])*n[0]+(centre[1]-wall[1])*n[1]) < 1e-6 and \
                    abs((centre[0]-wall[0])*door_along[0]+(centre[1]-wall[1])*door_along[1]) < w+dw+.3:
                raise SystemExit(f'{where}: it overlaps a street door')
        bucket = f'Build_{sid}_{side}'
        p = _offset(centre, inward, .02)
        a, b = _offset(p, along, -w), _offset(p, along, w)
        if glazing in WINDOW_ART:
            # the art role's leaded glazing, one whole picture per window; `along` runs right to left as seen from
            # the room, so b is the picture's left edge
            add(picture([world(*b, sill), world(*a, sill), world(*a, head), world(*b, head)], world_dir(inward),
                        glazing), bucket)
        else:
            add(upright(a, b, sill, head, inward, 'window_glass'), bucket)
        _door_frame(add, bucket, centre, along, inward, window['width'], sill-.12, head, .045)
        q = _offset(centre, inward, .05)
        add(upright(_offset(q, along, -(w+.14)), _offset(q, along, w+.14), sill-.12, sill, inward, 'timber_band'),
            bucket)
        add(level([_offset(centre, along, -(w+.14)), _offset(centre, along, w+.14),
                   _offset(_offset(centre, inward, .12), along, w+.14),
                   _offset(_offset(centre, inward, .12), along, -(w+.14))], sill, 'timber_band'), bucket)
        add(upright(_offset(q, along, -.03), _offset(q, along, .03), sill, head, inward, 'timber_band'), bucket)
        transom = sill+(head-sill)*.62
        add(upright(_offset(q, along, -w), _offset(q, along, w), transom-.03, transom+.03, inward, 'timber_band'),
            bucket)


def image_size(image_id):
    """The (width, height) in pixels of a decal's published art, or None while it has none."""
    path = surface_file(image_id)
    if path is None:
        return None
    with Image.open(path) as image:
        return image.size


# a decal's size may differ from its art's aspect by this share before the builder refuses to stretch the art
DECAL_ASPECT_SLACK = .15


def decal_geometry(section, add):
    """Each decal: on the floor (its art turned a quarter when the art is portrait and the decal landscape, or the
    other way round) or hung on a wall, upright. Refuses a size that would stretch published art."""
    theme = theme_of(section)
    sid = section['id']
    boxes = TS.rooms(section)
    for index, decal in enumerate(section.get('decals', [])):
        where = f'{sid}: decal {index}'
        material = 'decal_'+decal['image']
        width, tall = decal['size']
        u, v = decal['at']
        pixels = image_size(decal['image'])
        turned = (decal['side'] == 'floor' and pixels is not None
                  and (pixels[0] > pixels[1]) != (width > tall) and pixels[0] != pixels[1])
        if pixels is not None:
            art = pixels[1]/pixels[0] if turned else pixels[0]/pixels[1]
            if abs(width/tall/art-1) > DECAL_ASPECT_SLACK:
                raise SystemExit(f'{where}: {width} x {tall} m stretches {decal["image"]}\'s art ({pixels[0]} x '
                                 f'{pixels[1]} px): keep its aspect, e.g. {width} x {round(width/art, 2)} m')
        if decal['side'] == 'floor':
            x0, y0, x1, y1 = boxes[decal['room']]
            cx, cy = x0+(x1-x0)*u, y0+(y1-y0)*v
            if not (x0 <= cx-width/2 and cx+width/2 <= x1 and y0 <= cy-tall/2 and cy+tall/2 <= y1):
                raise SystemExit(f'{where}: the decal runs off its room')
            h = decal.get('height', 0)+.01+.002*index
            corners = [world(cx-width/2, cy-tall/2, h), world(cx+width/2, cy-tall/2, h),
                       world(cx+width/2, cy+tall/2, h), world(cx-width/2, cy+tall/2, h)]
            if turned:
                # the art's top runs along the east side: a quarter turn, not a mirror
                add(face(corners, (0, 1, 0), material, [[1, 1], [1, 0], [0, 0], [0, 1]]), f'Decal_{sid}')
            else:
                add(picture(corners, (0, 1, 0), material), f'Decal_{sid}')
            continue
        a, b = side_segment(section, decal['room'], decal['side'])
        centre = (a[0]+(b[0]-a[0])*u, a[1]+(b[1]-a[1])*u)
        n = TS.SIDE_TILE[decal['side']]
        # left to right as seen from inside the room, facing the wall (tile x east, y north: not mirrored)
        along, inward = (n[1], -n[0]), (-n[0], -n[1])
        height = theme['wallHeight']*v
        if height-tall/2 < .05 or height+tall/2 > theme['wallHeight']-.05:
            raise SystemExit(f'{where}: the decal runs off its wall\'s height')
        p0, p1 = _offset(centre, along, -width/2), _offset(centre, along, width/2)
        if _on_outer(section, p0, p1):
            bucket, inset = f'Build_{sid}_{decal["side"]}', .03
        else:
            bucket = None
            for k, part in enumerate(partitions(section)):
                (ax, ay), (dx, dy) = part['a'], part['along']
                if any(LineString([(ax+dx*s0, ay+dy*s0), (ax+dx*s1, ay+dy*s1)]).buffer(1e-6).covers(
                        LineString([p0, p1])) for s0, s1 in part['solid']):
                    bucket, inset = f'Part_{sid}_{k}', theme['partitionThickness']/2+.03
                    break
            if bucket is None:
                raise SystemExit(f'{where}: the decal must hang on a wall (an outer wall or a partition\'s solid piece)')
        p0, p1 = _offset(p0, inward, inset), _offset(p1, inward, inset)
        corners = [world(*p0, height-tall/2), world(*p1, height-tall/2), world(*p1, height+tall/2),
                   world(*p0, height+tall/2)]
        add(picture(corners, world_dir(inward), material), bucket)


def _post(add, bucket, centre, half, h0, h1, material):
    """A square post (tile axes) of half width `half` round a tile point, from h0 to h1 metres, capped."""
    x, y = centre
    x0, y0, x1, y1 = x-half, y-half, x+half, y+half
    add(upright((x0, y0), (x1, y0), h0, h1, (0, -1), material), bucket)
    add(upright((x0, y1), (x1, y1), h0, h1, (0, 1), material), bucket)
    add(upright((x0, y0), (x0, y1), h0, h1, (-1, 0), material), bucket)
    add(upright((x1, y0), (x1, y1), h0, h1, (1, 0), material), bucket)
    add(level([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], h1, material), bucket)


def _rail(add, bucket, p0, h0, p1, h1, lateral, material, half=.035, thick=.03):
    """A handrail from tile point p0 at h0 to p1 at h1 metres (it may slope): its top and both sides, `lateral` the
    unit tile direction across it."""
    lx, ly = lateral
    r = repeat_of(material)
    length = math.hypot(p1[0]-p0[0], p1[1]-p0[1], h1-h0)
    uvs = [[0, 0], [length/r, 0], [length/r, .07/r], [0, .07/r]]
    def at(p, s, h):
        return world(p[0]+lx*s, p[1]+ly*s, h)
    add(face([at(p0, -half, h0+thick), at(p1, -half, h1+thick), at(p1, half, h1+thick), at(p0, half, h0+thick)],
             (0, 1, 0), material, uvs), bucket)
    for s in (-1, 1):
        add(face([at(p0, s*half, h0-thick), at(p1, s*half, h1-thick), at(p1, s*half, h1+thick),
                  at(p0, s*half, h0+thick)], world_dir((lx*s, ly*s)), material, uvs), bucket)


def _open_side(section, point):
    """True where a stair's side has floor beside it (no outer wall or partition within a step of it): it gets a
    handrail."""
    if not outline(section).buffer(-.05).contains(Point(point)):
        return False
    return not any(line.distance(Point(point)) < .3 for line in _partition_lines(section))


def stair_geometry(section, add, walls):
    """Each stair (stairs()): stairs_up and sealed flights against their outer wall (cut away with it), stairwells
    down into the floor (never cut). A flight has lit treads with a nosing, shaded risers (SHADES), stepped timber
    stringers and, on every side with floor beside it, a handrail on newel posts and balusters; it rises to a dark
    opening in the wall (a passage up), or to a shut plank door with iron straps (a sealed stair). A stairwell's treads
    and sides darken with depth (never black), a dark passage opens under a timber lintel at its foot, and a handrail
    runs along both its sides. Returns the stairwells' footprints, which the floor leaves open."""
    theme = theme_of(section)
    sid = section['id']
    wells = []
    for k, stair in enumerate(stairs(section)):
        spec = STAIRS[stair['art']]
        (cx, cy), (ux, uy), d = stair['centre'], stair['facing'], stair['distance']
        vx, vy, w = -uy, ux, spec['width']/2
        steps, rise, depth = spec['steps'], spec['rise'], spec['depth']
        a0, run = d-depth, depth/steps
        room_side = (-ux, -uy)
        tread, rail = theme['stairs'], theme['stairRail']
        def P(a, b):
            return (cx+ux*a+vx*b, cy+uy*a+vy*b)
        if stair['art'] == 'stairs_up':
            bucket = f'Build_{sid}_stair{k}'
            walls[bucket] = world_dir((ux, uy))
            top = steps*rise
            for i in range(steps):
                ai, aj = a0+i*run, (a0+(i+1)*run if i < steps-1 else d)
                h = (i+1)*rise
                add(level([P(ai, -w), P(aj, -w), P(aj, w), P(ai, w)], h, tread), bucket)
                add(upright(P(ai, -w), P(ai, w), i*rise, h-NOSING, room_side, tread+'_shade'), bucket)
                # the nosing: the tread's front edge, a lit lip standing proud of the shaded riser
                add(upright(P(ai-.025, -w), P(ai-.025, w), h-NOSING, h, room_side, tread), bucket)
                add(level([P(ai-.025, -w), P(ai, -w), P(ai, w), P(ai-.025, w)], h, tread), bucket)
                for sign in (-1, 1):
                    add(upright(P(ai, sign*w), P(aj, sign*w), 0, h, (sign*vx, sign*vy), rail, ai), bucket)
            for sign in (-1, 1):
                if not _open_side(section, P((a0+d)/2, sign*(w+.45))):
                    continue
                lateral = (sign*vx, sign*vy)
                b = sign*(w-.06)
                low, high = a0+.08, d-.14
                h_low, h_high = rise+RAIL_HEIGHT, top+RAIL_HEIGHT
                _post(add, bucket, P(low, b), .05, 0, h_low+.08, rail)
                _post(add, bucket, P(high, b), .05, 0, h_high+.08, rail)
                _rail(add, bucket, P(low, b), h_low, P(high, b), h_high, lateral, rail)
                for i in range(1, steps):
                    a = a0+(i+.5)*run
                    _post(add, bucket, P(a, b), .018, (i+1)*rise, h_low+(h_high-h_low)*(a-low)/(high-low), rail)
            head = min(top+2.2, theme['wallHeight']-.2)
            if stair['kind'] == 'sealed':
                # a shut door of dark planks with two iron straps and a ring
                add(upright(P(d-.02, -w*.92), P(d-.02, w*.92), top, head, room_side, 'timber_band_shade'), bucket)
                for strap in (top+(head-top)*.22, top+(head-top)*.74):
                    add(upright(P(d-.035, -w*.92), P(d-.035, w*.92), strap-.04, strap+.04, room_side, 'iron'),
                        bucket)
                _post(add, bucket, P(d-.06, w*.45), .035, top+(head-top)*.45, top+(head-top)*.45+.09, 'iron')
            else:
                add(upright(P(d-.02, -w*.92), P(d-.02, w*.92), top, head, room_side, 'stair_dark'), bucket)
            _door_frame(add, bucket, P(d, 0), (vx, vy), room_side, w*1.84, top, head, .04)
        else:
            bucket = f'Stair_{sid}_{k}'
            bottom = -steps*rise
            sides = (TS.wall_of(section, TS.room_of(section, cx, cy)) or theme['walls'])+'_shade'
            for i in range(steps):
                ai, aj = a0+i*run, (a0+(i+1)*run if i < steps-1 else d)
                h = -(i+1)*rise
                lit = tread if i < 2 else tread+('_shade' if i < 4 else '_dusk')
                add(level([P(ai, -w), P(aj, -w), P(aj, w), P(ai, w)], h, lit), bucket)
                add(upright(P(ai, -w), P(ai, w), h, -i*rise, (ux, uy), lit), bucket)
                if i < steps-1:
                    # the tread's lit nosing on its downhill edge, so each step reads from above
                    add(level([P(aj-.05, -w), P(aj, -w), P(aj, w), P(aj-.05, w)], h+.004, tread), bucket)
            for sign in (-1, 1):
                add(upright(P(a0, sign*w), P(d, sign*w), bottom, 0, (-sign*vx, -sign*vy), sides, a0), bucket)
            # the well's far face (most of what the camera sees of it, looking down at -50 degrees) is its walls'
            # dim surface; only at the foot does a low dark passage lead on, under a timber lintel
            add(upright(P(d, -w), P(d, w), WELL_PASSAGE, 0, room_side, sides), bucket)
            add(upright(P(d, -w*.8), P(d, w*.8), bottom, WELL_PASSAGE, room_side, 'stair_dark'), bucket)
            for sign in (-1, 1):
                add(upright(P(d, sign*w*.8), P(d, sign*w), bottom, WELL_PASSAGE, room_side, sides), bucket)
            add(upright(P(d-.02, -w*.86), P(d-.02, w*.86), WELL_PASSAGE, WELL_PASSAGE+.14, room_side, rail), bucket)
            # a handrail along both sides of the well, on newels and balusters
            for sign in (-1, 1):
                b = sign*(w+.07)
                lateral = (sign*vx, sign*vy)
                low, high = a0+.05, d-.08
                _post(add, bucket, P(low, b), .05, 0, RAIL_HEIGHT+.08, rail)
                _post(add, bucket, P(high, b), .05, 0, RAIL_HEIGHT+.08, rail)
                _rail(add, bucket, P(low, b), RAIL_HEIGHT, P(high, b), RAIL_HEIGHT, lateral, rail)
                count = max(2, int((high-low)/.3))
                for i in range(1, count):
                    _post(add, bucket, P(low+(high-low)*i/count, b), .018, 0, RAIL_HEIGHT, rail)
            wells.append(stair['footprint'])
    return wells


def section_geometry(section, add, lights, chambers, walls, notes):
    """A section's shell: floors, ceiling, outer walls, partitions, doors, windows, decals, stairs; its rooms as
    chambers and its lights."""
    theme = theme_of(section)
    sid = section['id']
    wells = stair_geometry(section, add, walls)
    for room, (x0, y0, x1, y1) in enumerate(TS.rooms(section)):
        floor = box(x0, y0, x1, y1)
        for well in wells:
            floor = floor.difference(well)
        for part in getattr(floor, 'geoms', [floor]):
            if part.geom_type == 'Polygon' and part.area > 1e-6:
                for piece in floor_triangles(part, 0, section['floors'][room]):
                    add(piece, f'Walk_{sid}')
    for piece in floor_triangles(outline(section), theme['wallHeight'], 'wall_cap', up=False):
        add(piece, f'Roof_{sid}')
    outer_wall_geometry(section, add, walls)
    partition_geometry(section, add, notes)
    doors = door_geometry(section, add)
    window_geometry(section, add, doors)
    decal_geometry(section, add)
    for index, ((cx, cy, rx, ry), name) in enumerate(zip(section['rooms'], section['roomNames'])):
        # The music sync makes a chamber a square of half side radius + 1 m: one metre short of the room's LONGER half
        # extent, so the square covers the whole room (a room name without a music keyword has only its chamber). Where
        # the square spills past a wall the smaller zone wins (the neighbour's own space or chamber).
        chambers.append({'id': f'{sid}-{index}', 'section': sid, 'position': list(world(cx, cy)),
                         'radius': round(max(.5, max(rx, ry)-1), 2), 'name': name})
    found = section_lights(section)
    lights.extend(found)


def section_lights(section):
    """The section's light markers: the source's lights, then its lamp props (build_underground.KIT_LIGHTS) and props
    marked `light`; refused when a room holds more than town_source.MAX_LIGHTS_PER_ROOM."""
    sid = section['id']
    result, per_room = [], defaultdict(int)
    for index, light in enumerate(section.get('lights', [])):
        x, y = light['at']
        per_room[TS.room_of(section, x, y)] += 1
        result.append({'id': f'{sid}-light-{index}', 'position': list(world(x, y, light['height'])),
                       'color': list(light['colour']), 'energyHint': light['energy'], 'rangeHint': light['range'],
                       'section': sid})
    lamp = 0
    for item in dressing(section):
        light = B.KIT_LIGHTS.get(item['asset']) or (PROP_GLOW if item.get('light') else None)
        if light is None:
            continue
        colour, energy, reach, flame = light
        per_room[TS.room_of(section, item['x'], item['y'])] += 1
        result.append({'id': f'{sid}-lamp-{lamp}', 'position': list(world(item['x'], item['y'],
                                                                          flame*item['scale']+item['height'])),
                       'color': list(colour), 'energyHint': energy, 'rangeHint': reach, 'section': sid})
        lamp += 1
    for room, total in per_room.items():
        if total > TS.MAX_LIGHTS_PER_ROOM:
            raise SystemExit(f'{sid}: room {room} has {total} lights with its lamps (at most {TS.MAX_LIGHTS_PER_ROOM})')
    return result


def stair_offset(stair):
    """A passage end's drawn stair as [dx, 0, dz] metres from its end tile's centre to the flight's (or the well's)
    centre: retarget_underground.py writes it as the end's objects.json modelOffset, so the stair's pick and label
    stand on the stair drawn 1.4-4 m beyond the tile."""
    centre = stair['footprint'].centroid
    tx, ty = stair['end']['tile']
    return [round(centre.x-(tx+.5), 3)+0., 0., round(-(centre.y-(ty+.5)), 3)+0.]


def section_bounds(section):
    """A section's id, name and world-space X/Z bounds (metres, 2 m clear of its walls) for the client."""
    x0, y0, x1, y1 = outline(section).buffer(2, join_style='mitre').bounds
    cells = _FRAME['cells']
    return {'id': section['id'], 'name': section['name'],
            'bounds': {'min': [round(x0, 2), round(cells-y1, 2)], 'max': [round(x1, 2), round(cells-y0, 2)]}}


def build_geometry(design):
    builder = G.GltfBuilder(generator='Rabbit Lands Landfall town interiors builder; owner-approved room shells')
    root = G.Node('Landfall_Town')
    parts = defaultdict(list)
    lights, chambers, notes = [], [], []
    walls = {}

    def add(piece, bucket):
        parts[(bucket, piece.material)].append(piece)

    for section in design['sections']:
        section_geometry(section, add, lights, chambers, walls, notes)
    used = {material for _, material in parts}
    textures = register_materials(builder, used)
    meshes, collision, hidden, cutaway_walls, partition_nodes = [], [], [], [], []
    for (bucket, material), pieces in sorted(parts.items()):
        piece = M.merge(pieces, material=material).drop_degenerate().sanitise_normals()
        name = f'{bucket}_{material}'
        builder.add_mesh(name, piece, with_tangents=True)
        root.add(G.Node(name, mesh=name))
        meshes.append(piece)
        sid = max((s['id'] for s in design['sections'] if bucket.split('_', 1)[1].startswith(s['id'])), key=len)
        if bucket.startswith('Roof_'):
            hidden.append(name)
        if bucket.startswith(('Build_', 'Part_', 'Stair_')):
            collision.append(name)
        if bucket.startswith('Build_'):
            cutaway_walls.append({'node': name, 'outward': walls[bucket], 'section': sid})
        if bucket.startswith('Part_'):
            note = next(n for n in notes if n['bucket'] == bucket)
            partition_nodes.append({'node': name, **{k: v for k, v in note.items() if k != 'bucket'}})
    builder.add_node(root)
    bounds = M.merge(meshes).bounds()
    return builder, lights, chambers, hidden, collision, bounds, cutaway_walls, partition_nodes, textures


# --- the walk grid -------------------------------------------------------------------------------------------------


def doorway_tiles(part, o0, o1):
    """The tiles of the partition's row a doorway opening (o0..o1 metres along it) spans."""
    (ax, ay), (dx, dy) = part['a'], part['along']
    return sorted({(int(math.floor(ax+dx*u)), int(math.floor(ay+dy*u))) for u in np.arange(o0, o1, .25)})


def section_window(section, pad=2.5):
    """The tile box (x0, y0, x1, y1) a section's walk grid can touch: its outline and every prop's block, padded."""
    x0, y0, x1, y1 = outline(section).buffer(pad, join_style='mitre').bounds
    for item in dressing(section):
        reach = max(item['block'], max(item.get('blockBox', [0, 0]))*1.5)
        if reach > 0:
            x0, y0 = min(x0, item['x']-reach-pad), min(y0, item['y']-reach-pad)
            x1, y1 = max(x1, item['x']+reach+pad), max(y1, item['y']+reach+pad)
    return x0, y0, x1, y1


def masks(design, strict=True):
    """The walk grid: half-metre cells (`half`) and served tiles (`coarse`); see WALK GRID in the docstring. `strict`
    refuses a stranded pocket larger than STRANDED_MAX (a layout preview passes False)."""
    from scipy import ndimage
    if any('_ends' not in s for s in design['sections']):
        annotate(design)
    cells = design['map']['cells']
    size = cells*2
    half = np.zeros((size, size), dtype=bool)
    for section in design['sections']:
        theme = theme_of(section)
        shape = outline(section)
        wx0, wy0, wx1, wy1 = section_window(section)
        i0, j0 = max(0, int(math.floor(wx0*2))), max(0, int(math.floor(wy0*2)))
        i1, j1 = min(size, int(math.ceil(wx1*2))+1), min(size, int(math.ceil(wy1*2))+1)
        x, y = np.meshgrid((np.arange(i0, i1)+.5)*.5, (np.arange(j0, j1)+.5)*.5)
        cell = contains_xy(shape.buffer(-max(.4, theme['margin'])), x, y)
        lines = _partition_lines(section)
        if lines:
            cell &= ~contains_xy(unary_union(lines).buffer(theme['margin']), x, y)
        for stair in stairs(section):
            cell &= ~contains_xy(stair['footprint'].buffer(.4), x, y)
        for item in dressing(section):
            cell &= ~blocked_by(item, x, y)
        half[j0:j1, i0:i1] |= cell
    coarse = half.reshape(cells, 2, cells, 2).all(axis=(1, 3))
    for section in design['sections']:
        for part in partitions(section):
            for o0, o1, link in part['openings']:
                if not any(coarse[y, x] for x, y in doorway_tiles(part, o0, o1)):
                    raise SystemExit(f'{section["id"]}: link {link}: its doorway leaves no open tile through the wall '
                                     '(centre it on a tile centre, x.5, or widen it)')
    for section in design['sections']:
        x0, y0, x1, y1 = (int(v) for v in outline(section).buffer(1, join_style='mitre').bounds)
        window = coarse[y0:y1+1, x0:x1+1]
        labels, _ = ndimage.label(window)
        ax, ay = section['_arrival']
        if not window[ay-y0, ax-x0]:
            raise SystemExit(f'{section["id"]}: its arrival {section["_arrival"]} is not on open floor')
        stranded = window & (labels != labels[ay-y0, ax-x0])
        pieces, count = ndimage.label(stranded)
        close = np.zeros_like(stranded)
        for label in range(1, count+1):
            pocket = pieces == label
            if pocket.sum() <= STRANDED_MAX:
                close |= pocket
            elif strict:
                ys, xs = np.nonzero(pocket)
                raise SystemExit(f'{section["id"]}: {int(pocket.sum())} floor tiles are cut off from the arrival, '
                                 f'e.g. ({xs[0]+x0},{ys[0]+y0}): a prop, stair or doorway closes the way')
        half[y0*2:(y1+1)*2, x0*2:(x1+1)*2] &= ~np.repeat(np.repeat(close, 2, 0), 2, 1)
    coarse = half.reshape(cells, 2, cells, 2).all(axis=(1, 3))
    return half, coarse


def protect(design, coarse):
    """Refuse a layout whose props, stairs or doorways block a way in or out, a doorway, an NPC post or an
    interactive's approach (see WALK GRID in the docstring)."""
    from scipy import ndimage
    for section in design['sections']:
        sid = section['id']
        x0, y0, x1, y1 = (int(v) for v in outline(section).buffer(1, join_style='mitre').bounds)
        window = coarse[y0:y1+1, x0:x1+1]
        labels, _ = ndimage.label(window)
        ax, ay = section['_arrival']
        home = labels[ay-y0, ax-x0]

        def reached(tile):
            tx, ty = tile
            return x0 <= tx <= x1 and y0 <= ty <= y1 and bool(window[ty-y0, tx-x0]) and labels[ty-y0, tx-x0] == home

        ways = set()
        for door in TS.doors(section):
            for key in ('exit', 'arrival'):
                if not reached(door[key]):
                    raise SystemExit(f'{sid}: entrance {door["index"]}: its {key} {door[key]} is blocked or cut off '
                                     'from the arrival (a prop, stair or wall margin stands on it)')
                ways.add(tuple(door[key]))
        for end in section['_ends']:
            for key in ('tile', 'arrival'):
                if not reached(end[key]):
                    raise SystemExit(f'{sid}: passage {end["passage"]} end {end["end"]}: its {key} {end[key]} is '
                                     'blocked or cut off (a stair needs its tile a step out from its foot)')
                ways.add(tuple(end[key]))
        for part in partitions(section):
            for o0, o1, link in part['openings']:
                if not any(reached(t) for t in doorway_tiles(part, o0, o1)):
                    raise SystemExit(f'{sid}: link {link}: its doorway leaves no open tile through the wall (centre it '
                                     'on a tile centre, x.5, or widen it)')
        posts = {}
        for entry in TS.interactives(section):
            tile = tuple(entry['tile'])
            if tile in ways:
                raise SystemExit(f'{sid}: interactive {entry["object"]} stands on a way in or out {list(tile)}')
            if not reached(tile) and not any(reached((tile[0]+dx, tile[1]+dy))
                                             for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                raise SystemExit(f'{sid}: interactive {entry["object"]} at {list(tile)} has no reached approach')
            posts[tile] = f'interactive {entry["object"]}'
        for npc in TS.npcs(section):
            tile = tuple(npc['tile'])
            if tile in ways or tile in posts:
                raise SystemExit(f'{sid}: {npc["name"]} stands on a way in or out or on '
                                 f'{posts.get(tile, "a door or stair tile")} {list(tile)}')
            around = [(tile[0]+dx, tile[1]+dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
            if not all(reached(t) for t in around):
                raise SystemExit(f'{sid}: {npc["name"]}\'s post {list(tile)} needs its tile and all eight neighbours '
                                 'open and reached (a counter or prop closes one)')
            posts[tile] = npc['name']


# --- building ------------------------------------------------------------------------------------------------------


def _rgb(hexcode):
    return tuple(int(hexcode[i:i+2], 16) for i in (0, 2, 4))


def door_colour(category):
    try:
        import map_categories
        return _rgb(map_categories.colour(category))
    except ImportError:
        return _rgb('e8d09b')


def minimap(design, path, pixels=3):
    """The map's minimap: rooms in their floors' colours, outer walls, partitions, stairs, doors in their dots'
    colours, passage ends."""
    cells = design['map']['cells']
    image = Image.new('RGB', (cells*pixels, cells*pixels), 'black')
    draw = ImageDraw.Draw(image)
    for section in design['sections']:
        for room, (x0, y0, x1, y1) in enumerate(TS.rooms(section)):
            draw.rectangle((x0*pixels, y0*pixels, x1*pixels, y1*pixels), fill=MINIMAP[section['floors'][room]])
        for stair in stairs(section):
            draw.polygon([(x*pixels, y*pixels) for x, y in stair['footprint'].exterior.coords], fill=MINIMAP['stairs'])
        draw.polygon([(x*pixels, y*pixels) for x, y in outline(section).exterior.coords], outline=MINIMAP['wall'],
                     width=2)
        for line in _partition_lines(section):
            draw.line([(x*pixels, y*pixels) for x, y in line.coords], fill=MINIMAP['partition'], width=2)
        for door in TS.doors(section):
            x, y = door['exit']
            draw.rectangle((x*pixels-1, y*pixels-1, x*pixels+pixels+1, y*pixels+pixels+1),
                           fill=door_colour(door['category']))
        for end in section['_ends']:
            x, y = end['tile']
            draw.rectangle((x*pixels, y*pixels, x*pixels+pixels, y*pixels+pixels), fill=MINIMAP['passage'])
    image.save(path, lossless=True)


def _rotation(direction):
    """Godot rotation.y (degrees) turning a body to face the tile direction (dx, dy) (tile +y is world -Z)."""
    return round(math.degrees(math.atan2(direction[0], -direction[1]))) % 360


def resolve_server(server=None):
    """The server checkout whose served-grid codec writes served-grid.escg.gz: `server`, $ELORIA_SERVER_ROOT, or
    rabbitlands-server beside this checkout."""
    for candidate in (server, os.environ.get('ELORIA_SERVER_ROOT'), CHECKOUT.parent/'rabbitlands-server'):
        if candidate and (Path(candidate)/'eloria/served_grid.py').is_file():
            return Path(candidate).resolve()
    raise SystemExit('no server checkout: pass --server <rabbitlands-server> (its served-grid codec writes the grid)')


def build(server, source=None, out=None, registry=True, approval=None, share_images=True):
    """Build the package from the source (or `source`) into continent-v2/<map id>/client (or `out`). `server` is a
    server checkout (its served-grid codec); None skips served-grid.escg.gz (a scratch build: the manifest then names
    no served grid). `registry` holds the build to the map's registry.json row (checked after writing, as the cave
    builder does); `share_images` moves the images into the shared pool (a scratch build keeps them embedded).
    `approval` is the owner's note (who, when, what): required. Returns the build summary."""
    if not (approval or '').strip():
        raise RuntimeError('build_town_interiors.build() needs the owner\'s approval note (who, when, what)')
    source = Path(source or SOURCE)
    design = load_design(source)
    ident, cells = design['map']['id'], design['map']['cells']
    previous = _FRAME['cells']
    _FRAME['cells'] = cells
    try:
        return _build(server, source, design, ident, cells, out, registry, approval, share_images)
    finally:
        _FRAME['cells'] = previous


def _build(server, source, design, ident, cells, out, registry, approval, share_images):
    out = Path(out or HERE.parent/ident/'client')
    half, coarse = masks(design)
    protect(design, coarse)
    (builder, lights, chambers, hidden, collision_nodes, bounds, cutaway_walls, partition_nodes,
     textures) = build_geometry(design)
    out.mkdir(parents=True, exist_ok=True)
    builder.write_glb(str(out/'world.glb'))
    walk = half.astype(np.uint8)  # flat floors at 0 m: byte 1 (heightEncoding -0.1 m + 0.1 m a unit)
    codes = np.where(coarse, 2000, 0).astype(np.uint16)  # ESCG-v2: 0 m is code 2000
    (out/'collision.bin').write_bytes(struct.pack('<4sHHII', b'EWCG', 2, 0, cells*2, cells*2)+walk.tobytes())
    served = None
    if server is not None:
        sys.path.insert(0, str(server))
        from eloria import served_grid as SG
        grid = SG.ServedGrid(cells, cells, array('H', codes.ravel()))
        (out/'served-grid.escg.gz').write_bytes(SG.encode_file(grid))
        served = {'binary': 'served-grid.escg.gz', 'format': 'ESCG-v2', 'sha256': sha(out/'served-grid.escg.gz'),
                  'unitMetres': .05, 'climbMetres': 1., 'originMetres': -100., 'width': cells, 'height': cells}
    coordinate = {'metresPerTile': 1., 'serverOrigin': [0, cells], 'serverCells': [cells, cells], 'origin': [0, 0, 0],
                  'walkingHeight': 0., 'invertServerY': True, 'serverStorageVersion': 1, 'serverTileMin': [0, 0]}
    names = {s['id']: s['name'] for s in design['sections']}
    ends = {(e['passage'], e['end']): e for p in TS.passages(design) for e in p['ends']}
    spawns, exits, objects, spaces = [], [], [], {}
    for i, section in enumerate(design['sections']):
        sid = section['id']
        arrival = section['_arrival']
        found = TS.doors(section)
        inward = ((-found[0]['exitFacing'][0], -found[0]['exitFacing'][1]) if found
                  else tuple(-v for v in stairs(section)[0]['facing']))
        spawns.append({'id': sid, 'name': section['name'], 'section': sid, 'default': i == 0,
                       'position': list(world(*arrival, .05)), 'serverTile': arrival,
                       'rotationDegrees': _rotation(inward)})
        for door in found:
            exits.append({'id': f'{sid}-exit'+(str(door['index']) if door['index'] else ''),
                          'objectId': door['object'], 'role': 'portal', 'kind': door['kind'],
                          'position': list(world(*door['exit'])), 'serverTile': door['exit'],
                          'destinationMap': door['map'], 'destinationTile': door['returnTile'], 'section': sid,
                          'label': door['exitLabel'] or f'Leave {section["name"]}'})
        drawn = {(s['end']['passage'], s['end']['end']): s for s in stairs(section) if s['kind'] == 'passage'}
        for end in section['_ends']:
            other = ends[(end['passage'], 1-end['end'])]
            exits.append({'id': f'{sid}-passage{end["passage"]}-{end["end"]}', 'objectId': end['object'],
                          'role': 'portal', 'kind': end['art'], 'position': list(world(*end['tile'])),
                          'serverTile': end['tile'], 'destinationMap': ident, 'destinationTile': other['arrival'],
                          'section': sid, 'destinationSection': other['section'],
                          'label': end['label'] or f'On into {names[other["section"]]}',
                          'modelOffset': stair_offset(drawn[(end['passage'], end['end'])])})
        for entry in TS.interactives(section):
            objects.append({'id': f'{sid}-interactive{entry["index"]}', 'objectId': entry['object'],
                            'role': entry['role'], 'position': list(world(*entry['tile'])),
                            'serverTile': entry['tile'], 'section': sid, 'label': entry['text']})
        for room, ((x0, y0, x1, y1), name) in enumerate(zip(TS.rooms(section), section['roomNames'])):
            key, n = name, 2
            while key in spaces:
                key, n = f'{name} {n}', n+1
            spaces[key] = {'x0': x0, 'x1': x1, 'z0': cells-y1, 'z1': cells-y0, 'section': sid, 'room': room}
    pixels = 3
    collision = {'binary': 'collision.bin', 'format': 'EWCG-v2', 'width': cells*2, 'height': cells*2,
                 'cellMetres': .5, 'originMetres': [0, cells], 'heightEncoding': {'origin': -.1, 'step': .1},
                 'gridAlignment': 'tile-centres-v1', 'sha256': sha(out/'collision.bin'), 'nodeNames': collision_nodes}
    if served:
        collision['servedGrid'] = served
    helpers = {f'_continent_v2/{name}': sha(HERE/name) for name in ('build_underground.py', 'town_source.py',
                                                                     'underground_source.py')}
    try:
        source_name = source.resolve().relative_to(HERE.parent).as_posix()
    except ValueError:
        source_name = '_continent_v2/content/'+source.name
    manifest = {
        'schemaVersion': '1.1.0', 'assetVersion': '1.0.0',
        'asset': {'id': ident, 'name': design['map']['name'], 'glb': 'world.glb', 'units': 'meters',
                  'coordinateSystem': {'handedness': 'right', 'upAxis': 'Y', 'northAxis': '-Z'}, 'origin': [0, 0, 0],
                  'bounds': {'min': bounds[0].tolist(), 'max': bounds[1].tolist()}, 'interiorClass': 'insides',
                  'parentRegion': 'landfall', 'serverCells': cells},
        'coordinateTransform': coordinate, 'serverCells': [cells, cells], 'spawnPoints': spawns,
        'chambers': chambers, 'spaces': spaces, 'harvestables': [], 'portals': exits, 'interactives': exits+objects,
        'navigation': {'surfaceNodePrefixes': ['Walk_'], 'authority': 'server', 'defaultSpawn': spawns[0]['id']},
        'collision': collision,
        'environment': design['map']['environment'], 'camera': design['map']['camera'],
        'lighting': {'markers': lights},
        # Straight room walls drop while the camera looks through them (0.35: the caves' 0.6 kept too much of a room
        # standing); props against a wall drop with it; partitions are left to the occluder fade.
        'cutaway': {'hideNodes': hidden, 'walls': cutaway_walls, 'facingThreshold': CUTAWAY_THRESHOLD,
                    'props': {'facingThreshold': CUTAWAY_THRESHOLD, 'radiusMetres': 40},
                    'partitions': partition_nodes,
                    'reason': 'Building interiors: roofs hidden, outer walls cut away by facing, partitions faded '
                              'where they cover the player'},
        'sectioned': True, 'sections': [section_bounds(s) for s in design['sections']],
        'minimap': {'file': 'minimap.webp', 'image': 'minimap.webp', 'northUp': True, 'worldMin': [0, 0],
                    'worldMax': [cells, cells], 'imageSize': [cells*pixels, cells*pixels]},
        'provenance': {'source': source_name, 'sourceSha256': sha(source),
                       'builder': '_continent_v2/build_town_interiors.py', 'builderSha256': sha(__file__),
                       'imports': helpers, 'surfaces': textures, 'ownerApproved': approval.strip()}}
    write_json(out/'world.json', manifest)
    moved = {'moved': 0}
    if share_images:
        sys.path.insert(0, str(CHECKOUT/'eloria-assets/tools'))
        import shared_images
        moved = shared_images.externalise(out/'world.glb', dry_run=False)
        shared_images.record_manifest(out/'world.glb', moved['uris'], dry_run=False)
    minimap(design, out/'minimap.webp', pixels)
    summary = {'map': ident, 'sections': len(design['sections']),
               'rooms': sum(len(s['rooms']) for s in design['sections']),
               'doors': sum(len(TS.doors(s)) for s in design['sections']), 'passages': len(TS.passages(design)),
               'lights': len(lights), 'walkableTiles': int(coarse.sum()), 'glbBytes': (out/'world.glb').stat().st_size,
               'imagesShared': moved['moved'],
               'placeholders': sorted(k for k, v in textures.items() if 'placeholder' in v)}
    if registry:
        rows = json.loads(REGISTRY.read_text(encoding='utf-8'))
        if rows['maps'].get(ident, {}).get('coordinateTransform') != coordinate:
            raise SystemExit(f'registry.json has no {ident} row with this frame; publish it first')
    print(json.dumps(summary))
    return summary


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--owner-approved', metavar='NOTE',
                    help="the owner's approval for this build (who, when, what); the builder refuses without it")
    ap.add_argument('--server', type=Path,
                    help='a server checkout for the served-grid codec (default $ELORIA_SERVER_ROOT, or '
                         'rabbitlands-server beside this checkout)')
    ap.add_argument('--source', type=Path, help='a source in the same format (default content/landfall_town.json)')
    ap.add_argument('--out', type=Path, help='the package folder (default continent-v2/<map id>/client)')
    ap.add_argument('--no-registry', action='store_true',
                    help='skip the registry.json row check (a scratch build before the row is published)')
    args = ap.parse_args()
    if not (args.owner_approved or '').strip():
        raise RuntimeError('build_town_interiors.py is an owner-approved generator: procedural generators were '
                           'retired on 2026-10-16 (docs/procedural-model-archive.md). It builds only with '
                           '--owner-approved "<who, when, what>" (the owner approved the Landfall town room shells on '
                           '2026-10-27). No outputs were written.')
    build(resolve_server(args.server), source=args.source, out=args.out, registry=not args.no_registry,
          approval=args.owner_approved, share_images=args.out is None)
