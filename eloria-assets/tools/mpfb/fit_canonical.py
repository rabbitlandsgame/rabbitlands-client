"""Fit an authored MPFB study onto the unchanged Rabbit Lands player contract.

This authoring utility never modifies a source GLB.  MPFB's anatomical game
weights and joint-cube landmarks move its A-pose geometry to the accepted player
rest.  The output retains every existing skeleton node and inverse bind matrix.
Only ordinary static skinned geometry and capped baked maps reach the prototype.
Requires NumPy, SciPy and Pillow; Shapely 2.1 provides robust internal caps.
MPFB itself is needed only for the preceding authoring export, not by this
fitter or by the game.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
DTYPES = {5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
AXES = np.array([[1., 0., 0.], [0., 0., 1.], [0., -1., 0.]])
ALIASES = {'Root': 'root', 'head': 'Head'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Glb:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        length = struct.unpack_from('<I', raw, 12)[0]
        self.doc = json.loads(raw[20:20+length])
        self.binary = bytearray(raw[28+length:])
        self.doc.setdefault('accessors', [])
        self.doc.setdefault('bufferViews', [])
        self.doc.setdefault('materials', [])
        self.doc.setdefault('textures', [])
        self.doc.setdefault('images', [])
        self.doc.setdefault('samplers', [])

    def read(self, index):
        a = self.doc['accessors'][index]
        v = self.doc['bufferViews'][a['bufferView']]
        dtype = np.dtype(DTYPES[a['componentType']])
        n = COMPONENTS[a['type']]
        array = np.ndarray((a['count'], n), dtype=dtype, buffer=self.binary,
                           offset=v.get('byteOffset', 0)+a.get('byteOffset', 0),
                           strides=(v.get('byteStride', n*dtype.itemsize), dtype.itemsize)).copy()
        return array[:, 0] if n == 1 else array

    def blob(self, data, target=None):
        self.binary.extend(b'\0' * (-len(self.binary) % 4))
        record = {'buffer': 0, 'byteOffset': len(self.binary), 'byteLength': len(data)}
        if target:
            record['target'] = target
        self.binary.extend(data)
        self.doc['bufferViews'].append(record)
        return len(self.doc['bufferViews'])-1

    def array(self, array, kind, component, target=None):
        array = np.asarray(array, dtype=DTYPES[component])
        record = {'bufferView': self.blob(array.tobytes(), target), 'componentType': component,
                  'count': len(array), 'type': kind}
        if kind == 'VEC3' and component == 5126:
            record.update(min=array.min(0).tolist(), max=array.max(0).tolist())
        self.doc['accessors'].append(record)
        return len(self.doc['accessors'])-1

    def material(self, path, cap, name, roughness, alpha=False):
        image = Image.open(path).convert('RGBA' if alpha else 'RGB')
        image.thumbnail((cap, cap), Image.Resampling.LANCZOS)
        stream = io.BytesIO()
        image.save(stream, format='PNG', optimize=True)
        self.doc['images'].append({'name': name, 'bufferView': self.blob(stream.getvalue()), 'mimeType': 'image/png'})
        self.doc['samplers'].append({'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497})
        self.doc['textures'].append({'source': len(self.doc['images'])-1, 'sampler': len(self.doc['samplers'])-1})
        self.doc['materials'].append({'name': name, 'doubleSided': False,
            'pbrMetallicRoughness': {'baseColorTexture': {'index': len(self.doc['textures'])-1},
                                    'metallicFactor': 0., 'roughnessFactor': roughness}})
        if alpha:
            # Official MPFB high-poly eyes include a clear corneal shell.
            # Converting this atlas to RGB makes that shell an opaque blindfold.
            self.doc['materials'][-1].update(alphaMode='MASK',alphaCutoff=.5)
        return len(self.doc['materials'])-1

    def write(self, path):
        self.compact()
        self.binary.extend(b'\0' * (-len(self.binary) % 4))
        self.doc['buffers'] = [{'byteLength': len(self.binary)}]
        raw = json.dumps(self.doc, separators=(',', ':')).encode()
        raw += b' ' * (-len(raw) % 4)
        data = struct.pack('<4sII', b'glTF', 2, 28+len(raw)+len(self.binary))
        data += struct.pack('<I4s', len(raw), b'JSON') + raw
        data += struct.pack('<I4s', len(self.binary), b'BIN\0') + self.binary
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)

    def compact(self):
        """Remove superseded source geometry/maps without changing any joint node."""
        d = self.doc
        def remap(name, used):
            mapping = {old:new for new,old in enumerate(sorted(used))}
            d[name] = [d[name][old] for old in sorted(used)]
            return mapping
        meshmap = remap('meshes', {n['mesh'] for n in d['nodes'] if 'mesh' in n})
        for n in d['nodes']:
            if 'mesh' in n:
                n['mesh'] = meshmap[n['mesh']]
        mats = {p['material'] for m in d['meshes'] for p in m['primitives'] if 'material' in p}
        matmap = remap('materials', mats)
        for m in d['meshes']:
            for p in m['primitives']:
                if 'material' in p:
                    p['material'] = matmap[p['material']]
        texture_fields = []
        def scan(value, key=''):
            if isinstance(value, dict):
                if key.endswith('Texture') and 'index' in value:
                    texture_fields.append(value)
                for k,v in value.items():
                    scan(v,k)
            elif isinstance(value,list):
                for v in value:
                    scan(v,key)
        scan(d['materials'])
        texmap = remap('textures', {x['index'] for x in texture_fields})
        for x in texture_fields:
            x['index'] = texmap[x['index']]
        imgmap = remap('images', {x['source'] for x in d['textures'] if 'source' in x})
        smap = remap('samplers', {x['sampler'] for x in d['textures'] if 'sampler' in x})
        for x in d['textures']:
            if 'source' in x: x['source'] = imgmap[x['source']]
            if 'sampler' in x: x['sampler'] = smap[x['sampler']]
        access = set()
        for m in d['meshes']:
            for p in m['primitives']:
                access.update(p['attributes'].values())
                if 'indices' in p: access.add(p['indices'])
                for target in p.get('targets',[]): access.update(target.values())
        access.update(s['inverseBindMatrices'] for s in d.get('skins',[]) if 'inverseBindMatrices' in s)
        for a in d.get('animations',[]):
            for s in a['samplers']: access.update((s['input'],s['output']))
        amap = remap('accessors', access)
        for m in d['meshes']:
            for p in m['primitives']:
                p['attributes'] = {k:amap[v] for k,v in p['attributes'].items()}
                if 'indices' in p: p['indices'] = amap[p['indices']]
                for t in p.get('targets',[]):
                    for k,v in t.items(): t[k] = amap[v]
        for s in d.get('skins',[]):
            if 'inverseBindMatrices' in s: s['inverseBindMatrices'] = amap[s['inverseBindMatrices']]
        for a in d.get('animations',[]):
            for s in a['samplers']:
                s['input'],s['output'] = amap[s['input']],amap[s['output']]
        views = {a['bufferView'] for a in d['accessors'] if 'bufferView' in a}
        views.update(x['bufferView'] for x in d['images'] if 'bufferView' in x)
        vmap = {old:new for new,old in enumerate(sorted(views))}
        old_binary = self.binary
        self.binary = bytearray()
        new_views = []
        for old in sorted(views):
            view = copy.deepcopy(d['bufferViews'][old])
            start = view.get('byteOffset',0)
            self.binary.extend(b'\0' * (-len(self.binary)%4))
            view['byteOffset'] = len(self.binary)
            self.binary.extend(old_binary[start:start+view['byteLength']])
            new_views.append(view)
        d['bufferViews'] = new_views
        for a in d['accessors']:
            if 'bufferView' in a: a['bufferView'] = vmap[a['bufferView']]
        for x in d['images']:
            if 'bufferView' in x: x['bufferView'] = vmap[x['bufferView']]


def node_worlds(doc):
    nodes = doc['nodes']
    parents = {c:i for i,n in enumerate(nodes) for c in n.get('children',[])}
    cache = {}
    def world(i):
        if i in cache: return cache[i]
        n = nodes[i]
        m = np.eye(4)
        if 'matrix' in n:
            m = np.array(n['matrix']).reshape(4,4).T
        else:
            m[:3,:3] = Rotation.from_quat(n.get('rotation',[0,0,0,1])).as_matrix() @ np.diag(n.get('scale',[1,1,1]))
            m[:3,3] = n.get('translation',[0,0,0])
        cache[i] = world(parents[i])@m if i in parents else m
        return cache[i]
    return {n.get('name',''):world(i) for i,n in enumerate(nodes)}


def basis(direction, hint):
    a = direction/np.linalg.norm(direction)
    n = hint - a*np.dot(hint,a)
    if np.linalg.norm(n) < 1e-6:
        n = np.cross(a, np.array([1.,0.,0.]) if abs(a[0]) < .9 else np.array([0.,1.,0.]))
    n /= np.linalg.norm(n)
    return np.column_stack((a,n,np.cross(a,n)))


def segment_matrix(start, end, target_start, target_end, width, hint=None, target_hint=None):
    hint = np.array([0.,0.,1.]) if hint is None else hint
    target_hint = np.array([0.,0.,1.]) if target_hint is None else target_hint
    length = np.linalg.norm(end-start)
    target_length = np.linalg.norm(target_end-target_start)
    b = basis(end-start,hint)
    t = basis(target_end-target_start,target_hint)
    linear = t @ np.diag([target_length/max(length,1e-6),width,width]) @ b.T
    result = np.eye(4)
    result[:3,:3] = linear
    result[:3,3] = target_start-linear@start
    return result


def fit_geometry(data, meta, source, rig_path, weights_path):
    """Authoring-only linear blend of measured anatomical segment maps."""
    d = source.doc
    worlds = node_worlds(d)
    skin = d['skins'][0]
    names = [d['nodes'][i]['name'] for i in skin['joints']]
    name_to_bind = {n:i for i,n in enumerate(names)}
    rig = json.loads(Path(rig_path).read_text())
    weights = json.loads(Path(weights_path).read_text())['weights']
    landmarks = {k:AXES@np.asarray(v) for k,v in meta['joint_landmarks'].items()}
    def point(endpoint):
        if endpoint.get('cube_name') in landmarks:
            return landmarks[endpoint['cube_name']]
        return AXES@np.array(endpoint['default_position'])
    native = {}
    for n in d['nodes']:
        if n.get('name') == 'eyes':
            p = d['meshes'][n['mesh']]['primitives'][0]
            vertices = source.read(p['attributes']['POSITION'])
            ids = np.unique(source.read(p['indices']))
            native['eye_center'] = (vertices[ids].min(0)+vertices[ids].max(0))*.5
        elif n.get('name') == 'scalp':
            p = d['meshes'][n['mesh']]['primitives'][0]
            ids = np.unique(source.read(p['indices']))
            native['top'] = source.read(p['attributes']['POSITION'])[ids,1].max()
    body = np.asarray(data['body_vertices'],float)@AXES.T
    eyes = np.asarray(data['eye_vertices'],float)@AXES.T
    height_scale = native['top']/body[:,1].max()
    eye_center = (eyes.min(0)+eyes.max(0))*.5
    head_matrix = np.eye(4)
    head_matrix[:3,:3] *= height_scale
    head_matrix[:3,3] = native['eye_center']-eye_center*height_scale
    transforms = {}
    thumb = ['thumb','index','middle','ring','pinky']
    for key,bone in rig.items():
        canonical = ALIASES.get(key,key)
        if canonical not in worlds: continue
        if canonical == 'Head':
            transforms[key] = head_matrix
            continue
        start,end = point(bone['head']),point(bone['tail'])
        target_start = worlds[canonical][:3,3]
        # A stock terminal segment maps to the current corresponding leaf.
        children = [ALIASES.get(k,k) for k,v in rig.items() if v.get('parent') == key and ALIASES.get(k,k) in worlds]
        preferred = {'root':'pelvis','pelvis':'spine_01','spine_01':'spine_02','spine_02':'spine_03',
                     'spine_03':'neck_01','neck_01':'Head','hand_l':'middle_01_l','hand_r':'middle_01_r',
                     'foot_l':'ball_l','foot_r':'ball_r'}
        target_child = preferred.get(canonical)
        if target_child is None:
            target_child = children[0] if children else canonical.replace('_03_','_04_leaf_')
        if canonical.startswith('ball_'): target_child = canonical.replace('ball_','ball_leaf_')
        if canonical.startswith('hand_'):
            # MPFB's hand tail is a short orientation helper, not the end of
            # its palm. Mapping that tiny span to a full palm triples the hand.
            end = point(rig['middle_01_'+canonical.rsplit('_',1)[1]]['head'])
        if target_child in worlds:
            target_end = worlds[target_child][:3,3]
        else:
            target_end = target_start + np.array([0.,.05,0.])
        width = height_scale
        hint = target_hint = None
        if canonical.startswith(('hand_','index_','middle_','ring_','pinky_','thumb_')):
            side = canonical.rsplit('_',1)[1]
            wrist = landmarks['joint-'+side+'-hand']
            a = landmarks['joint-'+side+'-finger-2-1']-wrist
            b = landmarks['joint-'+side+'-finger-5-1']-wrist
            hint = np.cross(a,b)
            target_wrist = worlds['hand_'+side][:3,3]
            target_hint = np.cross(worlds['index_01_'+side][:3,3]-target_wrist,
                                   worlds['pinky_01_'+side][:3,3]-target_wrist)
        transforms[key] = segment_matrix(start,end,target_start,target_end,width,hint,target_hint)
    # Neck upper endpoint must meet the independently eye-aligned head volume.
    transforms['neck_01'] = segment_matrix(point(rig['neck_01']['head']),point(rig['neck_01']['tail']),
        worlds['neck_01'][:3,3],head_matrix[:3,:3]@point(rig['neck_01']['tail'])+head_matrix[:3,3],height_scale)
    original_count = int(np.max(data['body_source_indices']))+1
    dense = np.zeros((original_count,len(names)),float)
    fitted = np.zeros_like(body)
    totals = np.zeros(len(body),float)
    source_ids = np.asarray(data['body_source_indices'],int)
    idmap = {int(v):i for i,v in enumerate(source_ids)}
    for key,items in weights.items():
        canonical = ALIASES.get(key,key)
        if canonical not in name_to_bind or key not in transforms: continue
        matrix = transforms[key]
        for original_id,w in items:
            if original_id not in idmap: continue
            i = idmap[original_id]
            dense[original_id,name_to_bind[canonical]] += w
            fitted[i] += (matrix[:3,:3]@body[i]+matrix[:3,3])*w
            totals[i] += w
    if np.any(totals < .1):
        raise ValueError('MPFB anatomical weight coverage missing for '+str(np.flatnonzero(totals<.1).tolist()[:20]))
    fitted /= totals[:,None]
    # Keep bare soles inside the existing boots' floor envelope. Only the
    # lowest 5 cm are compressed; the ankle/pivots and all native clothing stay
    # exact, and the model's floor normalization must not lift the old boots.
    sole_min = float(fitted[:,1].min())
    if sole_min < 0.:
        low = fitted[:,1] < .05
        fitted[low,1] = (fitted[low,1]-sole_min) * (.05/(.05-sole_min))
    dense = dense[source_ids]
    order = np.argsort(dense,axis=1)[:,-4:][:,::-1]
    kept = np.take_along_axis(dense,order,axis=1)
    pruned = 1-kept.sum(1)/dense.sum(1)
    kept /= kept.sum(1)[:,None]
    eye_fitted = eyes@head_matrix[:3,:3].T+head_matrix[:3,3]
    eye_joints = np.full((len(eyes),4),name_to_bind['Head'],np.uint16)
    eye_weights = np.zeros((len(eyes),4),np.float32);eye_weights[:,0]=1
    head_ids = dense[:,name_to_bind['Head']]>.95
    inverse_head = np.linalg.inv(worlds['Head'])
    def head_point(value):
        return (inverse_head[:3,:3]@value+inverse_head[:3,3]).tolist()
    eye_sides = [eye_fitted[eyes[:,0]<0],eye_fitted[eyes[:,0]>0]]
    eye_centers = [(v.min(0)+v.max(0))*.5 for v in eye_sides]
    lip_ids = [idmap[int(i)] for i in meta['body_groups']['lips'] if int(i) in idmap]
    # The stock joint-mouth cube is an interior rig helper several centimetres
    # above the painted vermilion; the actual lip ownership group is authoritative.
    mouth = fitted[lip_ids].mean(0)
    local_lips = np.array([head_point(v) for v in fitted[lip_ids]])
    local_eye = np.array([head_point(c) for c in eye_centers])
    report = {'head_matrix':head_matrix.tolist(), 'height_scale':height_scale,
              'head_bounds':[fitted[head_ids].min(0).tolist(),fitted[head_ids].max(0).tolist()],
              'eye_bounds':[eye_fitted.min(0).tolist(),eye_fitted.max(0).tolist()],
              'anatomical_full_fit_body_bounds':[fitted.min(0).tolist(),fitted.max(0).tolist()],
              'weight_sum_max_error':float(np.abs(kept.sum(1)-1).max()),
              'max_pruned_weight':float(pruned.max()), 'mean_pruned_weight':float(pruned.mean()),
              'joint_count':len(names), 'source_landmarks':len(landmarks),
              'sole_compression_from_min_y':sole_min,
              'face_frame_head_local':{'eye_left':local_eye[0].tolist(),'eye_right':local_eye[1].tolist(),
                  'eye_y':float(local_eye[:,1].mean()),'eye_z':float(local_eye[:,2].mean()),
                  'mouth':head_point(mouth),'mouth_y':float(head_point(mouth)[1]),
                  'mouth_bounds':[local_lips.min(0).tolist(),local_lips.max(0).tolist()],
                  'scale':float(np.ptp(eye_fitted[:,0])/.10)},
              'fit_method':'MPFB game-engine anatomical weights; measured joint-segment affine maps; eye-anchored head',
              'finger_ownership':'direct source anatomical groups; no nearest-neighbour transfer'}
    return fitted,order.astype(np.uint16),kept.astype(np.float32),eye_fitted,eye_joints,eye_weights,report


def normals(vertices, triangles):
    output = np.zeros_like(vertices)
    faces = np.cross(vertices[triangles[:,1]]-vertices[triangles[:,0]],vertices[triangles[:,2]]-vertices[triangles[:,0]])
    for corner in range(3): np.add.at(output,triangles[:,corner],faces)
    output /= np.maximum(np.linalg.norm(output,axis=1)[:,None],1e-12)
    return output


def primitive(glb, vertices, triangles, uv, joints, weights, material, authored_normals=None):
    """Split UV seams only, retaining smooth normals from the connected mesh."""
    normal = normals(vertices,triangles) if authored_normals is None else authored_normals
    flat = triangles.reshape(-1)
    flat_uv = np.asarray(uv).reshape(-1,2).copy()
    flat_uv[:,1] = 1-flat_uv[:,1]  # Blender UV origin -> glTF texture convention.
    keys = np.column_stack((flat, np.round(flat_uv*1e7).astype(np.int64)))
    unique,first,inverse = np.unique(keys,axis=0,return_index=True,return_inverse=True)
    ids = flat[first]
    attributes = {'POSITION':glb.array(vertices[ids],'VEC3',5126,34962),
                  'NORMAL':glb.array(normal[ids],'VEC3',5126,34962),
                  'TEXCOORD_0':glb.array(flat_uv[first],'VEC2',5126,34962),
                  'JOINTS_0':glb.array(joints[ids],'VEC4',5123,34962),
                  'WEIGHTS_0':glb.array(weights[ids],'VEC4',5126,34962)}
    return {'attributes':attributes,'indices':glb.array(inverse,'SCALAR',5125,34963),'material':material,'mode':4}


def dense_weights(joints, weights, count=77):
    result = np.zeros((len(joints),count))
    for i in range(joints.shape[1]): np.add.at(result,(np.arange(len(joints)),joints[:,i]),weights[:,i])
    return result


def sparse_weights(weights):
    order = np.argsort(weights,axis=1)[:,-4:][:,::-1]
    kept = np.take_along_axis(weights,order,axis=1)
    kept /= np.maximum(kept.sum(1)[:,None],1e-12)
    return order.astype(np.uint16),kept.astype(np.float32)


def clipped(vertices, triangles, uv, weights, plane, above, authored_normals=None, eligible=None, track_origins=False):
    """Exact triangle/UV/weight clipping; all retained source vertices stay exact."""
    all_vertices=[];all_weights=[];all_normals=[];out_tri=[];out_uv=[];mapping={};origins=[]
    def inside(v): return v[0][1]>=plane if above else v[0][1]<=plane
    def append(v):
        pos,weight,tex,normal,key=v
        if key not in mapping:
            mapping[key]=len(all_vertices);all_vertices.append(pos);all_weights.append(weight);all_normals.append(normal)
            origins.append(int(key[1]) if key[0]=='v' else -1)
        return mapping[key]
    source_normals = normals(vertices,triangles) if authored_normals is None else authored_normals
    for number,(tri,tuv) in enumerate(zip(triangles,uv)):
        polygon=[(vertices[i],weights[i],tex,source_normals[i],('v',int(i))) for i,tex in zip(tri,tuv)]
        result=[]
        if eligible is not None and not eligible[number]:
            result=polygon
        for k,b in enumerate(polygon):
            if eligible is not None and not eligible[number]: break
            a=polygon[k-1];ain=inside(a);bin=inside(b)
            if ain != bin:
                t=(plane-a[0][1])/(b[0][1]-a[0][1])
                n=a[3]*(1-t)+b[3]*t;n/=max(np.linalg.norm(n),1e-12)
                key=('e',)+tuple(sorted((int(tri[k-1]),int(tri[k]))))
                result.append((a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t,a[2]*(1-t)+b[2]*t,n,key))
            if bin: result.append(b)
        for i in range(1,len(result)-1):
            corners=[result[0],result[i],result[i+1]]
            out_tri.append([append(v) for v in corners]);out_uv.append([v[2] for v in corners])
    result={'vertices':np.array(all_vertices),'triangles':np.array(out_tri,dtype=int),
            'uv':np.array(out_uv),'weights':np.array(all_weights),'normals':np.array(all_normals)}
    if track_origins:result['origins']=np.asarray(origins,dtype=int)
    return result


def neck_loop(mesh,plane,max_x=.14):
    """Find one welded, closed geometric boundary; arms are never neck samples."""
    vertices=mesh['vertices'];weld={};representatives=[];ids=[]
    for index,v in enumerate(vertices):
        key=tuple(np.round(v*1e6).astype(np.int64))
        if key not in weld: weld[key]=len(representatives);representatives.append(index)
        ids.append(weld[key])
    ids=np.asarray(ids);counts={}
    for tri in ids[mesh['triangles']]:
        for a,b in zip(tri,np.roll(tri,-1)):
            if a==b: continue
            edge=tuple(sorted((int(a),int(b))));counts[edge]=counts.get(edge,0)+1
    adjacency={}
    for (a,b),count in counts.items():
        pa,pb=vertices[representatives[a]],vertices[representatives[b]]
        if count!=1 or max(abs(pa[1]-plane),abs(pb[1]-plane))>1e-6: continue
        if max(abs(pa[0]),abs(pb[0]))>max_x: continue
        adjacency.setdefault(a,[]).append(b);adjacency.setdefault(b,[]).append(a)
    if not adjacency or any(len(v)!=2 for v in adjacency.values()):
        raise ValueError('Neck boundary is not a single degree-two loop: '+str({k:(len(v),vertices[representatives[k]].tolist()) for k,v in adjacency.items() if len(v)!=2}))
    start=min(adjacency);order=[start];previous=None;current=start
    while True:
        following=next(v for v in adjacency[current] if v!=previous)
        if following==start: break
        if following in order: raise ValueError('Self-intersecting neck graph')
        order.append(following);previous,current=current,following
    if len(order)!=len(adjacency): raise ValueError('Multiple neck boundary loops')
    return np.asarray([representatives[i] for i in order],dtype=int)


def head_component(mesh):
    """A sloped cut can leave isolated shoulder tips; keep the actual head."""
    parent=np.arange(len(mesh['vertices']))
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]];i=parent[i]
        return i
    for tri in mesh['triangles']:
        a=find(int(tri[0]))
        for value in tri[1:]: parent[find(int(value))]=a
    owner=find(int(np.argmax(mesh['vertices'][:,1])))
    used=np.asarray([find(i)==owner for i in range(len(parent))])
    kept=np.all(used[mesh['triangles']],axis=1)
    ids=np.flatnonzero(used);mapping=np.full(len(used),-1,int);mapping[ids]=np.arange(len(ids))
    result={k:(mapping[v[kept]] if k=='triangles' else v[kept] if k=='uv' else v[ids]) for k,v in mesh.items()}
    return result


def relax_neck_chart(original, fitted, triangles, head_weight, ring, cut=1.50):
    """Solve the neck's full chart positions with its rim and face pinned.

    The sloped MPFB boundary includes shoulder skin and is not a radial neck
    section. Scaling that section only in X/Z leaves folded chart heights below
    the ears. A uniform harmonic XYZ solve removes those folds without moving
    the canonical seam or any protected face vertex. This is an offline solve.
    """
    unknown=(original[:,1]<cut+.05)|(head_weight<.95)
    unknown[ring]=False
    ids=np.flatnonzero(unknown)
    if not len(ids): return fitted.copy(),unknown
    lookup=np.full(len(original),-1,dtype=int);lookup[ids]=np.arange(len(ids))
    adjacency=[set() for _ in range(len(original))]
    for tri in triangles:
        for a,b in zip(tri,np.roll(tri,-1)):
            adjacency[a].add(int(b));adjacency[b].add(int(a))
    rows=[];columns=[];values=[];rhs=np.zeros((len(ids),fitted.shape[1]))
    for row,index in enumerate(ids):
        if not adjacency[index]: raise ValueError('Isolated neck relaxation vertex')
        rows.append(row);columns.append(row);values.append(len(adjacency[index]))
        for other in adjacency[index]:
            if unknown[other]: rows.append(row);columns.append(lookup[other]);values.append(-1)
            else: rhs[row]+=fitted[other]
    system=coo_matrix((values,(rows,columns)),shape=(len(ids),len(ids))).tocsr()
    solved=np.asarray(spsolve(system,rhs)).reshape(rhs.shape)
    if not np.isfinite(solved).all(): raise ValueError('Neck relaxation is not finite')
    output=fitted.copy();output[ids]=solved
    return output,unknown


def legacy_hybrid_head(source, vertices, triangles, uv, joints, weights, cut=1.50, slope=.6, relax_neck=True):
    """MPFB head/neck with a weight-matched quarter-mm bridge to the accepted body.

    The full-body fit remains an experimental export mode.  Shared canonical
    garments require the accepted underlying body envelope; borrowing an
    unrelated body's skin weights alone cannot preserve garment clearance.
    """
    d=source.doc;skin=d['skins'][0];names=[d['nodes'][i]['name'] for i in skin['joints']]
    dw=dense_weights(joints,weights,len(names))
    headness=dw[:,names.index('Head')]+dw[:,names.index('neck_01')]
    owned=np.ones(len(triangles),dtype=bool)
    # Existing shirt geometry owns the back of the neck below its collar.
    # A horizontal cut there is an OPEN arc, not a closed neck. Use the actual
    # sloped neckline chart y' = y + .6*z, low at the throat, high at the rear.
    # This keeps the MPFB chin whole while making a closed source boundary.
    chart_vertices=vertices.copy();chart_vertices[:,1]+=slope*chart_vertices[:,2]
    head=head_component(clipped(chart_vertices,triangles[owned],uv[owned],dw,cut,True))
    original_head_chart=head['vertices'].copy()
    original_node=next(n for n in d['nodes'] if n.get('name')=='body')
    p=d['meshes'][original_node['mesh']]['primitives'][0]
    attrs=p['attributes'];original_vertices=source.read(attrs['POSITION'])
    original_triangles=source.read(p['indices']).reshape(-1,3)
    original_uv=source.read(attrs['TEXCOORD_0'])
    # Stored source UV is already glTF, while primitive() accepts Blender UV.
    original_uv=original_uv.copy();original_uv[:,1]=1-original_uv[:,1]
    original_weights=dense_weights(source.read(attrs['JOINTS_0']),source.read(attrs['WEIGHTS_0']),len(names))
    native_headness=original_weights[:,names.index('Head')]+original_weights[:,names.index('neck_01')]
    eligible=(np.max(np.abs(original_vertices[original_triangles,0]),axis=1)<.125) \
        & (native_headness[original_triangles].mean(1)>.05)
    original_chart=original_vertices.copy();original_chart[:,1]+=slope*original_chart[:,2]
    lower=clipped(original_chart,original_triangles,original_uv[original_triangles],original_weights,
                  cut,False,source.read(attrs['NORMAL']),eligible=eligible)
    native_ring=neck_loop(lower,cut)
    new_ring=neck_loop(head,cut,max_x=1.0)
    if len(native_ring)<8 or len(new_ring)<8:
        raise ValueError(f'Neck seam has insufficient boundary samples: {len(native_ring)}, {len(new_ring)}')
    target_center=lower['vertices'][native_ring][:,[0,2]].mean(0)
    source_center=head['vertices'][new_ring][:,[0,2]].mean(0)
    def angles(points,center): return np.mod(np.arctan2(points[:,0]-center[0],points[:,1]-center[1]),2*np.pi)
    native_angles=angles(lower['vertices'][native_ring][:,[0,2]],target_center)
    new_angles=angles(head['vertices'][new_ring][:,[0,2]],source_center)
    def interpolate(theta, sample_angles, values):
        return np.column_stack([np.interp(theta,sample_angles,values[:,k],period=2*np.pi) for k in range(values.shape[1])])
    # Keep the authored ownership field: the canonical weight transfer below
    # mutates head['weights'], while relaxation must use the original domain.
    head_weight=head['weights'][:,names.index('Head')].copy()
    near=np.flatnonzero((head['vertices'][:,1]<cut+.05)|(head_weight<.95))
    a=angles(head['vertices'][near][:,[0,2]],source_center)
    target=interpolate(a,native_angles,lower['vertices'][native_ring][:,[0,2]])
    current=interpolate(a,new_angles,head['vertices'][new_ring][:,[0,2]])
    phase=np.clip((head['vertices'][near,1]-cut)/.05,0,1)
    fade=1-phase*phase*(3-2*phase)
    ownership=np.clip((head_weight[near]-.30)/.65,0,1)
    fade=np.maximum(fade,1-ownership*ownership*(3-2*ownership))
    relative=head['vertices'][near][:,[0,2]]-source_center
    radial=np.linalg.norm(relative,axis=1)/np.maximum(np.linalg.norm(current-source_center,axis=1),1e-8)
    desired=target_center+(target-target_center)*radial[:,None]
    neck_delta=(desired-head['vertices'][near][:,[0,2]])*fade[:,None]
    head['vertices'][np.ix_(near,[0,2])] += neck_delta
    canonical_weights=interpolate(a,native_angles,lower['weights'][native_ring])
    head['weights'][near] = head['weights'][near]*(1-fade[:,None])+canonical_weights*fade[:,None]
    head['vertices'][near,1] += .00025*fade
    # Keep the rim exactly where the canonical bridge expects it, while solving
    # shoulder-derived interior positions rather than preserving folded heights.
    relaxed=np.zeros(len(head['vertices']),dtype=bool)
    if relax_neck:
        head['vertices'],relaxed=relax_neck_chart(original_head_chart,head['vertices'],
            head['triangles'],head_weight,new_ring,cut)
    # The short bridge closes differing tessellation of the two boundary rings.
    first_uv={}
    for tri,tex in zip(head['triangles'],head['uv']):
        for i,t in zip(tri,tex): first_uv.setdefault(int(i),t)
    top_order=new_ring[np.argsort(new_angles)]
    bottom_order=native_ring[np.argsort(native_angles)]
    top_angles=np.sort(new_angles);bottom_angles=np.sort(native_angles)
    bottom_ids=[];bottom_uv=[]
    for index,theta in zip(bottom_order,bottom_angles):
        bottom_ids.append(len(head['vertices'])+len(bottom_ids))
        closest=int(top_order[np.argmin(np.abs(np.angle(np.exp(1j*(top_angles-theta)))) )])
        bottom_uv.append(first_uv[closest])
    bottom_start=len(head['vertices'])
    head['vertices']=np.concatenate((head['vertices'],lower['vertices'][bottom_order]))
    head['weights']=np.concatenate((head['weights'],lower['weights'][bottom_order]))
    head['normals']=np.concatenate((head['normals'],lower['normals'][bottom_order]))
    added_tri=[];added_uv=[];i=j=0
    for _ in range(len(top_order)+len(bottom_order)):
        ti=int(top_order[i%len(top_order)]);bj=int(bottom_ids[j%len(bottom_order)])
        next_top=top_angles[(i+1)%len(top_order)]+(2*np.pi if i+1>=len(top_order) else 0)
        next_bottom=bottom_angles[(j+1)%len(bottom_order)]+(2*np.pi if j+1>=len(bottom_order) else 0)
        if next_top < next_bottom:
            ni=int(top_order[(i+1)%len(top_order)]);tri=[ti,bj,ni];tex=[first_uv[ti],bottom_uv[j%len(bottom_order)],first_uv[ni]];i+=1
        else:
            nj=int(bottom_ids[(j+1)%len(bottom_order)]);tri=[ti,bj,nj];tex=[first_uv[ti],bottom_uv[j%len(bottom_order)],bottom_uv[(j+1)%len(bottom_order)]];j+=1
        points=head['vertices'][tri];face=np.cross(points[1]-points[0],points[2]-points[0]);center=points.mean(0)
        radial=np.array([center[0]-target_center[0],0.,center[2]-target_center[1]])
        if np.dot(face,radial)<0: tri[1],tri[2]=tri[2],tri[1];tex[1],tex[2]=tex[2],tex[1]
        added_tri.append(tri);added_uv.append(tex)
    head['triangles']=np.concatenate((head['triangles'],added_tri))
    head['uv']=np.concatenate((head['uv'],added_uv))
    # Recompute only MPFB/bridge normals. The accepted lower body's authored
    # normals and all its vertices below the clipping plane remain untouched.
    normal_band=np.flatnonzero(head['vertices'][:bottom_start,1]<cut+.01025)
    normal_height=head['vertices'][normal_band,1]-cut
    normal_theta=angles(head['vertices'][normal_band][:,[0,2]],target_center)
    normal_target=interpolate(normal_theta,native_angles,lower['normals'][native_ring])
    normal_target/=np.maximum(np.linalg.norm(normal_target,axis=1)[:,None],1e-12)
    normal_phase=np.clip((normal_height-.00025)/.01,0,1)
    normal_gain=1-normal_phase*normal_phase*(3-2*normal_phase)
    head['vertices'][:,1]-=slope*head['vertices'][:,2]
    lower['vertices'][:,1]-=slope*lower['vertices'][:,2]
    head['normals']=normals(head['vertices'],head['triangles'])
    geometric_normals=head['normals'].copy()
    # A matched skin/position seam also needs the same shading frame. Reusing
    # the recomputed bridge normal would create a transverse specular crease.
    # Preserve each bottom vertex's exact corresponding native normal; fade
    # the upper centimetre into that field, leaving the face and ears untouched.
    head['normals'][normal_band]=head['normals'][normal_band]*(1-normal_gain[:,None])+normal_target*normal_gain[:,None]
    head['normals'][normal_band]/=np.maximum(np.linalg.norm(head['normals'][normal_band],axis=1)[:,None],1e-12)
    head['normals'][bottom_start:]=lower['normals'][bottom_order]
    normal_dot=np.sum(geometric_normals*head['normals'],axis=1)
    normal_dot/=np.maximum(np.linalg.norm(geometric_normals,axis=1)*np.linalg.norm(head['normals'],axis=1),1e-12)
    normal_change=float(np.degrees(np.arccos(np.clip(normal_dot,-1,1))).max())
    report={'mode':'hybrid','neck_cut_y':cut,'neck_plane':'y + %.3f*z = %.3f'%(slope,cut),'neck_bridge_height':.00025,
            'seam_topology':'one welded degree-two closed boundary on each side',
            'neck_warp_max_m':float(np.linalg.norm(neck_delta,axis=1).max()),
            'neck_relaxation':{'method':'harmonic absolute XYZ in sloped chart' if relax_neck else 'legacy radial only',
                               'interior_vertices':int(relaxed.sum()),'canonical_rim_and_protected_head_exact':True},
            'normal_stitch':{'native_corresponding_bottom_normals_exact':bool(np.array_equal(head['normals'][bottom_start:],lower['normals'][bottom_order])),
                             'blended_upper_band_m':.01,'upper_band_vertices':len(normal_band),
                             'maximum_authored_normal_change_degrees':normal_change,
                             'geometry_indices_uv_weights_unchanged':True},
            'canonical_boundary_vertices':len(native_ring),'mpfb_boundary_vertices':len(new_ring),
            'canonical_lower_triangles':len(lower['triangles']),'mpfb_head_triangles':len(head['triangles']),
            'canonical_original_material':p['material'],
            'canonical_body_below_neck':'unchanged source positions, skin ownership, UV and authored normals; only plane intersections added'}
    return head,lower,report


def intrinsic_ring(vertices, ring, center):
    """Clockwise graph order, anchored at the physical anterior midline."""
    order=ring.copy();points=vertices[order][:,[0,2]]
    area=np.sum(points[:,0]*np.roll(points[:,1],-1)-np.roll(points[:,0],-1)*points[:,1])
    if area>0: order=order[::-1]
    points=vertices[order][:,[0,2]]
    theta=np.abs(np.arctan2(points[:,0]-center[0],points[:,1]-center[1]))
    anchor=int(np.argmin(theta));order=np.roll(order,-anchor)
    points=vertices[order]
    lengths=np.linalg.norm(np.roll(points,-1,axis=0)-points,axis=1)
    if np.any(lengths<1e-9): raise ValueError('Repeated intrinsic boundary point')
    fractions=np.r_[0.,np.cumsum(lengths[:-1])]/lengths.sum()
    return order,fractions


def sample_ring(fractions, values, queries):
    indices=np.searchsorted(fractions,queries,side='right')-1
    following=(indices+1)%len(fractions)
    start=fractions[indices];end=np.r_[fractions[1:],1.][indices]
    blend=((queries-start)/(end-start))[:,None]
    return values[indices]*(1-blend)+values[following]*blend


def welded_vertices(vertices, tolerance=1e-6):
    parent=np.arange(len(vertices))
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]];i=parent[i]
        return i
    for a,b in cKDTree(vertices).query_pairs(tolerance,output_type='ndarray'):
        a,b=find(int(a)),find(int(b))
        if a!=b:parent[max(a,b)]=min(a,b)
    return np.asarray([find(i) for i in range(len(vertices))])


def plane_boundary_loops(mesh, plane):
    vertices=mesh['vertices'];weld=welded_vertices(vertices);edges={}
    for tri in weld[mesh['triangles']]:
        for a,b in zip(tri,np.roll(tri,-1)):
            if a==b:continue
            edge=tuple(sorted((int(a),int(b))));edges[edge]=edges.get(edge,0)+1
    graph={}
    for (a,b),count in edges.items():
        if count==1 and max(abs(vertices[a,1]-plane),abs(vertices[b,1]-plane))<1e-6:
            graph.setdefault(a,[]).append(b);graph.setdefault(b,[]).append(a)
    if any(len(neighbors)!=2 for neighbors in graph.values()):raise ValueError('Open cut boundary')
    loops=[];remaining=set(graph)
    while remaining:
        start=min(remaining);order=[start];previous=None;current=start
        while True:
            following=next(value for value in graph[current] if value!=previous)
            if following==start:break
            if following in order:raise ValueError('Repeated cut boundary')
            order.append(following);previous,current=current,following
        remaining.difference_update(order);loops.append(np.asarray(order,dtype=int))
    return loops,weld


def free_neck_uv(uv, size=(1024,1024), gutter=4):
    width,height=size;mask=Image.new('L',size,0);draw=ImageDraw.Draw(mask)
    for triangle in uv:draw.polygon([(float(p[0])*width,float(p[1])*height) for p in triangle],fill=255)
    occupied=np.asarray(mask.filter(ImageFilter.MaxFilter(gutter*2+1)))>0
    occupied[:gutter]=True;occupied[-gutter:]=True;occupied[:,:gutter]=True;occupied[:,-gutter:]=True
    integral=np.pad(occupied.astype(np.int32),((1,0),(1,0))).cumsum(0).cumsum(1)
    for w,h in [(256,256),(256,192),(192,192),(192,128),(128,128),(128,96),(96,96),(96,64),(64,64)]:
        if w>width or h>height:continue
        sums=integral[h:,w:]-integral[:-h,w:]-integral[h:,:-w]+integral[:-h,:-w]
        valid=np.argwhere(sums==0)
        if len(valid):
            y,x=map(int,valid[0]);tube=[(x+.5)/width,(y+.5)/height,(x+w-.5)/width,(y+h-16.5)/height]
            cap=[(x+4.5)/width,(y+h-4.5)/height]
            return {'pixels':[x,y,w,h],'texture_size':list(size),'gutter_pixels':gutter,
                    'tube_rectangle':tube,'cap_sample':cap,'direction':'glTF u=clockwise anterior-anchored arc; v=top to bottom'}
    raise ValueError('No unused neck atlas rectangle with four-pixel retained-face gutter')


def planar_cap(vertices, order):
    """Ear clipping of a clockwise planar loop, with a downward-facing cap."""
    try:
        from shapely import Polygon, constrained_delaunay_triangles, is_valid_reason
    except ImportError:
        Polygon=None
    if Polygon is not None:
        points=vertices[order][:,[0,2]]
        polygon=Polygon(points)
        if not polygon.is_valid:raise ValueError('Invalid internal neck cut: '+is_valid_reason(polygon))
        result=[]
        for triangle in constrained_delaunay_triangles(polygon).geoms:
            corners=np.asarray(triangle.exterior.coords)[:3]
            indices=[]
            for point in corners:
                distances=np.linalg.norm(points-point,axis=1);index=int(np.argmin(distances))
                if distances[index]>1e-9:raise ValueError('Cap triangulation inserted an untracked point')
                indices.append(int(order[index]))
            a,b,c=vertices[indices][:,[0,2]]
            if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<0:indices[1],indices[2]=indices[2],indices[1]
            result.append(indices)
        edges={(a,b) for tri in result for a,b in zip(tri,np.roll(tri,-1))}
        if any((int(b),int(a)) not in edges for a,b in zip(order,np.roll(order,-1))):
            raise ValueError('Cap triangulation lost a constrained boundary edge')
        return result
    remaining=list(map(int,order));result=[]
    def cross(a,b):return a[0]*b[1]-a[1]*b[0]
    while len(remaining)>3:
        found=False
        for i,current in enumerate(remaining):
            previous,following=remaining[i-1],remaining[(i+1)%len(remaining)]
            a,b,c=vertices[[previous,current,following]][:,[0,2]]
            if cross(b-a,c-b)>=-1e-13:continue
            blocked=False
            for other in remaining:
                if other in (previous,current,following):continue
                point=vertices[other,[0,2]]
                if max(cross(b-a,point-a),cross(c-b,point-b),cross(a-c,point-c))<=1e-13:
                    blocked=True;break
            if blocked:continue
            result.append([previous,following,current]);remaining.pop(i);found=True;break
        if not found:raise ValueError('Cannot triangulate internal neck loop without overlaps')
    a,b,c=vertices[remaining][:,[0,2]]
    if abs(cross(b-a,c-a))<1e-13:raise ValueError('Degenerate final internal cap triangle')
    result.append([remaining[0],remaining[2],remaining[1]])
    return result


def structured_neck_loft(source_head, native_body, top_cut=1.55, bottom_cut=1.50, slope=.6,
                         sections=4, samples=96, atlas_size=(1024,1024)):
    """Retain the complete upper head and replace shoulder-derived neck skin.

    UVs use glTF image coordinates. All retained original P/N/J/W/UV values are
    preserved; the new annulus is a direct longitudinal loft, never a minimal
    surface. Internal cut loops are retained and closed with planar caps.
    """
    chart=np.asarray(source_head['vertices'],float).copy();chart[:,1]+=slope*chart[:,2]
    upper=clipped(chart,source_head['triangles'],source_head['uv'],source_head['weights'],
                  top_cut,True,source_head['normals'],track_origins=True)
    loops,weld=plane_boundary_loops(upper,top_cut)
    if not loops:raise ValueError('True-neck trim has no closed boundary')
    def area(ring):
        points=upper['vertices'][ring][:,[0,2]]
        return abs(np.sum(points[:,0]*np.roll(points[:,1],-1)-np.roll(points[:,0],-1)*points[:,1]))
    outer=max(loops,key=area);center=upper['vertices'][outer][:,[0,2]].mean(0)
    top,top_s=intrinsic_ring(upper['vertices'],outer,center)
    native_chart=np.asarray(native_body['vertices'],float).copy();native_chart[:,1]+=slope*native_chart[:,2]
    native_loops,_=plane_boundary_loops({**native_body,'vertices':native_chart},bottom_cut)
    if len(native_loops)!=1:raise ValueError('Canonical body must expose one closed neck rim')
    bottom,bottom_s=intrinsic_ring(native_chart,native_loops[0],native_chart[native_loops[0]][:,[0,2]].mean(0))
    # Snap only newly inserted UV-seam cut copies to one geometric sample.
    boundary_ids=set(int(weld[i]) for loop in loops for i in loop)
    for i,owner in enumerate(weld):
        if int(owner) in boundary_ids and upper['origins'][i]<0:
            for key in ['vertices','normals','weights']:upper[key][i]=upper[key][owner]
    upper['vertices'][:,1]-=slope*upper['vertices'][:,2]
    retained=upper['origins']>=0
    upper['vertices'][retained]=source_head['vertices'][upper['origins'][retained]]
    upper['normals'][retained]=source_head['normals'][upper['origins'][retained]]
    uv_patch=free_neck_uv(upper['uv'],atlas_size)
    u0,v0,u1,v1=uv_patch['tube_rectangle']
    first_uv={}
    for tri,tex in zip(upper['triangles'],upper['uv']):
        for index,value in zip(tri,tex):first_uv.setdefault(int(index),value)
    vertices=list(upper['vertices']);weights=list(upper['weights']);normals_out=list(upper['normals'])
    origins=list(upper['origins']);roles=['retained' if value>=0 else 'cut' for value in origins]
    faces=list(upper['triangles']);texcoords=list(upper['uv']);face_roles=['retained']*len(faces)
    rings=[]
    start=len(vertices)
    for index in bottom:
        vertices.append(np.asarray(native_body['vertices'][index],float));weights.append(native_body['weights'][index]);normals_out.append(native_body['normals'][index]);origins.append(-1);roles.append('canonical_rim')
    rings.append((np.arange(start,len(vertices)),bottom_s,0.))
    query=np.arange(samples)/samples
    top_points=sample_ring(top_s,upper['vertices'][top],query)
    lower_points=sample_ring(bottom_s,native_body['vertices'][bottom],query)
    top_weights=sample_ring(top_s,upper['weights'][top],query)
    lower_weights=sample_ring(bottom_s,native_body['weights'][bottom],query)
    for t in np.linspace(0,1,sections+2)[1:-1]:
        start=len(vertices)
        vertices.extend(lower_points*(1-t)+top_points*t)
        weights.extend(lower_weights*(1-t)+top_weights*t)
        normals_out.extend(np.zeros((samples,3)));origins.extend([-1]*samples);roles.extend(['loft']*samples)
        rings.append((np.arange(start,len(vertices)),query,float(t)))
    rings.append((top,top_s,1.))
    for (low,low_s,low_t),(high,high_s,high_t) in zip(rings,rings[1:]):
        i=j=0
        for _ in range(len(high)+len(low)):
            hi=int(high[i%len(high)]);lo=int(low[j%len(low)])
            next_hi=high_s[(i+1)%len(high)]+(1 if i+1>=len(high) else 0)
            next_lo=low_s[(j+1)%len(low)]+(1 if j+1>=len(low) else 0)
            if next_hi<next_lo:
                ni=int(high[(i+1)%len(high)]);tri=[hi,lo,ni];s=[high_s[i%len(high)],low_s[j%len(low)],high_s[(i+1)%len(high)]];height=[high_t,low_t,high_t];i+=1
            else:
                ni=int(low[(j+1)%len(low)]);tri=[hi,lo,ni];s=[high_s[i%len(high)],low_s[j%len(low)],low_s[(j+1)%len(low)]];height=[high_t,low_t,low_t];j+=1
            if max(s)-min(s)>.5:s=[value+1 if value<.5 else value for value in s]
            faces.append(tri);texcoords.append([[u0+value*(u1-u0),v1-h*(v1-v0)] for value,h in zip(s,height)]);face_roles.append('loft')
    for loop in loops:
        if loop is outer:continue
        ordered,_=intrinsic_ring(np.column_stack((upper['vertices'][:,0],upper['vertices'][:,1]+slope*upper['vertices'][:,2],upper['vertices'][:,2])),loop,upper['vertices'][loop][:,[0,2]].mean(0))
        cap=planar_cap(np.asarray(vertices),ordered)
        faces.extend(cap);texcoords.extend([[uv_patch['cap_sample']]*3 for _ in cap]);face_roles.extend(['internal_cap']*len(cap))
    vertices=np.asarray(vertices);weights=np.asarray(weights);faces=np.asarray(faces,dtype=int);normals_out=np.asarray(normals_out)
    geometric=normals(vertices,faces);shared=welded_vertices(vertices)
    summed=np.zeros_like(vertices)
    np.add.at(summed,shared,geometric)
    summed/=np.maximum(np.linalg.norm(summed,axis=1)[:,None],1e-12)
    new=np.asarray(origins)<0;normals_out[new]=summed[shared[new]]
    canonical=np.asarray(roles)=='canonical_rim';normals_out[canonical]=native_body['normals'][bottom]
    j,w=sparse_weights(weights)
    if 'joints' in source_head:
        kept=np.flatnonzero(retained)
        j[kept]=source_head['joints'][upper['origins'][kept]];w[kept]=source_head['skinweights'][upper['origins'][kept]]
    if 'joints' in native_body:j[canonical]=native_body['joints'][bottom];w[canonical]=native_body['skinweights'][bottom]
    report={'mode':'structured_neck_loft','neck_cut_y':bottom_cut,'upper_neck_chart_cut':top_cut,
        'neck_plane':f'y + {slope:.3f}*z','sections':sections,'samples_per_section':samples,
        'retained_triangle_count':len(upper['triangles']),'new_loft_triangles':face_roles.count('loft'),
        'internal_cap_triangles':face_roles.count('internal_cap'),'internal_cut_loops':len(loops)-1,
        'canonical_boundary_vertices':len(bottom),'upper_boundary_vertices':len(top),'neck_uv':uv_patch,
        'top_boundary':{'positions':upper['vertices'][top].tolist(),'uv':[first_uv[int(i)].tolist() for i in top],'arc':top_s.tolist()},
        'bottom_boundary':{'positions':native_body['vertices'][bottom].tolist(),'uv':native_body['vertex_uv'][bottom].tolist(),'arc':bottom_s.tolist()},
        'source_vertex_origins':list(map(int,origins)),'vertex_roles':roles,'face_roles':face_roles}
    return {'vertices':vertices,'triangles':faces,'uv':np.asarray(texcoords),'normals':normals_out,
            'weights':weights,'joints':j,'skinweights':w,'origins':np.asarray(origins)},report


def hybrid_head(source, vertices, triangles, uv, joints, weights, cut=1.50, slope=.6, relax_neck=True, atlas_size=(1024,1024)):
    """Fit a true-neck loft while retaining the accepted body and complete face.

    The internal smoothing stage only conditions the old shoulder-derived skin
    above the trim. Its lower annulus is discarded, never shipped as a result.
    """
    conditioned,lower,old_report=legacy_hybrid_head(source,vertices,triangles,uv,joints,weights,cut,slope,relax_neck)
    if not relax_neck:return conditioned,lower,old_report
    upper={key:value.copy() for key,value in conditioned.items()}
    upper['uv'][...,1]=1-upper['uv'][...,1]
    upper['joints'],upper['skinweights']=sparse_weights(upper['weights'])
    native={key:value.copy() for key,value in lower.items()}
    native['uv'][...,1]=1-native['uv'][...,1]
    native['joints'],native['skinweights']=sparse_weights(native['weights'])
    native['vertex_uv']=np.zeros((len(native['vertices']),2))
    assigned=set()
    for tri,tex in zip(native['triangles'],native['uv']):
        for index,value in zip(tri,tex):
            if int(index) not in assigned:native['vertex_uv'][index]=value;assigned.add(int(index))
    head,report=structured_neck_loft(upper,native,top_cut=cut+.05,bottom_cut=cut,slope=slope,atlas_size=atlas_size)
    head['uv'][...,1]=1-head['uv'][...,1]
    report.update(canonical_original_material=old_report['canonical_original_material'],
                  canonical_body_below_neck=old_report['canonical_body_below_neck'])
    return head,lower,report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--mesh',required=True,type=Path)
    parser.add_argument('--metadata',required=True,type=Path)
    parser.add_argument('--mpfb-data',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--skin-texture',type=Path)
    parser.add_argument('--eye-texture',type=Path)
    parser.add_argument('--skin-cap',type=int,default=1024)
    parser.add_argument('--body-mode',choices=['hybrid','full'],default='hybrid',
                        help='Hybrid retains accepted body/gear envelope; full is an unvalidated anatomical study.')
    args = parser.parse_args()
    meta = json.loads(args.metadata.read_text())
    data = np.load(args.mesh)
    glb = Glb(args.source)
    source_nodes = copy.deepcopy(glb.doc['nodes'])
    source_ibm = glb.read(glb.doc['skins'][0]['inverseBindMatrices']).copy()
    rig = args.mpfb_data/'rigs/standard/rig.game_engine.json'
    weights = args.mpfb_data/'rigs/standard/weights.game_engine.json'
    vertices,joints,skinweights,eyes,eyejoints,eyeweights,report = fit_geometry(data,meta,glb,rig,weights)
    skinmat = glb.material(args.skin_texture or meta['skin_texture'],args.skin_cap,'MPFB baked skin',.83)
    eyemat = glb.material(args.eye_texture or meta['eye_texture'],512,'MPFB baked eyes',.36,alpha=True)
    if args.body_mode == 'hybrid':
        head,lower,hybrid = hybrid_head(glb,vertices,data['body_triangles'],data['body_uv'],joints,skinweights,atlas_size=(args.skin_cap,args.skin_cap))
        hj,hw=head['joints'],head['skinweights'];lj,lw=sparse_weights(lower['weights'])
        bodyprimitives = [primitive(glb,head['vertices'],head['triangles'],head['uv'],hj,hw,skinmat,head['normals']),
                          primitive(glb,lower['vertices'],lower['triangles'],lower['uv'],lj,lw,
                                    hybrid['canonical_original_material'],lower['normals'])]
        report['body_fit']=hybrid
    else:
        bodyprimitives = [primitive(glb,vertices,data['body_triangles'],data['body_uv'],joints,skinweights,skinmat)]
        report['body_fit']={'mode':'full','validated':False,'limitation':'Does not fit existing garments; authoring study only.'}
    eyeprimitive = primitive(glb,eyes,data['eye_triangles'],data['eye_uv'],eyejoints,eyeweights,eyemat)
    for node in glb.doc['nodes']:
        name = node.get('name')
        if name in ('body','eyes'):
            glb.doc['meshes'][node['mesh']]['primitives'] = bodyprimitives if name == 'body' else [eyeprimitive]
        elif name in ('eyebrows','scalp'):
            node.pop('mesh',None)
            node.pop('skin',None)
    glb.doc.setdefault('asset',{})['generator'] = 'Rabbit Lands MPFB canonical prototype fitter'
    glb.write(args.output)
    check = Glb(args.output)
    joint_indices = check.doc['skins'][0]['joints']
    skeleton_equal = all(check.doc['nodes'][i] == source_nodes[i] for i in joint_indices)
    ibm_equal = np.array_equal(check.read(check.doc['skins'][0]['inverseBindMatrices']),source_ibm)
    if not skeleton_equal or not ibm_equal: raise AssertionError('Canonical skeleton changed')
    body_node=next(n for n in check.doc['nodes'] if n.get('name')=='body')
    exported_body=check.doc['meshes'][body_node['mesh']]['primitives']
    body_arrays=[check.read(p['attributes']['POSITION']) for p in exported_body]
    body_points=np.concatenate(body_arrays)
    report.update({'source':str(args.source),'source_sha256':sha(args.source),
                   'mpfb_mesh_sha256':sha(args.mesh),'mpfb_metadata_sha256':sha(args.metadata),
                   'weights_sha256':sha(weights),'rig_definition_sha256':sha(rig),
                   'output':str(args.output),'output_sha256':sha(args.output),'output_bytes':args.output.stat().st_size,
                   'skeleton_nodes_exact':skeleton_equal,'inverse_binds_exact':ibm_equal,
                   'mpfb_source_body_triangles':len(data['body_triangles']),
                   'body_triangles':sum(check.read(p['indices']).size//3 for p in exported_body),
                   'exported_body_bounds':[body_points.min(0).tolist(),body_points.max(0).tolist()],
                   'eye_triangles':len(data['eye_triangles']),
                   'fitter_sha256':sha(__file__),
                   'skin_texture_cap':args.skin_cap,'eye_texture_cap':512,
                   'limitations':['Prototype: visual deformation and gear clearance require engine review.',
                                  'Existing wardrobe geometry retained; no equipment copies created.']})
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    report['body_fit']={key:value for key,value in report['body_fit'].items() if key not in ['source_vertex_origins','vertex_roles','face_roles']}
    fit={k:report[k] for k in
        ['face_frame_head_local','head_bounds','eye_bounds','head_matrix','body_fit','output_sha256']}
    shape_center=meta.get('profile',{}).get('runtime_shape_center')
    if shape_center is not None:
        fit['head_shape_center']=shape_center
    args.output.with_name('fit.json').write_text(json.dumps(fit,indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__': main()
