// Cosmetic age uses eye_color's otherwise unused alpha; RGB is still eye dye.
// 1 is the legacy/off value. Nonzero options are 2 + age + 128 * greying,
// with both integer amounts in 0..100 (exact even in a float32 uniform).
vec2 rl_age_amounts() {
	if (eye_color.a < 1.5) { return vec2(0.0); }
	float value = floor(max(eye_color.a - 2.0, 0.0) + 0.5);
	return clamp(vec2(mod(value, 128.0), floor(value / 128.0)), 0.0, 100.0) / 100.0;
}

// UV-anchored strands stay stable while a character moves and while its age
// changes. COLOR.r is deliberately unused: soft hairline assets use it for
// coverage. Alpha/keep levels, roots and silhouette are never changed here.
vec3 rl_grey_colour(vec3 colour, vec2 uv, float amount) {
	if (amount <= 0.0) { return colour; }
	float strand = fract(sin(floor(uv.x * 224.0) * 127.1 + 17.4) * 43758.5453);
	float grey = amount >= 1.0 ? 1.0 : smoothstep(strand - 0.035, strand + 0.035, amount);
	float lightness = max(max(colour.r, max(colour.g, colour.b)) * 0.95, 0.65);
	return mix(colour, vec3(0.97, 0.985, 1.0) * lightness, grey);
}

float rl_age_line(float distance_value, float width, float footprint) {
	float filtered = max(width, footprint);
	return exp(-pow(distance_value / filtered, 2.0)) * min(1.0, width / max(footprint, 0.00001));
}

// The head atlas is shared by both sexes and all identity/expression targets.
// These soft contours follow its forehead, outer eyes, lower lids and smile
// folds; the caller masks them to face skin before any painted features.
vec3 rl_age_masks(vec2 uv) {
	float px = max(fwidth(uv.x), 0.00001);
	float py = max(fwidth(uv.y), 0.00001);
	float x = uv.x - 0.37;
	float lines = 0.0;
	float tissue = 0.0;
	for (int i = 0; i < 4; i++) {
		float span = 0.105 - abs(float(i) - 1.5) * 0.008;
		float forehead = 1.0 - smoothstep(span, span + 0.040, abs(x));
		float centre = 0.477 + float(i) * 0.027 + 0.65 * x * x + 0.0018 * sin(uv.x * 61.0 + float(i));
		float broken = 0.5 + 0.5 * smoothstep(-0.5, 0.6, sin(x * 73.0 + float(i) * 1.9));
		lines += rl_age_line(uv.y - centre, 0.0014, py) * forehead * broken * (0.65 + float(i) * 0.10);
		tissue += rl_age_line(uv.y - centre - 0.002, 0.007, py) * forehead * broken * 0.22;
	}
	float side = x < 0.0 ? -1.0 : 1.0;
	float from_outer_eye = abs(x) - 0.132;
	float crow_span = smoothstep(-0.002, 0.006, from_outer_eye) * (1.0 - smoothstep(0.025, 0.048, from_outer_eye));
	for (int i = 0; i < 3; i++) {
		float slope = float(i - 1) * 0.50;
		float crease = 0.647 + slope * max(from_outer_eye, 0.0) + 0.001 * sin(from_outer_eye * 150.0 + float(i));
		lines += rl_age_line(uv.y - crease, 0.0014, py) * crow_span * 0.9;
	}
	float eye_x = (abs(x) - 0.101) / 0.052;
	float lower_lid = 0.687 + 0.011 * eye_x * eye_x;
	float eye_span = 1.0 - smoothstep(0.72, 1.0, abs(eye_x));
	lines += rl_age_line(uv.y - lower_lid, 0.0015, py) * eye_span * 0.75;
	lines += rl_age_line(uv.y - lower_lid - 0.015, 0.0012, py) * eye_span * 0.42;
	float under_eye = exp(-pow((uv.y - lower_lid - 0.010) / 0.015, 2.0)) * eye_span;
	tissue += under_eye * 0.65;
	float fold_t = clamp((uv.y - 0.771) / 0.111, 0.0, 1.0);
	float fold_x = 0.035 + 0.031 * fold_t - 0.010 * fold_t * fold_t;
	float fold_span = smoothstep(0.764, 0.785, uv.y) * (1.0 - smoothstep(0.863, 0.891, uv.y));
	lines += rl_age_line(abs(x) - fold_x, 0.0015, px) * fold_span * 0.85;
	tissue += rl_age_line(abs(x) - fold_x - 0.003, 0.009, px) * fold_span * 0.8;
	float corner_t = clamp((uv.y - 0.871) / 0.055, 0.0, 1.0);
	float corner_span = smoothstep(0.867, 0.883, uv.y) * (1.0 - smoothstep(0.905, 0.926, uv.y));
	float corner_x = 0.064 + 0.012 * corner_t - 0.003 * corner_t * corner_t;
	lines += rl_age_line(abs(x) - corner_x, 0.0013, px) * corner_span * 0.55;
	tissue += rl_age_line(abs(x) - corner_x - 0.002, 0.007, px) * corner_span * 0.55;
	float frown = 1.0 - smoothstep(0.020, 0.036, abs(uv.y - 0.586));
	lines += rl_age_line(x - side * 0.010, 0.0012, px) * frown * 0.65;
	return vec3(clamp(lines, 0.0, 1.6), under_eye, clamp(tissue, 0.0, 1.0));
}
