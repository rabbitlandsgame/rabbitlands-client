"""Fit wardrobe and authored hair to an assembled canonical body.

Writes review candidates to a separate directory. Skeletons, skin, textures and
non-shirt garments are preserved. Shader normal-grow is baked using a welded
displacement field, retaining the source's faceted shading without tearing UV
or material seams. The collar follows the reconstructed neck and its weights.

Race hair (P5, 2026-10): `--race <slug>` refits the nine styles of the model's
`hairStyles` (parted, long, buns, buzzed, bob, ponytail, braid, topknot,
mohawk) from the raw `native/hair/<style>_<sex>.glb` onto an installed race
body, into a scratch `--out`. The raw styles are only read (never
`expand_hairstyles author`) and no client file is written. Race bodies alone
get the `tuck_ears` post-pass, which pulls hair under pointed ears and the
Ssarathi head spikes; Human hair (fit_human_hair.py) and every other caller of
`fit_hair` stay bit-for-bit. Each body's report gates the bind pose, the crown
rays and the ear-edge crossings. `--race <slug> --install` copies a gated fit
into `native/hair/fitted/`, updates the catalog's `fittedHair` and
`validation.results` and drops the retired `hairAllowsProtrusions` from
models.json (see race_hair_skull.py).

    python eloria-assets/tools/fit_character_appearance.py --race votary_male --out <scratch> [--jobs 3]
    python eloria-assets/tools/fit_character_appearance.py --race votary_male --out <scratch> --install
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter, grey_dilation
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

import equipment_authoring as ea
from shared_player_bodies import append_array, dense_weights, sparse_weights, clip, write_group, append_view
from verify_shared_player_bodies import primitives, sha
sys.path.insert(0, str(Path(__file__).parent / "tpose_bodies/vendor"))
import glbkit as g


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def weld(points):
    # Clipping creates copies across material and UV boundaries with float32
    # roundoff. Use proximity, rather than rounding bins that split close pairs.
    parent = np.arange(len(points))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in sorted(cKDTree(points).query_pairs(2e-6)):
        a, b = root(i), root(j)
        parent[max(a, b)] = min(a, b)
    return np.unique([root(i) for i in range(len(points))], return_inverse=True)[1]


def average(values, groups):
    result = np.zeros((groups.max()+1, values.shape[1]))
    np.add.at(result, groups, values)
    result /= np.bincount(groups)[:, None]
    return result[groups]


def ray_surface(mesh, origins, directions):
    locations, rays, triangles = mesh.ray.intersects_location(
        origins, directions, multiple_hits=True)
    distance = np.full(len(origins), -np.inf)
    hit_face = np.full(len(origins), -1, dtype=int)
    hit_point = np.zeros_like(origins)
    if not len(rays):
        return distance, hit_face, hit_point
    lengths = np.einsum('ij,ij->i', locations-origins[rays], directions[rays])
    # Outermost hit closes cracks even where a source contains internal faces.
    for index in np.argsort(lengths):
        ray = rays[index]
        distance[ray] = lengths[index]
        hit_face[ray] = triangles[index]
        hit_point[ray] = locations[index]
    return distance, hit_face, hit_point


def combined(parts):
    arrays, faces, offset = [], [], 0
    for _, _, a, f in parts:
        ids = np.unique(f)
        remap = np.full(len(a['POSITION']), -1)
        remap[ids] = np.arange(len(ids))
        arrays.append({k: v[ids] for k, v in a.items()})
        faces.append(remap[f]+offset)
        offset += len(ids)
    return {k: np.concatenate([a[k] for a in arrays]) for k in arrays[0]}, np.concatenate(faces)


def fit_shirt(d, binary):
    parts = list(primitives(d, bytes(binary)))
    a, faces = combined([p for p in parts if p[0] == 'wardrobe_shirt'])
    original = a['POSITION'].copy()
    groups = weld(original)
    v = average(original, groups)
    normals = unit(average(a['NORMAL'], groups))
    # Average complete distributions before reducing to four weights, so UV
    # seams remain closed in animation as well as the rest pose.
    weights = average(dense_weights(a), groups)
    moved = v + .011 * normals
    skin, sf = combined([p for p in parts if p[0] == 'body' and p[1]=='neck_join'])
    world = ea.global_matrices(d)
    neck = next(i for i,n in enumerate(d['nodes']) if n.get('name') == 'neck_01')
    head = next(i for i,n in enumerate(d['nodes']) if n.get('name') == 'Head')
    origin = world[neck][:3,3]
    axis = world[head][:3,3]-origin
    axis /= np.linalg.norm(axis)
    height = (v-origin)@axis
    centres = origin + height[:,None]*axis
    radial = v-centres
    radius = np.linalg.norm(radial,axis=1)
    collar = np.flatnonzero((height > -.085) & (radius < .18))
    mesh = trimesh.Trimesh(skin['POSITION'], sf, process=False)
    direction = unit(radial[collar])
    near_axis = radius[collar] < .025
    outward = normals[collar] - (normals[collar]@axis)[:,None]*axis
    direction[near_axis] = unit(outward[near_axis])
    distance, face, hit = ray_surface(mesh, centres[collar], direction)
    valid = face >= 0
    collar, distance, face, hit, direction = (
        x[valid] for x in (collar,distance,face,hit,direction))
    current_radius = np.einsum('ij,ij->i', moved[collar]-centres[collar], direction)
    # The source also has folded inner collar faces close to the neck axis.
    # They must not be projected across the entire torso to the opposite wall.
    deficit = np.clip(distance + .012-current_radius, 0, .045)
    moved[collar] += deficit[:,None]*direction
    # Skin under the collar is reconstructed independently of the old shirt.
    # Follow its deformation near contact, fading into the original shoulder.
    bary = trimesh.triangles.points_to_barycentric(mesh.triangles[face],hit)
    skin_weights = dense_weights(skin)
    target_weights = np.einsum('ij,ijk->ik', bary, skin_weights[sf[face]])
    blend = np.clip((height[collar]+.025)/.06, 0, 1)
    blend = blend*blend*(3-2*blend)
    weights[collar] = weights[collar]*(1-blend[:,None])+target_weights*blend[:,None]
    moved = average(moved, groups)
    weights = average(weights, groups)
    a['POSITION'] = moved.astype('<f4')
    a['JOINTS_0'], a['WEIGHTS_0'] = sparse_weights(weights)
    # Each primitive gets a compact private attribute set; changing a shared
    # POSITION accessor would also move the exposed body and other garments.
    cursor = 0
    shirt = next(m for m in d['meshes'] if m['name']=='wardrobe_shirt')
    for p, source in zip(shirt['primitives'],[p for p in parts if p[0]=='wardrobe_shirt']):
        ids = np.unique(source[3]); count = len(ids)
        remap = np.full(len(source[2]['POSITION']),-1);remap[ids]=np.arange(count)
        p['attributes'] = {k: append_array(d,binary,value[cursor:cursor+count],
            'VEC'+str(value.shape[1]),5123 if k=='JOINTS_0' else 5126)
            for k,value in a.items() if k != 'TANGENT'}
        p['indices'] = append_array(d,binary,remap[source[3]].ravel(),'SCALAR',5125)
        cursor += count
    # Close small internal holes in the source; retain the collar, cuffs and
    # hem openings. Isolated source triangles are details, not missing faces.
    gf=groups[faces]
    directed=np.concatenate([gf[:,[0,1]],gf[:,[1,2]],gf[:,[2,0]]])
    edges,first,counts=np.unique(np.sort(directed,axis=1),axis=0,return_index=True,return_counts=True)
    boundary=directed[first[counts==1]]
    _,representatives=np.unique(groups,return_index=True)
    patches=[]
    for component in trimesh.graph.connected_components(boundary,min_len=1):
        if len(component)>18 or np.abs(v[representatives[component],0]).max()>.69:
            continue
        if np.isin(gf,component).all(1).any():
            continue
        links=boundary[np.isin(boundary,component).all(1)]
        if len(links)!=len(component):continue
        following={int(x):int(y) for x,y in links}
        if len(following)!=len(component):continue
        loop=[int(component[0])]
        while len(loop)<len(component) and loop[-1] in following:
            nxt=following[loop[-1]]
            if nxt in loop:break
            loop.append(nxt)
        if len(loop)!=len(component):continue
        ids=representatives[loop]
        for i in range(1,len(ids)-1):patches.append([ids[0],ids[i+1],ids[i]])
    if patches:
        repairs={'a':{k:value for k,value in a.items() if k!='TANGENT'},
            'f':{('wardrobe_shirt',shirt['primitives'][0]['material']):np.array(patches)},
            'role':'wardrobe_repairs'}
        repair_meshes={};write_group(d,binary,repairs,repair_meshes)
        shirt['primitives']+=repair_meshes['wardrobe_shirt']
    # A narrow fitted facing sits beneath the old collar, whose source opening
    # extends down the back. It covers the reconstructed neck below the collar
    # while preserving the lower V at the throat. It shares the neck's weights.
    relative=skin['POSITION']-origin
    travel=relative@axis
    radial=relative-travel[:,None]*axis
    forward=unit(radial)@np.array([0.,0.,1.])
    neckline=.0375-.0375*forward
    lining=clip({'a':skin,'f':{('wardrobe_shirt',0):sf}},travel-neckline,False)
    lining_groups=weld(lining['a']['POSITION'])
    lining['a']['POSITION']=(lining['a']['POSITION']+.006*unit(average(lining['a']['NORMAL'],lining_groups))).astype('<f4')
    # A neutral cloth texel tints with the other primitives without sampling
    # the skin atlas that the anatomical neck uses.
    import io
    from PIL import Image
    encoded=io.BytesIO();Image.new('RGB',(1,1),(235,235,235)).save(encoded,format='PNG')
    d['images'].append({'mimeType':'image/png','bufferView':append_view(d,binary,encoded.getvalue())})
    d['textures'].append({'source':len(d['images'])-1})
    d['materials'].append({'name':'Collar facing','doubleSided':True,'pbrMetallicRoughness':{
        'baseColorTexture':{'index':len(d['textures'])-1},'metallicFactor':0.,'roughnessFactor':.85}})
    lining['f']={('wardrobe_shirt',len(d['materials'])-1):next(iter(lining['f'].values()))}
    lining['role']='wardrobe_lining'
    lining_meshes={};write_group(d,binary,lining,lining_meshes)
    shirt['primitives']+=lining_meshes['wardrobe_shirt']
    return {'vertices':len(v),'weldedVertices':int(groups.max()+1),
        'patchedTriangles':len(patches),'liningTriangles':len(next(iter(lining['f'].values()))),
        'collarPushedVertices':int((deficit>0).sum()),
        'maximumDisplacementM':float(np.linalg.norm(moved-original,axis=1).max())}


def head_data(d,b):
    parts = [p for p in primitives(d,b) if p[1]=='race_head']
    a,f=combined(parts)
    hi=next(i for i,n in enumerate(d['nodes']) if n.get('name')=='Head')
    matrix=ea.global_matrices(d)[hi]
    v=(a['POSITION']-matrix[:3,3])@matrix[:3,:3]
    return trimesh.Trimesh(v,f,process=False), dense_weights(a), matrix


HAIR_STYLES = ('parted', 'long', 'buns', 'buzzed', 'bob', 'ponytail', 'braid', 'topknot', 'mohawk')
# Starting placement when a model's `hairFit` is empty, as on every race body
# and regenerated Human (`{}`): the placement the race hair has always been
# fitted with; each style's crown height and the radial push settle the rest.
DEFAULT_HAIR_FIT = {'scale': [1., 1., 1.], 'offset': [0., 0., -.015]}


def fit_hair(source, out, head, base_fit, body, body_binary, adjust=None):
    """Fit one raw style to `head` (Head-local cranium, its weights, the Head
    matrix). `adjust`, when given, receives every primitive's Head-local
    vertices and faces after the radial push and returns moved vertices;
    weights and normals are then taken at the moved positions."""
    skull, skull_weights, head_matrix = head
    base_fit = base_fit or DEFAULT_HAIR_FIT
    d,b=g.read(source);binary=bytearray(b)
    scale=np.array(base_fit['scale'],dtype=float);offset=np.array(base_fit['offset'],dtype=float)
    # Reference caps have different crown heights. Use each style's crown,
    # excluding side buns and long locks from the measurement.
    p=d['meshes'][0]['primitives'][0]
    raw=g.accessor(d,b,p['attributes']['POSITION'])
    skull_core=skull.vertices[(abs(skull.vertices[:,0])<.045)&(skull.vertices[:,1]>.07)]
    top=np.percentile(skull_core[:,1],99)
    cap=raw[(abs(raw[:,0])<.04)&(abs(raw[:,2])<.055)]
    cap_top = d.get('asset', {}).get('extras', {}).get('hairCapTopM', cap[:,1].max())
    scale[1]=(top+.007)/cap_top
    centre=np.array([offset[0],top-.075,offset[2]])
    maximum=0.
    fitted=[]
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            attributes={k:g.accessor(d,b,index) for k,index in p['attributes'].items()}
            f=g.accessor(d,b,p['indices']).astype(int).reshape(-1,3)
            # Curved skulls and raised scales can emerge between the original
            # cap's vertices. Subdivide without changing the authored UVs or
            # silhouette, then fit those extra surface samples too.
            edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
            unique,inverse=np.unique(edges,axis=0,return_inverse=True)
            midpoint=inverse.reshape(3,-1).T+len(attributes['POSITION'])
            for k,values in attributes.items():
                attributes[k]=np.concatenate([values,values[unique].mean(1)])
            a0,b0,c0=f.T;ab,bc,ca=midpoint.T
            f=np.concatenate([np.stack([a0,ab,ca],1),np.stack([b0,bc,ab],1),
                np.stack([c0,ca,bc],1),np.stack([ab,bc,ca],1)])
            v=attributes['POSITION']*scale+offset
            direction=unit(v-centre)
            distance,_,_=ray_surface(skull,np.broadcast_to(centre,v.shape),direction)
            radius=np.linalg.norm(v-centre,axis=1)
            push=np.maximum(distance+.010-radius,0)
            push[~np.isfinite(push)]=0
            maximum=max(maximum,float(push.max()))
            v+=push[:,None]*direction
            groups=weld(v)
            v=average(v,groups)
            fitted.append((p,attributes,f,v,groups))
    if adjust is not None:
        # One field over every primitive (a style's locks are primitives of
        # their own); welded copies share a position, so they move together.
        # `adjust` may also return a face mask per primitive: those faces are
        # removed, with the vertices only they used.
        moved=adjust([x[3] for x in fitted],[x[2] for x in fitted])
        drop=[None]*len(fitted)
        if isinstance(moved,tuple):
            moved,drop=moved
        kept=[]
        for (p,attributes,f,_,groups),v,gone in zip(fitted,moved,drop):
            if gone is not None and gone.any():
                f=f[~gone]
                used=np.unique(f)
                remap=np.full(len(v),-1);remap[used]=np.arange(len(used))
                f=remap[f];v=v[used]
                attributes={k:values[used] for k,values in attributes.items()}
                groups=np.unique(groups[used],return_inverse=True)[1].ravel()
            kept.append((p,attributes,f,v,groups))
        fitted=kept
    for p,attributes,f,v,groups in fitted:
        _, _, nearest = trimesh.proximity.closest_point(skull, v)
        closest = trimesh.triangles.closest_point(skull.triangles[nearest], v)
        bary = trimesh.triangles.points_to_barycentric(skull.triangles[nearest],closest)
        weights = np.einsum('ij,ijk->ik',bary,skull_weights[skull.faces[nearest]])
        joints,weights=sparse_weights(average(weights,groups))
        # Area-weighted normals shared at UV seams, with existing UVs and
        # all authored faces retained.
        face_normal=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
        n=np.zeros_like(v)
        for c in range(3):np.add.at(n,f[:,c],face_normal)
        n=unit(average(n,groups))
        v=v@head_matrix[:3,:3].T+head_matrix[:3,3]
        n=n@head_matrix[:3,:3].T
        p['attributes']['POSITION']=append_array(d,binary,v.astype('<f4'),'VEC3',5126)
        p['attributes']['NORMAL']=append_array(d,binary,n.astype('<f4'),'VEC3',5126)
        p['attributes']['JOINTS_0']=append_array(d,binary,joints,'VEC4',5123)
        p['attributes']['WEIGHTS_0']=append_array(d,binary,weights,'VEC4',5126)
        p['attributes'].pop('TANGENT',None)
        for k,values in attributes.items():
            if k not in ('POSITION','NORMAL','TANGENT'):
                p['attributes'][k]=append_array(d,binary,values.astype('<f4'),'VEC'+str(values.shape[1]),5126)
        p['indices']=append_array(d,binary,f.ravel(),'SCALAR',5125)
    # Hair follows the same weighted head surface as the skin. A rigid Head
    # attachment pulls away from occipital vertices blended with neck_01.
    node_offset=len(d['nodes'])
    for node in d['nodes']:
        if 'mesh' in node:node['skin']=0
    for source_node in body['nodes']:
        node=copy.deepcopy(source_node)
        node.pop('mesh',None);node.pop('skin',None)
        if 'children' in node:node['children']=[i+node_offset for i in node['children']]
        d['nodes'].append(node)
    source_skin=body['skins'][0]
    skin=copy.deepcopy(source_skin)
    skin['joints']=[i+node_offset for i in source_skin['joints']]
    if 'skeleton' in skin:skin['skeleton']+=node_offset
    binds=ea.accessor_array(body,body_binary,source_skin['inverseBindMatrices'])
    skin['inverseBindMatrices']=append_array(d,binary,binds,'MAT4',5126)
    d['skins']=[skin]
    d['scenes'][d.get('scene',0)]['nodes'] += [i+node_offset for i in body['scenes'][body.get('scene',0)]['nodes']]
    d.setdefault('asset',{}).setdefault('extras',{})['headFit']={
        'sourceSHA256':sha(source),'clearanceM':.010}
    d,binary=g.compact(d,bytes(binary));g.write(out,d,binary)
    return {'source':str(source),'sha256':sha(out),'maxRadialCorrectionM':maximum}


# --- Race hair (P5) -------------------------------------------------------
# tuck_ears decides per lateral feature piece (one ear, one spike), working on
# a 1-degree azimuth/elevation grid about the cranium centre. A piece the
# fitted hair does not cross is left alone. A crossed piece smaller than
# COVER_MAX_AREA_M2 that the hair can cover with a bulge of at most COVER_MAX_M
# (Ssarathi female spikes, crystal stubs) is covered: its bins push the hair
# out to COVER_CLEARANCE_M beyond the piece (COVER_DILATE_DEG dilation,
# COVER_BLUR_DEG blur), keeping its thickness. Any other crossed piece - ears,
# even the Stoneborn's small round ones (a cover reads as ear muffs, on pointed
# ears as helmet wings), and Ssarathi male spikes - is tucked: inside its footprint,
# dilated by TUCK_DILATE_DEG, hair above the piece's root (less 2 mm) is
# pulled to TUCK_CLEARANCE_M under the root at any radius, since a lock left
# over the ear in one bin would be joined to tucked hair in the next by a
# triangle through the ear. The dilation is wider than the coarse long-hair
# triangles for the same reason (4 degrees left 2-62 crossings per style). A
# TUCK_BLUR_DEG blur of the pulls draws neighbouring hair in by at most
# TUCK_EDGE_M so the notch has no step. A piece still crossed after a round,
# or first crossed by another piece's tuck, is tucked, for up to TUCK_ROUNDS.
# Tucking can cut a piece of hair off from the rest of its lock - the tip of
# a lock that hangs past the ear, a shred between ear and crystals - which
# would float on the jaw or cheek; such a cut-off part, smaller than
# ISLAND_MAX_M2, is removed (see _islands).
TUCK_DEG = 1.
TUCK_CLEARANCE_M, TUCK_DILATE_DEG, TUCK_BLUR_DEG, TUCK_EDGE_M, TUCK_ROUNDS = .003, 8, 3, .004, 8
ISLAND_MAX_M2 = 12e-4
COVER_MAX_M, COVER_MAX_AREA_M2, COVER_CLEARANCE_M, COVER_DILATE_DEG, COVER_BLUR_DEG = .018, 8e-4, .004, 6, 5
# Gates (P5): ear edges (lateral feature triangle edges) that cross the fitted
# hair surface. Long and buns may hang locks past the ear root; their limit
# needs a render review.
EAR_CROSSINGS_LIMIT = {'long': 180, 'buns': 180}
# The crown rays of test_character_appearance_fit.py: hair must lie more than
# CROWN_CLEARANCE_M above the bald cranium (scalp, or the race_head skin that
# caps a feature root) under each of these world (x, z).
CROWN_RAYS = ((0, 0), (-.012, 0), (.012, 0), (0, -.012), (0, .012))
CROWN_CLEARANCE_M = .001


def _tuck_grid(local):
    r = np.linalg.norm(local, axis=1)
    azimuth = np.degrees(np.arctan2(local[:, 0], local[:, 2])) % 360
    elevation = np.degrees(np.arcsin(np.clip(local[:, 1]/np.maximum(r, 1e-9), -1, 1)))+90
    na, ne = int(360/TUCK_DEG), int(180/TUCK_DEG)
    return (np.minimum((azimuth/TUCK_DEG).astype(int), na-1),
            np.minimum((elevation/TUCK_DEG).astype(int), ne-1), r)


def _extent(triangles, centre, shape):
    fa, fe, fr = _tuck_grid(triangles.reshape(-1, 3)-centre)
    tip = np.zeros(shape); np.maximum.at(tip, (fa, fe), fr)
    root = np.full(shape, np.inf); np.minimum.at(root, (fa, fe), fr)
    return tip, root


def _cover_field(every, centre, triangles):
    """Radial outward moves (>= 0) lifting the hair COVER_CLEARANCE_M clear of
    `triangles`, its whole thickness at once."""
    shape = (int(360/TUCK_DEG), int(180/TUCK_DEG))
    k = 2*int(round(COVER_DILATE_DEG/TUCK_DEG))+1
    tip = grey_dilation(_extent(triangles, centre, shape)[0], size=(k, k), mode='wrap')
    ha, he, hr = _tuck_grid(every-centre)
    inner = np.full(shape, np.inf); np.minimum.at(inner, (ha, he), hr)
    inner = np.where(np.isfinite(inner), inner, np.nan)
    # A bin without a hair sample borrows the nearest smaller radius.
    borrowed = -grey_dilation(np.nan_to_num(-inner, nan=-1.), size=(k, k), mode='wrap')
    inner = np.where(np.isnan(inner), borrowed, inner)
    delta = np.where(tip > 0, np.maximum(0, tip+COVER_CLEARANCE_M-inner), 0)
    delta = np.maximum(delta, gaussian_filter(grey_dilation(delta, size=(k, k), mode='wrap'),
                                              COVER_BLUR_DEG/TUCK_DEG, mode='wrap'))
    return delta[ha, he]


def _tuck_field(every, centre, triangles):
    """Radial inward moves (<= 0) pulling the hair under `triangles`, and
    which vertices end under a piece's root (the rest only follow the blur)."""
    shape = (int(360/TUCK_DEG), int(180/TUCK_DEG))
    tip, root = _extent(triangles, centre, shape)
    k = 2*int(round(TUCK_DILATE_DEG/TUCK_DEG))+1
    tip = grey_dilation(tip, size=(k, k), mode='wrap')
    root = -grey_dilation(np.where(np.isfinite(root), -root, -np.inf), size=(k, k), mode='wrap')
    ha, he, hr = _tuck_grid(every-centre)
    across = (tip[ha, he] > 0) & (hr > root[ha, he]-.002)
    with np.errstate(invalid='ignore'):
        want = np.where(across, np.minimum(0, root[ha, he]-TUCK_CLEARANCE_M-hr), 0.)
    grid = np.zeros(shape); np.minimum.at(grid, (ha, he), want)
    soft = gaussian_filter(grid, TUCK_BLUR_DEG/TUCK_DEG, mode='wrap')
    return np.where(across, np.minimum(want, soft[ha, he]), np.maximum(soft[ha, he], -TUCK_EDGE_M)), across


def _islands(points, faces, under):
    """Hair vertices the tuck cut off: parts of a connected piece of hair
    (welded copies joined) that no longer reach the piece's topmost hair
    except through vertices tucked `under` a root, touch such a vertex, and
    cover less than ISLAND_MAX_M2. Returns (vertex mask, folded area,
    largest cut-off part left because it is bigger)."""
    _, node = np.unique(np.round(points, 7), axis=0, return_inverse=True)
    node = node.ravel()
    n = int(node.max())+1
    tri = node[faces]
    edges = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    def components(e):
        graph = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
        return connected_components(graph, directed=False)[1]
    hidden = np.zeros(n, bool); hidden[node[under]] = True
    whole = components(edges)
    part = components(edges[~hidden[edges].any(1)])
    touching = np.zeros(n, bool)
    mixed = edges[hidden[edges[:, 0]] != hidden[edges[:, 1]]]
    touching[mixed[~hidden[mixed]]] = True
    corner = np.zeros((n, 3)); corner[node] = points
    area = np.linalg.norm(np.cross(corner[tri[:, 1]]-corner[tri[:, 0]], corner[tri[:, 2]]-corner[tri[:, 0]]), axis=1)/2
    open_ = ~hidden[tri].any(1)
    part_area = np.bincount(part[tri[open_, 0]], area[open_], minlength=n)
    # Each piece keeps the part holding its topmost untucked hair.
    shown = np.flatnonzero(~hidden)
    top = {}
    for v in shown[np.argsort(corner[shown, 1])]:
        top[whole[v]] = part[v]
    cut = np.zeros(n, bool)
    cut[shown] = [part[v] != top[whole[v]] for v in shown]
    reach = np.zeros(n, bool); reach[part[touching]] = True
    cut &= reach[part]
    small = cut & (part_area[part] < ISLAND_MAX_M2)
    folded = float(sum(part_area[p] for p in np.unique(part[small])))
    left = max((float(part_area[p]) for p in np.unique(part[cut & ~small])), default=0.)
    return small[node], folded, left


def tuck_ears(vertices, faces, lateral):
    """Clear Head-local hair (`vertices`/`faces`, one array per primitive) of
    the lateral features `(triangles, centre, pieces)` of
    race_hair_skull.lateral_features: tuck it under tall pieces and cover low
    ones (see the constants above). A no-op where no piece crosses the hair."""
    triangles, centre, labels = lateral
    every = np.concatenate(vertices)
    offsets = np.cumsum([0]+[len(v) for v in vertices[:-1]])
    joined = np.concatenate([f+o for f, o in zip(faces, offsets)])
    local = every-centre
    radius = np.linalg.norm(local, axis=1)
    def crossed(piece, points):
        return ear_crossings(triangles[labels == piece], trimesh.Trimesh(points, joined, process=False)) > 0
    mode, moved, dv, under = {}, every, np.zeros(len(every)), np.zeros(len(every), bool)
    for round_ in range(TUCK_ROUNDS):
        changed = False
        for piece in np.unique(labels):
            if mode.get(piece) == 'tuck' or not crossed(piece, moved):
                continue
            if piece in mode or round_:
                mode[piece] = 'tuck'
            else:
                own = triangles[labels == piece]
                area = np.linalg.norm(np.cross(own[:, 1]-own[:, 0], own[:, 2]-own[:, 0]), axis=1).sum()/2
                small = area < COVER_MAX_AREA_M2 and _cover_field(every, centre, own).max(initial=0.) <= COVER_MAX_M
                mode[piece] = 'cover' if small else 'tuck'
            changed = True
        if not changed:
            break
        dv, under = np.zeros(len(every)), np.zeros(len(every), bool)
        for kind in ('cover', 'tuck'):
            chosen = triangles[np.isin(labels, [p for p, m in mode.items() if m == kind])]
            if not len(chosen):
                continue
            if kind == 'cover':
                dv = np.maximum(dv, _cover_field(every, centre, chosen))
            else:
                # A tuck wins over a neighbouring cover where both reach.
                step, under = _tuck_field(every, centre, chosen)
                dv = np.where(step < 0, step, dv)
        moved = every.copy()
        on = dv != 0
        moved[on] = centre+local[on]*(1+dv[on]/np.maximum(radius[on], 1e-9))[:, None]
    island, folded, left = _islands(every, joined, under) if under.any() else (np.zeros(len(every), bool), 0., 0.)
    # A cut-off part is removed: its triangles join only tucked and cut-off
    # vertices, so the hair that stays ends under the root. (Folding its
    # vertices onto tucked ones left zero-area triangles and zero normals.)
    gone = island[joined].any(1)
    stats = {'tuckedPieces': sorted(int(p) for p, m in mode.items() if m == 'tuck'),
             'coveredPieces': sorted(int(p) for p, m in mode.items() if m == 'cover'),
             'pulledVertices': int((dv < -1e-5).sum()), 'maxPullM': float(max(0., -dv.min(initial=0.))),
             'pushedVertices': int((dv > 1e-5).sum()), 'maxPushM': float(max(0., dv.max(initial=0.))),
             'foldedVertices': int(island.sum()), 'foldedAreaM2': round(folded, 6),
             'largestCutOffLeftM2': round(left, 6), 'removedTriangles': int(gone.sum())}
    counts = np.cumsum([0]+[len(f) for f in faces])
    return np.split(moved, offsets[1:]), [gone[a:b] for a, b in zip(counts[:-1], counts[1:])], stats


def ear_crossings(triangles, mesh):
    """Lateral feature edges that pass through `mesh` (same space)."""
    if not len(triangles):
        return 0
    start = np.concatenate([triangles[:, i] for i in range(3)])
    end = np.concatenate([triangles[:, (i+1) % 3] for i in range(3)])
    direction = end-start
    length = np.linalg.norm(direction, axis=1)
    direction /= np.maximum(length, 1e-12)[:, None]
    engine = trimesh.ray.ray_triangle.RayMeshIntersector(mesh)
    location, ray, _ = engine.intersects_location(start, direction, multiple_hits=False)
    return int((np.linalg.norm(location-start[ray], axis=1) < length[ray]-1e-7).sum())


def _surface(document, binary, keep):
    vertices, faces, offset = [], [], 0
    for name, role, a, f in primitives(document, binary):
        if keep(name, role):
            vertices.append(a['POSITION']); faces.append(f+offset); offset += len(a['POSITION'])
    return trimesh.Trimesh(np.concatenate(vertices), np.concatenate(faces), process=False)


def crown_clearance(body, body_binary, hair, hair_binary):
    """Per crown ray: hair height above the bald cranium (None: no hair hit),
    or no entry where the ray misses the cranium. Mirrors the crown test of
    test_character_appearance_fit.py: the hair is the style's first mesh."""
    cranium = _surface(body, body_binary, lambda name, role: name == 'scalp' or (name == 'body' and role == 'race_head'))
    first = hair['meshes'][0]['name']
    worn = _surface(hair, hair_binary, lambda name, role: name == first)
    origins = np.array([[x, 2., z] for x, z in CROWN_RAYS])
    down = np.tile([0., -1., 0.], (len(origins), 1))
    def heights(mesh):
        location, ray, _ = mesh.ray.intersects_location(origins, down, multiple_hits=False)
        return {int(r): float(y) for r, y in zip(ray, location[:, 1])} if len(ray) else {}
    under, over = heights(cranium), heights(worn)
    return {r: (round(over[r]-y, 5) if r in over else None) for r, y in sorted(under.items())}


def fit_race_hair(root, slug, out):
    """Fit the nine styles to an installed race body into `out/<slug>/` and
    write `out/<slug>.config.json` (for ELORIA_APPEARANCE_CANDIDATES) and the
    gated report `out/<slug>.hair.json`."""
    from race_hair_skull import hair_skull, head_matrix, lateral_features
    client = root/'godot-client'
    if 'godot-client' in out.resolve().parts:
        raise ValueError('Fit into a scratch folder; --install copies reviewed fits')
    config = json.loads((client/'data/actors/models.json').read_text())['models'][slug]
    if 'bodyTemplate' not in config or slug.startswith('luminous_'):
        raise ValueError(f'{slug}: race bodies only; Human hair is fitted by fit_human_hair.py')
    sex = config['gender']
    body_path = client/config['scene'].removeprefix('res://')
    d, b = g.read(body_path)
    head = hair_skull(d, b, slug)
    lateral = lateral_features(d, b)
    matrix = head_matrix(d)
    lateral_world = lateral[0]@matrix[:3, :3].T+matrix[:3, 3]
    binds = ea.accessor_array(d, b, d['skins'][0]['inverseBindMatrices'])
    folder = out/slug
    folder.mkdir(parents=True, exist_ok=True)
    styles = list(config['hairStyles'])
    report = {'slug': slug, 'body': body_path.relative_to(root).as_posix(), 'bodySHA256': sha(body_path),
              'lateralTriangles': len(lateral[0]), 'lateralPieces': int(lateral[2].max(initial=-1))+1, 'styles': {}}
    for index, style in enumerate(HAIR_STYLES, 1):
        name = f'{slug}_{style}_{sex}.glb'
        if styles[index] != f'res://assets/actors/native/hair/fitted/{name}':
            raise ValueError(f'{slug} style {index} is {styles[index]}, not {name}')
        tuck = {}
        def adjust(vertices, faces):
            offsets = np.cumsum([0]+[len(v) for v in vertices[:-1]])
            joined = np.concatenate([f+o for f, o in zip(faces, offsets)])
            untucked = trimesh.Trimesh(np.concatenate(vertices), joined, process=False)
            tuck['earCrossingsUntucked'] = ear_crossings(lateral[0], untucked)
            moved, gone, tuck['stats'] = tuck_ears(vertices, faces, lateral)
            return moved, gone
        target = folder/name
        result = fit_hair(client/f'assets/actors/native/hair/{style}_{sex}.glb', target, head,
                          config.get('hairFit'), d, b, adjust)
        hd, hb = g.read(target)
        crossings = ear_crossings(lateral_world, _surface(hd, hb, lambda name, role: True))
        crown = crown_clearance(d, b, hd, hb)
        hits = [v for v in crown.values() if v is not None]
        checks = {
            'bindPose': bool(np.array_equal(binds, ea.accessor_array(hd, hb, hd['skins'][0]['inverseBindMatrices']))),
            'crown': len(crown) >= 3 and len(hits) == len(crown) and min(hits) > CROWN_CLEARANCE_M,
            'earCrossings': crossings <= EAR_CROSSINGS_LIMIT.get(style, 0)}
        report['styles'][str(index)] = {
            'style': style, 'path': target.as_posix(), 'sha256': result['sha256'],
            'triangles': sum(hd['accessors'][p['indices']]['count']//3 for m in hd['meshes'] for p in m['primitives']),
            'maxRadialCorrectionM': result['maxRadialCorrectionM'], 'tuck': tuck['stats'],
            'earCrossingsUntucked': tuck['earCrossingsUntucked'], 'earCrossings': crossings,
            'earCrossingsLimit': EAR_CROSSINGS_LIMIT.get(style, 0),
            'crownClearanceM': {str(k): v for k, v in crown.items()}, 'checks': checks}
        styles[index] = target.resolve().as_posix()
        print(slug, style, json.dumps(checks), 'ear crossings', tuck['earCrossingsUntucked'], '->', crossings,
              'crown min %.4f' % (min(hits) if hits else float('nan')), flush=True)
    report['gatesPass'] = all(all(s['checks'].values()) for s in report['styles'].values())
    candidate = {'hairStyles': styles, 'hairFit': {}, 'hairSkinned': True,
                 'wardrobeBakedGrow': config['wardrobeBakedGrow']}
    (out/f'{slug}.config.json').write_text(json.dumps(candidate, indent=2)+'\n')
    (out/f'{slug}.hair.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def install_race_hair(root, slugs, out):
    """Copy gated race hair fits into native/hair/fitted/ and record them in
    the catalog (fittedHair sha256/triangles, validation.results); drops the
    retired `hairAllowsProtrusions` from those models."""
    from build_native_nymara_glbs import validate_glb
    client = root/'godot-client'
    paths = {'models': client/'data/actors/models.json', 'catalog': client/'data/actors/native_asset_catalog.json'}
    raw = {k: p.read_bytes() for k, p in paths.items()}
    models, catalog = json.loads(raw['models']), json.loads(raw['catalog'])
    results = catalog['validation']['results']
    plan = []
    for slug in slugs:
        config = models['models'][slug]
        if 'bodyTemplate' not in config or slug.startswith('luminous_'):
            raise ValueError(f'{slug}: race bodies only')
        report = json.loads((out/f'{slug}.hair.json').read_text())
        if not report['gatesPass']:
            raise ValueError(f'{slug}: the fit failed its gates; see {out/slug}.hair.json')
        if sha(root/report['body']) != report['bodySHA256'] or report['body'] != 'godot-client/'+config['scene'].removeprefix('res://'):
            raise ValueError(f'{slug}: the body changed since the fit; refit')
        for index, style in enumerate(HAIR_STYLES, 1):
            entry = catalog['fittedHair'][f'{slug}:{index}']
            candidate = Path(report['styles'][str(index)]['path'])
            target = client/'assets/actors/native/hair/fitted'/candidate.name
            key = target.relative_to(root).as_posix()
            if entry['path'] != key or config['hairStyles'][index] != 'res://'+target.relative_to(client).as_posix():
                raise ValueError(f'{slug} style {index}: {key} is not the registered file')
            if sha(candidate) != report['styles'][str(index)]['sha256']:
                raise ValueError(f'{candidate} changed after its gates ran')
            # Never overwrite a file someone else changed after the catalog recorded it.
            if sha(target) not in (entry['sha256'], sha(candidate)):
                raise ValueError(f'{key} differs from its catalog entry; resolve before installing')
            plan.append((slug, index, candidate, target, key, entry))
    for slug, index, candidate, target, key, entry in plan:
        shutil.copyfile(candidate, target)
        fitted, _ = g.read(target)
        entry['sha256'] = sha(target)
        entry['triangles'] = sum(fitted['accessors'][p['indices']]['count']//3 for m in fitted['meshes'] for p in m['primitives'])
        results[key] = validate_glb(target)
        models['models'][slug].pop('hairAllowsProtrusions', None)
    catalog['validation']['files'] = len(results)
    # Other tools edit these files too: write only over the bytes read above.
    for k, p in paths.items():
        if p.read_bytes() != raw[k]:
            raise ValueError(f'{p} changed during the install; the GLBs are copied, rerun --install')
    for k, data in (('models', models), ('catalog', catalog)):
        # json.dumps(indent=2)+"\n", in the line endings the checkout has.
        text = (json.dumps(data, indent=2)+'\n').encode()
        if b'\r\n' in raw[k]:
            text = text.replace(b'\n', b'\r\n')
        if text != raw[k]:
            paths[k].write_bytes(text)
    return {'installed': len(plan)}


def run(model, config, hair_root, out):
    if 'godot-client' in out.resolve().parts or (out/model.name).resolve()==model.resolve():
        raise ValueError('Use a separate scratch output; review before installing')
    out.mkdir(parents=True,exist_ok=True)
    d,b=g.read(model);binary=bytearray(b)
    if d['asset'].get('extras',{}).get('appearanceFit'):
        raise ValueError('Use the original input snapshot, not an already fitted output')
    head=head_data(d,b)
    body=copy.deepcopy(d)
    report={'sourceSHA256':sha(model),'shirt':fit_shirt(d,binary),'hair':{}}
    d['asset'].setdefault('extras',{})['appearanceFit']={'version':1,'bakedShirtGrowM':.011}
    d,binary=g.compact(d,bytes(binary));g.write(out/model.name,d,binary)
    styles=list(config['hairStyles'])
    for style in range(1,len(styles)):
        source=hair_root/Path(styles[style]).name
        target=out/(model.stem+'_'+source.name)
        report['hair'][str(style)]=fit_hair(source,target,head,config.get('hairFit'),body,b)
        styles[style]=str(target.resolve()).replace('\\','/')
    candidate={'hairStyles':styles,'hairFit':{},'hairSkinned':True,'wardrobeBakedGrow':['wardrobe_shirt']}
    (out/(model.stem+'.config.json')).write_text(json.dumps(candidate,indent=2)+'\n')
    (out/(model.stem+'.report.json')).write_text(json.dumps(report,indent=2)+'\n')
    return report


def _fit_race_job(job):
    return fit_race_hair(*job)['gatesPass']


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model',type=Path)
    ap.add_argument('--models',type=Path)
    ap.add_argument('--hair-root',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--race',action='append',help='race body slug (repeatable): fit its nine hair styles')
    ap.add_argument('--install',action='store_true',help='with --race: install the gated fits from --out')
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2],help='repository root')
    ap.add_argument('--jobs',type=int,default=1,help='bodies fitted in parallel (--race; at most 4)')
    args=ap.parse_args()
    if args.race:
        root=args.root.resolve()
        if args.install:
            print(json.dumps(install_race_hair(root,args.race,args.out)))
        else:
            # Each worker holds a body and nine fits (about 1.5 GB); four at most.
            with ProcessPoolExecutor(max(1,min(args.jobs,len(args.race),4))) as pool:
                passed=dict(zip(args.race,pool.map(_fit_race_job,[(root,s,args.out) for s in args.race])))
            print(json.dumps(passed))
            sys.exit(0 if all(passed.values()) else 1)
    else:
        if not (args.model and args.models and args.hair_root):
            ap.error('--model, --models and --hair-root are required without --race')
        config=json.loads(args.models.read_text())['models'][args.model.stem]
        print(json.dumps(run(args.model,config,args.hair_root,args.out)))
