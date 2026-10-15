shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled;

uniform sampler2D albedo_map : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_map : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D orm_map : filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool use_albedo_map = false;
uniform bool use_normal_map = false;
uniform bool use_orm_map = false;
uniform vec4 albedo_tint : source_color = vec4(1.0);
uniform float roughness_value : hint_range(0.0, 1.0) = 1.0;
uniform float metallic_value : hint_range(0.0, 1.0) = 0.0;
uniform float normal_strength : hint_range(0.0, 2.0) = 1.0;
uniform vec3 uv_scale = vec3(1.0);
uniform vec3 uv_offset = vec3(0.0);
uniform bool use_triplanar = false;
uniform bool use_world_triplanar = false;
uniform float triplanar_sharpness = 1.0;
uniform float texture_rotation_radians = 0.0;

varying vec3 triplanar_position;
varying vec3 triplanar_weight;

vec2 rotate_texture_vector(vec2 value, float angle) {
	float sine = sin(angle);
	float cosine = cos(angle);
	return vec2(cosine * value.x - sine * value.y,
		sine * value.x + cosine * value.y);
}

vec2 oriented_uv(vec2 value) {
	return rotate_texture_vector(value, texture_rotation_radians);
}

// This projection order and X-axis flip intentionally match the shader that
// Godot generates for BaseMaterial3D triplanar textures. At a near-zero angle
// the only visual delta is the requested rotation.
vec4 sample_triplanar(sampler2D source) {
	vec4 sample_value = vec4(0.0);
	sample_value += texture(source, oriented_uv(triplanar_position.xy)) *
		triplanar_weight.z;
	sample_value += texture(source, oriented_uv(triplanar_position.xz)) *
		triplanar_weight.y;
	sample_value += texture(source, oriented_uv(
		triplanar_position.zy * vec2(-1.0, 1.0))) * triplanar_weight.x;
	return sample_value;
}

vec3 rotate_encoded_normal(vec3 encoded) {
	vec2 tangent_normal = encoded.xy * 2.0 - 1.0;
	tangent_normal = rotate_texture_vector(tangent_normal,
		-texture_rotation_radians);
	return vec3(tangent_normal * 0.5 + 0.5, encoded.z);
}

void vertex() {
	if (use_triplanar) {
		vec3 projection_normal = NORMAL;
		vec3 position = VERTEX;
		if (use_world_triplanar) {
			projection_normal = MODEL_NORMAL_MATRIX * NORMAL;
			position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
		}
		TANGENT = vec3(0.0, 0.0, -1.0) * abs(projection_normal.x);
		TANGENT += vec3(1.0, 0.0, 0.0) * abs(projection_normal.y);
		TANGENT += vec3(1.0, 0.0, 0.0) * abs(projection_normal.z);
		BINORMAL = vec3(0.0, 1.0, 0.0) * abs(projection_normal.x);
		BINORMAL += vec3(0.0, 0.0, -1.0) * abs(projection_normal.y);
		BINORMAL += vec3(0.0, 1.0, 0.0) * abs(projection_normal.z);
		if (use_world_triplanar) {
			TANGENT = inverse(MODEL_NORMAL_MATRIX) * normalize(TANGENT);
			BINORMAL = inverse(MODEL_NORMAL_MATRIX) * normalize(BINORMAL);
		} else {
			TANGENT = normalize(TANGENT);
			BINORMAL = normalize(BINORMAL);
		}
		triplanar_weight = pow(abs(projection_normal),
			vec3(max(triplanar_sharpness, 0.001)));
		triplanar_weight /= max(dot(triplanar_weight, vec3(1.0)), 0.00001);
		triplanar_position = (position * uv_scale + uv_offset) *
			vec3(1.0, -1.0, 1.0);
	} else {
		UV = UV * uv_scale.xy + uv_offset.xy;
	}
}

void fragment() {
	vec4 sampled_albedo = vec4(1.0);
	vec3 sampled_orm = vec3(1.0, roughness_value, metallic_value);
	if (use_triplanar) {
		if (use_albedo_map) {
			sampled_albedo = sample_triplanar(albedo_map);
		}
		if (use_orm_map) {
			sampled_orm = sample_triplanar(orm_map).rgb;
		}
		if (use_normal_map) {
			NORMAL_MAP = rotate_encoded_normal(sample_triplanar(normal_map).rgb);
			NORMAL_MAP_DEPTH = normal_strength;
		}
	} else {
		vec2 texture_uv = oriented_uv(UV);
		if (use_albedo_map) {
			sampled_albedo = texture(albedo_map, texture_uv);
		}
		if (use_orm_map) {
			sampled_orm = texture(orm_map, texture_uv).rgb;
		}
		if (use_normal_map) {
			NORMAL_MAP = rotate_encoded_normal(texture(normal_map, texture_uv).rgb);
			NORMAL_MAP_DEPTH = normal_strength;
		}
	}
	ALBEDO = sampled_albedo.rgb * albedo_tint.rgb;
	// ORMMaterial3D reads roughness and metallic directly from the packed map;
	// its scalar properties are not multipliers in Godot's generated shader.
	ROUGHNESS = use_orm_map ? sampled_orm.g : roughness_value;
	METALLIC = use_orm_map ? sampled_orm.b : metallic_value;
	AO = use_orm_map ? sampled_orm.r : 1.0;
}
