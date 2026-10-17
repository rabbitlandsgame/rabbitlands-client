# Moor Pony motion

The approved Moor Pony uses a native four-beat walk, diagonal trot, rearing forehoof strike and side-collapse death. Its installed GLB is byte-identical to the reviewed export. The six other imported horse-family models are inventoried for later fitting; this selection changes only Moor Pony.

The dedicated `data/animations/equid/moor_pony.json` map retains existing action/server-command bindings. Walk and trot play at authored speed. Their measured stride speeds are approximately 0.562502 and 1.454550 metres per second at the registry import scale, with actor scaling included by the resolver. Clips are `Walk` (1.12 s), `Jog` (0.66 s), `Sword_Attack` (1.60 s) and `Death_A` (2.60 s). The original idle, fighting-idle and hit sampler arrays are retained exactly.

Each complete hoof piece follows its own ankle, removing opposing-leg influences. Saddle, girth and stirrup pieces follow the torso; bridle pieces follow the head, and mane/neck straps blend smoothly from body to neck. Original geometry, UVs, normals, topology, node hierarchy, rest transforms, inverse binds, embedded images and morph arrays are preserved. Tail clearance is fitted to the gait and rear rather than correcting only its tip.

The saddle's native attachment control is node 24, `Bone_021`. It is a suitable starting frame for a rider preview because the saddle pieces are bound to it. Rider seating, hands, feet, clearance and mount transitions still require their own visual review. Use the registry's complete import/facing transform once; the native source is Y-up and faces +Z. Do not assume native vertex coordinates already include the 0.882353 import scale or the 180-degree forward-axis correction.

`docs/qa/equid-motion/` records the selected checksums, preparation scope, export diagnostics, fresh bone/surface import evidence and installed component checks. `tests/fixtures/equid_motion_worlds.json` contains independent off-grid witnesses. The tracked native import policy retains the qualified 3072 FPS bake cadence with optimization and compression disabled.

Run `python eloria-assets/tools/test_equid_motion.py` from the repository root with NumPy and SciPy. After importing the Godot project, `tests/test_equid_motion.gd` checks all seven installed slots through the actual scene cache, native animation importer and action resolver. These checks cover planted surfaces, full-skin clearance, native lengths, interpolation, loops, held poses, morph defaults, action switching and RESET. They are focused component checks, not a full client/server play session.

Gallop is being authored as a separate draft and is not included in this approved runtime file or its run mapping. Original high-resolution inputs, processing stages, review videos and private handoff records remain in the ignored authoring workspace.
