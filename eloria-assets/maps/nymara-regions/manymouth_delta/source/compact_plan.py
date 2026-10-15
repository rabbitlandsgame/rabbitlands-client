"""Manymouth's shorter distributary fan, authored before GLB export.

The town/market retain metre-for-metre spacing. Outer water journeys contract;
houses, halls, shrines and their local geometry keep their original size. The
timber network is surveyed again at its full 3.8 m width, including the porches
of every retained house. This field is also the server content migration.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import numpy as np

from compact_landscape import Axis, CompactLandscape
from amberwood import terrain as TER, waterfront as WF, routecraft as RC, materials as MAT
import region as REG
import layout as LAY
import deltakit as DK
import stiltkit as SK

REVISION = 'manymouth-compact-v1'
LEGACY_ORIGIN = (174.,174.)
LEGACY_CELLS = 576
NATIVE_ORIGIN = (138.,120.)
NATIVE_CELLS = 480
BOUNDS = [[-138.,-276.],[342.,120.]]
PLAN = CompactLandscape(Axis(-174,402,-138,342,(-56,95)),
                        Axis(-402,174,-276,120,(-91,18)),LEGACY_ORIGIN,NATIVE_ORIGIN)
LEGACY_CONSTANTS = {name:deepcopy(getattr(REG,name)) for name in
    ('SERVER_CELLS','SERVER_ORIGIN','PLAY_MIN_X','PLAY_MAX_X','PLAY_MIN_Z','PLAY_MAX_Z','SPAWN')}
GATES = {
    'west-landing':('sea_landing',[-113.5,3.14,-281.5]),
    'south-landing':('west_hamlet',[-131.5,4.,.5]),
    'east-landing':('east_watch',[334.5,4.,-63.5]),
}
# Standing posts sampled on the compact geometry with actor-centre guard and
# the server's staged heights. Two props move to clear adjacent silt below.
SECRET_STANDING_TILES = {
    'delta-lotus-hollow':(260,261),'delta-paddy-garden':(141,301),
    'delta-moot-vault':(195,168),'delta-crab-pit':(298,87),
    'delta-study-school':(299,215),'delta-temple-spring':(370,324),
    'delta-watch-butts':(450,138),'delta-stelae-reliquary':(385,287),
    'delta-shrine-well':(234,23),'delta-arch-focus':(282,240),
    'delta-bund-run':(132,303),'delta-waystone':(333,138),
    'delta-banyan-eyrie':(190,267),'delta-rootrun-mouth':(212,286),
}


def legacy_tile_to_native(tile):
    """Pure old 576-grid tile -> compact native tile (before continent padding)."""
    x,z=float(tile[0])-174.,174.-float(tile[1])
    return [round(float(PLAN.x(x))+138.),round(120.-float(PLAN.z(z)))]


def contract(ready=False, arrival=(183,162)):
    return dict(revision=REVISION,ready=ready,legacyOrigin=list(LEGACY_ORIGIN),
        legacyCells=[LEGACY_CELLS]*2,nativeOrigin=list(NATIVE_ORIGIN),
        nativeCells=[NATIVE_CELLS]*2,nativeArrival=list(arrival),nativeMapBounds=BOUNDS,
        axes={'x':{'old':PLAN.x.old.tolist(),'new':PLAN.x.new.tolist()},
              'z':{'old':PLAN.z.old.tolist(),'new':PLAN.z.new.tolist()}})


def restore_legacy_frame():
    for name,value in LEGACY_CONSTANTS.items():setattr(REG,name,deepcopy(value))


def install_native_frame():
    REG.SERVER_ORIGIN=NATIVE_ORIGIN;REG.SERVER_CELLS=NATIVE_CELLS
    REG.PLAY_MIN_X,REG.PLAY_MIN_Z=BOUNDS[0]
    REG.PLAY_MAX_X,REG.PLAY_MAX_Z=BOUNDS[1][0]-1,BOUNDS[1][1]
    spawn=PLAN.point([REG.ANCHORS['stilt_town'][0],0,REG.ANCHORS['stilt_town'][1]])
    REG.SPAWN=(spawn[0],spawn[2])


def _mapped_network(old):
    centres={name:np.asarray(PLAN.point(c),float) for name,c in old['centres'].items()}
    # The temple and cavern entrances are offsets from full-size monuments.
    # Preserve those local offsets, not a compressed fraction of a stair.
    for name in ('green_temple','cave_mouth'):
        x,z=REG.ANCHORS[name]
        base=np.asarray(PLAN.point([x,0,z]))
        centres[name][[0,2]]=base[[0,2]]+old['centres'][name][[0,2]]-np.array([x,z])
    surveys=[]
    for a,b,stations,_ in old['surveys']:
        mapped=np.asarray([PLAN.point(p) for p in stations])
        # Move each last short run with its unchanged-size monumental landing.
        for name,index in ((a,0),(b,-1)):
            difference=centres[name]-np.asarray(PLAN.point(old['centres'][name]))
            mapped[index]+=difference
            if len(mapped)>2:mapped[1 if index==0 else -2]+=difference*.35
        if (a,b)==('green_temple','temple_quay'):
            # The original two landings left a near-vertical 13 m connection.
            # A processional timber switchback climbs the west bank without
            # changing the temple, its stair foot, or the inhabited quay.
            mapped=np.array([centres[a],[228.,centres[a][1],-219.],
                [214.,9.8,-225.],[207.,7.5,-220.],[211.,4.,-211.],
                [225.,1.75,-205.],centres[b]])
        surveys.append((a,b,mapped))
    for portal,(start,end) in GATES.items():
        target='continent_'+portal
        centres[target]=np.asarray(end,float)
        surveys.append((start,target,np.array([centres[start],centres[target]])))
    radii=deepcopy(old['radii'])
    # End directly on the shared deck boundary; no extra landing overlaps it.
    for portal in GATES:radii['continent_'+portal]=0.
    return centres,radii,surveys


def connector_requests(build):
    """Use native timber spans inland, widening only at their shared collars."""
    identities={'grey-manymouth':'west-landing',
                'westhaven-manymouth':'south-landing',
                'ssarathi-manymouth':'east-landing'}
    frames={s['id']:s for s in build.streaming_borders}
    for road in build.geography_roads:
        portal=identities.get(road['id'])
        if portal is None:continue
        start=GATES[portal][0]
        survey=next(s for a,b,s,_ in build.network['surveys']
                    if a==start and b=='continent_'+portal)
        first,last=np.asarray(survey[0],float),np.asarray(survey[-1],float)
        length=float(np.linalg.norm(last[[0,2]]-first[[0,2]]))
        if length<=6.:raise ValueError('Native timber approach is too short for its collar taper')
        taper=last+(first-last)*(6./length)
        stations=np.array([build.network['centres'][start],first,taper,last,frames[road['id']]['anchor']],float)
        # The shared finisher's controls describe the bed, 3 cm below the skin.
        stations[:,1]-=.03
        road['contactStations']=stations.tolist()
        road['contactWidths']=[3.8,3.8,3.8,8.5,8.5]
        road['nativeBoardwalk']={'survey':[start,'continent_'+portal],
                                'clearWidth':3.8,'collarTaperMetres':6.}


def _bed(build,stations,width):
    t=build.terrain;plan=stations[:,[0,2]]
    distance,along=TER._polyline_distance(t.gx,t.gz,plan)
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(plan,axis=0),axis=1))]
    target=np.interp(along,lengths/lengths[-1],stations[:,1])-.32
    # A physical recess keeps the actual deck above its bank after compaction.
    mask=distance<width/2+.45
    t.height=np.where(mask,np.minimum(t.height,target),t.height)
    t.tree_block|=distance<width/2+3.5


def _network(build,old):
    centres,radii,surveys=_mapped_network(old)
    ports={name:[] for name in centres};resolved=[];segments=[]
    for a,b,stations in surveys:
        first=LAY._section(centres[a],stations[1,[0,2]],LAY.WIDTH,radii[a],LAY.PLATFORMS.get(a))
        if radii[b]==0:
            direction=stations[-1,[0,2]]-stations[-2,[0,2]];direction/=np.linalg.norm(direction)
            normal=np.array([-direction[1],0,direction[0]])
            last=[centres[b]-normal*LAY.WIDTH/2,centres[b]+normal*LAY.WIDTH/2]
        else:last=LAY._section(centres[b],stations[-2,[0,2]],LAY.WIDTH,radii[b],LAY.PLATFORMS.get(b))
        ports[a].append(first);ports[b].append(last)
        stations[0]=np.mean(first,axis=0);stations[-1]=np.mean(last,axis=0)
        ends=(first,list(reversed(last))) if radii[b] else (first,last)
        _bed(build,stations,LAY.WIDTH)
        key='Survey_'+a+'__'+b
        build.add_mesh(key,WF.piled_route(stations,LAY.WIDTH,DK.TEAK,SK.ROPE,bed=build.terrain.height_at,ends=ends))
        build.place(REG.Placement(node=key,mesh=key,position=(0,0,0),kind='structure'))
        resolved.append((a,b,stations,ends))
        for p,q in zip(stations,stations[1:]):
            segments.append({'a':tuple(p[[0,2]]),'b':tuple(q[[0,2]]),'level':float((p[1]+q[1])/2),
                'angle':math.atan2(q[2]-p[2],q[0]-p[0]),'route':(a,b)})
    for name,c in centres.items():
        if radii[name]==0:continue
        r=radii[name] if name not in LAY.PLATFORMS else max(LAY.PLATFORMS[name][:2])
        mask=np.hypot(build.terrain.gx-c[0],build.terrain.gz-c[2])<r+.5
        build.terrain.height=np.where(mask,np.minimum(build.terrain.height,c[1]-.32),build.terrain.height)
        if name in LAY.PLATFORMS:continue
        key='Landing_'+name
        build.add_mesh(key,WF.junction(c,ports[name],radii[name],DK.TEAK,
            foot=min(float(build.terrain.height_at(c[0],c[2]))-.5,-1)))
        build.place(REG.Placement(node=key,mesh=key,position=(0,0,0),kind='structure'))
    return dict(centres=centres,radii=radii,surveys=resolved,segments=segments,
        points={name:tuple(c[[0,2]]) for name,c in centres.items()},
        levels={name:float(c[1]) for name,c in centres.items()})


def _houses(build,network):
    """Seat the same named houses beside the rebuilt, full-width boardwalk."""
    houses=[p for p in build.placements if p.kind=='building' and '_house_' in p.node]
    occupied=[];moves=[]
    lines=[s for _,_,s,_ in network['surveys']]
    landmarks=[p for p in build.placements if p.kind=='landmark' and p.node.startswith('Landmark_')]
    for house in houses:
        proposed=np.asarray(house.position,float);candidates=[]
        for stations in lines:
            for a,b in zip(stations,stations[1:]):
                d=b-a;length=float(np.linalg.norm(d[[0,2]]));unit=d/length
                along=float(np.dot(proposed[[0,2]]-a[[0,2]],unit[[0,2]]))
                if np.linalg.norm((a+unit*np.clip(along,0,length)-proposed)[[0,2]])>42:continue
                for offset in (0,-3,3,-6,6,-9,9,-12,12,-18,18,-24,24):
                    value=np.clip(along+offset,1.,max(1.,length-1.))
                    centre=a+unit*value
                    for sign in (-1,1):
                        side=np.array([-unit[2]*sign,0,unit[0]*sign])
                        point=centre+side*7.6
                        cost=float(np.linalg.norm((point-proposed)[[0,2]]))
                        if cost>34 or any(np.linalg.norm((point-q)[[0,2]])<10.5 for q in occupied):continue
                        if any(np.linalg.norm((point-np.asarray(p.position))[[0,2]])<10.5 for p in landmarks):continue
                        if any(float(TER._polyline_distance(np.asarray(point[0]),np.asarray(point[2]),s[:,[0,2]])[0])<6.0 for s in lines):continue
                        candidates.append((cost,point,centre,side))
        if not candidates:raise ValueError('No separated stilt-house post for '+house.node)
        cost,point,centre,side=min(candidates,key=lambda v:v[0])
        house.position=tuple(point);house.rotation_y=math.atan2(-side[0],-side[2])
        occupied.append(point);moves.append(dict(node=house.node,metres=round(cost,3)))
        near=centre+side*LAY.WIDTH/2;far=point-side*2.3
        key=house.node.replace('_house_','_porch_')
        _bed(build,np.array([near,far]),2.6)
        build.add_mesh(key,WF.piled_route([near,far],2.6,DK.TEAK,SK.ROPE,bed=build.terrain.height_at,rails=False))
        build.place(REG.Placement(node=key,mesh=key,position=(0,0,0),kind='structure'))
    return moves


def content_layout():
    result=PLAN.metadata(deepcopy(LAY.CONTENT_LAYOUT))
    result['requireFullWildlife']=True
    result['npcs']={name:PLAN.point(p) for name,p in LAY.CONTENT_LAYOUT['npcs'].items()}
    for bucket in ('wildlife','harvest'):
        result[bucket]={name:[[round(float(PLAN.x(x)),4),round(float(PLAN.z(z)),4),r]
            for x,z,r in discs] for name,discs in LAY.CONTENT_LAYOUT[bucket].items()}
    return result


def _secret_access(build):
    """Keep remote discovery props accessible on their original silt pockets."""
    selected={'delta-study-school','delta-stelae-reliquary',
              'delta-banyan-eyrie','delta-rootrun-mouth'}
    routes=list(build.network['surveys'])
    for entry in build.interactives:
        if entry.get('secret') not in selected:continue
        prop=np.asarray(entry['position'],float);candidates=[]
        for a,b,stations,_ in routes:
            for p,q in zip(stations,stations[1:]):
                d=q-p;length=np.linalg.norm(d[[0,2]])
                if length<4:continue
                unit=d/length
                along=np.clip(np.dot(prop[[0,2]]-p[[0,2]],unit[[0,2]]),1.5,length-1.5)
                centre=p+unit*along
                candidates.append((np.linalg.norm((centre-prop)[[0,2]]),a,b,centre,unit))
        _,a,b,centre,unit=min(candidates,key=lambda p:p[0])
        side=np.array([-unit[2],0,unit[0]])
        if np.dot(side,prop-centre)<0:side=-side
        start=centre+side*LAY.WIDTH/2
        toward=start-prop;toward[1]=0;toward/=np.linalg.norm(toward)
        end=prop+toward*2.8
        end[1]=max(1.3,float(build.terrain.height_at(end[0],end[2]))+.22)
        width=2.8;normal=np.array([toward[2],0,-toward[0]])
        first=[start-unit*width/2,start+unit*width/2]
        first.sort(key=lambda p:float(np.dot(p-start,normal)))
        last=[end-normal*width/2,end+normal*width/2]
        # Cross sections retain the exact native road edge at the T junction.
        stations=np.array([start,end]);key='SecretAccess_'+entry['secret'].replace('-','_')
        _bed(build,stations,width)
        build.add_mesh(key,WF.piled_route(stations,width,DK.TEAK,SK.ROPE,
            bed=build.terrain.height_at,ends=(first,last),rails=False))
        build.place(REG.Placement(node=key,mesh=key,position=(0,0,0),kind='structure'))
        build.network['surveys'].append(('access_'+a,entry['secret'],stations,(first,last)))
        entry['serverTile']=[round(end[0]+138),round(120-end[2])]


def _open_east_landing_canopy(build):
    """Leave a readable opening above the east watch landing and timber road.

    Full-size palms compressed together here. Keep the two mature specimens
    on the southern forest verge, and use smaller edge crowns beside them.
    Their trunks remain seated on the actual silt; other forest is unchanged.
    """
    verge={'palm_0845':(308.,-9.),
           'palm_0957':(324.4403,-17.892)}
    edge={'palm_0049','palm_0802'}
    for placement in build.placements:
        if placement.node in verge:
            x,z=verge[placement.node]
            placement.position=(x,float(build.terrain.height_at(x,z)),z)
        if placement.node in edge:
            placement.scale*=.8


def apply(build,materials):
    old=deepcopy(build.network)
    # These are world-space timber surveys, not scaled prefabs. Re-author their
    # widths and connections after the source terrain field has been resampled.
    build.placements=[p for p in build.placements if not
        (p.node.startswith(('Survey_','Landing_')) or '_porch_' in p.node)]
    PLAN.apply(build)
    build.network=_network(build,old)
    house_moves=_houses(build,build.network)
    _secret_access(build)
    _open_east_landing_canopy(build)
    # The old march stone is part of the sea-landing furniture. Its pedestal
    # stands on that deck; the seabed is no longer its contact surface.
    march=next(p for p in build.placements if p.node=='March_west_landing_Stone')
    march.position=(march.position[0],float(build.network['centres']['sea_landing'][1]),march.position[2])
    for entry in build.landmarks:
        if entry.get('id')=='march-west-landing':entry['position']=list(march.position)
    # Two discoveries remain on their low banks, clear of the new temple
    # trestle and the south hamlet's full-size house footprint respectively.
    moved_secrets={'delta-temple-spring':(234.5,-204.5),
                   'delta-crab-pit':(160.5,34.5)}
    for entry in build.interactives:
        if entry.get('secret') in SECRET_STANDING_TILES:
            entry['serverTile']=list(SECRET_STANDING_TILES[entry['secret']])
        if entry.get('secret') in moved_secrets:
            x,z=moved_secrets[entry['secret']]
            point=[x,float(build.terrain.height_at(x,z)),z]
            node='Secret_'+entry['secret'].replace('-','_')
            next(p for p in build.placements if p.node==node).position=tuple(point)
            entry['position']=point
    # Narrow channels use one continuous water surface; land occludes it.
    # This removes coarse six-metre square holes at compressed silt banks.
    t=build.terrain
    build.water_meshes={'Water_Delta':TER.water_plane(t,0,t.x0-40,t.z0-40,
        t.x0+t.size_x+40,t.z0+t.size_z+40,material=DK.DELTA_WATER,cell=6.,only_below=False)}
    build.terrain_meshes=t.build_meshes(uv_scale=.28,blend_edges=True,
        material_suffix=MAT.GROUND_SUFFIX,materials=materials)
    build.content_layout=content_layout()
    # Correct the few full-size monumental offsets in semantic posts too.
    doors={'labyrinth-mouth':'cave_mouth','temple-sanctum-door':'green_temple'}
    for bucket in (build.portals,build.spawns):
        for p in bucket:
            if p['id'] in doors:
                point=build.network['centres'][doors[p['id']]].tolist()
                p['position']=point;p['serverTile']=[round(point[0]+138),round(120-point[2])]
            if p['id'] in GATES:
                point=build.network['centres']['continent_'+p['id']].tolist()
                p['position']=point;p['serverTile']=[round(point[0]+138),round(120-point[2])]
    for name,anchor in [('Green Temple Warden Vashi-Lo','green_temple'),('Labyrinth Guide Hess-Uru','cave_mouth')]:
        build.content_layout['npcs'][name]=build.network['centres'][anchor].tolist()
    # The guide works beside the mouth; his actor must not occupy its trigger.
    build.content_layout['npcs']['Labyrinth Guide Hess-Uru'][0]+=2.
    build.content_layout['npcs']['South Shrine Cantor Tem-Ossa'][0]+=2.
    lines=[s.tolist() for _,_,s,_ in build.network['surveys']]
    RC.clear_walk_corridors(build,lines,{'tree':5.2,'foliage':4.2,'prop':2.6,'rock':3.5})
    retained={p.node for p in build.placements}
    missing=['Secret_'+e['secret'].replace('-','_') for e in build.interactives
        if e.get('kind')=='secret' and 'Secret_'+e['secret'].replace('-','_') not in retained]
    if missing:raise ValueError('A discovery prop was removed by route clearance: '+', '.join(missing))
    if hasattr(build,'_walk_triangles'):del build._walk_triangles
    build.compact_revision=REVISION
    build.compact_report={'revision':REVISION,'mapBounds':BOUNDS,'housesRetained':len(house_moves),
        'houseMoves':house_moves,'routes':len(build.network['surveys']),
        'nativeArrival':legacy_tile_to_native([210,222])}
    build.notes.append('Compact480x396: full-size timber roads, houses and halls; shortened outer channels.')
    install_native_frame()
    return build


if __name__=='__main__':
    path=Path(__file__).with_name('continent-migration.json')
    path.write_text(json.dumps(contract(),indent=2)+'\n',encoding='utf-8')
