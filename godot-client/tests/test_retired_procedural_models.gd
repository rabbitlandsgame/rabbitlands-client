extends SceneTree
## Real actor/object/cache paths: retired IDs must never resurrect old visuals.
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
var failures: Array[String] = []

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error(message)

func _run() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var retired_index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ArchivedModelPolicy.INDEX))
	var checked := 0
	for relative: String in retired_index.runtimePaths:
		var path := "res://assets/" + relative
		check(ArchivedModelPolicy.is_retired_path(path), "retired resource path " + relative)
		check(ArchivedModelPolicy.is_retired_path(ProjectSettings.globalize_path(path)), "retired absolute path " + relative)
		check(GlbSceneCache.instantiate(path) == null, "cache refuses retired visual " + relative)
		checked += 1
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	for identity: String in retired_index.retiredActorModels:
		check(not registry.models.has(identity), identity + " definition removed")
	for identity: Variant in retired_index.retiredActorTypes:
		check(not registry.actorTypes.has(str(int(identity))), "retired actor mapping removed")
	for identity: String in retired_index.retiredEquipmentKeys:
		check(not equipment.models.has(identity), "retired equipment definition removed")
	# A stale server packet must not recreate a substitute for a removed definition.
	for actor_type: int in [215, 233, 785]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 7, "actor_type": actor_type, "kind": 2,
			"x": 0, "y": 0, "rotation": 0, "name": "stale"}, adapter, {}, {}, equipment)
		check(errors.is_empty(), "stale actor clean retirement")
		check(actor.has_meta("retired_model"), "stale actor retirement marker")
		check(actor.find_child("MissingModelFallback", true, false) == null, "stale actor no substitute body")
		check(actor.find_children("*", "Skeleton3D", true, false).is_empty(), "stale actor no model skeleton")
		actor.free()
	var current: Dictionary = registry.models.moss_bear
	check(not bool(current.get("retired", false)), "updated Moss Bear remains active")
	check(not ArchivedModelPolicy.is_retired_path(current.scene), "updated model allowed")
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var map: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(current.animationMap))
	var errors := actor.configure({"actor_id": 8, "actor_type": 564, "kind": 2,
		"x": 0, "y": 0, "rotation": 0, "name": "Moss Bear"}, adapter, current, map, equipment)
	check(errors.is_empty(), "current Moss Bear actor config " + str(errors))
	check(actor.animation_player != null and actor.animation_player.has_animation("Walk"), "approved gait still plays")
	actor.call("_create_equipment_part", 0, 64, true)
	check(actor.find_child("RetiredEquipment_0_64", true, false) != null, "stale equipment reserves lifecycle slot")
	check(actor.find_children("*Fallback*", "MeshInstance3D", true, false).is_empty(), "retired equipment does not create fallback geometry")
	actor.free()
	var object := MapObject3D.new()
	root.add_child(object)
	var height: float = object.call("_add_model", {"id": "retired_prop", "retired": true, "height": 2.0})
	check(is_equal_approx(height, 2.0), "retired service retains pick extent")
	check(object.get_child_count() == 0, "retired service has no model visual")
	object.free()
	# Parse a real baked copy, then verify scene generation has no retired mesh.
	var inline_checked := false
	for relative: String in retired_index.get("mapMeshCopies", {}):
		if not relative.begins_with("eloria-assets/maps/_shared/meshes/"): continue
		var copy_path := ProjectSettings.globalize_path("res://../" + relative)
		var document := GLTFDocument.new()
		var state := GLTFState.new()
		preload("res://src/world/gltf_quantization.gd").ensure_registered()
		check(document.append_from_file(copy_path, state) == OK, "real baked scenery copy parses")
		check(ArchivedModelPolicy.apply_to_gltf_state(state, copy_path) > 0, "baked procedural geometry suppressed")
		var generated := document.generate_scene(state)
		check(generated != null, "filtered scenery scene remains valid")
		if generated != null:
			check(generated.find_children("*", "MeshInstance3D", true, false).is_empty(), "retired baked mesh not rendered")
			generated.free()
		inline_checked = true
		break
	check(inline_checked, "actual baked-copy fixture checked")
	# Exercise the real package loader, including batching and scene attachment.
	var loader := WorldLoader.new()
	loader.detached_build = true
	loader.detached_cache_enabled = false
	root.add_child(loader)
	loader.load_world("res://../eloria-assets/maps/nymara-regions/ssarathi_ruins/chunks/12_17/world.json")
	check(loader.world_root != null, "real filtered map package loads")
	if loader.world_root != null:
		for identity: String in ["Secret_ruins_moss_hollow__timber_dark", "Secret_ruins_rootrun__timber_dark"]:
			var retained := loader.world_root.find_child(identity, true, false)
			check(retained != null, "retired scenery placement retains map identity")
			check(not retained is MeshInstance3D, "package does not draw retired scenery")
	loader.free()
	var pool := preload("res://src/world/external_mesh_pool.gd")
	for identity: String in retired_index.get("retiredMapPrototypes", []):
		check(pool.acquire(identity, "unused") == null, "pooled retired model refused")
	check(not ArchivedModelPolicy.cache_token().is_empty(), "retirement invalidates older scene caches")
	var report := {"passed": failures.is_empty(), "failures": failures,
		"retired_runtime_paths_checked": checked,
		"baked_copy_checked": inline_checked,
		"real_map_loader_checked": true,
		"scope": "Current scene cache, actor configuration, equipment lifecycle and service model path; no archived visuals or generated body fallback. Updated Moss Bear actor still configures."}
	var output := "user://procedural-retirement.json"
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="): output = argument.trim_prefix("--report=")
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("PROCEDURAL_RETIREMENT ", "PASS" if failures.is_empty() else "FAIL", " paths=", checked)
	quit(0 if failures.is_empty() else 1)
