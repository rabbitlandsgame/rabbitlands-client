extends SceneTree
## Keeps the armour out of the cape, and photographs the back to prove it.
##
## The clip this guards is not the cloth solver's. The cape's yoke - its collar
## and the sheet above the shoulder blades - is skinned rigidly to spine_03, so
## no chain the solver drives reaches it, and it was conformed offline to clear
## the BARE back. Every worn cuirass stands deeper than that, so the armour's
## back plate came through the cloth on every armoured wearer in every pose.
##
## Both halves of the fix are measured here: the yoke is cut against the torso
## actually worn (`CapeDrape`), and the capsule the solver pushes the chains
## out of is sized to the same armour rather than to a constant. Both are
## measured on the vertices the renderer draws - the two garments are skinned
## by hand out of the settled skeleton, because that is the only place they
## meet.
##
## What is deliberately NOT held clear is the collar itself. A gorget standing
## over a cape's collar, or a pauldron over the end of it, is how armour is
## worn; pushing the ring out to clear those turns it into a plank across the
## shoulders, which is what conforming the whole yoke looked like rendered. So
## the collar band is allowed to interpenetrate and everything below it is not.

const CAPE_VISUAL := 5
## A spread across the torso ladder: the shallowest back, the deepest, and two
## between, so a fix cannot be tuned to one cuirass.
const BODIES := [225, 184, 213, 197]
## Heights are reported relative to spine_03, the cape's anchor. Above this the
## cloth is collar and the armour may stand through it.
const COLLAR_HEIGHT := 0.13
## What the sheet below the collar may sink into the armour, and what the
## collar itself may. Both are floors on the art, not targets: measured before
## the cape was cut against the armour, the sheet reached 67 mm inside.
const SHEET_TOLERANCE := 0.020
const COLLAR_TOLERANCE := 0.055

var _failures := 0
var _artifacts := ""
var _main: Control
var _stage: Node3D
var _camera: Camera3D
var _adapter: CoordinateAdapter
var _model_config: Dictionary
var _animation_config: Dictionary
var _equipment_config: Dictionary

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/cape-armour")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = Vector2i(520, 720)
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_main.hide()
	await process_frame
	var models: Dictionary = _main.get("models") as Dictionary
	_equipment_config = _main.get("equipment_config") as Dictionary
	_model_config = models.get("luminous_male", {}) as Dictionary
	_animation_config = _main.call("_animation_for_model", _model_config) as Dictionary
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})

	_stage = Node3D.new()
	root.add_child(_stage)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.85, 0.87, 0.9)
	env.environment.ambient_light_energy = 1.2
	_stage.add_child(env)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-25.0, 15.0, 0.0)
	_stage.add_child(key)
	_camera = Camera3D.new()
	_camera.current = true
	_camera.cull_mask = 3
	_stage.add_child(_camera)

	for body: int in BODIES:
		var actor := _spawn({str(2): CAPE_VISUAL, str(5): body})
		await _settle(actor)
		_measure(actor, body)
		await _capture(actor, "back-%d.png" % body, Vector3(0.0, 0.15, 1.9))
		await _capture(actor, "quarter-%d.png" % body, Vector3(-1.2, 0.25, 1.5))
		actor.queue_free()
		await process_frame

	print("rendered cape over armour: ", "PASS" if _failures == 0
		else "FAIL (%d)" % _failures)
	_main.queue_free()
	await process_frame
	quit(_failures)

## Where the worn torso stands through the cape, by height above the anchor.
func _measure(actor: ReplicatedActor3D, body: int) -> void:
	var skeleton: Skeleton3D = _skeleton_of(actor)
	var torso: PackedVector3Array = _posed(skeleton, 5)
	var cape: PackedVector3Array = _posed(skeleton, 2)
	if torso.is_empty() or cape.is_empty():
		print("  body %d: nothing to measure (torso %d, cape %d)"
			% [body, torso.size(), cape.size()])
		_failures += 1
		return
	var anchor: Vector3 = skeleton.get_bone_global_pose(
		skeleton.find_bone("spine_03")).origin
	# The armour's reach from the spine, per bearing and height, taken from the
	# posed vertices rather than the rest ones so a lean is included.
	var grid: Dictionary = {}
	for point: Vector3 in torso:
		var key: Vector2i = _cell(point, anchor)
		if key.x == -999:
			continue
		var out: float = Vector2(point.x - anchor.x, point.z - anchor.z).length()
		if out > float(grid.get(key, 0.0)):
			grid[key] = out
	var sheet := 0.0
	var collar := 0.0
	var profile: Dictionary = {}
	for point: Vector3 in cape:
		var key: Vector2i = _cell(point, anchor)
		if key.x == -999 or not grid.has(key):
			continue
		var out: float = Vector2(point.x - anchor.x, point.z - anchor.z).length()
		var deep: float = float(grid[key]) - out
		if deep <= 0.0:
			continue
		var height: float = point.y - anchor.y
		if height > COLLAR_HEIGHT:
			collar = maxf(collar, deep)
		else:
			sheet = maxf(sheet, deep)
		var band: float = snappedf(height, 0.05)
		if deep > float(profile.get(band, 0.0)):
			profile[band] = deep
	var bands: Array = profile.keys()
	bands.sort()
	var line := PackedStringArray()
	for band: float in bands:
		if float(profile[band]) > 0.002:
			line.append("%+.2f:%.0f" % [band, float(profile[band]) * 1000.0])
	var why := PackedStringArray()
	if sheet > SHEET_TOLERANCE:
		why.append("sheet %.0f mm" % (sheet * 1000.0))
	if collar > COLLAR_TOLERANCE:
		why.append("collar %.0f mm" % (collar * 1000.0))
	if not why.is_empty():
		_failures += 1
	print("  body %-4d sheet %.0f mm, collar %.0f mm  %s" % [body,
		sheet * 1000.0, collar * 1000.0,
		"ok" if why.is_empty() else "CLIPS (%s)" % ", ".join(why)])
	if not line.is_empty():
		print("       by height above the anchor, mm: ", " ".join(line))

## A bearing and height cell around the trunk, or x = -999 for a point off the
## back the cape covers.
func _cell(point: Vector3, anchor: Vector3) -> Vector2i:
	var bearing: float = rad_to_deg(atan2(point.x - anchor.x,
		-(point.z - anchor.z)))
	if absf(bearing) > 50.0 or absf(point.x - anchor.x) > 0.26:
		return Vector2i(-999, 0)
	return Vector2i(int(floor(bearing / 10.0)), int(floor(point.y / 0.05)))

## One equipment part's vertices, skinned by hand. Left in the skeleton's own
## space, where the rig's back is -z whichever way the actor is turned.
func _posed(skeleton: Skeleton3D, part: int) -> PackedVector3Array:
	var out := PackedVector3Array()
	var prefix: String = "EquipmentSkin_%d_" % part
	for child: Node in skeleton.get_children():
		var node := child as MeshInstance3D
		if node == null or not node.name.begins_with(prefix):
			continue
		if node.mesh == null or node.skin == null:
			continue
		var joints: Array[Transform3D] = []
		for bind: int in range(node.skin.get_bind_count()):
			var bone: int = skeleton.find_bone(node.skin.get_bind_name(bind))
			if bone < 0:
				joints.append(Transform3D.IDENTITY)
				continue
			joints.append(skeleton.get_bone_global_pose(bone)
				* node.skin.get_bind_pose(bind))
		for surface: int in range(node.mesh.get_surface_count()):
			var arrays: Array = node.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			if vertices.is_empty() or bones.is_empty():
				continue
			var per: int = bones.size() / vertices.size()
			for index: int in range(vertices.size()):
				var moved := Vector3.ZERO
				var total := 0.0
				for slot: int in range(per):
					var at: int = index * per + slot
					var weight: float = weights[at]
					if weight <= 0.0 or bones[at] >= joints.size():
						continue
					moved += (joints[bones[at]] * vertices[index]) * weight
					total += weight
				if total > 0.0:
					out.append(moved / total)
	return out

func _capture(actor: ReplicatedActor3D, name: String, offset: Vector3) -> void:
	var skeleton: Skeleton3D = _skeleton_of(actor)
	var chest: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(
		skeleton.find_bone("spine_03")).origin
	_camera.global_position = chest + offset
	_camera.look_at(chest + Vector3(0.0, -0.25, 0.0), Vector3.UP)
	for _f: int in range(2):
		await process_frame
	root.get_texture().get_image().save_png(_artifacts.path_join(name))

func _skeleton_of(actor: ReplicatedActor3D) -> Skeleton3D:
	var model: Node = actor.get_node_or_null("NativeModel")
	for node_value: Node in model.find_children("*", "Skeleton3D", true, false):
		return node_value as Skeleton3D
	return null

func _spawn(visuals: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	actor.configure({
		"actor_id": 8200, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "cape", "appearance": {}, "equipment_visuals": visuals,
	}, _adapter, _model_config, _animation_config, _equipment_config)
	actor.server_target = Vector3.ZERO
	actor.global_position = Vector3.ZERO
	actor.rotation.y = 0.0
	return actor

func _settle(actor: ReplicatedActor3D) -> void:
	actor.play_action(&"idle")
	for _f: int in range(30):
		await process_frame
	# A handful of idle frames is not enough physics ticks for the cloth to
	# fall, and how many arrive is up to the frame rate. The solver is stepped
	# by hand instead, the way tests/test_cape_cloth.gd does, so the cape
	# settles in the same place every run.
	var skeleton: Skeleton3D = _skeleton_of(actor)
	var cloth: Node = skeleton.get_node_or_null("CapeCloth")
	if cloth == null or not cloth.active:
		return
	for _step: int in range(120):
		cloth.call("_process_modification_with_delta", 1.0 / 60.0)
	await process_frame
