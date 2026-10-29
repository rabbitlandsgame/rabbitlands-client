extends RefCounted
## Opt-in offline road experiment. Nothing in the production loader calls this.
## Load the baker's road-free base GLB first, then call apply after normal map
## material preparation. Failure never restores or renders the original ribbon.

const SCHEMA := "rabbitlands-road-texture-trial-v1"
const MATERIAL := preload("res://src/dev/road_texture_trial/trial_material.gd")
const Ground := preload("res://src/world/look/look_ground.gd")
const Profile := preload("res://src/world/look/look_profile.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const TexturePool := preload("res://src/world/external_texture_pool.gd")
const MaterialOwnership := preload("res://src/world/prepared_material_ownership.gd")
const MAX_PIXELS := 4194304
const MAX_LAYERS := 32
const WALK_LAYER := 8

static func apply(world_root: Node3D, trial_manifest_path: String, variant := "mask") -> Dictionary:
	var result: Dictionary = {"ok": false, "errors": [], "metrics": {
		"variant": variant, "production": false, "representation": "masked_reused_terrain_overlay",
		"original_road_visual_fallback": false, "full_painted_grass_supported": false,
		"road_visual_lift_metres": 0.055, "physical_road_geometry_preserved": true}}
	if variant in ["baseline", "original", "consolidated"]:
		result.ok = true
		result.metrics["no_op"] = true
		return result
	if world_root == null or variant not in ["mask", "mask2", "mask4"]:
		return _error(result, "invalid_world_or_variant")
	if world_root.has_meta(&"road_texture_trial"):
		return _error(result, "trial_already_installed")
	if not Profile.enabled():
		return _error(result, "trial_requires_the_current_painted_ground_look")
	if Profile.full_painted() and Graphics.decorative_grass:
		return _error(result, "full_painted_grass_requires_a_cpu_mask_adapter")
	var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(trial_manifest_path))
	if not document is Dictionary or str(document.get("schema", "")) != SCHEMA:
		return _error(result, "invalid_trial_manifest")
	var chunks: Array[Dictionary] = []
	if document.get("chunks") is Array:
		for relative: Variant in document.chunks:
			var child_path: String = _path(trial_manifest_path.get_base_dir(), str(relative))
			var child: Variant = JSON.parse_string(FileAccess.get_file_as_string(child_path))
			if not child is Dictionary or str(child.get("schema", "")) != SCHEMA:
				return _error(result, "invalid_trial_chunk: " + child_path)
			child["_directory"] = child_path.get_base_dir()
			chunks.append(child)
	else:
		document["_directory"] = trial_manifest_path.get_base_dir()
		chunks.append(document)
	var prepared: Array[Dictionary] = []
	var started: int = Time.get_ticks_usec()
	for chunk: Dictionary in chunks:
		var part: Dictionary = _prepare_chunk(world_root, chunk)
		if not bool(part.get("ok", false)):
			_dispose_prepared(prepared)
			return _error(result, str(part.get("error", "trial_prepare_failed")))
		prepared.append(part)
	# Source validation, texture decoding, shader construction and collision
	# reconstruction above complete before any original placeholder is changed.
	var installed: Array[Dictionary] = []
	var total_layers := 0
	var texture_bytes := 0
	var collider_bytes := 0
	for part: Dictionary in prepared:
		for replacement: Dictionary in part.colliders:
			var placeholder: Node3D = replacement.placeholder
			var compact: MeshInstance3D = replacement.node
			compact.transform = placeholder.transform
			placeholder.replace_by(compact)
			placeholder.free()
		for overlay: Dictionary in part.overlays:
			var terrain: MeshInstance3D = overlay.terrain
			var node: MeshInstance3D = overlay.node
			terrain.get_parent().add_child(node)
			node.transform = terrain.transform
			installed.append(overlay)
			total_layers += 1
		texture_bytes += int(part.texture_bytes)
		collider_bytes += int(part.collider_bytes)
	world_root.set_meta(&"road_texture_trial", {"layers": installed, "chunks": chunks})
	result.ok = true
	result.metrics.merge({"chunks": chunks.size(), "layers": total_layers,
		"field_texture_bytes": texture_bytes, "compact_collision_source_bytes": collider_bytes,
		"apply_usec": Time.get_ticks_usec() - started}, true)
	return result

static func _prepare_chunk(root: Node3D, chunk: Dictionary) -> Dictionary:
	var directory: String = chunk.get("_directory", "")
	var layers: Variant = chunk.get("layers")
	var nodes: Variant = chunk.get("nodes")
	if not layers is Array or layers.is_empty() or layers.size() > MAX_LAYERS or not nodes is Array:
		return {"ok": false, "error": "invalid_layer_or_collider_list"}
	var terrains: Array[MeshInstance3D] = []
	for name: Variant in chunk.get("terrain_node_names", []):
		var matches: Array[Node] = root.find_children(str(name), "MeshInstance3D", true, false)
		if matches.size() != 1 or (matches[0] as MeshInstance3D).mesh == null:
			return {"ok": false, "error": "terrain_not_unique: " + str(name)}
		terrains.append(matches[0] as MeshInstance3D)
	if terrains.is_empty():
		return {"ok": false, "error": "trial_has_no_terrain"}
	var context: Dictionary = _paint_context(root)
	var colliders: Array[Dictionary] = []
	var placeholders: Dictionary = {}
	var compact_by_name: Dictionary = {}
	var collider_bytes := 0
	for row: Variant in nodes:
		if not row is Dictionary:
			return _prepare_error(colliders, [], "invalid_collider_record")
		var node_name: String = str(row.get("road_node_name", ""))
		var matches: Array[Node] = root.find_children(node_name, "Node3D", true, false)
		if matches.size() != 1 or placeholders.has(node_name):
			return _prepare_error(colliders, [], "road_placeholder_not_unique: " + node_name)
		var placeholder := matches[0] as Node3D
		if placeholder is MeshInstance3D and (placeholder as MeshInstance3D).mesh != null:
			return _prepare_error(colliders, [], "original_road_visual_geometry_present: " + node_name)
		var collision_row: Dictionary = row.duplicate(true)
		for layer_value: Variant in layers:
			if layer_value is Dictionary and str(layer_value.get("road_node_name", "")) == node_name:
				collision_row["original_material_name"] = str(layer_value.get("original_material_name", node_name))
				break
		var compact: Dictionary = _collider(directory, collision_row)
		if not bool(compact.get("ok", false)):
			return _prepare_error(colliders, [], str(compact.get("error", "invalid_collision")))
		colliders.append({"placeholder": placeholder, "node": compact.node})
		placeholders[node_name] = placeholder
		compact_by_name[node_name] = compact.node
		collider_bytes += int(compact.bytes)
	var overlays: Array[Dictionary] = []
	var texture_bytes := 0
	var material_cache: Dictionary = {}
	for row: Variant in layers:
		if not row is Dictionary:
			return _prepare_error(colliders, overlays, "invalid_layer")
		var layer: Dictionary = row
		if not _valid_matrix(layer.get("world_matrix")):
			return _prepare_error(colliders, overlays, "invalid_source_node_frame")
		var placeholder: Node3D = placeholders.get(str(layer.get("road_node_name", "")))
		if placeholder == null:
			return _prepare_error(colliders, overlays, "layer_has_no_collider")
		var fields: Dictionary = _fields(directory, layer)
		if not bool(fields.get("ok", false)):
			return _prepare_error(colliders, overlays, str(fields.get("error", "invalid_fields")))
		var rgb_value: Variant = layer.get("source_vertex_rgb", [1, 1, 1])
		if not rgb_value is Array or rgb_value.size() != 3:
			return _prepare_error(colliders, overlays, "invalid_source_vertex_rgb")
		var rgb := Vector3(float(rgb_value[0]), float(rgb_value[1]), float(rgb_value[2]))
		var material_key: String = "%s:%d" % [layer.get("road_node_name", ""), int(layer.get("primitive_index", 0))]
		if not material_cache.has(material_key):
			var source: Dictionary = _source_material(layer)
			if not bool(source.get("ok", false)):
				return _prepare_error(colliders, overlays, str(source.get("error", "invalid_source_material")))
			var original_box: AABB = (compact_by_name[str(layer.road_node_name)] as MeshInstance3D).get_aabb()
			var original_area := Rect2(original_box.position.x, original_box.position.z,
				original_box.size.x, original_box.size.z)
			var painted := Ground.painted_for(source.material, Ground.Kind.DECK,
				source.mesh, 0, str(chunk.get("region", "suncoil")), context.paving, original_area) as ShaderMaterial
			if painted == null:
				return _prepare_error(colliders, overlays, "road_paint_not_supported")
			painted.set_shader_parameter(&"look_sun_heading", context.sun_heading)
			var derived: Dictionary = MATERIAL.build(painted)
			if not bool(derived.get("ok", false)):
				return _prepare_error(colliders, overlays, str(derived.get("error", "shader_contract")))
			material_cache[material_key] = derived.material
		var template: ShaderMaterial = material_cache[material_key]
		var frame: Transform3D = _matrix(layer.get("world_matrix", []))
		var source_to_runtime: Transform3D = placeholder.global_transform * frame.affine_inverse()
		for terrain: MeshInstance3D in terrains:
			var material := template.duplicate() as ShaderMaterial
			var mesh_to_mask: Transform3D = source_to_runtime.affine_inverse() * terrain.global_transform
			material.set_shader_parameter(&"trial_mesh_to_mask", mesh_to_mask)
			material.set_shader_parameter(&"trial_vertex_lift", mesh_to_mask.basis.inverse() *
				Vector3(0.0, float(chunk.get("road_visual_lift_metres", 0.055)), 0.0))
			material.set_shader_parameter(&"trial_mask_origin", fields.origin)
			material.set_shader_parameter(&"trial_mask_extent", fields.extent)
			material.set_shader_parameter(&"trial_coverage", fields.coverage)
			material.set_shader_parameter(&"trial_uv_field", fields.uv)
			material.set_shader_parameter(&"trial_vertex_rgb", rgb)
			material.render_priority = clampi(template.render_priority + int(layer.get("draw_order", 0)), -128, 127)
			var overlay := MeshInstance3D.new()
			overlay.name = "RoadTextureTrial_%s_%d_%d" % [layer.get("road_node_name", "road"),
				int(layer.get("primitive_index", 0)), int(layer.get("sheet_index", 0))]
			overlay.mesh = terrain.mesh
			overlay.material_override = material
			overlay.layers = terrain.layers
			# Match the source glTF MeshInstance3D default. The derived production
			# shader, including its alpha mode, remains responsible for shadow passes.
			overlay.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			overlay.extra_cull_margin = 0.1
			overlay.set_meta(&"road_texture_trial_visual", true)
			MaterialOwnership.attach(overlay)
			overlays.append({"terrain": terrain, "node": overlay, "grid": layer.grid,
				"coverage_image": fields.coverage_image, "road_node_name": layer.road_node_name})
		texture_bytes += int(fields.bytes)
	return {"ok": true, "colliders": colliders, "overlays": overlays,
		"texture_bytes": texture_bytes, "collider_bytes": collider_bytes}

static func _fields(directory: String, layer: Dictionary) -> Dictionary:
	var grid: Variant = layer.get("grid")
	var mips: Variant = layer.get("mips")
	if not grid is Dictionary or not mips is Array or mips.is_empty() \
			or str(layer.get("uv_format", "")) != "RG32F" or str(layer.get("uv_byte_order", "")) != "little":
		return {"ok": false, "error": "invalid_field_layout"}
	var width: int = int(grid.get("width", 0))
	var height: int = int(grid.get("height", 0))
	var ppm: float = float(grid.get("pixels_per_metre", 0.0))
	var origin_value: Variant = grid.get("origin_xz")
	if width < 1 or height < 1 or width * height > MAX_PIXELS or ppm <= 0.0 \
			or not is_finite(ppm) or not origin_value is Array or origin_value.size() != 2 \
			or str(grid.get("axis_order", "")) != "row_increasing_z,column_increasing_x" \
			or not Vector2(float(origin_value[0]), float(origin_value[1])).is_finite():
		return {"ok": false, "error": "field_bounds"}
	var coverage_bytes := PackedByteArray()
	var base_image: Image
	var expected_uv := 0
	var w: int = width
	var h: int = height
	for level: int in mips.size():
		var mip: Variant = mips[level]
		if not mip is Dictionary or int(mip.get("level", -1)) != level \
				or int(mip.get("width", 0)) != w or int(mip.get("height", 0)) != h \
				or int(mip.get("uv_offset_bytes", -1)) != expected_uv or int(mip.get("uv_bytes", -1)) != w * h * 8:
			return {"ok": false, "error": "field_mip_layout"}
		var image := Image.new()
		var coverage_path: String = _path(directory, str(mip.get("coverage", "")))
		if str(mip.get("coverage_sha256", "")).length() != 64 or \
				FileAccess.get_sha256(coverage_path) != str(mip.coverage_sha256):
			return {"ok": false, "error": "field_coverage_hash"}
		var error: Error = image.load(coverage_path)
		if error != OK or image.get_width() != w or image.get_height() != h:
			return {"ok": false, "error": "field_coverage_decode"}
		image.convert(Image.FORMAT_R8)
		if str(mip.get("coverage_decoded_sha256", "")).length() != 64 or \
				MATERIAL._sha(image.get_data()) != str(mip.coverage_decoded_sha256):
			return {"ok": false, "error": "field_coverage_decoded_hash"}
		if level == 0:
			base_image = image
		coverage_bytes.append_array(image.get_data())
		expected_uv += w * h * 8
		if w == 1 and h == 1 and level != mips.size() - 1:
			return {"ok": false, "error": "field_extra_mips"}
		w = maxi(1, w >> 1)
		h = maxi(1, h >> 1)
	if int(mips[-1].width) != 1 or int(mips[-1].height) != 1:
		return {"ok": false, "error": "field_byte_count_or_missing_mips"}
	var uv_path: String = _path(directory, str(layer.get("uv_file", "")))
	var stored_uv: PackedByteArray = FileAccess.get_file_as_bytes(uv_path)
	if str(layer.get("uv_file_sha256", "")).length() != 64 or \
			MATERIAL._sha(stored_uv) != str(layer.uv_file_sha256):
		return {"ok": false, "error": "field_uv_stored_hash"}
	var uv_bytes: PackedByteArray
	match str(layer.get("uv_compression", "none")):
		"none":
			uv_bytes = stored_uv
		"zstd":
			if int(layer.get("uv_uncompressed_bytes", -1)) != expected_uv:
				return {"ok": false, "error": "field_uv_decoded_size"}
			uv_bytes = stored_uv.decompress(expected_uv, FileAccess.COMPRESSION_ZSTD)
		_:
			return {"ok": false, "error": "field_uv_compression"}
	if uv_bytes.size() != expected_uv or str(layer.get("uv_sha256", "")).length() != 64 \
			or MATERIAL._sha(uv_bytes) != str(layer.uv_sha256):
		return {"ok": false, "error": "field_uv_decoded_hash_or_size"}
	# A malformed UV cannot be allowed to produce undefined texture gradients.
	for value: float in uv_bytes.to_float32_array():
		if not is_finite(value):
			return {"ok": false, "error": "field_uv_nonfinite"}
	var coverage := Image.create_from_data(width, height, mips.size() > 1, Image.FORMAT_R8, coverage_bytes)
	var uv := Image.create_from_data(width, height, mips.size() > 1, Image.FORMAT_RGF, uv_bytes)
	if coverage == null or uv == null:
		return {"ok": false, "error": "field_image_creation"}
	return {"ok": true, "coverage": ImageTexture.create_from_image(coverage),
		"uv": ImageTexture.create_from_image(uv), "coverage_image": base_image,
		"origin": Vector2(float(origin_value[0]), float(origin_value[1])),
		"extent": Vector2(width / ppm, height / ppm), "bytes": coverage_bytes.size() + uv_bytes.size()}

static func _collider(directory: String, row: Dictionary) -> Dictionary:
	var record: Variant = row.get("collision")
	if not record is Dictionary or str(record.get("space", "")) != "original_node_local" \
			or not bool(record.get("expanded_triangle_positions_byte_identical", false)):
		return {"ok": false, "error": "collision_contract"}
	var positions: PackedByteArray = FileAccess.get_file_as_bytes(_path(directory, str(record.get("positions", ""))))
	var indices: PackedByteArray = FileAccess.get_file_as_bytes(_path(directory, str(record.get("indices", ""))))
	var count: int = int(record.get("vertex_count", 0))
	var index_count: int = int(record.get("index_count", 0))
	var component: int = int(record.get("index_component_type", 0))
	var index_width: int = 2 if component == 5123 else 4 if component == 5125 else 0
	if count < 3 or index_count < 3 or index_count % 3 != 0 or index_width == 0 \
			or positions.size() != count * 12 or indices.size() != index_count * index_width \
			or MATERIAL._sha(positions) != str(record.get("positions_sha256", "")) \
			or MATERIAL._sha(indices) != str(record.get("indices_sha256", "")):
		return {"ok": false, "error": "collision_hash_or_layout"}
	var floats: PackedFloat32Array = positions.to_float32_array()
	var vertices := PackedVector3Array()
	vertices.resize(count)
	for i: int in count:
		vertices[i] = Vector3(floats[i * 3], floats[i * 3 + 1], floats[i * 3 + 2])
	var faces := PackedVector3Array()
	var element_indices := PackedInt32Array()
	faces.resize(index_count)
	element_indices.resize(index_count)
	for i: int in index_count:
		var index: int = indices.decode_u16(i * 2) if index_width == 2 else indices.decode_u32(i * 4)
		if index < 0 or index >= count:
			return {"ok": false, "error": "collision_index_bounds"}
		element_indices[i] = index
		faces[i] = vertices[index]
	var raw_faces_sha: String = MATERIAL._sha(faces.to_byte_array())
	if raw_faces_sha != str(record.get("expanded_triangle_positions_sha256", "")):
		return {"ok": false, "error": "collision_expanded_geometry_changed"}
	# The proof above is in glTF source order. Godot's glTF importer exchanges
	# triangle corners 1 and 2 before producing its Mesh/ImporterMesh. Concave
	# collision must receive that SAME front-face order, not the raw glTF order.
	# Keep backface collision at its production default instead of hiding this
	# conversion error by making a one-sided road double-sided.
	for triangle: int in range(0, index_count, 3):
		var old_index: int = element_indices[triangle + 1]
		element_indices[triangle + 1] = element_indices[triangle + 2]
		element_indices[triangle + 2] = old_index
		var old_corner: Vector3 = faces[triangle + 1]
		faces[triangle + 1] = faces[triangle + 2]
		faces[triangle + 2] = old_corner
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = element_indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var name: String = str(row.get("road_node_name", ""))
	var material := StandardMaterial3D.new()
	material.resource_name = str(row.get("original_material_name", name))
	mesh.surface_set_material(0, material)
	var carrier := MeshInstance3D.new()
	carrier.name = name
	carrier.mesh = mesh
	carrier.visible = false
	carrier.set_meta(&"road_texture_trial_collision_only", true)
	carrier.set_meta(&"road_texture_trial_gltf_faces_sha256", raw_faces_sha)
	carrier.set_meta(&"road_texture_trial_godot_faces_sha256", MATERIAL._sha(faces.to_byte_array()))
	var body := StaticBody3D.new()
	body.name = name + "_WalkSurfaceCollision"
	body.collision_layer = WALK_LAYER
	body.collision_mask = 1 # WorldLoader._create_static_collision keeps this default.
	var shape := CollisionShape3D.new()
	var concave := ConcavePolygonShape3D.new()
	concave.set_faces(faces)
	shape.shape = concave
	body.add_child(shape)
	carrier.add_child(body)
	MaterialOwnership.attach(carrier)
	return {"ok": true, "node": carrier, "bytes": positions.size() + indices.size()}

static func _source_material(layer: Dictionary) -> Dictionary:
	var value: Variant = layer.get("material_document")
	if not value is Dictionary or not value.get("materials") is Array or value.materials.size() != 1:
		return {"ok": false, "error": "material_document_contract"}
	if not Quantization.ensure_registered() or not Vram.ensure_registered():
		return {"ok": false, "error": "gltf_extension_initialization"}
	var source: Dictionary = value.duplicate(true)
	_prune_material_images(source)
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var resources: Dictionary = layer.get("externalResources", {})
	var source_directory: String = str(layer.get("source_directory", "")).replace("\\", "/").trim_suffix("/") + "/"
	for image: Dictionary in source.get("images", []):
		var uri: String = str(image.get("uri", ""))
		var expected: String = str(resources.get(uri, ""))
		if uri.is_empty() or expected.length() != 64 or \
				FileAccess.get_sha256(source_directory.path_join(uri).simplify_path()) != expected:
			return {"ok": false, "error": "material_source_image_hash: " + uri}
	state.set_additional_data(Vram.PLAN_KEY, Vram.plan_for({"externalResources": resources}))
	# Godot resolves an unterminated base path like a file path. Keep the
	# directory slash, otherwise every source URI loses one path component.
	var error: Error = document.append_from_buffer(_material_glb(source), source_directory, state)
	if error != OK or state.get_meshes().size() != 1:
		return {"ok": false, "error": "material_gltf_parse: " + error_string(error)}
	TexturePool.share(state, resources)
	# Resolve the same scene-level material copies the production loader sees.
	# In particular, do not invent a vertex-albedo flag: painted alpha coverage
	# uses the actual colour attribute independently of that flag.
	var generated: Node = document.generate_scene(state)
	if generated == null:
		return {"ok": false, "error": "material_gltf_scene"}
	var instance := generated as MeshInstance3D
	if instance == null:
		var matches: Array[Node] = generated.find_children("*", "MeshInstance3D", true, false)
		if matches.size() == 1:
			instance = matches[0] as MeshInstance3D
	if instance == null or instance.mesh == null:
		generated.free()
		return {"ok": false, "error": "material_gltf_instance"}
	var mesh: Mesh = instance.mesh
	var material := instance.get_active_material(0) as BaseMaterial3D
	generated.free()
	if material == null:
		return {"ok": false, "error": "material_gltf_not_pbr"}
	var authored: Dictionary = source.materials[0]
	var pbr: Dictionary = authored.get("pbrMetallicRoughness", {})
	if pbr.has("baseColorTexture") and material.albedo_texture == null:
		return {"ok": false, "error": "material_gltf_lost_base_texture"}
	if authored.has("normalTexture") and (not material.normal_enabled or material.normal_texture == null):
		return {"ok": false, "error": "material_gltf_lost_normal_texture"}
	return {"ok": true, "material": material, "mesh": mesh}

static func _prune_material_images(document: Dictionary) -> void:
	var used: Dictionary = {}
	_collect_texture_indices(document.materials[0], used)
	var texture_indices: Array = used.keys()
	texture_indices.sort()
	var textures: Array = []
	var images: Array = []
	var image_map: Dictionary = {}
	var texture_map: Dictionary = {}
	for old_index: Variant in texture_indices:
		texture_map[old_index] = textures.size()
		var texture: Dictionary = document.textures[int(old_index)].duplicate(true)
		if texture.has("source"):
			texture.source = _image_index(int(texture.source), document.images, images, image_map)
		for extension: Variant in texture.get("extensions", {}).values():
			if extension is Dictionary and extension.has("source"):
				extension.source = _image_index(int(extension.source), document.images, images, image_map)
		textures.append(texture)
	_remap_texture_indices(document.materials[0], texture_map)
	document.textures = textures
	document.images = images

static func _collect_texture_indices(value: Variant, found: Dictionary) -> void:
	if value is Dictionary:
		for key: Variant in value:
			var child: Variant = value[key]
			if str(key).ends_with("Texture") and child is Dictionary and child.has("index"):
				found[int(child.index)] = true
			else:
				_collect_texture_indices(child, found)
	elif value is Array:
		for child: Variant in value:
			_collect_texture_indices(child, found)

static func _remap_texture_indices(value: Variant, remap: Dictionary) -> void:
	if value is Dictionary:
		for key: Variant in value:
			var child: Variant = value[key]
			if str(key).ends_with("Texture") and child is Dictionary and child.has("index"):
				child.index = remap[int(child.index)]
			else:
				_remap_texture_indices(child, remap)
	elif value is Array:
		for child: Variant in value:
			_remap_texture_indices(child, remap)

static func _image_index(old: int, source: Array, output: Array, remap: Dictionary) -> int:
	if not remap.has(old):
		remap[old] = output.size()
		output.append(source[old].duplicate(true))
	return int(remap[old])

static func _material_glb(document: Dictionary) -> PackedByteArray:
	var packed := PackedByteArray()
	var views: Array = []
	var accessors: Array = []
	var values: Array[PackedFloat32Array] = [
		PackedFloat32Array([0, 0, 0, 0, 0, 1, 1, 0, 0]),
		PackedFloat32Array([0, 1, 0, 0, 1, 0, 0, 1, 0]),
		PackedFloat32Array([0, 0, 0, 1, 1, 0]),
		PackedFloat32Array([1, 0, 0, -1, 1, 0, 0, -1, 1, 0, 0, -1]),
		PackedFloat32Array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
	]
	var types: Array[String] = ["VEC3", "VEC3", "VEC2", "VEC4", "VEC4"]
	for i: int in values.size():
		var bytes: PackedByteArray = values[i].to_byte_array()
		views.append({"buffer": 0, "byteOffset": packed.size(), "byteLength": bytes.size(), "target": 34962})
		accessors.append({"bufferView": i, "componentType": 5126, "count": 3, "type": types[i]})
		packed.append_array(bytes)
	document.merge({"scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
		"meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1,
			"TEXCOORD_0": 2, "TANGENT": 3, "COLOR_0": 4}, "material": 0}]}],
		"buffers": [{"byteLength": packed.size()}], "bufferViews": views, "accessors": accessors}, true)
	var json: PackedByteArray = JSON.stringify(document).to_utf8_buffer()
	while json.size() % 4 != 0:
		json.append(32)
	var bytes := PackedByteArray()
	bytes.resize(20)
	bytes.encode_u32(0, 0x46546c67)
	bytes.encode_u32(4, 2)
	bytes.encode_u32(8, 28 + json.size() + packed.size())
	bytes.encode_u32(12, json.size())
	bytes.encode_u32(16, 0x4e4f534a)
	bytes.append_array(json)
	var binary_header := PackedByteArray()
	binary_header.resize(8)
	binary_header.encode_u32(0, packed.size())
	binary_header.encode_u32(4, 0x004e4942)
	bytes.append_array(binary_header)
	bytes.append_array(packed)
	return bytes

static func _paint_context(root: Node3D) -> Dictionary:
	var proxies: Array[MeshInstance3D] = []
	var sun_heading := Vector2.ZERO
	for value: Node in root.find_children("*", "MeshInstance3D", true, false):
		var node := value as MeshInstance3D
		if node.mesh == null or Ground.kind_of(str(node.name)) == Ground.Kind.NONE:
			continue
		var proxy := MeshInstance3D.new()
		proxy.name = node.name
		proxy.mesh = node.mesh
		for surface: int in node.mesh.get_surface_count():
			var active: Material = node.get_active_material(surface)
			if active is ShaderMaterial:
				var heading: Variant = (active as ShaderMaterial).get_shader_parameter(&"look_sun_heading")
				if heading is Vector2:
					sun_heading = heading
			var source: Material = active.get_meta(Profile.SOURCE_META, active) if active != null else null
			proxy.set_surface_override_material(surface, source)
		proxies.append(proxy)
	var paving: PackedVector4Array = Ground.paving_rects(proxies)
	for proxy: MeshInstance3D in proxies:
		proxy.free()
	return {"paving": paving, "sun_heading": sun_heading}

static func _matrix(value: Variant) -> Transform3D:
	if not value is Array or value.size() != 16:
		return Transform3D.IDENTITY
	return Transform3D(Basis(Vector3(value[0], value[1], value[2]),
		Vector3(value[4], value[5], value[6]), Vector3(value[8], value[9], value[10])),
		Vector3(value[12], value[13], value[14]))

static func _valid_matrix(value: Variant) -> bool:
	if not value is Array or value.size() != 16:
		return false
	for component: Variant in value:
		if not (component is int or component is float) or not is_finite(float(component)):
			return false
	return absf(_matrix(value).basis.determinant()) > 0.000000001 \
		and absf(float(value[3])) < 0.000000001 and absf(float(value[7])) < 0.000000001 \
		and absf(float(value[11])) < 0.000000001 and absf(float(value[15]) - 1.0) < 0.000000001

static func _path(directory: String, relative: String) -> String:
	return directory.path_join(relative).simplify_path() if not relative.is_absolute_path() else relative

static func _error(result: Dictionary, message: String) -> Dictionary:
	result.errors.append(message)
	return result

static func _prepare_error(colliders: Array, overlays: Array, message: String) -> Dictionary:
	_dispose_prepared([{"colliders": colliders, "overlays": overlays}])
	return {"ok": false, "error": message}

static func _dispose_prepared(parts: Array) -> void:
	for part: Dictionary in parts:
		for row: Dictionary in part.get("colliders", []):
			(row.node as Node).free()
		for row: Dictionary in part.get("overlays", []):
			(row.node as Node).free()
