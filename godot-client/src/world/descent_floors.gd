extends RefCounted
## The procedural descent floors of the map the player is on (descent_layout_v1).
##
## A procedural descent's map is a frame (its world.json states `descentFrame`)
## with nothing drawn on it: every floor of a run is built here from the
## server's layout (DescentFloorBuilder) when its layout arrives or the frame
## loads, under the frame's own scene root in one `DescentFloors` node that
## remembers whose run it is. A different run's floors are thrown away, so a
## frame parked by WorldPark and taken back for the next run never shows the
## last run's floors.
##
## A built floor joins the frame's own configuration as a baked floor did:
## its rock faces and stair mouths are added to the manifest's cutaway walls
## and its lamps to its light markers (each tagged RUNTIME_KEY, and removed
## again whenever the floors change), and its picture is the minimap's and full
## map's for its section. Main re-runs the cutaway, sections, lights, fade and
## pictures after a change (`sync` returns true).

const Builder := preload("res://src/world/descent_floor_builder.gd")
const NODE_NAME := "DescentFloors"
## Tags the manifest entries this adds (cutaway walls, light markers).
const RUNTIME_KEY := "descentRuntime"

var _themes: Dictionary = {}
var _root_id := 0
var _run := ""
var _floors: Dictionary = {}       # section -> {walls, markers, picture (Texture2D), extent}
var _prepared := false


## Whether `manifest` is a procedural descent's frame.
static func applies(manifest: WorldManifest) -> bool:
	return manifest != null and manifest.data.get("descentFrame") is Dictionary


func themes() -> Dictionary:
	if _themes.is_empty():
		_themes = Builder.load_themes()
	return _themes


## Builds the floors of `run` whose `layouts` (section -> decoded layout) the
## frame does not show yet, under `map_root`, and drops another run's.
## Returns true when what is drawn changed.
func sync(map_root: Node3D, manifest: WorldManifest, adapter: CoordinateAdapter,
		layouts: Dictionary, run: String, models := true) -> bool:
	if map_root == null or not applies(manifest) or adapter == null:
		return false
	var node := map_root.get_node_or_null(NODE_NAME) as Node3D
	var changed := false
	if node != null and (str(node.get_meta("run", "")) != run or layouts.is_empty()):
		map_root.remove_child(node)
		node.queue_free()
		node = null
		changed = true
	if map_root.get_instance_id() != _root_id or node == null:
		# A new frame (or one taken back from the park): what it holds is
		# what the floors node under it holds.
		_root_id = map_root.get_instance_id()
		_floors.clear()
	_run = run
	if layouts.is_empty():
		if changed:
			_merge(manifest)
		return changed
	if node == null:
		node = Node3D.new()
		node.name = NODE_NAME
		node.set_meta("run", run)
		map_root.add_child(node)
	for section: Variant in layouts:
		var id := str(section)
		if _floors.has(id) and node.has_node("Section_%s_floor" % id):
			continue
		if models and not _prepared:
			_prepare_models()
		var built := Builder.build(layouts[section] as Dictionary, themes(), adapter, models)
		if built.is_empty():
			push_warning("Descent floor %s: its layout could not be drawn" % id)
			continue
		var old := node.get_node_or_null("Section_%s_floor" % id)
		if old != null:
			node.remove_child(old)
			old.queue_free()
		node.add_child(built.root as Node3D)
		var picture: Image = built.picture
		_floors[id] = {"walls": built.walls, "markers": built.markers,
			"picture": ImageTexture.create_from_image(picture) if picture != null else null,
			"extent": built.extent}
		changed = true
	if changed:
		_merge(manifest)
	return changed


## The minimap's and full map's picture for `section`, as the map background
## catalog gives one ({texture, extent}); {} when no floor of it is built.
func picture(section: String) -> Dictionary:
	var built: Dictionary = _floors.get(section, {}) as Dictionary
	if built.is_empty() or built.picture == null:
		return {}
	return {"texture": built.picture, "extent": built.extent}


func built_sections() -> PackedStringArray:
	return PackedStringArray(_floors.keys())


func clear() -> void:
	_floors.clear()
	_root_id = 0
	_run = ""


## Kit models are parsed once a session, as the underground scenery's are.
func _prepare_models() -> void:
	_prepared = true
	var paths := Builder.asset_paths(themes())
	if not GlbSceneCache.prepare_bound_main(paths):
		var prepared := GlbSceneCache.prepare(GlbSceneCache.missing(paths))
		GlbSceneCache.install_prepared(prepared)


## The manifest's cutaway walls and light markers, with this run's floors'
## in place of whatever an earlier sync added.
func _merge(manifest: WorldManifest) -> void:
	var data: Dictionary = manifest.data
	if not data.get("cutaway") is Dictionary:
		data["cutaway"] = {}
	var cutaway: Dictionary = data.cutaway
	var walls: Array = []
	for entry: Variant in cutaway.get("walls", []) as Array:
		if not (entry is Dictionary and bool((entry as Dictionary).get(RUNTIME_KEY, false))):
			walls.append(entry)
	if not data.get("lighting") is Dictionary:
		data["lighting"] = {}
	var lighting: Dictionary = data.lighting
	var markers: Array = []
	for entry: Variant in lighting.get("markers", []) as Array:
		if not (entry is Dictionary and bool((entry as Dictionary).get(RUNTIME_KEY, false))):
			markers.append(entry)
	for built: Dictionary in _floors.values():
		for wall: Dictionary in built.walls:
			walls.append(wall.merged({RUNTIME_KEY: true}))
		for marker: Dictionary in built.markers:
			markers.append(marker.merged({RUNTIME_KEY: true}))
	cutaway["walls"] = walls
	lighting["markers"] = markers
