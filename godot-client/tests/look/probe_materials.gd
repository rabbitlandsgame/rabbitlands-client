extends SceneTree
## Look-pass inventory: what a frame-level look layer would have to touch.
##
## Loads Lantern Reach, Four Gates and Amberwood exactly as
## tests/integration/rendered_landscape_survey.gd does - the complete client, a
## local actor at a survey focus, every selected chunk of the active territory
## resident - and writes one JSON file (ELORIA_INVENTORY_OUT, else
## ELORIA_ARTIFACT_DIR/inventory.json) holding:
##   ground     every distinct material on terrain, authored ground and walk
##              surfaces, with a proposed class (grass / path-road / dirt /
##              paving-stone / sand / water / other)
##   foliage    tree, crown and undergrowth meshes by name pattern, and whether
##              crown and trunk are separate nodes, separate surfaces of one
##              mesh, or one shared material
##   batches    the loader's StaticBatch MultiMeshes: batched members are hidden
##              and drawn by the MultiMesh, so a per-node material_override
##              never reaches them
##   environment the Environment and sun actually bound, next to the block the
##              manifest declares
##   occluder_fade a live check of whether OccluderFade edits the shared material
##              or a duplicate, and what it does with a ShaderMaterial
##   code_sites where the environment is applied and re-applied, found by
##              scanning the sources rather than restated from memory
##   shaders    every .gdshader under res://src with its render mode, header
##              comment and the scripts that load it
## It only reads: no material it reports is edited, apart from the OccluderFade
## check, which applies and restores one occluder and verifies the restore.
##
## Run (ELORIA_LOOK unset, as develop):
##   Godot --audio-driver Dummy --rendering-method gl_compatibility --path godot-client
##     --script res://tests/look/probe_materials.gd
## with ELORIA_NO_MAP_CACHE=1 so the chunks import fresh, as the survey renders.

const TARGETS := [
	{"map": "lantern_reach", "x": 17.0, "z": -20.0},
	{"map": "four_gates", "x": 0.0, "z": 6.0},
	{"map": "amberwood", "x": -88.8, "z": 82.8},
]
## A mesh is ground when the loader gave it walk collision (the signal
## OccluderFade trusts), when its node is one of the exporters' ground layers,
## or when it draws with a ground material or shader. Names are never matched
## as substrings: "broadleaf" is not a road and "Firewood" is not a fir.
const GROUND_PREFIXES := ["Terrain_", "AuthoredGround_", "Walk_", "Water_", "Scenery_Water", "Scenery_Ground"]
const GROUND_SHADERS := ["biome_blend", "soft_ground", "continent_water", "lantern_water"]
## Words are matched against whole tokens of a name split at case changes,
## underscores, hyphens, spaces and digits.
const WATER_WORDS := ["water", "sea", "lake", "river", "pool", "moat", "tributary", "falls", "foam"]
const ROAD_WORDS := ["road", "path", "footpath", "trail", "highway", "street", "avenue", "lane", "climb",
	"track", "bridge", "causeway", "stair"]
const PAVING_WORDS := ["paving", "cobble", "cobbles", "flagstone", "flags", "plaza", "ashlar", "courtyard", "slab", "stone"]
const SAND_WORDS := ["sand", "beach", "shore", "dune"]
const GRASS_WORDS := ["grass", "meadow", "lawn", "moss", "turf", "heather", "clover"]
const DIRT_WORDS := ["dirt", "soil", "earth", "mud", "litter", "loam", "scorched"]
const FOLIAGE_WORDS := ["tree", "trees", "crown", "leaf", "leaves", "canopy", "maple", "oak", "fir", "pine",
	"birch", "grove", "undergrowth", "bush", "shrub", "hedge", "foliage", "fern", "palm", "cypress",
	"willow", "orchard", "sapling", "ivy", "vine", "reed", "bracken", "bramble", "pines", "seedheads", "hazel", "snag"]
## Tokens that make a foliage-sounding name a made object instead.
const NOT_FOLIAGE := ["thatch", "basket", "firewood", "plank", "planks", "timber", "cart", "crate", "barrel"]
const TRUNK_WORDS := ["bark", "trunk", "wood", "branch", "stem", "stump", "log"]
const CROWN_WORDS := ["foliage", "leaf", "leaves", "crown", "canopy", "needle", "needles", "blossom", "frond"]

var main: Control
var state: Node
var digits := RegEx.create_from_string("\\d+")
var camel := RegEx.create_from_string("([a-z])([A-Z])")
var separators := RegEx.create_from_string("[^a-z]+")
var report := {"generated": Time.get_datetime_string_from_system(), "look_enabled_env": OS.get_environment("ELORIA_LOOK"),
	"renderer": str(ProjectSettings.get_setting("rendering/renderer/rendering_method")), "maps": {}}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1440, 900)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	for target: Dictionary in TARGETS:
		if not await _load(target):
			quit(2)
			return
		var loader: WorldLoader = main.get("world_loader")
		report.maps[target.map] = _inventory(loader)
		print("PROBE inventoried ", target.map)
	report.occluder_fade = _fade_check(main.get("world_loader").world_root)
	report.code_sites = _code_sites()
	report.shaders = _shaders()
	var out := OS.get_environment("ELORIA_INVENTORY_OUT")
	if out.is_empty():
		out = OS.get_environment("ELORIA_ARTIFACT_DIR").path_join("inventory.json")
	var file := FileAccess.open(out, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, " "))
	file.close()
	print("PROBE wrote ", out)
	main.call("_on_disconnect_pressed")
	main.get("exterior_stream").clear()
	while not main.get("exterior_stream").is_idle():
		await process_frame
	for i in 6:
		await process_frame
	main.queue_free()
	await process_frame
	quit()

## The survey's own sequence: switch map, place the local actor, settle, then
## wait until every selected cell of the active territory is resident.
func _load(target: Dictionary) -> bool:
	state.set("actors", {})
	state.set("local_actor_id", -1)
	state.set("current_map", target.map)
	main.call("_load_server_map")
	var loader: WorldLoader = main.get("world_loader")
	var deadline := Time.get_ticks_msec() + 180000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if loader.world_root == null:
		push_error("Map failed to load: " + str(target.map))
		return false
	var adapter: CoordinateAdapter = main.get("adapter")
	var tile: Vector2i = adapter.godot_to_server(Vector3(float(target.x), 0, float(target.z)))
	state.set("local_actor_id", 1)
	state.set("actors", {1: {"actor_id": 1, "x": tile.x, "y": tile.y, "rotation": 0, "actor_type": 0,
		"kind": 1, "name": "Traveller", "health": 100, "max_health": 100, "alive": true, "appearance": {}}})
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	for i in 90:
		await physics_frame
		await process_frame
	deadline = Time.get_ticks_msec() + 90000
	while not _chunks_ready(loader.world_root) and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _chunks_ready(loader.world_root):
		push_error("Selected chunks never became resident: " + str(target.map))
		return false
	return true

func _chunks_ready(active: Node3D) -> bool:
	if not active is ContinentChunkStream:
		return true
	var chunks := active as ContinentChunkStream
	if not chunks.has_focus or chunks._thread != null or not chunks._retiring.is_empty():
		return false
	for entry: Dictionary in chunks.selection(chunks.focus, true):
		if float(entry.distance) <= chunks.preload_distance and not chunks.cells.has(str(entry.id)):
			return false
	return true

func _inventory(loader: WorldLoader) -> Dictionary:
	var world_root := loader.world_root
	var ground: Dictionary = {}
	var foliage: Dictionary = {}
	var batches: Array = []
	var other: Dictionary = {}
	var counts := {"mesh_instances": 0, "multimesh_batches": 0, "batched_members": 0}
	var stack: Array[Node] = [world_root]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		for child: Node in node.get_children():
			stack.append(child)
		if node is MultiMeshInstance3D:
			counts.multimesh_batches += 1
			batches.append(_batch_entry(world_root, node as MultiMeshInstance3D))
			continue
		if not node is MeshInstance3D:
			continue
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh == null:
			continue
		counts.mesh_instances += 1
		var batched := mesh_instance.has_meta(WorldLoader.BATCH_META)
		if batched:
			counts.batched_members += 1
		var path := str(world_root.get_path_to(mesh_instance))
		var pattern := _pattern(str(mesh_instance.name))
		var surfaces: Array = []
		for surface: int in mesh_instance.mesh.get_surface_count():
			surfaces.append(mesh_instance.get_active_material(surface))
		var names := _material_names(surfaces)
		var tokens := _tokens(str(mesh_instance.name) + " " + " ".join(names))
		var walk := OccluderFade._is_walk_surface(mesh_instance)
		if walk or _is_ground(mesh_instance, surfaces, names):
			for surface: int in surfaces.size():
				_add_ground(ground, surfaces[surface], path, pattern, walk, batched, mesh_instance)
		elif (_any(tokens, FOLIAGE_WORDS) or (_any(tokens, TRUNK_WORDS) and _any(tokens, CROWN_WORDS))) \
				and not _any(tokens, NOT_FOLIAGE):
			_add_foliage(foliage, mesh_instance, pattern, path, names, batched)
		else:
			for material_name: String in names:
				other[material_name] = int(other.get(material_name, 0)) + 1
	for key: String in foliage:
		var entry: Dictionary = foliage[key]
		entry.crown_and_trunk = _crown_trunk(entry)
	var top_other: Array = other.keys()
	top_other.sort_custom(func(a: String, b: String) -> bool: return int(other[a]) > int(other[b]))
	var environment_block: Variant = loader.manifest.data.get("environment", {})
	return {"manifest": loader.manifest.source_path, "chunked": world_root is ContinentChunkStream,
		"cells": (world_root as ContinentChunkStream).cells.keys() if world_root is ContinentChunkStream else [],
		"counts": counts, "ground": ground.values(), "foliage": foliage.values(),
		"static_batches": batches, "other_materials_top": top_other.slice(0, 40).map(
			func(name: String) -> Dictionary: return {"material": name, "surfaces": other[name]}),
		"environment_declared": environment_block, "environment_bound": _environment(),
		"rendering_declared": loader.manifest.data.get("rendering", {})}

func _add_ground(ground: Dictionary, material: Material, path: String, pattern: String, walk: bool,
		batched: bool, mesh_instance: MeshInstance3D) -> void:
	var info := _material_info(material)
	var key := "%s|%s|%s" % [info.get("name", ""), info.get("albedo_texture", ""), info.get("shader", "")]
	if not ground.has(key):
		info.proposed_class = _ground_class(info, pattern)
		info.nodes = 0
		info.walk_surface_nodes = 0
		info.batched_nodes = 0
		info.node_patterns = []
		info.example_paths = []
		info.vertex_colors_in_mesh = false
		ground[key] = info
	var entry: Dictionary = ground[key]
	entry.nodes += 1
	if walk:
		entry.walk_surface_nodes += 1
	if batched:
		entry.batched_nodes += 1
	if not entry.node_patterns.has(pattern) and entry.node_patterns.size() < 8:
		entry.node_patterns.append(pattern)
	if entry.example_paths.size() < 3:
		entry.example_paths.append(path)
	for surface: int in mesh_instance.mesh.get_surface_count():
		if mesh_instance.mesh.get_surface_count() > 0 and mesh_instance.mesh is ArrayMesh \
				and ((mesh_instance.mesh as ArrayMesh).surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) != 0:
			entry.vertex_colors_in_mesh = true

func _add_foliage(foliage: Dictionary, mesh_instance: MeshInstance3D, pattern: String, path: String,
		names: Array, batched: bool) -> void:
	var key := pattern + "|" + ",".join(names)
	if not foliage.has(key):
		var materials: Array = []
		for surface: int in mesh_instance.mesh.get_surface_count():
			var info := _material_info(mesh_instance.get_active_material(surface))
			info.role = _role(str(info.get("name", "")) + " " + str(mesh_instance.name))
			materials.append(info)
		foliage[key] = {"pattern": pattern, "surfaces": mesh_instance.mesh.get_surface_count(),
			"materials": materials, "nodes": 0, "batched_nodes": 0, "example_paths": [],
			"aabb_size": [snappedf(mesh_instance.get_aabb().size.x, .1), snappedf(mesh_instance.get_aabb().size.y, .1),
				snappedf(mesh_instance.get_aabb().size.z, .1)]}
	var entry: Dictionary = foliage[key]
	entry.nodes += 1
	if batched:
		entry.batched_nodes += 1
	if entry.example_paths.size() < 3:
		entry.example_paths.append(path)

## Separate nodes (Giant_5_Wood / Giant_5_Canopy), separate surfaces of one mesh
## (bark + foliage materials), or one material for the whole tree (a kit atlas).
func _crown_trunk(entry: Dictionary) -> String:
	var roles: Array = entry.materials.map(func(info: Dictionary) -> String: return str(info.role))
	if roles.has("crown") and roles.has("trunk"):
		return "separate surfaces of one mesh (distinct crown and trunk materials)"
	var name := str(entry.pattern).to_lower()
	if roles.size() == 1 and (name.contains("canopy") or name.contains("crown") or name.contains("_wood")):
		return "separate nodes (this node is only the %s)" % roles[0]
	if roles.size() == 1:
		return "one surface, one material for crown and trunk (%s)" % roles[0]
	return "several surfaces, roles %s" % ",".join(roles)

func _role(text: String) -> String:
	var tokens := _tokens(text)
	if _any(tokens, CROWN_WORDS):
		return "crown"
	if _any(tokens, TRUNK_WORDS):
		return "trunk"
	return "shared atlas"

func _is_ground(mesh_instance: MeshInstance3D, materials: Array, names: Array) -> bool:
	for prefix: String in GROUND_PREFIXES:
		if str(mesh_instance.name).begins_with(prefix):
			return true
	for material_name: String in names:
		if material_name == "continental_ground" or material_name == "ground" or material_name.begins_with("authored_"):
			return true
	for material: Material in materials:
		if material is ShaderMaterial and (material as ShaderMaterial).shader != null:
			for shader: String in GROUND_SHADERS:
				if (material as ShaderMaterial).shader.resource_path.contains(shader):
					return true
	return false

func _batch_entry(world_root: Node3D, batch: MultiMeshInstance3D) -> Dictionary:
	var mesh: Mesh = batch.multimesh.mesh if batch.multimesh != null else null
	var materials: Array = []
	if mesh != null:
		for surface: int in mesh.get_surface_count():
			materials.append(_material_info(mesh.surface_get_material(surface)).get("name", ""))
	return {"path": str(world_root.get_path_to(batch)), "instances": batch.multimesh.instance_count if batch.multimesh else 0,
		"materials": materials, "material_override": batch.material_override != null}

func _material_info(material: Material) -> Dictionary:
	if material == null:
		return {"type": "none", "name": ""}
	var info := {"type": material.get_class(), "name": material.resource_name}
	if material is BaseMaterial3D:
		var base := material as BaseMaterial3D
		info.albedo_color = "#" + base.albedo_color.to_html(true)
		info.albedo_texture = _texture_name(base.albedo_texture)
		info.vertex_color_use_as_albedo = base.vertex_color_use_as_albedo
		info.transparency = ["disabled", "alpha", "alpha_scissor", "alpha_hash", "alpha_depth_pre_pass"][base.transparency]
		info.cull = ["back", "front", "disabled"][base.cull_mode]
		info.shading = ["unshaded", "per_pixel", "per_vertex"][base.shading_mode]
		info.roughness = snappedf(base.roughness, .01)
		info.normal_map = base.normal_enabled and base.normal_texture != null
		info.uv1_scale = [snappedf(base.uv1_scale.x, .01), snappedf(base.uv1_scale.y, .01)]
		info.triplanar = base.uv1_triplanar
		info.texture_filter = base.texture_filter
	elif material is ShaderMaterial:
		var shader_material := material as ShaderMaterial
		info.shader = shader_material.shader.resource_path if shader_material.shader != null else ""
		var parameters := {}
		if shader_material.shader != null:
			for uniform: Dictionary in shader_material.shader.get_shader_uniform_list():
				var value: Variant = shader_material.get_shader_parameter(uniform.name)
				if value is Texture2D:
					parameters[uniform.name] = _texture_name(value as Texture2D)
				elif value is Color:
					parameters[uniform.name] = "#" + (value as Color).to_html(true)
				elif value is float or value is int or value is bool:
					parameters[uniform.name] = value
		info.parameters = parameters
	info.next_pass = material.next_pass != null
	return info

func _texture_name(texture: Texture2D) -> String:
	if texture == null:
		return ""
	if not texture.resource_path.is_empty():
		return texture.resource_path
	if not texture.resource_name.is_empty():
		return "embedded:" + texture.resource_name
	return "embedded:%dx%d" % [texture.get_width(), texture.get_height()]

func _material_names(materials: Array) -> Array:
	return materials.map(func(material: Material) -> String:
		return "" if material == null else (material.resource_name if not material.resource_name.is_empty() else material.get_class()))

## A proposal for the layer agents, from the material's own name, its texture
## and (for walk decks and ground layers) the node's route name. The authored
## ground-NN patches share one base texture and differ only by tint, so those
## fall back to the tint's colour.
func _ground_class(info: Dictionary, pattern: String) -> String:
	var shader := str(info.get("shader", ""))
	if shader.contains("biome_blend"):
		return "terrain blend (biome_blend.gdshader: splat of up to 8 ground layers)"
	if shader.contains("water") or shader.contains("sea"):
		return "water"
	if str(info.get("name", "")) == "continental_ground":
		return "terrain (continental_ground: one texture tinted by vertex colour)"
	if info.has("albedo_color") and Color.html(str(info.albedo_color)).a < 0.01:
		return "other (invisible walk threshold)"
	var named := _tokens(str(info.get("name", "")) + " " + str(info.get("albedo_texture", "")).get_file() + " " + pattern)
	for rule: Array in [[WATER_WORDS, "water"], [ROAD_WORDS, "path-road"], [PAVING_WORDS, "paving-stone"],
			[SAND_WORDS, "sand"], [GRASS_WORDS, "grass"], [DIRT_WORDS, "dirt"]]:
		if _any(named, rule[0]):
			return rule[1]
	if info.has("albedo_color") and not str(info.albedo_color).begins_with("#ffffff"):
		return _class_from_colour(Color.html(str(info.albedo_color))) + " (from tint)"
	return "other"

func _class_from_colour(colour: Color) -> String:
	if colour.s < 0.15:
		return "paving-stone"
	if colour.h > 0.19 and colour.h < 0.47:
		return "grass"
	if colour.h > 0.47 and colour.h < 0.72:
		return "water"
	if colour.s < 0.4 and colour.v > 0.7:
		return "sand"
	return "dirt"

func _tokens(text: String) -> PackedStringArray:
	var split := camel.sub(text, "$1 $2", true).to_lower()
	return separators.sub(split, " ", true).strip_edges().split(" ", false)

func _any(tokens: PackedStringArray, words: Array) -> bool:
	for word: String in words:
		if tokens.has(word):
			return true
	return false

func _pattern(node_name: String) -> String:
	return digits.sub(node_name, "#", true)

func _environment() -> Dictionary:
	var world_environment: WorldEnvironment = main.get("world_environment")
	var sun: DirectionalLight3D = main.get("world_sun")
	var environment := world_environment.environment
	var result := {}
	if environment != null:
		result = {"background_mode": environment.background_mode,
			"background_color": "#" + environment.background_color.to_html(false),
			"ambient_source": environment.ambient_light_source, "ambient_color": "#" + environment.ambient_light_color.to_html(false),
			"ambient_energy": environment.ambient_light_energy, "ambient_sky_contribution": environment.ambient_light_sky_contribution,
			"fog_enabled": environment.fog_enabled, "fog_color": "#" + environment.fog_light_color.to_html(false),
			"fog_density": environment.fog_density, "fog_sky_affect": environment.fog_sky_affect,
			"fog_aerial_perspective": environment.fog_aerial_perspective, "fog_height_density": environment.fog_height_density,
			"tonemap_mode": environment.tonemap_mode, "tonemap_exposure": environment.tonemap_exposure,
			"tonemap_white": environment.tonemap_white, "adjustment_enabled": environment.adjustment_enabled,
			"adjustment_brightness": environment.adjustment_brightness, "adjustment_contrast": environment.adjustment_contrast,
			"adjustment_saturation": environment.adjustment_saturation, "glow_enabled": environment.glow_enabled,
			"ssao_enabled": environment.ssao_enabled}
		if environment.sky != null and environment.sky.sky_material is ProceduralSkyMaterial:
			var sky := environment.sky.sky_material as ProceduralSkyMaterial
			result.sky = {"top": "#" + sky.sky_top_color.to_html(false), "horizon": "#" + sky.sky_horizon_color.to_html(false),
				"ground_horizon": "#" + sky.ground_horizon_color.to_html(false), "ground_bottom": "#" + sky.ground_bottom_color.to_html(false),
				"energy": sky.energy_multiplier}
	if sun != null:
		result.sun = {"visible": sun.visible, "color": "#" + sun.light_color.to_html(false), "energy": sun.light_energy,
			"rotation_degrees": [snappedf(sun.rotation_degrees.x, .1), snappedf(sun.rotation_degrees.y, .1),
				snappedf(sun.rotation_degrees.z, .1)], "shadow_enabled": sun.shadow_enabled, "shadow_opacity": sun.shadow_opacity}
	return result

## Applies OccluderFade to one unbatched multi-material mesh and one mesh with a
## ShaderMaterial surface, and reports what happened to the shared materials.
func _fade_check(world_root: Node3D) -> Dictionary:
	var result := {}
	var stack: Array[Node] = [world_root]
	var base_node: MeshInstance3D
	var shader_node: MeshInstance3D
	while not stack.is_empty() and (base_node == null or shader_node == null):
		var node: Node = stack.pop_back()
		for child: Node in node.get_children():
			stack.append(child)
		if not node is MeshInstance3D or (node as MeshInstance3D).mesh == null or node.has_meta(WorldLoader.BATCH_META):
			continue
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.material_override != null:
			continue
		var first := mesh_instance.get_active_material(0)
		# A crown is the case a look layer cares about: it is what fades most.
		if base_node == null and first is BaseMaterial3D and str(mesh_instance.name).contains("Canopy"):
			base_node = mesh_instance
		if shader_node == null and first is ShaderMaterial:
			shader_node = mesh_instance
	if base_node != null:
		var shared := base_node.get_active_material(0) as BaseMaterial3D
		var transparency_before := shared.transparency
		var occluder := OccluderFade.Occluder.new()
		occluder.node = base_node
		occluder.fade = 1.0
		occluder.apply()
		var faded := base_node.get_active_material(0)
		result.base_material = {"node": str(world_root.get_path_to(base_node)), "material": shared.resource_name,
			"faded_is_a_duplicate": faded != shared, "shared_transparency_unchanged": shared.transparency == transparency_before,
			"shared_alpha": shared.albedo_color.a, "faded_transparency_is_alpha": (faded as BaseMaterial3D).transparency == BaseMaterial3D.TRANSPARENCY_ALPHA,
			"faded_alpha": (faded as BaseMaterial3D).albedo_color.a, "via": "set_surface_override_material per surface"}
		occluder.restore()
		result.base_material.restored_to_shared = base_node.get_active_material(0) == shared \
			and base_node.get_surface_override_material(0) == null
	if shader_node != null:
		var original := shader_node.get_active_material(0)
		var occluder := OccluderFade.Occluder.new()
		occluder.node = shader_node
		occluder.fade = 1.0
		occluder.apply()
		result.shader_material = {"node": str(world_root.get_path_to(shader_node)),
			"shader": (original as ShaderMaterial).shader.resource_path if (original as ShaderMaterial).shader else "",
			"left_untouched": shader_node.get_active_material(0) == original}
		occluder.restore()
	return result

## Where the environment is bound and re-bound, found in the sources so the
## answer stays true when main.gd moves.
func _code_sites() -> Array:
	var needles := ["WorldEnvironmentBinder.apply", "DayNightBinder.apply", "adjustment_saturation",
		"adjustment_enabled", "tonemap_exposure", "fog_density", "OccluderFade.new", "_fade_copy"]
	var sites: Array = []
	for path: String in _files("res://src", ".gd"):
		var lines := FileAccess.get_file_as_string(path).split("\n")
		for index: int in lines.size():
			for needle: String in needles:
				if lines[index].contains(needle):
					sites.append({"file": path, "line": index + 1, "needle": needle, "text": lines[index].strip_edges()})
					break
	return sites

func _shaders() -> Array:
	var scripts: Dictionary = {}
	for script: String in _files("res://src", ".gd"):
		scripts[script] = FileAccess.get_file_as_string(script)
	var result: Array = []
	for path: String in _files("res://src", ".gdshader"):
		var lines := FileAccess.get_file_as_string(path).split("\n")
		var header: Array = []
		var mode := ""
		for line: String in lines.slice(0, 40):
			if line.begins_with("render_mode"):
				mode = line.strip_edges()
			elif line.begins_with("//"):
				header.append(line.trim_prefix("//").strip_edges())
			elif not header.is_empty() and not line.begins_with("shader_type") and not line.strip_edges().is_empty():
				break
		var users: Array = []
		for script: String in scripts:
			if str(scripts[script]).contains(path):
				users.append(script)
		result.append({"path": path, "lines": lines.size(), "render_mode": mode, "header": " ".join(header), "loaded_by": users})
	return result

func _files(folder: String, extension: String) -> Array[String]:
	var found: Array[String] = []
	var directory := DirAccess.open(folder)
	if directory == null:
		return found
	for sub: String in directory.get_directories():
		found.append_array(_files(folder.path_join(sub), extension))
	for file: String in directory.get_files():
		if file.ends_with(extension):
			found.append(folder.path_join(file))
	return found
