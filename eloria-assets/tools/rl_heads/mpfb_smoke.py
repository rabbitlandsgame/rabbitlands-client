import bpy, sys, time
t=time.time()
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
bpy.ops.wm.read_factory_settings(use_empty=True)
h = HumanService.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True, feet_on_ground=True, scale=0.1)
print("HUMAN", h.name, len(h.data.vertices), len(h.data.polygons), "shape keys", [k.name for k in (h.data.shape_keys.key_blocks if h.data.shape_keys else [])][:10])
print("vgroups", len(h.vertex_groups))
print("macro", TargetService.get_macro_info_dict_from_basemesh(h) if hasattr(TargetService,'get_macro_info_dict_from_basemesh') else 'n/a')
print("elapsed", time.time()-t)
