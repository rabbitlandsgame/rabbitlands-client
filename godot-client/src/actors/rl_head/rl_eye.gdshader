// RL head eyes, on the MPFB eye layout: two eyeball islands and a cornea
// shell packed into the texture's top-right corner.
//
// The shell is discarded - the pass is opaque - and the eyeball paints the
// cornea's wet gloss itself: a low roughness over the iris and a small
// catchlight. With eye.png the iris (its alpha) takes the actor's eye colour
// through the texture's own neutral detail and the sclera keeps the texture;
// without it, the iris, limbus and pupil are drawn around the iris centres
// RLHeadLibrary measured off the eye mesh. `eye_look` turns both irises by
// a look angle in radians (x towards model +X, y up) through the same fit.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform sampler2D eye_texture : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform bool has_texture = false;
uniform vec2 cornea_uv_min = vec2(0.875, 0.875);
uniform vec2 iris_uv_0 = vec2(0.25, 0.6);
uniform vec2 look_x_0 = vec2(0.1, 0.0);
uniform vec2 look_y_0 = vec2(0.0, 0.1);
uniform float iris_radius_0 = 0.085;
uniform vec2 iris_uv_1 = vec2(0.75, 0.2);
uniform vec2 look_x_1 = vec2(0.1, 0.0);
uniform vec2 look_y_1 = vec2(0.0, 0.1);
uniform float iris_radius_1 = 0.085;
uniform vec3 sclera_color : source_color = vec3(0.9, 0.87, 0.83);
uniform float pupil_ratio : hint_range(0.1, 0.7) = 0.36;
uniform float catchlight : hint_range(0.0, 2.0) = 0.55;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

void fragment() {
	if (UV.x > cornea_uv_min.x && UV.y > cornea_uv_min.y) {
		discard;
	}
	vec2 shift_0 = look_x_0 * eye_look.x + look_y_0 * eye_look.y;
	vec2 shift_1 = look_x_1 * eye_look.x + look_y_1 * eye_look.y;
	vec2 centre_0 = iris_uv_0 + shift_0;
	vec2 centre_1 = iris_uv_1 + shift_1;
	bool first = distance(UV, iris_uv_0) < distance(UV, iris_uv_1);
	vec2 centre = first ? centre_0 : centre_1;
	vec2 shift = first ? shift_0 : shift_1;
	float radius = max(first ? iris_radius_0 : iris_radius_1, 0.0001);
	vec2 up = normalize(first ? look_y_0 : look_y_1);
	vec2 across = normalize(first ? look_x_0 : look_x_1);
	float r = distance(UV, centre) / radius;
	vec3 albedo;
	float iris;
	if (has_texture) {
		// Carry the painted iris with the look; the sclera far from it stays put.
		float carried = 1.0 - smoothstep(1.5, 2.6, r);
		vec4 painted = texture(eye_texture, UV - shift * carried);
		iris = painted.a;
		vec3 tinted = eye_color.rgb * clamp(dot(painted.rgb, LUMA) * 1.8, 0.0, 1.5);
		albedo = mix(painted.rgb, tinted, iris);
	} else {
		vec2 offset = UV - centre;
		float angle = atan(offset.y, offset.x);
		float fibres = 0.82 + 0.18 * sin(angle * 41.0 + r * 7.0) * sin(angle * 17.0 - r * 5.0);
		float limbus = smoothstep(0.72, 1.0, r);
		vec3 iris_rgb = eye_color.rgb * fibres * mix(1.18, 0.5, limbus);
		iris_rgb = mix(iris_rgb, eye_color.rgb * 1.35 + 0.04, (1.0 - smoothstep(pupil_ratio, 0.62, r)) * 0.35);
		iris = 1.0 - smoothstep(0.96, 1.05, r);
		float pupil = 1.0 - smoothstep(pupil_ratio - 0.04, pupil_ratio + 0.03, r);
		// Sclera: a touch of warmth and shade towards the corners of the eye.
		vec3 sclera = sclera_color * mix(1.0, 0.82, smoothstep(1.4, 3.2, r));
		albedo = mix(sclera, iris_rgb, iris);
		albedo = mix(albedo, vec3(0.015), pupil);
	}
	ALBEDO = albedo;
	ROUGHNESS = mix(0.3, 0.06, iris);
	SPECULAR = 0.5;
	vec2 glint = centre + (up * 0.42 - across * 0.32) * radius;
	EMISSION = vec3(catchlight) * (1.0 - smoothstep(0.08, 0.16, distance(UV, glint) / radius));
}
