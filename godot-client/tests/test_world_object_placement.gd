extends SceneTree
## A world object stands its own model on its tile, and falls back to a ring.
##
## The models were authored, the registry described all fifty-two of them and
## every GLB was on disk - and every harvest node in the world drew a bare green
## ring anyway, because the one place that builds these objects called
## `configure` without the registry and an empty one is a legal one. This walks
## the same path with the real `data/world/objects.json`: a resource the
## registry names gets its model and no ring, one it does not gets the ring.

const REGISTRY := "res://data/world/objects.json"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var catalog: Dictionary = _json(REGISTRY)
	_expect(not catalog.is_empty(), "the registry loads from the path main.gd reads")
	var resources: Dictionary = (catalog.get("harvestables", {}) as Dictionary).get(
		"resources", {}) as Dictionary
	var roles: Dictionary = (catalog.get("interactives", {}) as Dictionary).get(
		"roles", {}) as Dictionary
	_expect(resources.size() >= 40, "and names a model for each of the resources in play")
	_expect(roles.size() >= 5, "and one for each interactive role")

	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [0.0, 0.0]})
	var known: String = resources.keys()[0]
	var node := _object(adapter, catalog, EloriaProtocol.MAP_OBJECT_HARVEST, known, 1)
	_expect(node.get_node_or_null("Model") != null,
		"a node whose resource the registry names stands its model: " + known)
	var ring: MeshInstance3D = node.get_node_or_null("Ring") as MeshInstance3D
	_expect(ring != null and not ring.visible,
		"and does not draw the ring that stands in for a missing model")
	_expect(not node.model_id.is_empty(), "and remembers which model it placed")
	# GLTFDocument builds runtime textures with no mip chain; a node's texture
	# minified at the gameplay camera would alias and swim without one.
	var texture := _albedo_texture(node.get_node_or_null("Model"))
	_expect(texture != null and texture.get_image() != null and texture.get_image().has_mipmaps(),
		"and its texture carries a mip chain: " + known)
	var material := _first_material(node.get_node_or_null("Model"))
	_expect(material != null and material.texture_filter ==
		BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC,
		"and is sampled anisotropically, like the map around it: " + known)

	var role: String = roles.keys()[0]
	var built := _object(adapter, catalog, EloriaProtocol.MAP_OBJECT_INTERACTIVE, role, 2)
	_expect(built.get_node_or_null("Model") != null,
		"an interactive stands its model too: " + role)

	var stranger := _object(adapter, catalog, EloriaProtocol.MAP_OBJECT_HARVEST,
		"Nothing The Registry Knows", 3)
	_expect(stranger.get_node_or_null("Model") == null,
		"a resource the registry does not name places nothing")
	var fallback: MeshInstance3D = stranger.get_node_or_null("Ring") as MeshInstance3D
	_expect(fallback != null and fallback.visible,
		"and falls back to the ring, which is what the ring is for")

	# Two of the same node are varied, so a hillside of ore is not one model
	# stamped in a row; the object id is what makes it the same on every client.
	var first := _object(adapter, catalog, EloriaProtocol.MAP_OBJECT_HARVEST, known, 11)
	var second := _object(adapter, catalog, EloriaProtocol.MAP_OBJECT_HARVEST, known, 12)
	var one: Node3D = first.get_node_or_null("Model") as Node3D
	var two: Node3D = second.get_node_or_null("Model") as Node3D
	_expect(one != null and two != null and not is_equal_approx(one.rotation.y, two.rotation.y),
		"two of the same node do not stand identically")
	var workshop_catalog: Dictionary = catalog.duplicate(true)
	workshop_catalog.authoredObjects = {"7310":{"height":1.9,"radius":1.25}}
	var seam := _object(adapter, workshop_catalog, EloriaProtocol.MAP_OBJECT_HARVEST, "Iron Ore", 7310)
	_expect(seam.get_node_or_null("Model") == null, "Authored ore is not doubled by a catalog model")
	_expect(not seam.get_node("Ring").visible, "Authored ore keeps its idle ring hidden")
	seam.set_active(true)
	_expect(seam.get_node("Ring").visible, "Real harvesting still highlights the authored seam")
	_expect(seam.get_node_or_null("MapMarker") != null, "Authored resources keep their map markers")
	var pick: CylinderShape3D = seam.get_node("PickShape").shape
	_expect(is_equal_approx(pick.height,1.9) and is_equal_approx(pick.radius,1.25), "Pick volume matches the authored resource")
	_check_imported_models(adapter, catalog, resources)
	var crossing := MapObject3D.new()
	root.add_child(crossing)
	crossing.configure({"object_id": 23, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x": 10, "y": 10, "label": "Portal", "detail": "Beyond it lies Whitehorn Range."},
		adapter, catalog, true)
	_expect(crossing.get_node_or_null("Model") == null and crossing.get_node_or_null("Ring") == null,
		"an authored landscape crossing adds no second monument or ring")
	_expect(crossing.is_portal() and crossing.map_glyph() == "P" and crossing.destination() == "Whitehorn Range",
		"the crossing retains its interaction identity and map destination")

	print("world object placement tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## The imported harvest nodes (the reviewed Meshy kits that
## `imported_world_objects.py` lists) are not the generator's own GLBs: they
## carry an embedded JPEG texture and ten times the triangles. Every label the
## registry hands to one must stand that model through the same runtime parse,
## textured and mip-mapped, with its ring hidden and a pick shape as tall as
## the model. Which labels those are is read from the registry, so a swap or
## its undoing is the table's flag and a regeneration, never an edit here.
func _check_imported_models(adapter: CoordinateAdapter, catalog: Dictionary,
		resources: Dictionary) -> void:
	var models: Dictionary = (catalog.get("harvestables", {}) as Dictionary).get(
		"models", {}) as Dictionary
	var answered := 0
	var object_id := 500
	for resource_label: String in resources:
		var model_key := str(resources[resource_label])
		var described: Dictionary = models.get(model_key, {}) as Dictionary
		if not bool(described.get("imported", false)):
			continue
		answered += 1
		object_id += 1
		var placed := _object(adapter, catalog, EloriaProtocol.MAP_OBJECT_HARVEST,
			resource_label, object_id)
		var model: Node3D = placed.get_node_or_null("Model") as Node3D
		_expect(model != null and placed.model_id == model_key,
			"an imported node stands its own model: %s -> %s" % [resource_label, model_key])
		if model == null:
			continue
		_expect(not (placed.get_node("Ring") as MeshInstance3D).visible,
			"and hides the ring under it: " + resource_label)
		var texture := _albedo_texture(model)
		_expect(texture != null, "and draws its embedded texture: " + resource_label)
		_expect(texture != null and texture.get_image() != null and texture.get_image().has_mipmaps(),
			"and that texture carries a mip chain: " + resource_label)
		var pick: CylinderShape3D = placed.get_node("PickShape").shape
		var standing := maxf(float(described.get("height", 0.0)) * model.scale.y, 1.2)
		_expect(is_equal_approx(pick.height, standing),
			"and is picked over the height the registry measured: " + resource_label)
	# Olive and Lemon are the isle's own crops: no procedural model serves them,
	# so they must always resolve to an imported one.
	for expected: String in ["Olive", "Lemon"]:
		var key := str(resources.get(expected, ""))
		_expect(bool((models.get(key, {}) as Dictionary).get("imported", false)),
			"%s resolves to an imported model" % expected)
	_expect(answered >= 2, "at least the two crops stand imported models")

static func _first_material(model: Node) -> BaseMaterial3D:
	if model == null:
		return null
	for node: Node in [model] + model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node != null and mesh_node.mesh != null and mesh_node.mesh.get_surface_count() > 0:
			return mesh_node.get_active_material(0) as BaseMaterial3D
	return null

static func _albedo_texture(model: Node) -> Texture2D:
	var material := _first_material(model)
	return material.albedo_texture if material != null else null

func _object(adapter: CoordinateAdapter, catalog: Dictionary, kind: int,
		label: String, object_id: int) -> MapObject3D:
	var node := MapObject3D.new()
	root.add_child(node)
	node.configure({"object_id": object_id, "kind": kind, "x": 10, "y": 10,
		"label": label, "detail": ""}, adapter, catalog)
	return node

static func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
