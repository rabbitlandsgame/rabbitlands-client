extends SceneTree
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = models[body]
		var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
		var errors := actor.configure({"actor_id": 42, "x": 120, "y": 70, "rotation": 0,
			"kind": 1, "name": "PonyTest", "appearance": {"skin": 0, "hair": 0, "eyes": 0,
			"shirt": 0, "pants": 0, "boots": 0, "head": 0}, "equipment_visuals": {}}, CoordinateAdapter.new(), config, mapping)
		expect(errors.is_empty(), body + " actual character loads " + str(errors))
		if not errors.is_empty():
			await _retire_fixtures([actor])
			continue
		actor.rotation.y = 1.1
		var authoritative := actor.global_transform
		var native := actor.get_node("NativeModel") as Node3D
		var original := native.transform
		var skeleton := actor.get_skeleton()
		var meshes := native.find_children("*", "MeshInstance3D", true, false)
		for gait: String in ["walk", "cruise", "burst"]:
			actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": gait, "step_us": 200000}, models)
			expect(is_instance_valid(actor._mount_visual), body + " mounts")
			if not is_instance_valid(actor._mount_visual):
				continue
			expect(actor.get_skeleton() == skeleton and native.find_children("*", "MeshInstance3D", true, false) == meshes, "same character and wardrobe remain")
			actor.play_action(&"run")
			actor._presentation_speed = 3.75
			var visual := actor._mount_visual
			for sample: int in range(30):
				visual.call("_process", 1.0 / 60.0)
				expect(actor.global_transform.is_equal_approx(authoritative), "mount does not move server actor or camera target")
				var pose: RefCounted = visual.get("pose")
				var measurements: Dictionary = pose.get("last_errors")
				for key: String in measurements:
					expect(float(measurements[key]) < .06, body + " " + gait + " contact " + key + " " + str(measurements[key]))
			# Check the actual clip clock at the same travel speed: halve only
			# trot cadence, retaining the walk/gallop timing and server position.
			var stride: float = {"walk": .5625018284987413, "cruise": 1.4545501827846241, "burst": 3.7500121899916086}[gait]
			var expected_elapsed := .5 * 3.75 / stride * (.5 if gait == "cruise" else 1.0)
			expect(absf(float(visual.get("elapsed")) - expected_elapsed) < .0001, body + " " + gait + " actual playback cadence")
			var pony: ReplicatedActor3D = visual.get("pony")
			var clip := "Walk" if gait == "walk" else ("Jog" if gait == "cruise" else "Gallop")
			var clip_time := fposmod(expected_elapsed, pony.animation_player.get_animation(clip).length)
			expect(absf(pony.animation_player.current_animation_position - clip_time) < .0001, body + " " + gait + " rendered animation matches cadence")
			expect((visual.get("reins") as Node3D).visible, "visible reins on live player")
			actor.set_mount_state({}, models)
			expect(not is_instance_valid(actor._mount_visual), "dismount removes pony")
			expect(native.transform.is_equal_approx(original), "dismount restores exact native root")
			expect(actor.animation_player.is_playing(), "normal animation resumes")
		await _retire_fixtures([actor])
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await _drain()
	print("MOUNTED_PLAYER_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)

func _retire_fixtures(actors: Array[ReplicatedActor3D]) -> void:
	for actor: ReplicatedActor3D in actors:
		actor.process_mode = Node.PROCESS_MODE_DISABLED
	await _drain()
	for actor: ReplicatedActor3D in actors:
		actor.queue_free()
	await _drain()

func _drain() -> void:
	await physics_frame
	await process_frame
	await process_frame
