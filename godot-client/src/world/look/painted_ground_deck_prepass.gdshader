// Look pass layer L2: the depth pre-pass of painted_ground_deck.gdshader for
// the Mobile renderer, which runs none of its own (LookGround.mobile_prepass
// chains it in as the deck's next pass there). Opaque and unshaded: it keeps
// the fragments Forward+'s pre-pass keeps and writes their depth, and the
// blended deck draws over them. See painted_ground_surface.gdshaderinc.
shader_type spatial;
render_mode unshaded, cull_disabled, fog_disabled;

#define LOOK_GROUND_ALPHA
#define LOOK_GROUND_EDGE_BAND
#define LOOK_GROUND_PREPASS
#include "res://src/world/look/painted_ground_surface.gdshaderinc"
