shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform vec4 hair_color : source_color = vec4(0.28, 0.13, 0.06, 1.0);
uniform float hair_length_delta = 0.0;
uniform float hair_volume_delta = 0.0;
uniform bool use_reference_paint = false;
uniform bool use_reference_texture = false;
uniform sampler2D reference_paint : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 paint_reference_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
varying vec2 strand_uv;

void vertex() {
	// Authored cap/root pinning is encoded in vertex alpha, not transparency.
	float free_lock = COLOR.a;
	VERTEX.xz *= 1.0 + 0.13 * hair_volume_delta * free_lock;
	VERTEX.y += 0.018 * hair_length_delta * free_lock * sign(VERTEX.y - 0.11);
	// Godot's raw glTF importer makes the material's texCoord=1 paint atlas
	// primary UV and retains the original lock-growth coordinates as UV2.
	strand_uv = use_reference_texture ? UV2 : UV;
}

void fragment() {
	float across = strand_uv.x;
	float along = strand_uv.y;
	float broad = pow(max(0.0, sin(across * 3.14159265)), 0.8);
	float derivative = fwidth(across);
	float fiber_fade = 1.0 - smoothstep(0.008, 0.035, derivative);
	float fibers = sin(across * 100.53096 + 0.7 * sin(along * 9.0));
	float fine = 1.0 + fiber_fade * 0.075 * fibers;
	float root = mix(0.72, 1.0, smoothstep(0.0, 0.23, along));
	float tip = mix(1.0, 0.86, smoothstep(0.72, 1.0, along));
	float painted_band = pow(max(0.0, sin(across * 3.14159265 + 0.15 * sin(along * 7.0))), 2.3);
	vec3 warm_highlight = hair_color.rgb * vec3(1.55, 1.72, 1.85);
	vec3 pigment = mix(hair_color.rgb * 0.72, warm_highlight, painted_band * 0.46) * fine * root * tip;
	if (use_reference_paint) {
		vec3 palette_ratio = hair_color.rgb / max(paint_reference_color.rgb, vec3(0.005));
		pigment = COLOR.rgb * palette_ratio * fine * (0.96 + 0.08 * broad);
	}
	if (use_reference_texture) {
		vec3 palette_ratio = hair_color.rgb / max(paint_reference_color.rgb, vec3(0.005));
		pigment = texture(reference_paint, UV).rgb * palette_ratio * fine;
	}
	ALBEDO = pigment;
	ROUGHNESS = 0.58 + 0.10 * (1.0 - broad);
	SPECULAR = 0.20;
	ANISOTROPY = 0.25;
	ANISOTROPY_FLOW = vec2(0.0, 1.0);
}
