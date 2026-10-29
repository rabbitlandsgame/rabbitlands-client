extends SceneTree
## Real shared scene/library paths against exact raw and packaged fixtures.
const Payload := preload("res://src/actors/creature_payload.gd")
const SceneCache := preload("res://src/actors/glb_scene_cache.gd")
const Importer := preload("res://src/actors/native_animation_importer.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const Extras := preload("res://src/actors/glb_mesh_extras.gd")
var failures: Array[String] = []

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error(message)

func snapshot(path: String, prewarm: bool) -> Dictionary:
	SceneCache.clear()
	Importer.clear()
	if prewarm: check(Importer.prewarm(path), "compressed library worker started")
	var model := SceneCache.instantiate(path)
	check(model != null, "scene loaded: " + path)
	if model == null: return {}
	root.add_child(model)
	var duplicate := SceneCache.instantiate(path)
	check(duplicate != null, "cached scene instance")
	root.add_child(duplicate)
	var meshes := model.find_children("*", "MeshInstance3D", true, false)
	var duplicates := duplicate.find_children("*", "MeshInstance3D", true, false)
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	for i in meshes.size():
		var mesh := (meshes[i] as MeshInstance3D).mesh
		check(mesh == (duplicates[i] as MeshInstance3D).mesh, "mesh resource shared")
		for surface in mesh.get_surface_count():
			hash.update(var_to_bytes(mesh.surface_get_arrays(surface)))
			hash.update(var_to_bytes(mesh.surface_get_blend_shape_arrays(surface)))
	var mesh_hash := hash.finish().hex_encode()
	var skeleton := model.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var imported := Importer.import_library(model,path,skeleton)
	check(imported.errors.is_empty(), "animation import errors")
	var player := imported.player as AnimationPlayer
	check(player != null and player.has_animation("RESET"), "corrective RESET retained")
	var duplicate_skeleton := duplicate.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var other := Importer.import_library(duplicate,path,duplicate_skeleton)
	check(player.get_animation_library("") == (other.player as AnimationPlayer).get_animation_library(""), "library resource shared")
	check(SceneCache.cached_scene_count() == 1 and Importer.cached_library_count() == 1, "single shared scene and library")
	hash.start(HashingContext.HASH_SHA256)
	var samples := 0
	var clips := []
	for clip in player.get_animation_list():
		var animation := player.get_animation(clip)
		clips.append({"name":str(clip),"duration":animation.length,"tracks":animation.get_track_count()})
		hash.update(var_to_bytes(clips[-1]))
		for fraction in [0.0,0.037,0.139,0.25,0.499,0.731,0.933,1.0]:
			var at: float = animation.length * fraction
			for track in animation.get_track_count():
				var kind := animation.track_get_type(track)
				var value: Variant
				match kind:
					Animation.TYPE_POSITION_3D: value = animation.position_track_interpolate(track,at)
					Animation.TYPE_ROTATION_3D: value = animation.rotation_track_interpolate(track,at)
					Animation.TYPE_SCALE_3D: value = animation.scale_track_interpolate(track,at)
					Animation.TYPE_BLEND_SHAPE: value = animation.blend_shape_track_interpolate(track,at)
					Animation.TYPE_VALUE: value = animation.value_track_interpolate(track,at)
					_: value = null
				hash.update(var_to_bytes([str(animation.track_get_path(track)),kind,value]))
				samples += 1
	var result := {"mesh_sha256":mesh_hash,"animation_sha256":hash.finish().hex_encode(),"samples":samples,"clips":clips,"root_name":str(model.name)}
	model.free()
	duplicate.free()
	SceneCache.clear()
	Importer.clear()
	return result

func prepared_round_trip(fixture: Dictionary) -> Dictionary:
	var source := str(fixture.source)
	var original := FileAccess.get_file_as_bytes(source)
	var digest := Payload.source_sha256(source)
	var directory := "user://creature-prepared-qa"
	DirAccess.make_dir_recursive_absolute(directory)
	var node := Node3D.new()
	var packed := PackedScene.new()
	check(packed.pack(node) == OK,"prepared fixture packed")
	node.free()
	var temporary := directory + "/temporary.scn"
	check(ResourceSaver.save(packed,temporary) == OK,"prepared fixture saved")
	var payload_sha := FileAccess.get_sha256(temporary)
	var payload := directory + "/" + payload_sha + ".scn"
	FileAccess.open(payload,FileAccess.WRITE).store_buffer(FileAccess.get_file_as_bytes(temporary))
	var entry := {"kind":"scene","source":Prepared.logical_source(source),"source_digest":digest,
		"texture_token":"creature-compression-test","engine_policy":Prepared.engine_policy(),
		"metadata_json":Prepared.encode_metadata({}),"resource":payload,
		"inputs":[{"path":Prepared.logical_source(source),"sha256":digest}],
		"payloads":[{"path":payload,"sha256":payload_sha}]}
	entry["entry_id"] = Prepared.entry_identity(entry)
	var catalog := directory + "/index.json"
	FileAccess.open(catalog,FileAccess.WRITE).store_string(JSON.stringify({"schema_version":Prepared.SCHEMA,"policy":Prepared.COOK_POLICY,"entries":[entry]}))
	var first := Prepared.acquire("scene",source,digest,"creature-compression-test","auto",catalog)
	check(first.status == "hit","prepared cache accepts verified decoded original hash: " + str(first.reason))
	# A valid recompressed but changed GLB must invalidate a previously verified
	# native entry even when the caller still supplies the old expected digest.
	FileAccess.open(source,FileAccess.WRITE).store_buffer(FileAccess.get_file_as_bytes(fixture.replacement))
	var changed := Prepared.acquire("scene",source,digest,"creature-compression-test","auto",catalog)
	check(changed.status == "miss" and changed.reason == "input_hash_mismatch","changed decoded content invalidates prepared cache")
	FileAccess.open(source,FileAccess.WRITE).store_buffer(original)
	var restored := Prepared.acquire("scene",source,digest,"creature-compression-test","auto",catalog)
	check(restored.status == "hit","restored exact compressed content verifies again")
	return {"initial":first.status,"changed":changed.reason,"restored":restored.status}

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		push_error("Supply fixture job JSON and result path")
		quit(1)
		return
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var results := []
	for fixture: Dictionary in job.fixtures:
		check(Payload.source_sha256(fixture.raw) == fixture.sha256, "raw source digest")
		check(Payload.source_sha256(fixture.compressed) == fixture.sha256, "verified decoded source digest")
		check(Payload.read_bytes(fixture.compressed) == FileAccess.get_file_as_bytes(fixture.raw), "complete source bytes identical")
		check(Extras.read(fixture.raw) == Extras.read(fixture.compressed),"embedded mesh/node metadata retained")
		var raw := snapshot(fixture.raw,false)
		var compressed := snapshot(fixture.compressed,true)
		check(raw == compressed,"raw/packaged scene and library parity: " + str(fixture.name))
		results.append({"name":fixture.name,"raw":raw,"compressed":compressed})
	var prepared := prepared_round_trip(job.prepared) if job.has("prepared") else {}
	var rejected := []
	for invalid: Dictionary in job.get("invalid",[]):
		check(Payload.append(GLTFDocument.new(),invalid.path,GLTFState.new()) == ERR_FILE_CORRUPT,"corrupt payload fails before parser fallback: " + str(invalid.name))
		rejected.append(invalid.name)
	var report := {"passed":failures.is_empty(),"failures":failures,"fixtures":results,"prepared_cache":prepared,"rejected_payloads":rejected,"engine":Engine.get_version_info(),"scope":"Actual scene cache, library importer/prewarm, sharing, corrective RESET, all mesh/shape arrays, sampled bone/morph playback, prepared-source invalidation and corruption rejection. No rendering/FPS test."}
	FileAccess.open(args[1],FileAccess.WRITE).store_string(JSON.stringify(report,"\t"))
	print("CREATURE_PAYLOAD ","PASS" if failures.is_empty() else "FAIL")
	quit(0 if failures.is_empty() else 1)
