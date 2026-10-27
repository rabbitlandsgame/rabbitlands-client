# Human portrait hair

This optional High finish interprets the Human leaderboard studies with compact, explicitly authored lock guides. It changes no source GLB, skeleton, equipment asset or animation. The guide sets cover male Parted/Tousled (Rowan), male Parted/Swept (Tavi), and female Buns/Swept (Mira). Other choices retain their fitted style and the common High surface finish.

hero-locks.json stores cubic design points and source-conformed ring samples in canonical Head-rest metres. Samples return to neutral hair size before shipping. Runtime applies the same length/volume field as the imported cap, then builds opaque tapered elliptical clumps once per distinct appearance. Clumps merge into the existing surface: no extra node, surface, draw, texture, alpha-blended card or per-frame simulation. LOD index chains retain the added silhouette. Head and Neck use the existing Skin binding, with at most 20% Neck influence on the nape.

Both hair controls are integers 0..100, neutral 50. Low and Medium reshape existing vertices, adding no hair triangles or textures. High adds authored layers and bounded curved-edge refinement. Imported meshes/materials stay immutable and restore exactly on downgrade. High caches hold at most 24 meshes/128 materials; active actors can retain shared meshes after eviction. The last High user releases these caches and guide data. Existing lower-tier Groom caches remain bounded at 40 hair/32 beard meshes.

The High shader uses fixed UVs and derivative-filtered bands. Source paint is mostly desaturated before applying selected pigment; warm highlights and dark roots preserve the chosen colour. Base cap COLOR.r=0; locks use COLOR.r=1, COLOR.g for fixed pigment variation, COLOR.b for progression. Cap COLOR.b stores crown height. No time or camera-space noise drives the paint.

## Beard fit contract

UV1.xy and COLOR.g retain the current shaped skin anchor (z is stored as z+0.2) expected by HighPortrait. UV2.xy and COLOR.b contain the canonical pre-face anchor (again z+0.2) for coverage/strokes. COLOR.r stores canonical growth coverage with the renderer's colour-byte quantization. Both selection and post-subdivision evaluation use the shared inverse-face helper. Measured canonical mouth_height keeps the cutout aligned through face-length/lip-fullness changes. High beard refinement preserves this payload and the same shader/surface, then restores to HighPortrait's result before HighPortrait restores the lower-tier source.

## Focused checks

tests/human_groom_reference_preview.gd exercises actual centralized presets, size choices, weights/indices, quality restoration, walk/run samples, helmets, cleanup and individual face-length/lip-fullness extremes. RL_GROOM_REFERENCE_OUTPUT selects an ignored review folder; RL_GROOM_QUICK_RENDER=1 limits capture to six views. tests/test_high_hair_appearance.gd checks source immutability, every existing colour, shared geometry and exact resource restoration. Optional RL_HIGH_HAIR_FULL_AUDIT=1 covers all Human styles/finishes and is unnecessary for shader-only changes.
