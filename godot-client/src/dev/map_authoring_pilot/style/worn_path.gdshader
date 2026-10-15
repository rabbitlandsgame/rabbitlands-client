shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled;

uniform sampler2D ground_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D ground_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D ground_orm : filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 worn_tint : source_color = vec4(0.62, 0.50, 0.34, 1.0);
uniform float texture_scale : hint_range(0.1, 16.0, 0.05) = 1.0;
uniform float roughness_multiplier : hint_range(0.0, 2.0, 0.05) = 1.0;
uniform float normal_strength : hint_range(0.0, 2.0, 0.05) = 0.72;
uniform float edge_feather : hint_range(0.01, 0.5, 0.01) = 0.16;
uniform float texture_rotation_radians = 0.0;

vec2 rotate_texture_vector(vec2 value, float angle) {
	float sine = sin(angle);
	float cosine = cos(angle);
	return vec2(cosine * value.x - sine * value.y,
		sine * value.x + cosine * value.y);
}

void fragment() {
	vec2 texture_uv = rotate_texture_vector(UV * texture_scale,
		texture_rotation_radians);
	vec4 base = texture(ground_albedo, texture_uv);
	vec3 packed_orm = texture(ground_orm, texture_uv).rgb;
	ALBEDO = base.rgb * worn_tint.rgb;
	vec3 sampled_normal = texture(ground_normal, texture_uv).rgb;
	// Rotating the lookup rotates the texture axes. Bring the decoded tangent
	// normal back through the inverse rotation so bumps turn with the pattern.
	// Keep the zero-angle path as the original exact sampled value.
	if (abs(texture_rotation_radians) > 0.000001) {
		vec2 tangent_normal = sampled_normal.xy * 2.0 - 1.0;
		tangent_normal = rotate_texture_vector(tangent_normal,
			-texture_rotation_radians);
		sampled_normal.xy = tangent_normal * 0.5 + 0.5;
	}
	NORMAL_MAP = sampled_normal;
	NORMAL_MAP_DEPTH = normal_strength;
	AO = packed_orm.r;
	ROUGHNESS = clamp(packed_orm.g * roughness_multiplier, 0.0, 1.0);
	METALLIC = packed_orm.b;
	float distance_from_edge = 1.0 - abs(UV2.x * 2.0 - 1.0);
	ALPHA = smoothstep(0.0, edge_feather, distance_from_edge);
}
