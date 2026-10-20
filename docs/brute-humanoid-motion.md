# Ogre, Troll and Giant motion

The approved Crag Ogre, Barnacle Ogre, Glacier Troll, Moss Stone Troll, Moss-Bearded Giant and Two-Headed Giant sets include Walk, Jog/run, Sword_Attack and Death_A, with retained idle, fighting idle and hit reactions. Club carriers use torso-led swings; the Stone Troll uses alternating right-left strikes. The Two-Headed Giant retains its taller forward strike posture, stable gait wrists, coherent pants attachment and relaxed death wrists.

Native proportions, model scale, facing, attachment declarations and embedded textures remain unchanged. Reviewed skin preparation covers complete limb transitions, torso, hands/soles, hair and clothing. Crag Ogre includes an approved conforming subdivision around broad joint faces; original vertex attributes and the rest silhouette are preserved. The other five models retain original geometry and topology. Original idle/guard/hit physical bone motion is retained through the reviewed rig preparations.

Dedicated maps under `data/animations/brute/` preserve gameplay action names and measured stride at the registry scale. Import policies disable optimizer/compression and retain the declared cadence: 3072 FPS for Crag Ogre, Barnacle Ogre, Glacier Troll and Stone Troll; 6144 FPS for Moss-Bearded and Two-Headed Giants. Both scene and animation-library loading honor the same fidelity declaration.

Runtime files losslessly omit unreferenced historical samplers and unreachable binary storage; active curve values and timing are retained. High-resolution sources, authoring stages and review media remain ignored. Numerical qualification, six-angle human review and engine playback are distinct evidence.

Run `python eloria-assets/tools/test_brute_humanoid_motion.py` with NumPy and SciPy. After import, run `tests/test_brute_humanoid_motion.gd`. These verify42 runtime slots against independent off-grid bone, corrective-shape and skinned-surface witnesses, native limb lengths, sole support, floor clearance, loop/hold behavior, action switching, RESET and idle restoration. The receipts cover component playback; full client/server sessions and crowd performance are separate checks.
