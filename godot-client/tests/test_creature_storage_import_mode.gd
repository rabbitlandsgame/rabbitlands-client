extends SceneTree
## Run in an ignored QA project with an already editor-imported fixture outside
## assets/actors. Arguments: absolute dumper script path, fixture res:// alias.
var checks := 0
func _init() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	assert(value,message)
func run() -> void:
	var arguments := OS.get_cmdline_user_args()
	assert(arguments.size()==2)
	var script: Script = load(arguments[0])
	var path: String = arguments[1]
	check(path.begins_with("res://") and not path.begins_with("res://assets/actors/"),"regression fixture is outside Cache's imported-actor whitelist")
	var imported: Dictionary = script.imported_fixture(path)
	check(imported.errors.is_empty(),"valid editor fixture loads")
	var resource: PackedScene = ResourceLoader.load(path,"PackedScene")
	check(imported.scene==resource,"same actual editor ResourceLoader PackedScene, never a repacked raw fallback")
	check(imported.proof.actual_loader=="ResourceLoader.load(PackedScene)","actual loader recorded")
	check(imported.proof.source_sha256==FileAccess.get_sha256(path),"source hash recorded")
	check(imported.proof.imported_resource_sha256==FileAccess.get_sha256(imported.proof.imported_resource_path),"generated editor resource hash recorded")
	check(not imported.proof.packed_scene_resource_path.is_empty(),"editor scene retains its source resource identity")
	var raw: Node3D = GlbSceneCache.instantiate(path)
	check(raw!=null,"the same alias could silently fall back to raw in the old code")
	var raw_scene: PackedScene = GlbSceneCache._scenes[GlbSceneCache._canonical_path(path)]
	check(raw_scene!=resource and raw_scene.resource_path.is_empty(),"control proves old Cache route is actually RAW at this alias")
	raw.free()
	var directory := "res://.local/storage-import-mode-test-"+str(OS.get_process_id())
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var missing := directory+"/fixture.glb"
	check(DirAccess.copy_absolute(ProjectSettings.globalize_path(path),ProjectSettings.globalize_path(missing))==OK,"negative fixture source retained")
	check(not script.imported_fixture(missing).errors.is_empty(),"missing import policy fails closed")
	var policy := ConfigFile.new()
	policy.set_value("remap","importer","keep")
	policy.save(missing+".import")
	check(not script.imported_fixture(missing).errors.is_empty(),"disabled import fails closed")
	policy.set_value("remap","importer","scene")
	policy.set_value("deps","source_file",missing)
	policy.set_value("remap","path","res://.godot/imported/missing-storage-mode.scn")
	policy.save(missing+".import")
	check(not script.imported_fixture(missing).errors.is_empty(),"missing generated scene rejects instead of returning raw")
	policy.set_value("remap","path",imported.proof.imported_resource_path)
	policy.set_value("deps","source_file",path)
	policy.save(missing+".import")
	check(not script.imported_fixture(missing).errors.is_empty(),"policy for a different source fails closed")
	check(not script.imported_fixture(ProjectSettings.globalize_path(path)).errors.is_empty(),"absolute native paths are not accepted as editor fixtures")
	GlbSceneCache.clear()
	print("CREATURE_STORAGE_IMPORT_MODE_PASS ",checks)
	quit()
