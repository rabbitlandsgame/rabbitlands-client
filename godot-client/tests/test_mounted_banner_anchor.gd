extends SceneTree
## Exercise real mounted animation while measuring the banner's world and screen anchors.
const Profiles := preload("res://src/mounts/mount_profiles.gd")
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		if failures < 8:
			push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.position = Vector3(6.0, 7.0, 10.0)
	camera.look_at(Vector3(0.0, 2.0, 0.0))
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = models[body]
		var errors := actor.configure({"actor_id": 42, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": "Rider"}, CoordinateAdapter.new({"walkingHeight": 0.0}), config,
			JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
		expect(errors.is_empty(), body + " rider loads")
		actor.set_process(false)
		actor.set_physics_process(false)
		var standing_height := actor.banner_head_height()
		for mount_id: String in Profiles.PATHS:
			actor.set_mount_state({"mode": "mounted", "mount_id": mount_id, "gait": "walk"}, models)
			expect(is_instance_valid(actor._mount_visual), mount_id + " mounts")
			if not is_instance_valid(actor._mount_visual):
				continue
			var visual: Variant = actor._mount_visual
			visual.set_process(false)
			var height := actor.banner_head_height()
			expect(height > standing_height, mount_id + " banner is raised above its seated rider")
			var anchor := actor.global_position + Vector3.UP * height
			var screen := camera.unproject_position(anchor)
			var minimum_body_height := INF
			var maximum_body_height := -INF
			for gait: String in ["idle", "walk", "cruise", "burst", "idle"]:
				actor.set_mount_state({"mode": "mounted", "mount_id": mount_id, "gait": gait}, models)
				actor._presentation_speed = 3.75
				actor.play_action(&"idle" if gait == "idle" else &"run", true)
				for sample: int in 90:
					visual._process(1.0 / 30.0)
					minimum_body_height = minf(minimum_body_height, actor.head_height())
					maximum_body_height = maxf(maximum_body_height, actor.head_height())
					var current_anchor := actor.global_position + Vector3.UP * actor.banner_head_height()
					expect(current_anchor.is_equal_approx(anchor), mount_id + " " + gait + " fixed banner height")
					expect(camera.unproject_position(current_anchor).distance_to(screen) < .001,
						mount_id + " " + gait + " steady projected banner")
					expect(is_equal_approx(actor.get_node("Nameplate").position.y,
						height + ReplicatedActor3D.NAMEPLATE_CLEARANCE), mount_id + " remote overhead stays steady")
			expect(maximum_body_height - minimum_body_height > .01, mount_id + " rider still bobs with the saddle")
			var travel := Vector3(2.0, .5, -1.0)
			actor.position += travel
			actor.rotation.y += .8
			visual._process(1.0 / 30.0)
			expect((actor.global_position + Vector3.UP * actor.banner_head_height()).is_equal_approx(anchor + travel),
				mount_id + " banner follows actual travel and terrain height")
			actor.position -= travel
			print("MOUNTED_BANNER_ANCHOR ", body, " ", mount_id, " height=", height,
				" body_bob=", maximum_body_height - minimum_body_height)
		actor.set_mount_state({}, models)
		expect(is_equal_approx(actor.banner_head_height(), standing_height), body + " dismount restores standing anchor")
		expect(is_equal_approx(actor.get_node("Nameplate").position.y,
			standing_height + ReplicatedActor3D.NAMEPLATE_CLEARANCE), body + " dismount restores overhead height")
		actor.free()
	camera.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("MOUNTED_BANNER_ANCHOR_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
