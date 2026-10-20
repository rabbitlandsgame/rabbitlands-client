extends SceneTree
## Exercise actual network interpolation, independently of the gait clip clock.
class TimedActor extends ReplicatedActor3D:
	var clock_msec := 100000
	func _movement_time_msec() -> int: return clock_msec

var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var adapter := CoordinateAdapter.new({"metresPerTile":1.0,"walkingHeight":0.0})
	var config: Dictionary = models.luminous_male
	for mount_id: String in preload("res://src/mounts/mount_profiles.gd").PATHS:
		for step_us: int in [133333,100000,50000]:
			var actor := TimedActor.new()
			root.add_child(actor)
			check(actor.configure({"actor_id":42,"x":0,"y":0,"rotation":0,"kind":1,"name":""},
				adapter,config,JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))).is_empty(), "rider loads")
			actor.set_process(false)
			actor.set_physics_process(false)
			actor.set_mount_state({"mode":"mounted","mount_id":mount_id,"gait":"burst" if step_us <= 100000 else "cruise",
				"step_us":step_us}, models)
			actor._mount_visual.set_process(false)
			actor.apply_server_state({"x":0,"y":0,"command":22,"rotation":0},adapter,true)
			var start := Vector3.ZERO
			var finish := Vector3.ZERO
			for step: int in range(1,81):
				# Walking commands remain legal while mounted; the authoritative
				# mount snapshot must supply the same speed as running commands.
				actor.apply_server_state({"x":step,"y":0,"command":22 if step < 40 else 32,"rotation":0},adapter)
				for frame: int in 5:
					actor.clock_msec = 100000 + int(round(((step - 1) + (frame + 1) / 5.0) * step_us / 1000.0))
					actor._physics_process(step_us / 5000000.0)
				if step == 20: start = actor.global_position
				if step == 80: finish = actor.global_position
				check(actor.global_position.distance_to(actor.server_target) < 1.0, "mounted travel never accumulates route lag")
			var speed := start.distance_to(finish) / (60.0 * step_us / 1000000.0)
			check(absf(speed - 1000000.0 / step_us) < .01, mount_id + " retains server ground speed")
			actor.set_mount_state({},models)
			check(is_equal_approx(actor._pace_for_gait(1), actor.initial_run_interval), "dismount restores on-foot pace")
			actor.free()
	print("MOUNT_MOVEMENT_CHECKS ",checks," failures=",failures)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)
