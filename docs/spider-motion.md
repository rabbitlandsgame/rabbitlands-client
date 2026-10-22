# Spider motion

Crystal Cave Spider and Nightweave Spider use the reviewed seven-action sets: idle, alert, flinch, tripod walk, faster skitter, braced bite and supported leg-curl death. Each model retains its stylized six walking limbs and two front palps.

The current imported geometry, skin, textures, original joint prefix and rest binds are preserved. Added anatomical controls carry complete armored sections and pointed blades through corrective surfaces. The dedicated maps use native playback speed and measured ground travel at the unchanged actor scale. Head and neck attachments use `RL_Spider_Head`; body effects use `RL_Spider_Body`.

Runtime packing removes only redundant keys inside constant holds and unreachable storage. Every reviewed sampler knot is reproduced to numerical precision; durations, articulated motion and tip contacts are retained. Both import policies require 4096 FPS, uncompressed meshes, and disabled animation optimization/compression. High-resolution inputs, intermediate exports and review videos remain outside Git.

Run `python eloria-assets/tools/test_spider_motion.py` with NumPy and SciPy. After importing the client, run `tests/test_spider_motion.gd` in Godot. These check fourteen slots against independent off-grid bone, morph, surface and normal witnesses, actual scene/library import, loop and held endpoints, action switching and RESET. Native checks also cover three-tip support, torso support polygons, mirrored touchdown advances, complete-blade rigidity, floor clearance, original segment lengths and abdomen-supported death. Sharp tips have point contacts rather than flat paw soles. Full client/server sessions and crowd performance are separate checks.
