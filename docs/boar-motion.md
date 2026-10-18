# Boar and tapir motion

Mossback Boar, Brambleback Boar, Autumn Bramble Boar, Berry Bramble Boar and Tapir
use the five user-reviewed native motion sets. Each has a grounded four-beat walk,
a diagonal trot, a head-led strike with recovery, and a support-aware side-fall
death. These motions were authored locally and fitted to native anatomy; no
reference video supplied the curves.

The runtime GLBs match the reviewed files byte for byte. Geometry, UVs, normals,
textures, materials, hierarchy, rest transforms and inverse binds are retained.
Scoped skin repairs anchor the physical low hooves. Brambleback also has two
hanging rear bramble pieces bound coherently at their native tail root, removing
the conflicting tail/thigh/knee/ankle pulls. The repair covers entire physical
pieces, including their duplicated UV and normal seams. All seven Brambleback
animation sampler arrays are exact across that foliage repair.

The three inherited idle, fighting-idle and hit motions are retained. Brambleback's
animated non-bone wrapper is baked into its physical root bones for the current
client importer, preserving primary bone worlds and the skin outside intentional
weight repairs. Its channel representation changes. Native hoof and foliage
repairs affect the shared skin across all actions. Detailed hashes and preservation
scope are in `docs/qa/suid-motion/promotion.json`.

The heavy strike braces the rear hooves, steps with the front hooves, drives the
head forward/upward, then recovers with staggered foot release. At least two
hooves support the action. Long-snouted boars use shallower anticipation for face
and tusk clearance. The shorter-legged tapir uses a deeper crouch and shorter
forestep for a head-led shove. The tapir collapse transports its native bend frame
to avoid a brief flexion-plane singularity and uses an inward free-paw tuck.

Dedicated `data/animations/suid/` maps preserve existing action and server-command
bindings. Walk and trot play at normal authored cadence, with measured stride
speed at the existing registry import scale. `strideScalesWithActor` accounts for
actor/server scaling. IDs, model paths, facing and attachments are retained.
Attack lasts 1.60 seconds and death 2.60 seconds. Server damage and combat
scheduling are outside this asset update.

All five models declare the supported 3072-Hz glTF bake cadence, matched by tracked
import policies. Optimization and compression are disabled. Exported keys and
between-key poses pass full-surface floor, supported-sole speed, native serial
length, rotation, loop and terminal-hold checks. Independent off-grid world
fixtures cover all 35 animation slots. Fresh Blender imports agree with those
witnesses; Brambleback's foliage repair also has independent skinned-surface
witnesses and same-pose original-edge measurements. Skin strain remains a
separate diagnostic from user visual acceptance.

Run the portable installed-file audit from the repository root:

```powershell
python eloria-assets/tools/test_suid_motion.py
```

After importing the client project, run:

```powershell
godot --headless --path godot-client --script tests/test_suid_motion.gd
```

The engine check can also use an isolated project containing the exact five
models, registry entries, maps, fixture and current loader components. It covers
all35 slots, four-influence skin, independent off-grid worlds, action switching,
held endpoints, RESET and idle restoration. This is component integration evidence,
not a full client/server play session. High-resolution originals, authoring
stages, review videos and processing records stay in the ignored authoring workspace.
