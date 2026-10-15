"""Keep the delta road's full carriageway inside the moor's owned bank.

The original diagonal tracked the Grey/West ownership edge too closely:
its outer carriageway fell in the retained cliff strip. This local curve
stays inland, then joins the unchanged eastward border road on level ground.
"""
import numpy as np

ROAD = 'grey-manymouth'
REVISION = 'inland-delta-bank-v2'


def collar_height(x):
    """Comfortable moor descent; the last three shared metres remain level."""
    x=np.asarray(x)
    return np.where(x>=285.5,3.14,14. + (3.14-14.)*np.clip((x-253.)/32.5,0.,1.))


def prepare(build):
    road = next(r for r in build.geography_roads if r['id'] == ROAD)
    original = np.asarray(road['stations'], float)
    prefix = original[original[:, 0] <= 220.00001].tolist()
    road['contactStations'] = prefix + [
        [229., 7., 98.], [239., 10., 98.], [248., 13.5, 110.],
        [253., 14., 117.], [253., float(collar_height(253.)), 122.5],
        [285.5, 3.14, 122.5],
        original[-1].tolist(),
    ]
    road['contactRevision'] = REVISION


def finish(build):
    """A visible draped road mouth covers its conservative edge samples.

    Reshape the inland bank, keeping its true shared edge and native floors.
    Subtract the existing road from the small visible bank mouth. Its surface
    follows the actual terrain rather than an independently sampled quad.
    """
    import connector_finish as F
    from amberwood import mesh as M
    import delta_bank_landform as BANK
    road_names = [n for n in build.terrain_meshes if n.startswith('Walk_ContinentRoad_'+ROAD)]
    authored = next((r for r in getattr(build,'geography_roads',[]) if r['id']==ROAD),None)
    controls = np.asarray(authored['contactStations'] if authored else
        [[220.,4.8,98.],[229.,6.5,98.],[241.,6.5,98.],[252.,5.5,102.],[262.,3.14,112.],[266.,3.14,122.5],[288.5,3.14,122.5]])
    mouth = np.array([[247.5,122.5],[254.,122.5]])
    if authored:
        # The retained old diagonal is no longer a road. Clip it to the
        # current carriageway only. The newly raised rounded mouth replaces
        # its old low retained strip; that strip must not supply a false floor.
        for name in road_names:
            mesh=build.terrain_meshes[name]
            d,_=F.G._road_coordinates(mesh.positions[:,[0,2]],controls[:,[0,2]])
            build.terrain_meshes[name]=F.R._clip_scalar(mesh,d-4.25)
        BANK.apply(build,controls,mouth)
    ground = F.VerticalRayIndex(F._triangles([m for n, m in build.terrain_meshes.items() if F._base(n)]))
    parts=[]
    for name,mesh in build.terrain_meshes.items():
        if not F._base(name) or not mesh.triangle_count:continue
        # Exact copied substrate triangles avoid the green slivers caused
        # by independently interpolated rectangular paving quads.
        copy=mesh.copy()
        F.R.refine_bed(copy,[dict(stations=np.c_[mouth[:,0],np.full(len(mouth),3.14),mouth[:,1]])])
        d,_=F.G._road_coordinates(copy.positions[:,[0,2]],mouth)
        copy=F.R._clip_scalar(copy,d-4.25)
        if copy.triangle_count:parts.append(copy)
    patch=M.merge(parts,material=build.terrain_meshes[road_names[0]].material)
    patch.positions[:,1]+=.03;patch.uvs=patch.positions[:,[0,2]]*.28
    existing = F._triangles([build.terrain_meshes[n] for n in road_names])
    patch = F._subtract_native(patch, existing)
    spec = F.G.plan()['regions']['grey_moors']
    polygon = np.asarray(spec['ownershipPolygon'])-np.asarray(spec['translation'])[[0, 2]]
    patch = F.G.clip_owned_mesh(patch, F.G.polygon_rectangles(polygon))
    faces = patch.indices.reshape(-1, 3).copy()
    triangles = patch.positions[faces]
    down = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])[:, 1] < 0
    faces[down] = faces[down][:, [0, 2, 1]]
    patch.indices = faces.ravel()
    patch.recompute_normals(180)
    name = 'Walk_DeltaRoadBankMouth'
    build.terrain_meshes[name] = patch
    frame = next(s for s in build.streaming_borders if s['id'] == ROAD)
    if name not in frame['sceneNodes']:
        frame['sceneNodes'].append(name)
    # These three unlabelled natural specimens sat on the newly shifted lane.
    # Keep their identities and dimensions on the nearby stony grass verge.
    verge = {'Scatter_Erratic_495': (240., 90.),
             'Scatter_Erratic_693': (247., 91.),
             'Scatter_Scrub_6149': (254., 95.)}
    for p in getattr(build, 'placements', []):
        if p.node not in verge:
            continue
        old = ground.top_hit(p.position[0], p.position[2])
        x, z = verge[p.node]
        new = ground.top_hit(x, z)
        if old is None or new is None:
            raise ValueError('Delta verge specimen has no physical footing')
        p.position = (x, new + p.position[1] - old, z)
    build.delta_approach_revision = REVISION
    if authored:
        import delta_verge
        delta_verge.apply(build,controls)
