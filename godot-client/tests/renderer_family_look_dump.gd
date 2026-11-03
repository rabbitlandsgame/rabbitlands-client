extends RefCounted
## Everything the look files compute differently by renderer, as plain data,
## for tests/test_renderer_family.gd's golden check: the region accessors
## (`region_value`, `ground_value`, the grass palette, map trims) over every
## region file, the grade an outdoor map and a continent region get, the
## painted ground, decoded water and kept chroma a small world gets in each
## region, the border trims, the screen-space settings at each quality and the
## grass beds' renderer scales. It runs under whichever renderer the process
## reports (or RendererFamily's test override), so a dump taken before a change
## and one taken after can be compared byte for byte (`digest`).
##
## Values are made plain: objects become their class and resource path (a
## shader built at run time, its code's hash), so two processes dump the same
## bytes. Only LookProfile's public names that predate the renderer family are
## used, so the same dump runs on the code before and after it.

const SENTINEL := "<fallback>"
const SCAN_DIRECTORY := "res://src/world/look"
## Where the test world's meshes lie, far from every region border, so the
## painted ground's border slots hold only the neighbours `_borders` names.
const FAR := Vector3(-100000.0, 0.0, -100000.0)
const ENVIRONMENT_PROPERTIES := ["tonemap_mode", "tonemap_exposure", "tonemap_white",
	"tonemap_agx_white", "tonemap_agx_contrast", "background_energy_multiplier",
	"adjustment_enabled", "adjustment_brightness", "adjustment_contrast",
	"adjustment_saturation", "adjustment_color_correction", "ambient_light_color",
	"ambient_light_energy", "ambient_light_sky_contribution", "fog_mode", "fog_density",
	"fog_depth_begin", "fog_depth_end", "fog_depth_curve", "fog_aerial_perspective",
	"fog_sky_affect", "ssao_enabled", "ssao_radius", "ssao_intensity", "ssao_power",
	"ssao_detail", "ssao_light_affect", "ssil_enabled", "ssil_radius", "ssil_intensity",
	"glow_enabled", "glow_intensity", "glow_strength", "glow_bloom", "glow_hdr_threshold",
	"glow_blend_mode"]

static var _parameter_names := PackedStringArray()

## The dump for the renderer in use. `tree_root` holds the test world while it
## is painted (some look code asks for nodes in a tree). The look mode is Full
## painted and the quality HIGH while dumping, and both are restored.
static func dump(tree_root: Node) -> Dictionary:
	var mode := LookProfile.player_mode()
	var quality := LookProfile.player_quality()
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookProfile.reload_regions()
	var ids: Array = Array(LookProfile.region_ids())
	ids.append_array(["", "no_such_region"])
	var result := {
		"scalars": _scalars(),
		"screen_space": _screen_space(),
		"borders": _borders(LookProfile.region_ids()),
		"grass_beds": _grass_beds(),
		"regions": {},
	}
	for id: String in ids:
		result.regions[id] = _region(id, tree_root)
	LookProfile.set_player_quality(quality)
	LookProfile.set_player_mode(mode)
	LookProfile.reload_regions()
	return result

## SHA-256 of `value`'s binary form: equal digests mean byte-identical values.
static func digest(value: Variant) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(var_to_bytes(value))
	return hashing.finish().hex_encode()

## One digest per top-level part and per region, so a mismatch names its place.
static func digests(dumped: Dictionary) -> Dictionary:
	var out := {}
	for key: String in ["scalars", "screen_space", "borders", "grass_beds"]:
		out[key] = digest(dumped[key])
	var regions := {}
	for id: String in dumped.regions:
		regions[id] = digest(dumped.regions[id])
	out["regions"] = regions
	return out

## SHA-256 over every region file's name and bytes: what the dump reads besides
## the code. A golden taken from other files cannot be compared.
static func inputs_digest() -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	for id: String in LookProfile.region_ids():
		hashing.update(id.to_utf8_buffer())
		hashing.update(FileAccess.get_file_as_bytes(LookProfile.region_path(id)))
	return hashing.finish().hex_encode()

static func _scalars() -> Dictionary:
	var saturations := []
	for declared: float in [0.0, 0.8, 1.0, 1.3, 2.0]:
		saturations.append(LookProfile.saturation(declared))
	var mottle := []
	for xz: Vector2 in [Vector2.ZERO, Vector2(12.5, -7.25), Vector2(300.1, 41.7)]:
		mottle.append(LookGrassBeds.ground_mottle(xz))
	return {
		"forward_plus": LookProfile.forward_plus(),
		"screen_space_effects": LookProfile.screen_space_effects(),
		"renderer_exposure": LookProfile.renderer_exposure(),
		"sun_warmth": LookProfile.sun_warmth(),
		"saturation": saturations,
		"ground_mottle": mottle,
	}

static func _screen_space() -> Dictionary:
	var out := {}
	var quality := LookProfile.player_quality()
	for level: int in LookProfile.QUALITY_NAMES.size():
		LookProfile.set_player_quality(level)
		var environment := Environment.new()
		LookGrade._grade_screen_space(environment)
		out[LookProfile.quality_name(level)] = _environment(environment)
	LookProfile.set_player_quality(quality)
	return out

static func _borders(ids: PackedStringArray) -> Array:
	var out := []
	var size := LookProfile.BORDER_NEIGHBOURS_MAX
	var start := 0
	while start < ids.size() + 1:
		var neighbours := PackedStringArray()
		for index: int in range(start, mini(start + size, ids.size())):
			neighbours.append(ids[index])
		if start + size > ids.size():
			neighbours.append("no_such_region")
		var segments := PackedVector4Array()
		var slots := PackedFloat32Array()
		for slot: int in neighbours.size():
			segments.append(Vector4(slot, 0.0, slot + 1.0, 1.0))
			slots.append(float(slot))
		var painted := ShaderMaterial.new()
		painted.shader = LookGround.SHADER_OPAQUE
		LookGround._set_border(painted, {"segments": segments, "slots": slots,
			"neighbours": neighbours})
		out.append(_material(painted))
		start += size
	return out

static func _grass_beds() -> Dictionary:
	var beds := LookGrassBeds.new()
	var material: ShaderMaterial = beds._material
	var out := {"material": _material(material), "slots": {}}
	# Slot 0 is the default palette; fill the others, never more (a full set
	# warns and grows the default).
	for id: String in LookProfile.region_ids():
		if out.slots.size() + 1 >= LookProfile.GRASS_PALETTE_SLOTS:
			break
		if not LookProfile.grass_palette(id).is_empty():
			out.slots[id] = beds._slot(id)
	out["material_after_slots"] = _material(material)
	beds.free()
	return out

static func _region(id: String, tree_root: Node) -> Dictionary:
	var values := {}
	for section: String in LookProfile.REGION_SECTIONS:
		var keys := {}
		for key: String in LookProfile.REGION_SECTIONS[section]:
			keys[key] = _plain(LookProfile.region_value(id, section, key, SENTINEL))
		values["region_value." + section] = keys
	var ground := {}
	for key: String in LookProfile.REGION_SECTIONS.ground:
		ground[key] = _plain(LookProfile.ground_value(id, key, SENTINEL))
	values["ground_value"] = ground
	var grass := {}
	for key: String in LookProfile.REGION_SECTIONS.grass:
		grass[key] = _plain(LookProfile._grass_value(id, key, SENTINEL))
	values["grass_value"] = grass
	values["grass_palette"] = _plain(LookProfile.grass_palette(id))
	var trims := {}
	for key: String in ["exposure", "saturation", "background"]:
		trims[key] = [LookProfile.map_trim(id, key), LookProfile.map_trim(id, key, true)]
	values["map_trim"] = trims
	values["sky_fallback"] = _plain(LookProfile.sky_fallback(id))
	values["sky_painted"] = LookProfile.sky_painted(id)
	return {"values": values, "grade": _grade(id, false), "grade_continent": _grade(id, true),
		"world": _world(id, tree_root)}

## The environment and sun an outdoor map (`continent`: a continent region)
## in `id` is graded to.
static func _grade(id: String, continent: bool) -> Dictionary:
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": id}, "environment": {
		"sun": {"enabled": true, "energy": 1.1, "color": [1.0, 0.94, 0.83]},
		"fog": {"enabled": true, "density": 0.0007}, "saturation": 1.3}}
	if continent:
		manifest.data["continentGeography"] = {"geometryMode": "continent-chunks-v1"}
	var world_environment := WorldEnvironment.new()
	var environment := Environment.new()
	environment.fog_enabled = true
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_color = Color(0.6, 0.67, 0.72)
	environment.ambient_light_energy = 0.6
	world_environment.environment = environment
	var sun := DirectionalLight3D.new()
	sun.light_color = Color(1.0, 0.94, 0.83)
	sun.light_energy = 1.1
	var graded := LookGrade.apply(manifest, world_environment, sun)
	var out := {"graded": graded, "environment": _environment(environment),
		"sun": [sun.light_color, sun.light_energy]}
	sun.free()
	world_environment.free()
	return out

## A small world painted, its water decoded and its signature props kept in
## region `id`: every surface's material afterwards.
static func _world(id: String, tree_root: Node) -> Array:
	var world := Node3D.new()
	world.name = "RendererDumpWorld"
	tree_root.add_child(world)
	var terrain := StandardMaterial3D.new()
	terrain.vertex_color_use_as_albedo = true
	var biome := ShaderMaterial.new()
	biome.shader = load(LookGround.BIOME_SHADER_PATH) as Shader
	biome.set_shader_parameter(&"mask_size", 66.0)
	biome.set_shader_parameter(&"base_tint_0", Color("b3eb80"))
	var soil := _patch(Color("ffa85c"))
	var meadow := _patch(Color("6f9a3c"))
	var stone := _patch(Color("b8b2a6"))
	var kept_words := LookProfile.keep_patches(id)
	var kept := _patch(Color("8c6f9a"))
	kept.resource_name = "patch_" + str(kept_words[0]) if not kept_words.is_empty() else "patch_plain"
	var deck := _patch(Color("997a4f"))
	var water := StandardMaterial3D.new()
	water.resource_name = "authored_test_river_water"
	_mesh(world, "Terrain_dump_4_5", terrain)
	_mesh(world, "AuthoredGround_dumpBase_4_5", null).set_surface_override_material(0, biome)
	_mesh(world, "AuthoredGround_dump_ground-01_dump_4_5", soil)
	_mesh(world, "AuthoredGround_dump_ground-02_dump_4_5", meadow)
	_mesh(world, "AuthoredGround_dump_ground-03_dump_4_5", stone)
	_mesh(world, "AuthoredGround_dump_ground-04_dump_4_5", kept)
	_mesh(world, "Walk_dump_highway-dump-south_dump_4_5", deck)
	_mesh(world, "Water_dump_4_5", water)
	var sea := ShaderMaterial.new()
	sea.shader = load(LookGround.CONTINENT_WATER_PATH) as Shader
	_mesh(world, "Water_dump_4_6", null).set_surface_override_material(0, sea)
	var table: Variant = LookProfile.region_section(id, "water").get("decode_albedo")
	if table is Dictionary:
		var paths: Array = (table as Dictionary).keys()
		paths.sort()
		for path: String in paths:
			var decoded := ShaderMaterial.new()
			decoded.shader = load(path) as Shader
			_mesh(world, "Scenery_sea_dump", null).material_override = decoded
	var keep := LookProfile.keep_words(id)
	var prop := StandardMaterial3D.new()
	prop.albedo_color = Color("6a8f7c")
	prop.resource_name = "prop_" + str(keep[0]) if not keep.is_empty() else "prop_plain"
	_mesh(world, "Prop_dump_1", prop, false)
	var counts := [LookGround.paint(world, id, Vector2(0.3, 0.7)),
		LookGround.decode_continent_sea(world, id), LookGround.decode_inland_water(world, id),
		LookGround.decode_water(world, id), LookFoliage.keep_chroma(world, id)]
	var out := [counts]
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		out.append([String(mesh_instance.name), _material(mesh_instance.material_override),
			_material(mesh_instance.get_surface_override_material(0))])
	tree_root.remove_child(world)
	world.free()
	return out

static func _patch(colour: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = colour
	return material

static func _mesh(parent: Node, node_name: String, material: Material,
		coloured := true) -> MeshInstance3D:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	for corner: Vector3 in [Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 0, 1)]:
		if coloured:
			tool.set_color(Color(1, 1, 1, 0.5))
		tool.set_normal(Vector3.UP)
		tool.set_uv(Vector2(corner.x, corner.z))
		tool.add_vertex(corner + FAR)
	var mesh := tool.commit()
	if material != null:
		mesh.surface_set_material(0, material)
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = node_name
	mesh_instance.mesh = mesh
	parent.add_child(mesh_instance)
	return mesh_instance

static func _environment(environment: Environment) -> Dictionary:
	var out := {}
	for property: String in ENVIRONMENT_PROPERTIES:
		out[property] = _plain(environment.get(property))
	return out

static func _material(material: Material) -> Variant:
	if material == null:
		return null
	var out := {"class": material.get_class(), "name": material.resource_name}
	if material is ShaderMaterial:
		var shader_material := material as ShaderMaterial
		out["shader"] = _plain(shader_material.shader)
		var parameters := {}
		for name: String in _names():
			var value: Variant = shader_material.get_shader_parameter(name)
			if value != null:
				parameters[name] = _plain(value)
		out["parameters"] = parameters
	elif material is BaseMaterial3D:
		var standard := material as BaseMaterial3D
		out["albedo"] = standard.albedo_color
		out["emission"] = standard.emission
		out["transparency"] = standard.transparency
	return out

## Every shader parameter the look files set, read off their source, so a
## parameter that is set is dumped whether or not the dummy renderer lists it.
static func _names() -> PackedStringArray:
	if _parameter_names.is_empty():
		var pattern := RegEx.create_from_string("set_shader_parameter\\(\\s*&?\"([A-Za-z0-9_]+)\"")
		var found := {}
		for file: String in DirAccess.get_files_at(SCAN_DIRECTORY):
			if file.get_extension() != "gd":
				continue
			var source := FileAccess.get_file_as_string(SCAN_DIRECTORY.path_join(file))
			for hit: RegExMatch in pattern.search_all(source):
				found[hit.get_string(1)] = true
		for name: String in ["mask_size", "base_tint_0"]:
			found[name] = true
		var names := PackedStringArray(found.keys())
		names.sort()
		_parameter_names = names
	return _parameter_names

static func _plain(value: Variant) -> Variant:
	match typeof(value):
		TYPE_OBJECT:
			var object: Object = value
			if object == null:
				return null
			if object is Shader:
				var shader := object as Shader
				return "Shader:" + (shader.resource_path if not shader.resource_path.is_empty()
					else "code#" + shader.code.sha256_text())
			if object is Texture2D:
				var texture := object as Texture2D
				return "%s:%s:%dx%d" % [texture.get_class(), texture.resource_path,
					texture.get_width(), texture.get_height()]
			if object is Resource:
				return "%s:%s" % [object.get_class(), (object as Resource).resource_path]
			return object.get_class()
		TYPE_ARRAY:
			var out := []
			for item: Variant in value:
				out.append(_plain(item))
			return out
		TYPE_DICTIONARY:
			var out := {}
			for key: Variant in value:
				out[_plain(key)] = _plain(value[key])
			return out
		TYPE_STRING_NAME:
			return String(value)
	return value
