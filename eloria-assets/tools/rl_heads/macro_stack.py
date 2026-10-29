"""Blender helper: print MPFB's macro target stack (relative paths + weights) as JSON."""
import bpy, sys, json, os
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.services.locationservice import LocationService
argv = sys.argv[sys.argv.index('--') + 1:]
macro = TargetService.get_default_macro_info_dict()
for k, v in json.loads(argv[0]).items():
    if k == 'race': macro['race'].update(v)
    else: macro[k] = v
stack = TargetService.calculate_target_stack_from_macro_info_dict(macro)
root = LocationService.get_mpfb_data('targets')
out = []
for item in stack:
    if isinstance(item, (list, tuple)): name, w = item[0], item[1]
    else: name, w = item['target'], item['value']
    p = TargetService.target_full_path(name) if not os.path.exists(str(name)) else name
    out.append([os.path.relpath(p, root).replace(chr(92), '/') if p else name, w])
json.dump({'macro': macro, 'stack': out}, open(argv[1], 'w'), indent=1)
print('STACK', len(out))
