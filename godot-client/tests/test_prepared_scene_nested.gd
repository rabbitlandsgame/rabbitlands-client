extends SceneTree

const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const DIRECTORY := "user://prepared-nested-preflight"
const PROBE := &"rabbitlands_prepared_nested_probe"
var failures := 0
var assertions := 0
var _files: Array[String] = []
var _resources: Array[Resource] = []


func _initialize() -> void:
	call_deferred("_run")


func _expect(value: bool, message: String) -> void:
	assertions += 1
	if not value:
		failures += 1
		push_error(message)


func _write(name: String, content: String) -> String:
	var path := DIRECTORY.path_join(name)
	var file := FileAccess.open(path, FileAccess.WRITE)
	_expect(file != null, "open nested-preflight fixture " + name)
	if file != null:
		file.store_string(content)
		file.close()
		_files.append(path)
	return path


func _packed(path: String) -> PackedScene:
	var packed := ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	_expect(packed != null, "load nested-preflight fixture " + path.get_file())
	if packed != null:
		_resources.append(packed)
	return packed


func _reset_probe() -> void:
	if Engine.has_meta(PROBE):
		Engine.remove_meta(PROBE)


func _calls() -> int:
	return int(Engine.get_meta(PROBE, 0))


func _reject_before_callback(path: String, label: String, nested_index := -1, inherited := false) -> void:
	_reset_probe()
	var packed := _packed(path)
	if packed == null:
		return
	_expect(_calls() == 0, label + " loading data did not instantiate a Node or run local-scene setup")
	if nested_index >= 0:
		_expect(packed.get_state().get_node_instance(nested_index) != null,
			label + " retains an actual nested PackedScene rather than flattened properties")
	if inherited:
		_expect(packed.get_state().get_base_scene_state() != null,
			label + " retains an actual inherited SceneState")
	var guarded := Lifecycle.instantiate({"status": "hit", "resource": packed, "entry": {}})
	_expect(guarded == null and _calls() == 0,
		label + " rejects before any scripted initializer or local-scene setup executes")
	if guarded != null:
		guarded.free()
	_reset_probe()
	# Positive control executes the exact same in-memory scene through the
	# ordinary engine API. Without this, a malformed fixture could appear safe.
	var ordinary := packed.instantiate()
	_expect(ordinary != null and _calls() > 0,
		label + " ordinary engine instantiate positively executes the prohibited callback")
	if ordinary != null:
		ordinary.free()
	_reset_probe()


func _run() -> void:
	_expect(DirAccess.make_dir_recursive_absolute(DIRECTORY) == OK, "create isolated fixture directory")
	var node_script := _write("probe_node.gd", "extends Node3D\nfunc _init() -> void:\n\tEngine.set_meta('%s', int(Engine.get_meta('%s', 0)) + 1)\n" % [PROBE, PROBE])
	var resource_script := _write("probe_resource.gd", "extends Resource\nfunc _setup_local_to_scene() -> void:\n\tEngine.set_meta('%s', int(Engine.get_meta('%s', 0)) + 1)\n" % [PROBE, PROBE])
	var leaf := _write("scripted_leaf.tscn", """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path=%s id="1"]

[node name="UnsafeLeaf" type="Node3D"]
script = ExtResource("1")
""" % JSON.stringify(node_script))
	var nested := _write("nested.tscn", """[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path=%s id="1"]

[node name="Outer" type="Node3D"]

[node name="Nested" parent="." instance=ExtResource("1")]
""" % JSON.stringify(leaf))
	var inherited := _write("inherited.tscn", """[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path=%s id="1"]

[node name="Inherited" instance=ExtResource("1")]
""" % JSON.stringify(leaf))
	_reject_before_callback(nested, "nested Node script", 1)
	_reject_before_callback(inherited, "inherited Node script", 0, true)
	for form: String in ["array", "dictionary"]:
		# These stored Node properties are not themselves Resources. Godot
		# discovers their local-to-scene Resource values during instantiate and
		# calls _setup_local_to_scene before returning the new scene root.
		var value := "[SubResource(\"Probe\")]" if form == "array" else "{\"probe\": SubResource(\"Probe\")}"
		var scene := _write("local_resource_" + form + ".tscn", """[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path=%s id="1"]

[sub_resource type="Resource" id="Probe"]
resource_local_to_scene = true
script = ExtResource("1")

[node name="DataContainer" type="Node3D"]
metadata/probe = %s
""" % [JSON.stringify(resource_script), value])
		_reject_before_callback(scene, form + " local Resource script")

	var safe_leaf := _write("safe_leaf.tscn", """[gd_scene format=3]

[node name="SafeLeaf" type="Node3D"]
position = Vector3(3, 2, 1)
""")
	var safe_nested := _write("safe_nested.tscn", """[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path=%s id="1"]

[node name="SafeOuter" type="Node3D"]

[node name="SafeNested" parent="." instance=ExtResource("1")]
""" % JSON.stringify(safe_leaf))
	var packed := _packed(safe_nested)
	if packed != null:
		var instance := Lifecycle.instantiate({"status": "hit", "resource": packed, "entry": {}})
		_expect(instance != null and instance.get_node_or_null("SafeNested") != null,
			"data-only nested scene remains usable")
		if instance != null:
			var child := instance.get_node("SafeNested") as Node3D
			_expect(child.position == Vector3(3, 2, 1), "accepted nested scene retains authored transform")
			instance.free()
	_reset_probe()
	_resources.clear()
	for path: String in _files:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	_files.clear()
	await process_frame
	await process_frame
	print("test_prepared_scene_nested: %d assertions, %d failures" % [assertions, failures])
	quit(1 if failures else 0)
