# Playable skin and eye mapping audit

Reviewed all eight playable races, both female and male variants: Luminous,
Votary, Glasswarden, Orun, Greyhaven, Ssarathi, Stoneborn and Mycelari.
The September 8 audit uses actual Godot actor renders, with bald heads to expose
the scalp, front and both side views, and both hands in the canonical rest pose.

## Findings and repairs

The retained head UVs align with each race's original painted face. The previous
eye and brow partitions selected complete triangles, however, so changing eye
colour painted angular patches onto eyelids and surrounding skin. Orun male
missed one painted eye, Votary male included an ear patch, and Stoneborn male
coloured the brow above its narrow eyes. Reptilian and fungal eye shapes also
extended outside those selections. Returning the source atlas to these regions
made the underlying eyes read correctly.

All sixteen variants now use a source-UV mask: red protects the complete painted
eye from skin dye, green selects the iris, and blue selects painted eyebrow
pigment. The face shader preserves pupils, sclera, painted highlights and each
race's eye shape. The face, old eye/brow partitions and scalp share this material,
so every texel receives the appropriate colour regardless of its old triangle
classification. Non-hair brow ridges retain their source skin texture.

The single-surface tint path previously multiplied the active material override,
causing eyes and scalp to darken on every appearance update. It now starts from
the original mesh material. The face material similarly takes absolute colour
parameters and is private to each actor.

The neck bake reflected a strip above the head cut down the entire neck. It
included mouth/chin details, producing duplicated mouths on Greyhaven female
and Votary, repeated chin shading on Luminous and Orun, and repeated dark jaw
marks on Glasswarden. All sixteen neck atlases are now rebuilt from actual
neck skin below the head cut, using one monotonic extension. Source collars are
excluded per texel, and missing skin behind a high collar uses nearby genuine
neck samples. The last atlas row matches the existing head boundary exactly.
The shared-body authoring pipeline also uses the corrected sampler, so future
body builds do not reintroduce the reflection. These are texture overrides on
the existing cylindrical UVs.

The mapping repair itself did not modify body GLBs, vertices, UVs, rigs, source
head textures or animations. The subsequent humanoid chin/jaw refinement is
documented in `facial-features.md` and updates twelve body GLBs.
Skin on the face, scalp, neck and both hands was inspected for all variants.
Source painted details remain; the separate facial refinement preserves UVs.

## Reproduction

From the repository root:

```powershell
python eloria-assets/tools/build_face_masks.py --models godot-client/assets/actors/native/races --out godot-client/assets/actors/native/face_masks
python -m pytest -p no:cacheprovider godot-client/tests/test_face_texture_mapping.py -q
```

`build_neck_textures.py`, which baked `neck_textures/`, was retired in the race
programme's P7 cleanup (2026-10): the rebased race bodies carry the Human neck
and no model names a neck texture any more (the manifest is `{}`). The baked
PNGs stay as the inputs `test_face_texture_mapping.py` still checks.

The reviewed polygon annotations are in `tools/face_regions.json`. Coordinates
refer to the canonical rest mesh projected from +Z; the JSON records the scale
and each crop origin. The mask and neck manifests hash both source GLBs and
generated textures. Re-review the annotations when a source head changes.
The `canonical-source` inputs are the sixteen full-body race GLBs from commit
`68f4f6e20e7c11051aecbb580c03b47b89a25393`, before the shared-body graft. The neck
manifest records their hashes. The installed shared-body GLBs are not suitable
as the `--sources` input, because their original lower necks were replaced.

After importing the Godot project, run
`tests/integration/face_texture_mapping.gd` for runtime checks. Set
`ELORIA_FACE_ARTIFACTS` to an absolute output directory and run
`tests/face_texture_preview.gd` for captures. `ELORIA_FACE_MODELS` optionally
limits captures to comma-separated model slugs.

## Validation

- Source-UV landmarks, off-eye skin samples, mask/source hashes, neck boundaries
  and repeated-mouth regressions: **3 Python tests and 38 subtests passed**.
- Actual actors: **16 variants, 1,920 skin/eye combinations, 11,451 checks,
  zero failures**, including helmet/armor changes, recolouring while equipped,
  and the independent single-surface tint regression.
- Character creation integration: **passed in structure-only mode**.
- **128 final engine captures** cover front, both sides, dark skin/red eyes,
  reset, source-atlas comparison, and both hands. All sixteen default/reset
  image pairs are pixel-identical.

Before/after captures and logs are in the workspace's
`work-output/face-mapping/` directory. Restart an existing client session to
load the updated appearance code and textures.
