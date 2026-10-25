shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never;
uniform float flow_strength : hint_range(0.0, 1.0) = 0.0;
uniform bool verified = false;
uniform bool reduced_motion = false;

void fragment() {
	float progress = reduced_motion ? 0.0 : TIME * (0.4 + flow_strength);
	float ripple = 0.5 + 0.5 * sin((UV.y - progress) * 44.0);
	vec3 moving_water = verified ? vec3(0.12, 0.65, 0.78) : vec3(0.91, 0.52, 0.16);
	ALBEDO = mix(moving_water, vec3(0.75, 0.92, 0.94), ripple * 0.3);
	ALPHA = flow_strength < 0.01 ? 0.08 : 0.56 + 0.18 * ripple;
}
