// Look pass layer L3: the surface a StandardMaterial3D gives a mesh, for the
// look shaders that stand in for one (painted_foliage_body and
// look_faded_standard). LookFade.copy_standard_surface fills these uniforms
// from the source material, and the helpers below are the formulas the engine
// generates for the same properties, so the stand-in lights as its source
// did. The continent's Meshy exports take their roughness from a texture's
// green channel (about 0.6) under a roughness of 1: read as 1, a dark fir lost
// the sky's specular and a third of its brightness.

uniform vec4 albedo_color : source_color = vec4(1.0);
uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_normal_texture = false;
uniform float normal_scale = 1.0;
uniform float roughness_value : hint_range(0.0, 1.0) = 1.0;
uniform sampler2D roughness_texture : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 roughness_channel = vec4(1.0, 0.0, 0.0, 0.0);
uniform float metallic_value : hint_range(0.0, 1.0) = 0.0;
uniform sampler2D metallic_texture : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 metallic_channel = vec4(1.0, 0.0, 0.0, 0.0);
uniform float specular_value : hint_range(0.0, 1.0) = 0.5;
uniform bool has_ao = false;
uniform sampler2D ao_texture : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 ao_channel = vec4(1.0, 0.0, 0.0, 0.0);
uniform float ao_light_affect = 0.0;
uniform bool has_emission = false;
uniform vec4 emission_color : source_color = vec4(0.0, 0.0, 0.0, 1.0);
uniform sampler2D emission_texture : source_color, hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float emission_energy = 1.0;
// 0 adds the emission texture to the colour, 1 multiplies.
uniform int emission_operator = 0;
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);

// Roughness, metallic, specular and ambient occlusion at `uv`.
vec4 look_standard_surface(vec2 uv) {
	return vec4(dot(texture(roughness_texture, uv), roughness_channel) * roughness_value,
		dot(texture(metallic_texture, uv), metallic_channel) * metallic_value,
		specular_value,
		has_ao ? dot(texture(ao_texture, uv), ao_channel) : 1.0);
}

vec3 look_standard_emission(vec2 uv) {
	vec3 emission = texture(emission_texture, uv).rgb;
	return (emission_operator == 0 ? emission_color.rgb + emission
		: emission_color.rgb * emission) * emission_energy;
}
