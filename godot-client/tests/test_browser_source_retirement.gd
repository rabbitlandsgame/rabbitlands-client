extends SceneTree

func _initialize() -> void: call_deferred("_run")

func _run() -> void:
	var path := "res://assets/browser_cache_test.glb"
	var other := "res://assets/other_cache_test.glb"
	var physical := ProjectSettings.globalize_path(path)
	var original := Node3D.new()
	var child := MeshInstance3D.new()
	child.mesh = BoxMesh.new()
	original.add_child(child)
	child.owner = original
	var template := PackedScene.new()
	assert(template.pack(original) == OK)
	original.free()
	var live := template.instantiate()
	root.add_child(live)
	GlbSceneCache._scenes[path] = template
	GlbSceneCache._scenes[other] = template
	GlbSceneCache._failed[path] = true
	GlbSceneCache.release_sources(PackedStringArray([physical]))
	assert(not GlbSceneCache._scenes.has(path) and not GlbSceneCache._failed.has(path))
	assert(GlbSceneCache._scenes.has(other))
	assert(is_instance_valid(live.get_child(0).mesh), "live instances retain their mesh")
	var library := AnimationLibrary.new()
	var player := AnimationPlayer.new()
	root.add_child(player)
	player.add_animation_library("retained", library)
	NativeAnimationImporter._libraries[path + "|fixture"] = {"library":library}
	NativeAnimationImporter._sources[path] = Node3D.new()
	assert(NativeAnimationImporter.release_sources(PackedStringArray([physical])))
	assert(not NativeAnimationImporter._sources.has(path))
	assert(not NativeAnimationImporter._libraries.has(path + "|fixture"))
	assert(player.get_animation_library("retained") == library)
	var worker := Thread.new()
	assert(worker.start(func() -> Variant: OS.delay_msec(200); return null) == OK)
	NativeAnimationImporter._prewarming[path] = worker
	assert(not NativeAnimationImporter.release_sources(PackedStringArray([physical])), "running workers are never joined")
	var deadline := Time.get_ticks_msec() + 5000
	while worker.is_alive() and Time.get_ticks_msec() < deadline:
		await process_frame
	assert(NativeAnimationImporter.release_sources(PackedStringArray([physical])))
	GlbSceneCache._scenes.erase(other)
	live.free()
	player.free()
	print("browser parsed-source retirement: PASS")
	quit()
