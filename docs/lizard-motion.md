# Lizard motion

The approved Gecko, Chameleon, Frilled Lizard and Iguana sets contain Walk (0.76 s), Jog/scurry (0.40 s), Sword_Attack/forward lunge (1.60 s) and Death_A/supported collapse (2.60 s), plus retained idle, fighting idle and hit clips. Attack and death hold from 1.45 s and 2.05 s. These are authored native-rig fits with shared action intent and individually solved limbs and physical contact frames.

Each model retains its geometry, normals, UVs, images, native rest, binds, hierarchy, scale, facing and attachment declarations. Skin preparation keeps complete palms/heels, a coherent face and abdomen, and continuous crest/frill/throat attachment transitions. The four underside regions used per paw are spatial support patches; the rigs have no finger skeleton. Native claw thickness and tail profiles are preserved. The forward lunge uses body and head motion without an independent jaw control.

Dedicated maps under `data/animations/lizard/` retain gameplay action names and measured stride speeds at each registry scale. Import policies preserve the declared 3072 FPS with optimizer/compression disabled. The accepted exports qualified 151,020 native samples and 28 current-client slots with actual eight-influence meshes. High-resolution sources, fitting stages and review media remain ignored.

Run `python eloria-assets/tools/test_lizard_motion.py` with NumPy and SciPy. After import, run `tests/test_lizard_motion.gd`. These cover independent bone/skin witnesses, complete-paw support and sliding, floor clearance, serial lengths, loops and held endpoints, face/torso coherence, action switching, RESET and idle restoration. The receipts certify component playback; full client/server sessions and crowd performance are separate checks.
