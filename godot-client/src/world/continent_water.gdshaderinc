// The continent's water: the sea, and the lakes and sloping drainage the
// continent exporter draws as Water_ cells with the water_sea material
// (WorldLoader._apply_continent_water). continent_water.gdshader draws it
// opaque, as the loader puts it in. The look pass's copy in Forward+ and
// Mobile (LookGround.decode_continent_sea) may be drawn by
// look/continent_water_shore.gdshader instead, which defines
// CONTINENT_WATER_SHORE: that one reads the scene's depth and softens the
// water's edge where it meets the ground (see below).

// This transform is authored map space -> continent space. It does not change
// when the client rebases a resident region at a crossing.
uniform mat4 water_to_continent;
uniform sampler2D wave_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_wave_texture = false;
// Quest channels use the same water appearance with an authoritative flow.
// Defaults preserve the continent sea's animation.
uniform float flow_strength = 1.0;
uniform bool reduced_motion = false;
// Look pass (LookGround sets it in Forward+ on a copy; never with
// ELORIA_LOOK=0): the colours below were picked in the compatibility
// renderer, which lights display-encoded albedo. Forward+ lights the same
// numbers as linear albedo, which drew the sea a milky pale turquoise as
// bright as the roads; decoded, it is the deep sea they were picked as, and
// look_sea_value sets its brightness and look_sea_chroma its chroma (the
// decode crushes the small red channel, which drove the sea teal);
// look_sea_tint multiplies the decoded colour (a region's water.sea_tint).
uniform bool look_decode_albedo = false;
uniform float look_sea_value = 1.0;
uniform float look_sea_chroma = 1.0;
uniform vec3 look_sea_tint = vec3(1.0);

#ifdef CONTINENT_WATER_SHORE
// The water's edge (LookProfile.WATER_SHORE_*). The terrain is faceted on a
// 2 m lattice, so where the flat water cuts through it the shoreline is a
// polyline that zigzags cell by cell (Ravenhead's harbour beach drew a row of
// saw teeth, Saltsound's inlet a staircase). Here the water fades in over the
// first look_shore_depth.x metres of its own depth - its surface height less
// the height of whatever the scene drew beneath it, read back from the depth
// buffer - so the cut becomes a gradient a few metres wide on a beach and a
// narrow one against a bank. look_shore_wobble moves that depth by up to x
// metres in noise y metres across, so the fade's own contours do not trace
// the facets either. A broken band of foam lies along the first
// look_shore_foam.x metres of depth, at most look_shore_foam.y opaque, in
// noise look_shore_foam.z metres across; look_shore_foam_colour is its colour
// as decoded (linear) albedo. rl_water_shore (project.godot
// [shader_globals]) is the graphics quality's switch: 0 at LOW draws the
// water whole, as the opaque shader does.
//
// Inland water (map polish round 4, 2026-11-16): the same Water_ cells draw
// the elevated lakes and the sloping drainage, whose drawn depth can be a
// few centimetres by design (Twinbrook's graded brook carries 0.03-0.28 m).
// Under the sea's fade it read as a clear grey smear scattered with foam.
// Water whose surface stands look_shore_inland.y metres or more above the sea
// in the continent's frame (water_to_continent, so a rebase cannot move it)
// is inland: it fades in over look_shore_inland.z metres instead, its wobble
// shrinks with its fade, and it carries no foam; from look_shore_inland.x up
// to .y it blends from the sea's edge to that, so a river mouth meets the
// coast without a seam.
//
// Steep ground beneath: the foam lies only where the ground under the water
// faces up. On a bank facet or a single-node tooth the foam band is a thin
// sliver over a stretched texture and read as a pale streaked smear with a
// straight top (Suncoil's pier root). The ground's slope is measured over a
// chord: the scene is read back from the depth buffer where the water's own
// point moved look_shore_foam_up.z metres east, west, south and north falls
// on the screen, and the two chords between those ground points give its
// normal; foam is whole where the normal's up component is look_shore_foam_up.y
// or more and gone at .x or less. Not the screen derivatives of the depth
// (round 4's first try): those give each 2 m facet its own normal, so the
// foam would switch on and off along the facets' straight edges, and the
// depth beneath a beach is a stack of ground layers millimetres apart
// (terrain, base ground, sand patches with dithered and depth-pushed edges)
// against a step of a few centimetres between neighbouring pixels. Over a
// metre the layers are nothing and the slope eases across a facet's edge.
// A chord that meets an object (a rock, a hull, a post) reads as steep, so
// no foam lines an object's outline either. Only pixels in the foam's band
// read it. Near the frame's edge an end can fall off the screen: that end is
// the ground under the pixel itself, so the chord is measured over its half on
// the screen (round 4's first gate kept the whole wash there instead, and the
// streaks came back in a strip a chord wide along every edge of the frame).
// Only a chord with both ends off the screen keeps the wash.
global uniform float rl_water_shore;
uniform sampler2D look_shore_depth_texture : hint_depth_texture, repeat_disable, filter_nearest;
uniform vec2 look_shore_depth = vec2(0.55, 0.0);
uniform vec2 look_shore_wobble = vec2(0.14, 2.3);
uniform vec3 look_shore_foam = vec3(0.28, 0.45, 1.4);
uniform vec3 look_shore_foam_colour = vec3(0.62, 0.68, 0.68);
uniform vec3 look_shore_foam_up = vec3(0.75, 0.9, 0.5);
uniform vec3 look_shore_inland = vec3(0.5, 2.0, 0.12);
varying float continent_water_height;
varying float continent_water_level;

// The scene drawn beneath the screen point `uv`, as a world position (w 1),
// read back from the depth buffer; w 0 where nothing was drawn.
vec4 continent_water_scene(vec2 uv, mat4 inv_projection, mat4 inv_view) {
	float raw = textureLod(look_shore_depth_texture, uv, 0.0).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec4 view = inv_projection * vec4(vec3(uv, raw) * 2.0 - 1.0, 1.0);
#else
	vec4 view = inv_projection * vec4(uv * 2.0 - 1.0, raw, 1.0);
#endif
	if (abs(view.w) <= 0.000001) {
		return vec4(0.0);
	}
	return vec4((inv_view * vec4(view.xyz / view.w, 1.0)).xyz, 1.0);
}

// The scene beneath the world point `world` as the camera sees it (w 0 when
// that point is off the screen or nothing was drawn there).
vec4 continent_water_scene_at(vec3 world, mat4 view_matrix, mat4 projection, mat4 inv_projection,
		mat4 inv_view) {
	vec4 clip = projection * (view_matrix * vec4(world, 1.0));
	if (clip.w <= 0.000001) {
		return vec4(0.0);
	}
	vec2 uv = clip.xy / clip.w * 0.5 + 0.5;
	if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) {
		return vec4(0.0);
	}
	return continent_water_scene(uv, inv_projection, inv_view);
}

float continent_water_hash(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

float continent_water_noise(vec2 p) {
	vec2 cell = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(continent_water_hash(cell), continent_water_hash(cell + vec2(1.0, 0.0)), u.x),
		mix(continent_water_hash(cell + vec2(0.0, 1.0)), continent_water_hash(cell + vec2(1.0, 1.0)), u.x),
		u.y);
}
#endif

varying vec2 continent_position;

void vertex() {
	continent_position = (water_to_continent * vec4(VERTEX, 1.0)).xz;
#ifdef CONTINENT_WATER_SHORE
	continent_water_height = (MODEL_MATRIX * vec4(VERTEX, 1.0)).y;
	continent_water_level = (water_to_continent * vec4(VERTEX, 1.0)).y;
#endif
}

void fragment() {
	float water_time = reduced_motion ? 0.0 : TIME * flow_strength;
	vec2 p = continent_position;
	float broad = sin(dot(p, vec2(.019, -.013))) * .5 + .5;
	float ripple = sin(dot(p, vec2(.43, .19)) + water_time * .45);
	float crossing = sin(dot(p, vec2(-.16, .37)) - water_time * .31);
	// Broad, low-contrast variation belongs to the water body, not a map tile.
	float curl = sin(dot(p, vec2(.13, -.29))) * 3.0 + sin(dot(p, vec2(.15, .37))) * 2.0;
	float crest = sin(dot(p, vec2(1.8, .92)) + curl + water_time * .3);
	float broken = smoothstep(.05, .75, sin(dot(p, vec2(-.6, .44)) + crossing));
	ALBEDO = mix(vec3(.045, .14, .17), vec3(.058, .18, .19), broad);
	ALBEDO += vec3(.006, .014, .016) * (ripple * crossing);
	if (has_wave_texture) {
		vec3 first = texture(wave_texture, p * .075 + vec2(water_time * .002, 0.0)).rgb;
		vec3 second = texture(wave_texture, p.yx * .043 + vec2(0.0, water_time * .0015)).rgb;
		float detail = dot(mix(first, second, .35), vec3(.2126, .7152, .0722));
		ALBEDO *= .7 + detail * 1.6;
	} else {
		ALBEDO += vec3(.012, .022, .025) * smoothstep(.82, .98, crest) * broken;
	}
	if (look_decode_albedo) {
		ALBEDO = pow(max(ALBEDO, vec3(0.0)), vec3(2.2)) * look_sea_value;
		ALBEDO = mix(vec3(dot(ALBEDO, vec3(.2126, .7152, .0722))), ALBEDO, look_sea_chroma);
		ALBEDO = max(ALBEDO * look_sea_tint, vec3(0.0));
	}
#ifdef CONTINENT_WATER_SHORE
	// The scene beneath, as a world position: its depth through the inverse
	// projection, then the inverse view. Where nothing was drawn (the far
	// plane) the water counts as deep.
	vec4 shore_world = continent_water_scene(SCREEN_UV, INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
	float shore_depth = shore_world.w > 0.5 ? continent_water_height - shore_world.y : 1000.0;
	float shore_on = clamp(rl_water_shore, 0.0, 1.0);
	// Inland water: a narrow fade, its wobble in proportion, no foam.
	float inland = smoothstep(look_shore_inland.x, look_shore_inland.y, continent_water_level);
	float fade = mix(look_shore_depth.x, min(look_shore_depth.x, look_shore_inland.z), inland);
	float shore_noise = 0.65 * continent_water_noise(p / look_shore_wobble.y)
		+ 0.35 * continent_water_noise(p / look_shore_wobble.y * 2.7 + vec2(13.1, 7.7));
	float wobble = look_shore_wobble.x * fade / max(look_shore_depth.x, 0.001);
	float wobbled = shore_depth + (shore_noise - 0.5) * 2.0 * wobble;
	float shore_alpha = smoothstep(look_shore_depth.y, max(fade, look_shore_depth.y + 0.001), wobbled);
	// The foam: strongest at the waterline, broken by a slow drifting noise
	// so it reads as a scatter of wash rather than a ruled white line; only
	// on the sea, over ground that faces up (its slope over a chord, above).
	float foam_band = (1.0 - smoothstep(0.0, look_shore_foam.x, wobbled)) * shore_on * (1.0 - inland);
	float foam_ground = 0.0;
	if (foam_band > 0.0 && shore_world.w > 0.5) {
		vec3 water_world = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
		vec3 reach_x = vec3(look_shore_foam_up.z, 0.0, 0.0);
		vec3 reach_z = vec3(0.0, 0.0, look_shore_foam_up.z);
		vec4 east = continent_water_scene_at(water_world + reach_x, VIEW_MATRIX, PROJECTION_MATRIX,
			INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		vec4 west = continent_water_scene_at(water_world - reach_x, VIEW_MATRIX, PROJECTION_MATRIX,
			INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		vec4 south = continent_water_scene_at(water_world + reach_z, VIEW_MATRIX, PROJECTION_MATRIX,
			INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		vec4 north = continent_water_scene_at(water_world - reach_z, VIEW_MATRIX, PROJECTION_MATRIX,
			INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		// An end off the screen is the ground under the pixel itself, so its
		// chord is measured over the half on the screen; only a chord with both
		// ends off the screen says nothing, and there the wash stays.
		bool blind = (east.w < 0.5 && west.w < 0.5) || (south.w < 0.5 && north.w < 0.5);
		east = east.w > 0.5 ? east : shore_world;
		west = west.w > 0.5 ? west : shore_world;
		south = south.w > 0.5 ? south : shore_world;
		north = north.w > 0.5 ? north : shore_world;
		foam_ground = 1.0;
		if (!blind) {
			vec3 facet = cross(south.xyz - north.xyz, east.xyz - west.xyz);
			float facet_up = abs(facet.y) / max(length(facet), 0.000001);
			foam_ground = smoothstep(look_shore_foam_up.x, look_shore_foam_up.y, facet_up);
		}
	}
	float foam_noise = continent_water_noise(p / look_shore_foam.z + vec2(water_time * .05, -water_time * .03));
	float foam = foam_band * smoothstep(0.35, 0.7, foam_noise) * look_shore_foam.y * foam_ground;
	ALBEDO = mix(ALBEDO, look_shore_foam_colour, foam);
	ALPHA = mix(1.0, clamp(shore_alpha + foam, 0.0, 1.0), shore_on);
#endif
	// All exterior frames are translation-only, so these continent-space
	// ripple normals also agree across differently authored water primitives.
	vec3 ripple_normal = normalize(vec3(-.055 * ripple, 1.0, -.045 * crossing));
	NORMAL = normalize((VIEW_MATRIX * vec4(ripple_normal, 0.0)).xyz);
	ROUGHNESS = .64;
	METALLIC = .0;
	SPECULAR = .16;
}
