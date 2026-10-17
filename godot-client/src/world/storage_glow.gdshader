shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;

uniform vec4 glow_colour : source_color = vec4(0.839, 0.733, 0.478, 1.0);
uniform float phase = 0.0;

void fragment() {
	vec2 point = UV * 2.0 - 1.0;
	float radius = length(point);
	float halo = smoothstep(0.42, 0.64, radius) * (1.0 - smoothstep(0.74, 1.0, radius));
	float pulse = 0.25 + 0.08 * sin(TIME * 1.8 + phase);
	float sweep = pow(0.5 + 0.5 * cos(atan(point.y, point.x) - TIME * 0.65 + phase), 8.0);
	ALBEDO = glow_colour.rgb;
	ALPHA = glow_colour.a * halo * (pulse + 0.12 * sweep);
}
