"""Two canonical body shapes with original race heads and Ssarathi tails.

Inputs are the reviewed canonical Rest_Pose GLBs, never raw Meshy rigs. Outputs
are scratch candidates. Below-neck geometry and weights come from Luminous of
the same sex. Heads keep their original attributes above an oblique neck cut.
No joint, inverse bind, animation, head attachment or hair transform is changed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter1d, maximum_filter1d
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

import equipment_authoring as ea
sys.path.insert(0, str(Path(__file__).parent / 'tpose_bodies/vendor'))
import glbkit as g

PARTS = ea.BODY_SURFACES
LOWER_CUT = .075
UPPER_CUT = .110
# The adaptor ends on exposed neck skin above the source shirt collar.
UPPER_CUT_BY_SOURCE = {}

# These source necks are wider than the shared human neck and have painted
# collars immediately below them. Preserve their skin detail above the collar.
DETAILED_NECKS = ('ssarathi_', 'glasswarden_')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def block(document, blob):
    """Read each shared attribute set once and union all named face buffers."""
    groups = {}
    for node in document['nodes']:
        if node.get('name') not in PARTS or 'mesh' not in node:
            continue
        for p in document['meshes'][node['mesh']]['primitives']:
            key = tuple(sorted(p['attributes'].items()))
            group = groups.setdefault(key, {'a': p['attributes'], 'f': {}})
            group['f'][(node['name'], p.get('material', 0))] = ea.accessor_array(
                document, blob, p['indices']).astype(int).reshape(-1, 3)
    if not groups:
        raise ValueError('No body surfaces')
    # Source-preserving material groups have separate cropped UV charts.
    # Concatenate each distinct attribute set once, retaining material IDs.
    attributes, faces, offset = {}, {}, 0
    keys = {'POSITION', 'NORMAL', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0'}
    for group in groups.values():
        a = {k: ea.accessor_array(document, blob, group['a'][k]).copy() for k in keys}
        for k, values in a.items():
            attributes.setdefault(k, []).append(values)
        for key, ff in group['f'].items():
            faces.setdefault(key, []).append(ff + offset)
        offset += len(a['POSITION'])
    return {'a': {k: np.concatenate(v) for k, v in attributes.items()},
            'f': {k: np.concatenate(v) for k, v in faces.items()}}


def dense_weights(a):
    out = np.zeros((len(a['POSITION']), 77))
    for col in range(4):
        out[np.arange(len(out)), a['JOINTS_0'][:, col]] += a['WEIGHTS_0'][:, col]
    return out


def sparse_weights(w):
    j = np.argsort(-w, axis=1, kind='stable')[:, :4]
    v = np.take_along_axis(w, j, axis=1)
    v /= np.maximum(v.sum(1, keepdims=True), 1e-12)
    return j.astype('<u2'), v.astype('<f4')


def clip(group, signed, keep_positive):
    """Clip triangles, interpolating full joint distributions at cut edges."""
    a = group['a']
    rows = {k: list(v) for k, v in a.items()}
    weights = dense_weights(a)
    cache, boundary, faces = {}, [], {}
    inside = signed >= 0 if keep_positive else signed <= 0

    def intersection(i, j):
        edge = tuple(sorted((int(i), int(j))))
        if edge not in cache:
            t = signed[i] / (signed[i] - signed[j])
            values = {k: a[k][i] * (1-t) + a[k][j] * t
                      for k in a if k not in ('JOINTS_0', 'WEIGHTS_0')}
            jj, ww = sparse_weights(((1-t)*weights[i]+t*weights[j])[None])
            values['JOINTS_0'], values['WEIGHTS_0'] = jj[0], ww[0]
            values['NORMAL'] /= max(np.linalg.norm(values['NORMAL']), 1e-12)
            cache[edge] = len(rows['POSITION'])
            for k in rows:
                rows[k].append(values[k])
        return cache[edge]

    for key, ff in group['f'].items():
        kept = []
        for f in ff:
            if inside[f].all():
                kept.append(f.tolist())
                continue
            if not inside[f].any():
                continue
            polygon, edge = [], []
            for i, j in zip(f, np.roll(f, -1)):
                if inside[i]:
                    polygon.append(int(i))
                if inside[i] != inside[j]:
                    ix = intersection(i, j)
                    polygon.append(ix)
                    edge.append(ix)
            if len(edge) == 2:
                boundary.append(edge)
            kept.extend([[polygon[0], polygon[i], polygon[i+1]]
                         for i in range(1, len(polygon)-1)])
        if kept:
            faces[key] = np.asarray(kept, dtype=int)
    return {'a': {k: np.asarray(v, dtype=a[k].dtype) for k, v in rows.items()},
            'f': faces, 'boundary': np.asarray(boundary, dtype=int)}


def loops(group, origin, axis):
    """Weld only the cut graph for analysis; UV splits stay independent."""
    edges = group['boundary']
    used = np.unique(edges)
    p = group['a']['POSITION'][used]
    pairs = cKDTree(p).query_pairs(1e-6, output_type='ndarray')
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                       shape=(len(p), len(p))).tocsr()
    count, labels = connected_components(graph, directed=False)
    representative = np.array([used[np.flatnonzero(labels == i)[0]] for i in range(count)])
    remap = dict(zip(used.tolist(), labels.tolist()))
    edges = np.array([[remap[i], remap[j]] for i, j in edges])
    neighbours = [set() for _ in range(count)]
    for i, j in edges:
        if i != j:
            neighbours[i].add(j)
            neighbours[j].add(i)
    pending = {i for i, n in enumerate(neighbours) if n}
    rings = []
    while pending:
        first = min(pending)
        ring, prev, cur = [], None, first
        while True:
            if len(neighbours[cur]) != 2:
                raise ValueError(f'Nonmanifold neck cut at {p[labels == cur][0]}')
            ring.append(cur)
            pending.discard(cur)
            nxt = next(i for i in sorted(neighbours[cur]) if i != prev)
            prev, cur = cur, nxt
            if cur == first:
                break
            if len(ring) > count:
                raise ValueError('Neck boundary did not close')
        rings.append(representative[ring])
    # Largest projected area is the exterior. Some source necks have an inner
    # wall; cap those hidden interior loops instead of connecting unrelated walls.
    def area(ids):
        pp = group['a']['POSITION'][ids] - origin
        return abs(float(np.cross(pp, np.roll(pp, -1, axis=0)).sum(0) @ axis))
    return sorted(rings, key=area, reverse=True)


def append_view(d, binary, payload):
    binary.extend(b'\0' * (-len(binary) % 4))
    d.setdefault('bufferViews', []).append({'buffer': 0, 'byteOffset': len(binary),
                                          'byteLength': len(payload)})
    binary.extend(payload)
    return len(d['bufferViews']) - 1


def append_array(d, binary, a, kind, component=5126):
    dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2'}[component]
    values = np.asarray(a, dtype=dtype)
    vi = append_view(d, binary, values.tobytes())
    spec = {'bufferView': vi, 'componentType': component, 'count': len(values), 'type': kind}
    if kind == 'VEC3':
        spec.update(min=values.min(0).tolist(), max=values.max(0).tolist())
    d['accessors'].append(spec)
    return len(d['accessors'])-1


def image_bytes(d, binary, index):
    image = d['images'][index]
    view = d['bufferViews'][image['bufferView']]
    return bytes(binary[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']])


def material_image(d, binary, material):
    ti = d['materials'][material]['pbrMetallicRoughness']['baseColorTexture']['index']
    ii = d['textures'][ti]['source']
    return ii, np.asarray(Image.open(io.BytesIO(image_bytes(d, binary, ii))).convert('RGB'))


def sample_image(pixels, uv):
    # Match glTF/Godot's texel-centre convention, including repeat wrapping.
    size=np.array(pixels.shape[:2][::-1]);xy=(uv%1)*size-.5
    lo=np.floor(xy).astype(int);t=xy-lo;hi=(lo+1)%size;lo%=size
    return ((pixels[lo[:,1],lo[:,0]]*(1-t[:,0,None])+pixels[lo[:,1],hi[:,0]]*t[:,0,None])*(1-t[:,1,None])
            +(pixels[hi[:,1],lo[:,0]]*(1-t[:,0,None])+pixels[hi[:,1],hi[:,0]]*t[:,0,None])*t[:,1,None])/255.


def body_material(group):
    return next(mat for name, mat in group['f'] if name == 'body')


def colour_template(d, binary, common, source, sd, sb, origin, axis, material_map, upper_cut):
    """Keep shared skin shading and match the retained race's neck palette."""
    src_mat = body_material(source)
    _, source_pixels = material_image(sd, sb, src_mat)
    faces = source['f'][('body', src_mat)]
    centres = source['a']['POSITION'][faces].mean(1)
    signed = (centres-origin)@axis
    colour_band = .020
    chosen = (signed > upper_cut) & (signed < upper_cut+colour_band)
    # Sparse source neck topology needs a taller colour sample, not more copies
    # of the same shared accessors. This never changes the cut or geometry.
    if chosen.sum() < 12:
        colour_band = .040
        chosen = (signed > upper_cut) & (signed < upper_cut+colour_band)
    if chosen.sum() < 12:
        raise ValueError('Too few source neck samples for colour transfer')
    target = np.median(sample_image(source_pixels, source['a']['TEXCOORD_0'][faces[chosen]].mean(1)), axis=0)
    common_mat = body_material(common)
    output_mat = material_map[common_mat]
    image_id, pixels = material_image(d, binary, output_mat)
    faces = common['f'][('body', common_mat)]
    signed = (common['a']['POSITION'][faces].mean(1)-origin)@axis
    chosen = (signed > LOWER_CUT-.005) & (signed < LOWER_CUT+.015)
    reference = np.median(sample_image(pixels, common['a']['TEXCOORD_0'][faces[chosen]].mean(1)), axis=0)
    ratio = target / np.maximum(reference, .05)
    recoloured = np.clip(np.rint(pixels.astype(float)*ratio), 0, 255).astype('u1')
    encoded = io.BytesIO(); Image.fromarray(recoloured).save(encoded, format='PNG', compress_level=6)
    d['images'][image_id] = {'mimeType': 'image/png', 'bufferView': append_view(d, binary, encoded.getvalue())}
    return {'sourceNeckRGB': target.tolist(), 'templateNeckRGB': reference.tolist(),
            'sourceColourBandM': colour_band,
            'channelRatio': ratio.tolist()}, recoloured, source_pixels



def cap_inner_loops(group, rings, direction):
    """Close hidden inner walls when the other source has no matching cavity."""
    material = body_material(group)
    extra = []
    for ring in rings[1:]:
        a = group['a']; center = len(a['POSITION'])
        dense = dense_weights(a)[ring].mean(0)
        jj, ww = sparse_weights(dense[None])
        for key in a:
            value = a[key][ring].mean(0)
            if key == 'JOINTS_0': value = jj[0]
            elif key == 'WEIGHTS_0': value = ww[0]
            elif key == 'NORMAL': value = direction
            a[key] = np.concatenate([a[key], np.asarray(value, dtype=a[key].dtype)[None]])
        for i, j in zip(ring, np.roll(ring, -1)):
            f = [int(i), int(j), center]
            p = a['POSITION'][f]
            if np.cross(p[1]-p[0], p[2]-p[0]) @ direction < 0: f.reverse()
            extra.append(f)
    if extra:
        group['f'][('body', material)] = np.concatenate([group['f'][('body', material)], extra])


def clean_tail_root(group):
    """Discard source trousers and the old closure fan inside the shared hips.

    Tail extraction also caught the source's brown seat around the attachment.
    Its material groups stop at the hips; the actual tail extends beyond x=.30.
    A fan across that entire cut made the unwanted seat's outline visible even
    after its clothing faces were removed. Keep the authored tail attributes
    and leave its hidden root open inside the complete shared trouser surface.
    """
    v, normals = group['a']['POSITION'], group['a']['NORMAL']
    result = dict(group)
    result['f'] = {}
    for key, faces in group['f'].items():
        if not len(faces) or v[faces, 0].max() <= .30:
            continue
        incidence = np.bincount(faces.ravel(), minlength=len(v))
        cap = (np.all(np.abs(normals-[0., 0., 1.]) < 1e-6, axis=1)
               & (incidence >= 12) & (np.abs(v[:, 0]) < .20)
               & (v[:, 1] > .70) & (v[:, 1] < .97)
               & (v[:, 2] > -.17) & (v[:, 2] < -.05))
        result['f'][key] = faces[~cap[faces].any(axis=1)]
    return result


def tail_graft(source, positions):
    """Keep the whole original tail, including its existing pelvis feather.

    The extraction boundary extends inside the shared pelvis. No distal tail
    vertices, UVs or weights are moved. Disconnected posterior clothing patches
    cannot masquerade as the tail: select the connected component with its tip.
    """
    v = source['a']['POSITION']
    distance = np.full(len(v), np.inf)
    for side in ('l', 'r'):
        chain = [positions[n+'_'+side] for n in ('thigh', 'calf', 'foot', 'ball')]
        chain.append(chain[-1]+[0, 0, .15])
        for a, b in zip(chain, chain[1:]):
            axis = b-a
            t = np.clip((v-a)@axis/(axis@axis), 0, 1)
            distance = np.minimum(distance, np.linalg.norm(v-a-t[:, None]*axis, axis=1))
    signed = np.minimum.reduce([distance-.10, np.maximum(v[:, 0]-.115, -.095-v[:, 2]),
                                positions['pelvis'][1]+.035-v[:, 1]])
    tail = clip(source, signed, True)
    ff = np.concatenate(list(tail['f'].values()))
    vv = tail['a']['POSITION']
    used = np.unique(ff)
    pairs = cKDTree(vv[used]).query_pairs(1e-6, output_type='ndarray')
    _, welded = connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                                               shape=(len(used), len(used))).tocsr(), directed=False)
    remap = np.full(len(vv), -1, dtype=int); remap[used] = welded
    edges = remap[np.concatenate([ff[:, [0, 1]], ff[:, [1, 2]], ff[:, [2, 0]]])]
    count = int(welded.max())+1
    _, component = connected_components(coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])),
                                                  shape=(count, count)).tocsr(), directed=False)
    tip = used[int(np.argmax(vv[used, 0]))]
    chosen = component[remap[tip]]
    tail['f'] = {key: f[component[remap[f[:, 0]]] == chosen] for key, f in tail['f'].items()}
    tail['f'] = {key: f for key, f in tail['f'].items() if len(f)}
    selected = np.unique(np.concatenate(list(tail['f'].values())))
    tail['boundary'] = tail['boundary'][np.isin(tail['boundary'], selected).all(1)]
    # Record the source cut before removing the redundant seat and its cap.
    root_axis = np.array([0., 0., -1.])
    rings = loops(tail, positions['pelvis'], root_axis)
    tail = clean_tail_root(tail)
    selected = np.unique(np.concatenate(list(tail['f'].values())))
    tail['boundary'] = tail['boundary'][np.isin(tail['boundary'], selected).all(1)]
    source_tail = np.flatnonzero(signed > 0)
    return tail, {'sourceTailTip': v[source_tail[np.argmax(v[source_tail, 0])]].tolist(),
                  'keptVertices': int(len(selected)), 'rootLoops': list(map(len, rings)),
                  'originalVerticesPreserveWeights': True,
                  'trianglesIncludingInternalCap': sum(len(f) for f in tail['f'].values())}


def copy_materials(out, binary, source, source_blob):
    image_map = {}
    for i, image in enumerate(source['images']):
        q = copy.deepcopy(image)
        q['bufferView'] = append_view(out, binary, image_bytes(source, source_blob, i))
        out['images'].append(q)
        image_map[i] = len(out['images'])-1
    sampler_offset = len(out.setdefault('samplers', []))
    out['samplers'].extend(copy.deepcopy(source.get('samplers', [])))
    texture_offset = len(out['textures'])
    for tex in source['textures']:
        q = copy.deepcopy(tex)
        q['source'] = image_map[q['source']]
        if 'sampler' in q:
            q['sampler'] += sampler_offset
        out['textures'].append(q)
    def remap(q):
        if isinstance(q, dict):
            for k, v in q.items():
                if k.endswith('Texture') and isinstance(v, dict) and 'index' in v:
                    v['index'] += texture_offset
                else:
                    remap(v)
        elif isinstance(q, list):
            for v in q:
                remap(v)
    offset = len(out['materials'])
    mats = copy.deepcopy(source['materials'])
    remap(mats)
    out['materials'].extend(mats)
    return {i: i+offset for i in range(len(mats))}


def neck_bridge(lower, upper, origin, axis, material, reference, smooth_profile=False):
    lr, ur = loops(lower, origin, axis), loops(upper, origin, axis)
    def ordered(group, ids):
        v = group['a']['POSITION'][ids] - origin
        other = np.cross(axis, [1., 0., 0.])
        theta = np.arctan2(v @ other, v[:, 0]) % (2*np.pi)
        # Preserve boundary order. Reverse if needed, then rotate at angle zero.
        if np.median(np.angle(np.exp(1j*np.diff(np.r_[theta, theta[0]])))) < 0:
            ids, theta = ids[::-1], theta[::-1]
        start = int(np.argmin(theta))
        return np.roll(ids, -start), np.unwrap(np.roll(theta, -start))
    li, lt = ordered(lower, lr[0]); ui, ut = ordered(upper, ur[0])
    # Use the common anatomical neck as the waist of the transition.
    # Interpolating chest radius straight to jaw radius creates a broad cone.
    theta = np.arange(64)*2*np.pi/64
    def sample(group, ids, angles):
        order = np.argsort(angles % (2*np.pi))
        angles = angles[order] % (2*np.pi); ids = ids[order]
        values = {k: group['a'][k][ids] for k in group['a']}
        values['dense'] = dense_weights(group['a'])[ids]
        return {k: np.column_stack([np.interp(theta, angles, v[:,j], period=2*np.pi)
                                    for j in range(v.shape[1])])
                for k,v in values.items()}
    ls, us = sample(lower,li,lt), sample(upper,ui,ut)
    ri,rt=ordered(reference,loops(reference,origin,axis)[0]);rs=sample(reference,ri,rt)
    rings = [{k:lower['a'][k][li] for k in lower['a']}]
    angles = [lt]
    steps = np.arange(1, 8)/8 if smooth_profile else (.125,.25,.5,.75)
    for t in steps:
        a = {k:(1-t)*ls[k]+t*us[k] for k in lower['a']}
        lp,up=ls['POSITION']-origin,us['POSITION']-origin
        lh,uh=lp@axis,up@axis
        rp=rs['POSITION']-origin;rr=rp-(rp@axis)[:,None]*axis
        top=np.clip((t-.5)*2,0,1);top=top*top*(3-2*top)
        neck_radial=(1-top)*rr+top*(up-uh[:,None]*axis)
        g=1-(1-t)**6
        radial=(1-g)*(lp-lh[:,None]*axis)+g*neck_radial
        a['POSITION']=origin+((1-t)*lh+t*uh)[:,None]*axis+radial
        if smooth_profile:
            # Follow both end tangents without forcing a narrow human waist
            # just below the wider source jaw. Keep the exact boundary copies.
            derivatives = []
            for section, rel, height in ((ls, lp, lh), (us, up, uh)):
                direction = rel-height[:, None]*axis
                direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-9)
                normal = gaussian_filter1d(section['NORMAL'], 1.5, axis=0, mode='wrap')
                slope = -(normal@axis)/np.maximum((normal*direction).sum(1), .25)
                derivatives.append(axis+np.clip(slope, -.8, .8)[:, None]*direction)
            span = (uh-lh)[:, None]
            a['POSITION'] = ((2*t**3-3*t*t+1)*ls['POSITION']
                +(t**3-2*t*t+t)*span*derivatives[0]
                +(-2*t**3+3*t*t)*us['POSITION']
                +(t**3-t*t)*span*derivatives[1])
        a['JOINTS_0'],a['WEIGHTS_0'] = sparse_weights((1-t)*ls['dense']+t*us['dense'])
        a['NORMAL'] /= np.maximum(np.linalg.norm(a['NORMAL'],axis=1,keepdims=True),1e-9)
        rings.append(a);angles.append(theta)
    rings.append({k:upper['a'][k][ui] for k in upper['a']});angles.append(ut)
    attrs = {k:np.concatenate([r[k] for r in rings]) for k in lower['a']}
    offsets = np.cumsum([0]+[len(r['POSITION']) for r in rings])
    ff = []
    for ring in range(len(rings)-1):
        n,m = len(rings[ring]['POSITION']),len(rings[ring+1]['POSITION'])
        lt0,ut0=angles[ring],angles[ring+1]
        i,j=0,0
        while i<n or j<m:
            a,b=offsets[ring]+i%n,offsets[ring+1]+j%m
            nxt_l=lt0[(i+1)%n]+(2*np.pi if i+1>=n else 0)
            nxt_u=ut0[(j+1)%m]+(2*np.pi if j+1>=m else 0)
            if i<n and (j>=m or nxt_l<=nxt_u):
                ff.append([a,offsets[ring]+(i+1)%n,b]);i+=1
            else:
                ff.append([a,offsets[ring+1]+(j+1)%m,b]);j+=1
    ff=np.asarray(ff)
    p=attrs['POSITION'];c=p[ff].mean(1)-origin
    radial=c-(c@axis)[:,None]*axis
    normal=np.cross(p[ff[:,1]]-p[ff[:,0]],p[ff[:,2]]-p[ff[:,0]])
    wrong=(normal*radial).sum(1)<0;ff[wrong]=ff[wrong][:,::-1]
    normal[wrong]*=-1
    summed=np.zeros_like(p)
    for column in range(3):np.add.at(summed,ff[:,column],normal)
    summed/=np.maximum(np.linalg.norm(summed,axis=1,keepdims=True),1e-9)
    attrs['NORMAL'][offsets[1]:offsets[-2]]=summed[offsets[1]:offsets[-2]]
    return {'a':attrs,'f':{('body',material):ff},'lowerIds':li,'upperIds':ui},lr,ur


def extend_neck_skin(group, pixels, points, origin, axis):
    """Stretch clean source neck texels once; never reflect lips or collars.

    A coarse source triangle can cross the painted collar even when its centre
    is skin. Sample within its UVs, then reject non-skin texels individually.
    Missing skin behind a source's high collar borrows the nearest actual neck
    samples around the circumference instead of stretching black cloth.
    """
    side=np.cross(axis,[1.,0.,0.])
    if '_neck_skin_samples' not in group:
        attrs=group['a'];faces=group['f'][('body',body_material(group))]
        corners=attrs['POSITION'][faces]-origin
        travel=corners@axis;centre=corners.mean(1)
        radial=centre-(centre@axis)[:,None]*axis
        radius=np.linalg.norm(radial,axis=1)
        face_rgb=sample_image(pixels,attrs['TEXCOORD_0'][faces].mean(1))
        head_band=(travel.mean(1)>UPPER_CUT+.025)&(travel.mean(1)<UPPER_CUT+.105)&(radius<.14)
        reference=np.median(face_rgb[head_band],axis=0)
        normals=attrs['NORMAL'][faces].mean(1)
        selected=(travel.max(1)>.025)&(travel.min(1)<UPPER_CUT)&(radius<.12)&((radial*normals).sum(1)>0)
        faces=faces[selected]
        bary=np.array([[1-u-v,u,v] for u in np.linspace(0,1,19)
                       for v in np.linspace(0,1,19) if u+v<=1+1e-8])
        positions=np.einsum('ki,nic->nkc',bary,attrs['POSITION'][faces]).reshape(-1,3)-origin
        uv=np.einsum('ki,nic->nkc',bary,attrs['TEXCOORD_0'][faces]).reshape(-1,2)
        rgb=sample_image(pixels,uv)
        height=positions@axis
        clean=(height>.025)&(height<UPPER_CUT)&(np.linalg.norm(rgb-reference,axis=1)<.20)
        if clean.sum()<32:raise ValueError('Insufficient clean source neck texels')
        chart=np.column_stack([np.arctan2(positions@side,positions[:,0])*.05,height])[clean]
        _,unique=np.unique(np.round(chart,6),axis=0,return_index=True)
        chart=chart[unique];rgb=rgb[clean][unique]
        copies=np.concatenate([chart+[-2*np.pi*.05,0],chart,chart+[2*np.pi*.05,0]])
        group['_neck_skin_samples']=(cKDTree(copies),np.tile(rgb,(3,1)))
    tree,rgb=group['_neck_skin_samples']
    rel=points-origin
    height=.030+np.clip(((rel@axis)+.160)/(UPPER_CUT+.160),0,1)*.075
    query=np.column_stack([np.arctan2(rel@side,rel[:,0])*.05,height])
    distance,nearest=tree.query(query,k=4)
    weight=1/np.maximum(distance,1e-8)**2
    weight/=weight.sum(1)[:,None]
    return np.einsum('ni,nic->nc',weight,rgb[nearest])


def project_neck_texture(group, pixels, points, origin, axis, extend=False, radius_limit=None):
    """Sample neck skin in angular/axial coordinates, independent of radius.

    Nearest triangles in 3-D collapse samples onto edges when two necks differ
    in girth, creating vertical texture streaks. Cylindrical projection follows
    each triangle's actual UV interpolation without assuming equal neck radii.
    """
    if extend:
        return extend_neck_skin(group,pixels,points,origin,axis)
    side=np.cross(axis,[1.,0.,0.])
    cache_key = ('neck_projection', tuple(origin), tuple(axis), radius_limit)
    if cache_key not in group:
        faces = group['f'][('body', body_material(group))]
        attrs=group['a'];corners=attrs['POSITION'][faces]-origin
        travel=corners@axis;centre=corners.mean(1)
        radial=centre-(centre@axis)[:,None]*axis
        normals=attrs['NORMAL'][faces].mean(1)
        selected=(travel.max(1)>.025)&(travel.min(1)<.190)&((radial*normals).sum(1)>0)
        if radius_limit is not None:
            selected &= np.linalg.norm(radial, axis=1) < radius_limit
        faces,corners,travel=faces[selected],corners[selected],travel[selected]
        angles=np.arctan2(corners@side,corners[:,:,0])
        angles=angles[:,:1]+np.angle(np.exp(1j*(angles-angles[:,:1])))
        chart=np.stack([angles*.05,travel],axis=-1)
        copies=np.concatenate([chart+[-2*np.pi*.05,0],chart,chart+[2*np.pi*.05,0]])
        face_map=np.tile(np.arange(len(faces)),3)
        group[cache_key] = faces, copies, face_map, cKDTree(copies.mean(1))
    faces, copies, face_map, tree = group[cache_key]
    attrs = group['a']
    rel=points-origin;pt=rel@axis
    query=np.column_stack([np.arctan2(rel@side,rel[:,0])*.05,pt])
    _,nearest=tree.query(query,k=min(32,len(copies)))
    if nearest.ndim==1:nearest=nearest[:,None]
    tri=copies[nearest];a,b,c=tri[:,:,0],tri[:,:,1],tri[:,:,2]
    ab,ac,ap=b-a,c-a,query[:,None]-a
    det=ab[:,:,0]*ac[:,:,1]-ab[:,:,1]*ac[:,:,0]
    good=np.abs(det)>1e-14;safe=np.where(good,det,1.)
    u=(ap[:,:,0]*ac[:,:,1]-ap[:,:,1]*ac[:,:,0])/safe
    v=(ab[:,:,0]*ap[:,:,1]-ab[:,:,1]*ap[:,:,0])/safe
    weights=[np.stack([1-u-v,u,v],axis=-1)]
    valid=good&(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)
    for start,end,first,last in [(a,b,0,1),(b,c,1,2),(c,a,2,0)]:
        edge=end-start
        t=np.clip(((query[:,None]-start)*edge).sum(-1)/np.maximum((edge*edge).sum(-1),1e-16),0,1)
        w=np.zeros((*t.shape,3));w[:,:,first]=1-t;w[:,:,last]=t;weights.append(w)
    weights=np.stack(weights,axis=2)
    projected=np.einsum('nkij,nkjc->nkic',weights,tri)
    distance=((projected-query[:,None,None])**2).sum(-1)
    distance[:,:,0]=np.where(valid,-1e-10,np.inf)
    chosen=np.argmin(distance.reshape(len(points),-1),axis=1)
    k,option=chosen//4,chosen%4;row=np.arange(len(points))
    uv=np.einsum('ni,nic->nc',weights[row,k,option],attrs['TEXCOORD_0'][faces[face_map[nearest[row,k]]]])
    return sample_image(pixels,uv)


def detailed_neck_colours(source, pixels, points, origin, axis):
    """Project intact neck texels; reflect only where the source wears cloth.

    A nearest-skin search in the painted collar collapses entire columns to a
    few edge texels. Find the collar separately around the circumference, then
    extend the skin at its original scale from the clean neck above it.
    """
    side = np.cross(axis, [1., 0., 0.])
    if '_clean_neck_floor' not in source:
        angles = (np.arange(512)+.5)/512*2*np.pi-np.pi
        heights = np.linspace(.025, .145, 121)
        probe = (origin+heights[:, None, None]*axis
                 +.055*(np.cos(angles)[None, :, None]*[1., 0., 0.]
                         +np.sin(angles)[None, :, None]*side)).reshape(-1, 3)
        rgb = np.concatenate([project_neck_texture(source, pixels, probe[i:i+4096], origin, axis, radius_limit=.095)
                              for i in range(0, len(probe), 4096)]).reshape(121, 512, 3)
        brightness = rgb.mean(2)
        reference = np.median(brightness[heights >= .12], axis=0)
        cloth = brightness < reference[None]*.55
        floor = np.max(np.where(cloth, heights[:, None], .025), axis=0)+.006
        floor = np.minimum(gaussian_filter1d(maximum_filter1d(floor, 7, mode='wrap'), 2, mode='wrap'), .125)
        source['_clean_neck_floor'] = angles, floor
        source['_clean_neck_palette'] = gaussian_filter1d(np.median(rgb[heights >= .12], axis=0), 2, axis=0, mode='wrap')
    angles, floor = source['_clean_neck_floor']
    rel = points-origin
    theta = np.arctan2(rel@side, rel[:, 0])
    lo = np.interp(theta, angles, floor, period=2*np.pi)
    h = rel@axis
    span = .155-lo
    phase = (h-lo) % (2*span)
    reflected = lo+span-np.abs(phase-span)
    query = points+np.where(h < lo, reflected-h, 0)[:, None]*axis
    colour = project_neck_texture(source, pixels, query, origin, axis, radius_limit=.095)
    palette = source['_clean_neck_palette']
    base = np.column_stack([np.interp(theta, angles, palette[:, k], period=2*np.pi) for k in range(3)])
    detail = np.clip((h-.075)/.055, 0, 1)
    detail = .35+.65*detail*detail*(3-2*detail)
    return base+detail[:, None]*(colour-base)


def collar_facing(d, binary, groups):
    """Give the source's small chest-lacing patches the shirt dye, not skin."""
    encoded = io.BytesIO()
    Image.new('RGB', (2, 2), (175, 175, 175)).save(encoded, format='PNG')
    d['images'].append({'mimeType': 'image/png', 'bufferView': append_view(d, binary, encoded.getvalue())})
    d['textures'].append({'source': len(d['images'])-1})
    d['materials'].append({'name': 'Collar facing', 'doubleSided': True,
        'pbrMetallicRoughness': {'baseColorTexture': {'index': len(d['textures'])-1},
                               'metallicFactor': 0, 'roughnessFactor': .85}})
    count = 0
    for group in groups:
        for key, faces in list(group['f'].items()):
            if key[0] != 'body': continue
            centre = group['a']['POSITION'][faces].mean(1)
            chosen = ((centre[:, 1] > 1.365) & (centre[:, 1] < 1.490)
                      & (abs(centre[:, 0]) < .05) & (centre[:, 2] > .020))
            if not chosen.any(): continue
            group['f'][key] = faces[~chosen]
            group['f'][('wardrobe_shirt', len(d['materials'])-1)] = faces[chosen]
            count += int(chosen.sum())
    return count


def texture_neck(d, binary, bridge, lower, upper, common, source, common_pixels, source_pixels, origin, axis,
                 upper_cut=UPPER_CUT, detailed=False, texture_geometry=None):
    """Use one continuous cylindrical atlas across the complete neck adaptor.

    The common atlas assigned little space to its plain skin. Baking detailed
    race skin into those tiny charts creates a blurred band even with perfect
    geometry. Give the neck its own consistent texel density, including the
    retained lower neck, and fade into the original common chest texture.
    """
    material=next(iter(bridge['f']))[1]
    body_key=next(k for k in lower['f'] if k[0]=='body')
    ff=lower['f'][body_key];p=lower['a']['POSITION']
    travel=(p-origin)@axis
    selected=(travel[ff].max(1)>.005)&(np.abs(p[ff,:,][...,0]).max(1)<.12)
    neck={'a':{k:v.copy() for k,v in lower['a'].items()},
          'f':{('body',material):ff[selected]},'role':'shared_neck'}
    lower['f'][body_key]=ff[~selected]
    side=np.cross(axis,[1.,0.,0.]);h0=-.160;h1=upper_cut
    width,height=1024,512
    yy,xx=np.mgrid[:height,:width]
    theta=((xx+.5)/width-.5)*2*np.pi
    h=h0+(yy+.5)/height*(h1-h0)
    points=(origin+h[:,:,None]*axis+.055*(np.cos(theta)[:,:,None]*[1.,0.,0.]
                                         +np.sin(theta)[:,:,None]*side)).reshape(-1,3)
    colours=[]
    for start in range(0,len(points),4096):
        query=points[start:start+4096]
        high = (detailed_neck_colours(texture_geometry or source, source_pixels, query, origin, axis) if detailed
                else project_neck_texture(source,source_pixels,query,origin,axis,extend=True))
        colours.append(high)
    colours=np.concatenate(colours).reshape(height,width,3)
    # The final atlas row samples the retained source boundary itself. A global
    # angular projection approximates the cut edges and can leave a colour line.
    boundary=upper['boundary'];corners=upper['a']['POSITION'][boundary]-origin
    planar=np.stack([corners[:,:,0],corners@side],axis=-1)
    directions=np.stack([np.cos(theta[0]),np.sin(theta[0])],axis=-1)
    start,end=planar[:,0],planar[:,1];edge=end-start
    cross_start=start[None,:,0]*directions[:,None,1]-start[None,:,1]*directions[:,None,0]
    cross_edge=edge[None,:,0]*directions[:,None,1]-edge[None,:,1]*directions[:,None,0]
    parameter=-cross_start/np.where(np.abs(cross_edge)>1e-12,cross_edge,1.)
    hit=start[None]+parameter[:,:,None]*edge[None]
    radius=(hit*directions[:,None]).sum(-1)
    valid=(np.abs(cross_edge)>1e-12)&(parameter>=0)&(parameter<=1)&(radius>0)
    if not valid.any(1).all():raise ValueError('Neck boundary is not a closed radial contour')
    chosen=np.argmax(np.where(valid,radius,-np.inf),axis=1)
    t=parameter[np.arange(width),chosen,None]
    edge_uv=upper['a']['TEXCOORD_0'][boundary[chosen]]
    boundary_colour=sample_image(source_pixels,edge_uv[:,0]*(1-t)+edge_uv[:,1]*t)
    fade=np.clip((h-(upper_cut-.006))/.006,0,1)[:,:,None];fade=fade*fade*(3-2*fade)
    colours=colours*(1-fade)+boundary_colour[None]*fade
    atlas=np.rint(colours*255).astype('u1')
    for group in (bridge,neck):
        key,faces=next(iter(group['f'].items()))
        rel=group['a']['POSITION'][faces]-origin
        theta=np.arctan2(rel@side,rel[:,:,0])
        theta=theta[:,:1]+np.angle(np.exp(1j*(theta-theta[:,:1])))
        uv=np.stack([theta/(2*np.pi)+.5,((rel@axis)-h0)/(h1-h0)],axis=-1)
        group['a']={k:v[faces.ravel()] for k,v in group['a'].items()}
        group['a']['TEXCOORD_0']=uv.reshape(-1,2).astype('<f4')
        group['f'][key]=np.arange(len(faces)*3).reshape(-1,3)
    encoded=io.BytesIO();Image.fromarray(atlas).save(encoded,format='PNG',compress_level=9)
    d['images'].append({'mimeType':'image/png','bufferView':append_view(d,binary,encoded.getvalue())})
    d.setdefault('samplers',[]).append({'wrapS':10497,'wrapT':33071,'magFilter':9729,'minFilter':9987})
    d['textures'].append({'source':len(d['images'])-1,'sampler':len(d['samplers'])-1})
    d['materials'][material]['pbrMetallicRoughness']['baseColorTexture']={'index':len(d['textures'])-1}
    return neck


def write_group(d, binary, group, meshes):
    # Head/neck installers also copy retained tails from older exports.
    # Clean those copies here so an old backup cannot restore the brown seat.
    if group.get('role') == 'race_tail':
        group = clean_tail_root(group)
    if not any(len(f) for f in group['f'].values()):return
    # Compact each primitive independently. Godot imports separate surfaces;
    # a shared full-body accessor otherwise duplicates thousands of unused
    # vertices in each garment and appearance mesh.
    for (name, mat), faces in group['f'].items():
        if not len(faces):continue
        used, inverse = np.unique(faces, return_inverse=True)
        # Cylindrical UV baking emits per-triangle corners. Merge only exact
        # full-attribute duplicates; keep every UV, normal and skinning seam.
        rows = np.concatenate([np.ascontiguousarray(group['a'][k][used]).view('u1').reshape(len(used), -1)
                               for k in sorted(group['a'])], axis=1)
        _, keep, remap = np.unique(rows, axis=0, return_index=True, return_inverse=True)
        used, inverse = used[keep], remap[inverse]
        attrs = {}
        for k, values in group['a'].items():
            attrs[k] = append_array(d, binary, values[used], 'VEC'+str(values.shape[1]),
                                    5123 if k == 'JOINTS_0' else 5126)
        indices = append_array(d, binary, inverse.ravel(), 'SCALAR', 5125)
        meshes.setdefault(name, []).append({'attributes': attrs, 'indices': indices, 'material': mat,
                                           'extras': {'sourceRole': group['role']}})



def run(source, template, out, texture_source=None):
    if 'godot-client' in out.resolve().parts or out.resolve() in (source.resolve(), template.resolve()):
        raise ValueError('Use a separate scratch output')
    if out.exists():
        raise FileExistsError(out)
    input_hashes = digest(source), digest(template)
    sd, sb = ea.read_glb(source); td, tb = ea.read_glb(template)
    ss, ts = sd['skins'][0], td['skins'][0]
    sn = [sd['nodes'][i]['name'] for i in ss['joints']]
    tn = [td['nodes'][i]['name'] for i in ts['joints']]
    assert sn == tn and len(sn) == 77
    sw, tw = ea.global_matrices(sd), ea.global_matrices(td)
    assert np.array_equal(np.array(sw)[ss['joints']], np.array(tw)[ts['joints']])
    origin = sw[ss['joints'][sn.index('neck_01')]][:3, 3]
    axis = sw[ss['joints'][sn.index('Head')]][:3, 3] - origin
    axis /= np.linalg.norm(axis)
    src, common = block(sd, sb), block(td, tb)
    relative=common['a']['POSITION']-origin
    travel=relative@axis
    radius=np.linalg.norm(relative-travel[:,None]*axis,axis=1)
    local_neck=np.minimum(travel+.060,.150-radius)
    source_body = 'sourceIntegration' in td.get('asset',{}).get('extras',{})
    # The approved source body already has a natural exposed neckline. Keep
    # it intact instead of replacing the old procedural chest/neck region.
    body_cut = travel-LOWER_CUT if source_body else np.maximum(travel-LOWER_CUT,local_neck)
    lower = clip(common, body_cut, False)
    original = sd.get('asset', {}).get('extras', {}).get('highResolutionHead', {}).get('original', '')
    detailed_neck = original.startswith(DETAILED_NECKS)
    texture_geometry = None
    if detailed_neck and texture_source is not None:
        hd, hb = g.read(texture_source)
        if hd['asset']['extras']['highResolutionHead']['originalSHA256'] != sd['asset']['extras']['highResolutionHead']['originalSHA256']:
            raise ValueError('Neck texture geometry must come from the same original model')
        hp = hd['meshes'][0]['primitives'][0]
        texture_geometry = {'a': {k: g.accessor(hd, hb, v) for k, v in hp['attributes'].items()},
                            'f': {('body', 0): g.accessor(hd, hb, hp['indices']).astype(int).reshape(-1, 3)}}
    upper_cut = .130 if detailed_neck else UPPER_CUT_BY_SOURCE.get(source.stem, UPPER_CUT)
    upper = clip(src, (src['a']['POSITION']-origin)@axis-upper_cut, True)
    # Retained head/neck facets are skin, even where the source classifier
    # labelled a lip or neck patch as shirt. They must not receive shirt tint
    # or wardrobe normal-grow after the original torso is replaced.
    head_wardrobe = 0
    for key in list(upper['f']):
        if key[0] == 'wardrobe_shirt':
            faces = upper['f'].pop(key);head_wardrobe += len(faces)
            target = ('body', body_material(src))
            upper['f'][target] = np.concatenate([upper['f'].get(target, np.empty((0,3),dtype=int)), faces])

    d, binary = copy.deepcopy(sd), bytearray(sb)
    mapping = copy_materials(d, binary, td, tb)
    colour, common_pixels, source_pixels = colour_template(
        d, binary, common, src, sd, sb, origin, axis, mapping, upper_cut)
    lower['f'] = {(name, mapping[mat]): ff for (name, mat), ff in lower['f'].items()}
    # The common shirt remains a separate complete garment over the new skin.
    # Cutting it away with the anatomical neck leaves a hole on unequip.
    wardrobe=clip(common,body_cut,True)
    wardrobe['f']={(name,mapping[mat]):ff for (name,mat),ff in wardrobe['f'].items() if name=='wardrobe_shirt'}
    wardrobe['role']='shared_wardrobe'

    neck_material = copy.deepcopy(sd['materials'][body_material(src)])
    neck_material['name'] = 'Shared neck bridge'
    d['materials'].append(neck_material)
    reference=clip(common,(common['a']['POSITION']-origin)@axis-LOWER_CUT,False)
    bridge, lr, ur = neck_bridge(lower, upper, origin, axis, len(d['materials'])-1, reference,
                                smooth_profile=detailed_neck)
    shared_neck = texture_neck(d, binary, bridge, lower, upper, common, src, common_pixels, source_pixels, origin, axis,
                              upper_cut=upper_cut, detailed=detailed_neck, texture_geometry=texture_geometry)
    facing_triangles = collar_facing(d, binary, (lower, shared_neck)) if detailed_neck and original.endswith('_male_tpose.glb') else 0
    cap_inner_loops(lower, lr, axis)
    cap_inner_loops(upper, ur, -axis)
    lower['role'], upper['role'], bridge['role'] = 'shared_body', 'race_head', 'neck_join'
    meshes = {}
    for group in (lower, upper, bridge, shared_neck, wardrobe):
        write_group(d, binary, group, meshes)
    tail_report = None
    if source.stem.startswith('ssarathi_'):
        positions = {name: sw[node][:3, 3] for name, node in zip(sn, ss['joints'])}
        tail, tail_report = tail_graft(src, positions)
        tail['role'] = 'race_tail'
        write_group(d, binary, tail, meshes)
    # Retain the original fitted head band/cap with their original attributes.
    for node in sd['nodes']:
        if node.get('name') in ('wardrobe_head_band', 'wardrobe_head_cap') and 'mesh' in node:
            meshes[node['name']] = copy.deepcopy(sd['meshes'][node['mesh']]['primitives'])
    parent = next(i for i, node in enumerate(d['nodes'])
                  if any('mesh' in d['nodes'][j] for j in node.get('children', [])))
    old_nodes = {node['name']: i for i, node in enumerate(d['nodes'])
                 if node.get('name') in (*PARTS, 'wardrobe_head_band', 'wardrobe_head_cap')}
    for node in d['nodes']:
        node.pop('mesh', None); node.pop('skin', None)
    d['meshes'] = []
    for name, primitives in meshes.items():
        d['meshes'].append({'name': name, 'primitives': primitives})
        if name in old_nodes:
            d['nodes'][old_nodes[name]].update(mesh=len(d['meshes'])-1, skin=0)
        else:
            d['nodes'].append({'name': name, 'mesh': len(d['meshes'])-1, 'skin': 0})
            d['nodes'][parent].setdefault('children', []).append(len(d['nodes'])-1)
    d['asset'].setdefault('extras', {})['sharedBodyShape'] = {
        'version': 2, 'neckBase': {'startM': -.060, 'radiusM': .150}, 'template': template.stem, 'templateSHA256': input_hashes[1],
        'headSourceSHA256': input_hashes[0], 'lowerCutM': LOWER_CUT, 'upperCutM': upper_cut,
        'bodyCutMode': 'neck-plane' if source_body else 'chest-adaptor',
        'toolSHA256': digest(__file__)}
    if detailed_neck:
        d['asset']['extras']['sharedBodyShape']['neckRefinement'] = {
            'profile': 'boundary-tangent', 'texture': 'source-scale-collar-extension',
            'collarFacingTriangles': facing_triangles, 'version': 1}
        if texture_source is not None:
            d['asset']['extras']['sharedBodyShape']['neckRefinement']['textureGeometrySHA256'] = digest(texture_source)
    d, binary = g.compact(d, bytes(binary))
    if (digest(source), digest(template)) != input_hashes:
        raise ValueError('A body input changed during generation')
    out.parent.mkdir(parents=True, exist_ok=True)
    g.write(out, d, binary)
    report = {'source': str(source), 'sourceSHA256': digest(source), 'template': str(template),
              'templateSHA256': digest(template), 'outputSHA256': digest(out),
              'lowerBoundaryLoops': list(map(len, lr)), 'upperBoundaryLoops': list(map(len, ur)),
              'colourTransfer': colour,
              'headWardrobeTrianglesReclassifiedAsSkin': head_wardrobe,
              'tail': tail_report,
              'status': 'candidate: requires visual/animation review',
              'toolSHA256': digest(__file__)}
    out.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--template', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--texture-source', type=Path)
    args = ap.parse_args()
    print(json.dumps(run(args.source, args.template, args.out, args.texture_source), indent=2))
