"""Finish generated public connectors after shared, local and outer shaping.

Native bridges, rooms and authored walking meshes are inputs, never outputs.
Only Walk_ContinentRoad geometry is replaced. The frozen northern numerical
solver supplies the same face-grade and conforming-edge rules used by the
three mountain passes, without applying their broad valley sculpture.
"""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_northern'))
import road_profiles as R
from landscape_finish import Substrate, substrate_name, paint_bias, collar_layers
from verify_runtime import VerticalRayIndex
from amberwood import mesh as M
import continent_geography as G

SOLVED={
    'whitehorn_range':{'whitehorn-amethyst'},
    'mirrorhold':{'mirrorhold-amethyst'},
    'amethyst_barrens':{'whitehorn-amethyst','mirrorhold-amethyst','amethyst-sunmane'},
}


def _base(name):
    return name.startswith('Terrain_') and not any(s in name for s in
        ('_StreamCollar_','_ContinentBlend_','OuterEscarpment','_StreamThreshold_'))


def _triangles(meshes):
    return np.concatenate([m.positions[m.indices.reshape(-1,3)] for m in meshes
                           if m.triangle_count]) if any(m.triangle_count for m in meshes) else np.empty((0,3,3))


def _native_walk(build):
    pieces=[m.positions[m.indices.reshape(-1,3)] for name,m in build.terrain_meshes.items()
            if name.startswith('Walk_') and not name.startswith(('Walk_ContinentRoad_','Walk_StreamThreshold_'))
            and m.triangle_count]
    for placement in build.placements:
        mesh=build.meshes.get(placement.mesh)
        if mesh is None:continue
        parts=getattr(mesh,'walk_parts',[])
        if not parts and placement.walk_surface and not hasattr(mesh,'all_parts'):parts=[mesh]
        rotation=M.rotation_y(placement.rotation_y)[:3,:3]
        for part in parts:
            if not part.triangle_count:continue
            p=part.positions*placement.scale@rotation.T+placement.position
            pieces.append(p[part.indices.reshape(-1,3)])
    return np.concatenate(pieces) if pieces else np.empty((0,3,3))


def _native_contact(points, allowed, triangles, ground, radius=3., visible_causeways=()):
    """Extend the actual visible native plane across its narrow contact rim.

    Grid vertices just outside a non-grid deck edge need the same plane as
    vertices inside it. Otherwise subtracting the exact footprint exposes an
    interpolated height lip. Native ramp grades are retained only in this rim.
    """
    heights=np.full(len(points),np.nan);distances=np.full(len(points),np.inf);grades=np.zeros(len(points))
    if not len(triangles):return heights,distances,grades
    oracle=VerticalRayIndex(triangles)
    normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    for i in np.flatnonzero(allowed):
        point=points[i,[0,2]];lo=np.floor((point-radius-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int)
        hi=np.floor((point+radius-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int);candidates=set()
        for x in range(lo[0],hi[0]+1):
            for z in range(lo[1],hi[1]+1):candidates.update(oracle.buckets.get((x,z),()))
        best=None;nearby=[]
        for index in sorted(candidates):
            triangle=triangles[index];normal=normals[index]
            if abs(normal[1])<1e-9:continue
            xz=triangle[:,[0,2]];sides=np.roll(xz,-1,axis=0)-xz
            relative=point-xz;cross=sides[:,0]*relative[:,1]-sides[:,1]*relative[:,0]
            if np.all(cross>=-1e-9) or np.all(cross<=1e-9):nearest=point;distance=0.
            else:
                t=np.clip(np.sum(relative*sides,axis=1)/np.maximum(np.sum(sides*sides,axis=1),1e-18),0.,1.)
                projections=xz+t[:,None]*sides;edge_distances=np.linalg.norm(projections-point,axis=1)
                k=int(np.argmin(edge_distances));nearest=projections[k];distance=float(edge_distances[k])
            grade=float(np.linalg.norm(normal[[0,2]])/abs(normal[1]))
            if distance>(radius if grade>.35+1e-8 else 1.75)+1e-8:continue
            native_y=float(triangle[0,1]-(nearest-triangle[0,[0,2]])@normal[[0,2]]/normal[1])
            base=ground.top_hit(*nearest) if ground is not None else None
            if base is not None and native_y<base-.05:
                # This named, measured causeway is the floor exposed by the
                # bounded landing clearance cut. Its contact plane must be
                # solved before that cut, even if old soil currently covers
                # it. Unrelated buried native layers remain excluded.
                known=False
                for floor,level in visible_causeways:
                    if abs(native_y-level)>1e-5:continue
                    actual=floor.top_hit(*nearest)
                    if actual is not None and abs(actual-native_y)<1e-5:known=True;break
                if not known:continue
            height=float(triangle[0,1]-(point-triangle[0,[0,2]])@normal[[0,2]]/normal[1])
            key=(round(distance,8),-height,index)
            nearby.append((distance,height))
            if best is None or key<best[0]:best=(key,height,grade)
        if best is not None:
            heights[i]=best[1];distances[i]=best[0][0];grades[i]=best[2]
            # Two joined native spans may have different tangential planes.
            # Their overlapping extrapolation is a requested level, not an
            # immutable deck. Free only these off-deck competing halo pins.
            if distances[i]>1e-7 and any(d<=1.75 and abs(y-heights[i])>.015 for d,y in nearby):
                distances[i]=max(distances[i],1.0001)
    return heights,distances,grades


def _contact_grade(values,allowed,pins,columns,retained,native_grade):
    """The frozen face constraints with a bounded native-ramp grade input.

    A bridge's retained derivative may exceed the new road budget. Every
    face is still constrained: only faces in its measured three-metre contact zone
    receive that actual native grade, never an unconstrained exemption.
    """
    if not np.any(native_grade>.35+1e-8):
        return R._face_grade(values,allowed,pins,columns,retained)
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix,hstack,vstack,eye
    rows=len(values)//columns;a=(np.arange(rows-1)[:,None]*columns+np.arange(columns-1)).ravel()
    faces=np.concatenate([np.stack([a,a+columns,a+columns+1],axis=1),np.stack([a,a+1,a+columns+1],axis=1)])
    faces=faces[allowed[faces].all(axis=1)&~retained[faces].all(axis=1)]
    free=np.flatnonzero(allowed&~pins);lookup=np.full(len(values),-1,int);lookup[free]=np.arange(len(free))
    limits=.5*np.maximum(.35,native_grade[faces].max(axis=1))
    coefficients=np.array([[-1.,1.,0.],[0.,-1.,1.],[-1.,0.,1.],[1.,-2.,1.]])
    # A clipped retained contour can cross a grid face diagonally. Only its
    # already-fixed contributing vertices determine the inherited bound;
    # a zero-coefficient free corner must not make that real contour invalid.
    for coefficient,scale in zip(coefficients,(1.,1.,np.sqrt(2.),np.sqrt(2.))):
        inherited=(retained[faces]|(coefficient==0)).all(axis=1)
        limits=np.maximum(limits,np.where(inherited,np.abs(values[faces]@coefficient)/scale,0.))
    row=[];col=[];data=[];bounds=[]
    for coefficient,scale in zip(coefficients,(1.,1.,np.sqrt(2.),np.sqrt(2.))):
        fixed_only=(pins[faces]|(coefficient==0)).all(axis=1)
        if np.any(fixed_only&(np.abs(values[faces]@coefficient)>limits*scale+1e-7)):
            raise ValueError('Native connector contact requires a longer physical approach')
        fixed=np.where(pins[faces],values[faces],0.)@coefficient
        for sign in (1.,-1.):
            start=len(bounds);bounds.extend((limits*scale-sign*fixed).tolist());face_rows=np.arange(start,start+len(faces))
            for j,c in enumerate(coefficient):
                indexes=lookup[faces[:,j]];keep=(indexes>=0)&(c!=0)
                row.extend(face_rows[keep]);col.extend(indexes[keep]);data.extend(np.full(keep.sum(),sign*c))
    if not len(free):return values
    A=coo_matrix((data,(row,col)),shape=(len(bounds),len(free))).tocsr();mutable=np.diff(A.indptr)>0;A=A[mutable];bounds=np.asarray(bounds)[mutable]
    identity=eye(len(free),format='csr')
    constraints=vstack([hstack([A,coo_matrix(A.shape)]),hstack([identity,-identity]),hstack([-identity,-identity])],format='csr')
    solved=linprog(np.r_[np.zeros(len(free)),np.ones(len(free))],A_ub=constraints,b_ub=np.r_[bounds,values[free],-values[free]],bounds=[(None,None)]*len(free)+[(0,None)]*len(free),method='highs')
    if not solved.success:raise ValueError('Native connector contact grade: '+solved.message)
    result=values.copy();result[free]=solved.x[:len(free)];return result


def _road_inputs(build,region,selected,ground,native):
    result=[]
    specs={s['id']:s for s in build.streaming_borders}
    for road in selected:
        prefix='Walk_ContinentRoad_'+road['id']
        names=[n for n,m in build.terrain_meshes.items() if n.startswith(prefix) and m.triangle_count]
        if not names:raise ValueError(f'{region}/{road["id"]}: no generated road')
        ray=VerticalRayIndex(_triangles([build.terrain_meshes[n] for n in names]))
        points,length=R._stations(road['stations'])
        for i,p in enumerate(points):
            y=ray.top_hit(*p[[0,2]])
            if y is not None:points[i,1]=y-.03
            elif length[-1]-length[i]>1.01:raise ValueError(f'{region}/{road["id"]}: missing inland road station {i}')
        if 'contactStations' in road:
            from copy import deepcopy
            road.setdefault('originalSurveyStations',deepcopy(road['stations']))
            authored,authored_length=R._stations(road['contactStations'])
            if not np.isfinite(authored).all() or np.linalg.norm(authored[-1,[0,2]]-points[-1,[0,2]])>1e-5:
                raise ValueError(f'{region}/{road["id"]}: authored contact curve moved the common endpoint')
            if np.linalg.norm(authored[0,[0,2]]-points[0,[0,2]])>1e-5 and not road.get('contactStartReason'):
                raise ValueError(f'{region}/{road["id"]}: relocated native road start needs an authored reason')
            points,length=authored,authored_length
        bridge=np.zeros(len(points),bool)
        native_y=np.zeros(len(points))
        if native is not None:
            for i,p in enumerate(points):
                a=native.top_hit(*p[[0,2]]);b=ground.top_hit(*p[[0,2]])
                if a is not None and (b is None or a>=b-.05):
                    bridge[i]=True;native_y[i]=a
        spec=specs[road['id']]
        width_data={}
        if 'contactWidths' in road:
            controls=np.asarray(road.get('contactStations',[]),float);widths=np.asarray(road['contactWidths'],float)
            if (controls.ndim!=2 or controls.shape[1]!=3 or widths.ndim!=1 or len(widths)!=len(controls)
                    or not np.isfinite(widths).all() or np.any(widths<3.8) or np.any(widths>8.5)):
                raise ValueError(f'{region}/{road["id"]}: contactWidths must give 3.8..8.5 metre widths for every contact station')
            width_distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(controls[:,[0,2]],axis=0),axis=1))]
            if np.any(np.diff(width_distance)<=1e-8) or abs(widths[-1]-8.5)>1e-8:
                raise ValueError(f'{region}/{road["id"]}: width controls need distinct stations and a full-width common endpoint')
            if np.interp(max(0.,width_distance[-1]-42.),width_distance,widths)<8.5-1e-8:
                raise ValueError(f'{region}/{road["id"]}: complete the authored widening before the last 42 metres')
            width_data={'widthDistances':width_distance,'halfWidths':widths*.5}
        if spec.get('profile')=='causeway':
            depth=(points[:,[0,2]]-np.array(spec['anchor'])[[0,2]])@np.asarray(spec['outward'])
            bridge[depth>=-42.000001]=True;native_y[depth>=-42.000001]=spec['anchor'][1]
        result.append({'road':road,'names':names,'points':points,'length':length,
                       'bridge':bridge,'nativeY':native_y,'spec':spec,**width_data})
    return result


def _half_width(item,along):
    """Optional authored native-bridge taper; the last 42 m remain full width."""
    if 'halfWidths' not in item:return np.full(np.asarray(along).shape,4.25)
    width=np.interp(along,item['widthDistances'],item['halfWidths'])
    return np.where(along>=item['length'][-1]-42.,4.25,width)


def _subtract_native(mesh, triangles):
    """Subtract actual native walking triangles, with exact interpolated cuts.

    A centreline hit never removes the wider carriageway. The native floor
    and remaining generated triangles meet at the same geometric edge.
    """
    if not len(triangles) or not mesh.triangle_count:return mesh
    oracle=VerticalRayIndex(triangles)
    fields=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:fields.append(mesh.colors)
    values=np.concatenate(fields,axis=1);output=[]
    for face in mesh.indices.reshape(-1,3):
        original=values[face];lo=original[:,[0,2]].min(axis=0);hi=original[:,[0,2]].max(axis=0)
        low=np.floor((lo-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int)
        high=np.floor((hi-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int)
        candidates=set()
        for x in range(low[0],high[0]+1):
            for z in range(low[1],high[1]+1):candidates.update(oracle.buckets.get((x,z),()))
        polygons=[original]
        for index in sorted(candidates):
            cutter=triangles[index];xz=cutter[:,[0,2]]
            if (xz.max(axis=0)<lo-1e-8).any() or (xz.min(axis=0)>hi+1e-8).any():continue
            if cutter[:,1].max()<original[:,1].min()-3. or cutter[:,1].min()>original[:,1].max()+3.:continue
            first,second=xz[1]-xz[0],xz[2]-xz[0];area=first[0]*second[1]-first[1]*second[0]
            if abs(area)<1e-10:continue
            if area<0:xz=xz[[0,2,1]]
            remaining=[]
            for polygon in polygons:
                inside=polygon
                for a,b in zip(xz,np.roll(xz,-1,axis=0)):
                    if not len(inside):break
                    vector=b-a;p=inside[:,[0,2]]-a
                    distance=vector[0]*p[:,1]-vector[1]*p[:,0]
                    keep=[];outside=[]
                    for i,j in zip(range(len(inside)),np.roll(np.arange(len(inside)),-1)):
                        v,w=inside[i],inside[j];d,e=distance[i],distance[j]
                        (keep if d>=0 else outside).append(v)
                        if (d>=0)!=(e>=0):
                            cut=v+(w-v)*(d/(d-e));keep.append(cut);outside.append(cut)
                    if len(outside)>=3:remaining.append(np.asarray(outside))
                    inside=np.asarray(keep)
            polygons=remaining
            if not polygons:break
        for polygon in polygons:
            for i in range(1,len(polygon)-1):output.append(polygon[[0,i,i+1]])
    p=np.concatenate(output) if output else np.empty((0,values.shape[1]));result=mesh.copy()
    result.positions,result.normals,result.uvs=p[:,:3],p[:,3:6],p[:,6:8]
    if result.colors is not None:result.colors=p[:,8:12]
    result.indices=np.arange(len(p));return result


def _conform_boundary(mesh,retained,build,region,native_triangles=None):
    """Insert the retained cut's own knots instead of bridging them linearly."""
    triangles=_triangles(retained)
    if not len(triangles) or not mesh.triangle_count:return mesh
    oracle=VerticalRayIndex(np.concatenate([triangles,native_triangles]) if native_triangles is not None else triangles)
    points=np.unique(triangles.reshape(-1,3),axis=0)
    points=points[np.abs(R._edge_distance(build,region,points[:,[0,2]])-3.)<1e-6]
    columns=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:columns.append(mesh.colors)
    data=np.concatenate(columns,axis=1)
    boundary=np.abs(R._edge_distance(build,region,data[:,[0,2]])-3.)<1e-6
    for i in np.flatnonzero(boundary):
        height=oracle.top_hit(*data[i,[0,2]])
        if height is not None:data[i,1]=height
    output=[]
    for ids in mesh.indices.reshape(-1,3):
        face=data[ids];split=False
        for a,b,c in ((0,1,2),(1,2,0),(2,0,1)):
            if not (boundary[ids[a]] and boundary[ids[b]]):continue
            vector=face[b,[0,2]]-face[a,[0,2]];length=float(vector@vector)
            if length<1e-12:continue
            relative=points[:,[0,2]]-face[a,[0,2]];along=relative@vector/length
            error=np.linalg.norm(relative-along[:,None]*vector,axis=1)
            selected=np.flatnonzero((error<1e-6)&(along>1e-7)&(along<1-1e-7))
            if not len(selected):continue
            values=np.unique(along[selected]);knots=[face[a]]
            for t in values:
                p=face[a]+(face[b]-face[a])*t;height=oracle.top_hit(*p[[0,2]])
                if height is not None:p[1]=height
                knots.append(p)
            knots.append(face[b]);output.extend(np.array([x,y,face[c]]) for x,y in zip(knots,knots[1:]));split=True;break
        if not split:output.append(face)
    p=np.concatenate(output);result=mesh.copy();result.positions,result.normals,result.uvs=p[:,:3],p[:,3:6],p[:,6:8]
    if result.colors is not None:result.colors=p[:,8:12]
    result.indices=np.arange(len(p));return result


def _union_grid(build,region,inputs,native_triangles=None,ground=None):
    """A shared half-metre triangulation gives intersecting roads one height."""
    stations=np.concatenate([r['points'][:,[0,2]] for r in inputs])
    low=np.floor((stations.min(axis=0)-5.5)*2)/2;high=np.ceil((stations.max(axis=0)+5.5)*2)/2
    xs=np.arange(low[0],high[0]+.25,.5);zs=np.arange(low[1],high[1]+.25,.5)
    gx,gz=np.meshgrid(xs,zs);p=np.c_[gx.ravel(),np.zeros(gx.size),gz.ravel()]
    nearest=np.full(len(p),np.inf);owner=np.zeros(len(p),int);bridge=np.zeros(len(p),bool)
    width_clip=np.full(len(p),np.inf)
    variable_width=any('halfWidths' in r for r in inputs)
    allowed=np.zeros(len(p),bool);pins=np.zeros(len(p),bool)
    record=G.plan()['regions'][region];polygon=np.array(record['ownershipPolygon'])-np.array(record['translation'])[[0,2]]
    inside=G.inside_polygon(p[:,[0,2]],polygon)
    edge=R._edge_distance(build,region,p[:,[0,2]])
    all_roads=VerticalRayIndex(_triangles([build.terrain_meshes[n] for r in inputs for n in r['names']]))
    causeway_rim=np.zeros(len(p),bool)
    for number,item in enumerate(inputs):
        points,length=item['points'],item['length']
        d,a=G._road_coordinates(p[:,[0,2]],points[:,[0,2]])
        along=a*length[-1];near=d<nearest
        if variable_width:width_clip=np.minimum(width_clip,d-_half_width(item,along))
        p[near,1]=np.interp(along[near],length,points[:,1])+.03
        owner[near]=number;nearest[near]=d[near]
        bridge[near]=np.interp(along[near],length,item['bridge'].astype(float))>=.5
        allowed|=d<=5.5
        if item['spec'].get('profile')=='causeway':
            spec=item['spec'];outward=np.asarray(spec['outward']);relative=p[:,[0,2]]-np.array(spec['anchor'])[[0,2]]
            causeway_rim|=(relative@outward>=-42.)&(np.abs(relative@np.array([-outward[1],outward[0]]))<=5.5)
    allowed&=inside
    for i in np.flatnonzero(allowed&(edge<=3.000001)):
        height=all_roads.top_hit(*p[i,[0,2]])
        if height is not None:p[i,1]=height;pins[i]=True
    for number,item in enumerate(inputs):
        for point in (item['points'][0],item['points'][-1]):
            i=int(np.argmin(np.linalg.norm(p[:,[0,2]]-point[[0,2]],axis=1)))
            if allowed[i] and not pins[i]:p[i,1]=point[1]+.03;pins[i]=True
    visible_causeways=[]
    for item in inputs:
        if item['spec'].get('profile')!='causeway':continue
        prefix='Walk_StreamCauseway_'+item['spec']['id'];level=float(item['spec']['anchor'][1])
        floors=_triangles([m for n,m in build.terrain_meshes.items() if n.startswith(prefix)])
        floors=floors[np.max(np.abs(floors[:,:,1]-level),axis=1)<1e-5] if len(floors) else floors
        if len(floors):visible_causeways.append((VerticalRayIndex(floors),level))
    contact,native_distance,native_grade=_native_contact(p,allowed,native_triangles,ground,visible_causeways=visible_causeways) if native_triangles is not None else (np.full(len(p),np.nan),np.full(len(p),np.inf),np.zeros(len(p)))
    contact_zone=np.isfinite(contact)&((edge>3.)|(native_distance<1e-7)|causeway_rim);native_pins=contact_zone&(native_distance<=1.)
    p[contact_zone,1]=contact[contact_zone];pins|=native_pins
    # The actual retained contour can have an inherited .38 longitudinal
    # grade. Preserve its measured derivative in the bounded6m transition,
    # including diagonal faces whose third, zero-coefficient vertex is free.
    _,_,boundary_grade=_native_contact(p,allowed&(edge<=6.),_triangles([build.terrain_meshes[n] for r in inputs for n in r['names']]),None)
    native_grade=np.maximum(native_grade,boundary_grade)
    if native_pins.any() or np.any(boundary_grade>.35+1e-8):
        p[:,1]=_contact_grade(p[:,1],allowed,pins,len(xs),edge<=3.000001,native_grade)
    else:
        p[:,1]=R._grid_grade(p[:,1],allowed,pins,len(xs),edge<=6.,edge<=3.000001)
    a=(np.arange(len(zs)-1)[:,None]*len(xs)+np.arange(len(xs)-1)).ravel()
    faces=np.stack([a,a+len(xs),a+len(xs)+1,a,a+len(xs)+1,a+1],axis=1).reshape(-1,3)
    faces=faces[allowed[faces].all(axis=1)]
    result=[]
    for number,item in enumerate(inputs):
        centres=p[faces].mean(axis=1)[:,[0,2]];dist=[]
        for r in inputs:dist.append(G._road_coordinates(centres,r['points'][:,[0,2]])[0])
        chosen=np.argmin(np.asarray(dist),axis=0)==number
        grid=M.Mesh(positions=p.copy(),normals=np.tile([0.,1.,0.],(len(p),1)),uvs=p[:,[0,2]]*.28,
                    indices=faces[chosen].ravel(),material=build.terrain_meshes[item['names'][0]].material)
        grid=R._clip_scalar(grid,width_clip if variable_width else nearest-4.25)
        cut=3.-R._edge_distance(build,region,grid.positions[:,[0,2]])
        if item['spec'].get('profile')=='causeway':
            spec=item['spec'];outward=np.asarray(spec['outward']);relative=grid.positions[:,[0,2]]-np.array(spec['anchor'])[[0,2]]
            # Retain all old common geometry; add only the real narrow rim
            # not supplied by the native deck. Ownership clipping below
            # prevents overlap with the reciprocal region's matching rim.
            rim=(relative@outward>=-42.)&(np.abs(relative@np.array([-outward[1],outward[0]]))<=4.250001)
            cut[rim]=np.minimum(cut[rim],-1.)
        grid=R._clip_scalar(grid,cut)
        if native_triangles is not None:grid=_subtract_native(grid,native_triangles)
        retained=[R._clip_scalar(build.terrain_meshes[n],R._edge_distance(build,region,build.terrain_meshes[n].positions[:,[0,2]])-3.) for n in item['names']]
        grid=_conform_boundary(grid,retained,build,region,native_triangles)
        final=M.merge([grid,*retained],material=grid.material)
        final=G.clip_owned_mesh(final,G.polygon_rectangles(polygon));final.recompute_normals(180)
        result.append(final)
    return result


def _footing_polygons(build):
    """Actual connected low geometry, excluding canopy and roof overhangs.

    Separate piers remain separate protected patches; joining their bounds
    would again freeze an entire bridge AABB and leave its banks hovering.
    """
    from northern_passes import _fixed_nodes,NATURAL_KINDS
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import ConvexHull,QhullError
    result=[];fixed=_fixed_nodes(build)
    ground_triangles=_triangles([m for n,m in build.terrain_meshes.items() if _base(n)])
    ground=VerticalRayIndex(ground_triangles) if len(ground_triangles) else None
    ground_cache={}
    for placement in build.placements:
        if placement.node not in fixed and (not placement.collides or placement.kind in NATURAL_KINDS|{'fallenlog','stump','mushrooms','leafdrift'}):continue
        mesh=build.meshes.get(placement.mesh)
        if mesh is None:continue
        parts=getattr(mesh,'all_parts',[mesh]);triangles=[];rotation=M.rotation_y(placement.rotation_y)[:3,:3]
        for part in parts:
            if not part.triangle_count:continue
            p=part.positions*placement.scale@rotation.T+placement.position
            triangles.append(p[part.indices.reshape(-1,3)])
        if not triangles:continue
        tri=np.concatenate(triangles);vertices=tri.reshape(-1,3)
        shell=M.Mesh(positions=vertices,normals=np.zeros_like(vertices),uvs=np.zeros((len(vertices),2)),indices=np.arange(len(vertices)))
        # On a slope, higher piers are genuine feet too. Classify structural
        # contact against the actual native soil, not the placement's single
        # lowest vertex. Trees retain their root band: a branch passing a hill
        # is not a second foundation.
        natural=placement.kind in NATURAL_KINDS or placement.mesh.lower().startswith('tree')
        if ground is not None and not natural:
            samples,lookup=np.unique(np.round(vertices[:,[0,2]],7),axis=0,return_inverse=True)
            for p in samples:
                key=tuple(p)
                if key not in ground_cache:ground_cache[key]=ground.top_hit(*p)
            support=np.array([ground_cache[tuple(p)] for p in samples],object)[lookup]
            present=np.array([v is not None for v in support])
            if present.any():
                distance=np.full(len(vertices),1000000.);distance[present]=vertices[present,1]-support[present].astype(float)-.6
            else:distance=vertices[:,1]-float(vertices[:,1].min()+.6)
        else:distance=vertices[:,1]-float(vertices[:,1].min()+.6)
        low=R._clip_scalar(shell,distance)
        if not low.triangle_count:continue
        points,labels=np.unique(np.round(low.positions,7),axis=0,return_inverse=True);faces=labels[low.indices.reshape(-1,3)]
        edges=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
        graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(points),len(points)))
        count,components=connected_components(graph,directed=False)
        for component in range(count):
            xz=np.unique(points[components==component][:,[0,2]],axis=0)
            try:polygon=xz[ConvexHull(xz).vertices]
            except QhullError:
                lo=xz.min(axis=0)-.025;hi=xz.max(axis=0)+.025
                polygon=np.array([lo,[hi[0],lo[1]],hi,[lo[0],hi[1]]])
            result.append(polygon)
    return result


def _footing_distance(points,polygon):
    sides=np.roll(polygon,-1,axis=0)-polygon
    relative=points[:,None,:]-polygon[None,:,:]
    cross=sides[None,:,0]*relative[:,:,1]-sides[None,:,1]*relative[:,:,0]
    inside=np.all(cross>=-1e-8,axis=1)
    along=np.clip(np.sum(relative*sides,axis=2)/np.maximum(np.sum(sides*sides,axis=1),1e-18),0.,1.)
    distances=np.linalg.norm(relative-along[:,:,None]*sides,axis=2).min(axis=1)
    distances[inside]=0.
    return distances


def _split_native_landing(mesh,native_triangles,roads,water):
    """Conform dry bank triangles to the real native deck footprint edge.

    The original terrain under a bridge remains present. New edge vertices
    let outside soil meet the road without interpolation from a low vertex
    under the deck. Splitting preserves every position/attribute and includes
    wet faces so adjacent material and shore triangles share the same cuts.
    The seating stage retains submerged bed at these new vertices.
    """
    if not mesh.triangle_count or not len(native_triangles):return mesh
    # Select whole native cutters once from the corridor bounds. Do not pick
    # terrain faces by centroid: neighboring material meshes must receive
    # identical cuts on a shared edge before nonlinear seating.
    native_lo=native_triangles[:,:,[0,2]].min(axis=1);native_hi=native_triangles[:,:,[0,2]].max(axis=1)
    selected=np.zeros(len(native_triangles),bool)
    for road in roads:
        xz=np.asarray(road['stations'])[:,[0,2]];lo=xz.min(axis=0)-12.;hi=xz.max(axis=0)+12.
        selected|=np.all(native_hi>=lo,axis=1)&np.all(native_lo<=hi,axis=1)
    native_triangles=native_triangles[selected]
    if not len(native_triangles):return mesh
    oracle=VerticalRayIndex(native_triangles)
    fields=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:fields.append(mesh.colors)
    data=np.concatenate(fields,axis=1);faces=mesh.indices.reshape(-1,3)
    output=[]
    def projected_area(polygon):
        xz=polygon[:,[0,2]]
        return abs(float(np.sum(xz[:,0]*np.roll(xz[:,1],-1)-xz[:,1]*np.roll(xz[:,0],-1))))*.5
    for face_index,ids in enumerate(faces):
        original=data[ids]
        lo=original[:,[0,2]].min(axis=0);hi=original[:,[0,2]].max(axis=0)
        low=np.floor((lo-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int);high=np.floor((hi-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int)
        candidates=set()
        for x in range(low[0],high[0]+1):
            for z in range(low[1],high[1]+1):candidates.update(oracle.buckets.get((x,z),()))
        outside=[original];inside_parts=[]
        for index in sorted(candidates):
            xz=native_triangles[index][:,[0,2]]
            if (xz.max(axis=0)<lo-1e-8).any() or (xz.min(axis=0)>hi+1e-8).any():continue
            a,b=xz[1]-xz[0],xz[2]-xz[0];area=a[0]*b[1]-a[1]*b[0]
            if abs(area)<1e-10:continue
            if area<0:xz=xz[[0,2,1]]
            remaining=[]
            for polygon in outside:
                inside=polygon;pieces=[]
                for a,b in zip(xz,np.roll(xz,-1,axis=0)):
                    if not len(inside):break
                    vector=b-a;relative=inside[:,[0,2]]-a;distance=vector[0]*relative[:,1]-vector[1]*relative[:,0]
                    kept=[];discarded=[]
                    for i,j in zip(range(len(inside)),np.roll(np.arange(len(inside)),-1)):
                        v,w=inside[i],inside[j];d,e=distance[i],distance[j]
                        (kept if d>=0 else discarded).append(v)
                        if (d>=0)!=(e>=0):
                            cut=v+(w-v)*(d/(d-e));kept.append(cut);discarded.append(cut)
                    if len(discarded)>=3:pieces.append(np.asarray(discarded))
                    inside=np.asarray(kept)
                if len(inside)>=3 and projected_area(inside)>1e-10:
                    remaining.extend(pieces);inside_parts.append(inside)
                else:remaining.append(polygon)
            outside=remaining
            if not outside:break
        for polygon in outside+inside_parts:
            output.extend(polygon[[0,i,i+1]] for i in range(1,len(polygon)-1))
    values=np.concatenate(output);result=mesh.copy();result.positions,result.normals,result.uvs=values[:,:3],values[:,3:6],values[:,6:8]
    if result.colors is not None:result.colors=values[:,8:12]
    result.indices=np.arange(len(values));return result


def _nearest_road_height(ray,point,radius=2.):
    """Nearest actual road edge for a shoulder whose radial sample is a hole.

    Native bridge footprints are subtracted from the road. A radial sample
    can therefore miss even where an exposed road wedge is millimetres away.
    This fallback is used only outside the ribbon and outside native decks.
    """
    point=np.asarray(point);low=np.floor((point-radius-[ray.min_x,ray.min_z])/ray.cell).astype(int)
    high=np.floor((point+radius-[ray.min_x,ray.min_z])/ray.cell).astype(int);ids=set()
    for x in range(low[0],high[0]+1):
        for z in range(low[1],high[1]+1):ids.update(ray.buckets.get((x,z),()))
    if not ids:return None
    tri=ray.triangles[sorted(ids)];a=tri;v=np.roll(tri,-1,axis=1)-tri
    xz=a[:,:,[0,2]];delta=point-xz;side=v[:,:,[0,2]]
    t=np.clip(np.sum(delta*side,axis=2)/np.maximum(np.sum(side*side,axis=2),1e-18),0.,1.)
    closest=a+t[:,:,None]*v;distance=np.linalg.norm(closest[:,:,[0,2]]-point,axis=2)
    index=np.unravel_index(int(np.argmin(distance)),distance.shape)
    return float(closest[index][1]) if distance[index]<=radius else None


def _seat(build,region,inputs):
    roads=[r['road'] for r in inputs]
    ray=VerticalRayIndex(_triangles([build.terrain_meshes[r['names'][0]] for r in inputs]))
    footprints=_footing_polygons(build);cache={};native_cache={};water_cache={};shoulder_cache={}
    native_triangles=_native_walk(build);water_triangles=_triangles(list(build.water_meshes.values()))
    native=VerticalRayIndex(native_triangles) if len(native_triangles) else None
    water=VerticalRayIndex(water_triangles) if len(water_triangles) else None
    def smooth(x):x=np.clip(x,0.,1.);return x*x*(3.-2.*x)
    def shape(points):
        out=points.copy();xz=points[:,[0,2]];distance=np.full(len(points),np.inf);centres=np.zeros_like(xz);bridge=np.zeros(len(points),bool)
        widths=np.full(len(points),4.25)
        for item in inputs:
            stations,length=item['points'],item['length'];d,a=G._road_coordinates(xz,stations[:,[0,2]]);near=d<distance
            centres[near,0]=np.interp(a[near]*length[-1],length,stations[:,0]);centres[near,1]=np.interp(a[near]*length[-1],length,stations[:,2]);distance[near]=d[near]
            bridge[near]=np.interp(a[near]*length[-1],length,item['bridge'].astype(float))>=.5
            widths[near]=_half_width(item,a[near]*length[-1])
        weight=(1-smooth((distance-(widths+1.25))/5.))*smooth((R._edge_distance(build,region,xz)-3.)/3.)
        causeway=np.zeros(len(points),bool)
        # Built deck footprints and their actual support volumes stay intact.
        # Do not infer a whole road-width hole from a centreline bridge hit.
        for item in inputs:
            if item['spec'].get('profile')=='causeway':
                spec=item['spec'];outward=np.asarray(spec['outward']);relative=xz-np.array(spec['anchor'])[[0,2]]
                depth=relative@outward;lateral=relative@np.array([-outward[1],outward[0]])
                causeway|=(depth>=-42.)&(np.abs(lateral)<=4.25)
        for polygon in footprints:
            near=(weight>1e-8)&np.all(xz>=polygon.min(axis=0)-1.5,axis=1)&np.all(xz<=polygon.max(axis=0)+1.5,axis=1)
            if near.any():weight[near]*=smooth(_footing_distance(xz[near],polygon)/1.5)
        for i in np.flatnonzero(weight>1e-8):
            delta=xz[i]-centres[i];length=np.linalg.norm(delta)
            # Exact footprint cuts can differ from the same road-distance
            # calculation by a few ULPs. Keep those boundary vertices on the
            # visible edge; projecting them1mm inward can enter the native
            # subtraction hole and leave a dry-bank notch.
            sample=xz[i] if distance[i]<=widths[i]+1e-7 else centres[i]+delta*min(1.,(widths[i]-.001)/max(length,1e-9))
            key=tuple(np.round(sample,7));point_key=tuple(np.round(xz[i],7))
            if key not in cache:cache[key]=ray.top_hit(*sample)
            if point_key not in native_cache:native_cache[point_key]=native.top_hit(*xz[i]) if native is not None else None
            deck=native_cache[point_key];height=cache[key]
            if height is None and deck is not None:
                # Existing dry soil may protrude through a causeway landing.
                # Only cut that obstruction; lower channel bed stays lower.
                if points[i,1]>deck-.03:height=deck
            elif height is None:
                # A bend's clipped skin may end just inside its nominal
                # distance band. Dry shoulder soil must still follow the
                # nearest actual edge; a missing wet floor is not filled.
                if water is not None:
                    if point_key not in water_cache:water_cache[point_key]=water.top_hit(*xz[i])
                    level=water_cache[point_key]
                    if level is not None and points[i,1]<=level+.15:continue
                if key not in shoulder_cache:shoulder_cache[key]=_nearest_road_height(ray,sample)
                height=shoulder_cache[key]
            if height is None:continue
            target=height-.03-.035*max(distance[i]-widths[i],0.)**2
            if target>points[i,1] and causeway[i]:continue
            if target>points[i,1] and deck is not None and water is not None:
                if point_key not in water_cache:water_cache[point_key]=water.top_hit(*xz[i])
                level=water_cache[point_key]
                if level is not None and points[i,1]<=level+.15:continue
            out[i,1]+=(target-out[i,1])*weight[i]
        return out
    G._lift_unprotected_scatter(build,shape)
    for name,mesh in build.terrain_meshes.items():
        if _base(name):
            R.refine_bed(mesh,roads)
            conformed=_split_native_landing(mesh,native_triangles,roads,water)
            for field in ('positions','normals','uvs','colors','indices'):setattr(mesh,field,getattr(conformed,field))
            mesh.positions=shape(mesh.positions);mesh.recompute_normals(180)
    t=build.terrain;p=np.c_[t.gx.ravel(),t.height.ravel(),t.gz.ravel()];t.height=shape(p)[:,1].reshape(t.height.shape)


def apply(build,region,road_ids=None,exclude=()):
    """Replace connector quads after shared/local grading and the outer cut.

    Pass road_ids for a bounded regional pilot. Solved northern roads are
    always excluded. Returns a serializable audit and never touches native
    bridge vertices or any water mesh. Optional contactWidths gives full
    metres (3.8..8.5) at each contactStations control; these interpolate along
    the native approach and retain full width throughout the last 42 m.
    """
    if getattr(build,'_connector_finish_applied',False):raise ValueError('Connector finish applied twice')
    omitted=SOLVED.get(region,set())|set(exclude)
    selected=[r for r in getattr(build,'geography_roads',[]) if r['id'] not in omitted and (road_ids is None or r['id'] in road_ids)]
    if not selected:return {'region':region,'roads':[]}
    ground=VerticalRayIndex(_triangles([m for n,m in build.terrain_meshes.items() if _base(n)]))
    native_triangles=_native_walk(build);native=VerticalRayIndex(native_triangles) if len(native_triangles) else None
    inputs=_road_inputs(build,region,selected,ground,native)
    outputs=_union_grid(build,region,inputs,native_triangles,ground)
    for item,mesh in zip(inputs,outputs):
        first=item['names'][0];removed=set(item['names'][1:]);build.terrain_meshes[first]=mesh
        for name in removed:del build.terrain_meshes[name]
        for spec in build.streaming_borders:
            old=spec.get('sceneNodes',[]);spec['sceneNodes']=[n for n in old if n not in removed]
            if removed.intersection(old) and first not in spec['sceneNodes']:spec['sceneNodes'].append(first)
    actual=VerticalRayIndex(np.concatenate([_triangles(outputs),native_triangles]))
    for item in inputs:
        for point in item['points']:
            height=actual.top_hit(*point[[0,2]])
            if height is not None:point[1]=height-.03
        item['road']['stations']=item['points'].tolist()
        item['road']['length']=float(item['length'][-1])
        item['road']['maximumGrade']=float(np.max(np.abs(np.diff(item['points'][:,1]))/np.diff(item['length'])))
    paint={n:m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_') and ('_StreamCollar_' in n or '_ContinentBlend_' in n)}
    # Nested B paint is a coverage subset of direct B with the same material.
    # Keep original boundary pieces exactly; discard redundant inland copies.
    for name in list(paint):
        if len(collar_layers(name))>1:
            mesh=paint.pop(name)
            build.terrain_meshes[name]=R._clip_scalar(mesh,R._edge_distance(build,region,mesh.positions[:,[0,2]])-3.)
    old_paint={n:Substrate([m.copy()]) for n,m in paint.items() if m.triangle_count}
    _seat(build,region,inputs)
    bases={}
    for name,mesh in build.terrain_meshes.items():
        if _base(name) and mesh.triangle_count:bases.setdefault(substrate_name(name),[]).append(mesh)
    order=[s['id'] for s in build.streaming_borders if any(collar_layers(n) and collar_layers(n)[-1][0]==s['id'] for n in paint)]
    slots={n:i for i,n in enumerate(order)};peers=sorted({p for e in G.boundary_segments(region) for p in e['regions'] if p!=region});samplers={}
    for name,mesh in paint.items():
        if not mesh.triangle_count:continue
        base=substrate_name(name)
        if base not in samplers:samplers[base]=Substrate(bases[base])
        R.refine_bed(mesh,selected)
        xz=mesh.positions[:,[0,2]];new=samplers[base].sample(xz)+paint_bias(name,slots,peers)
        edge=R._edge_distance(build,region,xz);blend=np.clip((edge-3.)/3.,0.,1.);blend=blend*blend*(3.-2.*blend)
        keep=blend<1.
        if keep.any():new[keep]=old_paint[name].sample(xz[keep])*(1.-blend[keep])+new[keep]*blend[keep]
        mesh.positions[:,1]=new;mesh.recompute_normals(180)
    import causeway_rims
    construction=causeway_rims.apply(build,region)
    build._connector_finish_applied=True
    audit={'region':region,'roads':[{'id':r['road']['id'],'bridgeSamplesPreserved':int(r['bridge'].sum()),'triangles':int(m.triangle_count)} for r,m in zip(inputs,outputs)],'boundaryPreservedMetres':3.,'causewayPhysicalRimAdded':any(r['spec'].get('profile')=='causeway' for r in inputs),'nativeBridgeTrianglesPreserved':len(native_triangles)}
    build.connector_finish_audit=audit
    audit['construction']=construction
    build.notes.append('Generated connector finish: one connected half-metre road bed at curves and shared junctions, intact boundary strip and native bridges, terrain and paint seated from actual final triangles.')
    return audit
