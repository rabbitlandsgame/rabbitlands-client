"""Repair an ignored extracted surface before LOD reduction (Blender 5.x).

blender -b --python repair_reference_topology.py -- <stage>
Weld position seams, remove separated small islands, and fill small closed
interior boundary loops. Preserve the large face/outer silhouette openings.
Original extraction files must be preserved in a separate source stage.
"""
import json,sys
from pathlib import Path
import bpy,bmesh,numpy as np
from mathutils.kdtree import KDTree

stage=Path(sys.argv[sys.argv.index('--')+1]);data=np.load(stage/'extracted.npz')
mesh=bpy.data.meshes.new('Reference topology source')
mesh.from_pydata(data['P'].tolist(),[],data['T'].tolist());mesh.update()
layer=mesh.uv_layers.new(name='UVMap')
layer.data.foreach_set('uv',data['UV'][data['T'].reshape(-1)].astype('f4').reshape(-1))
bm=bmesh.new();bm.from_mesh(mesh);uv=bm.loops.layers.uv.active
print('TOPOLOGY_INPUT',len(bm.faces),flush=True)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00015)
print('TOPOLOGY_WELDED',len(bm.verts),flush=True)
bm.verts.ensure_lookup_table();bm.verts.index_update()
unseen=set(bm.verts);components=[]
while unseen:
    first=unseen.pop();group={first};stack=[first]
    while stack:
        for edge in stack.pop().link_edges:
            for other in edge.verts:
                if other in unseen:unseen.remove(other);group.add(other);stack.append(other)
    components.append(group)
components.sort(key=len,reverse=True)
print('TOPOLOGY_COMPONENTS',len(components),flush=True)
main=KDTree(len(components[0]))
for i,v in enumerate(components[0]):main.insert(v.co,i)
main.balance()
removed=0
for group in components[1:]:
    gap=min(main.find(v.co)[2] for v in group)
    if len(group)<300 and gap>.001:
        removed+=len(group);bmesh.ops.delete(bm,geom=list(group),context='VERTS')
# Connected boundary loops only; branched non-manifold cuts are left for audit.
boundary={e for e in bm.edges if e.is_boundary};loops=[]
while boundary:
    first=boundary.pop();edges=[first];start=first.verts[0];current=first.verts[1]
    while current!=start:
        choices=[e for e in current.link_edges if e in boundary]
        if len(choices)!=1:break
        edge=choices[0];boundary.remove(edge);edges.append(edge);current=edge.other_vert(current)
    if current==start:loops.append(edges)
fillable=[];perimeters=[];uv_by_vertex={}
for edges in loops:
    perimeter=sum(e.calc_length() for e in edges);perimeters.append(perimeter)
    if perimeter>.16 or len(edges)>200:continue
    # A lone detached strand's outer rim should not be capped into a disc.
    if len({f for e in edges for f in e.link_faces})<3:continue
    uv_by_vertex.update({v:tuple(next(l[uv].uv for f in v.link_faces for l in f.loops if l.vert==v)) for e in edges for v in e.verts})
    fillable.extend(edges)
print('TOPOLOGY_LOOPS',len(loops),'FILL_EDGES',len(fillable),flush=True)
result=bmesh.ops.holes_fill(bm,edges=fillable,sides=0) if fillable else {'faces':[]}
for face in result['faces']:
    for loop in face.loops:loop[uv].uv=uv_by_vertex[loop.vert]
filled=len(result['faces'])
bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.normal_update()
bm.verts.index_update();bm.faces.ensure_lookup_table()
# Split UV seams explicitly, preserving smooth welded normals.
mapping={};P=[];N=[];UV=[];T=[]
for face in bm.faces:
    ids=[]
    for loop in face.loops:
        key=(loop.vert.index,round(loop[uv].uv.x,7),round(loop[uv].uv.y,7))
        if key not in mapping:
            mapping[key]=len(P);P.append(tuple(loop.vert.co));N.append(tuple(loop.vert.normal));UV.append(tuple(loop[uv].uv))
        ids.append(mapping[key])
    T.append(ids)
np.savez_compressed(stage/'extracted.npz',P=np.asarray(P),N=np.asarray(N),UV=np.asarray(UV),T=np.asarray(T))
receipt={'weld_mm':.15,'removed_island_vertices':removed,'filled_interior_loops':filled,'preserved_large_openings':sum(p>.16 for p in perimeters),'triangles':len(T)}
(stage/'topology-repair.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
