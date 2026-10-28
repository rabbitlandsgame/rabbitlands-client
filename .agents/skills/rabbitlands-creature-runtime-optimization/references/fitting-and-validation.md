# Offline fitting and validation notes

## What can be baked

For rest vertex `x`, joint bind/pose matrices `M_j(t)`, weights `w_j` and pre-skin morph displacement `d(t)`, the target surface is:

`y(t) = sum_j w_j M_j(t) [x + d(t), 1]`.

One fixed bake replaces `x + d(t)` with a single fitted `x'`. It reproduces all poses only if the corrected target lies in the fixed skin's trajectory family. It cannot generally reproduce pose-dependent contact, volume or normal corrections. Solve the constant rest displacement by least squares across representative poses; evaluate held-out poses rather than baking whichever frame looks best.

For a mesh/weight fit, alternate constrained per-vertex weight solves and rest-position solves. Weight constraints are nonnegative, sum to one and limited to supported influences and anatomically plausible local joints. Start from the original geometry plus a good weight-only solution; starting from a large static displacement can settle into a poor local solution. Keep mirrored anatomy coherent, record changed support and verify all coincident seams. A robust p-norm or iteratively reweighted objective can reduce extreme errors; report the corresponding average-error tradeoff and rest-pose deviation.

With fixed weights, a fixed normal can be fit by minimizing projected angular residuals through the blended skin matrices. Validate actual unit output directions. Neither fitted normals nor source normal maps guarantee unchanged tangent-space shading after rest positions or weights change. Inspect actual Forward+ renders, including feet, folds, thin triangles and inside/outside transitions.

## Residual representation

Given a new blended affine skin matrix `[C'(t), b'(t)]`, a residual position field is `inverse(C'(t)) * (y(t) - b'(t)) - x'`. Check conditioning; singular fits require another rig/weight choice. Reconstruct at the actual delivery knots and validate between knots and during blends: the inverse skin operation is nonlinear, so matching knots alone does not imply matching transitions.

Position bases may be arbitrary vectors. **Godot normalizes normal morph endpoints.** Arbitrary PCA normal vectors lose their intended magnitude on import. Use valid unit-normal endpoint poses, preserve a suitable original normal basis, or explicitly prove another representation through the real loader. Normalizing every reconstructed key pose can itself change interpolation near cancellation, even when key-pose directions match.

RenderingServer may ignore morph weights with `abs(weight) < 0.0001`; include that behavior in native error estimates. Account for native u16 weight quantization and packed normals. Use actual joint-palette indices, bind matrices and engine world bone transforms; node indices, skeleton bone indices and skin bind indices are not interchangeable.

A reduced basis can shrink a 30 Hz cache without changing the skin. Run this as a control: structural reweighting may improve the uncorrected surface yet give no additional storage saving once residual corrections are retained. Do not force a skin edit when the unchanged-skin control is better.

## Accepted tortoise precedent

`docs/qa/creature-storage/crystalback-tortoise-corrective-repair.json` binds the exact candidates and acceptance. The corrected 30 Hz reference had 577 basis shapes (221 position, 356 normal), occupying 23.08 MB of its 25.69 MB raw file. Coincident vertices already shared weights; seam welding was not the solution.

The original-weight fixed bake left about 98 mm maximum deviation. Joint least-squares mesh/weight fitting improved that to about 39 mm. Robust fitting produced the visually accepted zero-shape V2 (`53ae0f505843d9835224452ee860a662b2ed0ecbcad659654af966ca28412938`): 1,558,840 raw bytes, 21 bones and four influences. Across the same 4,827 current-client states, body RMS improved from 11.45 to 1.56 mm and maximum error from 97.78 to 33.51 mm. Shading still differed. The user accepted this **specific** compromise and explicitly requested installation and raw creature delivery. Those error values are not general automatic promotion thresholds.

The separate unchanged-skin 328-shape control was closer (roughly 0.103 mm sampled maximum) but larger (15.27 MB raw). This illustrates the visual-quality/storage tradeoff and why a small residual cache or extra joint controls may suit a different actor better.

## Practical validation

- Separate original-to-30-Hz error from 30-Hz-to-bake error. Keep the complete clip set, including retained special clips.
- Sample independent shifted times, full cycles, short and long crossfades at several source phases, default/reset, action interruption and held ends. Report maximum errors by clip and anatomical region in rendered units and normalized by actor height.
- Compare old/new candidates at the same native bone states when only rest geometry/weights differ; this avoids conflating different probe grids. Check original bone matrices remain equal before reusing them.
- A source GLB SHA or `.import` file alone does not prove current editor imports. Genuine editor QA should bind the generated `.scn`, source/destination freshness metadata and actual ResourceLoader route. Raw production loading is a distinct valid test route.
- Keep source landmarks, authoring fits, physical observations, visual acceptance and installed selection as separate records. Reissue candidate witnesses for the final hash without rewriting the original observations to erase differences.
- Corrective buffer bytes are shared mesh data. First-actor CPU allocations include scene/library caches; neither number is automatically per creature instance or total VRAM. Record added surfaces/helper joints and preserve effects, mounts, attachments and grounding behavior.
