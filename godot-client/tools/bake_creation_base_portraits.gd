extends SceneTree
## Offline authoring only. Run in a task worktree with the supported Godot:
## godot --path godot-client --script res://tools/bake_creation_base_portraits.gd
## Use the shared GPU lock. The game never invokes this baker.
## One actor/stage renders each exact catalog look, then is released before
## the next. Protocol variants are deduplicated by the complete look hash.
const BASES := preload("res://src/ui/creation_base_library.gd")
const STATIC_PORTRAITS := preload("res://src/ui/creation_base_portraits.gd")
const PORTRAIT_RENDERER := preload("res://src/ui/leaderboard_portraits.gd")
const PC := preload("res://src/actors/portrait_customization.gd")
const OUTPUT := "res://assets/ui/creation_base_portraits/"
const MANIFEST := "res://data/ui/creation_base_portraits.json"
const SIZE := 512
var renderer: Node
var result: Dictionary = {}
var failures: Array[String] = []

func dependency_files(folder: String) -> Array[String]:
	var result: Array[String] = []
	for name: String in DirAccess.get_files_at(folder):
		if name.get_extension() in ["gd", "gdshader", "json", "glb", "png", "import"]:
			result.append(folder.path_join(name))
	for name: String in DirAccess.get_directories_at(folder):
		if not name.begins_with("."):
			result.append_array(dependency_files(folder.path_join(name)))
	return result

func render_dependencies() -> String:
	var files: Array[String] = ["res://src/ui/leaderboard_portraits.gd",
		"res://tools/bake_creation_base_portraits.gd",
		"res://data/actors/models.json", "res://data/actors/equipment.json"]
	for folder: String in ["res://src/actors", "res://data/actors", "res://assets/actors/native/rl_heads",
			"res://assets/actors/native/rl_head_textures", "res://assets/actors/native/race_textures/luminous_female",
			"res://assets/actors/native/race_textures/luminous_male", "res://assets/actors/native/neck_textures"]:
		files.append_array(dependency_files(folder))
	for file: String in ["luminous_female.glb", "luminous_male.glb"]:
		files.append("res://assets/actors/native/races/" + file)
	files.sort()
	var hashes := {}
	for file: String in files:
		hashes[file] = FileAccess.get_sha256(file)
	return JSON.stringify(hashes, "", true).sha256_text()

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("Portrait baking needs the real renderer; runtime lookup never bakes portraits.")
		quit(1)
		return
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var dependencies := render_dependencies()
	# Preserve art for temporarily disabled bodies. Reuse an enabled portrait
	# only when both its complete look and the image bytes still match.
	var previous: Variant = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST))
	var retained: Dictionary = previous.get("portraits", {}) if previous is Dictionary else {}
	var enabled: Dictionary = {}
	for row: Dictionary in BASES.rows(registry, PC.LATEST):
		enabled[str(row.id)] = true
	for id: String in retained:
		if not enabled.has(id):
			result[id] = retained[id].duplicate(true)
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
	var reused := 0
	var expected_count := -1
	for protocol: int in range(PC.LATEST, -1, -1):
		var rows: Array[Dictionary] = BASES.rows(registry,protocol)
		assert(not rows.is_empty(),"The starting-look catalog is empty.")
		if expected_count < 0:
			expected_count = rows.size()
		assert(rows.size() == expected_count,"Protocol variants must cover the same starting looks.")
		for row: Dictionary in rows:
			var id: String = row.id
			assert(id.is_valid_filename() and not id.contains("/") and not id.contains("\\"))
			var model_id := str((registry.get("actorTypes",{}) as Dictionary).get(str(int(row.look.actor_type)),""))
			var model: Dictionary = registry.models[model_id]
			var model_hash := FileAccess.get_sha256(str(model.scene))
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
			var old: Dictionary = retained.get(id, {})
			var old_candidates: Array = [old]
			old_candidates.append_array(old.get("variants", []))
			for candidate: Dictionary in old_candidates:
				var image_path := str(candidate.get("texture", ""))
				if candidate.get("look_sha256", "") == fingerprint \
						and str(candidate.get("render_dependencies_sha256", "")) == dependencies \
						and str(candidate.get("model_sha256", "")) == model_hash \
						and image_path.begins_with(OUTPUT) and image_path.ends_with(".png") \
						and FileAccess.file_exists(image_path) \
						and FileAccess.get_sha256(image_path) == str(candidate.get("texture_sha256", "")):
					same = candidate.duplicate(true)
					same.erase("variants")
					same["protocol_versions"] = [protocol]
					break
			if not same.is_empty():
				if entry.is_empty():
					same["variants"] = []
					result[id] = same
				else:
					entry.variants.append(same)
				reused += 1
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
			var path := OUTPUT + id + ("" if protocol == PC.LATEST else "_pc%d" % protocol) + ".png"
			assert(image != null and image.get_size() == Vector2i(SIZE,SIZE))
			assert(image.save_png(ProjectSettings.globalize_path(path)) == OK)
			var descriptor := {"texture":path,"look_sha256":fingerprint,
				"render_dependencies_sha256":dependencies,
				"texture_sha256":FileAccess.get_sha256(path),"protocol_versions":[protocol],
				"dimensions":[SIZE,SIZE],"model":model_id,
				"model_sha256":model_hash,"quality":"High"}
			if entry.is_empty():
				descriptor["variants"] = []
				result[id] = descriptor
			else:
				entry.variants.append(descriptor)
			total += 1
			print("BAKED_STATIC_BASE ",id," PC/",protocol," ",path)
	assert(failures.is_empty(),"Portrait failures: "+str(failures))
	assert(result.size() >= expected_count)
	var image_paths: Dictionary = {}
	for entry: Dictionary in result.values():
		image_paths[str(entry.texture)] = true
		for variant: Dictionary in entry.get("variants", []):
			image_paths[str(variant.texture)] = true
	var commit := ""
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--source-commit="):
			commit = argument.trim_prefix("--source-commit=")
	var manifest := {"schema_version":1,"source_commit":commit,
		"baker_sha256":FileAccess.get_sha256("res://tools/bake_creation_base_portraits.gd"),
		"renderer_sha256":FileAccess.get_sha256("res://src/ui/leaderboard_portraits.gd"),
		"catalog_sha256":FileAccess.get_sha256("res://src/ui/creation_base_library.gd"),
		"archetypes_sha256":FileAccess.get_sha256("res://data/actors/rl_head_archetypes.json"),
		"portrait_size":[SIZE,SIZE],"portrait_count":image_paths.size(),
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
	NativeAnimationImporter.clear()
	RLHeadRig.clear_caches()
	print("STATIC_BASE_PORTRAITS_READY ",result.size()," IDs / ",image_paths.size(),
		" images (",total," baked, ",reused," reused)")
	quit()
