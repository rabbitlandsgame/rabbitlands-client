class_name RLHeadRig
extends Node3D
## The RL head prototype on one actor's skeleton: the head module, its hair
## and facial hair, their identity shapes, materials and level of detail.
##
## Built by `attach` as a child of the actor's Skeleton3D, after the actor's
## animation import (NativeAnimationImporter folds every blend shape present at
## import time into its RESET defaults; see its `_blend_shape_defaults`, which
## also skips `id_`/`ex_` shapes as a second guard). Opt-in: an actor without
## `appearance.rl_head` never builds one, and nothing here runs for it.
##
## Asset contract (assets/actors/rl_heads/, read by RLHeadLibrary):
##   * rl_head_<sex>.glb: a mesh skinned to spine_03, neck_01 and Head with the
##     body's inverse binds, at the scene root. Mesh nodes `rl_head_lod<k>`
##     (or one `rl_head`, which is LOD 0); materials rl_skin, rl_eye, rl_lash,
##     rl_brow and optionally rl_mouth; blend shapes `id_<control>_p/_n` and
##     `ex_<expression>`; `asset.extras.rlHead` with the controls, the
##     expressions and the body cut (RLHeadBodyCut).
##   * hair/<style>.glb: its own skeleton, rooted at `hair_root` on the body's
##     Head rest, plus optional spring chains; meshes `hair_lod<k>` or `hair`,
##     materials rl_hair_clump and rl_hair_card; `asset.extras.rlHair` for the
##     springs (RLHairMotion).
##   * beards/<style>.glb: skinned like the head, meshes `beard_lod<k>` or
##     `beard`, material rl_beard, and the head's `id_` and `ex_` shape names.
##     `stubble` with no file is painted by the skin shader.
##
## Identity is blend-shape weights only - changing a control never rebuilds a
## mesh - and per-actor colours are instance uniforms on shared materials.
## Expressions belong to the RLFaceExpression child, which never writes `id_`
## shapes; this never writes `ex_` shapes.

signal changed

const NODE_NAME := "RLHead"
## The BoneAttachment3D the hair hangs from. ReplicatedActor3D hides every
## skeleton child named AppearanceHair_* under hair-covering headwear.
const HAIR_NODE_NAME := "AppearanceHair_RL"
## Hair and facial hair cast no shadows: at the game's shadow-map resolution
## locks and cards shadow the face and neck as hard, splotchy shapes (owner
## review 2026-10-27). The head itself still shadows the neck.
const HAIR_SHADOWS := GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
const REBOUND_SKIN_POOL := preload("res://src/actors/rebound_skin_pool.gd")
## Where the next LOD takes over, in metres from the camera, by quality, when
## an asset ships more than one: HIGH draws lod0 to 10 m, lod1 to 25 m and lod2
## beyond; MEDIUM starts at lod1 and hands over to lod2 at 18 m; LOW is lod2.
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
## Frames between distance checks; actors are spread over them by id.
const LOD_CHECK_FRAMES := 6
const INSTANCE_UNIFORMS := ["skin_color", "lip_tint", "brow_color", "hair_color",
	"freckles", "liner", "stubble", "eye_color", "hairline", "brow_style", "brow_thickness",
	"liner_wing"]
## How much hair colour the skin paints on the scalp and hairline while a
## hairstyle is drawn (features2 B); none on a bald head, nor while the chosen
## hairstyle's file is missing.
const HAIRLINE_UNDER_HAIR := 0.35

var appearance: RLHeadAppearance
var quality: int = ActorRenderQuality.QUALITY_DEFAULT
## The lab's switch for secondary hair motion. RLHairMotion still applies its
## own quality, distance and count limits on top.
var hair_motion_allowed := true

var _skeleton: Skeleton3D
var _head_info: Dictionary = {}
var _head_lods: Array = []
var _beard_lods: Array = []
var _beard_style := ""
var _hair_lods: Array = []
var _hair_style := ""
## The hair's root on the skeleton: a BoneAttachment3D on Head for an RL
## hairstyle, a plain holder of skinned meshes for a `legacy:` one.
var _hair_attachment: Node3D
## Per-actor tinted copies of a legacy hairstyle's materials, by mesh node.
var _legacy_hair_materials: Dictionary = {}
var _hair_motion: RLHairMotion
var _expression: RLFaceExpression
var _rim_roughness := -1.0
## The visible band: 0 is the quality's first instanced level.
var _lod_band := 0
var _lod_countdown := 0
## The actor's body material, which the head's body patch is drawn with.
var _body_material: Material = null

## Mesh resource id -> {blend shape name: index}, shared by every actor.
static var _shape_indices: Dictionary = {}


## Builds an RL head on `skeleton` from `value` (a preset name, the dictionary
## form or an RLHeadAppearance). Null, with nothing left behind, when the
## value names no face or the head module for its sex is missing.
static func attach(skeleton: Skeleton3D, value: Variant,
		level: int = ActorRenderQuality.QUALITY_DEFAULT) -> RLHeadRig:
	var face := RLHeadAppearance.from_value(value)
	if face == null or skeleton == null:
		if face == null:
			RLHeadLibrary.warn_once("face:" + str(value), "no RL head preset or face in " + str(value))
		return null
	var rig := RLHeadRig.new()
	rig.name = NODE_NAME
	rig.quality = ActorRenderQuality.normalized_quality(level)
	rig._skeleton = skeleton
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
	_apply_colours()
	_show_band(mini(_lod_band, _band_count() - 1))
	changed.emit()
	return true


## One identity control, in [-1, 1], on the head, the beard and the hair.
func set_control(control_name: String, value: float) -> void:
	appearance.set_control(control_name, value)
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
	_apply_colours()
	_show_band(mini(_lod_band, _band_count() - 1))
	changed.emit()


func set_hair_motion_allowed(allowed: bool) -> void:
	hair_motion_allowed = allowed
	_refresh_hair_motion()


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
			for mesh_node: MeshInstance3D in level:
				if is_instance_valid(mesh_node):
					result.append(mesh_node)
	return result


## Every mesh an expression weight goes to: head and beard, all levels.
func expression_targets() -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	for group: Array in [_head_lods, _beard_lods]:
		for level: Array in group:
			for mesh_node: MeshInstance3D in level:
				if is_instance_valid(mesh_node):
					result.append(mesh_node)
	return result


## The head, beard and hair mesh nodes by part, for diagnostics and the lab.
func mesh_nodes() -> Dictionary:
	return {"head": _head_lods, "beard": _beard_lods, "hair": _hair_lods}


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
	if _hair_style == RLHeadAppearance.NONE or _skeleton.find_bone("Head") < 0:
		return
	if _hair_style.begins_with(RLHeadLibrary.LEGACY_PREFIX):
		_build_legacy_hair(_hair_style.trim_prefix(RLHeadLibrary.LEGACY_PREFIX))
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
			_assign_materials(mesh_node, _hair_style)
			mesh_node.cast_shadow = HAIR_SHADOWS
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


## The game's own fitted hairstyle for this body, skinned to the skeleton the
## way ReplicatedActor3D draws it, and tinted the way it tints it.
func _build_legacy_hair(style: String) -> void:
	var path := RLHeadLibrary.legacy_hair_path(appearance.sex, style)
	var pieces: Array = ReplicatedActor3D._equipment_pieces(path) \
		if FileAccess.file_exists(path) else []
	if pieces.is_empty():
		RLHeadLibrary.warn_once("legacy hair:" + path,
			"legacy hairstyle %s missing, drawing the head bald" % path, true)
		return
	_hair_attachment = Node3D.new()
	_hair_attachment.name = HAIR_NODE_NAME
	_skeleton.add_child(_hair_attachment)
	var nodes: Array[MeshInstance3D] = []
	for piece: Dictionary in pieces:
		var skin := _rebind(piece.get("bones", PackedStringArray()) as PackedStringArray,
			piece.get("binds", [] as Array[Transform3D]) as Array[Transform3D])
		if skin == null:
			continue
		var mesh_node := MeshInstance3D.new()
		mesh_node.name = "RLHair_" + str(piece.get("name", "legacy"))
		mesh_node.mesh = piece.get("mesh") as Mesh
		mesh_node.skin = skin
		mesh_node.transform = piece.get("transform", Transform3D.IDENTITY)
		ReplicatedActor3D._restore_piece_render_state(mesh_node, piece)
		mesh_node.cast_shadow = HAIR_SHADOWS
		_hair_attachment.add_child(mesh_node)
		mesh_node.skeleton = mesh_node.get_path_to(_skeleton)
		var tinted: Array = []
		for surface: int in mesh_node.mesh.get_surface_count():
			var source := mesh_node.mesh.surface_get_material(surface) as StandardMaterial3D
			if source == null:
				continue
			var copy := source.duplicate() as StandardMaterial3D
			copy.set_meta(&"rl_source_colour", source.albedo_color)
			mesh_node.set_surface_override_material(surface, copy)
			tinted.append(copy)
		_legacy_hair_materials[mesh_node] = tinted
		nodes.append(mesh_node)
	_hair_lods = [nodes] if not nodes.is_empty() else []


func _free_hair() -> void:
	_hair_lods = []
	_legacy_hair_materials.clear()
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
			mesh_node.skin = skin
			add_child(mesh_node)
			mesh_node.skeleton = mesh_node.get_path_to(_skeleton)
			_assign_materials(mesh_node, style)
			nodes.append(mesh_node)
		if not nodes.is_empty():
			result.append(nodes)
	_show_levels(result, _lod_band)
	return result


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


## Shows the levels of `band` (each part clamps to the levels it has).
func update_lod(distance: float) -> void:
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
	set_process(_band_count() > 1)


func _show_levels(levels: Array, band: int) -> void:
	var shown := mini(band, levels.size() - 1)
	for index: int in levels.size():
		for mesh_node: MeshInstance3D in levels[index]:
			mesh_node.visible = index == shown


func _ready() -> void:
	# Spread the actors' distance checks over LOD_CHECK_FRAMES.
	_lod_countdown = get_instance_id() % LOD_CHECK_FRAMES
	set_process(_band_count() > 1)


func _process(_delta: float) -> void:
	_lod_countdown -= 1
	if _lod_countdown > 0:
		return
	_lod_countdown = LOD_CHECK_FRAMES
	var camera := get_viewport().get_camera_3d()
	if camera != null:
		update_lod(camera.global_position.distance_to(
			_skeleton.global_transform * _skeleton.get_bone_global_rest(_skeleton.find_bone("Head")).origin))


func _free_levels(levels: Array) -> void:
	for level: Array in levels:
		for mesh_node: MeshInstance3D in level:
			if is_instance_valid(mesh_node):
				if mesh_node.get_parent() != null:
					mesh_node.get_parent().remove_child(mesh_node)
				mesh_node.queue_free()


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
	var names := PackedStringArray(_head_info.get("control_names", PackedStringArray()))
	for control_name: Variant in appearance.controls:
		if not names.has(str(control_name)):
			names.append(str(control_name))
	for mesh_node: MeshInstance3D in identity_targets():
		for control_name: String in names:
			var amount := appearance.control(control_name)
			_set_shape(mesh_node, "id_%s_p" % control_name, maxf(amount, 0.0))
			_set_shape(mesh_node, "id_%s_n" % control_name, maxf(-amount, 0.0))


func _apply_colours() -> void:
	var values := {
		"skin_color": appearance.skin, "lip_tint": appearance.lip_tint,
		"brow_color": appearance.brow_color, "hair_color": appearance.hair_color,
		"freckles": appearance.freckles, "liner": appearance.liner,
		"stubble": appearance.stubble_amount(), "eye_color": appearance.eyes,
		"hairline": HAIRLINE_UNDER_HAIR if not _hair_lods.is_empty() else 0.0,
		"brow_style": appearance.brow_style, "brow_thickness": appearance.brow_thickness,
		"liner_wing": appearance.liner_wing,
	}
	# The head's surfaces read all of them; hair and beard read the hair colour.
	for tinted: Variant in _legacy_hair_materials.values():
		for material: StandardMaterial3D in tinted as Array:
			material.albedo_color = (material.get_meta(&"rl_source_colour") as Color) * appearance.hair_color
	var shader_hair: Array = [] if not _legacy_hair_materials.is_empty() else _hair_lods
	for part: Array in [[_head_lods, INSTANCE_UNIFORMS], [_beard_lods, ["hair_color"]],
			[shader_hair, ["hair_color"]]]:
		for level: Array in part[0]:
			for mesh_node: MeshInstance3D in level:
				for uniform_name: String in part[1]:
					mesh_node.set_instance_shader_parameter(uniform_name, values[uniform_name])


## Sets a blend shape by name where the mesh has it. Identity only: an `ex_`
## shape is the expression node's, and is refused here.
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
