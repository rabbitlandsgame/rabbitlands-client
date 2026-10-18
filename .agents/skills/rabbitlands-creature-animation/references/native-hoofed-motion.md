# Native hoofed-family motion

Use this reference when fitting grounded hoofed walk/trot, horn-led strikes and supported collapse. The seven reviewed native sets are documented in `docs/caprine-motion.md`; consult current private selection/publication memory before continuing. Their curves are authored, not recovered from a generated video.

## Physical frames and symmetry

A named forward axis can differ from the visible torso and face. Thunder Ram's native trunk is skewed about 29 degrees; Cobalt Ibex's is skewed about 10 degrees. Estimate anatomical forward from actual torso geometry, paired leg roots and balanced facial surface patches. In Cobalt, a dense one-sided nose patch biased the estimate; equal weighting of nose/cheek regions gave a useful head direction. Correct the face relative to the torso, then carry that frame through all four authored actions. A walk-only correction leaves the strike and collapse visibly misaligned.

Measure hoof spacing relative to the anatomical centerline. Mirror the signed fore-to-hind outward difference, rather than forcing both feet to the same X or moving only a hoof target. Cobalt's approved right forehoof sits slightly outside its hindhoof. The matching left-side correction moves the complete scapula branch inward and refits its sole targets, retaining that outward difference. Moving the distal target alone can leave the upper leg detached from the shoulder. Recheck contact, serial lengths and silhouette. If the branch offset also applies to inherited idle/hit clips, declare that scope and prove every unrelated sampler and bone remains unchanged.

A tilted native hoof may require its own physical sole-plane frame. Fit the pad geometry in that frame before choosing a neutral ankle rotation. A generic foot angle can preserve a persistent outward lean. Check front, rear, both quarters and side views at identical times, plus normal-speed playback; a useful side view can hide crossing legs.

## Hierarchy, attachments and collapse

Inspect actual native parenting before IK. Golden Bison's thighs were siblings of their proximal controls; Whitehorn Yak's distal helpers needed to follow the physical hoof. Version such preparation and preserve rest-world transforms, inverse binds and inherited world motion. A non-bone wrapper's motion must be represented on physical roots when the client importer ignores that wrapper.

Rigid low hoof pads need coherent distal ownership with a smooth transition into the leg. Hanging coat pieces can mix tail and leg influences; repair each actual piece at its attachment, accounting for split vertices. Moss Horn Ram needed a feathered coat transition and Whitehorn Yak a coherent hanging tuft. A bone-only witness does not certify skinning: measure repaired surface points and inspect both rear quarters. Keep geometry, texture and morph arrays exact.

Disconnected collar and chest tufts can be wholly assigned to a foreleg, so a mixed-weight threshold alone misses them. Identify the visible attachment from welded physical components and multiple views, including hanging central pieces. Preserve the nearby fringe that belongs on the upper leg; treating the entire ruff as torso skin can drive those lower tufts through the floor during collapse. Give a rigid coat piece coherent ownership at its actual chest/neck attachment, then recheck the full deformed surface.

For a skin-only revision, prove animation arrays, geometry/binds/textures and protected hoof rows are unchanged. Add surface probes at repaired roots and tips across inherited as well as authored slots. Refresh both aggregate and actor-specific witnesses and reject a render witness whose model hash differs from the rendered file; an old actor-specific file can silently take precedence over a fresh aggregate.

For death, use the actual supporting horn/head envelope and body side. Do not force a horned animal's muzzle onto the floor while its horns already support it. Fit head, torso roll, free-leg tuck and floor envelope together. Measure local and world angular changes at playback cadence as well as between keys: Thunder's initially valid contact/length metrics hid an abrupt limb swivel. Refit the transported bend frame or tuck rather than merely increasing key count.

## Qualification and promotion

Keep source preparation, exported-motion qualification, current-client playback and user visual acceptance separate, each bound to the final combined file hash. Reused evidence needs byte-identical unchanged actors or exact sampler/static-array proof. Inherited clips can change intentionally through a declared branch offset or wrapper bake; describe world preservation accurately instead of claiming all channels are unchanged.

Public `test_caprine_motion.py` checks all 28 authored actions and the independent witnesses; `test_caprine_motion.gd` checks all 49 installed slots with the current client components. Persist qualified import cadence and measured stride speed at actual import scale. Stage tracked `.import` settings, import again, then run the engine check; stale cache remaps can invalidate a seemingly successful run. Publish only runtime files, maps, concise evidence and portable checks. Preserve unrelated local edits during integration.


## Deer and elk transfer lessons

Map physical chains from rest positions, parenting and surface ownership. Names such as `hips`, `head` or `ear` can belong to another visible region. Apply paired hoof-lane alignment to all four actions. Check the collapse solver separately: its transported rest pole can bypass a sagittal-plane correction used by walk/strike, leaving a sideways elbow bend during death.

Compact rigs can pass a straight blend of free-hoof targets through the unreachable inner radius of a two-section leg. Use a feasible radial path and resolve the actual paw surface floor together. Inspect angular changes at normal playback cadence as well as at exported keys/half-keys. A high export cadence can hide a brief visible swivel. Earlier gathering and a gentler fall can improve continuity while retaining protected hoof-release times and the final held pose. Keep any timing warp actor-specific and record both source-pose and display times.

Compare the declared animation cadence, tracked import policy and the current runtime ceiling. A denser prototype can pass native contact checks while exceeding the client loader's supported cadence. Do not treat that as deployable evidence. The compact Crown Antler Stag instead uses a slightly longer brace within its existing action duration, qualified at the current client cadence. Bind the final combined file to fresh physical-surface witnesses and action-switch/hold checks after every selected refinement.
