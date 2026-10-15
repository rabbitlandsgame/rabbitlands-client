"""Fit Landfall's decorative causeway legs and close its deck joints.

Run with --bake DIR (a region_bake_cli snapshot) and --apply to update the
authoring scene and its local streamed package. Original walk and solid meshes
are retained byte for byte: this pass changes only non-colliding dressing.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import numpy as np
import shapely as SH
from shapely.geometry import Polygon, MultiPoint
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(ROOT/'eloria-assets/maps/nymara-regions/_continent'),
                str(ROOT/'eloria-assets/maps/nymara-regions/_toolkit')]
import prepare_meshy_kit as K
import glb_reader as GR
import scene_io as S

TAG = 'landfall-causeway-repair-v1'
REGION = ROOT/'godot-client/world_authoring/regions/sw_isle'
PROTOS = REGION/'assets/prototypes'
SCENE = REGION/'sw_isle.tscn'
PACKAGE = ROOT/'eloria-assets/maps/continent-v2/sw_isle/client'
RECORD = Path(__file__).parent/'causeway-repair-record.json'


def check_record():
    """Read-only verification of the authored dressing and local game chunks."""
    record=json.loads(RECORD.read_text())
    def check(path,expected):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f'dressing output changed: {path}')
    check(SCENE,record['sceneSha256'])
    for name,digest in record['prototypeSha256'].items():check(PROTOS/name,digest)
    for chunk in record['chunks']:
        check(PACKAGE/'chunks'/chunk['chunk']/'world.glb',chunk['afterSha256'])
    for name,digest in record['servedBinaries'].items():check(PACKAGE/name,digest)
    print(f"causeway repair verified: {record['supports']} supports, {record['joints']} joints, "
          f"{len(record['chunks'])} chunks; served binaries unchanged")


def ground_sample(h, terrain, xz):
    f = (np.asarray(xz)-terrain['origin'])/terrain['cellMetres']
    ix, iz = np.floor(f).astype(int).T
    if np.any(ix<0) or np.any(iz<0) or np.any(ix>=h.shape[1]-1) or np.any(iz>=h.shape[0]-1):
        raise ValueError('support outside baked terrain')
    u,v = (f-np.floor(f)).T
    a,b,c,d = h[iz,ix],h[iz,ix+1],h[iz+1,ix],h[iz+1,ix+1]
    return np.where(u+v<=1,a+(b-a)*u+(c-a)*v,d+(c-d)*(1-u)+(b-d)*(1-v))


def model_soup(path):
    doc,body=K._read(path)
    root=doc['nodes'][0]
    return doc,K._soup(doc,body,root['mesh'])


def encode(template, soup, name, origin):
    """One decorative mesh; no Walk_ node, collider, or imported transforms."""
    doc=copy.deepcopy(template)
    material=doc['meshes'][doc['nodes'][0]['mesh']]['primitives'][0]['material']
    soup=soup.copy();soup[:,:,:3]-=origin
    # Thin seam slivers can collapse when the prototype is encoded to float32.
    p=soup[:,:,:3].astype('<f4').astype(float)
    area=np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1)
    soup=soup[area>1e-9]
    pos,normal,uv,indices=K._soup_arrays(soup)
    arrays=[pos,normal,uv,indices.reshape(-1,1)]
    doc['accessors']=[];doc['bufferViews']=[];body=bytearray()
    for values,kind,component in zip(arrays,['VEC3','VEC3','VEC2','SCALAR'],[5126,5126,5126,5125]):
        body.extend(b'\0'*(-len(body)%4));payload=values.tobytes()
        doc['bufferViews'].append({'buffer':0,'byteOffset':len(body),'byteLength':len(payload)})
        a={'bufferView':len(doc['bufferViews'])-1,'componentType':component,'count':len(values),'type':kind}
        if kind=='VEC3':a.update(min=values.min(0).tolist(),max=values.max(0).tolist())
        doc['accessors'].append(a);body.extend(payload)
    doc['meshes']=[{'name':name,'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'indices':3,'material':material}]}]
    doc['nodes']=[{'name':name,'mesh':0,'extras':{'eloria':{'dressing':TAG,'collisionRole':'none'}}}]
    doc['scenes']=[{'nodes':[0]}];doc['scene']=0
    doc.pop('animations',None)
    doc['buffers']=[{'byteLength':len(body)}]
    return doc,bytes(body)


def world_soup(soup, matrix):
    out=soup.copy();out[:,:,:3]=soup[:,:,:3]@matrix[:3,:3].T+matrix[:3,3]
    n=soup[:,:,3:6]@np.linalg.inv(matrix[:3,:3])
    out[:,:,3:6]=n/np.maximum(np.linalg.norm(n,axis=2,keepdims=True),1e-12)
    return out


def support_soup(body,matrix,h,terrain):
    """Sweep each existing foot contour vertically, repeating its stone UV band."""
    lower,_=K._split_soup(body,-7.7,axis=1)
    band,_=K._split_soup(body,-6.,axis=1)
    sample=band.reshape(-1,8)
    sample=sample[np.abs(sample[:,1]+6)<1e-5]
    out=[]
    for xs in (-1,1):
        for zs in (-1,1):
            select=(np.sign(lower[:,:,0].mean(1))==xs)&(np.sign(lower[:,:,2].mean(1))==zs)
            if not select.any():continue
            edges=[];seen=set()
            for tri in lower[select]:
                edge=tri[np.abs(tri[:,1]+7.7)<1e-5]
                if len(edge)!=2:continue
                key=tuple(sorted(tuple(p) for p in edge[:,:3].round(5)))
                if key in seen:continue
                seen.add(key);edges.append(edge)
            if not edges:continue
            world=world_soup(np.stack([np.stack([e[0],e[1],e[0]]) for e in edges]),matrix)
            xz=world[:,:2,[0,2]].reshape(-1,2)
            floor=float(ground_sample(h,terrain,np.vstack([xz,xz.mean(0)])).min())-.6
            if floor>=world[:,:,1].min()-.3:continue
            for edge,placed in zip(edges,world):
                a,b=placed[:2,:3];length=max(a[1],b[1])-floor
                # Use the UVs at both ends of the accepted 1.7 m leg band;
                # repeating this band keeps the masonry's original block size.
                near=cKDTree(sample[:,[0,2]]).query(edge[:,[0,2]])[1]
                uv_top=sample[near,6:8];uv_bottom=edge[:,6:8]
                for offset in np.arange(0,length,1.7):
                    depth=min(1.7,length-offset)
                    p=np.stack([a-[0,offset,0],b-[0,offset,0],b-[0,offset+depth,0],a-[0,offset+depth,0]])
                    uv_low=uv_top+(uv_bottom-uv_top)*(depth/1.7)
                    uv=np.stack([uv_top[0],uv_top[1],uv_low[1],uv_low[0]])
                    for indices in ([0,1,2],[0,2,3]):
                        pp=p[indices];normal=np.cross(pp[1]-pp[0],pp[2]-pp[0])
                        expected=placed[:2,3:6].mean(0)
                        if normal@expected<0:
                            indices=list(reversed(indices));pp=p[indices];normal=-normal
                        normal/=max(np.linalg.norm(normal),1e-12)
                        out.append(np.c_[pp,np.tile(normal,(3,1)),uv[indices]])
    return np.stack(out) if out else np.zeros((0,3,8))


def prism(points,top,bottom,texel):
    """Textured slab with a real underside and side faces, positive top winding."""
    polygon=Polygon(points)
    if not polygon.is_valid:polygon=SH.make_valid(polygon)
    soups=[]
    def face(p):
        p=np.asarray(p,float);n=np.cross(p[1]-p[0],p[2]-p[0]);length=np.linalg.norm(n)
        if length<1e-9:return
        soups.append(np.c_[p,np.tile(n/length,(3,1)),np.tile(texel,(3,1))])
    for tri in SH.get_parts(SH.constrained_delaunay_triangles(polygon)):
        xz=np.asarray(tri.exterior.coords)[:3];y=top(xz)
        p=np.c_[xz[:,0],y,xz[:,1]]
        if np.cross(p[1]-p[0],p[2]-p[0])[1]<0:p=p[::-1]
        face(p);q=p.copy();q[:,1]-=bottom;face(q[::-1])
    for poly in SH.get_parts(polygon):
        if poly.geom_type!='Polygon':continue
        for ring in [poly.exterior,*poly.interiors]:
            p=np.asarray(ring.coords)
            for a,b in zip(p,p[1:]):
                y=top(np.stack([a,b]));v=np.array([[a[0],y[0],a[1]],[b[0],y[1],b[1]],
                                                [b[0],y[1]-bottom,b[1]],[a[0],y[0]-bottom,a[1]]])
                face(v[[0,2,1]]);face(v[[0,3,2]])
    return np.stack(soups) if soups else np.zeros((0,3,8))


def joins(modules):
    """Join nearest facing module ends, including the short bend modules."""
    ends=[]
    for i,m in enumerate(modules):
        for side in (-1,1):
            center=m['matrix'][:3,3]+side*6*m['matrix'][:3,0]
            ends.append((i,side,center))
    edges=set()
    for k,(i,side,p) in enumerate(ends):
        candidates=[(np.linalg.norm(p-q),j) for j,(ii,ss,q) in enumerate(ends) if ii!=i]
        if not candidates:continue
        distance,j=min(candidates)
        # Longer gaps indicate the open abutment, not a neighbouring span.
        if distance<3.5:edges.add(tuple(sorted((k,j))))
    return [(ends[a],ends[b]) for a,b in sorted(edges)]


def generate(snapshot,bake,scene=None):
    terrain=snapshot['terrain'];h=np.fromfile(bake/terrain['resolvedHeights']['path'],dtype='<f4').reshape(terrain['height'],terrain['width'])
    groups={};jobs=[];cache={}
    scene=scene or SCENE.read_text(encoding='utf-8')
    for block in re.split(r'(?=\[node )',scene):
        if '"coastKind": "deck-top"' not in block:continue
        asset=re.search(r'asset_id = "([^"]+)"',block)[1]
        path=re.search(r'scene_path = "res://([^"]+)"',block)[1]
        values=np.array([float(v) for v in re.search(r'Transform3D\(([^)]*)\)',block)[1].split(',')])
        mat=np.eye(4);mat[:3,:3]=values[:9].reshape(3,3);mat[:3,3]=values[9:]
        group=re.search(r'"coastGroup": "([^"]+)"',block)[1]
        if path not in cache:
            doc,blob=K._read(ROOT/'godot-client'/path)
            parts=[K._soup(doc,blob,n['mesh']) for n in doc['nodes'] if 'mesh' in n]
            cache[path]=(doc,parts[0],parts)
        doc,soup,parts=cache[path];world=world_soup(soup,mat)
        m={'asset':asset,'matrix':mat,'doc':doc,'soup':soup,'world':world,'group':group,
           'parts':[(world_soup(part,mat),part) for part in parts]}
        groups.setdefault(group,[]).append(m)
        support=support_soup(soup,mat,h,terrain)
        if len(support):
            jobs.append({'name':'kit-sw-causeway-support-'+asset.removeprefix('sw_isle-kit-sw-causeway-arch-'),
                         'origin':mat[:3,3],'soup':support,'template':doc,'group':group})
    joint_count=0
    for group,modules in groups.items():
        for a,b in joins(modules):
            i,side,center=a;j,other,center2=b
            ma,mb=modules[i],modules[j]
            across=ma['matrix'][:3,2];across2=mb['matrix'][:3,2]
            if across@across2<0:across2=-across2
            # Bridge the complete cross-section, not just the centre line.
            corners=np.stack([center-6.7567568*across,center+6.7567568*across,
                              center2-6.7567568*across2,center2+6.7567568*across2])
            # Existing top surfaces supply boundary heights and UV colour.
            footprint=[];samples=[];texels=[]
            for m in (ma,mb):
                for ws,local in m['parts']:
                    norm=np.cross(ws[:,1,:3]-ws[:,0,:3],ws[:,2,:3]-ws[:,0,:3])
                    # Deck surface only; exclude parapet tops and gate steps.
                    keep=(norm[:,1]>0)&(np.abs(local[:,:,1].mean(1))<.15)
                    for tri in ws[keep]:
                        poly=Polygon(tri[:,[0,2]])
                        if poly.area>1e-8:footprint.append(poly)
                    samples.extend(ws[keep,:,:3].reshape(-1,3));texels.extend(ws[keep,:,6:8].reshape(-1,2))
            if not footprint:raise ValueError('joint has no deck surface')
            # Trim to the lane: the outer strips carry the connecting parapets.
            lane=MultiPoint(np.stack([center-5.49*across,center+5.49*across,
                                     center2-5.49*across2,center2+5.49*across2])[:,[0,2]]).convex_hull
            missing=lane.difference(SH.union_all(footprint))
            if missing.area<.002:continue
            samples=np.asarray(samples);texels=np.asarray(texels);tree=cKDTree(samples[:,[0,2]])
            def top(xz):
                # Local deck plane follows the existing graded centre line.
                delta=center2[[0,2]]-center[[0,2]];denom=delta@delta
                t=np.clip((xz-center[[0,2]])@delta/max(denom,1e-10),0,1)
                return center[1]+t*(center2[1]-center[1])+.012
            pieces=[]
            for poly in SH.get_parts(missing):
                if poly.geom_type!='Polygon' or poly.area<.002:continue
                pieces.append(prism(np.asarray(poly.exterior.coords)[:-1],top,.85,texels[tree.query(np.array(poly.centroid.coords))[1][0]]))
            # Carry both parapets across the seam with the same stone material.
            for sign in (-1,1):
                rail=MultiPoint(np.stack([center+sign*5.49*across,center+sign*6.7567568*across,
                                          center2+sign*5.49*across2,center2+sign*6.7567568*across2])[:,[0,2]]).convex_hull
                if rail.geom_type=='Polygon' and rail.area>.002:
                    rail_top=lambda xz:top(xz)+1.08
                    pieces.append(prism(np.asarray(rail.exterior.coords)[:-1],rail_top,1.9,texels[0]))
            if not pieces:continue
            joint_count+=1
            jobs.append({'name':f'kit-sw-causeway-joint-{group}-{joint_count:03d}','origin':(center+center2)/2,
                         'soup':np.concatenate(pieces),'template':ma['doc'],'group':group})
    return scene,jobs,joint_count


def write_scene(scene,jobs):
    blocks=re.split(r'(?=\[node )',scene)
    removed=[];kept=[];skip_parent=None
    for block in blocks:
        if '"coastKind": "tier"' in block:
            name=re.search(r'^\[node name="([^"]+)"',block)[1];skip_parent='AuthoredAssets/'+name
            removed.append(name);continue
        if skip_parent and 'parent="'+skip_parent+'"' in block:continue
        skip_parent=None;kept.append(block)
    text=''.join(kept);ext=[];nodes=[]
    for k,j in enumerate(jobs):
        rid=f'bridge_repair_{k}';name=j['name'];origin=j['origin']
        ext.append(f'[ext_resource type="PackedScene" path="res://world_authoring/regions/sw_isle/assets/prototypes/{name}.glb" id="{rid}"]\n')
        nodes.append(f'\n[node name="{name}" type="Node3D" parent="AuthoredAssets"]\nposition = Vector3({origin[0]}, {origin[1]}, {origin[2]})\nscript = ExtResource("19_jaile")\nasset_id = "sw_isle-{name}"\nnode_name = "{name}"\ncatalog_asset_id = "sw_isle:{name}"\nscene_path = "res://world_authoring/regions/sw_isle/assets/prototypes/{name}.glb"\ncollision_role = "none"\nmetadata = {{\n"bridgeDressing": "{TAG}",\n"coastGroup": "{j["group"]}"\n}}\nmetadata/map_authoring_asset_wrapper = true\n\n[node name="Content" parent="AuthoredAssets/{name}" instance=ExtResource("{rid}")]\nmetadata/map_asset_id = "sw_isle:{name}"\nmetadata/map_asset_scene = "res://world_authoring/regions/sw_isle/assets/prototypes/{name}.glb"\n')
    marker=text.index('[sub_resource')
    text=text[:marker]+''.join(ext)+'\n'+text[marker:]+''.join(nodes)
    return text,len(removed)


def append_document(target,body,source,src_body,origin,source_path,target_path):
    """Append a static decorative GLB without touching existing accessors."""
    fields=['bufferViews','accessors','images','samplers','textures','materials','meshes','nodes']
    offsets={key:len(target.get(key,[])) for key in fields}
    pad=-len(body)%4;start=len(body)+pad;body+=b'\0'*pad+src_body
    source=copy.deepcopy(source)
    for v in source['bufferViews']:v['byteOffset']=v.get('byteOffset',0)+start
    for a in source['accessors']:a['bufferView']+=offsets['bufferViews']
    for image in source.get('images',[]):
        if 'bufferView' in image:image['bufferView']+=offsets['bufferViews']
        if 'uri' in image:
            original=source_path.parent/image['uri'];payload=original.read_bytes()
            digest=hashlib.sha256(payload).hexdigest()
            shared=ROOT/'eloria-assets/maps/continent-v2/_continent_v2/shared-assets'/(digest+original.suffix)
            if not shared.exists():shared.write_bytes(payload)
            image['uri']=os.path.relpath(shared,target_path.parent).replace('\\','/')
    for tex in source.get('textures',[]):
        if 'source' in tex:tex['source']+=offsets['images']
        if 'sampler' in tex:tex['sampler']+=offsets['samplers']
    def material_walk(item):
        if isinstance(item,dict):
            for key,value in item.items():
                if key.endswith('Texture') and isinstance(value,dict) and 'index' in value:value['index']+=offsets['textures']
                else:material_walk(value)
        elif isinstance(item,list):
            for value in item:material_walk(value)
    for mat in source.get('materials',[]):material_walk(mat)
    for mesh in source['meshes']:
        for p in mesh['primitives']:
            p['attributes']={key:value+offsets['accessors'] for key,value in p['attributes'].items()}
            p['indices']+=offsets['accessors'];p['material']+=offsets['materials']
    for node in source['nodes']:
        if 'mesh' in node:node['mesh']+=offsets['meshes']
        if 'children' in node:node['children']=[i+offsets['nodes'] for i in node['children']]
    source['nodes'][0]['translation']=origin.tolist()
    for key in fields:target.setdefault(key,[]).extend(source.get(key,[]))
    target['scenes'][target.get('scene',0)]['nodes'].append(offsets['nodes'])
    target['buffers']=[{'byteLength':len(body)}]
    return body


def patch_package(jobs,record,backup):
    manifest=json.loads((PACKAGE/'world.json').read_text());changed=[]
    originals=manifest['streamingChunks']['chunks']
    additions={}
    for j in jobs:
        origin=j['origin'];cell=np.floor((origin[[0,2]]-[-1023,-1119])/96).astype(int)
        additions.setdefault(f'{cell[0]:02d}_{cell[1]:02d}',[]).append(j)
    for entry in originals:
        path=PACKAGE/entry['manifest'];glb=path.parent/'world.glb';doc,body=GR.load(glb)
        roots=doc['scenes'][doc.get('scene',0)]['nodes']
        tiers=[r for r in roots if 'causeway_arch_tier' in doc['nodes'][r].get('name','')]
        local_jobs=additions.get(entry['id'],[])
        if not tiers and not local_jobs:continue
        saved=backup/'chunks'/entry['id'];saved.mkdir(parents=True,exist_ok=True)
        (saved/'world.glb').write_bytes(glb.read_bytes());(saved/'world.json').write_bytes(path.read_bytes())
        # Drop the hierarchy from rendering; original buffers/indices remain
        # untouched, including every authoritative walk mesh.
        doc['scenes'][doc.get('scene',0)]['nodes']=[r for r in roots if r not in tiers]
        for r in tiers:
            for i in S.descendants(doc,[r]):doc['nodes'][i]={'name':'Retired_causeway_tier'}
        before=hashlib.sha256(glb.read_bytes()).hexdigest()
        for j in local_jobs:
            sd,sb=K._read(PROTOS/(j['name']+'.glb'))
            body=append_document(doc,body,sd,sb,j['origin'],PROTOS/(j['name']+'.glb'),glb)
        S.dump_glb(glb,doc,body)
        child=json.loads(path.read_text());matrices,_=GR.hierarchy(doc)
        bounds=[S.subtree_bounds(doc,body,r,matrices) for r in doc['scenes'][doc.get('scene',0)]['nodes']]
        bound={'min':np.min([b[0] for b in bounds],axis=0).tolist(),'max':np.max([b[1] for b in bounds],axis=0).tolist()}
        entry['bounds']=bound;entry['glbBytes']=glb.stat().st_size
        delta=entry['glbBytes']-child['performance']['glbBytes']
        entry['geometryResidentBytes']+=delta
        entry['estimatedResidentBytes']+=delta
        child['asset']['bounds']=bound;child['bounds']=bound
        child['performance'].update(glbBytes=entry['glbBytes'],nodes=len(doc['nodes']),meshes=len(doc['meshes']))
        child['provenance']['bridgeDressing']=TAG
        # New images reference the same accepted stone maps, by digest.
        for image in doc.get('images',[]):
            if 'uri' not in image:continue
            uri=image['uri'];digest=hashlib.sha256((glb.parent/uri).read_bytes()).hexdigest()
            child['externalResources'][uri]=digest
            child['performance']['externalResources'][uri]=digest
        from PIL import Image
        residents=child['performance']['sharedResourceResidentBytes']
        for image in doc.get('images',[]):
            if 'uri' not in image:continue
            image_path=glb.parent/image['uri'];digest=hashlib.sha256(image_path.read_bytes()).hexdigest()
            if digest not in residents:
                with Image.open(image_path) as picture:residents[digest]=int(np.ceil(picture.width*picture.height*4*4/3))
        entry['sharedResourceResidentBytes']=residents
        entry['estimatedResidentBytes']=entry['geometryResidentBytes']+sum(residents.values())
        path.write_text(json.dumps(child,indent=1)+'\n',encoding='utf-8',newline='\n')
        changed.append({'chunk':entry['id'],'beforeSha256':before,'afterSha256':hashlib.sha256(glb.read_bytes()).hexdigest(),'tiersRemoved':len(tiers),'dressingPieces':len(local_jobs)})
    manifest['provenance']['bridgeDressing']={'revision':TAG,'tool':'eloria-assets/maps/continent-v2/sw_isle/source/repair_causeways.py','sourceSceneSha256':hashlib.sha256(SCENE.read_bytes()).hexdigest(),'servedGeometryUnchanged':True}
    for c in changed:
        child=json.loads((PACKAGE/'chunks'/c['chunk']/'world.json').read_text())
        for uri,digest in child['externalResources'].items():
            manifest['externalResources'][os.path.relpath(PACKAGE/'chunks'/c['chunk']/uri,PACKAGE).replace('\\','/')]=digest
    # Mark the picture for the required render_minimap.py refresh.
    if manifest.get('minimap'):
        manifest['minimap']['bridgeDressingRevision']=TAG
    (PACKAGE/'world.json').write_text(json.dumps(manifest,indent=1)+'\n',encoding='utf-8',newline='\n')
    record['chunks']=changed
    publication_path=PACKAGE/'publication.json'
    publication=json.loads(publication_path.read_text());publication['bridgeDressing']=record
    publication_path.write_text(json.dumps(publication,indent=1)+'\n',encoding='utf-8',newline='\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--bake',type=Path);ap.add_argument('--apply',action='store_true')
    ap.add_argument('--check',action='store_true',help='verify the recorded output without a bake')
    args=ap.parse_args()
    if args.check:
        check_record();return
    if args.bake is None:ap.error('--bake is required to generate the dressing')
    snapshot=json.loads((args.bake/'continent-authoring.json').read_text())
    if snapshot['regionId']!='sw_isle':raise ValueError('expected Landfall bake')
    if TAG in SCENE.read_text():raise ValueError('repair already applied; use the recorded baseline scene to regenerate')
    if snapshot['sources']['scene']['sha256']!=hashlib.sha256(SCENE.read_bytes()).hexdigest():
        raise ValueError('scene changed since the terrain bake; re-bake before repairing')
    scene,jobs,count=generate(snapshot,args.bake)
    edited,tiers=write_scene(scene,jobs)
    record={'revision':TAG,'supports':len(jobs)-count,'joints':count,'tiersRemoved':tiers,'servedGeometryUnchanged':True,
            'terrainSha256':hashlib.sha256((args.bake/'resolved-heights.f32le').read_bytes()).hexdigest()}
    if args.apply:
        backup=args.bake/'bridge-backup';backup.mkdir(parents=True,exist_ok=True)
        (backup/'sw_isle.tscn').write_bytes(SCENE.read_bytes())
        (backup/'world.json').write_bytes((PACKAGE/'world.json').read_bytes())
        (backup/'publication.json').write_bytes((PACKAGE/'publication.json').read_bytes())
        for j in jobs:
            doc,body=encode(j['template'],j['soup'],j['name'],j['origin']);S.dump_glb(PROTOS/(j['name']+'.glb'),doc,body)
        SCENE.write_text(edited,encoding='utf-8',newline='\n')
        patch_package(jobs,record,backup)
        record['sceneSha256']=hashlib.sha256(SCENE.read_bytes()).hexdigest()
        record['prototypeSha256']={j['name']+'.glb':hashlib.sha256((PROTOS/(j['name']+'.glb')).read_bytes()).hexdigest() for j in jobs}
        record['servedBinaries']={name:hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest() for name in ('collision.bin','served-grid.escg.gz')}
        RECORD.write_text(json.dumps(record,indent=1)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in record.items() if k!='chunks'},indent=1))


if __name__=='__main__':main()
