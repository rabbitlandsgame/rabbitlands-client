"""Keep Mirrorhold's real footings while grading its open streets.

The initial city survey remains the terrain datum for its rigid architecture.
That survey also covers steep ground between compounds, which is not a building
foundation. Roads may grade those gaps while retaining actual object footprints.
Call after architectural support helpers and before foundation/road settlement.
"""
from __future__ import annotations

import numpy as np

REGION = 'mirrorhold'
MARGIN = 2.
# These formerly led to retired region edges or already have retained physical
# lake walkways. Civic streets and their yards are rebuilt on the shared ground.
EXCLUDED_ROADS = frozenset(('whitehorn-approach', 'barrens-approach',
    'high-cross-road', 'amber-gorge-road', 'lake-sanctuary', 'lake-city',
    'lake-westpier', 'lake-eastpier', 'sanctuary-approach'))
REQUIRED_ROADS = frozenset(('arrival-lane', 'quay-descent', 'civic-ascent',
                           'citadel-service-road', 'east-working-road'))


def actual_footprints(world, objects):
    """Conservative bounds of retained architecture, platforms and props.

    Bounds include open courtyards inside a building group. Protecting the full
    rectangle is deliberate: roads cannot excavate below a connected platform
    merely because there is no wall directly above the sample. Foreign objects
    remain protected too if their footprint overlaps the ownership boundary.
    """
    from assemblies import NATURE
    protected = np.zeros(world.height.shape, bool)
    retained = 0
    for obj in objects:
        if obj.get('kind') in NATURE:
            continue
        low = np.asarray(obj['low'], float)[[0, 2]] - MARGIN
        high = np.asarray(obj['high'], float)[[0, 2]] + MARGIN
        if not np.isfinite([low, high]).all() or np.any(high < low):
            raise ValueError('Mirror street footing requires finite actual bounds')
        ix0, ix1 = np.searchsorted(world.x, [low[0], high[0]], side='left')
        iz0, iz1 = np.searchsorted(world.z, [low[1], high[1]], side='left')
        ix1 = np.searchsorted(world.x, high[0], side='right')
        iz1 = np.searchsorted(world.z, high[1], side='right')
        protected[iz0:iz1, ix0:ix1] = True
        retained += obj.get('region') == REGION
    return protected, retained


def apply_mirror_street_footings(world, content):
    """Set road-only support weights without changing terrain or architecture."""
    if REGION in getattr(world, 'authoring_snapshots', {}):
        report = {'region': REGION, 'skipped': 'saved-authoring-authority'}
        world.mirror_streets = content.mirror_streets = report
        return report
    owned = world.owner_at(world.gx, world.gz) == world.ids.index(REGION)
    protected, retained = actual_footprints(world, content.objects)
    if not retained:
        raise ValueError('Mirror street grading requires retained architecture')
    weight = world.assembly_weight.copy()
    released = owned & ~protected & (weight > 0)
    weight[released] = 0.
    world.road_footing_weight = weight
    report = {'region': REGION, 'retainedObjects': int(retained),
              'footingMarginMetres': MARGIN,
              'protectedVertices': int(np.count_nonzero(owned & protected)),
              'releasedSurveyVertices': int(released.sum()),
              'policy': 'Initial city survey retained; roads grade open ground between actual architectural footings.'}
    world.mirror_streets = report
    content.mirror_streets = report
    return report


def add_mirror_streets(world, content):
    """Rebuild the civic circulation before continent/door route planning.

    These source surveys describe the streets around the retained architecture,
    including the quay descent and long east-side climb. They use the same rigid
    city translation as the buildings. The shared road solver sets final grades;
    source road meshes and former region edges are never copied into the world.
    """
    if REGION in getattr(world, 'authoring_snapshots', {}):
        report = {'region': REGION, 'streets': [],
                  'skipped': 'saved-authoring-authority'}
        world.mirror_circulation = report
        return report
    roads = content.metadata[REGION].get('authored_roads', [])
    by_id = {road['id']: road for road in roads}
    if not REQUIRED_ROADS <= by_id.keys():
        raise ValueError('Mirrorhold is missing its authored civic circulation')
    shift = np.asarray(content.assembly_records[REGION + '.city']['translation'], float)
    if shift.shape != (3,) or not np.isfinite(shift).all():
        raise ValueError('Mirror streets require the actual rigid city translation')
    existing = {road['id'] for road in world.roads}
    previous_distance = world.road_distance
    world.road_distance = np.full_like(previous_distance, np.inf)
    selected = []
    excluded = []
    for road in roads:
        if road['id'] in EXCLUDED_ROADS:
            continue
        identity = 'street-mirrorhold-' + road['id']
        if identity in existing:
            raise ValueError('Mirror civic street was already authored: ' + identity)
        points = np.asarray(road['waypoints'], float) + shift
        if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2 or not np.isfinite(points).all():
            raise ValueError('Invalid Mirror civic street survey: ' + road['id'])
        if np.any(world.owner_at(points[:, 0], points[:, 2]) != world.ids.index(REGION)):
            if road['id'] in REQUIRED_ROADS:
                raise ValueError('Required Mirror civic street leaves its retained territory: ' + road['id'])
            excluded.append({'source': road['id'], 'reason': 'Former peripheral yard route crosses the new territory boundary',
                             'globalSurvey': points.tolist()})
            continue
        width = float(road.get('width', 4.)) * .5
        world.add_road(points[:, [0, 2]], width=width, name=identity)
        selected.append({'id': identity, 'source': road['id'], 'widthMetres': width * 2,
                         'surveyStations': len(points), 'globalEndpoints': points[[0, -1]].tolist()})
    world.mirror_street_distance = world.road_distance.copy()
    world.road_distance = np.minimum(previous_distance, world.mirror_street_distance)
    report = {'cityTranslation': shift.tolist(), 'streets': selected,
              'excludedOutsideOwnership': excluded,
              'policy': 'Retained civic switchbacks and yards rebuilt as shared terrain roads; retired region exits and physical lake walks excluded.'}
    world.mirror_circulation = report
    return report


CIVIC_RUN_GAP_STATIONS = 2   # stations off the street inside a civic run that are a cut corner, not a departure


def trim_civic_approach(world, points):
    """Attach an exterior/door branch once, keeping existing streets narrow.

    The branch keeps its alignment from the station where it first leaves
    the civic network (a gap of up to CIVIC_RUN_GAP_STATIONS inside a street
    run is a cut corner). Trimming at the last civic station instead dropped
    everything between: with the terrain terms on, the verdant seam road
    left the streets at the hub, descended the bank, crossed the channel and
    touched the south-shore yard link once on its way to the seam; cut at
    that touch it lost its descent and its bridge, and the south shore stood
    unconnected (seventeen contract failures).
    """
    points = np.asarray(points, float)
    ix = np.clip(np.rint((points[:, 0] - world.x0) / 2).astype(int), 0, len(world.x) - 1)
    iz = np.clip(np.rint((points[:, 1] - world.z0) / 2).astype(int), 0, len(world.z) - 1)
    civic = world.mirror_street_distance[iz, ix] <= 1.25
    if len(points) < 3 or not civic[0]:
        return points
    last = 0
    for index in range(1, len(points)):
        if civic[index]:
            last = index
        elif index - last > CIVIC_RUN_GAP_STATIONS:
            break
    last = min(last, len(points) - 2)
    if last == 0:
        return points
    if not hasattr(world, 'mirror_street_attachments'):
        world.mirror_street_attachments = []
    world.mirror_street_attachments.append({'originalStart': points[0].tolist(),
        'attachment': points[last].tolist(), 'destination': points[-1].tolist(),
        'retainedCivicStations': last})
    return points[last:]


def grade_open_approach(world, content, name, start, stop, width=2., merge_length=0.):
    """Fit a local walking approach between two surveyed ground contacts.

    A two-metre triangle guard keeps all four actor samples within the actual
    ramp. The shoulder blends into open ground; every retained footing and its
    margin remain untouched. The centre contacts keep their original elevation.
    """
    start, stop = np.asarray(start, float), np.asarray(stop, float)
    if any(r.get('id')==name for r in world.roads):
        raise ValueError(name + ': approach has already been applied')
    direction = stop - start
    length = float(np.linalg.norm(direction))
    if length < 4:
        raise ValueError(name + ': walking approach needs two distinct contacts')
    levels = np.asarray(world.height_at(np.array([start[0], stop[0]]),
                                         np.array([start[1], stop[1]])))
    grade = float(abs(levels[1] - levels[0]) / length)
    if grade > .60:
        raise ValueError(name + ': contact elevations require a longer approach')
    along = ((world.gx-start[0])*direction[0]+(world.gz-start[1])*direction[1])/length**2
    fraction = np.clip(along, 0, 1)
    distance = np.hypot(world.gx-start[0]-fraction*direction[0],
                        world.gz-start[1]-fraction*direction[1])
    protected, _ = actual_footprints(world, content.objects)
    owned = world.owner_at(world.gx, world.gz) == world.ids.index(REGION)
    core = width + 2.
    blend = np.clip((core + 10. - distance)/10., 0., 1.)
    blend = blend*blend*(3.-2.*blend)
    if merge_length:
        merge = np.clip((1.-along)*length/merge_length,0.,1.)
        blend *= merge*merge*(3.-2.*merge)
    blend[protected | ~owned | world.water['mask']] = 0.
    target = levels[0] + fraction*(levels[1]-levels[0])
    before = world.height.copy()
    world.height += blend*(target-world.height)
    visible = (distance < width*2) & owned & ~world.water['mask']
    world.road_distance[visible] = np.minimum(world.road_distance[visible],distance[visible]/width)
    stations = np.linspace(0.,1.,max(2,int(np.ceil(length/2))+1))
    points = start+stations[:,None]*direction
    road = {'id':name,'width':width,'points':np.c_[points[:,0],
        levels[0]+stations*(levels[1]-levels[0]),points[:,1]].tolist()}
    world.roads.append(road)
    return {'id':name,'globalContacts':road['points'][::len(road['points'])-1],
            'grade':grade,'changedVertices':int(np.count_nonzero(before!=world.height)),
            'maximumFootingChange':float(np.max(abs(world.height[protected]-before[protected]),initial=0))}


def apply_mirror_access(world, content):
    """Finish the northern exploration trail and the working quay's bank path."""
    if REGION in getattr(world, 'authoring_snapshots', {}):
        report = {'region': REGION, 'paths': [],
                  'skipped': 'saved-authoring-authority'}
        world.mirror_access = content.mirror_access = report
        return report
    paths = [grade_open_approach(world, content, 'access-mirrorhold-north-plateau',
                                [854.,582.], [854.,622.])]
    # This service belongs on the retained quay beside the moored boats. Its
    # old coordinate fell on the reshaped hillside above the working harbour.
    if not hasattr(content, 'authored_actor_points'):
        content.authored_actor_points = {}
    quay = next(o for o in content.objects if o.get('region')==REGION and o['node']=='Landmark_Quay')
    point = np.array([(quay['low'][0]+quay['high'][0])*.5+5., 0., quay['high'][2]-2.])
    point[1] = float(world.height_at(point[0],point[2]))
    content.authored_actor_points[(REGION,'Quay Master Belen Tarr')] = point
    report = {'paths':paths,'quayMasterGlobal':point.tolist(),
              'policy':'Named civic approaches graded in open ground; retained footings and all original gameplay identities preserved.'}
    world.mirror_access = content.mirror_access = report
    return report
