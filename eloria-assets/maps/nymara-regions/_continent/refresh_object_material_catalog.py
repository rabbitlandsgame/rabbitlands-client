"""Apply saved AssetControl surface edits to already-published chunk GLBs.

This is the appearance-only companion to refresh_biome_catalog. It resolves
every saved mesh target through the exact published child scene hierarchy;
geometry, collision, and publication records are never rewritten. A future
normal export emits current materials in its GLB and an explicit child
objectMaterialOverrides field, which takes precedence over this fallback.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

import authoring as AUTHORING
from biome_blend import _resource_path


ROOT = AUTHORING.CLIENT / 'eloria-assets/maps/nymara-regions'
CATALOG = AUTHORING.CLIENT / 'godot-client/assets/world/biome_blend/object-materials.json'
SCHEMA = 'eloria-object-material-overrides-v1'


def _glb_document(path: Path) -> dict:
    with path.open('rb') as stream:
        header = stream.read(20)
        if len(header) != 20 or header[:4] != b'glTF':
            raise AUTHORING.AuthoringError(f'{path}: invalid GLB header')
        length = struct.unpack_from('<I', header, 12)[0]
        if header[16:20] != b'JSON':
            raise AUTHORING.AuthoringError(f'{path}: missing GLB JSON chunk')
        return json.loads(stream.read(length))


def _glb_nodes(path: Path) -> tuple[dict, dict[int, int]]:
    doc = _glb_document(path)
    nodes = doc['nodes']
    parents = {child: parent for parent, node in enumerate(nodes)
               for child in node.get('children', [])}
    return doc, parents


def _saved_wrappers(region: str, obj: dict, snapshot: AUTHORING.Snapshot,
                    cache: dict[Path, dict]) -> set[str]:
    """Derive the exact primary/companion export wrappers from pinned roots."""
    source = AUTHORING.baked_asset_path(obj, snapshot)
    if source not in cache:
        cache[source] = _glb_document(source)
    doc = cache[source]
    source_node = obj['bakedSource']['sourceNode']
    if source_node == '.':
        roots = doc['scenes'][doc.get('scene', 0)]['nodes']
    else:
        roots = [index for index, node in enumerate(doc['nodes'])
                 if node.get('name') == source_node]
    if not roots or (source_node != '.' and len(roots) != 1):
        raise AUTHORING.AuthoringError(f"{region}/{obj['id']}: source roots changed")
    names = [obj['nodeName']]
    for ordinal, index in enumerate(roots[1:], 1):
        original = doc['nodes'][index].get('name') or f'root-{ordinal}'
        names.append(f"{obj['nodeName']}__companion_{ordinal}_{original}")
    return {f'{region}_{name}_WorldPlacement' for name in names}


def _material(surface: dict, where: str) -> dict:
    preset = surface['preset']
    pbr = surface.get('pbr') if preset == 'Custom' else surface.get('pbrOverrides')
    if not isinstance(pbr, dict):
        raise AUTHORING.AuthoringError(f'{where}: saved material PBR record is missing')
    result = {'preset': preset, 'textureSha256': {},
              'albedoColor': list(pbr['albedoColor']), 'roughness': float(pbr['roughness']),
              'metallic': float(pbr['metallic']), 'normalStrength': float(pbr['normalScale']),
              'uvScale': list(pbr['uvScale'][:2]), 'uvOffset': list(pbr['uvOffset'][:2]),
              'rotationDegrees': float(surface.get('rotationDegrees', 0.0))}
    for key in ('albedoTexture', 'normalTexture', 'ormTexture'):
        value, digest = _resource_path(pbr.get(key), f'{where}.{key}')
        result[key] = value
        if digest is not None:
            result['textureSha256'][key] = digest
    if not result['albedoTexture']:
        raise AUTHORING.AuthoringError(f'{where}: saved object material lacks albedo')
    return result


def _matches_saved_target(chain: list[str], leaf: str, wrappers: set[str],
                          surface_index: int, primitive_count: int,
                          same_name_mesh_count: int) -> bool:
    """Match one exact composed mesh without aliasing a sibling wrapper."""
    return (chain[0] == leaf and any(ancestor in wrappers for ancestor in chain[1:])
            and 0 <= surface_index < primitive_count and same_name_mesh_count == 1)


def _published_nodes(regions: set[str]) -> tuple[dict[str, list[tuple[str, int, list[str], int, int]]], dict[str, str]]:
    result: dict[str, list[tuple[str, int, list[str], int, int]]] = defaultdict(list)
    glb_hashes = {}
    for region in sorted(regions):
        region_root = (AUTHORING.CLIENT / 'eloria-assets/maps/four-gates') if region == 'four_gates' else ROOT / region
        manifests = sorted((region_root / 'chunks').glob('*/world.json'))
        if not manifests:
            raise AUTHORING.AuthoringError(f'{region}: no published child chunk manifests')
        for manifest in manifests:
            data = json.loads(manifest.read_text(encoding='utf-8'))
            if 'objectMaterialOverrides' in data:
                raise AUTHORING.AuthoringError(
                    f'{manifest}: child objectMaterialOverrides is authoritative; use normal continent export for this material edit')
            asset_id = data['asset']['id']
            if not asset_id.startswith(region + '__chunk_'):
                raise AUTHORING.AuthoringError(f'{manifest}: wrong child asset identity')
            glb = manifest.parent / data['asset']['glb']
            doc, parents = _glb_nodes(glb)
            nodes = doc['nodes']
            glb_hashes[asset_id] = hashlib.sha256(glb.read_bytes()).hexdigest()
            mesh_name_counts = Counter(node.get('name') for node in nodes
                                       if 'mesh' in node and node.get('name'))
            for index, node in enumerate(nodes):
                if 'mesh' not in node or not node.get('name'):
                    continue
                ancestors = []
                current = index
                while current in parents:
                    current = parents[current]
                    ancestors.append(nodes[current].get('name', ''))
                primitives = doc['meshes'][node['mesh']]['primitives']
                result[region].append((asset_id, index, [node['name'], *ancestors],
                                       len(primitives), mesh_name_counts[node['name']]))
    return result, glb_hashes


def refresh() -> dict:
    snapshots = AUTHORING.load_snapshots()
    regions = {snapshot.document['regionId'] for snapshot in snapshots}
    if len(regions) != 12:
        raise AUTHORING.AuthoringError('object colour refresh requires all 12 current saved scenes')
    nodes, glb_hashes = _published_nodes(regions)
    assets: dict[str, list[dict]] = defaultdict(list)
    targets = set()
    saved_slots = 0
    source_documents: dict[Path, dict] = {}
    for snapshot in snapshots:
        region = snapshot.document['regionId']
        for obj in snapshot.document['objects']:
            if not obj.get('materialOverrides'):
                continue
            wrappers = _saved_wrappers(region, obj, snapshot, source_documents)
            for override in obj.get('materialOverrides', []):
                saved_slots += 1
                path = override['meshNodePath'].split('/')
                leaf = path[-1]
                # The saved root can be renamed by an AssetControl; the
                # material-bearing leaf and exact owner wrapper must remain.
                matches = [(asset_id, index) for asset_id, index, chain, primitives, name_count in nodes[region]
                           if _matches_saved_target(chain, leaf, wrappers,
                                                    override['surfaceIndex'], primitives, name_count)]
                # A published source object can be present in more than one
                # streamed child chunk when its bounds cross a chunk border.
                # Its exact mesh must resolve once *per child*, never twice.
                if not matches or len({asset_id for asset_id, _ in matches}) != len(matches):
                    raise AUTHORING.AuthoringError(
                        f"{region}/{obj['id']}:{override['meshNodePath']} resolves to {len(matches)} published mesh nodes")
                material = _material(override['surface'], f"{region}/{obj['id']}/{leaf}")
                for asset_id, _ in matches:
                    key = (asset_id, leaf, override['surfaceIndex'])
                    if key in targets:
                        raise AUTHORING.AuthoringError(f'duplicate saved object material target {key}')
                    targets.add(key)
                    assets[asset_id].append({
                        'nodeName': leaf, 'surfaceIndex': override['surfaceIndex'],
                        'material': material,
                    })
    for entries in assets.values():
        entries.sort(key=lambda row: (row['nodeName'], row['surfaceIndex']))
    result = {
        'schema': SCHEMA,
        'sources': {'snapshots': {s.document['regionId']: s.digest for s in snapshots},
                    'publishedChunkGlbSha256': glb_hashes},
        'assets': {asset_id: assets[asset_id] for asset_id in sorted(assets)},
    }
    encoded = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + '\n'
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    if not CATALOG.is_file() or CATALOG.read_text(encoding='utf-8') != encoded:
        CATALOG.write_text(encoded, encoding='utf-8', newline='\n')
    return {'regions': len(snapshots), 'assets': len(assets), 'savedSlots': saved_slots,
            'runtimeTargets': len(targets),
            'catalogSha256': hashlib.sha256(encoded.encode('utf-8')).hexdigest()}


if __name__ == '__main__':
    print(json.dumps(refresh(), sort_keys=True), flush=True)
