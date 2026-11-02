extends SceneTree
## Map discs keep their nodes, names and colours, but no camera draws their
## layer any more, so every disc of one look shares one mesh and material and
## none of them casts a shadow.

var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _run() -> void:
	var colour := Color(0.55, 0.8, 1.0)
	var first := MapMarkerDisc.build("MapDot", 6.0, colour)
	var second := MapMarkerDisc.build("MapDot", 6.0, colour)
	var outline := first.get_node_or_null("MapDotOutline") as MeshInstance3D
	expect(outline != null and outline.layers == MapMarkerDisc.MAP_MARKER_LAYER
		and first.layers == MapMarkerDisc.MAP_MARKER_LAYER,
		"a disc and its outline keep their names and the map layer")
	var material := first.mesh.surface_get_material(0) as StandardMaterial3D
	expect(material != null and material.albedo_color == colour
		and material.render_priority == MapMarkerDisc.FILL_PRIORITY,
		"the disc reads back exactly the colour it was asked for")
	expect(first.mesh == second.mesh and first.mesh.surface_get_material(0)
		== second.mesh.surface_get_material(0),
		"discs of one size and colour share one mesh and one material")
	expect(outline.mesh == (second.get_node("MapDotOutline") as MeshInstance3D).mesh
		and outline.mesh != first.mesh,
		"outlines share theirs, apart from the fills")
	var other := MapMarkerDisc.build("MapMarker", 7.0, Color(0.9, 0.5, 0.1))
	expect(other.mesh != first.mesh and (other.mesh.surface_get_material(0)
		as StandardMaterial3D).albedo_color == Color(0.9, 0.5, 0.1),
		"another size or colour gets its own")
	var nearly := MapMarkerDisc.build("MapDot", 6.0, Color(0.55, 0.8, 1.0 - 1e-6))
	expect(nearly.mesh != first.mesh, "colours are matched exactly, not rounded")
	expect(first.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		and outline.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"a disc no camera draws never enters a shadow caster cull")
	for disc: Node in [first, second, other, nearly]:
		disc.free()
	_check_actor_dots()
	_check_cameras()
	print("map marker disc tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## Replicated actors still carry their MapDot in the colour their packet asks
## for, and two of a kind share it.
func _check_actor_dots() -> void:
	var dots: Array[MeshInstance3D] = []
	for actor_id: int in [30014, 30015]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		actor.configure({"actor_id": actor_id, "x": 704, "y": 816, "rotation": 0,
			"actor_type": 308, "kind": 20, "name": "Gate Warden Ilyon"},
			CoordinateAdapter.new(), {}, {})
		dots.append(actor.get_node_or_null(String(ReplicatedActor3D.MAP_DOT_NODE)) as MeshInstance3D)
	var material: StandardMaterial3D = (dots[0].mesh.surface_get_material(0)
		as StandardMaterial3D) if dots[0] != null else null
	expect(material != null and dots[0].layers == ReplicatedActor3D.MAP_MARKER_LAYER
		and material.albedo_color.is_equal_approx(ReplicatedActor3D.MAP_DOT_COLOUR),
		"an actor's dot keeps its layer and the light blue the legend names")
	expect(dots[1] != null and dots[1].mesh == dots[0].mesh,
		"two actors of one colour share one dot mesh")
	for dot: MeshInstance3D in dots:
		if dot != null:
			dot.get_parent().free()

## Every camera in the main scene states a cull mask without the map layer.
## A camera that states none draws every layer, the map layer included.
func _check_cameras() -> void:
	var scene := FileAccess.get_file_as_string("res://src/app/main.tscn")
	var cameras := 0
	var blocks := scene.split("\n[")
	for block: String in blocks:
		if not block.begins_with("node ") or not block.contains("type=\"Camera3D\""):
			continue
		cameras += 1
		var mask := -1
		for line: String in block.split("\n"):
			if line.begins_with("cull_mask = "):
				mask = int(line.trim_prefix("cull_mask = "))
		expect(mask >= 0 and (mask & MapMarkerDisc.MAP_MARKER_LAYER) == 0,
			"main.tscn camera %s does not draw the map layer" % block.get_slice("\"", 1))
	expect(cameras >= 4, "main.tscn's cameras were all checked (%d)" % cameras)
