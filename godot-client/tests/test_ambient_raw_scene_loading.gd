extends SceneTree
## Synthetic loose source fixture only. No authored or retired asset is loaded.
const CACHE := preload("res://src/actors/glb_scene_cache.gd")
const POLICY := preload("res://src/actors/archived_model_policy.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)

func _operation_count(snapshot: Dictionary, operation: String) -> int:
	var timing: Dictionary = snapshot.get("timings", {})
	var operations: Dictionary = timing.get("operations", {})
	return int((operations.get(operation, {}) as Dictionary).get("count", 0))

func _binary() -> PackedByteArray:
	var result := PackedFloat32Array([-0.5, 0, 0, 0.5, 0, 0, 0, 1, 0]).to_byte_array()
	result.append_array(PackedFloat32Array([0, 1]).to_byte_array())
	result.append_array(PackedFloat32Array([0, 0, 0, 0, 0.25, 0]).to_byte_array())
	return result

func _document() -> Dictionary:
	return {"asset": {"version": "2.0", "generator": "Rabbit Lands synthetic ambient loader test"},
		"buffers": [{"byteLength": 68}],
		"bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36, "target": 34962},
			{"buffer": 0, "byteOffset": 36, "byteLength": 8}, {"buffer": 0, "byteOffset": 44, "byteLength": 24}],
		"accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [-0.5, 0, 0], "max": [0.5, 1, 0]},
			{"bufferView": 1, "componentType": 5126, "count": 2, "type": "SCALAR", "min": [0], "max": [1]},
			{"bufferView": 2, "componentType": 5126, "count": 2, "type": "VEC3"}],
		"meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
		"nodes": [{"name": "SyntheticAmbient", "mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0,
		"animations": [{"name": "SyntheticOnce", "samplers": [{"input": 1, "output": 2, "interpolation": "LINEAR"}],
			"channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}]}]}

func _glb() -> PackedByteArray:
	var json := JSON.stringify(_document()).to_utf8_buffer()
	while json.size() % 4 != 0:
		json.append(32)
	var binary := _binary()
	var result := PackedByteArray()
	result.resize(20)
	result.encode_u32(0, 0x46546c67)
	result.encode_u32(4, 2)
	result.encode_u32(8, 12 + 8 + json.size() + 8 + binary.size())
	result.encode_u32(12, json.size())
	result.encode_u32(16, 0x4e4f534a)
	result.append_array(json)
	var chunk := PackedByteArray()
	chunk.resize(8)
	chunk.encode_u32(0, binary.size())
	chunk.encode_u32(4, 0x004e4942)
	result.append_array(chunk)
	result.append_array(binary)
	return result

func _store(path: String, bytes: PackedByteArray) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(bytes)
	file.close()
	return true

func _player(instance: Node3D) -> AnimationPlayer:
	var players := instance.find_children("*", "AnimationPlayer", true, false)
	return players[0] as AnimationPlayer if not players.is_empty() else null

func _run() -> void:
	CACHE.clear()
	var directory := "user://synthetic_ambient_raw_%d" % Time.get_ticks_usec()
	_expect(DirAccess.make_dir_recursive_absolute(directory) == OK, "fixture directory created")
	var glb_path := ProjectSettings.globalize_path(directory.path_join("synthetic.glb"))
	var gltf_path := ProjectSettings.globalize_path(directory.path_join("synthetic.gltf"))
	var named_path := directory.path_join("named.tscn")
	var invalid_path := directory.path_join("invalid.glb")
	_expect(_store(glb_path, _glb()), "synthetic unimported GLB written")
	var gltf := _document()
	gltf.buffers[0]["uri"] = "data:application/octet-stream;base64," + Marshalls.raw_to_base64(_binary())
	_expect(_store(gltf_path, JSON.stringify(gltf).to_utf8_buffer()), "synthetic self-contained glTF written")
	_expect(_store(named_path, '[gd_scene format=3]\n[node name="NamedSynthetic" type="Node3D"]\n'.to_utf8_buffer()), "named scene fixture written")
	_expect(_store(invalid_path, "not a glTF document".to_utf8_buffer()), "invalid source fixture written")
	_expect(not FileAccess.file_exists(glb_path + ".import") and not FileAccess.file_exists(gltf_path + ".import"),
		"raw fixtures have no imported remaps")
	var population := AmbientPopulation.new()
	root.add_child(population)
	var catalog := {"synthetic": {"scene": glb_path}, "text": {"scene": gltf_path}, "named": {"scene": named_path}}
	var baseline := CACHE.retention_snapshot()
	var packed: PackedScene = population.call("_scene_for", "synthetic", catalog)
	_expect(packed != null, "ambient path loads an unimported loose GLB")
	if packed != null:
		var same := CACHE.packed_scene(glb_path)
		_expect(same == packed, "ambient and actor packed getter share the scene")
		var actor := CACHE.instantiate(glb_path)
		_expect(_operation_count(CACHE.retention_snapshot(), "gltf_parse") == _operation_count(baseline, "gltf_parse") + 1,
			"ambient and actor consumers parse the raw source only once")
		_expect(_operation_count(CACHE.retention_snapshot(), "scene_instantiate") == _operation_count(baseline, "scene_instantiate") + 1,
			"actor instantiate timing is retained after the getter refactor")
		var animal := packed.instantiate() as Node3D
		_expect(actor != null and animal != null, "both actor and ambient instances materialize")
		if actor != null and animal != null:
			root.add_child(actor)
			population.add_child(animal)
			var actor_player := _player(actor)
			var animal_player := _player(animal)
			_expect(actor_player != null and animal_player != null, "raw animation is available")
			if actor_player != null and animal_player != null:
				var clips_present := actor_player.has_animation("SyntheticOnce") and animal_player.has_animation("SyntheticOnce")
				_expect(clips_present, "raw source clip name is preserved")
				if clips_present:
					var original := actor_player.get_animation("SyntheticOnce")
					var original_mode := original.loop_mode
					var playing: AnimationPlayer = population.call("_play", animal, "SyntheticOnce", 0.3)
					_expect(playing == animal_player and animal_player.get_animation("SyntheticOnce").loop_mode == Animation.LOOP_LINEAR,
						"ambient instance receives a looping clip")
					_expect(original.loop_mode == original_mode and actor_player.get_animation("SyntheticOnce") == original,
						"ambient loop preparation leaves actor/cache animation unchanged")
					_expect(animal_player.get_animation("SyntheticOnce") != original or original_mode == Animation.LOOP_LINEAR,
						"non-looping shared clips are duplicated before editing")
			actor.free()
			animal.free()
		else:
			if actor != null: actor.free()
			if animal != null: animal.free()
	var before_text := CACHE.retention_snapshot()
	_expect(population.call("_scene_for", "text", catalog) != null, "ambient path loads a loose glTF with embedded binary data")
	var before_named := CACHE.retention_snapshot()
	var named: PackedScene = population.call("_scene_for", "named", catalog)
	_expect(named != null and CACHE.cached_scene_count() == int(before_named.strong_scene_entries),
		"named scene resources keep ResourceLoader without entering the glTF cache")
	_expect(_operation_count(CACHE.retention_snapshot(), "gltf_parse") == _operation_count(before_text, "gltf_parse") + 1,
		"named scenes do not invoke the raw parser")
	_expect(int(CACHE.retention_snapshot().lookup_hits) >= int(baseline.lookup_hits) + 2,
		"packed getter and instantiate retain cache hit telemetry")
	var prior_errors := Engine.print_error_messages
	Engine.print_error_messages = false # Intentional parser rejection, not an unexpected script failure.
	var rejected := CACHE.packed_scene(invalid_path)
	Engine.print_error_messages = prior_errors
	_expect(rejected == null, "malformed loose source is rejected")
	var failed := CACHE.retention_snapshot()
	_expect(CACHE.packed_scene(invalid_path) == null
		and _operation_count(CACHE.retention_snapshot(), "gltf_parse") == _operation_count(failed, "gltf_parse"),
		"failed raw parsing is cached rather than retried for every animal")
	var retired_index: Variant = JSON.parse_string(FileAccess.get_file_as_string(POLICY.INDEX))
	var retired: Array = (retired_index as Dictionary).get("runtimePaths", []) if retired_index is Dictionary else []
	_expect(not retired.is_empty(), "retirement policy has reserved paths")
	if not retired.is_empty():
		var retired_path := "res://assets/" + str(retired[0])
		catalog.synthetic = {"scene": retired_path}
		_expect(population.call("_scene_for", "synthetic", catalog) == null and CACHE.packed_scene(retired_path) == null,
			"retired paths are denied even when a model alias was locally cached")
	_test_named_library(population)
	population.free()
	CACHE.clear()
	_expect(CACHE.cached_scene_count() == 0, "session clear releases the shared cache entries")
	for path: String in [glb_path, gltf_path, named_path, invalid_path]:
		DirAccess.remove_absolute(path)
	DirAccess.remove_absolute(directory)
	print("ambient raw scene loading: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

func _test_named_library(population: AmbientPopulation) -> void:
	var animal := Node3D.new()
	var player := AnimationPlayer.new()
	player.name = "AnimationPlayer"
	animal.add_child(player)
	population.add_child(animal)
	var source_library := AnimationLibrary.new()
	var source_clip := Animation.new()
	source_clip.length = 1.0
	source_library.add_animation("Once", source_clip)
	player.add_animation_library("named", source_library)
	population.call("_play", animal, "named/Once", 0.0)
	_expect(source_library.get_animation("Once") == source_clip and source_clip.loop_mode == Animation.LOOP_NONE,
		"a named source library and its clip remain immutable")
	_expect(player.get_animation_library("named") != source_library
		and player.get_animation("named/Once") != source_clip
		and player.get_animation("named/Once").loop_mode == Animation.LOOP_LINEAR,
		"a named per-instance library receives only the selected duplicate clip")
	animal.free()
