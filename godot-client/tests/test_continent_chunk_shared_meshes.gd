extends SceneTree

## The chunk stream's byte budget counts the pooled prototypes a cell draws.
## The space passes moved most props out of the chunk GLBs into
## maps/_shared/meshes, so a cell's own geometry figure no longer covers them;
## publish_finish.py's restamp states them per cell (sharedMeshResidentBytes:
## prototype -> resident bytes, at the cell's own geometry factor), and the
## stream counts each one once while any resident or retiring cell names it,
## as it counts a shared image.
##
## Run: Godot_v4.7.2-stable_win64_console.exe --headless --path . \
##         --script res://tests/test_continent_chunk_shared_meshes.gd

const VramTextures := preload("res://src/world/vram_textures.gd")
const KEY := ContinentChunkStream.SHARED_MESHES_KEY
const BUDGET := 40000
const GEOMETRY := 1000
const PROTOTYPE := 30000

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)
	return ok

func _run() -> void:
	# Published image figures throughout: these cells name no image anyway.
	OS.set_environment(VramTextures.ENVIRONMENT, "0")
	VramTextures.reconfigure()
	_check_cost()
	_check_selection()
	_check_blocking()
	await _check_residency()
	_check_validation()
	OS.set_environment(VramTextures.ENVIRONMENT, "")
	VramTextures.reconfigure()
	print("continent chunk shared mesh tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

static func _id(letter: String) -> String:
	return letter.repeat(64)

static func _sum(figures: Dictionary) -> int:
	var total := 0
	for identity: String in figures:
		total += int(figures[identity])
	return total

## Five cells nearest-first, as test_continent_chunk_budget.gd lays them out:
## only the first is within FRAMED_RADIUS, so the budget decides the rest.
## `prototypes` gives each index's sharedMeshResidentBytes; `fields` overrides
## the cell's own figures.
func _stream(prototypes: Array, fields := {}, budget := BUDGET) -> ContinentChunkStream:
	var chunks := []
	for index: int in 5:
		var x := 100.0 + 20.0 * index if index > 0 else 0.0
		var drawn: Dictionary = prototypes[index]
		var cell := {"id": "c%d" % index, "manifest": "c%d/world.json" % index,
			"bounds": {"min": [x, 0, -1], "max": [x + 1, 1, 1]},
			"geometryResidentBytes": GEOMETRY, "sharedResourceResidentBytes": {}}
		cell.merge(fields, true)
		if not drawn.is_empty():
			cell[KEY] = drawn
		cell.estimatedResidentBytes = int(cell.geometryResidentBytes) + _sum(drawn)
		chunks.append(cell)
	var manifest := WorldManifest.new()
	manifest.source_path = "user://continent-chunk-shared-meshes/territory.json"
	manifest.data = {"streamingChunks": {"schemaVersion": "1.0", "coordinateSpace": "territory-local",
		"maximumResidentBytes": budget, "chunks": chunks}}
	var stream := ContinentChunkStream.new()
	stream.configure(manifest, false)
	return stream

## [ids selected, ids prime() would import synchronously].
func _walk(stream: ContinentChunkStream) -> Array:
	var ids := []
	var blocking := []
	for entry: Dictionary in stream.selection(Vector3.ZERO):
		ids.append(str(entry.id))
		if bool(entry.get("blocking", true)) and not bool(entry.get("beyond_budget", false)):
			blocking.append(str(entry.id))
	stream.free()
	return [ids, blocking]

func _check_cost() -> void:
	var published := ContinentChunkStream.PUBLISHED_SHARED_KEY
	var shared: Dictionary = {}
	var first := {"geometryResidentBytes": GEOMETRY, KEY: {_id("a"): PROTOTYPE}}
	_expect(ContinentChunkStream.incremental_cost(first, shared) == GEOMETRY + PROTOTYPE,
		"a cell costs its geometry plus the prototypes it draws")
	_expect(ContinentChunkStream.incremental_cost(first.duplicate(), shared) == GEOMETRY,
		"a second cell drawing the same prototype costs only its own geometry")
	var bigger := {"geometryResidentBytes": GEOMETRY, KEY: {_id("a"): PROTOTYPE + 500}}
	_expect(ContinentChunkStream.incremental_cost(bigger, shared) == GEOMETRY + 500,
		"a larger figure for a counted prototype adds only the difference")
	var clash := {"geometryResidentBytes": 1, "sharedResourceResidentBytes": {_id("b"): 700},
		KEY: {_id("b"): PROTOTYPE}}
	_expect(ContinentChunkStream.incremental_cost(clash, {}) == 1 + 700 + PROTOTYPE,
		"an image and a prototype with the same identity are two resources")
	# A continent-v2 cell states geometry and prototypes at 1 x their GLB
	# bytes; the blocking walk floors both at 5 x, a legacy cell already is.
	var v2 := {"geometryResidentBytes": GEOMETRY, "glbBytes": GEOMETRY, KEY: {_id("c"): 3000}}
	v2[published] = {}
	_expect(ContinentChunkStream.incremental_cost(v2, {}) == GEOMETRY + 3000
		and ContinentChunkStream.incremental_cost(v2, {}, published) == 5 * (GEOMETRY + 3000),
		"a 1 x cell: residency counts its prototypes as stated, the blocking walk at 5 x like its geometry")
	var legacy := {"geometryResidentBytes": 5 * GEOMETRY, "glbBytes": GEOMETRY, KEY: {_id("c"): 15000}}
	legacy[published] = {}
	_expect(ContinentChunkStream.incremental_cost(legacy, {}) == 20000
		and ContinentChunkStream.incremental_cost(legacy, {}, published) == 20000,
		"a 5 x cell costs the same in both walks")
	var bare := {"geometryResidentBytes": GEOMETRY, KEY: {_id("c"): 3000}}
	bare[published] = {}
	_expect(ContinentChunkStream.incremental_cost(bare, {}, published) == GEOMETRY + 3000,
		"a cell without glbBytes keeps its prototype figures in both walks")
	var all_in := {"estimatedResidentBytes": 4321, KEY: {_id("c"): 3000}}
	_expect(ContinentChunkStream.incremental_cost(all_in, {}) == 4321,
		"a cell with only the all-in estimate (which restamp sums them into) is not counted twice")

func _check_selection() -> void:
	var one := {_id("a"): PROTOTYPE}
	var shared := _walk(_stream([one, one, one, one, one]))
	_expect(shared[0] == ["c0", "c1", "c2", "c3", "c4"],
		"five cells drawing one 30 000-byte prototype fit a 40 000-byte budget: %s" % [shared[0]])
	var tight := _walk(_stream([one, one, one, one, one], {}, 4 * GEOMETRY + PROTOTYPE))
	_expect(tight[0] == ["c0", "c1", "c2", "c3"],
		"under 4 x geometry + one prototype, four cells: the prototype counts, and once: %s" % [tight[0]])
	var distinct := []
	for letter: String in ["a", "b", "c", "d", "e"]:
		distinct.append({_id(letter): PROTOTYPE})
	var apart := _walk(_stream(distinct))
	_expect(apart[0] == ["c0"],
		"five cells drawing their own prototype: one fits (before, all five did at 1 000 each): %s" % [apart[0]])
	var bare := _walk(_stream([{}, {}, {}, {}, {}]))
	_expect(bare[0] == ["c0", "c1", "c2", "c3", "c4"], "cells drawing no prototype walk as before: %s" % [bare[0]])

## Cells published at 1 x their GLB (continent-v2), each with its own
## 3 000-byte prototype: 4 000 a cell resident, all five fit. What prime()
## blocks on is judged at 5 x geometry AND prototypes (20 000 a cell): two.
func _check_blocking() -> void:
	var distinct := []
	for letter: String in ["a", "b", "c", "d", "e"]:
		distinct.append({_id(letter): 3000})
	var v2 := _walk(_stream(distinct, {"glbBytes": GEOMETRY}))
	_expect(v2[0] == ["c0", "c1", "c2", "c3", "c4"], "a 1 x cell with its prototypes: all five resident: %s" % [v2[0]])
	_expect(v2[1] == ["c0", "c1"], "and prime() blocks on two, the 5 x figure of both: %s" % [v2[1]])
	var legacy_drawn := []
	for letter: String in ["a", "b", "c", "d", "e"]:
		legacy_drawn.append({_id(letter): 15000})
	var legacy := _walk(_stream(legacy_drawn, {"glbBytes": GEOMETRY, "geometryResidentBytes": 5 * GEOMETRY}))
	_expect(legacy == [["c0", "c1"], ["c0", "c1"]], "a 5 x cell walks the same both ways: %s" % [legacy])

## What the stream reports resident (_update_resident_bytes) counts a
## prototype once across resident cells and the retiring ones still holding
## their nodes, and drops it when the last of them is freed.
func _check_residency() -> void:
	var stream := ContinentChunkStream.new()
	var tree := {"a": {_id("p"): PROTOTYPE}, "b": {_id("p"): PROTOTYPE}, "c": {_id("q"): 2 * PROTOTYPE}}
	for identity: String in tree:
		var imported := Node3D.new()
		imported.add_child(Node3D.new())
		stream.add_child(imported)
		stream.cells[identity] = {"root": imported, "entry": {"id": identity, "geometryResidentBytes": GEOMETRY,
			"estimatedResidentBytes": GEOMETRY + _sum(tree[identity]), KEY: tree[identity]}}
	stream._update_resident_bytes()
	_expect(stream.resident_bytes == 3 * GEOMETRY + 3 * PROTOTYPE,
		"three resident cells, two sharing a prototype: %d" % stream.resident_bytes)
	stream._retire_cell("c")
	stream._update_resident_bytes()
	_expect(stream.resident_bytes == 3 * GEOMETRY + 3 * PROTOTYPE,
		"a retiring cell still holds its prototype until its nodes are freed: %d" % stream.resident_bytes)
	await _drain(stream)
	_expect(stream.resident_bytes == 2 * GEOMETRY + PROTOTYPE,
		"freed, its prototype leaves the count: %d" % stream.resident_bytes)
	stream._retire_cell("a")
	await _drain(stream)
	_expect(stream.resident_bytes == GEOMETRY + PROTOTYPE,
		"a shared prototype stays while another resident cell draws it: %d" % stream.resident_bytes)
	stream._retire_cell("b")
	await _drain(stream)
	_expect(stream.resident_bytes == 0, "and leaves with the last: %d" % stream.resident_bytes)
	stream.free()

func _drain(stream: ContinentChunkStream) -> void:
	for attempt: int in 100:
		if stream._retiring.is_empty():
			return
		stream._drain_retired()
		# A shared owner receives at most one retirement slice per frame.
		await process_frame
	_expect(stream._retiring.is_empty(), "retirement drains within the bounded frame allowance")

func _check_validation() -> void:
	var cases := {
		"a valid figure": [{_id("a"): 12}, ""],
		"a key that is not a SHA256": [{"tree": 12}, "resource key must be SHA256"],
		"a negative figure": [{_id("a"): -1}, "must be nonnegative"],
		"a list": [[_id("a")], "must be an object"],
	}
	for label: String in cases:
		var manifest := WorldManifest.new()
		manifest.data = {"streamingChunks": {"schemaVersion": "1.0", "coordinateSpace": "territory-local",
			"chunks": [{"id": "c0", "manifest": "c0/world.json", "bounds": {"min": [0, 0, 0], "max": [1, 1, 1]},
				KEY: cases[label][0]}]}}
		manifest._validate_chunks()
		var expected: String = cases[label][1]
		var found := manifest.errors.is_empty() if expected.is_empty() else \
			manifest.errors.any(func(error: String) -> bool: return expected in error)
		_expect(found, "the manifest check takes %s: %s" % [label, manifest.errors])
