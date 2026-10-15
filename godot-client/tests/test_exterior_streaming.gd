extends SceneTree

var failures := 0
var stage: Node3D
var stream: ExteriorRegionStream
var loader: WorldLoader
var registry: Dictionary

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	registry = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json")).maps
	stage = Node3D.new()
	root.add_child(stage)
	stream = ExteriorRegionStream.new()
	stage.add_child(stream)
	stream.configure(registry)
	loader = WorldLoader.new()
	stage.add_child(loader)
	var a := _manifest("amberwood")
	var b := _manifest("whitehorn_range")
	# Preserve the legacy rotated-strip contract independently of today's
	# translation-only geographic packages. Emitted joins have their own audit.
	a.data.streamingBorders = [{"id":"amberwood-whitehorn", "anchor":[67.5,55.2,-256.5],
		"outward":[0,-1], "collarDepth":42, "geometryMode":"legacy-preview"}]
	b.data.streamingBorders = [{"id":"amberwood-whitehorn", "anchor":[-106.5,35.8,-54.5],
		"outward":[-1,0], "collarDepth":42, "geometryMode":"legacy-preview"}]
	var af: Dictionary = a.data.streamingBorders[0]
	var bf: Dictionary = b.data.streamingBorders[0]
	stream.links = [{"seamless":true, "ends":[
		{"map":"amberwood", "position":[67.5,55.2,-257.5], "frame":af},
		{"map":"whitehorn_range", "position":[-107.5,35.8,-54.5], "frame":bf}]}]
	var transform := ExteriorRegionStream.frame_transform(af, bf)
	var reverse := ExteriorRegionStream.frame_transform(bf, af)
	_expect((transform * reverse).is_equal_approx(Transform3D.IDENTITY), "reciprocal survey transforms cancel")
	for lane: int in range(-3, 4):
		var source := Vector3(67.5 + lane, 55.2, -257.5)
		var arrival := Vector3(-105.5, 35.8, -54.5 + lane)
		_expect((transform * arrival).distance_to(source) < .0001, "lane %d preserves position" % lane)
	var first := _terrain("Amber")
	loader.world_root = first
	loader.manifest = a
	loader.add_child(first)
	stream.activate("amberwood", first, a)
	var second := _terrain("White")
	stream.add_child(second)
	stream.residents["whitehorn_range"] = {"root": second, "manifest": b, "digest": "",
		"phases": {}, "from_cache": false, "cache_status": &"disabled", "cache_file": ""}
	stream._refresh_views()
	_expect(second.visible, "a resident surveyed neighbor is visible")
	_expect(not (first.get_node("StreamActive/Terrain_StreamOverflow_amberwood-whitehorn") as Node3D).visible, "resident neighbor replaces overflow")
	_expect((second.get_node("StreamPreview_amberwood-whitehorn/Terrain/Body") as StaticBody3D).collision_layer == 16,
		"neighbor picking cannot contaminate active grounding")
	_expect((first.get_node("StreamActive/Terrain_StreamOverflow_other-border") as Node3D).visible,
		"one resident does not cut another border's fallback terrain")
	_expect(not (second.get_node("StreamActive") as Node3D).visible,
		"unrelated destination geography is hidden in receiving preview")
	_expect(not (second.get_node("StreamPreview_other-border") as Node3D).visible,
		"only the reciprocal destination approach is displayed")
	_expect((second.get_node("StreamPreview_other-border/Terrain/Body") as StaticBody3D).collision_layer == 0,
		"an unrelated receiving approach cannot capture mouse rays")
	var handoff := stream.take_ready("whitehorn_range", loader, Vector3(67.5, 55.2, -256.5))
	_expect(bool(handoff.continuous), "nearby surveyed crossing permits a continuous handoff")
	loader.adopt_world(handoff.resident)
	stream.activate("whitehorn_range", loader.world_root, loader.manifest)
	_expect(loader.world_root == second, "handoff adopts the identical preloaded root")
	_expect(stream.residents.amberwood.root == first, "departed scene stays available for looking back")
	_expect(first.get_parent() == loader and second.get_parent() == stream,
		"resident scenes never leave their rendering and physics world during handoff")
	_expect((second.get_node("StreamActive/Terrain/Body") as StaticBody3D).collision_layer == 8, "destination owns grounding after handoff")
	_expect((second.get_node("StreamPreview_amberwood-whitehorn/Terrain/Body") as StaticBody3D).collision_layer == 0,
		"adoption disables duplicate receiving collision")
	_expect((second.get_node("StreamActive") as Node3D).visible,
		"adoption restores the full authored destination")
	stream.update_position(Vector3(2000, 0, 2000))
	await process_frame
	_expect(stream.residents.is_empty(), "far neighbours are evicted")
	stream.clear()
	loader.unload_world()
	await process_frame
	# A real cold import is superseded by disconnect. The rendering loop must
	# keep running while its one worker finishes, then discard the stale result.
	first = _terrain("NewSession")
	stage.add_child(first)
	stream.activate("amberwood", first, a)
	stream.update_position(Vector3(67.5, 55.2, -250))
	_expect(not stream.is_idle(), "proximity starts an asynchronous import")
	stream.clear()
	var rendered_frames := 0
	var deadline := Time.get_ticks_msec() + 60000
	while not stream.is_idle() and Time.get_ticks_msec() < deadline:
		rendered_frames += 1
		await process_frame
	_expect(stream.is_idle(), "cancelled import finishes without a blocking join")
	_expect(rendered_frames > 1, "the main loop keeps running during loading")
	_expect(stream.residents.is_empty(), "a stale completion cannot revive a disconnected world")
	GlbSceneCache.clear()
	var visual_path := "res://assets/world/harvestables/moor_peat.glb"
	var prepared := GlbSceneCache.prepare(GlbSceneCache.missing(PackedStringArray([visual_path])))
	GlbSceneCache.install_prepared(prepared)
	var visual := GlbSceneCache.instantiate(ProjectSettings.globalize_path(visual_path))
	_expect(visual != null and GlbSceneCache.cached_scene_count() == 1,
		"preloaded resource and absolute runtime path share one cached scene")
	if visual != null: visual.free()
	GlbSceneCache.clear()
	stage.queue_free()
	await process_frame
	print("exterior streaming tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _manifest(map_id: String) -> WorldManifest:
	return WorldManifest.load_file(ProjectSettings.globalize_path(registry[map_id].manifest))

func _terrain(label: String) -> Node3D:
	var imported := Node3D.new()
	imported.name = label
	for group_name: String in ["StreamActive", "StreamPreview_amberwood-whitehorn", "StreamPreview_other-border"]:
		var group := Node3D.new()
		group.name = group_name
		imported.add_child(group)
		for title: String in ["Terrain", "Terrain_StreamOverflow_amberwood-whitehorn", "Terrain_StreamOverflow_other-border"]:
			var piece := Node3D.new()
			piece.name = title
			group.add_child(piece)
			var body := StaticBody3D.new()
			body.name = "Body"
			body.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
			piece.add_child(body)
	return imported

func _expect(ok: bool, description: String) -> void:
	if ok:
		print("PASS: ", description)
	else:
		failures += 1
		push_error("FAIL: " + description)
