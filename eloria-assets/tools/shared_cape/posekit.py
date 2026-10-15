# shared helpers, exec'd inside Blender
import bpy
from mathutils import Vector, Matrix, Quaternion
LIB = [o for o in bpy.data.collections['lib'].all_objects]
def lib_world(action_name, frame):
    a = bpy.data.actions[action_name]
    for o in LIB:
        o.animation_data_create(); o.animation_data.action = a
        slot = next((s for s in a.slots if s.identifier == 'OB' + o.name), None)
        o.animation_data.action_slot = slot
    bpy.context.scene.frame_set(int(frame)); bpy.context.view_layer.update()
    return {o.name: o.matrix_world.copy() for o in LIB}
SCALES = {"spine_02": (1.07, 0.985, 1.05), "spine_03": (1.13, 0.985, 1.09), "neck_01": (1.05, 1.0, 1.05),
          "upperarm_l": (1.13, 1.0, 1.13), "upperarm_r": (1.13, 1.0, 1.13), "lowerarm_l": (1.16, 1.0, 1.16),
          "lowerarm_r": (1.16, 1.0, 1.16), "thigh_l": (1.09, 1.0, 1.09), "thigh_r": (1.09, 1.0, 1.09),
          "calf_l": (1.11, 1.0, 1.11), "calf_r": (1.11, 1.0, 1.11), "hand_l": (1.24,)*3, "hand_r": (1.24,)*3,
          "foot_l": (1.18, 1.20, 1.18), "foot_r": (1.18, 1.20, 1.18), "Head": (1.12, 1.09, 1.11)}
def pose_armature(arm, action='Idle_Subtle', frame=0, style=True, root_motion=False):
    rest = lib_world('Rest_Pose', 0); pose = lib_world(action, frame)
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    A = arm.matrix_world
    def walk(pb):
        key = pb.name if pb.name in pose else pb.name.lower()
        if key in pose:
            D = (pose[key].to_quaternion() @ rest[key].to_quaternion().inverted())
            rest_arm = pb.bone.matrix_local
            rot_world = D @ (A.to_quaternion() @ rest_arm.to_quaternion())
            rot_arm = A.to_quaternion().inverted() @ rot_world
            if pb.parent is None:
                loc = rest_arm.to_translation()
                if root_motion: pass
            else:
                par_rest = pb.parent.bone.matrix_local
                off = par_rest.inverted() @ rest_arm.to_translation()
                loc = pb.parent.matrix @ off
            if pb.name == 'pelvis':
                # pelvis translation delta (world) mapped into armature space, scaled 1
                dw = pose[key].to_translation() - rest[key].to_translation()
                loc = loc + (A.to_3x3().inverted() @ dw)
            pb.matrix = Matrix.LocRotScale(loc, rot_arm, Vector((1, 1, 1)))
            bpy.context.view_layer.update()
        for c in pb.children: walk(c)
    for pb in arm.pose.bones:
        if pb.parent is None: walk(pb)
    if style:
        for name, s in SCALES.items():
            if name in arm.pose.bones: arm.pose.bones[name].scale = s
    bpy.context.view_layer.update()
