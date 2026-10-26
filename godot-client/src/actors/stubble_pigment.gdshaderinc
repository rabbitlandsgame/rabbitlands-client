// Filtered, surface-bound pigment. No extra shell, depth competition or cutouts.
uniform sampler2D stubble_mask : filter_linear_mipmap, repeat_disable;
uniform vec4 stubble_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
uniform bool stubble_enabled = false;

vec3 apply_stubble(vec3 skin, vec2 atlas_uv) {
	if (!stubble_enabled) { return skin; }
	float coverage = texture(stubble_mask, atlas_uv).r;
	vec3 pigment = stubble_color.rgb * 0.72 + skin * 0.12;
	return mix(skin, pigment, coverage * 0.40);
}
