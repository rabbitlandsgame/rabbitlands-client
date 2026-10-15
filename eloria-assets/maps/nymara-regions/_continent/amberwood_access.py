"""Visible Motherroot hatch and a coherent approach to the retained canopy.

The library is immutable. One crossing in the retained timber walk is raised
to meet its intersecting walk, retaining both end levels and all XZ/UV data.
An authored root-side entrance replaces the old enclosed ground mouth.
"""
from __future__ import annotations
import copy
from pathlib import Path
import numpy as np
import scene_io as S
import landscape as L
from bridge_export import G,M
from ferry_export import ribbon
from mirror_access_geometry import ramp_mesh,foundation_faces

REGION='amberwood'
HATCH='Motherroot_RootHatch'
# The market stair descends from the canopy platform deck to whatever ground
# the final composition leaves at its foot: the shortest straight run that
# keeps a walkable grade, between these lengths, along the authored line.
MARKET_STAIR_MINIMUM_METRES=17.
MARKET_STAIR_MAXIMUM_METRES=45.   # the line runs down the natural hillside: 12 m below the deck at the landing, 19 m at 37 m out
MARKET_STAIR_GRADE=.58
MARKET_STAIR_LEVEL_METRES=4.
MARKET_STAIR_CLEARANCE_METRES=2.6
# The root ramp climbs the Great Tree's west root flank from the village yard
# onto the root plateau: a rigid footing nine metres above the yard whose
# flank blends at grade 1.1, which no corridor can grade. Its timber deck is
# the .45 lower envelope over the final ground (mirror_access_geometry.
# ramp_mesh), so the run starts on the flat yard west of x 486 to land at the
# grade. The yard itself is a served hollow: the canopy walkway's shadow on
# its west, the market decks on its north and the cliff on its south fence it
# in the served grid (one height per tile), and the fifteenth reached it only
# where a road happened to lift the ground at the walkway's foot into the
# 2.8 m code step. So the Motherroot Voice stands at the Motherroot mouth
# (MOTHERROOT_VOICE_POST), which the door road serves; the ramp joins the
# plateau to the yard for the day the yard gets its own approach.
ROOT_RAMP_FOOT=np.array([484.,472.])
ROOT_RAMP_HEAD=np.array([505.,472.])
ROOT_RAMP_HALF_WIDTH=1.8
ROOT_RAMP_CLEARANCE_METRES=2.6   # beyond the deck edge, for the reserve and the loose props
ROOT_RAMP_POST_SPACING_METRES=3
# The Motherroot Voice's post: the yard in front of the root hatch, three
# metres from the door's threshold, on the ground the door road serves.
MOTHERROOT_VOICE='Motherroot Voice Sillow'
MOTHERROOT_VOICE_POST=np.array([508.5,515.5])


def market_stair_line(world):
    """(landing, unit direction from the foot up to the landing) of the authored market stair line."""
    offset=np.asarray(world.regions[REGION]['center'])-[510.,540.]
    landing=np.array([510.,541.5])+offset;foot=np.array([503.,557.])+offset
    direction=(landing-foot)/np.linalg.norm(landing-foot)
    return landing,direction


def market_stair_run(height_at,landing,direction,deck):
    """(length, start, ground) of the shortest stair run that keeps MARKET_STAIR_GRADE on the given ground."""
    for length in np.arange(MARKET_STAIR_MINIMUM_METRES,MARKET_STAIR_MAXIMUM_METRES+1e-9,2.):
        start=landing-direction*length;ground=float(height_at(*start))+.025
        if abs(deck-ground)/(length-MARKET_STAIR_LEVEL_METRES)<=MARKET_STAIR_GRADE:
            return float(length),start,ground
    raise ValueError(f'Market stair needs a longer actual approach: {abs(deck-ground):.2f} m of rise within {MARKET_STAIR_MAXIMUM_METRES:.0f} m')


def root_ramp_line(world):
    """(foot, head) of the root ramp in continent metres: the authored line, placed with the region."""
    offset=np.asarray(world.regions[REGION]['center'])-[510.,540.]
    return ROOT_RAMP_FOOT+offset,ROOT_RAMP_HEAD+offset


def motherroot_voice_post(world):
    """The Motherroot Voice's post in continent metres (x, ground height, z), placed with the region."""
    offset=np.asarray(world.regions[REGION]['center'])-[510.,540.]
    x,z=MOTHERROOT_VOICE_POST+offset
    return np.array([x,float(world.height_at(x,z)),z])


def root_ramp_reserve(foot,head,half_width=ROOT_RAMP_HALF_WIDTH,clearance=ROOT_RAMP_CLEARANCE_METRES):
    """(low, high) XZ box no road alignment or grove enters: the deck and its clearance."""
    return np.minimum(foot,head)-half_width-clearance,np.maximum(foot,head)+half_width+clearance


def clear_strip_props(content,origin,direction,near,far,clearance):
    """Move the loose props off a strip, sideways to the clearance, as the stall row was moved.

    The strip runs from ``near`` to ``far`` metres from ``origin`` along the unit
    ``direction``; assemblies and everything but props stay. Returns the moves.
    """
    perp=np.array([-direction[1],direction[0]]);cleared=[]
    for obj in content.objects:
        if obj['region']!=REGION or obj.get('assembly') or obj.get('kind')!='prop':continue
        centre=((np.asarray(obj['low'])+np.asarray(obj['high']))*.5)[[0,2]];rel=centre-origin
        along=float(rel@direction);across=float(rel@perp)
        half=float(np.hypot(obj['high'][0]-obj['low'][0],obj['high'][2]-obj['low'][2])*.5)
        if not (near<along<far and abs(across)-half<clearance):continue
        move=perp*(1. if across>=0 else -1.)*(clearance+half-abs(across))
        delta=np.array([move[0],0.,move[1]]);obj['shift']+=delta;obj['low']+=delta;obj['high']+=delta
        content.mapping[(REGION,obj['node'])]=obj['shift'];content.bounds_by_name[(REGION,obj['node'])]=(obj['low'],obj['high'])
        cleared.append({'node':obj['node'],'displacement':[round(float(v),2) for v in delta]})
    return cleared


def root_ramp_rails(world,deck,rows):
    """Posts every third metre on both deck edges, from below the ground up to a handrail band along the edge."""
    grid=deck.positions.reshape(rows,-1,3);posts=[];rails=[]
    for edge in (grid[:,0],grid[:,-1]):
        for p in edge[::ROOT_RAMP_POST_SPACING_METRES]:
            ground=float(world.height_at(p[0],p[2]));top=p[1]+1.;height=top-(ground-.3)
            posts.append(M.box((.18,height,.18),center=(p[0],top-height*.5,p[2]),material='amber_access_dark'))
        n=len(edge);vertices=np.concatenate([edge+[0.,.86,0.],edge+[0.,.98,0.]])
        i=np.arange(n-1);indices=np.c_[i,i+1,n+i,i+1,n+i+1,n+i].ravel()
        rail=M.Mesh(positions=vertices,normals=np.zeros_like(vertices),uvs=vertices[:,[0,1]],indices=indices,material='amber_access_timber')
        rail.recompute_normals(180);rails.append(rail)
    return M.merge(posts,material='amber_access_dark'),M.merge(rails,material='amber_access_timber')


def prepare_camp_source(document,body,metadata,folder):
    """Author the small tent court before its common assembly is placed.

    The source survey already has a sheltered, nearly level camping shoulder.
    Spread the compressed tents onto it and retain each root's ground offset.
    Library files remain immutable; the cloned source enters normal bounds,
    common-footing and collision generation with its actual revised geometry.
    """
    from scipy.interpolate import RegularGridInterpolator
    samples=np.load(Path(folder)/'foundation-samples.npz')
    ground=RegularGridInterpolator((samples['z'],samples['x']),samples['height'])
    reference=np.array([161.3758,-224.9205])
    desired={**{f'Prop_Tent_ridge_camp_{i:02d}':p for i,p in enumerate(
        ((-6,-7),(-8,0),(-3,6),(4,4),(0,-6)),1)},
        **{f'Brazier_ridge_camp_{i:02d}':p for i,p in enumerate(((0,-1),(3,1),(-4,3)),1)}}
    result=copy.deepcopy(document);metadata=copy.deepcopy(metadata)
    by_name={n.get('name'):i for i,n in enumerate(result['nodes'])}
    placements={p['node']:p for p in metadata['placements']};matrices,_=S.GR.hierarchy(result)
    report=[]
    for name,offset in desired.items():
        if name not in by_name or name not in placements:raise ValueError('Missing authored camp member '+name)
        index=by_name[name];low,high=S.subtree_bounds(result,body,index,matrices)
        old=(low+high)[[0,2]]*.5;target=reference+offset
        y=float(ground([[target[1],target[0]]])[0]-ground([[old[1],old[0]]])[0])
        delta=np.array([target[0]-old[0],y,target[1]-old[1]])
        node=result['nodes'][index]
        if 'matrix' in node:
            node['matrix'][12:15]=(np.asarray(node['matrix'][12:15])+delta).tolist()
        else:node['translation']=(np.asarray(node.get('translation',[0,0,0]))+delta).tolist()
        placement=placements[name]
        placement['position']=(np.asarray(placement.get('position',[0,0,0]))+delta).tolist()
        placement['continentLayoutOffset']=delta.tolist()
        report.append({'node':name,'sourceDelta':delta.tolist(),'sourceCenter':target.tolist()})
    metadata['continentCampLayout']=report
    return result,metadata


def walk_faces(document,body,root):
    matrices,parents=S.GR.hierarchy(document);faces=[]
    for index in S.descendants(document,[root]):
        node=document['nodes'][index]
        if 'mesh' not in node:continue
        current=index;walk=False
        while True:
            walk|=document['nodes'][current].get('name','').startswith('Walk_')
            if current not in parents:break
            current=parents[current]
        if not walk:continue
        matrix=matrices[index]
        for p in document['meshes'][node['mesh']]['primitives']:
            v=S.GR.accessor(document,body,p['attributes']['POSITION']).astype(float)
            i=S.GR.accessor(document,body,p['indices']).ravel().astype(int)
            tri=v[i].reshape(-1,3,3)@matrix[:3,:3].T+matrix[:3,3]
            normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            faces.extend(tri[abs(normal[:,1])>1e-6])
    return np.asarray(faces)


def top_at(triangles,x,z):
    values=[]
    for tri in triangles:
        a,b=tri[1,[0,2]]-tri[0,[0,2]],tri[2,[0,2]]-tri[0,[0,2]]
        q=np.array([x,z])-tri[0,[0,2]];det=a[0]*b[1]-a[1]*b[0]
        if abs(det)<1e-10:continue
        u=(q[0]*b[1]-q[1]*b[0])/det;v=(a[0]*q[1]-a[1]*q[0])/det
        if u>=-1e-7 and v>=-1e-7 and u+v<=1+1e-7:
            values.append(float(tri[0,1]+u*(tri[1,1]-tri[0,1])+v*(tri[2,1]-tri[0,1])))
    return max(values) if values else None


def plane_near(triangles,point,radius=6.):
    v=triangles.reshape(-1,3);v=v[np.linalg.norm(v[:,[0,2]]-point,axis=1)<radius]
    if len(v)<6:raise ValueError('Canopy crossing has no sampled floor')
    xz=np.round(v[:,[0,2]],5);unique,indices=np.unique(xz,axis=0,return_inverse=True)
    h=np.full(len(unique),-np.inf);np.maximum.at(h,indices,v[:,1])
    return np.linalg.lstsq(np.c_[unique,np.ones(len(unique))],h,rcond=None)[0]


def open_platform_rail(document,body,root,center,deck):
    """Remove one visible railing bay where the market stair meets the deck.

    Weld face vertices only to identify whole rails/posts. Floor faces and
    supports below the standing level remain byte-for-byte unchanged.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    result=copy.deepcopy(document);data=bytearray(body);matrices,_=S.GR.hierarchy(result)
    removed=0;components=0
    for index in S.descendants(result,[root]):
        node=result['nodes'][index]
        if 'mesh' not in node or node.get('name','').startswith('Walk_'):continue
        mesh=copy.deepcopy(result['meshes'][node['mesh']]);changed=False
        for p in mesh['primitives']:
            v=S.GR.accessor(result,data,p['attributes']['POSITION']).astype(float)
            indices=S.GR.accessor(result,data,p['indices']).ravel().astype(int).reshape(-1,3)
            unique,remap=np.unique(np.round(v,5),axis=0,return_inverse=True);faces=remap[indices]
            edges=np.concatenate([faces[:,[a,b]] for a,b in ((0,1),(1,2),(2,0))])
            graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(unique),len(unique))).tocsr()
            count,labels=connected_components(graph,directed=False);labels=labels[remap]
            source=v@matrices[index][:3,:3].T+matrices[index][:3,3];cut=[]
            for label in range(count):
                points=source[labels==label];low,high=points.min(axis=0),points.max(axis=0)
                mid=(low+high)*.5
                if low[1]>=deck+.1 and np.linalg.norm(mid[[0,2]]-center)<1.8 and np.max((high-low)[[0,2]])<3.5:
                    cut.append(label)
            remove=np.isin(labels[indices[:,0]],cut)
            if not remove.any():continue
            values=np.ascontiguousarray(indices[~remove].ravel(),dtype='<u4');data.extend(b'\0'*((-len(data))%4))
            view=len(result['bufferViews']);result['bufferViews'].append({'buffer':0,'byteOffset':len(data),'byteLength':values.nbytes});data.extend(values.tobytes())
            accessor=len(result['accessors']);result['accessors'].append({'bufferView':view,'componentType':5125,'count':len(values),'type':'SCALAR'})
            p['indices']=accessor;removed+=int(remove.sum());components+=len(cut);changed=True
        if changed:node['mesh']=len(result['meshes']);result['meshes'].append(mesh)
    if removed==0 or components>12:raise ValueError('Market stair has no bounded railing bay')
    result['buffers'][0]['byteLength']=len(data)
    return result,bytes(data),{'removedRailTriangles':removed,'removedRailComponents':components}


def join_canopy_crossing(document,body,upper_root,lower_root,center):
    """Raise the lower walk locally; a broad taper leaves both platforms fixed."""
    upper=walk_faces(document,body,upper_root);lower=walk_faces(document,body,lower_root)
    upper_plane=plane_near(upper,center);lower_plane=plane_near(lower,center)
    difference=upper_plane-lower_plane
    if not 0<float(np.r_[center,1]@difference)<10:raise ValueError('Unexpected canopy crossing separation')
    vertices=lower.reshape(-1,3);xz=vertices[:,[0,2]]
    _,_,basis=np.linalg.svd(xz-xz.mean(axis=0),full_matrices=False);axis=basis[0]
    span=27.
    def displacement(points):
        along=(points[:,[0,2]]-center)@axis
        t=np.clip((abs(along)-3.)/(span-3.),0,1)
        weight=1-t*t*(3-2*t)
        return (np.c_[points[:,[0,2]],np.ones(len(points))]@difference)*weight
    result=copy.deepcopy(document);data=bytearray(body);matrices,_=S.GR.hierarchy(result)
    def append(values):
        a=np.ascontiguousarray(values,dtype='<f4');data.extend(b'\0'*((-len(data))%4))
        view=len(result['bufferViews']);result['bufferViews'].append({'buffer':0,'byteOffset':len(data),'byteLength':a.nbytes});data.extend(a.tobytes())
        index=len(result['accessors']);result['accessors'].append({'bufferView':view,'componentType':5126,'count':len(a),'type':'VEC3','min':a.min(axis=0).tolist(),'max':a.max(axis=0).tolist()});return index
    for index in S.descendants(result,[lower_root]):
        node=result['nodes'][index]
        if 'mesh' not in node:continue
        mesh=copy.deepcopy(result['meshes'][node['mesh']]);matrix=matrices[index];inverse=np.linalg.inv(matrix)
        for p in mesh['primitives']:
            attributes=p['attributes'];v=S.GR.accessor(result,data,attributes['POSITION']).astype(float)
            source=v@matrix[:3,:3].T+matrix[:3,3];delta=displacement(source);updated=source.copy();updated[:,1]+=delta
            attributes['POSITION']=append(updated@inverse[:3,:3].T+inverse[:3,3])
            if 'NORMAL' in attributes:
                normal=S.GR.accessor(result,data,attributes['NORMAL'])@np.linalg.inv(matrix[:3,:3])
                dx=source.copy();dx[:,0]+=.001;dz=source.copy();dz[:,2]+=.001
                gradient_x=(displacement(dx)-delta)/.001;gradient_z=(displacement(dz)-delta)/.001
                normal[:,0]-=gradient_x*normal[:,1];normal[:,2]-=gradient_z*normal[:,1]
                normal=normal@matrix[:3,:3];normal/=np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1e-12)
                attributes['NORMAL']=append(normal)
        node['mesh']=len(result['meshes']);result['meshes'].append(mesh)
    result['buffers'][0]['byteLength']=len(data)
    return result,bytes(data),{'sourceCenter':np.asarray(center).tolist(),'heightSeparationMetres':float(np.r_[center,1]@difference),'taperMetres':span}


def prepare_amberwood_access(world,content):
    if REGION not in world.ids:return {}
    offset=np.asarray(world.regions[REGION]['center'])-[510.,540.]
    # Explicit source-to-authored entrance mapping, shared by doors and return.
    entry=next(p for p in content.templates[REGION]['portals'] if p['id']=='motherroot-mouth')
    old=np.asarray(entry['position'],float);target=np.array([512.+offset[0],0.,513.+offset[1]])
    target[1]=float(world.height_at(target[0],target[2]))
    entry['node']=HATCH;entry.pop('landmark',None)
    content.mapping[(REGION,HATCH)]=target-old
    if not hasattr(content,'authored_server_points'):content.authored_server_points={}
    content.authored_server_points[(REGION,(221,320))]=target.copy()
    content.authored_server_points[(REGION,(221,318))]=target+np.array([-1.,0.,1.])
    # The Motherroot Voice keeps the mouth (npcs.txt: Motherroot Voice Sillow).
    if not hasattr(content,'authored_actor_points'):content.authored_actor_points={}
    content.authored_actor_points[(REGION,MOTHERROOT_VOICE)]=motherroot_voice_post(world)
    # The charcoal discovery is a physical hatch in the kiln side yard, rather
    # than the compressed legacy marker overlapping the adjacent lodge.
    cache=content.placement_by_name[(REGION,'Secret_amber_charcoal_cache')]
    delta=np.array([7.,0.,0.]);cache['shift']+=delta;cache['low']+=delta;cache['high']+=delta
    content.mapping[(REGION,cache['node'])]=cache['shift'];content.bounds_by_name[(REGION,cache['node'])]=(cache['low'],cache['high'])
    # Make space for the sloped market stair beside the existing stall row, and
    # take stall 3 off the line the Motherroot mouth door road takes north past
    # the platform's east side: 1.5 m east, with the firewood at its corner. The
    # road clipped the stall's west edge because the platform's own solid covers
    # the stall's cells and the router cannot see it there; moved any further
    # north the stall's widened box leaves the platform's, the router sees it,
    # and the door road loops 550 m round the Great Tree (the sixteenth's run 4).
    for name,delta in (('Prop_MarketStall_6',np.array([15.,0.,4.])),('Prop_MarketStall_3',np.array([1.5,0.,0.])),('Prop_Firewood_162',np.array([0.,0.,.6]))):
        stall=content.placement_by_name[(REGION,name)]
        stall['shift']+=delta;stall['low']+=delta;stall['high']+=delta
        content.mapping[(REGION,stall['node'])]=stall['shift'];content.bounds_by_name[(REGION,stall['node'])]=(stall['low'],stall['high'])
    # The stair's length follows the final ground (build_amberwood_access).
    # Reserve its longest strip now, so no road alignment or grove crosses
    # it, and move loose props off it as the stall row was moved.
    landing,direction=market_stair_line(world);perp=np.array([-direction[1],direction[0]])
    far=landing-direction*MARKET_STAIR_MAXIMUM_METRES
    reserve_low=np.minimum(landing,far)-MARKET_STAIR_CLEARANCE_METRES;reserve_high=np.maximum(landing,far)+MARKET_STAIR_CLEARANCE_METRES
    world.structure_obstacle([reserve_low[0],0.,reserve_low[1]],[reserve_high[0],0.,reserve_high[1]])
    cleared=clear_strip_props(content,landing,-direction,6.,MARKET_STAIR_MAXIMUM_METRES,MARKET_STAIR_CLEARANCE_METRES)
    # The root ramp's deck follows the final ground too (build_amberwood_access):
    # reserve its strip and clear it the same way.
    foot,head=root_ramp_line(world);ramp_low,ramp_high=root_ramp_reserve(foot,head)
    world.structure_obstacle([ramp_low[0],0.,ramp_low[1]],[ramp_high[0],0.,ramp_high[1]])
    ramp_run=head-foot;ramp_length=float(np.linalg.norm(ramp_run))
    ramp_cleared=clear_strip_props(content,foot,ramp_run/ramp_length,0.,ramp_length,ROOT_RAMP_HALF_WIDTH+ROOT_RAMP_CLEARANCE_METRES)
    doc,body=content.documents[REGION]
    upper=content.placement_by_name[(REGION,'Landmark_CanopyWalkway_0')]
    lower=content.placement_by_name[(REGION,'Landmark_CanopyWalkway_2')]
    center=np.array([520.,505.])-upper['shift'][[0,2]]
    doc,body,report=join_canopy_crossing(doc,body,upper['index'],lower['index'],center)
    platform=content.placement_by_name[(REGION,'Landmark_CanopyPlatform_0')]
    floor=walk_faces(doc,body,platform['index'])
    center=np.array([509.5,542.])+offset-platform['shift'][[0,2]]
    doc,body,opening=open_platform_rail(doc,body,platform['index'],center,float(floor[:,:,1].max()))
    content.documents[REGION]=(doc,body)
    matrices,_=S.GR.hierarchy(doc);low,high=S.subtree_bounds(doc,body,lower['index'],matrices)
    lower['low'][...]=low+lower['shift'];lower['high'][...]=high+lower['shift']
    content.bounds_by_name[(REGION,lower['node'])]=(lower['low'],lower['high'])
    world.amberwood_access={'hatch':target.tolist(),'canopyJunction':report,'marketRailOpening':opening,'marketStallDisplacement':[15,0,4],'marketStall3Displacement':[1.5,0,0],'charcoalHatchDisplacement':[7,0,0],
        'marketStairReserve':[reserve_low.tolist(),reserve_high.tolist()],'marketStairClearance':cleared,
        'rootRampReserve':[ramp_low.tolist(),ramp_high.tolist()],'rootRampClearance':ramp_cleared,
        'motherrootVoice':{'identity':MOTHERROOT_VOICE,'post':content.authored_actor_points[(REGION,MOTHERROOT_VOICE)].tolist()}}
    return world.amberwood_access


def build_amberwood_access(world,content,path):
    if REGION not in world.ids:return []
    if REGION in getattr(world,'authoring_snapshots',{}):
        # All access Walk roots and their visible supports are captured by the
        # saved scene. An empty valid auxiliary GLB keeps the shared exporter
        # shape without resurrecting a scene child the author later deletes.
        destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True)
        G.GltfBuilder('Saved Amberwood access authority').write_glb(str(destination))
        return []
    builder=G.GltfBuilder('Eloria Amberwood inhabited access')
    for name,color in [('timber',(.40,.25,.12)),('dark',(.20,.13,.075)),('iron',(.17,.18,.16))]:
        builder.add_material(G.Material('amber_access_'+name,base_color=tuple(np.asarray(color)**2.2)+(1.,),roughness=.9,double_sided=True))
    parts=[];hatch_parent=None;hatch_bounds=[]
    def add(name,mesh,solid=False):
        # Every walk this module builds is a designed deck the plan names (landscape.designed_deck_entry).
        if name.startswith('Walk_'):L.require_designed_deck(getattr(world,'plan',None) or {},name,'amberwood_access')
        parent=hatch_parent if HATCH in name else None
        builder.add_mesh(name,mesh,with_tangents=False);root=builder.add_node(G.Node(name,mesh=name),parent=parent)
        if parent is not None:
            hatch_bounds.append(np.asarray(mesh.bounds()));return
        parts.append({'region':REGION,'node':name,'roots':[root],'bounds':mesh.bounds(),'segment':[],'collides':solid})
    shift=np.asarray(content.assembly_records['amberwood.canopy-village']['translation'])
    offset=np.asarray(world.regions[REGION]['center'])-[510.,540.]
    doc,body=content.documents[REGION];platform=content.placement_by_name[(REGION,'Landmark_CanopyPlatform_0')]
    floor=walk_faces(doc,body,platform['index'])+shift
    # Plank slots are physical gaps; use the highest surrounding deck samples.
    landing=np.array([510.,541.5])+offset
    near=floor.reshape(-1,3);near=near[np.linalg.norm(near[:,[0,2]]-landing,axis=1)<3]
    if not len(near):raise ValueError('Market stair has no retained platform landing')
    deck=float(np.max(near[:,1]));landing,direction=market_stair_line(world);side=np.array([-direction[1],direction[0]])
    length,start,h0=market_stair_run(world.height_at,landing,direction,deck)
    delta=landing-start;level_length=MARKET_STAIR_LEVEL_METRES
    centres=np.array([start,landing-direction*level_length,landing]);heights=np.array([h0,deck,deck])
    add('Walk_Amber_MarketCanopyStair',ribbon(centres,heights,side,1.65,'amber_access_timber'))
    supports=[]
    for t in np.linspace(0,1,5):
        p=start+delta*t;y=h0+(deck-h0)*min(1,t*length/(length-level_length))
        for sign in (-1,1):
            q=p+side*(1.9*sign);ground=float(world.height_at(*q));height=max(.12,y-ground+.85)
            supports.append(M.box((.22,height,.22),center=(q[0],y+.85-height*.5,q[1]),material='amber_access_dark'))
    add('Amber_MarketCanopyStair_Posts',M.merge(supports,material='amber_access_dark'),True)
    # The root ramp: its deck is a Walk_ floor the collision export serves over
    # the flank's grade; the skirt, posts and rails are solids beside it.
    foot,head=root_ramp_line(world);rows=int(np.ceil(np.linalg.norm(head-foot)))+1
    deck_mesh,ramp=ramp_mesh(world,content,foot,head,'amber_access_timber',half_width=ROOT_RAMP_HALF_WIDTH,region=REGION)
    add('Walk_Amber_RootRamp',deck_mesh)
    add('Amber_RootRamp_Skirt',foundation_faces(world,deck_mesh,'amber_access_dark'),True)
    posts,rails=root_ramp_rails(world,deck_mesh,rows)
    add('Amber_RootRamp_Posts',posts,True);add('Amber_RootRamp_Rails',rails,True)
    centre=deck_mesh.positions.reshape(rows,-1,3)[:,4]
    hatch_parent=builder.add_node(G.Node(HATCH))
    hatch=np.asarray(world.amberwood_access['hatch'])[[0,2]];ground=float(world.height_at(*hatch))
    # An east-facing root-side door, with a broad short timber threshold.
    centres=np.array([hatch+[-3,0],hatch+[1.4,0]])
    heights=np.array([float(world.height_at(*centres[0]))+.025,ground+.28])
    add('Walk_'+HATCH,ribbon(centres,heights,np.array([0.,1.]),1.65,'amber_access_timber'))
    frame=[]
    for z in (-1.45,1.45):frame.append(M.box((.35,2.8,.32),center=(hatch[0]+1.6,ground+1.5,hatch[1]+z),material='amber_access_timber'))
    frame.append(M.box((.38,.4,3.25),center=(hatch[0]+1.6,ground+2.9,hatch[1]),material='amber_access_timber'))
    add(HATCH+'_Frame',M.merge(frame,material='amber_access_timber'),True)
    add(HATCH+'_Door',M.box((.18,2.45,2.5),center=(hatch[0]+1.78,ground+1.5,hatch[1]),material='amber_access_dark'),True)
    add(HATCH+'_Latch',M.box((.27,.16,.45),center=(hatch[0]+1.56,ground+1.35,hatch[1]-.7),material='amber_access_iron'))
    parts.append({'region':REGION,'node':HATCH,'roots':[hatch_parent],
                  'bounds':np.array([np.asarray(hatch_bounds)[:,0].min(axis=0),np.asarray(hatch_bounds)[:,1].max(axis=0)]),'segment':[],'collides':True})
    Path(path).parent.mkdir(parents=True,exist_ok=True);builder.write_glb(str(path))
    world.amberwood_access['marketRamp']={'start':[float(start[0]),h0,float(start[1])],'landing':[float(landing[0]),deck,float(landing[1])],'levelLandingMetres':level_length,
        'lengthMetres':float(length),'grade':float(abs(deck-h0)/(length-level_length))}
    world.amberwood_access['rootRamp']={**ramp,'foot':centre[0].tolist(),'head':centre[-1].tolist(),'halfWidthMetres':ROOT_RAMP_HALF_WIDTH,
        'lengthMetres':float(np.linalg.norm(head-foot)),'riseMetres':float(centre[-1,1]-centre[0,1])}
    return parts


def refresh_amberwood_access_heights(world,content):
    """Finalize portal/return metadata from the same terrain as the visible door."""
    if not hasattr(world,'amberwood_access'):return
    point=world.amberwood_access['hatch'];point[1]=float(world.height_at(point[0],point[2]))
    entry=next(p for p in content.templates[REGION]['portals'] if p['id']=='motherroot-mouth')
    content.mapping[(REGION,HATCH)][1]=point[1]-entry['position'][1]
    for tile in ((221,320),(221,318)):
        p=content.authored_server_points[(REGION,tile)];p[1]=float(world.height_at(p[0],p[2]))
    post=content.authored_actor_points[(REGION,MOTHERROOT_VOICE)];post[1]=float(world.height_at(post[0],post[2]))
    world.amberwood_access['motherrootVoice']['post']=post.tolist()
