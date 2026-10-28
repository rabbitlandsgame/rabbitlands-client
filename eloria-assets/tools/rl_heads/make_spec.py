"""Turn a likeness lab spec (macro + MPFB targets) into a head build spec:
macro stack via MPFB in Blender, plus the shared controls/expressions/proxies."""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import json, os, subprocess, sys
R = paths.LOCAL
lab, sex, out = sys.argv[1], sys.argv[2], sys.argv[3]
ls = json.load(open(lab))
stack_path = os.path.splitext(out)[0] + '.macro.json'
env = dict(os.environ, BLENDER_USER_RESOURCES=os.path.join(R, 'blender_profile'))
subprocess.run([paths.BLENDER, '-b', '--python', os.path.join(paths.TOOLS, 'macro_stack.py'), '--',
                json.dumps(ls['macro']), stack_path], env=env, check=True, capture_output=True)
cx = json.load(open(os.path.join(paths.SPECS, 'controls.json')))
spec = {'sex': sex, 'macro': stack_path, 'likeness': ls['targets'], 'custom_targets': ls.get('custom_targets', {}), 'likeness_units': ls.get('units', {}),
        'proxies': {'eyes': 'eyes/high-poly/high-poly.mhclo', 'eyes_low': 'eyes/low-poly/low-poly.mhclo', 'lashes': 'eyelashes/eyelashes02/eyelashes02.mhclo', 'teeth': 'teeth/teeth_base/teeth_base.mhclo', 'tongue': 'tongue/tongue01/tongue01.mhclo'},
        'controls': cx['controls'], 'expressions': cx['expressions'], 'source': os.path.relpath(lab, R)}
json.dump(spec, open(out, 'w'), indent=1)
print('spec', out)
