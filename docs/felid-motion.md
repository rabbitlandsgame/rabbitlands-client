# Feline-family motion

Puma, Leopard, Cheetah, Moonshadow Lynx, Ice Snow Leopard, Stormmane Lion and
Tidal Crystal Lion use the seven user-reviewed feline sets. Each has a four-beat
walk, diagonal trot, pounce attack and side-fall death. These are locally authored
native-rig adaptations; no generated video supplied the animation curves.

The runtime GLBs are byte-identical to the reviewed files. Geometry, UVs, textures,
materials and native hierarchy are retained. The reviewed shared-skin repairs
anchor the physical paw pads and repair anatomical ownership. The Lynx's offset
right shoulder and elbow have corrected pivots and rebased inverse binds. Its
inherited motion is preserved through that rebase and a world-preserving bake of
its animated non-bone armature wrapper into the physical root bones. The Snow
Leopard's sibling heel helpers follow their paws. The Stormmane's crown and beard
follow its head. Both lions retain their native twin tails.

Idle, fighting idle and hit motion is retained. Intentional shared-skin repairs
apply across all actions; the Lynx's rebase changes channel representation. The
collapse adapts to native shape and contact surfaces. The Stormmane rests its head
on the mane/jaw envelope; the upper snout is measured separately. Detailed
preservation scope and exact hashes are in `docs/qa/felid-motion/promotion.json`.

All seven dedicated `data/animations/felines/` maps preserve existing action and
server-command bindings. Walk and trot retain normal authored cadence and use
measured stride speed at the unchanged registry import scale.
`strideScalesWithActor` applies existing actor/server scaling. IDs, model paths,
facing and attachments are unchanged. Attack lasts 1.60 seconds and death 2.60
seconds. This asset update does not change server damage or combat scheduling.

Every model declares the supported 3072-Hz glTF bake cadence, matched by its tracked
import policy. Animation optimization and compression are disabled. Exported keys
and between-key poses pass full-surface floor, planted-sole velocity, serial limb
length, loop and terminal-hold checks. Independent world-pose fixtures cover all
seven slots per actor. Fresh Blender imports agree with those witnesses. The
isolated current-client check covers 49 slots, actual action maps, four-influence
skin, off-grid worlds, switching, RESET and idle restoration. This is component
integration evidence, not a full client/server play session. Skin edge strain is
reported separately as a diagnostic, not an artistic score.

Run the portable installed-file audit from the repository root:

```powershell
python eloria-assets/tools/test_felid_motion.py
```

After importing the client project, run:

```powershell
godot --headless --path godot-client --script tests/test_felid_motion.gd
```

The engine check can also use an isolated project with the seven exact models,
registry entries, maps, fixture and current loader component scripts. Private
high-resolution originals, authoring stages, videos and processing records remain
in the ignored authoring workspace. A new family needs its own anatomical profile
and visual review; these cat curves do not establish compatibility with other
quadrupeds.
