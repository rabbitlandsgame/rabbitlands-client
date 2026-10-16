# Validation and handoff

## Independent numerical validation

Read the exported GLB rather than trusting the authoring scene. Check:

- accessors, buffer ranges, animation sampler lengths, and finite values;
- joint indices and normalized weights;
- normalized quaternions with continuous signs;
- unchanged bone lengths where translation is not animated;
- preserved rest transforms and inverse bind matrices;
- required clip names, durations, loop metadata/profile mappings, and one-shot endpoints;
- recorded event times in both seconds and frames, with any retimed contact fraction preserved;
- every key and midpoint sample for deformation bounds, contacts, seams, and loop closure;
- no unwanted scale tracks, accumulated root travel, or root yaw;
- morph-target counts, POSITION/NORMAL deltas, activation tracks, and reset tracks;
- embedded textures and absence of unintended external dependencies.
- neutral/default transforms for controls omitted by individual actions, tested by switching from a strongly posed clip into every other clip on the same rig;

Use tolerances appropriate to asset scale and record them in the report. A pass/fail without the measured values is weak evidence.

## Fresh-import visual validation

1. Import the produced GLB into a clean Blender scene.
2. Sample every clip from the imported hierarchy and skin, not cached authoring data.
3. Render representative views and full motion cycles, including underside and rear when appendages overlap.
4. Inspect floor contacts using deformed surface geometry, foot slide, joint collapse, skin tearing, rigid-island drift, face/hand ownership, wing membranes or feather panels, and texture/material appearance.
5. Review each action at normal speed from the gameplay camera. Record artistic readability separately from technical fidelity.
6. Copy the export and only its declared dependencies into a clean temporary directory, then reimport from that copy. This catches textures or files resolving from the authoring workspace by accident.
7. Load the copied GLB in Godot and verify import, clip discovery, playback, action switching, loop behavior, root behavior, facing, bounds, scale, and action mapping.

For Blender-authored deliveries, also verify ordinary playback after selecting different Actions: action range, scene range, preview range, NLA state, FPS, and action slot are distinct. A dedicated review scene does not replace this test.

## Packaging gate

Deliver only when the manifest binds evidence to exact file hashes. Include:

- final self-contained animated GLB;
- fitted rig without the final motion set when available;
- animation profile/action mapping;
- rig graph or bone map;
- source mesh and concept references;
- generation and validation reports with tolerances;
- Godot probe results;
- representative renders or GIFs;
- known limitations and recommended manual polish;
- hashes for deliverables and evidence.

The report must distinguish:

1. source/authoring checks passed;
2. exported geometry and motion match within stated tolerances;
3. Godot imported and played the intended files;
4. visual quality was reviewed at gameplay scale;
5. explicit user approval, when it actually occurred.

Prevent stale evidence: regenerate probes and previews after the animated GLB changes. Rebuilding a base rig replaces animations, so reapply flight, hopping, or other supplements before validation. Preserve prior validated revisions and user review notes.

## Wolf motion lessons

Use separate gates for stride reach, paw/heel surface contact, shoulder placement, elbow direction, airborne paw pitch and skin deformation. A contact pass does not certify a correct elbow or neck. Trace surface weights: a named ankle can be a sibling heel helper, and shoulder-owned fur/ornaments may need a native offset adapter rather than a large rotating shoulder. Rigid collar shells need reviewed component IDs and one intended owner; source-only repairs do not transfer as category motion.

Fit a whole tail section coherently. Independent endpoint fitting can lower the image residual while producing a visually rejected counter-curl. Adapt amplitude/distribution to native target rest shape, and distinguish centered attachment from a sideways resting chain. A requested rest correction must bake the weighted surface/normals, update inverse binds and rebase native action channels, with default keys for omitted controls. Preserve segment lengths, UVs, weights and non-tail channels; compare deformed surfaces outside the repair scope and reset behavior. The accepted Moorland correction uses a one-degree tail-only clearance offset and leaves its walking surface outside the tail unchanged.

Record artistic acceptance against exact model and motion hashes without rewriting the accepted motion payload solely to change its status. Use a separate acceptance receipt and update presentation/manifest status. New actions start from the accepted animated GLB. Attacks retain anticipation/contact/recovery events; death retains a fallen held endpoint and transitions from paw to body support. Looping walk gates and automatic recurrence selection cannot certify those one-shot contracts.

For fallen creatures, inspect actual head/muzzle and distal-tail support patches. Shared neck fur can satisfy both a loose chest and head ownership test while the face is still floating. Use anatomically disjoint patches and verify their deformed bounds. Include native limb folding in the settled-body solve; longer transferred limbs can otherwise prop up the torso. Preserve native rest, skin and accepted Walk while replacing only the requested attack/death slots. Exact clip-end holds and restoration to Idle are separate engine checks from normal-speed visual review.

Audit jaw ownership with a weighted surface view before mapping generic bones. The Dire Wolf correction keeps upper-snout `Bone_049`/`Bone_048` with `Head` and opens lower-jaw `Bone_051`/`Bone_050` around its fixed native pivot. The Moorland Chin/Nose arc is a different actor policy. Test upper-snout stability, lower-jaw opening, segment lengths and reconstructed local transforms independently.

Sample early collapse poses at the reference timestamps as well as the final hold. A terminal contact pass can coexist with late, shallow foreleg folding. Check chest/head drop, signed elbow flexion and full forearm/neck/collar clearance, then lock the evaluated soles at sufficient semantic pose density. Recheck exported half-key motion after densification or reduction. When only the early phase is being corrected, compare the prior settled skin surface and unrelated clips against the final export rather than assuming they survived.

For a family of unlike native rigs, map physical shoulder/elbow/wrist/paw and hip/stifle/hock/paw before copying pose intent. Inspect hierarchy, rest positions and skin ownership; labels can be shifted by one joint or a named tail can actually carry a hind leg. Keep required joint/skin repairs in a separate prepared input with explicit scope and neutral-shape evidence. Serial wrists and sibling heel helpers need different elbow measurements. See the video-motion skill's family-transfer reference for long-claw offsets, rigid armor supports and endpoint continuity.

Inspect the native body pivot. A `root` beside a paw can make torso-pitch transfer unreasonable even when every limb role is correct. If adding an unweighted anatomical parent, preserve inherited translation/rotation channels on their original timestamps, compare the complete skin through all old clips, and check new parent distances. A previously qualified walk can retain its pitch pivot while height acts through the new parent; verify full-skin equivalence. Use evaluated physical hip heights for action adaptation instead of assuming root-local height is comparable between rigs.

Use the actual final dense contact pose for a recovered hold. A different coarse solution with the same paw endpoints can still produce a subframe slip when substituted at the hold boundary. Check contact velocity and floor clearance at twice the exported key rate, plus actual keys and half-keys; a coarse key-only pass is insufficient. Record the actual per-motion rate in the handoff and rebake tool.


After a requested family skin repair, compare fixed original anatomical triangle/vertex IDs so a changed influence mask cannot hide the defect. Distinguish stretched triangles from opened coincident seams. If using additional influence sets, verify the actual engine mesh retains the intended weights per vertex. Successful import alone does not prove this.

Center the complete visible tail and attached shells against the body midplane; a tiny named weighted chain does not establish a short anatomical tail. A mesh-only lateral correction can retain existing bind/rest pivots, but then every actual skinned clip still needs review. Keep its geometry/normal scope and skin ownership audit separate from category motion. Physical sole and distal-support regions must exclude nearby non-paw anatomy and use current prepared weights. See the video-motion skill's [skin and tail repair](../../rabbitlands-video-motion-fitting/references/skin-and-tail-repair.md) for contact-aware refitting and settled holds.

A support/hold pass can hide isolated pose jumps. Review actual skinned velocity, acceleration and jerk at the original cadence, including the approach to the hold. For transferred bites, evaluate physical upper-muzzle reach and aim on the native rest chain. Project all supported paws together when their skin shares influences, then check the exported keys and half-keys. See the motion-fitting skill [temporal quality reference](../../rabbitlands-video-motion-fitting/references/temporal-quality.md).

A temporally smooth, contact-valid transfer can still use the wrong limb articulation. Audit explicit source and target physical chains from side/front/rear/top and game views; validate elbow, knee and hock trajectories throughout the action. Use the established 3D fit as model evidence, distinguishing it from observed video data. Fit a feasible native terminal posture and verify its full approach. See the motion-fitting skill [anatomical motion audit](../../rabbitlands-video-motion-fitting/references/anatomical-motion-audit.md).
