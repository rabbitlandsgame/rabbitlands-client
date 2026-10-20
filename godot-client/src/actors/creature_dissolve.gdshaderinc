// Shared by the body and its surface fragments. Coordinates are actor-local,
// measured in metres, so all surfaces break apart along the same boundary.
uniform float dissolve_progress = 0.0;
uniform mat4 dissolve_to_actor;
uniform vec3 dissolve_min;
uniform vec3 dissolve_size = vec3(1.0);
uniform float dissolve_grain = 0.08;

float dissolve_hash(vec3 p) {
	return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
}

float dissolve_release(vec3 p) {
	vec3 cell = floor(p / dissolve_grain);
	vec3 f = fract(p / dissolve_grain);
	f = f * f * (3.0 - 2.0 * f);
	float n = mix(mix(mix(dissolve_hash(cell), dissolve_hash(cell + vec3(1,0,0)), f.x),
		mix(dissolve_hash(cell + vec3(0,1,0)), dissolve_hash(cell + vec3(1,1,0)), f.x), f.y),
		mix(mix(dissolve_hash(cell + vec3(0,0,1)), dissolve_hash(cell + vec3(1,0,1)), f.x),
		mix(dissolve_hash(cell + vec3(0,1,1)), dissolve_hash(cell + vec3(1,1,1)), f.x), f.y), f.z);
	vec3 along = clamp((p - dissolve_min) / max(dissolve_size, vec3(0.01)), vec3(0.0), vec3(1.0));
	return 0.02 + 0.60 * mix(n, 1.0 - (along.x * 0.65 + along.y * 0.35), 0.45);
}

void dissolve_body(vec3 world_position, inout vec3 albedo) {
	vec3 p = (dissolve_to_actor * vec4(world_position, 1.0)).xyz;
	float remaining = dissolve_release(p) - dissolve_progress;
	if (remaining <= 0.0) { discard; }
	float ash = 1.0 - smoothstep(0.0, 0.065, remaining);
	albedo = mix(albedo, vec3(0.24, 0.21, 0.18), ash * 0.75);
}
