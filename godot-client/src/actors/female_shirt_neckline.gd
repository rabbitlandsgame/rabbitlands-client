extends RefCounted
## A repaired mesh for the native female shirt. The canonical body is retained
## byte for byte: RL head cut lists and every other body surface keep their
## source contract. The override has the same skeleton, bind order and atlas.
const BODY := "res://assets/actors/native/races/luminous_female.glb"
const REPAIRED := "res://assets/actors/native/races/luminous_female_shirt.glb"
const APPLIED := &"female_shirt_neckline"
static var _mesh: Mesh
static func clear() -> void:
	_mesh = null

static func cover_skin(model: Node3D, active: bool) -> void:
	var body := model.find_child("body", true, false) as MeshInstance3D
	if body != null and body.mesh != null:
		var material := body.get_active_material(0) as ShaderMaterial
		if material != null:
			material.set_shader_parameter("smooth_shirt_neckline", active and bool(model.get_meta(APPLIED, false)))

static func apply(model: Node3D, path: String) -> void:
	if path.replace("\\", "/") != ProjectSettings.globalize_path(BODY).replace("\\", "/") and path != BODY:
		return
	if _mesh == null:
		var candidate := GlbSceneCache.instantiate(REPAIRED)
		if candidate == null:
			push_error("Female shirt neckline mesh is missing")
			return
		for node: Node in candidate.find_children("*", "MeshInstance3D", true, false):
			if node.name == &"wardrobe_shirt":
				_mesh = (node as MeshInstance3D).mesh
		candidate.free()
	if _mesh == null:
		return
	for node: Node in model.find_children("*", "MeshInstance3D", true, false):
		if node.name == &"wardrobe_shirt":
			(node as MeshInstance3D).mesh = _mesh
			model.set_meta(APPLIED, true)
