"""Decorative watercraft rest on the actual water or ground, wherever they stand.

The regional surveys placed every boat at the level its own map's water had;
on the continent that level, and often the ground, is different: Crownwater's
harbour boats stood buried under the raised island, a packet boat floated
three metres above its quay, Amberwood rowing boats hung ten metres over a
slope. ``manymouth_boats`` settles the independent delta dugouts; this module
does the same for every other decorative hull, standalone or inside a rigid
assembly, by a rigid Y translation only (``manymouth_boats.settle_hull``):
afloat on the clipped water surface when the whole footprint is navigable
water, hauled up on the ground otherwise, never buried. Rigging, masts and
cargo standing within a hull's footprint move with it. Assembly members keep
their XZ and their group's other members; the deviation is recorded.
Gameplay-linked hulls are left alone and listed.
"""
from __future__ import annotations
import re
import numpy as np

import scene_io as S
from manymouth_boats import settle_hull, terrain_contacts, water_coverage, SOURCE_WATER_LEVEL, _gameplay_linked
from terrain_export import sample_water_surface

# A hull hauled up across a slope (one end this far clear of the ground) may
# instead move to the nearest spot within reach where its whole footprint
# floats level: the legacy mooring became dry or raised ground on the continent.
SLOPE_SPREAD = 1.5
NUDGE_RADIUS = 12.
NUDGE_STEP = 1.
NUDGE_DIRECTIONS = 16


def nudge_to_water(world, triangles, faces):
    """Nearest XZ offset within reach where the whole footprint floats level, with its settle; None if none."""
    if getattr(world, 'water', None) is None:
        return None
    centre = triangles.reshape(-1, 3)[:, [0, 2]].mean(axis=0)
    for radius in np.arange(NUDGE_STEP, NUDGE_RADIUS + 1e-9, NUDGE_STEP):
        for k in range(NUDGE_DIRECTIONS):
            angle = 2 * np.pi * k / NUDGE_DIRECTIONS
            offset = np.array([radius * np.cos(angle), radius * np.sin(angle)])
            x, z = centre + offset
            wet, water = sample_water_surface(world, np.array([x]), np.array([z]))
            if not bool(wet[0]) or float(water[0] - world.height_at(x, z)) <= .35:
                continue
            moved = triangles + np.array([offset[0], 0., offset[1]])
            try:
                shift, record = settle_hull(world, moved, faces)
            except ValueError:
                continue
            if record['mode'] == 'afloat':
                return offset, shift, record
    return None

HULL = re.compile(r'boat|skiff|dugout|canoe|punt|lateen|packet|tender|barge|raft|wherry', re.I)
# A hull moored against a bank floats at the water line with its side or bow
# against the shore: most of its footprint is navigable water and the hull
# edge enters the bank slope by no more than a metre (the legacy quays these
# boats lay alongside became sloped banks on the continent).
MOORED_COVERAGE = .6
MOORED_INTRUSION = 1.


def settle_decorative_hull(world, triangles, faces):
    """settle_hull, plus a moored mode for a hull whose footprint meets the bank."""
    shift, record = settle_hull(world, triangles, faces)
    if record['mode'] == 'afloat' or record['waterLevelRange'] is None:
        return shift, record
    low_water, high_water = record['waterLevelRange']
    if record['footprintWaterCoverage'] < MOORED_COVERAGE or high_water - low_water > .12:
        return shift, record
    moored = (low_water + high_water) * .5 - SOURCE_WATER_LEVEL
    samples = terrain_contacts(world, triangles)
    intrusion = float(np.max(world.height_at(samples[:, 0], samples[:, 2]) - (samples[:, 1] + moored)))
    if intrusion > MOORED_INTRUSION:
        return shift, record
    record.update(mode='moored', sourceToWorldY=moored, bankIntrusionMetres=intrusion,
                  minimumGroundClearance=-intrusion, maximumGroundClearance=float(np.max(samples[:, 1] + moored - world.height_at(samples[:, 0], samples[:, 2]))))
    return moored, record
# Rigging, masts, sails, oars and cargo carry a hull word in their names but are companions, not hulls.
NOT_HULL = re.compile(r'rig|mast|sail|oar|cargo|net\b', re.I)
MANYMOUTH_OWN = re.compile(r'moored_boat_\d+')   # manymouth_boats.py settles these
COMPANION_HEIGHT_MARGIN = .5
POLICY = ('Rigid translation: afloat on the actual water surface with a complete navigable footprint, moored at '
          'the water line with the hull edge against the bank when most of the footprint is water, otherwise '
          'hauled up on the ground; a hull hauled up across a slope moves to the nearest spot within 12 m where '
          'it floats level, if one exists; companions within a hull footprint follow it; gameplay-linked hulls untouched.')


def hulls(content):
    """Decorative hull props anywhere, except the delta dugouts their own module settles."""
    saved=set(getattr(content,'authored_regions',()))
    return [o for o in content.objects
            if o.get('region') not in saved and o.get('kind') == 'prop' and
            not o.get('walk') and HULL.search(o.get('node', ''))
            and not NOT_HULL.search(o.get('node', ''))
            and not (o.get('region') == 'manymouth_delta' and MANYMOUTH_OWN.fullmatch(o.get('node', '')))]


def companions(content, hull, taken):
    """Other decorative props standing within the hull's footprint and height band."""
    low, high = hull['low'], hull['high']
    other_hulls = {id(o) for o in hulls(content)}
    result = []
    for o in content.objects:
        if o is hull or o.get('region') in getattr(content,'authored_regions',()) or \
                id(o) in taken or id(o) in other_hulls or o.get('kind') != 'prop' or o.get('walk'):
            continue
        if o.get('region') != hull.get('region'):
            continue
        centre = (o['low'] + o['high']) * .5
        if not (low[0] <= centre[0] <= high[0] and low[2] <= centre[2] <= high[2]):
            continue
        if not (low[1] - COMPANION_HEIGHT_MARGIN <= o['low'][1] <= high[1] + COMPANION_HEIGHT_MARGIN):
            continue
        result.append(o)
    return result


def hull_triangles(content, obj):
    document, body = content.documents[obj['region']]
    nodes = [i for i in S.descendants(document, obj.get('indices', [obj['index']])) if 'mesh' in document['nodes'][i]]
    source = S.GR.triangles(document, body, nodes)
    # Source Y already includes the authored flotation line; strip only the
    # obsolete terrain-following Y shift and keep the exact XZ.
    return source + np.array([obj['shift'][0], 0., obj['shift'][2]]) if len(source) else source


def water_faces(world):
    from terrain_export import clipped_water_surface
    nz, nx = world.height.shape
    row, col = np.indices((nz - 1, nx - 1))
    a = (row * nx + col).ravel()
    cells = np.stack((a, a + nx, a + 1, a + 1, a + nx, a + nx + 1), axis=1)
    points = np.c_[world.gx.ravel(), world.height.ravel(), world.gz.ravel()]
    mesh = clipped_water_surface(world, points, cells)
    return mesh['positions'][mesh['triangles']].astype(float)


def shift_object(content, obj, delta, offset=(0., 0.)):
    obj['shift'][0] += offset[0]
    obj['shift'][1] += delta
    obj['shift'][2] += offset[1]
    for key in ('low', 'high'):
        obj[key][0] += offset[0]
        obj[key][1] += delta
        obj[key][2] += offset[1]
    content.mapping[(obj['region'], obj['node'])] = obj['shift']
    content.bounds_by_name[(obj['region'], obj['node'])] = (obj['low'], obj['high'])


def apply_hull_settle(world, content, *, triangles=None, faces=None):
    """Run after content.reground and the delta dugouts, before export.

    ``triangles`` and ``faces`` let a test supply hull geometry and the water
    surface; the build reads them from the retained documents and the world.
    """
    selected = hulls(content)
    records, skipped = [], []
    if selected:
        water = faces if faces is not None else water_faces(world)
        taken = set()
        for obj in selected:
            template = content.templates.get(obj['region'], {})
            if obj.get('source', {}).get('landmark') or _gameplay_linked(template, obj.get('names', {obj['node']})):
                skipped.append({'region': obj['region'], 'node': obj['node'], 'reason': 'gameplay-linked'})
                continue
            geometry = triangles[obj['node']] if triangles is not None else hull_triangles(content, obj)
            if not len(geometry):
                skipped.append({'region': obj['region'], 'node': obj['node'], 'reason': 'no hull mesh'})
                continue
            try:
                new_y, record = settle_decorative_hull(world, geometry, water)
            except ValueError as error:
                skipped.append({'region': obj['region'], 'node': obj['node'], 'reason': str(error)})
                continue
            offset = (0., 0.)
            if record['mode'] == 'hauled-up' and record['maximumGroundClearance'] - record['minimumGroundClearance'] > SLOPE_SPREAD:
                nudged = nudge_to_water(world, geometry, water)
                if nudged is not None:
                    offset, new_y, record = (float(nudged[0][0]), float(nudged[0][1])), nudged[1], nudged[2]
            delta = new_y - float(obj['shift'][1])
            followers = companions(content, obj, taken)
            shift_object(content, obj, delta, offset)
            for other in followers:
                shift_object(content, other, delta, offset)
                taken.add(id(other))
            taken.add(id(obj))
            record.update(region=obj['region'], node=obj['node'], assembly=obj.get('assembly'), deltaY=delta,
                          movedXZ=list(offset), movedMetres=float(np.hypot(*offset)),
                          companions=[other['node'] for other in followers],
                          positionXZ=((obj['low'] + obj['high']) * .5)[[0, 2]].tolist())
            records.append(record)
    world.hull_settle = {'hulls': records, 'skipped': skipped,
        'afloat': sum(r['mode'] == 'afloat' for r in records), 'moored': sum(r['mode'] == 'moored' for r in records),
        'hauledUp': sum(r['mode'] == 'hauled-up' for r in records),
        'movedToWater': [{'region': r['region'], 'node': r['node'], 'metres': round(r['movedMetres'], 2)} for r in records if r['movedMetres'] > 0],
        'restingOnSlopes': [{'region': r['region'], 'node': r['node'], 'spreadMetres': round(r['maximumGroundClearance'] - r['minimumGroundClearance'], 2)}
                            for r in records if r['mode'] == 'hauled-up' and r['maximumGroundClearance'] - r['minimumGroundClearance'] > 1.5],
        'assemblyDeviations': sum(1 for r in records if r['assembly'] and abs(r['deltaY']) > 1e-9),
        'maximumMoveMetres': max((abs(r['deltaY']) for r in records), default=0.), 'policy': POLICY}
    return world.hull_settle
