# Native character and animation runtime

Playable characters are instantiated directly from the supplied native glTF 2.0 packages. The generated hierarchy, skins, skeletons, materials, morphs, and animations are retained. ReplicatedActor3D applies only an outer scale/orientation adapter and never rebuilds bones or meshes.

Animation selection is explicit data: gameplay action to exact clip name, and server command to gameplay action. Substring guessing is prohibited. Root motion never controls replicated actor position.

## Verified source assets

The user-supplied archive and animation GLB were compared using Git blob hashes. They match the canonical files already on develop byte-for-byte:

- Superhero_Female_FullBody.gltf plus bin and seven referenced textures
- Superhero_Male_FullBody.gltf plus bin and seven referenced textures
- Universal_Animation_Library.glb (the uploaded exported-model GLB)

Each body has one 65-joint skin, three meshes, and three materials. The animation GLB has 162 clips and a 66-node hierarchy. The only bone-name difference is animation head to model Head; this is an explicit per-model alias. The animation-only head_leaf node has no target and is intentionally ignored.

Godot loads both glTF and GLB natively through GLTFDocument. No custom mesh, skeleton, skin, or legacy actor format is generated.

## Exact gameplay mappings

Idle_A/Idle_Subtle, Walk, Run_Female, Fighting_Idle, Sword_Attack, Bow_Release, Spell_Simple_Shoot, Hit_Chest, Death_A, Sitting_Enter/Sitting_Idle/Sitting_Exit, Farm_Harvest, PickUp_Table, Throw_Object, and Greeting are explicitly mapped in data/animations/luminous.json.

## Remaining runtime validation

A Godot 4.7.2 executable is still required to render both bodies, cycle every mapped clip, inspect Skeleton3D/rest pose/materials, and verify attachments under gameplay lighting. Registry status remains source_validated_runtime_pending until that executable validation passes.
