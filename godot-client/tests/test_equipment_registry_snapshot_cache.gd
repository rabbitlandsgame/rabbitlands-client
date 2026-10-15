extends SceneTree
## Contract for explicit, bounded equipment registry snapshots.

const Cache = preload("res://src/actors/equipment_registry_snapshot_cache.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	Cache.clear()
	var source := {
		"models": {"0:1": {"scene": "one.glb", "tint": [[1, 2, 3], [4, 5, 6]]}},
		"fitGroups": {"luminous_male": ["canonical", "male"]},
		"enabled": true,
	}
	var prepared := Cache.prepare(source)
	_expect(_all_containers_read_only(prepared), "prepared snapshot is recursively read-only")
	_expect(prepared == source, "prepared snapshot initially matches its candidate")
	_expect(is_same(prepared, Cache.acquire(prepared)),
		"prepared snapshot is acquired by identity")
	_expect(int(Cache.stats()["hits"]) == 1 and int(Cache.stats()["prepares"]) == 1,
		"prepare and hit accounting identify the fast path")

	# Arbitrary mutable callers retain the old defensive-copy behavior. Existing
	# actors keep their copy; a later actor sees the caller's changed contents.
	var mutable_first := Cache.acquire(source)
	_expect(not is_same(source, mutable_first), "mutable input receives a defensive copy")
	var source_models := source["models"] as Dictionary
	var source_weapon := source_models["0:1"] as Dictionary
	source_weapon["scene"] = "two.glb"
	var mutable_changed := Cache.acquire(source)
	_expect(str(mutable_first["models"]["0:1"]["scene"]) == "one.glb",
		"caller mutation cannot change an existing actor copy")
	_expect(str(mutable_changed["models"]["0:1"]["scene"]) == "two.glb",
		"a later actor sees mutable caller changes")
	_expect(not is_same(mutable_first, mutable_changed),
		"mutable callers never alias through the prepared pool")
	mutable_first["models"]["0:1"]["scene"] = "actor-private.glb"
	_expect(str(source["models"]["0:1"]["scene"]) == "two.glb"
		and str(mutable_changed["models"]["0:1"]["scene"]) == "two.glb",
		"one actor's private mutation cannot cross into caller or another actor")

	Cache.clear()
	var typed: Array[int] = [1, 2, 3]
	var typed_dictionary: Dictionary[String, int] = {"one": 1, "two": 2}
	var typed_snapshot := Cache.prepare({
		"typed": typed,
		"typed_dictionary": typed_dictionary,
		"int": 1,
		"float": 1.0,
		"string": "name",
		"name": &"name",
	})
	var frozen_typed: Array = typed_snapshot["typed"] as Array
	var frozen_typed_dictionary: Dictionary = (
		typed_snapshot["typed_dictionary"] as Dictionary)
	_expect(frozen_typed.is_same_typed(typed), "typed Array retains its element type")
	_expect(frozen_typed.is_read_only(), "typed Array is read-only")
	_expect(frozen_typed_dictionary.is_same_typed(typed_dictionary),
		"typed Dictionary retains its key and value types")
	_expect(frozen_typed_dictionary.is_read_only(), "typed Dictionary is read-only")
	_expect(typeof(typed_snapshot["int"]) == TYPE_INT
		and typeof(typed_snapshot["float"]) == TYPE_FLOAT,
		"integer and float Variant types are preserved")
	_expect(typeof(typed_snapshot["string"]) == TYPE_STRING
		and typeof(typed_snapshot["name"]) == TYPE_STRING_NAME,
		"String and StringName Variant types are preserved")
	var packed_source := {"packed": PackedInt32Array([4, 5, 6])}
	var packed_copy := Cache.prepare(packed_source)
	_expect(not is_same(packed_source, packed_copy),
		"packed-array input stays on defensive-copy fallback")
	_expect(int(Cache.stats()["uncachedPrepares"]) == 1,
		"packed-array input is not registered as immutable")

	Cache.clear()
	var evicted := Cache.prepare({"evicted": true})
	for index: int in range(Cache.CAPACITY):
		Cache.prepare({"replacement": index})
	_expect(int(Cache.stats()["entries"]) == Cache.CAPACITY,
		"pool retains no more than its declared capacity")
	_expect(not is_same(evicted, Cache.acquire(evicted)),
		"evicted snapshots safely fall back to a defensive copy")

	Cache.clear()
	var resource_a := Resource.new()
	var object_input := {"value": resource_a}
	var object_prepared := Cache.prepare(object_input)
	_expect(not is_same(object_input, object_prepared),
		"Object-bearing preparation retains defensive top-level copying")
	_expect(is_same(object_input["value"], object_prepared["value"]),
		"Object-bearing preparation retains Dictionary.duplicate(true) Object semantics")
	_expect(int(Cache.stats()["entries"]) == 0
		and int(Cache.stats()["uncachedPrepares"]) == 1,
		"Object-bearing input is never registered")

	Cache.clear()
	var registry_value: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	_expect(registry_value is Dictionary, "real equipment registry parses")
	if registry_value is Dictionary:
		var registry := registry_value as Dictionary
		var snapshot := Cache.prepare(registry)
		_expect(snapshot == registry, "real registry snapshot is structurally exact")
		_expect(_all_containers_read_only(snapshot),
			"real registry snapshot recursively freezes every container")
		_expect(is_same(snapshot, Cache.acquire(snapshot)),
			"real registry uses the prepared identity fast path")

	print("equipment registry snapshot cache: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _all_containers_read_only(value: Variant) -> bool:
	if value is Dictionary:
		if not value.is_read_only():
			return false
		for key: Variant in value:
			if not _all_containers_read_only(key) or not _all_containers_read_only(value[key]):
				return false
	elif value is Array:
		if not value.is_read_only():
			return false
		for child: Variant in value:
			if not _all_containers_read_only(child):
				return false
	return true


func _expect(value: bool, label: String) -> void:
	if value:
		return
	_failures += 1
	push_error("FAIL: " + label)
