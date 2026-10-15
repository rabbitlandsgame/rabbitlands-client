// Look pass layer L3: painted_foliage_cutout.gdshader while OccluderFade
// fades it, dithered by look_fade. See painted_foliage_body.gdshaderinc.
shader_type spatial;
render_mode cull_disabled;

#define LOOK_FOLIAGE_CUTOUT
#define LOOK_FOLIAGE_FADE
#include "res://src/world/look/painted_foliage_body.gdshaderinc"
