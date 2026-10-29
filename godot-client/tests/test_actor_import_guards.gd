extends SceneTree
## A skipped loose-native folder may retain an otherwise usable editor remap.
## Exercise the real remap preflight with a tiny isolated PackedScene product.
var checks := 0
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)

func _run() -> void:
	var directory := "user://actor-import-guard-%d-%d" % [OS.get_process_id(), Time.get_ticks_usec()]
	var child := directory.path_join("nested")
	var source := child.path_join("fixture.glb")
	var product := directory.path_join("fixture.tscn")
	var guard := directory.path_join(".gdignore")
	expect(DirAccess.make_dir_recursive_absolute(child) == OK, "isolated fixture folder created")
	var node := Node3D.new()
	node.name = "ImportedFixture"
	var scene := PackedScene.new()
	expect(scene.pack(node) == OK and ResourceSaver.save(scene, product) == OK,
		"retained editor product is an actual PackedScene")
	node.free()
	var file := FileAccess.open(source, FileAccess.WRITE)
	expect(file != null, "fixture source exists independently of its remap")
	if file != null:
		file.store_string("fixture source is not parsed through the remap preflight")
		file.close()
	var settings := ConfigFile.new()
	settings.set_value("remap", "importer", "scene")
	settings.set_value("remap", "type", "PackedScene")
	settings.set_value("remap", "path", product)
	expect(settings.save(source + ".import") == OK, "retained scene import metadata written")
	expect(GlbSceneCache._editor_import_path(source) == product,
		"an unguarded eligible scene remap remains available")
	expect(GlbSceneCache._imported_actor_scene(source) == null,
		"test remap eligibility does not expand the actor-only import whitelist")
	var loaded := ResourceLoader.load(product, "PackedScene") as PackedScene
	expect(loaded != null, "the remapped product is readable before a guard is installed")
	file = FileAccess.open(guard, FileAccess.WRITE)
	expect(file != null, "ancestor loose-native guard created")
	if file != null:
		file.store_string("# This source is read raw at runtime.\n")
		file.close()
	expect(FileAccess.file_exists(source + ".import") and FileAccess.file_exists(product),
		"old import metadata and product are retained under the guard")
	expect(GlbSceneCache._editor_import_path(source).is_empty(),
		"ancestor guard rejects a retained scene remap instead of bypassing the raw policy")
	expect(DirAccess.remove_absolute(guard) == OK, "owned fixture guard removed")
	expect(GlbSceneCache._editor_import_path(source) == product,
		"removing the owned guard restores normal imported eligibility")
	settings.set_value("remap", "importer", "keep")
	settings.save(source + ".import")
	expect(GlbSceneCache._editor_import_path(source).is_empty(),
		"an explicitly skipped import still takes the raw fallback")
	settings.set_value("remap", "importer", "scene")
	settings.set_value("remap", "path", directory.path_join("missing.scn"))
	settings.save(source + ".import")
	expect(GlbSceneCache._editor_import_path(source).is_empty(),
		"an unfinished import still takes the raw fallback")
	loaded = null
	scene = null
	for path: String in [source + ".import", source, product]:
		expect(DirAccess.remove_absolute(path) == OK, "owned fixture file removed: " + path.get_file())
	expect(DirAccess.remove_absolute(child) == OK, "owned child folder removed")
	expect(DirAccess.remove_absolute(directory) == OK, "owned fixture folder removed")
	print("ACTOR_IMPORT_GUARDS: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
