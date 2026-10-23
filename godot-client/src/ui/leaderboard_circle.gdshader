shader_type canvas_item;
render_mode unshaded;
void fragment() {
	vec4 sample_color = texture(TEXTURE, UV);
	float edge = 1.0 - smoothstep(0.485, 0.5, distance(UV, vec2(0.5)));
	COLOR = vec4(sample_color.rgb, sample_color.a * edge);
}
