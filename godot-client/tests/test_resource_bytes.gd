extends SceneTree
## Byte estimators for memory ledgers (src/runtime/resource_bytes.gd), against
## hand-computed sizes and against what the engine itself reports: Image
## layouts for every format, an ArrayMesh with two blend shapes, RGBA8
## ImageTextures with and without mipmaps, an imported BPTC
## CompressedTexture2D, PackedScenes built from a GLB (one generated here with
## known contents, a creature parsed raw as releases do, an editor-imported
## world prop), the glTF-state and ImporterMesh ledgers, packed payloads, and
## the same answers on a worker thread, which never waits for the
## RenderingServer (ShaderMaterial parameters are walked on the main thread
## only). Read-backs (RenderingServer.mesh_get_surface) appear only here, as
## the reference the estimators must match.

const ResourceBytes := preload("res://src/runtime/resource_bytes.gd")
const BPTC_TEXTURE := "res://data/actors/portraits_high/male-regions.png"
const CREATURE_GLB := "res://assets/actors/native/creatures/red_fox.glb"
const IMPORTED_GLB := "res://assets/world/underground/crystal_cluster.glb"
const GENERATED_GLB := "user://test_resource_bytes.glb"

var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	_check_image_layouts()
	_check_textures()
	_check_meshes()
	_check_generated_glb()
	_check_imported_creature()
	await _check_materials()
	_check_packed()
	_check_worker()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(GENERATED_GLB))
	print("resource bytes tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## Godot's own layout for every format, size and chain length.
func _check_image_layouts() -> void:
	var missing := PackedStringArray()
	for format: int in Image.FORMAT_MAX:
		if not ResourceBytes.FORMAT_LAYOUT.has(format):
			missing.append(str(format))
	expect(missing.is_empty(), "every Image.Format has a layout: missing %s" % missing)
	var mismatches := PackedStringArray()
	var compared := 0
	for format: int in ResourceBytes.FORMAT_LAYOUT:
		for size: Vector2i in [Vector2i(1, 1), Vector2i(13, 7), Vector2i(64, 64), Vector2i(100, 3), Vector2i(256, 128)]:
			for mipmaps: bool in [false, true]:
				var image := Image.create_empty(size.x, size.y, mipmaps, format)
				var levels := image.get_mipmap_count() + 1 if mipmaps else 1
				var estimate := ResourceBytes.image_layout_bytes(size.x, size.y, format, levels)
				var full := ResourceBytes.image_layout_bytes(size.x, size.y, format, -1) if mipmaps else estimate
				compared += 1
				if estimate != image.get_data_size() or full != image.get_data_size():
					mismatches.append("format %d %s mips=%s: %d/%d vs %d" % [format, size, mipmaps, estimate,
						full, image.get_data_size()])
	expect(mismatches.is_empty(), "image_layout_bytes equals Image.get_data_size() in %d cases: %s" % [
		compared, mismatches])
	# By hand: 64x64x4 = 16384; its chain 4 x (4096+1024+256+64+16+4+1) = 21844.
	expect(ResourceBytes.image_layout_bytes(64, 64, Image.FORMAT_RGBA8) == 16384
		and ResourceBytes.image_layout_bytes(64, 64, Image.FORMAT_RGBA8, -1) == 21844,
		"64x64 RGBA8: 16384 B, 21844 B with mipmaps")
	# BC1 13x7: 16x8 /2 + 8x4 /2 + two 4x4 blocks at 8 B = 64 + 16 + 8 + 8.
	expect(ResourceBytes.image_layout_bytes(13, 7, Image.FORMAT_DXT1, -1) == 96,
		"13x7 BC1 with mipmaps rounds every level up to 4x4 blocks: 96 B")
	expect(ResourceBytes.image_layout_bytes(0, 64, Image.FORMAT_RGBA8) == 0
		and ResourceBytes.image_layout_bytes(8, 8, Image.FORMAT_MAX) == 256,
		"an empty image is 0 B and an unknown format counts as RGBA8")
	expect(ResourceBytes.full_chain_levels(1024, 1024) == 11 and ResourceBytes.full_chain_levels(13, 7) == 4
		and ResourceBytes.full_chain_levels(1, 1) == 1, "full chain level counts")

func _check_textures() -> void:
	var plain := ImageTexture.create_from_image(Image.create_empty(64, 64, false, Image.FORMAT_RGBA8))
	expect(ResourceBytes.texture_bytes(plain, ResourceBytes.MIPMAPS_NONE) == 16384,
		"RGBA8 ImageTexture 64x64 without mipmaps: 16384 B")
	expect(ResourceBytes.texture_bytes(plain) == 21844,
		"an ImageTexture whose chain is not known counts its full chain (errs high): 21844 B")
	var mipped_image := Image.create_empty(64, 64, true, Image.FORMAT_RGBA8)
	var mipped := ImageTexture.create_from_image(mipped_image)
	expect(ResourceBytes.texture_bytes(mipped, ResourceBytes.MIPMAPS_FULL) == 21844
		and ResourceBytes.texture_bytes(mipped, ResourceBytes.MIPMAPS_FULL) == mipped_image.get_data_size(),
		"RGBA8 ImageTexture 64x64 with mipmaps: 21844 B = its image's data size")
	var rgb := ImageTexture.create_from_image(Image.create_empty(64, 64, false, Image.FORMAT_RGB8))
	expect(ResourceBytes.texture_bytes(rgb, ResourceBytes.MIPMAPS_NONE) == 16384,
		"an RGB8 texture counts as the RGBA8 the GPU stores: 16384 B")
	var bc1_image := Image.create_empty(64, 64, true, Image.FORMAT_DXT1)
	var bc1 := ImageTexture.create_from_image(bc1_image)
	expect(ResourceBytes.texture_bytes(bc1, ResourceBytes.MIPMAPS_FULL) == bc1_image.get_data_size()
		and ResourceBytes.texture_bytes(bc1, ResourceBytes.MIPMAPS_NONE) == 2048,
		"a BC1 ImageTexture (a VRAM sidecar) counts its compressed size: 2048 B + mips")
	var atlas := AtlasTexture.new()
	atlas.atlas = plain
	atlas.region = Rect2(0, 0, 16, 16)
	expect(ResourceBytes.texture_bytes(atlas, ResourceBytes.MIPMAPS_NONE) == 16384,
		"an AtlasTexture counts the atlas that holds its pixels")
	var placeholder := PlaceholderTexture2D.new()
	placeholder.size = Vector2(512, 512)
	expect(ResourceBytes.texture_bytes(placeholder) == 0 and ResourceBytes.texture_bytes(null) == 0,
		"a placeholder and null hold nothing")
	var gradient := GradientTexture2D.new()
	gradient.width = 64
	gradient.height = 32
	expect(ResourceBytes.texture_bytes(gradient) == 8192, "another kind of texture counts as RGBA8 without mips")
	var compressed: Texture2D = load(BPTC_TEXTURE)
	expect(compressed is CompressedTexture2D and compressed.get_format() == Image.FORMAT_BPTC_RGBA
		and compressed.get_size() == Vector2(1024, 1024), "the project's BPTC test texture loads: %s" % compressed)
	if compressed is CompressedTexture2D:
		var bptc := compressed as CompressedTexture2D
		# BC7 is 1 B per pixel; levels 1024..8 are w*h, the 4x4, 2x2 and 1x1
		# levels one 16 B block each: 1048576+262144+65536+16384+4096+1024+256
		# +64+16+16+16.
		expect(ResourceBytes.compressed_texture_levels(bptc) == 11,
			"the .ctex header says 11 levels (1024 down to 1)")
		expect(ResourceBytes.texture_bytes(bptc) == 1398128,
			"BPTC CompressedTexture2D 1024x1024 with mipmaps: 1398128 B, by hand")
		var file := FileAccess.open(bptc.get_load_path(), FileAccess.READ)
		expect(file != null and file.get_length() - ResourceBytes.CTEX_HEADER_BYTES == 1398128,
			"the estimate is exactly the image data in the .ctex file (%d B after the header)" % [
				file.get_length() - ResourceBytes.CTEX_HEADER_BYTES if file != null else -1])

func _quad_arrays() -> Array:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 1, 0), Vector3(1, 1, 0)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.BACK, Vector3.BACK, Vector3.BACK, Vector3.BACK])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2(0, 0), Vector2(1, 0), Vector2(0, 1), Vector2(1, 1)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 2, 1, 3])
	return arrays

func _shape_arrays(arrays: Array, lift: float) -> Array:
	var shape := []
	shape.resize(Mesh.ARRAY_MAX)
	var moved := PackedVector3Array()
	for point: Vector3 in arrays[Mesh.ARRAY_VERTEX]:
		moved.append(point + Vector3(0, 0, lift))
	shape[Mesh.ARRAY_VERTEX] = moved
	shape[Mesh.ARRAY_NORMAL] = arrays[Mesh.ARRAY_NORMAL]
	return shape

## What the renderer holds for every surface of `mesh`, read back (test only).
func _readback_bytes(mesh: Mesh) -> int:
	var total := 0
	for surface: int in mesh.get_surface_count():
		var data := RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
		for key: String in ["vertex_data", "attribute_data", "skin_data", "index_data", "blend_shape_data"]:
			var bytes: Variant = data.get(key)
			if bytes is PackedByteArray:
				total += (bytes as PackedByteArray).size()
	return total

func _check_meshes() -> void:
	var arrays := _quad_arrays()
	var shaped := ArrayMesh.new()
	shaped.add_blend_shape(&"raise")
	shaped.add_blend_shape(&"lower")
	shaped.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays,
		[_shape_arrays(arrays, 0.5), _shape_arrays(arrays, -0.5)])
	# By hand: 4 vertices x (12 position + 8 normal/tangent + 8 UV) = 112,
	# 6 indices x 2 = 12, 4 vertices x 2 shapes x 20 = 160.
	expect(ResourceBytes.mesh_bytes(shaped) == 284,
		"ArrayMesh with two blend shapes: 284 B by hand (got %d)" % ResourceBytes.mesh_bytes(shaped))
	expect(ResourceBytes.mesh_bytes(shaped) == _readback_bytes(shaped),
		"and the renderer's own buffers for it are the same %d B" % _readback_bytes(shaped))
	var plain := ArrayMesh.new()
	plain.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	expect(ResourceBytes.mesh_bytes(plain) == 124 and _readback_bytes(plain) == 124,
		"the same quad without shapes: 124 B")
	var skinned_arrays := _quad_arrays()
	skinned_arrays[Mesh.ARRAY_BONES] = PackedInt32Array([0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0])
	skinned_arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([1, 0, 0, 0, 0.5, 0.5, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0])
	skinned_arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color.RED, Color.GREEN, Color.BLUE, Color.WHITE])
	var skinned := ArrayMesh.new()
	skinned.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, skinned_arrays)
	expect(ResourceBytes.mesh_bytes(skinned) == _readback_bytes(skinned),
		"a skinned, coloured surface matches the renderer's buffers (%d B)" % _readback_bytes(skinned))
	var compressed := ArrayMesh.new()
	compressed.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _quad_arrays(), [], {},
		Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES)
	expect(ResourceBytes.mesh_bytes(compressed) == _readback_bytes(compressed)
		and ResourceBytes.mesh_bytes(compressed) < ResourceBytes.mesh_bytes(plain),
		"a compressed surface matches the renderer's buffers (%d B, %d uncompressed)" % [
			_readback_bytes(compressed), ResourceBytes.mesh_bytes(plain)])
	# Blend shapes take the surface's own position + normal/tangent layout:
	# 12 + 8 B uncompressed, 8 + 4 B compressed, 12 B without normals.
	var compressed_shaped := ArrayMesh.new()
	compressed_shaped.add_blend_shape(&"raise")
	compressed_shaped.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _quad_arrays(),
		[_shape_arrays(arrays, 0.5)], {}, Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES)
	expect(ResourceBytes.mesh_bytes(compressed_shaped) == _readback_bytes(compressed_shaped),
		"a compressed surface with a blend shape matches the renderer's buffers (%d B, estimate %d)" % [
			_readback_bytes(compressed_shaped), ResourceBytes.mesh_bytes(compressed_shaped)])
	var bare := _quad_arrays()
	bare[Mesh.ARRAY_NORMAL] = null
	var bare_shape := []
	bare_shape.resize(Mesh.ARRAY_MAX)
	bare_shape[Mesh.ARRAY_VERTEX] = _shape_arrays(arrays, 0.5)[Mesh.ARRAY_VERTEX]
	var bare_shaped := ArrayMesh.new()
	bare_shaped.add_blend_shape(&"raise")
	bare_shaped.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, bare, [bare_shape])
	expect(ResourceBytes.mesh_bytes(bare_shaped) == _readback_bytes(bare_shaped),
		"a blend shape without normals matches the renderer's buffers (%d B, estimate %d)" % [
			_readback_bytes(bare_shaped), ResourceBytes.mesh_bytes(bare_shaped)])
	# A PrimitiveMesh keeps its arrays only in the renderer: replacing the
	# server-side surface changes what surface_get_arrays() returns, so asking
	# would read video memory back. It counts 0 instead.
	var box := BoxMesh.new()
	var generated_vertices := (box.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	var triangle := []
	triangle.resize(Mesh.ARRAY_MAX)
	triangle[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	RenderingServer.mesh_clear(box.get_rid())
	RenderingServer.mesh_add_surface_from_arrays(box.get_rid(), RenderingServer.PRIMITIVE_TRIANGLES, triangle)
	expect(generated_vertices == 24
		and (box.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() == 3,
		"a PrimitiveMesh's surface_get_arrays() is the renderer's copy (a read-back on a GPU)")
	expect(ResourceBytes.mesh_bytes(BoxMesh.new()) == 0 and ResourceBytes.mesh_bytes(box) == 0,
		"a PrimitiveMesh counts 0 rather than read back")
	expect(ResourceBytes.mesh_bytes(null) == 0 and ResourceBytes.mesh_bytes(ImmediateMesh.new()) == 0,
		"null and an ImmediateMesh (no CPU-side record) count 0")
	var position_only := Mesh.ARRAY_FORMAT_VERTEX | Mesh.ARRAY_FORMAT_INDEX
	expect(ResourceBytes.surface_bytes(position_only, 65536, 3, 0) == 65536 * 12 + 3 * 2
		and ResourceBytes.surface_bytes(position_only, 65537, 3, 0) == 65537 * 12 + 3 * 4,
		"indices are 16-bit up to 65536 vertices and 32-bit above")
	# An ImporterMesh with a LOD: the mesh it becomes plus the LOD's indices.
	var importer := ImporterMesh.new()
	importer.add_blend_shape("raise")
	importer.add_blend_shape("lower")
	importer.add_surface(Mesh.PRIMITIVE_TRIANGLES, _quad_arrays(),
		[_shape_arrays(arrays, 0.5), _shape_arrays(arrays, -0.5)], {0.5: PackedInt32Array([0, 1, 2])})
	var generated := importer.get_mesh()
	expect(ResourceBytes.importer_mesh_bytes(importer) == ResourceBytes.mesh_bytes(generated) + 3 * 2
		and ResourceBytes.mesh_bytes(generated) == 284,
		"importer_mesh_bytes is the generated mesh (284 B) plus its LOD indices (6 B): %d" % [
			ResourceBytes.importer_mesh_bytes(importer)])

## Builds a GLB with two quads sharing one 32x16 RGBA8 texture, then parses
## it back as the client does at runtime (GLTFDocument, generate_scene, pack).
func _check_generated_glb() -> void:
	var root := Node3D.new()
	var image := Image.create_empty(32, 16, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.6, 0.3, 0.1, 0.5))
	var material := StandardMaterial3D.new()
	material.albedo_texture = ImageTexture.create_from_image(image)
	for index: int in 2:
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _quad_arrays())
		mesh.surface_set_material(0, material)
		var instance := MeshInstance3D.new()
		instance.mesh = mesh
		root.add_child(instance)
		instance.owner = root
	var writer := GLTFDocument.new()
	var written := GLTFState.new()
	var error := writer.append_from_scene(root, written)
	if error == OK:
		error = writer.write_to_filesystem(written, GENERATED_GLB)
	root.free()
	expect(error == OK, "a GLB is written (%s)" % error_string(error))
	var reader := GLTFDocument.new()
	var state := GLTFState.new()
	expect(reader.append_from_file(ProjectSettings.globalize_path(GENERATED_GLB), state) == OK, "the GLB parses")
	var parsed := ResourceBytes.gltf_state_resources(state, ResourceBytes.MIPMAPS_NONE)
	# By hand: two meshes of 124 B (see _check_meshes) and one 32x16x4 texture.
	expect(parsed.meshes == 2 and parsed.textures == 1 and parsed.mesh_bytes == 248
		and parsed.texture_bytes == 2048 and parsed.bytes == 2296,
		"the parsed glTF state, before generation, holds 248 + 2048 B: %s" % parsed)
	expect(ResourceBytes.gltf_state_bytes(state) == 248 + 2732,
		"gltf_state_bytes with an unknown chain counts the texture's mips: 2980 B")
	var generated := reader.generate_scene(state)
	for child: Node in generated.get_children():
		child.owner = generated
	var scene := PackedScene.new()
	expect(scene.pack(generated) == OK, "the generated scene packs")
	generated.free()
	var nodes_before := Performance.get_monitor(Performance.OBJECT_NODE_COUNT)
	var found := ResourceBytes.scene_resources(scene, ResourceBytes.MIPMAPS_NONE)
	expect(Performance.get_monitor(Performance.OBJECT_NODE_COUNT) == nodes_before,
		"scene_resources instantiates nothing")
	expect(found.mesh_bytes == 248 and found.texture_bytes == 2048 and found.bytes == 2296
		and (found.meshes as Array).size() == 2 and (found.textures as Array).size() == 1,
		"PackedScene built from the GLB: 2 meshes (248 B) and 1 shared texture (2048 B): %s" % _summary(found))
	expect(found.bytes == parsed.bytes, "the worker-side state ledger and the published scene agree")
	var unknown_chain := ResourceBytes.scene_resources(scene)
	expect(unknown_chain.texture_bytes == 2732, "without a mip hint the texture counts its chain: 2732 B")
	var seen := {}
	var first := ResourceBytes.scene_resources(scene, ResourceBytes.MIPMAPS_NONE, seen)
	var again := ResourceBytes.scene_resources(scene, ResourceBytes.MIPMAPS_NONE, seen)
	expect(first.bytes == 2296 and again.bytes == 0 and (again.meshes as Array).is_empty(),
		"objects already in `seen` are not counted twice")
	_expect_matches_instance(scene, found, "generated GLB")

## A creature as releases build it: its GLB parsed raw at runtime (actor
## folders are not editor-imported), generated and packed.
func _creature_scene(state_ledger: Array) -> PackedScene:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(ProjectSettings.globalize_path(CREATURE_GLB), state) != OK:
		return null
	state_ledger.append(ResourceBytes.gltf_state_resources(state))
	var generated := document.generate_scene(state)
	if generated == null:
		return null
	_own(generated, generated)
	var scene := PackedScene.new()
	var error := scene.pack(generated)
	generated.free()
	return scene if error == OK else null

func _own(node: Node, scene_owner: Node) -> void:
	for child: Node in node.get_children():
		child.owner = scene_owner
		_own(child, scene_owner)

func _check_imported_creature() -> void:
	var ledger := []
	var scene := _creature_scene(ledger)
	expect(scene != null, "the creature GLB parses, generates and packs: %s" % CREATURE_GLB)
	if scene == null:
		return
	var began := Time.get_ticks_usec()
	var found := ResourceBytes.scene_resources(scene)
	var elapsed := Time.get_ticks_usec() - began
	print("INFO: %s %s in %d us" % [CREATURE_GLB.get_file(), _summary(found), elapsed])
	expect(found.mesh_bytes > 0 and found.texture_bytes > 0, "the creature has meshes and textures")
	var parsed: Dictionary = ledger[0]
	expect(parsed.mesh_bytes == found.mesh_bytes and parsed.texture_bytes == found.texture_bytes,
		"the creature's parsed-state ledger equals its packed scene's: %s vs %s" % [parsed, _summary(found)])
	_expect_matches_instance(scene, found, "creature GLB")
	# An editor-imported GLB (world props are imported): CompressedTexture2D
	# images, generated LODs (not counted) and shadow meshes.
	var imported: PackedScene = load(IMPORTED_GLB)
	expect(imported != null, "the imported world GLB loads: %s" % IMPORTED_GLB)
	if imported == null:
		return
	var world := ResourceBytes.scene_resources(imported)
	print("INFO: %s %s" % [IMPORTED_GLB.get_file(), _summary(world)])
	var by_hand := 0
	var compressed_count := 0
	for texture: Texture2D in world.textures:
		if texture is CompressedTexture2D:
			compressed_count += 1
			var compressed := texture as CompressedTexture2D
			by_hand += ResourceBytes.image_layout_bytes(compressed.get_width(), compressed.get_height(),
				ResourceBytes.gpu_format(compressed.get_format()), ResourceBytes.compressed_texture_levels(compressed))
	expect(compressed_count > 0 and compressed_count == (world.textures as Array).size()
		and by_hand == world.texture_bytes and world.mesh_bytes > 0,
		"an imported scene's textures are CompressedTexture2D counted from their headers (%d)" % compressed_count)
	_expect_matches_instance(imported, world, "imported world GLB")

## The meshes and textures an instance of `scene` actually shows are exactly
## the ones the walk found (instantiated here only to check).
func _expect_matches_instance(scene: PackedScene, found: Dictionary, label: String) -> void:
	var instance := scene.instantiate()
	var meshes := {}
	var textures := {}
	for node: Node in instance.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		if mesh == null:
			continue
		meshes[mesh.get_instance_id()] = true
		if mesh is ArrayMesh and (mesh as ArrayMesh).shadow_mesh != null:
			meshes[(mesh as ArrayMesh).shadow_mesh.get_instance_id()] = true
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface)
			var override := (node as MeshInstance3D).get_surface_override_material(surface)
			for used: Material in [material, override, (node as MeshInstance3D).material_override]:
				if used is BaseMaterial3D:
					for parameter: int in BaseMaterial3D.TEXTURE_MAX:
						var texture := (used as BaseMaterial3D).get_texture(parameter)
						if texture != null:
							textures[texture.get_instance_id()] = true
	instance.free()
	var found_meshes := {}
	for mesh: Mesh in found.meshes:
		found_meshes[mesh.get_instance_id()] = true
	var found_textures := {}
	for texture: Texture2D in found.textures:
		found_textures[texture.get_instance_id()] = true
	expect(_same_keys(meshes, found_meshes),
		"%s: the walk found every mesh an instance shows (%d) and no other (%d)" % [label, meshes.size(), found_meshes.size()])
	expect(_same_keys(textures, found_textures),
		"%s: the walk found every texture an instance samples (%d) and no other (%d)" % [label, textures.size(), found_textures.size()])

func _same_keys(a: Dictionary, b: Dictionary) -> bool:
	if a.size() != b.size():
		return false
	for key: Variant in a:
		if not b.has(key):
			return false
	return true

func _summary(found: Dictionary) -> String:
	return "{bytes %d, mesh_bytes %d, texture_bytes %d, meshes %d, textures %d}" % [found.bytes,
		found.mesh_bytes, found.texture_bytes, (found.meshes as Array).size(), (found.textures as Array).size()]

## A scene whose textures sit in every kind of material slot: a ShaderMaterial
## sampler (16x16, 1024 B) with a StandardMaterial3D next pass (normal map
## 8x8, 256 B) on a quad (124 B), and particles whose ParticleProcessMaterial
## has a colour ramp (256x1, 1024 B) and whose BoxMesh draw pass (0 B) has a
## roughness map (4x4, 64 B).
func _material_scene() -> PackedScene:
	var root := Node3D.new()
	var shader := Shader.new()
	shader.code = "shader_type spatial;\nuniform sampler2D detail : source_color;\nuniform float strength = 1.0;\n" \
		+ "void fragment() { ALBEDO = texture(detail, UV).rgb * strength; }\n"
	var shaded := ShaderMaterial.new()
	shaded.shader = shader
	shaded.set_shader_parameter(&"detail", ImageTexture.create_from_image(Image.create_empty(16, 16, false, Image.FORMAT_RGBA8)))
	var next := StandardMaterial3D.new()
	next.normal_enabled = true
	next.normal_texture = ImageTexture.create_from_image(Image.create_empty(8, 8, false, Image.FORMAT_RGBA8))
	shaded.next_pass = next
	var quad := ArrayMesh.new()
	quad.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _quad_arrays())
	quad.surface_set_material(0, shaded)
	var shown := MeshInstance3D.new()
	shown.mesh = quad
	root.add_child(shown)
	var particles := GPUParticles3D.new()
	var process := ParticleProcessMaterial.new()
	var ramp := GradientTexture1D.new()
	ramp.gradient = Gradient.new()
	process.color_ramp = ramp
	particles.process_material = process
	var box := BoxMesh.new()
	var box_material := StandardMaterial3D.new()
	box_material.roughness_texture = ImageTexture.create_from_image(Image.create_empty(4, 4, false, Image.FORMAT_RGBA8))
	box.material = box_material
	particles.draw_pass_1 = box
	root.add_child(particles)
	_own(root, root)
	var scene := PackedScene.new()
	var error := scene.pack(root)
	root.free()
	return scene if error == OK else null

## Material slots of every kind are walked; a ShaderMaterial's parameters
## only on the main thread, since listing them waits for the main thread.
func _check_materials() -> void:
	var scene := _material_scene()
	expect(scene != null, "the material scene packs")
	if scene == null:
		return
	var began := Time.get_ticks_usec()
	var main := ResourceBytes.scene_resources(scene, ResourceBytes.MIPMAPS_NONE)
	print("INFO: material scene %s in %d us" % [_summary(main), Time.get_ticks_usec() - began])
	expect(main.texture_bytes == 1024 + 256 + 1024 + 64 and (main.textures as Array).size() == 4
		and main.mesh_bytes == 124 and (main.meshes as Array).size() == 2 and main.skipped_shader_materials == 0,
		"the main thread finds the shader sampler, the next pass's normal map, the colour ramp and the box's roughness map: %s" % _summary(main))
	# A worker must not wait for the RenderingServer: the main thread stays
	# busy (no frame, no flush) while it runs, as a caller blocked on it would.
	var answers := []
	var task := WorkerThreadPool.add_task(func() -> void:
		answers.append(ResourceBytes.scene_resources(scene, ResourceBytes.MIPMAPS_NONE)))
	var deadline := Time.get_ticks_msec() + 3000
	while not WorkerThreadPool.is_task_completed(task) and Time.get_ticks_msec() < deadline:
		OS.delay_msec(2)
	expect(WorkerThreadPool.is_task_completed(task),
		"a worker's walk returns while the main thread is busy (no RenderingServer round trip)")
	while not WorkerThreadPool.is_task_completed(task):
		await process_frame
	WorkerThreadPool.wait_for_task_completion(task)
	var worker: Dictionary = answers[0] if not answers.is_empty() else {}
	expect(not worker.is_empty() and worker.skipped_shader_materials == 1
		and worker.texture_bytes == 256 + 1024 + 64 and worker.mesh_bytes == 124,
		"a worker skips the ShaderMaterial's parameters and says so: %s" % [
			"%s skipped %d" % [_summary(worker), worker.skipped_shader_materials] if not worker.is_empty() else "no answer"])

func _check_packed() -> void:
	var image := Image.create_empty(4, 4, false, Image.FORMAT_RGBA8)
	var payload := {
		"a": PackedFloat32Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
		"bb": PackedVector3Array([Vector3.ONE, Vector3.ONE, Vector3.ONE, Vector3.ONE, Vector3.ONE]),
		"c": [PackedByteArray([1, 2, 3, 4, 5, 6, 7]), PackedInt32Array([1, 2])],
		"image": image,
		"n": 3,
	}
	# Keys 1+2+1+5+1 characters x 4 = 40; 40 + 60 + (7 + 8) + 64 + 8.
	expect(ResourceBytes.packed_bytes(payload) == 40 + 40 + 60 + 15 + 64 + 8,
		"packed_bytes counts payloads: %d" % ResourceBytes.packed_bytes(payload))
	expect(ResourceBytes.packed_bytes(PackedVector2Array([Vector2.ONE, Vector2.ZERO])) == 16
		and ResourceBytes.packed_bytes(PackedColorArray([Color.RED])) == 16
		and ResourceBytes.packed_bytes(PackedInt64Array([1, 2, 3])) == 24
		and ResourceBytes.packed_bytes(PackedStringArray(["ab", "c"])) == 12
		and ResourceBytes.packed_bytes(null) == 0 and ResourceBytes.packed_bytes(Node3D) == 0,
		"element sizes of the packed array kinds")
	var cycle := []
	cycle.append(cycle)
	expect(ResourceBytes.packed_bytes(cycle) == 0, "an array that holds itself stops at the depth guard")
	cycle.clear()

## The estimators read no server state, so a worker gets the main thread's
## answers.
func _check_worker() -> void:
	var arrays := _quad_arrays()
	var importer := ImporterMesh.new()
	importer.add_blend_shape("raise")
	importer.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays, [_shape_arrays(arrays, 0.5)])
	var mesh := ArrayMesh.new()
	mesh.add_blend_shape(&"raise")
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [_shape_arrays(arrays, 0.5)])
	var texture: Texture2D = load(BPTC_TEXTURE)
	var scene := _creature_scene([])
	var main := [ResourceBytes.importer_mesh_bytes(importer), ResourceBytes.mesh_bytes(mesh),
		ResourceBytes.texture_bytes(texture), int(ResourceBytes.scene_resources(scene).bytes) if scene != null else 0]
	var worker := []
	var task := WorkerThreadPool.add_task(func() -> void:
		worker.append_array([ResourceBytes.importer_mesh_bytes(importer), ResourceBytes.mesh_bytes(mesh),
			ResourceBytes.texture_bytes(texture),
			int(ResourceBytes.scene_resources(scene).bytes) if scene != null else 0]))
	WorkerThreadPool.wait_for_task_completion(task)
	expect(worker == main, "a worker thread gets the same estimates: %s vs %s" % [worker, main])
