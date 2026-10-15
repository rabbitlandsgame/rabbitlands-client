"""Persist Whitehorn's authoritative NPC/resource posts for reproducible builds."""
from pathlib import Path
import json
import re
import sys

SOURCE = Path(__file__).resolve().parent
PACKAGE = SOURCE.parent
sys.path.insert(0, str(PACKAGE.parent / '_toolkit'))


def apply(manifest, package, posts):
    import contentposts
    for bucket in ('npcMarkers', 'harvestables'):
        manifest[bucket] = posts[bucket]
    tiles = {bucket: {e['id']: e['serverTile'] for e in posts[bucket]}
             for bucket in ('npcMarkers', 'harvestables')}
    tiles['spawnPoints'] = {'whitehorn-arrival': [106, 69]}
    contentposts.apply(manifest, package, tiles)


def sync(server):
    profile = server / 'config/eloria'
    posts = {'npcMarkers': [], 'harvestables': []}
    for line in (profile / 'npcs.txt').read_text().splitlines():
        p = [v.strip() for v in line.split('|')]
        if len(p) < 6 or p[0] != 'npc' or p[2] != 'whitehorn_range': continue
        posts['npcMarkers'].append({'id': 'whitehorn-' + re.sub(r'[^a-z0-9]+', '-', p[1].lower()),
            'name': p[1], 'role': p[5], 'serverTile': [int(p[3]), int(p[4])], 'authority': 'server'})
    for line in (profile / 'harvesting.txt').read_text().splitlines():
        p = [v.strip() for v in line.split('|')]
        if len(p) < 6 or p[0] != 'node' or p[1] != 'whitehorn_range': continue
        posts['harvestables'].append({'id': 'whitehorn-resource-' + p[2], 'resource': p[5],
            'serverTile': [int(p[3]), int(p[4])], 'authority': 'server'})
    (SOURCE / 'server-content.json').write_text(json.dumps(posts, indent=2) + '\n')
    path = PACKAGE / 'world.json'
    manifest = json.loads(path.read_text())
    apply(manifest, PACKAGE, posts)
    path.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__': sync(Path(sys.argv[1]).resolve())
