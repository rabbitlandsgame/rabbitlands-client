shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform sampler2D base_texture : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 base_color : source_color = vec4(1.0);
uniform vec4 skin_tint : source_color = vec4(1.0);
uniform vec4 eye_tint : source_color = vec4(0.35, 0.25, 0.15, 1.0);
uniform bool is_eye = false;
uniform float iris_recolor_strength = 0.78;
uniform bool use_iris_uv_mask = false;
uniform vec4 iris_uv_centers = vec4(0.29109, 0.70878, 0.70675, 0.29674);
uniform bool head_masks_enabled = false;
uniform bool stubble_enabled = false;
uniform vec4 groom_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
uniform vec4 groom_reference_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
uniform vec4 lip_uv_bounds = vec4(0.0);

float pigment_grain(vec2 cell) {
	return fract(sin(dot(cell, vec2(127.1, 311.7))) * 43758.5453);
}

void fragment() {
	vec4 sampled = texture(base_texture, UV);
	if (is_eye && sampled.a < 0.5) { discard; }
	vec3 paint = sampled.rgb * base_color.rgb;
	if (is_eye) {
		float lightness = dot(paint, vec3(0.2126, 0.7152, 0.0722));
		float chroma = max(paint.r, max(paint.g, paint.b)) - min(paint.r, min(paint.g, paint.b));
		// Recolor the iris pigment while retaining the white, pupil and limbus.
		float pigment = smoothstep(0.04, 0.14, chroma) * smoothstep(0.012, 0.06, lightness);
		if (use_iris_uv_mask) {
			// Stock MPFB eyes occupy two diagonal UV patches. Identity sculpts
			// retain these UVs. Spatial coverage recolors even dark/low-chroma
			// irises while preserving the pupil, outer limbus and sclera.
			float radius = min(distance(UV, iris_uv_centers.xy), distance(UV, iris_uv_centers.zw));
			pigment = smoothstep(0.032, 0.047, radius) * (1.0 - smoothstep(0.105, 0.121, radius));
			pigment *= smoothstep(0.0008, 0.004, lightness);
		}
		// Retain contrast between the source iris crypts and radial fibers.
		vec3 iris = eye_tint.rgb * clamp(3.8 * lightness, 0.04, 1.5);
		if (use_iris_uv_mask) {
			// Normalize the selected color's linear luminance so warm brown
			// and olive retain readable fibers as their source hue is replaced.
			float tint_lightness = max(dot(eye_tint.rgb, vec3(0.2126, 0.7152, 0.0722)), 0.015);
			iris = eye_tint.rgb * clamp(1.6 * lightness / tint_lightness, 0.08, 1.7);
		}
		ALBEDO = mix(paint, iris, pigment * iris_recolor_strength);
		ROUGHNESS = 0.20;
		SPECULAR = 0.48;
		CLEARCOAT = 0.35;
		CLEARCOAT_ROUGHNESS = 0.08;
	} else {
		vec3 skin = paint * skin_tint.rgb;
		float lips = 0.0;
		if (head_masks_enabled) {
			// The existing skin PNG's alpha carries disjoint semantic coverage;
			// its RGB, UVs and opaque rendering remain unchanged.
			float neutral = 128.0 / 255.0;
			float brow = clamp((neutral - sampled.a) / neutral, 0.0, 1.0);
			float beard = clamp((sampled.a - neutral) / (1.0 - neutral), 0.0, 1.0);
			// Lips share signed coverage with brows in a separately authored UV
			// region. RGB pigment stays untouched and no extra map is sampled.
			if (lip_uv_bounds.z > lip_uv_bounds.x && lip_uv_bounds.w > lip_uv_bounds.y) {
				float mouth_region = step(lip_uv_bounds.x, UV.x) * step(UV.x, lip_uv_bounds.z)
					* step(lip_uv_bounds.y, UV.y) * step(UV.y, lip_uv_bounds.w);
				lips = brow * mouth_region;
				brow *= 1.0 - mouth_region;
			}
			vec3 ratio = sqrt(clamp(groom_color.rgb / max(groom_reference_color.rgb, vec3(0.001)), vec3(0.08), vec3(7.8)));
			skin = mix(skin, skin * ratio, brow * 0.75);
			// Keep the painted strands while anchoring weak stock brow pigment
			// to the selected hair palette. The anatomical mask excludes bridge
			// and lips; bounded coverage avoids a solid painted stripe.
			skin = mix(skin, groom_color.rgb * 0.65, brow * 0.25);
			if (stubble_enabled) {
				// Rest UV coordinates keep the pigment attached during movement.
				// Average tiny fibers before they become shimmering distant pixels.
				vec2 cells = UV * 4096.0;
				float resolved = 1.0 - smoothstep(0.3, 1.5, length(fwidth(cells)));
				float grain = mix(0.5, smoothstep(0.32, 0.84, pigment_grain(floor(cells))), resolved);
				skin = mix(skin, groom_color.rgb * 0.34, beard * (0.14 + 0.17 * grain));
			}
		}
		ALBEDO = skin;
		ROUGHNESS = mix(0.66, 0.42, lips);
		SPECULAR = mix(0.28, 0.34, lips);
	}
}
