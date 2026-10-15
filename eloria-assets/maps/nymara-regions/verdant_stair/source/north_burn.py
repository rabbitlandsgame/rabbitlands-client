"""Seat the upper North Burn in one downhill course and a real road culvert.

The compact terrain and later continental road cuts lowered the old channel
without lowering its water. Its upper loop crossed the road three times in
mid-air. This local finish replaces only that loop, reconnecting at the first
low fall; downstream pools, falls, ruins and the shared road frame stay put.
"""
from collections import defaultdict
import copy
import numpy as np
from amberwood import mesh as M
import region as REG
import connector_finish as F


# Water-surface controls in local metres. The new ravine stays between the
# deep-jungle ruins and the actual eastern aqueduct footing, then rejoins the
# old fall. It never cuts beneath the aqueduct's solid foundation spine.
CONTROLS=np.array([
 [102.40336134453781,62.12,-248.41935483870967],
 [96.,61.95,-249.1],[88.,39.,-247.3],[82.,36.65,-245.8],
 [45.,35.8,-238.],[24.,34.3,-240.],[17.5,33.75,-240.],
 [9.,33.5,-240.],[-4.,33.25,-242.],[-22.,33.,-242.],
 [-22.,32.78,-234.],[-24.,32.64,-228.],[-21.5,32.5,-222.],
 [-26.,32.38,-216.],[-30.,32.26,-212.5],
 [-38.,32.1,-209.],[-41.5,31.9,-211.256213],
],float)


def _curve(build):
    points=CONTROLS.copy()
    old=F.VerticalRayIndex(F._triangles([m for n,m in build.water_meshes.items()
                                       if 'Stream_NorthBurn' in n]))
    level=old.top_hit(*points[-1,[0,2]])
    if level is None:raise ValueError('North Burn downstream receiving surface is missing')
    points[-1,1]=level
    if np.any(np.diff(points[:,1])>1e-8):raise ValueError('North Burn water must drain downhill')
    return F.R._stations(points,spacing=.35)


def _coordinates(xz,points,distance):
    v=np.diff(points[:,[0,2]],axis=0)
    turn=np.abs(v[:-1,0]*v[1:,1]-v[:-1,1]*v[1:,0])>1e-9
    keep=np.r_[True,turn,True]
    across,along=F.G._road_coordinates(np.asarray(xz),points[keep][:,[0,2]])
    s=along*distance[-1]
    width=np.interp(s,[0.,5.,distance[-1]-5.,distance[-1]],[2.3,1.4,1.4,2.3])
    return across,s,width,np.interp(s,distance,points[:,1])


def _cut(points,curve,distance):
    result=points.copy();d,s,w,y=_coordinates(points[:,[0,2]],curve,distance)
    bed=y-.18
    # The receiving ravine crosses a real limestone ridge. Give its exposed
    # banks room to descend instead of drawing a deep, constant-width slot.
    # Keep the compact channel at the literal road culvert to retain its
    # abutments and the existing roadway outside the twelve-metre span.
    depth=np.maximum(points[:,1]-bed,0.)
    west=np.clip((9.-points[:,0])/12.,0.,1.)
    irregular=1.+.14*np.sin(points[:,0]*.17+points[:,2]*.11)+.09*np.sin(points[:,2]*.27)
    run=3.5+west*((7.+.15*depth)*irregular-3.5)
    blend=np.clip((d-w-.35)/run,0.,1.);blend=1-blend*blend*(3-2*blend)
    # The short source cascade also needs its underlying rock profile seated
    # where the old carved floor dipped below the intended waterfall sheet.
    result[:,1]+=(bed-points[:,1])*blend
    return result


def _exposed_rock(mesh,old_y):
    """Select real newly cut steep substrate faces, never an overlay skin."""
    faces=mesh.indices.reshape(-1,3);tri=mesh.positions[faces]
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    slope=np.linalg.norm(normal[:,[0,2]],axis=1)/np.maximum(abs(normal[:,1]),1e-12)
    cut=(old_y-mesh.positions[:,1])[faces].mean(axis=1)
    return (cut>.45)&(slope>.55)


def _rock_banks(build,before):
    """Replace cut grass faces by the same physical limestone triangles."""
    added={};count=0
    for name,old_y in before.items():
        mesh=build.terrain_meshes[name];mask=_exposed_rock(mesh,old_y)
        if not mask.any():continue
        faces=mesh.indices.reshape(-1,3)
        vertices=mesh.positions[faces[mask]]
        normals=np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0])
        axes=np.argmax(abs(normals),axis=1)
        # A single projection plane per face avoids stretching across a
        # steep triangle whose vertex normals choose different UV planes.
        uv=np.empty((len(vertices),3,2))
        for axis,plane in enumerate(((2,1),(0,2),(0,1))):
            use=axes==axis;uv[use]=vertices[use][:,:,plane]*.26
        p=vertices.reshape(-1,3)
        rock=M.Mesh(positions=p,normals=mesh.normals[faces[mask]].reshape(-1,3),
                    uvs=uv.reshape(-1,2),indices=np.arange(len(p)),material='verdant_wet_limestone')
        rock.recompute_normals(180)
        mesh.indices=faces[~mask].ravel();mesh.recompute_normals(180)
        rock_name='Terrain_NorthBurn_RockBank_'+name
        added[rock_name]=rock;count+=int(mask.sum())
        for spec in build.streaming_borders:
            if name in spec.get('sceneNodes',[]):spec['sceneNodes'].append(rock_name)
    build.terrain_meshes.update(added)
    return count


def _ribbon(points,distance):
    direction=np.gradient(points[:,[0,2]],axis=0)
    direction/=np.maximum(np.linalg.norm(direction,axis=1)[:,None],1e-12)
    side=np.c_[-direction[:,1],direction[:,0]]
    width=np.interp(distance,[0.,5.,distance[-1]-5.,distance[-1]],[2.3,1.4,1.4,2.3])
    rings=[]
    for p,s,w in zip(points,side,width):
        rings.append(np.array([[p[0]-s[0]*w,p[1],p[2]-s[1]*w],
                               [p[0]+s[0]*w,p[1],p[2]+s[1]*w]]))
    mesh=M.loft(rings,closed_rings=False,material='water_stream')
    faces=mesh.indices.reshape(-1,3);tri=mesh.positions[faces]
    down=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]<0
    faces[down]=faces[down][:,[0,2,1]]
    mesh.indices=faces.ravel()
    mesh.uvs=mesh.positions[:,[0,2]]*.09;mesh.recompute_normals(180)
    return mesh


def _culvert():
    # The existing road supplies its unchanged walking top. Only a soffit,
    # visible sides and two channel-parallel bearing walls are added here.
    slab=M.box((8.5,.55,12.),center=(17.5,35.03-.275,-240.),material='verdant_wet_limestone')
    tri=slab.positions[slab.indices.reshape(-1,3)]
    slab.indices=slab.indices.reshape(-1,3)[np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]<=0].ravel()
    parts=[slab]
    for z in (-244.,-236.):
        part=M.box((8.5,1.4,4.),center=(17.5,34.33,z),material='verdant_wet_limestone')
        faces=part.indices.reshape(-1,3);tri=part.positions[faces]
        part.indices=faces[np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]<=0].ravel()
        parts.append(part)
    return M.merge(parts,material='verdant_wet_limestone')


def _east_brook_crossing(build):
    """A short stone span above the retained eastern brook, on the same road."""
    def lift(p):
        x,z=p[:,0],p[:,2]
        a=np.clip((x-149.)/6.,0.,1.);a=a*a*(3-2*a)
        c=np.clip((174.-x)/10.,0.,1.);c=c*c*(3-2*c)
        return np.where((z>-190.)&(z<-164.),.55*np.minimum(a,c),0.)
    parts=[];minimum_clearance=float('inf');maximum_grade=0.
    water=F.VerticalRayIndex(F._triangles([m for n,m in build.water_meshes.items() if 'EastBrook' in n]))
    for name,mesh in build.terrain_meshes.items():
        if not name.startswith('Walk_ContinentRoad_sunmane-verdant'):continue
        before=mesh.positions.copy();height=lift(before);mesh.positions[:,1]+=height
        changed=height[mesh.indices.reshape(-1,3)].max(1)>1e-9
        tri=mesh.positions[mesh.indices.reshape(-1,3)][changed]
        normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);valid=abs(normal[:,1])>1e-9
        maximum_grade=max(maximum_grade,float((np.linalg.norm(normal[valid][:,[0,2]],axis=1)/abs(normal[valid,1])).max(initial=0.)))
        mesh.recompute_normals(180)
        piece=mesh.copy()
        piece=F.R._clip_scalar(piece,149.-piece.positions[:,0]);piece=F.R._clip_scalar(piece,piece.positions[:,0]-174.)
        piece=F.R._clip_scalar(piece,-190.-piece.positions[:,2]);piece=F.R._clip_scalar(piece,piece.positions[:,2]+164.)
        if not piece.triangle_count:continue
        # Existing modified road supplies the single visible walking top.
        # The new mesh supplies only its downward soffit and vertical fascia.
        faces=piece.indices.reshape(-1,3);vertices=piece.positions.copy();bottom=vertices.copy();bottom[:,1]-=.30
        underside=bottom[faces].copy()
        n=np.cross(underside[:,1]-underside[:,0],underside[:,2]-underside[:,0]);up=n[:,1]>0
        underside[up]=underside[up][:,[0,2,1]]
        out=[underside.reshape(-1,3)]
        unique,labels=np.unique(np.round(vertices,7),axis=0,return_inverse=True);ff=labels[faces]
        edges=np.concatenate([ff[:,[0,1]],ff[:,[1,2]],ff[:,[2,0]]]);canonical=np.sort(edges,axis=1)
        pairs,counts=np.unique(canonical,axis=0,return_counts=True)
        for a,b in pairs[counts==1]:
            # Keep the directed boundary of the upward walking face.
            oriented=next(e for e in edges if (np.sort(e)==[a,b]).all())
            a,b=oriented
            p,q=unique[a],unique[b];r=p-[0.,.30,0.];s=q-[0.,.30,0.]
            out.append(np.array([p,s,q,p,r,s]))
        p=np.concatenate(out);body=M.Mesh(positions=p,normals=np.zeros_like(p),uvs=p[:,[0,2]]*.26,indices=np.arange(len(p)),material='verdant_wet_limestone');body.recompute_normals(180);parts.append(body)
        ray=F.VerticalRayIndex(F._triangles([piece]))
        for x in np.arange(152.,168.01,.125):
            for z in np.arange(-188.2,-169.79,.125):
                top=ray.top_hit(x,z);w=water.top_hit(x,z)
                if top is not None and w is not None:minimum_clearance=min(minimum_clearance,top-.30-w)
    if maximum_grade>.39:
        g=np.linalg.norm(normal[valid][:,[0,2]],axis=1)/abs(normal[valid,1])
        raise ValueError(f'East Brook span is too steep: {maximum_grade}; face {tri[valid][int(g.argmax())].tolist()}')
    if minimum_clearance<.04:raise ValueError(f'East Brook soffit has no open water clearance: {minimum_clearance}')
    build.terrain_meshes['Structure_EastBrook_RoadSpan']=M.merge(parts,material='verdant_wet_limestone')
    for road in build.geography_roads:
        if road['id']=='sunmane-verdant':
            p=np.array(road['stations']);p[:,1]+=lift(p);road['stations']=p.tolist()
    for spec in build.streaming_borders:
        if spec['id']=='sunmane-verdant':spec['sceneNodes'].append('Structure_EastBrook_RoadSpan')
    return {'maximumActualFaceGrade':maximum_grade,'minimumSoffitWaterClearance':minimum_clearance,
            'spanX':[149.,174.],'maximumRoadLift':.55,'waterUnchanged':True}


def _discard_empty_water(build, names):
    """Drop fully clipped water pieces from the exported water inventories."""
    removed = {name for name in names if not build.water_meshes[name].triangle_count}
    for name in removed:
        del build.water_meshes[name]
    for frame in build.streaming_borders:
        frame['sceneNodes'] = [name for name in frame.get('sceneNodes', []) if name not in removed]
    return sorted(removed)


def apply(build):
    if getattr(build,'north_burn_finish',None):raise ValueError('North Burn applied twice')
    points,distance=_curve(build);roads=[{'stations':CONTROLS.tolist()}]
    tangent=np.gradient(CONTROLS[:,[0,2]],axis=0)
    tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-12)
    side=np.c_[-tangent[:,1],tangent[:,0]]
    for offset in (-4.,4.):
        bank=CONTROLS.copy();bank[:,[0,2]]+=side*offset
        roads.append({'stations':bank.tolist()})
    # Reject an authored route that touches actual structural feet. Canopies
    # are not foundations; the shared footprint reader uses grounded parts.
    structural=copy.copy(build)
    structural.placements=[copy.copy(p) for p in build.placements if not F.G._is_scatter(p)]
    structural.meshes=build.meshes.copy()
    footprints=F._footing_polygons(structural)
    across=np.full(len(points),np.inf)
    for polygon in footprints:across=np.minimum(across,F._footing_distance(points[:,[0,2]],polygon))
    widths=_coordinates(points[:,[0,2]],points,distance)[2]
    clearance=float(across.min())
    if np.any(across<widths+.4):
        i=int(across.argmin());poly=next(p for p in footprints if F._footing_distance(points[i:i+1,[0,2]],p)[0]<=clearance+1e-8)
        raise ValueError(f'North Burn reaches a protected footing ({clearance:.3f} m) at {points[i].tolist()}; polygon {poly.tolist()}')
    def shape(p):
        result=_cut(p,points,distance);changed=np.abs(result[:,1]-p[:,1])>1e-9
        if changed.any():
            xz=p[changed][:,[0,2]];factor=np.ones(len(xz))
            edge=F.R._edge_distance(build,'verdant_stair',xz)
            factor*=np.clip((edge-3.)/1.,0.,1.)
            for polygon in footprints:
                near=np.all(xz>=polygon.min(0)-2.,axis=1)&np.all(xz<=polygon.max(0)+2.,axis=1)
                if near.any():
                    # Retain one complete refined face around the foot so
                    # interpolating a partly cut face cannot lower its edge.
                    support=np.clip((F._footing_distance(xz[near],polygon)-.8)/1.2,0.,1.)
                    factor[near]*=support*support*(3-2*support)
            result[changed,1]=p[changed,1]+(result[changed,1]-p[changed,1])*factor
        return result
    original_bases=defaultdict(list)
    for name,mesh in build.terrain_meshes.items():
        if F._base(name) and mesh.triangle_count:original_bases[F.substrate_name(name)].append(mesh.copy())
    old={n:F.Substrate(ms) for n,ms in original_bases.items()}
    old_ground=F.VerticalRayIndex(F._triangles([m for ms in original_bases.values() for m in ms]))
    paint={n:m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_') and not F._base(n)
           and ('_StreamCollar_' in n or '_ContinentBlend_' in n)}
    paint_offsets={}
    for n,m in paint.items():
        F.R.refine_bed(m,roads)
        paint_offsets[n]=m.positions[:,1]-old[F.substrate_name(n)].sample(m.positions[:,[0,2]])
    maximum_cut=0.;maximum_fill=0.;before_shaping={}
    for n,m in build.terrain_meshes.items():
        if not F._base(n):continue
        F.R.refine_bed(m,roads);before=m.positions[:,1].copy()
        before_shaping[n]=before
        m.positions=shape(m.positions);maximum_cut=max(maximum_cut,float(np.max(before-m.positions[:,1],initial=0.)))
        maximum_fill=max(maximum_fill,float(np.max(m.positions[:,1]-before,initial=0.)))
        m.recompute_normals(180)
    changed=defaultdict(list)
    for n,m in build.terrain_meshes.items():
        if F._base(n) and m.triangle_count:changed[F.substrate_name(n)].append(m)
    samplers={n:F.Substrate(ms) for n,ms in changed.items()}
    for n,m in paint.items():
        before=m.positions[:,1].copy()
        m.positions[:,1]=samplers[F.substrate_name(n)].sample(m.positions[:,[0,2]])+paint_offsets[n]
        # The original paint is complementary only on intact sward. Exposed
        # new rock must not keep a floating grass layer above its substrate.
        faces=m.indices.reshape(-1,3)
        m.indices=faces[~_exposed_rock(m,before)].ravel()
        m.recompute_normals(180)
    rock_faces=_rock_banks(build,before_shaping)
    terrain=build.terrain
    terrain.height=shape(np.c_[terrain.gx.ravel(),terrain.height.ravel(),terrain.gz.ravel()])[:,1].reshape(terrain.height.shape)
    # Native non-content foliage must not remain suspended over the new cut.
    removed=set();linked={r.get('node') for key in ('landmarks','interactives','npc_markers','harvestables','portals','spawns') for r in getattr(build,key,[])}
    for p in build.placements:
        if not F.G._is_scatter(p) or p.node in linked:continue
        d,_,w,_=_coordinates(np.asarray(p.position)[None,[0,2]],points,distance)
        if d[0]<w[0]+1.:removed.add(p.node)
        elif d[0]<w[0]+18.:
            q=np.array([p.position],float)
            h=old_ground.top_hit(p.position[0],p.position[2])
            if h is None:raise ValueError(f'North Burn scatter has no support: {p.node}')
            q[0,1]=h
            delta=shape(q)[0,1]-q[0,1]
            p.position=(p.position[0],p.position[1]+float(delta),p.position[2])
    build.placements[:]=[p for p in build.placements if p.node not in removed]
    old_path=REG.STREAMS['north_burn'];old_length=np.linalg.norm(np.diff(old_path,axis=0),axis=1).sum()
    _,join=F.G._road_coordinates(points[-1:,[0,2]],old_path);join=float(join[0]*old_length)
    affected=[]
    for n,m in list(build.water_meshes.items()):
        if 'NorthBurn' not in n:continue
        _,a=F.G._road_coordinates(m.positions[:,[0,2]],old_path)
        build.water_meshes[n]=F.R._clip_scalar(m,join-a*old_length);affected.append(n)
    removed_water = _discard_empty_water(build, affected)
    name='Water_Stream_NorthBurn_GroundedUpper'
    build.water_meshes[name]=_ribbon(points,distance)
    build.terrain_meshes['Structure_NorthBurn_Culvert']=_culvert()
    for spec in build.streaming_borders:
        spec['sceneNodes']=[n for n in spec.get('sceneNodes',[]) if n not in removed]
        if spec['id']=='sunmane-verdant':spec['sceneNodes']+= [name,'Structure_NorthBurn_Culvert']
    eastern=_east_brook_crossing(build)
    report={'waterControls':points.tolist(),'downstreamJoinAlongMetres':join,
            'changedWaterNodes':affected,'removedEmptyWaterNodes':removed_water,
            'removedUnlinkedScatter':sorted(removed),
            'minimumFootingDistance':clearance,'maximumLocalBedCut':maximum_cut,
            'maximumLocalBedFill':maximum_fill,
            'newExposedRockFaces':rock_faces,
            'northRoadWalkingTopUnchanged':True,'eastBrookCrossing':eastern,'downstreamPoolsAndFallsPreserved':True}
    build.north_burn_finish=report
    build.notes.append('North Burn upper drainage follows its real carved bed and crosses beneath a stone road culvert; the downstream falls remain authored.')
    return report
