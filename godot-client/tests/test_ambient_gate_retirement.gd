extends SceneTree
## Real modifier callbacks with synthetic bones only. No model or herd restored.
var failures := 0

class CountingModifier extends SkeletonModifier3D:
	var counts: Dictionary = {}
	func _process_modification_with_delta(_delta: float) -> void:
		counts.calls = int(counts.get("calls", 0)) + 1

func _init() -> void:
	call_deferred("_run")

func _animal(parent: Node3D, label: String) -> Dictionary:
	var animal := Node3D.new()
	animal.name = label
	var skeleton := Skeleton3D.new()
	skeleton.add_bone("Root")
	animal.add_child(skeleton)
	var counts := {"calls": 0}
	var modifier := CountingModifier.new()
	modifier.counts = counts
	skeleton.add_child(modifier)
	var player := AnimationPlayer.new()
	animal.add_child(player)
	var animation := Animation.new()
	animation.length = 4.0
	animation.loop_mode = Animation.LOOP_LINEAR
	var track := animation.add_track(Animation.TYPE_VALUE)
	animation.track_set_path(track, NodePath("..:position"))
	animation.track_insert_key(track, 0.0, Vector3.ZERO)
	animation.track_insert_key(track, 4.0, Vector3.RIGHT)
	var library := AnimationLibrary.new()
	library.add_animation("slide", animation)
	player.add_animation_library("", library)
	parent.add_child(animal)
	player.play("slide")
	return {"animal": animal, "skeleton": skeleton, "player": player, "counts": counts}

func _run() -> void:
	var holder := Node3D.new()
	root.add_child(holder)
	var retiring_root := Node3D.new()
	var live_root := Node3D.new()
	holder.add_child(retiring_root)
	holder.add_child(live_root)
	var population := AmbientPopulation.new()
	holder.add_child(population)
	population.set_process(false)
	population.set_physics_process(false)
	population._gate.stagger = false
	var departing := _animal(retiring_root, "Departing")
	var surviving := _animal(live_root, "Surviving")
	population._streamed_samples = [{"model": "synthetic"}, {"model": "synthetic"}]
	population._sample_nodes = {0: departing.animal, 1: surviving.animal}
	population._sample_chunks = {0: "retiring", 1: "retained"}
	for entry: Dictionary in [departing, surviving]:
		population._spawned.append(entry.animal)
		population._track_animated(entry.animal, entry.player)
		population._apply_animal_tier(population._animated.back(), AnimationGate.Tier.HALF)
		(entry.skeleton as Skeleton3D).advance(0.05)
	await _drain()
	_expect(int(departing.counts.calls) > 0 and int(surviving.counts.calls) > 0,
		"both synthetic skeleton modifiers provide a real positive control")
	var departing_calls := int(departing.counts.calls)
	var surviving_calls := int(surviving.counts.calls)
	population._gate.advance(0.125) # First half-rate tick only accumulates.
	var player := surviving.player as AnimationPlayer
	var previous_position := player.current_animation_position
	var group_index: int = int(population._gate._group_of[player])
	var pending := float(population._gate._groups[group_index].delta)
	var gate_tick: int = population._gate._tick
	var departing_player := departing.player as AnimationPlayer
	var departing_skeleton := departing.skeleton as Skeleton3D
	var departing_position := departing_player.current_animation_position
	# Match the chunk stream: it disables its root before emitting retirement.
	retiring_root.process_mode = Node.PROCESS_MODE_DISABLED
	population._on_cell_retiring("retiring", retiring_root)
	_expect(population._spawned == [surviving.animal] and population._animated.size() == 1,
		"retirement removes only the departing population records")
	_expect((departing.animal as Node3D).process_mode == Node.PROCESS_MODE_DISABLED
		and (surviving.animal as Node3D).process_mode == Node.PROCESS_MODE_INHERIT,
		"only the departing animal subtree is quiesced")
	_expect(departing_player.callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		and departing_skeleton.modifier_callback_mode_process == Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL,
		"retirement does not reactivate departing player or modifier callbacks")
	_expect(population._gate.half_rate_count() == 1 and not population._gate._group_of.has(departing_player)
		and int(population._gate._group_of[player]) == group_index
		and population._gate._tick == gate_tick
		and is_equal_approx(float(population._gate._groups[group_index].delta), pending),
		"survivor membership, frame phase and accumulated clock survive retirement")
	for group: Dictionary in population._gate._groups:
		_expect(not (group.members as Dictionary).has(departing_player)
			and departing_skeleton not in (group.members as Dictionary).values(),
			"no departed player or skeleton consumes gate capacity")
	population._gate.advance(0.125)
	await _drain()
	_expect(is_equal_approx(player.current_animation_position, previous_position + 0.25)
		and int(surviving.counts.calls) > surviving_calls,
		"the surviving real modifier advances with all accumulated elapsed time")
	_expect(is_equal_approx(departing_player.current_animation_position, departing_position)
		and int(departing.counts.calls) == departing_calls,
		"the departing modifier receives no new advance or automatic callback")
	retiring_root.queue_free()
	await _drain()
	_expect(not is_instance_valid(departing.animal) and int(departing.counts.calls) == departing_calls,
		"chunk-owned destruction stays quiescent after departure")
	var arriving := _animal(live_root, "Arriving")
	population._spawned.append(arriving.animal)
	population._track_animated(arriving.animal, arriving.player)
	population._apply_animal_tier(population._animated.back(), AnimationGate.Tier.HALF)
	var before_arrival := (arriving.player as AnimationPlayer).current_animation_position
	population._gate.advance(0.1)
	population._gate.advance(0.1)
	await _drain()
	_expect(population._gate.half_rate_count() == 2
		and (arriving.player as AnimationPlayer).current_animation_position > before_arrival
		and int(arriving.counts.calls) > 0,
		"a later animal joins the surviving population and receives real modifier callbacks")
	var survivor_calls_before_clear := int(surviving.counts.calls)
	var arriving_calls_before_clear := int(arriving.counts.calls)
	population.clear()
	_expect(population.pending_creation_count() == 0 and population._animated.is_empty()
		and population._gate.half_rate_count() == 0 and population._gate.quarter_rate_count() == 0
		and population._gate._group_of.is_empty(),
		"full clear discards all creation and animation membership")
	_expect((surviving.animal as Node3D).process_mode == Node.PROCESS_MODE_DISABLED
		and player.callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		and (surviving.skeleton as Skeleton3D).modifier_callback_mode_process == Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL,
		"full clear queues disabled animals without restoring idle callbacks")
	population._gate.advance(1.0)
	await _drain()
	_expect(not is_instance_valid(surviving.animal) and not is_instance_valid(arriving.animal)
		and int(surviving.counts.calls) == survivor_calls_before_clear
		and int(arriving.counts.calls) == arriving_calls_before_clear,
		"queued full-population deletion generates no new modifier work")
	holder.process_mode = Node.PROCESS_MODE_DISABLED
	await _drain()
	holder.queue_free()
	await _drain()
	print("ambient gate retirement: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _drain() -> void:
	await physics_frame
	await process_frame
	await process_frame

func _expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
