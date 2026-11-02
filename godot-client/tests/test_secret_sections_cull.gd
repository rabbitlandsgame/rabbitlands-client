extends SceneTree
## SecretSections judges actors and map objects by where they stand every
## frame. Its packed, remembered section lookup must give exactly the answer
## of the plain first-match scan over the manifest's sections (bounds grown by
## the margin, earliest listed section first), for nodes that stand still,
## nodes that wander, nodes that jump between sections, and points inside two
## sections' grown bounds at once.

const SectionsScript := preload("res://src/world/secret_sections.gd")
var failures := 0
var checks := 0

const SECTIONS := [
	{"id": "alpha", "bounds": {"min": [0, 0], "max": [40, 40]}},
	# 4 m east of alpha: the grown bounds overlap in the gap.
	{"id": "beta", "bounds": {"min": [44, 0], "max": [80, 40]}},
	{"id": "gamma", "bounds": {"min": [0, 50], "max": [40, 90]}},
	{"id": "delta", "bounds": {"min": [100, 100], "max": [140, 140]}},
	# Overlaps delta outright: delta, listed first, keeps the shared ground.
	{"id": "epsilon", "bounds": {"min": [130, 100], "max": [170, 140]}},
	{"id": "zeta", "bounds": {"min": [-60, -60], "max": [-20, -20]}},
]


func _init() -> void:
	call_deferred("_run")


## The lookup as it was written before the packed index: a scan in list order.
func _reference_section(point: Vector2) -> String:
	for entry: Dictionary in SECTIONS:
		var lo := Vector2(float(entry.bounds.min[0]), float(entry.bounds.min[1]))
		var hi := Vector2(float(entry.bounds.max[0]), float(entry.bounds.max[1]))
		if point.x >= lo.x - SectionsScript.MARGIN and point.x <= hi.x + SectionsScript.MARGIN \
				and point.y >= lo.y - SectionsScript.MARGIN and point.y <= hi.y + SectionsScript.MARGIN:
			return str(entry.id)
	return ""


func _run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	for entry: Dictionary in SECTIONS:
		var floor_mesh := MeshInstance3D.new()
		floor_mesh.name = "Walk_%s_stone" % entry.id
		world.add_child(floor_mesh)
	var manifest := WorldManifest.new()
	manifest.data = {"sectioned": true, "sections": SECTIONS}
	var sections = SectionsScript.new()
	_expect(sections.configure(manifest, world) == SECTIONS.size(), "every section's floor is claimed")
	sections.update(Vector3(20, 0, 20), true)
	_expect(sections.current_section() == "alpha", "the player starts in alpha")

	var rng := RandomNumberGenerator.new()
	rng.seed = 20261102
	var nodes: Array[Node3D] = []
	for index: int in range(240):
		var node := Node3D.new()
		node.position = Vector3(rng.randf_range(-70, 180), 0, rng.randf_range(-70, 150))
		world.add_child(node)
		nodes.append(node)
	var keep := nodes[0]
	keep.visible = true
	var mismatches := 0
	var player_stops := [Vector3(20, 0, 20), Vector3(60, 0, 20), Vector3(42, 0, 20),
		Vector3(120, 0, 120), Vector3(135, 0, 120), Vector3(160, 0, 120), Vector3(-40, 0, -40)]
	for round_index: int in range(60):
		if round_index % 8 == 0:
			sections.update(player_stops[floori(round_index / 8.0) % player_stops.size()], true)
		for node: Node3D in nodes:
			var roll := rng.randf()
			if roll < 0.35:
				# Stands still: the remembered answer is reused.
				pass
			elif roll < 0.8:
				# Wanders a little, often across a gap or a shared edge.
				node.position += Vector3(rng.randf_range(-4, 4), 0, rng.randf_range(-4, 4))
			else:
				node.position = Vector3(rng.randf_range(-70, 180), 0, rng.randf_range(-70, 150))
			if rng.randf() < 0.05:
				# Something else showed it: the next pass re-asserts the cull.
				node.visible = true
		sections.cull_dynamic(nodes, keep)
		var current: String = sections.current_section()
		for node: Node3D in nodes:
			if node == keep:
				continue
			var wanted: bool = _reference_section(Vector2(node.position.x, node.position.z)) == current
			if node.visible != wanted:
				mismatches += 1
	_expect(mismatches == 0, "the remembered lookup matches the list-order scan (%d mismatches)" % mismatches)
	_expect(keep.visible, "the kept node is never culled")

	# Points on the shared ground pick the earlier section, whichever section
	# the node was last judged in.
	sections.update(Vector3(60, 0, 20), true)
	var walker := Node3D.new()
	world.add_child(walker)
	walker.position = Vector3(70, 0, 20)
	sections.cull_dynamic([walker])
	_expect(walker.visible, "a node in beta is shown to a player in beta")
	walker.position = Vector3(42, 0, 20)
	sections.cull_dynamic([walker])
	_expect(_reference_section(Vector2(42, 20)) == "alpha" and not walker.visible,
		"the gap between alpha and beta belongs to alpha, listed first")
	sections.update(Vector3(120, 0, 120), true)
	walker.position = Vector3(160, 0, 120)
	sections.cull_dynamic([walker])
	_expect(not walker.visible, "a node in epsilon is hidden from a player in delta")
	walker.position = Vector3(135, 0, 120)
	sections.cull_dynamic([walker])
	_expect(walker.visible, "ground delta and epsilon share is delta's, even for a node coming from epsilon")

	# Freed inputs are skipped and reset still restores what it hid.
	var doomed := Node3D.new()
	world.add_child(doomed)
	doomed.position = Vector3(20, 0, 20)
	sections.cull_dynamic([doomed])
	var stale: Variant = doomed
	doomed.free()
	sections.cull_dynamic([stale, walker])
	_expect(walker.visible, "a freed input does not stop the pass")
	var hidden_before := 0
	for node: Node3D in nodes:
		if not node.visible:
			hidden_before += 1
	sections.reset()
	var hidden_after := 0
	for node: Node3D in nodes:
		if not node.visible:
			hidden_after += 1
	_expect(hidden_before > 0 and hidden_after == 0, "reset shows every node the cull hid")
	_expect(not sections.is_active(), "reset deactivates the controller")
	world.free()
	print("SecretSections cull: %d checks, %d failures" % [checks, failures])
	if failures == 0:
		print("PASS: secret sections cull matches the list-order scan")
	quit(failures)


func _expect(condition: bool, message: String) -> void:
	checks += 1
	if condition:
		return
	failures += 1
	push_error("FAIL: " + message)
