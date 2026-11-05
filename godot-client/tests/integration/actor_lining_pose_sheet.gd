extends SceneTree
## Lining pose sheet (actor LODs C4): renders worn garments with their lining
## surfaces drawn plain and drawn with the lining stage's masked base, in six
## poses (idle, walk, attack, arms raised, sit, mounted) and five views, so the
## two can be compared pixel for pixel. The masks must be lossless: every pair
## should match. A half-faded pass (the transparency the game gives a fading
## humanoid corpse) shows the one case where hidden lining faces can show.
##
## Windowed, under the GPU lock. RABBITLANDS_LINING_MASKS names a folder of
## lining_visibility.py masks (<variant>/<stem>.lining.json);
## RABBITLANDS_LINING_SHEET_OUT the output folder. The companion
## actor_lining_pose_sheet.py counts the changed pixels and composes the sheets.
##
## For each lining the actor actually wears, the script runs the cook's lining
## stage (cook.gd plan_state + LiningPolicy.apply) on a fresh parse of the
## garment, then builds two meshes from the worn mesh's own arrays (after the
## game's derivations, which keep the index buffer): `rebuilt` with the parsed
## index buffer and `masked` with the masked base (and compaction, if any).
## Captures per pose and view, in order: plain (the worn mesh), rebuilt,
## masked, rebuilt again and plain again. A pixel the two rebuilt (or plain)
## frames disagree on changed by itself and is not judged; elsewhere rebuilt vs
## masked is the masking change and plain vs rebuilt the rebuild's own.
## Output: <out>/<config>/<pose>__<view>__{plain,rebuilt,masked,rebuilt2,
## plain2}.png, <out>/<config>/fade__<view>__{rebuilt,masked,rebuilt2}.png and
## <out>/manifest.json.

const Cook := preload("res://tools/actor_geometry/cook.gd")
const LiningPolicy := preload("res://tools/actor_geometry/lining_policy.gd")
const Format := preload("res://src/actors/actor_geometry_format.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")

const MASKS_ENVIRONMENT := "RABBITLANDS_LINING_MASKS"
const OUT_ENVIRONMENT := "RABBITLANDS_LINING_SHEET_OUT"
const SIZE := Vector2i(420, 600)
## [label, race model, equipment visuals]. Kit B is the benchmark's Mossbound
## kit (both twins: legs WithBoots, boots WithLegs); the rest wear one piece.
const CONFIGS: Array = [
	["kit_b_male", "luminous_male", {5: 185, 4: 172, 6: 193}],
	["sunburst_cuirass_male", "luminous_male", {5: 196}],
	["mossbound_coat_male", "luminous_male", {5: 185}],
	["homespun_shirt_male", "luminous_male", {5: 232}],
	["mossbound_legguards_male", "luminous_male", {4: 172}],
	["splinted_chausses_male", "luminous_male", {4: 221}],
	["work_trousers_female", "luminous_female", {4: 244}],
	["glowline_boots_male", "luminous_male", {6: 193}],
	["cathedral_greaves_male", "luminous_male", {6: 243}],
]
## [label, clip, time in seconds]; "mounted" seats the rider on a horse.
const POSES: Array = [
	["idle", "Idle_Subtle", 0.3], ["walk", "Walk", 0.25], ["attack", "Combat_Slash_A", 0.45],
	["arms_raised", "Power_Up", 0.6], ["sit", "Meditate", 0.8], ["mounted", "", 0.0],
]
## [label, yaw degrees round the actor, pitch degrees (negative looks down)].
const VIEWS: Array = [["front", 0.0, 0.0], ["back", 180.0, 0.0], ["side", 90.0, 0.0],
	["above", 35.0, -50.0], ["below", 200.0, 25.0]]
const PARTS := {"GeneratedArmorBacking": 5, "GeneratedLegBacking": 4, "GeneratedBootBacking": 6}

var _stage: Node3D
var _camera: Camera3D
var _out := ""
var _masks := ""
var _models: Dictionary
var _equipment: Dictionary
var _animations: Dictionary
var _manifest := {"configs": {}, "size": [SIZE.x, SIZE.y], "poses": [], "views": []}
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_out = OS.get_environment(OUT_ENVIRONMENT)
	_masks = OS.get_environment(MASKS_ENVIRONMENT)
	if _out.is_empty() or _masks.is_empty():
		printerr("set %s and %s" % [OUT_ENVIRONMENT, MASKS_ENVIRONMENT])
		quit(2)
		return
	GltfQuantization.ensure_registered()
	DirAccess.make_dir_recursive_absolute(_out)
	root.size = SIZE
	_build_stage()
	_models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	_equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	_animations = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for pose: Array in POSES:
		(_manifest.poses as Array).append(pose[0])
	for view: Array in VIEWS:
		(_manifest.views as Array).append(view[0])
	for config: Array in CONFIGS:
		await _render_config(config)
	var file := FileAccess.open(_out.path_join("manifest.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_manifest, " ", true))
	file.close()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("LINING POSE SHEET: %d configs, %d failures, out %s" % [CONFIGS.size(), _failures, _out])
	quit(1 if _failures > 0 else 0)


func _build_stage() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(.13, .16, .19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = .75
	_stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = 1.2
	_stage.add_child(light)
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.current = true
	_stage.add_child(_camera)


func _render_config(config: Array) -> void:
	var label: String = config[0]
	var folder := _out.path_join(label)
	DirAccess.make_dir_recursive_absolute(folder)
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	var errors := actor.configure({"actor_id": 910, "kind": 1, "name": "", "x": 0, "y": 0, "rotation": 0,
		"appearance": {"hair": 1}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.}),
		_models[config[1]], _animations, _equipment)
	if not errors.is_empty():
		_fail("%s configures: %s" % [label, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.global_position = Vector3.ZERO
	actor.rotation.y = PI
	actor._advance_facing_offset(1.)
	actor.apply_equipment_visuals(config[2])
	for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
		(marker as MeshInstance3D).hide()
	for frame: int in 3:
		await process_frame
	var swaps := _swaps(actor, config)
	var entry := {"race": config[1], "equipment": config[2], "linings": []}
	for swap: Dictionary in swaps:
		(entry.linings as Array).append(swap.report)
	_manifest.configs[label] = entry
	var masked_any := false
	for swap: Dictionary in swaps:
		masked_any = masked_any or swap.has("masked")
	for pose: Array in POSES:
		var mounted: bool = pose[0] == "mounted"
		if mounted:
			actor.set_mount_state({"mode": "mounted", "mount_id": "golden_plains_horse", "gait": "idle",
				"step_us": 200000}, _models)
			if actor._mount_visual != null:
				actor._mount_visual.set_process(false)
				for step: int in 8:
					actor._mount_visual._process(1.0 / 30.0)
			else:
				_fail("%s mounts" % label)
		else:
			actor.animation_player.play(pose[1])
			actor.animation_player.seek(float(pose[2]), true)
			actor.animation_player.pause()
		for view: Array in VIEWS:
			_place_camera(view, mounted)
			var stem := folder.path_join("%s__%s__" % [pose[0], view[0]])
			await _capture(stem + "plain.png")
			if not masked_any:
				continue
			# plain, rebuilt, masked, rebuilt, plain: a pixel that differs
			# between the two rebuilt (or plain) frames moved on its own (the
			# RL head's eyes, for one) and is not judged.
			_use(swaps, "rebuilt")
			await _capture(stem + "rebuilt.png")
			_use(swaps, "masked")
			await _capture(stem + "masked.png")
			_use(swaps, "rebuilt")
			await _capture(stem + "rebuilt2.png")
			_use(swaps, "plain")
			await _capture(stem + "plain2.png")
		if mounted:
			actor.set_mount_state({}, _models)
	if masked_any:
		# A fading humanoid corpse: every geometry at half transparency.
		actor.animation_player.play("Idle_Subtle")
		actor.animation_player.seek(0.3, true)
		actor.animation_player.pause()
		var geometry: Array = actor.find_children("*", "GeometryInstance3D", true, false)
		for node: GeometryInstance3D in geometry:
			node.transparency = 0.5
		for view: Array in [VIEWS[0], VIEWS[3]]:
			_place_camera(view, false)
			var stem := folder.path_join("fade__%s__" % view[0])
			_use(swaps, "rebuilt")
			await _capture(stem + "rebuilt.png")
			_use(swaps, "masked")
			await _capture(stem + "masked.png")
			_use(swaps, "rebuilt")
			await _capture(stem + "rebuilt2.png")
			_use(swaps, "plain")
		for node: GeometryInstance3D in geometry:
			if is_instance_valid(node):
				node.transparency = 0.0
	actor.free()
	await process_frame
	print("LINING POSE SHEET: %s done (%d linings, masked: %s)" % [label, swaps.size(), masked_any])


## For every worn lining: the plain mesh, a rebuild from its own arrays and,
## when the lining stage masks it, the masked rebuild.
func _swaps(actor: ReplicatedActor3D, config: Array) -> Array:
	var swaps: Array = []
	var variant := "canonical_human_female" if str(config[1]).ends_with("_female") else "canonical_human_male"
	# Worn skinned pieces are EquipmentSkin_<part>_Visual_<id>_<glTF node name>.
	var pattern := RegEx.create_from_string("^EquipmentSkin_(\\d+)_Visual_(\\d+)_(Generated.+)$")
	for node: Node in actor.get_skeleton().find_children("EquipmentSkin_*", "MeshInstance3D", true, false):
		var lining := node as MeshInstance3D
		var found := pattern.search(str(node.name))
		if lining == null or lining.mesh == null or found == null:
			continue
		var name := found.get_string(3)
		var part := int(found.get_string(1))
		var visual := int(found.get_string(2))
		var report := {"node": str(node.name), "lining": name, "part": part, "visible": lining.is_visible_in_tree()}
		if not lining.is_visible_in_tree() or not PARTS.values().has(part):
			(swaps as Array).append({"node": lining, "plain": lining.mesh, "report": report})
			continue
		var model: Dictionary = _equipment.models.get("%d:%d" % [part, visual], {})
		var scene := str((model.get("variants", {}) as Dictionary).get(variant, model).get("scene", model.get("scene", "")))
		report["garment"] = scene
		var swap := {"node": lining, "plain": lining.mesh, "report": report}
		var record := _lining_record(scene, name, report)
		var mesh := lining.mesh as ArrayMesh
		if mesh == null or mesh.get_surface_count() != 1 or mesh.get_blend_shape_count() != 0:
			report["skipped"] = "mesh shape"
			swaps.append(swap)
			continue
		var arrays := mesh.surface_get_arrays(0)
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		report["worn_vertices"] = (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		report["worn_index_digest_matches"] = not record.is_empty() and Format.index_digest(indices) == str(record.index_digest)
		swap["rebuilt"] = _rebuild(mesh, arrays)
		if not record.is_empty() and record.has("base") and bool(report.worn_index_digest_matches) \
				and int(report.worn_vertices) == int(record.vertex_count):
			var masked := arrays.duplicate()
			if record.has("compact_runs"):
				masked = ActorGeometry._compact(masked, record.compact_runs, int(record.vertex_count))
			masked[Mesh.ARRAY_INDEX] = record.base
			swap["masked"] = _rebuild(mesh, masked)
		elif record.has("base"):
			_fail("%s %s: the worn mesh does not match the parse the mask binds to" % [config[0], name])
		swaps.append(swap)
	return swaps


## The lining stage's sidecar record for one lining of a garment, from a fresh
## parse and its mask; {} when the garment has no usable mask.
func _lining_record(scene: String, node_name: String, report: Dictionary) -> Dictionary:
	var stem := scene.get_base_dir().get_file().path_join(scene.get_file().get_basename())
	var mask_path := _masks.path_join(stem + ".lining.json")
	if not FileAccess.file_exists(mask_path):
		report["status"] = "no_mask"
		return {}
	var text := FileAccess.get_file_as_string(mask_path)
	var mask: Dictionary = JSON.parse_string(text)
	var absolute := ProjectSettings.globalize_path(scene)
	if str(mask.get("source", {}).get("sha256", "")) != FileAccess.get_sha256(absolute):
		report["status"] = "stale_mask"
		return {}
	var parsed := Cook.parse(absolute)
	var plan := Cook.plan_state(parsed.state, scene, FileAccess.get_sha256(absolute), 0, 1.0)
	plan = LiningPolicy.apply(parsed.state, plan, LiningPolicy.input_from_mask(mask, Format.sha256_hex(text.to_utf8_buffer())))
	var meshes: Array = parsed.state.get_meshes()
	for mesh_index: int in meshes.size():
		var importer: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		if LiningPolicy.gltf_mesh_name(str(importer.resource_name), parsed.state.get_scene_name()) != node_name:
			continue
		var row: Dictionary = plan.meshes[mesh_index].surfaces[0]
		report["status"] = str(row.get("lining", {}).get("status", "unmasked"))
		report["stats"] = row.get("lining", {})
		return plan.sidecar.meshes[mesh_index].surfaces[0]
	report["status"] = "not_in_garment"
	return {}


func _rebuild(mesh: ArrayMesh, arrays: Array) -> ArrayMesh:
	var out := ArrayMesh.new()
	out.add_surface_from_arrays(mesh.surface_get_primitive_type(0), arrays, [], {}, mesh.surface_get_format(0))
	out.surface_set_material(0, mesh.surface_get_material(0))
	out.resource_name = mesh.resource_name
	return out


func _use(swaps: Array, kind: String) -> void:
	for swap: Dictionary in swaps:
		var node: MeshInstance3D = swap.node
		node.mesh = swap.get(kind, swap.get("rebuilt", swap.plain)) if kind != "plain" else swap.plain


func _place_camera(view: Array, mounted: bool) -> void:
	var focus := Vector3(0.0, 1.45 if mounted else 0.95, 0.0)
	_camera.size = 3.4 if mounted else 2.3
	var yaw := deg_to_rad(float(view[1]))
	var pitch := deg_to_rad(float(view[2]))
	var direction := Vector3(sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch))
	_camera.position = focus + direction * 6.0
	_camera.look_at(focus, Vector3.UP if absf(direction.y) < 0.99 else Vector3.FORWARD)


func _capture(path: String) -> void:
	for frame: int in 2:
		await process_frame
	await RenderingServer.frame_post_draw
	if root.get_texture().get_image().save_png(path) != OK:
		_fail("save " + path)


func _fail(message: String) -> void:
	_failures += 1
	push_error(message)
