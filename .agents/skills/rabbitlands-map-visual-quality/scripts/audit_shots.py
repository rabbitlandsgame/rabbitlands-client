"""audit_shots.py <out dir> <views json>: one trailer-camera shot file per map, one key per audit view.

The shots are for the dev trailer camera (godot-client/src/dev/trailer_camera, see its
README), rendered as stills with its --preview mode, so the same views can be taken
before and after a change:

  godot --path godot-client --resolution 1600x900 res://src/dev/trailer_camera/trailer_camera.tscn \
      -- --shot=<out dir>/audit_<map>.json --preview=<stills dir>

Each view: {"map", "id", "target": [x, z] in map metres (as world.json landmarks),
"yaw": compass degrees the camera looks toward (0 north, 90 east), "pitch": degrees
below the horizon, "distance": metres from the target, "fov": optional}. Camera and
target heights come from the walkable ground (aboveGround / lookAtAboveGround). The
preview writes a still per key and one between keys; the in-between ones can be ignored.
"""
import json
import math
import os
import sys

out_dir, views_path = sys.argv[1], sys.argv[2]
views = json.load(open(views_path))
os.makedirs(out_dir, exist_ok=True)
by_map = {}
for v in views:
    by_map.setdefault(v['map'], []).append(v)
for m, items in by_map.items():
    keys = []
    for i, v in enumerate(items):
        yaw, pitch, d = math.radians(v['yaw']), math.radians(v['pitch']), v['distance']
        horizontal = d * math.cos(pitch)
        tx, tz = v['target']
        x = tx - math.sin(yaw) * horizontal
        z = tz + math.cos(yaw) * horizontal
        keys.append({'t': float(i * 4), 'position': [round(x, 2), 60.0, round(z, 2)],
                     'aboveGround': round(d * math.sin(pitch) + 1.5, 2),
                     'lookAt': [tx, 60.0, tz], 'lookAtAboveGround': 0.0, 'fov': v.get('fov', 50)})
    if len(keys) == 1:
        keys.append(dict(keys[0], t=1.0))
    shot = {'schema': 'rabbitlands-trailer-shot/1', 'name': f'audit_{m}', 'map': m, 'gameMinute': 150,
            'msaa': 4, 'shadowDistance': 200, 'streamRadius': 200, 'preroll': 0.5, 'keys': keys,
            'ambientLife': False}
    json.dump(shot, open(os.path.join(out_dir, f'audit_{m}.json'), 'w'), indent=1)
    print(m, len(keys))
