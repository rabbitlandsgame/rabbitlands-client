# Approved cape fit and bone-motion source

This portable package records the user-approved v100 cape geometry, skin and motion reviewed in video101 on2026-10-31. It contains two fits for the same cape: wardrobe and armour. It replaces neither a body mesh nor a body animation, and does not change the original65 body-bone rests.

Rebuild the runtime data from the client checkout:

```powershell
python eloria-assets/tools/prepare_approved_cape_motion.py
python eloria-assets/tools/prepare_approved_cape_motion.py --check
```

The generator requires NumPy and reads only this source package. No Blender project, private path, paid service or retired model generator is needed for replay. `source-catalog.json` binds the fit buffers and `approved-motion.npz` to their SHA-256 hashes and records the reviewed authoring-stage hashes. The numerical archive contains only arrays, without pickled objects.

The fit buffers store the approved surfaces in native model coordinates (right handed, Y up). Their scalar arrays are little endian: float32 positions, normals, tangents, UV and weights; int32 indices and bone slots. Each render vertex retains eight slots and refers to the17 names in the catalog: the12 cape controls plus spine_03, clavicle_l/r, neck_01 and Head. Material slots0â€“2 borrow the existing generic cape's Base, Trim and Detail resources. Existing colours and perk emblems continue to use the original material and UV paths; no texture is duplicated here.

The cape was authored through a scene containing differently rebound skins. Therefore the five body-owned named binds include a measured joint-frame correction. Do not replace them with inverse skeleton rests or run the legacy geometry fit over the approved arrays again. Native reference poses combined with the corrected skin reproduce the approved cape to0.091mm maximum /0.028mm RMS in the independent numerical witnesses; see `native-adapter-validation.json`.

For control i, the runtime cape-only writer uses native skeleton-global transforms:

```text
cape_global_i = spine_pose * corrected_spine_bind
                * Translation(control_i) * cape_bind_i.inverse()
```

It writes only the12 cape bones. The five body-owned skin contributions follow their existing body poses. Inactive/reset presentation uses the complete approved idle control vector rather than leaving an earlier action's pose behind. Legacy or mounted writers need the explicit neutral-frame bridge documented by the runtime implementation; native cape rest alone differs from the corrected source frame by about33mm and0.319degrees.

`approved-motion.npz` preserves the complete approved episode and an intrinsic attack field with the preceding run carry removed. The generated runtime library uses original native clip seconds, not the combined review montage. Walk and run are three-harmonic phase averages of the steady source windows, with position and finite velocity closure. Their lower nine controls receive a bounded measured gain to retain at least95% of the approved hem/middle excursion; the first row is not amplified. Peak excursions stay within the recorded approved steady limits. This loop projection is deliberately documented as an approximation to the longer, nonperiodic episode.

Entry-only hand clearances are separate from repeating gait curves. The optional entry table follows unwrapped native seconds from action entry, is added after the idle/travel blend, and never repeats on each body loop. Intrinsic attacks retain the approved local hand clearances; the runtime supplies outgoing-state inertialization. Supported actions write every cape control. Inactive quality or crowd presentation holds the complete approved idle pose. Unsupported or cinematic states use the bridged legacy writer on the approved fit; mounted presentation uses its qualified legacy geometry, skin and solver.

The runtime artifacts are `godot-client/data/actors/cape_motion/{catalog.json,wardrobe-fit.bin,armour-fit.bin,motion.bin}`. Import, actual gameplay fitting, switching, mount/fallback and performance qualification remain separate from this portable source record.
