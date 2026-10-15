"""Authored dry approaches around Amberwood's retained tree and hillside workyards.

These are visible earth roads with local cut/fill and broad shoulders. The
canopy compound, kiln buildings and authored discovery identities stay fixed.

The chapel hill's cluster (chapel, boundary stone, lookouts, ridge camp,
arches, coppice yard, cinder field and the two secrets) stands 132 m west and
139 m south of the plateau it was authored on, so the Whitehorn Range can take
the ground north-east of Amberwood as its tail: continent-edits.json carries
every loose placement and diagonal-plan.json's assembly_sites carries the ridge
camp. The routes below moved with it on the same translation. Numbers quoted in
these comments were measured before that move, on the old plateau.
"""
from __future__ import annotations
import numpy as np
import landscape as L
from world_layout import corridor_grade,graded_profile,SOLID_MAXIMUM_AREA_SQUARE_METRES
from four_gates_support import path_field

REGION='amberwood'
# Routed branches graded as approaches (approach name -> road id). The ids are
# maps.txt line numbers and do not move with the cluster; the discoveries
# themselves do, because content.mapped_server_point resolves a server tile
# through the nearest retained object in the SOURCE frame and both tiles land
# inside a secret that carries the cluster's shift (473 in Secret_amber_boar_run,
# 481 in Secret_amber_undercut). On the old plateau the ridge camp's branch
# (473, the boar-run door) climbed the plateau's north feather from whichever
# public road stood nearest. The shared road solve holds a footing feather at
# its blended ground, so the branch climbed it at 1.1-1.4 once the terrain terms
# took the seam and door roads off the ridge (the fifteenth's three roads had
# graded that hillside together). The undercut secret's branch (481) climbed the
# same feather 2-3 m beside the camp branch. The relocated ground is forest
# floor falling 15-25 m over 120 m towards the kelp landing, so branch_runs
# should find few steep runs to regrade there until the door and seam roads
# build their own feathers again; the beds stay one authored earth surface
# each, like the paths below, and neither fades beside the other.
APPROACH_BRANCHES={'amber-ridge-camp-branch':'discovery-amberwood-473','amber-undercut-branch':'discovery-amberwood-481'}
APPROACH_GRADE=.45
# A branch approach leaves other roads' corridors as the shared solve left
# them: its cut and fill fade out from APPROACH_OTHER_ROAD_CLEAR to
# APPROACH_OTHER_ROAD_FADE metres of any other centreline. Measured on the old
# plateau without the fade: the camp branch ran 20 m beside the cinder chapel
# door road, its shoulders raised the plateau edge 2-4.5 m and the door road's
# climb steepened from .65 to .84, so the whole chapel hill lost its served
# corridor. The two branches still share ground with the chapel's door road at
# the new site, so the fade is kept; it has not been re-measured there.
APPROACH_OTHER_ROAD_CLEAR=2.5
APPROACH_OTHER_ROAD_FADE=7.
# A branch approach is regraded along its steep runs only: each run of
# stations steeper than the grade, padded by APPROACH_RUN_PAD_METRES and
# widened until its ends stay on the natural ground, gets a local bounded
# profile; the corridor weight fades to nothing APPROACH_RUN_FADE_METRES past
# a run. Measured on the old plateau with the whole line regraded: the
# branches' shoulders imposed their level on its south side (2-3 m of fill at
# the old x 596-624, z 494-502, the moved x 464-492, z 633-641) and the step at
# its north edge cut the plateau, the chapel foot and the camp approach off the
# hub reach.
APPROACH_RUN_PAD_METRES=6.
APPROACH_RUN_FADE_METRES=3.
# Loose yard dressing that an approach's earth surface runs under wherever it
# stands: ruin fragments, log piles and carts are a name family, not a lookup of
# fixed placements, so moving one does not change what this stage does with it.
# The prefixes are spelled without a trailing underscore, as the ruin fragments
# already were, so object_edits.catalogue does not read the family as a per-node
# reference and refuse to move the coppice yard with the rest of the chapel hill.
# Across every certified library these three match exactly the 34 nodes the
# underscored spellings matched.
LOOSE_DRESSING=('Stone_RuinFragment','LogPile','Cart')


def branch_routes(world):
    """The routed branches graded as approaches, by approach name, as XZ stations."""
    routes={}
    for name,road_id in APPROACH_BRANCHES.items():
        road=next((r for r in world.roads if r['id']==road_id),None)
        if road is None:raise ValueError(f'{name}: branch {road_id} was not routed')
        routes[name]=np.asarray(road['points'],float)[:,[0,2]]
    return routes


def branch_profile(levels,stations,maximum_grade=APPROACH_GRADE):
    """A routed branch keeps its ends and its general rise; the feather step is cut and filled to the grade."""
    return graded_profile(levels,stations,maximum_grade=maximum_grade)


def branch_runs(levels,stations,maximum_grade=APPROACH_GRADE,pad=APPROACH_RUN_PAD_METRES):
    """(profile, runs): the station levels with every steep run regraded locally, and the along-line
    intervals [start, stop] the runs cover once padded and widened to keep their ends on the natural ground.
    """
    levels=np.asarray(levels,float);stations=np.asarray(stations,float);profile=levels.copy()
    grades=np.abs(np.diff(levels))/np.maximum(np.diff(stations),1e-6)
    runs=[];i=0
    while i<len(grades):
        if grades[i]<=maximum_grade:i+=1;continue
        j=i
        while j+1<len(grades) and grades[j+1]>maximum_grade:j+=1
        start,stop=stations[i]-pad,stations[j+1]+pad
        if runs and start<=runs[-1][1]:runs[-1][1]=stop
        else:runs.append([start,stop])
        i=j+1
    for run in runs:
        ia=int(np.searchsorted(stations,run[0]));ib=int(np.searchsorted(stations,run[1],side='right'))-1
        ia=max(0,min(ia,len(stations)-2));ib=min(len(stations)-1,max(ib,ia+1))
        while abs(levels[ib]-levels[ia])/max(stations[ib]-stations[ia],1e-6)>maximum_grade and (ia>0 or ib<len(stations)-1):
            ia=max(0,ia-1);ib=min(len(stations)-1,ib+1)
        profile[ia:ib+1]=branch_profile(levels[ia:ib+1],stations[ia:ib+1],maximum_grade)
        run[0],run[1]=float(stations[ia]),float(stations[ib])
    return profile,runs


def branch_need(along,runs,fade=APPROACH_RUN_FADE_METRES):
    """How much of the corridor regrade each vertex takes: 1 inside a steep run, fading to 0 within ``fade`` metres."""
    along=np.asarray(along,float);need=np.zeros(along.shape)
    for start,stop in runs:
        outside=np.maximum(0.,np.maximum(start-along,along-stop))
        need=np.maximum(need,np.clip(1.-outside/fade,0.,1.))
    return need


def other_road_distance(world,exclude,x,z,margin=20.):
    """Metres from each vertex to the nearest centreline of any road not named in ``exclude``."""
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    low=np.array([x.min()-margin,z.min()-margin]);high=np.array([x.max()+margin,z.max()+margin])
    distance=np.full(x.shape,np.inf)
    for road in world.roads:
        if road['id'] in exclude:continue
        points=np.asarray(road['points'],float)[:,[0,2]]
        if len(points)<2 or not ((points>=low)&(points<=high)).all(axis=1).any():continue
        distance=np.minimum(distance,path_field(points,np.zeros(len(points)),x,z)[1])
    return distance


def authored_routes(world):
    offset=np.asarray(world.regions[REGION]['center'])-[510.,540.]
    return {
        'amber-side-kilnyard':np.array([[638,613],[634,617],[630,624],[629,634]],float)+offset,
        # The cluster's own routes carry the same (-132, +139) translation as its
        # placements, so the chapel foot, the ruins, the camp and the arches keep
        # their relation to the roads that serve them. The plateau they climbed is
        # gone: on the natural ground the camp route falls from .59 to .10 and the
        # undercut path from 1.05 to .14, both inside the corridor grade, while the
        # chapel climb was already gentle (.05 to .07). The authored beds still
        # matter because the shared solve's door and branch roads raise feathers
        # across them wherever they meet.
        'amber-chapel-climb':np.array([[494,630],[502,630],[509,633],[514,642],[522,649],[531,650],[534,648]],float)+offset,
        'amber-motherroot-yard':np.array([[510,522],[510,517],[512,513]],float)+offset,
        'amber-moot-path':np.array([[496,500],[495,505],[500,508],[503,504]],float)+offset,
        'amber-ridge-camp':np.array([[472,574],[473,584],[467,591],[459,595],[452,595],[446,589]],float)+offset,
        # The undercut path bends east between the two ruins (33.8 m): with the
        # structures registered where they stand (content.register_obstacles) the
        # cinder chapel door road takes its direct line to the chapel foot and the
        # two roads stay apart. On the plateau the foot at (626, 491) lay 26 m below
        # the chapel, the bend held the path to .45 and the former 28 m line climbed
        # at .54; the moved line rises 5 m over the same 33.8 m, so the bend now
        # earns its keep by separating the roads rather than by the grade.
        'amber-undercut-path':np.array([[494,630],[502,630],[509,626],[515,625],[518,620],[515,615]],float)+offset,
        # The village yard's approach: from the hub-connected ground west of
        # the canopy walkway's foot, south of Canopy Platform 2, over the low
        # hump beside the walkway end (h 45) and down to the root ramp's foot
        # (h 41, amberwood_access.ROOT_RAMP_FOOT). The yard is a 5 m hollow
        # between that hump and the tree's roots; the fifteenth and the terms
        # measurements reached it only where a routed branch's shoulder
        # happened to fill the ground beside the walkway end.
        'amber-yard-approach':np.array([[462,469],[474,471],[484,473]],float)+offset,
        # 'amber-chapel-bank' is gone with the plateau. It carried the cinder
        # chapel door road up the plateau's north bank, 8 m of rise over 14 m
        # that the shared solve left at .62-.67 (the served fold blocks .65), so
        # the chapel, the estate door, the undercut secret and the ridge camp
        # behind them were served by rounding or not at all. The same line at the
        # moved site rises 5 m over 25 m, inside the corridor grade and inside
        # the served fold, so there is no bank to author; a flat authored surface
        # there would only raise ground the door road does not need.
    }


def prepare_amberwood_routes(world,content):
    """Add the alternate workyard approaches before the shared road grade solve."""
    if REGION not in world.ids:return {}
    paths=authored_routes(world)
    for name,path in paths.items():
        if any(r['id']==name for r in world.roads):raise ValueError('Amber approaches were already prepared')
        world.add_road(path,width=2.2,name=name)
    return {'roads':list(paths)}


def apply_amberwood_support(world,content):
    if REGION not in world.ids:return {}
    rows=[]
    for name,points in list(authored_routes(world).items())+list(branch_routes(world).items()):
        # Final road ends join the actual current earth, not a cached camera Y.
        levels=world.height_at(points[:,0],points[:,1])
        stations=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
        branch=name in APPROACH_BRANCHES;runs=[]
        if branch:profile,runs=branch_runs(levels,stations)
        else:profile=np.interp(stations,[0,stations[-1]],[levels[0],levels[-1]])
        if abs(levels[-1]-levels[0])/stations[-1]>(APPROACH_GRADE if branch else .48):
            raise ValueError(f'{name}: authored climb must be lengthened')
        half_width=3.6;shoulder=10.
        low=points.min(axis=0)-half_width-shoulder;high=points.max(axis=0)+half_width+shoulder
        ix0,iz0=np.maximum(0,np.floor((low-[world.x0,world.z0])/2).astype(int))
        ix1,iz1=np.minimum([len(world.x),len(world.z)],np.ceil((high-[world.x0,world.z0])/2).astype(int)+1)
        sl=np.s_[iz0:iz1,ix0:ix1];gx,gz=world.gx[sl],world.gz[sl]
        target,distance,along,length=path_field(points,profile,gx,gz)
        active=distance<=half_width
        target=corridor_grade(target,active,maximum_grade=.45)
        weight=(1-L.smoothstep(half_width,half_width+shoulder,distance))
        weight*=~world.water['mask'][sl]
        weight*=world.owner_at(gx,gz)==world.ids.index(REGION)
        # Architectural interiors keep their foundation. The Motherroot's
        # surface roots remain visible outside the small worn path opening.
        # Boxes larger than the router's compact-solid area (the Great Tree's
        # hollow hall and its wood, 61 m across) cover open ground: they are
        # not interiors, and the roads already cross them.
        occupied=np.zeros_like(weight,dtype=bool)
        for obj in content.objects:
            if obj['region']!=REGION or not obj.get('collides') or obj.get('assembly'):continue
            if obj['node'].startswith(LOOSE_DRESSING):continue
            if obj.get('kind') in ('tree','rock','foliage','undergrowth','scrub'):continue
            a,b=obj['low'],obj['high']
            if (b[0]-a[0])*(b[2]-a[2])>SOLID_MAXIMUM_AREA_SQUARE_METRES:continue
            occupied|=(gx>=a[0]-.25)&(gx<=b[0]+.25)&(gz>=a[2]-.25)&(gz<=b[2]+.25)
        weight*=~occupied
        if branch:
            weight*=branch_need(along,runs)
            siblings=set(APPROACH_BRANCHES)|set(APPROACH_BRANCHES.values())
            weight*=L.smoothstep(APPROACH_OTHER_ROAD_CLEAR,APPROACH_OTHER_ROAD_FADE,other_road_distance(world,siblings,gx,gz))
        # Routed roads crossing an approach are regraded with it: the approach
        # is one authored earth surface and the corridors it crosses become
        # part of it. Two guards were tried in the fifteenth publication and
        # each stepped a served corridor at the crossing (excluding the other
        # road's core cut the ridge camp approach at its own stations; blending
        # into the core made the kilnyard yard steep beside the Hamlet Elder).
        old=world.height[sl].copy();new=old*(1-weight)+target*weight
        world.height[sl]=new
        rows.append({'road':name,'lengthMetres':float(length),'changedVertices':int(np.count_nonzero(abs(new-old)>1e-8)),
                     'maximumCut':float(np.max(old-new,initial=0)),'maximumFill':float(np.max(new-old,initial=0))})
        road=next((r for r in world.roads if r['id']==APPROACH_BRANCHES.get(name,name)),None)
        if road is not None:
            p=np.asarray(road['points']);p[:,1]=world.height_at(p[:,0],p[:,2]);road['points']=p.tolist()
    world.amberwood_support={'approaches':rows}
    from amberwood_access import refresh_amberwood_access_heights
    refresh_amberwood_access_heights(world,content)
    return world.amberwood_support
