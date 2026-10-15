"""Fit Westhaven's retained maritime architecture to one continental shore.

The quay and its work yards keep their surveyed local grades; water structures
keep a common sea datum. Two small, irregular support envelopes preserve those
contacts and blend into the global terrain. No old rectangular map is copied.
Call apply_westhaven_support after Content.load and before settle_foundations.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import ConvexHull

HARBOUR = 'westhaven.harbour'
LIGHTHOUSE = 'westhaven.lamp-island'
REFERENCES = {HARBOUR: ((34., 6.), 'water'), LIGHTHOUSE: ((260., 23.), 'water')}
TRANSLATIONS = {HARBOUR: (120., 0., 1120.), LIGHTHOUSE: (45., 0., 1130.)}

HARBOUR_PREFIXES = ('Quay_Wall_', 'Prop_Quay_', 'Jetty_', 'Ship_',
    'Mole_Run_', 'Prop_Mole_', 'Landmark_Mole_', 'Landmark_Warehouse_',
    'Landmark_Pier_', 'Landmark_Yard_Shed_', 'Prop_Timber_Stack_',
    'Prop_Fish_Stall_', 'House_lower_', 'Yard_lower_',
    'Prop_Lamp_quayside_', 'Prop_Lamp_market_climb_', 'Prop_Boat_',
    # The quay's working dressing: the chandlery stock beside Quay_Wall_06 and the loads at the warehouses and the
    # yard shed. As singles they were mapped and grounded apart from the harbour they dress, 46-76 m from their
    # buildings (asset audit, family D scattered props).
    'Prop_Chandlery_', 'Working_Load_')
HARBOUR_NODES = frozenset(('Landmark_Quay_Arch', 'Landmark_Fish_Market', 'Prop_Cistern_lower_square',
    'Landmark_Gantry', 'Landmark_Harbour_Crane', 'Landmark_Harbour_Gate',
    'Landmark_Custom_House', 'Landmark_Shipyard_Hull', 'Landmark_Ropewalk',
    'Landmark_Guild_Hall', 'Lore_league_post_house', 'Landmark_Gullstone_Watch',
    'Landmark_Sea_Arch', 'Landmark_Route_quay_mole_ramp',
    'Landmark_Route_yard_bridge', 'Landmark_Route_gullstone_bridge',
    'Secret_haven_ropewalk_garden', 'Secret_haven_guild_vault',
    'Secret_haven_mole_pit', 'Secret_haven_lamp_spring',
    'Secret_haven_shipyard_butts', 'Secret_haven_waystone',
    'Secret_haven_wrack_hollow', 'Secret_haven_smuggle',
    'Entry_bonded_vaults_door', 'Entry_gullstone_door'))
LIGHTHOUSE_NODES = frozenset(('Landmark_Route_lamp_causeway',
    'Landmark_Great_Lighthouse', 'Secret_haven_lighthouse_eyrie',
    'Entry_lamp_rock_door'))


def placement_group(placement):
    """Only the actual connected waterfront, its dressing and linked doors."""
    name = placement['node']
    if name in LIGHTHOUSE_NODES or (name.startswith('Prop_Boat_') and placement.get('position', [0])[0] >= 200):
        return LIGHTHOUSE
    if name in HARBOUR_NODES or name.startswith(HARBOUR_PREFIXES):
        return HARBOUR
    return None


@dataclass
class Envelope:
    equations: np.ndarray
    vertices: np.ndarray


def envelope(points):
    """Convex local shore envelope; returned half-planes have unit normals."""
    points = np.unique(np.asarray(points, float), axis=0)
    if len(points) < 3 or not np.isfinite(points).all():
        raise ValueError('Harbour support requires finite actual XZ bounds')
    hull = ConvexHull(points)
    return Envelope(hull.equations, points[hull.vertices])


def influence(x, z, equations, *, apron=5., feather=32.):
    """Smooth, bounded influence around an irregular architectural envelope."""
    x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
    signed = np.full(x.shape, -np.inf)
    for nx, nz, offset in equations.equations:
        signed = np.maximum(signed, nx*x+nz*z+offset)
    # A max half-plane distance alone underestimates distance beyond acute
    # corners, creating long support spikes outside the intended shoreline.
    distance = np.full(x.shape, np.inf)
    for a, b in zip(equations.vertices, np.roll(equations.vertices, -1, axis=0)):
        d = b-a
        u = np.clip(((x-a[0])*d[0]+(z-a[1])*d[1])/float(d@d), 0., 1.)
        distance = np.minimum(distance, np.hypot(x-a[0]-u*d[0], z-a[1]-u*d[1]))
    distance = np.where(signed <= 0., 0., distance)
    t = np.clip(1-np.maximum(0., distance-apron)/feather, 0., 1.)
    return t*t*(3-2*t)


def support_fields(x, z, translation, equations, source_height, *, feather=32.):
    translation = np.asarray(translation, float)
    if translation.shape != (3,) or not np.isfinite(translation).all():
        raise ValueError('Harbour support requires one finite XYZ translation')
    sx, sz = np.asarray(x)-translation[0], np.asarray(z)-translation[2]
    weight = influence(sx, sz, equations, feather=feather)
    target = np.asarray(source_height(sx, sz), float)+translation[1]
    if not np.isfinite(target).all():
        raise ValueError('Harbour foundation samples do not cover their support envelope')
    return target, weight


def _corners(objects, *, source=False):
    return np.array([[x, z] for obj in objects
        for x in (obj['low'][0]-(obj['shift'][0] if source else 0), obj['high'][0]-(obj['shift'][0] if source else 0))
        for z in (obj['low'][2]-(obj['shift'][2] if source else 0), obj['high'][2]-(obj['shift'][2] if source else 0))])


def _hull_below_water(document, body, obj, matrices):
    """Use the actual hull below its waterline, excluding masts and rigging."""
    import scene_io as S
    vertices = []
    for index in S.descendants(document, obj.get('indices', [obj['index']])):
        node = document['nodes'][index]
        if 'mesh' not in node:
            continue
        for part in document['meshes'][node['mesh']]['primitives']:
            p = S.GR.accessor(document, body, part['attributes']['POSITION'])
            matrix = matrices[index]
            p = p@matrix[:3, :3].T+matrix[:3, 3]
            p = p[p[:, 1] < .10]
            if len(p):
                vertices.append(p)
    if not vertices:
        raise ValueError(obj['node']+': floating boat has no actual submerged hull')
    vertices = np.vstack(vertices)
    return envelope(vertices[:, [0, 2]]), float(vertices[:, 1].min())-.45


def bridge_terminals(triangles):
    """Find the actual two crosswise open ends of a retained walk ribbon."""
    edges = {}
    for triangle in np.asarray(triangles, float):
        for a, b in zip(triangle, np.roll(triangle, -1, axis=0)):
            key = tuple(sorted((tuple(np.round(a, 6)), tuple(np.round(b, 6)))))
            edges.setdefault(key, []).append(np.array([a, b]))
    boundary = [values[0] for values in edges.values() if len(values) == 1]
    points = np.asarray(triangles)[:, :, [0, 2]].reshape(-1, 2)
    axis = np.linalg.eigh(np.cov(points.T))[1][:, -1]
    if axis[0] < 0:
        axis = -axis
    crosswise = []
    for edge in boundary:
        d = edge[1, [0, 2]]-edge[0, [0, 2]]
        if np.linalg.norm(d) > .5 and abs(float(d@axis))/np.linalg.norm(d) < .65:
            crosswise.append(edge)
    if len(crosswise) < 2:
        raise ValueError('Working harbour bridge has no distinct actual bank contacts')
    order = sorted(crosswise, key=lambda edge: float(edge[:, [0, 2]].mean(axis=0)@axis))
    return [order[0], order[-1]]


def contact_fields(x, z, edge, *, radius=2., feather=6.):
    """A short bank collar meets an actual deck end without filling its span."""
    a, b = np.asarray(edge, float)
    d = b[[0, 2]]-a[[0, 2]]
    u = np.clip(((x-a[0])*d[0]+(z-a[2])*d[1])/float(d@d), 0., 1.)
    distance = np.hypot(x-a[0]-u*d[0], z-a[2]-u*d[1])
    t = np.clip(1-np.maximum(distance-radius, 0.)/feather, 0., 1.)
    return a[1]+u*(b[1]-a[1]), t*t*(3-2*t)


def apply_westhaven_support(world, content):
    """Install one coherent bank/basin constraint per rigid maritime group.

    The wrapper deliberately fails if a generic ownership pull moved a group
    away from its authored shore. Plan sites and geometry must agree exactly.
    Existing library samples preserve real quay thresholds; hull-specific cuts
    protect depth under boats without filling the spans beneath piers or decks.
    """
    import scene_io as S
    objects = [obj for obj in content.objects if obj['region'] == 'westhaven']
    grouped = {identity: [obj for obj in objects if obj.get('assembly') == identity]
               for identity in TRANSLATIONS}
    if any(not members for members in grouped.values()):
        raise ValueError('Both Westhaven maritime assemblies must be loaded before shoreline support')
    ground = np.load(content.library/'westhaven/foundation-samples.npz')
    sample = RegularGridInterpolator((ground['z'], ground['x']), ground['height'],
                                     bounds_error=False, fill_value=None)
    def source_height(x, z):
        x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
        return sample(np.c_[z.ravel(), x.ravel()]).reshape(x.shape)
    document, body = content.documents['westhaven']
    matrices = S.GR.hierarchy(document)[0]
    report = {'policy': 'Rigid sea-level harbour and lighthouse; curved local bank and basin supports', 'assemblies': {}}
    ferry_exclusion = np.asarray(getattr(world, 'ferry_exclusion', np.zeros_like(world.height, bool)), bool).copy()
    for identity, members in grouped.items():
        shift = np.asarray(TRANSLATIONS[identity])
        if any(not np.allclose(obj['shift'], shift, rtol=0, atol=1e-7) for obj in members):
            raise ValueError(identity+': actual assembly translation differs from the fitted coast')
        if np.any(world.owner_at(*_corners(members).T) != world.ids.index('westhaven')):
            raise ValueError(identity+': actual architectural bounds leave Westhaven')
        corners = _corners(members, source=True)
        equations = envelope(corners)
        feather = 40. if identity == HARBOUR else 24.
        low, high = corners.min(axis=0)+shift[[0, 2]]-feather-8, corners.max(axis=0)+shift[[0, 2]]+feather+8
        ix0, iz0 = np.maximum(0, np.floor((low-[world.x0, world.z0])/2).astype(int))
        ix1, iz1 = np.minimum([len(world.x), len(world.z)], np.ceil((high-[world.x0, world.z0])/2).astype(int)+1)
        sl = np.s_[iz0:iz1, ix0:ix1]
        gx, gz = world.gx[sl], world.gz[sl]
        target, weight = support_fields(gx, gz, shift, equations, source_height, feather=feather)
        contacts = []
        for obj in members:
            if obj['node'] != 'Landmark_Route_yard_bridge':
                continue
            nodes = [i for i in S.descendants(document, [obj['index']])
                     if 'mesh' in document['nodes'][i] and document['nodes'][i].get('name', '').startswith('Walk_')]
            triangles = S.GR.triangles(document, body, nodes)+shift
            for edge in bridge_terminals(triangles):
                y, w = contact_fields(gx, gz, edge)
                target = target*(1-w)+y*w
                weight = np.maximum(weight, w)
                contacts.append(edge.tolist())
        berths = []
        for obj in members:
            if not obj['node'].startswith(('Ship_', 'Prop_Boat_')):
                continue
            if obj['node'].startswith('Prop_Boat_') and float(obj['source']['position'][1]) > .15:
                # Authored rowboats hauled onto the bank are work-yard props.
                # Their original ground contact belongs to the rigid survey.
                continue
            if abs(float(obj['source']['position'][1])) > .151:
                raise ValueError(obj['node']+': moored boat does not share the source sea datum')
            hull, bed = _hull_below_water(document, body, obj, matrices)
            # Feather outside the genuine submerged hull only. An entire ship
            # AABB includes empty corners that can cut into its adjacent quay.
            hull_weight = influence(gx-shift[0], gz-shift[2], hull, apron=.65, feather=2.)
            target = np.minimum(target, target*(1-hull_weight)+(bed+shift[1])*hull_weight)
            weight = np.maximum(weight, hull_weight)
            berths.append({'node': obj['node'], 'bedCeiling': bed+float(shift[1])})
        # Equal-weight local support replaces earlier generic per-footprint
        # accumulation; every member here used this same source survey datum.
        replace = weight >= world.assembly_weight[sl]
        world.assembly_target[sl] = np.where(replace, target, world.assembly_target[sl])
        world.assembly_weight[sl] = np.maximum(world.assembly_weight[sl], weight)
        for obj in members:
            if not obj['node'].startswith(('Ship_', 'Prop_Boat_', 'Jetty_', 'Quay_Wall_',
                    'Mole_Run_', 'Landmark_Pier_', 'Landmark_Route_', 'Landmark_Mole_')):
                continue
            # The separately authored passenger landing needs water of its
            # own; exclude existing working piers, boats and breakwaters.
            low, high = obj['low'][[0, 2]], obj['high'][[0, 2]]
            dx = np.maximum(np.maximum(low[0]-gx, gx-high[0]), 0.)
            dz = np.maximum(np.maximum(low[1]-gz, gz-high[1]), 0.)
            ferry_exclusion[sl] |= np.hypot(dx, dz) <= 4.
        report['assemblies'][identity] = {'translation': shift.tolist(), 'members': len(members),
            'sourceEnvelope': corners[ConvexHull(corners).vertices].tolist(),
            'featherMetres': feather, 'supportedVertices': int(np.count_nonzero(weight)),
            'berths': berths, 'bridgeBankContacts': contacts}
    content.westhaven_support = report
    world.westhaven_support = report
    world.ferry_exclusion = ferry_exclusion
    return report
