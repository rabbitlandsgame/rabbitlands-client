// Look pass layer L2: painted ground for a blended source drawn with an
// opaque depth pre-pass and no culling (the authored ground patches; walk
// decks use painted_ground_deck.gdshader). See
// painted_ground_surface.gdshaderinc.
shader_type spatial;
render_mode blend_mix, depth_prepass_alpha, cull_disabled;

#define LOOK_GROUND_ALPHA
#include "res://src/world/look/painted_ground_surface.gdshaderinc"
