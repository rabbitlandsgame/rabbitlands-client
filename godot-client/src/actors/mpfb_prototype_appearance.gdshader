shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform sampler2D base_texture : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 base_color : source_color = vec4(1.0);
uniform vec4 skin_tint : source_color = vec4(1.0);
uniform vec4 eye_tint : source_color = vec4(0.35, 0.25, 0.15, 1.0);
uniform bool is_eye = false;

void fragment() {
	vec4 sampled = texture(base_texture, UV);
	if (is_eye && sampled.a < 0.5) { discard; }
	vec3 paint = sampled.rgb * base_color.rgb;
	if (is_eye) {
		float lightness = dot(paint, vec3(0.2126, 0.7152, 0.0722));
		float chroma = max(paint.r, max(paint.g, paint.b)) - min(paint.r, min(paint.g, paint.b));
		// Recolor the iris pigment while retaining the white, pupil and limbus.
		float pigment = smoothstep(0.04, 0.14, chroma) * smoothstep(0.012, 0.06, lightness);
		// Retain contrast between the source iris crypts and radial fibers.
		vec3 iris = eye_tint.rgb * clamp(3.8 * lightness, 0.04, 1.5);
		ALBEDO = mix(paint, iris, pigment * 0.78);
		ROUGHNESS = 0.20;
		SPECULAR = 0.48;
	} else {
		ALBEDO = paint * skin_tint.rgb;
		ROUGHNESS = 0.66;
		SPECULAR = 0.28;
	}
}
