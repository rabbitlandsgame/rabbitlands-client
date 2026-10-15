// Look pass layer L3: a painted crown drawn alpha-cut and two-sided, as an
// authored tree's leaf cards import. See painted_foliage_body.gdshaderinc.
shader_type spatial;
render_mode cull_disabled;

#define LOOK_FOLIAGE_CUTOUT
#include "res://src/world/look/painted_foliage_body.gdshaderinc"
