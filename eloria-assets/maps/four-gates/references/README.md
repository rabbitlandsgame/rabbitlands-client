# Four Gates client comparison set

Every image here is a screenshot from the **running Godot client** rendering the
shipped `world.glb` through the production `WorldLoader`, captured by
`godot-client/tests/integration/rendered_four_gates_views.gd`.

- `comparison-reference-vs-client.webp` — the eleven supplied concept panels
  beside the closest client view. The pairing is an art-direction judgement, not
  a claim that the camera matches exactly; it is intended to let composition,
  landmark presence, shape language, material and colour be compared directly.
- `contact-sheet-client-views.webp` — all 22 client views on one sheet.
- `00-*` … `20-*` — the individual client views at 1600×900.

Rendering conditions: OpenGL compatibility renderer on llvmpipe (software GL,
no GPU), manifest-declared environment, no post-processing beyond the
manifest's filmic tonemap.
