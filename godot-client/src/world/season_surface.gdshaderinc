// Shared by scenery's original or painted shader, after its own surface work.
uniform float rl_season = -1.0;
uniform int rl_kind = 0; // ground, deciduous leaves, evergreen, shrub, roof
uniform float rl_snow = 1.0;
uniform float rl_foliage = 1.0;
uniform bool rl_mixed_crown = false;
uniform vec2 rl_height = vec2(0.0, 1.0);
uniform float rl_seed = 0.5;
varying vec3 rl_position;
varying float rl_up;

float rl_noise(vec2 p) {
	vec2 cell = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	vec4 n = fract(sin(vec4(dot(cell, vec2(127.1, 311.7)),
		dot(cell + vec2(1.0, 0.0), vec2(127.1, 311.7)),
		dot(cell + vec2(0.0, 1.0), vec2(127.1, 311.7)),
		dot(cell + vec2(1.0), vec2(127.1, 311.7)))) * 43758.5453);
	return mix(mix(n.x, n.y, f.x), mix(n.z, n.w, f.x), f.y);
}

void rl_apply(inout vec3 colour, inout float roughness, inout float metal) {
	if (rl_season < -0.5) { return; }
	float green = smoothstep(0.0, 0.08, colour.g - colour.r * 0.93)
		* smoothstep(0.0, 0.06, colour.g - colour.b * 0.9);
	float height = clamp((rl_position.y - rl_height.x) / rl_height.y, 0.0, 1.0);
	float leaves = rl_kind == 1 || rl_kind == 2 || rl_kind == 3 ? 1.0 : 0.0;
	if (rl_mixed_crown) {
		// Atlas trees contain their bark too. Keep brown trunks and branches.
		float pink = smoothstep(0.02, 0.10, colour.b - colour.r * 0.45)
			* smoothstep(0.02, 0.12, colour.r - colour.g);
		float leaf_colour = rl_season < 0.5 || rl_season > 2.5 ? max(green, pink) : green;
		leaves *= smoothstep(0.18, 0.38, height) * leaf_colour;
	}
	leaves *= rl_foliage;
	float luma = max(dot(colour, vec3(0.2126, 0.7152, 0.0722)), 0.015);
	float variation = rl_noise(rl_position.xz * 0.35 + vec2(rl_seed * 19.0));
	if (leaves > 0.001 && rl_kind != 2) {
		vec3 palette = vec3(0.16, 0.36, 0.075);
		float amount = 0.24;
		if (rl_season > 2.5) {
			// A stable mix of russet, orange and gold across each crown.
			palette = mix(vec3(0.58, 0.065, 0.018), vec3(0.94, 0.49, 0.035), variation);
			amount = 0.94;
		} else if (rl_season > 0.5 && rl_season < 1.5) {
			palette = vec3(0.28, 0.57, 0.09);
			amount = 0.44;
		} else if (rl_season < 0.5) {
			palette = vec3(0.30, 0.27, 0.19);
			amount = 0.65;
		}
		float target_luma = dot(palette, vec3(0.2126, 0.7152, 0.0722));
		colour = mix(colour, palette * (luma / max(target_luma, 0.01)), leaves * amount);
	}
	if (rl_kind == 0 && rl_season > 2.5) {
		colour = mix(colour, colour * vec3(1.13, 0.91, 0.66), green * 0.5);
	}
	if (rl_season < 0.5 && rl_snow > 0.0) {
		// Only upward-facing surfaces accumulate snow; cliff faces and trunks
		// retain their materials. Fine variation keeps the snow from flat white.
		float upward = smoothstep(0.30, 0.82, rl_up);
		float cover = upward;
		if (rl_kind == 1 || rl_kind == 2 || rl_kind == 3) {
			cover *= leaves * 0.83;
		} else if (rl_kind == 4) {
			cover *= 0.78;
		}
		cover *= rl_snow * mix(0.86, 0.99, variation);
		vec3 snow = vec3(0.84, 0.89, 0.95) * mix(0.91, 1.0,
			rl_noise(rl_position.xz * 4.0));
		colour = mix(colour, snow, clamp(cover, 0.0, 1.0));
		roughness = mix(roughness, 0.94, cover);
		metal = mix(metal, 0.0, cover);
	}
}
