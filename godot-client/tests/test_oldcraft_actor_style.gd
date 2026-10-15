extends SceneTree

const OldcraftActorStyleScript := preload("res://src/actors/oldcraft_actor_style.gd")

var failures := 0
var assertions := 0


func _init() -> void:
	_test_no_skeleton_styling()
	_test_painted_finish()
	_test_glass_keeps_its_gloss()
	_test_material_names_survive_import()
	if failures == 0:
		print("oldcraft actor style: PASS (%d assertions)" % assertions)
		quit(0)
	else:
		push_error("oldcraft actor style: FAIL (%d failures, %d assertions)"
			% [failures, assertions])
		quit(1)


func _expect(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		failures += 1
		push_error(message)


func _test_no_skeleton_styling() -> void:
	# Owner call 2026-10-05: no runtime bone growth on player bodies.
	for name: String in ["pose_scales", "apply_skeleton", "restore_skeleton", "has_profile"]:
		_expect(not (OldcraftActorStyleScript as Script).get_script_method_list().any(
			func(m: Dictionary) -> bool: return m.name == name),
			"the style no longer offers %s" % name)
	var source := FileAccess.get_file_as_string("res://src/actors/replicated_actor_3d.gd")
	_expect(not source.contains("apply_skeleton") and not source.contains("set_bone_pose_scale"),
		"actors never scale their skeleton's bones")


func _test_painted_finish() -> void:
	var instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	var material := StandardMaterial3D.new()
	material.roughness = 0.2
	material.metallic = 0.8
	material.metallic_specular = 0.9
	material.normal_enabled = true
	material.normal_texture = GradientTexture2D.new()
	material.normal_scale = 1.0
	mesh.material = material
	instance.mesh = mesh
	var mesh_identity := instance.mesh
	var material_identity := instance.get_active_material(0)
	_expect(OldcraftActorStyleScript.apply_mesh_finish(instance) == 1,
		"painted finish finds the active material")
	_expect(instance.mesh == mesh_identity and instance.get_active_material(0) == material_identity,
		"painted finish preserves mesh and material identity")
	_expect(material.roughness >= OldcraftActorStyleScript.ROUGHNESS_FLOOR,
		"painted finish removes the plastic-sharp highlight")
	_expect(material.metallic_specular <=
		OldcraftActorStyleScript.DIELECTRIC_SPECULAR_CEILING,
		"dielectric specular is restrained")
	_expect(material.normal_scale <= OldcraftActorStyleScript.NORMAL_SCALE_CEILING,
		"fine normal relief stays subordinate to the painted value blocks")
	_expect(is_equal_approx(material.metallic, 0.8),
		"authored metallic response is retained")
	instance.free()


func _finish_material(material: StandardMaterial3D) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.material = material
	instance.mesh = mesh
	OldcraftActorStyleScript.apply_mesh_finish(instance)
	return instance


func _test_glass_keeps_its_gloss() -> void:
	# Race programme P4: Glasswarden crystals are authored glossy (opaque,
	# roughness about 0.2, metallic 0) and named "Race feature glass".
	var glass := StandardMaterial3D.new()
	glass.resource_name = "Race feature glass"
	glass.roughness = 0.2
	glass.metallic = 0.0
	glass.metallic_specular = 0.5
	var glass_instance := _finish_material(glass)
	_expect(is_equal_approx(glass.roughness, 0.2),
		"glass keeps its authored roughness under the painted finish")
	_expect(is_equal_approx(glass.metallic_specular, 0.5),
		"glass keeps its authored specular under the painted finish")
	_expect(int(glass.get_meta(OldcraftActorStyleScript.MATERIAL_FINISH_META, 0)) ==
		OldcraftActorStyleScript.STYLE_VERSION, "glass is still marked as finished")
	glass_instance.free()
	for name: String in ["Race feature horn", "Race feature stone",
			"Race feature growth", "Race head", "Glass"]:
		var other := StandardMaterial3D.new()
		other.resource_name = name
		other.roughness = 0.2
		other.metallic_specular = 0.5
		var other_instance := _finish_material(other)
		_expect(other.roughness >= OldcraftActorStyleScript.ROUGHNESS_FLOOR and
			other.metallic_specular <= OldcraftActorStyleScript.DIELECTRIC_SPECULAR_CEILING,
			"%s takes the painted finish" % name)
		other_instance.free()


func _test_material_names_survive_import() -> void:
	# The opt-out keys on the glTF material name, so it must reach the
	# material Godot builds: through a runtime glTF load ...
	var scene := Node3D.new()
	var instance := MeshInstance3D.new()
	instance.name = "race_feature_head"
	var mesh := BoxMesh.new()
	var glass := StandardMaterial3D.new()
	glass.resource_name = "Race feature glass"
	glass.roughness = 0.2
	mesh.material = glass
	instance.mesh = mesh
	scene.add_child(instance)
	instance.owner = scene
	var export_state := GLTFState.new()
	var document := GLTFDocument.new()
	_expect(document.append_from_scene(scene, export_state) == OK, "the glass fixture exports")
	var bytes := document.generate_buffer(export_state)
	scene.free()
	var import_state := GLTFState.new()
	_expect(GLTFDocument.new().append_from_buffer(bytes, "", import_state) == OK,
		"the glass fixture imports")
	var imported := GLTFDocument.new().generate_scene(import_state)
	var found: MeshInstance3D = null
	if imported != null:
		# A script-run load builds importer meshes; take the ArrayMesh the
		# importer would hand an actor.
		for node: Node in imported.find_children("*", "", true, false):
			if node is MeshInstance3D:
				found = node as MeshInstance3D
			elif node is ImporterMeshInstance3D and found == null:
				found = MeshInstance3D.new()
				found.mesh = (node as ImporterMeshInstance3D).mesh.get_mesh()
				node.add_child(found)
	_expect(found != null and found.get_active_material(0) != null and
		found.get_active_material(0).resource_name == "Race feature glass",
		"a glTF material name survives a runtime import")
	if found != null:
		OldcraftActorStyleScript.apply_mesh_finish(found)
		var material := found.get_active_material(0) as BaseMaterial3D
		_expect(material != null and material.roughness < 0.3,
			"an imported glass material keeps its gloss")
	if imported != null:
		imported.free()
	# ... and through the editor import of the shipped race bodies, whose
	# head primitives carry the glTF name "Race head".
	var body := (load("res://assets/actors/native/races/votary_male.glb") as PackedScene).instantiate()
	var names: Array[String] = []
	for node: Node in body.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		for surface in mesh_node.mesh.get_surface_count():
			var material := mesh_node.mesh.surface_get_material(surface)
			if material != null:
				names.append(material.resource_name)
	_expect(names.has("Race head"), "imported race bodies keep their glTF material names")
	body.free()
