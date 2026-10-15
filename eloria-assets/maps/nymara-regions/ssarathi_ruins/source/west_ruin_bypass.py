"""Keep the western public causeway outside the old ruin's standing walls."""
import numpy as np
from amberwood import mesh as M
from verify_runtime import VerticalRayIndex


def _landing_cap(build, road):
    """A short masonry slab joins the bank to the native deck over water.

    The shared deck ends at local X=-107.5 with its existing 0.8 m stone
    thickness. The last half metre of new road crosses water before reaching
    it. Side faces and a soffit make that contact a visible structural span;
    the existing/new walking skins supply the single top surface.
    """
    x0, x1, z0, z1, bottom, top = -108., -106.75, -77.75, -69.25, 3.2, 4.
    faces = [
        [(x0,bottom,z0),(x1,bottom,z0),(x1,top,z0),(x0,top,z0)],
        [(x1,bottom,z1),(x0,bottom,z1),(x0,top,z1),(x1,top,z1)],
        [(x0,bottom,z1),(x0,bottom,z0),(x0,top,z0),(x0,top,z1)],
        [(x1,bottom,z0),(x1,bottom,z1),(x1,top,z1),(x1,top,z0)],
        [(x0,bottom,z1),(x1,bottom,z1),(x1,bottom,z0),(x0,bottom,z0)],
    ]
    name = 'Structure_WestRuinLanding_Cap'
    slab = M.merge([M.quad(face,material='pale_ashlar') for face in faces],material='pale_ashlar')
    # Orient every side from the actual slab centre; keep the underside down.
    centre = np.array([(x0+x1)/2,(bottom+top)/2,(z0+z1)/2])
    for offset in range(0,len(slab.indices),3):
        face = slab.indices[offset:offset+3]
        points = slab.positions[face]
        normal = np.cross(points[1]-points[0],points[2]-points[0])
        if normal @ (points.mean(axis=0)-centre) < 0:
            slab.indices[offset+1],slab.indices[offset+2] = slab.indices[offset+2],slab.indices[offset+1]
    slab.recompute_normals(0)
    build.terrain_meshes[name] = slab
    frame = next(s for s in build.streaming_borders if s['id']=='ssarathi-manymouth')
    frame.setdefault('sceneNodes',[]).append(name)
    road['supportedLanding'] = {'structure':name,'bounds':[[x0,bottom,z0],[x1,top,z1]],
        'topSurface':'Existing native causeway and generated connected carriageway; no duplicate top.',
        'waterLevel':0.,'nativeDeckThickness':.8}


def apply(build):
    if getattr(build, '_west_ruin_bypass', False):
        raise ValueError('The western ruin approach was authored twice')
    from road_profiles import _stations
    from connector_finish import _native_walk
    road = next(r for r in build.geography_roads if r['id'] == 'ssarathi-manymouth')
    original, _ = _stations(road['stations'], spacing=.5)
    meshes = [m for name, m in build.terrain_meshes.items()
              if name.startswith('Walk_ContinentRoad_ssarathi-manymouth') and m.triangle_count]
    ray = VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1, 3)] for m in meshes]))
    # The original underwater road-bed mesh is hidden beneath the real deck.
    # Sample that native walking top so the requested contact height records
    # the visible bridge, not the obsolete submarine paint.
    native = VerticalRayIndex(_native_walk(build))
    for point in original:
        y = ray.top_hit(*point[[0, 2]])
        deck = native.top_hit(*point[[0, 2]])
        if deck is not None and (y is None or deck > y):
            y = deck
        if y is not None:
            point[1] = y - .03
    # The existing low public landing remains the inland connection. Round
    # east of the shrine/station, then south of the march stone, boat and old
    # ruin. The narrow gap between stone and station is not a cartway.
    first = 0
    last = int(np.argmin(np.linalg.norm(original[:, [0, 2]] - [-107.5, -73.5], axis=1)))
    controls = np.array([original[first], [-67., 1.8, -106.], [-65.5, 1.8, -101.],
                         [-65.5, 2.2, -93.], [-68., 2.8, -85.], [-73., 3.4, -78.],
                         [-80., 3.8, -74.], [-92., 4., -71.5], [-100., 4., -72.5], original[last]])
    extended = np.vstack([original[max(0, first-1)], controls,
                          original[min(len(original)-1, last+1)]])
    curve = []
    for i in range(1, len(controls)):
        a, b, c, d = extended[i-1:i+3]
        count = max(2, int(np.ceil(np.linalg.norm(c[[0, 2]]-b[[0, 2]])/.4)))
        for t in np.linspace(0., 1., count, endpoint=False):
            curve.append(.5*(2*b+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
    requested = np.vstack([original[:first], curve, original[last:]])
    if not np.array_equal(requested[[0, -1]], original[[0, -1]]):
        raise ValueError('The ruin bypass changed an immutable public road endpoint')
    road['contactStations'] = requested.tolist()
    road['contactNote'] = ('The western causeway leaves the low public landing east of its shrine and station, '
        'then rounds south of the march stone, moored boat and intact ruin; native bridges and the common deck remain.')
    _landing_cap(build, road)
    build._west_ruin_bypass = True
