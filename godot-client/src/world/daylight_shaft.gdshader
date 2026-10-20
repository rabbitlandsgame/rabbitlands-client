shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never, shadows_disabled;
// The Cenote Deeps' daylight through the sinkhole (underground_scenery.gd puts
// it on Shaft_*): added light, soft at the column's edges and fading upward,
// so it reads as sun in damp air rather than a glass cylinder.
varying float height;

void vertex() {
	height = (MODEL_MATRIX * vec4(VERTEX, 1.0)).y;
}

void fragment() {
	float facing = abs(dot(normalize(NORMAL), normalize(VIEW)));
	float edge = pow(facing, 2.5);
	float rise = 1.0 - smoothstep(2.0, 15.0, height);
	float foot = smoothstep(-0.4, 1.2, height);
	ALBEDO = vec3(.62, .66, .50) * edge * rise * foot * .45;
}
