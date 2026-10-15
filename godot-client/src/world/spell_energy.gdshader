shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never;

uniform bool radial = false;
uniform float intensity = 1.0;

float srgb_channel_to_linear(float channel) {
	return channel <= 0.04045
		? channel / 12.92
		: pow((channel + 0.055) / 1.055, 2.4);
}

vec3 srgb_to_linear(vec3 color) {
	return vec3(
		srgb_channel_to_linear(color.r),
		srgb_channel_to_linear(color.g),
		srgb_channel_to_linear(color.b));
}

void fragment() {
	float distance_to_edge = radial ? length(UV * 2.0 - 1.0) : abs(UV.y * 2.0 - 1.0);
	float softness = pow(max(0.0, 1.0 - distance_to_edge), radial ? 2.6 : 1.8);
	// COLOR is mesh vertex data, so unlike a `source_color` uniform or texture
	// it has no hint that asks the RenderingDevice path to decode sRGB-authored
	// palette values. Compatibility outputs sRGB and already matched the authored
	// values. Forward+/Mobile output linear light, so decode RGB there only.
	ALBEDO = OUTPUT_IS_SRGB ? COLOR.rgb : srgb_to_linear(COLOR.rgb);
	ALPHA = min(1.0, COLOR.a * softness * intensity);
}
