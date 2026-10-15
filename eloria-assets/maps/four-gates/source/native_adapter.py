"""Adapt the existing Four Gates art kits to the shared RegionBuild contract.

Only field/material translation lives here: geometry, terrain operators,
streaming clipping, GLB writing and texture recipes remain in their original
shared/native providers. No authored kit is copied or uniformly rescaled.
"""
from pathlib import Path
import re,sys
import numpy as np
HERE=Path(__file__).resolve().parent
ASSETS=HERE.parents[2]
TOOLKIT=ASSETS/'maps/nymara-regions/_toolkit'
NATIVE=ASSETS/'tools/four_gates'
sys.path[:0]=[str(TOOLKIT),str(NATIVE)]
from amberwood import mesh as M, stonework as S, gltf as G, materials as MAT
import kits as K
import landmarks as L

NAMES=list(dict.fromkeys(re.findall(r'materials\["([^"]+)"\]',(NATIVE/'texturing.py').read_text())))
PALETTE=K.Palette({n:i for i,n in enumerate(NAMES)})

def mesh(geo):
    group=S.MeshGroup()
    for material in np.unique(geo.m):
        faces=geo.f[geo.m==material]
        used,indices=np.unique(faces.ravel(),return_inverse=True)
        part=M.Mesh(positions=geo.v[used].copy(),normals=geo.n[used].copy(),
                    uvs=geo.t[used].copy(),indices=indices,
                    material='fg_'+NAMES[int(material)])
        group.add(part)
    return group

def register_materials(builder,build,cache):
    used=set()
    for item in list(build.meshes.values())+list(build.terrain_meshes.values())+list(build.water_meshes.values()):
        for part in getattr(item,'all_parts',[item]):
            if part.triangle_count:used.add(part.material)
    import corner_material
    corner_materials={n for n in used if n.startswith(corner_material.PREFIX)}
    if corner_materials:
        corner_material.register(builder,build,corner_materials)
        used-=corner_materials
    native={n[3:] for n in used if n.startswith('fg_')}
    if native:
        from assembly import MaterialLibrary
        sets,_=MaterialLibrary._load_or_build(512,1024,20260827,str(cache))
        from gltf_writer import GLB
        from PIL import Image
        for name in sorted(native):
            spec=sets[name];images={}
            for key,img in [('base',spec.base),('normal',spec.normal),('orm',spec.orm),('emissive',spec.emissive)]:
                if img is None:continue
                side=512 if name in ('stone_ashlar','stone_trim','plaster_warm','roof_verdigris','paving_plaza') else 256
                if img.width>side:img=img.resize((side,side),Image.Resampling.LANCZOS)
                image_name='fg_'+name+'_'+key
                builder.add_image(image_name,GLB.encode_png(img));images[key]=image_name
            builder.add_material(G.Material('fg_'+name,base_color=spec.base_factor,
                metallic=1.,roughness=1.,base_color_texture=images['base'],
                normal_texture=images['normal'],orm_texture=images['orm'],
                normal_scale=spec.normal_scale,emissive=spec.emissive_factor,
                emissive_texture=images.get('emissive'),alpha_mode=spec.alpha_mode,
                double_sided=spec.double_sided))
    shared={n if n in MAT.BY_NAME else MAT.base_material(n) for n in used if not n.startswith('fg_')}
    if shared:
        import preview
        sets=preview.texture_sets()
        MAT.register_gltf_materials(builder,sets,only=shared)
        MAT.register_ground_materials(builder,sets,{m for m in used if m.endswith(MAT.GROUND_SUFFIX) and m not in MAT.BY_NAME})

class AnimatedBuilder(G.GltfBuilder):
    """Carry native gate clips using the shared writer's buffer/accessor API."""
    def to_json(self):
        doc=super().to_json()
        if getattr(self,'animations',[]):doc['animations']=self.animations
        return doc

def export(build,path,cache,lod=False):
    builder=AnimatedBuilder('Eloria Four Gates: native art / shared landscape toolkit')
    register_materials(builder,build,cache)
    root=builder.add_node(G.Node('Four_Gates_Root'))
    pieces={}
    active={p.mesh for p in build.placements if not (lod and p.kind in ('undergrowth','small_dressing'))}
    for key,item in build.meshes.items():
        if key not in active:continue
        solid=(item.by_material(False) if hasattr(item,'parts') else {item.material:item})
        walk=item.by_material(True) if hasattr(item,'parts') else {}
        entries=[]
        for category,parts in [('solid',solid),('walk',walk)]:
            for material,part in parts.items():
                if not part.triangle_count:continue
                name=key+'__'+category+'__'+material
                part.sanitise_normals();part.drop_degenerate()
                part.weld(1e-4)
                builder.add_mesh(name,part)
                entries.append((name,category))
        pieces[key]=entries
    for bucket in (build.terrain_meshes,build.water_meshes):
        for name,part in bucket.items():
            if not part.triangle_count:continue
            part.sanitise_normals();part.drop_degenerate();part.weld(1e-4)
            builder.add_mesh(name,part);builder.add_node(G.Node(name,mesh=name),root)
    node_indices={}
    for p in build.placements:
        if lod and p.kind in ('undergrowth','small_dressing'):continue
        parts=pieces[p.mesh]
        container=builder.add_node(G.Node(p.node,translation=p.position,
            rotation_y=p.rotation_y,scale=(p.scale,p.scale,p.scale),extras=p.extras),root)
        node_indices[p.node]=container
        for name,category in parts:
            prefix='Walk_' if category=='walk' or p.walk_surface else ''
            builder.add_node(G.Node(prefix+p.node+'__'+name,mesh=name),container)
    for marker in getattr(build,'empty_nodes',[]):
        builder.add_node(G.Node(marker['node'],translation=marker['position'],extras=marker.get('extras')),root)
    builder.animations=[]
    for clip in getattr(build,'animations',[]):
        if clip['node'] not in node_indices:continue
        time_index=builder._add_accessor(np.asarray(clip['times']),'SCALAR',G.COMPONENT_FLOAT,None)
        value_index=builder._add_accessor(np.asarray(clip['values']),'VEC3',G.COMPONENT_FLOAT,None)
        builder.animations.append({'name':clip['name'],
          'samplers':[{'input':time_index,'output':value_index,'interpolation':'LINEAR'}],
          'channels':[{'sampler':0,'target':{'node':node_indices[clip['node']],'path':clip['path']}}]})
    size=builder.write_glb(str(path))
    stats=builder.statistics();stats.update(glbBytes=size,instancedTriangles=builder.instanced_triangles())
    return stats
