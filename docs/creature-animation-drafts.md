# Additional creature animation drafts

Twenty-three current imported creatures now use authored, actor-specific animation sets. They remain **drafts awaiting visual review**. The earlier accepted sets and the previous 47 installed drafts retain their existing files and review records.

| Group | Creatures |
| --- | --- |
| Aquatic mammals | Manatee, Dolphin |
| Low crawlers | Caecilian, Mudskipper |
| Fish | Abyssal Armored Fish, Hammerhead Shark, Sturgeon, Seahorse, Luminous Manta Ray |
| Cephalopods | Octopus, Cuttlefish, Nautilus |
| Jellyfish | Levitating Jellyfish |
| Crabs | Bronze Tide Crab, Crystal Shore Crab, Delta Mud Crab, Glacier Crab, Manymouth Crab |
| Lobster | Lobster |
| Beetles | Bronze Diving Beetle, Crystal Carapace Beetle, Amethyst Stag Beetle |
| Moths | Amber Lantern Moth |

Each set maps idle, alert, recoil, two movement actions, attack and death to the existing client action slots. Movement follows the sculpt: swimmers and hovering creatures do not claim planted walking contacts. Attachment aliases, authored travel speeds and the required import cadence are explicit; actor scale and forward correction remain unchanged.

The selected drafts retain native segment lengths or fixed appendage roots, coherent surface ownership, actor-specific attacks and supported held endings. Source geometry, materials, images, skin and rest transforms remain exact in the runtime copies. Numerically flat animation channels are normalized only where bounded comparisons confirm the same motion to floating-point precision. Genuine motion cadence and source textures are retained.

The authoring review includes native-speed videos from six angles, pose sheets and anatomy-appropriate contact or support details. Run review-creature-animations.bat from the authoring checkout to inspect them and save per-creature/per-animation comments. Videos, high-resolution sources, authoring scripts, frozen recipes and comments stay in the ignored local authoring workspace. Runtime integration does not mark an artistic review approved.

Offline verification:

```powershell
python eloria-assets/tools/test_creature_animation_drafts.py
Godot --headless --path godot-client --script tests/test_creature_animation_drafts.gd
blender --background --factory-startup --python eloria-assets/tools/check_creature_animation_drafts_blender.py -- --root . --report blender-check.json
```

The native check verifies installed hashes, mapped actions, import settings, unsigned joint storage, attachment names, speed metadata and independent off-grid surface/normal/bone witnesses. Fresh Blender and current Godot checks evaluate the runtime copies, including loops, one-shot holds, action switching and RESET. Reports are in [the verification folder](qa/creature-animation-drafts/).
