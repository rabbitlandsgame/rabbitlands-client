extends SceneTree
const Content := preload("res://tests/integration/benchmark_route_content.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")

class FixtureMain:
	extends Node
	var world_loader := WorldLoader.new()
	var exterior_stream := ExteriorRegionStream.new()
	var loaded_server_map := "route_fixture"
	var fixture_ready := true
	func benchmark_readiness_snapshot() -> Dictionary:
		return {"ready": fixture_ready, "loadedMap": loaded_server_map}
	func benchmark_runtime_snapshot() -> Dictionary:
		return {"effectiveSettings": {"textureQuality": "full", "textureSkip": 0}}

class FixtureStream:
	extends ContinentChunkStream
	var selection_calls := 0
	func selection(position: Vector3, retain := false) -> Array[Dictionary]:
		selection_calls += 1
		return super.selection(position, retain)

func _manifest(identity: String) -> WorldManifest:
	var result := WorldManifest.new()
	result.data = {"asset": {"id": identity}}
	return result

func _stream(identity: String) -> FixtureStream:
	var stream := FixtureStream.new()
	stream.territory = _manifest(identity)
	stream.has_focus = true
	stream.set("_corrected_generation", VramTextures.budget_generation())
	for cell_id: String in ["b", "a"]:
		var entry := {"id": cell_id, "manifest": cell_id + "/world.json",
			"bounds": {"min": [-1, -1, -1], "max": [1, 1, 1]}, "geometryResidentBytes": 1}
		stream.entries.append(entry)
		var imported := Node3D.new()
		stream.add_child(imported)
		stream.cells[cell_id] = {"root": imported, "entry": entry,
			"manifest": _manifest(identity + "/" + cell_id), "digest": "1".repeat(64)}
	return stream

func _init() -> void:
	var main := FixtureMain.new()
	var active := _stream("route_fixture")
	main.add_child(main.world_loader)
	main.add_child(main.exterior_stream)
	main.world_loader.add_child(active)
	main.world_loader.world_root = active
	main.world_loader.manifest = active.territory
	main.world_loader.package_digest = "2".repeat(64)
	main.exterior_stream.active_map = main.loaded_server_map
	main.exterior_stream.active_root = active
	var neighbour := _stream("neighbour_fixture")
	main.exterior_stream.add_child(neighbour)
	main.exterior_stream.residents["neighbour_fixture"] = {"root": neighbour,
		"manifest": neighbour.territory, "digest": "3".repeat(64)}
	var entries_before := JSON.stringify(active.entries)
	var first := Content.capture(main)
	assert(bool(first.complete), JSON.stringify(first.errors))
	assert(first.streams.size() == 2)
	assert(first.streams[0].residentIds == ["a", "b"])
	assert(first.streams[0].selectedIds == ["a", "b"])
	assert(first.streams[1].map == "neighbour_fixture")
	assert(first.streams[0].residents[0].actualPackageDigest == "1".repeat(64))
	assert(JSON.stringify(active.entries) == entries_before, "capture must not refresh or mutate entries")
	var calls_before := active.selection_calls
	main.fixture_ready = false
	var not_ready := Content.capture(main)
	assert(not bool(not_ready.complete) and not_ready.streams[0].selectedIds.is_empty())
	assert(active.selection_calls == calls_before, "unready boundaries must not call the selector")
	main.fixture_ready = true
	active.cells["a"].entry["manifest"] = "changed.json"
	assert(first.streams[0].residents[0].package == "a/world.json", "snapshot must not retain live dictionaries")
	active.set("_corrected_generation", VramTextures.budget_generation() - 1)
	var stale := Content.capture(main)
	assert(not bool(stale.complete))
	assert(stale.streams[0].selectedIds.is_empty())
	assert(int(active.get("_corrected_generation")) == VramTextures.budget_generation() - 1)
	active.set("_corrected_generation", VramTextures.budget_generation())
	active.set("_pending", {"id": "not-yet-resident"})
	var pending := Content.capture(main)
	assert(not bool(pending.complete) and pending.streams[0].selectedIds.is_empty())
	assert(active.selection_calls == calls_before, "pending streams must not call the selector")
	active.set("_pending", {})
	var detached := active.cells["b"].root as Node3D
	active.remove_child(detached)
	assert(not bool(Content.capture(main).complete))
	detached.free()
	main.free()
	print("route boundary content snapshots: PASS")
	quit(0)
