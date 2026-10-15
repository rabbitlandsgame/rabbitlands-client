#!/usr/bin/env python3
"""Render consistent north-up cartography from the packaged GLB scene.

No source builder, manifest or framing is changed. Output directories contain
an RGB minimap, the same render with geometry-derived alpha, a coverage image,
and provenance. Geometry is traversed once through the active glTF scene,
including node transforms and instances. Invisible streaming thresholds and
legacy copied receiving scenery are omitted. Native regional albedo/UVs remain;
water uses one opaque atlas ink so oceans do not change color at map edges.

Requires numpy, Pillow and a C compiler. The frozen native raster source is
compiled into the content-addressed atlas cache for the current platform.

    python eloria-assets/tools/render_region_cartography.py \
        --regions four_gates crownwater amberwood sunmane_steppe \
        --output-dir work-output/cartography-preview

After reviewing the prototype, --all uses the 12 continent-layout entries.
The publication coordinator can add --apply after geometry is frozen to copy
the RGB image and RGBA cartography.webp into each package and record their
generator inputs. --output-dir must not be inside eloria-assets/maps.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import atlas_soft_ground

ROOT = Path(__file__).resolve().parents[2]
TOOLKIT = ROOT / 'eloria-assets/maps/nymara-regions/_toolkit'
sys.path.insert(0, str(TOOLKIT))
from amberwood import mesh as M, render as R

STYLE_VERSION = 4
REPEAT, CLAMP_TO_EDGE = 10497, 33071
# Linear-space atlas water, used only on actual water primitives. The RGB
# background uses its exact lit result, while coverage remains transparent.
WATER = (.035, .10, .11, 1.)
LIGHT = R.Lighting(sun_direction=(-.45, .82, -.35),
                   sun_color=(.83, .81, .77), sky_color=(.70, .76, .80),
                   ground_color=(.32, .30, .26), ambient_strength=.78,
                   exposure=1.65, saturation=1., fog_density=0.,
                   shadow_strength=0.)
WATER_NAMES = {'fg_water_turquoise', 'crownwater_lagoon', 'grey_bog_water',
               'ssarathi_basin_water', 'westhaven_harbour_water',
               'manymouth_delta_shallow', 'manymouth_delta_deep'}
DTYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2',
          5125: '<u4', 5126: '<f4'}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4,
          'MAT2': 4, 'MAT3': 9, 'MAT4': 16}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def water_linear_lit():
    """The uniform up-facing water result before the shared display transform."""
    return np.asarray(WATER[:3]) * (np.asarray(LIGHT.sky_color)*LIGHT.ambient_strength
        + np.asarray(LIGHT.sun_color)*R._normalised(LIGHT.sun_direction)[1])


def water_rgb():
    """Exact uncompressed sea RGB for the surrounding continent background."""
    color=water_linear_lit().reshape(1,1,3).astype(np.float32)
    return tuple(int(v) for v in np.asarray(R._tonemap(color,LIGHT.exposure,LIGHT.saturation))[0,0])


def read_glb(path):
    raw = Path(path).read_bytes()
    magic, version, total = struct.unpack_from('<4sII', raw)
    if magic != b'glTF' or version != 2 or total != len(raw):
        raise ValueError(f'Invalid GLB 2.0: {path}')
    size, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4e4f534a:
        raise ValueError('First GLB chunk is not JSON')
    doc = json.loads(raw[20:20 + size])
    size, kind = struct.unpack_from('<II', raw, 20 + size)
    if kind != 0x004e4942:
        raise ValueError('Packaged GLB has no binary chunk')
    # The JSON chunk size is recomputed from its preceding header.
    start = 28 + struct.unpack_from('<I', raw, 12)[0]
    if len(doc.get('buffers', [])) > 1:
        import glb_reader                       # a region master kept in part files
        return glb_reader.join_parts(Path(path), doc, raw[start:start + size])
    return doc, raw[start:start + size]


def accessor(doc, binary, index):
    spec = doc['accessors'][index]
    if 'sparse' in spec:
        raise ValueError('Sparse GLB accessors are unsupported, not silently ignored')
    view = doc['bufferViews'][spec['bufferView']]
    dtype = np.dtype(DTYPES[spec['componentType']])
    width = WIDTHS[spec['type']]
    offset = view.get('byteOffset', 0) + spec.get('byteOffset', 0)
    stride = view.get('byteStride', dtype.itemsize * width)
    out = np.ndarray((spec['count'], width), dtype=dtype, buffer=binary,
                     offset=offset, strides=(stride, dtype.itemsize)).copy()
    if spec.get('normalized') and dtype.kind in 'iu':
        info = np.iinfo(dtype)
        out = np.maximum(out.astype(np.float32) / info.max, -1.)
    return out


def node_matrix(node):
    if 'matrix' in node:
        return np.asarray(node['matrix'], dtype=np.float64).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0., 0., 0., 1.])
    matrix = np.eye(4)
    matrix[:3, :3] = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                       [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                       [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    matrix[:3, :3] *= np.asarray(node.get('scale', [1., 1., 1.]))[None, :]
    matrix[:3, 3] = node.get('translation', [0., 0., 0.])
    return matrix


def visible_nodes(doc):
    """Yield real scene instances in world coordinates, without mesh-table copies."""
    scenes = doc.get('scenes', [])
    if not scenes:
        raise ValueError('Packaged GLB must declare its active scene')
    stack = [(i, np.eye(4), False) for i in reversed(scenes[doc.get('scene', 0)]['nodes'])]
    while stack:
        index, parent, excluded = stack.pop()
        node = doc['nodes'][index]
        name = node.get('name', '')
        excluded |= ('_StreamThreshold_' in name or '_StreamOverflow_' in name
                     or name.startswith('StreamView_'))
        transform = parent @ node_matrix(node)
        if not excluded and 'mesh' in node:
            yield name, node['mesh'], transform
        stack.extend((i, transform, excluded) for i in reversed(node.get('children', [])))


def frame(manifest):
    """Preserve the existing pixel-to-world mapping, including its exact extent."""
    minimap = manifest['minimap']
    low = np.asarray(minimap['worldMin'], dtype=float)
    high = np.asarray(minimap['worldMax'], dtype=float)
    size = tuple(int(v) for v in minimap['imageSize'])
    if low.shape != (2,) or high.shape != (2,) or min(size) <= 0 or np.any(high <= low):
        raise ValueError('Invalid declared minimap framing')
    ppm = float(minimap['pixelsPerMetre'])
    if not np.allclose((high-low) * ppm, size, atol=1e-4):
        raise ValueError('Minimap imageSize and world bounds disagree; publication must resolve framing')
    return low, high, size


def external_resource(path, uri, expected, asset_root=None):
    """Resolve deliberate shared PNG dependencies inside the authored asset tree."""
    if not isinstance(uri, str) or not uri or ':' in uri or '\\' in uri or uri.startswith('/'):
        raise ValueError(f'Unsupported external texture URI: {uri!r}')
    root = Path(asset_root or ROOT/'eloria-assets').resolve()
    target = (Path(path).parent/uri).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f'External texture escapes asset root: {uri}')
    if not isinstance(expected, str) or len(expected) != 64 or sha(target) != expected:
        raise ValueError(f'External texture hash mismatch: {uri}')
    return target


def source_inputs(path, manifest, asset_root=None):
    glb = Path(path).parent/manifest['asset']['glb']
    result = {'manifest':sha(path), 'glb':sha(glb)}
    resources = manifest.get('externalResources', {})
    if resources:
        result['externalResources'] = {uri:sha(external_resource(glb, uri, expected, asset_root))
            for uri, expected in sorted(resources.items())}
    return result


def _texture(doc, binary, index, path=None, external_resources=None, asset_root=None):
    spec = doc['images'][doc['textures'][index]['source']]
    if 'bufferView' in spec:
        view = doc['bufferViews'][spec['bufferView']]
        at = view.get('byteOffset', 0)
        source = io.BytesIO(binary[at:at+view['byteLength']])
    else:
        uri = spec.get('uri')
        expected = (external_resources or {}).get(uri)
        if path is None or expected is None:
            raise ValueError(f'External texture must have a declared SHA256: {uri}')
        source = external_resource(path, uri, expected, asset_root)
    with Image.open(source) as image:
        return np.asarray(image.convert('RGBA')).copy()


def texture_wrap(doc, index):
    texture = doc['textures'][index]
    sampler = doc.get('samplers', [])[texture['sampler']] if 'sampler' in texture else {}
    result = (sampler.get('wrapS', REPEAT), sampler.get('wrapT', REPEAT))
    if any(value not in (REPEAT, CLAMP_TO_EDGE) for value in result):
        raise ValueError(f'Unsupported atlas glTF texture wrap mode: {result}')
    return result


def clamp_flags(material):
    wrap = getattr(material, 'atlas_wrap', (REPEAT, REPEAT))
    if len(wrap) != 2 or any(value not in (REPEAT, CLAMP_TO_EDGE) for value in wrap):
        raise ValueError(f'Unsupported atlas material wrap mode: {wrap}')
    flags = (atlas_soft_ground.CLAMP_S if wrap[0] == CLAMP_TO_EDGE else 0) | (
             atlas_soft_ground.CLAMP_T if wrap[1] == CLAMP_TO_EDGE else 0)
    if flags and (material.alpha_mode != 'OPAQUE' or getattr(material,'atlas_soft_ground',False) or material.orm):
        raise ValueError('Atlas CLAMP_TO_EDGE supports opaque albedo only; masked, soft-ground or ORM clamp requires explicit support')
    return flags


def scene_from_glb(path, external_resources=None, asset_root=None):
    doc, binary = read_glb(path)
    scene = R.Scene()
    material_water = set()
    for i, material in enumerate(doc.get('materials', [])):
        name = material.get('name', str(i))
        water = name.startswith('water_') or name in WATER_NAMES
        if water:
            material_water.add(i)
            scene.add_material(R.RenderMaterial(str(i), WATER, roughness=1., double_sided=True))
            continue
        pbr = material.get('pbrMetallicRoughness', {})
        albedo = None
        wrap = (REPEAT, REPEAT)
        if 'baseColorTexture' in pbr:
            texture = pbr['baseColorTexture']
            if texture.get('texCoord', 0) != 0 or texture.get('extensions'):
                raise ValueError(f'Unsupported texture coordinate transform in {name}')
            albedo = f"albedo-{texture['index']}"
            wrap = texture_wrap(doc, texture['index'])
            if albedo not in scene._textures:
                rgba = _texture(doc, binary, texture['index'], path, external_resources, asset_root)
                # Native shader expects linear albedo; alpha is linear already.
                rgba[..., :3] = np.rint((rgba[..., :3] / 255.) ** 2.2 * 255).astype(np.uint8)
                scene.add_texture(albedo, rgba)
        mode = material.get('alphaMode', 'OPAQUE')
        authored = R.RenderMaterial(str(i), tuple(pbr.get('baseColorFactor', [1,1,1,1])),
            roughness=max(.5, float(pbr.get('roughnessFactor', 1.))),
            metallic=float(pbr.get('metallicFactor', 1.)), albedo=albedo,
            alpha_mode='MASK' if mode == 'BLEND' or name.endswith('_soft_ground') else mode,
            alpha_cutoff=float(material.get('alphaCutoff', .5)),
            double_sided=bool(material.get('doubleSided', False)))
        authored.atlas_soft_ground = name.endswith('_soft_ground')
        authored.atlas_wrap = wrap
        clamp_flags(authored)
        scene.add_material(authored)
    if not scene.materials:
        scene.add_material(R.RenderMaterial('0'))
    cache = {}
    colors = []
    instances = 0
    for name, mesh_index, transform in visible_nodes(doc):
        for pi, primitive in enumerate(doc['meshes'][mesh_index]['primitives']):
            if primitive.get('mode', 4) != 4:
                raise ValueError(f'Non-triangle primitive in {name}')
            key = mesh_index, pi
            if key not in cache:
                a = primitive['attributes']
                pos = accessor(doc, binary, a['POSITION']).astype(np.float32)
                indices = (accessor(doc, binary, primitive['indices']).reshape(-1).astype(np.int64)
                           if 'indices' in primitive else np.arange(len(pos)))
                if len(indices) % 3:
                    raise ValueError(f'Incomplete triangle in {name}')
                if not len(indices):
                    cache[key] = None
                    continue
                normal = (accessor(doc, binary, a['NORMAL']).astype(np.float32) if 'NORMAL' in a
                          else np.tile([0., 1., 0.], (len(pos), 1)))
                uv = (accessor(doc, binary, a['TEXCOORD_0']).astype(np.float32) if 'TEXCOORD_0' in a
                      else np.zeros((len(pos), 2), np.float32))
                color = (accessor(doc, binary, a['COLOR_0']).astype(np.float32) if 'COLOR_0' in a
                         else np.ones((len(pos), 4), np.float32))
                if color.shape[1] == 3:
                    color = np.column_stack((color, np.ones(len(color), np.float32)))
                material = int(primitive.get('material', 0))
                if material in material_water:
                    color = np.ones((len(pos), 4), np.float32)
                cache[key] = M.Mesh(pos, normal, uv, indices=indices, material=str(material)), color
            if cache[key] is None:
                continue
            mesh, color = cache[key]
            if np.linalg.det(transform[:3, :3]) < 0:
                mesh = mesh.copy()
                mesh.indices = mesh.indices.reshape(-1, 3)[:, ::-1].reshape(-1)
            scene.add_mesh(mesh, transform)
            colors.append(color)
            instances += 1
    vertex_colors = np.ascontiguousarray(np.vstack(colors), dtype=np.float32)
    return scene, vertex_colors, {'meshPrimitiveInstances': instances,
        'triangles': scene.triangle_count(), 'waterMaterials':
        [doc['materials'][i].get('name', str(i)) for i in sorted(material_water)]}


def projected_mip_levels(positions, uvs, indices, pixel_metres, texture_size=512):
    """Nearest mip level from the major axis of each projected UV footprint.

    This atlas has an orthographic X/Z camera, so UV derivatives are constant
    within each actual triangle, including transformed or mirrored instances.
    Vertical faces have zero projected area and never reach the raster buffer.
    """
    faces = np.asarray(indices).reshape(-1, 3)
    p = positions[faces][:, :, [0, 2]].astype(np.float64)
    uv = uvs[faces].astype(np.float64)
    edge, other = p[:, 1]-p[:, 0], p[:, 2]-p[:, 0]
    du, dv = uv[:, 1]-uv[:, 0], uv[:, 2]-uv[:, 0]
    det = edge[:, 0]*other[:, 1]-edge[:, 1]*other[:, 0]
    valid = np.abs(det) > 1e-10
    inv = np.divide(1., det, out=np.zeros_like(det), where=valid)
    dx = (du*other[:, 1, None]-dv*edge[:, 1, None])*inv[:, None]
    dz = (dv*edge[:, 0, None]-du*other[:, 0, None])*inv[:, None]
    dx *= float(pixel_metres[0])*texture_size
    dz *= float(pixel_metres[1])*texture_size
    trace = (dx*dx+dz*dz).sum(axis=1)
    determinant = (dx[:, 0]*dz[:, 1]-dx[:, 1]*dz[:, 0])**2
    footprint = np.sqrt((trace+np.sqrt(np.maximum(trace*trace-4*determinant, 0.)))*.5)
    lod = np.log2(np.maximum(footprint, 1.))
    return np.clip(np.floor(lod+.5), 0, int(math.log2(texture_size))).astype(np.int8)


def mip_albedo(texture, level, wrap=(REPEAT, REPEAT)):
    """Linear-light box mip, wrap-aware sampling back into the native array.

    The frozen raster ABI has one 512px texture-array size. Expanding the mip
    with the material's repeat/clamp bilinear taps preserves its edge semantics.
    Only RGB is filtered: original cutout alpha and vertex coverage stay exact,
    so a texture fix cannot change a tree silhouette or erase a thin roof.
    """
    if len(wrap) != 2 or any(value not in (REPEAT, CLAMP_TO_EDGE) for value in wrap):
        raise ValueError(f'Unsupported atlas mip wrap mode: {wrap}')
    if texture.shape[:2] != (512, 512):
        texture = np.asarray(Image.fromarray(texture).resize((512, 512), Image.Resampling.BILINEAR))
    if not level:
        return texture.copy()
    factor = 2**int(level)
    side = 512//factor
    small = texture[:, :, :3].astype(np.float32).reshape(side, factor, side, factor, 3).mean(axis=(1, 3))
    at = (np.arange(512)+.5)/factor-.5
    first = np.floor(at).astype(int)
    weight = (at-first).astype(np.float32)
    taps = lambda offset, mode: (first+offset) % side if mode == REPEAT else np.clip(first+offset, 0, side-1)
    horizontal = small[:, taps(0,wrap[0])]*(1-weight[None, :, None]) + small[:, taps(1,wrap[0])]*weight[None, :, None]
    rgb = horizontal[taps(0,wrap[1])]*(1-weight[:, None, None]) + horizontal[taps(1,wrap[1])]*weight[:, None, None]
    result = texture.copy()
    result[:, :, :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return result


def minified_scene(scene, low, high, dimensions):
    """An atlas-only material view; geometry, UVs and input textures are immutable."""
    if not any(material.albedo for material in scene.materials):
        return scene
    geometry, keep = scene._pack()
    positions, normals, uvs, indices, tri_material = keep
    levels = projected_mip_levels(positions, uvs, indices,
                                  (np.asarray(high)-np.asarray(low))/np.asarray(dimensions))
    result = copy.copy(scene)
    result.materials = list(scene.materials)
    result._textures = dict(scene._textures)
    result._texture_images = list(scene._texture_images)
    result._packed_textures = None
    materials = tri_material.copy()
    filtered = {}
    for identity, material in enumerate(scene.materials):
        if not material.albedo:
            continue
        selected = tri_material == identity
        for level in np.unique(levels[selected]):
            if not level:
                continue
            wrap = getattr(material,'atlas_wrap',(REPEAT,REPEAT))
            key = (material.albedo, int(level), wrap)
            if key not in filtered:
                texture = scene._texture_images[scene._textures[material.albedo]]
                name = f'atlas-mip-{len(filtered)}'
                result.add_texture(name, mip_albedo(texture, level, wrap))
                filtered[key] = name
            variant = copy.copy(material)
            variant.name = f'{material.name}-atlas-mip-{level}'
            variant.albedo = filtered[key]
            materials[selected & (levels == level)] = len(result.materials)
            result.materials.append(variant)
    geometry = R._Geometry(geometry.positions, geometry.normals, geometry.uvs,
        geometry.indices, materials.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        geometry.vertex_count, geometry.triangle_count)
    result._packed = geometry, (positions, normals, uvs, indices, materials)
    return result


def raster(scene, colors, low, high, size, supersample=2, *, minify=True, native_cache=None):
    """One exact orthographic geometry pass; alpha is the z-buffer coverage."""
    width, height = (int(v) * supersample for v in size)
    if minify:
        scene = minified_scene(scene, low, high, (width, height))
    geometry, keep = scene._pack()
    textures, texture_keep = scene._pack_textures()
    materials = scene._pack_materials()
    soft = [i for i,m in enumerate(scene.materials) if getattr(m,'atlas_soft_ground',False)]
    clamped = {i:clamp_flags(m) for i,m in enumerate(scene.materials) if clamp_flags(m)}
    library, adapter_proof = atlas_soft_ground.load(TOOLKIT/'native/raster.c',
        ROOT/'godot-client/src/world/soft_ground.gdshader',
        native_cache or ROOT.parent/'work-output/atlas-native-cache')
    if soft or clamped:
        for i in soft:
            materials[i].alpha_mode = 3
        for i,flags in clamped.items():
            materials[i].alpha_mode = flags  # Opaque low bits remain zero; native ABI unchanged.
    all_positions = keep[0]
    ceiling = float(all_positions[:, 1].max()) + 100.
    floor = float(all_positions[:, 1].min()) - 10.
    center = (low+high)/2
    eye = np.asarray([center[0], ceiling, center[1]], dtype=np.float32)
    # Camera up is world north (-Z); the image's positive Y is world +Z.
    view = R.look_at(eye, [center[0], 0., center[1]], up=(0., 0., -1.))
    projection = R.orthographic(high[0]-low[0], high[1]-low[1], .1, ceiling-floor)
    matrix = np.ascontiguousarray(projection @ view, dtype=np.float32)
    light = R._Lighting((ctypes.c_float*3)(*R._normalised(LIGHT.sun_direction)),
        (ctypes.c_float*3)(*LIGHT.sun_color), (ctypes.c_float*3)(*LIGHT.sky_color),
        (ctypes.c_float*3)(*LIGHT.ground_color), (ctypes.c_float*3)(0,0,0),
        0.,0.,LIGHT.exposure,LIGHT.ambient_strength,.1,0.)
    color = np.zeros((height,width,3), dtype=np.float32)
    depth = np.empty((height,width), dtype=np.float32)
    identity = np.ascontiguousarray(np.eye(4), dtype=np.float32)
    fn = getattr(library, 'render_scene_colored', None)
    if fn is None:
        raise RuntimeError('Rebuild native/libraster.so: optional vertex-color renderer is missing')
    ptr = ctypes.POINTER(ctypes.c_float)
    fn.argtypes = [ctypes.POINTER(R._Geometry), ctypes.POINTER(R._Material), ctypes.c_int32,
        ctypes.POINTER(R._TextureArray), ptr, ptr, ctypes.POINTER(R._Lighting), ptr, ptr,
        ctypes.c_int32, ptr, ptr, ctypes.c_int32, ctypes.c_int32, ptr]
    fn(ctypes.byref(geometry),materials,len(scene.materials),ctypes.byref(textures),
       matrix.ctypes.data_as(ptr),eye.ctypes.data_as(ptr),ctypes.byref(light),
       identity.ctypes.data_as(ptr),None,0,color.ctypes.data_as(ptr),
       depth.ctypes.data_as(ptr),width,height,colors.ctypes.data_as(ptr))
    coverage = depth < 1e29
    color[~coverage] = water_linear_lit()
    rgb = R._tonemap(color,LIGHT.exposure,LIGHT.saturation)
    alpha = Image.fromarray(coverage.astype(np.uint8)*255)
    rgba = rgb.copy().convert('RGBA')
    rgba.putalpha(alpha)
    if supersample != 1:
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
        # Pillow's RGBA resizing uses premultiplied alpha, avoiding a background fringe.
        rgba = rgba.resize(size, Image.Resampling.LANCZOS)
        alpha = rgba.getchannel('A')
    counts = {'coveredSamples':int(coverage.sum()),
        'sampleCount':int(coverage.size), 'coverageFraction':round(float(coverage.mean()),6),
        'nativeRenderer':atlas_soft_ground.publication_provenance(adapter_proof)}
    if soft:
        counts['softGroundDither'] = adapter_proof
    if clamped:
        counts['opaqueClampSampler'] = adapter_proof
        counts['clampedMaterialCount'] = len(clamped)
    return rgb, rgba, alpha, counts


def regions():
    registry = json.loads((ROOT/'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))['maps']
    layout = json.loads((ROOT/'eloria-assets/maps/nymara-regions/continent-layout.json').read_text(encoding='utf-8'))
    return {key: ROOT/'godot-client'/entry['manifest'].removeprefix('res://')
            for key, entry in registry.items() if key in layout['regions']}


def render_region(identity, path, output, supersample=2):
    began = time.perf_counter()
    path = path.resolve()
    manifest = json.loads(path.read_text(encoding='utf-8'))
    low, high, size = frame(manifest)
    glb = path.parent/manifest['asset']['glb']
    inputs = source_inputs(path, manifest)
    scene, colors, stats = scene_from_glb(glb, manifest.get('externalResources'))
    rgb, rgba, coverage, counts = raster(scene, colors, low, high, size, supersample,
                                        native_cache=output/'_atlas_native')
    if inputs != source_inputs(path, manifest):
        raise RuntimeError(f'{identity}: package changed during render; retry after geometry freeze')
    folder = output/identity
    folder.mkdir(parents=True, exist_ok=True)
    rgb.save(folder/'minimap.webp','WEBP',quality=92,method=6)
    rgba.save(folder/'geometry.png')
    # Lossless encoding keeps sea RGB and geometry coverage exactly identical
    # to the shared atlas background, avoiding region-shaped JPEG/WebP shifts.
    rgba.save(folder/'cartography.webp','WEBP',lossless=True,method=6,exact=True)
    coverage.save(folder/'coverage.png')
    report = {'region':identity,'styleVersion':STYLE_VERSION,'inputs':inputs,
        'sourceManifest':str(path),'worldMin':low.tolist(),'worldMax':high.tolist(),
        'imageSize':list(size),'supersample':supersample,'projection':'orthographic, -Z north, +X east',
        'textureMinification':'Projected per-triangle UV footprint; nearest linear-light RGB mip with glTF repeat/clamp bilinear filtering; original alpha retained. Clamp is supported for opaque albedo.',
        'waterLinearRGBA':list(WATER),'waterRGB':list(water_rgb()),
        'lighting':vars(LIGHT),'geometry':stats,'coverage':counts,
        'seconds':round(time.perf_counter()-began,3),
        'rendererSourceSha256':sha(TOOLKIT/'native/raster.c'),
        'toolSha256':sha(__file__),
        'outputs':{f:sha(folder/f) for f in ('minimap.webp','cartography.webp','geometry.png','coverage.png')},
        'limits':['Opaque atlas water uses actual water triangles; it does not infer shorelines from colors.',
                  'Uniform daylight omits atmosphere and cast shadows; geometric normals retain relief.',
                  'Microscopic normal/roughness textures are omitted at atlas scale; native albedo, alpha and vertex colors remain.']}
    (folder/'render-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def apply_outputs(report, output):
    """Publish only derived images and minimap provenance; never alter framing."""
    path=Path(report['sourceManifest'])
    manifest=json.loads(path.read_text(encoding='utf-8'))
    glb=path.parent/manifest['asset']['glb']
    if report['inputs'] != source_inputs(path, manifest):
        raise RuntimeError(f"{report['region']}: refusing publication after source inputs changed")
    original_frame={k:manifest['minimap'].get(k) for k in
                    ('worldMin','worldMax','imageSize','pixelsPerMetre','transform','origin','centre')}
    for filename in ('minimap.webp','cartography.webp'):
        source=output/report['region']/filename
        if sha(source)!=report['outputs'][filename]:
            raise RuntimeError(f'Changed render output: {source}')
        destination=path.parent/filename
        temporary=destination.with_suffix(destination.suffix+'.cartography-tmp')
        temporary.write_bytes(source.read_bytes())
        temporary.replace(destination)
    minimap=manifest['minimap']
    minimap['geometryImage']='cartography.webp'
    minimap['renderedFrom']='world.glb (shared geometry cartography renderer)'
    minimap['cartographyRender']={'generator':'eloria-assets/tools/render_region_cartography.py',
        'styleVersion':STYLE_VERSION,'glbSha256':report['inputs']['glb'],
        'toolSha256':report['toolSha256'],'rendererSourceSha256':report['rendererSourceSha256'],
        'supersample':report['supersample'],'waterRGB':report['waterRGB']}
    if report['inputs'].get('externalResources'):
        minimap['cartographyRender']['externalResources'] = report['inputs']['externalResources']
    if report.get('coverage', {}).get('softGroundDither'):
        minimap['cartographyRender']['softGroundDither'] = atlas_soft_ground.publication_provenance(
            report['coverage']['softGroundDither'])
    if report.get('coverage', {}).get('opaqueClampSampler'):
        minimap['cartographyRender']['opaqueClampSampler'] = atlas_soft_ground.publication_provenance(
            report['coverage']['opaqueClampSampler'])
    assert original_frame=={k:minimap.get(k) for k in original_frame}
    temporary=path.with_suffix('.json.cartography-tmp')
    temporary.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    temporary.replace(path)


def contact_sheet(reports, output):
    width, label, columns = 420, 32, 2
    sheet = Image.new('RGB',(width*columns,(width+label)*math.ceil(len(reports)/columns)),(24,36,39))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=17)
    for i,r in enumerate(reports):
        image = Image.open(output/r['region']/'minimap.webp').convert('RGB')
        # Contact sheet only; authoritative outputs keep exact original pixel dimensions.
        image.thumbnail((width,width),Image.Resampling.LANCZOS)
        x=(i%columns)*width;y=(i//columns)*(width+label)
        sheet.paste(image,(x+(width-image.width)//2,y+(width-image.height)//2))
        draw.text((x+12,y+width+5),r['region'].replace('_',' ').title(),font=font,fill=(220,225,204))
    sheet.save(output/'contact-sheet.png')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--regions',nargs='+')
    group.add_argument('--all',action='store_true')
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--supersample',type=int,choices=(1,2,3,4),default=2)
    ap.add_argument('--apply',action='store_true',help='publish images + generator metadata after geometry is frozen')
    args=ap.parse_args();output=args.output_dir.resolve()
    if output.is_relative_to(ROOT/'eloria-assets/maps'):
        ap.error('Render to a separate output directory; package publication belongs to the coordinator')
    available=regions();wanted=list(available) if args.all else args.regions
    unknown=set(wanted)-available.keys()
    if unknown:ap.error(f'Unknown atlas regions: {sorted(unknown)}')
    output.mkdir(parents=True,exist_ok=True);reports=[]
    for identity in wanted:
        report=render_region(identity,available[identity],output,args.supersample)
        if args.apply:
            apply_outputs(report,output)
            report['publishedManifestSha256']=sha(available[identity])
            (output/identity/'render-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        reports.append(report)
        print(f"{identity}: {report['geometry']['triangles']:,} triangles, {report['seconds']:.2f}s, coverage {report['coverage']['coverageFraction']:.1%}",flush=True)
    contact_sheet(reports,output)
    (output/'render-summary.json').write_text(json.dumps(reports,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
