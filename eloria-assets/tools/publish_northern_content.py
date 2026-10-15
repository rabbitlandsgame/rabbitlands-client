"""Record actual served NPCs, resources and encounters for a landscape batch.

The default remains the original northern group; --region selects another batch.
"""
import argparse
import json
from pathlib import Path
import sys

from legacy_content import read_base_only

CLIENT = Path(__file__).resolve().parents[2]
REGIONS = CLIENT/'eloria-assets/maps/nymara-regions'
EXTERIORS = ('amberwood', 'whitehorn_range', 'grey_moors', 'mirrorhold', 'amethyst_barrens')


def publish(server, regions=EXTERIORS):
    # The legacy rosters come from the base content tables only, never the continent-v2 overlay (serve plan CV13).
    read_base_only(server)
    sys.path[:0] = [str(server), str(REGIONS/'_toolkit')]
    from eloria.npcs import load_npcs
    from eloria.harvesting import load_harvesting
    from eloria.spawns import load_spawns
    from contentposts import apply_runtime, native_tile_delta
    profile = server/'config/eloria'
    npcs = load_npcs(profile/'npcs.txt')
    _, resources = load_harvesting(profile/'harvesting.txt')
    spawns = load_spawns(profile/'spawns.txt')
    for region in regions:
        package = CLIENT/'eloria-assets/maps/four-gates' if region=='four_gates' else REGIONS/region
        path = package/'world.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        delta = native_tile_delta(manifest, package)
        def tile(entry):
            return {'serverTile': [int(entry.x-delta[0]), int(entry.y-delta[1])], 'authority': 'server'}
        roster = {
            'npcs': [dict(id=n.name, name=n.name, role=n.role, **tile(n)) for n in sorted(npcs,key=lambda n:n.name) if n.map_id == region],
            'resources': [dict(id=identity, resource=n.resource, **tile(n))
                          for (map_id, identity), n in sorted(resources.items()) if map_id == region],
            'encounters': [dict(creature=n.creature, **tile(n)) for n in spawns if n.map_id == region],
        }
        (package/'source/runtime-content.json').write_text(json.dumps(roster, indent=2)+'\n', encoding='utf-8')
        apply_runtime(manifest, package)
        path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        print(region, {k: len(v) for k, v in roster.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True, type=Path)
    parser.add_argument('--region', action='append')
    args = parser.parse_args()
    publish(args.server.resolve(), args.region or EXTERIORS)
