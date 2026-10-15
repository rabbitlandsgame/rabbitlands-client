shader_type spatial;

// Draws the actor's shape over whatever is hiding it.
//
// No depth test, so it reaches the screen through trees, roofs and cliffs; the
// stencil is what keeps it honest. The marker pass stamped 1 wherever the actor
// is really visible, so comparing "not equal to 1" leaves those fragments to the
// actor itself and paints only the parts something covered. Half a body behind a
// trunk therefore renders half shaded and half tinted, which no camera-to-actor
// raycast can do - a raycast is one answer for the whole actor.
//
// Reads the stencil rather than DEPTH_TEXTURE because this project renders with
// GL Compatibility, where the depth texture is not available: sampling it there
// returns zero everywhere and the silhouette floods the screen. Stencil is
// exact on both Compatibility and Forward+.
render_mode unshaded, depth_test_disabled, depth_draw_never, blend_mix,
	shadows_disabled, cull_back;
stencil_mode read, compare_not_equal, 1;

uniform vec4 tint : source_color = vec4(0.42, 0.72, 1.0, 0.62);
// Rim brightening, so the outline of the shape reads against a busy canopy
// instead of dissolving into it.
uniform float rim_strength : hint_range(0.0, 2.0) = 0.85;

void fragment() {
	float facing = abs(dot(normalize(NORMAL), normalize(-VERTEX)));
	float rim = pow(1.0 - facing, 2.0) * rim_strength;
	ALBEDO = tint.rgb + vec3(rim);
	ALPHA = clamp(tint.a + rim * 0.5, 0.0, 1.0);
}
