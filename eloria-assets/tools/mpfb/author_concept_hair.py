"""Author the Rowan/Mira concept hair from editable directed Bezier guides.

Run in an isolated Blender process. The original imported scalp, player rig and
animations are read-only fitting references. Output is one opaque Head-local
mesh/material, plus a Blender authoring stage with the original curve guides.
This workflow is independent of Rabbit Lands' retired model builders.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree


COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
DTYPES = {5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blender(v):
    return (v[0], -v[2], v[1])


class Glb:
    def __init__(self, path):
        data = Path(path).read_bytes()
        length = struct.unpack_from('<I', data, 12)[0]
        self.doc = json.loads(data[20:20 + length])
        self.binary = data[28 + length:]

    def read(self, index):
        accessor = self.doc['accessors'][index]
        view = self.doc['bufferViews'][accessor['bufferView']]
        dtype = np.dtype(DTYPES[accessor['componentType']])
        columns = COMPONENTS[accessor['type']]
        array = np.ndarray((accessor['count'], columns), dtype=dtype, buffer=self.binary,
                           offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                           strides=(view.get('byteStride', columns * dtype.itemsize), dtype.itemsize)).copy()
        return array[:, 0] if columns == 1 else array

    def head_world(self):
        nodes = self.doc['nodes']
        parents = {child: i for i, node in enumerate(nodes) for child in node.get('children', [])}
        cache = {}

        def world(i):
            if i in cache:
                return cache[i]
            node = nodes[i]
            if 'matrix' in node:
                matrix = Matrix(np.array(node['matrix']).reshape(4, 4).T.tolist())
            else:
                x, y, z, w = node.get('rotation', [0, 0, 0, 1])
                matrix = Matrix.LocRotScale(Vector(node.get('translation', [0, 0, 0])),
                                            Quaternion((w, x, y, z)), Vector(node.get('scale', [1, 1, 1])))
            cache[i] = world(parents[i]) @ matrix if i in parents else matrix
            return cache[i]
        return world(next(i for i, node in enumerate(nodes) if node.get('name') == 'Head'))

    def local_primitive(self, mesh, primitive, inverse):
        p = self.doc['meshes'][mesh]['primitives'][primitive]
        positions = self.read(p['attributes']['POSITION'])
        local = np.array([inverse @ Vector(v) for v in positions], dtype=float)
        triangles = self.read(p['indices']).reshape(-1, 3)
        uv = self.read(p['attributes']['TEXCOORD_0'])
        return local, triangles, uv, p


def bezier_path(points, steps):
    p = np.asarray(points, dtype=float)
    tangents = np.empty_like(p)
    tangents[0], tangents[-1] = (p[1] - p[0]) / 3, (p[-1] - p[-2]) / 3
    tangents[1:-1] = (p[2:] - p[:-2]) / 6
    result = []
    for t in np.linspace(0, len(p) - 1, steps):
        i = min(int(t), len(p) - 2)
        u = t - i
        a, b, c, d = p[i], p[i] + tangents[i], p[i + 1] - tangents[i + 1], p[i + 1]
        result.append((1 - u) ** 3 * a + 3 * (1 - u) ** 2 * u * b + 3 * (1 - u) * u ** 2 * c + u ** 3 * d)
    return np.array(result), tangents


def normalized(vector):
    return vector / max(np.linalg.norm(vector), 1e-10)


def add_guide(lock, tangents, collection):
    curve = bpy.data.curves.new(lock['name'] + ' editable Bezier', 'CURVE')
    curve.dimensions = '3D'
    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(len(lock['points']) - 1)
    for point, location, tangent in zip(spline.bezier_points, lock['points'], tangents):
        p = np.array(location)
        point.co = blender(p)
        point.handle_left_type = point.handle_right_type = 'FREE'
        point.handle_left = blender(p - tangent)
        point.handle_right = blender(p + tangent)
    obj = bpy.data.objects.new(lock['name'] + ' guide', curve)
    collection.objects.link(obj)
    obj.hide_render = True


def build_hair(profile, head_vertices, head_triangles):
    center = np.asarray(profile['skull_center'])
    head_minimum, head_maximum = head_vertices.min(0), head_vertices.max(0)
    bvh = BVHTree.FromPolygons([Vector(v) for v in head_vertices], head_triangles.tolist(), all_triangles=True)
    positions, normals, uv, faces, progress = [], [], [], [], []
    correction_count, correction_max = 0, 0.0

    def collision(point):
        nonlocal correction_count, correction_max
        if point[1] < .035:
            return point
        # Concave ear folds can have a nearest face pointing back into the ear.
        # A point already outside the complete head bounds cannot be inside it.
        if np.any(point < head_minimum - .0001) or np.any(point > head_maximum + .0001):
            return point
        nearest, normal, _, distance = bvh.find_nearest(Vector(point))
        if nearest is None or distance > .025:
            return point
        n = np.array(normal)
        if np.dot(point - np.array(nearest), n) < -0.0001:
            delta = np.array(nearest) + n * .001 - point
            correction_count += 1
            correction_max = max(correction_max, float(np.linalg.norm(delta)))
            return point + delta
        return point

    # Fit the undercoat to the actual imported scalp, rather than using a block
    # sphere cap. The front hairline stops above the brow; the nape runs lower.
    sectors, rings = 48, 12
    cap_start = len(positions)
    for ring in range(rings + 1):
        for sector in range(sectors + 1):
            theta = sector * math.tau / sectors
            front = max(math.cos(theta), 0.)
            back = max(-math.cos(theta), 0.)
            end = (profile['cap_side_angle'] +
                   (profile['cap_front_angle'] - profile['cap_side_angle']) * front ** 3 +
                   (profile['cap_back_angle'] - profile['cap_side_angle']) * back ** 2)
            end += profile.get('cap_edge_scallop', .026) * math.sin(theta * 9 + .4) + profile.get('cap_edge_secondary', .012) * math.sin(theta * 15 - .8)
            # A parted updo exposes a small forehead opening rather than a
            # horizontal undercoat edge beneath separately swept bangs.
            opening=profile.get('cap_part_opening',0.)
            if opening:
                angle=math.atan2(math.sin(theta-profile.get('cap_part_center',.0)),
                                 math.cos(theta-profile.get('cap_part_center',.0)))
                end-=opening*math.exp(-(angle/profile.get('cap_part_width',.35))**2)
            phi = .012 + (end - .012) * ring / rings
            direction = np.array([math.sin(phi) * math.sin(theta), math.cos(phi), math.sin(phi) * math.cos(theta)])
            hit, _, _, _ = bvh.ray_cast(Vector(center), Vector(direction), .5)
            if hit is None:
                radius = 1 / np.linalg.norm(direction / np.array([.083, .105, .105]))
                point = center + direction * radius
            else:
                point = np.array(hit)
            # Subtle flow channels keep uncovered roots from reading as a
            # perfectly smooth helmet. The broader authored locks carry shape.
            ridge = .0015 * (.5 + .5 * math.cos(theta * 24 + phi * 2.5))
            point += direction * (profile['cap_offset'] + ridge)
            # A radial scalp fit can hit an inner ear fold before its outer
            # helix. Resolve that local clearance just as for the fitted locks.
            positions.append(collision(point))
            normals.append(direction)
            uv.append((sector / sectors, ring / rings))
    for ring in range(rings):
        for sector in range(sectors):
            a = cap_start + ring * (sectors + 1) + sector
            b = a + sectors + 1
            faces.append((a, b, b + 1, a + 1))

    # The gathered updo needs an opaque underlayer beneath its overlapping
    # curled ribbons. Its irregular lobes stay inside the authored outer curls;
    # it is not a separate visible round bun or another material.
    if profile.get('bun_core'):
        core = profile['bun_core']
        origin, radii = np.array(core['center']), np.array(core['radii'])
        start = len(positions)
        segments, latitudes = 32, 16
        for latitude in range(latitudes + 1):
            phi = .01 + (math.pi - .02) * latitude / latitudes
            for segment in range(segments + 1):
                theta = segment * math.tau / segments
                direction = np.array([math.sin(phi) * math.sin(theta), math.cos(phi), math.sin(phi) * math.cos(theta)])
                lobe = 1 + .045 * math.sin(theta * 3 + phi * 2) + .025 * math.cos(theta * 5 - phi)
                positions.append(origin + direction * radii * lobe)
                normals.append(normalized(direction / radii))
                uv.append((segment / segments, latitude / latitudes))
        for latitude in range(latitudes):
            for segment in range(segments):
                a = start + latitude * (segments + 1) + segment
                b = a + segments + 1
                faces.append((a, b, b + 1, a + 1))

    progress.extend([0.] * len(positions))
    fixed_undercoat_vertices = len(positions)

    guides = bpy.data.collections.new('Editable concept hair Bezier guides')
    bpy.context.scene.collection.children.link(guides)
    guides.hide_render = True
    guides.hide_viewport = True
    lock_report = []
    for lock in profile['locks']:
        # Raised bun curls wrap the bun, not the skull beneath it. Using the
        # skull frame turns broad front-facing ribbons edge-on like wire loops.
        frame_center=np.array(profile['bun_core']['center']) if lock.get('surface_fit')=='bun' else center
        if lock.get('surface_fit') or lock.get('root_surface_fit'):
            lock = dict(lock)
            fit_kind = lock.get('surface_fit') or lock['root_surface_fit']
            fitted = []
            points = np.asarray(lock['points'], dtype=float)
            for i, point in enumerate(points):
                f = i / (len(points) - 1)
                if fit_kind == 'bun':
                    origin = np.array(profile['bun_core']['center'])
                    radii = np.array(profile['bun_core']['radii'])
                    direction = normalized(point - origin)
                    radius = 1 / np.linalg.norm(direction / radii)
                    hit = origin + direction * radius
                else:
                    direction = normalized(point - center)
                    surface, _, _, _ = bvh.ray_cast(Vector(center), Vector(direction), .5)
                    hit = np.array(surface) if surface is not None else point
                lift = .003 + lock.get('surface_offset', .006) * max(math.sin(f * math.pi), 0) ** .8
                target = hit + direction * (lock['thickness'] * .5 + lift)
                # Retain a short authored hooked tip, while rooting the rest on
                # actual scalp/bun surfaces instead of leaving roof-like arches.
                tip_fit = lock.get('tip_fit', .8)
                fit = 1 if f < .8 else 1 - (1 - tip_fit) * (f - .8) / .2
                if lock.get('surface_release'):
                    start,end=lock['surface_release']
                    phase=np.clip((f-start)/(end-start),0.,1.)
                    fit*=1-phase*phase*(3-2*phase)
                if lock.get('root_surface_fit') and not lock.get('surface_fit'):
                    fit = 1 if i == 0 else .65 if i == 1 else 0
                fitted.append((target * fit + point * (1 - fit)).tolist())
            lock['points'] = fitted
        path, handles = bezier_path(lock['points'], lock['steps'])
        add_guide(lock, handles, guides)
        lengths = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        length = lengths[-1]
        tangent = np.gradient(path, axis=0)
        start = len(positions)
        last_normal = None
        sides = lock['sides']
        for index, (point, t) in enumerate(zip(path, tangent)):
            t = normalized(t)
            outward = point - frame_center
            outward -= t * np.dot(outward, t)
            if np.linalg.norm(outward) < 1e-5:
                outward = last_normal if last_normal is not None else np.array([0., 0., 1.])
            outward = normalized(outward)
            if last_normal is not None and np.dot(outward, last_normal) < 0:
                outward = -outward
            width_direction = normalized(np.cross(t, outward))
            outward = normalized(np.cross(width_direction, t))
            last_normal = outward
            f = index / (len(path) - 1)
            pin = min(f / .35, 1.)
            pin = pin * pin * (3 - 2 * pin)
            # A broad living midsection and fine hooked tip are more readable
            # than a constant-radius rope. Profiles are shared across sections.
            root = lock.get('root_width', .3)
            tip = lock.get('tip_width', .015)
            swell = root + (1 - root) * min(f / lock.get('root_swell_end', .22), 1)
            taper_start = lock.get('taper_start', .64)
            taper = 1 if f < taper_start else tip + (1 - tip) * ((1 - f) / (1 - taper_start)) ** .78
            width = lock['width'] * swell * taper
            thickness = lock['thickness'] * (0.45 + 0.55 * swell) * math.sqrt(max(taper, .002))
            for side in range(sides + 1):
                angle = side * math.tau / sides
                lateral, radial = math.sin(angle), math.cos(angle)
                # Two shallow sculpted longitudinal channels on the outside of
                # broad ribbons break one highlight into layered keratin planes.
                channel = 1 - .10 * max(radial, 0) * math.cos(lateral * math.pi * 3) ** 6
                vertex = point + width_direction * width * .5 * lateral + outward * thickness * .5 * radial * channel
                positions.append(collision(vertex))
                normals.append(normalized(width_direction * lateral / max(width, .0001) + outward * radial / max(thickness, .0001)))
                uv.append((side / sides, lengths[index] / max(length, 1e-7)))
                progress.append(pin)
        for index in range(len(path) - 1):
            for side in range(sides):
                a = start + index * (sides + 1) + side
                b = a + sides + 1
                faces.append((a, a + 1, b + 1, b))
        for ring_index, flip in ((0, False), (len(path) - 1, True)):
            ring_start = start + ring_index * (sides + 1)
            face = tuple(ring_start + i for i in range(sides))
            faces.append(tuple(reversed(face)) if flip else face)
        lock_report.append({'name': lock['name'], 'arc_length_metres': float(length),
                            'cross_section': 'lenticular' if lock['width'] > lock['thickness'] * 1.5 else 'small elliptical tendril'})
    return np.array(positions), np.array(normals), np.array(uv), np.array(progress), faces, lock_report, {
        'projected_inside_scalp_vertices': correction_count, 'largest_scalp_projection_metres': correction_max,
        'fixed_undercoat_source_vertex_span': [0, fixed_undercoat_vertices]}


def geometric_normals(vertices, faces):
    """Smooth the actual sculpt, sharing normals across repeated UV seam verts."""
    accumulated = np.zeros_like(vertices)
    for face in faces:
        points = vertices[list(face)]
        normal = np.zeros(3)
        for i in range(1, len(points) - 1):
            normal += np.cross(points[i] - points[0], points[i + 1] - points[0])
        accumulated[list(face)] += normal
    shared = {}
    keys = [tuple(np.rint(point * 1e8).astype(np.int64)) for point in vertices]
    for key, normal in zip(keys, accumulated):
        shared[key] = shared.get(key, np.zeros(3)) + normal
    return np.array([normalized(shared[key]) for key in keys])


def pin_scalp_clearance(vertices, progress, faces, profile, head, triangles):
    """Bake conservative slider clearance into the existing root-alpha field.

    Distance to the nearest head surface bounds motion in every direction. A
    complete cross-section shares the smallest safe gain, so sliders cannot
    flatten one side of a lock. No runtime queries or attributes are added.
    """
    control=profile.get('runtime_control_center',{'length':50,'volume':50})
    length=max(abs((value-control['length'])/50.) for value in (0,100))
    volume=max(abs((value-control['volume'])/50.) for value in (0,100))
    maximum=np.sqrt((.13*volume)**2*(vertices[:,0]**2+vertices[:,2]**2)+(.018*length)**2)
    bvh=BVHTree.FromPolygons([Vector(v) for v in head],triangles.tolist(),all_triangles=True)
    distance=np.array([bvh.find_nearest(Vector(v))[3] for v in vertices])
    limit=np.clip((distance-.001)/np.maximum(maximum,1e-9),0.,1.)
    head_minimum,head_maximum=head.min(0),head.max(0)
    for face in faces:
        ids=np.asarray(face,dtype=int)
        if not np.any(progress[ids]): continue
        points=vertices[ids]
        # Wide lenticular sections can bridge the scalp between otherwise safe
        # vertices. Include their interior and edges before sharing ring gains.
        samples=[points.mean(0)]
        samples.extend((points+np.roll(points,-1,axis=0))*.5)
        clearance=float('inf')
        for point in samples:
            nearest,normal,_,gap=bvh.find_nearest(Vector(point))
            if np.all(point>=head_minimum) and np.all(point<=head_maximum) \
                    and np.dot(point-np.array(nearest),np.array(normal))<-.00025:
                gap=0.
            clearance=min(clearance,gap)
        safe=np.clip((clearance-.001)/max(float(maximum[ids].max()),1e-9),0.,1.)
        limit[ids]=np.minimum(limit[ids],safe)
    original=progress.copy();output=progress.copy()
    start=49*13+(33*17 if profile.get('bun_core') else 0)
    for lock in profile['locks']:
        width=lock['sides']+1
        for ring in range(lock['steps']):
            ids=slice(start+ring*width,start+(ring+1)*width)
            # Round downward to the exact RGBA8 alpha field, preserving margin.
            safe=math.floor(float(limit[ids].min())*255)/255.
            output[ids]=np.minimum(output[ids],safe)
        start+=lock['steps']*width
    assert start==len(vertices)
    return output,{'control_center':control,'margin_metres':.001,
        'method':'nearest-head distance at vertices, face centers and edge midpoints bounds worst 0/100 motion; one quantized gain per section',
        'reduced_vertices':int((output<original-1e-8).sum()),
        'cap_and_roots_exact':bool(np.array_equal(output[original==0],original[original==0])),
        'largest_worst_case_motion_metres':float((maximum*output).max())}


def mesh_object(name, vertices, faces, uv, normals=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([blender(v) for v in vertices], [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name='Hair strand' if 'Hair' in name else 'UVMap')
    for loop in mesh.loops:
        layer.data[loop.index].uv = uv[loop.vertex_index]
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if normals is not None:
        mesh.normals_split_custom_set([blender(normals[loop.vertex_index]) for loop in mesh.loops])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def material(name, color, roughness=.60):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = True
    node = mat.node_tree.nodes.get('Principled BSDF')
    rgb = [int(color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
    node.inputs['Base Color'].default_value = (*linear, 1)
    node.inputs['Roughness'].default_value = roughness
    node.inputs['Specular IOR Level'].default_value = .35
    if 'Anisotropic IOR Level' in node.inputs:
        node.inputs['Anisotropic IOR Level'].default_value = .3
    mat.diffuse_color = (*linear, 1)
    return mat


def pack_root_colors(path):
    """Keep the root-pin interface in normalized RGBA8 instead of exporter U16."""
    source = Glb(path)
    primitive = source.doc['meshes'][0]['primitives'][0]
    accessor = source.doc['accessors'][primitive['attributes']['COLOR_0']]
    raw = source.read(primitive['attributes']['COLOR_0'])
    maximum = np.iinfo(raw.dtype).max
    rgba = np.rint(raw.astype(float) * 255 / maximum).astype(np.uint8)
    selected = accessor['bufferView']
    accessor['componentType'], accessor['normalized'] = 5121, True
    source.doc['materials'][0]['alphaMode'] = 'OPAQUE'
    binary = bytearray()
    for index, view in enumerate(source.doc['bufferViews']):
        old_start = view.get('byteOffset', 0)
        payload = rgba.tobytes() if index == selected else source.binary[old_start:old_start + view['byteLength']]
        binary.extend(b'\0' * (-len(binary) % 4))
        view['byteOffset'], view['byteLength'] = len(binary), len(payload)
        binary.extend(payload)
    source.doc['buffers'][0]['byteLength'] = len(binary)
    binary.extend(b'\0' * (-len(binary) % 4))
    encoded = json.dumps(source.doc, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    data = struct.pack('<4sII', b'glTF', 2, 28 + len(encoded) + len(binary))
    data += struct.pack('<I4s', len(encoded), b'JSON') + encoded
    data += struct.pack('<I4s', len(binary), b'BIN\0') + binary
    Path(path).write_bytes(data)


def preview_head(glb, inverse, output):
    for mesh_index, mesh in enumerate(glb.doc['meshes'][:2]):
        primitive_indices = [0]
        for primitive_index in primitive_indices:
            vertices, triangles, uv, primitive = glb.local_primitive(mesh_index, primitive_index, inverse)
            # Native glTF V is down; Blender V is up.
            uv[:, 1] = 1 - uv[:, 1]
            obj = mesh_object('Reference ' + mesh.get('name', str(mesh_index)), vertices, triangles.tolist(), uv)
            mat = material('Reference skin ' + str(mesh_index), '#c8a18b', .75)
            pbr = glb.doc['materials'][primitive['material']]['pbrMetallicRoughness']
            image_index = glb.doc['textures'][pbr['baseColorTexture']['index']]['source']
            image = glb.doc['images'][image_index]
            view = glb.doc['bufferViews'][image['bufferView']]
            file = output / ('reference-image-' + str(mesh_index) + '.png')
            file.write_bytes(glb.binary[view['byteOffset']:view['byteOffset'] + view['byteLength']])
            texture = mat.node_tree.nodes.new('ShaderNodeTexImage')
            texture.image = bpy.data.images.load(str(file))
            texture.image.pack()
            bsdf = mat.node_tree.nodes.get('Principled BSDF')
            mat.node_tree.links.new(texture.outputs['Color'], bsdf.inputs['Base Color'])
            if mesh_index == 1:
                mat.node_tree.links.new(texture.outputs['Alpha'], bsdf.inputs['Alpha'])
                mat.surface_render_method = 'DITHERED'
            obj.data.materials.append(mat)


def render_previews(output, sex):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 4
    scene.render.resolution_x = scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.world.color = (.28, .28, .28)
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = -1
    for location, energy, size in [((-.5, -.55, .65), 45, .5), ((.45, -.3, .35), 18, .6), ((.1, .4, .55), 35, .4)]:
        bpy.ops.object.light_add(type='AREA', location=location)
        light = bpy.context.object
        light.data.energy, light.data.shape, light.data.size = energy, 'DISK', size
        light.rotation_euler = (Vector((0, 0, .12)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = .40 if sex == 'female' else .36
    scene.camera = camera
    focus = Vector(blender((0, .108, -.025)))
    cameras = {'front': (0, .12, .60), 'side': (.60, .12, 0), 'rear': (0, .12, -.60),
               'isometric': (-.39, .20, .51)}
    for name, point in cameras.items():
        camera.location = Vector(blender(point))
        camera.rotation_euler = (focus - camera.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(output / ('hair-' + name + '.png'))
        bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--body', type=Path, required=True)
    parser.add_argument('--sex', choices=('male', 'female'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    if hasattr(bpy.context.preferences.filepaths, 'use_save_preview_images'):
        bpy.context.preferences.filepaths.use_save_preview_images = False
    if hasattr(bpy.context.preferences.filepaths, 'file_preview_type'):
        bpy.context.preferences.filepaths.file_preview_type = 'NONE'
    source = json.loads(args.source.read_text())
    profile = source['profiles'][args.sex]
    glb = Glb(args.body)
    head_world = glb.head_world()
    inverse = head_world.inverted()
    head, triangles, _, _ = glb.local_primitive(0, 0, inverse)
    vertices, normals, uv, progress, faces, locks, collision = build_hair(profile, head, triangles)
    progress,pinning=pin_scalp_clearance(vertices,progress,faces,profile,head,triangles)
    normals = geometric_normals(vertices, faces)
    obj = mesh_object(profile['material_name'], vertices, faces, uv, normals)
    color = obj.data.color_attributes.new(name='Hair root pin', type='BYTE_COLOR', domain='POINT')
    rgba = np.ones((len(vertices), 4), dtype=np.float32)
    rgba[:, 3] = progress
    color.data.foreach_set('color', rgba.ravel())
    obj.data.color_attributes.active_color_index = 0
    obj.data.color_attributes.render_color_index = 0
    obj.data.materials.append(material(profile['material_name'], profile['color_srgb']))
    obj['rabbit_lands_concept_hair'] = True
    obj['space'] = 'canonical Head local; attach rigidly to Head with identity transform'
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    export = args.output / 'concept_hair.glb'
    bpy.ops.export_scene.gltf(filepath=str(export), export_format='GLB', use_selection=True,
                              export_yup=True, export_animations=False, export_apply=False,
                              export_extras=True, export_materials='EXPORT',
                              export_vertex_color='ACTIVE', export_all_vertex_colors=False)
    pack_root_colors(export)
    obj.data.calc_loop_triangles()
    np.savez_compressed(args.output / 'hair-head-local.npz', vertices=vertices, normals=normals,
                        uv=uv, root_progress=progress,
                        triangles=np.array([list(t.vertices) for t in obj.data.loop_triangles], dtype=np.int32))
    preview_head(glb, inverse, args.output)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output / 'authoring.blend'))
    if args.render:
        render_previews(args.output, args.sex)
    report = {'source': str(args.source.resolve()), 'source_sha256': digest(args.source),
              'source_body': str(args.body.resolve()), 'source_body_sha256': digest(args.body),
              'tool_sha256': digest(__file__), 'sex': args.sex, 'blender': bpy.app.version_string,
              'head_world_matrix': [list(row) for row in head_world],
              'attachment': 'Rigid canonical Head local; identity offset; GLB has no skeleton',
              'bounds_head_local': [vertices.min(0).tolist(), vertices.max(0).tolist()],
              'vertices': len(vertices), 'triangles': len(obj.data.loop_triangles),
              'materials': 1, 'textures': 0, 'mesh': str(export.resolve()), 'mesh_sha256': digest(export),
              'color_alpha_contract': 'COLOR_0 alpha: undercoat/cap0, lock root0 smoothly to1 at35percent; opacity remains OPAQUE. RGB white.',
              'color_encoding': 'normalized RGBA8; four bytes per exported vertex; back-face culling enabled',
              'mesh_bytes': export.stat().st_size, 'locks': locks, 'scalp_clearance': collision,
              'deformation_pin': pinning,
              'limitations': ['Rear shape inferred from front/side/isometric concept views.',
                             'Static authored hair; no physics. Headgear must use the existing hide-hair policy.',
                             'Constant PBR pigment is a geometry study; directional strand paint can be added in a shared small atlas.']}
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('RL_CONCEPT_HAIR', json.dumps({k: report[k] for k in ('sex', 'vertices', 'triangles', 'mesh_bytes', 'scalp_clearance')}))


if __name__ == '__main__':
    main()
