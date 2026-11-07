extends SceneTree
## CPU-only offline WD-C5 producer. Never calls get_mesh()/generate_scene().
const Lods := preload("res://src/world/browser_prototype_lods.gd")
const Classes := preload("res://src/world/world_distance_classes.gd")

class Quantization extends GLTFDocumentExtension:
	func _get_supported_extensions() -> PackedStringArray:
		return PackedStringArray(["KHR_mesh_quantization"])
	func _parse_image_data(_state: GLTFState, _bytes: PackedByteArray, _mime: String, image: Image) -> Error:
		# Pixel content does not participate in the WD-C5 index calculation.
		# Keep material/texture declarations intact without decoding images.
		image.set_data(1, 1, false, Image.FORMAT_RGBA8, PackedByteArray([255, 255, 255, 255]))
		return OK

func _initialize() -> void: _run.call_deferred()

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1:
		push_error("Pass one producer job JSON path after --")
		quit(1)
		return
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not raw is Dictionary or not raw.get("sources") is Array or not raw.get("out") is String:
		push_error("Invalid browser prototype LOD job")
		quit(1)
		return
	var job: Dictionary = raw
	var out := str(job.out)
	var extension := Quantization.new()
	GLTFDocument.register_gltf_document_extension(extension)
	var index := {"schema": Lods.SCHEMA, "policy": Lods.POLICY, "engine": Lods.engine_identity(), "sources": {}}
	var summary: Array = []
	for item: Dictionary in job.sources:
		var source := str(item.absolute)
		var document := GLTFDocument.new()
		var state := GLTFState.new()
		state.handle_binary_image = GLTFState.HANDLE_BINARY_DISCARD_TEXTURES
		var error := document.append_from_file(source, state)
		if error != OK or state.get_meshes().is_empty():
			push_error("Prototype parse failed: " + str(item.path))
			quit(1)
			return
		var mesh: ImporterMesh = (state.get_meshes()[0] as GLTFMesh).mesh
		if mesh == null or not Lods.qualifies(mesh):
			summary.append({"path": item.path, "status": "gate"})
			continue
		var began := Time.get_ticks_usec()
		mesh.generate_lods(Classes.LOD_NORMAL_MERGE_ANGLE, Classes.LOD_NORMAL_SPLIT_ANGLE, [])
		var usec := Time.get_ticks_usec() - began
		var file := FileAccess.open(source, FileAccess.READ)
		var sha := FileAccess.get_sha256(source)
		var data := Lods.document(mesh, sha, file.get_length())
		var levels := 0
		for surface: Dictionary in data.mesh.surfaces: levels += surface.lods.size()
		if levels == 0:
			summary.append({"path": item.path, "status": "empty", "generate_usec": usec})
			continue
		var sidecar := out.path_join(sha + Lods.SUFFIX)
		var encoded := JSON.stringify(data).to_utf8_buffer()
		if encoded.size() > Lods.MAX_BYTES:
			push_error("Prototype sidecar exceeds budget: " + str(item.path))
			quit(1)
			return
		var destination := FileAccess.open(sidecar, FileAccess.WRITE)
		destination.store_buffer(encoded)
		destination.close()
		index.sources[str(item.path)] = {"source_sha256": sha, "sidecar_path": sidecar}
		summary.append({"path": item.path, "status": "cooked", "levels": levels,
			"sidecar_bytes": encoded.size(), "generate_usec": usec})
	GLTFDocument.unregister_gltf_document_extension(extension)
	var result := FileAccess.open(out.path_join("index.json"), FileAccess.WRITE)
	result.store_string(JSON.stringify(index, "  ") + "\n")
	result.close()
	result = FileAccess.open(out.path_join("summary.json"), FileAccess.WRITE)
	result.store_string(JSON.stringify(summary, "  ") + "\n")
	result.close()
	print("Browser prototype LOD sidecars: ", index.sources.size(), " / ", job.sources.size(), " sources; ", out.path_join("index.json"))
	quit()
