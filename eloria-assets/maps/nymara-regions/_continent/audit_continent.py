"""Read emitted master/territory/chunk geometry and verify its common surface.

This audit does not rebuild or repair maps. The only output is its JSON report.
Every actual two-metre terrain triangle must occur once in the shared source,
master, union of territories, and union of streaming chunks. Attribute checks
use the emitted source vertex buffer, including colours, normals and UVs.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import re
import struct
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / '_toolkit'))
import glb_reader as GR
from world_layout import triangle_sample

SHAPING_SOURCES=('landscape.py','world_layout.py','content.py','assemblies.py','crown_support.py','westhaven_support.py','ferry_export.py','ferry_support.py','mirror_support.py','manymouth_support.py','mirror_streets.py','four_gates_support.py','amberwood_support.py','amberwood_access.py','mirror_lake_support.py','ssarathi_bank_support.py','manymouth_boats.py','terrain_export.py','scene_io.py','grey_crossings.py','four_gates_sage.py','door_approaches.py','hull_settle.py','resource_trails.py','object_edits.py','winding.py','river_crossings.py','reach_links.py','authored_points.py','authoring.py','authoring_catalog.py','saved_seam_profile.py','saved-seam-grey-whitehorn-v1.json','saved_post_support_profile.py','saved-seam-post-support-v1.json','bridge_export.py','bridge_prepare.py','coastal_prepare.py','coastal_bridge_export.py','bridge_profiles.py','sea_crossings.py','coastal_bank_fit.py','../_northern/requirements.txt')
EXPORT_SOURCES={'build_continent.py','scene_io.py','terrain_export.py','biome_blend.py','compact_glb_images.py','bridge_export.py','coastal_prepare.py','coastal_bridge_export.py','bridge_profiles.py','sea_crossings.py','coastal_bank_fit.py','../_northern/requirements.txt','ferry_export.py','crossings.py','amberwood_access.py','manymouth_access.py','manymouth_village_streets.py','collision_export.py','mirror_access_geometry.py','grey_crossings.py','access_decks.py'}
SHAPING_SOURCES+=('storage_bounds.py',)
EXPORT_SOURCES.add('storage_bounds.py')


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def geometry_dependencies():
    import shapely
    return {'shapely':shapely.__version__,'geos':shapely.geos_version_string}


class Inputs:
    def __init__(self):
        self.hashes = {}
        self.stats = {}

    def digest(self, path):
        path = Path(path).resolve()
        if str(path) not in self.hashes:
            require(path.is_file(), f'Missing input: {path}')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            self.hashes[str(path)] = digest.hexdigest()
            stat = path.stat()
            self.stats[str(path)] = (stat.st_size, stat.st_mtime_ns)
        return self.hashes[str(path)]

    def json(self, path):
        self.digest(path)
        return json.loads(Path(path).read_text(encoding='utf-8'))

    def unchanged(self):
        return all(Path(p).is_file() and (Path(p).stat().st_size, Path(p).stat().st_mtime_ns) == v
                   for p, v in self.stats.items())


def ownership_raster(polygons, bounds, cell=2.0):
    """Independent scan conversion; detect gaps, overlap and unclosed outlines."""
    x0, z0, x1, z1 = bounds
    nx, nz = int(round((x1 - x0) / cell)), int(round((z1 - z0) / cell))
    owner = np.full((nz, nx), -1, dtype=np.int16)
    coverage = np.zeros((nz, nx), dtype=np.uint8)
    for region_index, (region, polygon) in enumerate(polygons.items()):
        p = np.asarray(polygon, dtype=float)
        require(len(p) >= 3 and np.isfinite(p).all(), f'{region}: invalid ownership polygon')
        a, b = p, np.roll(p, -1, axis=0)
        for row in range(nz):
            z = z0 + (row + .5) * cell
            active = (a[:, 1] > z) != (b[:, 1] > z)
            lo, hi = a[active], b[active]
            crossings = np.sort(lo[:, 0] + (z - lo[:, 1]) * (hi[:, 0] - lo[:, 0]) / (hi[:, 1] - lo[:, 1]))
            require(len(crossings) % 2 == 0, f'{region}: odd scanline crossings at {z}')
            for left, right in crossings.reshape(-1, 2):
                start = max(0, int(np.ceil((left - x0) / cell - .5)))
                stop = min(nx, int(np.ceil((right - x0) / cell - .5)))
                coverage[row, start:stop] += 1
                owner[row, start:stop] = region_index
    require(np.all(coverage == 1), f'Ownership has {int((coverage == 0).sum())} missing and {int((coverage > 1).sum())} overlapping source cells')
    return owner


def parent_names(document):
    parents = {child: i for i, node in enumerate(document['nodes']) for child in node.get('children', [])}
    result = []
    for i in range(len(document['nodes'])):
        names, seen = [], set()
        while i is not None:
            require(i not in seen, 'Cyclic scene hierarchy')
            seen.add(i)
            names.append(document['nodes'][i].get('name', ''))
            i = parents.get(i)
        result.append(names)
    return result


def image_digest(document, body, index, path, inputs, client):
    image = document['images'][index]
    if 'uri' in image:
        require('://' not in image['uri'] and not image['uri'].startswith('data:'), f'{path}: nonlocal image URI')
        target = (path.parent / image['uri']).resolve()
        require(target.is_relative_to(client.resolve()), f'{path}: external image escapes client workspace')
        return inputs.digest(target)
    view = document['bufferViews'][image['bufferView']]
    start = view.get('byteOffset', 0)
    return hashlib.sha256(body[start:start + view['byteLength']]).hexdigest()


def material_signature(document, body, index, path, inputs, client):
    def texture(index):
        entry = document['textures'][index]
        return {'imageSha256': image_digest(document, body, entry['source'], path, inputs, client),
                'sampler': document.get('samplers', [])[entry['sampler']] if 'sampler' in entry else {}}
    def normalize(value):
        if isinstance(value, list):
            return [normalize(v) for v in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, value in value.items():
            if key == 'name':
                continue
            if key.endswith('Texture') and isinstance(value, dict) and 'index' in value:
                result[key] = {**normalize({k:v for k,v in value.items() if k != 'index'}), 'texture': texture(value['index'])}
            else:
                result[key] = normalize(value)
        return result
    return json.dumps(normalize(document['materials'][index]), sort_keys=True, separators=(',', ':'))


class Surface:
    def __init__(self, bounds, polygons, inputs=None, client=CLIENT, cell=2.0):
        self.bounds = np.asarray(bounds, dtype=float)
        self.cell = cell
        self.ids = list(polygons)
        self.owner = ownership_raster(polygons, bounds, cell)
        self.nz, self.nx = np.array(self.owner.shape) + 1
        self.attributes = np.full((self.nx * self.nz, 12), np.nan)
        self.source_counts = np.zeros(self.owner.size * 2, dtype=np.uint32)
        self.inputs = inputs or Inputs()
        self.client = Path(client)
        self.material = None
        self.max_error = defaultdict(float)

    def vertex_indices(self, positions):
        horizontal = positions[:, [0, 2]]
        coordinates = (horizontal - self.bounds[:2]) / self.cell
        rounded = np.rint(coordinates).astype(np.int64)
        require(np.max(np.abs(coordinates - rounded), initial=0) < 0.0001, 'Terrain has vertices off the common two-metre lattice')
        require(np.all((rounded[:, 0] >= 0) & (rounded[:, 0] < self.nx) & (rounded[:, 1] >= 0) & (rounded[:, 1] < self.nz)), 'Terrain vertices outside continent bounds')
        return rounded[:, 1] * self.nx + rounded[:, 0]

    def face_indices(self, vertices, indices):
        triangles = vertices[indices.reshape(-1, 3)]
        x, z = triangles % self.nx, triangles // self.nx
        cx, cz = x.min(axis=1), z.min(axis=1)
        require(np.all((x.max(axis=1) - cx == 1) & (z.max(axis=1) - cz == 1)), 'Terrain contains non-source triangles or degenerate faces')
        code = np.sort((x - cx[:, None]) + (z - cz[:, None]) * 2, axis=1)
        first = np.all(code == [0, 1, 2], axis=1)
        second = np.all(code == [1, 2, 3], axis=1)
        require(np.all(first | second), 'Terrain uses a different diagonal than the shared source')
        winding = (x[:,1]-x[:,0])*(z[:,2]-z[:,0])-(z[:,1]-z[:,0])*(x[:,2]-x[:,0])
        require(np.all(winding < 0), 'Terrain face winding is reversed')
        return (cz * (self.nx - 1) + cx) * 2 + second.astype(int)

    def read(self, path, counts, region=None, source=False, bounds=None, manifest=None):
        path = Path(path).resolve()
        self.inputs.digest(path)
        doc, body = GR.load(path)
        matrices, _ = GR.hierarchy(doc)
        names = parent_names(doc)
        vertex_count = face_count = 0
        signatures = {}
        declared = manifest.get('externalResources', {}) if manifest else None
        actual_dependencies = {}
        for image_index, image in enumerate(doc.get('images', [])):
            if 'uri' in image:
                uri = image['uri']
                actual_dependencies[uri] = image_digest(doc, body, image_index, path, self.inputs, self.client)
        if declared is not None:
            require(actual_dependencies == declared, f'{path}: declared external resources differ from actual GLB image dependencies')
        primitive_cache = {}
        for index, node in enumerate(doc['nodes']):
            if 'mesh' not in node:
                continue
            matrix = matrices[index].copy()
            if region is not None:
                matrix[:3, 3] += self.translations[region]
            terrain_names = [n for n in names[index] if n.startswith('Terrain_')]
            territory = None
            if terrain_names:
                territory = next((r for r in self.ids if any(n.startswith('Terrain_' + r + '_') for n in terrain_names)), None)
                require(territory is not None, f'{path}: legacy or unidentified visible terrain {terrain_names[0]}')
                require(region is None or territory == region, f'{path}: contains another territory\'s terrain')
            if territory is None and bounds is None:
                continue
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                position_index = primitive['attributes']['POSITION']
                if position_index not in primitive_cache:
                    primitive_cache[position_index] = GR.accessor(doc, body, position_index).astype(float)
                raw = primitive_cache[position_index]
                positions = raw @ matrix[:3, :3].T + matrix[:3, 3]
                if bounds is not None:
                    # Use actual vertices, not merely a placement origin or bbox centre.
                    local = positions - self.translations[region]
                    require(np.all(local >= np.asarray(bounds['min']) - .005) and np.all(local <= np.asarray(bounds['max']) + .005), f'{path}: rendered geometry extends outside declared loading bounds')
                if territory is None:
                    continue
                require(primitive.get('mode', 4) == 4 and 'indices' in primitive, f'{path}: terrain is not indexed triangles')
                attrs = primitive['attributes']
                require(all(k in attrs for k in ('NORMAL', 'TEXCOORD_0', 'COLOR_0')), f'{path}: terrain lost normals, UVs or biome colours')
                normals = GR.accessor(doc, body, attrs['NORMAL']).astype(float) @ np.linalg.inv(matrix[:3, :3])
                normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
                uv = GR.accessor(doc, body, attrs['TEXCOORD_0'])
                color = GR.accessor(doc, body, attrs['COLOR_0'])
                require(color.shape[1] == 4, f'{path}: terrain colour schema changed')
                values = np.c_[positions, normals, uv, color]
                require(np.isfinite(values).all(), f'{path}: non-finite terrain attributes')
                vertices = self.vertex_indices(positions)
                if source:
                    present = np.isfinite(self.attributes[vertices, 0])
                    require(np.allclose(self.attributes[vertices[present]], values[present], atol=1e-5, rtol=0), f'{path}: source split has inconsistent shared attributes')
                    self.attributes[vertices] = values
                else:
                    difference = np.abs(self.attributes[vertices] - values)
                    for label, lo, hi, tolerance in (('position',0,3,.0001),('normal',3,6,.000002),('UV',6,8,.000002),('color',8,12,.000002)):
                        error = float(difference[:, lo:hi].max(initial=0))
                        self.max_error[label] = max(self.max_error[label], error)
                        require(np.isfinite(error) and error <= tolerance, f'{path}: shared {label} changed by {error}')
                faces = self.face_indices(vertices, GR.accessor(doc, body, primitive['indices']).ravel().astype(np.int64))
                owner = self.owner.ravel()[faces // 2]
                require(np.all(owner == self.ids.index(territory)), f'{path}: terrain faces cross named ownership')
                np.add.at(counts, faces, 1)
                material = primitive.get('material')
                require(material is not None, f'{path}: unmaterialed terrain')
                if material not in signatures:
                    signatures[material] = material_signature(doc, body, material, path, self.inputs, self.client)
                if self.material is None:
                    self.material = signatures[material]
                require(signatures[material] == self.material, f'{path}: terrain material or texture changes at partition')
                vertex_count += len(vertices)
                face_count += len(faces)
        return {'terrainTriangles':face_count, 'terrainVertices':vertex_count, 'externalDependencies':len(actual_dependencies)}

    def complete(self, counts, label):
        missing, duplicate = int((counts == 0).sum()), int((counts > 1).sum())
        require(not missing and not duplicate, f'{label}: {missing} missing and {duplicate} duplicated visible terrain triangles')


# A road contract needs a way across. An open border publishes the lanes its
# ground offers - the gate's among them, carried by the border lanes nearest
# its surveyed ones - which a narrow pass can make fewer than a gate's seven.
GATE_LANES = 1


def audit_frames(publication, manifests, translations):
    checks = 0
    triggers = set()
    arrivals = []
    def position(region, tile):
        origin = manifests[region]['coordinateTransform']['serverOrigin']
        return np.array([tile[0] + .5 - origin[0] + translations[region][0],
                         origin[1] - tile[1] - .5 + translations[region][2]])
    def tile_at(region, point):
        """The tile of one map under a global cell centre: position() inverted."""
        transform = manifests[region]['coordinateTransform']
        origin, cells = transform['serverOrigin'], transform.get('serverCells')
        tile = [int(round(point[0] - translations[region][0] + origin[0] - .5)),
                int(round(origin[1] + translations[region][2] - point[1] - .5))]
        if cells and not (0 <= tile[0] < cells[0] and 0 <= tile[1] < cells[1]):
            return None
        return tile if np.allclose(position(region, tile), point, atol=1e-6, rtol=0) else None
    for link in publication['connections']:
        if link['type'] != 'walk':
            continue
        a, b = link['ends']
        frames = [end['frame'] for end in (a,b)]
        global_anchors = [np.asarray(end['frame']['anchor']) + translations[end['region']] for end in (a,b)]
        require(np.allclose(global_anchors[0], global_anchors[1], atol=.00001, rtol=0), f'{link["id"]}: reciprocal global frame anchors differ')
        require(np.allclose(frames[0]['outward'], -np.asarray(frames[1]['outward']), atol=1e-9), f'{link["id"]}: reciprocal directions differ')
        for source, target in ((a,b),(b,a)):
            region = source['region']
            # A border no road crosses has no threshold in its territories' packages;
            # its frame is the publication's alone.
            if link.get('road', True):
                stored = [f for f in manifests[region]['streamingBorders'] if f['id'] == link['id']]
                require(len(stored) == 1 and stored[0]['anchor'] == source['frame']['anchor'] and stored[0]['outward'] == source['frame']['outward'], f'{link["id"]}: territory frame differs from publication')
            # A crossing hands the walker over at the very cell they stand on, so every
            # departure must name a cell of the other map. This was checked against the far
            # side's own lane list, which held for a gate of seven lanes either side of one
            # anchor but cannot hold for a border crossed along its length: each step in the
            # boundary leaves one more tile outside it than inside, so the two lists are the
            # same ground in different numbers. The reading is exact instead - one metre grid,
            # whole-tile origins, whole-metre translations - and the ground it lands on is
            # judged by the served grids in export_contracts.
            require(len(source['lanes']) >= GATE_LANES, f'{link["id"]}: no way across')
            require(len({tuple(lane['tile']) for lane in source['lanes']}) == len(source['lanes']),
                    f'{link["id"]}: a crossing lane is declared twice')
            for lane in source['lanes']:
                point = position(region, lane['tile'])
                landing = tile_at(target['region'], point)
                require(landing is not None, f'{link["id"]}: crossing changes global actor coordinates')
                # One step for a lane on the border's first tile, two for a gate's, which
                # its survey lays a metre either side of the seam's line.
                require(1 <= max(abs(lane['tile'][0] - lane['arrival'][0]),
                                 abs(lane['tile'][1] - lane['arrival'][1])) <= 2,
                        f'{link["id"]}: a lane and the ground a walker arrives on are not beside each other')
                trigger = (region, *lane['tile'])
                require(trigger not in triggers, f'{link["id"]}: duplicate departure trigger')
                triggers.add(trigger)
                arrivals.append((target['region'], *landing))
                checks += 1
    require(not set(arrivals) & triggers, 'A crossing arrival immediately triggers another crossing')
    return {'checkedLaneDirections':checks}


def audit_collision(surface, region, manifest, package, inputs, server=None):
    path = package / 'collision.bin'
    require(path.is_file(), f'{region}: missing EWCG collision')
    inputs.digest(path)
    raw = path.read_bytes()
    magic, version, _, width, height = struct.unpack_from('<4sHHII', raw)
    origin = manifest['coordinateTransform']['serverOrigin']
    cells = manifest['coordinateTransform']['serverCells']
    require(magic == b'EWCG' and version == 2 and [width,height] == [v*2 for v in cells], f'{region}: EWCG dimensions/format differ from its territory frame')
    require(len(raw) == 16 + width*height, f'{region}: EWCG byte length mismatch')
    collision = manifest['collision']
    require(collision.get('sourceGlbSha256') == inputs.digest(package/'world.glb'), f'{region}: collision is not derived from the current emitted geometry')
    encoding = collision['heightEncoding']
    grid = np.frombuffer(raw, dtype=np.uint8, offset=16).reshape(height,width)
    x0,z1 = -origin[0],origin[1]
    lx,lz = np.meshgrid(x0+(np.arange(width)+.5)*.5, z1-(np.arange(height)+.5)*.5)
    gx,gz = lx+surface.translations[region][0], lz+surface.translations[region][2]
    ground = triangle_sample(surface.attributes[:,1].reshape(surface.nz,surface.nx),gx,gz,*surface.bounds[:2],surface.cell)
    doc,body = GR.load(package/'world.glb')
    names = parent_names(doc)
    decks = [i for i,node in enumerate(doc['nodes']) if 'mesh' in node and any(n.startswith('Walk_') for n in names[i]) and not any(any(word in n.lower() for word in ('ceiling','soffit','underside','roof')) for n in names[i])]
    triangles = GR.triangles(doc,body,decks)
    covered, deck = GR.rasterise(triangles,width,height,x0,z1,.5,upward=1/np.sqrt(1+.65**2)-1e-9)
    expected = np.where(covered & (deck >= ground-.03), deck, ground)
    valid = grid > 0
    decoded = encoding['origin'] + grid.astype(float)*encoding['step']
    errors = np.abs(decoded[valid]-expected[valid])
    maximum = float(errors.max(initial=0))
    require(maximum <= encoding['step']*.501+.003, f'{region}: EWCG support height differs from actual emitted terrain/deck by {maximum:.4f}m')
    result = {'halfCells':int(valid.sum()),'maximumQuantizationErrorMetres':maximum,'encodingStepMetres':encoding['step']}
    if server is not None:
        server_path = server/'tools/collision'/f'{region}.escg.gz'
        inputs.digest(server_path)
        data = gzip.decompress(server_path.read_bytes())
        magic,version,stage,size = struct.unpack_from('<4sHHI',data)
        require(magic == b'ESCG' and version == 1 and cells == [size,size] and len(data) == 12+size*size, f'{region}: server collision frame differs from EWCG')
        served = np.frombuffer(data,dtype=np.uint8,offset=12).reshape(size,size)
        conservative = valid.reshape(size,2,size,2).all(axis=(1,3))
        require(not np.any((served>0)&~conservative), f'{region}: server opens tiles unsupported by the four authored half-cells')
        result.update(serverWalkableTiles=int((served>0).sum()),serverStageMillimetres=stage)
    return result


def composition_algorithm_sha(path):
    """Match the composition certificate without importing/running its builder."""
    source=Path(path).read_text(encoding='utf-8');lines=source.splitlines(keepends=True)
    functions={node.name:node for node in ast.parse(source).body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    blocks=[]
    for name in ('prepare','ferry_landing'):
        require(name in functions,f'Composition builder omits {name}')
        node=functions[name]
        first=min([node.lineno,*[d.lineno for d in node.decorator_list]])
        blocks.append(''.join(inspect.getblock(lines[first-1:])))
    return hashlib.sha256(''.join(blocks).encode()).hexdigest()


def audit_shaping(client, continent, composition, inputs):
    plan_sha=inputs.digest(continent/'diagonal-plan.json')
    require(composition['planSha256']==plan_sha,'Composition uses a different landscape plan')
    shaping={str((continent/name).resolve().relative_to(client.resolve())).replace('\\','/'):name for name in SHAPING_SOURCES}
    sources={relative.replace('\\','/'):expected for relative,expected in composition['sources'].items()}
    missing=set(shaping)-sources.keys()
    require(not missing,'Composition is missing shaping source certificates: '+', '.join(sorted(missing)))
    for relative,name in shaping.items():
        expected=sources[relative];path=(client/relative).resolve()
        require(path==(continent/name).resolve(),f'Composition shaping source resolves outside its authored location: {relative}')
        require(inputs.digest(path)==expected,f'Authored landscape changed after composition: {relative}')
    builder=continent/'build_continent.py';inputs.digest(builder)
    algorithm_sha=composition_algorithm_sha(builder)
    require(composition.get('compositionAlgorithmSha256')==algorithm_sha,'Composition algorithm changed after composition')
    entrance_sha=inputs.digest(continent/'legacy-server-profile/config/eloria/maps.txt')
    require(composition.get('entranceProfileSha256')==entrance_sha,'Authored entrance profile changed after composition')
    edits_path=continent/'continent-edits.json'
    edits_sha=inputs.digest(edits_path) if edits_path.exists() else hashlib.sha256(b'').hexdigest()
    require(composition.get('objectEditsSha256',hashlib.sha256(b'').hexdigest())==edits_sha,'Object edits (continent-edits.json) changed after composition')
    dependencies=geometry_dependencies()
    require(composition.get('geometryDependencies')==dependencies,'Composition geometry dependencies changed after composition')
    return {'planSha256':plan_sha,'objectEditsSha256':edits_sha,'compositionAlgorithmSha256':algorithm_sha,'entranceProfileSha256':entrance_sha,'geometryDependencies':dependencies,'shapingModules':list(SHAPING_SOURCES)}


def exported_frames(client, exports, plan, master_sha, plan_sha, inputs):
    """Read the new export's frames without consulting an older publication."""
    plan_regions={r['id']:r for r in plan['regions']}
    require(len(plan_regions)==len(plan['regions']) and set(exports['regions'])==set(plan_regions),
            'Exported named territory set differs from continent plan')
    frames={};manifests={};packages={}
    for region in plan_regions:
        path=Path(exports['regions'][region]['world'])
        if not path.is_absolute():path=client/path
        path=path.resolve()
        require(path.is_relative_to(client.resolve()) and path.name=='world.json',f'{region}: exported territory manifest escapes the client')
        manifest=inputs.json(path);geo=manifest['continentGeography'];frame=manifest['coordinateTransform']
        require(manifest['asset']['id']==region,f'{region}: export points to another named territory')
        require(geo.get('geometryMode')=='continent-chunks-v1',f'{region}: named manifest is not a shared-continent export')
        source=manifest['singleContinentSource']
        require(source['masterSha256']==master_sha,f'{region}: territory references a different master')
        require(source['planSha256']==plan_sha,f'{region}: territory references a different landscape plan')
        translation=np.asarray(geo['translation'],float);center=np.asarray(plan_regions[region]['center'],float)
        require(translation.shape==(3,) and np.isfinite(translation).all() and
                np.allclose(translation,[center[0],0,center[1]],atol=1e-6,rtol=0),f'{region}: translation differs from the authored territory centre')
        origin=np.asarray(frame['serverOrigin'],float);cells=np.asarray(frame['serverCells'],float)
        require(origin.shape==(2,) and cells.shape==(2,) and np.isfinite(origin).all() and
                np.isfinite(cells).all() and (cells>0).all() and np.equal(cells,np.rint(cells)).all(),
                f'{region}: invalid exported server address frame')
        require(frame.get('metresPerTile')==1 and frame.get('invertServerY') is True and
                frame.get('origin')==[0,0,0],f'{region}: unsupported exported server coordinate transform')
        address=frame['addressableWorldBounds']
        expected={'min':[-origin[0],origin[1]-cells[1]],'max':[cells[0]-origin[0],origin[1]]}
        require(all(np.array_equal(address[k],expected[k]) for k in ('min','max')),f'{region}: exported address bounds disagree with its origin/dimensions')
        polygon=np.asarray(geo['ownershipPolygon'],float)
        require(polygon.ndim==2 and polygon.shape[1]==2 and len(polygon)>=3 and np.isfinite(polygon).all(),
                f'{region}: invalid exported ownership polygon')
        local=polygon-translation[[0,2]]
        require(np.all(local>=np.asarray(address['min'])-.001) and np.all(local<=np.asarray(address['max'])+.001),
                f'{region}: ownership extends beyond its exported server address')
        frames[region]={'translation':geo['translation'],'ownershipPolygon':geo['ownershipPolygon'],
                        'serverOrigin':frame['serverOrigin'],'serverCells':frame['serverCells']}
        manifests[region]=manifest;packages[region]=path.parent
    return frames,manifests,packages


# ---------------------------------------------------------------------------------------------------------------------
# The owner's road rules (the roads pass, R1, 2026-09-16), checked on the emitted terrain against the composed roads the
# geometry export records in roads.json: no road over river water outside a bridge site's span; a site's crossing no
# more than 4 m longer than the shortest crossing within 40 m along its river and at least 70 degrees to the flow;
# sites on one river at least the policy's spacing apart; no bridge pier taller than 8 m; no road station and no
# bridge floor more than 1.5 m above the ground outside site spans and designed decks.
ROAD_RULE_STATION_METRES = 2.
ROAD_RULE_FLOAT_METRES = 1.5
ROAD_RULE_PIER_METRES = 8.
ROAD_RULE_SHORTEST_EXCESS_METRES = 4.
ROAD_RULE_SQUARE_DEGREES = 70.
ROAD_RULE_WINDOW_METRES = 40.
ROAD_RULE_SPAN_HALF_METRES = 6.


def resample_stations(points, step=ROAD_RULE_STATION_METRES):
    """Stations every ``step`` metres along an xyz polyline (y linear between its points)."""
    p = np.asarray(points, float)
    if len(p) < 2:
        return p.reshape(-1, 3)
    seg = np.linalg.norm(np.diff(p[:, [0, 2]], axis=0), axis=1)
    p = p[np.r_[True, seg > 1e-9]]
    if len(p) < 2:
        return p
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, [0, 2]], axis=0), axis=1))]
    s = np.r_[np.arange(0, cum[-1], step), cum[-1]]
    return np.c_[np.interp(s, cum, p[:, 0]), np.interp(s, cum, p[:, 1]), np.interp(s, cum, p[:, 2])]


def site_span_boxes(sites, landing):
    """Each site's span plus its landings as (origin, axis, length, half width)."""
    boxes = []
    for site in sites:
        left, right = np.asarray(site['wetEdges'][0], float), np.asarray(site['wetEdges'][1], float)
        axis = right - left
        length = float(np.linalg.norm(axis))
        axis = axis / max(length, 1e-9)
        boxes.append((left - axis * landing, axis, length + 2 * landing, ROAD_RULE_SPAN_HALF_METRES))
    return boxes


def inside_boxes(xz, boxes):
    xz = np.asarray(xz, float).reshape(-1, 2)
    inside = np.zeros(len(xz), bool)
    for origin, axis, length, half in boxes:
        rel = xz - origin
        along = rel @ axis
        across = rel @ np.array([-axis[1], axis[0]])
        inside |= (along >= -1e-9) & (along <= length + 1e-9) & (np.abs(across) <= half)
    return inside


def authored_deck_height(xz, triangles):
    """Highest emitted authored walk-deck surface under each XZ point.

    This uses the actual transformed triangles instead of their bounding box,
    so an uncovered corner beside a diagonal bridge remains outside the span.
    """
    xz = np.asarray(xz, float).reshape(-1, 2)
    result = np.full(len(xz), -np.inf)
    for triangle in np.asarray(triangles, float).reshape(-1, 3, 3):
        projected = triangle[:, [0, 2]]
        a, b, c = projected
        ab, ac = b - a, c - a
        denominator = ab[0] * ac[1] - ab[1] * ac[0]
        if abs(denominator) <= 1e-12:
            continue
        relative = xz - a
        u = (relative[:, 0] * ac[1] - relative[:, 1] * ac[0]) / denominator
        v = (ab[0] * relative[:, 1] - ab[1] * relative[:, 0]) / denominator
        w = 1. - u - v
        inside = (u >= -1e-9) & (v >= -1e-9) & (w >= -1e-9)
        height = w * triangle[0, 1] + u * triangle[1, 1] + v * triangle[2, 1]
        result[inside] = np.maximum(result[inside], height[inside])
    return result


def saved_deck_height(xz, deck_groups):
    """Sample only emitted, certified walk floors whose actual bounds meet the road."""
    xz = np.asarray(xz, float).reshape(-1, 2)
    result = np.full(len(xz), -np.inf)
    for low, high, triangles, *_ in deck_groups:
        nearby = np.all((xz >= low) & (xz <= high), axis=1)
        if nearby.any():
            result[nearby] = np.maximum(result[nearby], authored_deck_height(xz[nearby], triangles))
    return result


def saved_road_station_heights(stations, groups):
    """Reconcile only source endpoints within emitted vertex encoding error.

    Interior coverage remains exact. At a missing endpoint, use the highest
    closest face whose distance is bounded by its interpolated float32 vertex
    error after the actual node transform. Original station XZ is never moved.
    """
    xz = stations[:, [0, 2]]
    heights = saved_deck_height(xz, groups)
    reconciled = []
    for index in np.flatnonzero(~np.isfinite(heights)):
        if index not in (0, len(stations) - 1):
            continue
        point = xz[index]
        candidates = []
        for _, _, triangles, *encoding in groups:
            if not encoding:
                continue
            errors = encoding[0]
            for triangle, error in zip(triangles, errors):
                projected = triangle[:, [0, 2]]
                ab, ac = projected[1] - projected[0], projected[2] - projected[0]
                if abs(ab[0] * ac[1] - ab[1] * ac[0]) <= 1e-12:
                    continue
                a = projected
                b = np.roll(projected, -1, axis=0)
                delta = b - a
                squared = (delta * delta).sum(axis=1)
                amount = np.clip(((point - a) * delta).sum(axis=1) / np.maximum(squared, 1e-30), 0., 1.)
                # A perpendicular edge projection can lie outside an
                # anisotropic encoding box although its endpoint vertex is
                # supported, so consider both edge projections and vertices.
                for weights in (amount, np.zeros(3)):
                    nearest = a + weights[:, None] * delta
                    distances = np.linalg.norm(nearest - point, axis=1)
                    for edge, weight in enumerate(weights):
                        following = (edge + 1) % 3
                        bound_xz = error[edge] * (1. - weight) + error[following] * weight
                        bound = float(np.linalg.norm(bound_xz))
                        if np.all(np.abs(nearest[edge] - point) <= bound_xz) and distances[edge] <= bound:
                            height = triangle[edge, 1] * (1. - weight) + triangle[following, 1] * weight
                            candidates.append((float(height), float(distances[edge]), bound))
        if candidates:
            height, distance, bound = max(candidates)
            heights[index] = height
            reconciled.append({'station': int(index), 'distanceMetres': distance, 'encodingBoundMetres': bound})
    return heights, reconciled


def saved_walk_surfaces(client, generated, composition, inputs, roads=()):
    """Read certified saved decks and road surfaces from the emitted master.

    The snapshot records select the physical Walk root. A persistent crossing
    claim alone never makes a missing or moved floor pass the road audit.
    """
    import collision_export as C
    master, body = GR.load(generated / 'continent.glb')
    nodes = master['nodes']
    matrices, parents = GR.hierarchy(master)
    names = parent_names(master)
    by_name = defaultdict(list)
    for index, node in enumerate(nodes):
        by_name[node.get('name', '')].append(index)

    def subtree(root):
        pending = [root]
        while pending:
            index = pending.pop()
            yield index
            pending.extend(nodes[index].get('children', ()))

    def triangles_of(indices, *, walkable_only=True, encoding_bounds=False):
        parts, errors = [], []
        for index in indices:
            node = nodes[index]
            if 'mesh' not in node or (walkable_only and any(any(word in name.lower() for word in C.CEILINGS) for name in names[index])):
                continue
            matrix = matrices[index]
            for primitive in master['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode', 4) != 4:
                    continue
                points = GR.accessor(master, body, primitive['attributes']['POSITION']).astype(np.float64)
                order = (GR.accessor(master, body, primitive['indices']).reshape(-1).astype(np.int64)
                         if 'indices' in primitive else np.arange(len(points)))
                world = (matrix[:3, :3] @ points.T).T + matrix[:3, 3]
                parts.append(world[order].reshape(-1, 3, 3))
                if encoding_bounds:
                    accessor = master['accessors'][primitive['attributes']['POSITION']]
                    require(accessor['componentType'] == 5126, 'Saved road positions must use float32 encoding')
                    encoded = points.astype(np.float32)
                    half_ulp = np.maximum(np.abs(np.nextafter(encoded, np.float32(np.inf)).astype(float) - points),
                                          np.abs(points - np.nextafter(encoded, np.float32(-np.inf)).astype(float))) * .5
                    # Project the actual local vertex rounding box through the
                    # actual node matrix; gamma4 bounds the three products/sum
                    # and translation in the float64 coordinate evaluation.
                    linear = np.abs(matrix[[0, 2], :3])
                    eps = np.finfo(float).eps
                    gamma4 = 4. * eps / (1. - 4. * eps)
                    transformed = half_ulp @ linear.T
                    transformed += gamma4 * (np.abs(points) @ linear.T + np.abs(matrix[[0, 2], 3]))
                    require(np.isfinite(transformed).all(), 'Saved road encoding bounds are non-finite')
                    errors.append(transformed[order].reshape(-1, 3, 2))
        triangles = np.concatenate(parts) if parts else np.zeros((0, 3, 3))
        if len(triangles) and walkable_only:
            normal = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
            length = np.linalg.norm(normal, axis=1)
            upward = 1 / np.sqrt(1 + C.MAX_GRADE ** 2) - 1e-9
            triangles = triangles[(length > 1e-9) & (normal[:, 1] > length * upward)]
        return (triangles, np.concatenate(errors)) if encoding_bounds else triangles

    groups, road_groups = [], {}
    records = composition.get('continentAuthoring', {}).get('regions', {})
    published = {road['id']: road for road in roads}
    require(len(published) == len(roads), 'Ambiguous published road identities')
    owner_pattern = '|'.join(re.escape(region) for region in records)
    for region, certificate in records.items():
        source = [path for path in certificate['sources'] if path.endswith('/authoring/continent-authoring.json')]
        require(len(source) == 1, f'{region}: missing unique certified saved snapshot')
        path = client / source[0]
        require(inputs.digest(path) == certificate['sources'][source[0]] == certificate['snapshotSha256'],
                f'{region}: saved snapshot changed after composition')
        snapshot = inputs.json(path)
        require(snapshot['regionId'] == region, f'{region}: saved snapshot region differs from composition')
        for road in snapshot.get('paths', []):
            if road['kind'] != 'road':
                continue
            identity = road.get('replacesRouteId') or road['id']
            require(identity in published, f'{region}: saved road {identity} missing from published routes')
            require(identity not in road_groups, f'{region}: ambiguous saved road identity {identity}')
            # Route IDs may differ from local authoring IDs. Bind both the
            # certified source XZ and the exporter's exact mesh-name format.
            controls = np.asarray([point['position'] for point in road['points']], float)
            controls += np.asarray(snapshot['continentTranslation'], float)
            route = np.asarray(published[identity]['points'], float)
            require(route.shape == controls.shape and np.allclose(route[:, [0, 2]], controls[:, [0, 2]], rtol=0., atol=1e-6),
                    f'{region}: saved road {identity} differs from published route XZ')
            local_name = road['id'] if region == 'sunmane_steppe' else region + '_' + road['id']
            pattern = re.compile(r'Walk_' + re.escape(local_name) + r'_(?:' + owner_pattern + r')_[0-9]+_[0-9]+')
            selected = [index for index, node in enumerate(nodes)
                        if 'mesh' in node and pattern.fullmatch(node.get('name', ''))]
            selected_names = [nodes[index]['name'] for index in selected]
            require(selected and len(selected_names) == len(set(selected_names)),
                    f'{region}: saved road {identity} missing or ambiguous in emitted master')
            triangles, errors = triangles_of(selected, walkable_only=False, encoding_bounds=True)
            require(len(triangles) > 0 and np.isfinite(triangles).all(),
                    f'{region}: saved road {identity} has no finite emitted triangles')
            projected = triangles[:, :, [0, 2]]
            road_groups[identity] = [(projected.min(axis=(0, 1)), projected.max(axis=(0, 1)), triangles, errors)]
        for obj in snapshot['objects']:
            if obj.get('collisionRole') != 'walk_surface':
                continue
            metadata = obj.get('metadata', {})
            keys = [key for key in ('authoredCrossing', 'authoredAccessAssembly') if key in metadata]
            if not keys:
                continue
            require(len(keys) == 1, f'{region}: ambiguous saved walk assembly metadata on {obj.get("nodeName")}')
            walk_name = metadata[keys[0]]['walkNode']
            wrapper_name = f'{region}_{obj["nodeName"]}_WorldPlacement'
            wrappers = by_name[wrapper_name]
            require(len(wrappers) == 1, f'{region}: saved walk wrapper {wrapper_name} missing or ambiguous in emitted master')
            roots = [index for index in subtree(wrappers[0]) if nodes[index].get('name') == walk_name]
            require(len(roots) == 1, f'{region}: saved walk root {walk_name} missing or ambiguous under {wrapper_name}')
            triangles = triangles_of(subtree(roots[0]))
            require(len(triangles) > 0, f'{region}: saved walk root {walk_name} has no walkable emitted triangles')
            projected = triangles[:, :, [0, 2]]
            groups.append((projected.min(axis=(0, 1)), projected.max(axis=(0, 1)), triangles))
    return groups, road_groups


def river_curve(river):
    import landscape as L
    points = L.river_points(river)[:, :2]
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    points = points[np.r_[True, seg > 1e-9]]
    seg = np.diff(points, axis=0)
    length = np.linalg.norm(seg, axis=1)
    return np.r_[0, np.cumsum(length)], points, seg / length[:, None]


def wet_width(river_water_at, centre, normal, reach, edges=False):
    """The wet run through (or nearest) the centre, square to the centreline, sampled every half metre (and its two
    edge offsets when ``edges``)."""
    offsets = np.arange(-reach, reach + 1e-9, .5)
    wet = np.asarray(river_water_at(centre[0] + normal[0] * offsets, centre[1] + normal[1] * offsets), bool)
    middle = len(offsets) // 2
    near = np.flatnonzero(wet)
    if not len(near):
        return (0., (0., 0.)) if edges else 0.
    seed = int(near[np.argmin(np.abs(near - middle))])
    lo = hi = seed
    while lo > 0 and wet[lo - 1]:
        lo -= 1
    while hi < len(wet) - 1 and wet[hi + 1]:
        hi += 1
    width = (hi - lo + 1) * .5
    return (width, (float(offsets[lo]), float(offsets[hi]))) if edges else width


def road_rule_findings(roads, sites, rivers, policy, ground_at, river_water_at, piers=(), designed_boxes=(), union_vertices=None,
                       authored_deck_triangles=(),
                       sea_near_at=None, sea_at=None, seam_near_at=None, saved_deck_groups=(), saved_road_groups=None):
    """Every breach of the road rules, with the measured totals; pure over its inputs (the audit's and tests' fixtures).

    ``sea_near_at(x, z)`` marks points over the sea or within a deck landing of it: a road there is on a sea span or its
    landing, which the river rules do not cover (reported in the totals, not refused). Piers carry their ``bed``
    height; one standing in the sea is reported, not held to the pier limit. ``seam_near_at(x, z)`` marks points within
    the crossing policy's seam distance of a territory seam, where no bridge is built: the local-shortest comparison
    skips sections there."""
    landing = float(policy.get('deck_landing_metres', 6.))
    sea_near = sea_near_at if sea_near_at is not None else (lambda x, z: np.zeros(np.shape(np.asarray(x, float)), bool))
    sea_at = sea_at if sea_at is not None else (lambda x, z: np.zeros(np.shape(np.asarray(x, float)), bool))
    spacing = float(policy.get('minimum_spacing_metres', 100.))
    spans = site_span_boxes(sites, landing)
    designed = [(np.asarray(low, float), np.asarray(high, float)) for low, high in designed_boxes]
    def in_designed(xz):
        result = np.zeros(len(xz), bool)
        for low, high in designed:
            result |= np.all((xz >= low) & (xz <= high), axis=1)
        return result
    rivers = {river['id']: river for river in rivers}
    curves = {key: river_curve(river) for key, river in rivers.items()}
    violations = []
    totals = {'roads': len(roads), 'stations': 0, 'overRiverWaterOutsideSitesMetres': 0., 'floatingOutsideDecksMetres': 0.,
              'sites': len(sites), 'crossingRuns': 0, 'piers': len(piers), 'tallestPierMetres': max((p['height'] for p in piers), default=0.),
              'encodedRoadEndpointsReconciled': 0, 'maximumRoadEndpointReconciliationMetres': 0.}
    for road in roads:
        stations = resample_stations(road['points'])
        if not len(stations):
            continue
        totals['stations'] += len(stations)
        xz = stations[:, [0, 2]]
        if saved_road_groups is not None and road['id'] in saved_road_groups:
            height, reconciled = saved_road_station_heights(stations, saved_road_groups[road['id']])
            require(np.isfinite(height).all(), f"{road['id']}: emitted saved road does not cover every rule station")
            totals['encodedRoadEndpointsReconciled'] += len(reconciled)
            totals['maximumRoadEndpointReconciliationMetres'] = max(totals['maximumRoadEndpointReconciliationMetres'],
                max((entry['distanceMetres'] for entry in reconciled), default=0.))
            # Source curve Y controls terrain shaping, not the rendered ribbon.
            # Keep the same stations/rules, measuring the actual highest road
            # triangle where consistent chunk boundaries overlap. A raised
            # emitted road still fails the unchanged clearance limit.
            stations[:, 1] = height
        deck_height = authored_deck_height(xz, authored_deck_triangles)
        if saved_deck_groups:
            deck_height = np.maximum(deck_height, saved_deck_height(xz, saved_deck_groups))
        # A saved walk deck supports the road only where its emitted triangle
        # covers the station and reaches at least the road surface.  A road
        # floating above a deck is still a road-rule failure.
        on_authored_deck = np.isfinite(deck_height) & (stations[:, 1] <= deck_height + 1e-9)
        on_span = inside_boxes(xz, spans) | on_authored_deck
        wet = np.asarray(river_water_at(xz[:, 0], xz[:, 1]), bool)
        stray = wet & ~on_span
        if stray.any():
            metres = float(stray.sum() * ROAD_RULE_STATION_METRES)
            totals['overRiverWaterOutsideSitesMetres'] += metres
            violations.append(f"{road['id']}: {metres:g} m over river water outside every bridge site, first at {xz[stray][0].round(1).tolist()}")
        lift = stations[:, 1] - np.asarray(ground_at(xz[:, 0], xz[:, 1]), float)
        at_sea = np.asarray(sea_near(xz[:, 0], xz[:, 1]), bool)
        totals['seaSpanStationsMetres'] = totals.get('seaSpanStationsMetres', 0.) + float((at_sea & (lift > ROAD_RULE_FLOAT_METRES)).sum() * ROAD_RULE_STATION_METRES)
        floating = (lift > ROAD_RULE_FLOAT_METRES) & ~on_span & ~in_designed(xz) & ~at_sea
        if floating.any():
            metres = float(floating.sum() * ROAD_RULE_STATION_METRES)
            totals['floatingOutsideDecksMetres'] += metres
            violations.append(f"{road['id']}: {metres:g} m of stations more than {ROAD_RULE_FLOAT_METRES:g} m above the ground outside site spans and designed decks, up to {float(lift[floating].max()):.1f} m at {xz[floating][int(np.argmax(lift[floating]))].round(1).tolist()}")
        # Every wet run is one crossing: square to the flow of its river.
        edges = np.flatnonzero(np.diff(np.r_[0, wet.astype(int), 0]))
        for a, b in zip(edges[::2], edges[1::2]):
            if b - a < 2:
                continue
            totals['crossingRuns'] += 1
            chord = xz[b - 1] - xz[a]
            if np.linalg.norm(chord) < 1e-6:
                continue
            middle = (xz[a] + xz[b - 1]) * .5
            best = None
            for key, (arc, points, unit) in curves.items():
                rel = middle - points[:-1]
                t = np.clip(np.sum(rel * (points[1:] - points[:-1]), axis=1) / np.maximum(np.sum((points[1:] - points[:-1]) ** 2, axis=1), 1e-9), 0, 1)
                d = np.linalg.norm(middle - (points[:-1] + t[:, None] * (points[1:] - points[:-1])), axis=1)
                k = int(np.argmin(d))
                if best is None or d[k] < best[0]:
                    best = (float(d[k]), unit[k], key)
            if best is None:
                continue
            angle = float(np.degrees(np.arccos(np.clip(abs(np.dot(chord / np.linalg.norm(chord), best[1])), 0, 1))))
            if angle < ROAD_RULE_SQUARE_DEGREES:
                violations.append(f"{road['id']}: crosses {best[2]} at {angle:.0f} degrees to the flow at {middle.round(1).tolist()}")
    by_river = defaultdict(list)
    for site in sites:
        by_river[site['river']].append(site)
        if site['river'] not in curves:
            violations.append(f"site {site.get('id')}: river {site['river']!r} is not a plan river")
            continue
        arc, points, unit = curves[site['river']]
        river = rivers[site['river']]
        left, right = np.asarray(site['wetEdges'][0], float), np.asarray(site['wetEdges'][1], float)
        span = right - left
        s0 = float(site['arcMetres'])
        near = (arc[:-1] >= s0 - 6) & (arc[:-1] <= s0 + 6)
        flow = unit[near].sum(axis=0) if near.any() else unit[int(np.argmin(np.abs(arc[:-1] - s0)))]
        flow = flow / max(float(np.linalg.norm(flow)), 1e-9)
        square = float(np.degrees(np.arccos(np.clip(abs(np.dot(span / max(float(np.linalg.norm(span)), 1e-9), flow)), 0, 1))))
        if square < ROAD_RULE_SQUARE_DEGREES:
            violations.append(f"site {site.get('id')} on {site['river']}: span stands {square:.0f} degrees to the flow")
        reach = float(river['width']) + 30.
        widths = []
        for s in np.arange(max(0., s0 - ROAD_RULE_WINDOW_METRES), min(arc[-1], s0 + ROAD_RULE_WINDOW_METRES) + 1e-9, 2.):
            k = int(np.clip(np.searchsorted(arc, s, side='right') - 1, 0, len(unit) - 1))
            centre = points[k] + unit[k] * (s - arc[k])
            normal = np.array([-unit[k][1], unit[k][0]])
            width, edges = wet_width(river_water_at, centre, normal, reach, edges=True)
            if width <= 0:
                continue
            # Only a crossing a bridge could land: dry ground above the sea a landing beyond each wet edge, and no
            # sea in the run (a river mouth widens into the sea, which is no narrow reach).
            if sea_near is not None:
                ends = np.array([centre + normal * (edges[0] - landing), centre + normal * (edges[1] + landing)])
                run = centre + normal * np.linspace(edges[0], edges[1], 9)[:, None]
                if np.asarray(river_water_at(ends[:, 0], ends[:, 1]), bool).any() or np.asarray(sea_at(ends[:, 0], ends[:, 1]), bool).any()                         or np.asarray(sea_at(run[:, 0], run[:, 1]), bool).any():
                    continue
                if seam_near_at is not None and (np.asarray(seam_near_at(ends[:, 0], ends[:, 1]), bool).any()
                                                 or np.asarray(seam_near_at(run[:, 0], run[:, 1]), bool).any()):
                    continue
            widths.append(width)
        here = float(np.linalg.norm(span)) + .5
        if site.get('authored'):
            # The plan named this crossing and said why; the local-shortest and spacing rules judge the crossings the
            # model sites for itself.
            totals['authoredSites'] = totals.get('authoredSites', 0) + 1
            continue
        if widths and here > min(widths) + ROAD_RULE_SHORTEST_EXCESS_METRES:
            violations.append(f"site {site.get('id')} on {site['river']}: crossing {here:.1f} m against {min(widths):.1f} m within {ROAD_RULE_WINDOW_METRES:g} m")
    for river, group in by_river.items():
        arcs = sorted(float(site['arcMetres']) for site in group if not site.get('authored'))
        for a, b in zip(arcs, arcs[1:]):
            if b - a < spacing - 1e-6:
                violations.append(f"{river}: bridge sites {b - a:.0f} m apart along the river (at least {spacing:g})")
    for pier in piers:
        if 'x' in pier and bool(np.asarray(sea_near(np.array([pier['x']]), np.array([pier['z']])), bool).reshape(-1)[0]) and not inside_boxes(np.array([[pier['x'], pier['z']]]), spans)[0]:
            totals['seaPiers'] = totals.get('seaPiers', 0) + 1
            totals['tallestSeaPierMetres'] = max(totals.get('tallestSeaPierMetres', 0.), float(pier['height']))
            continue
        if pier['height'] > ROAD_RULE_PIER_METRES:
            violations.append(f"{pier['name']}: pier {pier['height']:.1f} m tall (at most {ROAD_RULE_PIER_METRES:g})")
    if union_vertices is not None and len(union_vertices):
        vertices = np.asarray(union_vertices, float)
        xz = vertices[:, [0, 2]]
        lift = vertices[:, 1] - np.asarray(ground_at(xz[:, 0], xz[:, 1]), float)
        dry = ~np.asarray(river_water_at(xz[:, 0], xz[:, 1]), bool)
        at_sea = np.asarray(sea_near(xz[:, 0], xz[:, 1]), bool)
        totals['seaSpanFloorVerticesOver1.5m'] = int((at_sea & dry & (lift > ROAD_RULE_FLOAT_METRES)).sum())
        floating = dry & (lift > ROAD_RULE_FLOAT_METRES) & ~inside_boxes(xz, spans) & ~at_sea
        totals['floatingBridgeVertices'] = int(floating.sum())
        if floating.any():
            violations.append(f"{int(floating.sum())} bridge floor vertices stand more than {ROAD_RULE_FLOAT_METRES:g} m over dry ground outside site spans, up to {float(lift[floating].max()):.1f} m at {xz[floating][int(np.argmax(lift[floating]))].round(1).tolist()}")
    totals['violations'] = len(violations)
    return {'totals': totals, 'violations': violations}


def audit_road_rules(generated, plan, surface, inputs, composition):
    """The road rules on the emitted terrain, the composed roads (roads.json) and the emitted bridge structures."""
    import landscape as L
    record = inputs.json(generated / 'roads.json')
    heights = surface.attributes[:, 1].reshape(surface.nz, surface.nx)
    x0, z0 = surface.bounds[:2]
    def ground_at(x, z):
        return triangle_sample(heights, x, z, x0, z0, surface.cell)
    # One water survey of the emitted terrain on its own lattice: river water (with its lakes) and the sea.
    gx, gz = np.meshgrid(x0 + np.arange(surface.nx) * surface.cell, z0 + np.arange(surface.nz) * surface.cell)
    fields = L.water_fields(gx, gz, height=heights, plan=plan)
    river_depth = np.where(np.asarray(fields['river_mask'], bool), np.asarray(fields['depth'], float), 0.)
    def lattice(grid, x, z):
        x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
        iz = np.clip(np.rint((z - z0) / surface.cell).astype(int), 0, grid.shape[0] - 1)
        ix = np.clip(np.rint((x - x0) / surface.cell).astype(int), 0, grid.shape[1] - 1)
        return grid[iz, ix]
    def river_water_at(x, z):
        return triangle_sample(river_depth, x, z, x0, z0, surface.cell) > .02
    doc, body = GR.load(generated / 'bridges.glb')
    inputs.digest(generated / 'bridges.glb')
    piers, union, boxes, authored_decks = [], [], [], []
    designed = plan.get('designed_decks') or []
    def is_designed(name):
        return any(entry['name'] == name or (entry['name'].endswith('*') and name.startswith(entry['name'][:-1])) for entry in designed)
    for index, node in enumerate(doc['nodes']):
        name = node.get('name', '')
        if 'mesh' not in node:
            continue
        if name.startswith('BridgeUnionPier_'):
            tri = GR.triangles(doc, body, [index]).reshape(-1, 3)
            piers.append({'name': name, 'height': float(tri[:, 1].max() - tri[:, 1].min()),
                          'x': float((tri[:, 0].min() + tri[:, 0].max()) * .5), 'z': float((tri[:, 2].min() + tri[:, 2].max()) * .5)})
        elif name.startswith('Walk_ContinentalBridgeUnion_'):
            union.append(GR.triangles(doc, body, [index]).reshape(-1, 3))
        elif name.startswith('Walk_AuthoredBridge_'):
            authored_decks.append(GR.triangles(doc, body, [index]).reshape(-1, 3, 3))
        elif name.startswith('Walk_') and is_designed(name):
            tri = GR.triangles(doc, body, [index]).reshape(-1, 3)
            boxes.append((tri[:, [0, 2]].min(axis=0) - 1., tri[:, [0, 2]].max(axis=0) + 1.))
    policy = L.crossing_policy(plan)
    # Sea spans (a channel between islands) and their landings are not river crossings: reported, not refused.
    from scipy.ndimage import distance_transform_edt
    sea = np.asarray(fields['sea_mask'], bool)
    sea_distance = distance_transform_edt(~sea) * surface.cell if sea.any() else np.full(heights.shape, np.inf)
    def sea_near_at(x, z):
        return lattice(sea_distance, x, z) <= float(policy['deck_landing_metres']) + surface.cell
    def sea_at(x, z):
        return lattice(sea_distance, x, z) <= 0.
    # Territory seams on the ownership raster (cells whose owner differs from a neighbour's), as river_crossings measures them.
    owner = surface.owner
    boundary = np.zeros(owner.shape, bool)
    boundary[:-1, :] |= owner[:-1, :] != owner[1:, :]; boundary[1:, :] |= owner[:-1, :] != owner[1:, :]
    boundary[:, :-1] |= owner[:, :-1] != owner[:, 1:]; boundary[:, 1:] |= owner[:, :-1] != owner[:, 1:]
    seam_distance = np.pad(distance_transform_edt(~boundary) * surface.cell, ((0, 1), (0, 1)), mode='edge') if boundary.any() else np.full(heights.shape, np.inf)
    def seam_near_at(x, z):
        return lattice(seam_distance, x, z) <= float(policy['seam_metres'])
    saved_decks, saved_roads = saved_walk_surfaces(surface.client, generated, composition, inputs, record['roads'])
    findings = road_rule_findings(record['roads'], record.get('crossingSites', []), plan.get('rivers', []), policy, ground_at, river_water_at,
                                  piers, boxes, np.concatenate(union) if union else None,
                                  np.concatenate(authored_decks) if authored_decks else (), sea_near_at, sea_at, seam_near_at, saved_decks, saved_roads)
    require(not findings['violations'], 'Road rules: ' + '; '.join(findings['violations'][:12]) + (f' (and {len(findings["violations"]) - 12} more)' if len(findings['violations']) > 12 else ''))
    return findings['totals']


def run(client, generated, report_path, server=None, require_collision=False, geometry_only=False):
    started = time.monotonic()
    inputs = Inputs()
    report = {'schema':1,'passed':False,'complete':False,'publicationVerified':False,'scope':'geometry-only' if geometry_only else 'full-publication','errors':[],'regions':{},'limitations':[
        ('This provisional audit excludes collision, route publication, camera obstruction, residency timing and moving actors.' if geometry_only else
         'This audit checks emitted static geometry and collision; camera obstruction, residency timing and moving actors require the live client.'),
        'Terrain, normals, UVs and biome colours are checked exhaustively; retained object loading bounds/dependencies are checked without comparing every object triangle to the master.']}
    try:
        report['auditSha256']=inputs.digest(Path(__file__))
        require(not geometry_only or server is None and not require_collision, 'Geometry-only cannot also request server/collision validation')
        base = client/'eloria-assets/maps/nymara-regions'
        continent=base/'_continent'
        plan = inputs.json(continent/'diagonal-plan.json')
        composition = inputs.json(generated/'composition.json')
        master_record = inputs.json(generated/'master-scene.json')
        exports = inputs.json(generated/'export.json')
        require(exports.get('compositionSha256')==inputs.digest(generated/'composition.json'),'Geometry differs from the current composition')
        report['shapingFreshness']=audit_shaping(client,continent,composition,inputs)
        require(set(exports.get('geometrySources',{}))==EXPORT_SOURCES,'Geometry export must certify every export source')
        require(exports.get('geometryDependencies')==geometry_dependencies(),'Geometry export dependencies changed after export')
        for name,expected in exports['geometrySources'].items():
            require(inputs.digest(continent/name)==expected,f'Geometry export source changed: {name}')
        report['geometrySourceFreshness']=exports['geometrySources']
        master_sha = inputs.digest(generated/'continent.glb')
        require(master_sha == master_record['sha256'] == exports['masterSha256'], 'Master scene provenance differs between exported artifacts')
        master_path=Path(exports['masterPath'])
        if not master_path.is_absolute():master_path=generated/master_path
        require(master_path.resolve()==(generated/'continent.glb').resolve(),'Export ledger references another master path')
        shared_sha=inputs.digest(generated/'shared-terrain.glb')
        frames,manifests,packages=exported_frames(client,exports,plan,master_sha,composition['planSha256'],inputs)
        require(set(master_record['regions'])==set(frames),'Master scene named territory set differs from its export')
        if not geometry_only:
            geography = inputs.json(base/'continent-geography.json')
            require(geography.get('geometryMode')=='continent-chunks-v1','The canonical continent-chunks-v1 publication is not ready')
            require(master_sha==geography['verification']['masterSha256'],'Master scene provenance differs from canonical geography')
            require(shared_sha==geography['verification']['sharedSurfaceSha256'],'Shared terrain source digest differs from canonical geography')
            require(set(geography['regions'])==set(frames),'Canonical named territory set differs from the export')
            require(geography['ownershipRasterMetres']==2,'Canonical ownership lattice differs from shared terrain')
            for region,frame in frames.items():
                for key in ('ownershipPolygon','translation','serverOrigin','serverCells'):
                    require(frame[key]==geography['regions'][region][key],f'{region}: published {key} differs from its exported named manifest')
        polygons = {r:v['ownershipPolygon'] for r,v in frames.items()}
        surface = Surface(plan['bounds'],polygons,inputs,client,2.)
        surface.translations = {r:np.asarray(v['translation'],float) for r,v in frames.items()}
        report['frameAuthority']='export ledger, named manifests and authored plan' if geometry_only else 'canonical publication matched to exported named manifests'
        report['publicationVerified']=False
        surface.read(generated/'shared-terrain.glb',surface.source_counts,source=True)
        surface.complete(surface.source_counts,'Shared source')
        require(np.isfinite(surface.attributes).all(), 'Shared source omits vertices from the global lattice')
        master_counts = np.zeros_like(surface.source_counts)
        surface.read(generated/'continent.glb',master_counts)
        surface.complete(master_counts,'Master')
        named_counts = np.zeros_like(surface.source_counts)
        chunk_counts = np.zeros_like(surface.source_counts)
        for region in surface.ids:
            package=packages[region];manifest=manifests[region]
            stats = surface.read(package/'world.glb',named_counts,region=region,manifest=manifest)
            chunks = manifest['streamingChunks']['chunks']
            require(len(chunks) == len({c['id'] for c in chunks}) == exports['regions'][region]['chunks'], f'{region}: chunk inventory is inconsistent')
            require(chunks, f'{region}: empty chunk inventory')
            for chunk in chunks:
                child_path = (package/chunk['manifest']).resolve()
                require(child_path.is_relative_to(package.resolve()), f'{region}: chunk manifest escapes territory')
                child = inputs.json(child_path)
                require('streamingChunks' not in child, f'{child_path}: recursive chunk stream')
                require(child['bounds'] == chunk['bounds'], f'{child_path}: parent/child loading bounds differ')
                require(child['coordinateTransform'] == manifest['coordinateTransform'], f'{child_path}: chunk moved into a different coordinate frame')
                require(child['continentGeography']==manifest['continentGeography'] and child['singleContinentSource']==manifest['singleContinentSource'],
                        f'{child_path}: chunk ownership/master provenance differs from its named territory')
                glb = child_path.parent/child['asset']['glb']
                require(glb.stat().st_size == chunk['glbBytes'], f'{glb}: byte estimate is stale')
                surface.read(glb,chunk_counts,region=region,bounds=chunk['bounds'],manifest=child)
            stats['chunks'] = len(chunks)
            if not geometry_only and (require_collision or server is not None or (package/'collision.bin').is_file()):
                stats['collision'] = audit_collision(surface,region,manifest,package,inputs,server)
            report['regions'][region] = stats
            print(f'{region}: actual terrain, {len(chunks)} chunks, dependencies and bounds verified',flush=True)
        surface.complete(named_counts,'Named territories')
        surface.complete(chunk_counts,'Streaming chunks')
        # The owner's road rules (R1): every composition since records its crossing sites and its roads.
        if 'riverCrossings' in composition:
            require((generated/'roads.json').is_file(),'Geometry export did not record the composed roads (roads.json)')
            report['roadRules']=audit_road_rules(generated,plan,surface,inputs,composition)
        if not geometry_only:
            publication = inputs.json(generated/'publication.json')
            report['frames'] = audit_frames(publication,manifests,surface.translations)
        if server is not None:
            served = inputs.json(server/'config/eloria/client_content_manifest.json')
            require(served['continentGeography']['masterSha256'] == master_sha, 'Server publishes a different continent master')
            client_graph = inputs.json(client/'godot-client/data/maps/exterior_connections.json')
            server_graph = inputs.json(server/'config/eloria/exterior_connections.json')
            require(client_graph == server_graph, 'Client/server adjacent-territory graphs differ')
        report.update(complete=not geometry_only,passed=True,sourceTerrainTriangles=len(surface.source_counts),
                      sourceTerrainVertices=len(surface.attributes),maximumSharedAttributeErrors=dict(surface.max_error),
                      masterSha256=master_sha,sharedSurfaceSha256=shared_sha,publicationVerified=not geometry_only)
    except (AuditError,KeyError,ValueError,TypeError,SyntaxError,OSError,struct.error) as error:
        report['errors'].append(str(error))
    report['unchangedDuringAudit'] = inputs.unchanged()
    if not report['unchangedDuringAudit']:
        report['errors'].append('Audited inputs changed during verification')
        report['passed'] = False
    report['elapsedSeconds'] = round(time.monotonic()-started,3)
    report['inputs'] = inputs.hashes
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',type=Path,default=CLIENT)
    parser.add_argument('--generated',type=Path,default=HERE/'generated')
    parser.add_argument('--server',type=Path)
    parser.add_argument('--output','--report',dest='report',type=Path,required=True)
    parser.add_argument('--require-collision',action='store_true')
    parser.add_argument('--geometry-only',action='store_true',help='Provisional exhaustive geometry check; excludes collision and published route contracts')
    args = parser.parse_args()
    report = run(args.client.resolve(),args.generated.resolve(),args.report.resolve(),args.server.resolve() if args.server else None,args.require_collision,args.geometry_only)
    print(json.dumps({k:report[k] for k in ('passed','complete','elapsedSeconds','errors')},indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
