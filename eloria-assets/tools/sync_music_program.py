"""Publish the authored music contexts to the sibling Rabbit Lands server.

With no --map, the whole server file is written from the client source (every map's record, the programs list and
the shared settings). The server copy also carries music the client source does not (the A3 isles' records), which
a whole sync reverts; --map MAP (repeatable) rewrites only that map's block in the server file - its record from the
client source, with the room zones its package's world.json gives an interior and that file's digest
(zone_source_sha256), exactly as a whole sync writes them - and leaves every other byte of the file as it stands. A
map the server file lacks is inserted where the client source orders it. --check writes nothing and exits 1 when
the server file differs from what the run would write.

    python -B eloria-assets/tools/sync_music_program.py --server ../rabbitlands-server --map landfall_town [--check]
"""
from pathlib import Path
import argparse
import copy
import json
import hashlib
import sys

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

def load_source() -> dict:
    """The client's music program, every program's tracks checked against the music the client ships."""
    source = CLIENT / 'eloria-assets/source/audio/music-program.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    tracks = {a['name'].removeprefix('music_') for a in json.loads(
        (source.parent / 'manifest.json').read_text(encoding='utf-8'))['assets'] if a['kind'] == 'music'}
    for name, program in data['programs'].items():
        if not program['tracks'] or not set(program['tracks']) <= tracks:
            raise ValueError('Unknown music in program ' + name)
    return data

def registry() -> dict:
    return json.loads((CLIENT / 'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))['maps']

def map_record(map_id: str, record: dict, rows: dict) -> dict:
    """One map's server record: the client source's `record` (not changed), with the room zones of an interior that
    has a registry row (`rows`) and is neither outside nor a gauntlet, and its world.json's digest."""
    record = copy.deepcopy(record)
    if map_id in rows and not record.get('outside') and not record.get('gauntlet'):
        zones, digest = interior_zones(map_id, rows[map_id])
        if zones:
            record['zones'] = zones
            record['zone_source_sha256'] = digest
    return record

def server_file(server: Path) -> Path:
    destination = server / 'config/eloria/music-program.json'
    if not destination.parent.is_dir():
        raise ValueError('Expected a Rabbit Lands server profile: ' + str(destination.parent))
    return destination

def render(data: dict) -> str:
    """The server file's text for `data`, as every run of this tool writes it."""
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'

def sync(server: Path, check: bool = False) -> bool:
    """Write the whole server file from the client source. Returns whether the file changed (would change)."""
    data = load_source()
    output = {k: v for k, v in data.items() if k != 'programs'}
    output['programs'] = list(data['programs'])
    rows = registry()
    output['maps'] = {map_id: map_record(map_id, record, rows) for map_id, record in data['maps'].items()}
    destination = server_file(server)
    text = render(output)
    changed = not destination.is_file() or destination.read_text(encoding='utf-8') != text
    if changed and not check:
        destination.write_text(text, encoding='utf-8', newline='\n')
    return changed

def _placed(maps: dict, map_id: str, record: dict, order: list) -> dict:
    """`maps` with `map_id`'s record replaced where it stands, or inserted after the nearest map the client source
    (`order`) lists before it (first when there is none)."""
    if map_id in maps:
        maps[map_id] = record
        return maps
    before = order[:order.index(map_id)]
    anchor = next((key for key in reversed(before) if key in maps), None)
    result = {} if anchor is not None else {map_id: record}
    for key, value in maps.items():
        result[key] = value
        if key == anchor:
            result[map_id] = record
    return result

def sync_maps(server: Path, map_ids, check: bool = False) -> list:
    """Rewrite only the blocks of `map_ids` in the server file (see the module docstring); the rest of the file,
    the server-only music included, stays byte for byte. Returns the map ids whose block changed (would change).
    Refuses a map the client source has no record for, a program the server file does not list, and a server file
    this tool did not write (rewriting a block there would reformat everything else)."""
    data = load_source()
    destination = server_file(server)
    text = destination.read_text(encoding='utf-8')
    current = json.loads(text)
    if render(current) != text:
        raise ValueError(f'{destination} is not laid out as this tool writes it: a single-map rewrite would change '
                         'the rest of the file too; run the whole sync, or lay it out first')
    rows = registry()
    order = list(data['maps'])
    programs = set(current.get('programs', []))
    maps = current['maps']
    changed = []
    for map_id in dict.fromkeys(map_ids):
        if map_id not in data['maps']:
            raise ValueError(f'{map_id} has no record in the client music program')
        record = map_record(map_id, data['maps'][map_id], rows)
        played = {record.get('day'), record.get('night')} | {zone.get(key) for zone in record.get('zones', [])
                                                              for key in ('day', 'night')}
        unknown = sorted(name for name in played - {None} if name not in programs)
        if unknown:
            raise ValueError(f'{map_id} plays {", ".join(unknown)}, which the server file does not list: run the '
                             'whole sync')
        if map_id not in maps or json.dumps(maps[map_id], ensure_ascii=False) != json.dumps(record, ensure_ascii=False):
            changed.append(map_id)
        maps = _placed(maps, map_id, record, order)
    current['maps'] = maps
    if changed and not check:
        destination.write_text(render(current), encoding='utf-8', newline='\n')
    return changed

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--server', type=Path, default=CLIENT.parent / 'rabbitlands-server')
    parser.add_argument('--map', action='append', dest='maps', metavar='MAP',
                        help='rewrite only this map\'s block of the server file (repeatable)')
    parser.add_argument('--check', action='store_true', help='write nothing; exit 1 when the server file is stale')
    arguments = parser.parse_args()
    server = arguments.server.resolve()
    if arguments.maps:
        stale = sync_maps(server, arguments.maps, arguments.check)
        for map_id in dict.fromkeys(arguments.maps):
            zones = len((json.loads(server_file(server).read_text(encoding='utf-8'))['maps'].get(map_id) or {})
                        .get('zones', []))
            state = ('stale' if arguments.check else 'written') if map_id in stale else 'current'
            print(f'{map_id}: {state} ({zones} zones in the server file)')
    else:
        stale = sync(server, arguments.check)
        print('server music program: ' + (('stale' if arguments.check else 'written') if stale else 'current'))
    sys.exit(1 if arguments.check and stale else 0)
