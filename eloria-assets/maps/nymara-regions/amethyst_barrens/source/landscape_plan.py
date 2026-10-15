"""A compact working basin: the Glasswardens shelter below exposed crystal country.

Authoring coordinates remain the original survey. Axis knots shorten the empty
journeys while preserving the observatory stair and the inhabited service yard.
Architecture, door mouths, vegetation and furniture retain metre dimensions.
"""
from copy import deepcopy
import math
import numpy as np
from compact_landscape import Axis, CompactLandscape
from amberwood import terrain as TER, landscape as LAND, routecraft as RC
from amberwood import architecture as ARCH, props as PROPS, canyoncraft as CANYON
from amberwood import noise as N
from regionbuild import Placement
import region as REG
import layout

SERVER_CELLS = 384
SERVER_ORIGIN = (116.0, 116.0)
PLAY_MIN_X, PLAY_MAX_X = -116.0, 267.0
PLAY_MIN_Z, PLAY_MAX_Z = -267.0, 116.0
PLAN = CompactLandscape(Axis(-174, 402, -116, 268, (-95, 30)),
                        Axis(-402, 174, -268, 116, (-205, 5)),
                        REG.SERVER_ORIGIN, SERVER_ORIGIN)
PORTALS = {'north-pass': (54.0, 12.0, -262.0),
           'west-road': (-111.0, 8.0, -192.0),
           'south-road': (54.5, 19.0, 114.5)}
# Compact-space road surveys. Wide, gently feathered earth shoulders make the
# shared 42m collars part of a landform rather than holes in the perimeter wall.
BORDER_ROADS = {
    'whitehorn_ascent': ([(54,-209),(54,-223),(54,-244),(54,-262),(54,-281)],
                         [5.0,8.0,12.0,12.0,12.0], 6.4),
    'mirror_shelf': ([(-84,-161),(-88,-179),(-95,-192),(-111,-192),(-128,-192)],
                     [6.0,7.0,8.0,8.0,8.0], 6.4),
    'sunmane_ascent': ([(108,48),(93,55),(77,62),(63,68),(54.5,71.5),(54.5,127)],
                       [5.8,9.0,13.0,17.0,19.0,19.0], 7.0),
    'sour_cut_path': ([(132,-178),(135,-188),(139,-195),(147,-201)],
                     [6.8,9.0,13.0,17.8], 4.4),
}
# Settlement fronts look into one working court, with a clear lane between the
# existing station and exchange. No new service identities replace live NPCs.
HOUSES = [('glasswarden-bunkhouse','Glasswarden Bunkhouse',-22,-43,9.6,7.6),
          ('glasswarden-mess','Naia Flint\'s Cookhouse',13,-43,8.2,7.6)]
# Exact compact posts on final server-reachable working ground. The tuning
# adept stands on the Ring's western bank, the counter outside his door, and
# the digger in front of the geode mouth rather than within its stone footprint.
NPC_COMPACT_POSTS = {
    'Tuning Adept Ollum Ghast': [204.0, 6.1767, 74.0],       # tile 320,42
    'Shard Counter Bel Ammon': [196.0, 6.1240, -52.0],      # tile 312,168
    'Geode Digger Torvin Slate': [-82.0, 2.873272, -214.0], # tile 34,330; final cave-front soil
    'Grinder Vell': [-86.1375, 2.671041, -215.7049],       # tile 30,332; same working shelf
}


def prepare(t, seed):
    level = float(t.height_at(0,0))
    # The working yard is dust and aggregate, with a travelled cart strip. A
    # twenty-four-metre square of luminous masonry overwhelmed every actor.
    yard=(t.gx>-35)&(t.gx<29)&(t.gz>-38)&(t.gz<20)
    t.surface[yard]=TER.BARRENS
    LAND.worn_path(t,REG.ROUTES['arrival_road'],5.5,seed+4220,surface=TER.RESONANT_ROAD)
    LAND.worn_path(t,[(-29,-17),(23,-17)],5.0,seed+4221,surface=TER.RESONANT_ROAD)
    for _,_,x,z,width,depth in HOUSES:
        distance=np.maximum(abs(t.gx-x)-width/2-1.5,abs(t.gz-z)-depth/2-2.0)
        LAND.feather_level(t,distance,level,shoulder=7)
        t.surface[distance<0]=TER.BARRENS
        t.tree_block|=distance<3
        RC.grade_road(t,[(x,z+depth/2),(x,-29)],[level,level],
                      width=3.8,shoulder=4,surface=TER.RESONANT_ROAD,clearance=3)
    # The dry basin has three quiet expanses. Their margins, not each square
    # metre, carry debris and plants. The open ground also leaves combat room.
    quiet=np.zeros_like(t.height)
    for x,z,rx,rz in [(56,31,48,40),(205,-53,35,30),(-48,58,45,33)]:
        r=np.hypot((t.gx-x)/rx,(t.gz-z)/rz)
        quiet=np.maximum(quiet,1-LAND.smoothstep(.65,1.1,r))
    t.barrens_quiet=quiet
    t.tree_block|=quiet>.7
    for name,(points,heights,width) in BORDER_ROADS.items():
        source=[(float(PLAN.x.inverse(x)),float(PLAN.z.inverse(z))) for x,z in points]
        old_surface=t.surface.copy()
        RC.grade_road(t,source,heights,width=width/0.58,shoulder=52 if name=='whitehorn_ascent' else 25,
                      surface=TER.RESONANT_ROAD,clearance=7)
        d=LAND.distance_field(t,[source])
        shoulder=(d>width*.85)&(d<48)&(t.surface==TER.RESONANT_ROAD)
        t.surface[shoulder]=old_surface[shoulder]
    # Narrow worn spurs distinguish prospectors' footpaths from the cart roads.
    for name,points in REG.ROUTES.items():
        if name in ('observatory_approach','arrival_road'):continue
        width=3.1 if 'track' in name else 4.8
        LAND.worn_path(t,points,width,seed+N.stable_hash(name)%997,surface=TER.RESONANT_ROAD)


def geology_relation(x,z):
    """One bedrock family: massif, eastern fault, western gully shoulders."""
    return min(np.hypot((x-a)/rx,(z-b)/rz) for a,b,rx,rz in
               [(174,-304,85,110),(290,-150,44,110),(-110,-172,31,130),
                (146,-37,55,30),(144,90,55,34)])


def dress(build, seed, lod=None):
    import populate as POP
    t=build.terrain
    for mesh in build.meshes.values():
        for part in getattr(mesh,'all_parts',[mesh]):
            if part.material=='amethyst_resonant_road':part.material='alpine_gravel'
    # Named phenomena remain visible beside their trails. The old generic
    # corridor culler removed two complete fields while leaving dangling names.
    for index,position in [(0,(194,-300)),(5,(-5,-330))]:
        p=next(p for p in build.placements if p.node==f'Landmark_LevitatingShards_{index}')
        x,z=position
        p.position=(x,float(t.height_at(x,z)),z)
        entry=next(l for l in build.landmarks if l['id']==f'amethyst-levitating-shards-{index}')
        entry['position']=list(p.position)
    for i,(identity,name,x,z,width,depth) in enumerate(HOUSES):
        piece=ARCH.forest_lodge(seed=seed+4300+i,width=width,depth=depth,
                               storeys=1,porch=False,balcony=False,workshop=False,
                               preserve_materials=True)
        # Pale local rubble, salvaged timber and verdigris roofs put the same
        # construction vocabulary into everyday dwellings and civic buildings.
        palette=dict(POP.KIT_TO_REGION)
        palette.update({'timber_warm':'timber_grey','timber_grey':'timber_grey',
                        'timber_dark':'amethyst_storm_rock','carved_wood':'timber_grey'})
        POP._remap(piece,palette)
        node='Landmark_'+identity
        y=float(t.height_at(x,z))-.12
        build.add_mesh(node,piece)
        build.place(Placement(node,node,(x,y,z),collides=True,kind='building'))
        build.landmarks.append({'id':identity,'name':name,'node':node,'type':'building',
                                'position':[x,y,z]})
    for i,(x,z) in enumerate([(-30,-35),(-28,-35),(20,-36),(22,-35)]):
        piece=PROPS.barrel(seed=seed+i) if i%2 else PROPS.crate(seed=seed+i)
        POP._remap(piece,POP.KIT_TO_REGION)
        node=f'Prop_OutpostStores_{i}'
        build.add_mesh(node,piece)
        build.place(Placement(node,node,(x,float(t.height_at(x,z)),z),kind='prop',collides=True))
    # Filter the old independent litter lottery into related geological belts.
    keep=[]
    removed=0
    for p in build.placements:
        x,_,z=p.position
        if p.node.startswith(('Prop_BarrensRocks_','Prop_VeinScatter_','Crystal_Outcrop_')):
            quiet=float(t.barrens_quiet[np.clip(round((z-t.z0)/t.cell),0,t.rows-1),
                                        np.clip(round((x-t.x0)/t.cell),0,t.cols-1)])
            if geology_relation(x,z)>1.08 or quiet>.35:
                removed+=1
                continue
        keep.append(p)
    build.placements[:]=keep
    # Dry grass takes the leeward pockets and drainage margins; bare ridges and
    # the centres of the open basin remain exposed. Every tuft is seeded.
    rng=np.random.default_rng(seed+4400)
    for v in range(5):
        build.add_mesh(f'DryTuft_{v}',CANYON.dry_tuft(seed+v,material='thatch_reed'))
    count=0
    for i in range(420 if lod is None else 130):
        site=[(-61,-115,25,48),(36,71,37,24),(288,74,25,22)][i%3]
        x,z=rng.normal(site[0],site[2]),rng.normal(site[1],site[3])
        if not (REG.PLAY_MIN_X<x<REG.PLAY_MAX_X and REG.PLAY_MIN_Z<z<REG.PLAY_MAX_Z):continue
        if t.blocked_at(x,z) or t.height_at(x,z)<1.8:continue
        if int(t.surface_at(x,z)) not in (TER.BARRENS,TER.TURF):continue
        node=f'Scrub_LeeTuft_{count}'
        build.place(Placement(node,f'DryTuft_{i%5}',(x,float(t.height_at(x,z))-.03,z),
                              float(rng.uniform(0,math.tau)),float(rng.uniform(.85,1.7)),kind='scrub'))
        count+=1
    build.notes.append(f'Inhabited 384m basin: two sheltered dwellings, {count} lee tufts; '
                       f'{removed} unrelated scatter instances removed from quiet ground.')


def compact(build):
    # Recompose surveyed bridges between their new banks at full cart width.
    # Compressing their entire mesh also squeezed the ferry deck below 2m.
    survey=build.terrain._survey
    bridge_nodes={p.node for p in build.placements if p.node.startswith('Landmark_SurveyedBridge_')}
    build.placements[:]=[p for p in build.placements if p.node not in bridge_nodes]
    build.landmarks[:]=[p for p in build.landmarks if p.get('node') not in bridge_nodes]
    build.crossings[:]=[]
    for name in survey:build.meshes.pop(name,None)
    PLAN.apply(build)
    t=build.terrain
    # The full-size southern geode mouth used to project into the third cart
    # lane. Recess it into the eastern shoulder with its exploration entrance.
    moved={}
    for p in build.placements:
        if p.node == 'Landmark_GeodeCave_2' or p.node.startswith('Secret_barrens_cave_eyrie'):
            x,y,z=p.position
            dy=float(t.height_at(x+10,z)-t.height_at(x,z))
            p.position=(x+10,y+dy,z)
            moved[p.node]=dy
    seen=set()
    for entries in (build.landmarks,build.interactives,build.portals,build.spawns):
        for entry in entries:
            if id(entry) in seen:continue
            seen.add(id(entry))
            node=entry.get('node')
            if entry.get('secret')=='barrens-cave-eyrie':node='Secret_barrens_cave_eyrie'
            if node in moved and 'position' in entry:
                entry['position'][0]+=10
                entry['position'][1]+=moved[node]
                if 'serverTile' in entry:
                    entry['serverTile']=[math.floor(entry['position'][0]+116),
                                         math.floor(116-entry['position'][2])]
    t._survey={name:(np.array([[float(PLAN.x(x)),float(PLAN.z(z))] for x,z in points]),heights)
               for name,(points,heights) in survey.items()}
    layout.dress_crossings(build,0)
    for identity,position in PORTALS.items():
        entry=next(p for p in build.portals if p['id']==identity)
        entry['position']=list(position)
        entry['serverTile']=[round(position[0]+SERVER_ORIGIN[0]),round(SERVER_ORIGIN[1]-position[2])]
    roads=[[(float(PLAN.x(x)),float(PLAN.z(z))) for x,z in points] for points in REG.ROUTES.values()]
    roads.extend(v[0] for v in BORDER_ROADS.values())
    # Preserve human cart clearance after journey distances shrink.
    RC.clear_walk_corridors(build,[[[x,0,z] for x,z in points] for points in roads],
                            {'crystal':5.2,'shards':5.0,'rock':4.5,'scrub':3.5,'scatter':3.6,'prop':2.5})
    # Old landmark furniture at the inland pass is no longer the crossing.
    # Keep signs outside the shared scenery collar, and keep the geode approach
    # on the inland southern flank of the west shelf.
    removed=set()
    for p in build.placements:
        if p.node.startswith('March_') and any(road in p.node for road in ('north_pass','west_road','south_road')):
            if not p.node.endswith('_Signpost'):removed.add(p.node)
    build.placements[:]=[p for p in build.placements if p.node not in removed]
    for l in build.landmarks:
        if l.get('node') in removed:
            prefix=l['node'].split('_Station')[0].split('_Stone')[0]
            l['node']=prefix+'_Signpost'
            post=next((p for p in build.placements if p.node==l['node']),None)
            if post:l['position']=list(post.position)
    # The west gate's old tower remains a landmark above the route; the new
    # trigger belongs to the open road. Important entries are south/east of it.
    import streaming_borders as SB
    if hasattr(SB,'region_specs') and SB.region_specs('amethyst_barrens'):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_outer'))
        import outer_aprons
        outer_snapshot = outer_aprons.capture(build, 'amethyst_barrens')
        SB.apply(build,'amethyst_barrens')
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_northern'))
        import landscape_finish
        landscape_finish.apply(build, 'amethyst_barrens')
        import sunmane_approach
        sunmane_approach.apply(build)
        outer_aprons.apply(build, 'amethyst_barrens', outer_snapshot)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_finishing'))
        import geode_working_approach
        geode_working_approach.apply(build)
    used={p.mesh for p in build.placements}
    build.meshes={k:v for k,v in build.meshes.items() if k in used}


def content_layout():
    data=PLAN.metadata(deepcopy(layout.CONTENT_LAYOUT))
    data['npcs']={name:PLAN.point(p) for name,p in layout.CONTENT_LAYOUT['npcs'].items()}
    data['npcs'].update(deepcopy(NPC_COMPACT_POSTS))
    for category in ('harvest','wildlife'):
        data[category]={name:[[float(PLAN.x(x)),float(PLAN.z(z)),r*.72] for x,z,r in patches]
                        for name,patches in layout.CONTENT_LAYOUT[category].items()}
    # Four more metres of the eastern massif-foot apron fit the third
    # automaton with all road, resource, NPC and encounter spacing exclusions.
    data['wildlife']['arcane_crystal_automaton'][1][2] = 23.44
    data['requireFullWildlife']=True
    data['gauntlets']={'amethyst_gauntlet':{'keeperTile':[30,332],'returnTile':[41,333]}}
    data['primaryArrivalOnly']=True
    return data


def roads():
    result=[]
    for name,points in REG.ROUTES.items():
        result.append({'id':name,'waypoints':[PLAN.point([x,0,z]) for x,z in points]})
    for name,(points,heights,width) in BORDER_ROADS.items():
        result.append({'id':name,'width':width,'waypoints':[[x,y,z] for (x,z),y in zip(points,heights)]})
    return result
