# Humanoid chin, jaw and eyebrow refinement

Both variants of Luminous, Greyhaven, Votary, Orun, Glasswarden and Mycelari
received lower-face geometry refinements. Chin projection, jaw breadth and the
recess below the chin are tuned per model. Female Luminous and Orun use smaller
displacements to preserve their finer source triangles. Stoneborn and Ssarathi
GLBs remain byte-identical to the fitted bodies before this refinement.

The deformation uses one continuous field across the head and neck, including
material and UV seams. Normals use its inverse-transpose Jacobian; tangents use
the forward Jacobian. Face UVs, painted mouths and eyes, skeletons, skin weights,
topology, head attachments and clothing remain intact. The tool rejects repeat
application, a folded deformation or a source triangle turning over.

Eyebrows on all twelve faces were checked. Glasswarden female's existing painted
brows now receive the brow pigment mask. Bare brows on Glasswarden male,
Luminous male and both Mycelari variants receive tapered directional hair
strokes in the same source UV mask. These strokes follow the brow ridge and
share the hair colour selector. The other seven variants retain their painted
brows. Stoneborn and Ssarathi brow masks remain empty.

## Reproduction

Use fitted race GLBs from commit `562ddf09d2b5f85fb4715523065114b9ed39490a` as
the input directory. Do not apply the tool to already refined GLBs.

```powershell
python eloria-assets/tools/refine_facial_features.py --models <fitted-bodies> --out <candidates>
```

The tool emits twelve candidates and a provenance manifest. The reviewed
manifest is `facial-features-manifest.json` beside this document. After
installing the candidates, rebuild the face masks and neck texture manifests
with the commands in `face-texture-mapping.md`. Neck UVs and boundary textures
remain identical, so the neck bake produces the same texture pixels.

## Validation

- Paired source/candidate checks for all twelve changed bodies: rig, weights,
  UVs, topology and clothing preserved; no turned-over triangles; material and
  UV seam positions agree within four micrometres. Four excluded bodies are
  byte-identical to their inputs.
- Face mapping: **4 Python tests, 50 subtests passed**, including independently
  measured landmarks for two separate eyebrows on every humanoid variant.
- Shirt/hair fit regression: **2 Python tests, 80 subtests passed**.
- Actual Godot actors: **16 variants, 1,920 skin/eye combinations, 11,611 checks,
  zero failures**, including brow colour updates and equipment transitions.
- Engine captures include the front, both three-quarter views, both profiles,
  dark skin, reset and hands. All twelve humanoid default/reset pairs are
  pixel-identical. The front, profile and dark-skin contact sheets were reviewed.

Captures, comparison images and the detailed geometry report are in the
workspace's `work-output/facial-features/` directory. Set
`ELORIA_FACE_PROFILES=1` when using `tests/face_texture_preview.gd` to include
the full left and right profiles.
