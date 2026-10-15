// Look pass layer L3: painted_foliage.gdshader drawn back-face culled, as a
// closed kit mesh imports whose material is single-sided (Sunmane's steppe
// trees and shrubs, sun_foliage). See painted_foliage_body.gdshaderinc.
shader_type spatial;
render_mode cull_back;

#include "res://src/world/look/painted_foliage_body.gdshaderinc"
