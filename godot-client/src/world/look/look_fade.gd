class_name LookFade
extends RefCounted
## Look pass layer L3: occluders open a hole round the player instead of
## blending. Used by OccluderFade only when LookProfile.enabled(); with the
## pass off OccluderFade blends exactly as it does on develop.
##
## OccluderFade fades an obstacle by swapping in a copy of its material that
## alpha-blends towards FADED_ALPHA. A blended surface stops writing depth, so
## a faded crown's hundreds of overlapping leaf cards sort against each other
## and against the ground and read as a brown smear, and a roof loses its own
## shading under the blend. The pass first dithered the whole occluder
## instead, a one-pixel screen-door at 35 % coverage, which read as a
## crosshatched window screen over up to a fifth of the frame. Now the
## occluder stays solid, lit and depth-tested as always, and a round hole
## with a dithered rim opens where it covers the player
## (look_fade_hole.gdshaderinc), as the reference frames' crown fade cuts one.
## The fade's timing is OccluderFade's, unchanged: it opens the hole.
##
## - A painted look material (LookFoliage's crowns, LookGround's blended
##   ground) names its dithered variant in FADED_SHADER_META; the copy
##   switches to that shader and OccluderFade opens its hole.
## - A StandardMaterial3D is copied into look_faded_standard.gdshader, which
##   draws what the engine would draw for it and cuts the hole. The
##   engine's own dither for it, hashed alpha, is ignored by the compatibility
##   renderer (its copies drew fully opaque there). A material using a feature
##   that shader does not reproduce keeps develop's blended copy.
## - Any other ShaderMaterial is left solid, as on develop.
##
## Every one of them cuts the same hole, and only the faded copies carry its
## discard, so a resting surface keeps the engine's early depth test.
##
## How an occluder fades is decided per occluder as its fade begins (`mode_of`):
##
## - HOLE: a painted crown, and a mid-sized prop, roof or wall that covers
##   little of the view - a round hole opens round the player, the rest stays.
## - VANISH: the dithered copy dissolves the whole mesh as the fade opens and
##   draws none of it once open. For what a hole cannot leave readable: a roof
##   or tent whose footprint holds the player (a Sunmane yurt drew a straw
##   cone over them with a porthole in it), a thin post, pillar, beam or wall
##   (Whitehorn's gate pillars and Verdant's hub gate kept a solid bar across
##   the frame), and anything that covers more than FADE_VANISH_COVERAGE of
##   the view (the Grey Moors' turf roof, a quarter of the frame, near-black
##   round a hole). Blended instead, as develop does, a roof over a room read
##   as a grey smear of the room (aw_coppice); gone, the room reads.
## - BLEND: develop's own fade (OccluderFade's alpha-blended copies), for
##   interiors (`bind`), water (`is_water`), and anything wider across the
##   ground than FADE_SOLID_MAX_METRES, or part of a structure that is (a
##   giant dome's pieces).
##
## A faded copy would cast its hole into its shadow too, so while a mesh fades
## by its hole or vanishes it stops casting. A wall or a roof that keeps its
## hole hands its shadow to a shadow-only twin with its resting materials,
## because a room lighting up under a roof the viewer still sees reads as a
## bug; one that vanishes casts none, as develop's blended copies cast none. A crown casts none, as develop's
## blended copies cast none: the twin held a giant canopy's whole shadow over
## the player and took the deep grove from luminance 80 to 64 (53 in Forward+),
## the darkest frame of the pass, where walking under a tree on develop lights
## the ground. A blended occluder keeps develop's shadow exactly: a twin there
## laid the Sunmane gauntlet's canyon walls' full shadows beside the player as
## hard dark quads under walls the viewer sees as ghosts.
##
## The ground never fades. Develop has no walk collision on the continent's
## authored ground patches, so the patch a player stands on was indexed as an
## occluder and faded to glass under their feet; with the pass on, anything
## LookGround paints as ground is kept out of the index, as walk surfaces are.

const SHADER_STANDARD := preload("res://src/world/look/look_faded_standard.gdshader")
const SHADER_STANDARD_TWO_SIDED := preload("res://src/world/look/look_faded_standard_two_sided.gdshader")

## On a painted material: the Shader its faded copy switches to.
const FADED_SHADER_META := &"look_faded_shader"
## On a fading mesh: the cast_shadow setting to give back to it.
const SHADOW_META := &"look_fade_shadow"
const SHADOW_TWIN_NAME := &"LookFadeShadow"
## The uniform a dithered material records its opacity in.
const FADE_PARAMETER := &"look_fade"
## The uniforms that open its hole, and centre it.
const OPEN_PARAMETER := &"look_fade_open"
const FOCUS_PARAMETER := &"look_fade_focus"
## The uniform that dissolves the whole mesh rather than a hole (Mode.VANISH).
const WHOLE_PARAMETER := &"look_fade_whole"
## On a fading mesh: the Mode its fade was given when it began (`hold_shadow`
## decides, `dither_copy` reads, `release_shadow` forgets).
const MODE_META := &"look_fade_mode"
## ELORIA_LOOK_FADE_DEBUG=1 prints every fade's mode and what decided it, and
## the mesh's first material, for finding what an occluder in a frame is.
const DEBUG_VARIABLE := "ELORIA_LOOK_FADE_DEBUG"

enum Mode { HOLE, VANISH, BLEND }

## Where the holes are centred this frame: the local player's chest, handed
## over by OccluderFade.update before it animates its fades.
static var focus := Vector3.ZERO

## True while the bound map is an interior (see `bind`): every occluder then
## fades as develop fades it.
static var blend_only := false

## Called as each map binds. On an interior - a map that declares no enabled
## sun, or any map whose asset names an interiorClass (a secrets tower, a
## gauntlet, the sunlit insides) - every occluder blends as on develop. The
## hole was made for crowns and props seen from above the open ground; a
## room's ceiling covers the camera's whole view of the room, so kept solid
## round a hole it blacked out five of the six Four Gates interiors but for a
## disc round the player (near-black 8 % to 52 % in the stormglass house),
## and the secrets towers' domes stayed a dark cap.
static func bind(manifest: WorldManifest) -> void:
	blend_only = manifest != null and (not LookGround.outdoor(manifest)
		or not str((manifest.data.get("asset", {}) as Dictionary).get("interiorClass", "")).is_empty())
	hole_words = [] if manifest == null else LookProfile.hole_words(LookGround.region_of(manifest))

## The bound map's landmarks that keep a hole rather than vanish (its region
## file's `props.hole_words`, contained in the occluding mesh's node name):
## sw_isle's palace keep vanished whole from its own town's view at the
## player's maximum zoom, and its west gatehouse left a curtain-wall stub and
## a floating floor slab while the player stood in the gate passage.
static var hole_words: Array = []

## True when an occluder fades by a dithered look copy (a hole, or vanishing)
## rather than by develop's blend: see `mode_of`.
static func keeps_hole(node: MeshInstance3D) -> bool:
	return mode_of(node) != Mode.BLEND

## How `node` fades (see the header), as decided when its fade began, or now:
##
## - BLEND on an interior (`bind`), and for a mesh wider across the ground
##   than LookProfile.FADE_SOLID_MAX_METRES or part of a structure that is
##   (`assembly_width`): kept solid round the largest hole, Crownwater's giant
##   dome drew the player in a dark disc under an opaque cap.
## - HOLE for a painted crown whatever its size: a painted crown has no
##   blended copy (OccluderFade would leave it solid), its leaf cards would
##   sort into a smear if it had, and it never vanishes (a tree the player
##   walks under stays a tree). Camera distance alone never hides a crown.
## - VANISH for a mesh whose footprint holds the player under its top, a thin
##   one (LookProfile.FADE_THIN_METRES across, or a post or pillar at least
##   FADE_PILLAR_RATIO times as tall as it is wide), and one whose box covers
##   more than LookProfile.FADE_VANISH_COVERAGE of the view from `camera`
##   (the current camera when null).
## - HOLE for everything else: a cart, a lamp, a cottage beside the path.
##
## A mesh drawn by a look stand-in (a kept signature colour, a tree's trunk)
## that would blend dissolves instead, or keeps a hole if it is a trunk: a
## stand-in has no blended copy, and OccluderFade would leave it solid.
##
## A landmark the bound map's region names (`hole_words`) keeps a hole
## wherever it would vanish, unless it covers more than
## LookProfile.FADE_NAMED_HOLE_MAX_COVERAGE of the view: a town's keep or gate
## stays standing round the player instead of disappearing from its own view,
## but a wall that fills a low camera's frame still goes.
static func mode_of(node: MeshInstance3D, camera: Camera3D = null) -> Mode:
	if node != null and node.has_meta(MODE_META):
		return int(node.get_meta(MODE_META)) as Mode
	var mode := _mode(node, camera)
	# A look stand-in (a kept signature colour, a tree's trunk) has no blended
	# copy: OccluderFade would leave it solid. It dissolves instead, or keeps a
	# hole under its crown if it is a trunk.
	if mode == Mode.BLEND and node != null and _stands_in(node):
		mode = Mode.HOLE if LookFoliage.is_tree_wood(String(node.name)) else Mode.VANISH
	if mode == Mode.VANISH and node != null and keeps_named_hole(String(node.name)) 			and screen_coverage(world_box(node), camera if camera != null else _camera_of(node)) 				<= LookProfile.FADE_NAMED_HOLE_MAX_COVERAGE:
		return Mode.HOLE
	return mode

## True when `node_name` (a neighbour's preview copy's original name) holds
## one of the bound region's `hole_words`.
static func keeps_named_hole(node_name: String) -> bool:
	if hole_words.is_empty():
		return false
	if node_name.begins_with("StreamView_"):
		node_name = node_name.get_slice("__", 1)
	var lowered := node_name.to_lower()
	for word: Variant in hole_words:
		if lowered.contains(str(word)):
			return true
	return false

## True when one of `node`'s surfaces draws with a look stand-in that names
## its dithered variant.
static func _stands_in(node: MeshInstance3D) -> bool:
	if node.material_override != null:
		return node.material_override.has_meta(FADED_SHADER_META)
	var surfaces := 0 if node.mesh == null else node.mesh.get_surface_count()
	for surface: int in surfaces:
		var material := node.get_active_material(surface)
		if material is ShaderMaterial and material.has_meta(FADED_SHADER_META):
			return true
	return false

static func _mode(node: MeshInstance3D, camera: Camera3D) -> Mode:
	if blend_only or (node != null and is_water(node)):
		return Mode.BLEND
	if node == null or node.mesh == null or is_crown(node):
		return Mode.HOLE
	var box := world_box(node)
	if maxf(box.size.x, box.size.z) > LookProfile.FADE_SOLID_MAX_METRES \
			or assembly_width(node) > LookProfile.FADE_SOLID_MAX_METRES:
		return Mode.BLEND
	if over_focus(box) or thin(box) \
			or screen_coverage(box, camera if camera != null else _camera_of(node)) \
				> LookProfile.FADE_VANISH_COVERAGE:
		return Mode.VANISH
	return Mode.HOLE

## `node`'s bounds in world space (in its parent chain's space before it has
## joined the tree).
static func world_box(node: MeshInstance3D) -> AABB:
	if node == null or node.mesh == null:
		return AABB()
	var place := node.global_transform if node.is_inside_tree() else node.transform
	return place * node.mesh.get_aabb()

## The width across the ground of the structure `node` belongs to: the
## merged bounds of the meshes under its parent, when that parent is a
## landmark's own node (its name is not a map's or chunk's root and it holds
## at most LookProfile.FADE_ASSEMBLY_PIECES_MAX meshes); 0 otherwise. A giant
## dome is exported as a landmark node holding its shell's pieces, each far
## narrower than the dome.
static func assembly_width(node: MeshInstance3D) -> float:
	if node == null or not node.is_inside_tree():
		return 0.0
	var parent := node.get_parent() as Node3D
	if parent == null or parent.get_child_count() < 2 \
			or parent.get_child_count() > LookProfile.FADE_ASSEMBLY_PIECES_MAX:
		return 0.0
	var parent_name := String(parent.name)
	for prefix: String in LookProfile.FADE_ASSEMBLY_PREFIXES:
		if parent_name.begins_with(prefix):
			var merged := AABB()
			var first := true
			for child: Node in parent.get_children():
				var piece := child as MeshInstance3D
				if piece == null or piece.mesh == null:
					continue
				var box := world_box(piece)
				merged = box if first else merged.merge(box)
				first = false
			return 0.0 if first else maxf(merged.size.x, merged.size.z)
	return 0.0

## True when `box` stands over the player: its footprint (shrunk by
## FADE_OVER_INSET_METRES) holds the focus and its top is above the player's
## chest - a roof, a tent, an awning the player is under.
static func over_focus(box: AABB) -> bool:
	var inset := LookProfile.FADE_OVER_INSET_METRES
	return focus.x > box.position.x + inset and focus.x < box.end.x - inset \
		and focus.z > box.position.z + inset and focus.z < box.end.z - inset \
		and box.end.y > focus.y

## True for a thin occluder: a wall, a fence, a beam (at most FADE_THIN_METRES
## across one way), or a post, pillar or obelisk (FADE_PILLAR_RATIO times as
## tall as it is wide, and taller than FADE_PILLAR_METRES).
static func thin(box: AABB) -> bool:
	var narrow := minf(box.size.x, box.size.z)
	var wide := maxf(box.size.x, box.size.z)
	return narrow <= LookProfile.FADE_THIN_METRES \
		or (box.size.y >= wide * LookProfile.FADE_PILLAR_RATIO
			and box.size.y >= LookProfile.FADE_PILLAR_METRES)

## The share of `camera`'s view (0..1) that `box`'s projected bounds cover; 1
## when part of it is behind the camera, 0 without a camera.
static func screen_coverage(box: AABB, camera: Camera3D) -> float:
	if camera == null or not camera.is_inside_tree():
		return 0.0
	var view := camera.get_viewport().get_visible_rect().size
	if view.x <= 0.0 or view.y <= 0.0:
		return 0.0
	var low := Vector2(INF, INF)
	var high := Vector2(-INF, -INF)
	for corner: int in 8:
		var point := box.get_endpoint(corner)
		if camera.is_position_behind(point):
			return 1.0
		var on_screen := camera.unproject_position(point)
		low = low.min(on_screen)
		high = high.max(on_screen)
	low = low.clamp(Vector2.ZERO, view)
	high = high.clamp(Vector2.ZERO, view)
	return maxf(high.x - low.x, 0.0) * maxf(high.y - low.y, 0.0) / (view.x * view.y)

static func _camera_of(node: Node) -> Camera3D:
	if node == null or not node.is_inside_tree():
		return null
	return node.get_viewport().get_camera_3d()

## Decides `node`'s fade as it begins and keeps the answer until
## `release_shadow`, so its shadow and its materials agree.
static func _decide(node: MeshInstance3D) -> Mode:
	if node.has_meta(MODE_META):
		node.remove_meta(MODE_META)
	var mode := mode_of(node)
	node.set_meta(MODE_META, mode)
	if OS.get_environment(DEBUG_VARIABLE) == "1":
		_print_decision(node, mode)
	return mode

static func _print_decision(node: MeshInstance3D, mode: Mode) -> void:
	var box := world_box(node)
	var material := node.get_active_material(0) if node.mesh != null \
		and node.mesh.get_surface_count() > 0 else null
	var described := "none"
	if material is BaseMaterial3D:
		var standard := material as BaseMaterial3D
		var texture := standard.albedo_texture
		described = "%s albedo=%s texture=%s" % [standard.resource_name,
			standard.albedo_color.to_html(), "none" if texture == null
			else "%s %dx%d" % [texture.resource_path, texture.get_width(), texture.get_height()]]
	elif material != null:
		described = "%s %s" % [material.get_class(), material.resource_name]
	print("look_fade mode=%s node=%s parent=%s size=%s coverage=%.3f over=%s thin=%s crown=%s assembly=%.1f material=%s"
		% [Mode.keys()[mode], node.name, node.get_parent().name if node.get_parent() else "",
			box.size, screen_coverage(box, _camera_of(node)), over_focus(box), thin(box),
			is_crown(node), assembly_width(node), described])

## BaseMaterial3D.TextureChannel as the vector look_faded_standard dots a
## texel with.
const CHANNELS := [Vector4(1, 0, 0, 0), Vector4(0, 1, 0, 0), Vector4(0, 0, 1, 0),
	Vector4(0, 0, 0, 1), Vector4(0.333333, 0.333333, 0.333333, 0)]

## True when a mesh stays solid whatever covers the player: ground.
static func keeps_solid(node_name: String) -> bool:
	return LookGround.kind_of(node_name) != LookGround.Kind.NONE

## True for water (a Water_ or Scenery_Water mesh): it fades as develop fades
## it. Develop fades a bog pool or a river whose box holds the player's chest
## as if it stood between them and the camera, which shows the bed through
## it; the Grey Moors' bog water is authored near black (its texture averages
## 11 of 255), so kept solid round a hole, or not faded at all, it drew a
## flat black sheet over a quarter of gm_road.
static func is_water(node: MeshInstance3D) -> bool:
	var node_name := String(node.name)
	if node_name.begins_with("StreamView_"):
		node_name = node_name.get_slice("__", 1)
	return node_name.begins_with("Water_") or node_name.begins_with("Scenery_Water")

## A dithered copy of `source` for OccluderFade to fade by, or null when it
## has none or `node` should blend instead (`mode_of`; OccluderFade then does
## what develop does). Its hole is sized for `node`, the mesh it fades (see
## hole_metres), or it dissolves all of it (Mode.VANISH).
static func dither_copy(source: Material, node: MeshInstance3D = null) -> ShaderMaterial:
	var mode := mode_of(node)
	if mode == Mode.BLEND:
		return null
	var copy: ShaderMaterial = null
	if source is BaseMaterial3D:
		copy = _dithered_standard(source as BaseMaterial3D)
	else:
		var painted := source as ShaderMaterial
		if painted == null or not painted.has_meta(FADED_SHADER_META):
			return null
		var faded_shader := painted.get_meta(FADED_SHADER_META) as Shader
		if faded_shader == null:
			return null
		copy = painted.duplicate() as ShaderMaterial
		copy.shader = faded_shader
		_set_hole(copy)
	if copy != null:
		_size_hole(copy, node)
		copy.set_shader_parameter(WHOLE_PARAMETER, 1.0 if mode == Mode.VANISH else 0.0)
	return copy

## The hole's radius for an occluder: FADE_HOLE_METRES, or a share of a
## larger occluder's width. A giant canopy the camera looks down through
## covered most of the frame round a hole sized for a player, as a ceiling of
## flat leaf cards; opened by a fifth of its width it reads as a gap in the
## crown, with the canopy round the frame's edges.
static func hole_metres(node: MeshInstance3D) -> float:
	if node == null or node.mesh == null:
		return LookProfile.FADE_HOLE_METRES
	var size := node.mesh.get_aabb().size
	var scale := node.transform.basis.get_scale()
	if node.is_inside_tree():
		scale = node.global_transform.basis.get_scale()
	var width := maxf(size.x * absf(scale.x), size.z * absf(scale.z))
	if is_crown(node):
		return clampf(width * LookProfile.CROWN_HOLE_SHARE, LookProfile.FADE_HOLE_METRES,
			LookProfile.CROWN_HOLE_MAX_METRES)
	return clampf(width * LookProfile.FADE_HOLE_SHARE, LookProfile.FADE_HOLE_METRES,
		LookProfile.FADE_HOLE_MAX_METRES)

## Sets a dithered copy's opacity (1 solid, 0 gone), how far its hole is open
## (the fade's progress, 0..1) and where it is centred.
static func write(copy: ShaderMaterial, opacity: float, open := 1.0) -> void:
	copy.set_shader_parameter(FADE_PARAMETER, clampf(opacity, 0.0, 1.0))
	copy.set_shader_parameter(OPEN_PARAMETER, clampf(open, 0.0, 1.0))
	copy.set_shader_parameter(FOCUS_PARAMETER, focus)

## True when `node` draws a painted crown (LookFoliage): a crown fades without
## a shadow, as develop's blended copies do.
static func is_crown(node: MeshInstance3D) -> bool:
	if node.material_override != null:
		return node.material_override.has_meta(LookFoliage.PAINTED_META)
	var surfaces := 0 if node.mesh == null else node.mesh.get_surface_count()
	for surface: int in surfaces:
		var material := node.get_active_material(surface)
		if material != null and material.has_meta(LookFoliage.PAINTED_META):
			return true
	return false

## True when look_faded_standard draws `material` as the engine does.
static func reproduces(material: BaseMaterial3D) -> bool:
	if material is ORMMaterial3D:
		return false
	if material.shading_mode != BaseMaterial3D.SHADING_MODE_PER_PIXEL \
			or material.blend_mode != BaseMaterial3D.BLEND_MODE_MIX \
			or material.cull_mode == BaseMaterial3D.CULL_FRONT \
			or material.diffuse_mode != BaseMaterial3D.DIFFUSE_BURLEY \
			or material.specular_mode != BaseMaterial3D.SPECULAR_SCHLICK_GGX \
			or material.billboard_mode != BaseMaterial3D.BILLBOARD_DISABLED \
			or material.distance_fade_mode != BaseMaterial3D.DISTANCE_FADE_DISABLED \
			or material.depth_draw_mode != BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY:
		return false
	if material.uv1_triplanar or material.uv2_triplanar or material.grow \
			or material.detail_enabled or material.rim_enabled \
			or material.clearcoat_enabled or material.anisotropy_enabled \
			or material.heightmap_enabled or material.subsurf_scatter_enabled \
			or material.backlight_enabled or material.refraction_enabled \
			or material.proximity_fade_enabled or material.emission_on_uv2 \
			or material.ao_on_uv2:
		return false
	for flag: int in [BaseMaterial3D.FLAG_DISABLE_DEPTH_TEST, BaseMaterial3D.FLAG_USE_POINT_SIZE,
			BaseMaterial3D.FLAG_FIXED_SIZE, BaseMaterial3D.FLAG_USE_SHADOW_TO_OPACITY,
			BaseMaterial3D.FLAG_UV1_USE_WORLD_TRIPLANAR, BaseMaterial3D.FLAG_PARTICLE_TRAILS_MODE]:
		if material.get_flag(flag):
			return false
	return material.texture_filter in [BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS,
		BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC]

## The dithered stand-in for a StandardMaterial3D, or null when
## look_faded_standard cannot reproduce it.
static func _dithered_standard(source: BaseMaterial3D) -> ShaderMaterial:
	if not reproduces(source):
		return null
	var copy := ShaderMaterial.new()
	copy.resource_name = source.resource_name
	copy.shader = SHADER_STANDARD_TWO_SIDED \
		if source.cull_mode == BaseMaterial3D.CULL_DISABLED else SHADER_STANDARD
	copy.render_priority = source.render_priority
	copy.next_pass = source.next_pass
	var alpha_mode := 0
	match source.transparency:
		BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
			alpha_mode = 1
		BaseMaterial3D.TRANSPARENCY_ALPHA, BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS, \
				BaseMaterial3D.TRANSPARENCY_ALPHA_HASH:
			alpha_mode = 2
	copy_standard_surface(source, copy)
	copy.set_shader_parameter(&"use_vertex_albedo", source.vertex_color_use_as_albedo)
	copy.set_shader_parameter(&"vertex_albedo_srgb", source.vertex_color_is_srgb)
	copy.set_shader_parameter(&"alpha_mode", alpha_mode)
	copy.set_shader_parameter(&"alpha_scissor_threshold", source.alpha_scissor_threshold)
	_set_hole(copy)
	return copy

## A fresh faded copy: whole, its hole's size from LookProfile.
static func _set_hole(copy: ShaderMaterial) -> void:
	copy.set_shader_parameter(FADE_PARAMETER, 1.0)
	copy.set_shader_parameter(OPEN_PARAMETER, 0.0)
	copy.set_shader_parameter(FOCUS_PARAMETER, focus)
	copy.set_shader_parameter(&"look_fade_hole_metres", LookProfile.FADE_HOLE_METRES)
	copy.set_shader_parameter(&"look_fade_rim_metres", LookProfile.FADE_RIM_METRES)
	copy.set_shader_parameter(&"look_fade_behind_metres", LookProfile.FADE_BEHIND_METRES)

## Sizes a faded copy's hole, and its rim with it, for the mesh it fades.
static func _size_hole(copy: ShaderMaterial, node: MeshInstance3D) -> void:
	var radius := hole_metres(node)
	copy.set_shader_parameter(&"look_fade_hole_metres", radius)
	copy.set_shader_parameter(&"look_fade_rim_metres",
		maxf(LookProfile.FADE_RIM_METRES, radius * LookProfile.FADE_RIM_SHARE))

## Fills the uniforms of look_standard_surface.gdshaderinc (albedo, normal,
## roughness, metallic, occlusion, emission, UV scale) on `target` from
## `source`, so a look shader lights as the material it stands in for.
static func copy_standard_surface(source: BaseMaterial3D, target: ShaderMaterial) -> void:
	target.set_shader_parameter(&"albedo_color", source.albedo_color)
	target.set_shader_parameter(&"albedo_texture", source.albedo_texture)
	target.set_shader_parameter(&"has_normal_texture",
		source.normal_enabled and source.normal_texture != null)
	target.set_shader_parameter(&"normal_texture", source.normal_texture)
	target.set_shader_parameter(&"normal_scale", source.normal_scale)
	target.set_shader_parameter(&"roughness_value", source.roughness)
	target.set_shader_parameter(&"roughness_texture", source.roughness_texture)
	target.set_shader_parameter(&"roughness_channel", CHANNELS[source.roughness_texture_channel])
	target.set_shader_parameter(&"metallic_value", source.metallic)
	target.set_shader_parameter(&"metallic_texture", source.metallic_texture)
	target.set_shader_parameter(&"metallic_channel", CHANNELS[source.metallic_texture_channel])
	target.set_shader_parameter(&"specular_value", source.metallic_specular)
	target.set_shader_parameter(&"has_ao", source.ao_enabled and source.ao_texture != null)
	target.set_shader_parameter(&"ao_texture", source.ao_texture)
	target.set_shader_parameter(&"ao_channel", CHANNELS[source.ao_texture_channel])
	target.set_shader_parameter(&"ao_light_affect", source.ao_light_affect)
	target.set_shader_parameter(&"has_emission", source.emission_enabled)
	target.set_shader_parameter(&"emission_color", source.emission)
	target.set_shader_parameter(&"emission_texture", source.emission_texture)
	target.set_shader_parameter(&"emission_energy", source.emission_energy_multiplier)
	target.set_shader_parameter(&"emission_operator", int(source.emission_operator))
	target.set_shader_parameter(&"uv1_scale", source.uv1_scale)
	target.set_shader_parameter(&"uv1_offset", source.uv1_offset)

## Stops `node` casting while it fades, and hands a wall's or roof's shadow
## to a shadow-only twin drawing its current (resting) materials; a crown gets
## no twin (see the header). Call before the faded copies go in. Returns the
## twin, or null when there is none.
static func hold_shadow(node: MeshInstance3D) -> MeshInstance3D:
	if not is_instance_valid(node) or node.mesh == null:
		return null
	# Decided here, as the fade begins: a blended occluder keeps develop's
	# shadow exactly (see the header), and a vanished one casts none, as
	# develop's blended copies cast none: its shadow twin left the shadow of a
	# mesh the viewer no longer sees, a dark disc round the player where the
	# Grey Moors' barrow mound and a Sunmane yurt had been.
	var mode := _decide(node)
	if mode == Mode.BLEND:
		return null
	if mode == Mode.VANISH:
		if node.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF \
				and node.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:
			node.set_meta(SHADOW_META, node.cast_shadow)
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		return null
	if node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF \
			or node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:
		return null
	node.set_meta(SHADOW_META, node.cast_shadow)
	var crown := is_crown(node)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	if crown:
		return null
	var twin := MeshInstance3D.new()
	twin.name = SHADOW_TWIN_NAME
	twin.mesh = node.mesh
	twin.material_override = node.material_override
	for surface: int in node.get_surface_override_material_count():
		twin.set_surface_override_material(surface, node.get_surface_override_material(surface))
	twin.layers = node.layers
	twin.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
	node.add_child(twin)
	return twin

## Gives `node` its shadow back and takes any twin out of the tree at once (a
## twin left for the frame a queue_free takes would double the shadow). Either
## may be null: a node freed with its map, a crown that has no twin.
static func release_shadow(node: MeshInstance3D, twin: MeshInstance3D) -> void:
	if node != null and node.has_meta(MODE_META):
		node.remove_meta(MODE_META)
	if node != null and node.has_meta(SHADOW_META):
		node.cast_shadow = int(node.get_meta(SHADOW_META)) \
			as GeometryInstance3D.ShadowCastingSetting
		node.remove_meta(SHADOW_META)
	if twin == null:
		return
	var parent := twin.get_parent()
	if parent != null:
		parent.remove_child(twin)
	twin.queue_free()
