# Forward+ crowd visual readiness

The focused visual review found and corrected one concrete Forward+ color-space
error in the production spell-flight shader. The final shader now matches
Godot's `StandardMaterial3D` color handling in Compatibility and Forward+ for
three unsaturated controls, including channels on both sides of the sRGB
transfer threshold. Representative equipment, fixed actor poses, overhead
names and health, ground, spell flight, and a complete radiation contact remain
present in the final captures.

This is a bounded visual-readiness result. It does not establish complete game
renderer parity, it does not measure FPS, and it does not change the ordinary
shipping renderer. `project.godot` still selects `gl_compatibility` for desktop
and mobile. Forward+ remains a separately selected comparison mode.

## Controlled fixture

`tests/integration/rendered_renderer_parity.gd` builds three production
`ReplicatedActor3D` rigs using the two complete equipment kits from the crowd
benchmark. It fixes all actors at animation position 0.37 seconds and records
their equipment mesh counts and selected-bone pose hashes. It also fixes a
production fire flight at 56% of its analytic duration and a production
radiation contact at 0.42 seconds. The environment, camera, ground, light,
screen dimensions, positions, and effect ages are identical between renderer
runs.

The fixture disables native presentation (`ELORIA_NATIVE_PRESENTATION=0`) so
the comparison isolates the GDScript geometry and shader path used in the
historical diagnosis. It disables GPU particles because their simulation is
not deterministic across fresh processes. Cape cloth is held inactive after
the fixed authored pose. Those two restrictions apply only to this visual
fixture; production particles and cloth are unchanged.

The final framing contains all three actors and the complete radiation contact.
Each actor has ten native equipment meshes. The two renderer runs record the
same actor mesh counts (28, 55, and 29), animation position, action, inactive
fixture cloth state, and selected-bone pose hashes.

## Historical v2 diagnosis

The original shader assigned the sRGB-authored mesh vertex value directly:

```glsl
ALBEDO = COLOR.rgb;
```

V2 placed the same solid `#6bcddb` color into an unlit additive
`StandardMaterial3D` control and into the production `spell_energy.gdshader`
vertex-color path. Compatibility made the two agree (RGB
`[0.709403, 1, 1]` versus `[0.708807, 1, 1]`, RMSE `0.000344`). Forward+
produced `[0.501961, 0.858824, 0.912018]` through `StandardMaterial3D` but
`[0.725490, 0.956863, 0.984314]` through the vertex-color shader, an RMSE of
`0.146974`.

The Forward+ vertex result matched the prediction obtained by treating the
sRGB numeric channels as linear light (prediction RMSE `0.001277`). The
`StandardMaterial3D` result matched decoding the source color before linear
additive blending (prediction RMSE `0.001000`). That isolated the fault from
lighting, effect geometry, animation time, and the broader crowd scene.

Godot documents [`OUTPUT_IS_SRGB`](https://docs.godotengine.org/en/4.6/tutorials/shaders/shader_reference/spatial_shader.html)
as true for Compatibility and false for Forward+ and Mobile. The same spatial
shader reference says vertex `COLOR` passes through to the fragment stage.
Godot's [shader language documentation](https://docs.godotengine.org/en/4.2/tutorials/shaders/shader_reference/shading_language.html)
describes `source_color` as the hint that converts color uniforms and textures
from sRGB to the linear 3D rendering space; mesh vertex `COLOR` cannot carry
that uniform/texture hint. Godot's documented `FUNC_SRGB_TO_LINEAR` formula
uses the standard `0.04045`, `12.92`, `0.055`, and `2.4` piecewise transfer used
by the correction.

V2 is retained as historical diagnostic evidence. Its source hashes identify
the pre-correction shader and fixture; it is not a claim about the final source.

## Validated v3 correction

`spell_energy.gdshader` now leaves Compatibility on the original `COLOR.rgb`
path and decodes the sRGB-authored vertex RGB only when `OUTPUT_IS_SRGB` is
false. Alpha, softness, intensity, mesh geometry, effect timing, and all effect
counts are unchanged.

V3 replaces the saturated single control with three matched, unsaturated pairs:

| Probe | Source RGBA | Compatibility max RGB difference | Forward+ max RGB difference |
| --- | --- | ---: | ---: |
| Threshold | `(0.02, 0.04045, 0.08, 0.70)` | `0.000000` | `0.001801` |
| Cyan | `#6bcddb`, alpha `0.34` | `0.003922` | `0.000000` |
| Orange | `#ed7544`, alpha `0.34` | `0.003922` | `0.003922` |

Every probe passed the fixture's `3/255` maximum-channel tolerance in both
renderers. Forward+'s corrected cyan and orange shader results are far from the
historical raw-color-as-linear predictions (RMSE `0.073379` and `0.075237`).
The correction therefore removes the shader-specific conversion error while
preserving Compatibility behavior.

The final controlled ground is close between renderers: encoded luma
`0.319561` versus `0.320020`, with pixel RMSE `0.003881`. The brighter ground
seen in earlier full crowd captures did not reproduce with this controlled
`StandardMaterial3D` ground and fixed lighting. It should not be attributed to
a renderer-global color shift from this evidence.

The complete fire-flight ROI still differs across renderers (encoded luma
`0.476018` versus `0.437544`, pixel RMSE `0.086422`). The corrected Forward+
fire is warmer and less white. Matched `StandardMaterial3D` additive controls
also encode and blend differently across Compatibility and Forward+, so the
remaining complete-effect difference is not evidence of the corrected shader
still mishandling its vertex input. Geometry, alpha, and timing remain intact.
The complete radiation ROI is much closer in mean encoded luma (`0.376173`
versus `0.375546`), with pixel RMSE `0.020596`.

Root independently inspected both the v2 diagnostic images and the v3 final
images. The final captures are retained here:

- [Compatibility final capture](benchmarks/crowd-forward-plus-readiness-compatibility-2026-09-19.png)
- [Forward+ final capture](benchmarks/crowd-forward-plus-readiness-forward-plus-2026-09-19.png)

The compact [evidence manifest](benchmarks/crowd-forward-plus-readiness-2026-09-19.json)
contains source, executable, process, raw report, metadata, and PNG hashes.

## Replay

The retained stage starts at commit
`0bf6c96bc09aba578b2bd54877a8940c2964f4a6`. Run serially from
`godot-client` while holding the shared four-core slot:

```powershell
(Get-Process -Id $PID).ProcessorAffinity = 15
$env:ELORIA_NATIVE_PRESENTATION = '0'
.\scripts\run_presentation_checks.ps1 `
  -GodotPath '.\Godot_v4.7.2-stable_win64_console.exe' `
  -Scripts 'res://tests/integration/rendered_renderer_parity.gd' `
  -Renderer gl_compatibility -Label renderer-parity-v3-native-off `
  -TimeoutMinutes 10

(Get-Process -Id $PID).ProcessorAffinity = 15
$env:ELORIA_NATIVE_PRESENTATION = '0'
.\scripts\run_presentation_checks.ps1 `
  -GodotPath '.\Godot_v4.7.2-stable_win64_console.exe' `
  -Scripts 'res://tests/integration/rendered_renderer_parity.gd' `
  -Renderer forward_plus -Label renderer-parity-v3-native-off `
  -TimeoutMinutes 10
```

Pass the two emitted script artifact directories to the lightweight analyzer:

```powershell
(Get-Process -Id $PID).ProcessorAffinity = 15
python scripts/compare_renderer_parity.py `
  --compatibility <compatibility-script-artifact-directory> `
  --forward-plus <forward-plus-script-artifact-directory> `
  --output test-artifacts/presentation-checks/renderer-parity-v3-comparison
```

Both final renderer processes passed identity and affinity attestation, exited
zero, and contained no script or shader errors. The updated headless
`tests/test_crowd_benchmark.gd` contract also passed after these captures. The
result supports retaining the bounded shader correction and continuing a
separate Forward+ adoption review; it is not an FPS result or a general
renderer-parity certification.
