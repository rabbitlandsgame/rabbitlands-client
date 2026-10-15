shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled;

uniform vec4 deep_color : source_color = vec4(0.045, 0.15, 0.20, 0.90);
uniform vec4 shallow_color : source_color = vec4(0.12, 0.29, 0.28, 0.86);
uniform vec4 foam_color : source_color = vec4(0.38, 0.56, 0.54, 1.0);
uniform float river_half_width : hint_range(0.1, 64.0, 0.1) = 3.0;
varying vec3 world_position;

void vertex() {
	world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = world_position.xz;
	float a = sin(dot(p, vec2(0.59, 0.26)) + TIME * 0.8);
	float b = sin(dot(p, vec2(-0.24, 0.72)) - TIME * 0.55);
	float ripples = sin(dot(p, vec2(2.7, 1.5)) + a * 1.1 + TIME) * 0.5 + 0.5;
	// Generated water vertices carry their distance from the authored river
	// curve in UV2.x, so bends and transformed paths shade correctly while the
	// saved material keeps control of the width-aware bank treatment. New
	// meshes carry their local authored half-width in UV2.y; zero retains the
	// uniform fallback for old meshes and hand-authored previews.
	float local_half_width = UV2.y > 0.0 ? UV2.y : river_half_width;
	float bank = smoothstep(local_half_width * 0.48, local_half_width, UV2.x);
	ALBEDO = mix(deep_color.rgb, shallow_color.rgb, bank);
	ALBEDO += vec3(0.009, 0.018, 0.02) * ripples;
	float foam = smoothstep(0.72, 0.98, bank) * (0.3 + 0.7 * pow(ripples, 5.0));
	ALBEDO = mix(ALBEDO, foam_color.rgb, foam * 0.48);
	NORMAL_MAP = vec3(0.5 + a * 0.08, 0.5 + b * 0.065, 1.0);
	NORMAL_MAP_DEPTH = 0.48;
	ROUGHNESS = 0.52;
	METALLIC = 0.08;
	SPECULAR = 0.3;
	ALPHA = mix(deep_color.a, shallow_color.a, bank);
}
