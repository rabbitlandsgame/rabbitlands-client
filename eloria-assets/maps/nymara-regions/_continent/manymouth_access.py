"""Visible timber circulation through the delta's retained settlements.

Retained houses, porches and landings stay intact. Narrow local boardwalks
join their actual upper floors and nearby public approaches; terrain and water
remain unchanged. Existing floor faces are subtracted to avoid duplicate decks.
"""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import scene_io as S
import manymouth_support as D
import landscape as L
from bridge_export import G,M,RoadOutline,_clip_halfplane,triangulate_floor,_area_xz

REGION='manymouth_delta'
GROUP=REGION+'.north_fishing'
LEVEL=1.75
HALF_WIDTH=1.3


def subtract(polygons,clip):
    result=[];clip=np.asarray(clip,float)
    for polygon in polygons:
        if np.any(polygon[:,[0,2]].max(axis=0)<clip.min(axis=0)-1e-7) or np.any(polygon[:,[0,2]].min(axis=0)>clip.max(axis=0)+1e-7):
            result.append(polygon);continue
        inside=polygon
        for a,b in zip(clip,np.roll(clip,-1,axis=0)):
            outside=_clip_halfplane(inside,a,b,False)
            if len(outside):result.append(outside)
            inside=_clip_halfplane(inside,a,b)
            if not len(inside):break
    return result


def fishing_faces(world,content):
    group=[o for o in content.objects if o.get('assembly')==GROUP]
    if len(group)!=9:raise ValueError('Fishing access needs all nine retained assembly members')
    by_name={o['node']:o for o in group};translation=np.asarray(content.assembly_records[GROUP]['translation'])
    anchor=np.asarray(content.assembly_records[GROUP]['referenceXZ'])+translation[[0,2]]
    level=LEVEL+translation[1]
    center=lambda name:(by_name[name]['low'][[0,2]]+by_name[name]['high'][[0,2]])*.5
    porch=[center(f'north_fishing_porch_{i:02d}') for i in range(4)]
    landing=center('Landing_north_fishing')
    # One quiet street between the paired houses, then short door branches.
    spine_a=porch[3];spine_b=landing
    axis=spine_b-spine_a
    paths=[np.array([spine_a,spine_b])]
    for p in porch[:3]:
        t=np.clip(np.dot(p-spine_a,axis)/np.dot(axis,axis),0,1)
        paths.append(np.array([p,spine_a+t*axis]))
    roads=[{'points':np.c_[p[:,0],np.full(len(p),level),p[:,1]],'width':HALF_WIDTH} for p in paths]
    outline=RoadOutline(SimpleNamespace(roads=roads));matrices,_=S.GR.hierarchy(content.documents[REGION][0])
    exclusions=[]
    for obj in group:
        faces=D._triangles(content,obj,matrices=matrices)
        for face in faces:
            normal=np.cross(face[1]-face[0],face[2]-face[0])
            if normal[1]<=1e-7 or np.max(abs(face[:,1]-level))>.025:continue
            exclusions.append(face[::-1][:,[0,2]])
        if obj['collides']:
            lo,hi=obj['low'][[0,2]],obj['high'][[0,2]]
            exclusions.append(np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]]))
    faces=cut_links(outline,level,exclusions)
    q=faces[:,:,[0,2]].reshape(-1,2)
    if not np.all(world.owner_at(q[:,0],q[:,1])==world.ids.index(REGION)):raise ValueError('Fishing boardwalk leaves territory')
    return faces,paths,level


def cut_links(outline,level,exclusions):
    accepted=[];covered=[]
    for capsule in outline.polygons:
        polygon=np.c_[capsule[::-1,0],np.full(len(capsule),level),capsule[::-1,1]]
        pieces=[polygon]
        for clip in exclusions+covered:
            pieces=subtract(pieces,clip)
            if not pieces:break
        accepted.extend(pieces);covered.append(capsule)
    faces=[]
    for polygon in accepted:
        faces.extend(triangulate_floor(polygon))
    faces=np.asarray(faces,float).reshape(-1,3,3).astype(np.float32)
    normal=np.cross(faces[:,1].astype(float)-faces[:,0],faces[:,2].astype(float)-faces[:,0])
    if np.any(normal[:,1]<-1e-8):raise ValueError('Fishing boardwalk floor wound downward')
    faces=faces[normal[:,1]>2e-8]
    if not len(faces):raise ValueError('Fishing boardwalk has no new visible surface')
    return faces


def market_faces(world,content):
    """Restore the short north entrance link of the intact market hall."""
    anchor=np.asarray(content.assembly_records[REGION+'.boardwalk-town']['translation'])
    # Surveyed sixth pairs in this compound's frame, each on an actual floor.
    reference=np.array([475.9741,0.,1184.8415])
    delta=anchor-reference
    path=np.array([[507.5,1152.5],[504.5,1157.5]])+delta[[0,2]]
    level=2.2+anchor[1]
    outline=RoadOutline(SimpleNamespace(roads=[{'points':np.c_[path[:,0],np.full(2,level),path[:,1]],'width':1.3}]))
    exclusions=[];matrices,_=S.GR.hierarchy(content.documents[REGION][0])
    low=path.min(axis=0)-4;high=path.max(axis=0)+4
    for obj in content.objects:
        if obj['region']!=REGION or np.any(obj['high'][[0,2]]<low) or np.any(obj['low'][[0,2]]>high):continue
        if obj.get('kind') in ('tree','rock','foliage','undergrowth'):continue
        for face in D._triangles(content,obj,matrices=matrices):
            normal=np.cross(face[1]-face[0],face[2]-face[0])
            if normal[1]>1e-7 and np.max(abs(face[:,1]-level))<.025:exclusions.append(face[::-1][:,[0,2]])
        # Stalls have collision walls; the open market hall's broad bounds also
        # contain its useful floor and must not be treated as a solid rectangle.
        if obj['node'].startswith('market_stall_'):
            lo,hi=obj['low'][[0,2]],obj['high'][[0,2]]
            exclusions.append(np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]]))
    faces=cut_links(outline,level,exclusions)
    q=faces[:,:,[0,2]].reshape(-1,2)
    if not np.all(world.owner_at(q[:,0],q[:,1])==world.ids.index(REGION)):raise ValueError('Market link leaves Manymouth')
    return faces,path,level


def paddy_faces(world,content):
    """One street between the rice hamlet's two rows, with eight porch links."""
    identity=REGION+'.paddy_hamlet'
    group=[o for o in content.objects if o.get('assembly')==identity]
    by_name={o['node']:o for o in group}
    required={'Landing_paddy_hamlet',*(f'paddy_hamlet_{kind}_{i:02d}' for kind in ('house','porch') for i in range(8))}
    if set(by_name)!=required:raise ValueError('Paddy access needs all eight rigid houses and porches plus their landing')
    translation=np.asarray(content.assembly_records[identity]['translation'])
    level=1.75+float(translation[1])
    center=lambda name:(by_name[name]['low'][[0,2]]+by_name[name]['high'][[0,2]])*.5
    porches=np.array([center(f'paddy_hamlet_porch_{i:02d}') for i in range(8)])
    landing=center('Landing_paddy_hamlet')
    pairs=porches.reshape(4,2,2).mean(axis=1)
    spine=np.vstack((landing,pairs))
    paths=[np.array([a,b]) for a,b in zip(spine,spine[1:])]
    paths.extend(np.array([point,pairs[i//2]]) for i,point in enumerate(porches))
    roads=[{'points':np.c_[path[:,0],np.full(2,level),path[:,1]],'width':HALF_WIDTH} for path in paths]
    outline=RoadOutline(SimpleNamespace(roads=roads))
    matrices,_=S.GR.hierarchy(content.documents[REGION][0]);exclusions=[]
    for obj in group:
        floors=D._triangles(content,obj,matrices=matrices)
        normal=np.cross(floors[:,1]-floors[:,0],floors[:,2]-floors[:,0])
        keep=(normal[:,1]>1e-7)&(np.max(abs(floors[:,:,1]-level),axis=1)<.025)
        if not keep.any():raise ValueError(obj['node']+': paddy floor no longer meets the shared street datum')
        exclusions.extend(face[::-1][:,[0,2]] for face in floors[keep])
        if obj['collides']:
            lo,hi=obj['low'][[0,2]],obj['high'][[0,2]]
            exclusions.append(np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]]))
    faces=cut_links(outline,level,exclusions)
    vertices=faces.reshape(-1,3)
    if not np.all(world.owner_at(vertices[:,0],vertices[:,2])==world.ids.index(REGION)):
        raise ValueError('Paddy street leaves Manymouth ownership')
    if np.max(abs(vertices[:,1]-level))>1e-6:raise ValueError('Encoded paddy street leaves its shared floor datum')
    return faces,paths,level,{'porches':porches.tolist(),'landing':landing.tolist(),'spine':spine.tolist()}


def boardwalk_fascia(faces,material):
    """Visible timber thickness below the actual floor, including clipped ends."""
    edges={}
    for face in faces:
        for a,b in zip(face,np.roll(face,-1,axis=0)):
            key=tuple(sorted((tuple(np.round(a,5)),tuple(np.round(b,5)))))
            if key in edges:edges[key]=None
            else:edges[key]=(a,b)
    walls=[]
    for edge in edges.values():
        if edge is None:continue
        a,b=np.asarray(edge,dtype=float);a=a-[0,.01,0];b=b-[0,.01,0]
        c=b-[0,.15,0];d=a-[0,.15,0]
        walls.extend((np.array([a,b,c]),np.array([a,c,d])))
    p=np.asarray(walls,np.float32).reshape(-1,3)
    normals=np.repeat(np.cross(np.asarray(walls)[:,1]-np.asarray(walls)[:,0],np.asarray(walls)[:,2]-np.asarray(walls)[:,0]),3,axis=0)
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-9)
    return M.Mesh(positions=p,normals=normals,uvs=p[:,[0,2]]*.4,indices=np.arange(len(p)),material=material)


def build_manymouth_access(world,content,path):
    if REGION not in world.ids:return []
    if REGION in getattr(world,'authoring_snapshots',{}):
        destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True)
        G.GltfBuilder('Saved Manymouth access authority').write_glb(str(destination))
        world.manymouth_access={'region':REGION,'skipped':'saved-authoring-authority'}
        return []
    destination=Path(path)
    faces,paths,level=fishing_faces(world,content)
    builder=G.GltfBuilder('Eloria Manymouth fishing boardwalk')
    for name,color in (('timber',(.43,.30,.17)),('posts',(.25,.17,.105))):
        builder.add_material(G.Material('fishing_'+name,base_color=tuple(np.asarray(color)**2.2)+(1.,),roughness=.95,double_sided=False))
    parts=[]
    def add(name,mesh):
        # Every walk this module builds is a designed deck the plan names (the village streets register their own).
        if name.startswith('Walk_') and not name.startswith('Walk_Manymouth_Village_'):
            L.require_designed_deck(getattr(world,'plan',None) or {},name,'manymouth_access')
        builder.add_mesh(name,mesh,with_tangents=False);root=builder.add_node(G.Node(name,mesh=name))
        parts.append({'region':REGION,'node':name,'roots':[root],'bounds':mesh.bounds(),'segment':[],'collides':False})
    positions=faces.reshape(-1,3)
    mesh=M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(len(positions),1)),uvs=positions[:,[0,2]]*.4,indices=np.arange(len(positions)),material='fishing_timber')
    add('Walk_Manymouth_FishingBoardwalk',mesh)
    posts=[]
    for path in paths:
        axis=path[1]-path[0];length=np.linalg.norm(axis)
        if length<1:continue
        side=np.array([-axis[1],axis[0]])/length
        for distance in np.arange(2.,length-1.,4.):
            center=path[0]+axis*(distance/length)
            for sign in (-1,1):
                p=center+side*(HALF_WIDTH-.13)*sign;bed=float(world.height_at(*p));height=level-.08-bed
                if height>.35:posts.append(M.box((.17,height,.17),center=(p[0],bed+height*.5,p[1]),material='fishing_posts'))
    if posts:add('Manymouth_FishingBoardwalk_Piles',M.merge(posts,material='fishing_posts'))
    market,market_path,market_level=market_faces(world,content)
    v=market.reshape(-1,3)
    add('Walk_Manymouth_MarketEntrance',M.Mesh(positions=v,normals=np.tile([0.,1.,0.],(len(v),1)),uvs=v[:,[0,2]]*.4,indices=np.arange(len(v)),material='fishing_timber'))
    paddy,paddy_paths,paddy_level,paddy_report=paddy_faces(world,content)
    v=paddy.reshape(-1,3)
    add('Walk_Manymouth_PaddyStreet',M.Mesh(positions=v,normals=np.tile([0.,1.,0.],(len(v),1)),uvs=v[:,[0,2]]*.4,indices=np.arange(len(v)),material='fishing_timber'))
    add('Manymouth_PaddyStreet_Fascia',boardwalk_fascia(paddy,'fishing_timber'))
    paddy_posts=[];post_contacts=[]
    for branch in paddy_paths:
        axis=branch[1]-branch[0];length=np.linalg.norm(axis)
        if length<1:continue
        side=np.array([-axis[1],axis[0]])/length
        for distance in np.arange(1.,length-.5,4.):
            center=branch[0]+axis*(distance/length)
            for sign in (-1,1):
                p=center+side*(HALF_WIDTH-.13)*sign;bed=float(world.height_at(*p));top=paddy_level-.08
                if top-bed>.35:
                    paddy_posts.append(M.box((.17,top-bed+.05,.17),center=(p[0],(bed-.05+top)*.5,p[1]),material='fishing_posts'))
                    post_contacts.append([float(p[0]),bed-.05,float(p[1])])
    if paddy_posts:add('Manymouth_PaddyStreet_Piles',M.merge(paddy_posts,material='fishing_posts'))
    from manymouth_village_streets import build_village_streets,floor_samples,deck_name
    village_reports=[]
    for village_faces,village_paths,village_report in build_village_streets(world,content):
        identity=village_report['id'];v=village_faces.reshape(-1,3)
        normal=np.cross(village_faces[:,1].astype(float)-village_faces[:,0],village_faces[:,2].astype(float)-village_faces[:,0])
        normal/=np.linalg.norm(normal,axis=1,keepdims=True)
        add(deck_name(world,identity),M.Mesh(positions=v,normals=np.repeat(normal,3,axis=0),
            uvs=v[:,[0,2]]*.4,indices=np.arange(len(v)),material='fishing_timber'))
        add('Manymouth_Village_Fascia_'+identity,boardwalk_fascia(village_faces,'fishing_timber'))
        positions=[]
        for branch in village_paths:
            for a,b in zip(branch,branch[1:]):
                axis=b-a;length=np.linalg.norm(axis)
                if length<2:continue
                side=np.array([-axis[1],axis[0]])/length
                for distance in np.arange(1.5,length-.5,4.):
                    for sign in (-1,1):positions.append(a+axis*(distance/length)+side*1.08*sign)
        fitted=[];piles=[]
        if positions:
            positions=np.unique(np.round(positions,4),axis=0)
            footprint=positions[:,None,:]+np.array([[x,z] for x in (-.085,0,.085) for z in (-.085,0,.085)])[None,:,:]
            floor=floor_samples(village_faces,footprint[:,:,0],footprint[:,:,1])
            ground=world.height_at(footprint[:,:,0],footprint[:,:,1])
            for p,heights,beds in zip(positions,floor,ground):
                if not np.isfinite(heights).all():continue
                top=float(heights.min()-.08);bed=float(beds.min()-.05)
                if top-bed<.35:continue
                piles.append(M.box((.17,top-bed,.17),center=(p[0],(top+bed)*.5,p[1]),material='fishing_posts'))
                fitted.append({'positionXZ':p.tolist(),'bottom':bed,'top':top,'floorGap':float(heights.min()-top)})
        if piles:add('Manymouth_Village_Piles_'+identity,M.merge(piles,material='fishing_posts'))
        village_report['fittedPiles']=fitted;village_reports.append(village_report)
    destination.parent.mkdir(exist_ok=True,parents=True);builder.write_glb(str(destination))
    world.manymouth_access={'floorLevel':level,'halfWidth':HALF_WIDTH,'newTriangles':len(faces),'paths':[p.tolist() for p in paths],
        'marketEntrance':{'path':market_path.tolist(),'floorLevel':market_level,'newTriangles':len(market)},
        'paddyHamlet':dict(paddy_report,floorLevel=paddy_level,halfWidth=HALF_WIDTH,newTriangles=len(paddy),
            paths=[p.tolist() for p in paddy_paths],postGroundContacts=post_contacts,
            policy='Eight actual porches join the retained round landing through one narrow street between the houses.'),
        'villageStreets':village_reports,
        'policy':'Visible timber links, existing floors subtracted, unchanged tidal bank and rigid houses.'}
    return parts
