shader_type spatial;
render_mode unshaded, blend_mix, cull_disabled, depth_draw_never;

uniform bool radial = false;
uniform bool soft_edges = true;
uniform float intensity = 1.0;
uniform vec4 tint : source_color = vec4(1.0);

// A saturated body supplies contrast on snow; the separate additive pass
// retains the familiar light on darker terrain. This is review option A.
void fragment() {
	float radius = radial ? length(UV * 2.0 - 1.0) * 1.65 : abs(UV.y * 2.0 - 1.0);
	float coverage = soft_edges ? pow(max(0.0, 1.0 - radius), 0.70) : 1.0;
	vec3 pale = mix(tint.rgb, vec3(1.0), 0.82);
	float core = soft_edges ? (1.0 - smoothstep(0.0, 0.20, radius)) * 0.35 : 0.0;
	ALBEDO = mix(tint.rgb, pale, core);
	ALPHA = min(1.0, coverage * COLOR.a * 0.95 * intensity);
}
