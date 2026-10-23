import bpy,json,math,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
source=ROOT/'godot-client/assets/actors/native/mounts/giant_rat.glb'
output=HERE/'blender-checks.json'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps=60
bpy.ops.import_scene.gltf(filepath=str(source))
armatures=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
assert len(armatures)==1
arm=armatures[0]
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)]
print('IMPORTED_MESHES',[(o.name,len(o.data.vertices),[m.type for m in o.modifiers]) for o in meshes])
results={};worst_loop=0;floor=math.inf
for action in bpy.data.actions:
    if action.name not in ['Idle_A','Walk','Jog']:continue
    arm.animation_data_create();arm.animation_data.action=action
    if action.slots: arm.animation_data.action_slot=action.slots[0]
    lo,hi=action.frame_range;first=None;last=None;clip_floor=math.inf;frames=0
    sample_frames=sorted(set([lo+i*.5 for i in range(math.floor((hi-lo)*2)+1)]+[hi]))
    for frame in sample_frames:
        bpy.context.scene.frame_set(math.floor(frame),subframe=frame-math.floor(frame))
        graph=bpy.context.evaluated_depsgraph_get();points=[]
        for obj in meshes:
            current=obj.evaluated_get(graph);mesh=current.to_mesh()
            for vertex in mesh.vertices:
                p=current.matrix_world@vertex.co
                assert all(math.isfinite(float(x)) for x in p)
                points.append(tuple(p));clip_floor=min(clip_floor,p.z)
            current.to_mesh_clear()
        if first is None:first=points
        last=points;frames+=1
    loop=max(math.dist(a,b) for a,b in zip(first,last));worst_loop=max(worst_loop,loop);floor=min(floor,clip_floor)
    results[action.name]={'samples':frames,'minimum_surface_height_metres':clip_floor,'maximum_loop_surface_difference_metres':loop}
print('PRELIMINARY_RESULTS',json.dumps(results))
assert set(results)=={'Idle_A','Walk','Jog'}
assert worst_loop<.0001,(worst_loop,results)
assert floor>-.006,(floor,results)
report={'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'fresh_blender_import':True,'bones':len(arm.data.bones),'clips':results,'failures':0}
output.write_text(json.dumps(report,indent=2)+'\n');print('GIANT_RAT_BLENDER_CHECKS',json.dumps(report))
