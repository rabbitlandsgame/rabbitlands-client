// The per-actor values of every RL head shader, as instance uniforms, so the
// materials themselves are shared by every actor wearing the same head.
//
// Every RL shader includes this one block, unused entries and all. One
// MeshInstance3D carries the skin, eye, lash and brow materials together, and
// Godot keeps one slot per instance uniform name for the whole instance: two
// shaders declaring `hair_color` in different positions would disagree on its
// slot, and only the first would see the colour.
instance uniform vec4 skin_color : source_color = vec4(0.85, 0.66, 0.55, 1.0);
instance uniform vec4 lip_tint : source_color = vec4(0.75, 0.45, 0.42, 1.0);
instance uniform vec4 brow_color : source_color = vec4(0.2, 0.12, 0.07, 1.0);
instance uniform vec4 hair_color : source_color = vec4(0.25, 0.14, 0.08, 1.0);
instance uniform vec4 eye_color : source_color = vec4(0.3, 0.45, 0.6, 1.0);
instance uniform vec2 eye_look = vec2(0.0);
instance uniform float freckles = 0.0;
instance uniform float liner = 0.0;
instance uniform float stubble = 0.0;
// How much hair colour shows on the scalp and hairline (0 bald, about 0.6 under hair).
instance uniform float hairline = 0.0;
// Brows: which painted style (0 arched, 1 straight, 2 soft, 3 angled; a
// fraction blends the two neighbours), and how thick, from -1 to 1.
instance uniform float brow_style = 2.0;
instance uniform float brow_thickness = 0.0;
// How far the liner flicks out past the outer corner of the eye, 0 to 1.
instance uniform float liner_wing = 0.0;
