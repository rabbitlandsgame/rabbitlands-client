shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, shadows_disabled, cull_disabled;
varying flat int family;
varying float angle;

void vertex() {
	// Billboard each tiny particle, preserving its individual size and position.
	vec3 scale = vec3(length(MODEL_MATRIX[0].xyz), length(MODEL_MATRIX[1].xyz), length(MODEL_MATRIX[2].xyz));
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0] * scale.x,
		INV_VIEW_MATRIX[1] * scale.y, INV_VIEW_MATRIX[2] * scale.z, MODEL_MATRIX[3]);
	family = int(INSTANCE_CUSTOM.x + 0.5);
	angle = INSTANCE_CUSTOM.y;
}

void fragment() {
	vec2 point = (UV - 0.5) * 2.0;
	point = mat2(vec2(cos(angle), -sin(angle)), vec2(sin(angle), cos(angle))) * point;
	float radius = length(point);
	if (family == 1) {
		radius = abs(point.x) + abs(point.y);
	} else if (family == 6) {
		radius = length(point * vec2(0.7, 2.2));
	} else if (family == 7) {
		radius = min(length(point * vec2(0.7, 2.6)), length(point * vec2(2.6, 0.7)));
	}
	float fleck = 1.0 - smoothstep(0.0, 0.8, radius);
	ALBEDO = COLOR.rgb;
	ALPHA = COLOR.a * fleck * fleck;
}
