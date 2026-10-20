shader_type spatial;
render_mode cull_disabled;
// The Cenote Deeps' standing water (underground_scenery.gd puts it on Water_*).
// Dissolved limestone makes a sinkhole pool the clearest green in the jungle:
// translucent over its mossy bed, rippled, faintly lit from within. Colours are
// linear albedo, as Forward+ lights them (lantern_water.gdshader's note).
varying vec3 world_position;

void vertex() {
	world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = world_position.xz;
	float a = sin(dot(p, vec2(.61, .27)) + TIME * .7);
	float b = sin(dot(p, vec2(-.23, .69)) - TIME * .5);
	float ripples = sin(dot(p, vec2(2.4, 1.3)) + a * 1.2 + TIME * .9) * .5 + .5;
	vec3 deep = vec3(.03, .19, .17);
	vec3 clear = vec3(.08, .40, .34);
	ALBEDO = mix(deep, clear, .55 + .25 * a * b) + vec3(.012, .03, .026) * ripples;
	ROUGHNESS = .06;
	SPECULAR = .6;
	NORMAL_MAP = vec3(.5 + a * .07, .5 + b * .06, 1.0);
	NORMAL_MAP_DEPTH = .5;
	EMISSION = vec3(0.0, .035, .03) * (.6 + .4 * ripples);
	ALPHA = .82;
}
