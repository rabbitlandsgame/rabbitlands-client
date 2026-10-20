shader_type spatial;
render_mode cull_disabled;

#include "creature_dissolve.gdshaderinc"

uniform vec4 base_color : source_color = vec4(1.0);
uniform sampler2D base_texture : source_color, hint_default_white, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap_anisotropic;
uniform sampler2D emission_texture : source_color, hint_default_white, filter_linear_mipmap_anisotropic;
uniform vec3 emission_color : source_color = vec3(0.0);
uniform vec3 uv_scale = vec3(1.0);
uniform vec3 uv_offset = vec3(0.0);
uniform float surface_roughness = 0.9;
uniform float surface_metallic = 0.0;
uniform float surface_specular = 0.3;
uniform float normal_strength = 1.0;
uniform bool use_normal = false;
uniform bool use_vertex_color = false;
uniform float alpha_cutoff = 0.0;

void fragment() {
	vec2 uv = UV * uv_scale.xy + uv_offset.xy;
	vec4 base = texture(base_texture, uv) * base_color;
	if (use_vertex_color) { base *= COLOR; }
	if (base.a < alpha_cutoff) { discard; }
	ALBEDO = base.rgb;
	ROUGHNESS = surface_roughness;
	METALLIC = surface_metallic;
	SPECULAR = surface_specular;
	if (use_normal) {
		NORMAL_MAP = texture(normal_texture, uv).rgb;
		NORMAL_MAP_DEPTH = normal_strength;
	}
	EMISSION = texture(emission_texture, uv).rgb * emission_color * (1.0 - dissolve_progress);
	dissolve_body((INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz, ALBEDO);
}
