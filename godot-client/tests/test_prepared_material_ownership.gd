extends SceneTree
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const Ownership := preload("res://src/world/prepared_material_ownership.gd")
var failures := 0
var assertions := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	assertions += 1
	if not value:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func _record() -> Dictionary:
	var source := Node3D.new()
	source.name = "PreparedMaterialFixture"
	var member := MeshInstance3D.new()
	member.name = "Member"
	var box := BoxMesh.new()
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, box.surface_get_arrays(0))
	var material := ShaderMaterial.new()
	var shader := Shader.new()
	shader.code = "shader_type spatial; render_mode unshaded; void fragment(){ALBEDO=vec3(0.4,0.7,0.3);}"
	material.shader = shader
	mesh.surface_set_material(0, material)
	member.mesh = mesh
	source.add_child(member)
	member.owner = source
	var packed := PackedScene.new()
	_expect(packed.pack(source) == OK, "native fixture scene packs")
	source.free()
	var path := "user://prepared-material-ownership.scn"
	_expect(ResourceSaver.save(packed, path) == OK, "native fixture scene saves")
	packed = null
	var loaded := ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	_expect(loaded != null, "actual serialized native Resource graph reloads")
	return {"status": "hit", "resource": loaded, "entry": {}}

func _member(instance: Node3D) -> MeshInstance3D:
	return instance.get_node("Member") as MeshInstance3D

func _settle() -> void:
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
	await process_frame
	await process_frame

func _run() -> void:
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.position = Vector3(0, 0, 8)
	camera.current = true
	var record := _record()

	# No frame gap before partial deletion, and no external Material reference
	# across it. The surviving instance continues to render after its peer dies.
	var first := Lifecycle.instantiate(record)
	var second := Lifecycle.instantiate(record)
	root.add_child(first)
	root.add_child(second)
	first.position.x = -1.5
	second.position.x = 1.5
	var survivor := _member(first)
	var survivor_material_id := survivor.get_active_material(0).get_instance_id()
	var survivor_rid_id := survivor.get_active_material(0).get_rid().get_id()
	var retired := _member(second)
	var weak_material: WeakRef = weakref(retired.get_active_material(0))
	_expect(retired.has_meta(Ownership.META), "each geometry owns private Materials in Object metadata")
	_expect(first.get_child_count() == 1 and second.get_child_count() == 1,
		"material ownership adds no scene Nodes")
	retired.free()
	_expect(is_instance_valid(second) and second.get_child_count() == 0,
		"incremental member deletion leaves its prepared root alive")
	_expect(weak_material.get_ref() == null,
		"private Material is released by actual Object destruction without a delayed queue")
	for index: int in 6:
		await _settle()
	_expect(survivor.get_active_material(0).get_instance_id() == survivor_material_id
		and survivor.get_active_material(0).get_rid().get_id() == survivor_rid_id,
		"survivor renders with unchanged Material ObjectID/RID after partial deletion")

	# Exit capture must preserve the CURRENT look material until the render
	# instance is freed, in addition to the original private material at birth.
	var changed := _member(first)
	var replacement := ShaderMaterial.new()
	replacement.shader = Shader.new()
	replacement.shader.code = "shader_type spatial; render_mode unshaded; void fragment(){ALBEDO=vec3(0.1,0.3,0.9);}"
	changed.set_surface_override_material(0, replacement)
	var weak_replacement: WeakRef = weakref(replacement)
	replacement = null
	first.remove_child(changed)
	_expect((changed.get_meta(Ownership.META) as Array).has(changed.get_active_material(0)),
		"tree exit captures current look replacement")
	first.add_child(changed)
	changed.free()
	_expect(weak_replacement.get_ref() == null,
		"look replacement ownership is finite after render-instance destruction")
	await _settle()
	first.free()
	second.free()
	first = null
	second = null
	await _settle()

	# NativeAnimationImporter keeps source Nodes detached. Never entering the
	# SceneTree still requires initial materials to outlive the instance RID.
	var detached := Lifecycle.instantiate(record)
	var weak_detached: WeakRef = weakref(_member(detached).get_active_material(0))
	detached.free()
	detached = null
	_expect(weak_detached.get_ref() == null, "never-attached source Material ownership is finite")
	await _settle()

	# A consumer may replace material while detached, so provide a deliberate
	# refresh boundary before publishing or freeing that private source.
	var private_source := Lifecycle.instantiate(record)
	var private_material := StandardMaterial3D.new()
	_member(private_source).material_overlay = private_material
	Ownership.refresh(private_source)
	_expect((_member(private_source).get_meta(Ownership.META) as Array).has(private_material),
		"explicit detached refresh captures newly assigned overlay")
	var weak_private: WeakRef = weakref(private_material)
	private_material = null
	private_source.free()
	private_source = null
	_expect(weak_private.get_ref() == null, "detached replacement releases at Object destruction")
	await _settle()

	# Packing paths explicitly strip the exact runtime-only key. No custom
	# guard ScriptObject/Callable/Node is stored in the imported metadata Array.
	var packed_source := Lifecycle.instantiate(record)
	var member := _member(packed_source)
	var count := (member.get_meta(Ownership.META) as Array).size()
	var undo := Ownership.strip_runtime_metadata(packed_source)
	_expect(not member.has_meta(Ownership.META) and undo.size() == 1,
		"packing strips only runtime material ownership metadata")
	var clean := PackedScene.new()
	_expect(clean.pack(packed_source) == OK and Lifecycle._data_only(clean, {}),
		"packed template remains data-only")
	Ownership.restore_runtime_metadata(undo)
	undo.clear()
	_expect(member.has_meta(Ownership.META) and (member.get_meta(Ownership.META) as Array).size() == count,
		"packing restore preserves complete runtime material ownership")
	clean = null
	packed_source.free()
	packed_source = null
	record.clear()
	camera.free()
	await _settle()
	print("PREPARED_MATERIAL_OWNERSHIP ", "PASS" if failures == 0 else "FAIL", " assertions=", assertions)
	quit(0 if failures == 0 else 1)
