shader_type spatial;

// Stamps the stencil buffer wherever the actor is genuinely visible, and draws
// nothing at all. It is depth-tested like any transparent surface, so a
// fragment the world has already covered never reaches here and never stamps.
//
// Applied as `material_overlay` on the actor's own mesh instances, so it does
// not disturb the imported materials, the appearance tints, or the equipment
// system - all of which own `material_override`.
render_mode unshaded, depth_draw_never, blend_mix, shadows_disabled;
stencil_mode write, compare_always, 1;

void fragment() {
	ALBEDO = vec3(0.0);
	ALPHA = 0.0;
}
