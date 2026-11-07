extends SceneTree
const Lods := preload("res://src/world/browser_prototype_lods.gd")
const Classes := preload("res://src/world/world_distance_classes.gd")
const Producer := preload("res://tools/build_browser_prototype_lods.gd")
var failures := 0

func _initialize() -> void: _run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func _parse(path: String) -> ImporterMesh:
	var state := GLTFState.new()
	state.handle_binary_image = GLTFState.HANDLE_BINARY_DISCARD_TEXTURES
	if GLTFDocument.new().append_from_file(path, state) != OK: return null
	return (state.get_meshes()[0] as GLTFMesh).mesh

func _base(mesh: ImporterMesh) -> Array:
	var result: Array = [mesh.get_blend_shape_mode(), mesh.get_lightmap_size_hint()]
	for shape: int in mesh.get_blend_shape_count(): result.append(mesh.get_blend_shape_name(shape))
	for surface: int in mesh.get_surface_count():
		result.append([mesh.get_surface_primitive_type(surface), mesh.get_surface_name(surface),
			mesh.get_surface_format(surface), mesh.get_surface_material(surface), mesh.get_surface_arrays(surface)])
		for shape: int in mesh.get_blend_shape_count(): result.append(mesh.get_surface_blend_shape_arrays(surface, shape))
	return result

func _levels(mesh: ImporterMesh) -> Array:
	var result: Array = []
	for surface: int in mesh.get_surface_count():
		var rows: Array = []
		for level: int in mesh.get_surface_lod_count(surface):
			rows.append([mesh.get_surface_lod_size(surface, level), mesh.get_surface_lod_indices(surface, level)])
		result.append(rows)
	return result

func _generate(mesh: ImporterMesh) -> void:
	mesh.generate_lods(Classes.LOD_NORMAL_MERGE_ANGLE, Classes.LOD_NORMAL_SPLIT_ANGLE, [])

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	assert(args.size() == 1, "Pass a cohort test job JSON")
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var extension := Producer.Quantization.new()
	GLTFDocument.register_gltf_document_extension(extension)
	var report: Array = []
	for source: Dictionary in job.sources:
		var path := str(source.absolute)
		var reference := _parse(path)
		_expect(reference != null, "real prototype parses")
		if reference == null: continue
		var began := Time.get_ticks_usec()
		_generate(reference)
		var generated_usec := Time.get_ticks_usec() - began
		var expected := _levels(reference)
		var target := _parse(path)
		var before := _base(target)
		var sha := FileAccess.get_sha256(path)
		var file := FileAccess.open(path, FileAccess.READ)
		var document := Lods.document(reference, sha, file.get_length())
		# JSON numeric values use the real parser's float representation.
		var decoded: Dictionary = JSON.parse_string(JSON.stringify(document))
		began = Time.get_ticks_usec()
		var applied := Lods.apply_document(target, decoded, sha, file.get_length())
		var applied_usec := Time.get_ticks_usec() - began
		_expect(bool(applied.applied), "sidecar applies to exact source")
		_expect(_levels(target) == expected, "every edge size and LOD index matches the ordinary WD-C5 generator")
		_expect(_base(target) == before, "base arrays/material identity/surface names/flags/blend shapes remain exact")
		# Invalid sidecars never partially modify a previously generated mesh.
		for change: String in ["schema", "engine", "source", "bytes", "generation", "base", "vertices", "mesh", "index", "encoding", "count", "edge", "extra"]:
			var invalid: Dictionary = decoded.duplicate(true)
			match change:
				"schema": invalid.schema = 2
				"engine": invalid.engine = "other engine"
				"source": invalid.source_sha256 = "0".repeat(64)
				"bytes": invalid.source_bytes += 1
				"generation": invalid.generation.normal_merge_angle += 1
				"base": invalid.mesh.surfaces[0].index_sha256 = "0".repeat(64)
				"vertices": invalid.mesh.surfaces[0].vertex_sha256 = "0".repeat(64)
				"mesh": invalid.mesh.name = "another mesh"
				"index":
					var packed := Marshalls.base64_to_raw(invalid.mesh.surfaces[0].lods[0].indices).to_int32_array()
					packed[0] = int(invalid.mesh.surfaces[0].vertex_count)
					invalid.mesh.surfaces[0].lods[0].indices = Marshalls.raw_to_base64(packed.to_byte_array())
				"encoding": invalid.mesh.surfaces[0].lods[0].indices = "?".repeat(invalid.mesh.surfaces[0].lods[0].indices.length())
				"count": invalid.mesh.surfaces[0].lods[0].count = 1e12
				"edge": invalid.mesh.surfaces[0].lods[0].edge = 0
				"extra": invalid.replacement_vertices = []
			var rejected := Lods.apply_document(target, invalid, sha, file.get_length())
			_expect(not bool(rejected.applied), "rejects invalid " + change)
			_expect(_base(target) == before and _levels(target) == expected, "rejection is atomic: " + change)
		# The file interface and native bypass use a private source copy only.
		var private := str(job.out).path_join("test-source.glb")
		DirAccess.copy_absolute(path, private)
		var output := FileAccess.open(private + Lods.SUFFIX, FileAccess.WRITE)
		output.store_string(JSON.stringify(decoded))
		output.close()
		var from_file := _parse(path)
		_expect(bool(Lods.apply_file(from_file, private, sha, true).applied), "verified file path applies")
		_expect(_levels(from_file) == expected, "file path retains exact LOD ladder")
		var native := _parse(path)
		_expect(Lods.apply_file(native, private, sha, false).reason == "native", "native path does not read the sidecar")
		DirAccess.remove_absolute(private + Lods.SUFFIX)
		_expect(Lods.apply_file(native, private, sha, true).reason == "missing", "absent sidecar requests normal generation")
		report.append({"source": source.path, "generate_usec": generated_usec, "apply_usec": applied_usec,
			"sidecar_bytes": JSON.stringify(decoded).to_utf8_buffer().size()})
	GLTFDocument.unregister_gltf_document_extension(extension)
	var output := FileAccess.open(str(job.out).path_join("test-results.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify(report, "  ") + "\n")
	output.close()
	print("Browser prototype LOD tests: ", "PASS" if failures == 0 else "FAIL", " ", JSON.stringify(report))
	quit(failures)
