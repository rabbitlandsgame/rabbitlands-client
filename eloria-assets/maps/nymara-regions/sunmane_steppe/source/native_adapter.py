"""Translate the retained Sunmane kit into shared mesh/material containers.

All primitives still come from the original kit; terrain, normal handling,
GLB serialization and border slicing use the shared authoring toolkit.
"""
from pathlib import Path
import io,sys
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent
TOOLKIT=HERE.parents[1]/'_toolkit'
sys.path[:0]=[str(HERE),str(TOOLKIT)]
from amberwood import mesh as M,stonework as S,gltf as G,materials as MAT
import settlement as NATIVE
import textures as TEXTURES

def group(parts):
    out=S.MeshGroup()
    for material,geometry in parts.items():
        if not geometry.triangle_count:continue
        p,n,uv,indices,colors=geometry.weld().arrays(with_colors=True)
        faces=indices.reshape(-1,3).copy()
        normal=np.cross(p[faces[:,1]]-p[faces[:,0]],p[faces[:,2]]-p[faces[:,0]])
        reverse=np.einsum('ij,ij->i',normal,n[faces].mean(axis=1))<0
        faces[reverse]=faces[reverse][:,::-1]
        piece=M.Mesh(positions=p.copy(),normals=n.copy(),uvs=uv.copy(),
                     colors=colors.copy(),indices=faces.ravel(),material='sun_'+material)
        piece.sanitise_normals();piece.drop_degenerate();out.add(piece)
    return out

def materials(builder,build,lod=False):
    used={part.material for item in list(build.meshes.values())+list(build.terrain_meshes.values())+list(build.water_meshes.values())
          for part in getattr(item,'all_parts',[item]) if part.triangle_count}
    native={name[4:] for name in used if name.startswith('sun_')}
    kit=TEXTURES.build_kit(scale=.5 if lod else 1.)
    images={}
    for name in sorted(native):
        family,color,metal,rough,double,*normal=NATIVE.MATERIALS[name]
        if family not in images:
            maps=kit[family];images[family]={}
            for channel,data in [('base',maps.base_color),('normal',maps.normal),('orm',maps.orm)]:
                image_name='sun_'+family+'_'+channel
                builder.add_image(image_name,data);images[family][channel]=image_name
        builder.add_material(G.Material('sun_'+name,base_color=color,metallic=metal,roughness=rough,
            double_sided=double,base_color_texture=images[family]['base'],
            normal_texture=images[family]['normal'] if not normal or normal[0] else None,
            normal_scale=.38 if family in ('ground','stone','thatch') else .65,
            orm_texture=images[family]['orm']))
    shared={name if name in MAT.BY_NAME else MAT.base_material(name) for name in used if not name.startswith('sun_')}
    import preview
    sets=preview.texture_sets()
    for name in ('steppe_sward','steppe_dust'):
        if name in shared and name not in sets:
            from amberwood import textures as T
            sets[name]=T.steppe_ground(name)
    MAT.register_gltf_materials(builder,sets,only=shared)
    MAT.register_ground_materials(builder,sets,{name for name in used if not name.startswith('sun_')
          and name not in MAT.BY_NAME and name.endswith(MAT.GROUND_SUFFIX)})

def export(build,path,lod=False):
    builder=G.GltfBuilder('Eloria Sunmane: native Orun kit / shared landscape toolkit')
    materials(builder,build,lod)
    root=builder.add_node(G.Node('Sunmane_Steppe_Root'))
    meshes={};solid_nodes=[]
    for key,item in build.meshes.items():
        entries=[]
        for category,parts in [('solid',item.by_material(False)),('walk',item.by_material(True))]:
            for material,part in parts.items():
                if not part.triangle_count:continue
                part.sanitise_normals();part.drop_degenerate();part.weld(1e-4)
                name=key+'__'+category+'__'+material
                builder.add_mesh(name,part);entries.append((name,category))
        meshes[key]=entries
    for bucket in (build.terrain_meshes,build.water_meshes):
        for name,piece in bucket.items():
            if not piece.triangle_count:continue
            piece.sanitise_normals();piece.drop_degenerate();piece.weld(1e-4)
            builder.add_mesh(name,piece);builder.add_node(G.Node(name,mesh=name),root)
    for p in build.placements:
        parent=builder.add_node(G.Node(p.node,translation=p.position,rotation_y=p.rotation_y,
            scale=(p.scale,p.scale,p.scale),extras=p.extras),root)
        for key,category in meshes[p.mesh]:
            name=('Walk_' if category=='walk' or p.walk_surface else '')+p.node+'__'+key
            builder.add_node(G.Node(name,mesh=key),parent)
            if p.collides and category=='solid' and not p.node.startswith('StreamView_'):solid_nodes.append(name)
    for marker in getattr(build,'empty_nodes',[]):
        builder.add_node(G.Node(marker['node'],translation=marker['position'],extras=marker.get('extras')),root)
    size=builder.write_glb(str(path));stats=builder.statistics()
    stats.update(glbBytes=size,instancedTriangles=builder.instanced_triangles())
    return stats,solid_nodes
