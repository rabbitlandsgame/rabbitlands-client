// Look pass: a one-sided StandardMaterial3D at rest with its chroma scaled (the
// signature-colour layer, LookFoliage.keep_chroma). See
// look_faded_standard.gdshaderinc.
shader_type spatial;
render_mode cull_back;

#define LOOK_STANDARD_RESTING
#include "res://src/world/look/look_faded_standard.gdshaderinc"
