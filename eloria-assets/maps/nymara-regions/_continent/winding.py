"""Inverted triangle winding in retained library meshes, measured and corrected.

Some certified library meshes carry outward vertex normals but list their
triangles clockwise, so everything that reads the winding sees them inside out:
the client's back-face culling and the atlas rasteriser (``_toolkit/native/
raster.c``) hide the outside of a roof, and every face classifier that takes
``cross(b - a, c - a)`` as the facing (the walk decks in collision_export, the
support modules' upper floors) reads a deck's walking face as pointing down.
The vertex normals are the evidence: a triangle whose geometric normal opposes
the sum of its three vertex normals (cosine below ``MIN_COS``) is listed
backwards, and it is reversed by swapping two of its indices. The decision is
taken per sheet, the triangles joined across shared edges they traverse in
opposite directions (wound the same way round their surface): a sheet turns
whole when its area-weighted mean cosine is below ``MIN_COS``. A lone triangle
is its own sheet, so this is the plain rule wherever triangles do not share
edges; where they do, a few triangles whose smoothed normals point the wrong
way inside a consistently wound surface (creases in the Amethyst geode mouths
and in boulders) are outvoted instead of being punched out of it. The normals
are not always the right side: ``mesh.lathe`` winds against its normals and
points them by the profile's direction, so a profile running clockwise round
its solid has inward normals over an outward winding. A closed sheet that
already encloses a positive signed volume therefore keeps its winding (the
Mirrorhold lamps, the Amberwood resin markers); the open sheets of the clockwise
lathes named in ``KEEP_WINDING`` keep theirs (the Whitehorn icefall columns, the
skep, the Crownwater compass-rose ring); and a level triangle of a water
material faces up whatever its normals say (fountain and well pools, the
Ssarathi waterfall plunge rings). A sheet kept against its normals by
either rule shows the side its normals turn away from and would be lit from
behind, so its vertex normals are negated in a new NORMAL accessor
(``relit_triangles``). ``DOUBLE_SIDED_SHEETS`` names the authored open sheets
meant to be seen from both sides; ``double_sided_sheets`` makes them doubleSided.

The correction works on a private copy of a loaded document. Each corrected
primitive gets a new index accessor on a new buffer view appended to a new body
(4-byte aligned, the original index component type); positions, normals, UVs
and every untouched primitive keep their accessors, so a corrected document
exports through ``scene_io.Exporter`` exactly as the original does. Geometry
shared by several meshes or nodes is corrected once. Left alone, and reported:
primitives without NORMAL, non-triangle modes, double-sided materials,
unreadable accessors, degenerate triangles, triangles whose vertex normals
cancel, and the back copy of a two-sided card (a backwards triangle whose exact
opposite twin stays: reversing it would make the card one-sided). The certified
libraries stay immutable on disk: ``content.load`` corrects each document as it
reads it (README, "Inverted winding in retained library meshes").

    python winding.py --library <task root>/library [--region R] [--output report.json]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import scene_io as S

GR = S.GR
MIN_COS = -.2
# A triangle whose cross product is this small against its longest edge squared
# (roughly the sine of its smallest angle) has no facing worth trusting.
DEGENERATE = 1e-6
# Three vertex normals whose sum is this short against their own lengths cancel.
CANCELLED = 1e-6
TRIANGLES = 4
INDEX_TYPES = {5121: '<u1', 5123: '<u2', 5125: '<u4'}
ELEMENT_ARRAY_BUFFER = 34963
ARRAY_BUFFER = 34962
# Meshes whose open surfaces are wound the authored side although their normals oppose it. The toolkit's
# mesh.lathe always winds against its normals and points them by the profile's direction ((dy, -dr) of
# the profile step): a profile running counter-clockwise round the solid (up the outside, in across the
# top: podiums, towers, domes) gets outward normals over inward winding, which is what this module
# corrects, but one running clockwise gets inward normals over outward winding. These are clockwise
# lathes seen from outside: the Whitehorn icefall columns (kit.frozen_cascade, profile -drop * t), the
# skep (amberwood populate) and the gilt ring of the Crownwater compass rose (populate._compass_rose, in
# the plaza and the sunken court; the gilt star prisms beside it are closed and still turn). A clockwise
# bowl seen from inside (the Amethyst sand sink) has the right normals and is corrected. Closed surfaces
# need no list: their signed volume says which way they wind. Matched against the start of mesh names.
KEEP_WINDING = ('frozen_cascade_', 'Prop_Skep', 'PlazaRose__', 'SunkenCourt__')
# A level triangle of an open sheet whose material has ``water`` as a whole word of its name (water_pool,
# grey_bog_water; not crownwater_marble) faces up when its winding is in question, whatever its normals
# say: water is seen from above. The fountain and well pools are flat lathes run outward from the axis,
# whose analytic normals point down, and the Ssarathi waterfall plunge rings are clockwise lathes; the
# Grey Moors bog pools and the Mirrorhold ring pool face down and turn up. The triangles this rule and KEEP_WINDING
# keep against their normals are relit: their vertex normals turn to the side they show (normalise_winding).
WATER_WORD = 'water'
LEVEL = .5
# Authored single-sided open sheets that must render from both sides. The asset audit of the O5 composition
# (experiments/asset-audit, family B, 2026-09-16) found them with their culled side open to a viewer, authored
# so: the winding correction reverses nothing in them, and the library shows the same gap. Per territory,
# ``materials`` names cloth whose every use in the library is an open sheet (the Sunmane canvases of the
# pavilions, tents, windmill sails, market canopies and water stations); the material itself turns doubleSided.
# A material that also dresses closed solids is named through ``meshes`` instead, as (mesh name, material name)
# pairs, the mesh name an fnmatch pattern on the library mesh name (case-sensitive; ``*`` names a family): the
# matching primitives with that material point at one doubleSided private copy of it, which keeps the
# material's name, so the client's name-keyed surfaces (footsteps, water) read it as before. Left out: bark and
# branch meshes (the Great Tree, the Hanged Oak, the dead trees, the root hollows and root-bound arches), whose
# open branch prisms need a render first, and models built to stand against terrain (the cave mouths, the cenote
# stair, retaining walls, the Northern Grotto arch), which need their backing rather than a second side.
DOUBLE_SIDED_SHEETS = {
    'sunmane_steppe': {'materials': ('sun_canvas_pale', 'sun_canvas_ochre', 'sun_canvas_red')},
    'four_gates': {'meshes': (('Plaza_Arcade_*__solid__fg_stone_ashlar', 'fg_stone_ashlar'),
                              ('Sanctuary_Portal__solid__fg_crystal_blue', 'fg_crystal_blue'))},
    'amberwood': {'meshes': (('Garden_Rotunda__ashlar', 'ashlar'), ('Garden_Statue__ashlar', 'ashlar'),
                             ('Prop_CultivatedGrain_*', 'thatch_reed'), ('Garden_Fall', 'water_stream'),
                             ('Prop_HarbourPacket__timber_grey', 'timber_grey'), ('RowingBoat', 'timber_grey'))},
    'amethyst_barrens': {'meshes': (('PacketTender', 'timber_grey'),)},
    'crownwater': {'meshes': (('CrownStatue_*__ashlar', 'ashlar'), ('Boat_*__timber_dark', 'timber_dark'),
                              ('PacketBoat__timber_dark', 'timber_dark'))},
    'grey_moors': {'meshes': (('CoveBoat', 'grey_bog_timber'), ('PeatCutting_*__grey_bog_timber', 'grey_bog_timber'))},
    'manymouth_delta': {'meshes': (('green_temple__manymouth_glyph_stone', 'manymouth_glyph_stone'),
                                   ('PacketLateen__timber_grey', 'timber_grey'))},
    'mirrorhold': {'meshes': (('Mirrorhold_RoseWindow__blue_crystal', 'blue_crystal'), ('Mirrorhold_Boat', 'timber_grey'),
                              ('Mirrorhold_Waterfall', 'water_stream'))},
    'ssarathi_ruins': {'meshes': (('WaterGate__ssarathi_jade_ashlar', 'ssarathi_jade_ashlar'),
                                  ('CourtShrine__ssarathi_jade_scale', 'ssarathi_jade_scale'),
                                  ('MarketShrine__ssarathi_jade_scale', 'ssarathi_jade_scale'),
                                  ('RoadShrine__ssarathi_jade_scale', 'ssarathi_jade_scale'),
                                  ('RuinBuilding_*__ssarathi_jade_scale', 'ssarathi_jade_scale'),
                                  ('MooredPunt', 'timber_grey'))},
    'verdant_stair': {'meshes': (('Statue__ashlar', 'ashlar'), ('PavilionSmall__verdant_jade', 'verdant_jade'),
                                 ('Boat', 'timber_grey'))},
    'westhaven': {'meshes': (('Mole_Bastion__rubble_stone', 'rubble_stone'), ('Rowing_Boat', 'timber_grey'))},
}
SHEET_TABLE_KEYS = ('materials', 'meshes')
STATUSES = ('consistent', 'corrected', 'outvoted', 'two_sided', 'authored_winding', 'water_up', 'double_sided',
            'no_normals', 'not_triangles', 'unreadable')
LEFT_ALONE = ('outvoted', 'two_sided', 'authored_winding', 'water_up', 'double_sided', 'no_normals', 'not_triangles',
              'unreadable')


def _private(value):
    """A private copy of a glTF JSON value; anything that is not plain JSON is deep-copied."""
    if isinstance(value, dict):
        return {key: _private(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_private(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return copy.deepcopy(value)


def _geometry_key(primitive):
    """Primitives with the same mode, indices, positions and normals are one piece of geometry."""
    attributes = primitive.get('attributes') or {}
    return (primitive.get('mode', TRIANGLES), primitive.get('indices'),
            attributes.get('POSITION'), attributes.get('NORMAL'))


def _unreadable(document, body, index, name):
    """Why accessor ``index`` cannot be read straight out of ``body``; None when it can."""
    accessors = document.get('accessors') or []
    if not isinstance(index, int) or not 0 <= index < len(accessors):
        return f'{name} accessor {index!r} does not exist'
    accessor = accessors[index]
    if 'sparse' in accessor:
        return f'{name} accessor is sparse'
    if accessor.get('bufferView') is None:
        return f'{name} accessor has no buffer data'
    views = document.get('bufferViews') or []
    if not 0 <= accessor['bufferView'] < len(views):
        return f'{name} buffer view does not exist'
    view = views[accessor['bufferView']]
    if view.get('buffer', 0) != 0:
        return f'{name} data lies outside the binary chunk'
    if accessor.get('componentType') not in GR.COMPONENT or accessor.get('type') not in GR.COLUMNS:
        return f'{name} accessor has an unsupported layout'
    if name == 'index' and (accessor['type'] != 'SCALAR' or accessor['componentType'] not in INDEX_TYPES):
        return 'index accessor is not unsigned scalar'
    element = GR.COMPONENT[accessor['componentType']][1] * GR.COLUMNS[accessor['type']]
    stride = view.get('byteStride') or element
    count = int(accessor.get('count', 0))
    start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    # glb_reader.accessor reads whole strides of an interleaved view.
    if start + count * stride > len(body):
        return f'{name} accessor runs past the binary chunk'
    return None


def _measure(document, body, primitive):
    """(geometry, None) of one triangle primitive in its mesh's own space, or (None, the reason it cannot be read)."""
    attributes = primitive.get('attributes') or {}
    if attributes.get('POSITION') is None:
        return None, 'no POSITION accessor'
    for name, index in (('POSITION', attributes['POSITION']), ('NORMAL', attributes.get('NORMAL')),
                        ('index', primitive.get('indices'))):
        reason = None if index is None else _unreadable(document, body, index, name)
        if reason:
            return None, reason
    positions = GR.accessor(document, body, attributes['POSITION']).astype(np.float64)
    if positions.shape[1] != 3:
        return None, 'POSITION is not VEC3'
    normals = None
    if 'NORMAL' in attributes:
        normals = GR.accessor(document, body, attributes['NORMAL']).astype(np.float64)
        if normals.shape != positions.shape:
            return None, 'NORMAL does not match POSITION'
    if 'indices' in primitive:
        order = GR.accessor(document, body, primitive['indices']).reshape(-1).astype(np.int64)
    else:
        order = np.arange(len(positions), dtype=np.int64)
    faces = order[:len(order) - len(order) % 3].reshape(-1, 3)
    if len(faces) and (faces.min() < 0 or faces.max() >= len(positions)):
        return None, 'an index points past the vertices'
    a, b, c = positions[faces[:, 0]], positions[faces[:, 1]], positions[faces[:, 2]]
    ab, ac, bc = b - a, c - a, c - b
    cross = np.cross(ab, ac).reshape(-1, 3)
    length = np.sqrt(np.einsum('ij,ij->i', cross, cross))
    longest = np.maximum(np.maximum(np.einsum('ij,ij->i', ab, ab), np.einsum('ij,ij->i', ac, ac)),
                         np.einsum('ij,ij->i', bc, bc))
    degenerate = ((faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 0] == faces[:, 2])
                  | (length <= DEGENERATE * longest))
    if len(faces):
        corners = positions[faces].reshape(-1, 3)
        centre = (corners.min(axis=0) + corners.max(axis=0)) * .5
    else:
        centre = np.zeros(3)
    # About the primitive's own box centre, so an open part's figure does not hang on its origin.
    volume = np.einsum('ij,ij->i', a - centre, np.cross(b - centre, c - centre).reshape(-1, 3)) / 6.
    cosine = np.full(len(faces), np.nan)
    if normals is not None and len(faces):
        first, second, third = normals[faces[:, 0]], normals[faces[:, 1]], normals[faces[:, 2]]
        total = first + second + third
        total_length = np.sqrt(np.einsum('ij,ij->i', total, total))
        scale = sum(np.sqrt(np.einsum('ij,ij->i', n, n)) for n in (first, second, third))
        evidence = ~degenerate & (scale > 0) & (total_length > CANCELLED * scale)
        cosine[evidence] = (np.einsum('ij,ij->i', cross[evidence], total[evidence])
                            / (length[evidence] * total_length[evidence]))
    return {'order': order, 'faces': faces, 'vertices': len(positions), 'positions': positions, 'cross': cross,
            'area': .5 * length, 'degenerate': degenerate, 'volume': volume, 'cosine': cosine}, None


def _material(document, primitive):
    index = primitive.get('material')
    materials = document.get('materials') or []
    if isinstance(index, int) and 0 <= index < len(materials):
        return index, materials[index]
    return index, {}


def _weld(measured):
    """Vertex ids welded by exact position (cached): split normals and UV seams do not part a surface."""
    if 'weld' not in measured:
        positions = measured['positions']
        order = np.lexsort(positions.T[::-1])
        ordered = positions[order]
        new = np.ones(len(positions), bool)
        new[1:] = np.any(ordered[1:] != ordered[:-1], axis=1)
        weld = np.empty(len(positions), np.int64)
        weld[order] = np.cumsum(new) - 1
        measured['weld'] = weld
    return measured['weld']


def _paired_back_faces(measured, opposing, min_cos):
    """The opposing triangles that are the back of a two-sided card: the same three positions stand in the
    primitive wound the other way, and that twin is not reversed itself. A card built as a front face and
    a back copy that kept the front's normals reads as a backwards back copy; reversing it would lay it on
    its front, and the card would vanish from behind (the Grey Moors scrub)."""
    key = ('paired', min_cos)
    if key not in measured:
        ids = _weld(measured)[measured['faces']]
        valid = (~measured['degenerate'] & (ids[:, 0] != ids[:, 1]) & (ids[:, 1] != ids[:, 2])
                 & (ids[:, 0] != ids[:, 2]))
        # A cyclic rotation of the sorted ids is an even permutation: two of the three pairs ascend.
        even = ((ids[:, 0] < ids[:, 1]).astype(np.int8) + (ids[:, 1] < ids[:, 2]) + (ids[:, 2] < ids[:, 0])) == 2
        corners = np.sort(ids, axis=1)
        count = int(ids.max()) + 1 if len(ids) else 1
        if count < 2 ** 20:
            _, group = np.unique((corners[:, 0] * count + corners[:, 1]) * count + corners[:, 2], return_inverse=True)
        else:
            _, group = np.unique(corners, axis=0, return_inverse=True)
        group = group.reshape(-1)
        kept = valid & ~opposing
        size = int(group.max()) + 1 if len(group) else 0
        kept_even = np.bincount(group[kept & even], minlength=size)
        kept_odd = np.bincount(group[kept & ~even], minlength=size)
        measured[key] = opposing & valid & np.where(even, kept_odd[group] > 0, kept_even[group] > 0)
    return measured[key]


def _sheets(measured):
    """(sheet per triangle, -1 when degenerate; closed per sheet). A sheet is the triangles joined across
    welded edges that exactly two of them share and traverse in opposite directions, so it is wound one
    way round its surface; where a reversed part meets a correct one they traverse their shared edges the
    same way, and part. A sheet is closed when every edge of it is such a joint within it."""
    if 'sheets' not in measured:
        ids = _weld(measured)[measured['faces']]
        valid = (~measured['degenerate'] & (ids[:, 0] != ids[:, 1]) & (ids[:, 1] != ids[:, 2])
                 & (ids[:, 0] != ids[:, 2]))
        labels = np.full(len(ids), -1, np.int64)
        closed = np.zeros(0, bool)
        index = np.flatnonzero(valid)
        if len(index):
            start, stop = ids[index].reshape(-1), ids[index][:, [1, 2, 0]].reshape(-1)
            owner = np.repeat(index, 3)
            key = np.minimum(start, stop) * (int(ids.max()) + 1) + np.maximum(start, stop)
            order = np.argsort(key, kind='stable')
            ordered = key[order]
            first = np.flatnonzero(np.r_[True, ordered[1:] != ordered[:-1]])
            sharing = np.diff(np.r_[first, len(ordered)])
            shared = first[sharing == 2]
            one, two = order[shared], order[shared + 1]
            opposite = (start[one] < stop[one]) != (start[two] < stop[two])
            graph = coo_matrix((np.ones(int(opposite.sum()), np.int8), (owner[one[opposite]], owner[two[opposite]])),
                               shape=(len(ids), len(ids)))
            component = connected_components(graph, directed=False)[1]
            labels[index] = component[index]
            # An edge that is not one of those joints is a rim of every sheet it touches.
            rim = np.repeat(sharing != 2, sharing)[np.argsort(order, kind='stable')]
            rim[one[~opposite]] = rim[two[~opposite]] = True
            closed = np.bincount(labels[owner[rim]], minlength=int(component.max()) + 1) == 0
        measured['sheets'] = (labels, closed)
    return measured['sheets']


def _relit_vertices(measured, relit):
    """(mask of the vertices whose normals turn, how many vertices of the relit triangles keep theirs): a vertex
    turns when every readable triangle of the primitive that uses it is relit; one shared with any other triangle
    keeps its normal, which that triangle is lit by."""
    faces, valid = measured['faces'], ~measured['degenerate']
    used = np.zeros(measured['vertices'], bool)
    other = np.zeros(measured['vertices'], bool)
    used[faces[relit].reshape(-1)] = True
    other[faces[valid & ~relit].reshape(-1)] = True
    return used & ~other, int((used & other).sum())


def _record(document, mesh, number, primitive, measured, reason, min_cos):
    """(the report record, the triangles the default rule reverses, the triangles whose normals turn) of one primitive."""
    material_index, material = _material(document, primitive)
    attributes = primitive.get('attributes') or {}
    mode = primitive.get('mode', TRIANGLES)
    record = {'mesh': mesh, 'primitive': number, 'mesh_name': document['meshes'][mesh].get('name'),
              'material': material_index, 'material_name': material.get('name'), 'mode': mode, 'status': None,
              'triangles': 0, 'degenerate_triangles': 0, 'area': 0., 'disagreeing_area_share': None,
              'opposing_triangles': 0, 'opposing_area': 0., 'ambiguous_triangles': 0, 'no_evidence_triangles': 0,
              'paired_back_faces': 0, 'paired_back_face_area': 0., 'outvoted_triangles': 0, 'outvoted_area': 0.,
              'enclosing_triangles': 0, 'authored_triangles': 0, 'water_kept_triangles': 0, 'carried_triangles': 0,
              'flipped_triangles': 0, 'flipped_area': 0., 'signed_volume': None, 'corrected_signed_volume': None,
              'relit_triangles': 0, 'relit_area': 0., 'relit_vertices': 0, 'relit_shared_vertices': 0,
              'has_normals': 'NORMAL' in attributes, 'double_sided': bool(material.get('doubleSided', False))}
    if mode != TRIANGLES:
        record['status'] = 'not_triangles'
        return record, None, None
    if measured is None:
        record.update(status='unreadable', reason=reason)
        return record, None, None
    cosine, area, volume = measured['cosine'], measured['area'], measured['volume']
    with np.errstate(invalid='ignore'):
        opposing = cosine < min_cos
        disagreeing = cosine < 0
    total = float(area.sum())
    record.update(triangles=len(cosine), degenerate_triangles=int(measured['degenerate'].sum()), area=total,
                  opposing_triangles=int(opposing.sum()), opposing_area=float(area[opposing].sum()),
                  ambiguous_triangles=int((disagreeing & ~opposing).sum()),
                  signed_volume=float(volume.sum()))
    if record['has_normals']:
        record['disagreeing_area_share'] = float(area[disagreeing].sum()) / total if total > 0 else 0.
        record['no_evidence_triangles'] = int((~measured['degenerate'] & np.isnan(cosine)).sum())
    flip = np.zeros(len(cosine), bool)
    relit = np.zeros(len(cosine), bool)
    if not record['has_normals']:
        record['status'] = 'no_normals'
    elif record['double_sided']:
        record['status'] = 'double_sided'
    elif record['opposing_triangles']:
        paired = _paired_back_faces(measured, opposing, min_cos)
        sheets, closed = _sheets(measured)
        member = sheets >= 0
        of_sheet = np.maximum(sheets, 0)
        # Each sheet turns as a whole when its area-weighted mean cosine is below min_cos. A lone triangle
        # is its own sheet (the plain rule); a crease whose smoothed normals point the wrong way inside a
        # surface wound consistently one way is outvoted by that surface.
        voters = member & ~np.isnan(cosine) & ~paired
        weight = np.bincount(sheets[voters], weights=area[voters], minlength=len(closed))
        lean = np.bincount(sheets[voters], weights=(cosine * area)[voters], minlength=len(closed))
        backwards = lean < min_cos * weight
        # A closed sheet enclosing a positive volume is wound outward already: there the normals are the
        # wrong side (a top-down lathe closed at both ends), and reversing it would turn the solid inside out.
        enclosing = closed & (np.bincount(sheets[member], weights=volume[member], minlength=len(closed)) > 0)
        flip = member & (backwards & ~enclosing)[of_sheet] & ~paired
        kept_closed = member & (backwards & enclosing)[of_sheet] & ~paired
        water_kept = np.zeros(len(cosine), bool)
        if WATER_WORD in re.split(r'[^a-z]+', str(record['material_name'] or '').lower()):
            # Only the triangles whose winding is in question: opposing their normals, or reversed with their sheet.
            rise = measured['cross'][:, 1] / np.maximum(2. * area, 1e-300)
            level = member & (np.abs(rise) >= LEVEL) & ~closed[of_sheet] & (opposing | flip)
            water_kept = level & flip & (rise > 0)
            flip = (flip & ~level) | (level & (rise < 0) & ~paired)
        authored = flip & str(record['mesh_name'] or '').startswith(KEEP_WINDING) & ~closed[of_sheet]
        flip &= ~authored
        # A sheet that keeps its winding against its normals by rule (an authored clockwise lathe, level water
        # facing up) shows the side its normals turn away from, so it is lit from behind: its normals turn.
        relit = authored | water_kept
        outvoted = opposing & ~paired & ~flip & ~kept_closed & ~authored & ~water_kept
        record.update(paired_back_faces=int(paired.sum()), paired_back_face_area=float(area[paired].sum()),
                      outvoted_triangles=int(outvoted.sum()), outvoted_area=float(area[outvoted].sum()),
                      enclosing_triangles=int((kept_closed & opposing).sum()), authored_triangles=int(authored.sum()),
                      water_kept_triangles=int(water_kept.sum()), carried_triangles=int((flip & ~opposing).sum()),
                      status='corrected' if flip.any() else 'authored_winding' if authored.any()
                      else 'water_up' if water_kept.any() else 'outvoted' if (opposing & ~paired).any() else 'two_sided')
    else:
        record['status'] = 'consistent'
    record.update(flipped_triangles=int(flip.sum()), flipped_area=float(area[flip].sum()),
                  corrected_signed_volume=float(volume.sum() - 2. * volume[flip].sum()))
    if relit.any():
        turned, shared = _relit_vertices(measured, relit)
        record.update(relit_triangles=int(relit.sum()), relit_area=float(area[relit].sum()),
                      relit_vertices=int(turned.sum()), relit_shared_vertices=shared)
    return record, flip, relit


def _survey(document, body, meshes, min_cos):
    """(record, geometry, flip mask, relit mask) per primitive of ``meshes``; shared geometry is measured once."""
    measured_by_key = {}
    for mesh in meshes:
        for number, primitive in enumerate(document['meshes'][mesh].get('primitives') or []):
            measured, reason, first = None, None, None
            if primitive.get('mode', TRIANGLES) == TRIANGLES:
                key = _geometry_key(primitive)
                if key not in measured_by_key:
                    measured_by_key[key] = (*_measure(document, body, primitive), (mesh, number))
                measured, reason, first = measured_by_key[key]
            record, flip, relit = _record(document, mesh, number, primitive, measured, reason, min_cos)
            if first is not None and first != (mesh, number):
                record['shared_geometry'] = list(first)
            yield record, measured, flip, relit


def _mesh_uses(document, nodes):
    """{mesh: [node, ...]} with a node repeated once per occurrence in ``nodes`` (every mesh node once when None)."""
    all_nodes = document.get('nodes') or []
    uses = {}
    for node in (range(len(all_nodes)) if nodes is None else nodes):
        mesh = all_nodes[int(node)].get('mesh')
        if mesh is not None:
            uses.setdefault(mesh, []).append(int(node))
    return uses


def _cofactor(linear):
    """C with (L u) x (L v) = C (u x v), singular L included."""
    l0, l1, l2 = linear[:, 0], linear[:, 1], linear[:, 2]
    return np.stack([np.cross(l1, l2), np.cross(l2, l0), np.cross(l0, l1)], axis=1)


def _closed(measured):
    """Every edge of the welded (by exact position) triangles is shared by exactly two of them."""
    faces = measured['faces'][~measured['degenerate']]
    if len(faces) < 4:
        return False
    weld = _weld(measured)
    faces = weld[faces]
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    if len(faces) < 4:
        return False
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges[:, 0] * (int(weld.max()) + 1) + edges[:, 1], return_counts=True)
    return bool(np.all(counts == 2))


def winding_report(document, body, nodes=None, *, min_cos=MIN_COS):
    """Per triangle primitive: {mesh, primitive, triangles, area, disagreeing_area_share, flipped_triangles,
    signed_volume, has_normals, double_sided} and more.

    ``nodes`` limits the report to the meshes those node indices carry (repeat a node once per exported
    instance); None reports every mesh. Areas and volumes are in the mesh's own space; ``world_area`` and
    ``world_flipped_area`` sum each instance's world transform over ``nodes``. ``disagreeing_area_share`` is
    the area whose geometric normal points against the summed vertex normals (cosine below 0);
    ``flipped_triangles`` and ``flipped_area`` are what ``normalise_winding`` reverses on a single-sided
    primitive with normals: the sheets whose area-weighted mean cosine is below ``min_cos``, less the back
    copies of two-sided cards (``paired_back_faces``), closed sheets already enclosing a positive volume
    (``enclosing_triangles``) and open sheets of meshes named in KEEP_WINDING (``authored_triangles``); on a
    water material a level triangle of an open sheet is reversed exactly when it faces down
    (``water_kept_triangles``: those the vote would have turned down). ``opposing_*`` count the triangles
    whose own cosine is below ``min_cos`` on every primitive, left alone or not; ``outvoted_*`` those of
    them their sheet's vote keeps, ``carried_triangles`` those reversed without opposing on their own.
    ``status`` is one of STATUSES (``outvoted``: opposing triangles, none reversed; ``two_sided``: every
    opposing triangle is a paired back face; ``authored_winding``: a KEEP_WINDING mesh the rule would have
    reversed; ``water_up``: water already facing up); ``signed_volume`` is taken about the primitive's box
    centre and ``corrected_signed_volume`` after the reversal, which for a ``closed`` primitive is its
    enclosed volume (negative: wound inward).
    """
    uses = _mesh_uses(document, nodes)
    meshes = range(len(document.get('meshes') or [])) if nodes is None else sorted(uses)
    matrices = GR.hierarchy(document)[0] if uses else {}
    records = []
    for record, measured, flip, _ in _survey(document, body, meshes, min_cos):
        instances = uses.get(record['mesh'], [])
        names = []
        for node in instances:
            name = document['nodes'][node].get('name')
            if name is not None and name not in names:
                names.append(name)
        record.update(nodes=sorted(set(instances)), node_names=names[:8], instances=len(instances),
                      world_area=0., world_flipped_area=0., closed=None)
        if measured is not None:
            record['closed'] = _closed(measured)
            for node in instances:
                cross = measured['cross'] @ _cofactor(matrices[node][:3, :3]).T
                world = np.sqrt(np.einsum('ij,ij->i', cross, cross))
                record['world_area'] += .5 * float(world.sum())
                record['world_flipped_area'] += .5 * float(world[flip].sum())
        records.append(record)
    return records


def normalise_winding(document, body, *, min_cos=MIN_COS):
    """(private document copy, body, report): every backwards triangle reversed in new index accessors, and the
    sheets kept against their normals by rule relit in new normal accessors.

    A triangle is reversed (its last two indices swapped) when the cosine between its geometric normal
    and the sum of its vertex normals is below ``min_cos``, decided per sheet by the area-weighted mean
    (see the module docstring), unless it is the back copy of a two-sided card (its exact opposite twin in
    the primitive is not reversed), its sheet is closed round a positive volume, or it lies in an open sheet
    of a mesh named in KEEP_WINDING; level water faces up. Each corrected primitive points at a new index
    accessor, of the original component type,
    on a new buffer view appended to a new body at a 4-byte boundary; a primitive without indices gets its
    first index accessor. The triangles that keep their winding against their normals by rule, the open sheets
    of a KEEP_WINDING mesh the vote would have reversed and the level water facing up (``relit_triangles``),
    show the side their normals turn away from and would be lit from behind: their vertex normals are negated
    in a new float VEC3 NORMAL accessor on a new buffer view of the same body, except at a vertex a triangle
    outside that set also uses, which keeps its normal (``relit_shared_vertices``). Untouched primitives keep
    their accessors, geometry shared by several meshes gets one new accessor of each kind, and the input
    document and body are never modified. When nothing needs reversing or relighting the body comes back as it
    was (as bytes).

    The report: ``records`` (winding_report's per-primitive records without the node and world fields),
    ``primitives``, ``corrected_primitives``, ``corrected_geometries``, ``triangles``, ``flipped_triangles``,
    ``area``, ``flipped_area``, ``paired_back_faces``, ``outvoted_triangles``, ``enclosing_triangles``,
    ``authored_triangles``, ``carried_triangles`` (geometry counted once, mesh space), ``relit_primitives``,
    ``relit_geometries``, ``relit_triangles``, ``relit_area``, ``relit_vertices``, ``relit_shared_vertices``,
    ``left_alone`` (primitives per status that is left alone), ``left_alone_opposing`` (those among them with
    triangles the rule would have reversed), ``appended_bytes`` and ``seconds``.
    """
    started = time.perf_counter()
    result = _private(document)
    source = body if isinstance(body, bytes) else bytes(body)
    chunks, length = [], len(source)
    written, relit_written, records, counted = {}, {}, [], set()
    kept = ('paired_back_faces', 'outvoted_triangles', 'enclosing_triangles', 'authored_triangles', 'water_kept_triangles',
            'carried_triangles')
    relit_totals = ('relit_triangles', 'relit_area', 'relit_vertices', 'relit_shared_vertices')
    totals = {'triangles': 0, 'flipped_triangles': 0, 'area': 0., 'flipped_area': 0., **dict.fromkeys(kept, 0),
              **dict.fromkeys(relit_totals, 0)}

    def append(data, target, accessor):
        """Append ``data`` to the new body on its own buffer view and ``accessor`` over it; its accessor index."""
        nonlocal length
        padding = (-length) % 4
        if padding:
            chunks.append(bytes(padding))
            length += padding
        view = {'buffer': 0, 'byteOffset': length, 'byteLength': len(data)}
        if target is not None:
            view['target'] = target
        chunks.append(data)
        length += len(data)
        result.setdefault('bufferViews', []).append(view)
        accessor['bufferView'] = len(result['bufferViews']) - 1
        result.setdefault('accessors', []).append(accessor)
        return len(result['accessors']) - 1

    for record, measured, flip, relit in _survey(document, body, range(len(document.get('meshes') or [])), min_cos):
        records.append(record)
        original = document['meshes'][record['mesh']]['primitives'][record['primitive']]
        key = _geometry_key(original)
        if measured is not None and key not in counted:
            counted.add(key)
            for name in ('triangles', 'area', *kept):
                totals[name] += record[name]
        primitive = result['meshes'][record['mesh']]['primitives'][record['primitive']]
        if record['status'] == 'corrected' and key in written:
            primitive['indices'] = record['indices'] = written[key]
        elif record['status'] == 'corrected':
            totals['flipped_triangles'] += record['flipped_triangles']
            totals['flipped_area'] += record['flipped_area']
            order = measured['order'].copy()
            faces = order[:3 * len(flip)].reshape(-1, 3)
            faces[flip] = faces[flip][:, [0, 2, 1]]
            if 'indices' in original:
                old = document['accessors'][original['indices']]
                component = old['componentType']
                target = document['bufferViews'][old['bufferView']].get('target')
                accessor = {name: _private(value) for name, value in old.items() if name not in ('bufferView', 'byteOffset')}
            else:
                # The largest value of a component type is reserved (primitive restart).
                component = 5123 if measured['vertices'] <= 65535 else 5125
                target = ELEMENT_ARRAY_BUFFER
                accessor = {'componentType': component, 'count': len(order), 'type': 'SCALAR'}
                if len(order):
                    accessor.update(min=[int(order.min())], max=[int(order.max())])
            primitive['indices'] = record['indices'] = written[key] = append(
                order.astype(INDEX_TYPES[component]).tobytes(), target, accessor)
        if not record['relit_triangles']:
            continue
        if key in relit_written:
            primitive['attributes']['NORMAL'] = record['normals'] = relit_written[key]
            continue
        old = document['accessors'][original['attributes']['NORMAL']]
        if old.get('componentType') != 5126 or old.get('type') != 'VEC3':
            record['relit_refused'] = 'normals are not float VEC3'
            continue
        for name in relit_totals:
            totals[name] += record[name]
        turned, _ = _relit_vertices(measured, relit)
        normals = np.array(GR.accessor(document, body, original['attributes']['NORMAL']), dtype='<f4')
        normals[turned] *= -1.
        primitive['attributes']['NORMAL'] = record['normals'] = relit_written[key] = append(
            normals.tobytes(), ARRAY_BUFFER, {'componentType': 5126, 'count': len(normals), 'type': 'VEC3'})
    if chunks:
        source = b''.join([source, *chunks])
        if result.get('buffers'):
            result['buffers'][0]['byteLength'] = len(source)
        else:
            result['buffers'] = [{'byteLength': len(source)}]
    left_alone = {status: sum(1 for r in records if r['status'] == status) for status in LEFT_ALONE}
    report = {'min_cos': min_cos, 'primitives': len(records),
              'corrected_primitives': sum(1 for r in records if r['status'] == 'corrected'),
              'corrected_geometries': len(written), **totals,
              'relit_primitives': sum(1 for r in records if 'normals' in r), 'relit_geometries': len(relit_written),
              'left_alone': left_alone,
              'left_alone_opposing': {status: sum(1 for r in records if r['status'] == status and r['opposing_triangles'])
                                      for status in LEFT_ALONE},
              'appended_bytes': len(source) - len(body), 'seconds': time.perf_counter() - started, 'records': records}
    return result, source, report


def double_sided_sheets(document, sheets=None):
    """(document, report): one territory's authored open sheets set to render from both sides.

    ``sheets`` is the territory's DOUBLE_SIDED_SHEETS entry ({'materials': names, 'meshes': (mesh pattern,
    material name) pairs}); with none the document comes back as it is. A listed material turns doubleSided
    wherever a material of that name is defined. A listed pair re-points each primitive of a mesh whose name
    matches the pattern (fnmatch, case-sensitive) and whose material has the pair's name at a doubleSided copy
    of that material, one copy per source material appended to ``materials`` with its name kept; a primitive
    whose material is double-sided already keeps it. The result is a new document dict with its own
    ``materials`` list and copies of the meshes it re-points; the input document is never modified. The report:
    ``materials`` (names turned), ``primitives`` ([mesh name, primitive number, material name] re-pointed),
    ``copies`` ({source material index: copy index}) and ``unmatched`` (materials and pairs that name nothing in
    this document). Refuses an entry with keys other than SHEET_TABLE_KEYS.
    """
    import fnmatch
    report = {'materials': [], 'primitives': [], 'copies': {}, 'unmatched': []}
    if not sheets:
        return document, report
    unknown = sorted(set(sheets) - set(SHEET_TABLE_KEYS))
    if unknown:
        raise ValueError(f'double-sided sheets: unknown key(s) {unknown}; an entry carries {list(SHEET_TABLE_KEYS)}')
    result = dict(document)
    source = document.get('materials') or []
    materials = result['materials'] = [dict(material) for material in source]
    for name in sheets.get('materials', ()):
        indices = [index for index, material in enumerate(source) if material.get('name') == name]
        if not indices:
            report['unmatched'].append(name)
            continue
        for index in indices:
            materials[index]['doubleSided'] = True
        report['materials'].append(name)
    meshes = result['meshes'] = list(document.get('meshes') or [])
    copies = report['copies']
    for pattern, material_name in sheets.get('meshes', ()):
        matched = False
        for number, mesh in enumerate(document.get('meshes') or []):
            if not fnmatch.fnmatchcase(str(mesh.get('name') or ''), pattern):
                continue
            for part, primitive in enumerate(mesh.get('primitives') or []):
                index = primitive.get('material')
                if not isinstance(index, int) or not 0 <= index < len(source) or source[index].get('name') != material_name:
                    continue
                matched = True
                if materials[index].get('doubleSided'):
                    continue
                if index not in copies:
                    twin = _private(source[index])
                    twin['doubleSided'] = True
                    materials.append(twin)
                    copies[index] = len(materials) - 1
                if meshes[number] is mesh:
                    meshes[number] = dict(mesh, primitives=[dict(item) for item in mesh['primitives']])
                meshes[number]['primitives'][part]['material'] = copies[index]
                report['primitives'].append([mesh.get('name'), part, material_name])
        if not matched:
            report['unmatched'].append([pattern, material_name])
    return result, report


# ------------------------------------------------------------------ the audit command
def _summary_record(record):
    keys = ('mesh', 'mesh_name', 'node_names', 'instances', 'material_name', 'status', 'triangles', 'flipped_triangles',
            'disagreeing_area_share', 'world_area', 'world_flipped_area', 'area', 'flipped_area', 'signed_volume',
            'corrected_signed_volume', 'closed')
    return {key: record.get(key) for key in keys}


def audit_region(folder, *, min_cos=MIN_COS, top=10):
    """One library's winding audit: the correction timed as content.load would run it, then measured and re-measured."""
    path = Path(folder) / 'library.glb'
    started = time.perf_counter()
    document, body = S.GR.load(path)
    loaded = time.perf_counter()
    corrected, corrected_body, summary = normalise_winding(document, body, min_cos=min_cos)
    normalised = time.perf_counter()
    before = winding_report(document, body, min_cos=min_cos)
    after = winding_report(corrected, corrected_body, min_cos=min_cos)
    remaining = sum(r['flipped_triangles'] for r in after)
    unique = [r for r in before if 'shared_geometry' not in r]
    reversed_volumes = [r for r in unique if r['closed'] and r['status'] == 'corrected'
                        and r['signed_volume'] > 0 > r['corrected_signed_volume']]
    ranked = sorted((r for r in before if r['world_flipped_area'] > 0), key=lambda r: -r['world_flipped_area'])
    left = {status: [_summary_record(r) for r in before if r['status'] == status and r['opposing_triangles']]
            for status in LEFT_ALONE}
    return {'library_glb': str(path), 'library_glb_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'min_cos': min_cos,
            'primitives': summary['primitives'], 'corrected_primitives': summary['corrected_primitives'],
            'corrected_geometries': summary['corrected_geometries'],
            'triangles': summary['triangles'], 'flipped_triangles': summary['flipped_triangles'],
            'area': summary['area'], 'flipped_area': summary['flipped_area'],
            'world_area': sum(r['world_area'] for r in before),
            'world_flipped_area': sum(r['world_flipped_area'] for r in before),
            'left_alone': summary['left_alone'], 'left_alone_opposing': summary['left_alone_opposing'],
            'paired_back_faces': summary['paired_back_faces'], 'outvoted_triangles': summary['outvoted_triangles'],
            'enclosing_triangles': summary['enclosing_triangles'], 'authored_triangles': summary['authored_triangles'],
            'water_kept_triangles': summary['water_kept_triangles'],
            'carried_triangles': summary['carried_triangles'], 'appended_bytes': summary['appended_bytes'],
            'seconds': {'load': loaded - started, 'normalise': normalised - loaded},
            'verified': {'remaining_flipped_triangles': remaining,
                         'closed_primitives_whose_volume_sign_the_correction_reverses': [_summary_record(r) for r in reversed_volumes]},
            'top_meshes': [_summary_record(r) for r in ranked[:top]],
            'left_alone_with_opposing_triangles': left,
            'corrected': [_summary_record(r) for r in before if r['status'] == 'corrected']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--library', type=Path, required=True, help='Verified retained-content cache (<task root>/library)')
    parser.add_argument('--region', action='append', help='Audit only this region (repeatable); the report keeps other regions it already holds')
    parser.add_argument('--output', type=Path, help='Report path (default <library>/../experiments/winding-audit/report.json)')
    parser.add_argument('--min-cos', type=float, default=MIN_COS)
    parser.add_argument('--top', type=int, default=10, help='Meshes listed per region by world flipped area')
    args = parser.parse_args(argv)
    library = args.library.resolve()
    folders = ([library / region for region in args.region] if args.region
               else [p for p in sorted(library.iterdir()) if (p / 'library.glb').is_file()])
    missing = [str(folder) for folder in folders if not (folder / 'library.glb').is_file()]
    if missing:
        parser.error('no library.glb in ' + ', '.join(missing))
    output = (args.output or library.parent / 'experiments' / 'winding-audit' / 'report.json').resolve()
    report = {'schema': 1, 'generator': 'eloria-assets/maps/nymara-regions/_continent/winding.py',
              'library': str(library), 'regions': {}}
    if args.region and output.exists():
        previous = json.loads(output.read_text(encoding='utf-8'))
        if previous.get('schema') == 1:
            report['regions'] = previous.get('regions', {})
    for folder in folders:
        entry = audit_region(folder, min_cos=args.min_cos, top=args.top)
        report['regions'][folder.name] = entry
        left = entry['left_alone_opposing']
        print(f"{folder.name}: {entry['primitives']} primitives, {entry['corrected_primitives']} corrected; "
              f"{entry['flipped_triangles']:,} of {entry['triangles']:,} triangles flipped "
              f"({entry['world_flipped_area']:,.0f} of {entry['world_area']:,.0f} m2 placed); "
              f"left alone with backwards triangles: {left['double_sided']} double-sided, {left['two_sided']} two-sided cards, "
              f"{left['outvoted']} outvoted, {left['authored_winding']} authored winding, {left['water_up']} water up, "
              f"{left['no_normals']} without normals, {left['not_triangles'] + left['unreadable']} other; triangles kept: "
              f"{entry['paired_back_faces']} paired back faces, {entry['outvoted_triangles']} outvoted, "
              f"{entry['enclosing_triangles']} in closed outward sheets, {entry['authored_triangles']} authored, "
              f"{entry['water_kept_triangles']} level water facing up; {entry['carried_triangles']} carried; "
              f"normalise {entry['seconds']['normalise']:.2f} s, "
              f"+{entry['appended_bytes']:,} bytes; remaining after correction {entry['verified']['remaining_flipped_triangles']}",
              flush=True)
        for record in entry['top_meshes']:
            names = ', '.join(record['node_names'][:3]) + (' ...' if record['instances'] > 3 else '')
            print(f"    {record['mesh_name'] or record['mesh']}: {record['world_flipped_area']:,.0f} m2 flipped over "
                  f"{record['instances']} node(s) [{names}], {record['disagreeing_area_share']:.0%} of its area backwards", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f'Winding report: {output}', flush=True)


if __name__ == '__main__':
    main()
