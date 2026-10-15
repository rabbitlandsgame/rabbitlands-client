extends RefCounted

const OBJECTS_PATH := "res://data/world/objects.json"
const EXTRAS_PATH := "res://data/world/map_asset_extras.json"
const EXTRA_CATEGORIES := {
	"Continent props": true,
	"Continent structures": true,
	"Continent landmarks": true,
}
const STARTER_SCENE_PATH := \
	"res://src/dev/map_authoring_pilot/scenery/last_lantern_scenery.tscn"
const STARTER_ENTRIES := [
	["starter:cabin_lantern", "Cabin Lantern", "CabinLantern", "lantern light cabin"],
	["starter:shore_rock_west", "Shore Rock West", "ShoreRockWest", "rock stone shore"],
	["starter:shore_rock_east", "Shore Rock East", "ShoreRockEast", "rock stone shore"],
	["starter:wind_pine", "Wind Pine", "WindPine", "tree pine foliage"],
	["starter:grass_clump_north", "Grass Clump North", "GrassClumpNorth", "grass foliage"],
	["starter:grass_clump_south", "Grass Clump South", "GrassClumpSouth", "grass foliage"],
	["starter:weathered_sign", "Weathered Sign", "WeatheredSign", "sign timber"],
]

## Drop-in library: every .glb, .tscn or .scn under this folder becomes a palette
## entry with no JSON to edit (a loose .gltf is listed in skipped_library_files:
## the bake needs .glb, and Import models converts it). A first-level subfolder names its category
## ("Library: Rocks"); files directly inside are listed under "Library".
const LIBRARY_DIRECTORY := "res://assets/world/library"
const LIBRARY_EXTENSIONS := ["glb", "tscn", "scn"]
const IMPORT_EXTENSIONS := ["glb", "gltf"]
const LIBRARY_CATEGORY := "Library"
const LIBRARY_PREFIX := "library:"
## The open territory's own kit: every .glb in `assets/prototypes` beside its
## scene. The category decides the collision role a placed copy starts with
## (region_control.prepare_palette_asset makes "structure" categories solid).
const TERRITORY_KIT_FOLDER := "assets/prototypes"
const TERRITORY_SCENERY := "Territory kit: scenery"
const TERRITORY_STRUCTURES := "Territory kit: structures"
## Words in a kit file name that mean something you walk through, for a piece
## no saved copy has given a role yet; anything else starts solid.
const WALK_THROUGH_WORDS := ["shrub", "sage", "scrub", "grass", "bones", "tree", "scree",
	"crystal", "rack", "fire-pit", "hitching", "earthrock", "flower", "reed", "fern", "bush",
	"weed", "pail", "sack", "blanket", "churn", "brush", "thorn", "lichen", "mine-rail", "tripod",
	"undergrowth", "driftwood", "terracotta", "basket", "lantern-string", "leaves", "pumpkin",
	"cabbage", "scarecrow", "fence", "wheelbarrow", "rose-arch", "stook", "drift", "flag-line",
	"frozen-pond", "icicle-fringe", "rockfall", "net-frame", "vineyard", "rope-coils",
	"lobster-pots", "fish-crates", "buoy", "gate-arch", "fish-weir", "water-jars", "hearth", "hammock",
	"fish-line", "decoy", "floating-lantern", "rice-paddy", "rice-sheaves", "water-lilies", "bamboo-clump", "pergola",
	"lamp-buoy", "diver-float", "sorting-table", "net-mending", "parasols", "statue-head", "citrus-planter",
	"heather", "gorse", "rushes", "bracken", "grave-markers", "candle-stake", "skeleton", "peat-stack",
	"peat-barrow", "wisp-lantern", "bog-pool", "kelp", "toadstool", "bramble", "leaf-pile", "sawhorse",
	"forest-shrine", "cider-press", "woodcutter-block", "stone-bench", "garden-urn", "notice-board",
	"lantern-post", "stone-well", "produce-stall", "market-canopy", "beehive", "net-drying", "mooring-posts",
	"quay-steps", "landing-stage", "sanctuary-beacon"]

## The largest dimension the continent's own library extractor admits for one
## asset (export_map_asset_library.py); anything bigger is usually a unit slip.
const MAX_LIBRARY_DIMENSION := 80.0

static var library_directory := LIBRARY_DIRECTORY
## Library files the last scan left out (a .gltf the bake cannot take directly).
static var skipped_library_files: PackedStringArray = []
static var _cache: Array[Dictionary] = []
static var _cache_ready := false


static func entries(refresh_cache: bool = false) -> Array[Dictionary]:
	if refresh_cache or not _cache_ready:
		_cache = _build_entries()
		_cache_ready = true
	var result: Array[Dictionary] = []
	for entry: Dictionary in _cache:
		result.append(entry.duplicate(true))
	return result


static func filter_entries(source_entries: Array[Dictionary], query: String,
		category: String = "") -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var wanted_query := query.strip_edges().to_lower()
	var wanted_category := category.strip_edges().to_lower()
	if wanted_category == "all":
		wanted_category = ""
	for entry: Dictionary in source_entries:
		if not wanted_category.is_empty() and \
				String(entry.get("category", "")).to_lower() != wanted_category:
			continue
		var searchable := String(entry.get("search_text", "")).to_lower()
		if not wanted_query.is_empty() and searchable.find(wanted_query) < 0:
			continue
		result.append(entry)
	return result


static func categories(source_entries: Array[Dictionary]) -> PackedStringArray:
	var result := PackedStringArray()
	var seen := {}
	for entry: Dictionary in source_entries:
		var category := String(entry.get("category", "")).strip_edges()
		if category.is_empty() or seen.has(category):
			continue
		seen[category] = true
		result.append(category)
	return result


static func _build_entries() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var catalog := _read_dictionary(OBJECTS_PATH)
	if catalog.is_empty():
		return result
	_append_native_group(result, catalog, "harvestables", "Harvestables")
	_append_native_group(result, catalog, "interactives", "Interactives")
	if _valid_resource_path(STARTER_SCENE_PATH):
		for spec: Array in STARTER_ENTRIES:
			result.append(_entry(String(spec[0]), String(spec[1]),
				"Starter scenery", STARTER_SCENE_PATH, String(spec[2]), 0.0,
				String(spec[3])))
	else:
		push_warning("Map asset catalog skipped missing starter scene: %s" %
			STARTER_SCENE_PATH)
	_append_extras(result)
	_append_library(result)
	return result


## Own kit plus the active catalog's shared libraries. Saved copies keep their
## identities and roles; pinned shared bindings also cover models absent from
## this particular scene. Unsaved and non-catalog scenes retain the own-kit path.
static func territory_entries(root: Node) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if root == null or root.scene_file_path.is_empty():
		return result
	var own_folder := root.scene_file_path.get_base_dir().path_join(TERRITORY_KIT_FOLDER)
	var libraries: Array[Dictionary] = []
	if DirAccess.dir_exists_absolute(own_folder):
		libraries.append({"directory": own_folder, "catalogPrefix": ""})
	var shared := _shared_kit_config(root)
	var seen_folders := {own_folder: true}
	for raw: Variant in shared.get("sharedAssetLibraries", []):
		if not raw is Dictionary:
			continue
		var folder := String(raw.get("directory", "")).trim_suffix("/")
		if not folder.begins_with("res://") or seen_folders.has(folder):
			continue
		seen_folders[folder] = true
		if not DirAccess.dir_exists_absolute(folder):
			push_warning("Shared territory kit is missing: %s" % folder)
			continue
		libraries.append({"directory": folder, "catalogPrefix": String(raw.get("catalogPrefix", ""))})
	var bindings: Dictionary = {}
	var binding_path := String(shared.get("sharedAssetCatalogPath", ""))
	if not binding_path.is_empty():
		var source := _read_dictionary(binding_path)
		if source.get("schema") == "eloria-shared-kit-catalog-v1" and source.get("models") is Dictionary:
			bindings = source.models
	var used := {}
	var container := root.get_node_or_null("AuthoredAssets")
	if container != null:
		for child in container.get_children():
			var scene_path := String(child.get("scene_path")) if "scene_path" in child else ""
			if scene_path.is_empty():
				continue
			var record: Dictionary = used.get(scene_path, {"ids": {}, "roles": {}})
			var catalog_id := String(child.get("catalog_asset_id"))
			var role := String(child.get("collision_role"))
			record.ids[catalog_id] = int(record.ids.get(catalog_id, 0)) + 1
			record.roles[role] = int(record.roles.get(role, 0)) + 1
			used[scene_path] = record
	var seen_ids := {}
	for library: Dictionary in libraries:
		var folder := String(library.directory)
		var prefixes := {}
		for path: String in used:
			if path.begins_with(folder + "/"):
				for identity: String in used[path].ids:
					if ":" in identity:
						var prefix := identity.get_slice(":", 0)
						prefixes[prefix] = int(prefixes.get(prefix, 0)) + int(used[path].ids[identity])
		var prefix := String(library.catalogPrefix)
		if prefix.is_empty():
			prefix = _most_common(prefixes)
		if prefix.is_empty():
			prefix = String(root.get("region_id")) if "region_id" in root else "territory"
		var files := Array(DirAccess.get_files_at(folder))
		files.sort()
		for file: String in files:
			if file.get_extension().to_lower() != "glb":
				continue
			var scene_path := folder.path_join(file)
			var stem := file.get_basename()
			var record: Dictionary = used.get(scene_path, {})
			var binding: Dictionary = bindings.get(scene_path, {})
			var identity := _most_common(record.get("ids", {}))
			if identity.is_empty():
				identity = String(binding.get("catalogAssetId", "%s:%s" % [prefix, stem]))
			var role := _most_common(record.get("roles", {}))
			if role.is_empty():
				role = String(binding.get("collisionRole", ""))
			if role.is_empty():
				role = "none" if WALK_THROUGH_WORDS.any(func(word: String) -> bool:
					return word in stem) else "solid"
			if seen_ids.has(identity):
				push_warning("Shared territory kit has a duplicate catalog id: %s" % identity)
				continue
			seen_ids[identity] = true
			var label := stem.trim_prefix("kit-").replace("-", " ").capitalize()
			result.append(_entry(identity, label,
				TERRITORY_STRUCTURES if role == "solid" else TERRITORY_SCENERY, scene_path, "", 0.0,
				"%s territory kit %s" % [stem, "solid" if role == "solid" else "walk-through"]))
	return result


static func _shared_kit_config(root: Node) -> Dictionary:
	var path := String(ProjectSettings.get_setting("map_authoring/territory_catalog_path",
		"res://world_authoring/territories.json"))
	var catalog := _read_dictionary(path)
	for entry: Variant in catalog.get("entries", []):
		if entry is Dictionary and entry.get("scenePath") == root.scene_file_path:
			return catalog
	return {}


static func _most_common(counts: Dictionary) -> String:
	var best := ""
	var best_count := 0
	var keys := counts.keys()
	keys.sort()
	for key: Variant in keys:
		if int(counts[key]) > best_count:
			best = String(key)
			best_count = int(counts[key])
	return best


## Library entries, found by walking library_directory (see LIBRARY_DIRECTORY).
static func library_entries() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	_append_library(result)
	return result


static func _append_library(result: Array[Dictionary]) -> void:
	skipped_library_files = PackedStringArray()
	var root := library_directory.trim_suffix("/")
	if not DirAccess.dir_exists_absolute(root):
		return
	var known_ids := {}
	for existing: Dictionary in result:
		known_ids[String(existing.id)] = true
	_scan_library(result, known_ids, root, root, "")


static func _scan_library(result: Array[Dictionary], known_ids: Dictionary, root: String,
		directory: String, category: String) -> void:
	var files := DirAccess.get_files_at(directory)
	var sorted_files := Array(files)
	sorted_files.sort_custom(func(a: String, b: String) -> bool:
		return a.naturalnocasecmp_to(b) < 0)
	for file_name: String in sorted_files:
		if file_name.get_extension().to_lower() == "gltf":
			skipped_library_files.append(directory.path_join(file_name))
			continue
		if file_name.begins_with(".") or not file_name.get_extension().to_lower() in \
				LIBRARY_EXTENSIONS:
			continue
		var path := directory.path_join(file_name)
		var relative := path.trim_prefix(root + "/").get_basename()
		var id := LIBRARY_PREFIX + relative
		if known_ids.has(id):
			id = LIBRARY_PREFIX + path.trim_prefix(root + "/")
		if known_ids.has(id):
			continue
		known_ids[id] = true
		var label := file_name.get_basename().replace("_", " ").replace("-", " ").capitalize()
		var category_name := LIBRARY_CATEGORY if category.is_empty() else \
			"%s: %s" % [LIBRARY_CATEGORY, category]
		result.append(_entry(id, label, category_name, path, "", 0.0,
			"library imported %s %s" % [category, relative.replace("/", " ")]))
	var folders := Array(DirAccess.get_directories_at(directory))
	folders.sort_custom(func(a: String, b: String) -> bool:
		return a.naturalnocasecmp_to(b) < 0)
	for folder: String in folders:
		if folder.begins_with("."):
			continue
		_scan_library(result, known_ids, root, directory.path_join(folder),
			folder if category.is_empty() else category)


## Copies model files from anywhere on disk into library_directory/<category>.
## A .glb is copied as it is; a .gltf is converted to a self-contained .glb,
## because the bake accepts only static GLB sources ("bakedSource.path must be
## a static GLB"). Existing names get a numeric suffix; nothing is overwritten.
## Returns {"copied": [res paths], "skipped": [reasons]}. The editor still has
## to scan and import the copies.
static func import_models(sources: PackedStringArray, category: String) -> Dictionary:
	var copied: Array[String] = []
	var skipped: Array[String] = []
	var folder := library_directory.trim_suffix("/")
	var cleaned := _clean_name(category)
	if not cleaned.is_empty():
		folder = folder.path_join(cleaned)
	var absolute_folder := ProjectSettings.globalize_path(folder)
	DirAccess.make_dir_recursive_absolute(absolute_folder)
	for source in sources:
		var extension := source.get_extension().to_lower()
		if not extension in IMPORT_EXTENSIONS:
			skipped.append("%s: only .glb and .gltf models can be imported" % source.get_file())
			continue
		if not FileAccess.file_exists(source):
			skipped.append("%s: file not found" % source)
			continue
		var stem := _clean_name(source.get_file().get_basename())
		if stem.is_empty():
			stem = "model"
		var target_name := "%s.glb" % stem
		var suffix := 2
		while FileAccess.file_exists(absolute_folder.path_join(target_name)):
			target_name = "%s_%d.glb" % [stem, suffix]
			suffix += 1
		var target := absolute_folder.path_join(target_name)
		var error := DirAccess.copy_absolute(source, target) if extension == "glb" \
			else _gltf_to_glb(source, target)
		if error != OK:
			skipped.append("%s: %s failed (%s)" % [source.get_file(),
				"copy" if extension == "glb" else "conversion to .glb", error_string(error)])
			continue
		copied.append(folder.path_join(target_name))
	return {"copied": copied, "skipped": skipped}


## What to check before a library asset goes into a territory: the things the
## palette will place but the bake or the game will not carry as they look in
## the editor. Read from the packed scene's state without instantiating it, so
## none of its scripts run. Empty when nothing needs a look.
static func admission_notes(scene_path: String) -> PackedStringArray:
	var notes := PackedStringArray()
	var packed := ResourceLoader.load(scene_path) as PackedScene \
		if ResourceLoader.exists(scene_path) else null
	if packed == null:
		notes.append("It does not load as a scene; the editor may still be importing it.")
		return notes
	var state := packed.get_state()
	if state.get_node_count() == 0:
		notes.append("The scene is empty.")
		return notes
	var root_type := String(state.get_node_type(0))
	if root_type.is_empty() and state.get_node_instance(0) != null:
		root_type = String(state.get_node_instance(0).get_state().get_node_type(0))
	if not root_type.is_empty() and not ClassDB.is_parent_class(root_type, "Node3D"):
		notes.append("Its root is a %s, not a Node3D; placement and the bake expect a 3D scene." %
			root_type)
	var found := {"scripts": [], "shaders": 0, "triplanar": 0, "meshes": 0,
		"box": AABB(), "sized": false}
	_scan_scene_state(state, Transform3D.IDENTITY, found, 0)
	var scripts := PackedStringArray(found.scripts)
	if not scripts.is_empty():
		notes.append(("It carries %d script%s (%s). Scripts never run in the game: the bake " +
			"exports geometry and materials only.") % [scripts.size(),
			"" if scripts.size() == 1 else "s", ", ".join(scripts.slice(0, 3))])
	if int(found.shaders) > 0:
		notes.append(("%d surface%s use%s a custom shader, which does not survive the export to " +
			"GLB; the game shows a plain material there.") % [int(found.shaders),
			"" if int(found.shaders) == 1 else "s", "s" if int(found.shaders) == 1 else ""])
	if int(found.triplanar) > 0:
		notes.append("%d material%s triplanar mapping, which the production bake does not support." % [
			int(found.triplanar), " uses" if int(found.triplanar) == 1 else "s use"])
	if int(found.meshes) == 0:
		notes.append("It has no mesh, so nothing would be drawn or baked.")
	elif bool(found.sized):
		var size: Vector3 = (found.box as AABB).size
		var largest := maxf(size.x, maxf(size.y, size.z))
		if largest > MAX_LIBRARY_DIMENSION:
			notes.append(("It is %.0f x %.0f x %.0f m, over the %.0f m the library extractor admits " +
				"for one asset; check it was exported in metres.") % [size.x, size.y, size.z,
				MAX_LIBRARY_DIMENSION])
	return notes


static func _scan_scene_state(state: SceneState, base: Transform3D, found: Dictionary,
		depth: int) -> void:
	var transforms := {}
	for index in state.get_node_count():
		var path := String(state.get_node_path(index))
		var parent := String(state.get_node_path(index, true))
		var local := Transform3D.IDENTITY
		var mesh: Mesh = null
		var materials: Array[Material] = []
		for property in state.get_node_property_count(index):
			var property_name := String(state.get_node_property_name(index, property))
			var value: Variant = state.get_node_property_value(index, property)
			if property_name == "transform" and value is Transform3D:
				local = value
			elif property_name == "script" and value is Script:
				var script_path := (value as Script).resource_path
				(found.scripts as Array).append(script_path.get_file()
					if not script_path.is_empty() and not "::" in script_path else "a built-in script")
			elif property_name == "mesh" and value is Mesh:
				mesh = value
			elif (property_name in ["material_override", "material_overlay"] or
					property_name.begins_with("surface_material_override/")) and value is Material:
				materials.append(value)
		var global: Transform3D = (transforms.get(parent, base) as Transform3D) * local
		transforms[path] = global
		if mesh != null:
			found.meshes = int(found.meshes) + 1
			var box: AABB = global * mesh.get_aabb()
			found.box = box if not bool(found.sized) else (found.box as AABB).merge(box)
			found.sized = true
			for surface in mesh.get_surface_count():
				var material := mesh.surface_get_material(surface)
				if material != null:
					materials.append(material)
		for material in materials:
			if material is ShaderMaterial:
				found.shaders = int(found.shaders) + 1
			elif material is BaseMaterial3D and ((material as BaseMaterial3D).uv1_triplanar or
					(material as BaseMaterial3D).uv1_world_triplanar):
				found.triplanar = int(found.triplanar) + 1
		var instance := state.get_node_instance(index)
		if instance != null and depth < 4:
			_scan_scene_state(instance.get_state(), global, found, depth + 1)


## Reads a .gltf with its buffers and images and writes one binary .glb.
static func _gltf_to_glb(source: String, target: String) -> Error:
	var reader := GLTFDocument.new()
	var state := GLTFState.new()
	var error := reader.append_from_file(source, state)
	if error != OK:
		return error
	var scene := reader.generate_scene(state)
	if scene == null:
		return ERR_PARSE_ERROR
	var writer := GLTFDocument.new()
	var output := GLTFState.new()
	error = writer.append_from_scene(scene, output)
	if error == OK:
		error = writer.write_to_filesystem(output, target)
	scene.free()
	return error


static func _clean_name(text: String) -> String:
	var cleaned := ""
	for character in text.strip_edges():
		if character.is_valid_identifier() or character.is_valid_int() or character == "-":
			cleaned += character
		elif not cleaned.ends_with("_"):
			cleaned += "_"
	return cleaned.trim_prefix("_").trim_suffix("_")


static func _append_native_group(result: Array[Dictionary], catalog: Dictionary,
		group_name: String, category: String) -> void:
	var group := catalog.get(group_name, {}) as Dictionary
	var models := group.get("models", {}) as Dictionary
	var roles := group.get("roles", {}) as Dictionary
	var role_names := {}
	for role_label: String in roles:
		role_names[String(roles[role_label])] = role_label
	# Two models can share a label: an imported harvest node registered beside
	# the procedural one it replaces (or may replace). The label alone would
	# list two identical "Flint" entries, so each of those names its model and
	# says which one the server's label does not draw.
	var resources := group.get("resources", {}) as Dictionary
	var label_counts := {}
	for model_id: String in models:
		var shared := String((models[model_id] as Dictionary).get("label", model_id))
		label_counts[shared] = int(label_counts.get(shared, 0)) + 1
	var sorted_models: Array[Dictionary] = []
	for model_id: String in models:
		var model := models[model_id] as Dictionary
		sorted_models.append({"id": model_id, "model": model})
	sorted_models.sort_custom(func(left: Dictionary, right: Dictionary) -> bool:
		var left_label := String((left.model as Dictionary).get("label", left.id))
		var right_label := String((right.model as Dictionary).get("label", right.id))
		if left_label.naturalnocasecmp_to(right_label) == 0:
			return String(left.id) < String(right.id)
		return left_label.naturalnocasecmp_to(right_label) < 0)
	for item: Dictionary in sorted_models:
		var model_id := String(item.id)
		var model := item.model as Dictionary
		var scene_path := String(model.get("scene", ""))
		if not _valid_resource_path(scene_path):
			push_warning("Map asset catalog skipped invalid path for '%s': %s" % [
				model_id, scene_path])
			continue
		var label := String(model.get("label", model_id))
		var imported := bool(model.get("imported", false))
		if int(label_counts.get(label, 0)) > 1:
			var note := model_id
			if String(resources.get(label, "")) != model_id:
				note += ", not swapped in" if imported else ", replaced"
			label = "%s (%s)" % [label, note]
		var search_fields := [String(model.get("kind", "")),
			String(role_names.get(model_id, "")), group_name,
			"imported" if imported else "procedural"]
		result.append(_entry(model_id, label, category, scene_path, "",
			float(model.get("height", 0.0)), " ".join(search_fields)))


static func _append_extras(result: Array[Dictionary]) -> void:
	if not FileAccess.file_exists(EXTRAS_PATH):
		return
	var manifest := _read_dictionary(EXTRAS_PATH)
	var declared: Variant = manifest.get("entries", null)
	if int(manifest.get("version", 0)) != 1 or not declared is Array:
		push_warning("Map asset extras must use version 1 with an entries array: %s" %
			EXTRAS_PATH)
		return
	var known_ids := {}
	for existing: Dictionary in result:
		known_ids[String(existing.id)] = true
	for value: Variant in declared as Array:
		if not value is Dictionary:
			push_warning("Map asset extras skipped a non-object entry")
			continue
		var extra := value as Dictionary
		var id := String(extra.get("id", "")).strip_edges()
		var label := String(extra.get("label", "")).strip_edges()
		var category := String(extra.get("category", "")).strip_edges()
		var scene_path := String(extra.get("scene_path", "")).strip_edges()
		var height := float(extra.get("height", 0.0))
		var tags_value: Variant = extra.get("tags", [])
		if not id.begins_with("continent:") or label.is_empty() or \
				not EXTRA_CATEGORIES.has(category) or known_ids.has(id) or \
				not scene_path.begins_with("res://assets/world/continent/") or \
				not _valid_resource_path(scene_path) or not is_finite(height) or \
				height < 0.0 or not tags_value is Array:
			push_warning("Map asset extras skipped invalid or duplicate entry '%s'" % id)
			continue
		var tags: Array[String] = []
		var tags_valid := true
		for tag_value: Variant in tags_value as Array:
			if not tag_value is String:
				tags_valid = false
				break
			var tag := String(tag_value).strip_edges()
			if not tag.is_empty():
				tags.append(tag)
		if not tags_valid:
			push_warning("Map asset extras skipped invalid tags for '%s'" % id)
			continue
		known_ids[id] = true
		result.append(_entry(id, label, category, scene_path, "", height,
			" ".join(tags)))


static func _entry(id: String, label: String, category: String,
		scene_path: String, source_node: String, height: float,
		extra_search: String) -> Dictionary:
	return {
		"id": id,
		"label": label,
		"category": category,
		"scene_path": scene_path,
		"source_node": source_node,
		"height": height,
		"search_text": "%s %s %s %s %s" % [
			id, label, category, source_node, extra_search],
	}


static func _read_dictionary(path: String) -> Dictionary:
	if not _valid_resource_path(path):
		push_warning("Map asset catalog source is missing: %s" % path)
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		push_warning("Map asset catalog source is not a JSON object: %s" % path)
		return {}
	return parsed as Dictionary


static func _valid_resource_path(path: String) -> bool:
	return path.begins_with("res://") and FileAccess.file_exists(path)
