"""Publish the authored interior packages beside the exterior partition: the Landfall underground's caves and the
Landfall town's building rooms.

Interiors have independent frames and deliberately disconnected chambers. They never acquire ownership polygons or
seamless continent links; click portals connect each section. SOURCES lists the interior sources, each authoring one
interior map, in publication order (the caves first, so their rows, manifest keys and record stay as they were):

  content/underground.json    the caves (underground_source.py reads it; build_underground.py builds landfall_insides)
  content/landfall_town.json  the town's rooms (town_source.py reads it; build_town_interiors.py builds landfall_town)

A source that is absent publishes nothing. Each package must have been built from its source by the builder its own
provenance names, and that builder must be the one SOURCES gives the source (its provenance.builderSha256 is that
file's; a package that records the helpers its builder imports, provenance.imports {name: sha256} (the town's:
build_underground.py, town_source.py, underground_source.py), is refused once any of them changed).

The rules (pass 2, 2026-10-21: several doors per section, passages between sections; 2026-10-27: building doors,
interior people and interactives, several sources):
  * every cave door (kind "underground", the default): its marker is in its exterior map's bake as an
    underground_entrance runtime point on the door's tile;
  * every building door (kind "building"): no scene marker (the bake holds no runtime point with its object id); the
    painted door point (`position`) lies within DOOR_REACH tiles of its tile; it carries a `label`, an `exitLabel` and
    optionally a map `category` (map_categories.py; an unknown one is refused); neither its tile nor its return tile
    is an exterior NPC post, an exterior interactive's tile or another door's tile;
  * every door: the entrance and return tiles lie in the map's territory, are walkable on its served grid, reached
    from its arrival, with four walkable neighbours, and differ; its object id is used nowhere else; its arrival is
    walkable and its exit reached;
  * every passage end: its tile and its arrival are reached inside its own section; its object id (one per end) is
    used nowhere else;
  * object ids: a door, passage end, node or interactive id is used once across every interior source (the client's
    objects.json authoredObjects is keyed by id alone), and no door, passage end or interactive id is an exterior
    node's or interactive's on any map;
  * a section's floor is one walk component from its primary arrival with every interior person's post closed (the
    server blocks the tile an NPC stands on); sections never connect; nothing walkable is stranded;
  * nodes: the tile is blocked, a 4-neighbour is reached, the resource exists;
  * encounters: a reviewed model, the footprint fits, leash 1-8 and leash + 20 tiles from every arrival of the section
    (doors' and passage ends');
  * interior people (`npcs`): the post is open ground with all eight neighbours reached; it is no arrival, exit,
    passage end, interactive, spawn or other post; the name is new (not in the base npcs.txt, not an isle person's,
    not another interior person's); the body is an actor type 300-377; facing is a compass point;
  * interior interactives: role information or crafting_station; the tile is reached or a reached tile lies within
    INTERACTIVE_REACH (Chebyshev) of it; it is no arrival, exit, passage end or post.
Rows: a portal pair and an interactive per door end (caves: "Beyond it lies <section>. <danger>." outside, "Beyond it
lies <map>." inside; buildings: "<label>. <danger>." outside, "<exitLabel>." inside), a same-map portal and an
interactive ("A way leads on into <section>. <danger>.", or the end's own "<label>.") per passage end, the nodes,
spawns, the people (npcs.txt) and the interactives.
"""
from collections import Counter, deque
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import ownership
import underground_source as S

SOURCE = 'eloria-assets/maps/continent-v2/_continent_v2/content/underground.json'
TOWN_SOURCE = 'eloria-assets/maps/continent-v2/_continent_v2/content/landfall_town.json'
HERE = Path(__file__).resolve().parent

# The interior sources in publication order. `reader` is the module that reads the source's ways in (both expose the
# underground_source functions); `builder` the one builder whose packages publish (compared with the package's own
# provenance); `portals`/`rows` the manifest block's keys for the interior's portal rows and row counts; `banner` the
# comment heading the interior's rows in each overlay table.
SOURCES = (
    SimpleNamespace(kind='underground', source=SOURCE, reader='underground_source', builder='build_underground.py',
                    portals='undergroundPortals', rows='undergroundRows', label='underground',
                    banner='# Landfall underground: authored shared interiors.'),
    SimpleNamespace(kind='building', source=TOWN_SOURCE, reader='town_source', builder='build_town_interiors.py',
                    portals='buildingPortals', rows='buildingRows', label='town interiors',
                    banner='# Landfall town: building interiors.'),
)
DOOR_KINDS = ('underground', 'building')
# A building door's painted point (`position`, on the facade) stands this close to its tile (Chebyshev tiles).
DOOR_REACH = 6
# An interior interactive may stand in its furniture: a reached tile within this reach (Chebyshev) is enough.
INTERACTIVE_REACH = 2
INTERACTIVE_ROLES = ('information', 'crafting_station')
# The default `target` column of an interior interactive by role (a source may name its own).
INTERACTIVE_TARGETS = {'information': 'notice', 'crafting_station': 'crafting'}
NPC_ACTOR_TYPES = range(300, 378)
COMPASS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
FOUR = ((1, 0), (-1, 0), (0, 1), (0, -1))
EIGHT = tuple((dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy)


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reader_of(spec):
    """The source's reader module: underground_source for the caves, town_source for the town (its functions as
    underground_source's where it defines none of its own)."""
    module = importlib.import_module(spec.reader)
    if module is S:
        return S
    return SimpleNamespace(**{name: getattr(module, name, getattr(S, name, None)) for name in
                              ('check', 'doors', 'passages', 'passage_ends', 'arrivals', 'primary_arrival',
                               'primary_exit', 'object_ids')},
                           npcs=getattr(module, 'npcs', None), interactives=getattr(module, 'interactives', None),
                           module=module)


def section_npcs(reader, section):
    found = getattr(reader, 'npcs', None)
    return list(found(section)) if found else list(section.get('npcs', []))


def section_interactives(reader, section):
    found = getattr(reader, 'interactives', None)
    return list(found(section)) if found else list(section.get('interactives', []))


class Fields:
    """The overlay's field rules (publish_server passes its own: plain_field, occupation_field, npc_portrait)."""

    def __init__(self, error):
        self.error = error

    def plain(self, value, where):
        text = str(value)
        if any(mark in text for mark in ('|', '#', '\n', '\r')) or text != text.strip() or not text:
            raise self.error(f"{where}: {text!r} is empty, padded, or holds '|', '#' or a line break")
        return text

    def occupation(self, value, name, where):
        if value in (None, ''):
            return ''
        text = self.plain(value, where)
        if len(text) > 32 or any(c in '|#,=<>' for c in text):
            raise self.error(f'{where}: occupation {value!r} breaks the npcs.txt rules')
        return text

    def portrait(self, actor_type, occupation='', facing=''):
        return (f'actor_type={int(actor_type)}' + (f',occupation={occupation}' if occupation else '')
                + (f',facing={facing}' if facing else ''))


def sentence(text):
    """`text` as a sentence ending in one full stop."""
    text = str(text).rstrip()
    return text if text.endswith(('.', '!', '?')) else text + '.'


def load(ctx, error):
    """[(spec, reader, path, design)] for every interior source present, checked and told apart."""
    loaded, regions, aliases = [], {}, {}
    exteriors = set(getattr(ctx, 'frames', {}) or {})
    for spec in SOURCES:
        path = Path(ctx.checkout)/spec.source
        if not path.is_file():
            continue
        design = json.loads(path.read_text(encoding='utf-8'))
        reader = reader_of(spec)
        try:
            reader.check(design)
        except ValueError as problem:
            raise error(f'{spec.label} source: {problem}')
        info = design['map']
        if info['id'] in regions or info['id'] in exteriors:
            raise error(f'{spec.source}: map {info["id"]} is already {regions.get(info["id"], "an exterior map")}')
        if info['alias'] in aliases:
            raise error(f'{spec.source}: alias {info["alias"]} is already {aliases[info["alias"]]}\'s')
        regions[info['id']] = spec.source
        aliases[info['alias']] = info['id']
        loaded.append((spec, reader, path, design))
    return loaded


def interior_ids(reader, design):
    """[(kind, id)] of every object id an interior source uses: doors, passage ends, nodes and interactives."""
    result = [('door', d['object']) for s in design['sections'] for d in reader.doors(s)]
    result += [('node', n[0]) for s in design['sections'] for n in s.get('nodes', [])]
    result += [('passage', e['object']) for p in reader.passages(design) for e in p['ends']]
    result += [('interactive', i['object']) for s in design['sections'] for i in section_interactives(reader, s)]
    return result


def check_ids(loaded, pub, error):
    """Object ids are unique across every interior source, and no door, passage end or interactive id is an exterior
    node's or interactive's on any map (objects.json authoredObjects is keyed by id alone)."""
    owners = {}
    exterior = {n['id'] for n in pub.nodes} | {i['object'] for i in pub.interactives}
    for spec, reader, _path, design in loaded:
        for kind, oid in interior_ids(reader, design):
            if not isinstance(oid, int) or not 0 < oid < 60000:
                raise error(f'{spec.source}: {kind} object id {oid!r} is not 1-59999')
            if oid in owners:
                raise error(f'{spec.source}: {kind} object id {oid} is already {owners[oid]}')
            owners[oid] = f'a {kind} of {design["map"]["id"]}'
            if kind != 'node' and oid in exterior:
                raise error(f'{spec.source}: {kind} object id {oid} is already an exterior object\'s '
                            '(objects.json is keyed by id alone)')


def attach(ctx, pub, error=ValueError, fields=None):
    """Validate every interior source present and add its rows to the overlay. Sets pub.interiors (one namespace per
    interior, in SOURCES order), pub.underground (the caves', or None) and pub.vendor_regions."""
    fields = fields or Fields(error)
    pub.interiors = []
    pub.underground = None
    pub.vendor_regions = list(pub.regions)
    loaded = load(ctx, error)
    check_ids(loaded, pub, error)
    door_tiles = {}
    for spec, reader, path, design in loaded:
        interior = attach_one(ctx, pub, spec, reader, path, design, error, fields, door_tiles)
        pub.interiors.append(interior)
        if spec.kind == 'underground' and pub.underground is None:
            pub.underground = interior
        pub.vendor_regions.append(interior.region)


def attach_one(ctx, pub, spec, reader, path, design, error, fields, door_tiles):
    info=design['map']; region=info['id'];cells=info['cells']
    package=ctx.maps_root/'continent-v2'/region/'client'
    if not (package/'world.json').is_file():
        raise error(f'{region}: {spec.source} has no package at {package}: build it with {spec.builder}')
    doc=json.loads((package/'world.json').read_text(encoding='utf-8'))
    provenance=doc.get('provenance',{})
    named=Path(str(provenance.get('builder',''))).name
    if named!=spec.builder:
        raise error(f'{region}: the package was built by {named or "no named builder"}; {spec.source} publishes only '
                    f'what {spec.builder} builds')
    if provenance.get('sourceSha256')!=digest(path) or provenance.get('builderSha256')!=digest(HERE/named):
        raise error(f'{spec.label} source or builder changed: run {spec.builder}')
    for name,sha in (provenance.get('imports') or {}).items():
        helper=HERE/Path(name).name
        if not helper.is_file() or digest(helper)!=sha:
            raise error(f'{region}: {helper.name}, which {spec.builder} imports, changed since the build: run {spec.builder}')
    from collision_sources import read_served_package
    from eloria.collision import CollisionMap, erode_for_footprint
    blob,grid,_=read_served_package(package/'collision.bin',cells)
    collision=CollisionMap.from_grid(grid)
    walk_codes=np.frombuffer(grid.codes,dtype=np.uint16).reshape(cells,cells)
    # The interior people stand on their posts: the server blocks the tile an NPC stands on for every walker, so
    # every reach below is walked with the posts closed (and a post judged as open ground with a reached ring).
    people=[(section['id'],person) for section in design['sections'] for person in section_npcs(reader,section)]
    posts={}
    for sid,person in people:
        where=f'{sid} person {person.get("name")!r}'
        tile=person.get('tile')
        if not (isinstance(tile,list) and len(tile)==2 and all(type(v) is int for v in tile)):
            raise error(f'{where}: tile {tile!r} is not [x, y]')
        if tuple(tile) in posts: raise error(f'{where}: shares a post with {posts[tuple(tile)]}')
        posts[tuple(tile)]=person.get('name')
    # Distinct entrance components are the shared-insides contract. Checking
    # reach with the actual server step rule also catches one-cell pinches.
    reaches=[]; portals=[]; nodes=[];spawns=[];objects=[];npc_rows=[];interactive_rows=[]
    used={(n['map'],n['id']) for n in pub.nodes}|{(i['map'],i['object']) for i in pub.interactives}
    reach_of={}
    exterior_posts={(p['map'],tuple(p['tile'])):p['name'] for p in [*getattr(pub,'new_people',[]),*getattr(pub,'rehomed',[])]}
    exterior_objects={(i['map'],tuple(i['tile'])):i['object'] for i in pub.interactives}
    def walk(start):
        reach={start};q=deque([start])
        while q:
            a,b=q.popleft()
            for dx,dy in FOUR:
                target=(a+dx,b+dy)
                if target not in reach and target not in posts and collision.can_step(a,b,*target,2):
                    reach.add(target);q.append(target)
        return reach
    for section in design['sections']:
        sid=section['id']; arrival=tuple(reader.primary_arrival(design,section))
        if not collision.walkable(*arrival) or arrival in posts: raise error(f'{sid}: arrival blocked')
        reach=walk(arrival)
        if any(reach&other for other in reaches): raise error(f'{spec.label} sections connect across blackspace')
        reaches.append(reach); reach_of[sid]=reach
        for door in reader.doors(section):
            e=door; exterior=e['map']; tag=f'{sid} door {door["index"]}'
            kind=door.get('kind','underground')
            if kind not in DOOR_KINDS: raise error(f'{tag}: kind {kind!r} is not one of {DOOR_KINDS}')
            records=ctx.bakes[exterior].doc['gameplay'].get('runtimePoints',[])
            if kind=='underground':
                matches=[r for r in records if r['id']==e['marker']]
                if len(matches)!=1 or list(matches[0]['serverTile'])!=e['tile'] or matches[0].get('role')!='underground_entrance':
                    raise error(f'{tag}: saved entrance marker and underground source disagree')
            else:
                # A building door has no scene marker: export_collision.py stamps entrance art for every
                # underground_entrance runtime point, and a building's door is painted on its facade.
                if any(r.get('objectId')==e['object'] for r in records):
                    raise error(f'{tag}: the {exterior} bake has a runtime point for building door {e["object"]}; '
                                'a building door has no marker')
                for key in ('label','exitLabel'):
                    if not door.get(key): raise error(f'{tag}: a building door needs a {key}')
                    fields.plain(door[key],f'{tag} {key}')
                if door.get('category') is not None:
                    import map_categories
                    try:
                        map_categories.check(door['category'],tag)
                    except ValueError as problem:
                        raise error(str(problem))
                frame=ctx.frames[exterior]
                px,_py,pz=door['position']
                painted=frame.tile(px,pz)
                if max(abs(painted[0]-e['tile'][0]),abs(painted[1]-e['tile'][1]))>DOOR_REACH:
                    raise error(f'{tag}: its painted point {list(painted)} is more than {DOOR_REACH} tiles from its '
                                f'tile {e["tile"]}')
            x,y=e['tile']; rx,ry=e['returnTile']
            if (x,y)==(rx,ry): raise error(f'{tag}: the return tile is the door\'s own tile')
            for px,py in [(x,y),(rx,ry)]:
                cx,cz=ctx.frames[exterior].continent(px,py)
                if not ownership.contains(cx,cz,ctx.packages[exterior]['polygon']):
                    raise error(f'{tag}: entrance/return lies outside its territory')
                if kind=='building' and not ctx.packages[exterior]['grid'].walkable(px,py):
                    raise error(f'{tag}: entrance/return {[px,py]} is not walkable on the {exterior} served grid')
                if not pub.reached[exterior][py,px]: raise error(f'{tag}: entrance/return is unreachable')
                for dx,dy in FOUR:
                    if not ctx.packages[exterior]['grid'].walkable(px+dx,py+dy): raise error(f'{tag}: entrance/return has no clear approach')
                if kind=='building':
                    for what,table in (('an NPC post',exterior_posts),('an interactive\'s tile',exterior_objects)):
                        if (exterior,(px,py)) in table:
                            raise error(f'{tag}: entrance/return {[px,py]} is {what} ({table[(exterior,(px,py))]})')
            if (exterior,(x,y)) in door_tiles: raise error(f'{tag}: door tile {[x,y]} is already {door_tiles[(exterior,(x,y))]}\'s')
            door_tiles[(exterior,(x,y))]=f'{region} door {e["object"]}'
            if (exterior,e['object']) in used: raise error(f'{spec.label} entrance object id is already used')
            if not collision.walkable(*door['arrival']) or tuple(door['arrival']) not in reach:
                raise error(f'{tag}: arrival blocked or not on the section\'s floor')
            if tuple(door['exit']) not in reach: raise error(f'{tag}: exit unreachable')
            portals.extend([[exterior,e['object'],x,y,region,*door['arrival']],
                            [region,e['object'],*door['exit'],exterior,rx,ry]])
            if kind=='underground':
                outside=f'Beyond it lies {section["name"]}. {section["danger"]}.'
                inside=f'Beyond it lies {exterior.replace("_"," ").title()}.'
            else:
                outside=sentence(door['label'])+f' {sentence(section["danger"])}'
                inside=sentence(door['exitLabel'])
            objects.extend([f'{exterior} | {e["object"]} | {x} | {y} | portal | maps.txt | {outside}',
                            f'{region} | {e["object"]} | {door["exit"][0]} | {door["exit"][1]} | portal | maps.txt | {inside}'])
    sections={s['id']:s for s in design['sections']}
    for passage in reader.passages(design):
        for end in passage['ends']:
            other=passage['ends'][1-end['end']]; tag=f'passage {passage["index"]} end {end["end"]} ({end["section"]})'
            reach=reach_of[end['section']]
            if tuple(end['tile']) not in reach: raise error(f'{tag}: its tile {end["tile"]} is not reached inside its section')
            if not collision.walkable(*end['arrival']) or tuple(end['arrival']) not in reach:
                raise error(f'{tag}: its arrival {end["arrival"]} is not reached inside its section')
            if (region,end['object']) in used: raise error(f'{tag}: object id {end["object"]} is already used')
            target=sections[other['section']]
            portals.append([region,end['object'],*end['tile'],region,*other['arrival']])
            text=(sentence(fields.plain(end['label'],f'{tag} label')) if end.get('label') else
                  f'A way leads on into {target["name"]}. {target["danger"]}.')
            objects.append(f'{region} | {end["object"]} | {end["tile"][0]} | {end["tile"][1]} | portal | maps.txt | {text}')
    # what no person may stand on and no interactive may share: every arrival, exit and passage end
    ways={}
    for section in design['sections']:
        for door in reader.doors(section):
            ways[tuple(door['arrival'])]=f'door {door["object"]}\'s arrival'
            ways[tuple(door['exit'])]=f'door {door["object"]}\'s exit'
        for end in reader.passage_ends(design,section['id']):
            ways[tuple(end['tile'])]=f'passage end {end["object"]}'
            ways[tuple(end['arrival'])]=f'passage end {end["object"]}\'s arrival'
    ids=set()
    spawn_tiles=set()
    for section in design['sections']:
        sid=section['id']; reach=reach_of[sid]
        safe=[tuple(a) for _,_,a in reader.arrivals(design,section)]
        for oid,res,nx,ny in section['nodes']:
            if oid in ids: raise error(f'duplicate {spec.label} object id')
            ids.add(oid)
            if res not in ctx.server.base_resources: raise error(f'unknown {spec.label} resource {res}')
            if walk_codes[ny,nx] or not any((nx+dx,ny+dy) in reach for dx,dy in FOUR):
                raise error(f'{sid}: node {oid} has no harvest approach or its body is open')
            nodes.append(f'node | {region} | {oid} | {nx} | {ny} | {res}')
        for creature,sx,sy,leash in section['spawns']:
            definition=ctx.server.creatures.get(creature)
            if definition is None or definition.raw.get('model')!='final': raise error(f'{creature}: no reviewed model')
            fitted=erode_for_footprint(collision,definition.footprint)
            if not fitted.walkable(sx,sy) or (sx,sy) not in reach: raise error(f'{creature}: footprint does not fit')
            if not 1<=leash<=8 or any(max(abs(sx-ax),abs(sy-ay))<leash+20 for ax,ay in safe):
                raise error(f'{creature}: encounter too close to a safe entry (an arrival)')
            spawns.append(f'spawn | {region} | {creature} | {sx} | {sy} | leash:{leash}')
            spawn_tiles.add((sx,sy))
    # interior interactives: a desk, a board, an anvil; the furniture may close the tile itself
    taken={}
    for section in design['sections']:
        sid=section['id']; reach=reach_of[sid]
        for item in section_interactives(reader,section):
            oid=item['object']; tag=f'{sid} interactive {oid}'
            x,y=item['tile']
            role=item.get('role')
            if role not in INTERACTIVE_ROLES: raise error(f'{tag}: role {role!r} is not one of {INTERACTIVE_ROLES}')
            if (x,y) in ways or (x,y) in posts or (x,y) in taken:
                raise error(f'{tag}: stands on {ways.get((x,y)) or posts.get((x,y)) or taken[(x,y)]}')
            if not any((x+dx,y+dy) in reach for dx in range(-INTERACTIVE_REACH,INTERACTIVE_REACH+1)
                       for dy in range(-INTERACTIVE_REACH,INTERACTIVE_REACH+1)):
                raise error(f'{tag}: no reached floor within {INTERACTIVE_REACH} tiles')
            taken[(x,y)]=f'interactive {oid}'
            target=fields.plain(item.get('target',INTERACTIVE_TARGETS[role]),f'{tag} target')
            text=fields.plain(item['text'],f'{tag} text')
            objects.append(f'{region} | {oid} | {x} | {y} | {role} | {target} | {text}')
            interactive_rows.append(oid)
    # interior people: open posts with a reached ring, clear of every way, object and spawn
    known=set(getattr(getattr(ctx,'server',None),'npc_lines',{}) or {})
    known|={p['name'].casefold() for p in [*getattr(pub,'new_people',[]),*getattr(pub,'rehomed',[])]}
    seen=getattr(pub,'interior_people',None)
    if seen is None: seen=pub.interior_people={}
    for sid,person in people:
        reach=reach_of[sid]
        name=fields.plain(person.get('name',''),f'{sid} person name')
        where=f'{sid} person {name}'
        if name.casefold() in known: raise error(f'{where}: {name} is already in npcs.txt; an interior person needs a new name')
        if name.casefold() in seen: raise error(f'{where}: {name} also stands in {seen[name.casefold()]}')
        seen[name.casefold()]=region
        x,y=person['tile']
        if not collision.walkable(x,y): raise error(f'{where}: post {[x,y]} is not open ground')
        unreached=[[x+dx,y+dy] for dx,dy in EIGHT if (x+dx,y+dy) not in reach]
        if unreached: raise error(f'{where}: post {[x,y]} has unreached neighbours {unreached}')
        clash=ways.get((x,y)) or taken.get((x,y)) or ('a spawn' if (x,y) in spawn_tiles else None)
        if clash: raise error(f'{where}: stands on {clash}')
        actor=person.get('actorType')
        if type(actor) is not int or actor not in NPC_ACTOR_TYPES:
            raise error(f'{where}: actorType {actor!r} is not a body 300-377')
        facing=person.get('facing','') or ''
        if facing and facing not in COMPASS: raise error(f'{where}: facing {facing!r} is not one of {COMPASS}')
        if person.get('mapCategory') not in (None,''):
            import map_categories
            try:
                map_categories.check(person['mapCategory'],where)
            except ValueError as problem:
                raise error(str(problem))
        role=fields.plain(person.get('role',''),f'{where} role')
        greeting=fields.plain(person.get('greeting',''),f'{where} greeting')
        occupation=fields.occupation(person.get('occupation'),name,where)
        npc_rows.append(f'npc | {name} | {region} | {x} | {y} | {role} | {fields.portrait(actor,occupation,facing)} | {greeting}')
    covered=set().union(*reaches)
    if len(covered)+len(posts)!=int(np.count_nonzero(walk_codes)): raise error(f'{spec.label} has a stranded walkable pocket')
    def summary(s):
        # the old keys, then (pass 2) every way in: doors [object, map, arrival, exit], passage ends [object, arrival]
        return {'id':s['id'],'name':s['name'],'danger':s['danger'],'arrival':reader.primary_arrival(design,s),
                'exit':reader.primary_exit(design,s),
                **({'doors':[[d['object'],d['map'],d['arrival'],d['exit']] for d in reader.doors(s)]} if 'entrances' in s else {}),
                **({'passageEnds':[[e['object'],e['arrival'],e['tile']] for e in reader.passage_ends(design,s['id'])]}
                   if reader.passage_ends(design,s['id']) else {})}
    metadata={'name':info['name'],'alias':info['alias'],'serverOrigin':[0,cells],'serverCells':[cells,cells],
              'arrival':reader.primary_arrival(design,design['sections'][0]),'servedGridSha256':digest(package/'served-grid.escg.gz'),
              'collisionSha256':digest(package/'collision.bin'),'sourceSha256':digest(path),
              'manifestSha256':digest(package/'world.json'),'sections':[summary(s) for s in design['sections']]}
    if spec.kind!='underground':
        metadata['kind']=spec.kind
    ctx.packages[region]={'manifest':doc,'servedBytes':blob,'servedGridSha256':metadata['servedGridSha256'],
                          'collisionSha256':metadata['collisionSha256']}
    rows={'nodes':len(nodes),'spawns':len(spawns),'interactives':len(objects)}
    if spec.kind!='underground':
        rows['npcs']=len(npc_rows)
    interior=SimpleNamespace(region=region,kind=spec.kind,spec=spec,metadata=metadata,portals=portals,design=design,
                             rows=rows,walkable=int(np.count_nonzero(walk_codes)))
    def append(name,lines,always=spec.kind=='underground'):
        # the caves' four tables take their block as they always have, empty or not; any other table only with rows
        if lines or always:
            pub.files[name]+=('\r\n'+spec.banner+'\r\n'+'\r\n'.join(lines)+'\r\n').encode()
    append('maps.txt',[f'map | {region} | {info["name"]} | maps/nymara/{region}.elm | {info["alias"]}',
                       *['portal | '+' | '.join(map(str,p)) for p in portals]])
    append('spawns.txt',spawns);append('harvesting.txt',nodes);append('interactives.txt',objects)
    append('npcs.txt',npc_rows,always=False)
    return interior


def manifest_entries(pub):
    """client_content_manifest.json maps[] entries of every interior."""
    entries=[]
    for u in getattr(pub,'interiors',None) or ([pub.underground] if getattr(pub,'underground',None) else []):
        m=u.metadata;cells=m['serverCells'][0]
        entries.append({'id':u.region,'server_cells':cells,'arrival':m['arrival'],'server_origin':m['serverOrigin'],
                        'coordinateTransform':{'metresPerTile':1.,'serverOrigin':m['serverOrigin'],'serverCells':m['serverCells'],
                                               'origin':[0,0,0],'walkingHeight':0.,'invertServerY':True,'serverStorageVersion':1,'serverTileMin':[0,0]},
                        'serverCells':m['serverCells'],'serverStorageVersion':1,'serverTileMin':[0,0],'portals':[]})
    return entries


def manifest_keys(pub):
    """The manifest block's interior keys, in order: interiorMaps, then each kind's portal rows and row counts."""
    interiors=getattr(pub,'interiors',None) or []
    if not interiors:
        return {}
    block={'interiorMaps':{u.region:u.metadata for u in interiors}}
    for spec in SOURCES:
        mine=[u for u in interiors if u.kind==spec.kind]
        if mine:
            block[spec.portals]=[row for u in mine for row in u.portals]
            block[spec.rows]=mine[0].rows if len(mine)==1 else {u.region:u.rows for u in mine}
    return block
