extends RefCounted
## Byte estimates for memory ledgers (perf work 2026-11, memory classes M1).
##
## The caches that keep meshes and textures (WorldPark, GlbSceneCache, the RL
## head library, the texture and mesh pools) need to know roughly what an
## entry holds to stay inside a class budget (memory_budgets.gd). Asking the
## GPU is not an option: Texture2D.get_image(), Mesh.surface_get_arrays() on
## an ArrayMesh or a PrimitiveMesh and RenderingServer.mesh_get_surface() read
## the data back from video memory and stall the frame. Everything here reads
## only what the resources keep on the CPU side (sizes, formats, counts, file
## headers), so a call costs microseconds and is safe on a worker thread: no
## function waits for the RenderingServer (see `scene_resources` for the one
## case that would, ShaderMaterial parameters, which only the main thread
## walks).
##
## What the figures mean:
## - Textures: the GPU copy, with Godot's own mip and block layout
##   (Image.get_data_size() for the same size, format and levels). Three-
##   channel formats count as four, as the Vulkan/D3D12 renderers upload them
##   (RGB8 as RGBA8); an unknown format counts as RGBA8. A CompressedTexture2D
##   (imported) states its mip count in its file header, which is read; an
##   ImageTexture does not expose it, so unless the caller says
##   (`mipmaps`), its full chain is counted: the estimate errs high, never
##   low, as texture_footprint.gd's does.
## - Meshes: vertex, attribute, skin and index buffers from each surface's
##   vertex count, index count and format (RenderingServer's own stride
##   functions: pure arithmetic, no server state), plus, per vertex and blend
##   shape, the surface's position and normal/tangent strides: 20 B
##   uncompressed with normals (measured 20.2 B over the RL heads,
##   memory-classes design), 12 B without normals or with compressed
##   attributes. Not counted: LOD index buffers of an ArrayMesh (not exposed;
##   an ImporterMesh's are), shadow meshes (their own resources), the
##   per-instance buffers the renderer adds for skinned or blend-shape
##   instances, and PrimitiveMeshes (BoxMesh and the like keep their arrays
##   only in the renderer, so they count 0).
## - `packed_bytes`: the payload of packed arrays, strings and images held on
##   the CPU (sidecars), without allocator or Variant overhead.
## - Animations (`animation_bytes`, CPU memory): every track's keys at the
##   engine's own key size, with the slack of a key array grown one insert at
##   a time, plus a fixed cost per track (see ANIMATION_KEY_BYTES).
##
## No `class_name`: callers preload it (worker threads and early autoloads do
## not wait for the global class cache).

## Bits per pixel and block edge of every Image.Format, as Godot lays images
## out (Image.get_format_pixel_size / get_format_block_size). A level's size
## is rounded up to whole blocks; block-compressed chains continue to 1x1.
const FORMAT_LAYOUT := {
	Image.FORMAT_L8: [8, 1], Image.FORMAT_LA8: [16, 1], Image.FORMAT_R8: [8, 1],
	Image.FORMAT_RG8: [16, 1], Image.FORMAT_RGB8: [24, 1], Image.FORMAT_RGBA8: [32, 1],
	Image.FORMAT_RGBA4444: [16, 1], Image.FORMAT_RGB565: [16, 1],
	Image.FORMAT_RF: [32, 1], Image.FORMAT_RGF: [64, 1], Image.FORMAT_RGBF: [96, 1],
	Image.FORMAT_RGBAF: [128, 1], Image.FORMAT_RH: [16, 1], Image.FORMAT_RGH: [32, 1],
	Image.FORMAT_RGBH: [48, 1], Image.FORMAT_RGBAH: [64, 1], Image.FORMAT_RGBE9995: [32, 1],
	Image.FORMAT_DXT1: [4, 4], Image.FORMAT_DXT3: [8, 4], Image.FORMAT_DXT5: [8, 4],
	Image.FORMAT_RGTC_R: [4, 4], Image.FORMAT_RGTC_RG: [8, 4],
	Image.FORMAT_BPTC_RGBA: [8, 4], Image.FORMAT_BPTC_RGBF: [8, 4], Image.FORMAT_BPTC_RGBFU: [8, 4],
	Image.FORMAT_ETC: [4, 4], Image.FORMAT_ETC2_R11: [4, 4], Image.FORMAT_ETC2_R11S: [4, 4],
	Image.FORMAT_ETC2_RG11: [8, 4], Image.FORMAT_ETC2_RG11S: [8, 4],
	Image.FORMAT_ETC2_RGB8: [4, 4], Image.FORMAT_ETC2_RGBA8: [8, 4],
	Image.FORMAT_ETC2_RGB8A1: [4, 4], Image.FORMAT_ETC2_RA_AS_RG: [8, 4],
	Image.FORMAT_DXT5_RA_AS_RG: [8, 4], Image.FORMAT_ASTC_4x4: [8, 4],
	Image.FORMAT_ASTC_4x4_HDR: [8, 4], Image.FORMAT_ASTC_8x8: [2, 8],
	# Godot 4.7 sizes ASTC 8x8 HDR at 8 bits per pixel (Image.get_data_size),
	# not the 2 of ASTC 8x8; kept as the engine allocates it.
	Image.FORMAT_ASTC_8x8_HDR: [8, 8], Image.FORMAT_R16: [16, 1], Image.FORMAT_RG16: [32, 1],
	Image.FORMAT_RGB16: [48, 1], Image.FORMAT_RGBA16: [64, 1], Image.FORMAT_R16I: [16, 1],
	Image.FORMAT_RG16I: [32, 1], Image.FORMAT_RGB16I: [48, 1], Image.FORMAT_RGBA16I: [64, 1],
}
## Three-channel formats the RenderingDevice renderers store with a fourth.
const GPU_PADDED_FORMATS := {
	Image.FORMAT_RGB8: Image.FORMAT_RGBA8, Image.FORMAT_RGBH: Image.FORMAT_RGBAH,
	Image.FORMAT_RGBF: Image.FORMAT_RGBAF, Image.FORMAT_RGB16: Image.FORMAT_RGBA16,
	Image.FORMAT_RGB16I: Image.FORMAT_RGBA16I,
}
## The format a texture of unknown format is counted as.
const DEFAULT_FORMAT := Image.FORMAT_RGBA8

## `mipmaps` arguments: the texture has none, has its full chain, or the
## caller does not know (an ImageTexture then counts its full chain).
const MIPMAPS_UNKNOWN := -1
const MIPMAPS_NONE := 0
const MIPMAPS_FULL := 1

## CompressedTexture2D (.ctex, "GST2") header: the image's mip count (not
## counting the base level) is a little-endian u32 at this offset.
const CTEX_MAGIC := "GST2"
const CTEX_MIPMAPS_OFFSET := 44
const CTEX_HEADER_BYTES := 52

## Bytes of a `width` x `height` image of `format` with `levels` levels (base
## included; < 0: the full chain to 1x1), exactly as Image.get_data_size()
## would say. An unknown format counts as RGBA8.
static func image_layout_bytes(width: int, height: int, format: int, levels := 1) -> int:
	if width <= 0 or height <= 0:
		return 0
	var layout: Array = FORMAT_LAYOUT.get(format, FORMAT_LAYOUT[DEFAULT_FORMAT])
	var bits := int(layout[0])
	var block := int(layout[1])
	var count := levels if levels > 0 else full_chain_levels(width, height)
	var total := 0
	var w := width
	var h := height
	for level: int in count:
		var bw := ceili(w / float(block)) * block
		var bh := ceili(h / float(block)) * block
		total += bw * bh * bits / 8
		if w == 1 and h == 1:
			break
		w = maxi(1, w >> 1)
		h = maxi(1, h >> 1)
	return total

## Levels in a full mip chain of a `width` x `height` image, base included.
static func full_chain_levels(width: int, height: int) -> int:
	var levels := 1
	var edge := maxi(width, height)
	while edge > 1:
		edge >>= 1
		levels += 1
	return levels

## What `format` occupies on the GPU (three channels padded to four).
static func gpu_format(format: int) -> int:
	return int(GPU_PADDED_FORMATS.get(format, format)) if FORMAT_LAYOUT.has(format) else DEFAULT_FORMAT

## Estimated GPU bytes of `texture` (see the header). An AtlasTexture counts
## its atlas, a placeholder nothing. `mipmaps` (MIPMAPS_*) is for an
## ImageTexture whose chain the caller knows; a CompressedTexture2D reads its
## own header, and any other kind counts RGBA8 without mips.
static func texture_bytes(texture: Texture2D, mipmaps := MIPMAPS_UNKNOWN) -> int:
	if texture == null or texture is PlaceholderTexture2D:
		return 0
	if texture is AtlasTexture:
		return texture_bytes((texture as AtlasTexture).atlas, mipmaps)
	var width := texture.get_width()
	var height := texture.get_height()
	var format := DEFAULT_FORMAT
	var levels := 1
	if texture is CompressedTexture2D:
		format = _reported_format(texture)
		levels = compressed_texture_levels(texture as CompressedTexture2D)
	elif texture is ImageTexture or texture is PortableCompressedTexture2D:
		format = _reported_format(texture)
		levels = 1 if mipmaps == MIPMAPS_NONE else -1
	return image_layout_bytes(width, height, gpu_format(format), levels)

## Levels (base included) an imported texture was saved with, from its .ctex
## header; 1 when the file cannot be read.
static func compressed_texture_levels(texture: CompressedTexture2D) -> int:
	var path := texture.get_load_path()
	if path.is_empty():
		return 1
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() < CTEX_HEADER_BYTES:
		return 1
	var header := file.get_buffer(CTEX_HEADER_BYTES)
	if header.slice(0, 4).get_string_from_ascii() != CTEX_MAGIC:
		return 1
	var mipmaps := int(header.decode_u32(CTEX_MIPMAPS_OFFSET))
	return clampi(mipmaps + 1, 1, full_chain_levels(texture.get_width(), texture.get_height()))

## The format an ImageTexture, CompressedTexture2D or PortableCompressedTexture2D
## reports (kept on the CPU side), or DEFAULT_FORMAT. Not asked of other
## kinds, whose implementation could read the image back.
static func _reported_format(texture: Texture2D) -> int:
	var format := int(texture.get_format())
	return format if format >= 0 and format < Image.FORMAT_MAX else DEFAULT_FORMAT

## Estimated GPU bytes of `mesh`: every surface's buffers and blend shapes
## (see the header). An ArrayMesh reads its CPU-side surface records; an
## ImporterMesh-built mesh has the same layout. Every other kind counts 0
## rather than read back: a PrimitiveMesh's surface_get_arrays() is
## RenderingServer.mesh_surface_get_arrays() (measured in 4.7.2: replacing
## the server-side surface changes what it returns), and an ImmediateMesh or a
## placeholder keeps no CPU-side record.
static func mesh_bytes(mesh: Mesh) -> int:
	if mesh == null or mesh is not ArrayMesh:
		return 0
	var total := 0
	var array_mesh := mesh as ArrayMesh
	var shapes := array_mesh.get_blend_shape_count()
	for surface: int in array_mesh.get_surface_count():
		total += surface_bytes(array_mesh.surface_get_format(surface),
			array_mesh.surface_get_array_len(surface),
			array_mesh.surface_get_array_index_len(surface), shapes)
	return total

## Bytes of one surface of `format` (Mesh.ARRAY_FORMAT_* and flags) with
## `vertices` vertices, `indices` indices and `blend_shapes` shapes. A blend
## shape stores each vertex's position and normal/tangent in the surface's own
## layout (12 + 8 B uncompressed, 8 + 4 B with compressed attributes).
static func surface_bytes(format: int, vertices: int, indices: int, blend_shapes: int) -> int:
	if vertices <= 0:
		return 0
	var position := RenderingServer.mesh_surface_get_format_vertex_stride(format, vertices) \
		+ RenderingServer.mesh_surface_get_format_normal_tangent_stride(format, vertices)
	var per_vertex := position \
		+ RenderingServer.mesh_surface_get_format_attribute_stride(format, vertices) \
		+ RenderingServer.mesh_surface_get_format_skin_stride(format, vertices)
	var total := vertices * per_vertex
	if indices > 0:
		total += indices * RenderingServer.mesh_surface_get_format_index_stride(format, vertices)
	if blend_shapes > 0:
		total += vertices * blend_shapes * position
	return total

## The Mesh.ARRAY_FORMAT_* bits of the arrays present in `arrays` (a surface
## array as Mesh.surface_get_arrays returns it). Normals bring a tangent slot,
## as the renderer adds one; 8-weight skins and custom channel formats are
## flags the caller ORs in.
static func array_format(arrays: Array) -> int:
	var format := 0
	for index: int in mini(arrays.size(), Mesh.ARRAY_MAX):
		if arrays[index] != null:
			format |= 1 << index
	if format & Mesh.ARRAY_FORMAT_NORMAL:
		format |= Mesh.ARRAY_FORMAT_TANGENT
	return format

static func _array_size(arrays: Array, index: int) -> int:
	if index >= arrays.size() or arrays[index] == null:
		return 0
	var value: Variant = arrays[index]
	return value.size() if value is Array or _is_packed_array(value) else 0

## Estimated GPU bytes of the ArrayMesh `mesh` will become (`get_mesh()`),
## plus its LOD index buffers: for ledgers kept on a worker before the scene
## is generated. Reads only the CPU-side arrays the importer mesh holds.
static func importer_mesh_bytes(mesh: ImporterMesh) -> int:
	if mesh == null:
		return 0
	var total := 0
	var shapes := mesh.get_blend_shape_count()
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.get_surface_arrays(surface)
		# get_surface_format() holds the flags only (compression, 8 weights,
		# custom channel formats); the array bits come from the arrays.
		var format := mesh.get_surface_format(surface) | array_format(arrays)
		var vertices := _array_size(arrays, Mesh.ARRAY_VERTEX)
		total += surface_bytes(format, vertices, _array_size(arrays, Mesh.ARRAY_INDEX), shapes)
		if vertices <= 0:
			continue
		var index_stride := RenderingServer.mesh_surface_get_format_index_stride(format, vertices)
		for lod: int in mesh.get_surface_lod_count(surface):
			total += mesh.get_surface_lod_indices(surface, lod).size() * index_stride
	return total

## What a parsed glTF state will hold once generated: its meshes
## (`importer_mesh_bytes`) and images (`texture_bytes` with `mipmaps`), each
## distinct object once, and objects already in `seen` (instance id -> true,
## shared across calls) not at all. {"bytes", "mesh_bytes", "texture_bytes",
## "meshes", "textures"} (the last two are counts). For a worker-side ledger:
## the state is not changed.
static func gltf_state_resources(state: GLTFState, mipmaps := MIPMAPS_UNKNOWN,
		seen: Dictionary = {}) -> Dictionary:
	var result := {"bytes": 0, "mesh_bytes": 0, "texture_bytes": 0, "meshes": 0, "textures": 0}
	if state == null:
		return result
	for gltf_mesh: GLTFMesh in state.get_meshes():
		var mesh: ImporterMesh = gltf_mesh.mesh if gltf_mesh != null else null
		if mesh == null or not _first_sight(mesh, seen):
			continue
		result.mesh_bytes += importer_mesh_bytes(mesh)
		result.meshes += 1
	for texture: Texture2D in state.get_images():
		var resolved := _atlas_source(texture)
		if resolved == null or not _first_sight(resolved, seen):
			continue
		result.texture_bytes += texture_bytes(resolved, mipmaps)
		result.textures += 1
	result.bytes = int(result.mesh_bytes) + int(result.texture_bytes)
	return result

## `gltf_state_resources(state, mipmaps).bytes`.
static func gltf_state_bytes(state: GLTFState, mipmaps := MIPMAPS_UNKNOWN) -> int:
	return int(gltf_state_resources(state, mipmaps).bytes)

## The meshes and textures a packed scene references, found by walking its
## SceneState node properties (meshes, their surface materials and shadow
## meshes, materials and their texture parameters, next passes, MultiMesh
## meshes, nested scene instances) without instantiating it or reading any
## resource back. Each distinct object is counted once; objects already in
## `seen` (instance id -> true, shared across calls, materials included) are
## skipped. `mipmaps` applies to ImageTextures (see texture_bytes).
## Returns {"bytes", "mesh_bytes", "texture_bytes", "meshes": Array[Mesh],
## "textures": Array[Texture2D], "skipped_shader_materials"}; the arrays hold
## strong references, so a caller that keeps them for reference-count probes
## should keep WeakRefs.
## A ShaderMaterial's parameters can only be listed through the
## RenderingServer, a round trip that waits for the main thread (measured: a
## worker asking while the main thread waits for that worker never returns).
## So only the main thread walks them; on a worker such materials are counted
## in "skipped_shader_materials" and their parameter textures are missing.
## Call this on the main thread (a ledger kept at publish time does) when the
## scene may hold ShaderMaterials.
static func scene_resources(scene: PackedScene, mipmaps := MIPMAPS_UNKNOWN,
		seen: Dictionary = {}) -> Dictionary:
	var meshes: Array[Mesh] = []
	var textures: Array[Texture2D] = []
	var result := {"bytes": 0, "mesh_bytes": 0, "texture_bytes": 0,
		"meshes": meshes, "textures": textures, "skipped_shader_materials": 0}
	if scene != null:
		_walk_state(scene.get_state(), result, seen, mipmaps, 0)
	result.bytes = int(result.mesh_bytes) + int(result.texture_bytes)
	return result

## Nested scene instances and inherited bases deeper than this are not walked.
const MAX_SCENE_DEPTH := 8
## Nested arrays, dictionaries and material passes deeper than this are not
## walked (a guard against cycles).
const MAX_VALUE_DEPTH := 16

static func _walk_state(state: SceneState, result: Dictionary, seen: Dictionary,
		mipmaps: int, depth: int) -> void:
	if state == null or depth > MAX_SCENE_DEPTH:
		return
	_walk_state(state.get_base_scene_state(), result, seen, mipmaps, depth + 1)
	for node: int in state.get_node_count():
		var instance := state.get_node_instance(node)
		if instance != null:
			_walk_state(instance.get_state(), result, seen, mipmaps, depth + 1)
		for property: int in state.get_node_property_count(node):
			_collect(state.get_node_property_value(node, property), result, seen, mipmaps, 0)

static func _collect(value: Variant, result: Dictionary, seen: Dictionary, mipmaps: int,
		depth: int) -> void:
	if depth > MAX_VALUE_DEPTH:
		return
	if value is Array:
		for item: Variant in value:
			_collect(item, result, seen, mipmaps, depth + 1)
	elif value is Dictionary:
		for item: Variant in (value as Dictionary).values():
			_collect(item, result, seen, mipmaps, depth + 1)
	elif value is Texture2D:
		var texture := _atlas_source(value)
		if texture != null and _first_sight(texture, seen):
			result.texture_bytes += texture_bytes(texture, mipmaps)
			(result.textures as Array).append(texture)
	elif value is Mesh:
		var mesh := value as Mesh
		if not _first_sight(mesh, seen):
			return
		result.mesh_bytes += mesh_bytes(mesh)
		(result.meshes as Array).append(mesh)
		if mesh is PrimitiveMesh:
			# Its get_surface_count() builds a pending mesh in the renderer.
			_collect((mesh as PrimitiveMesh).material, result, seen, mipmaps, depth + 1)
			return
		for surface: int in mesh.get_surface_count():
			_collect(mesh.surface_get_material(surface), result, seen, mipmaps, depth + 1)
		if mesh is ArrayMesh:
			_collect((mesh as ArrayMesh).shadow_mesh, result, seen, mipmaps, depth + 1)
	elif value is ImporterMesh:
		var importer := value as ImporterMesh
		if not _first_sight(importer, seen):
			return
		result.mesh_bytes += importer_mesh_bytes(importer)
		for surface: int in importer.get_surface_count():
			_collect(importer.get_surface_material(surface), result, seen, mipmaps, depth + 1)
	elif value is Material:
		if not _first_sight(value, seen):
			return
		for referenced: Variant in _material_references(value as Material, result):
			_collect(referenced, result, seen, mipmaps, depth + 1)
	elif value is MultiMesh:
		_collect((value as MultiMesh).mesh, result, seen, mipmaps, depth + 1)

## The textures and materials (next passes) `material` references; getting one
## returns the referenced resource, never image data. A BaseMaterial3D answers
## through its texture slots (under 1 us; its property list costs about
## 0.2 ms, measured), a ShaderMaterial through its shader's uniform list on
## the main thread only (see scene_resources), any other kind through its
## Object-valued properties.
static func _material_references(material: Material, result: Dictionary) -> Array:
	var found := [material.next_pass]
	if material is BaseMaterial3D:
		for slot: int in BaseMaterial3D.TEXTURE_MAX:
			found.append((material as BaseMaterial3D).get_texture(slot))
	elif material is ShaderMaterial:
		var shader := (material as ShaderMaterial).shader
		if shader == null:
			return found
		if OS.get_thread_caller_id() != OS.get_main_thread_id():
			result.skipped_shader_materials += 1
			return found
		for uniform: Dictionary in shader.get_shader_uniform_list():
			if int(uniform.get("type", TYPE_NIL)) == TYPE_OBJECT:
				found.append((material as ShaderMaterial).get_shader_parameter(StringName(uniform.name)))
	else:
		for property: Dictionary in material.get_property_list():
			if int(property.get("type", TYPE_NIL)) == TYPE_OBJECT and property.name != &"next_pass":
				found.append(material.get(StringName(property.name)))
	return found

## The texture that holds an AtlasTexture's pixels (followed to the end), or
## `texture` itself.
static func _atlas_source(texture: Texture2D) -> Texture2D:
	var current := texture
	for step: int in MAX_VALUE_DEPTH:
		if current is not AtlasTexture:
			return current
		current = (current as AtlasTexture).atlas
	return current

## True the first time `object` is seen in `seen`, and marks it.
static func _first_sight(object: Object, seen: Dictionary) -> bool:
	var id := object.get_instance_id()
	if seen.has(id):
		return false
	seen[id] = true
	return true

## Payload bytes `value` holds on the CPU: packed arrays by element size,
## strings at 4 B per character, an Image's data, arrays and dictionaries by
## their contents (keys included), any other value 8 B. No allocator or
## Variant overhead; other objects (meshes, textures, nodes) count 0 here.
static func packed_bytes(value: Variant, depth := 0) -> int:
	if depth > MAX_VALUE_DEPTH:
		return 0
	match typeof(value):
		TYPE_NIL:
			return 0
		TYPE_PACKED_BYTE_ARRAY:
			return (value as PackedByteArray).size()
		TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_FLOAT32_ARRAY:
			return value.size() * 4
		TYPE_PACKED_INT64_ARRAY, TYPE_PACKED_FLOAT64_ARRAY:
			return value.size() * 8
		TYPE_PACKED_VECTOR2_ARRAY:
			return value.size() * 8
		TYPE_PACKED_VECTOR3_ARRAY:
			return value.size() * 12
		TYPE_PACKED_VECTOR4_ARRAY, TYPE_PACKED_COLOR_ARRAY:
			return value.size() * 16
		TYPE_PACKED_STRING_ARRAY:
			var characters := 0
			for text: String in value:
				characters += text.length()
			return characters * 4
		TYPE_STRING, TYPE_STRING_NAME:
			return str(value).length() * 4
		TYPE_ARRAY:
			var total := 0
			for item: Variant in value:
				total += packed_bytes(item, depth + 1)
			return total
		TYPE_DICTIONARY:
			var total := 0
			for key: Variant in value:
				total += packed_bytes(key, depth + 1) + packed_bytes(value[key], depth + 1)
			return total
		TYPE_OBJECT:
			return (value as Image).get_data_size() if value is Image else 0
	return 8

static func _is_packed_array(value: Variant) -> bool:
	return typeof(value) >= TYPE_PACKED_BYTE_ARRAY and typeof(value) <= TYPE_PACKED_VECTOR4_ARRAY

## Bytes one key of each Animation.TrackType occupies (Godot 4.7: a time, a
## transition and the value). Position, rotation, scale, blend-shape and value
## keys were measured with the static memory counter (debug build, 4,096-key
## tracks: 32, 32, 32, 24 and 40 B); the rest follow the same layout.
const ANIMATION_KEY_BYTES := {
	Animation.TYPE_VALUE: 40, Animation.TYPE_POSITION_3D: 32, Animation.TYPE_ROTATION_3D: 32,
	Animation.TYPE_SCALE_3D: 32, Animation.TYPE_BLEND_SHAPE: 24, Animation.TYPE_METHOD: 48,
	Animation.TYPE_BEZIER: 40, Animation.TYPE_AUDIO: 32, Animation.TYPE_ANIMATION: 24,
}
## A key type not in the table counts as a value key.
const ANIMATION_DEFAULT_KEY_BYTES := 40
## Key arrays grow by half again when an insert finds them full, and every
## parse and Animation.copy_track inserts keys one at a time: on average a
## track holds 1.23x its keys' bytes (the mean of a 1.5x growth step; measured
## -12..+21 % per track for 100..4,096 keys).
const ANIMATION_KEY_SLACK := 1.23
## What a track costs before its first key: the track record and its path
## (measured 196-204 B with a short bone path).
const ANIMATION_TRACK_BYTES := 200

## Estimated CPU bytes of `animation`'s tracks and keys (see the constants
## above). Reads only key counts and track types: never a key.
static func animation_bytes(animation: Animation) -> int:
	if animation == null:
		return 0
	var keys := 0.0
	var tracks := animation.get_track_count()
	for track: int in tracks:
		keys += animation.track_get_key_count(track) \
			* int(ANIMATION_KEY_BYTES.get(animation.track_get_type(track), ANIMATION_DEFAULT_KEY_BYTES))
	return tracks * ANIMATION_TRACK_BYTES + int(keys * ANIMATION_KEY_SLACK)

## `animation_bytes` over every animation of `library`, each distinct
## Animation once (`seen`, instance id -> true, shared across calls).
static func animation_library_bytes(library: AnimationLibrary, seen: Dictionary = {}) -> int:
	if library == null or not _first_sight(library, seen):
		return 0
	var total := 0
	for name: StringName in library.get_animation_list():
		var animation := library.get_animation(name)
		if animation != null and _first_sight(animation, seen):
			total += animation_bytes(animation)
	return total

## The animation bytes of every AnimationMixer (AnimationPlayer) under `root`,
## root included: the libraries a parsed scene keeps. Walks nodes that belong
## to no tree or to the caller's thread only.
static func node_animation_bytes(root: Node, seen: Dictionary = {}) -> int:
	var total := 0
	for node: Node in _subtree(root):
		total += _mixer_bytes(node, seen)
	return total

## What a live node tree holds (a parsed source scene kept by a cache): the
## meshes of its MeshInstance3D and MultiMeshInstance3D nodes with their
## materials and the materials' textures (as `scene_resources` counts them),
## the material overrides of every GeometryInstance3D, and the animation
## libraries of every AnimationMixer, each distinct object once (`seen`).
## Counts only, no references: {"bytes", "mesh_bytes", "texture_bytes",
## "animation_bytes", "meshes", "textures", "skipped_shader_materials"}.
## Safe on a worker for a tree that belongs to no SceneTree (ShaderMaterial
## parameters are skipped there, as in `scene_resources`).
static func node_resources(root: Node, mipmaps := MIPMAPS_UNKNOWN, seen: Dictionary = {}) -> Dictionary:
	var meshes: Array[Mesh] = []
	var textures: Array[Texture2D] = []
	var found := {"bytes": 0, "mesh_bytes": 0, "texture_bytes": 0,
		"meshes": meshes, "textures": textures, "skipped_shader_materials": 0}
	var animation := 0
	for node: Node in _subtree(root):
		animation += _mixer_bytes(node, seen)
		if node is MeshInstance3D:
			var instance := node as MeshInstance3D
			_collect(instance.mesh, found, seen, mipmaps, 0)
			for surface: int in instance.get_surface_override_material_count():
				_collect(instance.get_surface_override_material(surface), found, seen, mipmaps, 0)
		elif node is MultiMeshInstance3D:
			_collect((node as MultiMeshInstance3D).multimesh, found, seen, mipmaps, 0)
		if node is GeometryInstance3D:
			_collect((node as GeometryInstance3D).material_override, found, seen, mipmaps, 0)
			_collect((node as GeometryInstance3D).material_overlay, found, seen, mipmaps, 0)
	return {"bytes": int(found.mesh_bytes) + int(found.texture_bytes) + animation,
		"mesh_bytes": int(found.mesh_bytes), "texture_bytes": int(found.texture_bytes),
		"animation_bytes": animation, "meshes": meshes.size(), "textures": textures.size(),
		"skipped_shader_materials": int(found.skipped_shader_materials)}

static func _mixer_bytes(node: Node, seen: Dictionary) -> int:
	if node is not AnimationMixer:
		return 0
	var mixer := node as AnimationMixer
	var total := 0
	for name: StringName in mixer.get_animation_library_list():
		total += animation_library_bytes(mixer.get_animation_library(name), seen)
	return total

## `root` and every node under it.
static func _subtree(root: Node) -> Array[Node]:
	var nodes: Array[Node] = []
	if root == null:
		return nodes
	nodes.append(root)
	nodes.append_array(root.find_children("*", "", true, false))
	return nodes
