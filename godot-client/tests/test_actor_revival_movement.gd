extends SceneTree

class TimedActor extends ReplicatedActor3D:
	var clock: Dictionary

	func _movement_time_msec() -> int:
		return int(clock.msec)

var failures := 0
var clock := {"msec": 100000}
var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func fixture(id: int) -> TimedActor:
	var actor := TimedActor.new()
	actor.clock = clock
	actor.actor_id = id
	root.add_child(actor)
	actor.resolver = AnimationResolver.new({
		"actions": {"idle": "Idle", "run": "Run", "death": "Death"},
		"serverCommands": {"3": "death", "7": "idle", "32": "run"}})
	var player := AnimationPlayer.new()
	actor.add_child(player)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var library := AnimationLibrary.new()
	for clip: String in ["Idle", "Run", "Death"]:
		var animation := Animation.new()
		animation.length = 0.1
		animation.loop_mode = Animation.LOOP_NONE if clip == "Death" else Animation.LOOP_LINEAR
		library.add_animation(clip, animation)
	player.add_animation_library("", library)
	actor.animation_player = player
	player.animation_finished.connect(actor._on_animation_finished)
	return actor

func living(id: int) -> Dictionary:
	return {"actor_id": id, "x": 0, "y": id, "rotation": 0,
		"health": 100, "max_health": 100, "alive": true, "command": 7}

func frames(count: int) -> void:
	for _frame: int in range(count):
		await physics_frame
		clock.msec += 17

func run() -> void:
	var actors: Array[TimedActor] = []
	var records: Array[Dictionary] = []
	for id: int in range(4):
		var actor := fixture(id)
		var dto := ActorReducer.apply_command(living(id), 32)
		actor.apply_server_state(dto, adapter, true)
		actors.append(actor)
		records.append(dto)
	await frames(2)
	for wipe: int in range(2):
		for index: int in range(actors.size()):
			records[index] = ActorReducer.apply_command(records[index], 3)
			actors[index].apply_server_state(records[index], adapter)
		await frames(2)
		expect(actors.all(func(actor: TimedActor) -> bool:
			return not actor.is_physics_processing() and actor.current_action == &"death"),
			"a party wipe pauses movement for all four fallen actors")
		clock.msec += 10000
		for index: int in range(actors.size()):
			# Main can coalesce REMOVE + ADD for the same id into an update of
			# the existing body. Both an idle spawn and a folded first run step
			# must release the paused body, without replacing the node.
			records[index] = living(index)
			if index % 2:
				records[index] = ActorReducer.apply_command(records[index], 32)
			actors[index].apply_server_state(records[index], adapter)
		expect(actors.all(func(actor: TimedActor) -> bool: return actor.is_physics_processing()),
			"revival wakes every existing body, including actors that died while moving")
		var largest_jump := 0.0
		var largest_lag := 0.0
		var smooth_steps := true
		for _step: int in range(32):
			for index: int in range(actors.size()):
				var actor := actors[index]
				var before := actor.global_position
				records[index] = ActorReducer.apply_command(records[index], 32)
				actor.apply_server_state(records[index], adapter)
				largest_jump = maxf(largest_jump, actor.global_position.distance_to(before))
			await frames(3)
			for index: int in range(actors.size()):
				var actor := actors[index]
				largest_lag = maxf(largest_lag, actor.global_position.distance_to(actor.server_target))
				smooth_steps = smooth_steps and actor.current_action == &"run"
			await frames(3)
		expect(largest_jump < 0.01, "post-wipe movement never relies on distance-correction teleports")
		expect(largest_lag < 2.5, "revived bodies keep up across 32 running steps (lag %.3f)" % largest_lag)
		expect(smooth_steps, "revived companions retain their running animation")
	for actor: TimedActor in actors:
		actor.free()
	print("Revival movement failures: ", failures)
	quit(1 if failures else 0)
