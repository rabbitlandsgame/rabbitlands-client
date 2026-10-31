extends SceneTree
## Offline authoring only. Run in a task worktree with the supported Godot:
## godot --path godot-client --script res://tools/bake_creation_base_portraits.gd
## Use the shared GPU lock. The game never invokes this baker.
## One actor/stage renders each exact catalog look, then is released before
## the next. Protocol variants are deduplicated by the complete look hash.
const BASES := preload("res://src/ui/creation_base_library.gd")
const STATIC_PORTRAITS := preload("res://src/ui/creation_base_portraits.gd")
const PORTRAIT_RENDERER := preload("res://src/ui/leaderboard_portraits.gd")
const OUTPUT := "res://assets/ui/creation_base_portraits/"
const MANIFEST := "res://data/ui/creation_base_portraits.json"
const SIZE := 512
var renderer: Node
var result: Dictionary = {}
var failures: Array[String] = []

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("Portrait baking needs the real renderer; runtime lookup never bakes portraits.")
		quit(1)
		return
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(MANIFEST.get_base_dir()))
	renderer = PORTRAIT_RENDERER.new()
	root.add_child(renderer)
	renderer.configure(registry,equipment)
	renderer._load_resources()
	renderer._active = true
	renderer._generation = 1
	renderer._create_stage()
	renderer._viewport.size = Vector2i(SIZE,SIZE)
	var total := 0
	var expected_count := -1
	for protocol: int in [3,2,1,0]:
		var rows: Array[Dictionary] = BASES.rows(registry,protocol)
		assert(not rows.is_empty(),"The starting-look catalog is empty.")
		if expected_count < 0:
			expected_count = rows.size()
		assert(rows.size() == expected_count,"Protocol variants must cover the same starting looks.")
		for row: Dictionary in rows:
			var id: String = row.id
			assert(id.is_valid_filename() and not id.contains("/") and not id.contains("\\"))
			var fingerprint: String = STATIC_PORTRAITS.look_hash(row.look)
			var entry: Dictionary = result.get(id,{})
			var same: Dictionary = {}
			var candidates: Array = [entry]
			candidates.append_array(entry.get("variants",[]))
			for candidate: Dictionary in candidates:
				if candidate.get("look_sha256","") == fingerprint:
					same = candidate
					break
			if not same.is_empty():
				same.protocol_versions.append(protocol)
				continue
			# _render owns one actor and frees it after readback. The stage is
			# authoring-only and this is the existing in-game portrait framing.
			# Votary horns rise above the usual human-sized head frame. This
			# moves only the offline camera; runtime previews are unchanged.
			renderer._camera.v_offset = .09 if row.race_id == "votary" else 0.0
			var portrait: Texture2D = await renderer._render(row.look,1)
			if portrait == null:
				failures.append(id+" PC/"+str(protocol))
				continue
			var image := portrait.get_image()
			var path := OUTPUT + id + ("" if protocol == 3 else "_pc%d" % protocol) + ".png"
			assert(image != null and image.get_size() == Vector2i(SIZE,SIZE))
			assert(image.save_png(ProjectSettings.globalize_path(path)) == OK)
			var model_id := str((registry.get("actorTypes",{}) as Dictionary).get(str(int(row.look.actor_type)),""))
			var model: Dictionary = registry.models[model_id]
			var descriptor := {"texture":path,"look_sha256":fingerprint,
				"texture_sha256":FileAccess.get_sha256(path),"protocol_versions":[protocol],
				"dimensions":[SIZE,SIZE],"model":model_id,
				"model_sha256":FileAccess.get_sha256(str(model.scene)),"quality":"High"}
			if entry.is_empty():
				descriptor["variants"] = []
				result[id] = descriptor
			else:
				entry.variants.append(descriptor)
			total += 1
			print("BAKED_STATIC_BASE ",id," PC/",protocol," ",path)
	assert(failures.is_empty(),"Portrait failures: "+str(failures))
	assert(result.size() == expected_count)
	var commit := ""
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--source-commit="):
			commit = argument.trim_prefix("--source-commit=")
	var manifest := {"schema_version":1,"source_commit":commit,
		"baker_sha256":FileAccess.get_sha256("res://tools/bake_creation_base_portraits.gd"),
		"renderer_sha256":FileAccess.get_sha256("res://src/ui/leaderboard_portraits.gd"),
		"catalog_sha256":FileAccess.get_sha256("res://src/ui/creation_base_library.gd"),
		"archetypes_sha256":FileAccess.get_sha256("res://data/actors/rl_head_archetypes.json"),
		"portrait_size":[SIZE,SIZE],"portrait_count":total,
		"lighting":"Existing client portrait key/fill on dark blue background",
		"portraits":result}
	FileAccess.open(MANIFEST,FileAccess.WRITE).store_string(JSON.stringify(manifest,"  ")+"\n")
	renderer.clear()
	renderer.queue_free()
	for frame: int in 6:
		await process_frame
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	print("STATIC_BASE_PORTRAITS_READY ",result.size()," IDs / ",total," images")
	quit()
