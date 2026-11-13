shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, shadows_disabled, cull_back;

uniform vec4 colors[4] : source_color;
uniform int families[4];
uniform int color_count = 1;
uniform float strength = 1.0;
varying vec3 point;

void vertex() {
	point = VERTEX;
	VERTEX += NORMAL * 0.0065;
}

void fragment() {
	float around = fract(atan(point.z, point.x) / 6.2831853 + 0.5 + TIME * 0.055);
	float band = around * float(color_count);
	int index = min(int(band), color_count - 1);
	int next_index = (index + 1) % color_count;
	vec3 tint = mix(colors[index].rgb, colors[next_index].rgb, smoothstep(0.65, 1.0, fract(band)));
	int family = families[index];
	float pattern = 0.6;
	if (family == 0) { // Flame tongues climb the piece.
		pattern = 0.5 + 0.5 * sin(point.y * 32.0 - TIME * 4.5 + sin(point.x * 35.0) * 2.0);
	} else if (family == 1) { // Slow crystalline facets.
		pattern = pow(abs(sin((point.x + point.z) * 45.0) * cos(point.y * 30.0 + TIME * 0.5)), 0.7);
	} else if (family == 2 || family == 5) { // Bands of arcane/radiant energy.
		pattern = pow(0.5 + 0.5 * sin(point.y * 48.0 + TIME * 2.0), 5.0);
	} else if (family == 3 || family == 4) { // Life and draining effects breathe.
		pattern = 0.5 + 0.5 * sin(TIME * 2.4 + point.y * 8.0);
	} else if (family == 6) { // Wind moves in fine sweeping ribbons.
		pattern = pow(0.5 + 0.5 * sin(point.y * 60.0 + around * 18.0 - TIME * 3.0), 3.0);
	} else { // Physical defenses and damage have a restrained metallic glint.
		pattern = pow(0.5 + 0.5 * sin(point.y * 16.0 + TIME * 1.3), 8.0);
	}
	float rim = pow(1.0 - clamp(dot(normalize(NORMAL), normalize(VIEW)), 0.0, 1.0), 1.7);
	ALBEDO = tint * 1.3;
	ALPHA = clamp((0.12 + rim * 0.8) * (0.5 + pattern * 0.65) * strength, 0.0, 0.95);
}
