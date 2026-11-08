extends SceneTree
## Catalog metadata admits the exact potential appearance before files exist.
func _initialize() -> void: _run.call_deferred()

func _run() -> void:
	var original := WebPrototype._configuration.duplicate(true)
	var was_loaded := WebPrototype._loaded
	WebPrototype._loaded = true
	WebPrototype._configuration = {}
	WebPrototype._source_path_lists.clear()
	assert(WebPrototype.source_paths("res://assets/actors/native/rl_heads/").is_empty())
	assert(WebPrototype.file_groups(PackedStringArray(["res://missing.glb"])).is_empty())
	WebPrototype._configuration = {"source_groups":{
		"res://assets/actors/native/rl_heads/z.glb":["head:z", "shared"],
		"res://assets/actors/native/rl_heads/a.glb":["head:a", "shared"],
		"res://other.glb":["other"]}}
	WebPrototype._source_path_lists.clear()
	var paths := WebPrototype.source_paths("res://assets/actors/native/rl_heads/")
	assert(paths == PackedStringArray(["res://assets/actors/native/rl_heads/a.glb", "res://assets/actors/native/rl_heads/z.glb"]))
	paths.clear()
	assert(WebPrototype.source_paths("res://assets/actors/native/rl_heads/").size() == 2, "callers cannot mutate cached metadata")
	assert(WebPrototype.file_groups(PackedStringArray(["res://assets/actors/native/rl_heads/a.glb",
		"res://missing.glb", "res://assets/actors/native/rl_heads/z.glb"])) == ["head:a", "shared", "head:z"])
	var previous_heads := OS.get_environment("RL_HEADS")
	OS.set_environment("RL_HEADS", "force")
	ReplicatedActor3D.reload_rl_heads_switch()
	var model := {"culture":"luminous", "bodyTemplate":"luminous_male", "gender":"male"}
	var look := {"hair_module":22, "hair":1, "skin":0, "eyes":0}
	var selected := ReplicatedActor3D.rl_hair_only_files_for(model, look, 1, false)
	assert(not selected.is_empty(), "potential selected hair exists without extraction")
	var source_groups := {}
	for source: String in selected:
		assert(not FileAccess.file_exists(source), "fixture has no extracted head source")
		source_groups[source] = ["selected-head"]
	WebPrototype._configuration = {"source_groups":source_groups}
	assert(WebPrototype.appearance_groups(model, look, 1) == ["selected-head"])
	assert(WebPrototype.appearance_groups({"culture":"other"}, look, 1).is_empty())
	WebPrototype._configuration["groups"] = {"selected":{"dependencies":["shared"]}, "shared":{"dependencies":[]}}
	assert(WebPrototype.group_failure(["selected"], {"failed_groups":["abandoned"], "error":"old style failed"}).is_empty())
	assert(WebPrototype.group_failure(["selected"], {"failed_groups":["shared"], "error":"shared source failed"}) == "shared source failed")
	assert(not WebPrototype.group_failure(["selected"], {"failed_groups":["selected"]}).is_empty())
	WebPrototype._configuration = original
	WebPrototype._loaded = was_loaded
	WebPrototype._source_path_lists.clear()
	OS.set_environment("RL_HEADS", previous_heads)
	ReplicatedActor3D.reload_rl_heads_switch()
	print("browser appearance source metadata, selected missing-file admission and legacy fallback: PASS")
	quit()
