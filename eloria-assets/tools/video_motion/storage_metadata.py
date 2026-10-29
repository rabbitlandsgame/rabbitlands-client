"""Rebind representation metadata while freezing independent observations."""
import copy

import numpy as np


def _parts(document):
    parts, offset = [], 0
    for node_index, node in enumerate(document['nodes']):
        if 'mesh' not in node: continue
        for primitive_index, primitive in enumerate(document['meshes'][node['mesh']]['primitives']):
            count = document['accessors'][primitive['attributes']['POSITION']]['count']
            parts.append({'node': node_index, 'mesh': node['mesh'], 'primitive': primitive_index,
                          'begin': offset, 'end': offset + count})
            offset += count
    return parts, offset


def vertex_permutation(document, partition):
    _, count = _parts(document)
    if not partition or 'all_candidate_original_vertex_ids' not in partition:
        return np.arange(count)
    ids = np.asarray(partition['all_candidate_original_vertex_ids'], dtype=int)
    if len(ids) != count or not np.array_equal(np.sort(ids), np.arange(count)):
        raise ValueError('Partition must preserve every source vertex exactly once')
    return np.argsort(ids)


def remap_vertex_fields(record, permutation):
    """Remap named physical index sets, never bone IDs or measured coordinates."""
    result = copy.deepcopy(record)
    def indices(value):
        if isinstance(value, dict): return {key: indices(v) for key, v in value.items()}
        if isinstance(value, list) and all(type(v) is int for v in value):
            if any(v < 0 or v >= len(permutation) for v in value): raise ValueError('Physical vertex set exceeds source')
            return permutation[value].tolist()
        return value
    def visit(value):
        if isinstance(value, dict):
            for key in list(value):
                if key == 'surface_vertex_ids' or key.endswith('_vertex_ids') or key.endswith('_vertices'):
                    value[key] = indices(value[key])
                elif isinstance(value[key], (dict, list)): visit(value[key])
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (dict, list)): visit(child)
    visit(result)
    return result


def remap_witness(witness, source_document, prune_report, partition, source_sha256,
                  candidate_sha256, profile=None):
    if witness['sha256'] != source_sha256:
        raise ValueError('Independent witness does not match source SHA256')
    permutation = vertex_permutation(source_document, partition)
    result = remap_vertex_fields(witness, permutation)
    result['sha256'] = candidate_sha256
    result.setdefault('reference_sha256', source_sha256)
    mapping = {row['mesh']: row for row in prune_report.get('meshes', [])}
    parts, _ = _parts(source_document)
    def visit(value):
        if isinstance(value, dict):
            for node, weights in value.get('morph_weights', {}).items():
                mesh = source_document['nodes'][int(node)].get('mesh')
                row = mapping.get(mesh)
                if row is not None and row['removed_target_indices']:
                    if len(weights) != row['targets_before']: raise ValueError('Unexpected original weight-vector length')
                    value['morph_weights'][node] = [weights[i] for i in row['retained_target_indices']]
            for key, child in value.items():
                if key not in ('morph_weights', 'bones', 'surface', 'surface_normals') and isinstance(child, (dict, list)): visit(child)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (dict, list)): visit(child)
    visit(result.get('clips', {}))
    selected = set()
    owner_names = {}
    if profile and partition and 'new_node' in partition:
        part = next(p for p in parts if p['node'] == profile['source_node'] and p['primitive'] == profile.get('primitive', 0))
        selected = {int(i) + part['begin'] for i in profile['vertex_ids']}
        if profile['mode'] == 'rigid':
            skin = source_document['skins'][source_document['nodes'][part['node']]['skin']]
            owners = profile.get('owner_joints', [profile.get('owner_joint')] * len(profile['vertex_ids']))
            if len(owners) != len(profile['vertex_ids']): raise ValueError('Rigid owner map differs from selected vertex count')
            amounts = partition.get('rigid_weight_sums') if profile.get('preserve_rigid_weight_bits') else [1.0] * len(owners)
            if amounts is None or len(amounts) != len(owners): raise ValueError('Rigid preserved weight sums are missing')
            owner_names = {int(vertex) + part['begin']: (source_document['nodes'][skin['joints'][owner]]['name'], amount)
                           for vertex, owner, amount in zip(profile['vertex_ids'], owners, amounts)}
    original_ids = witness.get('surface_vertex_ids', [])
    for probe, signature in enumerate(witness.get('surface_source_morph_positions', [])):
        source_id = original_ids[probe]
        if source_id in selected:
            result['surface_source_morph_positions'][probe] = []
        else:
            part = next(p for p in parts if p['begin'] <= source_id < p['end'])
            row = mapping.get(part['mesh'])
            if row is not None and row['removed_target_indices']:
                if len(signature) > row['targets_before']: raise ValueError('Unexpected original morph-signature prefix')
                removed = set(row['removed_target_indices'])
                result['surface_source_morph_positions'][probe] = [v for i, v in enumerate(signature) if i not in removed]
    if owner_names and 'surface_skin_influences' in result:
        for probe, source_id in enumerate(original_ids):
            if source_id in owner_names:
                name, amount = owner_names[source_id]
                result['surface_skin_influences'][probe] = {name: amount}
    # The transformation is intentionally limited to identity/binding metadata.
    def physical(value):
        ignored = {'sha256', 'reference_sha256', 'morph_weights', 'surface_source_morph_positions',
                   'surface_skin_influences', 'surface_vertex_ids'}
        if isinstance(value, dict): return {k: physical(v) for k, v in value.items() if k not in ignored and not k.endswith('_vertex_ids') and not k.endswith('_vertices')}
        if isinstance(value, list): return [physical(v) for v in value]
        return value
    if physical(witness) != physical(result): raise ValueError('Independent physical observations changed')
    return result
