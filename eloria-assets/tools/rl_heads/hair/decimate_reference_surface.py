"""Blender background helper: preserve the extracted hair UVs and bake three LODs.
blender -b --python decimate_reference_surface.py -- <stage>
"""
import sys,json,hashlib
from pathlib import Path
import bpy,bmesh,numpy as np
stage=Path(sys.argv[sys.argv.index('--')+1]);source=np.load(stage/'extracted.npz')
weld_geometry='--weld-geometry' in sys.argv
weld_tolerance=1e-6
receipt={'source_sha256':hashlib.sha256((stage/'extracted.npz').read_bytes()).hexdigest(),'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'weld_geometry':weld_geometry,'weld_tolerance_mm':weld_tolerance*1000,'lods':{}}
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new('Reference hair only');mesh.from_pydata(source['P'].tolist(),[],source['T'].tolist());mesh.update()
uv=mesh.uv_layers.new(name='UVMap')
uv.data.foreach_set('uv',source['UV'][source['T'].reshape(-1)].astype('f4').reshape(-1))
mesh.polygons.foreach_set('use_smooth',np.ones(len(mesh.polygons),dtype=bool))
if weld_geometry:
    # UV and shading normals belong to corners. Weld only POSITION topology,
    # so reduction cannot move the two sides of one UV seam independently.
    bm=bmesh.new();bm.from_mesh(mesh);bm.faces.ensure_lookup_table()
    normal_layer=bm.loops.layers.float_vector.new('rl_source_normal')
    face_layer=bm.faces.layers.int.new('rl_source_face')
    source_t=source['T'];source_uv=source['UV'];source_n=source['N'][source_t]
    for face in bm.faces:
        face[face_layer]=face.index
        for index,loop in enumerate(face.loops):loop[normal_layer]=source_n[face.index,index]
    before_vertices=len(bm.verts);before_faces=len(bm.faces)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=weld_tolerance)
    uv_layer=bm.loops.layers.uv.active;uv_error=0.;normal_error=0.
    for face in bm.faces:
        original=int(face[face_layer]);expected_uv=source_uv[source_t[original]];expected_n=source_n[original]
        for loop in face.loops:
            uv_value=np.array(loop[uv_layer].uv);dist=np.linalg.norm(expected_uv-uv_value,axis=1)
            corner=int((dist+np.linalg.norm(expected_n-np.array(loop[normal_layer]),axis=1)).argmin())
            uv_error=max(uv_error,float(dist[corner]));normal_error=max(normal_error,float(np.linalg.norm(np.array(loop[normal_layer])-expected_n[corner])))
    assert uv_error<1e-6 and normal_error<1e-5,'Welding changed retained painted corners'
    receipt['weld']={'vertices_before':before_vertices,'vertices_after':len(bm.verts),'faces_before':before_faces,'faces_after':len(bm.faces),'max_retained_uv_error':uv_error,'max_retained_normal_error':normal_error}
    bm.to_mesh(mesh);bm.free();mesh.update()
    normals=np.empty(len(mesh.loops)*3,'f4');mesh.attributes['rl_source_normal'].data.foreach_get('vector',normals)
    mesh.normals_split_custom_set(normals.reshape(-1,3).tolist())
    for temporary in ['rl_source_normal','rl_source_face']:
        mesh.attributes.remove(mesh.attributes[temporary])
    print('REFERENCE_POSITION_WELD',receipt['weld'],flush=True)
print('REFERENCE_HAIR_INPUT',len(mesh.polygons),flush=True)
obj=bpy.data.objects.new('Reference hair only',mesh);bpy.context.collection.objects.link(obj)
budgets=json.loads((stage/'lod-budgets.json').read_text()) if (stage/'lod-budgets.json').exists() else [15800,5800,1700]
for lod,budget in enumerate(budgets):
    candidate=obj.copy();candidate.data=mesh.copy();bpy.context.collection.objects.link(candidate)
    bpy.context.view_layer.objects.active=candidate
    if len(mesh.polygons)>budget:
        mod=candidate.modifiers.new('Measured LOD budget','DECIMATE');mod.ratio=budget/len(mesh.polygons);mod.use_collapse_triangulate=True
        bpy.ops.object.modifier_apply(modifier=mod.name)
    m=candidate.data;m.calc_loop_triangles()
    co=np.empty(len(m.vertices)*3,'f4');normal=co.copy();m.vertices.foreach_get('co',co);m.vertices.foreach_get('normal',normal)
    corners=np.empty(len(m.loop_triangles)*3,np.int32);loops=corners.copy();m.loop_triangles.foreach_get('vertices',corners);m.loop_triangles.foreach_get('loops',loops)
    uvco=np.empty(len(m.loops)*2,'f4');m.uv_layers.active.data.foreach_get('uv',uvco)
    uvco=uvco.reshape(-1,2)[loops]
    keys=np.column_stack([corners,np.round(uvco*1e8).astype(np.int64)])
    if weld_geometry:
        corner_n=np.empty(len(m.corner_normals)*3,'f4');m.corner_normals.foreach_get('vector',corner_n);corner_n=corner_n.reshape(-1,3)[loops]
        keys=np.column_stack([keys,np.round(corner_n*1e6).astype(np.int64)])
    _,first,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    P=co.reshape(-1,3)[corners[first]];N=corner_n[first] if weld_geometry else normal.reshape(-1,3)[corners[first]];UV=uvco[first];T=inverse.reshape(-1,3)
    np.savez_compressed(stage/f'lod{lod}.npz',P=P,N=N,UV=UV,T=T)
    bpy.data.objects.remove(candidate,do_unlink=True)
    print('REFERENCE_HAIR_LOD',lod,len(T),flush=True)
    if weld_geometry:
        _,position_groups=np.unique(np.round(P/weld_tolerance),axis=0,return_inverse=True)
        edges=np.sort(position_groups[T[:,[0,1,1,2,2,0]].reshape(-1,2)],axis=1);_,counts=np.unique(edges,axis=0,return_counts=True)
        receipt['lods'][str(lod)]={'triangles':len(T),'target_triangles':budget,'within_target':len(T)<=budget,'vertices':len(P),'geometric_open_edges':int((counts==1).sum()),'output_sha256':hashlib.sha256((stage/f'lod{lod}.npz').read_bytes()).hexdigest()}
if weld_geometry:(stage/'lod-position-weld.json').write_text(json.dumps(receipt,indent=2)+'\n')
