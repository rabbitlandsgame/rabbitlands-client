# Luminous animated GLB runtime

Luminous female (actor type 0) and male (actor type 1) are rendered directly
from the original `Superhero_<sex>_FullBody.gltf` files under
`actors/playable/native`. Other actors continue to use Cal3D. The runtime
preserves the three native skinned meshes, 65-joint hierarchy, inverse binds,
UVs, materials, and referenced PNG textures.

The source character meshes are Quaternius Universal Base Characters and the
source animations are the Quaternius Universal Animation Library (CC0-1.0).
The native character files and `Universal_Animation_Library.glb` are checked
in under `eloria-assets/source/player_models/native`; the data generator copies
them byte-for-byte. The client samples the animation library by native bone and
clip name without rebuilding the character skeleton or skin weights.

## Client action mapping

| Client action | GLB clip |
| --- | --- |
| standing, alternate standing | `Idle_A`, `Idle_Subtle` |
| walking, running | `Walk`, `Jog` |
| combat stance and held combat stance | `Fighting_Idle` |
| melee/ranged and held attack frames | `Sword_Attack` |
| spell attack | `Spell_Simple_Shoot` |
| pain, death | `Hit_Chest`, `Death_A` |
| sit transition, seated idle, stand transition | `Sitting_Enter`, `Sitting_Idle`, `Sitting_Exit` |
| harvest, pick up, drop | `Farm_Harvest`, `PickUp_Table`, `Throw_Object` |

Animation time remains driven by the existing actor command lifecycle, so
movement duration scaling and server protocol behavior are unchanged. The GLB
runtime samples native rotation and translation tracks and CPU-skins each
original primitive per visible instance. Native materials replace legacy actor
texture-atlas composition for these two actors.

## Limitations

The path supports linear and step rotation/translation tracks, native unsigned
8/16-bit joints, and unsigned 16/32-bit indices. Cal3D state remains only for
protocol timing, attachments, and non-GLB actors. The fixed-function renderer
uses native base-color materials; native normal/roughness shading and
GLB-driven equipment attachments remain follow-up work.
