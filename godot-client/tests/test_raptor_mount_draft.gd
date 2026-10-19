extends SceneTree
const Draft := preload("res://src/dev/raptor_mount_draft.gd")
const Profiles := preload("res://src/mounts/mount_profiles.gd")
var checks := 0
var failures := 0
var max_rider_error := 0.0
var max_cape_error := 0.0
var min_sole := INF
var max_all_paw_clearance := 0.0
var mesh: MeshInstance3D
var bind_bones := PackedInt32Array()
var arrays: Array
var fixture: Dictionary
var sole_indices: Dictionary = {}

func _init() -> void: call_deferred("run")

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		if failures < 8: push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	fixture = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/raptor_mount_soles.json"))
	check(FileAccess.get_sha256(models.jadefeather_raptor.scene) == fixture.sourceSha256, "uses the current roster-pinned raptor source")
	check(not Profiles.supports("jadefeather_raptor"), "draft does not enable a live catalogue entry")
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id":42,"x":10,"y":20,"rotation":0,"kind":1,"name":"", "equipment_visuals":{2:1}},
			CoordinateAdapter.new(),models[body],JSON.parse_string(FileAccess.get_file_as_string(models[body].animationMap)),equipment)
		check(errors.is_empty(), "equipped rider loads")
		actor.set_process(false)
		actor.set_physics_process(false)
		var authority := actor.global_transform
		var native := actor.get_node("NativeModel") as Node3D
		var original := native.transform
		check(Draft.attach(actor, models).is_empty(), "raptor mount draft configures")
		var visual: Variant = actor._mount_visual
		visual.set_process(false)
		check(visual.pony.rig_name() == "jadefeather_raptor" and visual.locomotion == null, "uses unchanged native raptor and its original clips")
		check(visual.tack.triangle_count == 638, "reuses the complete imported pony saddle")
		mesh = visual.pony.get_node("NativeModel").find_children("*","MeshInstance3D",true,false)[0] as MeshInstance3D
		arrays = mesh.mesh.surface_get_arrays(0)
		bind_bones.clear()
		var sk: Skeleton3D = visual.pony.get_skeleton()
		for bind: int in mesh.skin.get_bind_count():
			var bone := sk.find_bone(mesh.skin.get_bind_name(bind))
			bind_bones.append(bone if bone >= 0 else mesh.skin.get_bind_bone(bind))
		# The editor reorders vertices. Resolve the fixed anatomical witnesses
		# by exact rest position and include every coincident imported seam.
		var lookup := {}
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for index: int in vertices.size():
			if not lookup.has(vertices[index]): lookup[vertices[index]] = []
			lookup[vertices[index]].append(index)
		sole_indices.clear()
		for leg: String in fixture.soles:
			var unique := {}
			for id: int in fixture.soles[leg]:
				var reference: Array = fixture.referencePositions[str(id)]
				var matches: Array = lookup.get(Vector3(reference[0],reference[1],reference[2]), [])
				check(not matches.is_empty(), "qualified sole patch resolves in the actual engine mesh")
				for index: int in matches: unique[index] = true
			sole_indices[leg] = PackedInt32Array(unique.keys())
		for gait: String in ["idle","cruise","burst"]:
			Draft.pace(actor, gait)
			actor._presentation_speed = {"idle":0.0,"cruise":10.0,"burst":20.0}[gait]
			actor.play_action(&"idle" if gait == "idle" else &"run", true)
			visual._process(0.0)
			visual.elapsed = 0.0
			for frame: int in 180:
				visual._process(1.0 / 60.0)
				check(actor.global_transform.is_equal_approx(authority), "riding keeps network and camera placement stable")
				for error: float in visual.pose.last_errors.values(): max_rider_error = maxf(max_rider_error,error)
				var all_low := INF
				for ids: PackedInt32Array in sole_indices.values():
					for id: int in ids:
						var local := actor.to_local(_skin(sk,id))
						min_sole = minf(min_sole,local.y)
						all_low = minf(all_low,local.y)
				max_all_paw_clearance = maxf(max_all_paw_clearance,all_low)
				for chain: int in 3:
					var points: PackedVector3Array = actor._cape_cloth.get("_points")[chain]
					var lengths: PackedFloat32Array = actor._cape_cloth.get("_lengths")[chain]
					for link: int in range(1,points.size()):
						max_cape_error = maxf(max_cape_error,absf(points[link].distance_to(points[link-1])-lengths[link-1]))
				for side: String in ["l","r"]:
					var points: PackedVector3Array = visual.reins.last_points[side]
					check(visual.reins.to_global(points[-1]).distance_to(visual.reins.grip_world(actor.get_skeleton(),side)) < .00001,
						"harness reins stay in the riding hands")
		actor.set_mount_state({},models)
		check(native.transform.is_equal_approx(original), "dismount restores the on-foot visual")
		actor.free()
	check(max_rider_error < .06, "rider seat, hands and feet reach their targets")
	check(max_cape_error < .02, "cape keeps its authored material length")
	check(min_sole > -.006, "actual skinned paw soles stay above the floor at mount scale")
	check(max_all_paw_clearance > .01, "the native gait has a visible recovery phase")
	var report := {"checks":checks,"failures":failures,"max_rider_contact_error_metres":max_rider_error,
		"max_cape_link_error_metres":max_cape_error,"min_paw_sole_height_metres":min_sole,
		"max_all_paw_ground_clearance_metres":max_all_paw_clearance}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			FileAccess.open(argument.trim_prefix("--report="),FileAccess.WRITE).store_string(JSON.stringify(report,"  "))
	print("RAPTOR_MOUNT_DRAFT_CHECKS ",JSON.stringify(report))
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)

func _skin(sk: Skeleton3D, index: int) -> Vector3:
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var count := joints.size() / points.size()
	var point := Vector3.ZERO
	for slot: int in count:
		var at := index * count + slot
		if weights[at] > 0.0:
			var bind := joints[at]
			point += sk.global_transform * sk.get_bone_global_pose(bind_bones[bind]) * mesh.skin.get_bind_pose(bind) * points[index] * weights[at]
	return point
