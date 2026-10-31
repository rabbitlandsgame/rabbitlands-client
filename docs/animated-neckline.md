# Animated default shirt neckline

The default Human female shirt uses a symmetric collar opening. Its inner rim
now follows the underlying neck's canonical weights, mirrored by left/right
bone meaning. The remaining upper-shoulder openings are closed with 15
triangles using existing vertex records. Cloth positions, normals, UVs,
materials, skeleton, inverse binds and morph payloads are unchanged.

The source-skin clipping mask must use unposed coordinates. The supported
Godot RD renderer skins vertex positions in a compute pass before the spatial
shader's `vertex()` function. Reading `VERTEX` there moved the opening's cut
through the animated neck. `CUSTOM0` now carries the canonical mesh positions
through the separate attribute stream.

The existing body-refinement cache creates that channel before deforming the
female body. The existing head cache adds it only to the female head's body
patch. Its packed vertex, skin, index and morph buffers remain exact; face and
eye primitives are copied as packed surfaces without another normal/tangent
encoding pass. Both ordinary and classic High skin shaders use the same mask.
The original UV and colour channels retain their authored purpose.

There is no additional mesh cache or runtime lining node. Existing body
refinement and head-cache restore/release paths own the derived meshes. The
carrier survives the body cut, face sculpt, classic High subdivision and head
identity bake. The identity-bake byte estimate includes custom attributes.

To reproduce the shirt processing, retain the original repaired shirt with
SHA-256 `33bc520528eb0631087e728a0d3f04b99370196e445379f83f7c308b90938a29`
and the canonical female body with SHA-256
`3a8ff81e9f152102ee1e57d892759c0a8e69ab49064ab8e473f5cb9ed3e8fc94`.
Use a new ignored output stage; the processor refuses to overwrite a take.
It requires the existing authoring dependencies NumPy, trimesh and Shapely.

```powershell
python eloria-assets/tools/rl_heads/hair/repair_animated_female_neckline.py `
  --source-shirt .local/neckline-inputs/luminous_female_shirt.glb `
  --body godot-client/assets/actors/native/races/luminous_female.glb `
  --out .local/neckline-candidate/luminous_female_shirt.glb
```

The report binds the original, body, processor and candidate hashes. It records
the exact collar and shoulder scope, four-influence reduction, mirrored weights
and unchanged channels. It is not a command to regenerate a head or hairstyle.

Focused checks are `tests/test_mesh_rest_coordinates.gd`,
`tests/test_female_shirt_neckline.gd`, `tests/test_human_body_refinement.gd`
and `tests/test_character_proportions.gd`. The rest-coordinate check includes
packed face/eye and morph preservation, a pre-existing custom channel, classic
High midpoint interpolation, non-neutral body proportions, all qualities,
classic High fallback, torso changes and exact cached Medium restoration.
Run `tests/test_legacy_hair_material_lifecycle.gd` with Vulkan when qualifying
the combined actor path. Actual Idle front/profile/rear views remain necessary
for judging the collar and skin contact.
