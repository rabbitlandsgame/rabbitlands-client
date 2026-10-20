// Look pass layer L4: grass beds in the wind.
//
// Draws the tufts LookGrassBeds scatters as MultiMesh instances. The tuft
// meshes carry no texture: each vertex's colour is the blade's shade, darker
// at the root, and UV.y how far up the blade it sits (0 root, 1 tip; UV.x is
// the blade's own wind phase). The colour comes from the tuft's region
// palette, blended root to tip, times the shade and the tuft's own tint:
//
//   COLOR              vertex shade x the instance's tint (its value jitter
//                      and its bed's warmth, worked out when it is placed)
//   INSTANCE_CUSTOM.x  palette slot (0 the default palette, the others handed
//                      out by LookGrassBeds as it meets regions whose region
//                      file has a grass palette, LookProfile.grass_palette)
//   INSTANCE_CUSTOM.y  a neighbouring region's palette slot, and
//   INSTANCE_CUSTOM.z  how much of it the tuft takes: near a region border the
//                      grass fades into the neighbour's, as the ground paint's
//                      trims do (LookBorders); 0 elsewhere
//   INSTANCE_CUSTOM.w  the wind's phase at the tuft (0..1 of a wave)
//
// The MultiMeshes must carry instance colours even though every tint could
// have lived in custom data: the compatibility renderer multiplies a
// multimesh's vertex colour by an instance colour whether the MultiMesh has
// one or not, and without one it drew half the blades black and a tenth
// white. Both survive that renderer's 16-bit packing of instance data.
//
// A blade is lit as if it were the ground it grows from: its normal is the
// tuft's up, on both faces, so a bed takes the sun and shade the ground
// around it takes instead of flickering blade by blade. It casts no shadow
// (the node turns that off) and only the tips move, weighted by the square
// of the height.
//
// The wind leans the tips downwind by up to look_wind_metres, easing and
// swelling with a slow gust, and sways them on a wave that rolls across the
// field. The phase is baked per tuft from its position in the continent
// frame, so a seam crossing's rebase does not jump the wave. Tufts shrink to
// nothing between look_fade_metres from the focus, so the bed's edge thins
// out instead of ending in a line.
shader_type spatial;
uniform float rl_grass_season = -1.0;
render_mode cull_disabled, depth_draw_opaque, diffuse_lambert;

// The palettes, root and tip, one per slot. The length is
// LookProfile.GRASS_PALETTE_SLOTS; they are set as plain vectors (display
// values, not converted to linear), as the four single uniforms before them.
uniform vec3 look_roots[32];
uniform vec3 look_tips[32];
uniform float look_gradient_power = 1.4;
// How much of the root-to-tip gradient every tuft keeps about its middle
// (LookProfile.GRASS_CONTRAST).
uniform float look_contrast = 1.0;
// The palette's value and chroma in the renderer in use
// (LookProfile.GRASS_VALUE_*, GRASS_CHROMA_*): the compatibility renderer
// lights display-encoded albedo, Forward+ linear.
uniform float look_value = 1.0;
uniform float look_chroma = 1.0;
uniform float look_specular = 0.15;
// Wind, in the frame the tufts are placed in (the grass node's own axes).
uniform vec2 look_wind_direction = vec2(0.8, -0.6);
uniform float look_wind_metres = 0.1;
uniform float look_wind_speed = 1.7;
uniform float look_gust_speed = 0.37;
// Where the bed is centred (global) and where its tufts shrink away.
uniform vec3 look_focus = vec3(0.0);
uniform vec2 look_fade_metres = vec2(52.0, 72.0);
// Distance softening (LookProfile.GRASS_SOFTEN_*): between these distances
// from the camera a tuft loses up to look_soften of its root-to-tip gradient
// and look_soften_shrink of its size, so the far half of a -60 degree frame
// reads as a bed's tone rather than as dark roots and bright tips a pixel or
// two apart.
uniform vec2 look_soften_metres = vec2(24.0, 44.0);
uniform float look_soften = 0.0;
uniform float look_soften_shrink = 0.0;

varying vec3 v_colour;
varying vec3 v_up;

vec3 look_palette(int index, bool tip) {
	int slot = clamp(index, 0, 31);
	return tip ? look_tips[slot] : look_roots[slot];
}

void vertex() {
	float height = UV.y;
	int index = int(INSTANCE_CUSTOM.x + 0.5);
	int other = int(INSTANCE_CUSTOM.y + 0.5);
	float blend = clamp(INSTANCE_CUSTOM.z, 0.0, 1.0);
	vec3 origin = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	float far = smoothstep(look_soften_metres.x, look_soften_metres.y,
		distance(origin, INV_VIEW_MATRIX[3].xyz));
	float gradient = mix(pow(height, look_gradient_power), 0.45, far * look_soften);
	gradient = mix(0.45, gradient, look_contrast);
	vec3 root = mix(look_palette(index, false), look_palette(other, false), blend);
	vec3 tip = mix(look_palette(index, true), look_palette(other, true), blend);
	vec3 colour = mix(root, tip, gradient) * COLOR.rgb * look_value;
	float luma = dot(colour, vec3(0.2126, 0.7152, 0.0722));
	v_colour = max(mix(vec3(luma), colour, look_chroma), vec3(0.0));

	float shrink = (1.0 - smoothstep(look_fade_metres.x, look_fade_metres.y,
		length(origin.xz - look_focus.xz))) * (1.0 - far * look_soften_shrink);

	// The instance basis is a turn, a tilt and a uniform scale, so its
	// transpose over its scale squared takes a world offset into the tuft.
	mat3 basis = mat3(MODEL_MATRIX);
	float scale_squared = max(dot(basis[0], basis[0]), 0.0001);
	float phase = INSTANCE_CUSTOM.w * 6.2831853;
	float gust = 0.5 + 0.5 * sin(TIME * look_gust_speed - phase * 0.29);
	float sway = sin(TIME * look_wind_speed - phase + UV.x * 2.6);
	float push = look_wind_metres * height * height * (0.3 + 0.7 * gust)
		* (0.6 + 0.4 * sway);
	vec3 lean = vec3(look_wind_direction.x, -0.35 * push, look_wind_direction.y) * push;
	VERTEX = (VERTEX + transpose(basis) * lean / scale_squared) * shrink;

	v_up = normalize((MODELVIEW_MATRIX * vec4(0.0, 1.0, 0.0, 0.0)).xyz);
	NORMAL = vec3(0.0, 1.0, 0.0);
}

void fragment() {
	ALBEDO = v_colour;
	if (rl_grass_season > 2.5) {
		ALBEDO *= vec3(1.18, 0.85, 0.55);
	} else if (rl_grass_season > 0.5 && rl_grass_season < 1.5) {
		ALBEDO *= vec3(1.02, 1.12, 0.91);
	}
	ROUGHNESS = 1.0;
	SPECULAR = look_specular;
	// Both faces take the tuft's up: the engine flips a back face's normal
	// before this runs, which would light half the blades from below.
	NORMAL = normalize(v_up);
}
