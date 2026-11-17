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
// no foam lines an object's outline either (round 6: every sea pixel inside
// the fade reads it, below). Near the frame's edge an end can fall off the
// screen: it is pulled back along the chord to the frame's edge, and one off
// even a tenth of the way out is its opposite mirrored through the ground
// under the pixel (round 4's first gate kept the whole wash there instead,
// and the streaks came back in a strip a chord wide along every edge of the
// frame). Only with neither chord telling does the wash stay.
//
// Shallow water (map polish round 6, 2026-11-17). The fade was a plain
// smoothstep of alpha with the sea's own colour: over the first decimetres
// the water was nearly clear, and the sand blended (in linear light) with the
// dark teal came out grey, under a grey foam sheet at full strength right on
// the facets' cut, so gentle beaches drew a frosted, milky film with pale
// wedges in the sawtooth's notches. Now:
// - the water closes like light through water: its cover rises steeply and
//   eases out (1 - (1 - t)^look_shore_clear.x over the fade), so the bed is
//   darkened within centimetres of the waterline and deep by mid-fade;
// - over a beach the water at the waterline is the sea's colour times
//   look_shore_shallow.rgb (a greener teal, about 1.2 times the sea's
//   luminance), easing to the sea's own colour by the end of the fade, so the
//   sand that shows through is tinted, never grey; over steep ground or an
//   object (the chord's gate)
//   it stays the sea's colour, so a dark bank does not glow cyan, and inland
//   water takes only look_shore_shallow.w of the tint (over a brook's pale
//   stones the whole tint drew a pale cyan sheet);
// - cover and foam both rise from nothing over the first look_shore_clear.y
//   metres of TRUE depth (scaled with the fade, as the wobble is), so no
//   wobble or foam draws a line off the facets' cut, and past that rise the
//   sea already covers look_shore_clear.w of the bed (inland water none);
// - over steep ground or an object (the chord above, now read for every sea
//   pixel inside the fade, not only the foam's band) the sea closes within
//   look_shore_clear.z metres, so rocks, hulls, posts and risers keep a crisp
//   waterline and their submerged flanks stay teal. The gate also reads a
//   bump the chords straddle: the ground under the pixel against the mean of
//   the four ends, over the reach, adds to the chords' grade. A planar beach
//   has none; a submerged rock's top or a shelf's edge, whose four ends all
//   lie on the seabed around it (a flat chord), reads as steep;
// - an end whose scene point stands above the water tells the gate nothing
//   (continent_water_chord_end): it is something in front of the end's water
//   point or ground already out of the water;
// - a scene point in front of the water (an anti-aliased silhouette's
//   resolved depth, never real ground under visible water) counts as deep,
//   so no pale dotted rim outlines a cliff or a palm over the sea;
// - the noise hashes its integer cell, so its corners agree bit for bit at
//   continent coordinates (the float hash stepped along cell lines: ruled
//   lines in the wash and the rim haze).
// Repair of round 6 (its review, 2026-11-17). The first cut's tint raised the
// sea's luminance 2.35 times and its cover was 0 for 4 cm, 0.25 at 5 cm and
// 0.45 at 10 cm, so over the submerged sand, which the ground draws paler and
// greyer than the dry beach, a notch or a step's shelf drew a pane lighter
// than the sand (Saltsound's kelp notch, its steps). And the gate read any
// scene point at an end's screen position as ground, so a tuft, a stump, a
// seaweed pile or a near bank's crest in front of the water shut it: opaque,
// untinted water in the occluder's shape beside it. With the floor, the
// milder tint and a 0.22 m steep fade, a gate flipping in one pixel steps
// the cover by about a tenth instead of switching a band to opaque.
global uniform float rl_water_shore;
uniform sampler2D look_shore_depth_texture : hint_depth_texture, repeat_disable, filter_nearest;
uniform vec2 look_shore_depth = vec2(0.55, 0.0);
uniform vec2 look_shore_wobble = vec2(0.14, 2.3);
uniform vec3 look_shore_foam = vec3(0.14, 0.05, 1.4);
uniform vec3 look_shore_foam_colour = vec3(0.5, 0.54, 0.52);
uniform vec3 look_shore_foam_up = vec3(0.75, 0.9, 0.5);
uniform vec3 look_shore_inland = vec3(0.5, 2.0, 0.12);
uniform vec4 look_shore_clear = vec4(3.0, 0.003, 0.22, 0.7);
uniform vec4 look_shore_shallow = vec4(1.0, 1.26, 0.96, 0.18);
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

// One end of the gate's chords (below): the scene beneath the water point
// `water + offset` as the camera sees it, in xyz, and in w the share of
// `offset` the end stands at: 1, or less where the end fell off the screen and
// was pulled back along the chord to the frame's edge. w is 0 where the end
// tells nothing about the ground under the water: still off the screen a tenth
// of the way out, nothing drawn there, or a scene point standing above the
// water's surface `level`. That is something in front of the end's own water
// point (a tuft, a stump, a seaweed pile, a near bank's crest, a creature) or
// ground already out of the water, and neither is the ground beneath it.
vec4 continent_water_chord_end(vec3 water, vec3 offset, float level, mat4 view_matrix, mat4 projection,
		mat4 inv_projection, mat4 inv_view) {
	vec4 from = projection * (view_matrix * vec4(water, 1.0));
	vec4 span = projection * (view_matrix * vec4(water + offset, 1.0)) - from;
	// Clip space is linear along the chord: against each of the frame's four
	// edges (|x| and |y| at most w, a hair inside) an end beyond it is pulled
	// back to where the chord crosses it.
	vec4 inside = vec4(from.x, -from.x, from.y, -from.y) - 0.998 * from.w;
	vec4 slope = vec4(span.x, -span.x, span.y, -span.y) - 0.998 * span.w;
	vec4 cap = mix(vec4(1.0), clamp(-inside / max(slope, vec4(0.000001)), 0.0, 1.0),
		step(vec4(0.0), inside + slope));
	float kept = min(min(cap.x, cap.y), min(cap.z, cap.w));
	vec4 clip = from + span * kept;
	if (kept < 0.1 || clip.w <= 0.000001) {
		return vec4(0.0);
	}
	vec4 scene = continent_water_scene(clip.xy / clip.w * 0.5 + 0.5, inv_projection, inv_view);
	if (scene.w < 0.5 || scene.y > level + 0.03) {
		return vec4(0.0);
	}
	return vec4(scene.xyz, kept);
}

// A chord end as a point: the end itself, or where it tells nothing its
// opposite mirrored through the ground under the pixel `centre` (exact for a
// plane), or with neither end the level point `reach` from the centre (no
// slope read along that chord).
vec3 continent_water_chord_point(vec3 centre, vec4 end, vec4 opposite, vec3 reach) {
	return end.w > 0.0 ? end.xyz : (opposite.w > 0.0 ? 2.0 * centre - opposite.xyz : centre + reach);
}

// How far the ground under the pixel `centre` stands off the line through a
// chord's two ends (both telling), scaled to a whole chord: an end pulled back
// to the frame's edge spans less, and a bowl's or a hump's offset shrinks with
// the product of the two shares.
float continent_water_chord_bump(vec3 centre, vec4 plus, vec4 minus) {
	float across = (plus.w * minus.y + minus.w * plus.y) / max(plus.w + minus.w, 0.000001);
	return (centre.y - across) / max(plus.w * minus.w, 0.2);
}

// A lattice corner's value in [0, 1), from its integer cell alone: integer
// arithmetic, so every fragment that reaches a corner (from either side of a
// cell's edge) gets the same bits at any coordinate. The float hash it
// replaces (fract(p * 0.1031)...) was chaotic at continent-scale cells
// (1,000-8,500): one rounding of `cell + offset` moved it by up to 0.5, and
// the noise stepped along cell lines.
float continent_water_hash(ivec2 cell) {
	uint h = (uint(cell.x) * 1597334677u) ^ (uint(cell.y) * 3812015801u);
	h ^= h >> 16u;
	h *= 2246822519u;
	h ^= h >> 13u;
	h *= 3266489917u;
	h ^= h >> 16u;
	return float(h >> 8u) / 16777216.0;
}

float continent_water_noise(vec2 p) {
	vec2 corner = floor(p);
	vec2 f = p - corner;
	ivec2 cell = ivec2(corner);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(continent_water_hash(cell), continent_water_hash(cell + ivec2(1, 0)), u.x),
		mix(continent_water_hash(cell + ivec2(0, 1)), continent_water_hash(cell + ivec2(1, 1)), u.x),
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
	// Ground under visible water is never in front of it: a scene point above
	// the surface on this pixel's ray is a silhouette's resolved depth (MSAA
	// averages a cliff's or a palm's samples with the seabed's), so the water
	// there is deep, not a waterline. The margin grows with distance, past the
	// depth buffer's own error at a real waterline.
	if (shore_depth < -(0.05 + 0.004 * length(VERTEX))) {
		shore_depth = 1000.0;
	}
	float shore_on = clamp(rl_water_shore, 0.0, 1.0);
	// Inland water: a narrow fade, its wobble in proportion, no foam.
	float inland = smoothstep(look_shore_inland.x, look_shore_inland.y, continent_water_level);
	float fade = mix(look_shore_depth.x, min(look_shore_depth.x, look_shore_inland.z), inland);
	float shore_noise = 0.65 * continent_water_noise(p / look_shore_wobble.y)
		+ 0.35 * continent_water_noise(p / look_shore_wobble.y * 2.7 + vec2(13.1, 7.7));
	float wobble = look_shore_wobble.x * fade / max(look_shore_depth.x, 0.001);
	float wobbled = shore_depth + (shore_noise - 0.5) * 2.0 * wobble;
	// The ground's slope beneath (the chord above), for every sea pixel inside
	// the fade: 1 over a beach, 0 over a bank, a riser or an object.
	float foam_ground = 1.0;
	if (wobbled < fade && inland < 1.0 && shore_on > 0.0 && shore_world.w > 0.5) {
		vec3 water_world = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
		vec3 reach_x = vec3(look_shore_foam_up.z, 0.0, 0.0);
		vec3 reach_z = vec3(0.0, 0.0, look_shore_foam_up.z);
		vec4 east = continent_water_chord_end(water_world, reach_x, continent_water_height, VIEW_MATRIX,
			PROJECTION_MATRIX, INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		vec4 west = continent_water_chord_end(water_world, -reach_x, continent_water_height, VIEW_MATRIX,
			PROJECTION_MATRIX, INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		vec4 south = continent_water_chord_end(water_world, reach_z, continent_water_height, VIEW_MATRIX,
			PROJECTION_MATRIX, INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		vec4 north = continent_water_chord_end(water_world, -reach_z, continent_water_height, VIEW_MATRIX,
			PROJECTION_MATRIX, INV_PROJECTION_MATRIX, INV_VIEW_MATRIX);
		// An end that tells nothing (off the screen, or something in front of
		// the water there) is its opposite mirrored through the ground under the
		// pixel, so a plane keeps its grade and its zero bump; a chord with
		// neither end reads no slope along it; with neither chord the wash stays.
		if (max(east.w, west.w) > 0.0 || max(south.w, north.w) > 0.0) {
			vec3 east_end = continent_water_chord_point(shore_world.xyz, east, west, reach_x);
			vec3 west_end = continent_water_chord_point(shore_world.xyz, west, east, -reach_x);
			vec3 south_end = continent_water_chord_point(shore_world.xyz, south, north, reach_z);
			vec3 north_end = continent_water_chord_point(shore_world.xyz, north, south, -reach_z);
			vec3 facet = cross(south_end - north_end, east_end - west_end);
			// The bump, from each chord with both ends telling: the ground under
			// the pixel off the line through them, over the reach.
			float bumps = 0.0;
			float chords = 0.0;
			if (min(east.w, west.w) > 0.0) {
				bumps += continent_water_chord_bump(shore_world.xyz, east, west);
				chords += 1.0;
			}
			if (min(south.w, north.w) > 0.0) {
				bumps += continent_water_chord_bump(shore_world.xyz, south, north);
				chords += 1.0;
			}
			float bump = abs(bumps) / max(chords, 1.0) / max(look_shore_foam_up.z, 0.001);
			float grade = length(facet.xz) / max(abs(facet.y), 0.000001) + bump;
			float facet_up = inversesqrt(1.0 + grade * grade);
			foam_ground = smoothstep(look_shore_foam_up.x, look_shore_foam_up.y, facet_up);
		}
	}
	// Over steep ground or an object the sea closes within look_shore_clear.z
	// (its wobble and its first rise in proportion); a beach keeps its fade.
	float shore_fade = mix(min(fade, look_shore_clear.z), fade, max(foam_ground, inland));
	float shore_scale = shore_fade / max(look_shore_depth.x, 0.001);
	wobbled = shore_depth + (shore_noise - 0.5) * 2.0 * look_shore_wobble.x * shore_scale;
	float shore_t = clamp((wobbled - look_shore_depth.y) / max(shore_fade - look_shore_depth.y, 0.001), 0.0, 1.0);
	// Nothing at the cut itself, whatever the wobble: the first look_shore_clear.y
	// metres of true depth (scaled with the fade) bring the water in, to
	// look_shore_clear.w of cover on the sea at once (none inland).
	float shore_rise = smoothstep(0.0, max(look_shore_clear.y * shore_scale, 0.001), shore_depth);
	float shore_floor = look_shore_clear.w * (1.0 - inland);
	float shore_alpha = (shore_floor + (1.0 - shore_floor) * (1.0 - pow(1.0 - shore_t, look_shore_clear.x)))
		* shore_rise;
	// Shallow water over a beach is a greener teal than the open sea (about
	// 1.2 times its luminance), so the sand it covers is tinted rather than
	// greyed and never drawn lighter than it is; over steep
	// ground or an object it is the sea's own colour, and inland water takes
	// a share of the tint.
	vec3 shore_tint = mix(vec3(1.0), look_shore_shallow.rgb, foam_ground * mix(1.0, look_shore_shallow.w, inland));
	vec3 shore_shallow = ALBEDO * shore_tint;
	ALBEDO = mix(ALBEDO, mix(shore_shallow, ALBEDO, smoothstep(0.0, 1.0, shore_t)), shore_on);
	// The foam: a thin broken ridge a few centimetres of WOBBLED depth off the
	// waterline (so it wanders on and off the beach rather than tracing the
	// facets' cut, where it is nothing), broken by a slow drifting noise so it
	// reads as a scatter of wash; only on the sea, over ground that faces up.
	float foam_peak = 0.4 * look_shore_foam.x;
	float foam_band = shore_rise * smoothstep(0.0, foam_peak, wobbled)
		* (1.0 - smoothstep(foam_peak, look_shore_foam.x, wobbled)) * shore_on * (1.0 - inland);
	float foam_noise = continent_water_noise(p / look_shore_foam.z + vec2(water_time * .05, -water_time * .03));
	float foam = foam_band * smoothstep(0.45, 0.75, foam_noise) * look_shore_foam.y * foam_ground;
	// The foam lies over the water: together they cover foam + water * (1 - foam).
	float shore_cover = foam + shore_alpha * (1.0 - foam);
	ALBEDO = mix(ALBEDO, look_shore_foam_colour, foam / max(shore_cover, 0.0001));
	ALPHA = mix(1.0, clamp(shore_cover, 0.0, 1.0), shore_on);
#endif
	// All exterior frames are translation-only, so these continent-space
	// ripple normals also agree across differently authored water primitives.
	vec3 ripple_normal = normalize(vec3(-.055 * ripple, 1.0, -.045 * crossing));
	NORMAL = normalize((VIEW_MATRIX * vec4(ripple_normal, 0.0)).xyz);
	ROUGHNESS = .64;
	METALLIC = .0;
	SPECULAR = .16;
}
