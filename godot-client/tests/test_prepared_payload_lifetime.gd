extends SceneTree
## Child-first verified loads must stay alive until their parent owns them.
const Prepared := preload("res://src/world/prepared_content.gd")
const Keys := preload("res://src/world/prepared_animation_keys.gd")
const DIRECTORY := "user://prepared-payload-lifetime"
const SOURCE := DIRECTORY + "/source.glb"
const CATALOG := DIRECTORY + "/index.json"
var failures := 0

func _initialize() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if value:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _save(resource: Resource, extension: String) -> Dictionary:
	var temporary := DIRECTORY.path_join("writing." + extension)
	_expect(ResourceSaver.save(resource, temporary) == OK, "fixture resource saves")
	var digest := FileAccess.get_sha256(temporary)
	var path := DIRECTORY.path_join(digest + "." + extension)
	_expect(DirAccess.rename_absolute(temporary, path) == OK, "fixture uses exact native payload identity")
	resource.take_over_path(path)
	return {"path": path, "sha256": digest}

func _generation() -> Array:
	var source := Animation.new()
	source.length = 1.0
	var track := source.add_track(Animation.TYPE_POSITION_3D)
	source.track_set_path(track, NodePath("."))
	source.track_insert_key(track, 0.0, Vector3.ZERO)
	source.track_insert_key(track, 1.0 / 30.0, Vector3.ONE)
	var animation := source.duplicate(false) as Animation
	_expect(Keys.prepare(source, animation), "fixture preserves original animation clocks")
	var animation_record := _save(animation, "res")
	var library := AnimationLibrary.new()
	library.add_animation(&"clip", animation)
	var library_record := _save(library, "res")
	var root := Node3D.new()
	var player := AnimationPlayer.new()
	player.name = "Player"
	root.add_child(player)
	player.owner = root
	player.add_animation_library(&"", library)
	var packed := PackedScene.new()
	_expect(packed.pack(root) == OK, "fixture parent packs")
	root.free()
	var scene_record := _save(packed, "scn")
	# No source/parent Resource escapes this scope. The next loads are cold.
	return [animation_record, library_record, scene_record, weakref(animation), weakref(library)]

func _weak_cache_control(generation: Array) -> void:
	var child := ResourceLoader.load(generation[0].path, "Animation", ResourceLoader.CACHE_MODE_REUSE) as Animation
	_expect(Keys.restore_verified(child), "negative control first restores the standalone child")
	var weak: WeakRef = weakref(child)
	child = null
	_expect(weak.get_ref() == null, "ResourceLoader cache does not own a restored child")
	var parent := ResourceLoader.load(generation[2].path, "PackedScene", ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	var root := parent.instantiate()
	var player := root.get_node("Player") as AnimationPlayer
	_expect(player.get_animation(&"clip").track_get_key_time(0, 1) != 1.0 / 30.0,
		"negative control reloads narrowed child bytes when no owner spans the parent load")
	root.free()

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	var input := FileAccess.open(SOURCE, FileAccess.WRITE)
	input.store_string("exact synthetic source identity")
	input.close()
	var generation := _generation()
	_expect((generation[3] as WeakRef).get_ref() == null and (generation[4] as WeakRef).get_ref() == null,
		"fixture has no surviving animation or library owner before acquire")
	_weak_cache_control(generation)
	var digest := FileAccess.get_sha256(SOURCE)
	var entry := {"kind": "scene", "source": SOURCE, "source_digest": digest,
		"texture_token": "fixture", "engine_policy": Prepared.engine_policy(),
		"resource": generation[2].path, "inputs": [{"path": SOURCE, "sha256": digest}],
		"payloads": generation.slice(0, 3), "shared_images": {}, "shared_meshes": {},
		"metadata_json": Prepared.encode_metadata({})}
	entry.entry_id = Prepared.entry_identity(entry)
	var catalog := FileAccess.open(CATALOG, FileAccess.WRITE)
	catalog.store_string(JSON.stringify({"schema_version": Prepared.SCHEMA, "policy": Prepared.COOK_POLICY, "entries": [entry]}))
	catalog.close()
	var record := Prepared.acquire("scene", SOURCE, digest, "fixture", "require-pilot", CATALOG)
	_expect(str(record.get("status", "")) == "hit", "child-first catalog acquires its verified primary")
	var packed := record.get("resource") as PackedScene
	if packed != null:
		var root := packed.instantiate()
		var player := root.get_node("Player") as AnimationPlayer
		var animation := player.get_animation(&"clip")
		_expect(animation.track_get_key_time(0, 1) == 1.0 / 30.0,
			"parent owns the exact restored child instead of reloading narrowed bytes")
		_expect(animation.has_meta(Keys.PUBLISHED), "parent retains the already verified child instance")
		root.free()
	await process_frame
	print("PREPARED_PAYLOAD_LIFETIME ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)
