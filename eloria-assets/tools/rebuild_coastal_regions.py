"""Build the compact coastal group and publish matching client/server contracts.

python eloria-assets/tools/rebuild_coastal_regions.py --server <checkout> --data <ELM directory>
Use --skip-build for reviewed assets, or --stage to resume one contract phase.
Regional coordinate migrations are guarded; repeated publication preserves IDs.
"""
from pathlib import Path
import argparse
import json
import sys
import rebuild_northern_regions as shared
from legacy_content import read_base_only

CLIENT=Path(__file__).resolve().parents[2]
MAPS=CLIENT/'eloria-assets/maps'
REGIONS=MAPS/'nymara-regions'
NEW=('westhaven','four_gates','crownwater')
EXTERIORS=('grey_moors','mirrorhold',*NEW)
ROOMS=tuple('four-gates-'+suffix for suffix in ('lantern-row','reedworks',
    'stormglass-house','mirrorsmith-forge','ferrymans-rest','deposit-four-keys'))
FAMILY=EXTERIORS+('grey_moor_barrows','mirrorhold_interiors','westhaven_insides','drowned_crown')+tuple(
    name+'_secrets' for name in EXTERIORS)+ROOMS

def package(region):
    return MAPS/'four-gates' if region=='four_gates' else REGIONS/region

def bind_legacy_resource_ids(server):
    """Resolve the legacy Four Gates markers once, before their coordinates move."""
    sys.path.insert(0,str(server))
    from eloria.harvesting import load_harvesting
    profile=server/'config/eloria';path=profile/'client_content_manifest.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    _,nodes=load_harvesting(profile/'harvesting.txt')
    for entry in data.get('four_gates_harvestables',[]):
        if entry.get('server_object_id') is not None:
            continue
        matches=[n.object_id for n in nodes.values() if n.map_id=='four_gates'
                 and [n.x,n.y]==entry['serverTile']]
        if len(matches)!=1:
            raise ValueError(f"{entry['id']}: expected one existing server resource at {entry['serverTile']}, got {matches}")
        entry['server_object_id']=matches[0]
    path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')

def prepare(server,data):
    bind_legacy_resource_ids(server)
    for region in NEW:
        source=package(region)/'source'
        args=[server] if region=='westhaven' else ['--server',server,'--apply']
        shared.run(source,source/'migrate_compact_server.py',*args)
    for room in ROOMS:
        shared.run(CLIENT,REGIONS/'_toolkit/export_interior_collision.py',
                   '--package',MAPS/room,'--cells',36)
    sys.path[:0]=[str(server/'tools'),str(server)]
    from generate_nymara_maps import ARRIVAL_TILES,MAP_TILES_WIDE_BY_NAME
    path=server/'config/eloria/client_content_manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    by_id={entry['id']:entry for entry in manifest['maps']}
    for region in FAMILY:
        entry=by_id.get(region)
        if entry is None:
            entry={'id':region};manifest['maps'].append(entry)
        entry.update(server_cells=MAP_TILES_WIDE_BY_NAME[region]*6,
                     arrival=list(ARRIVAL_TILES[region]))
    path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    update_registry()

def collision(server,data):
    shared.collision(server,data,family=FAMILY)

def content(server,data):
    shared.content(server,data,exteriors=EXTERIORS,new=NEW,family=FAMILY)
    shared.run(CLIENT,CLIENT/'eloria-assets/tools/sync_package_content.py','--manifest',
               server/'config/eloria/client_content_manifest.json','--package','four-gates',
               '--write-source-posts','--apply')

def update_registry():
    registry_path=CLIENT/'godot-client/data/maps/registry.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8'))
    for region in NEW:
        manifest=json.loads((package(region)/'world.json').read_text(encoding='utf-8'))
        registry['maps'][region]['coordinateTransform']=manifest['coordinateTransform']
        registry['maps'][region]['landscapeTransitions']=True
    for room in ROOMS:
        manifest=json.loads((MAPS/room/'world.json').read_text(encoding='utf-8'))
        registry['maps'][room]['coordinateTransform']=manifest['coordinateTransform']
        registry['maps'][room]['interiorOf']='four_gates'
    registry_path.write_text(json.dumps(registry,indent=2)+'\n',encoding='utf-8')

def publish(server,data):
    update_registry()
    shared.publish(server,exteriors=EXTERIORS,family=FAMILY)
    shared.run(CLIENT,CLIENT/'eloria-assets/tools/build_continent_map.py')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--skip-build',action='store_true')
    parser.add_argument('--stage',choices=('all','prepare','collision','content','publish'),default='all')
    args=parser.parse_args();server=args.server.resolve();data=args.data.resolve()
    # Legacy content only: base tables, never the continent-v2 overlay (serve plan CV13; see legacy_content.py).
    read_base_only(server)
    if not args.skip_build:
        for region in EXTERIORS:
            source=package(region)/'source'
            shared.run(source,source/'rebuild_landscape.py')
    for name,stage in (('prepare',prepare),('collision',collision),('content',content),('publish',publish)):
        if args.stage in ('all',name):
            stage(server,data)

if __name__=='__main__':main()
