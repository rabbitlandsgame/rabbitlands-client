shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

#include "res://src/actors/stubble_pigment.gdshaderinc"

uniform sampler2D base_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D region_texture : filter_linear_mipmap, repeat_enable;
uniform vec2 mask_uv_scale = vec2(1.0);
uniform vec2 mask_uv_offset = vec2(0.0);
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool use_normal = false;
uniform float normal_scale = 1.0;
uniform vec4 base_color : source_color = vec4(1.0);
uniform vec4 skin_tint : source_color = vec4(1.0);
uniform vec4 skin_reference : source_color = vec4(1.0);
uniform vec4 skin_color : source_color = vec4(1.0);
uniform bool recolor_skin = false;
uniform bool use_regions = true;
uniform vec4 eye_tint : source_color = vec4(1.0);
uniform vec4 hair_tint : source_color = vec4(1.0);
uniform float roughness = 0.85;
uniform sampler2D portrait_paint : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D portrait_regions : filter_linear_mipmap, repeat_disable;
uniform sampler2D portrait_normal : hint_normal, filter_linear_mipmap, repeat_disable;
// The High geometry now owns broad planes; this map carries only pore/paint
// microrelief instead of reapplying the coarse source's geometric residual.
uniform float portrait_normal_strength = 0.30;
// Only the retained eye patch receives the corneal response. Skin/lid paint
// around it keeps the ordinary head roughness and microrelief strength.
uniform bool portrait_eye_surface = false;
uniform vec4 portrait_eye_centers = vec4(-0.035, 0.079, 0.032, 0.079);
uniform vec2 portrait_iris_radii = vec2(0.007, 0.007);
uniform vec4 portrait_bounds = vec4(-0.105, 0.105, -0.075, 0.205);

void fragment() {
	vec2 atlas_uv = UV * mask_uv_scale + mask_uv_offset;
	vec3 original = texture(base_texture, UV).rgb * base_color.rgb;
	vec3 mask = use_regions ? texture(region_texture, atlas_uv).rgb : vec3(0.0);
	vec4 paint = texture(portrait_paint, UV2);
	vec4 detail = texture(portrait_regions, UV2);
	float coverage = COLOR.r * paint.a;
	original = mix(original, paint.rgb * base_color.rgb, coverage);
	mask = mix(mask, detail.rgb, coverage);
	vec3 skin = original * skin_tint.rgb;
	// The authored lip roughness band doubles as a compact pigment selector;
	// eyes/brows are excluded, and the nose stays above this range. This keeps
	// warm vermilion detail through skin selection without another texture.
	float lip_pigment = coverage * (1.0 - mask.r) * (1.0 - mask.b) *
		(1.0 - smoothstep(0.59, 0.71, detail.a));
	if (recolor_skin) {
		vec3 pigment = original / max(skin_reference.rgb, vec3(0.005));
		float value = dot(original, vec3(0.2126, 0.7152, 0.0722)) /
			max(dot(skin_reference.rgb, vec3(0.2126, 0.7152, 0.0722)), 0.005);
		// Retain the authored local warm/cool paint while the selected skin
		// colour continues to own the broad pigment of the head and body.
		skin = skin_color.rgb * mix(vec3(value), pigment, mix(mix(0.20, 0.50, coverage), 0.85, lip_pigment));
	}
	skin = apply_stubble(skin, atlas_uv);
	float peak = max(original.r, max(original.g, original.b));
	float eye_value = dot(eye_tint.rgb, vec3(0.2126, 0.7152, 0.0722));
	vec3 natural_eye = mix(eye_tint.rgb, vec3(eye_value), 0.16);
	if (portrait_eye_surface && mask.g > 0.001 && coverage > 0.001) {
		// Canonical atlas coordinates follow the selected face and animation.
		// Warm crypts around the pupil vary the selected hue locally, instead
		// of multiplying the entire iris into one uniform green/blue disc.
		vec2 head_xy = vec2(mix(portrait_bounds.x, portrait_bounds.y, UV2.x), mix(portrait_bounds.w, portrait_bounds.z, UV2.y));
		vec2 center = head_xy.x < 0.0 ? portrait_eye_centers.xy : portrait_eye_centers.zw;
		float radius = head_xy.x < 0.0 ? portrait_iris_radii.x : portrait_iris_radii.y;
		float radial = length(head_xy - center) / max(radius, 0.001);
		float collarette = exp(-pow((radial - 0.48) / 0.16, 2.0));
		vec3 warm_crypt = vec3(0.26, 0.16, 0.055) * clamp(eye_value / 0.17, 0.45, 1.4);
		natural_eye = mix(natural_eye, warm_crypt, collarette * 0.28);
	}
	// Source iris pixels are already shaded. Restore their readable value
	// after hue selection rather than multiplying two dark pigments together.
	vec3 iris = natural_eye * min(peak * 2.85, 0.88);
	float highlight = smoothstep(0.38, 0.72, min(original.r, min(original.g, original.b)));
	vec3 eye = mix(original, mix(iris, original, highlight), mask.g);
	ALBEDO = mix(skin, eye, mask.r);
	float brow_value = clamp(peak * 3.5 + 0.15, 0.28, 0.90);
	// The imported brow primitive also contains light skin between hairs.
	// Dye only its dark pigment, preserving those feathered skin gaps instead
	// of turning the whole primitive into a uniformly coloured wedge.
	float brow_pigment = mask.b * (1.0 - smoothstep(0.08, 0.32, peak));
	ALBEDO = mix(ALBEDO, vec3(brow_value) * hair_tint.rgb, brow_pigment);
	ROUGHNESS = mix(roughness, detail.a, coverage);
	float cornea = portrait_eye_surface ? coverage * mask.r : 0.0;
	SPECULAR = mix(0.50, mix(mix(0.24, 0.32, lip_pigment), 0.48, cornea), coverage);
	CLEARCOAT = cornea * 0.12;
	CLEARCOAT_ROUGHNESS = 0.10;
	// UV2 was baked once into this High-only mesh from the canonical head.
	// Derivative tangents follow the animated surface, so texture details stay
	// attached through head turns, skeletal animation and facial proportions.
	vec3 dpdx = dFdx(VERTEX);
	vec3 dpdy = dFdy(VERTEX);
	vec2 duvdx = dFdx(UV2);
	vec2 duvdy = dFdy(UV2);
	float determinant = duvdx.x * duvdy.y - duvdx.y * duvdy.x;
	if (coverage > 0.001 && abs(determinant) > 0.00000001) {
		vec3 n = normalize(NORMAL);
		vec3 t = normalize((dpdx * duvdy.y - dpdy * duvdx.y) * sign(determinant));
		t = normalize(t - n * dot(t, n));
		vec3 b = normalize((-dpdx * duvdy.x + dpdy * duvdx.x) * sign(determinant));
		b = normalize(b - n * dot(b, n) - t * dot(b, t));
		vec2 xy = texture(portrait_normal, UV2).rg * 2.0 - 1.0;
		float strength = coverage * mix(portrait_normal_strength, 0.90, cornea);
		xy *= strength;
		vec3 mapped = vec3(xy, sqrt(max(1.0 - dot(xy, xy), 0.01)));
		NORMAL = normalize(t * mapped.x + b * mapped.y + n * mapped.z);
	}
}
