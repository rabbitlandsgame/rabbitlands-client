# Orc and Kobold motion

The approved Highland Orc and Coal Kobold sets include Walk, Jog/run, Sword_Attack and Death_A, plus retained idle, fighting idle and hit reactions. The Orc uses a forward punch; the Kobold uses an aggressive raised wind-up and downward scratch across the body, with a relaxed left arm following the torso and a stable wrist.

Native geometry, topology, textures, rest joints, registry scale, facing and attachments are retained. Reviewed skin preparation covers coherent torso and joint transitions, hands/fingers, complete feet, cranial details and accessories. The Kobold retains both knee/hock/ankle arrangements, its true tail and its independent loincloth chain. The centered tail clears the floor and settles through collapse. The Orc retains its articulated skirt and braids.

Dedicated maps under `data/animations/orc-kobold/` preserve gameplay action names and declare measured stride at the unchanged registry scale. Both models declare a 3072 FPS import cadence with optimizer/compression disabled. The imported scene and native animation library honor the same settings.

The installed GLBs are byte-exact copies of the approved selections. High-resolution sources, intermediate processing stages and review media remain ignored. Numerical qualification, sampled collision checks, multi-angle visual approval and client playback are separate evidence.

Run `python eloria-assets/tools/test_orc_kobold_motion.py` with NumPy and SciPy. After import, run `tests/test_orc_kobold_motion.gd`. These cover fourteen runtime slots with independent bone, morph and surface witnesses, native lengths, complete-foot support, floor clearance, loops/holds, action switching, RESET and idle restoration. They are component checks; full client/server sessions and crowd performance are separate checks.
