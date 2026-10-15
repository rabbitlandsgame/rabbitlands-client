"""Static views into a neighbour, sampled from its authored terrain geometry.

The view begins outside the served footprint and never creates walk collision.
It uses the receiving biome's shared ground recipe, with an explicit survey
alignment; runtime actors and simulation still change maps at the border.
"""
import hashlib
import json
import numpy as np
from scipy.spatial import cKDTree
from amberwood import mesh as M
import glb_reader as GLB
from verify_runtime import VerticalRayIndex


def clip_window(mesh, edge, forward, side, half_width=80):
    """Clip the far side of a border plane, retaining exact seam vertices."""
    faces=mesh.indices.reshape(-1,3)
    depths=(mesh.positions[:,[0,2]]-edge)@forward
    lateral=((mesh.positions[faces][:,:,[0,2]]-edge)@side).mean(axis=1)
    active=abs(lateral)<half_width
    lo,hi=depths[faces].min(axis=1),depths[faces].max(axis=1)
    kept=faces[~active | (hi<=0)].reshape(-1).tolist()
    columns=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:columns.append(mesh.colors)
    attributes=np.concatenate(columns,axis=1)
    added=[]
    on_plane=mesh.positions[abs(depths)<1e-8][:,[0,2]]-edge
    seam=[float(u) for u in on_plane@side if abs(u)<=half_width]
    for face in faces[active & (lo<0) & (hi>0)]:
        polygon=[]
        for i,j in ((0,1),(1,2),(2,0)):
            a,b=face[i],face[j];da,db=depths[a],depths[b]
            if da<=0:polygon.append(attributes[a])
            if (da<=0)!=(db<=0):
                vertex=attributes[a]+(attributes[b]-attributes[a])*(da/(da-db))
                polygon.append(vertex)
                u=float((vertex[[0,2]]-edge)@side)
                if abs(u)<=half_width:seam.append(u)
        start=len(attributes)+len(added)
        added.extend(polygon)
        for i in range(1,len(polygon)-1):kept.extend([start,start+i,start+i+1])
    if added:
        attributes=np.vstack([attributes,added])
        mesh.positions=attributes[:,:3];mesh.normals=attributes[:,3:6]
        mesh.uvs=attributes[:,6:8]
        if mesh.colors is not None:mesh.colors=attributes[:,8:12]
    mesh.indices=np.asarray(kept,dtype=np.int64)
    return seam


def add_vista(build, package, portal_id, edge, outward, inward, material, label,
              road_half_width=2.4, scenery=False):
    document,body=GLB.load(package/'world.glb')
    manifest=json.loads((package/'world.json').read_text())
    portal=next(p for p in manifest['portals'] if p['id']==portal_id)
    anchor=np.asarray(portal['position'],float)
    triangles=GLB.triangles(document,body,GLB.named(document,'Terrain_'))
    vertices=triangles.reshape(-1,3)
    source_xz,inverse=np.unique(vertices[:,[0,2]],axis=0,return_inverse=True)
    source_y=np.full(len(source_xz),-np.inf);np.maximum.at(source_y,inverse,vertices[:,1])
    tree=cKDTree(source_xz)
    forward=np.asarray(outward,float);side=np.array([-forward[1],forward[0]])
    source_forward=np.asarray(inward,float);source_side=np.array([-source_forward[1],source_forward[0]])
    edge=np.asarray(edge,float)
    host_triangles=np.concatenate([m.positions[m.indices].reshape(-1,3,3)
        for name,m in build.terrain_meshes.items() if not name.startswith('Backdrop')])
    index=VerticalRayIndex(host_triangles,cell=4)
    seam=[]
    for old in build.terrain_meshes.values():seam.extend(clip_window(old,edge,forward,side))
    for old in build.water_meshes.values():clip_window(old,edge,forward,side)
    # Match every host cut vertex, so the join has neither gaps nor overlaps.
    us=np.unique(np.round(np.r_[np.arange(-80,81,2.0),seam],7));vs=np.arange(0,141,2.0)
    uu,vv=np.meshgrid(us,vs)
    source=anchor[[0,2]]+uu[...,None]*source_side+vv[...,None]*source_forward
    distances,indices=tree.query(source.reshape(-1,2),k=4)
    weights=1/np.maximum(distances,1e-6)**2
    ys=((source_y[indices]*weights).sum(axis=1)/weights.sum(axis=1)).reshape(uu.shape)
    _,at=tree.query(anchor[[0,2]])
    target=edge+uu[...,None]*side+vv[...,None]*forward
    def host_height(point):
        hit=index.top_hit(*point)
        return float(build.terrain.height_at(*point)) if hit is None else hit
    edge_y=np.array([host_height(edge+u*side) for u in us])
    slope=np.array([edge_y[i]-host_height(edge+u*side-forward) for i,u in enumerate(us)])
    centre_y=float(build.terrain.height_at(*edge))
    blend=np.clip(vv/40,0,1);blend=blend*blend*(3-2*blend)
    ys=(edge_y+np.clip(slope,-.45,.45)*np.minimum(vv,12))*(1-blend)+(ys-source_y[at]+centre_y)*blend
    positions=np.stack([target[...,0],ys,target[...,1]],axis=-1).reshape(-1,3)
    faces=[];cols=len(us)
    for row in range(len(vs)-1):
        for col in range(cols-1):
            a=row*cols+col;b=a+1;c=a+cols;d=c+1
            faces.extend([a,c,b,b,c,d])
    piece=M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(len(positions),1)),
                 uvs=positions[:,[0,2]]*.28,indices=np.asarray(faces),material=material+'_ground')
    # Grid winding depends on the chosen lateral axis.
    tri=piece.positions[piece.indices[:3]]
    if np.cross(tri[1]-tri[0],tri[2]-tri[0])[1]<0:piece.flip_winding()
    piece.recompute_normals(180)
    # The road continues through the view, narrowing and bending with distance.
    centre=4*(1-np.cos(vv/42))
    width=road_half_width*(1-.35*np.clip(vv/100,0,1))
    ragged=.25*np.sin(vv*.7)+.18*np.sin(vv*1.7)
    coverage=np.clip(.5+(width-abs(uu-centre)+ragged)/1.2,0,1).reshape(-1)
    piece.colors=np.ones((len(positions),4));piece.colors[:,3]=1-coverage
    path=piece.copy();path.material='woodland_track_ground';path.colors[:,3]=coverage
    # Alpha masks share a seam, not two complete 160 m terrain sheets. Drop
    # triangles whose coverage can never pass the material's alpha test.
    from amberwood.terrain import _compact
    for part in (piece,path):
        faces=part.indices.reshape(-1,3)
        part.indices=faces[part.colors[faces,3].max(axis=1)>=.5].reshape(-1)
    piece,path=_compact(piece),_compact(path)
    build.terrain_meshes['Backdrop_Neighbour_'+label]=piece
    build.terrain_meshes['Backdrop_NeighbourRoad_'+label]=path
    # Scenery authored on the replaced far-side hills would float in this view.
    build.placements[:]=[p for p in build.placements if not
        (float((np.array(p.position)[[0,2]]-edge)@forward)>0 and
         abs(float((np.array(p.position)[[0,2]]-edge)@side))<80)]
    # Paired regions may show their actual tree silhouettes as static scenery.
    # Only ordinary trees in the visible receiving strip are copied. No actors,
    # services, triggers, walk surfaces or recursively copied vistas are added.
    scenery_count=0
    if scenery:
        from regionbuild import Placement
        matrices,_=GLB.hierarchy(document)
        rotation=np.outer(side,source_side)+np.outer(forward,source_forward)
        for node_id,node in enumerate(document['nodes']):
            if not node.get('name','').startswith('Tree_') or 'mesh' not in node:continue
            matrix=matrices[node_id];origin=matrix[:3,3]
            relative=origin[[0,2]]-anchor[[0,2]]
            u,v=float(relative@source_side),float(relative@source_forward)
            if not (8<v<108 and abs(u)<60):continue
            if abs(u-4*(1-np.cos(v/42)))<road_half_width+5:continue
            row=int(v//2);fraction=v/2-row
            y=float(np.interp(u,us,ys[row])*(1-fraction)+np.interp(u,us,ys[row+1])*fraction)
            d,at=tree.query(origin[[0,2]],k=4);w=1/np.maximum(d,1e-6)**2
            source_floor=float((source_y[at]*w).sum()/w.sum())
            target_xz=edge+u*side+v*forward
            pivot=np.array([target_xz[0],y,target_xz[1]])
            for part_id,primitive in enumerate(document['meshes'][node['mesh']]['primitives']):
                attrs=primitive['attributes']
                material_name=document['materials'][primitive['material']]['name']
                points=GLB.accessor(document,body,attrs['POSITION']).astype(float)
                part=M.Mesh(positions=points,
                    normals=GLB.accessor(document,body,attrs['NORMAL']).astype(float),
                    uvs=GLB.accessor(document,body,attrs['TEXCOORD_0']).astype(float),
                    indices=GLB.accessor(document,body,primitive['indices']).reshape(-1).astype(np.int64),
                    colors=GLB.accessor(document,body,attrs['COLOR_0']).astype(float) if 'COLOR_0' in attrs else None,
                    material=material_name)
                part.transform(matrix)
                part.positions[:,[0,2]]=(part.positions[:,[0,2]]-origin[[0,2]])@rotation.T
                part.positions[:,1]-=source_floor
                part.normals[:,[0,2]]=part.normals[:,[0,2]]@rotation.T
                key=f'Vista_{label}_{node_id}_{part_id}'
                build.add_mesh(key,part)
                build.place(Placement(key,key,tuple(pivot),kind='vista'))
                if not hasattr(build,'vista_materials'):build.vista_materials=set()
                build.vista_materials.add(material_name)
                scenery_count+=1
    return {'region':manifest['asset']['id'],'portal':portal_id,'depthMetres':140,
            'widthMetres':160,'edge':edge.tolist(),'direction':forward.tolist(),
            'sourceGlbSha256':hashlib.sha256((package/'world.glb').read_bytes()).hexdigest(),
            'staticSceneryMeshes':scenery_count,
            'mode':'static terrain view; simulation changes at the road crossing'}
