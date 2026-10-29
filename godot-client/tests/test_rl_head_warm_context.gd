extends SceneTree
## Bulk render publication follows live screens; CPU parse completion remains
## independent. Fake empty holders exercise lifecycle without compiling meshes.
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
class Context extends RefCounted:
	var allowed := false
	func permits() -> bool: return allowed
var failures := 0
var checks := 0

func _init() -> void: _run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _holder(frames := 0) -> Node3D:
	var holder := Node3D.new()
	holder.name = "RLHeadPipelineWarmupTest"
	holder.set_meta(&"frames", frames)
	root.add_child(holder)
	Library._pipeline_holder = holder
	return holder

func _run() -> void:
	Library.cancel_warm()
	expect(Library.render_warm_allowed(), "standalone calls retain their default permission")
	var context := Context.new()
	Library.set_render_warm_context(context, &"permits")
	Library._texture_queue = PackedStringArray(["context-test-missing.png"])
	Library._pipelines_wanted = true
	Library._poll_warm()
	expect(Library._texture_queue.size() == 1 and Library._pipelines_wanted and not Library.render_warm_active(),
		"denied publication retains queued maps and pending pipelines")
	context.allowed = true
	expect(Library.render_warm_allowed(), "gate reads changed context immediately without a Main process pass")
	Library._poll_warm()
	expect(Library._texture_queue.is_empty(), "an allowed screen can publish the next queued texture")
	context.allowed = false
	var holder := _holder(Library.PIPELINE_WARM_FRAMES - 2)
	Library._texture_queue.clear()
	Library._pipelines_wanted = false
	Library._poll_warm()
	expect(Library.render_warm_active(), "a submitted holder keeps its required settle frames")
	Library._poll_warm()
	expect(not Library.render_warm_active() and Library._pipelines_done,
		"active rendering settles even after permission closes")
	await process_frame
	expect(not is_instance_valid(holder), "settled holder is freed")
	var newer := Context.new()
	Library.set_render_warm_context(newer, &"permits")
	Library.clear_render_warm_context(context)
	expect(not Library.render_warm_allowed(), "an old owner's cleanup cannot clear a newer owner's gate")
	var weak: WeakRef = weakref(newer)
	newer = null
	expect(weak.get_ref() == null, "registered predicate does not retain its RefCounted owner")
	Library._texture_queue = PackedStringArray(["context-test-missing.png"])
	Library._pipelines_wanted = true
	_holder()
	Library._poll_warm()
	expect(not Library.warming() and Library.render_warm_allowed(),
		"an expired owner cancels orphan publication and restores standalone mode")
	await process_frame
	expect(root.find_child("RLHeadPipelineWarmupTest", false, false) == null, "owner expiry leaves no root-level holder")
	await _cpu_under_denied_gate()
	await _main_context()
	Library.cancel_warm()
	print("RL_HEAD_WARM_CONTEXT: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _cpu_under_denied_gate() -> void:
	var context := Context.new()
	Library.set_render_warm_context(context, &"permits")
	var source := Library.head_path("male")
	var absolute := ProjectSettings.globalize_path(source)
	GlbSceneCache._scenes.erase(absolute)
	Library.prewarm(PackedStringArray([source]))
	var deadline := Time.get_ticks_msec() + 20000
	while not GlbSceneCache.missing(PackedStringArray([absolute])).is_empty() and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(GlbSceneCache.missing(PackedStringArray([absolute])).is_empty() and not Library.render_warm_allowed(),
		"CPU worker parsing and finished-scene publication continue under a denied render gate")
	Library.clear_render_warm_context(context)
	Library.clear()

func _main_context() -> void:
	var main: Variant = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var creation := main.creation_panel as Control
	var login := main.login_panel as Control
	var curtain: CanvasLayer = main.arrival_curtain
	creation.set_block_signals(true)
	expect(Library.render_warm_allowed(), "real login context permits publication")
	creation.show()
	expect(not Library.render_warm_allowed(), "creation editing overrides a still-visible login panel")
	creation.hide()
	login.hide()
	expect(not Library.render_warm_allowed(), "ordinary play denies speculative render publication")
	curtain.begin("Warm-up context fixture")
	expect(not Library.render_warm_allowed(), "loading screen must be drawn before heavy publication")
	curtain.set("_drawn_frames", 2)
	expect(Library.render_warm_allowed(), "drawn loading screen permits publication")
	curtain.finish()
	expect(curtain.visible and not Library.render_warm_allowed(), "a fading curtain releases input and closes the gate immediately")
	curtain.begin("Arrival barrier fixture")
	curtain.set("_drawn_frames", 2)
	curtain.set("_began_msec", Time.get_ticks_msec() - int(main.ARRIVAL_CURTAIN_LIMIT_MSEC) - 1)
	var state := root.get_node("AppState")
	var saved := {"authenticated": state.get("authenticated"), "connection_state": state.get("connection_state"),
		"local_actor_id": state.get("local_actor_id")}
	state.set("authenticated", true)
	state.set("connection_state", "connected")
	state.set("local_actor_id", 19002)
	var actor := ReplicatedActor3D.new()
	main.world_root.add_child(actor)
	(main.actor_nodes as Dictionary)[19002] = actor
	(main.get("_grounded_actors") as Dictionary)[19002] = true
	var holder := _holder()
	for frame: int in 4: main.call("_update_arrival")
	expect(curtain.is_showing(), "submitted pipeline warm-up holds arrival even after the ordinary curtain timeout")
	Library._pipeline_holder = null
	holder.free()
	Library._texture_queue = PackedStringArray(["context-test-missing.png"])
	Library._pipelines_wanted = true
	for frame: int in 3: main.call("_update_arrival")
	expect(not curtain.is_showing(), "pending-but-unstarted warm-up does not strand an arrival")
	expect(not Library.render_warm_allowed() and Library._texture_queue.size() == 1 and Library._pipelines_wanted,
		"pending publication stays deferred as arrival releases input")
	for key: String in saved: state.set(key, saved[key])
	var main_weak: WeakRef = weakref(main)
	main.queue_free()
	main = null
	await process_frame
	expect(main_weak.get_ref() == null and not Library.render_warm_snapshot().context_registered \
		and not Library.warming(), "Main teardown clears only its owned context and all queued publication")
