"""Generate audited live-client fixtures from a completed paired publication.

No server or database is started. Every emitted movement leg is tested with
the server's real World.find_path, final ELMs, storage bodies and configured
NPC occupancy. Moving creatures remain a live-run concern. Outputs are QA
artifacts only; map configuration and canonical fixtures are never changed.
"""
from __future__ import annotations

import argparse
import ast
from array import array
from collections import defaultdict, deque
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import textwrap

from sync_geographic_family import CLIENT, family, resolve, LOD_CONTENT
from sync_package_content import digest_for
import continent_approaches as approaches
from legacy_content import read_base_only


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def served_instance_exits(client, server, publication, track):
    """Join actual served definitions to independently certified authored exits."""
    import publish_diagonal_continent as publisher
    if type(publication.get('instanceExitSchema')) is not int or publication['instanceExitSchema'] != 2:
        raise AuditError('Static instance proof requires authored instance exit schema 2')
    specs = publication['regions']
    try:
        sources = publisher.certified_instance_exit_sources(client, specs)
        entries = publisher.validate_instance_exit_table(specs, sources, client=client, require_authored=True)
        found = {}
        for relative in sorted({source['path'] for source in sources.values()}):
            path = server / relative
            track(path)
            for identity, actual in publisher.instance_exit_records(relative, path.read_text(encoding='utf-8'), specs).items():
                if identity in found or identity not in entries:
                    raise ValueError(f'{identity}: duplicate or unexpected served instance exit')
                source = sources[identity]
                if ({k: actual[k] for k in ('path', 'spawnName', 'fields', 'map', 'line')} !=
                        {k: source[k] for k in ('path', 'spawnName', 'fields', 'map', 'line')} or
                        actual['originalTile'] != entries[identity]['tile']):
                    raise ValueError(f'{identity}: actual served definition differs from certified instance exit')
                found[identity] = entries[identity]
        if set(found) != set(entries):
            raise ValueError('Actual served instance exit inventory is incomplete')
    except (ValueError, KeyError, OSError) as exc:
        raise AuditError(str(exc)) from exc
    baseline = client / 'eloria-assets/maps/nymara-regions/_continent/legacy-server-profile'
    track(baseline / 'snapshot.json')
    for source in sources.values():
        track(baseline / source['path'])
    for entry in entries.values():
        track(client / entry['authoredBinding']['source']['amendmentReport']['path'])
    track(Path(publisher.__file__))
    track(Path(publisher.shared.__file__))
    return found


# The live harness gameplay camera: rendered_landscape_walk.gd applies pitch -60,
# the route yaw and distance and aims 1.2 m above the actor; run_live_continent
# launches the client at this resolution with the main scene's 50 degree FOV.
HARNESS_VIEWPORT=(1440,900)
HARNESS_FOV_DEGREES=50.0
HARNESS_PITCH_DEGREES=-60.0
HARNESS_AIM_HEIGHT=1.2
CLICK_CAMERA_DISTANCE=32
# A clicked neighbour tile must project this far inside the frame: the offline
# surface model (the client's own collision export, 0.29 m steps) differs from
# the rendered surface by up to half a metre, about 15 px at this zoom.
CLICK_VISIBLE_MARGIN_PX=60
ROADLESS_LOCAL_CANDIDATES=32


def harness_screen_position(focus,yaw_degrees,distance,point):
    """Where the live harness camera projects `point` (Godot metres) with the actor at `focus`.

    Mirrors IsometricCameraController._update_camera and Camera3D.unproject_position
    (vertical field of view, KEEP_HEIGHT). None when the point is behind the camera.
    """
    yaw=math.radians(yaw_degrees);pitch=math.radians(HARNESS_PITCH_DEGREES)
    camera=(focus[0]+math.sin(yaw)*math.cos(pitch)*distance,focus[1]-math.sin(pitch)*distance,
            focus[2]+math.cos(yaw)*math.cos(pitch)*distance)
    forward=(focus[0]-camera[0],focus[1]+HARNESS_AIM_HEIGHT-camera[1],focus[2]-camera[2])
    length=math.sqrt(sum(v*v for v in forward))
    z_axis=tuple(-v/length for v in forward)
    sideways=math.hypot(z_axis[2],z_axis[0])
    x_axis=(z_axis[2]/sideways,0.0,-z_axis[0]/sideways)
    y_axis=(z_axis[1]*x_axis[2]-z_axis[2]*x_axis[1],z_axis[2]*x_axis[0]-z_axis[0]*x_axis[2],
            z_axis[0]*x_axis[1]-z_axis[1]*x_axis[0])
    local=tuple(point[i]-camera[i] for i in range(3))
    along=lambda axis:sum(local[i]*axis[i] for i in range(3))
    depth=-along(z_axis)
    if depth<=1e-6:return None
    half=math.tan(math.radians(HARNESS_FOV_DEGREES)/2)
    width,height=HARNESS_VIEWPORT
    x=along(x_axis)/depth/(half*width/height);y=along(y_axis)/depth/half
    return ((x+1)/2*width,(1-y)/2*height)


def visible_margin(screen):
    """Pixels between a projected point and the nearest viewport edge; negative outside."""
    if screen is None:return -math.inf
    width,height=HARNESS_VIEWPORT
    return min(screen[0],width-screen[0],screen[1],height-screen[1])


def finite_span_union(lines):
    """Canonical union of cardinal finite spans, retaining actual gaps."""
    grouped=defaultdict(list)
    for line in lines:
        if len(line)!=2 or any(len(point)!=2 or not all(math.isfinite(float(v)) for v in point) for point in line):
            raise AuditError('Invalid finite preload edge')
        a,b=line
        if math.dist(a,b)<1e-7:raise AuditError('Zero-length preload edge')
        axis=1 if abs(a[0]-b[0])<1e-6 else 0
        if abs(a[1-axis]-b[1-axis])>=1e-6:raise AuditError('Non-cardinal preload edge')
        grouped[(axis,round(a[1-axis],6))].append(sorted((round(a[axis],6),round(b[axis],6))))
    result=[]
    for (axis,fixed),spans in sorted(grouped.items()):
        merged=[]
        for low,high in sorted(spans):
            if merged and low<=merged[-1][1]+1e-6:merged[-1][1]=max(merged[-1][1],high)
            else:merged.append([low,high])
        result.extend([axis,fixed,low,high] for low,high in merged)
    return result


def owned_adjacencies(geography, bounds):
    """Derive every physical shared edge from polygons, not route metadata."""
    import numpy as np
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maps/nymara-regions/_continent'))
    from audit_continent import ownership_raster
    polygons={name:spec['ownershipPolygon'] for name,spec in geography['regions'].items()}
    names=list(polygons);cell=float(geography['ownershipRasterMetres'])
    if not math.isfinite(cell) or cell<=0:raise AuditError('Invalid ownership lattice spacing')
    try:owner=ownership_raster(polygons,bounds,cell)
    except ValueError as error:raise AuditError(str(error)) from error
    result=defaultdict(list);x0,z0,_,_=bounds
    for axis in (0,1):
        a,b=(owner[:,:-1],owner[:,1:]) if axis==0 else (owner[:-1,:],owner[1:,:])
        for row,column in zip(*np.nonzero(a!=b)):
            pair=tuple(sorted((names[a[row,column]],names[b[row,column]])))
            x=x0+(int(column)+(axis==0))*cell;z=z0+(int(row)+(axis==1))*cell
            result[pair].append([[x,z],[x+(axis==1)*cell,z+(axis==0)*cell]])
    return result


def travel_route(connections, source, destination):
    """Shortest declared itinerary; ferry legs remain explicit interactions."""
    queue=[(source,[])];visited={source}
    for current,route in queue:
        if current==destination:return route
        for link in connections:
            for a,b in (link['ends'],link['ends'][::-1]):
                if a['region']!=current or b['region'] in visited:continue
                visited.add(b['region']);queue.append((b['region'],route+[(link,a,b)]))
    raise AuditError(f'{source} -> {destination}: no declared continent travel route')


def runtime(server):
    """Load the paired production modules without constructing a live World.

    The proof is of the legacy publication, so the loaders read the base content tables only, never the continent-v2
    overlay (legacy_content.read_base_only); this tool, publish_interior_staff and their tests all load through here.
    """
    server = Path(server).resolve()
    read_base_only(server)
    sys.path[:0] = [str(server/'tools'), str(server)]
    previous = Path.cwd()
    try:
        os.chdir(server)  # Module-level catalogs use the production profile.
        modules = {name: importlib.import_module('eloria.'+name) for name in
                   ('world', 'collision', 'maps', 'settings', 'interactives', 'harvesting', 'spawns')}
    finally:
        os.chdir(previous)
    if not Path(modules['world'].__file__).resolve().is_relative_to(server):
        raise ValueError('Another server checkout is already imported in this Python process')
    return modules


class AuditError(ValueError):
    pass


class AccessFlood:
    """Single-arrival reachability using the production staged step graph.

    NPC footprints block target cells exactly as World.find_path does. Auto
    doors are terminal: walking through one cannot prove access beyond it.
    Distances follow the deterministic fewest-step flood path, not weighted A*.
    """
    def __init__(self, world, region, arrival, *, occupied=(), terminals=(), arrival_departure=False):
        self.world, self.region = world, region
        self.collision = world.collision_for(region)
        if self.collision is None:raise AuditError(f'{region}: inventory requires an actual ELM')
        self.width, self.height = self.collision.width, self.collision.height
        self.occupied, self.terminals = set(occupied), set(terminals)
        self.steps = array('i', [-1])*(self.width*self.height)
        self.metres = array('f', [-1])*(self.width*self.height)
        self.points = []
        arrival = tuple(arrival)
        # change_map does not call check_portal: only a subsequent walking
        # step can activate an automatic exit. Permit this one initial departure,
        # never expansion through another terminal encountered along the route.
        self.departure = arrival if arrival_departure else None
        if not world.is_walkable(region,*arrival) or arrival in self.occupied:
            raise AuditError(f'{region}: primary arrival {arrival} is unsupported or occupied')
        mask = world.search_mask(self.collision)
        module = type(world).find_path.__globals__
        directions, legal = module['DIRS'], module['LEGAL_STEPS']
        queue=deque([arrival]);index=arrival[1]*self.width+arrival[0]
        self.steps[index]=0;self.metres[index]=0
        while queue:
            current=queue.popleft();x,y=current;index=y*self.width+x
            if current not in self.terminals or current == self.departure:self.points.append(current)
            else:continue
            for dx,dy in (legal[mask[0][index]] if mask is not None else directions):
                point=(x+dx,y+dy)
                if not 0<=point[0]<self.width or not 0<=point[1]<self.height or point in self.occupied:continue
                at=point[1]*self.width+point[0]
                if self.steps[at]>=0:continue
                if mask is None:
                    if not world.can_walk_step(region,current,point):continue
                    if dx and dy and (not world.can_walk_step(region,current,(x+dx,y))
                                      or not world.can_walk_step(region,current,(x,y+dy))):continue
                self.steps[at]=self.steps[index]+1
                self.metres[at]=self.metres[index]+math.hypot(dx,dy)
                queue.append(point)

    def reachable(self, point):
        x,y=point
        return (0<=x<self.width and 0<=y<self.height and self.steps[y*self.width+x]>=0
                and (tuple(point) not in self.terminals or tuple(point)==self.departure))

    def near(self, target, radius):
        candidates=[(target[0]+x,target[1]+y) for x in range(-radius,radius+1)
                    for y in range(-radius,radius+1)]
        candidates=[p for p in candidates if self.reachable(p)]
        return min(candidates,key=lambda p:(max(abs(p[i]-target[i]) for i in (0,1)),
                   self.steps[p[1]*self.width+p[0]],p),default=None)

    def describe(self, target, point):
        if point is None:return None
        at=point[1]*self.width+point[0]
        return {'tile':list(point),'targetDistanceTiles':max(abs(point[i]-target[i]) for i in (0,1)),
                'targetDistanceMetres':round(math.dist(target,point),3),
                'walkingSteps':self.steps[at],'walkingMetres':round(self.metres[at],3)}

    def nearest(self, target):
        return min(self.points,key=lambda p:(math.dist(target,p),p),default=None)


class WalkAudit:
    def __init__(self, world, portals, *, move_seconds=.6, max_leg=64):
        self.world = world
        self.portals = portals
        self.move_seconds = move_seconds
        self.max_leg = max_leg
        self.automatic = defaultdict(set)
        for portal in portals:
            if portal.object_id is None:
                self.automatic[portal.source].add((portal.x, portal.y))
        self.legs = []
        self.requests = []

    def one_request(self, region, start, target, label, *, allowed=()):
        """Audit one runtime MOVE_TO, never inserting continuation waypoints.

        For a truncated result only, a private diagnostic copy of the exact
        production method removes its final [:512] slice to measure the full
        requested path. The actual request still fails; no World is patched.
        """
        start, target = tuple(start), tuple(target)
        if not self.standing(region, start) or not self.standing(region, target):
            raise AuditError(f'{region}: unsupported or occupied direct request {start} -> {target}')
        actual = self.world.find_path(region, start, target, self.world.walk_blocked(region, target))
        full = actual
        diagnostic = False
        if len(actual) == 512 and actual[-1] != target:
            if not self.world.collision_for(region):
                raise AuditError(f'{region}: direct-request audit requires an actual ELM')
            method = type(self.world).find_path
            tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
            matches = [node for node in ast.walk(tree) if isinstance(node, ast.Return)
                       and isinstance(node.value, ast.Subscript)
                       and isinstance(node.value.slice, ast.Slice)
                       and isinstance(node.value.slice.upper, ast.Constant)
                       and node.value.slice.upper.value == 512]
            if len(matches) != 1:
                raise AuditError('Production path result slice changed; update diagnostic measurement explicitly')
            matches[0].value = matches[0].value.value
            namespace = dict(method.__globals__)
            exec(compile(ast.fix_missing_locations(tree), '<diagnostic-only untruncated World.find_path>', 'exec'), namespace)
            full = namespace[method.__name__](self.world, region, start, target, self.occupied(region))
            if actual != full[:512]:
                raise AuditError('Diagnostic path differs from the actual production prefix')
            diagnostic = True
        unintended = sorted(set(full) & (self.automatic[region]-set(allowed)))
        reached = start == target or bool(actual and actual[-1] == target)
        item = {'label':label,'map':region,'from':list(start),'to':list(target),
                'requestedSteps':len(full),'returnedSteps':len(actual),'reached':reached,
                'exceeds512':len(full)>512,'unintendedPortals':[list(p) for p in unintended],
                'diagnosticUncappedMeasurement':diagnostic,'syntheticBlockers':False,
                'waypointsAdded':0,'pathSha256':hashlib.sha256(json.dumps(full).encode()).hexdigest(),
                'passes':reached and not unintended}
        self.requests.append(item)
        return item

    def renewed_intent(self, region, start, target, *, allowed=(), renew_at=448, maximum_renewals=16):
        """Simulate runtime same-target renewal, not user/fixture waypoints."""
        if not 1<=renew_at<512 or not 0<=maximum_renewals<=64:
            raise AuditError('Unsupported runtime road renewal limits')
        current,target=tuple(start),tuple(target)
        segments=[];unintended=set();total=0
        for request in range(maximum_renewals+1):
            if current==target:
                return {'passes':True,'requestsIssued':len(segments),'renewals':max(0,len(segments)-1),
                        'executedSteps':total,'segments':segments,'userClicks':1,'fixtureWaypoints':0}
            actual=self.world.find_path(region,current,target,self.world.walk_blocked(region,target))
            executed=actual[:renew_at]
            unintended.update(set(executed)&(self.automatic[region]-set(allowed)))
            segment={'from':list(current),'requestedTarget':list(target),'serverReturnedSteps':len(actual),
                     'executedSteps':len(executed),'pathSha256':hashlib.sha256(json.dumps(executed).encode()).hexdigest()}
            segments.append(segment);total+=len(executed)
            if unintended or not executed:
                return {'passes':False,'reason':'unintended automatic portal' if unintended else 'no server path',
                        'unintendedPortals':[list(p) for p in sorted(unintended)],'segments':segments,
                        'userClicks':1,'fixtureWaypoints':0}
            current=executed[-1]
            if current!=target and len(actual)<renew_at:
                return {'passes':False,'reason':'server stopped before renewal threshold or exact target',
                        'stoppedAt':list(current),'segments':segments,'userClicks':1,'fixtureWaypoints':0}
        if current==target:
            return {'passes':True,'requestsIssued':len(segments),'renewals':max(0,len(segments)-1),
                    'executedSteps':total,'segments':segments,'userClicks':1,'fixtureWaypoints':0}
        return {'passes':False,'reason':'runtime renewal budget exhausted','segments':segments,
                'userClicks':1,'fixtureWaypoints':0}

    def occupied(self, region):
        return self.world.blocking_tiles(region)

    def standing(self, region, point):
        return self.world.is_walkable(region, *point) and point not in self.occupied(region)

    def arrival_departure(self, region, point):
        """A literal, unoccupied arrival with a real non-portal first step."""
        point=tuple(point)
        if not self.world.collision_for(region) or not self.standing(region,point):return None
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            target=(point[0]+dx,point[1]+dy)
            if target in self.automatic[region] or not self.standing(region,target):continue
            try:
                if self.exact_path(region,point,target)==[target]:return target
            except AuditError:pass
        return None

    def exact_path(self, region, start, target, *, allowed=(), planning=False):
        start, target = tuple(start), tuple(target)
        if not self.standing(region, start) or not self.standing(region, target):
            raise AuditError(f'{region}: unsupported or occupied standing tile {start} -> {target}')
        # What the server's own walk refuses: bodies and every way off the map but the target.
        blocked = self.world.walk_blocked(region, target)
        if planning:
            blocked = blocked | (self.automatic[region]-set(allowed)-{start})
        path = self.world.find_path(region, start, target, blocked)
        if start == target:
            return []
        if not path:
            raise AuditError(f'{region}: no path {start} -> {target}')
        if not planning and path[-1] != target:
            raise AuditError(f'{region}: request ends at {path[-1]}, not {target} (512-step limit or occupancy)')
        unexpected = set(path) & (self.automatic[region]-set(allowed))
        if not planning and unexpected:
            raise AuditError(f'{region}: actual path enters unintended portal {sorted(unexpected)}')
        return path

    def movement(self, region, start, target, label, *, allowed=()):
        """Plan around entrances, then prove each unmodified actual request.

        Extra forbidden entrances are used only to propose waypoint positions.
        They are never supplied to the final path proof. If a long request
        cuts a corner through a doorway, progressively shorter real requests
        follow the clear street. Every request stays far below 512 steps.
        """
        start, target = tuple(start), tuple(target)
        current, output = start, []
        for _ in range(200):
            if current == target:
                return output
            guide = self.exact_path(region, current, target, allowed=allowed, planning=True)
            chosen = None
            for end in range(min(len(guide), self.max_leg), 0, -1):
                waypoint = guide[end-1]
                try:
                    path = self.exact_path(region, current, waypoint, allowed=allowed)
                except AuditError:
                    continue
                if len(path) <= self.max_leg:
                    chosen = waypoint, path
                    break
            if chosen is None:
                raise AuditError(f'{region}: no real movement request follows the clear approach at {current}')
            waypoint, path = chosen
            seconds = max(20, math.ceil(len(path)*self.move_seconds*1.35+12))
            output.append({'tile': list(waypoint), 'label': label if waypoint == target else label+' approach',
                           'walkTimeout': seconds})
            self.legs.append({'map': region, 'from': list(current), 'to': list(waypoint),
                              'steps': len(path), 'metres': round(sum(math.dist(a,b) for a,b in zip([current]+path,path)), 3),
                              'pathSha256': hashlib.sha256(json.dumps(path).encode()).hexdigest(),
                              'runtimeNpcTiles': len(self.occupied(region)), 'syntheticBlockers': False})
            current = waypoint
        raise AuditError(f'{region}: excessive waypoint count for {start} -> {target}')

    def approach(self, region, start, point, *, radius=3, minimum=2, forbidden=()):
        candidates = [(point[0]+x, point[1]+y) for x in range(-radius,radius+1)
                      for y in range(-radius,radius+1) if minimum <= max(abs(x),abs(y)) <= radius]
        candidates.sort(key=lambda p:(math.dist(start,p),math.dist(point,p),p))
        for target in candidates:
            if target in self.automatic[region] or target in forbidden or not self.standing(region,target):
                continue
            try:
                self.exact_path(region,start,target,planning=True)
                return target
            except AuditError:
                continue
        raise AuditError(f'{region}: no reachable standing approach within {radius} tiles of {point}')


class Generator:
    def __init__(self, client, server, data, *, max_leg=64, publication=None):
        self.client, self.server, self.data = Path(client).resolve(), Path(server).resolve(), Path(data).resolve()
        self.profile = self.server/'config/eloria'
        self.inputs = {}
        self.manifest = self.json_input(self.profile/'client_content_manifest.json')
        self.specs = self.manifest.get('continentGeography', {}).get('regions', {})
        if len(self.specs) != 12:
            raise AuditError('Final twelve-region geographic publication is not ready')
        geography_path=self.client/'eloria-assets/maps/nymara-regions/continent-geography.json'
        self.geography=self.json_input(geography_path)
        self.chunk_mode=self.geography.get('geometryMode')=='continent-chunks-v1'
        if self.chunk_mode:
            publication_path=Path(publication) if publication else geography_path.parent/'_continent/generated/publication.json'
            self.publication=self.json_input(publication_path)
            self.landscape_plan=self.json_input(geography_path.parent/self.geography['planSource'])
            ledger=self.manifest['continentGeography'];publication_hash=sha(publication_path)
            if (ledger.get('geometryMode')!='continent-chunks-v1' or ledger.get('geographySha256')!=publication_hash or
                self.manifest.get('diagonalContinent',{}).get('publicationSha256')!=publication_hash or
                ledger.get('masterSha256')!=self.publication['masterSha256'] or
                self.geography['verification']['masterSha256']!=self.publication['masterSha256']):
                raise AuditError('Server publication, continent master and authored geography provenance differ')
            for region,spec in self.specs.items():
                for key in ('serverOrigin','serverCells','translation'):
                    if spec[key]!=self.geography['regions'][region][key] or spec[key]!=self.publication['regions'][region][key]:
                        raise AuditError(f'{region}: canonical/publication/server {key} differs')
        elif self.manifest['continentGeography'].get('geographySha256')!=sha(geography_path):
            raise AuditError('Server publication does not match the current authored geography')
        graph = self.json_input(self.profile/'exterior_connections.json')
        if graph!=self.json_input(self.client/'godot-client/data/maps/exterior_connections.json'):
            raise AuditError('Client and server neighbor graphs differ')
        self.links = [link for link in graph['connections'] if not link.get('visualOnly')]
        self.visual_links = [link for link in graph['connections'] if link.get('visualOnly')]+graph.get('visualConnections', [])
        if (not self.chunk_mode and len(self.links) != 17) or not all(x.get('seamless') for x in self.links):
            raise AuditError('All seventeen reciprocal geographic links must be published first')
        mode='continent-chunks-v1' if self.chunk_mode else 'continent-owned-v1'
        if not all(e.get('frame',{}).get('geometryMode') == mode for x in self.links for e in x['ends']):
            raise AuditError('Live proof requires the final continent-owned geometry frames')
        if not self.chunk_mode and (len(self.visual_links) != 7 or not all(x.get('visualOnly') and not x.get('seamless') for x in self.visual_links)):
            raise AuditError('The seven final visual-only shoreline pairs must be published first')
        self.registry = self.json_input(self.client/'godot-client/data/maps/registry.json')['maps']
        stream_path=self.client/'godot-client/src/world/exterior_region_stream.gd'
        self.track(stream_path)
        stream=stream_path.read_text(encoding='utf-8')
        self.renew_at=int(re.search(r'const WALK_RENEW_COMMANDS := (\d+)',stream).group(1))
        self.maximum_renewals=int(re.search(r'const MAX_WALK_RENEWALS_PER_LEG := (\d+)',stream).group(1))
        self.track(self.client/'godot-client/src/state/actor_reducer.gd')
        self.members = family(self.client,self.server,self.specs)
        if len(self.members)!=65:raise AuditError(f'Expected all65 served family identities, found {len(self.members)}')
        self.track(Path(approaches.__file__))
        for link in self.links:
            # A border no road crosses has no authored approach to merge.
            if not link.get('road',True):continue
            for end in link['ends']:
                package=self.json_input(self.members[end['map']]['path'])
                end['frame']=self.approach_frame(end['frame'],package,link['id'])
        R = runtime(self.server)
        self.R = R
        for name in ('maps.txt','npcs.txt','interactives.txt','harvesting.txt','spawns.txt','server.txt'):
            self.track(self.profile/name)
        for name in ('world.py','collision.py','settings.py','npcs.py','maps.py','footprint.py','interactives.py','spawns.py','harvesting.py'):
            self.track(self.server/'eloria'/name)
        maps, portals = R['maps'].load_maps(self.profile/'maps.txt')
        settings = R['settings'].load_settings(str(self.profile/'server.txt'))
        self.interactives = R['interactives'].load_interactives(self.profile/'interactives.txt')
        _, self.resources = R['harvesting'].load_harvesting(self.profile/'harvesting.txt')
        self.spawns = R['spawns'].load_spawns(self.profile/'spawns.txt')
        world = R['world'].World.__new__(R['world'].World)
        world.maps, world.settings = maps, settings
        # The server's walk keeps off every way out of a map but the one it was
        # sent to (World.walk_blocked reads the portal table), so the model does too.
        world.portals = portals
        world.collision_maps = R['collision'].load_collision_maps(str(self.data), maps, settings.max_walk_height_change)
        for region in self.members:
            if region not in world.collision_maps:
                raise AuditError(f'Missing final ELM for {region}')
            path = self.data/maps[region].file
            if not path.exists():
                path = Path(str(path)+'.gz')
            self.track(path)
            self.track(self.members[region]['path'])
        for region, collision in world.collision_maps.items():
            world.collision_maps[region] = R['collision'].with_storage_collision(collision,
                ((i.x,i.y) for i in self.interactives.values() if i.map_id==region and i.role=='storage'))
        world.sessions,world.animals,world.animals_by_map = [],{},{}
        world.npcs,world.npc_roles,world.npc_dialogues = {},{},{}
        world._footprint_collision = {}
        world.load_configured_npcs(str(self.profile/'npcs.txt'))
        from eloria.spawn_groups import load_instance_control
        self.instance_entries=[]
        self.instance_exits=served_instance_exits(self.client,self.server,self.publication,self.track)
        consumed_exits=set()
        for path in sorted((self.profile/'instances').glob('*.def')):
            self.track(path);definition=load_instance_control(path)
            if not definition.is_gauntlet:continue
            keepers=[(npc,npc_map) for identity,(npc,npc_map,_,_) in world.npcs.items()
                     if npc.name.casefold()==definition.keeper.casefold() and world.npc_roles.get(identity)=='instance']
            if len(keepers)!=1:raise AuditError(f'{definition.name}: missing unique actual instance keeper')
            keeper,source=keepers[0]
            relative=path.relative_to(self.server).as_posix()
            matches=[(identity,entry) for identity,entry in self.instance_exits.items()
                     if entry['source']['path']==relative and entry['source']['spawnName']==definition.name]
            if len(matches)!=1:
                raise AuditError(f'{relative}: missing unique certified instance exit identity')
            identity,exit_entry=matches[0];consumed_exits.add(identity)
            if (definition.exit_map!=exit_entry['source']['map'] or
                    [definition.exit_x,definition.exit_y]!=exit_entry['tile']):
                raise AuditError(f'{identity}: runtime instance parser differs from served exit record')
            for destination in definition.copies:
                if destination in self.members:self.instance_entries.append({
                    'definition':definition.name,'exitIdentity':identity,'keeper':keeper.name,'source':source,'keeperTile':[keeper.x,keeper.y],
                    'destination':destination,'arrival':[definition.entry_x,definition.entry_y],
                    'exitMap':definition.exit_map,'exitTile':[definition.exit_x,definition.exit_y]})
        if consumed_exits!=set(self.instance_exits):
            raise AuditError('Certified instance exits are not all consumed by actual gauntlet definitions')
        self.track(self.server/'eloria/spawn_groups.py');self.track(self.server/'eloria/gauntlets.py')
        self.audit = WalkAudit(world,portals,move_seconds=settings.player_move_interval_ms/1000,max_leg=max_leg)
        self.portals,self.world = portals,world
        self.errors,self.lanes,self.coverage = [],[],{}
        if self.chunk_mode:self.graph_integrity()  # Fail before expensive route planning on an invalid topology.

    def track(self,path):
        value=sha(path)
        if str(path) in self.inputs and self.inputs[str(path)]!=value:
            raise AuditError(f'Input changed between reads: {path}')
        self.inputs[str(path)] = value

    def json_input(self,path):
        self.track(path)
        return read(path)

    def attempt(self,label,fn):
        try:
            return fn()
        except (AuditError,ValueError,KeyError) as error:
            self.errors.append({'route':label,'error':str(error)})
            return None

    def publication_integrity(self):
        entries={e['id']:e for e in self.manifest['maps']}
        packages={};identities=[]
        for identity,member in self.members.items():
            path=member['path'];entry=entries.get(identity,{})
            if path not in packages:
                data=self.json_input(path)
                glb=path.parent/data['asset']['glb']
                self.track(glb);self.track(path.parent/'collision.bin')
                for binary in path.parent.glob('world*.glb'):self.track(binary)
                actual=digest_for(path)
                if not actual:raise AuditError(f'{identity}: incomplete package')
                lod_path=path.with_name('world-lod2.json')
                if lod_path.is_file():
                    lod=self.json_input(lod_path);self.track(path.parent/lod['asset']['glb'])
                    for key in LOD_CONTENT:
                        if key in data and lod.get(key)!=data[key]:raise AuditError(f'{identity}: stale LOD {key}')
                    for key in ('serverCells','regionSpanMeters','mapBounds'):
                        if key in data['asset'] and lod['asset'].get(key)!=data['asset'][key]:raise AuditError(f'{identity}: stale LOD asset.{key}')
                    collision={k:v for k,v in data.get('collision',{}).items() if k!='nodeNames'}
                    lod_collision={k:v for k,v in lod.get('collision',{}).items() if k!='nodeNames'}
                    if collision!=lod_collision:raise AuditError(f'{identity}: stale LOD collision/guard metadata')
                    if 'continentGeography' in data:
                        expected=dict(data['continentGeography'],geometrySha256=sha(path.parent/lod['asset']['glb']),
                                      collisionGeometry=data['asset']['glb'])
                        if lod.get('continentGeography')!=expected:raise AuditError(f'{identity}: stale LOD geography or geometry hash')
                packages[path]={'packageSha256':actual,'manifest':data,'hasLodManifest':lod_path.is_file()}
            actual=packages[path]['packageSha256']
            if entry.get('packageSha256')!=actual:raise AuditError(f'{identity}: actual package bytes do not match the served digest')
            manifest=packages[path]['manifest']
            registry=self.registry[member['canonical']]
            for key,default in (('serverOrigin',[0,0]),('origin',[0,0,0]),('metresPerTile',1),('invertServerY',True)):
                if registry.get('coordinateTransform',{}).get(key,default)!=manifest.get('coordinateTransform',{}).get(key,default):
                    raise AuditError(f'{identity}: registry/manifest coordinateTransform.{key} differs')
            declared={(tuple(p['server_tile']),p['destination']) for p in entry.get('portals',[])}
            served={((p.x,p.y),p.destination) for p in self.portals if p.source==identity}
            if declared!=served:raise AuditError(f'{identity}: stale served-family portal metadata')
            collision=self.world.collision_for(identity)
            if entry.get('server_cells')!=collision.width or collision.width!=collision.height:
                raise AuditError(f'{identity}: served metadata/ELM dimensions differ')
            identities.append({'id':identity,'canonical':member['canonical'],'owner':member['owner'],
                               'packageSha256':actual,'portalCount':len(served),'cells':collision.width})
        return {'passed':True,'identityCount':len(identities),'uniquePackages':len(packages),'identities':identities,
                'lodManifestsChecked':sum(p['hasLodManifest'] for p in packages.values())}

    def graph_integrity(self):
        expected=defaultdict(list)
        chunk_mode=getattr(self,'chunk_mode',False)
        if chunk_mode:
            expected=owned_adjacencies(self.geography,self.landscape_plan['bounds'])
            declared=self.publication['connections'];walk={};roadless={};seen=set()
            for link in declared:
                pair=tuple(sorted(end['region'] for end in link['ends']))
                if (link['id'] in seen or len(pair)!=2 or pair[0]==pair[1] or
                    not set(pair)<=set(self.specs) or link['type'] not in ('walk','ferry')):
                    raise AuditError('Invalid or duplicate declared continent travel connection')
                seen.add(link['id'])
                if link['type']=='walk':
                    if pair not in expected:raise AuditError(f"{link['id']}: road joins territories without a physical boundary")
                    # A border no road crosses is opened wherever its ground meets; the
                    # geography's connections are its roads.
                    (walk if link.get('road',True) else roadless)[link['id']]=pair
                    for end in link['ends']:
                        # An open border publishes the lanes its ground offers, which a narrow
                        # pass can make fewer than a gate's seven; what a road contract needs is a
                        # way across, and halfWidthTiles still describes the authored threshold.
                        if not end.get('lanes') or end['frame'].get('halfWidthTiles')!=3:
                            raise AuditError(f"{link['id']}: published road contract has no way across")
            canonical={link['id']:tuple(sorted(e['region'] for e in link['ends'])) for link in self.geography['connections']}
            actual_walk={link['id']:tuple(sorted(e['map'] for e in link['ends'])) for link in self.links if link.get('road',True)}
            actual_roadless={link['id']:tuple(sorted(e['map'] for e in link['ends'])) for link in self.links if not link.get('road',True)}
            if walk!=canonical or walk!=actual_walk or len(actual_walk)+len(actual_roadless)!=len(self.links):
                raise AuditError('Runtime roads differ from canonical published crossings')
            if roadless!=actual_roadless:raise AuditError('Runtime roadless borders differ from the published ones')
            crossed=list(walk.values())+list(roadless.values())
            if len(set(crossed))!=len(crossed):raise AuditError('Multiple road records duplicate a physical adjacency')
            visual_pairs=[tuple(sorted(e['map'] for e in link['ends'])) for link in self.visual_links]
            if set(visual_pairs)!=set(expected)-set(crossed) or len(set(visual_pairs))!=len(visual_pairs):
                raise AuditError('Visual links do not cover the exact remaining owned boundaries')
            if not all(link.get('visualOnly') for link in self.visual_links):raise AuditError('Non-road physical connection lacks visualOnly')
            first=next(iter(self.specs))
            for region in self.specs:travel_route(declared,first,region)
        else:
            for segment in self.geography['boundaryHeightField']['segments']:
                expected[tuple(sorted(segment['regions']))].append([segment['start'],segment['end']])
        records=self.links+self.visual_links
        actual=[tuple(sorted(e['map'] for e in link['ends'])) for link in records]
        if len(actual)!=len(set(actual)) or set(actual)!=set(expected) or (not chunk_mode and len(actual)!=24):
            raise AuditError('Published links do not cover the exact physical adjacency pairs')
        if len({link['id'] for link in records})!=len(records):raise AuditError('Duplicate runtime physical connection identity')
        result=[]
        for link,pair in zip(records,actual):
            union=finite_span_union(expected[pair]);anchors=[]
            for end in link['ends']:
                spec=self.specs[end['map']];translation=spec['translation']
                if end.get('coordinateTransform',{}).get('serverOrigin')!=spec['serverOrigin']:
                    raise AuditError(f"{link['id']}: stale end origin")
                frame=end.get('frame',{})
                mode='continent-chunks-v1' if chunk_mode else 'continent-owned-v1'
                if frame.get('geometryMode')!=mode:raise AuditError(f"{link['id']}: wrong geometry frame mode")
                lines=[[[p[0]+translation[0],p[1]+translation[2]] for p in line] for line in end.get('preloadEdges',[])]
                if not lines or finite_span_union(lines)!=union:
                    raise AuditError(f"{link['id']}: finite preload edges differ from owned physical boundary on {end['map']}")
                anchors.append([frame['anchor'][i]+translation[i] for i in range(3)])
            if math.dist(*anchors)>.001:raise AuditError(f"{link['id']}: global frame anchors disagree")
            if chunk_mode and not link.get('visualOnly'):
                xz=(anchors[0][0],anchors[0][2])
                if not any(abs(xz[1-axis]-fixed)<.001 and low-.001<=xz[axis]<=high+.001 for axis,fixed,low,high in union):
                    raise AuditError(f"{link['id']}: road frame anchor is outside its physical boundary")
            result.append({'id':link['id'],'regions':list(pair),'visualOnly':bool(link.get('visualOnly')),
                           'globalFiniteSpanUnion':union})
        return {'passed':True,'roadPairs':len(self.links),'visualPairs':len(self.visual_links),'physicalPairs':len(result),'pairs':result,
                'boundarySource':'independent ownership polygon scan conversion' if chunk_mode else 'legacy boundaryHeightField',
                'ferryPairs':sum(c['type']=='ferry' for c in self.publication['connections']) if chunk_mode else 0}

    @staticmethod
    def approach_frame(frame,package,link_id):
        """Merge authored route metadata only after matching the published frame."""
        borders=[b for b in package.get('streamingBorders',[]) if b.get('id')==frame.get('id')]
        if len(borders)!=1:raise AuditError(f'{link_id}: missing unique authored streaming border')
        border=borders[0]
        for key in ('id','portal','destination','anchor','outward'):
            if key in frame and frame[key]!=border.get(key):
                raise AuditError(f'{link_id}: registry/manifest frame {key} differs')
        result=dict(frame)
        if 'approachCenterline' in border:
            if 'approachCenterline' in result and result['approachCenterline']!=border['approachCenterline']:
                raise AuditError(f'{link_id}: stale registry authored approach')
            result['approachCenterline']=border['approachCenterline']
            approaches.collar_length(result)  # Fail closed on malformed geometry contracts.
        elif 'approachCenterline' in result:
            raise AuditError(f'{link_id}: registry has an unauthored approach')
        return result

    def external_boundary(self,portal):
        """An external legacy map must supply a real, occupied return route."""
        region=portal.destination;arrival=(portal.destination_x,portal.destination_y)
        result={'scope':'Registered external map; outside the 65 authored GLB family identities',
                'map':region,'arrival':list(arrival),'passed':False}
        if region not in self.world.maps or self.world.collision_for(region) is None:
            return dict(result,reason='External destination lacks registered actual ELM')
        if hasattr(self,'data'):
            path=self.data/self.world.maps[region].file
            self.track(path if path.exists() else Path(str(path)+'.gz'))
        returns=[p for p in self.portals if p.source==region and p.destination==portal.source]
        if len(returns)!=1:return dict(result,reason='External boundary lacks a unique reciprocal departure')
        back=returns[0];target=(back.x,back.y);home=(back.destination_x,back.destination_y)
        try:
            if self.audit.arrival_departure(region,arrival) is None:
                raise AuditError('External arrival is blocked, occupied or cannot depart')
            route=self.audit.exact_path(region,arrival,target,allowed=[target])
            if self.audit.arrival_departure(portal.source,home) is None:
                raise AuditError('External reciprocal arrival cannot depart safely')
        except AuditError as error:return dict(result,reason=str(error))
        return dict(result,passed=True,returnTrigger=list(target),returnMap=back.destination,
                    returnArrival=list(home),path=[list(p) for p in route],steps=len(route),
                    occupancy='Actual configured NPC and storage bodies',
                    terminalPolicy='Only the intended reciprocal departure may activate')

    def family_portal_access(self):
        """Check real entries, including arrival on an automatic return tile.

        Interior components become reachable only through an already reachable
        incoming portal. A return cannot bootstrap its own disconnected room.
        """
        entries={e['id']:e for e in self.manifest['maps']}
        bound_exits=getattr(self,'instance_exits',{})
        definitions=getattr(self,'instance_entries',[])
        for definition in definitions:
            bound=bound_exits.get(definition.get('exitIdentity'))
            if (bound is None or bound['source']['map']!=definition['exitMap'] or
                    bound['tile']!=definition['exitTile']):
                raise AuditError('Actual instance definition lacks its exact certified exit binding')
        if {e['exitIdentity'] for e in definitions}!=set(bound_exits):
            raise AuditError('Certified exits and actual instance definitions differ')
        arrivals=[];checks=[];issues=[];departures={};reached={};entry_proof=[];hub_reached={}
        for region in self.members:
            primary=tuple(entries[region]['arrival'])
            incoming={(p.destination_x,p.destination_y) for p in self.portals if p.destination==region}
            incoming.update(tuple(p['arrival']) for p in getattr(self,'instance_entries',[]) if p['destination']==region)
            incoming.update(tuple(p['exitTile']) for p in getattr(self,'instance_entries',[]) if p['exitMap']==region)
            for point in sorted(incoming|{primary}):
                departure=self.audit.arrival_departure(region,point)
                valid=departure is not None;departures[(region,point)]=departure
                item={'map':region,'tile':list(point),'primary':point==primary,
                      'walkableUnoccupiedNoBounce':valid,'automaticReturnAtArrival':point in self.audit.automatic[region],
                      'departureStep':list(departure) if valid else None}
                arrivals.append(item)
                if not valid:issues.append({'reason':'blocked/occupied/bouncing family arrival',**item})
            collision=self.world.collision_for(region)
            reached[region]=bytearray(collision.width*collision.height)
        def reachable(region,point):
            collision=self.world.collision_for(region)
            return (region in reached and self.audit.standing(region,point) and
                    0<=point[0]<collision.width and 0<=point[1]<collision.height and
                    bool(reached[region][point[1]*collision.width+point[0]]))
        def source_access(portal):
            interactive=getattr(self,'interactives',{}).get((portal.source,portal.object_id))
            if interactive is not None and interactive.role=='waystone':
                # Production use_map_object calls gauntlets.use_waystone from
                # interaction range; leave() uses the active instance exit,
                # never walks the actor onto the decorative stone's tile.
                definitions=[e for e in getattr(self,'instance_entries',[]) if e['destination']==portal.source]
                if not definitions or (interactive.x,interactive.y)!=(portal.x,portal.y):
                    return False,{'activation':'instance waystone','reason':'waystone/instance source association differs'}
                radius=self.world.settings.portal_activation_distance
                options=[(interactive.x+dx,interactive.y+dy) for dx in range(-radius,radius+1)
                         for dy in range(-radius,radius+1) if reachable(portal.source,(interactive.x+dx,interactive.y+dy))
                         and (interactive.x+dx,interactive.y+dy) not in self.audit.automatic[portal.source]]
                point=min(options,key=lambda p:(math.dist(p,(interactive.x,interactive.y)),p),default=None)
                return point is not None,{'activation':'instance waystone from real interaction range',
                                          'sourceApproach':list(point) if point else None,'conditionalOnInstanceRun':True,
                                           'activeInstanceReturns':[{'identity':e['exitIdentity'],'map':e['exitMap'],
                                                                     'tile':e['exitTile']} for e in definitions]}
            return reachable(portal.source,(portal.x,portal.y)),{'activation':'walk to portal trigger'}
        expanded=set()
        def enter(region,point,provenance):
            if (region,point) in expanded or departures.get((region,point)) is None:return False
            expanded.add((region,point))
            if reachable(region,point) and point not in self.audit.automatic[region]:return False
            # Reached terminal tiles have not been expanded; an actual arrival
            # on one must still prove the legal departure into its own room.
            flood=AccessFlood(self.world,region,point,occupied=self.audit.occupied(region),
                             terminals=self.audit.automatic[region],arrival_departure=True)
            mask=reached[region]
            for index,distance in enumerate(flood.steps):
                if distance>=0:mask[index]=1
            entry_proof.append({'map':region,'arrival':list(point),**provenance})
            return True
        for region in self.members:
            incoming=(any(p.destination==region for p in self.portals) or
                      any(p['destination']==region for p in getattr(self,'instance_entries',[])))
            if region in self.specs or not incoming:
                enter(region,tuple(entries[region]['arrival']),{'via':'published primary arrival'})
                if region in self.specs:hub_reached[region]=bytes(reached[region])
        exit_checks=[]
        for identity,entry in getattr(self,'instance_exits',{}).items():
            region=entry['source']['map'];point=tuple(entry['tile']);collision=self.world.collision_for(region)
            standing=self.audit.standing(region,point) if collision else False
            mask=hub_reached.get(region,b'')
            local_access=(bool(collision) and 0<=point[0]<collision.width and 0<=point[1]<collision.height and
                          len(mask)==collision.width*collision.height and bool(mask[point[1]*collision.width+point[0]]))
            departure=departures.get((region,point))
            no_trigger=not any(p.source==region and (p.x,p.y)==point for p in self.portals)
            item={'identity':identity,'map':region,'tile':list(point),'standing':standing,
                  'publishedHubAccessible':local_access,'noPortalTrigger':no_trigger,
                  'departureStep':list(departure) if departure is not None else None}
            exit_checks.append(item)
            if not (standing and local_access and no_trigger and departure is not None):
                issues.append({'reason':'certified instance exit lacks actual served access',**item})
        while True:
            changed=False
            for entry in getattr(self,'instance_entries',[]):
                source=entry['source'];x,y=entry['keeperTile']
                approaches=[(x+dx,y+dy) for dx in range(-4,5) for dy in range(-4,5)
                            if reachable(source,(x+dx,y+dy)) and (x+dx,y+dy) not in self.audit.automatic[source]]
                if not approaches:continue
                point=min(approaches,key=lambda p:(math.dist(p,(x,y)),p))
                changed|=enter(entry['destination'],tuple(entry['arrival']),
                    {'via':'reachable instance keeper','source':source,'keeper':entry['keeper'],
                     'sourceTile':list(point),'definition':entry['definition'],
                     'conditionalOnInstanceStart':True})
            for portal in self.portals:
                if portal.destination not in self.members or not source_access(portal)[0]:continue
                interactive=getattr(self,'interactives',{}).get((portal.source,portal.object_id))
                if interactive is not None and interactive.role=='waystone':
                    # Active runs use definition exits; maps.txt rows remain independently checked below.
                    for entry in self.instance_entries:
                        if entry['destination']==portal.source:
                            changed|=enter(entry['exitMap'],tuple(entry['exitTile']),
                                {'via':'reachable instance waystone','source':portal.source,'definition':entry['definition'],
                                 'exitIdentity':entry['exitIdentity'],'conditionalOnInstanceRun':True})
                else:
                    changed|=enter(portal.destination,(portal.destination_x,portal.destination_y),
                                   {'via':'reachable incoming portal','source':portal.source,'sourceTile':[portal.x,portal.y]})
            if not changed:break
        for portal in self.portals:
            if portal.source not in self.members:continue
            point=(portal.x,portal.y);destination=portal.destination;arrival=(portal.destination_x,portal.destination_y)
            connected,activation=source_access(portal)
            # A continent can retain an outbound road to an older served map.
            # Verify its actual ELM and arrival; it does not become a 66th family identity.
            if destination not in self.members:
                boundary=self.external_boundary(portal)
                departure=self.audit.arrival_departure(destination,arrival)
            else:
                boundary=None;departure=departures.get((destination,arrival))
            item={'map':portal.source,'tile':list(point),'object':portal.object_id,'destination':destination,
                  'arrival':list(arrival),'sourceReachableFromRealEntry':connected,
                  **activation,
                  'destinationInServedFamily':destination in self.members,
                  'destinationHasActualElm':self.world.collision_for(destination) is not None,
                  'destinationDepartureStep':list(departure) if departure is not None else None}
            if boundary is not None:item['externalBoundary']=boundary
            checks.append(item)
            if not connected:issues.append({'reason':'family exit/door disconnected from its actual entry',**item})
            if departure is None:issues.append({'reason':'family portal destination cannot depart safely',**item})
            if boundary is not None and not boundary['passed']:
                issues.append({'reason':'external boundary reciprocal route failed',**item})
        if issues:self.errors.append({'route':'all65 family doors/arrivals','error':f'{len(issues)} family portal access failures','issues':issues})
        return {'passed':not issues,'mapCount':len(self.members),'arrivals':arrivals,'portalChecks':checks,'issues':issues,
                'entryProvenance':entry_proof,'instanceExitChecks':exit_checks,
                'interiorSeedPolicy':'Only reachable incoming portal arrivals; initial automatic-return departure follows World.change_map semantics.'}

    @staticmethod
    def yaw(frame):
        x,z=frame['outward']
        return math.degrees(math.atan2(-x,-z))

    @staticmethod
    def inward(frame):
        x,z=frame['outward']
        return -x,z

    @staticmethod
    def offset(point,direction,distance):
        # Published seam normals are unit vectors, most of them diagonal on the
        # continent; a lane is the nearest server tile at each metre inward.
        return tuple(int(math.floor(point[i]+direction[i]*distance+.5)) for i in (0,1))

    def surface_height(self,region,tile):
        """Rendered walking height (metres) of a server tile from the client's own collision export.

        The territory's EWCG grid folds to the server tile the same way the
        published server collision does (four half-metre cells, highest floor,
        none blocked), so a tile the server can stand on always has a height.
        """
        if not hasattr(self,'_surfaces'):self._surfaces={}
        if region not in self._surfaces:
            path=self.members[region]['path']
            encoding=self.json_input(path)['collision']['heightEncoding']
            binary=path.parent/'collision.bin';self.track(binary);raw=binary.read_bytes()
            magic,_version,width,height=struct.unpack('<4sIII',raw[:16])
            if magic!=b'EWCG' or len(raw)<16+width*height:raise AuditError(f'{region}: unreadable client collision export')
            self._surfaces[region]=(raw,width,height,encoding)
        raw,width,height,encoding=self._surfaces[region]
        x,y=tile
        if not (0<=x and 2*x+1<width and 0<=y and 2*y+1<height):return None
        cells=[raw[16+(2*y+dy)*width+2*x+dx] for dy in (0,1) for dx in (0,1)]
        if not all(cells):return None
        return max(cells)*encoding['step']+encoding['origin']

    def godot_xz(self,region,x,y):
        """Continent-frame metres of server coordinates in `region`; fractional tiles allowed."""
        spec=self.specs[region];ox,oy=spec['serverOrigin'];tx,_,tz=spec['translation']
        return (x-ox+tx,oy-y+tz)

    def harness_screen(self,region,start,neighbour,target,yaw,distance):
        """Project a neighbour tile as the live harness clicks it: the actor at `start`, the ray at the tile's +0.1 corner."""
        stand=self.surface_height(region,start);floor=self.surface_height(neighbour,target)
        if stand is None or floor is None:return None
        fx,fz=self.godot_xz(region,start[0]+.5,start[1]+.5)
        px,pz=self.godot_xz(neighbour,target[0]+.1,target[1]+.1)
        return harness_screen_position((fx,stand,fz),yaw,distance,(px,floor,pz))

    def route_path(self,region,start,label):
        """The real server route from `start` toward the territory arrival.

        Graded continent roads curve within metres of a seam and their normals
        are diagonal, so a straight-line offset can leave the road; the actual
        route to the territory arrival is the only faithful inward reference.
        """
        start=tuple(start);hub=tuple(self.specs[region]['arrival'])
        if not self.audit.standing(region,start):raise AuditError(f'{region}: unsupported or occupied standing tile {start} ({label})')
        # Other automatic triggers are obstacles for a reference route, as in planning.
        blocked=set(self.audit.occupied(region))|(set(self.audit.automatic[region])-{start})
        path=self.world.find_path(region,start,hub,blocked)
        if not path:raise AuditError(f'{region}: no route from {start} to the arrival ({label})')
        return [tuple(tile) for tile in path]

    def route_tile(self,region,start,steps,label):
        """The tile reached after `steps` real server steps from `start` toward the hub."""
        path=self.route_path(region,start,label)
        tile=path[min(steps,len(path))-1]
        if tile in self.audit.automatic[region]:raise AuditError(f'{region}: route reference {tile} is an automatic trigger ({label})')
        return tile

    def published_link(self,a,b):
        """The publication's walk link between a and b."""
        records=[link for link in self.publication['connections'] if link['type']=='walk' and
                 {e['region'] for e in link['ends']}=={a['map'],b['map']}]
        if len(records)!=1:raise AuditError('Missing unique published road lane set')
        return records[0]

    def published_end(self,a,b):
        """The publication's end of the walk link a->b, which carries its lanes."""
        return next(e for e in self.published_link(a,b)['ends'] if e['region']==a['map'])

    def sorted_lanes(self,a,b):
        """Every lane a->b along the common tangent: a gate's seven, or an open border's whole length."""
        found=[p for p in self.portals if p.source==a['map'] and p.destination==b['map'] and p.object_id is None]
        chunk=getattr(self,'chunk_mode',False)
        if (len(found)!=7) if not chunk else not found:
            raise AuditError(f"{a['map']} -> {b['map']}: expected {'seven lanes' if not chunk else 'lanes'}, got {len(found)}")
        if chunk:
            first=self.published_end(a,b)
            # A crossing hands the walker over at the cell they stand on, so each served
            # row is its departure read in the other map's own frame (every territory's
            # tiles are one metre grid in the shared frame). This matched the far side's
            # own lane list while a seam was a gate; an open border has one more tile
            # outside each step in it than inside, so the two lists are not lane for lane.
            def cell(tile):
                spec=self.specs[a['map']];ox,oy=spec['serverOrigin'];x,_,z=spec['translation']
                gx,gz=tile[0]+.5-ox+x,oy-tile[1]-.5+z
                spec=self.specs[b['map']];ox,oy=spec['serverOrigin'];x,_,z=spec['translation']
                return (int(round(gx-x+ox-.5)),int(round(oy+z-gz-.5)))
            expected={(tuple(e['tile']),cell(e['tile'])) for e in first['lanes']}
            actual={((p.x,p.y),(p.destination_x,p.destination_y)) for p in found}
            if expected!=actual:
                raise AuditError(f"{a['map']} -> {b['map']}: served lanes differ from globally identical published cells")
        x,z=a['frame']['outward']
        return sorted(found,key=lambda p:p.x*(-z)+p.y*(-x))

    def gate_lanes(self,a,b):
        """The gate's own lanes a->b by their surveyed offset along the seam, -3 to 3.

        An open border's lanes run its whole length; the walks that prove the gate
        - its handoffs and its neighbour clicks - are the gate's. A gate lane that a
        step of the border put on its own side was dropped when the border opened,
        so an offset can be missing.
        """
        lanes=self.sorted_lanes(a,b)
        if not getattr(self,'chunk_mode',False):
            return {index-3:p for index,p in enumerate(lanes)}
        offsets={tuple(e['tile']):e['gate'] for e in self.published_end(a,b)['lanes'] if 'gate' in e}
        if not offsets and len(lanes)==7 and self.published_link(a,b).get('road',True):
            # A publication from before the borders opened: its seven lanes are the gate.
            return {index-3:p for index,p in enumerate(lanes)}
        return {offsets[(p.x,p.y)]:p for p in lanes if (p.x,p.y) in offsets}

    def gate_lane(self,a,b,offset):
        """The gate lane at a surveyed offset, or the surviving one nearest it."""
        gate=self.gate_lanes(a,b)
        if not gate:raise AuditError(f"{a['map']} -> {b['map']}: no lane of its gate survives")
        return gate[min(gate,key=lambda k:(abs(k-offset),k))]

    def border_lane(self,a,b,p,lane):
        """An open border's lane: the neighbour's first tile across it, stepped onto from ground behind."""
        tile,behind=(p.x,p.y),tuple(lane['arrival'])
        if not self.audit.standing(a['map'],tile):
            raise AuditError(f"{a['map']}: border lane {tile} cannot be stood on")
        if (not self.audit.standing(a['map'],behind) or max(abs(tile[i]-behind[i]) for i in (0,1))!=1
                or not self.world.can_walk_step(a['map'],behind,tile)):
            raise AuditError(f"{a['map']}: border lane {tile} cannot be stepped onto from {behind}")
        arrival=(p.destination_x,p.destination_y)
        if not self.audit.standing(b['map'],arrival) or arrival in self.audit.automatic[b['map']]:
            raise AuditError(f"{b['map']}: occupied, blocked or bouncing lane arrival {arrival}")
        return {'from':a['map'],'to':b['map'],'lane':'border','trigger':list(tile),'arrival':list(arrival),
                'behind':list(behind)}

    def first_road_leg(self, source, destination):
        """Mirror ExteriorRegionStream._first_walk_leg, including link order."""
        queue, visited = [(source, None)], {source}
        for current, first in queue:
            for link in self.links:
                if not link.get('seamless'):continue
                for here, there in (link['ends'], link['ends'][::-1]):
                    if here['map'] != current or there['map'] in visited:continue
                    leg = first or (here, there)
                    if there['map'] == destination:return leg
                    visited.add(there['map']);queue.append((there['map'], leg))
        raise AuditError(f'{source} -> {destination}: no runtime road route')

    def road_portal(self, here, there):
        config = here['coordinateTransform'];point = here['position']
        origin = config.get('origin', [0,0,0]);server_origin = config.get('serverOrigin',[0,0])
        scale = config.get('metresPerTile',1)
        y = (origin[2]-point[2]) if config.get('invertServerY',True) else point[2]-origin[2]
        tile = (math.floor((point[0]-origin[0])/scale+server_origin[0]),
                math.floor(y/scale+server_origin[1]))
        portals = [p for p in self.portals if p.source==here['map'] and p.destination==there['map']
                   and p.object_id is None and (p.x,p.y)==tile]
        if len(portals)!=1:
            raise AuditError(f"{here['map']} -> {there['map']}: runtime road command {tile} has {len(portals)} matching portals")
        return portals[0]

    def visual_road_requests(self):
        """Audit every intermediate leg for each shore-click direction.

        Start and final clicked positions are camera-dependent and remain live
        checks. Intermediate arrival-to-portal requests are completely fixed
        by the published graph and must work without fixture waypoints.
        """
        routes=[]
        for link in self.visual_links:
            for a,b in (link['ends'],link['ends'][::-1]):
                def check():
                    current, destination = a['map'], b['map']
                    if getattr(self,'chunk_mode',False):
                        try:self.first_road_leg(current,destination)
                        except AuditError:
                            itinerary=travel_route(self.publication['connections'],current,destination)
                            if not any(c['type']=='ferry' for c,_,_ in itinerary):raise
                            routes.append({'pair':link['id'],'from':current,'to':destination,
                                'maps':[current]+[end['region'] for _,_,end in itinerary],
                                'travelMode':'ferry-required','oneClickWalkAvailable':False,
                                'ferryConnections':[c['id'] for c,_,_ in itinerary if c['type']=='ferry'],
                                'intermediateRequests':[]})
                            return
                    arrival = None;maps=[current];requests=[]
                    for _ in range(len(self.specs)):
                        here,there=self.first_road_leg(current,destination)
                        portal=self.road_portal(here,there)
                        if arrival is not None:
                            item=self.audit.one_request(current,arrival,(portal.x,portal.y),
                                link['id']+' '+a['map']+' -> '+destination,allowed=[(portal.x,portal.y)])
                            item['renewedIntent']=self.audit.renewed_intent(current,arrival,(portal.x,portal.y),
                                allowed=[(portal.x,portal.y)],renew_at=getattr(self,'renew_at',448),
                                maximum_renewals=getattr(self,'maximum_renewals',16))
                            requests.append(item)
                            if not item['renewedIntent']['passes']:
                                self.errors.append({'route':item['label'],'error':'Intermediate one-click runtime continuation fails',
                                                    'request':item})
                        current=there['map'];maps.append(current)
                        arrival=(portal.destination_x,portal.destination_y)
                        if current==destination:
                            routes.append({'pair':link['id'],'from':a['map'],'to':destination,
                                           'maps':maps,'intermediateRequests':requests})
                            return
                    raise AuditError(f"{link['id']}: runtime road routing did not converge")
                self.attempt(link['id']+' '+a['map']+' direct road requests',check)
        return routes

    def border_route(self,link,index):
        a,b=link['ends']
        p=self.gate_lane(a,b,index-3)
        target=(p.x,p.y)
        start=self.route_tile(a['map'],target,8,link['id']+' lane start')
        # The reciprocal lane arrives one cell inside this trigger; both sides sort
        # their lanes along the common tangent, so match by actual arrival tile - by
        # the gate's own lanes first, since this walk proves the gate.
        candidates=[(max(abs(q.destination_x-target[0]),abs(q.destination_y-target[1])),q)
                    for q in (list(self.gate_lanes(b,a).values()) or self.sorted_lanes(b,a))]
        gap,q=min(candidates,key=lambda row:row[0])
        if gap>3:
            raise AuditError(f"{link['id']}: lane {index-3} has no reciprocal arrival beside its trigger {target}")
        expected_return=(q.destination_x,q.destination_y)
        identity=link['id']+'-lane-'+str(index-3)
        steps=self.audit.movement(a['map'],start,target,identity+' outward',allowed=[target])
        steps[-1].update(destination=b['map'])
        arrival=(p.destination_x,p.destination_y)
        end=(q.x,q.y)
        # Walk off the return lane before reversing; do not use an admin jump.
        back_approach=self.route_tile(b['map'],end,6,link['id']+' return approach')
        steps+=self.audit.movement(b['map'],arrival,back_approach,identity+' reverse approach')
        back=self.audit.movement(b['map'],back_approach,end,identity+' return',allowed=[end])
        back[-1].update(destination=a['map'])
        steps+=back
        return {'id':identity,'map':a['map'],'start':list(start),'startTolerance':0,
                'yaw':self.yaw(a['frame']),'distance':32,'steps':steps}

    def click_route(self,link,a,b,depth):
        p=self.gate_lane(a,b,0)
        start=self.route_tile(a['map'],(p.x,p.y),8,link['id']+' click start')
        destination=(p.destination_x,p.destination_y)
        path=self.route_path(b['map'],destination,link['id']+' click target')
        yaw=self.yaw(a['frame'])
        # The harness asserts the clicked tile projects inside its fixed camera.
        # Graded roads bend and climb within metres of a seam, so the deep
        # target is the farthest of the first `depth` real steps that stays a
        # clear margin inside the frame; a shallow target must itself be visible.
        chosen=None
        for steps in range(min(depth,len(path)),0,-1):
            tile=path[steps-1]
            if tile in self.audit.automatic[b['map']]:raise AuditError(f"{b['map']}: route reference {tile} is an automatic trigger ({link['id']} click target)")
            margin=visible_margin(self.harness_screen(a['map'],start,b['map'],tile,yaw,CLICK_CAMERA_DISTANCE))
            if margin>=CLICK_VISIBLE_MARGIN_PX:chosen=(steps,tile,margin);break
        if chosen is None or (depth>2 and chosen[0]<=2):
            raise AuditError(f"{b['map']}: no route tile {3 if depth>2 else 1}-{depth} steps beyond {destination} is visible from the gameplay camera at {start}")
        steps,target,margin=chosen
        self.audit.exact_path(a['map'],start,(p.x,p.y),allowed=[(p.x,p.y)])
        self.audit.exact_path(b['map'],destination,target)
        identity=link['id']+'-'+a['map']+'-click-'+str(depth)
        return {'id':identity,'map':a['map'],'start':list(start),'startTolerance':0,
                'yaw':yaw,'distance':CLICK_CAMERA_DISTANCE,'walkTimeout':60,
                'requestedSteps':depth,'targetSteps':steps,'screenMarginPx':round(margin,1),
                'steps':[{'tile':list(target),'destination':b['map'],'clickNeighbor':True,
                          'label':'exact visible resident target','capture':identity}]}

    def local_route_candidates(self,region,origin,direction,minimum,maximum,preferred,label,*,reverse=False):
        """Short real paths into a border pocket, independent of the territory hub."""
        origin=tuple(origin);ideal=(origin[0]+direction[0]*preferred,origin[1]+direction[1]*preferred)
        points=[(origin[0]+dx,origin[1]+dy) for dx in range(-maximum,maximum+1)
                for dy in range(-maximum,maximum+1) if dx or dy]
        points.sort(key=lambda p:((p[0]-ideal[0])**2+(p[1]-ideal[1])**2,
                                  -((p[0]-origin[0])*direction[0]+(p[1]-origin[1])*direction[1]),p))
        result=[]
        for point in points:
            if point in self.audit.automatic[region] or not self.audit.standing(region,point):continue
            try:
                path=(self.audit.exact_path(region,point,origin,allowed=[origin]) if reverse else
                      self.audit.exact_path(region,origin,point))
            except AuditError:
                continue
            if minimum<=len(path)<=maximum:
                result.append((point,len(path)))
                if len(result)>=ROADLESS_LOCAL_CANDIDATES:break
        return result

    def roadless_routes(self,link,a,b):
        """One local physical crossing and neighbour click for a roadless direction."""
        lanes=self.sorted_lanes(a,b)
        order=sorted(range(len(lanes)),key=lambda index:(abs(index-(len(lanes)-1)/2),index))
        published={tuple(e['tile']):e for e in self.published_end(a,b)['lanes']}
        failures=[];selected=None
        for index in order:
            p=lanes[index];trigger=(p.x,p.y);arrival=(p.destination_x,p.destination_y)
            lane=published.get(trigger)
            if lane is None:
                failures.append(f'{trigger}: absent from published lane set');continue
            try:self.border_lane(a,b,p,lane)
            except AuditError as error:
                failures.append(f'{trigger}: {error}');continue
            starts=self.local_route_candidates(a['map'],trigger,self.inward(a['frame']),3,12,8,
                                                link['id']+' roadless approach',reverse=True)
            if not starts:
                failures.append(f'{trigger}: no safe 3-12-step local source approach');continue
            targets=self.local_route_candidates(b['map'],arrival,self.inward(b['frame']),3,12,8,
                                                 link['id']+' roadless target')
            if not targets:
                failures.append(f'{trigger}: no safe 3-12-step nonportal destination target');continue
            yaw=self.yaw(a['frame'])
            for start,source_steps in starts:
                for target,target_steps in targets:
                    margin=visible_margin(self.harness_screen(a['map'],start,b['map'],target,yaw,
                                                              CLICK_CAMERA_DISTANCE))
                    if margin>=CLICK_VISIBLE_MARGIN_PX:
                        selected=(p,start,source_steps,arrival,target,target_steps,yaw,margin);break
                if selected:break
            if selected:break
            failures.append(f'{trigger}: no local approach/target pair has {CLICK_VISIBLE_MARGIN_PX}px camera margin')
        if selected is None:
            detail='; '.join(failures[:8])
            if len(failures)>8:detail+=f'; plus {len(failures)-8} more lanes'
            raise AuditError(f"{link['id']} {a['map']} -> {b['map']}: no usable roadless representative ({detail})")
        p,start,source_steps,arrival,target,target_steps,yaw,margin=selected
        identity=link['id']+'-'+a['map']+'-roadless-crossing'
        steps=self.audit.movement(a['map'],start,(p.x,p.y),identity+' outward',allowed=[(p.x,p.y)])
        steps[-1].update(destination=b['map'])
        steps+=self.audit.movement(b['map'],arrival,target,identity+' safe departure')
        walk={'id':identity,'map':a['map'],'start':list(start),'startTolerance':0,
              'yaw':yaw,'distance':CLICK_CAMERA_DISTANCE,'steps':steps}
        clicks=[]
        for mode,suffix,label in ((None,'','exact visible roadless resident target'),
                                  ('full_map','-full-map','exact roadless resident target via full map'),
                                  ('minimap','-minimap','exact roadless resident target via minimap')):
            click_identity=link['id']+'-'+a['map']+'-roadless-click'+suffix
            step={'tile':list(target),'destination':b['map'],'clickNeighbor':True,
                  'label':label,'capture':click_identity}
            if mode is not None:step['mapClick']=mode
            clicks.append({'id':click_identity,'map':a['map'],'start':list(start),'startTolerance':0,
                           'yaw':yaw,'distance':CLICK_CAMERA_DISTANCE,'walkTimeout':60,
                           'requestedSteps':12,'targetSteps':target_steps,'screenMarginPx':round(margin,1),
                           'steps':[step]})
        return walk,clicks

    def borders(self):
        centre,shoulders,clicks=[],[],[]
        for link in self.links:
            for a,b in (link['ends'],link['ends'][::-1]):
                def check_lanes():
                    if getattr(self,'chunk_mode',False):
                        # Every lane of an open border, the gate's among them, is the neighbour's
                        # first tile across it stepped onto from the ground behind, so each is
                        # proved as one; the gate's own walks are the handoffs and clicks below.
                        published={tuple(e['tile']):e for e in self.published_end(a,b)['lanes']}
                        offsets={(q.x,q.y):k for k,q in self.gate_lanes(a,b).items()}
                        for q in self.sorted_lanes(a,b):
                            item=self.border_lane(a,b,q,published[(q.x,q.y)])
                            if (q.x,q.y) in offsets:item['lane']=offsets[(q.x,q.y)]
                            self.lanes.append(item)
                        return
                    for offset,p in sorted(self.gate_lanes(a,b).items()):
                        index=offset+3
                        curved='approachCenterline' in a['frame']
                        if curved:
                            lane=approaches.lane_tiles(a['frame'],a['coordinateTransform'],index-3,outward=1)
                            if lane[-1]!=(p.x,p.y):raise AuditError(f"{a['map']}: authored lane misses its actual trigger")
                        else:
                            depth=int(a['frame']['collarDepth']) if getattr(self,'chunk_mode',False) else 40
                            if depth<2:raise AuditError(f"{a['map']}: receiving strip is too short")
                            lane=[self.offset((p.x,p.y),self.inward(a['frame']),offset) for offset in range(depth,-1,-1)]
                            lane=[tile for i,tile in enumerate(lane) if i==0 or tile!=lane[i-1]]
                        start=lane[0]
                        path=self.audit.exact_path(a['map'],start,(p.x,p.y),allowed=[(p.x,p.y)])
                        # Prove the surveyed lane itself, not just a winding detour.
                        previous=None
                        for point in lane:
                            if (not self.audit.standing(a['map'],point) or
                                (point!=(p.x,p.y) and point in self.audit.automatic[a['map']]) or
                                (previous is not None and (max(abs(point[i]-previous[i]) for i in (0,1))>1 or
                                 not self.world.can_walk_step(a['map'],previous,point)))):
                                raise AuditError(f"{a['map']} lane {index-3}: blocked receiving strip at {point}")
                            previous=point
                        arrival=(p.destination_x,p.destination_y)
                        if not self.audit.standing(b['map'],arrival) or arrival in self.audit.automatic[b['map']]:
                            raise AuditError(f"{b['map']}: occupied, blocked or bouncing lane arrival {arrival}")
                        self.lanes.append({'from':a['map'],'to':b['map'],'lane':index-3,
                                           'trigger':[p.x,p.y],'arrival':list(arrival),'approachSteps':len(path),
                                           'surveyedLaneTiles':len(lane),'authoredCurve':curved,
                                           'collarMetres':approaches.collar_length(a['frame']) if curved else depth})
                self.attempt(link['id']+' '+a['map']+' lanes',check_lanes)
                if not link.get('road',True):
                    routes=self.attempt(link['id']+' '+a['map']+' roadless representative',
                                        lambda:self.roadless_routes(link,a,b))
                    if routes:
                        walk,roadless_clicks=routes;centre.append(walk);clicks.extend(roadless_clicks)
                    continue
                for depth in (2,12):
                    route=self.attempt(link['id']+' neighbor click',lambda:self.click_route(link,a,b,depth))
                    if route:clicks.append(route)
            if not link.get('road',True):continue
            for index in (0,3,6):
                route=self.attempt(link['id']+' handoff',lambda:self.border_route(link,index))
                if route:(centre if index==3 else shoulders).append(route)
        return centre,shoulders,clicks

    def ferry_routes(self):
        """Prove actual dock access, remote departure and return with live fixtures."""
        routes=[]
        if not getattr(self,'chunk_mode',False):return routes
        for link in self.publication['connections']:
            if link['type']!='ferry':continue
            for a,b in (link['ends'],link['ends'][::-1]):
                def check():
                    identity=link['id']+'-'+a['region']+'-roundtrip'
                    start=tuple(self.specs[a['region']]['arrival']);steps=[]
                    for source,destination,current in ((a,b,start),(b,a,tuple(b['arrival']))):
                        triggers=[p for p in self.portals if p.source==source['region'] and p.destination==destination['region']
                                  and (p.x,p.y)==tuple(source['tile']) and p.object_id is None]
                        if len(triggers)!=1 or (triggers[0].destination_x,triggers[0].destination_y)!=tuple(destination['arrival']):
                            raise AuditError(f'{identity}: missing exact published ferry departure/arrival')
                        leg=self.audit.movement(source['region'],current,tuple(source['tile']),identity,
                                                allowed=[tuple(source['tile'])])
                        if not leg:raise AuditError(f'{identity}: ferry approach contains no movement')
                        leg[-1]['destination']=destination['region']
                        leg[-1]['expectedArrival']=self.ferry_arrival(destination)
                        steps+=leg
                        arrival=tuple(destination['arrival'])
                        if arrival in self.audit.automatic[destination['region']] or self.audit.arrival_departure(destination['region'],arrival) is None:
                            raise AuditError(f'{identity}: ferry arrival cannot safely depart')
                    steps.append({'tile':a['arrival'],'label':'exact return from ferry','capture':identity+'-returned'})
                    routes.append({'id':identity,'map':a['region'],'start':list(start),'startTolerance':0,
                                   'distance':32,'travelMode':'ferry','steps':steps})
                self.attempt(link['id']+' '+a['region']+' ferry access',check)
        return routes

    def ferry_arrival(self,destination):
        """Freeze the published server tile and its shared continent centre.

        The live harness checks this on the first real destination spawn,
        before any next MOVE_TO can conceal a displaced ferry arrival.
        """
        region=destination['region'];tile=destination['arrival'];spec=self.specs[region]
        if len(tile)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or int(v)!=v for v in tile):
            raise AuditError(f'{region}: ferry arrival is not an exact authoritative tile')
        origin=spec.get('serverOrigin');translation=spec.get('translation')
        if (not isinstance(origin,(list,tuple)) or len(origin)!=2 or
            not isinstance(translation,(list,tuple)) or len(translation)!=3 or
            any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in [*origin,*translation])):
            raise AuditError(f'{region}: ferry arrival has no finite published continent transform')
        x=tile[0]+.5-origin[0]+translation[0]
        z=origin[1]-tile[1]-.5+translation[2]
        return {'map':region,'tile':[int(v) for v in tile],'global':[round(x,6),round(z,6)],
                'units':'metres','point':'tile-center'}

    def services(self,region):
        start=tuple(self.specs[region]['arrival'])
        route={'id':region+'-arrival-services-resource','map':region,'start':list(start),
               'startTolerance':0,'distance':28,'steps':[]}
        current=start
        furniture={(i.x+x,i.y+y) for i in self.interactives.values() if i.map_id==region
                   for x in (-1,0,1) for y in (-1,0,1)}
        roles=[]
        package=self.json_input(self.members[region]['path'])
        plan=package.get('contentLayout',{}).get('services')
        service_roles=[item['role'] for item in plan] if plan else ['information','storage','crafting_station']
        if not {'information','storage','crafting_station'}<=set(service_roles):
            raise AuditError(f'{region}: authored service plan omits a core service')
        for role in service_roles:
            entries=sorted((i for i in self.interactives.values() if i.map_id==region and i.role==role),
                           key=lambda i:(math.dist(current,(i.x,i.y)),i.object_id))
            if not entries:raise AuditError(f'{region}: missing {role} service')
            chosen=None
            for entry in entries:
                try:
                    tile=self.audit.approach(region,current,(entry.x,entry.y),radius=min(4,self.world.settings.portal_activation_distance),forbidden=furniture)
                    chosen=entry,tile;break
                except AuditError:continue
            if chosen is None:raise AuditError(f'{region}: no actual standing approach for {role}')
            entry,tile=chosen
            legs=self.audit.movement(region,current,tile,role)
            if not legs:legs=[{'tile':list(tile),'label':role}]
            legs[-1].update(useObject=entry.object_id,capture=region+'-'+role)
            if role=='storage':legs[-1]['expectStorage']=True
            else:legs[-1]['expectText']=entry.text
            route['steps']+=legs;current=tile;roles.append({'role':role,'object':entry.object_id,'tile':list(tile)})
        if region=='four_gates' and 'training' not in service_roles:
            teachers=[(identity,npc) for identity,(npc,npc_map,_,_) in self.world.npcs.items()
                      if npc_map==region and npc.name=='Wayfinder Nesh' and self.world.npc_roles.get(identity)=='tutorial']
            if len(teachers)!=1:raise AuditError('Four Gates requires its actual Wayfinder Nesh tutorial service')
            identity,teacher=teachers[0]
            tile=self.audit.approach(region,current,(teacher.x,teacher.y),radius=4,forbidden=furniture)
            legs=self.audit.movement(region,current,tile,'training conversation')
            if not legs:legs=[{'tile':list(tile),'label':'training conversation'}]
            legs[-1].update(useNpc=teacher.name,expectDialogue=teacher.name,
                            expectDialogueText='You already know how to find your feet.',capture=region+'-training')
            route['steps']+=legs;current=tile
            roles.append({'role':'training','npc':teacher.name,'serverRole':'tutorial','actorId':identity,'tile':list(tile)})
        resources=sorted((n for n in self.resources.values() if n.map_id==region),key=lambda n:(math.dist(current,(n.x,n.y)),n.object_id))
        for node in resources:
            try:tile=self.audit.approach(region,current,(node.x,node.y),radius=3,forbidden=furniture)
            except AuditError:continue
            legs=self.audit.movement(region,current,tile,'representative resource '+node.resource)
            if not legs:legs=[{'tile':list(tile),'label':'representative resource'}]
            legs[-1].update(expectResource=node.object_id,capture=region+'-resource')
            route['steps']+=legs
            self.coverage.setdefault(region,{})['services']=roles
            self.coverage[region]['resource']={'id':node.object_id,'name':node.resource,'tile':list(tile)}
            return route
        raise AuditError(f'{region}: no visible-resource standing approach')

    def content_inventory(self):
        """Inventory all outdoor living content separately from live samples."""
        result={'regions':{},'issues':[],'counts':defaultdict(int),
                'scope':'All twelve exterior maps; static geometry and configured NPC bodies. No moving actors simulated.',
                'distanceMetric':'Fewest-step flood path with measured edge lengths; not a weighted shortest-distance claim.',
                'inheritance':'Unreachable final posts are not classified as inherited without comparison to frozen baseline.'}
        for region,spec in self.specs.items():
            occupied=self.audit.occupied(region);terminals=self.audit.automatic[region]
            flood=AccessFlood(self.world,region,spec['arrival'],occupied=occupied,terminals=terminals)
            records=[]
            for identity,(npc,npc_map,_,_) in self.world.npcs.items():
                if npc_map==region:records.append(('npc',identity,npc.name,(npc.x,npc.y),4))
            for service in self.interactives.values():
                if service.map_id==region:
                    records.append(('interactive',service.object_id,service.role,(service.x,service.y),
                                    min(4,self.world.settings.portal_activation_distance)))
            for node in self.resources.values():
                if node.map_id==region:records.append(('resource',node.object_id,node.resource,(node.x,node.y),2))
            for index,spawn in enumerate(self.spawns):
                if spawn.map_id==region:records.append(('spawn',index,spawn.creature,(spawn.x,spawn.y),2))
            fallback={};entries=[]
            for kind,identity,label,target,radius in records:
                point=flood.near(target,radius)
                item={'kind':kind,'id':identity,'label':label,'tile':list(target),'approachRadiusTiles':radius,
                      'pointWalkable':self.world.is_walkable(region,*target),'pointOccupied':target in occupied,
                      'pointConnected':flood.reachable(target),'accessible':point is not None,
                      'approach':flood.describe(target,point)}
                if point is not None:
                    item['reason']='exact point reachable' if point==target else 'reachable interaction/observation neighbor'
                else:
                    if 'without_terminals' not in fallback:
                        fallback['without_terminals']=AccessFlood(self.world,region,spec['arrival'],occupied=occupied)
                    if fallback['without_terminals'].near(target,radius) is not None:
                        reason='access requires crossing an automatic portal'
                    else:
                        if 'geometry' not in fallback:
                            fallback['geometry']=AccessFlood(self.world,region,spec['arrival'])
                        reason=('static NPC bodies block the approach' if fallback['geometry'].near(target,radius) is not None
                                else 'no primary-arrival geometry connection within interaction/observation range')
                    item.update(reason=reason,nearestReachable=flood.describe(target,flood.nearest(target)),
                                inheritance='unverified; requires frozen baseline comparison')
                    result['issues'].append({'map':region,**item})
                entries.append(item);result['counts'][kind]+=1
            result['regions'][region]={'arrival':spec['arrival'],'reachableStandingTiles':len(flood.points),
                                       'staticNpcOccupiedTiles':len(occupied),'automaticPortalTiles':len(terminals),
                                       'entries':entries}
        result['counts']=dict(result['counts'])
        result['allAccessible']=not result['issues']
        return result

    def ordinary_doors(self,region):
        result=[]
        for p in self.portals:
            member=self.members.get(p.destination)
            if p.source!=region or member is None or member['owner']!=region or p.destination==region:
                continue
            if 'gauntlet' in p.destination or p.destination.endswith('_secrets'):continue
            result.append(p)
        return sorted(result,key=lambda p:(math.dist(self.specs[region]['arrival'],(p.x,p.y)),p.destination,p.x,p.y))

    def interior(self,region,p,index):
        start=tuple(self.specs[region]['arrival']);trigger=(p.x,p.y)
        identity=f'{region}-door-{index:02d}-{p.destination}'
        steps=self.audit.movement(region,start,trigger,'ordinary door',allowed=[trigger])
        if not steps:raise AuditError(f'{identity}: arrival itself is a door trigger')
        steps[-1]['destination']=p.destination
        if p.object_id is not None:steps[-1]['object']=p.object_id
        inside=(p.destination_x,p.destination_y)
        stand=self.audit.approach(p.destination,inside,inside,radius=5,minimum=2)
        legs=self.audit.movement(p.destination,inside,stand,'inside doorway')
        if not legs:raise AuditError(f'{identity}: no interior approach movement')
        legs[-1]['capture']=identity+'-inside';steps+=legs
        returns=sorted((q for q in self.portals if q.source==p.destination and q.destination==region),key=lambda q:(math.dist(inside,(q.x,q.y)),q.x,q.y))
        for q in returns:
            if max(abs(q.destination_x-p.x),abs(q.destination_y-p.y))>12:
                continue  # A different public exit is not this door's round trip.
            try:back=self.audit.movement(p.destination,stand,(q.x,q.y),'return through door',allowed=[(q.x,q.y)])
            except AuditError:continue
            if not back:continue
            back[-1]['destination']=region
            if q.object_id is not None:back[-1]['object']=q.object_id
            steps+=back
            arrival=(q.destination_x,q.destination_y)
            # An explicit arrival check catches return-coordinate drift as well as wrong maps.
            self.audit.exact_path(region,arrival,arrival)
            if arrival in self.audit.automatic[region]:raise AuditError(f'{identity}: return bounces at {arrival}')
            steps.append({'tile':list(arrival),'label':'exact exterior return','capture':identity+'-returned'})
            return {'id':identity,'map':region,'start':list(start),'startTolerance':0,'distance':28,'steps':steps}
        raise AuditError(f'{identity}: no reachable paired return from this interior section')

    def generate(self):
        integrity=self.attempt('actual65-family package bytes and metadata',self.publication_integrity)
        graph=self.attempt('all physical neighbor pairs',self.graph_integrity)
        family_access=self.attempt('all65 family portal standing/access',self.family_portal_access)
        centre,shoulders,clicks=self.borders()
        visual_routes=self.visual_road_requests()
        ferries=self.ferry_routes()
        inventory=self.attempt('all-content access inventory',self.content_inventory)
        core,doors=[],[]
        for region in self.specs:
            route=self.attempt(region+' services/resource',lambda:self.services(region))
            if route:core.append(route)
            entries=self.ordinary_doors(region)
            if not entries:self.errors.append({'route':region,'error':'No ordinary served interior door'})
            selected=[]
            for index,p in enumerate(entries):
                route=self.attempt(region+' interior '+str(index),lambda:self.interior(region,p,index))
                if route:selected.append(route)
            doors+=selected
            if selected:core.append(selected[0])
            self.coverage.setdefault(region,{})['ordinaryDoorsDeclared']=len(entries)
            self.coverage[region]['ordinaryRoundTripsAudited']=len(selected)
        outputs={'streaming-centre.json':centre,'streaming-shoulders.json':shoulders,
                 'streaming-all-three-lanes.json':centre+shoulders,'neighbor-clicks.json':clicks,
                 'region-core.json':core,'all-interior-roundtrips.json':doors}
        expected_lanes=sum(len(end['lanes']) for link in self.publication['connections'] if link['type']=='walk'
                           for end in link['ends']) if getattr(self,'chunk_mode',False) else 238
        if getattr(self,'chunk_mode',False):outputs['ferry-roundtrips.json']=ferries
        if len(self.lanes)!=expected_lanes:self.errors.append({'route':'all lanes','error':f'Only {len(self.lanes)}/{expected_lanes} lanes audited'})
        changed=[p for p,h in self.inputs.items() if sha(Path(p))!=h]
        if changed:self.errors.append({'route':'provenance','error':'Inputs changed during generation','files':changed})
        report={'ready':not self.errors,'errors':self.errors,'coverage':self.coverage,
                'readyDefinition':'Actual package bytes, every ownership-derived physical neighbor pair, all served family portal entries/exits, published ferry roundtrips, representative live fixtures and required road requests passed their offline checks; inspect allContentAccess separately for exhaustive content claims.',
                'counts':{name:len(routes) for name,routes in outputs.items()},'laneCount':len(self.lanes),
                'lanes':self.lanes,'movementLegs':self.audit.legs,'inputSha256':self.inputs,
                'visualOnlyRoadRoutes':visual_routes,'singleMoveRequests':self.audit.requests,'expectedLaneCount':expected_lanes,
                'allContentAccess':inventory,
                'publicationIntegrity':integrity,'graphIntegrity':graph,'familyPortalAccess':family_access,
                'maximumIntermediateRequestSteps':max((r['requestedSteps'] for r in self.audit.requests),default=0),
                'assumptions':['Actual ELM floor overrides, runtime storage bodies and configured NPC occupancy are included.',
                               'Moving creatures and other logged-in players can change occupancy during live execution.',
                               'Every emitted waypoint uses the real unmodified World.find_path; planning-only entrance exclusions are never passed to its final proof.',
                               'Neighbor visibility, rendered walking surfaces, camera continuity and exact resumed targets are asserted by the live harness.',
                               'Visual-only shore routing audits fixed intermediate arrival-to-portal MOVE_TO requests without waypoints; camera-dependent first/final legs are separate live checks.',
                               'Island adjacency without a continuous road is explicitly ferry-required; each declared ferry dock and return is audited separately and is not claimed as a one-click walk.',
                               'An uncapped diagnostic copy measures overlong paths only; individual 512-step truncations remain visible.',
                               'Each intermediate path also simulates actual runtime 448-command same-target renewals, with one user click, no fixture waypoint, exact endpoint/door checks and the runtime renewal budget.']}
        return outputs,report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',type=Path,default=CLIENT)
    parser.add_argument('--server',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-leg',type=int,default=64)
    parser.add_argument('--publication',type=Path,help='New-continent publication contract; defaults to _continent/generated/publication.json')
    args=parser.parse_args()
    if not 1<=args.max_leg<=128:parser.error('--max-leg must be in 1..128')
    args.output.mkdir(parents=True,exist_ok=True)
    try:
        outputs,report=Generator(args.client,args.server,args.data,max_leg=args.max_leg,publication=args.publication).generate()
    except (AuditError,ValueError) as error:
        outputs,report={}, {'ready':False,'errors':[{'error':str(error)}]}
    (args.output/'fixture-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if not report['ready']:
        print(json.dumps({'ready':False,'errors':report['errors']},indent=2))
        raise SystemExit(1)
    for name,routes in outputs.items():
        (args.output/name).write_text(json.dumps(routes,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ready':True,'counts':report['counts'],'lanes':report['laneCount']},indent=2))


if __name__=='__main__':main()
