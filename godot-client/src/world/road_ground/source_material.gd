extends RefCounted
## Parse portable road PBR documents through the normal glTF texture pipeline.
## GLTFState material Resources need no generated scene or dummy road mesh.

const Vram := preload("res://src/world/vram_textures.gd")

static func read(style: Dictionary, directory: String, image_policies: Dictionary = {}) -> Dictionary:
	var source: Variant = style.get("material_document")
	var resources: Variant = style.get("externalResources")
	if not source is Dictionary or not source.get("materials") is Array or source.materials.size() != 1 \
			or not resources is Dictionary or style.get("vertex_rgb") != [1.0, 1.0, 1.0]:
		return {"ok": false, "error": "road_style_material_contract"}
	var authored: Dictionary = source.materials[0]
	if str(authored.get("alphaMode", "OPAQUE")) != "BLEND" or not bool(authored.get("doubleSided", false)) \
			or not authored.get("extensions", {}).is_empty() or authored.has("emissiveTexture") \
			or authored.get("emissiveFactor", [0.0, 0.0, 0.0]) != [0.0, 0.0, 0.0]:
		return {"ok": false, "error": "road_style_unsupported_pbr_features"}
	if not Vram.ensure_registered():
		return {"ok": false, "error": "road_texture_extension_registration"}
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	state.set_additional_data(Vram.PLAN_KEY, Vram.plan_for({"externalResources": resources,
		Vram.POLICY_COLLECTION: image_policies}))
	var input: Dictionary = source.duplicate(true)
	input["asset"] = {"version": "2.0"}
	# A material-only glTF is valid: image extraction and prepared texture jobs
	# happen during parsing, without constructing scene Nodes.
	var bytes: PackedByteArray = _glb(input)
	var error: Error = document.append_from_buffer(bytes, directory.trim_suffix("/") + "/", state)
	if error != OK or state.get_materials().size() != 1:
		return {"ok": false, "error": "road_material_parse: " + error_string(error)}
	var material := state.get_materials()[0] as BaseMaterial3D
	if material == null or material.albedo_texture == null or not material.normal_enabled or material.normal_texture == null:
		return {"ok": false, "error": "road_material_source_texture_missing"}
	var names: Array = style.get("original_material_names", [])
	material.resource_name = str(names[0]) if not names.is_empty() else "authored_road"
	return {"ok": true, "material": material, "state": state, "resources": resources}

static func _glb(document: Dictionary) -> PackedByteArray:
	# The engine's in-memory GLB reader expects a BIN chunk even for a
	# material-only document. A four-byte unused buffer avoids short reads.
	document["buffers"] = [{"byteLength": 4}]
	var json: PackedByteArray = JSON.stringify(document).to_utf8_buffer()
	while json.size() % 4 != 0:
		json.append(32)
	var bytes := PackedByteArray()
	bytes.resize(20)
	bytes.encode_u32(0, 0x46546c67)
	bytes.encode_u32(4, 2)
	bytes.encode_u32(8, 32 + json.size())
	bytes.encode_u32(12, json.size())
	bytes.encode_u32(16, 0x4e4f534a)
	bytes.append_array(json)
	var binary := PackedByteArray()
	binary.resize(12)
	binary.encode_u32(0, 4)
	binary.encode_u32(4, 0x004e4942)
	bytes.append_array(binary)
	return bytes
