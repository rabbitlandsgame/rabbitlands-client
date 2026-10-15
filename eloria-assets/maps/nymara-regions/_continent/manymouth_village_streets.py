"""Local timber circulation for the retained delta settlements.

Actual porch/landing floors pin a common bounded-grade street surface. Each
hamlet keeps its own routes; only its nearest public landing or road supplies
an approach. No terrain, source building, or authored semantic point moves.
"""
from __future__ import annotations
import heapq
from types import SimpleNamespace
import numpy as np
from scipy.spatial import ConvexHull,QhullError
import scene_io as S
import manymouth_support as D
import collision_export as C
import bridge_export as B
import landscape as L

REGION='manymouth_delta'
WIDTH=1.25
SOURCE_PLANS={
    'town':(['Landing_stilt_town','town_porch_01'],[f'town_porch_{i:02d}' for i in (0,2,3,4,5,6,7,8)]),
    'floating_market':([] ,['Landing_floating_market']),
    'sea_landing':([],['Landing_sea_landing',*[f'sea_landing_porch_{i:02d}' for i in range(5)]]),
    'east_hamlet':(['Landing_east_hamlet','Landing_lore_court','Landing_shore_lore_court',*[f'east_hamlet_porch_{i:02d}' for i in (0,1,5,6,7)]],
                   [f'east_hamlet_porch_{i:02d}' for i in (2,3,4,8)]),
    'south_hamlet':(['Landing_south_hamlet','south_hamlet_porch_08'],
                    [f'south_hamlet_porch_{i:02d}' for i in range(8)]),
    'boat_yard':(['Landing_boat_yard',*[f'boat_yard_porch_{i:02d}' for i in (0,1,3)]],
                 [f'boat_yard_porch_{i:02d}' for i in (2,4,5)]),
    'far_bar':(['Landing_far_bar',*[f'far_bar_porch_{i:02d}' for i in (0,1,3)]],['far_bar_porch_02']),
    'deep_grove':(['Landing_deep_grove','deep_grove_porch_00','deep_grove_porch_02'],[f'deep_grove_porch_{i:02d}' for i in (1,3,4)]),
}


def structural_parts(content):
    """Retained solid mesh parts keep open gaps between buildings and piers."""
    if hasattr(content,'_village_structural_parts'):return content._village_structural_parts
    document,body=content.documents[REGION];result=[];matrices,_=S.GR.hierarchy(document);meshes={}
    for obj in content.objects:
        if obj['region']!=REGION or not obj.get('collides'):continue
        for index in S.descendants(document,[obj['index']]):
            node=document['nodes'][index]
            if 'mesh' not in node or node.get('name','').startswith('Walk_'):continue
            mesh_index=node['mesh']
            if mesh_index not in meshes:
                parts=[]
                for primitive in document['meshes'][mesh_index]['primitives']:
                    if primitive.get('mode',4)!=4:continue
                    vertices=S.GR.accessor(document,body,primitive['attributes']['POSITION']).astype(float)
                    order=S.GR.accessor(document,body,primitive['indices']).reshape(-1).astype(int) if 'indices' in primitive else np.arange(len(vertices))
                    parts.append(vertices[order].reshape(-1,3,3))
                meshes[mesh_index]=np.concatenate(parts) if parts else np.empty((0,3,3))
            matrix=matrices[index];triangles=meshes[mesh_index]@matrix[:3,:3].T+matrix[:3,3]+obj['shift']
            if len(triangles):result.append((triangles,triangles.min(axis=(0,1)),triangles.max(axis=(0,1))))
    content._village_structural_parts=result
    return result


def actor_band_polygon(triangles,low,high):
    p=triangles.reshape(-1,3);points=[p[(p[:,1]>=low)&(p[:,1]<=high)]]
    for a,b in ((triangles[:,0],triangles[:,1]),(triangles[:,1],triangles[:,2]),(triangles[:,2],triangles[:,0])):
        for level in (low,high):
            cross=(np.minimum(a[:,1],b[:,1])<level)&(np.maximum(a[:,1],b[:,1])>level)
            if cross.any():points.append(a[cross]+(b[cross]-a[cross])*((level-a[cross,1])/(b[cross,1]-a[cross,1]))[:,None])
    points=np.concatenate(points)
    if len(points)<3:return None
    try:return points[ConvexHull(points[:,[0,2]]).vertices][:,[0,2]]
    except QhullError:return None


def floor_samples(faces,x,z):
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float));shape=x.shape
    xx,zz=x.ravel(),z.ravel();top=np.full(len(xx),-np.inf)
    for face in faces:
        normal=np.cross(face[1]-face[0],face[2]-face[0])
        if normal[1]<=1e-8:continue
        lo=face[:,[0,2]].min(axis=0);hi=face[:,[0,2]].max(axis=0)
        at=np.flatnonzero((xx>=lo[0]-1e-7)&(xx<=hi[0]+1e-7)&(zz>=lo[1]-1e-7)&(zz<=hi[1]+1e-7))
        if not len(at):continue
        a,b,c=face;u=b[[0,2]]-a[[0,2]];v=c[[0,2]]-a[[0,2]]
        dx,dz=xx[at]-a[0],zz[at]-a[2];det=u[0]*v[1]-u[1]*v[0]
        s=(dx*v[1]-dz*v[0])/det;t=(u[0]*dz-u[1]*dx)/det
        keep=(s>=-1e-7)&(t>=-1e-7)&(s+t<=1+1e-7)
        yy=a[1]+s*(b[1]-a[1])+t*(c[1]-a[1]);at=at[keep]
        top[at]=np.maximum(top[at],yy[keep])
    return top.reshape(shape)


def encoded_planar_points(points):
    """Use one binary grid on both axes so shared cell diagonals stay joined.

    Independent float32 axis rounding otherwise moves the two ends of a
    clipped x+z=integer edge to opposite sides of that same line. At continent
    scale the common grid is below a millimetre, and is exactly representable
    both globally and after territory-local translation.
    """
    points=np.asarray(points,float)
    spacing=float(np.max(np.abs(np.spacing(points.astype(np.float32))),initial=0))
    if not spacing:return points.astype(np.float32).astype(float)
    return (np.rint(points/spacing)*spacing).astype(np.float32).astype(float)


def station(content,name,matrices):
    obj=content.placement_by_name.get((REGION,name))
    if obj is None:raise ValueError(name+': retained village contact is missing')
    faces=D._triangles(content,obj,matrices=matrices)
    if not len(faces):raise ValueError(name+': retained contact has no actual Walk floor')
    points=faces.reshape(-1,3);xz=(points[:,[0,2]].min(axis=0)+points[:,[0,2]].max(axis=0))*.5
    y=float(floor_samples(faces,*xz))
    if not np.isfinite(y):raise ValueError(name+': floor centre is not an actual standing surface')
    return {'name':name,'xz':xz,'y':y,'faces':faces}


PUBLIC_ROAD_REACH_METRES=36.
# R1: roads cross the delta's channels only on bridge sites 100 m apart, so a landing the old roads passed within the
# usual reach (the floating market, 29 m from the Crownwater ferry road in O5) can stand farther from every road now.
PUBLIC_ROAD_FALLBACK_REACH_METRES=64.


PUBLIC_ROAD_BANK_CHOICES=4          # banks per target a group without public contacts may try, best first
PUBLIC_ROAD_BANK_SPACING_METRES=4.  # ...each this far from the better ones


def public_road_station(world,content,target):
    return public_road_stations(world,content,target,count=1)[0]


def public_road_stations(world,content,target,count=PUBLIC_ROAD_BANK_CHOICES):
    """A target's public road banks, best first (distance plus three times the height difference), each at least
    PUBLIC_ROAD_BANK_SPACING_METRES from the better ones: dry, manageable ground of the territory beside a public
    road within the usual reach, else within the fallback reach."""
    for reach in (PUBLIC_ROAD_REACH_METRES,PUBLIC_ROAD_FALLBACK_REACH_METRES):
        samples=[]
        for road in world.roads:
            # A resource trail is not a public approach for a village street.
            if str(road.get('id','')).startswith('trail-'):continue
            p=np.asarray(road['points'])[:,[0,2]]
            for a,b in zip(p,p[1:]):
                d=b-a;t=np.clip(np.dot(target['xz']-a,d)/max(np.dot(d,d),1e-9),0,1)
                q=a+t*d
                if 3<np.linalg.norm(q-target['xz'])<reach:samples.append(q)
        if samples:break
    if not samples:raise ValueError(target['name']+': no local public road approach')
    p=np.unique(np.floor(samples)+.5,axis=0);h=world.height_at(p[:,0],p[:,1])
    if not hasattr(content,'_village_walk_floors'):
        matrices,_=S.GR.hierarchy(content.documents[REGION][0]);parts=[]
        for obj in content.objects:
            if obj['region']==REGION and obj.get('kind') not in ('tree','foliage','rock','undergrowth'):
                faces=D._triangles(content,obj,matrices=matrices)
                if len(faces):parts.append(faces)
        content._village_walk_floors=np.concatenate(parts)
    h=np.maximum(h,floor_samples(content._village_walk_floors,p[:,0],p[:,1]))
    q=p[:,None,:]+np.array([[-.25,-.25],[-.25,.25],[.25,-.25],[.25,.25]])[None,:,:]
    wet,water=C.water_samples(world,q[:,:,0],q[:,:,1])
    use=((world.owner_at(q[:,:,0],q[:,:,1])==world.ids.index(REGION))&(~wet)&(C.terrain_grade(world,q[:,:,0],q[:,:,1])<.5)).all(axis=1)
    indices=np.flatnonzero(use)
    if not len(indices):raise ValueError(target['name']+': public approach has no dry manageable bank')
    ranked=sorted(indices,key=lambda i:np.linalg.norm(p[i]-target['xz'])+abs(h[i]-target['y'])*3)
    chosen=[]
    for i in ranked:
        if all(np.linalg.norm(p[i]-p[j])>=PUBLIC_ROAD_BANK_SPACING_METRES for j in chosen):chosen.append(i)
        if len(chosen)==count:break
    return [{'name':'public-road-'+target['name'],'xz':p[i],'y':float(h[i]),'faces':np.empty((0,3,3)),'ground':True,'reach':reach}
            for i in chosen]


def route(world,content,start,end):
    """A local street stays outside houses and within endpoint grade reach."""
    a,b=start['xz'],end['xz'];lo=np.floor(np.minimum(a,b)-12);hi=np.ceil(np.maximum(a,b)+12)
    x=np.arange(lo[0],hi[0]+1);z=np.arange(lo[1],hi[1]+1);gx,gz=np.meshgrid(x,z)
    ground=world.height_at(gx,gz)
    allowed=world.owner_at(gx,gz)==world.ids.index(REGION)
    allowed&=ground+.02<=np.minimum(start['y']+.48*np.hypot(gx-a[0],gz-a[1]),end['y']+.48*np.hypot(gx-b[0],gz-b[1]))+.08
    for triangles,low,high in structural_parts(content):
        if np.any(high[[0,2]]<lo) or np.any(low[[0,2]]>hi):continue
        if high[1]<min(start['y'],end['y'])+.1 or low[1]>max(start['y'],end['y'])+2.1:continue
        polygon=actor_band_polygon(triangles,min(start['y'],end['y'])+.06,max(start['y'],end['y'])+2.1)
        if polygon is not None:allowed&=~B.RoadOutline.inside(polygon,np.stack((gx,gz),axis=-1),tolerance=WIDTH+.1)
    for node in (start,end):
        if len(node['faces']):
            own=floor_samples(node['faces'],gx,gz)
            allowed|=np.isfinite(own)&(np.hypot(gx-node['xz'][0],gz-node['xz'][1])<2.4)
        else:allowed|=np.hypot(gx-node['xz'][0],gz-node['xz'][1])<1.8
    key=lambda p:(int(round(p[1]-lo[1])),int(round(p[0]-lo[0])))
    first,last=key(a),key(b);allowed[first]=allowed[last]=True
    queue=[(float(np.linalg.norm(a-b)),0.,first)];cost={first:0.};previous={}
    moves=[(dy,dx,float(np.hypot(dx,dy))) for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1))]
    while queue:
        _,g,current=heapq.heappop(queue)
        if g!=cost[current]:continue
        if current==last:break
        cy,cx=current
        for dy,dx,distance in moves:
            ny,nx=cy+dy,cx+dx
            if not 0<=ny<len(z) or not 0<=nx<len(x) or not allowed[ny,nx]:continue
            if dy and dx and (not allowed[cy,nx] or not allowed[ny,cx]):continue
            candidate=g+distance*(1.+.08*max(0.,abs(float(ground[ny,nx])-start['y'])))
            nxt=(ny,nx)
            if candidate<cost.get(nxt,np.inf):
                cost[nxt]=candidate;previous[nxt]=current
                heapq.heappush(queue,(candidate+float(np.hypot(nx-last[1],ny-last[0])),candidate,nxt))
    if last not in cost:return None
    chain=[last]
    while chain[-1]!=first:chain.append(previous[chain[-1]])
    p=np.array([[x[ix],z[iz]] for iz,ix in chain[::-1]]);p[0]=a;p[-1]=b
    def visible(a,b):
        q=a+np.linspace(0,1,max(2,int(np.linalg.norm(b-a)*3)+1))[:,None]*(b-a)
        ix=np.rint(q[:,0]-lo[0]).astype(int);iz=np.rint(q[:,1]-lo[1]).astype(int)
        return bool(allowed[iz,ix].all())
    result=[p[0]];i=0
    while i<len(p)-1:
        j=len(p)-1
        while j>i+1 and not visible(p[i],p[j]):j-=1
        result.append(p[j]);i=j
    return np.asarray(result)


def connect_group(world,content,roots,targets):
    connected=list(roots);remaining=list(targets);paths=[];links=[]
    while remaining:
        pairs=sorted((float(np.linalg.norm(a['xz']-b['xz'])),i,j) for i,a in enumerate(remaining) for j,b in enumerate(connected))
        found=None
        for distance,i,j in pairs:
            # A street is short: 40 m, or the reach its public road bank was found within (the fallback reach).
            if distance>max(40.,float(connected[j].get('reach',0.))):continue
            path=route(world,content,remaining[i],connected[j])
            if path is not None:found=(i,j,path);break
        if found is None:raise ValueError('No short exterior street reaches '+', '.join(n['name'] for n in remaining))
        i,j,path=found;node=remaining.pop(i)
        paths.append(path);links.append([node['name'],connected[j]['name']]);connected.append(node)
    return paths,links


def street_faces(world,content,paths,nodes,matrices):
    from manymouth_access import subtract
    p=np.concatenate(paths);lo=np.floor(p.min(axis=0)-3);hi=np.ceil(p.max(axis=0)+3)
    x=np.arange(lo[0],hi[0]+1);z=np.arange(lo[1],hi[1]+1);gx,gz=np.meshgrid(x,z)
    roads=[{'points':np.c_[p[:,0],np.zeros(len(p)),p[:,1]],'width':WIDTH} for p in paths]
    proxy=SimpleNamespace(x0=lo[0],z0=lo[1],x1=hi[0],z1=hi[1],roads=roads)
    outline=B.RoadOutline(proxy);cells=B.road_footprint(proxy);active=B.vertices_for_cells(cells)
    floor_parts=[];exclusions=[]
    for obj in content.objects:
        if obj['region']!=REGION or np.any(obj['high'][[0,2]]<lo) or np.any(obj['low'][[0,2]]>hi):continue
        if obj.get('kind') in ('tree','foliage','rock','undergrowth'):continue
        faces=D._triangles(content,obj,matrices=matrices)
        if len(faces):floor_parts.append(faces)
    for triangles,low,high in structural_parts(content):
        if np.any(high[[0,2]]<lo) or np.any(low[[0,2]]>hi):continue
        polygon=actor_band_polygon(triangles,min(n['y'] for n in nodes)+.06,max(n['y'] for n in nodes)+2.1)
        if polygon is not None:exclusions.append(polygon)
    existing=np.concatenate(floor_parts) if floor_parts else np.empty((0,3,3))
    visible=outline.contains(gx,gz)
    own=floor_samples(existing,gx,gz);fixed=np.isfinite(own)&active&visible
    ground=world.height_at(gx,gz);wet,water=C.water_samples(world,gx,gz)
    lower=np.maximum(ground+.015,np.where(wet,water+.1,-np.inf))
    # Conservative enclosing cells support interpolation outside the clipped
    # street; terrain outside its actual outline must not lift the walkway.
    lower[active&~visible]=-1e6
    lower[fixed]=own[fixed]+.015
    for node in nodes:
        if node.get('ground'):
            pin=(np.hypot(gx-node['xz'][0],gz-node['xz'][1])<=1.8)&active&visible
            pin&=~fixed
            fixed|=pin;lower[pin]=ground[pin]+.015
    if not fixed.any():raise ValueError('Village street has no actual floor or bank contacts')
    minimum=B.bounded_floor(lower,active,maximum_grade=.62)
    maximum=-B.bounded_floor(np.where(fixed,-lower,-1e6),active,maximum_grade=.62)
    if np.any(minimum[active]>maximum[active]+1e-6):
        at=np.unravel_index(np.argmax(np.where(active,minimum-maximum,-1)),minimum.shape)
        raise ValueError(f'Village approach needs more grade length at {[float(gx[at]),float(gz[at])]}: bounds differ {minimum[at]-maximum[at]:.3f}m')
    target=B.bank_profile(lower,active,~fixed)
    high=B.bounded_floor(target,active,maximum_grade=.62)
    low=-B.bounded_floor(-target,active,maximum_grade=.62)
    surface=lower.copy()
    surface[active]=np.clip((high[active]+low[active])*.5,minimum[active],maximum[active])
    error=float(np.max(surface[fixed]-lower[fixed],initial=0))
    if error>.025:
        at=np.unravel_index(np.argmax(np.where(fixed,surface-lower,-1)),surface.shape)
        raise ValueError(f'Village street cannot fit its true floor at {[float(gx[at]),float(gz[at])]}: lift {error:.3f}m')
    def sample(points):
        xx,zz=points[:,0],points[:,1];fx=np.clip(xx-lo[0],0,len(x)-1.00000001);fz=np.clip(zz-lo[1],0,len(z)-1.00000001)
        ix,iz=fx.astype(int),fz.astype(int);u,v=fx-ix,fz-iz
        a,b,c,d=surface[iz,ix],surface[iz,ix+1],surface[iz+1,ix],surface[iz+1,ix+1]
        with np.errstate(invalid='ignore'):
            return np.where(u+v<=1,a+(b-a)*u+(c-a)*v,d+(c-d)*(1-u)+(b-d)*(1-v))
    existing_clips=[]
    for face in existing:
        n=np.cross(face[1]-face[0],face[2]-face[0])
        if n[1]<=1e-8:continue
        point=face.mean(axis=0)
        if lo[0]<=point[0]<=hi[0] and lo[1]<=point[2]<=hi[1] and abs(sample(point[[0,2]][None])[0]-point[1])<.25:
            existing_clips.append(face[::-1][:,[0,2]])
    accepted=[]
    for iz,ix in np.argwhere(cells):
        corners=np.array([[x[ix],surface[iz,ix],z[iz]],[x[ix+1],surface[iz,ix+1],z[iz]],
            [x[ix],surface[iz+1,ix],z[iz+1]],[x[ix+1],surface[iz+1,ix+1],z[iz+1]]])
        for triangle in (corners[[0,2,1]],corners[[1,2,3]]):
            pieces=outline.clip(triangle)
            for clip in exclusions+existing_clips:
                pieces=subtract(pieces,clip)
                if not pieces:break
            for piece in pieces:accepted.extend(B.triangulate_floor(piece))
    faces=np.asarray(accepted,float).reshape(-1,3,3)
    if not len(faces):raise ValueError('Village street produced no new floor')
    q=encoded_planar_points(faces[:,:,[0,2]].reshape(-1,2))
    faces=np.c_[q[:,0],sample(q).astype(np.float32),q[:,1]].reshape(-1,3,3).astype(np.float32)
    normal=np.cross(faces[:,1].astype(float)-faces[:,0],faces[:,2].astype(float)-faces[:,0])
    keep=normal[:,1]>.0002;faces=faces[keep];normal=normal[keep]
    grades=np.hypot(normal[:,0],normal[:,2])/normal[:,1]
    if (grades>.65+1e-8).any():raise ValueError(f'Encoded village street grade {grades.max():.5f} exceeds .65')
    if not np.all(world.owner_at(faces[:,:,0],faces[:,:,2])==world.ids.index(REGION)):raise ValueError('Village street leaves territory')
    return faces,{'maximumGrade':float(grades.max(initial=0)),'maximumContactLift':error+.015,
        'newTriangles':len(faces),'precisionCleanupTriangles':int((~keep).sum())}


DECK_PREFIX='Walk_Manymouth_Village_'


def deck_name(world,identity):
    """The village street deck's node name, registered against the plan's designed_decks (an elevated walk)."""
    name=DECK_PREFIX+identity
    L.require_designed_deck(getattr(world,'plan',None) or {},name,'manymouth_village_streets')
    return name


def build_village_streets(world,content):
    matrices,_=S.GR.hierarchy(content.documents[REGION][0]);results=[]
    for identity,(public,names) in SOURCE_PLANS.items():
        roots=[station(content,name,matrices) for name in public]
        targets=[station(content,name,matrices) for name in names]
        options=[roots]
        if not roots:
            choices=[]
            for target in targets:
                try:nodes=public_road_stations(world,content,target)
                except ValueError:continue
                choices.extend((float(np.linalg.norm(node['xz']-target['xz']))+abs(node['y']-target['y'])*3,node) for node in nodes)
            if not choices:raise ValueError(identity+': no nearby public road bank')
            # Best bank first (a stable sort keeps the targets' order between equal banks); the next is tried only
            # when a street from the better one cannot reach every floor within the grade bounds.
            options=[[node] for _,node in sorted(choices,key=lambda item:item[0])]
        for index,roots in enumerate(options):
            try:
                paths,links=connect_group(world,content,roots,targets)
                faces,report=street_faces(world,content,paths,roots+targets,matrices)
                break
            except ValueError:
                if index==len(options)-1:raise
        report.update(id=identity,halfWidth=WIDTH,connections=links,paths=[p.tolist() for p in paths],
            publicContacts=[{'node':n['name'],'position':[float(n['xz'][0]),n['y'],float(n['xz'][1])]} for n in roots],
            targetFloors=[{'node':n['name'],'position':[float(n['xz'][0]),n['y'],float(n['xz'][1])]} for n in targets])
        results.append((faces,paths,report))
        print(f'Manymouth {identity}: {len(targets)} retained floor connections, grade {report["maximumGrade"]:.3f}',flush=True)
    return results
