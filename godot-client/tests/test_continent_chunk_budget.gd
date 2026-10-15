extends SceneTree

## The chunk stream's byte budget counts a shared image at what it really
## holds on the GPU: its sidecar's bytes when this client uploads the sidecar,
## the publisher's RGBA8 figure otherwise (VramTextures.resident_bytes, read
## by ContinentChunkStream.configure).
##
## Uses the committed sidecar index of tests/fixtures/vram: four images with
## sidecars (BC7 base, BC7 cutout, BC5 normal, BC1 ORM) and three excluded.
##
## Run: Godot_v4.7.2-stable_win64_console.exe --headless --path . \
##         --script res://tests/test_continent_chunk_budget.gd

const VramTextures := preload("res://src/world/vram_textures.gd")

const FIXTURE := "res://tests/fixtures/vram"
const SCRATCH := "user://continent-chunk-budget-test"
const GEOMETRY := 1000
## w*h*4*4/3 for a 64 px image, as scene_io.py writes it.
const PUBLISHED := 21845

var failures := 0
var _index: Dictionary
var _by_recipe: Dictionary = {}
var _excluded: Array = []

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
	_index = JSON.parse_string(FileAccess.get_file_as_string(
		FIXTURE.path_join("shared-assets/vram/index.json")))
	for sha: String in _index.images:
		_by_recipe[str(_index.images[sha].recipe)] = sha
	_excluded = (_index.excluded as Dictionary).keys()

	_check_resident_bytes()
	_check_selection()
	_check_territory_indexes()
	_check_untrusted_entries()
	_check_rejection_feedback()
	_set_mode("")
	_remove_tree(SCRATCH)
	print("continent chunk budget tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

func _set_mode(value: String, read_index := true) -> void:
	OS.set_environment(VramTextures.ENVIRONMENT, value)
	VramTextures.reconfigure()
	if read_index:
		VramTextures.index_for_directory(FIXTURE.path_join("shared-assets"))

func _gpu(recipe: String) -> int:
	return int(_index.images[_by_recipe[recipe]].gpuBytes)

func _check_resident_bytes() -> void:
	_set_mode("force")
	var base: String = _by_recipe.base
	_expect(VramTextures.resident_bytes(base, PUBLISHED) == _gpu("base") and _gpu("base") * 3 < PUBLISHED,
		"a sidecar image counts its BC7 bytes (%d of %d)" % [_gpu("base"), PUBLISHED])
	_expect(VramTextures.resident_bytes(_by_recipe.orm, PUBLISHED) == _gpu("orm")
		and _gpu("orm") * 7 < PUBLISHED, "an ORM counts its BC1 bytes (%d)" % _gpu("orm"))
	var excluded_ok := true
	for sha: String in _excluded:
		excluded_ok = excluded_ok and VramTextures.resident_bytes(sha, PUBLISHED) == PUBLISHED
	_expect(excluded_ok, "an excluded image keeps the published RGBA8 figure")
	_expect(VramTextures.resident_bytes("f".repeat(64), 12345) == 12345, "an unknown sha keeps the published figure")

	_set_mode("force")
	VramTextures.force_formats(VramTextures.FORMAT_BITS.bc1 | VramTextures.FORMAT_BITS.bc5)
	_expect(VramTextures.resident_bytes(base, PUBLISHED) == PUBLISHED
		and VramTextures.resident_bytes(_by_recipe.normal, PUBLISHED) == _gpu("normal"),
		"a format the renderer lacks keeps the published figure; one it samples does not")

	_set_mode("0")
	_expect(VramTextures.resident_bytes(base, PUBLISHED) == PUBLISHED, "=0 keeps every published figure")

## Five cells nearest-first, one image each; only the first is framed. Under a
## 40 000-byte budget the published (RGBA8) figures admit one cell; the real
## ones admit the four whose images have sidecars and stop at the excluded one.
## With `images_in`, the territory manifest names the fixture images it holds
## (externalResources, as published territories do) in that directory. With
## `loadable`, every cell's manifest is the fixture package itself, so prime()
## really imports the cells it loads.
func _territory(images_in := "", loadable := false) -> WorldManifest:
	var chunks := []
	var shas: Array = [_by_recipe.base, _by_recipe.base_alpha, _by_recipe.normal, _by_recipe.orm, _excluded[0]]
	for index: int in shas.size():
		var x := 100.0 + 20.0 * index if index > 0 else 0.0
		chunks.append({"id": "c%d" % index, "manifest": "world.json" if loadable else "c%d/world.json" % index,
			"bounds": {"min": [x, 0, -1], "max": [x + 1, 1, 1]},
			"estimatedResidentBytes": GEOMETRY + PUBLISHED, "geometryResidentBytes": GEOMETRY,
			"sharedResourceResidentBytes": {shas[index]: PUBLISHED}})
	var manifest := WorldManifest.new()
	manifest.source_path = (images_in if not images_in.is_empty() else FIXTURE).path_join("territory.json")
	manifest.data = {"streamingChunks": {"schemaVersion": "1.0", "coordinateSpace": "territory-local",
		"maximumResidentBytes": 40000, "chunks": chunks}}
	if not images_in.is_empty():
		manifest.data["asset"] = {"id": "budget_territory", "glb": "world.glb"}
		manifest.data["externalResources"] = JSON.parse_string(FileAccess.get_file_as_string(
			images_in.path_join("world.json"))).externalResources
	return manifest

## The cells an arrival loads synchronously, from prime() itself (every cell
## is the fixture package, so prime() really imports what it blocks on). It
## keeps develop's set, the published figures' budget, even when the real
## figures admit more, so the arrival freeze is no longer than develop's; the
## extra cells go to the worker.
func _primed(mode: String, budget := 0) -> Array:
	_set_mode(mode)
	var stream := ContinentChunkStream.new()
	stream.configure(_territory("", true), false)
	if budget > 0:
		stream.maximum_resident_bytes = budget
	stream.prime(Vector3.ZERO)
	var ids: Array = stream.cells.keys()
	ids.sort()
	stream.free()
	return ids

func _check_blocking() -> void:
	var develop := _primed("0")
	_expect(develop == ["c0"], "develop's budget: prime() imports one cell synchronously: %s" % [develop])
	var corrected := _primed("force")
	_expect(corrected == develop,
		"with the real figures (four cells in budget) prime() still imports only develop's cells: %s" % [corrected])
	var everything := _primed("force", 1 << 30)
	_expect(everything == ["c0", "c1", "c2", "c3", "c4"],
		"under a budget that admits everything as published, prime() imports every cell as before: %s" % [everything])

## Five cells nearest-first sharing one image, each with a GLB of GLB_BYTES:
## `factor` x those bytes is the geometry each publishes (5 for develop's
## exporters, 1 for continent-v2 since the owner call of 2026-10-03). Returns
## [selected ids, the ids marked blocking] under a 40 000-byte budget with
## the published (RGBA8) image figures.
const GLB_BYTES := 3000

func _geometry_walk(factor: int, with_glb := true) -> Array:
	_set_mode("0")
	var chunks := []
	for index: int in 5:
		var x := 100.0 + 20.0 * index if index > 0 else 0.0
		var cell := {"id": "c%d" % index, "manifest": "c%d/world.json" % index,
			"bounds": {"min": [x, 0, -1], "max": [x + 1, 1, 1]},
			"estimatedResidentBytes": factor * GLB_BYTES + PUBLISHED, "geometryResidentBytes": factor * GLB_BYTES,
			"sharedResourceResidentBytes": {_by_recipe.base: PUBLISHED}}
		if with_glb:
			cell["glbBytes"] = GLB_BYTES
		chunks.append(cell)
	var manifest := WorldManifest.new()
	manifest.source_path = FIXTURE.path_join("territory.json")
	manifest.data = {"streamingChunks": {"schemaVersion": "1.0", "coordinateSpace": "territory-local",
		"maximumResidentBytes": 40000, "chunks": chunks}}
	var stream := ContinentChunkStream.new()
	stream.configure(manifest, false)
	var ids := []
	var blocking := []
	for entry: Dictionary in stream.selection(Vector3.ZERO):
		ids.append(str(entry.id))
		if bool(entry.get("blocking", true)) and not bool(entry.get("beyond_budget", false)):
			blocking.append(str(entry.id))
	stream.free()
	return [ids, blocking]

## A cell published at 1 x its GLB is admitted to residency at that figure,
## but what an arrival imports synchronously is still judged at 5 x (develop's
## figure), so the arrival freeze does not grow; a legacy cell (5 x) and one
## without glbBytes walk exactly as before.
func _check_blocking_geometry() -> void:
	var legacy := _geometry_walk(5)
	_expect(legacy == [["c0"], ["c0"]], "a 5 x cell: one cell resident, one blocking: %s" % [legacy])
	var v2 := _geometry_walk(1)
	_expect(v2[0] == ["c0", "c1", "c2", "c3", "c4"],
		"a 1 x cell: all five resident under the same budget: %s" % [v2[0]])
	_expect(v2[1] == legacy[1], "a 1 x cell: prime() still blocks on the 5 x set only: %s" % [v2[1]])
	var bare := _geometry_walk(1, false)
	_expect(bare == [v2[0], v2[0]], "a cell without glbBytes keeps its own figure in both walks: %s" % [bare])
	var cell := {"geometryResidentBytes": 700, "glbBytes": 700, "sharedResourceResidentBytes": {}}
	cell[ContinentChunkStream.PUBLISHED_SHARED_KEY] = {}
	_expect(ContinentChunkStream.incremental_cost(cell, {}) == 700
		and ContinentChunkStream.incremental_cost(cell, {}, ContinentChunkStream.PUBLISHED_SHARED_KEY) == 3500,
		"incremental_cost: residency counts the published geometry, the blocking walk 5 x the GLB")
	cell.geometryResidentBytes = 3500
	_expect(ContinentChunkStream.incremental_cost(cell, {}, ContinentChunkStream.PUBLISHED_SHARED_KEY) == 3500
		and ContinentChunkStream.incremental_cost(cell, {}) == 3500, "a legacy 5 x cell costs the same in both walks")

func _selected(mode: String, read_index := true) -> Array:
	_set_mode(mode, read_index)
	var stream := ContinentChunkStream.new()
	stream.configure(_territory(), false)
	var ids := []
	for entry: Dictionary in stream.selection(Vector3.ZERO):
		ids.append("%s%s" % [entry.id, "*" if entry.get("beyond_budget", false) else ""])
	stream.free()
	return ids

func _check_selection() -> void:
	var published := _selected("0")
	_expect(published == ["c0"], "with the RGBA8 figures the budget admits one cell: %s" % [published])
	var real := _selected("force")
	_expect(real == ["c0", "c1", "c2", "c3"],
		"with the sidecars' bytes it admits the four compressed cells: %s" % [real])
	# No index for these images: exactly today's selection.
	var unindexed := _selected("force", false)
	_expect(unindexed == published, "with no index the selection is develop's exactly: %s" % [unindexed])
	_check_blocking()
	_check_blocking_geometry()
	_set_mode("force")
	VramTextures.force_formats(0)
	var stream := ContinentChunkStream.new()
	stream.configure(_territory(), false)
	var ids := []
	for entry: Dictionary in stream.selection(Vector3.ZERO):
		ids.append(str(entry.id))
	stream.free()
	_expect(ids == published, "with no usable format the selection is develop's exactly: %s" % [ids])

func _ids(stream: ContinentChunkStream) -> Array:
	var ids := []
	for entry: Dictionary in stream.selection(Vector3.ZERO):
		ids.append(str(entry.id))
	return ids

## The budget reads the indexes its territory's manifest names, at configure,
## wherever the images live: no chunk import, no prior read, and not the one
## fixed SHARED_ASSETS path (which a template run outside the package layout,
## or a move of the shared images, would not resolve).
func _check_territory_indexes() -> void:
	_set_mode("force", false)
	var stream := ContinentChunkStream.new()
	stream.configure(_territory(FIXTURE), false)
	var ids := _ids(stream)
	stream.free()
	_expect(ids == ["c0", "c1", "c2", "c3"],
		"configure reads the index of the images its territory names, with nothing read before: %s" % [ids])
	_expect(not VramTextures._indexes.has(VramTextures._normalise(VramTextures.SHARED_ASSETS)),
		"and the budget never reads the fixed shared-assets path")
	var moved := _copy_fixture("moved")
	_set_mode("force", false)
	stream = ContinentChunkStream.new()
	stream.configure(_territory(moved), false)
	ids = _ids(stream)
	stream.free()
	_expect(ids == ["c0", "c1", "c2", "c3"], "the same with the images and sidecars in another directory: %s" % [ids])
	_set_mode("0", false)
	stream = ContinentChunkStream.new()
	stream.configure(_territory(FIXTURE), false)
	ids = _ids(stream)
	stream.free()
	_expect(ids == ["c0"] and VramTextures._indexes.is_empty(), "=0 reads no index and keeps develop's selection: %s" % [ids])

## An index entry the client cannot trust is not used: that image decodes and
## the budget keeps its published figure, never less.
func _check_untrusted_entries() -> void:
	var directory := _copy_fixture("untrusted")
	var index_path := directory.path_join("shared-assets/vram/index.json")
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(index_path))
	var base: String = _by_recipe.base
	var normal: String = _by_recipe.normal
	var orm: String = _by_recipe.orm
	index.images[base].erase("gpuBytes")
	index.images[normal].gpuBytes = 100
	index.images[orm].erase("sha256")
	var file := FileAccess.open(index_path, FileAccess.WRITE)
	file.store_string(JSON.stringify(index, " "))
	file.close()
	_set_mode("force", false)
	var info := VramTextures.index_for_directory(directory.path_join("shared-assets"))
	_expect(int(info.get("skipped", -1)) == 3 and int(info.entries) == 1,
		"entries without gpuBytes, with fewer gpuBytes than mip 0 holds, or without a hash are skipped: %s of %s"
		% [info.get("skipped"), int(info.entries) + int(info.get("skipped", 0))])
	_expect(VramTextures.resident_bytes(base, PUBLISHED) == PUBLISHED
		and VramTextures.resident_bytes(normal, PUBLISHED) == PUBLISHED
		and VramTextures.resident_bytes(orm, PUBLISHED) == PUBLISHED,
		"and keep the published figure in the budget")
	_expect(VramTextures.sidecar_entry(base, directory.path_join("shared-assets")).is_empty(),
		"and are never uploaded from their sidecar")

## A sidecar refused at load is uploaded as RGBA8: the stream's budget must
## count that image at its published figure from then on, not the sidecar's.
func _check_rejection_feedback() -> void:
	var directory := _copy_fixture("rejected")
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		directory.path_join("shared-assets/vram/index.json")))
	var base: String = _by_recipe.base
	var cutout: String = _by_recipe.base_alpha
	for sha: String in [base, cutout]:
		DirAccess.remove_absolute(directory.path_join("shared-assets/vram").path_join(index.images[sha].file))
	_set_mode("force", false)
	var stream := ContinentChunkStream.new()
	stream.configure(_territory(directory), false)
	var before := _ids(stream)
	var builder := WorldLoader.prepare_detached(directory.path_join("world.json"), false)
	var rejected := int(builder.load_phases.get(&"sidecarRejected", -1))
	var resident: Dictionary = builder.release_world()
	builder.free()
	if resident.root != null:
		(resident.root as Node).free()
	var after := _ids(stream)
	var figure := int((stream.entries[0].sharedResourceResidentBytes as Dictionary).get(base, -1))
	stream.free()
	_expect(before == ["c0", "c1", "c2", "c3"] and rejected == 2,
		"before the load the missing sidecars still count at BC7 size (%s); the load refuses both (%d)" % [before, rejected])
	_expect(figure == PUBLISHED and after == ["c0"],
		"after it, the budget counts them at the published RGBA8 figure (%d) and admits less: %s" % [figure, after])
	_expect(VramTextures.resident_bytes(_by_recipe.normal, PUBLISHED) == _gpu("normal"),
		"images whose sidecars loaded keep their sidecar figure")

## A copy of the fixture package (manifest, GLB, images, sidecars) under user://.
func _copy_fixture(name: String) -> String:
	var target := SCRATCH.path_join(name)
	_remove_tree(target)
	for relative: String in ["", "shared-assets", "shared-assets/vram"]:
		DirAccess.make_dir_recursive_absolute(target.path_join(relative))
		for file: String in DirAccess.get_files_at(FIXTURE.path_join(relative)):
			DirAccess.copy_absolute(FIXTURE.path_join(relative).path_join(file), target.path_join(relative).path_join(file))
	return target

func _remove_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for directory: String in DirAccess.get_directories_at(path):
		_remove_tree(path.path_join(directory))
	for file: String in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(file))
	DirAccess.remove_absolute(path)
