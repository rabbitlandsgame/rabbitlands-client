// Look pass layer L2: the painted ground's value hierarchy.
//
// Included by the painted ground shaders (painted_ground*.gdshader), which
// stand in for the ground's StandardMaterial3Ds, and by the painted copy of
// the biome blend that LookGround derives from biome_blend.gdshader at run
// time. Every value arrives as a uniform that LookGround sets from
// LookProfile, so the whole look is tuned in one place.
//
// It works on linear albedo, before light and tone curve, in three steps:
// a pixel is weighed as path (a walk deck, the exporter's worn-road colour in
// the terrain's vertex colour), yard (an authored ground patch) or pale ground
// (paving, sand, a gold trail); whatever is none of those is verge. Paths are
// repainted in a set value and hue with their texture's grain, darker than the
// paving where they run through it; the verge deepens and enriches; pale gold
// is richened; and everything carries a low-frequency variation in continent
// space and darkens with slope. Nothing reads the screen, so it runs in the
// compatibility renderer and in Forward+ alike.
//
// The compatibility renderer shades in sRGB: its albedo arrives gamma-encoded
// (measured: a walk deck whose linear luminance is 0.056 read above 0.2 there).
// Every threshold and target here is linear, so on that renderer the albedo
// is decoded on the way in and encoded again on the way out, and the two
// renderers paint the same colours.

// What the surface is. A walk deck is a path whatever its colour.
uniform float look_path_force = 0.0;
// Terrain only: read the exporter's worn-road colour out of the vertex colour.
uniform float look_road_detect = 0.0;
uniform vec3 look_road_colour = vec3(0.2265, 0.1746, 0.0855);
// Relative distance from the road colour that is still fully road, and where
// it stops being road at all.
uniform vec2 look_road_tolerance = vec2(0.12, 0.34);
// Authored ground patches: how much of the yard lift they take.
uniform float look_yard = 0.0;
// How much of the surface keeps its own colour whatever its hue, times this
// linear multiplier and at this chroma: a walk deck that its region paints as
// ground, not road (LookGround.deck_path_of).
uniform float look_keep = 0.0;
uniform vec3 look_keep_tint = vec3(1.0);
uniform float look_keep_chroma = 1.0;
// Painted ground keeps its chroma trim on the surface, away from actors/UI.
uniform float look_local_saturation = 1.0;
// And its texture's grain about the texture's mean, scaled by this.
uniform float look_keep_grain = 1.0;
// How much pale ground is spared the verge treatment (0 for the biome blend).
uniform float look_pale = 1.0;

uniform float look_path_luma = 0.24;
uniform float look_path_lift_max = 6.0;
// The road's hue as an sRGB colour; its own luminance is divided out.
uniform vec3 look_path_tint = vec3(1.0);
uniform float look_path_chroma = 1.0;
uniform float look_path_detail = 1.8;
uniform float look_path_fine_metres = 1.5;
uniform float look_path_fine = 0.12;
// Pale paving in continent space (min x, min z, max x, max z), for roads that
// run through it and are painted darker than it.
uniform vec4 look_paving_rects[8];
uniform int look_paving_count = 0;
uniform float look_paving_inset = 3.0;
uniform float look_paving_luma = 0.1;
uniform float look_paving_chroma = 0.55;
// The hue a road through the paving is painted in: warm cobble, not the
// country road's dust.
uniform vec3 look_paving_tint = vec3(0.72, 0.52, 0.4);
// A last multiplier on the whole surface: the pale paving's warm step down.
uniform vec3 look_surface_tint = vec3(1.0);
uniform float look_compat_chroma = 1.25;
uniform float look_yard_luma = 0.12;
uniform float look_yard_lift_max = 2.0;
uniform float look_yard_saturation = 1.0;
uniform vec2 look_pale_luma = vec2(0.16, 0.3);
// Gold: hue window (sRGB degrees), minimum sRGB saturation, value, chroma.
uniform vec2 look_gold_hue = vec2(35.0, 56.0);
uniform float look_gold_saturation = 0.5;
uniform float look_gold_value = 0.8;
uniform float look_gold_chroma = 1.1;
uniform float look_gold_chroma_compat = 1.5;
uniform float look_gold_value_compat = 0.8;
uniform float look_verge_value_green = 0.6;
uniform float look_verge_value_earth = 0.8;
uniform float look_verge_saturation = 1.08;
uniform float look_verge_green_red = 0.9;
uniform float look_verge_fine_metres = 4.0;
uniform float look_verge_fine = 0.12;
// How much of its texture's grain the verge keeps around its mean colour.
uniform float look_verge_grain = 1.0;
// How much of the texture's grain a steep face keeps (1: as much as flat ground). A planar-mapped detail
// tile streaks down a cliff (sw_isle's gorge walls); a region may calm it there (ground.verge_grain_steep).
uniform float look_verge_grain_steep = 1.0;
// How much of the steep-face rock layer's grain it keeps (LookProfile.ROCK_FACE_GRAIN).
uniform float look_rock_grain = 1.0;
uniform float look_variation_metres = 16.0;
uniform float look_variation = 0.2;
uniform float look_variation_hue = 0.06;
uniform float look_path_variation_share = 0.35;
uniform vec2 look_slope_up = vec2(0.94, 0.62);
uniform float look_slope_shade = 0.72;
// Where the sun is, across the ground (a unit xz vector towards it; zero when
// unknown): a bank turned towards it is spared the slope shade, as the sun
// lights it already. Shaded regardless, a sunlit terrace bank at wh_garden
// drew a straight dark band (93 against 109) where develop drew it brighter.
uniform vec2 look_sun_heading = vec2(0.0);
// The terrain's worn-road colour is road only on ground at least this level
// (world-up normal component, fading from x to y): the exporter's road tint
// bleeds up the cliff faces beside a lane, and painted as road it drew pale
// gravel blotches up the Whitehorn crags at gm_border_wh.
uniform vec2 look_road_slope = vec2(0.72, 0.84);

// The region's border, where its trims above fade into its neighbours'
// (LookBorders, LookProfile.BORDER_*): up to 32 segments in continent space
// (a.x, a.z, b.x, b.z), each oriented with this region on its left, and the
// neighbour (0-3) each belongs to; and each neighbour's own trims. None away
// from a border and off the continent.
uniform vec4 look_border_segments[32];
uniform float look_border_neighbour[32];
uniform int look_border_count = 0;
uniform float look_border_feather = 24.0;
uniform float look_border_path_luma[4];
uniform vec3 look_border_path_tint[4];
uniform float look_border_path_chroma[4];
// verge_value_green, verge_value_earth, verge_saturation, verge_green_red
uniform vec4 look_border_verge[4];

// 0 paints; 1-4 are the debug views (see look_debug_colour).
uniform int look_debug = 0;
// 0 terrain, 1 biome blend, 2 authored patch, 3 walk deck. Only for debug.
uniform int look_class = 0;

float look_luma(vec3 colour) {
	return dot(colour, vec3(0.2126, 0.7152, 0.0722));
}

// Dave Hoskins' sine-free hash: stable at continent coordinates in the
// thousands of metres, where fract(sin()) bands.
float look_hash(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

float look_value_noise(vec2 p) {
	vec2 cell = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	float a = look_hash(cell);
	float b = look_hash(cell + vec2(1.0, 0.0));
	float c = look_hash(cell + vec2(0.0, 1.0));
	float d = look_hash(cell + vec2(1.0, 1.0));
	return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// Two octaves centred on zero, roughly -0.5..0.5.
float look_variation_at(vec2 xz) {
	vec2 p = xz / look_variation_metres;
	return 0.65 * look_value_noise(p)
		+ 0.35 * look_value_noise(p * 2.7 + vec2(13.1, 7.7)) - 0.5;
}

// The steep-face rock layer (LookProfile.ROCK_FACE_*; look_rock_metres 0:
// none, which every surface but opaque terrain and base ground keeps). The
// ground textures are mapped from above, so on a face steeper than about 50
// degrees one texel stretches down the slope into a long vertical streak
// (Landfall's bailey cliff, Spindle Hill, Boarsend's sea cliffs; map quality
// sweeps 2026-11-15). There the surface gives way to a rock face mapped from
// the side: projected along x and along z, each weighed by how far the face
// normal points that way, in continent metres. It is drawn as stone at the
// ground's own luminance (times look_rock_value), keeping look_rock_hue of its
// own grey hue and taking the rest from the ground's mean colour with any
// grass green taken out (look_rock_tone), and the paint gives it none of the
// verge's grass trims: recoloured to the ground's whole mean colour and then
// deepened and stripped of red as grass, Coilmere's Spindle Hill read dark
// olive (map polish 2026-11-16).
// look_rock_up: the world-up normal component where the rock begins (x) and
// where it is whole (y). look_rock_wobble: how far noise moves that threshold
// (x) and the noise's size in metres (y), so the rock's edge wanders across a
// bank instead of following one contour.
// look_rock_metres is the material's repeat (0 off: the surface's kind, its
// region's ground.rock_face 0 or a texture that did not load). rl_rock_face,
// a global (project.godot [shader_globals]), is the graphics quality's switch:
// 0 at LOW, 1 otherwise, set by LookGround.apply_quality. Every material reads
// it as it draws, so a root painted on a worker before a quality change, a
// parked or prewarmed root and a road composite all follow the change at once.
// The guard keeps road_ground's composed shader, which copies this include
// into its road half, to one declaration.
#ifndef RL_ROCK_FACE_GLOBAL
#define RL_ROCK_FACE_GLOBAL
global uniform float rl_rock_face;
#endif
uniform sampler2D look_rock_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float look_rock_metres = 0.0;
uniform vec2 look_rock_up = vec2(0.72, 0.6);
uniform vec2 look_rock_wobble = vec2(0.05, 7.0);
uniform float look_rock_hue = 0.5;
uniform float look_rock_value = 1.0;

// The rock face's repeat in metres as drawn: the material's, or 0 where the
// layer is off for it or at this quality.
float look_rock_repeat() {
	return look_rock_metres * rl_rock_face;
}

// How steep a pixel is on the rock layer's scale, whether or not the layer
// draws: 0 on anything less steep than look_rock_up.x, 1 from look_rock_up.y,
// the threshold wobbled as the rock's edge is. A forest floor gives way over
// it (painted_ground_surface.gdshaderinc look_rim_steep).
float look_rock_steep(vec3 world_normal, vec2 xz) {
	float up = abs(world_normal.y) + (look_value_noise(xz / look_rock_wobble.y
		+ vec2(23.1, 4.7)) - 0.5) * 2.0 * look_rock_wobble.x;
	return 1.0 - smoothstep(look_rock_up.y, look_rock_up.x, up);
}

// How much of a pixel is rock face: 0 on anything less steep than the
// threshold, and wherever the layer is off.
float look_rock_weight(vec3 world_normal, vec2 xz) {
	if (look_rock_repeat() <= 0.0) {
		return 0.0;
	}
	return look_rock_steep(world_normal, xz);
}

// What a blended patch keeps of its coverage on a steep face: 1 where
// `amount` is 0 (every surface but the forest floor) and on level ground, down
// to 1 - amount where the rock layer is whole.
float look_steep_keep(float amount, vec3 world_normal, vec2 xz) {
	return amount > 0.0 ? 1.0 - amount * look_rock_steep(world_normal, xz) : 1.0;
}

// How much of a terrain pixel is the exporter's worn road. The terrain mixes
// its biome colour towards the road colour and divides by 0.92, so a road
// vertex is the road colour over 0.92 and its verge fades into the biome.
float look_road_weight(vec3 vertex_colour) {
	vec3 road = look_road_colour / 0.92;
	float distance_from_road = length(vertex_colour - road) / length(road);
	return 1.0 - smoothstep(look_road_tolerance.x, look_road_tolerance.y,
		distance_from_road);
}

vec3 look_saturate(vec3 colour, float amount) {
	return max(mix(vec3(look_luma(colour)), colour, amount), vec3(0.0));
}

// The renderer's albedo encoding to linear, and back.
vec3 look_to_linear(vec3 colour) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	colour = max(colour, vec3(0.0));
	return mix(pow((colour + vec3(0.055)) * (1.0 / 1.055), vec3(2.4)),
		colour * (1.0 / 12.92), lessThan(colour, vec3(0.04045)));
#else
	return colour;
#endif
}

vec3 look_from_linear(vec3 colour) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	colour = clamp(colour, vec3(0.0), vec3(1.0));
	return mix(vec3(1.055) * pow(colour, vec3(1.0 / 2.4)) - vec3(0.055),
		colour * 12.92, lessThan(colour, vec3(0.0031308)));
#else
	return clamp(colour, vec3(0.0), vec3(1.0));
#endif
}

// How much chroma a painted tint needs on this renderer to land where it
// lands in Forward+ (see LookProfile.COMPAT_CHROMA).
float look_renderer_chroma() {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	return look_compat_chroma;
#else
	return 1.0;
#endif
}

// Hue in degrees and saturation of a linear colour as it would display, so a
// window like the gold one reads the same as a colour picker.
vec2 look_display_hue(vec3 linear_colour) {
	vec3 c = pow(clamp(linear_colour, vec3(0.0), vec3(1.0)), vec3(1.0 / 2.2));
	float high = max(c.r, max(c.g, c.b));
	float low = min(c.r, min(c.g, c.b));
	float range = high - low;
	float hue = 0.0;
	if (range > 0.00001) {
		if (high == c.r) {
			hue = mod((c.g - c.b) / range, 6.0);
		} else if (high == c.g) {
			hue = (c.b - c.r) / range + 2.0;
		} else {
			hue = (c.r - c.g) / range + 4.0;
		}
	}
	return vec2(hue * 60.0, high > 0.0 ? range / high : 0.0);
}

// A painted tint as linear albedo of luminance 1: `display_tint` (sRGB) with
// its chroma scaled by `chroma` as a colour picker would, around its own grey.
// Scaled in linear light instead, a tint that is already strong there lost
// its blue channel at 1.25 and went orange.
vec3 look_tint(vec3 display_tint, float chroma) {
	vec3 display = max(mix(vec3(look_luma(display_tint)), display_tint, chroma), vec3(0.0));
	vec3 linear_tint = pow(display, vec3(2.2));
	return linear_tint / max(look_luma(linear_tint), 0.0001);
}

// How green-dominant a colour is: grass however pale, not olive or earth, and
// not snow. Green has to lead blue as well as red: led by red alone, the
// bluish-white snow crust (linear 0.47, 0.57, 0.76 under Whitehorn's tint)
// counted as grass and was deepened and stripped of red like it, pale
// cyan-grey snow at luminance 174-176 against develop's 236-242.
float look_green(vec3 colour) {
	return smoothstep(0.02, 0.12, (colour.g - max(colour.r, colour.b)) / max(colour.g, 0.0001));
}

// The steep-face rock's mean colour as drawn on ground whose mean colour is
// `ground` (linear, after tint and vertex colour): stone at the ground's
// luminance times look_rock_value, keeping look_rock_hue of the rock
// texture's own hue (`face_mean`) and taking the rest from the ground's hue
// with its grass green turned to grey (look_green), so Landfall's tan cliffs
// stay a warm stone and Coilmere's green hills grow grey ones.
vec3 look_rock_tone(vec3 ground, vec3 face_mean) {
	float luma = max(look_luma(ground), 0.0001);
	vec3 ground_hue = mix(ground / luma, vec3(1.0), look_green(ground));
	vec3 own_hue = face_mean / max(look_luma(face_mean), 0.0001);
	return mix(ground_hue, own_hue, look_rock_hue) * luma * look_rock_value;
}

// The albedo with the rock face laid over it where the face is steep, and in
// .a how much of it is rock. `albedo` and `reference` are the surface's own
// albedo and mean colour after its tint and vertex colour, `position` the
// continent position in metres. On rock the reference becomes the stone's
// (look_rock_tone), so the paint classes and trims it as stone, not grass.
// Level ground returns `albedo` and `reference` untouched and samples
// nothing. The gradients are taken before the steepness test, where the whole
// quad runs, and handed to textureGrad: the samples are made only on steep
// pixels.
vec4 look_rock_layer(vec3 albedo, inout vec3 reference, vec3 world_normal, vec3 position) {
	float metres = look_rock_repeat();
	if (metres <= 0.0) {
		return vec4(albedo, 0.0);
	}
	vec3 p = position / metres;
	vec3 p_dx = dFdx(p);
	vec3 p_dy = dFdy(p);
	float rock = look_rock_weight(world_normal, position.xz);
	if (rock <= 0.0) {
		return vec4(albedo, 0.0);
	}
	// Each side projection by how far the face points along its axis,
	// sharpened so a corner turns over a narrow band.
	vec2 sides = pow(abs(world_normal.xz), vec2(4.0));
	sides /= max(sides.x + sides.y, 0.0001);
	vec3 face = vec3(0.0);
	float taken = 0.0;
	if (sides.x > 0.01) {
		face += sides.x * textureGrad(look_rock_texture, vec2(p.z, -p.y),
			vec2(p_dx.z, -p_dx.y), vec2(p_dy.z, -p_dy.y)).rgb;
		taken += sides.x;
	}
	if (sides.y > 0.01) {
		face += sides.y * textureGrad(look_rock_texture, vec2(p.x, -p.y) + vec2(0.37, 0.61),
			vec2(p_dx.x, -p_dx.y), vec2(p_dy.x, -p_dy.y)).rgb;
		taken += sides.y;
	}
	face /= max(taken, 0.0001);
	vec3 face_mean = max(textureLod(look_rock_texture, vec2(0.5), 16.0).rgb, vec3(0.02));
	vec3 stone = look_rock_tone(reference, face_mean);
	reference = mix(reference, stone, rock);
	return vec4(mix(albedo, face * stone / face_mean, rock), rock);
}

// How far inside the pale paving a continent position is, 0..1 over
// look_paving_inset metres in from the paving's edge.
float look_paving_at(vec2 xz) {
	float paving = 0.0;
	for (int index = 0; index < 8; index++) {
		if (index >= look_paving_count) {
			break;
		}
		vec4 rect = look_paving_rects[index];
		vec2 inside = min(xz - rect.xy, rect.zw - xz);
		paving = max(paving, smoothstep(0.0, look_paving_inset, min(inside.x, inside.y)));
	}
	return paving;
}

// How much of each neighbour's trims (0-3) the paint takes at a continent
// position: per neighbour, 1 - smoothstep(-feather, feather, the signed
// distance to its border, positive on this region's side), scaled down
// together where they add up to more than 1. The neighbour's own material
// sees the same segments reversed, so the two meet exactly (LookBorders).
vec4 look_border_weights(vec2 xz) {
	float best[4] = float[4](1e9, 1e9, 1e9, 1e9);
	float side[4] = float[4](1.0, 1.0, 1.0, 1.0);
	for (int index = 0; index < 32; index++) {
		if (index >= look_border_count) {
			break;
		}
		vec4 segment = look_border_segments[index];
		vec2 a = segment.xy;
		vec2 ab = segment.zw - a;
		vec2 ap = xz - a;
		float t = clamp(dot(ap, ab) / max(dot(ab, ab), 0.000001), 0.0, 1.0);
		float gap = length(ap - ab * t);
		int slot = clamp(int(look_border_neighbour[index] + 0.5), 0, 3);
		if (gap < best[slot]) {
			best[slot] = gap;
			side[slot] = (ab.x * ap.y - ab.y * ap.x) >= 0.0 ? 1.0 : -1.0;
		}
	}
	float taken[4] = float[4](0.0, 0.0, 0.0, 0.0);
	for (int slot = 0; slot < 4; slot++) {
		if (best[slot] < 1e8) {
			taken[slot] = 1.0 - smoothstep(-look_border_feather, look_border_feather,
				side[slot] * best[slot]);
		}
	}
	vec4 weights = vec4(taken[0], taken[1], taken[2], taken[3]);
	float total = weights.x + weights.y + weights.z + weights.w;
	return total > 1.0 ? weights / total : weights;
}

// The weights look_paint uses (path, yard, pale), for the debug views too.
// `reference` is the surface's mean albedo, linear: classing and lifting by
// the mean rather than by each texel keeps the texture's own grain.
vec3 look_weights(vec3 reference, vec3 vertex_colour, float up) {
	float luma = look_luma(reference);
	float road = look_road_detect > 0.0 ? look_road_weight(vertex_colour)
		* smoothstep(look_road_slope.x, look_road_slope.y, up) : 0.0;
	float path = max(look_path_force, road);
	float green = look_green(reference);
	float pale = smoothstep(look_pale_luma.x, look_pale_luma.y, luma) * (1.0 - green)
		* look_pale;
	float yard = look_yard * (1.0 - green);
	return vec3(path, yard, pale);
}

// albedo: the renderer's albedo after texture, tint and vertex colour.
// reference: the same from the texture's smallest mip (its mean colour), or
// the albedo itself where there is no single texture to average.
// vertex_colour: the raw vertex colour (only the terrain reads it).
// xz: continent-space position in metres. world_normal: the surface normal
// in world space (its up component, and which way a bank faces).
// rock: how much of the pixel is the steep-face rock layer
// (painted_ground_surface.gdshaderinc), which keeps look_rock_grain of its
// grain where the planar texture's streaks keep only look_verge_grain_steep.
vec3 look_paint_rock(vec3 albedo, vec3 reference, vec3 vertex_colour, vec2 xz,
		vec3 world_normal, float rock) {
	float up = abs(world_normal.y);
	albedo = look_to_linear(albedo);
	reference = look_to_linear(reference);
	vec3 weights = look_weights(reference, vertex_colour, up);
	float path = weights.x;
	float yard = weights.y;
	float pale = weights.z;
	float luma = max(look_luma(reference), 0.0001);

	// This region's trims, faded into its neighbours' near a border.
	vec4 border = look_border_count > 0 ? look_border_weights(xz) : vec4(0.0);
	float own = 1.0 - (border.x + border.y + border.z + border.w);
	float path_luma = look_path_luma * own + dot(border, vec4(look_border_path_luma[0],
		look_border_path_luma[1], look_border_path_luma[2], look_border_path_luma[3]));
	vec3 path_tint = look_path_tint * own + look_border_path_tint[0] * border.x
		+ look_border_path_tint[1] * border.y + look_border_path_tint[2] * border.z
		+ look_border_path_tint[3] * border.w;
	float path_chroma = look_path_chroma * own + dot(border, vec4(look_border_path_chroma[0],
		look_border_path_chroma[1], look_border_path_chroma[2], look_border_path_chroma[3]));
	vec4 verge_trims = vec4(look_verge_value_green, look_verge_value_earth,
			look_verge_saturation, look_verge_green_red) * own
		+ look_border_verge[0] * border.x + look_border_verge[1] * border.y
		+ look_border_verge[2] * border.z + look_border_verge[3] * border.w;

	// A steep face keeps look_verge_grain_steep of its texture's grain, and
	// look_rock_grain of the rock face's that replaces it there.
	float steep_grain = rock > 0.0 ? mix(look_verge_grain_steep, look_rock_grain, rock)
		: look_verge_grain_steep;
	vec3 grained = mix(reference, albedo, mix(steep_grain, 1.0, smoothstep(0.55, 0.8, up)));

	// Verge: deeper and a little richer by hue, with a painted mottle. The
	// rock face is stone: it takes the earth's value and none of the grass's
	// deepening or lost red, even where it is only part of the pixel.
	float verge_green = look_green(reference) * (1.0 - rock);
	float verge_scale = mix(verge_trims.y, verge_trims.x, verge_green);
	vec3 verge = look_saturate(mix(reference, grained, look_verge_grain) * verge_scale,
		verge_trims.z);
	verge.r *= mix(1.0, verge_trims.w, verge_green);
	verge *= 1.0 + (look_value_noise(xz / look_verge_fine_metres + vec2(5.3, 2.1))
		- 0.5) * 2.0 * look_verge_fine;
	vec3 colour = mix(verge, grained, pale);

	// Gold, a little darker and richer so the tone curve keeps it gold. Told
	// by hue and chroma, not by the pale weight: Lantern Reach's trail sits
	// between the pale luminances and was only half pale.
	vec2 hue = look_display_hue(reference);
	float gold = look_pale * smoothstep(0.06, 0.12, luma)
		* smoothstep(look_gold_hue.x - 4.0, look_gold_hue.x, hue.x)
		* (1.0 - smoothstep(look_gold_hue.y, look_gold_hue.y + 4.0, hue.x))
		* smoothstep(look_gold_saturation - 0.06, look_gold_saturation, hue.y);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	float gold_chroma = look_gold_chroma_compat;
	float gold_value = look_gold_value_compat;
#else
	float gold_chroma = look_gold_chroma;
	float gold_value = look_gold_value;
#endif
	colour = mix(colour, look_saturate(albedo * gold_value, gold_chroma), gold);

	// Yards keep their own colour and lift a little.
	float yard_lift = clamp(look_yard_luma / luma, 1.0, look_yard_lift_max);
	colour = mix(colour, look_saturate(albedo * yard_lift, look_yard_saturation), yard);
	vec3 kept = max(reference + (albedo - reference) * look_keep_grain, vec3(0.0));
	colour = mix(colour, look_saturate(kept * look_keep_tint, look_keep_chroma), look_keep);

	// Paths: a set value and hue, the texture's grain, a fine mottle; darker
	// than the paving where they run through it. A yard inside the paving (a
	// patch of bare soil in the square) is worn into the same cobble, where
	// on its own it read as a stain.
	float paving = look_paving_at(xz);
	float target = min(mix(path_luma, look_paving_luma, paving),
		luma * look_path_lift_max);
	float grain = pow(max(look_luma(albedo) / luma, 0.0), look_path_detail);
	float fine = 1.0 + (look_value_noise(xz / look_path_fine_metres + vec2(3.7, 1.9))
		- 0.5) * 2.0 * look_path_fine;
	vec3 tint = mix(look_tint(path_tint, path_chroma * look_renderer_chroma()),
		look_tint(look_paving_tint, look_paving_chroma * look_renderer_chroma()), paving);
	colour = mix(colour, tint * target * grain * fine, max(path, yard * paving));

	float variation = look_variation_at(xz)
		* mix(1.0, look_path_variation_share, max(path, max(yard, pale) * 0.5));
	colour *= 1.0 + variation * 2.0 * look_variation;
	colour *= vec3(1.0) + vec3(variation, 0.0, -variation) * 2.0 * look_variation_hue;
	float level = smoothstep(look_slope_up.y, look_slope_up.x, up);
	float sunward = clamp(dot(world_normal.xz, look_sun_heading)
		/ max(length(world_normal.xz), 0.0001), 0.0, 1.0);
	colour *= mix(look_slope_shade, 1.0, max(level, sunward));
	return look_from_linear(look_saturate(colour * look_surface_tint, look_local_saturation));
}

// look_paint_rock without the rock layer: the biome blend's splice
// (LookGround.BIOME_PAINTED_LINE) and any surface without it.
vec3 look_paint(vec3 albedo, vec3 reference, vec3 vertex_colour, vec2 xz, vec3 world_normal) {
	return look_paint_rock(albedo, reference, vertex_colour, xz, world_normal, 0.0);
}

// What the debug views draw as emission (ALBEDO is black): 1, the class as
// a flat colour (terrain red, biome blend green, patch blue, walk deck
// magenta); 2, the weights, path in red, yard in green and pale in blue;
// 3, the reference luminance in steps (red above 0.08, green above 0.12,
// blue above 0.2); 4, the border blend: how much of the neighbours' trims the
// paint takes in red (a half on the border line), over a faint blue on every
// material that was handed a border.
vec3 look_debug_colour(vec3 reference, vec3 vertex_colour, vec2 xz) {
	if (look_debug == 4) {
		vec4 border = look_border_count > 0 ? look_border_weights(xz) : vec4(0.0);
		return vec3(border.x + border.y + border.z + border.w, 0.0,
			look_border_count > 0 ? 0.15 : 0.0);
	}
	reference = look_to_linear(reference);
	if (look_debug == 2) {
		return look_weights(reference, vertex_colour, 1.0) * 0.5;
	}
	if (look_debug == 3) {
		float luma = look_luma(reference);
		return vec3(luma > 0.08 ? 0.5 : 0.0, luma > 0.12 ? 0.5 : 0.0,
			luma > 0.2 ? 0.5 : 0.0);
	}
	return look_class == 0 ? vec3(0.5, 0.0, 0.0)
		: look_class == 1 ? vec3(0.0, 0.5, 0.0)
		: look_class == 2 ? vec3(0.0, 0.0, 0.5)
		: vec3(0.5, 0.0, 0.5);
}
