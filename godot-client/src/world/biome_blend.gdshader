shader_type spatial;
render_mode depth_draw_opaque, cull_disabled;

uniform sampler2D base_mask : filter_linear, repeat_disable;
uniform sampler2D secondary_mask : filter_linear, repeat_disable;
uniform sampler2D base_albedo_0 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D base_albedo_1 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D base_albedo_2 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D base_albedo_3 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D secondary_albedo_0 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D secondary_albedo_1 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D secondary_albedo_2 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D secondary_albedo_3 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;

uniform mat4 terrain_to_continent = mat4(1.0);
uniform vec2 mask_origin = vec2(0.0);
uniform float mask_metres_per_pixel = 1.5;
uniform float mask_size = 66.0;
uniform vec4 base_tint_0 : source_color = vec4(1.0);
uniform vec4 base_tint_1 : source_color = vec4(1.0);
uniform vec4 base_tint_2 : source_color = vec4(1.0);
uniform vec4 base_tint_3 : source_color = vec4(1.0);
uniform vec4 secondary_tint_0 : source_color = vec4(1.0);
uniform vec4 secondary_tint_1 : source_color = vec4(1.0);
uniform vec4 secondary_tint_2 : source_color = vec4(1.0);
uniform vec4 secondary_tint_3 : source_color = vec4(1.0);
uniform vec4 base_uv_metres_inverse = vec4(1.0);
uniform vec4 base_uv_scale_x = vec4(1.0);
uniform vec4 base_uv_scale_y = vec4(1.0);
uniform vec4 base_uv_offset_x = vec4(0.0);
uniform vec4 base_uv_offset_y = vec4(0.0);
uniform vec4 base_rotation_radians = vec4(0.0);
uniform vec4 secondary_uv_metres_inverse = vec4(1.0);
uniform vec4 secondary_uv_scale_x = vec4(1.0);
uniform vec4 secondary_uv_scale_y = vec4(1.0);
uniform vec4 secondary_uv_offset_x = vec4(0.0);
uniform vec4 secondary_uv_offset_y = vec4(0.0);
uniform vec4 secondary_rotation_radians = vec4(0.0);
uniform vec4 base_roughness = vec4(1.0);
uniform vec4 secondary_roughness = vec4(1.0);
uniform vec4 base_metallic = vec4(0.0);
uniform vec4 secondary_metallic = vec4(0.0);

varying vec2 continent_xz;

vec2 rotate_uv(vec2 value, float angle) {
	float sine = sin(angle);
	float cosine = cos(angle);
	return vec2(cosine * value.x - sine * value.y,
		sine * value.x + cosine * value.y);
}

vec2 palette_uv(int index, bool secondary) {
	float metres_inverse = secondary ? secondary_uv_metres_inverse[index] :
		base_uv_metres_inverse[index];
	vec2 scale = secondary ? vec2(secondary_uv_scale_x[index],
		secondary_uv_scale_y[index]) : vec2(base_uv_scale_x[index],
		base_uv_scale_y[index]);
	vec2 offset = secondary ? vec2(secondary_uv_offset_x[index],
		secondary_uv_offset_y[index]) : vec2(base_uv_offset_x[index],
		base_uv_offset_y[index]);
	float angle = secondary ? secondary_rotation_radians[index] :
		base_rotation_radians[index];
	return rotate_uv(continent_xz * metres_inverse * scale + offset, angle);
}

vec4 base_sample(int index) {
	if (index == 0) return texture(base_albedo_0, palette_uv(0, false));
	if (index == 1) return texture(base_albedo_1, palette_uv(1, false));
	if (index == 2) return texture(base_albedo_2, palette_uv(2, false));
	return texture(base_albedo_3, palette_uv(3, false));
}

vec4 secondary_sample(int index) {
	if (index == 0) return texture(secondary_albedo_0, palette_uv(0, true));
	if (index == 1) return texture(secondary_albedo_1, palette_uv(1, true));
	if (index == 2) return texture(secondary_albedo_2, palette_uv(2, true));
	return texture(secondary_albedo_3, palette_uv(3, true));
}

vec3 base_tint_at(int index) {
	if (index == 0) return base_tint_0.rgb;
	if (index == 1) return base_tint_1.rgb;
	if (index == 2) return base_tint_2.rgb;
	return base_tint_3.rgb;
}

vec3 secondary_tint_at(int index) {
	if (index == 0) return secondary_tint_0.rgb;
	if (index == 1) return secondary_tint_1.rgb;
	if (index == 2) return secondary_tint_2.rgb;
	return secondary_tint_3.rgb;
}

void vertex() {
	continent_xz = (terrain_to_continent * vec4(VERTEX, 1.0)).xz;
}

void fragment() {
	vec2 mask_uv = ((continent_xz - mask_origin) / mask_metres_per_pixel +
		vec2(1.0)) / mask_size;
	vec4 region_weights = texture(base_mask, mask_uv);
	vec4 secondary_weights = texture(secondary_mask, mask_uv);
	vec3 color = vec3(0.0);
	float roughness = 0.0;
	float metallic = 0.0;
	float total = 0.0;
	for (int index = 0; index < 4; index++) {
		float weight = max(region_weights[index], 0.0);
		if (weight <= (1.0 / 255.0)) {
			continue;
		}
		float secondary_amount = clamp(secondary_weights[index], 0.0, 1.0);
		vec3 base_color = base_sample(index).rgb * base_tint_at(index);
		vec3 mixed_color = base_color;
		if (secondary_amount > (1.0 / 255.0)) {
			vec3 secondary_color = secondary_sample(index).rgb *
				secondary_tint_at(index);
			mixed_color = mix(base_color, secondary_color, secondary_amount);
		}
		color += mixed_color * weight;
		roughness += mix(base_roughness[index], secondary_roughness[index],
			secondary_amount) * weight;
		metallic += mix(base_metallic[index], secondary_metallic[index],
			secondary_amount) * weight;
		total += weight;
	}
	total = max(total, 0.00001);
	// Terrain COLOR_0 is the old absolute biome albedo, not a neutral detail
	// modulation. The opted palette replaces that legacy colour; multiplying it
	// here would apply the biome tint twice and make peat/forest nearly black.
	ALBEDO = color / total;
	ROUGHNESS = roughness / total;
	METALLIC = metallic / total;
}
