class_name RLHeadRig
extends Node3D
## The RL head on one actor's skeleton: the head module, its hair and facial
## hair, their identity shapes, materials and level of detail.
##
## Built by `attach` as a child of the actor's Skeleton3D, after the actor's
## animation import (NativeAnimationImporter folds every blend shape present at
## import time into its RESET defaults; see its `_blend_shape_defaults`, which
## also skips `id_`/`ex_`/`hl_` shapes as a second guard). ReplicatedActor3D
## builds one for a Human at High quality (and for the lab's `rl_head`
## override at any quality); nothing here runs for any other actor.
##
## Asset contract (assets/actors/native/rl_heads/ and the maps in
## assets/actors/native/rl_head_textures/, read by RLHeadLibrary):
##   * rl_head_<sex>.glb: a mesh skinned to spine_03, neck_01 and Head with the
##     body's inverse binds, at the scene root. Mesh nodes `rl_head_lod<k>`
##     (or one `rl_head`, which is LOD 0); materials rl_skin, rl_eye, rl_lash,
##     rl_brow and optionally rl_mouth; blend shapes `id_<control>_p/_n` and
##     `ex_<expression>`; `asset.extras.rlHead` with the controls, the
##     expressions and the body cut (RLHeadBodyCut).
##   * hair/<style>.glb: its own skeleton, rooted at `hair_root` on the body's
##     Head rest, plus optional spring chains; meshes `hair_lod<k>` or `hair`,
##     materials rl_hair_clump and rl_hair_card; `asset.extras.rlHair` for the
##     springs (RLHairMotion) and `headSHA256`, the head build it was fitted
##     to. Grooming blend shapes, read when present and a no-op when absent:
##     `hl_length_p/_n` and `hl_volume_p/_n` (weight 1 = the full change, 0 =
##     as authored) for the hair length and volume. COLOR_0.A is each point's
##     keep level for the hair's fine detail (1 core geometry, flyaway and wisp
##     cards 0.5-0.95, messy extras 0.05-0.45), which the hair shader compares
##     with the `hair_detail` instance uniform (RLHeadAppearance.hair_detail /
##     100; see rl_hair.gdshader).
##   * beards/<style>.glb: skinned like the head, meshes `beard_lod<k>` or
##     `beard`, material rl_beard, and the head's `id_` and `ex_` shape names.
##     `stubble` with no file is painted by the skin shader.
##
## A `legacy:<style>` hairstyle is not built here: the actor draws its own
## fitted hairstyle (ReplicatedActor3D._add_hair_variant, the one path every
## quality uses), and this rig only paints the hairline under it.
##
## Identity is blend-shape weights - changing a control never rebuilds a mesh
## - and per-actor colours are instance uniforms on shared materials.
## Expressions belong to the RLFaceExpression child, which never writes `id_`
## shapes; this never writes `ex_` shapes.
##
## The levels shown are drawn with their identity baked in (RLHeadIdentityBake:
## one cached mesh per distinct face and level, shared by every actor wearing
## it, keeping only the `ex_` shapes live), so a crowd does not deform up to 42
## identity shapes per part every frame. Each mesh node keeps its source mesh
## (SOURCE_MESH_META) and falls back to it, with the identity weights set live,
## while its bake is pending, when the bake budget is spent, for the levels not
## shown, and for good once `set_control` edits a face interactively (the lab).
##
## Every rig counts as one user of RLHeadLibrary's shared caches from its
## creation to its deletion; the last one to go releases them (heads, beards,
## textures, materials, the body cuts and the headwear refits), so switching
## every Human down from High frees the High head's memory as develop's own
## High portrait does.

signal changed

const NODE_NAME := "RLHead"
## The BoneAttachment3D the hair hangs from. ReplicatedActor3D hides every
## skeleton child named AppearanceHair_* under hair-covering headwear.
const HAIR_NODE_NAME := "AppearanceHair_RL"
## On every head, beard and hair mesh this rig makes: CharacterProportions'
## body refinement and the other legacy finishing passes leave such meshes alone.
const MESH_META := &"rl_head"
## Hair and facial hair cast no shadows: at the game's shadow-map resolution
## locks and cards shadow the face and neck as hard, splotchy shapes (owner
## review 2026-10-27). The head itself still shadows the neck.
const HAIR_SHADOWS := GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
const REBOUND_SKIN_POOL := preload("res://src/actors/rebound_skin_pool.gd")
const IDENTITY_BAKE := preload("res://src/actors/rl_head/rl_head_identity_bake.gd")
## On every head, beard and hair mesh node: the shared, unbaked mesh it was
## built with, which carries the live identity shapes.
const SOURCE_MESH_META := &"rl_source_mesh"
## Where the next LOD takes over, in metres from the camera, by quality, when
## an asset ships more than one: HIGH draws lod0 to 10 m, lod1 to 25 m and lod2
## beyond; MEDIUM starts at lod1 and hands over to lod2 at 18 m; LOW is lod2.
## (The game builds the RL head only at HIGH; MEDIUM and LOW are the lab's.)
## Every level of the head carries the same rim and the same shapes, so a
## hand-over never opens the neck seam.
##
## Exactly one level is visible at a time, switched here by distance rather
## than by visibility ranges: a range-culled skinned instance with blend
## shapes is still deformed every frame, and in the compatibility renderer
## three per actor doubled a 40-actor crowd's frame time (18.4 ms against
## 9.2 ms with the unused levels hidden; .local/rl-heads evidence).
const LOD_DISTANCES := {
	ActorRenderQuality.Quality.HIGH: [10.0, 25.0],
	ActorRenderQuality.Quality.MEDIUM: [18.0],
	ActorRenderQuality.Quality.LOW: [],
}
## Hysteresis either side of a hand-over, so an actor on the line does not flicker.
const LOD_MARGIN := 1.0
## Frames between distance checks. One per-frame callback checks the rigs in
## turn, a sixth of them each frame, instead of a _process on every rig.
const LOD_CHECK_FRAMES := 6
const INSTANCE_UNIFORMS := ["skin_color", "lip_tint", "brow_color", "hair_color",
	"freckles", "liner", "stubble", "eye_color", "hairline", "brow_style", "brow_thickness",
	"liner_wing"]
## How much hair colour the skin paints on the scalp and hairline while a
## hairstyle is drawn (features2 B); none on a bald head, nor while the chosen
## hairstyle's file is missing.
const HAIRLINE_UNDER_HAIR := 0.35
## The hair-shape blend shapes (see the asset contract above).
const HAIR_LENGTH_SHAPES := ["hl_length_p", "hl_length_n"]
const HAIR_VOLUME_SHAPES := ["hl_volume_p", "hl_volume_n"]
## The instance uniforms on an RL hairstyle's meshes. A beard keeps the
## shader's default `hair_detail` (0.5, nothing dropped).
const HAIR_INSTANCE_UNIFORMS := ["hair_color", "hair_detail"]

var appearance: RLHeadAppearance
var quality: int = ActorRenderQuality.QUALITY_DEFAULT
## The lab's switch for secondary hair motion. RLHairMotion still applies its
## own quality, distance and count limits on top.
var hair_motion_allowed := true
## The actor's animated-head culling envelope, set on every mesh made here.
var cull_margin := 0.0
## The render layers of the actor's body, given to every mesh made here so the
## dialogue portrait's layer lease and the cameras see the head as the body.
var mesh_layers := 1

var _skeleton: Skeleton3D
var _head_info: Dictionary = {}
var _head_lods: Array = []
var _beard_lods: Array = []
var _beard_style := ""
var _hair_lods: Array = []
var _hair_style := ""
## The actor draws this face's hair itself (a `legacy:` style, or the
## fallback when an RL hairstyle's file is missing): only the hairline here.
var _hair_external := false
## The hair's root on the skeleton: a BoneAttachment3D on Head.
var _hair_attachment: Node3D
var _hair_motion: RLHairMotion
var _expression: RLFaceExpression
var _rim_roughness := -1.0
## The visible band: 0 is the quality's first instanced level.
var _lod_band := 0
## In _lod_rigs (several levels and no portrait pose held).
var _lod_listed := false
## The actor's body material, which the head's body patch is drawn with.
var _body_material: Material = null
## A portrait (dialogue line, leaderboard card) is being taken: first level,
## neutral expression, eyes open, no blinking, no distance switching.
var _portrait_pose := false
var _counted := false
## Mesh node instance id -> the RLHeadIdentityBake key it holds (shown, or
## waiting for its bake while the source mesh draws the identity live).
var _bakes: Dictionary = {}
## The face is being edited control by control (`set_control`): every level
## stays live from then on.
var _live_identity := false

## Mesh resource id -> {blend shape name: index}, shared by every actor.
static var _shape_indices: Dictionary = {}
## The rigs whose level follows the camera, checked in turn by _check_lods.
static var _lod_rigs: Array[RLHeadRig] = []
static var _lod_cursor := 0
static var _lod_ticking := false


## Builds an RL head on `skeleton` from `value` (a preset name, the dictionary
## form or an RLHeadAppearance). Null, with nothing left behind, when the
## value names no face or the head module for its sex is missing.
static func attach(skeleton: Skeleton3D, value: Variant,
		level: int = ActorRenderQuality.QUALITY_DEFAULT, margin: float = 0.0,
		layers: int = 1) -> RLHeadRig:
	var face := RLHeadAppearance.from_value(value)
	if face == null or skeleton == null:
		if face == null:
			RLHeadLibrary.warn_once("face:" + str(value), "no RL head preset or face in " + str(value))
		return null
	var rig := RLHeadRig.new()
	rig.name = NODE_NAME
	rig.quality = ActorRenderQuality.normalized_quality(level)
	rig.cull_margin = margin
	rig.mesh_layers = layers
	rig._skeleton = skeleton
	rig._counted = true
	RLHeadLibrary.acquire()
	skeleton.add_child(rig)
	if not rig.apply_appearance(face):
		rig.teardown()
		return null
	return rig


## The rig on `skeleton`, or null.
static func find_on(skeleton: Skeleton3D) -> RLHeadRig:
	if skeleton == null:
		return null
	return skeleton.get_node_or_null(NODE_NAME) as RLHeadRig


## Drops the shared blend-shape index tables (RLHeadLibrary.release_unused).
static func clear_caches() -> void:
	_shape_indices.clear()


## Drops one mesh's blend-shape index table (a baked mesh leaving the cache).
static func forget_mesh(mesh: Mesh) -> void:
	if mesh != null:
		_shape_indices.erase(mesh.get_instance_id())


func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		for entry_key: Variant in _bakes.values():
			IDENTITY_BAKE.release(str(entry_key))
		_bakes.clear()
		if _counted:
			_counted = false
			RLHeadLibrary.release()


## Applies a whole face. Only what differs is rebuilt: a new sex replaces the
## head, a new style its hair or beard; controls and colours are values.
func apply_appearance(face: RLHeadAppearance) -> bool:
	if face == null:
		return false
	var previous := appearance
	appearance = face.duplicate_appearance()
	if previous == null or previous.sex != appearance.sex or _head_lods.is_empty():
		if not _build_head():
			return false
		_hair_style = "\n"
		_beard_style = "\n"
	if appearance.hair != _hair_style:
		_build_hair()
	if appearance.beard != _beard_style:
		_build_beard()
	_apply_controls()
	_apply_hair_shapes()
	_apply_colours()
	_show_band(0 if _portrait_pose else mini(_lod_band, _band_count() - 1))
	_apply_portrait_pose()
	changed.emit()
	return true


## One identity control, in [-1, 1], on the head, the beard and the hair.
## Drawn live from then on (no bake per slider step).
func set_control(control_name: String, value: float) -> void:
	appearance.set_control(control_name, value)
	_go_live()
	var amount := appearance.control(control_name)
	for mesh_node: MeshInstance3D in identity_targets():
		_set_shape(mesh_node, "id_%s_p" % control_name, maxf(amount, 0.0))
		_set_shape(mesh_node, "id_%s_n" % control_name, maxf(-amount, 0.0))
	changed.emit()


## Re-reads colours and amounts from `appearance` after it was edited in place.
func refresh_colours() -> void:
	_apply_colours()
	changed.emit()


## Picks the LOD meshes for a quality (ActorRenderQuality / LookProfile order).
## The game keeps the rig at HIGH; the lab's override previews the others.
func set_quality(level: int) -> void:
	level = ActorRenderQuality.normalized_quality(level)
	if level == quality:
		return
	quality = level
	_build_head()
	_hair_style = "\n"
	_beard_style = "\n"
	_build_hair()
	_build_beard()
	_apply_controls()
	_apply_hair_shapes()
	_apply_colours()
	_show_band(0 if _portrait_pose else mini(_lod_band, _band_count() - 1))
	_apply_portrait_pose()
	changed.emit()


func set_hair_motion_allowed(allowed: bool) -> void:
	hair_motion_allowed = allowed
	_refresh_hair_motion()


## Whether the actor draws this face's hair (a `legacy:` style, or the
## fallback for a missing RL hairstyle). Only the hairline changes here.
func set_hair_external(external: bool) -> void:
	if external == _hair_external:
		return
	_hair_external = external
	_apply_colours()


func hair_external() -> bool:
	return _hair_external


## True when this rig draws an RL hairstyle of its own (a module that loaded).
func draws_module_hair() -> bool:
	return not _hair_lods.is_empty()


## Holds the portrait pose (see `_portrait_pose`) while `held`.
func set_portrait_pose(held: bool) -> void:
	if held == _portrait_pose:
		return
	_portrait_pose = held
	if held:
		_show_band(0)
	_apply_portrait_pose()


func portrait_pose() -> bool:
	return _portrait_pose


func expression() -> RLFaceExpression:
	return _expression


func hair_motion() -> RLHairMotion:
	return _hair_motion


## RLHeadLibrary.head() for this head: controls, expressions, body cut, path.
func head_info() -> Dictionary:
	return _head_info


## The body meshes the head module replaces (`bodyCut.hideMeshes`).
func hide_meshes() -> PackedStringArray:
	var names := PackedStringArray()
	for name: Variant in (_head_info.get("body_cut", {}) as Dictionary).get("hideMeshes", []) as Array:
		names.append(str(name).to_lower())
	return names


## Every mesh an identity weight goes to: head, beard and hair, all levels.
func identity_targets() -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	for group: Array in [_head_lods, _beard_lods, _hair_lods]:
		for level: Array in group:
			for mesh_node: Variant in level:
				if is_instance_valid(mesh_node):
					result.append(mesh_node as MeshInstance3D)
	return result


## Every mesh an expression weight goes to: head and beard, all levels.
func expression_targets() -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	for group: Array in [_head_lods, _beard_lods]:
		for level: Array in group:
			for mesh_node: Variant in level:
				if is_instance_valid(mesh_node):
					result.append(mesh_node as MeshInstance3D)
	return result


## The head, beard and hair mesh nodes by part, for diagnostics and the lab.
func mesh_nodes() -> Dictionary:
	return {"head": _head_lods, "beard": _beard_lods, "hair": _hair_lods}


## Every mesh node this rig made, all parts and levels.
func all_meshes() -> Array[MeshInstance3D]:
	return identity_targets()


## Triangles drawn up close: the first level of each part, summed over surfaces.
func near_triangle_count() -> int:
	var total := 0
	for group: Array in [_head_lods, _beard_lods, _hair_lods]:
		if group.is_empty():
			continue
		for mesh_node: MeshInstance3D in group[0]:
			total += mesh_triangles(mesh_node.mesh)
	return total


static func mesh_triangles(mesh: Mesh) -> int:
	var total := 0
	if mesh == null:
		return 0
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		var indices: Variant = arrays[Mesh.ARRAY_INDEX]
		total += ((indices as PackedInt32Array).size() if indices is PackedInt32Array
			else (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()) / 3
	return total


## The body face material's roughness, so the neck rim shades like the body.
func set_rim_shading(roughness: float, specular: float = 0.5) -> void:
	_rim_roughness = roughness
	for level: Array in _head_lods:
		for mesh_node: MeshInstance3D in level:
			for surface: int in mesh_node.mesh.get_surface_count():
				var material := mesh_node.get_surface_override_material(surface) as ShaderMaterial
				if material != null and material.resource_name == "rl_skin":
					material.set_shader_parameter("rim_roughness", roughness)
					material.set_shader_parameter("rim_specular", specular)


## The material the actor's `body` mesh is drawn with (its face/skin shader
## with the actor's recolour), for the head's `rl_bodypatch` surface: the
## clipped bottom of the body triangles the cut removed, on the body's UVs.
func set_body_material(material: Material) -> void:
	_body_material = material
	for level: Array in _head_lods:
		for mesh_node: MeshInstance3D in level:
			_assign_body_patch(mesh_node)


## The actor's culling envelope and render layers, on every mesh made here.
func set_mesh_presentation(margin: float, layers: int) -> void:
	cull_margin = margin
	mesh_layers = layers
	for mesh_node: MeshInstance3D in identity_targets():
		_present(mesh_node)


## Frees every node this rig made, the hair attachment on the skeleton too.
func teardown() -> void:
	_free_hair()
	if is_instance_valid(_skeleton) and get_parent() == _skeleton:
		_skeleton.remove_child(self)
	queue_free()


# ---------------------------------------------------------------- building

func _base_level(available: int) -> int:
	var wanted := 0
	match quality:
		ActorRenderQuality.Quality.MEDIUM:
			wanted = 1
		ActorRenderQuality.Quality.LOW:
			wanted = 2
	return clampi(wanted, 0, maxi(available - 1, 0))


func _build_head() -> bool:
	_free_levels(_head_lods)
	_head_lods = []
	_head_info = RLHeadLibrary.head(appearance.sex)
	if _head_info.is_empty():
		return false
	_head_lods = _instance_levels(_head_info["lods"] as Array, "RLHead", "")
	if _head_lods.is_empty():
		return false
	if _rim_roughness >= 0.0:
		set_rim_shading(_rim_roughness)
	if _expression == null:
		_expression = RLFaceExpression.new()
		_expression.name = "RLFaceExpression"
		add_child(_expression)
	_expression.configure(expression_targets(), _head_info.get("expressions", PackedStringArray()))
	return true


func _build_beard() -> void:
	_free_levels(_beard_lods)
	_beard_lods = []
	_beard_style = appearance.beard
	if _beard_style != RLHeadAppearance.NONE:
		var lods := RLHeadLibrary.beard(_beard_style)
		if not lods.is_empty():
			_beard_lods = _instance_levels(lods, "RLBeard", _beard_style)
			for level: Array in _beard_lods:
				for mesh_node: MeshInstance3D in level:
					mesh_node.cast_shadow = HAIR_SHADOWS
		elif _beard_style != RLHeadAppearance.STUBBLE:
			RLHeadLibrary.warn_once("beard:" + _beard_style,
				"facial hair %s missing, drawing the face clean-shaven" % _beard_style, true)
	if _expression != null:
		_expression.set_targets(expression_targets())


func _build_hair() -> void:
	_free_hair()
	_hair_style = appearance.hair
	_hair_external = false
	if _hair_style == RLHeadAppearance.NONE or _skeleton.find_bone("Head") < 0:
		return
	if _hair_style.begins_with(RLHeadLibrary.LEGACY_PREFIX):
		# The actor's own fitted hairstyle (ReplicatedActor3D._add_hair_variant).
		_hair_external = true
		return
	var instance := RLHeadLibrary.instantiate_hair(_hair_style)
	if instance == null:
		return
	var attachment := BoneAttachment3D.new()
	attachment.name = HAIR_NODE_NAME
	attachment.bone_name = "Head"
	_skeleton.add_child(attachment)
	_hair_attachment = attachment
	# The hair is authored in the body's model space with hair_root on the
	# Head rest; undoing that rest under the Head attachment puts the whole
	# scene back where it was authored, riding the head once the clip plays.
	var frame := Node3D.new()
	frame.name = "RLHairFrame"
	frame.transform = _skeleton.get_bone_global_rest(_skeleton.find_bone("Head")).affine_inverse()
	_hair_attachment.add_child(frame)
	instance.name = "RLHair_" + _hair_style
	frame.add_child(instance)
	var by_level: Dictionary = {}
	for node_value: Node in instance.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node_value as MeshInstance3D
		var level := RLHeadLibrary.lod_level(str(mesh_node.name))
		# Renamed so nothing taking body meshes by name (`hair`) finds these.
		mesh_node.name = "RLHair_" + str(mesh_node.name)
		if not by_level.has(level):
			by_level[level] = []
		(by_level[level] as Array).append(mesh_node)
	var levels: Array = by_level.keys()
	levels.sort()
	var base := _base_level(levels.size())
	for index: int in levels.size():
		var nodes: Array = by_level[levels[index]]
		if index < base:
			for mesh_node: MeshInstance3D in nodes:
				mesh_node.queue_free()
			continue
		var kept: Array[MeshInstance3D] = []
		for mesh_node: MeshInstance3D in nodes:
			mesh_node.set_meta(SOURCE_MESH_META, mesh_node.mesh)
			_assign_materials(mesh_node, _hair_style)
			mesh_node.cast_shadow = HAIR_SHADOWS
			_present(mesh_node)
			kept.append(mesh_node)
		_hair_lods.append(kept)
	_show_band(_lod_band)
	var skeleton: Skeleton3D = null
	for node_value: Node in instance.find_children("*", "Skeleton3D", true, false):
		skeleton = node_value as Skeleton3D
		break
	if skeleton != null:
		var info := RLHeadLibrary.hair_info(_hair_style)
		_hair_motion = RLHairMotion.new()
		_hair_motion.name = "RLHairMotion"
		instance.add_child(_hair_motion)
		_hair_motion.configure(skeleton, info.get("extras", {}) as Dictionary)
		_refresh_hair_motion()


func _free_hair() -> void:
	_release_bakes(_hair_lods)
	_hair_lods = []
	_hair_motion = null
	if is_instance_valid(_hair_attachment):
		if _hair_attachment.get_parent() != null:
			_hair_attachment.get_parent().remove_child(_hair_attachment)
		_hair_attachment.queue_free()
	_hair_attachment = null


func _refresh_hair_motion() -> void:
	if _hair_motion != null:
		_hair_motion.enabled = hair_motion_allowed and quality == ActorRenderQuality.Quality.HIGH


## Skinned pieces rebound onto the actor's skeleton, one Array per LOD level
## from the quality's first level on. Levels below it are never instanced.
func _instance_levels(lods: Array, prefix: String, style: String) -> Array:
	var result: Array = []
	var base := _base_level(lods.size())
	for level: int in range(base, lods.size()):
		var nodes: Array[MeshInstance3D] = []
		for piece: Dictionary in lods[level]:
			var skin := _rebind(piece["bones"] as PackedStringArray,
				piece["binds"] as Array[Transform3D])
			if skin == null:
				RLHeadLibrary.warn_once("rebind:" + prefix + str(piece["name"]),
					"%s %s has joints this skeleton lacks" % [prefix, piece["name"]])
				continue
			var mesh_node := MeshInstance3D.new()
			mesh_node.name = "%s_lod%d_%s" % [prefix, level, piece["name"]]
			mesh_node.mesh = piece["mesh"] as Mesh
			mesh_node.set_meta(SOURCE_MESH_META, piece["mesh"])
			mesh_node.skin = skin
			add_child(mesh_node)
			mesh_node.skeleton = mesh_node.get_path_to(_skeleton)
			_assign_materials(mesh_node, style)
			_present(mesh_node)
			nodes.append(mesh_node)
		if not nodes.is_empty():
			result.append(nodes)
	_show_levels(result, _lod_band)
	return result


## The marks and presentation every mesh made here carries.
func _present(mesh_node: MeshInstance3D) -> void:
	mesh_node.set_meta(MESH_META, true)
	mesh_node.extra_cull_margin = maxf(mesh_node.extra_cull_margin, cull_margin)
	mesh_node.layers = mesh_layers


## glTF's inverse binds are in model space, which is the actor skeleton's
## space: named binds onto it reproduce the authored rest exactly.
func _rebind(bones: PackedStringArray, binds: Array[Transform3D]) -> Skin:
	if bones.is_empty() or bones.size() != binds.size():
		return null
	var skin := Skin.new()
	for index: int in bones.size():
		if _skeleton.find_bone(bones[index]) < 0:
			return null
		skin.add_named_bind(bones[index], binds[index])
	return REBOUND_SKIN_POOL.intern_finalized(skin)


## The band a camera at `distance` metres calls for, from `current`, with
## LOD_MARGIN of hysteresis around each hand-over.
func lod_band_for(distance: float, current: int = -1) -> int:
	var distances: Array = LOD_DISTANCES.get(quality, []) as Array
	var band := 0
	for edge: Variant in distances:
		var threshold := float(edge)
		if current >= 0:
			threshold += LOD_MARGIN if band >= current else -LOD_MARGIN
		if distance > threshold:
			band += 1
	return mini(band, _band_count() - 1)


## Shows the levels of `band` (each part clamps to the levels it has). A held
## portrait pose keeps the first level whatever the distance.
func update_lod(distance: float) -> void:
	if _portrait_pose:
		return
	var band := lod_band_for(distance, _lod_band)
	if band != _lod_band:
		_show_band(band)


func lod_band() -> int:
	return _lod_band


func _band_count() -> int:
	return maxi(1, maxi(_head_lods.size(), maxi(_beard_lods.size(), _hair_lods.size())))


func _show_band(band: int) -> void:
	_lod_band = band
	for group: Array in [_head_lods, _beard_lods, _hair_lods]:
		_show_levels(group, band)
	_refresh_lod_listing()
	_bake_shown()


func _show_levels(levels: Array, band: int) -> void:
	var shown := mini(band, levels.size() - 1)
	for index: int in levels.size():
		for mesh_node: Variant in levels[index]:
			if is_instance_valid(mesh_node):
				(mesh_node as MeshInstance3D).visible = index == shown


func _enter_tree() -> void:
	_refresh_lod_listing()


func _exit_tree() -> void:
	_refresh_lod_listing(false)


## Lists the rig for camera-distance checks while it has several levels, no
## portrait pose is held and it is in the tree.
func _refresh_lod_listing(in_tree: bool = true) -> void:
	var wanted := in_tree and is_inside_tree() and _band_count() > 1 and not _portrait_pose
	if wanted == _lod_listed:
		return
	_lod_listed = wanted
	if wanted:
		_lod_rigs.append(self)
		if not _lod_ticking:
			_lod_ticking = true
			(Engine.get_main_loop() as SceneTree).process_frame.connect(_check_lods)
	else:
		_lod_rigs.erase(self)


## A sixth of the listed rigs each frame look at their camera. A rig whose
## processing is off (its actor paused by the animation gate) keeps its level.
static func _check_lods() -> void:
	var count := _lod_rigs.size()
	if count == 0:
		var tree := Engine.get_main_loop() as SceneTree
		if tree != null and tree.process_frame.is_connected(_check_lods):
			tree.process_frame.disconnect(_check_lods)
		_lod_ticking = false
		return
	for step: int in ceili(float(count) / LOD_CHECK_FRAMES):
		if _lod_rigs.is_empty():
			return
		_lod_cursor = _lod_cursor % _lod_rigs.size()
		var rig := _lod_rigs[_lod_cursor]
		_lod_cursor += 1
		if is_instance_valid(rig) and rig.can_process():
			rig._check_lod()


func _check_lod() -> void:
	var camera := get_viewport().get_camera_3d()
	if camera != null:
		update_lod(camera.global_position.distance_to(
			_skeleton.global_transform * _skeleton.get_bone_global_rest(_skeleton.find_bone("Head")).origin))


func _apply_portrait_pose() -> void:
	_refresh_lod_listing()
	if _expression != null:
		_expression.hold_neutral(_portrait_pose)


func _free_levels(levels: Array) -> void:
	_release_bakes(levels)
	for level: Array in levels:
		for mesh_node: Variant in level:
			if is_instance_valid(mesh_node):
				var node := mesh_node as Node
				if node.get_parent() != null:
					node.get_parent().remove_child(node)
				node.queue_free()


## Replaces each surface's imported material with the shared shader material
## for its name. A name outside the contract keeps its imported material.
func _assign_materials(mesh_node: MeshInstance3D, style: String) -> void:
	for surface: int in mesh_node.mesh.get_surface_count():
		var imported := mesh_node.mesh.surface_get_material(surface)
		var material_name := imported.resource_name if imported != null else ""
		if _is_body_patch(imported):
			continue
		var shared := RLHeadLibrary.material(material_name, appearance.sex, style, quality)
		if shared == null:
			RLHeadLibrary.warn_once("material:" + material_name,
				"material %s is outside the RL head contract; kept as imported" % material_name)
			continue
		mesh_node.set_surface_override_material(surface, shared)
	_assign_body_patch(mesh_node)


## The body patch takes the body's material, or flat skin until one is given.
func _assign_body_patch(mesh_node: MeshInstance3D) -> void:
	for surface: int in mesh_node.mesh.get_surface_count():
		var imported := mesh_node.mesh.surface_get_material(surface)
		if not _is_body_patch(imported):
			continue
		var material := _body_material
		if material == null:
			material = RLHeadLibrary.material("rl_skin", appearance.sex, "", quality)
		mesh_node.set_surface_override_material(surface, material)


static func _is_body_patch(material: Material) -> bool:
	if material == null:
		return false
	if material.resource_name == RLHeadLibrary.BODY_PATCH_MATERIAL:
		return true
	var extras: Variant = material.get_meta(&"extras", {})
	return extras is Dictionary and (extras as Dictionary).has("useBodyMaterial")


# ---------------------------------------------------------------- values

func _apply_controls() -> void:
	for mesh_node: MeshInstance3D in identity_targets():
		_apply_identity_weights(mesh_node)


## The identity controls this head declares, plus any the face sets beyond them.
func _control_names() -> PackedStringArray:
	var names := PackedStringArray(_head_info.get("control_names", PackedStringArray()))
	for control_name: Variant in appearance.controls:
		if not names.has(str(control_name)):
			names.append(str(control_name))
	return names


## Every identity weight of the face on one mesh node (live; a baked mesh has
## no `id_` shapes left and ignores them).
func _apply_identity_weights(mesh_node: MeshInstance3D) -> void:
	for control_name: String in _control_names():
		var amount := appearance.control(control_name)
		_set_shape(mesh_node, "id_%s_p" % control_name, maxf(amount, 0.0))
		_set_shape(mesh_node, "id_%s_n" % control_name, maxf(-amount, 0.0))


## Hair length and volume on an RL hairstyle that carries the hair-shape blend
## shapes; a hairstyle without them is left as authored. (Its fine detail is an
## instance uniform, set with the colours.)
func _apply_hair_shapes() -> void:
	var weights := _hair_shape_weights()
	for level: Array in _hair_lods:
		for node: Variant in level:
			if not is_instance_valid(node):
				continue
			for shape: String in weights:
				_set_shape(node as MeshInstance3D, shape, float(weights[shape]))


## The hair-shape weights of the face: length and volume as _p/_n pairs.
func _hair_shape_weights() -> Dictionary:
	var length := clampf(appearance.hair_length, -1.0, 1.0)
	var volume := clampf(appearance.hair_volume, -1.0, 1.0)
	return {HAIR_LENGTH_SHAPES[0]: maxf(length, 0.0), HAIR_LENGTH_SHAPES[1]: maxf(-length, 0.0),
		HAIR_VOLUME_SHAPES[0]: maxf(volume, 0.0), HAIR_VOLUME_SHAPES[1]: maxf(-volume, 0.0)}


## The `hair_detail` instance uniform: the face's level as 0..1.
func hair_detail_uniform() -> float:
	return clampf(float(appearance.hair_detail) / 100.0, 0.0, 1.0)


func _is_hair_node(mesh_node: MeshInstance3D) -> bool:
	for level: Array in _hair_lods:
		if level.has(mesh_node):
			return true
	return false


# ---------------------------------------------------------------- identity bake

## What a mesh node's bake bakes in: every identity weight, and on a hair node
## the hair-shape weights.
func _baked_weights(mesh_node: MeshInstance3D) -> Dictionary:
	var weights := {}
	for control_name: String in _control_names():
		var amount := appearance.control(control_name)
		weights["id_%s_p" % control_name] = maxf(amount, 0.0)
		weights["id_%s_n" % control_name] = maxf(-amount, 0.0)
	if _is_hair_node(mesh_node):
		weights.merge(_hair_shape_weights(), true)
	return weights


## The shown level of every part draws its baked mesh (or waits for it, live);
## every other level goes back to its live source mesh and lets its bake go.
func _bake_shown() -> void:
	var baking := not _live_identity and IDENTITY_BAKE.enabled()
	for group: Array in [_head_lods, _beard_lods, _hair_lods]:
		var shown := mini(_lod_band, group.size() - 1)
		for index: int in group.size():
			for node: Variant in group[index]:
				if not is_instance_valid(node):
					continue
				if baking and index == shown:
					_bake(node as MeshInstance3D)
				else:
					_unbake(node as MeshInstance3D, true)


func _bake(mesh_node: MeshInstance3D) -> void:
	var source := mesh_node.get_meta(SOURCE_MESH_META, null) as ArrayMesh
	if source == null or not IDENTITY_BAKE.has_baked_shapes(source):
		return
	var weights := _baked_weights(mesh_node)
	var entry_key := IDENTITY_BAKE.key(source, weights)
	var id := mesh_node.get_instance_id()
	if str(_bakes.get(id, "")) == entry_key:
		return
	_unbake(mesh_node, true)
	var baked := IDENTITY_BAKE.acquire(source, weights, _on_baked.bind(id, entry_key))
	if baked == null and not IDENTITY_BAKE.holds(entry_key):
		# No bake to be had now (budget spent): this node stays live.
		return
	_bakes[id] = entry_key
	if baked != null:
		_show_baked(mesh_node, baked)


func _on_baked(baked: ArrayMesh, id: int, entry_key: String) -> void:
	if str(_bakes.get(id, "")) != entry_key:
		return
	var mesh_node := instance_from_id(id) as MeshInstance3D
	if mesh_node != null:
		_show_baked(mesh_node, baked)


func _show_baked(mesh_node: MeshInstance3D, baked: ArrayMesh) -> void:
	if mesh_node.mesh == baked:
		return
	mesh_node.mesh = baked
	_after_mesh_swap(mesh_node)


## Lets a node's bake go; with `restore`, it draws its source mesh live again.
func _unbake(mesh_node: MeshInstance3D, restore: bool) -> void:
	var id := mesh_node.get_instance_id()
	if _bakes.has(id):
		IDENTITY_BAKE.release(str(_bakes[id]))
		_bakes.erase(id)
	if not restore:
		return
	var source := mesh_node.get_meta(SOURCE_MESH_META, null) as Mesh
	if source != null and mesh_node.mesh != source:
		mesh_node.mesh = source
		_after_mesh_swap(mesh_node)


## A node's mesh changed: MeshInstance3D keeps blend-shape weights by index
## across meshes, so every weight is cleared and written again (identity and
## hair shapes here, expressions by RLFaceExpression), with the colours.
func _after_mesh_swap(mesh_node: MeshInstance3D) -> void:
	for index: int in mesh_node.mesh.get_blend_shape_count():
		mesh_node.set_blend_shape_value(index, 0.0)
	_apply_identity_weights(mesh_node)
	if _is_hair_node(mesh_node):
		var weights := _hair_shape_weights()
		for shape: String in weights:
			_set_shape(mesh_node, shape, float(weights[shape]))
	_apply_colours()
	if _expression != null:
		_expression.set_targets(expression_targets())


func _release_bakes(levels: Array) -> void:
	for level: Array in levels:
		for node: Variant in level:
			if is_instance_valid(node):
				_unbake(node as MeshInstance3D, false)


## Every level draws its live source mesh from now on (interactive editing).
func _go_live() -> void:
	if _live_identity:
		return
	_live_identity = true
	for mesh_node: MeshInstance3D in identity_targets():
		_unbake(mesh_node, true)


## Whether a mesh node draws a baked identity now (diagnostics and tests).
func is_baked(mesh_node: MeshInstance3D) -> bool:
	return mesh_node != null and mesh_node.mesh != null \
		and mesh_node.mesh != mesh_node.get_meta(SOURCE_MESH_META, mesh_node.mesh)


## The unbaked mesh a node was built with (its identity shapes intact).
static func source_mesh(mesh_node: MeshInstance3D) -> Mesh:
	return mesh_node.get_meta(SOURCE_MESH_META, mesh_node.mesh) as Mesh if mesh_node != null else null


func _apply_colours() -> void:
	var haired := not _hair_lods.is_empty() or _hair_external
	var beard_colour := appearance.beard_color if appearance.beard_color_set else appearance.hair_color
	var values := {
		"skin_color": appearance.skin, "lip_tint": appearance.lip_tint,
		"brow_color": appearance.brow_color, "hair_color": appearance.hair_color,
		"freckles": appearance.freckles, "liner": appearance.liner,
		"stubble": appearance.stubble_amount(), "eye_color": appearance.eyes,
		"hairline": HAIRLINE_UNDER_HAIR if haired else 0.0,
		"brow_style": appearance.brow_style, "brow_thickness": appearance.brow_thickness,
		"liner_wing": appearance.liner_wing, "hair_detail": hair_detail_uniform(),
	}
	# The head's surfaces read all but the hair's detail; the beard reads its
	# colour, the hair its colour and detail.
	var beard_values := {"hair_color": beard_colour}
	for part: Array in [[_head_lods, INSTANCE_UNIFORMS, values], [_beard_lods, ["hair_color"], beard_values],
			[_hair_lods, HAIR_INSTANCE_UNIFORMS, values]]:
		for level: Array in part[0]:
			for node: Variant in level:
				if not is_instance_valid(node):
					continue
				for uniform_name: String in part[1]:
					(node as MeshInstance3D).set_instance_shader_parameter(uniform_name, (part[2] as Dictionary)[uniform_name])


## Sets a blend shape by name where the mesh has it. Identity and hair shapes
## only: an `ex_` shape is the expression node's, and is refused here.
static func _set_shape(mesh_node: MeshInstance3D, shape: String, value: float) -> void:
	if shape.begins_with("ex_"):
		return
	var index := shape_index(mesh_node, shape)
	if index >= 0:
		mesh_node.set_blend_shape_value(index, value)


## A blend shape's index on a mesh node, or -1; looked up once per mesh.
static func shape_index(mesh_node: MeshInstance3D, shape: String) -> int:
	var mesh := mesh_node.mesh
	if mesh == null:
		return -1
	var key := mesh.get_instance_id()
	var table: Dictionary = _shape_indices.get(key, {}) as Dictionary
	if table.is_empty():
		for index: int in mesh.get_blend_shape_count():
			table[str(mesh.get_blend_shape_name(index))] = index
		table[""] = -1
		_shape_indices[key] = table
	return int(table.get(shape, -1))
