"""Grey Moors crossing consolidation: retire duplicate spans, keep their identities.

Three surveyed boardwalk fragments (gate, centre, south) crossed the same
headwater outlet and southern pool that the continental bridge union now
spans. Their retained floors sat beside, or metres above, the generated deck.
``content.retained_source_placements`` retires exactly those roots before
assembly grouping, so no old foundation influence survives a fresh
composition. Four authoritative server records used those spans as nearest
deformation anchors; their expected global positions are authored here
explicitly, so the retirement cannot displace them. At geometry export the
three generic landmark identities are re-associated with the actual emitted
crossing floors, using their real node names and floor heights.

The other spans, the causeway bridges, the boardwalk cache discovery and the
Moor hydraulic/landform sources are unchanged by this module.
"""
from __future__ import annotations
import numpy as np
import scene_io as S
from content import RETIRED_GREY_SPANS
from mirror_support import upper_floor_field
import landscape as L

REGION='grey_moors'
CACHE='Secret_moor_boardwalk_cache'
BOARDWALK_PREFIX='Landmark_boardwalk_'
CROSSING_PREFIX='Walk_ContinentalBridgeUnion_'
SAMPLE_METRES=1.
# R1: two Moorwater bridge sites remain (the hub crossing and the southern pool); the retired centre span stands
# 56.7 m from the hub crossing's floor, the nearest emitted floor.
MAXIMUM_ASSOCIATION_METRES=64.
# Expected global XZ of the four records on the last composition that still
# retained the spans (ninth), replayed read-only in
# diagnostic-moor-southern-rims/combined-retirement-ninth.json; they equal the
# seventh contract field within 3e-14 m. Y follows the composed terrain.
AUTHORED_POINTS={
    (145,178):(237.635264,373.459628),  # harvesting.txt:212:64 Hearthroot; old anchor Landmark_boardwalk_gate
    (152,100):(236.540463,432.749464),  # spawns.txt:370:0 autumn_antler_stag; old anchor Landmark_boardwalk_south
    (230,86):(314.540463,446.749464),   # spawns.txt:380:10 moor_heron; old anchor Landmark_boardwalk_south
    (221,88):(305.540463,444.749464)}   # spawns.txt:389:19 autumn_crown_stag; old anchor Landmark_boardwalk_south
RETAINED_IDENTITIES={'grey-boardwalk-0':'Landmark_boardwalk_gate',
                     'grey-boardwalk-1':'Landmark_boardwalk_centre',
                     'grey-boardwalk-6':'Landmark_boardwalk_south'}


def prepare_grey_crossings(world,content):
    """Pin the four semantic targets once retained content has been placed."""
    if REGION not in world.ids:return {}
    placed=[node for node in RETIRED_GREY_SPANS if (REGION,node) in content.mapping]
    if placed:raise ValueError('Retired Grey Moors spans are still placed: '+', '.join(placed))
    if (REGION,CACHE) not in content.mapping:raise ValueError(CACHE+' must remain a placed discovery')
    if not hasattr(content,'authored_server_points'):content.authored_server_points={}
    owner=world.ids.index(REGION);points={}
    for tile,(x,z) in AUTHORED_POINTS.items():
        if int(world.owner_at(x,z))!=owner:
            raise ValueError(f'{REGION}:{list(tile)}: authored semantic point lies outside its territory')
        point=np.array([x,float(world.height_at(x,z)),z])
        content.authored_server_points[(REGION,tile)]=point;points[str(list(tile))]=point.tolist()
    # The retained boardwalks that stay are designed decks: elevated walks the plan names (owner, 2026-09-16).
    boardwalks=sorted(node for (region,node) in content.mapping if region==REGION and node.startswith(BOARDWALK_PREFIX))
    for node in boardwalks:L.require_designed_deck(getattr(world,'plan',None) or {},node,'grey_crossings')
    world.grey_crossings={'retiredSpans':list(RETIRED_GREY_SPANS),'authoredPoints':points,'designedBoardwalks':boardwalks}
    return world.grey_crossings


def refresh_grey_crossing_heights(world,content):
    """Resolve the pinned points' heights from the final composed terrain."""
    if REGION not in world.ids:return
    for tile in AUTHORED_POINTS:
        point=content.authored_server_points[(REGION,tile)]
        point[1]=float(world.height_at(point[0],point[2]))
        world.grey_crossings['authoredPoints'][str(list(tile))]=point.tolist()


def upward_faces(document,body,roots):
    indices=[i for i in S.descendants(document,roots) if 'mesh' in document['nodes'][i]]
    triangles=S.GR.triangles(document,body,indices)
    if not len(triangles):return triangles
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    return triangles[normal[:,1]>.6*np.maximum(np.linalg.norm(normal,axis=1),1e-10)]


def crossing_floors(bridge_doc,bridge_body,bridges):
    """Actual emitted Grey crossing decks, in global coordinates."""
    floors=[]
    for part in bridges:
        name=part['node']
        if name.startswith(CROSSING_PREFIX) and name.endswith('_'+REGION):
            floors.append((name,upward_faces(bridge_doc,bridge_body,part['roots'])))
    return floors


def retired_floor(content,span):
    """The retired span's walking floor at its generic continental position.

    The old placement loop never ran for a retired root, so the reference is
    the regional transform alone; the earlier hub pull is not replayed.
    """
    document,body=content.documents[REGION]
    by_name={node.get('name'):index for index,node in enumerate(document['nodes'])}
    if span not in by_name:raise ValueError(span+': retired span is missing from the Grey Moors library')
    faces=upward_faces(document,body,[by_name[span]])
    if not len(faces):raise ValueError(span+': retired span has no upward walking floor')
    low=faces.reshape(-1,3).min(axis=0);high=faces.reshape(-1,3).max(axis=0);pivot=(low+high)*.5
    target=np.asarray(content.mapped_xz(REGION,pivot[[0,2]]),float)
    return faces+np.array([target[0]-pivot[0],0.,target[1]-pivot[2]])


def associate(floors,old):
    """Choose the emitted floor covering most of the old floor, else the nearest one."""
    low=old.reshape(-1,3).min(axis=0);high=old.reshape(-1,3).max(axis=0);pivot=(low+high)*.5
    x,z=np.meshgrid(np.arange(np.floor(low[0]),np.ceil(high[0])+.01,SAMPLE_METRES),
                    np.arange(np.floor(low[2]),np.ceil(high[2])+.01,SAMPLE_METRES))
    _,distance=upper_floor_field(old,x.ravel(),z.ravel());inside=distance<1e-7
    x=x.ravel()[inside];z=z.ravel()[inside]
    best=None
    for name,faces in sorted(floors,key=lambda floor:floor[0]):
        if not len(faces):continue
        height,distance=upper_floor_field(faces,x,z);covered=np.flatnonzero(distance<1e-7)
        if len(covered):
            i=covered[int(np.argmin(np.hypot(x[covered]-pivot[0],z[covered]-pivot[2])))]
            candidate=((0,-len(covered)),name,np.array([x[i],height[i],z[i]]),
                       {'coveredSamples':int(len(covered)),'oldFloorSamples':int(len(x)),'distanceMetres':0.})
        else:
            vertices=np.unique(faces.reshape(-1,3),axis=0)
            gap=np.hypot(vertices[:,0]-pivot[0],vertices[:,2]-pivot[2]);i=int(np.argmin(gap))
            if gap[i]>MAXIMUM_ASSOCIATION_METRES:continue
            candidate=((1,float(gap[i])),name,vertices[i].copy(),
                       {'coveredSamples':0,'oldFloorSamples':int(len(x)),'distanceMetres':float(gap[i])})
        if best is None or candidate[0]<best[0]:best=candidate
    if best is None:
        raise ValueError(f'No emitted Grey Moors crossing floor lies within {MAXIMUM_ASSOCIATION_METRES:g} m of the retired span')
    return best[1],best[2],best[3]


def remap_grey_crossing_landmarks(world,content,region,manifest,bridge_doc,bridge_body,bridges):
    """Carry the three generic identities onto the actual emitted crossing floors."""
    if region!=REGION:return []
    floors=crossing_floors(bridge_doc,bridge_body,bridges)
    if not floors:raise ValueError('Grey Moors export has no continental crossing floor for the retired boardwalk identities')
    center=np.asarray(world.regions[region]['center'],float);landmarks=manifest.get('landmarks',[])
    by_id={entry.get('id'):entry for entry in landmarks}
    report=[]
    for identity,span in RETAINED_IDENTITIES.items():
        entry=by_id.get(identity)
        if entry is None or entry.get('node')!=span:
            raise ValueError(f'{identity}: expected the retained landmark record of {span}')
        name,point,how=associate(floors,retired_floor(content,span))
        entry['node']=name
        entry['position']=[float(point[0]-center[0]),float(point[1]),float(point[2]-center[1])]
        entry['replacedSpan']=span;entry['association']=dict(how)
        report.append({'id':identity,'replacedSpan':span,'node':name,'globalPosition':[float(v) for v in point],**how})
    dangling=[entry.get('id') for entry in landmarks if entry.get('node') in RETIRED_GREY_SPANS]
    if dangling:raise ValueError('Retired Grey Moors spans are still referenced by landmarks: '+', '.join(map(str,dangling)))
    return report
