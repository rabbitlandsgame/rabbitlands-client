extends SceneTree
var failures := 0
func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
func run() -> void:
	var previous_prepared_mode := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var config: Dictionary = registry.models.rabbit
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var warmup := preload("res://src/actors/actor_resource_warmup.gd").new()
	expect(not warmup.request(config, animation), "cold request queues preparation")
	var deadline := Time.get_ticks_msec() + 20000
	while not warmup.request(config, animation) and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(warmup.request(config, animation), "queued creature preparation completes")
	expect(GlbSceneCache.cached_scene_count() > 0, "geometry published into the actual session cache")
	var libraries := NativeAnimationImporter.cached_library_count()
	expect(libraries > 0, "immutable retargeted clips published before actor construction")
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var configure_started := Time.get_ticks_usec()
	var errors := actor.configure({"actor_id": 32000, "actor_type": 200, "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND,
		"name": "Rabbit", "x": 0, "y": 0, "rotation": 0},
		CoordinateAdapter.new({"metresPerTile": 1.0}), config, animation)
	print("prepared rabbit main-thread configure_ms=", (Time.get_ticks_usec() - configure_started) / 1000.0)
	expect(errors.is_empty(), "prepared actor configures without import errors")
	expect(NativeAnimationImporter.cached_library_count() == libraries,
		"real actor reuses the prepared key rather than retargeting synchronously")
	expect(actor.animation_player != null and actor.animation_player.has_animation("RESET"),
		"prepared actor retains playback and RESET")
	actor.free()
	# Exercise Main's real session boundary, not only the loader's clear API.
	var main: Variant = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.actor_resource_warmup = warmup
	root.add_child(main)
	for frame: int in 4: await process_frame
	main._clear_world_presentation(true)
	expect(warmup.request(config, animation),
		"reconnect retaining map resources preserves completed creature preparation")
	main._clear_world_presentation(false)
	expect(NativeAnimationImporter.cached_library_count() == 0 and GlbSceneCache.cached_scene_count() == 0,
		"leaving a session clears both actor resource caches")
	expect(not warmup.request(config, animation),
		"after session caches clear, a previously completed creature queues fresh preparation")
	# Clearing an active job serves frames until it can be joined, with no
	# stale publication or live Thread left behind at shutdown.
	warmup.clear()
	while not warmup.is_idle():
		await process_frame
	expect(NativeAnimationImporter.cached_library_count() == 0 and GlbSceneCache.cached_scene_count() == 0,
		"clearing an active job discards completion instead of repopulating session caches")
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	main.queue_free()
	await process_frame
	print("actor resource warmup: ", failures, " failures")
	if previous_prepared_mode.is_empty():
		OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else:
		OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_prepared_mode)
	quit(failures)
