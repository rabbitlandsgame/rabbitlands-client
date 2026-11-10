// Fog of war over a descent floor (descent_fog.gd). A screen quad that darkens
// every pixel by where the surface it shows stands on the floor grid: clear
// over revealed cells, fading over the first `soft_cells` beyond them, then
// `strength` dark. The surface's position comes from the depth buffer, so
// unrevealed ground near the camera never covers revealed ground behind it.
shader_type spatial;
render_mode unshaded, fog_disabled, shadows_disabled, depth_draw_never, depth_test_disabled, cull_disabled, blend_mix;

uniform sampler2D depth_texture : hint_depth_texture, filter_nearest, repeat_disable;
// One texel a cell, x = cell column, y = cell row; red 1 where revealed.
uniform sampler2D revealed_cells : filter_nearest, repeat_disable;
// Godot x/z of the corner of cell (0, 0) nearest the grid's origin.
uniform vec2 grid_origin;
// Rows of the inverse of the cell frame: cell = (dot(to_cell_x, d), dot(to_cell_y, d))
// for d = position.xz - grid_origin.
uniform vec2 to_cell_x;
uniform vec2 to_cell_y;
uniform ivec2 grid_cells;
uniform float soft_cells = 1.5;
uniform float strength = 0.94;

bool revealed(ivec2 cell) {
	if (cell.x < 0 || cell.y < 0 || cell.x >= grid_cells.x || cell.y >= grid_cells.y) {
		return false;
	}
	return texelFetch(revealed_cells, cell, 0).r > 0.5;
}

void vertex() {
	POSITION = vec4(VERTEX.xy, 1.0, 1.0);
}

void fragment() {
	float depth = textureLod(depth_texture, SCREEN_UV, 0.0).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec3 ndc = vec3(SCREEN_UV, depth) * 2.0 - 1.0;
#else
	vec3 ndc = vec3(SCREEN_UV * 2.0 - 1.0, depth);
#endif
	vec4 world = INV_VIEW_MATRIX * INV_PROJECTION_MATRIX * vec4(ndc, 1.0);
	vec2 d = world.xz / world.w - grid_origin;
	vec2 g = vec2(dot(to_cell_x, d), dot(to_cell_y, d));
	ivec2 cell = ivec2(floor(g));
	// Distance, in cells, from this point to the nearest revealed cell within
	// two cells (enough for a ramp up to two cells wide).
	float nearest = 3.0;
	for (int dy = -2; dy <= 2; dy++) {
		for (int dx = -2; dx <= 2; dx++) {
			ivec2 n = cell + ivec2(dx, dy);
			if (revealed(n)) {
				vec2 outside = max(vec2(n) - g, g - vec2(n + ivec2(1)));
				nearest = min(nearest, length(max(outside, vec2(0.0))));
			}
		}
	}
	ALBEDO = vec3(0.0);
	ALPHA = strength * smoothstep(0.0, soft_cells, nearest);
}
