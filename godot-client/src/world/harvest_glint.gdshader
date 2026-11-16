shader_type spatial;
// The cave glint on a harvest node (harvest_glint.gd): a few small warm
// four-pointed flares on the node's model that wink in turn. Each quad's four
// vertices all stand at its flare's centre; the vertex stage opens the quad in
// view space (UV gives the corner), so a flare faces the camera at any yaw or
// tilt the model takes, and keeps its size in metres whatever the model's
// scale. COLOR.r is the flare's share of the wink cycle; the node's world
// position staggers whole nodes so a cave of them never blinks in unison.
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, skip_vertex_transform,
	shadows_disabled, fog_disabled;

uniform sampler2D flare_texture : source_color, filter_linear, repeat_disable;
uniform vec3 tint : source_color = vec3(1.0, 0.82, 0.46);
// The flare's side at the height of its wink, in metres.
uniform float flare_metres = 0.34;
// Additive strength at the height of a wink: faint, and plain in a dark cave.
uniform float strength = 0.7;
// Seconds per wink cycle; a node's three flares share it a third apart.
uniform float period = 3.6;
// Each flare is drawn this far towards the camera, so it sits on the face of
// the seam or the cap it marks rather than inside it.
uniform float lift_metres = 0.16;
// Distance from the camera (metres) over which the flares fade out: a near
// glint, not a beacon across the cave.
uniform float fade_start = 26.0;
uniform float fade_end = 36.0;

varying float wink;

float node_hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void vertex() {
	vec3 centre = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float distance_to_camera = length(centre);
	centre += normalize(-centre) * min(lift_metres, distance_to_camera * 0.5);
	float phase = node_hash(floor(NODE_POSITION_WORLD.xz * 2.0) + vec2(0.37, 0.71)) + COLOR.r;
	float t = fract(TIME / period + phase);
	// A quick swell and a slower fade, then dark for the rest of the cycle.
	wink = smoothstep(0.0, 0.09, t) * (1.0 - smoothstep(0.09, 0.3, t));
	wink *= 1.0 - smoothstep(fade_start, fade_end, distance_to_camera);
	vec2 corner = UV * 2.0 - 1.0;
	VERTEX = centre + vec3(corner * flare_metres * 0.5 * (0.5 + 0.5 * wink), 0.0);
	NORMAL = vec3(0.0, 0.0, 1.0);
}

void fragment() {
	ALBEDO = tint;
	ALPHA = clamp(texture(flare_texture, UV).a * wink * strength, 0.0, 1.0);
}
