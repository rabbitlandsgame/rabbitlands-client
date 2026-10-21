"""Publish the authored music contexts to the sibling Rabbit Lands server."""
from pathlib import Path
import argparse
import json
import hashlib

CLIENT = Path(__file__).resolve().parents[2]

def room_program(name: str) -> str | None:
    name = name.lower()
    for words, program in [
        (('tavern', 'inn', 'ferryman'), 'inn'),
        (('sunken', 'undercity'), 'ancient_temple'),
        (('chapel', 'temple', 'basilica', 'sanctuary', 'sanctum', 'shrine'), 'temple'),
        (('snowline', 'shelter'), 'winter_home'),
        (('hall', 'castle'), 'castle'),
        (('cottage', 'house', 'home', 'lodging'), 'home_day'),
        (('shop', 'store', 'forge', 'workshop'), 'shop'),
        (('archive', 'library', 'lens_vault'), 'library'),
        (('barrow', 'crypt', 'tomb', 'catacomb'), 'barrow'),
        (('basalt', 'lava', 'magma'), 'fire_dungeon'),
        (('cenote', 'crystal', 'geode', 'vault', 'cistern', 'labyrinth'), 'mystic_cave'),
        (('mine', 'cave', 'cavern', 'undercroft', 'cellar', 'root', 'quarry'), 'cave'),
    ]:
        if any(word in name for word in words):
            return program
    return None

def interior_zones(map_id: str, metadata: dict) -> tuple[list, str]:
    """Transform authored spaces and disconnected-section arrivals into server cells."""
    path = CLIENT / 'godot-client' / metadata['manifest'].removeprefix('res://')
    content = path.read_bytes()
    world = json.loads(content)
    transform = metadata.get('coordinateTransform', {})
    origin = transform.get('origin', [0, 0, 0])
    server = transform.get('serverOrigin', [0, 0])
    scale = transform.get('metresPerTile', 1)
    flip = transform.get('invertServerY', True)
    def point(x, z):
        return [(x-origin[0])/scale+server[0],
                (-(z-origin[2]) if flip else z-origin[2])/scale+server[1]]
    zones = []
    def add(name, bounds, program):
        x0, z0, x1, z1 = bounds
        a, b = point(x0, z0), point(x1, z1)
        zones.append(dict(name=name,
            bounds=[round(min(a[0],b[0]),3), round(min(a[1],b[1]),3),
                    round(max(a[0],b[0]),3), round(max(a[1],b[1]),3)],
            day=program, night='home_night' if program=='home_day' else program))
    for name, space in world.get('spaces', {}).items():
        program = room_program(name)
        if program and all(k in space for k in ('x0','x1','z0','z1')):
            add(name, (space['x0']-.6,space['z0']-.6,space['x1']+.6,space['z1']+.6), program)
    for chamber in world.get('chambers', []):
        # The chamber's name first: the Cenote Deeps keeps its section id, spindle_cavern, from its cavern days.
        program = room_program(chamber.get('name', '')) or room_program(chamber.get('section', ''))
        if program:
            x, _, z = chamber['position']
            radius = chamber['radius']+1
            add(chamber['id'], (x-radius,z-radius,x+radius,z+radius), program)
    if not zones:
        for section in world.get('sections', []):
            program = room_program(section['id'])
            arrival = next((s['position'] for s in world.get('spawnPoints', [])
                            if s['id']==section['id']+'-default'), None)
            if program and arrival:
                # These sections are disconnected. Their actual entry points
                # classify the component without inventing rectangular extents.
                zones.append(dict(name=section['id'], anchor=point(arrival[0], arrival[2]),
                                  day=program, night='home_night' if program=='home_day' else program))
    return zones, hashlib.sha256(content).hexdigest()

def sync(server: Path) -> None:
    source = CLIENT / 'eloria-assets/source/audio/music-program.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    tracks = {a['name'].removeprefix('music_') for a in json.loads(
        (source.parent / 'manifest.json').read_text(encoding='utf-8'))['assets'] if a['kind'] == 'music'}
    for name, program in data['programs'].items():
        if not program['tracks'] or not set(program['tracks']) <= tracks:
            raise ValueError('Unknown music in program ' + name)
    output = {k: v for k, v in data.items() if k != 'programs'}
    output['programs'] = list(data['programs'])
    registry = json.loads((CLIENT / 'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))['maps']
    for map_id, record in output['maps'].items():
        if map_id in registry and not record.get('outside') and not record.get('gauntlet'):
            zones, digest = interior_zones(map_id, registry[map_id])
            if zones:
                record['zones'] = zones
                record['zone_source_sha256'] = digest
    destination = server / 'config/eloria/music-program.json'
    if not destination.parent.is_dir():
        raise ValueError('Expected a Rabbit Lands server profile: ' + str(destination.parent))
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, default=CLIENT.parent / 'rabbitlands-server')
    sync(parser.parse_args().server.resolve())
