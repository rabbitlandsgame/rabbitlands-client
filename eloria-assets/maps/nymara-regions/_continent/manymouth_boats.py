"""Float independent delta dugouts on real water or rest them on the bank.

These decorative boats have no doors, actor collision, or assembly membership.
Their old seabed offset is not a foundation height in the reshaped continent.
All corrections are rigid Y translations; source meshes and terrain stay fixed.
"""
from __future__ import annotations
import re
import numpy as np
from scipy.spatial import ConvexHull
import scene_io as S

REGION='manymouth_delta'
SOURCE_WATER_LEVEL=0.0  # Retained dugouts were authored at sea level minus .14m.
GROUND_CLEARANCE=.015
HULL_CLEARANCE=.12


def clip_polygon(points,normal,limit):
    """Clip XYZ values by an XZ half-plane, retaining interpolated hull height."""
    points=np.asarray(points,float)
    if not len(points):return np.empty((0,3))
    scalar=points[:,[0,2]]@np.asarray(normal,float)-limit
    result=[]
    for a,b,sa,sb in zip(points,np.roll(points,-1,axis=0),scalar,np.roll(scalar,-1)):
        if sa<=1e-10:result.append(a)
        if (sa<=0)!=(sb<=0):result.append(a+(b-a)*sa/(sa-sb))
    return np.asarray(result).reshape(-1,3)


def terrain_contacts(world,triangles):
    """Every extremum of hull-minus-ground on the actual shared terrain faces.

    Between these intersection vertices both heights are linear, so checking
    only original boat vertices would miss a bank peak inside a long face.
    """
    cell=float(getattr(world,'cell',2.))
    result=[]
    for triangle in np.asarray(triangles,float):
        lo=triangle[:,[0,2]].min(axis=0);hi=triangle[:,[0,2]].max(axis=0)
        first=np.floor((lo-[world.x0,world.z0])/cell).astype(int)
        last=np.floor((hi-[world.x0,world.z0])/cell).astype(int)
        if (first<0).any() or last[0]>=world.height.shape[1]-1 or last[1]>=world.height.shape[0]-1:
            raise ValueError('Independent boat hull lies outside the shared terrain field')
        for iz in range(first[1],last[1]+1):
            for ix in range(first[0],last[0]+1):
                x=world.x0+ix*cell;z=world.z0+iz*cell
                polygon=triangle
                for normal,limit in (([-1,0],-x),([1,0],x+cell),([0,-1],-z),([0,1],z+cell)):
                    polygon=clip_polygon(polygon,normal,limit)
                for normal,limit in (([1,1],x+z+cell),([-1,-1],-x-z-cell)):
                    part=clip_polygon(polygon,normal,limit)
                    if len(part):result.extend(part)
    if not result:raise ValueError('Independent boat has no terrain-contact geometry')
    return np.unique(np.round(result,10),axis=0)


def area(polygon):
    p=np.asarray(polygon)[:,[0,2]]
    if len(p)<3:return 0.
    return float(abs(np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1)))*.5)


def water_coverage(triangles,water_faces):
    """Intersect the complete convex dugout footprint with disjoint water faces."""
    points=np.asarray(triangles).reshape(-1,3)
    outline=points[ConvexHull(points[:,[0,2]]).vertices]
    full_area=area(outline);covered=0.;levels=[]
    if full_area<=1e-8:raise ValueError('Independent boat has a degenerate hull footprint')
    lower=outline[:,[0,2]].min(axis=0);upper=outline[:,[0,2]].max(axis=0)
    faces=np.asarray(water_faces)
    if not len(faces):return 0.,None,None
    bounds=faces[:,:,[0,2]]
    use=np.all(bounds.max(axis=1)>=lower,axis=1)&np.all(bounds.min(axis=1)<=upper,axis=1)
    for face in faces[use]:
        polygon=face.copy()
        # scipy's planar ConvexHull vertices are counterclockwise in XZ.
        for a,b in zip(outline,np.roll(outline,-1,axis=0)):
            edge=b[[0,2]]-a[[0,2]];normal=np.array([edge[1],-edge[0]])
            polygon=clip_polygon(polygon,normal,float(normal@a[[0,2]]))
        overlap=area(polygon)
        if overlap>1e-10:
            covered+=overlap;levels.extend(polygon[:,1])
    if not levels:return 0.,None,None
    return min(1.,covered/full_area),float(min(levels)),float(max(levels))


def settle_hull(world,triangles,water_faces):
    """Return absolute source-to-world Y shift plus measured physical support."""
    samples=terrain_contacts(world,triangles)
    ground=world.height_at(samples[:,0],samples[:,2])
    coverage,low_water,high_water=water_coverage(triangles,water_faces)
    floating_shift=((low_water+high_water)*.5-SOURCE_WATER_LEVEL) if low_water is not None else 0.
    floating_clearance=float(np.min(samples[:,1]+floating_shift-ground))
    floating=(coverage>=1.-1e-7 and high_water-low_water<=.12 and floating_clearance>=HULL_CLEARANCE)
    shift=floating_shift if floating else float(np.max(ground-samples[:,1])+GROUND_CLEARANCE)
    clearance=samples[:,1]+shift-ground
    if float(clearance.min())<-1e-7:raise ValueError('Independent boat correction buries its actual hull')
    return shift,{'mode':'afloat' if floating else 'hauled-up','footprintWaterCoverage':coverage,
        'waterLevelRange':None if low_water is None else [low_water,high_water],
        'minimumGroundClearance':float(clearance.min()),'maximumGroundClearance':float(clearance.max()),
        'terrainIntersectionVertices':len(samples),'sourceToWorldY':shift}


def _gameplay_linked(template,names):
    def contains(value):
        if isinstance(value,str):return value in names
        if isinstance(value,list):return any(contains(item) for item in value)
        if isinstance(value,dict):return any(contains(item) for item in value.values())
        return False
    return any(contains(template.get(key)) for key in ('portals','interactives','interiors','npcMarkers',
        'spawnPoints','harvestables','creatureSpawns','pointsOfInterest','landmarks'))


def apply_manymouth_boats(world,content):
    """Run after final water/road grading and content.reground, before export."""
    selected=[obj for obj in content.objects if obj.get('region')==REGION
        and re.fullmatch(r'moored_boat_\d+',obj.get('node',''))
        and not obj.get('assembly') and not obj.get('collides') and not obj.get('walk')]
    if not selected:
        world.manymouth_boats={'boats':[],'afloat':0,'hauledUp':0};return world.manymouth_boats
    for obj in selected:
        if obj.get('source',{}).get('landmark') or _gameplay_linked(content.templates[REGION],obj.get('names',{obj['node']})):
            raise ValueError(obj['node']+': decorative boat correction cannot move a gameplay-linked object')
    from terrain_export import clipped_water_surface
    nz,nx=world.height.shape;row,col=np.indices((nz-1,nx-1));a=(row*nx+col).ravel()
    cells=np.stack((a,a+nx,a+1,a+1,a+nx,a+nx+1),axis=1)
    points=np.c_[world.gx.ravel(),world.height.ravel(),world.gz.ravel()]
    mesh=clipped_water_surface(world,points,cells)
    water_faces=mesh['positions'][mesh['triangles']].astype(float)
    document,body=content.documents[REGION];records=[]
    for obj in selected:
        nodes=[i for i in S.descendants(document,obj.get('indices',[obj['index']])) if 'mesh' in document['nodes'][i]]
        source=S.GR.triangles(document,body,nodes)
        if not len(source):raise ValueError(obj['node']+': independent boat has no actual hull')
        # Source Y already includes the authored -.14m flotation offset. Strip
        # only the obsolete terrain-following Y shift, retaining exact XZ.
        triangles=source+np.array([obj['shift'][0],0.,obj['shift'][2]])
        new_y,record=settle_hull(world,triangles,water_faces)
        delta=new_y-float(obj['shift'][1])
        obj['shift'][1]=new_y;obj['low'][1]+=delta;obj['high'][1]+=delta
        content.mapping[(REGION,obj['node'])]=obj['shift']
        content.bounds_by_name[(REGION,obj['node'])]=(obj['low'],obj['high'])
        record.update(node=obj['node'],deltaY=delta,positionXZ=((obj['low']+obj['high'])*.5)[[0,2]].tolist())
        records.append(record)
    world.manymouth_boats={'boats':records,'afloat':sum(r['mode']=='afloat' for r in records),
        'hauledUp':sum(r['mode']=='hauled-up' for r in records),'policy':'Actual complete hull water coverage and terrain triangle contact; rigid Y only.'}
    content.manymouth_boats=world.manymouth_boats
    return world.manymouth_boats
