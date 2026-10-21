extends SceneTree
## The harvest presentation (owner-approved 2026-10-14): a continent-v2
## package's harvestables entries present each node - its model variant, its
## exact yaw, a pick shaped to its footprint, its grouping, and promoted
## scenery bound to a kit placement already standing in its chunk - and its
## harvestGroupings are marked once each on the maps. A package from before
## (no harvestablesSchema) presents every node as it always did, except that a
## node whose label's own model is retired stands a variant marked
## `standsAlone`, or the ring when the label has none; the underground's seams
## and pans take the client's own table instead. Runtime nodes
## are painted by the look pass as the identical kit plant beside them is, and
## a region file's foliage.crown_tint tints its tree crowns, faded across the
## old continent's borders.
##
## eloria-assets/maps/continent-v2/_continent_v2/harvest_presentation.py
## writes the package side; its tests are tests/test_harvest_presentation.py
## there.

const REGISTRY := "res://data/world/objects.json"
const SCHEMA := "eloria-harvest-presentation-v1"

var failures := 0
var main: Control

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var previous_look := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "1")
	var catalog: Dictionary = _json(REGISTRY)
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [0.0, 0.0]})
	_check_node_presentation(adapter, catalog)
	_check_retired_label_fallback(adapter, catalog)
	_check_underground_presentation(catalog)
	_check_promoted_scenery(adapter, catalog)
	_check_look_parity(adapter)
	_check_crown_tint()
	_check_map_presentation_of()
	await _check_main(catalog)
	LookBorders.reload()
	LookProfile.reload_regions()
	OS.set_environment(LookProfile.ENABLE_VARIABLE, previous_look)
	print("harvest presentation tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --- one node -----------------------------------------------------------------

func _check_node_presentation(adapter: CoordinateAdapter, catalog: Dictionary) -> void:
	var resources: Dictionary = (catalog.harvestables as Dictionary).resources
	var label := "Sage" if resources.has("Sage") else str(resources.keys()[0])
	# An entry with no presentation stands exactly as before: seeded yaw and
	# scale, a 0.9 m cylinder, its own map marker.
	var plain := _object(adapter, catalog, label, 41)
	var plain_model := plain.get_node_or_null("Model") as Node3D
	var rng := RandomNumberGenerator.new()
	rng.seed = 41
	var yaw := rng.randf() * TAU
	var scale := rng.randf_range(0.92, 1.08)
	_expect(plain_model != null and is_equal_approx(plain_model.rotation.y, yaw)
		and is_equal_approx(plain_model.scale.x, scale),
		"a node without presentation keeps the yaw and scale its object id seeds")
	_expect(plain.get_node("PickShape").shape is CylinderShape3D
		and is_equal_approx((plain.get_node("PickShape").shape as CylinderShape3D).radius, 0.9),
		"and the 0.9 m pick cylinder")
	_expect(plain.get_node_or_null("MapMarker") != null and not plain.grouped,
		"and its own map marker")

	# A row segment: its yaw is exact, its footprint is its pick, and it stands
	# at scale 1 so butted segments meet.
	var row := _object(adapter, catalog, label, 42,
		{"yaw": 90.0, "footprint": [3.0, 0.9], "grouping": "north-farm", "grouped": true})
	var row_model := row.get_node_or_null("Model") as Node3D
	_expect(row_model != null and is_equal_approx(row_model.rotation.y, deg_to_rad(90.0))
		and row_model.scale.is_equal_approx(Vector3.ONE),
		"a package's yaw is applied exactly and a footprint stands its model at scale 1")
	var pick := row.get_node("PickShape") as CollisionShape3D
	var box := pick.shape as BoxShape3D
	_expect(box != null and is_equal_approx(box.size.x, 3.0) and is_equal_approx(box.size.z, 0.9)
		and box.size.y >= 1.2 and is_equal_approx(pick.rotation.y, deg_to_rad(90.0)),
		"the footprint is picked with a box of its length and width, turned with the row")
	_expect(row.grouped and row.grouping == "north-farm" and row.get_node_or_null("MapMarker") == null,
		"a grouped node has no map marker of its own")
	var thin := _object(adapter, catalog, label, 43, {"footprint": [2.0, 0.2]})
	_expect(is_equal_approx(((thin.get_node("PickShape") as CollisionShape3D).shape as BoxShape3D).size.z,
		MapObject3D.FOOTPRINT_PICK_MINIMUM),
		"a thin footprint is still a target a player can hit")
	_expect(is_equal_approx((thin.get_node("PickShape") as CollisionShape3D).rotation.y,
		(thin.get_node("Model") as Node3D).rotation.y),
		"and without a yaw its box turns with the seeded model")
	var named_only := _object(adapter, catalog, label, 44, {"grouping": "unlisted"})
	_expect(not named_only.grouped and named_only.get_node_or_null("MapMarker") != null,
		"a grouping the package does not list is not marked in place of the node")

	# Variants: the registry's list for the label, chosen by the package or by
	# the object id, the same on every client. Live models only: a retired one
	# stands nothing of its own.
	var models: Dictionary = (catalog.harvestables as Dictionary).models
	var choices: Array = []
	for model_id: String in ["isle_sage", "sage_clump_b", "isle_olive"]:
		if models.has(model_id) and not bool((models[model_id] as Dictionary).get("retired", false)):
			choices.append(model_id)
	var varied: Dictionary = catalog.duplicate(true)
	(varied.harvestables as Dictionary)["variants"] = {label: choices}
	var stated := _object(adapter, varied, label, 45, {"variant": 1})
	_expect(choices.size() == 3 and stated.model_id == choices[1],
		"a package's variant picks that model from the label's list: " + stated.model_id)
	var wrapped := _object(adapter, varied, label, 46, {"variant": 4.0})
	_expect(wrapped.model_id == choices[1], "a JSON variant past the list wraps round it")
	var seen := {}
	for identity: int in range(100, 130):
		var picked := _object(adapter, varied, label, identity, {"footprint": [1.5, 1.5]})
		_expect(picked.model_id == choices[MapObject3D.variant_index(identity, choices.size())],
			"a laid-out node without a stated variant has its object id pick one (%d)" % identity)
		seen[picked.model_id] = true
		picked.free()
	_expect(seen.size() == choices.size(), "and thirty nodes stand every variant")
	var unlaid := _object(adapter, varied, label, 48)
	_expect(unlaid.model_id == str(resources[label]),
		"a node its package does not lay out keeps the label's own model: " + unlaid.model_id)
	_expect(MapObject3D.variant_index(77, 1) == 0 and MapObject3D.variant_index(77, 3, 5) == 2,
		"one model is always variant 0, and a stated variant is taken modulo the list")
	var ghost: Dictionary = catalog.duplicate(true)
	(ghost.harvestables as Dictionary)["variants"] = {label: ["not_a_model"]}
	var fallback := _object(adapter, ghost, label, 47, {"variant": 0})
	_expect(fallback.model_id == str(resources[label]),
		"a listed variant the registry does not describe falls back to the label's model")

# --- a retired label's node that no package lays out ------------------------------
# The 2026-10-19 playtest map review, finding 6: such a node stands only a variant
# that stands alone (a clump or a mat reads right at its seeded yaw). A row, hedge,
# seam, bank, strand, drift or pan needs the footprint and yaw a package states, so
# a node of a label with none keeps the retired model's ring and name.

func _check_retired_label_fallback(adapter: CoordinateAdapter, catalog: Dictionary) -> void:
	var harvest: Dictionary = catalog.harvestables
	var models: Dictionary = harvest.models
	var variants: Dictionary = harvest.get("variants", {})
	var alone := {}
	for listed_label: String in variants:
		for model_id: Variant in variants[listed_label]:
			var entry: Dictionary = models.get(str(model_id), {})
			_expect(entry.get("standsAlone") is bool,
				"every listed variant says whether it stands alone: " + str(model_id))
			if bool(entry.get("standsAlone", false)):
				alone[str(model_id)] = true
	for model_id: String in ["reed_clump_a", "reed_clump_b", "reed_clump_c", "watercress_mat_a",
			"watercress_mat_b", "lavender_clump_a", "rosemary_clump_a", "rosemary_clump_b"]:
		_expect(alone.has(model_id), "a clump or mat stands alone: " + model_id)
	for shaped: String in ["Bramble", "Hearthroot", "Cotton", "Clay", "Quartz", "Salt", "Kelp", "Shell"]:
		for model_id: Variant in variants.get(shaped, []):
			_expect(not alone.has(str(model_id)),
				"a row, hedge, face, strand, drift or pan does not: " + str(model_id))
	_expect(not alone.has("lavender_clump_b"), "nor the lavender row on its tilled strip")

	# Reed's own model is retired and its clumps all stand alone: the clump the
	# object id picks, at the yaw and scale the object id seeds.
	_expect(bool((models.get(str(harvest.resources.get("Reed", "")), {}) as Dictionary).get("retired", false)),
		"Reed's own model is retired")
	var reeds: Array = (variants.get("Reed", []) as Array).filter(
		func(model_id: Variant) -> bool: return alone.has(str(model_id)))
	var reed := _object(adapter, catalog, "Reed", 4101)
	var reed_model := reed.get_node_or_null("Model") as Node3D
	var rng := RandomNumberGenerator.new()
	rng.seed = 4101
	var yaw := rng.randf() * TAU
	var scale := rng.randf_range(0.92, 1.08)
	_expect(not reeds.is_empty() and reed.model_id == reeds[MapObject3D.variant_index(4101, reeds.size())],
		"an undescribed Reed node stands the reed clump its object id picks: " + reed.model_id)
	_expect(reed_model != null and is_equal_approx(reed_model.rotation.y, yaw)
		and is_equal_approx(reed_model.scale.x, scale) and not reed.get_node("Ring").visible,
		"at its seeded yaw and scale, with no idle ring")
	reed.free()
	# Lavender has a clump and a planted row: only the clump stands in.
	for identity: int in range(4110, 4116):
		var lavender := _object(adapter, catalog, "Lavender", identity)
		_expect(lavender.model_id == "lavender_clump_a",
			"an undescribed Lavender node always stands the clump (%d): %s" % [identity, lavender.model_id])
		lavender.free()

	# Bramble's variants are all hedge segments: no hedge at a random yaw.
	_expect(bool((models.get(str(harvest.resources.get("Bramble", "")), {}) as Dictionary).get("retired", false)),
		"Bramble's own model is retired")
	var bramble := _object(adapter, catalog, "Bramble", 4102)
	_expect(bramble.model_id.is_empty() and bramble.get_node_or_null("Model") == null,
		"an undescribed Bramble node stands no hedge: " + bramble.model_id)
	_expect((bramble.get_node("Ring") as MeshInstance3D).visible
		and (bramble.get_node("ResourceLabel") as Label3D).text == "Bramble",
		"it keeps the bare ring and its resource name")
	bramble.free()
	# Laid out by its package, the same label stands its hedge where it is told.
	var hedges: Array = variants.get("Bramble", [])
	var hedge := _object(adapter, catalog, "Bramble", 4103,
		{"variant": 1, "yaw": 30.0, "footprint": [2.8, 0.8]})
	var hedge_model := hedge.get_node_or_null("Model") as Node3D
	_expect(hedges.size() > 1 and hedge.model_id == str(hedges[1]) and hedge_model != null
		and is_equal_approx(hedge_model.rotation.y, deg_to_rad(30.0)),
		"a laid-out Bramble node stands its stated hedge at its stated yaw")
	hedge.free()

# --- the underground's seams and pans ----------------------------------------------
# The underground package (landfall_insides) states no harvest presentation, and its
# Quartz and Salt labels have retired models and no variant that stands alone. The
# client's own table (underground-scenery.json harvestPresentation) lays them out.

func _check_underground_presentation(catalog: Dictionary) -> void:
	var scenery := preload("res://src/world/underground_scenery.gd")
	var table: Dictionary = scenery.harvest_presentation("landfall_insides")
	_expect(scenery.harvest_presentation("landfall").is_empty(), "no other map takes the underground's table")
	var package := _json("res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json")
	var harvest: Dictionary = catalog.harvestables
	var variants: Dictionary = harvest.get("variants", {})
	var needed := 0
	var stated := 0
	for value: Variant in package.get("harvestables", []):
		var node := value as Dictionary
		var resource := str(node.resource)
		var own: Dictionary = (harvest.models as Dictionary).get(str(harvest.resources.get(resource, "")), {})
		var listed: Array = variants.get(resource, [])
		var alone := listed.any(func(model_id: Variant) -> bool:
			return bool((harvest.models as Dictionary).get(str(model_id), {}).get("standsAlone", false)))
		var hint: Dictionary = table.get(str(int(node.objectId)), {})
		# A label whose own model is retired and whose variants need a stated
		# footprint must be laid out; a label with its own model may be (Flint's
		# seams face the room), and then states a valid variant too.
		var must := bool(own.get("retired", false)) and not listed.is_empty() and not alone
		if not must and hint.is_empty():
			continue
		_expect(str(hint.get("resource", "")) == resource and hint.get("variant") is float
			and int(hint.variant) >= 0 and int(hint.variant) < listed.size() and hint.get("yaw") is float,
			"underground %s node %d states its variant and yaw" % [resource, int(node.objectId)])
		needed += 1 if must else 0
		stated += 1
	_expect(needed >= 7 and stated == table.size(),
		"the table presents every underground node that needs it and names no other (%d needed, %d of %d stated)"
		% [needed, stated, table.size()])

# --- promoted scenery ---------------------------------------------------------

func _check_promoted_scenery(adapter: CoordinateAdapter, catalog: Dictionary) -> void:
	var node := _object(adapter, catalog, "Olive", 106,
		{"bind": {"node": "Authored_landfall_kit_olive_tree_1_017", "chunk": "08_10", "height": 5.2}})
	_expect(node.get_node_or_null("Model") == null and node.bound_node_name == "Authored_landfall_kit_olive_tree_1_017"
		and node.model_id == "bound_Authored_landfall_kit_olive_tree_1_017",
		"promoted scenery stands no model of its own")
	var ring := node.get_node("Ring") as MeshInstance3D
	_expect(not ring.visible, "and keeps its ring hidden until it is harvested")
	node.set_active(true)
	_expect(ring.visible, "the ring still marks the tree being harvested")
	node.set_active(false)
	_expect(is_equal_approx((node.get_node("PickShape").shape as CylinderShape3D).height, 5.2),
		"its own pick stands as tall as the placed tree")
	# The placed tree, hidden by the loader's static batching (its MultiMesh draws it).
	var cell := Node3D.new()
	root.add_child(cell)
	var tree := _kit_tree(cell, "Authored_landfall_kit_olive_tree_1_017", Vector3(30, 0, 40))
	(tree.get_child(0) as MeshInstance3D).visible = false
	(tree.get_child(0) as MeshInstance3D).set_meta(WorldLoader.BATCH_META, MultiMeshInstance3D.new())
	_expect(node.bind_placement(tree) and node.placement_bound(),
		"the pick binds to the placed mesh, batched or not")
	var body := tree.get_node_or_null("MapObjectPickProxy") as StaticBody3D
	_expect(body != null and body.collision_layer == MapObject3D.PICK_LAYER
		and MapObject3D.from_pick_collider(body) == node,
		"and clicking the tree is clicking the node")
	node.release_placement()
	_expect(not node.placement_bound(), "a chunk streaming out lets the binding go")
	cell.free()

# --- look parity ---------------------------------------------------------------

func _check_look_parity(adapter: CoordinateAdapter) -> void:
	var atlas := StandardMaterial3D.new()
	atlas.resource_name = "Material_0"
	atlas.cull_mode = BaseMaterial3D.CULL_DISABLED
	var chunk := Node3D.new()
	chunk.name = "ImportedWorld_parity__chunk_8_10"
	root.add_child(chunk)
	var placed := _mesh(chunk, "kit-olive-tree-1", atlas, Vector3(4, 5, 4), Vector3(10, 0, 10))
	LookFoliage.paint(chunk, "parity")
	# A runtime node whose model is the same kit plant.
	var node := MapObject3D.new()
	root.add_child(node)
	node.configure({"object_id": 9, "kind": EloriaProtocol.MAP_OBJECT_HARVEST, "x": 12, "y": 12,
		"label": "Nothing The Registry Knows", "detail": ""}, adapter, {})
	var model := Node3D.new()
	model.name = "Model"
	node.add_child(model)
	var twin := MeshInstance3D.new()
	twin.name = "kit-olive-tree-1"
	twin.mesh = placed.mesh
	model.add_child(twin)
	var surfaces := LookFoliage.paint_object(node, "parity", node.transform)
	var a := placed.get_surface_override_material(0) as ShaderMaterial
	var b := twin.get_surface_override_material(0) as ShaderMaterial
	_expect(surfaces >= 1 and a != null and b != null and a.shader == b.shader,
		"a runtime node is painted with the shader the kit plant beside it takes")
	var differing := []
	if a != null and b != null:
		for uniform: Dictionary in a.shader.get_shader_uniform_list():
			var key := StringName(uniform.name)
			if key != &"look_seed" and a.get_shader_parameter(key) != b.get_shader_parameter(key):
				differing.append(String(key))
	_expect(differing.is_empty(), "and every parameter but its jitter seed: %s" % [differing])
	_expect(LookSwitch.revert(node) >= 1 and twin.get_surface_override_material(0) == null,
		"switching the look off gives the node its own material back")
	node.free()
	chunk.free()

# --- crown tint ------------------------------------------------------------------

func _check_crown_tint() -> void:
	var problems := LookProfile.define_region("tint_west", {"id": "tint_west", "schema": 1,
		"foliage": {"crown_tint": [0.75, 1.0, 0.625]}})
	_expect(problems.is_empty(), "foliage.crown_tint is a region colour key: %s" % [problems])
	_expect(not LookProfile.define_region("tint_bad", {"id": "tint_bad", "schema": 1,
		"foliage": {"crown_tint": "leafy"}}).is_empty(), "and a malformed one is reported")
	LookProfile.define_region("tint_east", {"id": "tint_east", "schema": 1})
	LookBorders.define({
		"tint_west": [[0, 0], [100, 0], [100, 100], [0, 100]],
		"tint_east": [[100, 0], [100, 100], [200, 100], [200, 0]],
		"tint_far": [[400, 0], [500, 0], [500, 100], [400, 100]],
	})
	var feather := LookProfile.BORDER_FEATHER_METRES
	_expect(LookFoliage.crown_tint_at("tint_west", Vector2(10, 50)) == Color(0.75, 1.0, 0.625),
		"a region's crowns take its tint")
	_expect(LookFoliage.crown_tint_at("tint_west", Vector2(100, 50)) == Color(0.875, 1.0, 0.8125)
		and LookFoliage.crown_tint_at("tint_east", Vector2(100, 50)) == Color(0.875, 1.0, 0.8125),
		"on the border line both sides meet at the mean")
	_expect(LookFoliage.crown_tint_at("tint_east", Vector2(100 + feather + 1, 50)) == Color.WHITE,
		"a feather inside the neighbour is its own")
	_expect(LookFoliage.crown_tints_near("tint_far").is_empty(),
		"a region with no tint and no tinted neighbour works nothing out per crown")
	var atlas := StandardMaterial3D.new()
	atlas.resource_name = "Material_0"
	atlas.cull_mode = BaseMaterial3D.CULL_DISABLED
	var chunk := Node3D.new()
	root.add_child(chunk)
	var oak := _mesh(chunk, "kit-green-oak-1", atlas, Vector3(5, 7, 5), Vector3(10, 0, 50))
	var shrub := _mesh(chunk, "kit-green-shrub-1", atlas.duplicate(), Vector3(2, 2, 2), Vector3(12, 0, 50))
	# The root's frame is its territory's; the meta says where that lies.
	var shifted := _mesh(chunk, "kit-green-oak-2", atlas, Vector3(5, 7, 5), Vector3(0, 0, 50))
	shifted.reparent(Node3D.new())
	var border_chunk := Node3D.new()
	root.add_child(border_chunk)
	border_chunk.set_meta(LookFoliage.CONTINENT_META, Vector2(100, 0))
	var moved := _mesh(border_chunk, "kit-green-oak-3", atlas, Vector3(5, 7, 5), Vector3(0, 0, 50))
	LookFoliage.paint(chunk, "tint_west")
	LookFoliage.paint(border_chunk, "tint_west")
	_expect(_tint_of(oak) == Vector3(0.75, 1.0, 0.625), "a tree crown is painted with the tint")
	_expect(_tint_of(shrub) == Vector3.ONE, "a shrub is not a tree crown and keeps white")
	_expect(_tint_of(moved) == Vector3(0.875, 1.0, 0.8125),
		"a crown is placed by its territory's translation before the border is asked")
	var plain := Node3D.new()
	root.add_child(plain)
	var untinted := _mesh(plain, "kit-green-oak-1", atlas, Vector3(5, 7, 5), Vector3(10, 0, 50))
	LookFoliage.paint(plain, "tint_far")
	_expect(_tint_of(untinted) == Vector3.ONE, "a region that sets none paints its crowns as before")
	shifted.get_parent().free()
	chunk.free()
	border_chunk.free()
	plain.free()

func _tint_of(node: MeshInstance3D) -> Vector3:
	var painted := node.get_surface_override_material(0) as ShaderMaterial
	if painted == null:
		return Vector3(-1, -1, -1)
	var value: Variant = painted.get_shader_parameter(&"look_crown_tint")
	return value if value is Vector3 else Vector3(-1, -1, -1)

# --- the package ---------------------------------------------------------------------

func _check_map_presentation_of() -> void:
	var script: Script = load("res://src/app/main.gd")
	_expect(script != null and script.can_instantiate(), "main.gd compiles")
	if script == null:
		return
	var manifest := _manifest()
	var read: Dictionary = script.call("map_presentation_of", "landfall", manifest.data,
		{"7": {"height": 2.0, "radius": 1.1}})
	var nodes: Dictionary = read.nodes
	_expect(nodes.has(100) and nodes[100].get("grouped", false) and nodes[100].get("yaw") == 90.0,
		"a package entry presents its node, keyed by its object id as an int")
	_expect(not nodes.has(103) or not nodes[103].has("grouped"),
		"a node outside every grouping is not grouped")
	_expect(nodes.has(104) and (nodes[104].bind as Dictionary).node == "Authored_landfall_kit_olive_tree_1_017",
		"and promoted scenery keeps its binding")
	_expect(nodes.has(7) and (nodes[7].pick as Dictionary).radius == 1.1,
		"a lantern map's authored pick is the same presentation, scoped to its map")
	_expect((read.groupings as Array).size() == 1, "the groupings are read")
	var old := manifest.data.duplicate(true)
	old.erase("harvestablesSchema")
	var before: Dictionary = script.call("map_presentation_of", "landfall", old, {})
	_expect((before.nodes as Dictionary).is_empty() and (before.groupings as Array).is_empty(),
		"a package without the schema presents nothing (the older packages' harvestables are other records)")
	# The client's own table (the underground's) presents the nodes a package
	# leaves bare; a node the package presents keeps the package's.
	var authored := {"1201": {"resource": "Quartz", "variant": 0.0, "yaw": 241.054},
		"100": {"variant": 0.0, "yaw": 5.0}, "not an id": {"variant": 1.0}, "1302": "malformed"}
	var bare: Dictionary = script.call("map_presentation_of", "landfall_insides", {}, {}, authored)
	var quartz: Dictionary = (bare.nodes as Dictionary).get(1201, {})
	_expect(quartz.get("variant") == 0.0 and quartz.get("yaw") == 241.054 and not quartz.has("resource"),
		"a client-authored entry presents a node the package leaves bare")
	_expect((bare.nodes as Dictionary).size() == 2, "and nothing malformed is read")
	var mixed: Dictionary = script.call("map_presentation_of", "landfall", manifest.data, {}, authored)
	_expect(mixed.nodes[100].get("yaw") == 90.0 and mixed.nodes[100].get("variant") == 1.0,
		"a node its package presents keeps the package's presentation")

func _manifest() -> WorldManifest:
	var manifest := WorldManifest.new()
	var row := [{"objectId": 100, "id": "m-100", "resource": "Sage", "serverTile": [10, 10],
			"yaw": 90.0, "footprint": [3.0, 0.9], "grouping": "north-farm", "variant": 1.0},
		{"objectId": 101.0, "id": "m-101", "resource": "Sage", "serverTile": [13, 10],
			"yaw": 90.0, "footprint": [3.0, 0.9], "grouping": "north-farm"},
		{"objectId": 102, "id": "m-102", "resource": "Sage", "serverTile": [16, 10],
			"grouping": "north-farm"},
		{"objectId": 103, "id": "m-103", "resource": "Sage", "serverTile": [30, 30]},
		{"objectId": 104, "id": "m-104", "resource": "Olive", "serverTile": [40, 40],
			"bind": {"node": "Authored_landfall_kit_olive_tree_1_017", "assetId": "x", "chunk": "08_10",
				"height": 5.2}}]
	manifest.data = {"asset": {"id": "landfall"},
		"continentGeography": {"translation": [1000.0, 0.0, 2000.0]},
		"harvestablesSchema": SCHEMA, "harvestables": row,
		"harvestGroupings": [{"id": "north-farm", "name": "North Wall farm", "resources": ["Sage"],
			"centre": [13.5, -10.5], "centreTile": [13, 10], "nodeCount": 3,
			"objectIds": [100, 101, 102]}]}
	return manifest

# --- main --------------------------------------------------------------------------------

func _check_main(catalog: Dictionary) -> void:
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var state: Node = root.get_node("AppState")
	root.get_node("Network").set_process(false)
	var chunks := ContinentChunkStream.new()
	main.world_root.add_child(chunks)
	main.world_loader.world_root = chunks
	main._watch_chunk_surfaces()
	_expect(chunks.cell_retiring.is_connected(main._on_chunk_cell_retiring),
		"a chunk streaming out is watched")
	var manifest := _manifest()
	main.world_loader.manifest = manifest
	state.current_map = "landfall"
	var objects := {}
	for entry: Dictionary in manifest.data.harvestables:
		var tile: Array = entry.serverTile
		var identity := int(entry.objectId)
		objects[identity] = {"object_id": identity, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
			"x": int(tile[0]), "y": int(tile[1]), "label": str(entry.resource), "detail": ""}
	state.map_objects = objects
	# Listed while the map was still loading: built without its presentation.
	main._sync_map_objects()
	var early: MapObject3D = main.map_object_nodes[100]
	_expect(early.presentation.is_empty(), "an object listed before its map binds has no presentation")
	main._bind_map_presentation(manifest)
	main._sync_map_objects()
	await process_frame
	var sage: MapObject3D = main.map_object_nodes[100]
	_expect(sage != early and sage.grouped and is_equal_approx(
		(sage.get_node("Model") as Node3D).rotation.y, deg_to_rad(90.0)),
		"the map's binding builds it again with its package's presentation")
	var marks: Array[Dictionary] = main._collect_minimap_marks()
	var harvest := marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"harvest")
	var grouping := harvest.filter(func(mark: Dictionary) -> bool: return mark.has("grouping"))
	_expect(harvest.size() == 3 and grouping.size() == 1,
		"the maps mark the grouping once and the two ungrouped nodes each (%d harvest marks)" % harvest.size())
	if grouping.size() == 1:
		var mark: Dictionary = grouping[0]
		var centre: Vector3 = main.adapter.tile_center(13, 10)
		_expect(str(mark.label) == "North Wall farm" and is_equal_approx(float(mark.radius),
			main.HARVEST_GROUPING_RADIUS) and is_equal_approx((mark.position as Vector3).x, centre.x)
			and is_equal_approx((mark.position as Vector3).z, centre.z),
			"at its centre tile, named, a little larger than a node's dot")
	var named := false
	for point: Dictionary in main._collect_map_waypoints():
		named = named or (str(point.get("label", "")) == "North Wall farm"
			and str(point.get("glyph", "x")).is_empty())
	_expect(named, "and the full map names it on hover")

	# Promoted scenery binds to its placement as its chunk arrives, lets go as
	# it streams out and binds again when it is back.
	var olive: MapObject3D = main.map_object_nodes[104]
	_expect(olive.get_node_or_null("Model") == null and not olive.placement_bound(),
		"a promoted tree waits for its chunk")
	var cell := Node3D.new()
	cell.name = "Cell_08_10"
	chunks.add_child(cell)
	_kit_tree(cell, "Authored_landfall_kit_olive_tree_1_017", Vector3(40, 0, -40))
	chunks.cells["08_10"] = {"root": cell}
	chunks.cell_ready.emit("08_10", cell)
	await process_frame
	await process_frame
	_expect(olive.placement_bound(), "and binds to the placed tree when the chunk is ready")
	chunks.cell_retiring.emit("08_10", cell)
	_expect(not olive.placement_bound(), "a retiring chunk takes the binding with it")
	chunks.cell_ready.emit("08_10", cell)
	await process_frame
	await process_frame
	_expect(olive.placement_bound(), "and it binds again when the chunk is back")
	chunks.cells.erase("08_10")

	# A package from before: every node is its own mark again.
	var old := WorldManifest.new()
	old.data = {"asset": {"id": "landfall"}, "continentGeography": {"translation": [0.0, 0.0, 0.0]},
		"harvestables": []}
	main._bind_map_presentation(old)
	for raw: Variant in main.map_object_nodes.values():
		(raw as Node).queue_free()
	main.map_object_nodes.clear()
	main._sync_map_objects()
	await process_frame
	marks = main._collect_minimap_marks()
	harvest = marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"harvest")
	var grouped_marks := harvest.filter(func(mark: Dictionary) -> bool: return mark.has("grouping"))
	_expect(harvest.size() == 5 and grouped_marks.is_empty(),
		"a package without the presentation marks every node itself")
	_expect((main.map_object_nodes[100] as MapObject3D).get_node_or_null("MapMarker") != null,
		"and keeps its per-node marker")

	# The lantern island's authored pick shapes are the same presentation,
	# read for their own map only.
	state.map_objects = {}
	main._sync_map_objects()
	main.world_loader.manifest = null
	state.current_map = "cinderbank"
	var island := WorldManifest.new()
	island.data = {"asset": {"id": "cinderbank"}}
	main._bind_map_presentation(island)
	state.map_objects = {7310: {"object_id": 7310, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
		"x": 60, "y": 70, "label": "Iron Ore", "detail": ""}}
	main._sync_map_objects()
	var seam: MapObject3D = main.map_object_nodes[7310]
	var seam_pick := seam.get_node("PickShape").shape as CylinderShape3D
	_expect(seam.get_node_or_null("Model") == null and seam.model_id == "map_authored_7310"
		and seam_pick != null and is_equal_approx(seam_pick.radius, 1.25)
		and is_equal_approx(seam_pick.height, 1.9),
		"Cinderbank's authored ore seam takes its layout's pick and stands no model")
	state.current_map = "landfall"
	main._bind_map_presentation(island)
	main.map_object_nodes.clear()
	(seam as Node).queue_free()
	main._sync_map_objects()
	var elsewhere: MapObject3D = main.map_object_nodes[7310]
	_expect(elsewhere.model_id != "map_authored_7310" and not elsewhere.presentation.has("pick"),
		"and the same object id on another map does not take it")
	state.map_objects = {}
	main._sync_map_objects()
	await process_frame

# --- helpers --------------------------------------------------------------------------------

func _object(adapter: CoordinateAdapter, catalog: Dictionary, label: String, object_id: int,
		presentation: Dictionary = {}) -> MapObject3D:
	var node := MapObject3D.new()
	root.add_child(node)
	node.configure({"object_id": object_id, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
		"x": 10, "y": 10, "label": label, "detail": ""}, adapter, catalog, false, presentation)
	return node

func _kit_tree(parent: Node, node_name: String, at: Vector3) -> Node3D:
	var placement := Node3D.new()
	placement.name = node_name
	placement.position = at
	parent.add_child(placement)
	var trunk := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(4, 5, 4)
	trunk.mesh = box
	placement.add_child(trunk)
	return placement

func _mesh(parent: Node, node_name: String, material: Material, size: Vector3,
		at: Vector3) -> MeshInstance3D:
	var box := BoxMesh.new()
	box.size = size
	var tool := SurfaceTool.new()
	tool.create_from(box, 0)
	var arrays := tool.commit_to_arrays()
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	for index: int in vertices.size():
		vertices[index].y += size.y * 0.5
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.position = at
	parent.add_child(node)
	return node

static func _json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
