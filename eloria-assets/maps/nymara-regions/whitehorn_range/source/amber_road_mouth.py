"""Continue the Amber road across Whitehorn's half-metre ownership inset.

The nominal gate is x=-122.5, while White owns the terrain from x=-123.
The retained seven-metre road ends at that nominal gate. This one strip joins
its literal cross-section to the retained Amber edge; no existing mesh moves.
The outer survey is from Amber's accepted 4d349de5 GLB, in White-local metres.
"""
import numpy as np
from amberwood.mesh import Mesh

ROAD = 'amberwood-whitehorn'
NODE = 'Walk_AmberOwnershipRoadMouth'
# (Z, walking top), including every vertex of the clipped Amber edge.
OUTER = np.array([
    (99.0,45.638153076171875), (99.7916717529297,45.59550476074219),
    (99.875,45.59101486206055), (100.6666717529297,45.56039810180664),
    (100.75,45.55717468261719), (101.5416717529297,45.53874206542969),
    (101.625,45.53680419921875), (102.4166717529297,45.53064727783203),
    (102.5,45.529998779296875), (103.2916717529297,45.536155700683594),
    (103.375,45.53680419921875), (104.1666717529297,45.55523681640625),
    (104.25,45.55717468261719), (105.0416717529297,45.587791442871094),
    (105.125,45.59101486206055), (105.9166717529297,45.633663177490234),
    (106.0,45.638153076171875)], dtype=float)


def make_strip(roads):
    vertices = np.concatenate([m.positions[np.unique(m.indices)] for m in roads])
    edge = vertices[(abs(vertices[:,0]+122.5)<1e-7) &
                    (vertices[:,2]>=99.-1e-7) & (vertices[:,2]<=106.+1e-7)]
    if not len(edge):
        raise ValueError('Amber road mouth lost its retained White gate edge')
    edge = np.unique(edge,axis=0)
    edge = edge[np.argsort(edge[:,2])]
    if abs(edge[0,2]-99)>1e-7 or abs(edge[-1,2]-106)>1e-7:
        raise ValueError('Amber road mouth requires the full seven-metre gate')
    if np.any(np.diff(edge[:,2])<1e-9):
        raise ValueError('Amber road mouth has competing heights on its gate edge')
    z = np.unique(np.r_[OUTER[:,0],edge[:,2]])
    outer = np.c_[np.full(len(z),-123.),np.interp(z,OUTER[:,0],OUTER[:,1]),z]
    inner = np.c_[np.full(len(z),-122.5),np.interp(z,edge[:,2],edge[:,1]),z]
    positions = np.concatenate([outer,inner])
    count=len(z)
    faces=[]
    for i in range(count-1):
        faces.extend(((i,i+1,count+i),(i+1,count+i+1,count+i)))
    mesh=Mesh(positions=positions,uvs=positions[:,[0,2]]*.28,
              indices=np.asarray(faces,dtype=np.int64).ravel(),material='packed_earth_ground')
    mesh.recompute_normals(180)
    return mesh


def apply(build):
    if NODE in build.terrain_meshes:
        raise ValueError('Amber road mouth was applied twice')
    frames=[f for f in build.streaming_borders if f['id']==ROAD]
    if len(frames)!=1 or frames[0]['anchor']!=[-122.5,45.5,102.5]:
        raise ValueError('Amber road mouth requires its unchanged continental frame')
    roads=[m for n,m in build.terrain_meshes.items()
           if n.startswith('Walk_ContinentRoad_'+ROAD) and m.triangle_count]
    mesh=make_strip(roads)
    build.terrain_meshes[NODE]=mesh
    frames[0].setdefault('sceneNodes',[]).append(NODE)
    build.notes.append('The retained Amber road continues over Whitehorn’s 0.5 m ownership inset, joining both literal seven-metre road edges without moving terrain or scenery.')
    return {'node':NODE,'metres':.5,'width':7.,'triangles':mesh.triangle_count}
