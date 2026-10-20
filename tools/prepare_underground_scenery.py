"""Package reviewed Meshy scenery for underground use without rebuilding models.

Reuses source geometry and UVs. Selected lantern faces remove the unused post;
stone material variants use generated atlases. An outer transform sets gameplay
size and aligns the physical passage or base with the floor.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eloria-assets/tools'))
from video_motion.asset import accessor, read_glb, write_glb  # noqa: E402
from video_motion.packing import append_array  # noqa: E402
from imported_world_objects import measure_glb  # noqa: E402

SELECTION = {
    'crystal_arch': ('amethyst_barrens', 'crystal-rock-arch-1', 'height', 5.2),
    'crystal_cluster': ('amethyst_barrens', 'crystal-growth-1', 'height', 1.7),
    'mine_rail': ('amethyst_barrens', 'mine-rail-straight-1', 'length', 3.0),
    'wall_lantern': ('amethyst_barrens', 'lantern-post-1', 'height', .8),
    'mossy_rock': ('grey_moors', 'mossy-boulder-2', 'length', 3.0),
    'cave_mouth': ('whitehorn_range', 'whitehorn-ice-cave-mouth-v001', 'height', 5.2),
    'resource_rock_1': ('amethyst_barrens','veined-boulder-1','height',.8),
    'resource_rock_2': ('amethyst_barrens','veined-boulder-2','height',.8),
    'resource_rock_3': ('amethyst_barrens','veined-boulder-3','height',.8),
    # The Cenote Deeps (owner 2026-10-20): Landfall A3's own jungle kit, lf-biomes.
    'mossy_crag_1': ('lf-biomes','mossy-crag-1','height',6.0),
    'mossy_crag_2': ('lf-biomes','mossy-crag-2','height',7.0),
    'mossy_boulder_1': ('lf-biomes','mossy-boulder-1','height',2.4),
    'mossy_boulder_2': ('lf-biomes','mossy-boulder-2','height',3.2),
    'mossy_boulder_3': ('lf-biomes','mossy-boulder-3','length',3.0),
    'waterfall_rocks': ('lf-biomes','waterfall-rocks-1','length',11.0),
    'jade_lantern_shrine': ('lf-biomes','jade-shrine-1','height',2.0),
    'jade_cairn': ('lf-biomes','jade-shrine-2','height',2.2),
    'jade_lantern_pole': ('lf-biomes','jade-lantern-pole-1','height',2.8),
    'incense_brazier': ('lf-biomes','serpent-incense-brazier-1','height',1.6),
    'serpent_arch': ('lf-biomes','serpent-ruin-8','length',6.6),
    'serpent_altar': ('lf-biomes','serpent-ruin-7','length',2.6),
    'serpent_pillar': ('lf-biomes','serpent-ruin-3','height',3.2),
    'serpent_obelisk': ('lf-biomes','serpent-ruin-6','height',3.0),
    'serpent_frieze': ('lf-biomes','serpent-ruin-4','length',3.5),
    'lotus_pads': ('lf-biomes','lotus-flower-pads-1','length',3.0),
    'lagoon_reed': ('lf-biomes','lagoon-reed-1','height',1.4),
    'tree_fern': ('lf-biomes','tree-fern-1','height',4.5),
    'jungle_undergrowth': ('lf-biomes','jungle-undergrowth-1','height',2.2),
    'jungle_undergrowth_2': ('lf-biomes','jungle-undergrowth-2','height',1.8),
    'split_geode': ('lf-biomes','split-geode-1','height',2.0),
    'toadstool_ring': ('lf-biomes','toadstool-ring-1','length',2.5),
    'mossy_log': ('lf-biomes','mossy-log-1','length',5.0),
}
KITS = {'lf-biomes': 'godot-client/world_authoring/continent-v2/kits/lf-biomes/prototypes'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, document):
    # LF on every platform: a Windows text-mode write turns a one-entry change
    # into a whole-file diff of the shared registry.
    path.write_text(json.dumps(document, indent=2)+'\n', encoding='utf-8', newline='\n')


def matrix(node):
    if 'matrix' in node:
        return np.array(node['matrix']).reshape(4, 4).T
    from scipy.spatial.transform import Rotation
    result = np.eye(4)
    result[:3, :3] = Rotation.from_quat(node.get('rotation', [0, 0, 0, 1])).as_matrix()
    result[:3, :3] *= np.array(node.get('scale', [1, 1, 1]))[None, :]
    result[:3, 3] = node.get('translation', [0, 0, 0])
    return result


def bounds(document, blob):
    points = []

    def visit(index, parent):
        node = document['nodes'][index]
        world = parent @ matrix(node)
        if 'mesh' in node:
            for primitive in document['meshes'][node['mesh']]['primitives']:
                vertices = accessor(document, blob, primitive['attributes']['POSITION'])
                if 'indices' in primitive:
                    vertices = vertices[accessor(document, blob, primitive['indices']).astype(int).ravel()]
                points.append(vertices @ world[:3, :3].T + world[:3, 3])
        for child in node.get('children', []):
            visit(child, world)

    for index in document['scenes'][document.get('scene', 0)]['nodes']:
        visit(index, np.eye(4))
    vertices = np.concatenate(points)
    return vertices.min(0), vertices.max(0)


def package(name, spec, output):
    region, slug, measure, size = spec
    source = ROOT / KITS.get(region, f'godot-client/world_authoring/regions/{region}/assets/prototypes') / f'kit-{slug}.glb'
    if name == 'cave_mouth':
        source = ROOT / f'eloria-assets/maps/nymara-regions/{region}/assets/{slug}/model-reference.glb'
    source_bytes = source.read_bytes()
    document, original_blob = read_glb(source)
    preserved_cave = name == 'cave_mouth' and sha(source_bytes) == '8f7861af0f32d5ff561f2c6112c45136c9f917682e2a226739326a5e12d6a1e6'
    if not preserved_cave and 'prepare_meshy_kit' not in document['asset'].get('generator', ''):
        raise ValueError(f'{source.name}: selection must be an imported Meshy model')
    blob = bytearray(original_blob)
    if preserved_cave:
        # The game has a quantization extension, but the editor's standalone
        # importer does not. Expand the same normalized attribute values so
        # both paths can load this reused source without a custom plugin.
        expanded = {}
        for mesh in document['meshes']:
            for primitive in mesh['primitives']:
                for key,index in list(primitive['attributes'].items()):
                    spec = document['accessors'][index]
                    if spec['componentType'] == 5126 or key.startswith(('JOINTS_','WEIGHTS_')): continue
                    if index not in expanded:
                        values = accessor(document,blob,index)
                        new_index = append_array(document,blob,values,spec['type'])
                        assert np.allclose(accessor(document,blob,new_index),values,atol=1e-7)
                        expanded[index] = new_index
                    primitive['attributes'][key] = expanded[index]
        for key in ('extensionsRequired','extensionsUsed'):
            document[key] = [v for v in document.get(key,[]) if v != 'KHR_mesh_quantization']
    if name == 'wall_lantern':
        # Reuse the imported lantern head and its bracket. The tall freestanding
        # post cannot sit outside a cutaway wall without appearing to float.
        for mesh in document['meshes']:
            for primitive in mesh['primitives']:
                positions = accessor(document, blob, primitive['attributes']['POSITION'])
                indices = accessor(document, blob, primitive['indices']).astype(int).reshape(-1,3)
                threshold = positions[:,1].min()+np.ptp(positions[:,1])*.63
                kept = indices[(positions[indices,1] >= threshold).all(axis=1)].astype('<u4').ravel()
                if not len(kept): raise ValueError('Lantern head selection is empty')
                blob.extend(b'\0'*(-len(blob)%4))
                document['bufferViews'].append({'buffer':0,'byteOffset':len(blob),'byteLength':kept.nbytes,'target':34963})
                blob.extend(kept.tobytes())
                document['accessors'].append({'bufferView':len(document['bufferViews'])-1,'componentType':5125,
                                             'count':len(kept),'type':'SCALAR','min':[int(kept.min())],'max':[int(kept.max())]})
                primitive['indices'] = len(document['accessors'])-1
    before = bounds(document, blob)
    extent = before[1] - before[0]
    factor = size / (extent[1] if measure == 'height' else max(extent[0], extent[2]))
    images = []
    changed_material = name == 'cave_mouth'
    base_image = None
    if changed_material:
        material = document['materials'][0]
        pbr = material['pbrMetallicRoughness']
        base_image = document['textures'][pbr['baseColorTexture']['index']]['source']
        pbr.pop('metallicRoughnessTexture', None)
        pbr['roughnessFactor'] = 1
        if 'normalTexture' in material: material['normalTexture']['scale'] = .35
    for image_index, image in enumerate(document.get('images', [])):
        if 'uri' not in image:
            continue
        image_path = (source.parent / image.pop('uri')).resolve()
        if image_index == base_image:
            image_path = ROOT/'eloria-assets/source/world_objects/underground/cave-earth-basecolor-v001.png'
            image['mimeType'] = 'image/png'
        if not image_path.is_relative_to(ROOT):
            raise ValueError('Image escaped the client checkout')
        payload = image_path.read_bytes()
        blob.extend(b'\0' * (-len(blob) % 4))
        image['bufferView'] = len(document['bufferViews'])
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(payload)})
        blob.extend(payload)
        images.append({'sha256': sha(payload), 'bytes': len(payload)})
    scene = document['scenes'][document.get('scene', 0)]
    wrapper = len(document['nodes'])
    centre = np.array([(before[0][0]+before[1][0])/2, before[0][1], (before[0][2]+before[1][2])/2])
    if name == 'cave_mouth':
        # Align the original passage floor, rather than the lowest stones,
        # so its walk-in surface meets the served outdoor ground.
        centre[1] = -.23254863242764562
    document['nodes'].append({'name': f'RL_{name}', 'children': scene['nodes'],
                              'scale': [factor]*3, 'translation': (-centre*factor).tolist()})
    scene['nodes'] = [wrapper]
    document['buffers'][0]['byteLength'] = len(blob)
    document['asset']['extras'] = {'sourceModelSha256': sha(source_bytes),
                                  'processing': 'Reused geometry and UVs; embedded textures, optional stone atlas or lantern-face selection; outer size/floor transform'}
    destination = output / f'{name}.glb'
    write_glb(destination, document, blob)
    saved_document, saved_blob = read_glb(destination)
    if saved_blob[:len(original_blob)] != original_blob:
        raise ValueError('Source geometry or material data changed')
    if any('uri' in i for i in saved_document.get('images', [])):
        raise ValueError('Runtime model still needs an external image')
    low, high = bounds(saved_document, saved_blob)
    return {'id': name, 'source': source.relative_to(ROOT).as_posix(), 'sourceSha256': sha(source_bytes),
            'output': destination.relative_to(ROOT).as_posix(), 'sha256': sha(destination.read_bytes()),
            'bounds': [low.tolist(), high.tolist()], 'images': images,
            'sourceBinaryPrefixPreserved': True, 'newModelGeneration': False,
            'materialVariant': 'Generated matte stone atlas; reduced normal strength' if changed_material else None,
            'geometrySelection': 'Original upper lantern/bracket faces only' if name == 'wall_lantern' else 'Complete source model'}


def main():
    output = ROOT / 'godot-client/assets/world/underground'
    output.mkdir(parents=True, exist_ok=True)
    records = [package(name, spec, output) for name, spec in SELECTION.items()]
    report = ROOT / 'eloria-assets/source/world_objects/underground/reused-scenery.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    write_json(report, {'schema': 'rabbitlands-reused-underground-scenery-v1', 'assets': records})
    plan_path = ROOT / 'eloria-assets/maps/continent-v2/_continent_v2/content/underground.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    placements = []
    def place(asset, x, y, yaw=0, height=0):
        placements.append({'asset': asset, 'position': [x, height, 240-y], 'yaw': yaw})
    # The cenote's dressing is the builder's: the same list decides what the walk grid blocks.
    sys.path.insert(0, str(plan_path.parents[1]))
    from build_underground import dressing
    for section in plan['sections']:
        if section['style'] == 'cenote':
            for item in dressing(section):
                place(item['asset'], item['x'], item['y'], item['yaw'], item['height'])
                extra = {'scale': item['scale']} if item['scale'] != 1 else {}
                if 'palette' in item:
                    extra['palette'] = item['palette']
                placements[-1].update(extra)
            continue
        for x, y, rx, ry in section['rooms']:
            place('wall_lantern', x-rx+.2, y, height=2.2)
        if section['style'] == 'mine':
            # Track ends stay in the broad main chamber, away from the
            # collision kit's timber supports and every resource approach.
            x, y, rx, ry = section['rooms'][1]
            for distance in (-4.5, -1.5, 1.5, 4.5):
                place('mine_rail', x, y+distance, 90)
            place('mossy_rock', x+rx+1.2, y)
        elif section['style'] == 'crystal':
            for x, y, rx, ry in section['rooms'][1:]:
                for index in range(5):
                    angle = index*1.3
                    # Match the existing blocked mineral patches exactly.
                    place('crystal_cluster', x+rx*.82*np.cos(angle), y+ry*.82*np.sin(angle), index*73)
        elif section['style'] == 'barrow':
            # Room 1 is the barrow's hub: a passage leaves each of its four
            # sides, and the east one is room 3's only way in. Wedge the rock
            # diagonally into the north-east corner, where the wall margin of
            # the served collision is already blocked under all of it.
            x, y, rx, ry = section['rooms'][1]
            place('mossy_rock', x+rx+.3, y-ry-.7, 45)
    config = {'schemaVersion': 1, 'map': plan['map']['id'], 'sourcePlanSha256': sha(plan_path.read_bytes()),
              'assets': {record['id']: 'res://'+record['output'].split('godot-client/', 1)[1] for record in records},
              'placements': placements}
    write_json(ROOT/'godot-client/data/world/underground-scenery.json', config)
    catalog_path = ROOT/'godot-client/data/world/objects.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    harvest = catalog['harvestables']
    minerals = {
        'Coal':('1','25282b','171a1d'), 'Iron Ore':('2','777979','8d5d3c'),
        'Copper':('3','777471','b87333'), 'Sulfur':('1','777468','d8b94c'),
        'Slate':('2','5d656d','77818a'), 'Geode':('3','666572','b093d0'),
        'Crystal':('cluster','77748a','9b74d5'),
    }
    for label,(shape,stone,vein) in minerals.items():
        identity = 'rl_'+label.lower().replace(' ','_')+'_v1'
        asset = 'crystal_cluster' if shape == 'cluster' else 'resource_rock_'+shape
        # Reused scenery, not a row of imported_world_objects: several labels
        # share one packaged GLB and draw it in their own resource palette.
        # The retired procedural model it replaces keeps the label's tier.
        replaced = next(model for model, entry in harvest['models'].items()
                        if entry['label'] == label and entry.get('retired'))
        harvest['models'][identity] = {'label':label,'kind':'mineral','tier':harvest['models'][replaced]['tier'],
            'reusedScenery':True,'scene':config['assets'][asset],
            **measure_glb(ROOT/'godot-client'/config['assets'][asset].removeprefix('res://')),
            'resourcePalette':{'stone':'#'+stone,'mineral':'#'+vein},
            'source':'eloria-assets/source/world_objects/underground/reused-scenery.json','replaces':replaced}
        harvest['resources'][label] = identity
    write_json(catalog_path, catalog)
    for record in records:
        print(record['id'], record['bounds'])


if __name__ == '__main__':
    main()
