extends SceneTree

const Quantization = preload("res://src/world/gltf_quantization.gd")
const MapExtension = preload("res://src/world/map_mesh_extension.gd")
const Vram = preload("res://src/world/vram_textures.gd")
const WorldImages = preload("res://src/world/world_object_images.gd")
const Importer = preload("res://src/actors/native_animation_importer.gd")
const Pool = preload("res://src/world/external_mesh_pool.gd")
const WORKERS := 8
const PARSES_PER_WORKER := 8
const PROTOTYPE := "registration-fixture-only"
var failures := 0
var assertions := 0


func _initialize() -> void:
	call_deferred("_run")


func _expect(value: bool, label: String) -> void:
	assertions += 1
	if not value:
		failures += 1
		push_error(label)


func _cold_worker(path: String) -> Dictionary:
	return {"quantization": Quantization.ensure_registered(),
		"map": MapExtension.ensure_registered(), "prewarm": Importer.prewarm(path)}


func _marker(node: Node) -> Node:
	if str(node.get_meta(Pool.POOLED_META, "")) == PROTOTYPE:
		return node
	for child: Node in node.get_children():
		var found := _marker(child)
		if found != null:
			return found
	return null


func _parse_document(path: String, image: bool = false) -> Dictionary:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if image:
		state.set_additional_data(WorldImages.ENABLED, true)
	var error := document.append_from_file(path, state)
	if error != OK:
		return {"error": error, "marker": false, "preparedImages": -1}
	var generated := document.generate_scene(state)
	var marker := generated != null and _marker(generated) != null
	var prepared := int(state.get_additional_data(WorldImages.PREPARED)) if image else 0
	if generated != null:
		generated.free()
	return {"error": OK, "marker": marker, "preparedImages": prepared}


func _parallel_worker(path: String) -> Dictionary:
	var accepted := 0
	var parsed := 0
	var marked := 0
	for _index: int in PARSES_PER_WORKER:
		if not Quantization.ensure_registered() or not MapExtension.ensure_registered():
			continue
		accepted += 1
		var result := _parse_document(path)
		if int(result.error) == OK:
			parsed += 1
		if bool(result.marker):
			marked += 1
	return {"accepted": accepted, "parsed": parsed, "marked": marked}


func _write(path: String, data: Dictionary) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify(data))
	file.close()
	return true


func _run() -> void:
	# Run in a fresh process without Main: initializing here before the cold
	# probe would hide exactly the worker-first registration regression.
	_expect(not Quantization.is_registered() and not MapExtension.is_registered()
		and not Vram.is_registered(), "fixture starts before runtime registration")
	var path := "user://gltf-registration-fixture.gltf"
	var image_path := "user://gltf-registration-image-fixture.gltf"
	var data := {"asset": {"version": "2.0"}, "scene": 0,
		"extensionsUsed": ["KHR_mesh_quantization"],
		"extensionsRequired": ["KHR_mesh_quantization"],
		"scenes": [{"nodes": [0]}],
		"nodes": [{"name": "registration_marker", "extras": {"eloria": {"prototype": PROTOTYPE}}}]}
	_expect(_write(path, data), "write minimal required-extension fixture")
	var cold_threads: Array[Thread] = []
	for _index: int in WORKERS:
		var worker := Thread.new()
		var started := worker.start(_cold_worker.bind(path))
		_expect(started == OK, "start cold registration worker")
		if started == OK:
			cold_threads.append(worker)
	for worker: Thread in cold_threads:
		var result: Dictionary = worker.wait_to_finish()
		_expect(not result.quantization and not result.map and not result.prewarm,
			"worker-first registration/prewarm fails without parsing or global mutation")
	_expect(Quantization._registered == null and Quantization._world_images == null
		and MapExtension._registered == null and not Vram.is_registered(),
		"cold workers did not publish extension resources")
	_expect(Importer.retention_snapshot().prewarming_sources == 0
		and Importer.retention_snapshot().strong_source_scenes == 0,
		"cold worker prewarm did not acquire a thread or source")

	# Actual standalone API, not a test-only bootstrap: it must register the
	# whole runtime set before starting its real animation parse worker.
	_expect(Importer.prewarm(path), "main standalone prewarm starts")
	_expect(Quantization.is_registered() and MapExtension.is_registered() and Vram.is_registered(),
		"all global runtime extensions completed before prewarm returns")
	_expect(Quantization._registered != null and Quantization._world_images != null,
		"completed quantization registration publishes both extension resources")
	var quantization_id: int = Quantization._registered.get_instance_id()
	var world_images_id: int = Quantization._world_images.get_instance_id()
	var map_id: int = MapExtension._registered.get_instance_id()
	var parsed := Importer._source_scene(path)
	_expect(parsed != null and _marker(parsed) != null,
		"real prewarm parsed required KHR extension and applied map metadata")
	_expect(not Importer.is_prewarming(path) and Importer.has_source(path),
		"real prewarm joined and transferred its source exactly once")
	var supported_before := GLTFDocument.get_supported_gltf_extensions()
	_expect(supported_before.has("KHR_mesh_quantization"), "engine reports quantization support")

	var workers: Array[Thread] = []
	for _index: int in WORKERS:
		var worker := Thread.new()
		var started := worker.start(_parallel_worker.bind(path))
		_expect(started == OK, "start registered concurrent parser")
		if started == OK:
			workers.append(worker)
	for worker: Thread in workers:
		var result: Dictionary = worker.wait_to_finish()
		_expect(result.accepted == PARSES_PER_WORKER and result.parsed == PARSES_PER_WORKER
			and result.marked == PARSES_PER_WORKER,
			"concurrent actual parses retain extension support and map-node callback")
	for _index: int in 16:
		_expect(Quantization.ensure_registered() and MapExtension.ensure_registered(),
			"repeated main registration remains ready")
	_expect(Quantization._registered.get_instance_id() == quantization_id
		and Quantization._world_images.get_instance_id() == world_images_id
		and MapExtension._registered.get_instance_id() == map_id,
		"parallel/repeated readiness does not replace registered extensions")
	_expect(GLTFDocument.get_supported_gltf_extensions() == supported_before,
		"supported global extension set unchanged after parallel imports")

	# Exercise the second registered extension, rather than only inspecting its
	# Ref: a generated valid PNG must be decoded by WorldObjectImages.
	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.25, 0.5, 0.75, 1.0))
	var with_image: Dictionary = data.duplicate(true)
	with_image["images"] = [{"uri": "data:image/png;base64," + Marshalls.raw_to_base64(image.save_png_to_buffer())}]
	_expect(_write(image_path, with_image), "write image-extension fixture")
	var image_result := _parse_document(image_path, true)
	_expect(int(image_result.error) == OK and bool(image_result.marker)
		and int(image_result.preparedImages) == 1,
		"actual image decode and map callback both survive complete registration")
	Importer.clear()
	_expect(Importer.retention_snapshot().prewarming_sources == 0
		and Importer.retention_snapshot().strong_source_scenes == 0,
		"fixture clears joined source ownership")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(image_path))
	await process_frame
	await process_frame
	print("test_gltf_runtime_registration: %d assertions, %d failures; %d actual concurrent parses" % [
		assertions, failures, workers.size() * PARSES_PER_WORKER])
	quit(1 if failures else 0)
