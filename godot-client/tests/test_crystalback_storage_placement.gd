extends SceneTree
## Compare complete actor adapters against the immutable pre-pilot model.
## --baseline=<original GLB> --report=<JSON output>
var failures: Array[String] = []

func _init() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message); push_error(message)

func transform_error(a: Transform3D, b: Transform3D) -> float:
	var error := a.origin.distance_to(b.origin)
	for axis in 3: error = maxf(error,a.basis[axis].distance_to(b.basis[axis]))
	return error

func run() -> void:
	var baseline := ""
	var report_path := "user://crystalback-storage-placement.json"
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--baseline="): baseline = argument.trim_prefix("--baseline=")
		if argument.begins_with("--report="): report_path = argument.trim_prefix("--report=")
	var witness: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/completed-creature-motion/crystalback_tortoise.json"))
	check(not baseline.is_empty() and FileAccess.get_sha256(baseline) == witness.reference_sha256,"original reference hash")
	if not failures.is_empty(): quit(1); return
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var players: Array[ReplicatedActor3D] = []
	var maximum := 0.0
	var wild: Array[ReplicatedActor3D] = []
	for source in [baseline,str(registry.crystalback_tortoise.scene)]:
		var models := registry.duplicate(true)
		models.crystalback_tortoise.scene = source
		models.crystalback_tortoise.animationLibrary = source
		var creature := ReplicatedActor3D.new(); root.add_child(creature)
		var config: Dictionary = models.crystalback_tortoise
		check(creature.configure({"actor_id":43,"x":0,"y":0,"rotation":0,"kind":5,"name":""},CoordinateAdapter.new(),config,JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))).is_empty(),"wild actor configures")
		creature.set_process(false); creature.set_physics_process(false); wild.append(creature)
		var actor := ReplicatedActor3D.new(); root.add_child(actor)
		check(actor.configure({"actor_id":42,"x":0,"y":0,"rotation":0,"kind":1,"name":"","equipment_visuals":{2:1}},CoordinateAdapter.new(),models.luminous_male,JSON.parse_string(FileAccess.get_file_as_string(models.luminous_male.animationMap)),equipment).is_empty(),"rider configures")
		actor.set_process(false); actor.set_physics_process(false)
		actor.set_mount_state({"mode":"mounted","mount_id":"crystalback_tortoise","gait":"cruise"},models)
		check(actor._mount_visual != null,"mounted actor configures")
		actor._mount_visual.set_process(false); players.append(actor)
	maximum = maxf(maximum,transform_error(wild[0].get_node("NativeModel").global_transform,wild[1].get_node("NativeModel").global_transform))
	var old_bounds: AABB = wild[0]._native_body_bounds
	var new_bounds: AABB = wild[1]._native_body_bounds
	var bounds_error := maxf(old_bounds.position.distance_to(new_bounds.position),old_bounds.size.distance_to(new_bounds.size))
	check(bounds_error < .000001,"wild body bounds and overhead placement preserved")
	for gait: String in ["idle","walk","cruise","burst"]:
		for frame in 65:
			for actor: ReplicatedActor3D in players:
				var visual: Variant = actor._mount_visual
				visual.state = {"mode":"mounted","mount_id":"crystalback_tortoise","gait":gait}
				actor._presentation_speed = {"idle":0.0,"walk":.5,"cruise":10.0,"burst":20.0}[gait]
				actor.play_action(&"idle" if gait == "idle" else &"run")
				visual._process(0.0)
				visual.elapsed = float(visual.profile.cycleLengths[visual.action])*frame/64.0
				visual._process(0.0)
			var a: Variant = players[0]._mount_visual
			var b: Variant = players[1]._mount_visual
			maximum = maxf(maximum,transform_error(a.pony.get_node("NativeModel").global_transform,b.pony.get_node("NativeModel").global_transform))
			for rigs: Array in [[a.pony.get_skeleton(),b.pony.get_skeleton()],[players[0].get_skeleton(),players[1].get_skeleton()]]:
				for bone in rigs[0].get_bone_count():
					maximum = maxf(maximum,transform_error(rigs[0].global_transform*rigs[0].get_bone_global_pose(bone),rigs[1].global_transform*rigs[1].get_bone_global_pose(bone)))
	check(maximum < .000001,"wild/mounted actor, skeleton and rider transforms preserved")
	var report := {"passed":failures.is_empty(),"failures":failures,"reference_sha256":witness.reference_sha256,"runtime_sha256":witness.sha256,"maximum_transform_error":maximum,"body_bounds_error":bounds_error,"mounted_samples":260}
	FileAccess.open(report_path,FileAccess.WRITE).store_string(JSON.stringify(report,"\t"))
	for actor: ReplicatedActor3D in players + wild: actor.free()
	NativeAnimationImporter.clear(); GlbSceneCache.clear()
	print("CRYSTALBACK_STORAGE_PLACEMENT ",JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
