// The per-actor values of every RL head shader, as instance uniforms, so the
// materials themselves are shared by every actor wearing the same head.
//
// Every RL shader includes this one block, unused entries and all. One
// MeshInstance3D carries the skin, eye, lash and brow materials together, and
// Godot keeps one slot per instance uniform name for the whole instance: two
// shaders declaring `hair_color` in different positions would disagree on its
// slot, and only the first would see the colour. So a new entry goes at the
// end of this list, never between two existing ones, and no RL shader
// declares an instance uniform of its own. (Godot allows 16 per shader, and
// all 16 are used: a new per-face value must be packed into an existing one,
// as eye_style_paint packs two, or be geometry.)
//
// The Compatibility renderer keeps instance uniforms in one global buffer of
// 4096 items, 16 for each mesh instance that uses any, which a crowd of RL
// heads ran out of between 40 and 160 Humans. There RLHeadLibrary compiles
// each RL shader with RL_MATERIAL_VALUES defined before this include: the same
// values become ordinary material uniforms, set on per-face copies of the
// shared materials (RLHeadLibrary.face_material); nothing draws differently.
#ifdef RL_MATERIAL_VALUES
#define RL_VALUE uniform
#else
#define RL_VALUE instance uniform
#endif
RL_VALUE vec4 skin_color : source_color = vec4(0.85, 0.66, 0.55, 1.0);
RL_VALUE vec4 lip_tint : source_color = vec4(0.75, 0.45, 0.42, 1.0);
RL_VALUE vec4 brow_color : source_color = vec4(0.2, 0.12, 0.07, 1.0);
RL_VALUE vec4 hair_color : source_color = vec4(0.25, 0.14, 0.08, 1.0);
RL_VALUE vec4 eye_color : source_color = vec4(0.3, 0.45, 0.6, 1.0);
RL_VALUE vec2 eye_look = vec2(0.0);
RL_VALUE float freckles = 0.0;
RL_VALUE float liner = 0.0;
RL_VALUE float stubble = 0.0;
// How much hair colour shows on the scalp and hairline (0 bald, about 0.6 under hair).
RL_VALUE float hairline = 0.0;
// Brows: which painted style (0 arched, 1 straight, 2 soft, 3 angled; a
// fraction blends the two neighbours), and how thick, from -1 to 1.
RL_VALUE float brow_style = 2.0;
RL_VALUE float brow_thickness = 0.0;
// How far the liner flicks out past the outer corner of the eye, 0 to 1.
RL_VALUE float liner_wing = 0.0;
// RL hair's fine detail, 0 to 1 (RLHeadAppearance.hair_detail / 100): a hair
// fragment whose keep level (COLOR.a) is below 1 - hair_detail is dropped
// (rl_hair.gdshader). 0.5, the default and what beards keep, shows the
// hairstyle as authored.
RL_VALUE float hair_detail = 0.5;
// The stylised eye, derived from identity controls (the eye_style control's
// `uniforms`; RLHeadRig.control_uniforms), two values in one slot:
//   x `iris_scale`: the iris and pupil drawn this many times their painted size
//     on the eyeball (1 as authored), the sclera round them drawn in to make room
//     (rl_eye);
//   y `eye_paint`, 0 to 1: a heavier upper lash line and liner (rl_skin) and the
//     upper lid's shadow over the top of the iris (rl_eye).
RL_VALUE vec2 eye_style_paint = vec2(1.0, 0.0);
// The lids' motion from RLFaceExpression: x, y how far the left and right eye are
// closed by a blink, z the squint weight. A closing lid stretches the painted lash
// line and liner over itself, so the line fades out with the blink, and the
// stylised liner's extra width gives way while the lids come down (rl_skin).
RL_VALUE vec4 lid_closure = vec4(0.0);
#undef RL_VALUE
