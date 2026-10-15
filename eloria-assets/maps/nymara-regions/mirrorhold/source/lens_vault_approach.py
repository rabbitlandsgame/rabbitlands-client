"""Seat the intact Lens Vault entrance on the connected lower working road.

Move it before shared shaping so its abandoned high footing is no longer a
protected soil pillar. Finish only its small, formal apron after road grading.
The Orrery itself and the interior room stay in place.
"""
import numpy as np

NODE='Building_VaultEntry_lens-vault-stair'
DOOR='lens-vault-stair'
POSITION=(67.0,91.0,-199.0)
TRIGGER=(67.0,91.1,-195.0)
NATIVE_ORIGIN=(120.0,96.0)
REVISION='working-road-vault-entry-1'

def weight(x,z):
    # A modest 7.4 x 9.6m court includes the complete 4.8 x 3.8m footing.
    distance=np.maximum(np.abs(x-67.0)-3.7,np.abs(z+197.2)-4.8)
    t=np.clip(distance/4.0,0.,1.)
    return 1.-t*t*(3.-2.*t)

def prepare(build):
    """Author the new foundation before ownership and northern pass shaping."""
    if hasattr(build,'lens_vault_approach'):return
    placement=next(p for p in build.placements if p.node==NODE)
    portal=next(p for p in build.portals if p['id']==DOOR)
    old=list(placement.position)
    build.lens_vault_approach={'revision':REVISION,'originalPosition':old,
        'position':list(POSITION),'trigger':list(TRIGGER),
        'reason':'The existing full-size vault entry now fronts the connected lower working road; its old isolated approach footing is released.'}
    placement.position=POSITION
    # Keep the Orrery association; the physical node is the separate doorway.
    portal['position']=list(TRIGGER)
    portal['serverTile']=[round(TRIGGER[0]+NATIVE_ORIGIN[0]),round(NATIVE_ORIGIN[1]-TRIGGER[2])]
    portal['node']=NODE
    portal['approachRevision']=REVISION
    for landmark in build.landmarks:
        if landmark.get('node')==NODE:landmark['position']=list(POSITION)
    for road in build.authored_roads:
        if road['id']=='lens-vault-lane':
            road['originalSurveyWaypoints']=road['waypoints']
            road['waypoints']=[[67.,91.,-193.],[67.,91.,-195.]]
            road['width']=4.
    terrain=build.terrain
    blend=weight(terrain.gx,terrain.gz)
    terrain.height=terrain.height*(1.-blend)+91.*blend
    terrain.tree_block|=blend>.5

def finish(build):
    """A real earth-supported court, with a thin stone walking finish."""
    if not hasattr(build,'lens_vault_approach'):raise ValueError('Lens Vault foundation was not prepared')
    if build.lens_vault_approach.get('finished'):return
    import connector_finish as F
    from amberwood import mesh as M
    entry=next(p for p in build.placements if p.node==NODE)
    entry_mesh=build.meshes[entry.mesh]
    rotation=M.rotation_y(entry.rotation_y)[:3,:3]
    entry_points=np.concatenate([part.positions for part in getattr(entry_mesh,'all_parts',[entry_mesh])])
    entry_points=entry_points*entry.scale@rotation.T+entry.position
    # Reserve the asymmetric actor-.75/.25 conservative fold as well as the
    # real facade: a half-covered server tile must not widen into its jamb.
    entry_low=entry_points.min(axis=0)[[0,2]]-.8
    entry_high=entry_points.max(axis=0)[[0,2]]+.8
    approach=np.array([[56.5,92.80145,-198.5],[60.,91.867364815,-196.5],[63.25,91.,-195.5]])
    def path_field(xz):
        distance,_=F.G._road_coordinates(xz,approach[:,[0,2]])
        t=np.clip((distance-3.5)/4.,0.,1.)
        # One continuous 0.267-grade bank reaches the complete Y91 court.
        # A half-metre soil margin keeps clipped walking faces inside this
        # plane instead of interpolating a steep feather across the verge.
        target=91.+(92.80145-91.)*np.clip((63.25-xz[:,0])/(63.25-56.5),0.,1.)
        return 1.-t*t*(3.-2.*t),target
    def shaped(xz,earth):
        court=weight(xz[:,0],xz[:,1]);result=earth+(91.-earth)*court
        blend,target=path_field(xz)
        # Keep the complete formal court/foundation level, while the broad
        # western shoulder joins the surveyed public road at its actual Y.
        return result+(target-result)*blend
    selected={n:m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_')
              and np.any((weight(m.positions[:,0],m.positions[:,2])>0.)|(path_field(m.positions[:,[0,2]])[0]>0.))}
    guide=[{'stations':[[67.,91.,-202.],[67.,91.,-192.]]},{'stations':approach}]
    for mesh in selected.values():F.R.refine_bed(mesh,guide)
    substrate=F.Substrate([m.copy() for n,m in build.terrain_meshes.items() if F._base(n)])
    changes=[]
    for name,mesh in selected.items():
        points=mesh.positions;active=(weight(points[:,0],points[:,2])>0.)|(path_field(points[:,[0,2]])[0]>0.)
        if not active.any():continue
        # Sample physical soil before applying any material layer offset.
        earth=substrate.sample(points[active][:,[0,2]])
        delta=shaped(points[active][:,[0,2]],earth)-earth
        points[active,1]+=delta
        changes.extend(delta.tolist())
        mesh.recompute_normals(180)
    t=build.terrain
    t.height=shaped(np.c_[t.gx.ravel(),t.gz.ravel()],t.height.ravel()).reshape(t.height.shape)
    # A single clipped copy of the actual earth supplies the full six-metre
    # support through the bend. Its material/UV match the earth; the formal
    # stone court above it has a separate positive 5mm finish allowance.
    for source,base in selected.items():
        if not F._base(source):continue
        d,_=F.G._road_coordinates(base.positions[:,[0,2]],approach[:,[0,2]])
        skin=F.R._clip_scalar(base,d-3.)
        # The walking opener intentionally trusts Walk_ geometry. Keep this
        # soil finish outside the complete native entry's blocked footprint,
        # so it cannot reopen the jamb or the covered room's side walls.
        fragments=[]
        remainder=skin
        for axis,low,high in zip((0,2),entry_low,entry_high):
            fragments.append(F.R._clip_scalar(remainder,remainder.positions[:,axis]-low))
            remainder=F.R._clip_scalar(remainder,low-remainder.positions[:,axis])
            fragments.append(F.R._clip_scalar(remainder,high-remainder.positions[:,axis]))
            remainder=F.R._clip_scalar(remainder,remainder.positions[:,axis]-high)
        skin=M.merge([part for part in fragments if part.triangle_count],material=skin.material)
        if not skin.triangle_count:continue
        skin.positions[:,1]+=.020
        faces=skin.indices.reshape(-1,3).copy();tri=skin.positions[faces]
        down=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]<0
        faces[down]=faces[down][:,[0,2,1]];skin.indices=faces.ravel();skin.recompute_normals(180)
        node='Walk_LensVaultWorkingPath_'+source;build.terrain_meshes[node]=skin
        for frame in build.streaming_borders:
            if source in frame['sceneNodes']:frame['sceneNodes'].append(node)
    # Full support lives in earth; this thin formal paving is clear of the
    # front wall and joins the same level soil at every edge.
    name='Walk_LensVaultWorkingApron'
    build.terrain_meshes[name]=M.quad([(63.8,91.025,-196.5),(63.8,91.025,-193.0),
        (70.2,91.025,-193.0),(70.2,91.025,-196.5)],uv_scale=.28,material='cobble_paving')
    mesh=build.terrain_meshes[name]
    tri=mesh.positions[mesh.indices.reshape(-1,3)]
    if np.cross(tri[0,1]-tri[0,0],tri[0,2]-tri[0,0])[1]<0:mesh.indices=mesh.indices.reshape(-1,3)[:,[0,2,1]].ravel()
    mesh.recompute_normals(180)
    for frame in build.streaming_borders:
        if NODE in frame['sceneNodes'] and name not in frame['sceneNodes']:frame['sceneNodes'].append(name)
    build.lens_vault_approach.update(finished=True,finishedTerrainMeshes=sorted(selected),
        maximumFinishRaise=max(changes,default=0.),maximumFinishCut=min(changes,default=0.),
        pavementBounds=[63.8,70.2,-196.5,-193.0],publicApproach=approach.tolist(),
        supportedShoulderWidth=6.,publicApproachFeather=4.,
        walkingFinishExcludesEntryBounds=[entry_low.tolist(),entry_high.tolist()])
    build.notes.append('The Lens Vault keeps its full-size covered doorway and interior identity on a grounded working-road court; the abandoned high entry footing is released.')
