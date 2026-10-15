"""Actual low stone ramps connect the retained quay and sanctuary bank walks."""
from pathlib import Path
import copy
import numpy as np
import scene_io as S
from ferry_export import G,M
from mirror_support import upper_floor_field
import landscape as L

REGION='mirrorhold'


def _split(poly, values):
    inside=[];outside=[]
    for i,current in enumerate(poly):
        j=(i+1)%len(poly);following=poly[j];a,b=values[i],values[j]
        (inside if a>=0 else outside).append(current)
        if (a>=0)!=(b>=0):
            hit=current+(following-current)*(a/(a-b))
            inside.append(hit);outside.append(hit)
    return np.asarray(inside),np.asarray(outside)


def open_sanctuary_landing(content):
    """Cut one real entry through the old causeway's continuous stone parapet.

    Only non-Walk faces of the named link can change. Clipping the six planes
    retains every part of the rail outside a 4.6 m opening and every foundation
    below the walking level. The floor and the discovery's geometry are intact.
    """
    if hasattr(content,'mirror_landing_opening'):return content.mirror_landing_opening
    obj=content.placement_by_name[(REGION,'Landmark_LakeLink_Sanctuary')]
    document,body=content.documents[REGION];doc=copy.deepcopy(document);data=bytearray(body)
    matrices,_=S.GR.hierarchy(doc);center=np.array([866.5,874.5])
    direction=np.array([-8.,-26.]);direction/=np.linalg.norm(direction)
    side=np.array([-direction[1],direction[0]]);changed=0
    for index in S.descendants(doc,[obj['index']]):
        node=doc['nodes'][index]
        if 'mesh' not in node or node.get('name','').startswith('Walk_'):continue
        mesh=copy.deepcopy(doc['meshes'][node['mesh']]);node_changed=False
        for primitive in mesh['primitives']:
            attrs=list(primitive['attributes']);arrays=[S.GR.accessor(doc,data,primitive['attributes'][a]).astype(float) for a in attrs]
            sizes=[a.shape[1] if a.ndim>1 else 1 for a in arrays];offsets=np.cumsum([0]+sizes)
            packed=np.concatenate([a.reshape(len(a),-1) for a in arrays],axis=1)
            position=attrs.index('POSITION');ps=slice(offsets[position],offsets[position+1])
            ids=S.GR.accessor(doc,data,primitive['indices']).reshape(-1,3).astype(int)
            matrix=matrices[index];output=[];cuts=0
            for face in packed[ids]:
                remaining=face.copy();pieces=[];original_area=np.linalg.norm(np.cross(face[1,ps]-face[0,ps],face[2,ps]-face[0,ps]))
                for axis,bound,sign in ((0,-2.3,1),(0,2.3,-1),(1,-3.,1),(1,3.,-1),(2,85.25,1),(2,88.,-1)):
                    if not len(remaining):break
                    xyz=remaining[:,ps]@matrix[:3,:3].T+matrix[:3,3]+obj['shift']
                    q=xyz[:,[0,2]]-center
                    coordinates=np.c_[q@side,q@direction,xyz[:,1]]
                    remaining,outside=_split(remaining,(coordinates[:,axis]-bound)*sign)
                    if len(outside)>=3:pieces.append(outside)
                if len(remaining)>=3:
                    area=np.linalg.norm(np.cross(remaining[1,ps]-remaining[0,ps],remaining[2,ps]-remaining[0,ps]))
                    cuts+=int(area>1e-8 and original_area>1e-8)
                for polygon in pieces:
                    output.extend(np.asarray([polygon[0],polygon[i],polygon[i+1]]) for i in range(1,len(polygon)-1))
            if not cuts:continue
            vertices=np.asarray(output).reshape(-1,packed.shape[1])
            def append(array,kind):
                array=np.ascontiguousarray(array,dtype='<f4' if kind!='SCALAR' else '<u4');data.extend(b'\0'*((-len(data))%4))
                view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':len(data),'byteLength':array.nbytes});data.extend(array.tobytes())
                accessor={'bufferView':view,'componentType':5126 if kind!='SCALAR' else 5125,'count':len(array),'type':kind}
                if kind=='VEC3':accessor.update(min=array.min(axis=0).tolist(),max=array.max(axis=0).tolist())
                result=len(doc['accessors']);doc['accessors'].append(accessor);return result
            for i,attr in enumerate(attrs):primitive['attributes'][attr]=append(vertices[:,offsets[i]:offsets[i+1]],'VEC'+str(sizes[i]))
            primitive['indices']=append(np.arange(len(vertices)),'SCALAR')
            changed+=cuts;node_changed=True
        if node_changed:node['mesh']=len(doc['meshes']);doc['meshes'].append(mesh)
    if not 1<=changed<=48:raise ValueError('Sanctuary ramp requires one bounded actual parapet opening')
    doc['buffers'][0]['byteLength']=len(data);content.documents[REGION]=(doc,bytes(data))
    content.mirror_landing_opening={'node':obj['node'],'clippedTriangles':changed,'openingWidth':4.6,'floorUnchanged':True}
    return content.mirror_landing_opening


def existing_floor(world,content,x,z,region=REGION):
    """The ground, lifted to any authored Walk_ floor of the region standing over the point."""
    result=world.height_at(x,z)
    lo=np.array([x.min(),z.min()])-1;hi=np.array([x.max(),z.max()])+1
    doc,body=content.documents[region]
    for obj in content.objects:
        if obj['region']!=region or np.any(obj['high'][[0,2]]<lo) or np.any(obj['low'][[0,2]]>hi):continue
        indices=[i for i in S.descendants(doc,[obj['index']]) if 'mesh' in doc['nodes'][i]
                 and doc['nodes'][i].get('name','').startswith('Walk_')]
        if not indices:continue
        triangles=S.GR.triangles(doc,body,indices)+obj['shift']
        normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        triangles=triangles[normal[:,1]>.7*np.linalg.norm(normal,axis=1)]
        if not len(triangles):continue
        floor,distance=upper_floor_field(triangles,x,z)
        result=np.where(distance<1e-7,np.maximum(result,floor),result)
    return result


def stone_texture():
    """Coursed ashlar readable from the gameplay camera: two courses per metre, staggered joints."""
    import io
    from PIL import Image
    x,y=np.meshgrid(np.arange(128),np.arange(128));course=y//32
    block=(x+(course%2)*32)//64
    tone=np.array([0,-6,4,-3])[(course*3+block)%4]
    grain=3*np.sin(x*.31+course*2.1)+2*np.sin(y*.47+block*1.3)
    joint=(y%32<2)|(((x+(course%2)*32)%64)<2)
    rgb=np.stack([150+tone+grain,146+tone+grain,132+tone+grain],axis=-1)
    rgb[joint]=[92,88,78]
    output=io.BytesIO();Image.fromarray(np.uint8(np.clip(rgb,0,255))).save(output,format='PNG')
    return output.getvalue()


def ramp_mesh(world,content,start,stop,material,half_width=1.8,region=REGION):
    """A walking deck between two points: the .45 lower envelope over the region's ground and authored floors."""
    start,stop=np.asarray(start,float),np.asarray(stop,float)
    vector=stop-start;length=np.linalg.norm(vector);normal=np.array([-vector[1],vector[0]])/length
    along=np.linspace(0,1,int(np.ceil(length))+1);across=np.linspace(-half_width,half_width,9)
    points=start+along[:,None,None]*vector+across[None,:,None]*normal
    floor=existing_floor(world,content,points[:,:,0],points[:,:,1],region)
    flat=points.reshape(-1,2)
    # A Euclidean lower envelope raises only the stone surface over the local
    # bank. .45 bounds both axes of every linear triangle below .65 grade.
    distances=np.linalg.norm(flat[:,None,:]-flat[None,:,:],axis=2)
    upper=np.max((floor.ravel()+.025)[:,None]-.45*distances,axis=0).reshape(floor.shape)
    vertices=np.c_[flat[:,0],upper.ravel(),flat[:,1]]
    row,col=np.indices((len(along)-1,len(across)-1));a=(row*len(across)+col).ravel();b=a+1;c=a+len(across);d=c+1
    indices=np.c_[a,b,c,b,d,c].ravel()
    mesh=M.Mesh(positions=vertices,normals=np.tile([0.,1.,0.],(len(vertices),1)),
                uvs=np.c_[np.repeat(along*length,len(across)),np.tile(across,len(along))],indices=indices,material=material)
    mesh.recompute_normals(180)
    tri=vertices.astype(np.float32).astype(float)[indices.reshape(-1,3)];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    grade=np.hypot(n[:,0],n[:,2])/n[:,1]
    if n[:,1].min()<=0 or grade.max()>.65:raise ValueError('Access ramp violates actual triangle walking grade')
    contact=(upper[[0,-1]]-floor[[0,-1]]).max(axis=1)
    if contact.max()>.08:raise ValueError('Access ramp needs a better ground/deck contact')
    return mesh,{'start':start.tolist(),'stop':stop.tolist(),'maximumGrade':float(grade.max()),
        'maximumSupportHeight':float((upper-floor).max()),'contactLift':(upper[[0,-1]]-floor[[0,-1]]).max(axis=1).tolist()}


def foundation_faces(world,mesh,material):
    """Visible masonry edge foundations stay below the actual walking face."""
    faces=mesh.indices.reshape(-1,3)
    edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True)
    top=mesh.positions[unique[counts==1]].copy();top[:,:,1]-=.04
    bottom=top.copy()
    bottom[:,:,1]=np.minimum(top[:,:,1]-.24,world.height_at(top[:,:,0],top[:,:,2])-.12)
    vertices=np.stack([top[:,0],top[:,1],bottom[:,0],bottom[:,1]],axis=1).reshape(-1,3)
    indices=(np.arange(len(top))[:,None]*4+np.array([0,2,1,1,2,3])).ravel()
    result=M.Mesh(positions=vertices,normals=np.zeros_like(vertices),uvs=vertices[:,[0,2]],indices=indices,material=material)
    result.recompute_normals(180)
    return result


def build_mirror_access(world,content,path):
    if REGION in getattr(world,'authoring_snapshots',{}):
        # The imported Mirrorhold scene owns exact saved copies of both bank
        # ramp/foundation pairs. Keep the auxiliary GLB structurally valid for
        # the normal export pipeline without regenerating duplicate geometry.
        builder=G.GltfBuilder('Saved Mirrorhold bank access authority')
        Path(path).parent.mkdir(parents=True,exist_ok=True);builder.write_glb(str(path))
        world.mirror_bank_access=[{'authority':'saved-authored-assets','region':REGION}]
        world.mirror_bank_opening={'authority':'saved-resolved-terrain','region':REGION}
        return []
    opening=open_sanctuary_landing(content)
    builder=G.GltfBuilder('Eloria Mirrorhold bank access')
    # Coursed stone instead of one flat pale colour; the ramp UVs are metres.
    builder.add_image('mirror_bank_ashlar',stone_texture())
    builder.add_material(G.Material('mirror_bank_stone',base_color_texture='mirror_bank_ashlar',roughness=.95,double_sided=True))
    parts=[];reports=[]
    for name,start,stop in [('Quay',[968.5,814.5],[940.5,796.5]),
                            ('Sanctuary',[874.5,900.5],[866.5,874.5])]:
        node='Walk_Mirror_BankRamp_'+name
        L.require_designed_deck(getattr(world,'plan',None) or {},node,'mirror_access_geometry')
        mesh,report=ramp_mesh(world,content,start,stop,'mirror_bank_stone')
        builder.add_mesh(node,mesh,with_tangents=False);root=builder.add_node(G.Node(node,mesh=node))
        parts.append({'region':REGION,'node':node,'roots':[root],'bounds':mesh.bounds(),'segment':[],'collides':False})
        foundation=foundation_faces(world,mesh,'mirror_bank_stone');foundation_name='Mirror_BankRamp_Foundation_'+name
        builder.add_mesh(foundation_name,foundation,with_tangents=False)
        root=builder.add_node(G.Node(foundation_name,mesh=foundation_name))
        parts.append({'region':REGION,'node':foundation_name,'roots':[root],'bounds':foundation.bounds(),'segment':[],'collides':False})
        reports.append({'node':node,**report})
    Path(path).parent.mkdir(parents=True,exist_ok=True);builder.write_glb(str(path))
    world.mirror_bank_access=reports
    world.mirror_bank_opening=opening
    return parts
