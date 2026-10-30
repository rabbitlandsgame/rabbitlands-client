shader_type spatial;
render_mode cull_disabled;
uniform sampler2D cloth_texture : source_color, filter_linear_mipmap, repeat_enable;
// Replace the hood's olive dye with the set's brown leather. Neutral fur,
// antlers, painted highlights and gold ornament retain their source colors.
void fragment() {
	vec3 paint = texture(cloth_texture, UV).rgb;
	float green = smoothstep(0.92, 1.12, paint.g / max(paint.r, 0.001));
	green *= smoothstep(1.15, 1.55, paint.g / max(paint.b, 0.001));
	float value = dot(paint, vec3(0.2126, 0.7152, 0.0722));
	vec3 leather = vec3(0.34, 0.205, 0.11) * value / 0.227;
	ALBEDO = mix(paint, leather, green);
	ROUGHNESS = 0.83;
}
