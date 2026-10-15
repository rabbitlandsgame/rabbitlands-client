extends SceneTree

const Catalog := preload("res://addons/map_asset_palette/asset_catalog.gd")
const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")
const KIT_SOURCE := "res://world_authoring/regions/sunmane_steppe/assets/prototypes/"
const KIT_FIXTURE := "res://test-artifacts/territory-kit"
const OBJECTS_PATH := "res://data/world/objects.json"
const EXTRAS_PATH := "res://data/world/map_asset_extras.json"
const STARTER_PATH := \
	"res://src/dev/map_authoring_pilot/scenery/last_lantern_scenery.tscn"
const STARTER_NODES := [
	"CabinLantern", "ShoreRockWest", "ShoreRockEast", "WindPine",
	"GrassClumpNorth", "GrassClumpSouth", "WeatheredSign",
]

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var entries := Catalog.entries()
	_test_real_counts(entries)
	_test_valid_unique_entries(entries)
	_test_source_nodes(entries)
	_test_extra_manifest(entries)
	_test_metadata_and_stability(entries)
	_test_filtering(entries)
	_test_territory_kit()
	_test_shared_territory_kits()
	print("map asset catalog: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _test_real_counts(entries: Array[Dictionary]) -> void:
	var source: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(OBJECTS_PATH)) as Dictionary
	var harvestable_count := ((source.harvestables as Dictionary).models as Dictionary).size()
	var interactive_count := ((source.interactives as Dictionary).models as Dictionary).size()
	var extra_count := (_extras_manifest().get("entries", []) as Array).size()
	_expect(entries.size() == harvestable_count + interactive_count +
		STARTER_NODES.size() + extra_count,
		"catalog contains every native model, starter subtree, and declared extra")
	_expect(Catalog.filter_entries(entries, "", "Harvestables").size() ==
		harvestable_count and Catalog.filter_entries(entries, "", "Interactives").size() ==
		interactive_count and Catalog.filter_entries(entries, "", "Starter scenery").size() == 7,
		"category totals match their real sources")


func _test_valid_unique_entries(entries: Array[Dictionary]) -> void:
	var ids := {}
	var valid := true
	for entry: Dictionary in entries:
		var id := String(entry.get("id", ""))
		var label := String(entry.get("label", ""))
		var path := String(entry.get("scene_path", ""))
		valid = valid and not id.is_empty() and not label.is_empty() and \
			not ids.has(id) and \
			path.begins_with("res://") and FileAccess.file_exists(path)
		ids[id] = true
	_expect(valid, "every entry has a unique ID, nonempty label, and existing res path")
	_expect(not ids.has("quartz"),
		"the uncataloged legacy quartz duplicate is not invented as an entry")
	# An imported node registered beside the procedural model of the same label
	# must not list as a second identical entry.
	var harvest_labels := {}
	var distinct := true
	for entry: Dictionary in Catalog.filter_entries(entries, "", "Harvestables"):
		var shown := String(entry.get("label", ""))
		distinct = distinct and not harvest_labels.has(shown)
		harvest_labels[shown] = true
	_expect(distinct, "no two harvest models list under the same palette label")


func _test_source_nodes(entries: Array[Dictionary]) -> void:
	var scene_text := FileAccess.get_file_as_string(STARTER_PATH)
	var found := {}
	var valid := true
	for entry: Dictionary in entries:
		var source_node := String(entry.get("source_node", ""))
		if entry.category == "Starter scenery":
			valid = valid and entry.scene_path == STARTER_PATH and \
				source_node in STARTER_NODES and \
				scene_text.find('[node name="%s"' % source_node) >= 0
			found[source_node] = true
		else:
			valid = valid and source_node.is_empty()
	_expect(valid and found.size() == STARTER_NODES.size(),
		"starter entries name real top-level subtrees and full scenes leave source_node empty")


func _test_extra_manifest(entries: Array[Dictionary]) -> void:
	var manifest := _extras_manifest()
	var declared := manifest.get("entries", []) as Array
	var valid := true
	var declared_ids := PackedStringArray()
	for value: Variant in declared:
		if not value is Dictionary:
			valid = false
			continue
		var extra := value as Dictionary
		var extra_id := String(extra.get("id", ""))
		declared_ids.append(extra_id)
		var found := _by_id(entries, extra_id)
		valid = valid and not found.is_empty() and \
			found.label == extra.get("label") and \
			found.category == extra.get("category") and \
			found.scene_path == extra.get("scene_path") and \
			is_equal_approx(float(found.height), float(extra.get("height", 0.0)))
		for tag: Variant in extra.get("tags", []) as Array:
			var tag_text := String(tag).strip_edges()
			var matches := Catalog.filter_entries(entries, tag_text,
				String(extra.get("category", "")))
			valid = valid and not tag_text.is_empty() and \
				matches.any(func(entry: Dictionary) -> bool:
				return entry.id == extra.get("id"))
	var catalog_ids := PackedStringArray()
	for entry: Dictionary in entries:
		if String(entry.id).begins_with("continent:"):
			catalog_ids.append(String(entry.id))
	_expect(valid,
		"every declared continent extra preserves identity and searchable manifest tags")
	_expect(catalog_ids == declared_ids,
		"continent extras preserve manifest order")


func _test_metadata_and_stability(entries: Array[Dictionary]) -> void:
	var reed := _by_id(entries, "mirror_reed")
	var gate := _by_id(entries, "gate")
	# Reed's harvest patch nodes (2026-10-14) share its label, so the palette names the
	# model that the server's label draws.
	_expect(reed.label == "Reed (mirror_reed)" and reed.scene_path.ends_with("mirror_reed.glb") and
		is_equal_approx(float(reed.height), 1.606) and gate.label == "Gate" and
		is_equal_approx(float(gate.height), 2.62),
		"catalog preserves native labels, source paths, and desired heights")
	var second := Catalog.entries(true)
	var original_label := String(second[0].label)
	entries[0]["label"] = "mutated"
	_expect(second.size() == entries.size() and second[0].label == original_label and
		Catalog.entries()[0].label == original_label,
		"refresh keeps stable order and returned dictionaries cannot mutate the cache")
	entries[0]["label"] = original_label


func _test_filtering(entries: Array[Dictionary]) -> void:
	var fibre := Catalog.filter_entries(entries, "FIBRE", "hArVeStAbLeS")
	var station := Catalog.filter_entries(entries, "crafting STATION", "INTERACTIVES")
	var shore := Catalog.filter_entries(entries, "shore ROCK west", "starter SCENERY")
	var geode := Catalog.filter_entries(entries, "VOLTAIC_GEODE", "")
	_expect(fibre.any(func(entry: Dictionary) -> bool: return entry.id == "mirror_reed") and
		station.size() == 1 and station[0].id == "crafting_station" and
		shore.size() == 1 and shore[0].source_node == "ShoreRockWest" and
		geode.size() == 1 and geode[0].id == "voltaic_geode",
		"query and category matching are case-insensitive across kind, label, node, and ID")
	var expected_categories := PackedStringArray([
		"Harvestables", "Interactives", "Starter scenery"])
	for value: Variant in _extras_manifest().get("entries", []) as Array:
		if not value is Dictionary:
			continue
		var category := String((value as Dictionary).get("category", ""))
		if not category.is_empty() and category not in expected_categories:
			expected_categories.append(category)
	_expect(Catalog.categories(entries) == expected_categories,
		"categories preserve stable catalog order")


func _extras_manifest() -> Dictionary:
	if not FileAccess.file_exists(EXTRAS_PATH):
		return {"version": 1, "entries": []}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(EXTRAS_PATH))
	return parsed as Dictionary if parsed is Dictionary else {}


func _by_id(entries: Array[Dictionary], id: String) -> Dictionary:
	for entry: Dictionary in entries:
		if entry.id == id:
			return entry
	return {}


## A territory's own kit is listed from the prototypes folder beside its scene.
## Copied pieces keep the saved copies' id and role; a new piece takes the
## scene's prefix and a role from its name. Uses a throwaway folder, never a
## production territory.
func _test_territory_kit() -> void:
	var folder := KIT_FIXTURE.path_join("assets/prototypes")
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	for file in ["kit-cart.glb", "kit-steppe-shrub-0.glb", "kit-grey-boulder-1.glb"]:
		DirAccess.copy_absolute(ProjectSettings.globalize_path(KIT_SOURCE + file),
			ProjectSettings.globalize_path(folder.path_join(file)))
	var root := Node3D.new()
	root.scene_file_path = KIT_FIXTURE.path_join("fixture.tscn")
	var container := Node3D.new()
	container.name = "AuthoredAssets"
	root.add_child(container)
	for pair: Array in [["demo:kit-cart", "solid"], ["demo:kit-cart", "solid"]]:
		var wrapper: Node3D = ASSET_SCRIPT.new()
		wrapper.set("scene_path", folder.path_join("kit-cart.glb"))
		wrapper.set("catalog_asset_id", pair[0])
		wrapper.set("collision_role", pair[1])
		container.add_child(wrapper)
	var listed := Catalog.territory_entries(root)
	var by_file := {}
	for entry: Dictionary in listed:
		by_file[String(entry.scene_path).get_file()] = entry
	_expect(listed.size() == 3, "the territory kit lists every .glb beside the scene")
	_expect(String(by_file.get("kit-cart.glb", {}).get("id", "")) == "demo:kit-cart" and
		String(by_file["kit-cart.glb"].category) == Catalog.TERRITORY_STRUCTURES,
		"a placed kit piece keeps its copies' catalog id and solid role")
	_expect(String(by_file.get("kit-steppe-shrub-0.glb", {}).get("id", "")) ==
		"demo:kit-steppe-shrub-0" and
		String(by_file["kit-steppe-shrub-0.glb"].category) == Catalog.TERRITORY_SCENERY,
		"a new ground-cover piece takes the scene's prefix and starts walk-through")
	_expect(String(by_file.get("kit-grey-boulder-1.glb", {}).get("category", "")) ==
		Catalog.TERRITORY_STRUCTURES, "a new boulder starts solid")
	var unsaved := Node3D.new()
	_expect(Catalog.territory_entries(unsaved).is_empty(),
		"an unsaved scene has no territory kit")
	unsaved.free()
	root.free()
	for file in DirAccess.get_files_at(folder):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(folder.path_join(file)))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(folder))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(KIT_FIXTURE.path_join("assets")))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(KIT_FIXTURE))


func _test_shared_territory_kits() -> void:
	var first := KIT_FIXTURE.path_join("first")
	var second := KIT_FIXTURE.path_join("second")
	for folder: String in [first, second]:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	DirAccess.copy_absolute(ProjectSettings.globalize_path(KIT_SOURCE + "kit-cart.glb"),
		ProjectSettings.globalize_path(first.path_join("kit-cart.glb")))
	DirAccess.copy_absolute(ProjectSettings.globalize_path(KIT_SOURCE + "kit-grey-boulder-1.glb"),
		ProjectSettings.globalize_path(second.path_join("kit-grey-boulder-1.glb")))
	var scene_path := KIT_FIXTURE.path_join("new_scene.tscn")
	var catalog_path := KIT_FIXTURE.path_join("catalog.json")
	var binding_path := KIT_FIXTURE.path_join("bindings.json")
	var catalog_file := FileAccess.open(catalog_path, FileAccess.WRITE)
	catalog_file.store_string(JSON.stringify({"entries": [{"scenePath": scene_path}],
		"sharedAssetLibraries": [{"directory": first, "catalogPrefix": "first"},
			{"directory": second, "catalogPrefix": "second"}, {"directory": first}],
		"sharedAssetCatalogPath": binding_path}))
	catalog_file.close()
	var binding_file := FileAccess.open(binding_path, FileAccess.WRITE)
	binding_file.store_string(JSON.stringify({"schema": "eloria-shared-kit-catalog-v1",
		"models": {second.path_join("kit-grey-boulder-1.glb"):
			{"catalogAssetId": "shared:rock", "collisionRole": "none"}}}))
	binding_file.close()
	var setting := "map_authoring/territory_catalog_path"
	var previous: Variant = ProjectSettings.get_setting(setting, "")
	ProjectSettings.set_setting(setting, catalog_path)
	var root := Node3D.new()
	root.scene_file_path = scene_path
	var container := Node3D.new()
	container.name = "AuthoredAssets"
	root.add_child(container)
	var wrapper: Node3D = ASSET_SCRIPT.new()
	wrapper.set("scene_path", first.path_join("kit-cart.glb"))
	wrapper.set("catalog_asset_id", "saved:cart")
	wrapper.set("collision_role", "none")
	container.add_child(wrapper)
	var listed := Catalog.territory_entries(root)
	_expect(listed.size() == 2, "shared kits list both libraries once without a sibling kit")
	var saved := _by_id(listed, "saved:cart")
	_expect(saved.get("category") == Catalog.TERRITORY_SCENERY,
		"a saved shared copy keeps its catalog identity and collision role")
	var unplaced := _by_id(listed, "shared:rock")
	_expect(unplaced.get("scene_path") == second.path_join("kit-grey-boulder-1.glb") and
		unplaced.get("category") == Catalog.TERRITORY_SCENERY,
		"an unplaced shared model keeps its pinned identity and role")
	root.scene_file_path = KIT_FIXTURE.path_join("unregistered.tscn")
	_expect(Catalog.territory_entries(root).is_empty(), "shared kits belong only to registered scenes")
	ProjectSettings.set_setting(setting, previous)
	root.free()
	for folder: String in [first, second]:
		for file: String in DirAccess.get_files_at(folder):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(folder.path_join(file)))
		DirAccess.remove_absolute(ProjectSettings.globalize_path(folder))
	for path: String in [catalog_path, binding_path]:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(KIT_FIXTURE))


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
