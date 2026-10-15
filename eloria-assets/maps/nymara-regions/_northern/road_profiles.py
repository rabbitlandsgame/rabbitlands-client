"""Sample northern road beds after the shared border pass has graded them.

The original geography stations describe the road before border shaping. A
later valley pass must follow the actual emitted road, or it can restore low
ground underneath a road that the common border saddle has already raised.
"""
import numpy as np
import heapq


def _limit_profile(distance, heights, pinned, maximum=.38):
    """Project a sampled bed onto an endpoint-constrained grade envelope."""
    fixed=np.flatnonzero(pinned)
    lower=np.max(heights[fixed,None]-maximum*np.abs(distance[fixed,None]-distance),axis=0)
    upper=np.min(heights[fixed,None]+maximum*np.abs(distance[fixed,None]-distance),axis=0)
    if np.any(lower>upper+1e-7):
        raise ValueError('Protected northern road stations require a longer approach')
    result=np.clip(heights,lower,upper)
    for i in range(1,len(result)):
        rise=maximum*(distance[i]-distance[i-1])
        result[i]=np.clip(result[i],result[i-1]-rise,result[i-1]+rise)
    for i in range(len(result)-2,-1,-1):
        rise=maximum*(distance[i+1]-distance[i])
        result[i]=np.clip(result[i],result[i+1]-rise,result[i+1]+rise)
    if not np.allclose(result[fixed],heights[fixed],atol=1e-7,rtol=0):
        raise ValueError('Northern road grade could not retain protected stations')
    return result


def _grid_grade(values,allowed,pins,columns,retained=None,face_retained=None):
    """Slope-limited interpolation on the real connected road, not shortcuts.

    Graph bounds provide a feasible initial profile; the subsequent sparse
    face solve constrains the actual triangulation rather than just its edges.
    """
    if retained is None:retained=np.zeros(len(values),bool)
    def envelope(seed):
        result=seed.copy();queue=[(float(result[i]),int(i)) for i in np.flatnonzero(allowed&np.isfinite(result))]
        owner=np.full(len(values),-1,dtype=int)
        for _,index in queue:owner[index]=index
        heapq.heapify(queue)
        while queue:
            level,index=heapq.heappop(queue)
            if level>result[index]+1e-10:continue
            row,col=divmod(index,columns)
            for dz,dx in ((0,-1),(0,1),(-1,0),(1,0),(-1,-1),(-1,1),(1,-1),(1,1)):
                nr,nc=row+dz,col+dx
                if nr<0 or nc<0 or nc>=columns:continue
                other=nr*columns+nc
                if other>=len(values) or not allowed[other]:continue
                if dx and dz and not (allowed[index+dx] and allowed[index+dz*columns]):continue
                rise=(.25 if retained[index] or retained[other] else .175)*(np.sqrt(2.) if dx and dz else 1.)
                if level+rise>=result[other]-1e-10:continue
                result[other]=level+rise;owner[other]=owner[index];heapq.heappush(queue,(level+rise,other))
        return result,owner
    upper,up_owner=envelope(np.where(pins,values,np.inf))
    inverse,low_owner=envelope(np.where(pins,-values,np.inf));lower=-inverse
    if np.any(allowed&(lower>upper+1e-6)):
        index=int(np.flatnonzero(allowed&(lower>upper+1e-6))[0]);a,b=up_owner[index],low_owner[index]
        path=((upper[index]-values[a])+(values[b]-lower[index]))/.267
        raise ValueError(f'Fixed northern road pins {divmod(int(a),columns)} Y{values[a]:.4f} and {divmod(int(b),columns)} Y{values[b]:.4f} exceed the connected corridor grade budget; geodesic {path:.3f}m')
    result,_=envelope(np.where(allowed,np.clip(values,lower,upper),np.inf))
    result[pins]=values[pins]
    result=_face_grade(result,allowed,pins,columns,retained if face_retained is None else face_retained)
    return np.where(allowed,result,values)


def _face_grade(values,allowed,pins,columns,retained):
    """Sparse convex directional-gradient solve on the actual road faces."""
    try:
        from scipy.optimize import linprog
        from scipy.sparse import coo_matrix,hstack,vstack,eye
    except ImportError as error:
        raise RuntimeError('Northern continent road builds require SciPy (python -m pip install -r eloria-assets/maps/nymara-regions/_northern/requirements.txt).') from error
    rows=len(values)//columns
    a=(np.arange(rows-1)[:,None]*columns+np.arange(columns-1)).ravel()
    faces=np.concatenate([np.stack([a,a+columns,a+columns+1],axis=1),np.stack([a,a+1,a+columns+1],axis=1)])
    faces=faces[allowed[faces].all(axis=1)&~retained[faces].all(axis=1)]
    free=np.flatnonzero(allowed&~pins);lookup=np.full(len(values),-1,int);lookup[free]=np.arange(len(free))
    if not len(faces):return values
    coefficients=np.array([[-1.,1.,0.],[0.,-1.,1.],[-1.,0.,1.],[1.,-2.,1.]])
    limits=np.array([.175,.175,.175*np.sqrt(2),.175*np.sqrt(2)])
    for coefficient,limit in zip(coefficients,limits):
        fixed_only=(pins[faces]|(coefficient==0)).all(axis=1)
        if np.any(fixed_only&(np.abs(values[faces]@coefficient)>limit+1e-7)):
            raise ValueError('Fixed northern road face exceeds the actual gradient limit')
    if not len(free):return values
    row=[];col=[];data=[];bounds=[]
    for coefficient,limit in zip(coefficients,limits):
        fixed=np.where(pins[faces],values[faces],0.)@coefficient
        for sign in (1.,-1.):
            start=len(bounds);bounds.extend((limit-sign*fixed).tolist())
            face_rows=np.arange(start,start+len(faces))
            for j,c in enumerate(coefficient):
                indexes=lookup[faces[:,j]];keep=(indexes>=0)&(c!=0)
                row.extend(face_rows[keep]);col.extend(indexes[keep]);data.extend(np.full(keep.sum(),sign*c))
    A=coo_matrix((data,(row,col)),shape=(len(bounds),len(free))).tocsr()
    mutable=np.diff(A.indptr)>0;A=A[mutable];bounds=np.asarray(bounds)[mutable]
    # L1 displacement preserves the intended longitudinal profile, without
    # locking its incidental old interior bumps or introducing new low spots.
    identity=eye(len(free),format='csr')
    constraints=vstack([hstack([A,coo_matrix(A.shape)]),hstack([identity,-identity]),hstack([-identity,-identity])],format='csr')
    rhs=np.r_[bounds,values[free],-values[free]]
    solved=linprog(np.r_[np.zeros(len(free)),np.ones(len(free))],A_ub=constraints,b_ub=rhs,
        bounds=[(None,None)]*len(free)+[(0,None)]*len(free),method='highs')
    if not solved.success:raise ValueError('Northern actual-face grade constraints: '+solved.message)
    result=values.copy();result[free]=solved.x[:len(free)]
    return result


def _protected_distance(build,region,xz):
    """Distance to true common edges and actual civic/discovery footings."""
    import continent_geography as G
    from northern_passes import _footprints
    distance=np.full(len(xz),np.inf)
    if hasattr(build,'continent_geography'):
        distance,_=G.boundary_sample(region,xz,maximum=9.)
    if hasattr(build,'placements'):
        for lo,hi in _footprints(build):
            offset=np.maximum(np.maximum(lo-xz,xz-hi),0.)
            distance=np.minimum(distance,np.linalg.norm(offset,axis=1))
    return distance


def _edge_distance(build,region,xz):
    import continent_geography as G
    if hasattr(build,'continent_geography'):
        return G.boundary_sample(region,xz,maximum=9.)[0]
    return np.full(len(xz),np.inf)


def _clip_scalar(mesh,values):
    """Keep scalar <=0; neighbouring faces share the same cut vertices."""
    from amberwood.terrain import _compact
    faces=mesh.indices.reshape(-1,3);d=values[faces]
    columns=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:columns.append(mesh.colors)
    v=np.concatenate(columns,axis=1);parts=[v[faces[d.max(axis=1)<=1e-9]].reshape(-1,v.shape[1])]
    for face in faces[(d.min(axis=1)<-1e-9)&(d.max(axis=1)>1e-9)]:
        polygon=[]
        for a,b in zip(face,np.roll(face,-1)):
            da,db=values[a],values[b]
            if da<=0:polygon.append(v[a])
            if da*db<0:polygon.append(v[a]+(v[b]-v[a])*(da/(da-db)))
        if len(polygon)>2:parts.append(np.array([p for i in range(1,len(polygon)-1) for p in (polygon[0],polygon[i],polygon[i+1])]))
    combined=np.concatenate(parts);result=mesh.copy()
    result.positions,result.normals,result.uvs=combined[:,:3],combined[:,3:6],combined[:,6:8]
    if result.colors is not None:result.colors=combined[:,8:12]
    result.indices=np.arange(len(combined))
    return _compact(result)


def _corridor(build,region,meshes,points,distance):
    """One continuous eight-metre bed, including the full outside of bends."""
    import continent_geography as G
    from amberwood import mesh as M
    xz=points[:,[0,2]];low=np.floor((xz.min(axis=0)-5.5)*2)/2;high=np.ceil((xz.max(axis=0)+5.5)*2)/2
    xs=np.arange(low[0],high[0]+.25,.5);zs=np.arange(low[1],high[1]+.25,.5)
    gx,gz=np.meshgrid(xs,zs);p=np.c_[gx.ravel(),np.zeros(gx.size),gz.ravel()]
    across,along=G._road_coordinates(p[:,[0,2]],xz)
    # Pin the entire cut cross-section, not only its centre. Otherwise a
    # mathematically gentle planar field can meet the retained strip with a
    # transverse step at the very place that must stay continuous.
    interface=np.flatnonzero((_edge_distance(build,region,p[:,[0,2]])<=3.000001)&(across<=3.500001))
    p[:,1]=np.interp(along,distance/distance[-1],points[:,1])+.03
    allowed=across<=5.5;pins=np.zeros(len(p),bool)
    if hasattr(build,'continent_geography'):
        record=G.plan()['regions'][region]
        polygon=np.array(record['ownershipPolygon'])-np.array(record['translation'])[[0,2]]
        allowed &= G.inside_polygon(p[:,[0,2]],polygon)
    if len(interface):
        from verify_runtime import VerticalRayIndex
        ray=VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)] for m in meshes]))
        for index in interface:
            if not allowed[index]:continue
            height=ray.top_hit(float(p[index,0]),float(p[index,2]))
            if height is not None:p[index,1]=height;pins[index]=True
    for point in (points[0],points[-1]):
        index=int(np.argmin(np.linalg.norm(p[:,[0,2]]-point[[0,2]],axis=1)))
        if allowed[index] and not pins[index]:pins[index]=True;p[index,1]=point[1]+.03
    name=next(n for n,m in build.terrain_meshes.items() if m is meshes[0])
    for spec in getattr(build,'streaming_borders',[]):
        if 'id' not in spec or not name.startswith('Walk_ContinentRoad_'+spec['id']):continue
        anchor=np.asarray(spec['anchor']);out=np.asarray(spec['outward']);side=np.array([-out[1],out[0]])
        relative=p[:,[0,2]]-anchor[[0,2]];depth=relative@out;lateral=relative@side
        # An apron is a target inland, not a second fixed contour beside the
        # real common edge. Leave room to converge from its retained crown.
        apron=allowed&(depth>=-42.)&(depth<=0)&(abs(lateral)<=3.75)&(_edge_distance(build,region,p[:,[0,2]])>6.)&~pins
        pins[apron]=True;p[apron,1]=anchor[1]+.03
    if region=='amethyst_barrens' and name.startswith('Walk_ContinentRoad_whitehorn-amethyst'):
        # The two northern roads meet west of the grotto. Their overlapping
        # travel/fold surfaces share the existing Mirror plateau, instead of
        # placing a lower White approach immediately beside its raised edge.
        junction=allowed&(p[:,0]>=-117.)&(p[:,0]<=-99.)&(p[:,2]>=-240.)&(p[:,2]<=-229.)&(_edge_distance(build,region,p[:,[0,2]])>6.)&~pins
        pins[junction]=True;p[junction,1]=24.08
    try:p[:,1]=_grid_grade(p[:,1],allowed,pins,len(xs),_edge_distance(build,region,p[:,[0,2]])<=6.,_edge_distance(build,region,p[:,[0,2]])<=3.000001)
    except ValueError as error:
        raise ValueError(f'{region}/{name}, grid origin XZ {low.tolist()}: {error}') from error
    a=(np.arange(len(zs)-1)[:,None]*len(xs)+np.arange(len(xs)-1)).ravel()
    faces=np.stack([a,a+len(xs),a+len(xs)+1,a,a+len(xs)+1,a+1],axis=1).ravel()
    grid=M.Mesh(positions=p,normals=np.tile([0.,1,0],(len(p),1)),uvs=p[:,[0,2]]*.28,indices=faces,material=meshes[0].material)
    grid=_clip_scalar(grid,across-4.25)
    if region=='amethyst_barrens' and any(n.startswith('Walk_ContinentRoad_mirrorhold-amethyst') and m is meshes[0] for n,m in build.terrain_meshes.items()):
        # All +3m actor lanes and their +.75m fold samples stay supported;
        # the original grotto discovery post at z=-222.3607 stays uncovered.
        q=grid.positions
        grid=_clip_scalar(grid,np.minimum.reduce([q[:,0]+98.,-64.-q[:,0],q[:,2]+222.625,-220.-q[:,2]]))
    edge=_edge_distance(build,region,grid.positions[:,[0,2]])
    grid=_clip_scalar(grid,3.-edge)
    retained=[_clip_scalar(m,_edge_distance(build,region,m.positions[:,[0,2]])-3.) for m in meshes]
    result=M.merge([grid,*retained],material=meshes[0].material)
    if hasattr(build,'continent_geography'):
        record=G.plan()['regions'][region]
        polygon=np.array(record['ownershipPolygon'])-np.array(record['translation'])[[0,2]]
        result=G.clip_owned_mesh(result,G.polygon_rectangles(polygon))
    result.recompute_normals(180)
    first=meshes[0]
    for field in ('positions','normals','uvs','colors','indices','material'):
        setattr(first,field,getattr(result,field))
    dropped={name for name,m in build.terrain_meshes.items() if any(m is old for old in meshes[1:])}
    first_name=next(name for name,m in build.terrain_meshes.items() if m is first)
    for name in dropped:del build.terrain_meshes[name]
    for spec in getattr(build,'streaming_borders',[]):
        if 'sceneNodes' in spec:
            previous=spec['sceneNodes'];spec['sceneNodes']=[name for name in previous if name not in dropped]
            if dropped.intersection(previous) and first_name not in spec['sceneNodes']:
                spec['sceneNodes'].append(first_name)


def _reshape(build,region,meshes,points,distance):
    """Keep fixed contours, repairing only the newly authored public bed."""
    import continent_geography as G
    raw=points[:,1].copy()
    old_grade=float(np.max(np.abs(np.diff(raw))/np.diff(distance)))
    pinned=_protected_distance(build,region,points[:,[0,2]])<=3.
    pinned[[0,-1]]=True
    limited=_limit_profile(distance,raw,pinned) if old_grade>.380001 else raw
    points[:,1]=limited
    _corridor(build,region,meshes,points,distance)
    from verify_runtime import VerticalRayIndex
    ray=VerticalRayIndex(meshes[0].positions[meshes[0].indices.reshape(-1,3)])
    for index,point in enumerate(points):
        height=ray.top_hit(float(point[0]),float(point[2]))
        if height is not None:points[index,1]=height-.03
    return old_grade,float(np.max(np.abs(limited-raw)))


def _stations(points, spacing=1.):
    points=np.asarray(points,float)
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points[:,[0,2]],axis=0),axis=1))]
    if lengths[-1]<=1e-6:
        raise ValueError('Northern road profile has no horizontal length')
    samples=np.sort(np.r_[np.arange(0.,lengths[-1],spacing),lengths])
    samples=samples[np.r_[True,np.diff(samples)>1e-6]]
    if lengths[-1]-samples[-1]>1e-6:samples=np.r_[samples,lengths[-1]]
    else:samples[-1]=lengths[-1]
    result=np.c_[np.interp(samples,lengths,points[:,0]),
                 np.interp(samples,lengths,points[:,1]),
                 np.interp(samples,lengths,points[:,2])]
    return result,samples


def refresh(build, region):
    """Replace selected station heights with actual post-border road-bed Y."""
    from northern_passes import ROADS
    from verify_runtime import VerticalRayIndex
    selected=ROADS.get(region,set())
    audit=[]
    for road in getattr(build,'geography_roads',[]):
        if road['id'] not in selected:continue
        prefix='Walk_ContinentRoad_'+road['id']
        meshes=[m for name,m in build.terrain_meshes.items()
                if (name==prefix or name.startswith(prefix+'_')) and m.triangle_count]
        if not meshes:raise ValueError(f'{region}/{road["id"]}: missing post-border road geometry')
        triangles=np.concatenate([m.positions[m.indices.reshape(-1,3)] for m in meshes])
        ray=VerticalRayIndex(triangles)
        points,distance=_stations(road['stations'])
        original_y=points[:,1].copy();tail=[]
        for index,p in enumerate(points):
            actual=ray.top_hit(float(p[0]),float(p[2]))
            if actual is not None:
                points[index,1]=actual-.03
            elif distance[-1]-distance[index]<=1.01:
                # The half-metre anchor can lie outside the visible owned
                # cut. Its invisible threshold retains the surveyed bed Y.
                # This narrow terminal exception must never mask an inland gap.
                points[index,1]=road['stations'][-1][1]
                tail.append(index)
            else:
                raise ValueError(f'{region}/{road["id"]}: no road at inland station {index}: {p.tolist()}')
        if region=='amethyst_barrens' and road['id']=='whitehorn-amethyst':
            # Give the low White approach a separate verge away from
            # the rising Mirror branch; neither native entrance is moved.
            x=points[:,0]
            enter=np.clip((x+61.)/8.,0.,1.);leave=np.clip((-25.-x)/10.,0.,1.)
            points[:,2]-=np.minimum(enter*enter*(3.-2.*enter),leave*leave*(3.-2.*leave))*4.
            distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points[:,[0,2]],axis=0),axis=1))]
            road['length']=float(distance[-1])
        if region=='mirrorhold' and road['id']=='mirrorhold-amethyst':
            # The protected Orrery slab ends at z=-233.355. A short
            # bend away from the footing puts all seven lanes and their conservative fold samples
            # outside its native footing transition, without moving the slab.
            x=points[:,0]
            enter=np.clip((x-85.)/18.,0.,1.);leave=np.clip((145.-x)/20.,0.,1.)
            offset=np.minimum(enter*enter*(3.-2.*enter),leave*leave*(3.-2.*leave))*4.
            points[:,2]-=offset
            distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points[:,[0,2]],axis=0),axis=1))]
            road['length']=float(distance[-1])
        original_grade,grade_change=_reshape(build,region,meshes,points,distance)
        # Preserve the identity, endpoints, authored length and all other
        # metadata. Only the shaping stations need the post-border elevations.
        road['stations']=points.tolist()
        audit.append({'road':road['id'],'sampleCount':len(points),'thresholdTailSamples':tail,
                      'maximumBedChange':float(np.max(np.abs(points[:,1]-original_y))),
                      'maximumUncorrectedGrade':original_grade,'gradeRepairMaxChange':grade_change,
                      'maximumActualGrade':float(np.max(np.abs(np.diff(points[:,1]))/np.diff(distance)))})
    build.northern_road_profile_audit=audit
    return audit


def refine_bed(mesh,roads):
    """Resolve the narrow transition from intact footings to a usable verge."""
    import continent_geography as G
    columns=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:columns.append(mesh.colors)
    values=np.concatenate(columns,axis=1);faces=mesh.indices.reshape(-1,3)
    for _ in range(8):
        ends=np.stack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]],axis=1)
        edge_points=values[ends,:3][:,:,:,[0,2]]
        middle=edge_points.mean(axis=2).reshape(-1,2)
        length=np.linalg.norm(edge_points[:,:,1]-edge_points[:,:,0],axis=2).ravel()
        near=np.full(len(middle),np.inf)
        for road in roads:
            d,_=G._road_coordinates(middle,np.asarray(road['stations'])[:,[0,2]])
            near=np.minimum(near,d)
        # Identical edge endpoints make identical decisions, even across
        # separate material/StreamCell meshes. A short shared edge is never
        # split merely because its triangle has a different long edge.
        split=((near<11.5+length*.5)&(length>.7)).reshape(-1,3)
        if not split.any():break
        mids=(values[ends[:,:,0]]+values[ends[:,:,1]])*.5
        ids=np.full(split.shape,-1,int);ids[split]=np.arange(len(values),len(values)+split.sum())
        values=np.concatenate([values,mids[split]])
        codes=split@np.array([1,2,4]);parts=[]
        templates={
            0:((0,1,2),),1:((0,3,2),(3,1,2)),2:((1,4,0),(4,2,0)),4:((2,5,1),(5,0,1)),
            3:((3,1,4),(0,3,4),(0,4,2)),6:((4,2,5),(1,4,5),(1,5,0)),
            5:((5,0,3),(2,5,3),(2,3,1)),7:((0,3,5),(3,1,4),(5,4,2),(3,4,5))}
        vertices=np.concatenate([faces,ids],axis=1)
        for code,triples in templates.items():
            selected=vertices[codes==code]
            parts.extend(selected[:,t] for t in triples)
        faces=np.concatenate(parts)
    mesh.positions,mesh.normals,mesh.uvs=values[:,:3],values[:,3:6],values[:,6:8]
    if mesh.colors is not None:mesh.colors=values[:,8:12]
    mesh.indices=faces.ravel()


def seat_ground(build,region):
    """Seat the real unprotected road bed after the broad valley shaping."""
    import continent_geography as G
    from northern_passes import ROADS,_footprints
    from verify_runtime import VerticalRayIndex
    selected=[r for r in getattr(build,'geography_roads',[]) if r['id'] in ROADS.get(region,set())]
    meshes=[m for n,m in build.terrain_meshes.items() if any(n.startswith('Walk_ContinentRoad_'+r['id']) for r in selected)]
    if not meshes:return
    ray=VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)] for m in meshes]))
    footprints=_footprints(build);cache={}
    def smooth(x):
        x=np.clip(x,0.,1.);return x*x*(3.-2.*x)
    def shape(points):
        result=points.copy();xz=points[:,[0,2]]
        distance=np.full(len(points),np.inf);centres=np.zeros_like(xz)
        for road in selected:
            p=np.asarray(road['stations']);d,a=G._road_coordinates(xz,p[:,[0,2]])
            lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p[:,[0,2]],axis=0),axis=1))];near=d<distance
            centres[near,0]=np.interp(a[near],lengths/lengths[-1],p[:,0]);centres[near,1]=np.interp(a[near],lengths/lengths[-1],p[:,2]);distance[near]=d[near]
        weight=1.-smooth((distance-5.5)/5.)
        weight*=smooth((_edge_distance(build,region,xz)-3.)/3.)
        for lo,hi in footprints:
            d=np.linalg.norm(np.maximum(np.maximum(lo-xz,xz-hi),0.),axis=1)
            weight*=smooth(d/1.5)
        candidates=np.flatnonzero(weight>1e-8)
        for index in candidates:
            vector=xz[index]-centres[index];length=np.linalg.norm(vector)
            sample=centres[index]+vector*min(1.,3.75/max(length,1e-9));key=tuple(np.round(sample,7))
            if key not in cache:
                height=ray.top_hit(*sample)
                if height is None:height=ray.top_hit(*centres[index])
                cache[key]=height
            height=cache[key]
            if height is None:continue
            target=height-.03-.035*max(distance[index]-4.25,0.)**2
            result[index,1]+=(target-result[index,1])*weight[index]
        return result
    G._lift_unprotected_scatter(build,shape)
    for name,mesh in build.terrain_meshes.items():
        if name.startswith('Terrain_'):
            refine_bed(mesh,selected)
            mesh.positions=shape(mesh.positions);mesh.recompute_normals(180)
    terrain=build.terrain
    points=np.c_[terrain.gx.ravel(),terrain.height.ravel(),terrain.gz.ravel()]
    terrain.height=shape(points)[:,1].reshape(terrain.height.shape)
    build.notes.append('Northern road beds are seated from their final triangle surfaces; common boundaries and actual native structural footings are protected.')


def add_supports(build,region):
    """A real stone arch carries the raised road over the preserved grotto."""
    if region!='amethyst_barrens':return
    from amberwood import mesh as M
    from regionbuild import Placement
    from verify_runtime import VerticalRayIndex
    road=[m for n,m in build.terrain_meshes.items() if n.startswith('Walk_ContinentRoad_mirrorhold-amethyst')]
    if not road:raise ValueError('Grotto bridge requires the physical Mirrorhold road')
    ray=VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)] for m in road]))
    ground=VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)] for n,m in build.terrain_meshes.items()
        if n.startswith('Terrain_') and '_StreamCollar_' not in n and '_ContinentBlend_' not in n]))
    xs=np.linspace(-101.,-61.,41);z=-226.5
    top=np.array([ray.top_hit(float(x),z) for x in xs],float)-.04
    if not np.isfinite(top).all():raise ValueError('Grotto bridge deck has a missing span')
    bases=np.array([ground.top_hit(float(x),z) for x in (xs[0],xs[-1])],float)
    bases=np.minimum(bases,top[[0,-1]]-.8)
    t=np.linspace(0,1,len(xs));spring=bases[0]*(1-t)+bases[1]*t
    rise=max(0.,float(np.min((top[1:-1]-.65-spring[1:-1])/(4*t[1:-1]*(1-t[1:-1])))))
    soffit=np.minimum(top-.65,spring+4*rise*t*(1-t))
    material='amethyst_pale_stone';parts=[]
    # Two narrow spandrel ribs leave the grotto and its public floor open.
    for side in (-1,1):
        za,zb=z+side*3.85,z+side*4.95
        for i in range(len(xs)-1):
            a,b=xs[i:i+2];ya,yb=top[i:i+2];la,lb=soffit[i:i+2]
            parts.extend([M.quad([[a,ya,za],[b,yb,za],[b,lb,za],[a,la,za]],material=material),
                          M.quad([[a,la,zb],[b,lb,zb],[b,yb,zb],[a,ya,zb]],material=material),
                          M.quad([[a,la,za],[b,lb,za],[b,lb,zb],[a,la,zb]],material=material)])
    # Literal soffit slab immediately below the deck, with no duplicate top.
    for i in range(len(xs)-1):
        a,b=xs[i:i+2];ya,yb=top[i:i+2]-.12
        parts.append(M.quad([[a,ya,z-4.25],[b,yb,z-4.25],[b,yb,z+4.25],[a,ya,z+4.25]],material=material))
    mesh=M.merge(parts,material=material);mesh.recompute_normals(50)
    name='Northern_Grotto_Bridge_Arch';build.add_mesh(name,mesh)
    build.place(Placement(node=name,mesh=name,position=(0.,0.,0.),kind='bridge',collides=False))
    # Foundation blocks are outside the clear travel width, with bottoms
    # sampled from the final terrain rather than their original source datum.
    for index,x in enumerate((xs[0],xs[-1])):
        for side in (-1,1):
            pz=z+side*4.4;base=ground.top_hit(float(x),pz)
            cap=float(top[0 if index==0 else -1]);height=max(.3,cap-base)
            key=f'Northern_Grotto_Abutment_{index}_{side}'
            block=M.box((2.,height,1.1),material=material)
            build.add_mesh(key,block)
            build.place(Placement(node=key,mesh=key,position=(float(x),base+height*.5-.05,pz),kind='stone',collides=True))
    build.notes.append('The northern public road crosses the existing grotto on a stone arch with terrain-seated abutments; the native cave and its floor remain intact.')
