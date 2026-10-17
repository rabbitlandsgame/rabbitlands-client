# Hoofed-family creature motion

Seven imported creatures use the reviewed native walk, trot, horn-led strike and collapse: Moss Horn Ram, Thunder Ram, Whitehorn Ice Ram, Cobalt Ibex, Glowhorn Sheep, Golden Bison and Whitehorn Yak. The installed GLBs are byte-identical to the selected review exports. These are locally authored behaviors fitted to each creature's anatomy.

Stable actor IDs, model paths, import scale, facing, attachments and action/server-command bindings remain in place. Dedicated `data/animations/caprine/` maps play walk and trot at their authored speed and expose measured stride speed at the actual import scale; runtime actor scaling is included. The four authored actions retain the existing `Walk`, `Jog`, `Sword_Attack` and `Death_A` names. Idle, fighting idle and hit remain available.

Native hoof-pad weights and selected hanging coat pieces were repaired explicitly. Golden Bison has corrected hind-thigh parenting and Whitehorn Yak has corrected distal hoof-helper parenting, with original rest-world transforms and inverse binds retained. Non-bone wrapper animation is represented on physical roots where required by the native importer. Cobalt Ibex's inherited idle/hit actions intentionally receive the same left-scapula offset as its fitted actions; all other inherited primary-bone worlds are retained. Its final left forehoof sits slightly outside the left hindhoof by the same amount as the right pair. Thunder Ram and Cobalt Ibex use anatomy-based forward alignment across all four authored actions.

Geometry, UVs, normals, topology, embedded textures, morph arrays and inverse binds are preserved. Native serial segment lengths, full skin-floor clearance, supported hoof-surface velocity, rotation continuity, loops and held endpoints are checked on exported keys and between them. Death support uses the actor's actual horn/head envelope and body side rather than forcing its muzzle through the floor.

`docs/qa/caprine-motion/` contains portable profiles, checksums, preparation scope and reviewed-export evidence. `tests/fixtures/caprine_motion_worlds.json` contains independent off-grid GLB witnesses. Tracked import policies preserve the qualified 3072 FPS import cadence; optimization and compression remain disabled for these native curves.

Run the portable export check from the repository root with Python, NumPy and SciPy:

```text
python eloria-assets/tools/test_caprine_motion.py --report /path/to/report.json
```

After a Godot import, run `tests/test_caprine_motion.gd` headlessly through the client project or an isolated copy of its actual component dependencies. It checks all 49 slots through the current scene cache, native animation importer and action resolver, including off-grid poses, morph defaults, holds, action switching, idle restoration and RESET. This is focused component integration; a full client/server play session is not claimed.

High-resolution originals, authoring stages, review videos and private receipts remain outside Git in the ignored authoring workspace.
