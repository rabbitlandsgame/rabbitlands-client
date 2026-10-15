"""Publish proximity links from the continent graph and authored border surveys.

Run after rebuilding a paired border. Ferries retain their deliberate journeys.
Only reciprocal, surveyed collars permit a continuous visual handoff; every land
connection can still preload its destination without changing server authority.

The single-master continent publishes its graph with its geometry and server
contracts. This legacy builder must not replace those surveyed physical edges.
"""
import json
import argparse
import re
import math
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2]
REGIONS = CLIENT / 'eloria-assets/maps/nymara-regions'


def guard_shared_continent(geography, manifests=()):
    """Reject both published chunk worlds and an export awaiting publication."""
    if geography.get('geometryMode') == 'continent-chunks-v1' or any(
            manifest.get('streamingChunks') or manifest.get('continentGeography', {}).get(
                'geometryMode') == 'continent-chunks-v1' for manifest in manifests):
        raise ValueError('The shared continent graph is published together with its named chunk '
                         'exports. Use eloria-assets/maps/nymara-regions/_continent/build_pipeline.py '
                         'instead of build_exterior_streaming.py; the legacy builder cannot '
                         'reconstruct its surveyed physical preload edges and visual neighbours.')


def physical_edges(geography):
    """Merge profile samples into finite straight shared-edge spans."""
    grouped = {}
    for segment in geography.get('boundaryHeightField', {}).get('segments', []):
        pair = tuple(sorted(segment['regions']))
        a, b = segment['start'], segment['end']
        axis = 1 if abs(a[0]-b[0]) < 1e-6 else 0
        key = pair, axis, round(a[1-axis], 6)
        grouped.setdefault(key, []).append(sorted([a[axis], b[axis]]))
    result = {}
    for (pair, axis, fixed), spans in sorted(grouped.items()):
        merged = []
        for lo, hi in sorted(spans):
            if merged and lo <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for lo, hi in merged:
            points = [[lo, fixed], [hi, fixed]] if axis == 0 else [[fixed, lo], [fixed, hi]]
            result.setdefault(pair, []).append(points)
    return result


def add_geographic_views(result, registry):
    path = REGIONS / 'continent-geography.json'
    if not path.is_file(): return []
    geography = json.loads(path.read_text(encoding='utf-8'))
    edges = physical_edges(geography)
    linked = {tuple(sorted(end['map'] for end in link['ends'])) for link in result}
    def local_edges(region, spans):
        t = geography['regions'][region]['translation']
        return [[[p[0]-t[0], p[1]-t[2]] for p in line] for line in spans]
    for link in result:
        spans = edges.get(tuple(sorted(end['map'] for end in link['ends'])), [])
        for end in link['ends']:
            end['preloadEdges'] = local_edges(end['map'], spans)
    visual = []
    for pair, spans in sorted(edges.items()):
        if pair in linked: continue
        lengths = [math.dist(a, b) for a, b in spans]
        center = [sum((a[i]+b[i])*.5*d for (a,b),d in zip(spans,lengths))/sum(lengths) for i in (0, 1)]
        identity = 'geographic-view:' + '--'.join(pair)
        ends = []
        for index, region in enumerate(pair):
            t = geography['regions'][region]['translation']
            anchor = [center[0]-t[0], -t[1], center[1]-t[2]]
            manifest_path = Path(registry[region]['manifest'].replace('res://', str(CLIENT/'godot-client')+'/')).resolve()
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            ends.append(dict(map=region, position=anchor, preloadEdges=local_edges(region, spans),
                coordinateTransform=manifest['coordinateTransform'], visualScenes=[],
                frame=dict(id=identity, anchor=anchor, outward=[1 if index == 0 else -1, 0],
                    geometryMode='continent-owned-v1', viewHalfWidth=110, collarDepth=0)))
        visual.append(dict(id=identity, ends=ends, seamless=False, visualOnly=True))
    return visual


def build(server=None):
    geography_path = REGIONS / 'continent-geography.json'
    geography = json.loads(geography_path.read_text(encoding='utf-8')) if geography_path.is_file() else {}
    guard_shared_continent(geography)
    graph = json.loads((REGIONS / 'region-connections.json').read_text(encoding='utf-8'))
    registry = json.loads((CLIENT / 'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))
    registry = registry.get('maps', registry)
    region_ids = {link[key] for link in graph['connections'] if link['type'] in ('walk', 'causeway')
                  for key in ('from', 'to')}
    manifests = {}
    for region in sorted(region_ids):
        path = Path(registry[region]['manifest'].replace('res://', str(CLIENT / 'godot-client') + '/')).resolve()
        manifests[region] = json.loads(path.read_text(encoding='utf-8'))
    guard_shared_continent(geography, manifests.values())
    actors = json.loads((CLIENT / 'godot-client/data/actors/models.json').read_text(encoding='utf-8'))
    objects = json.loads((CLIENT / 'godot-client/data/world/objects.json').read_text(encoding='utf-8'))
    npc_types = {}
    if server:
        for line in (server / 'config/eloria/npcs.txt').read_text(encoding='utf-8').splitlines():
            fields = [p.strip() for p in line.split('|')]
            actor_type = re.search(r'actor_type=(\d+)', line)
            if len(fields) > 2 and fields[0] == 'npc' and actor_type:
                npc_types.setdefault(fields[2], set()).add(actor_type[1])
    result = []
    for link in graph['connections']:
        if link['type'] not in ('walk', 'causeway'): continue
        ends = []
        for key in ('from', 'to'):
            region = link[key]
            manifest = manifests[region]
            entries = manifest.get('portals', []) + manifest.get('interactives', [])
            portal = next(p for p in entries if p.get('id') == link[key + '_portal'])
            frame = next((s for s in manifest.get('streamingBorders', []) if s['portal'] == portal['id']), {})
            visuals = set()
            harvest = objects['harvestables']
            resources = manifest.get('harvestables', []) + manifest.get('runtimePopulation', {}).get('resources', [])
            for resource in resources:
                key = harvest['resources'].get(resource.get('resource', ''))
                if key in harvest['models']: visuals.add(harvest['models'][key]['scene'])
            for actor_type in npc_types.get(region, []):
                key = actors['actorTypes'].get(actor_type)
                if key in actors['models']: visuals.add(actors['models'][key]['scene'])
            ends.append(dict(map=region, portal=portal['id'], position=portal['position'], frame=frame,
                             coordinateTransform=manifest['coordinateTransform'], visualScenes=sorted(visuals)))
        joined = bool(ends[0]['frame'] and ends[1]['frame'] and
                      ends[0]['frame']['id'] == ends[1]['frame']['id'])
        result.append(dict(id=link['from'] + '--' + link['to'], ends=ends, seamless=joined))
    visual = add_geographic_views(result, registry)
    return dict(schema=1, preloadDistance=240, retainDistance=320, maximumNeighbours=3,
                connections=result, visualConnections=visual)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path)
    args = parser.parse_args()
    target = CLIENT / 'godot-client/data/maps/exterior_connections.json'
    data = build(args.server)
    target.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    if args.server:
        (args.server / 'config/eloria/exterior_connections.json').write_text(
            json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(f"{len(data['connections'])} land connections; {sum(c['seamless'] for c in data['connections'])} surveyed joins")
