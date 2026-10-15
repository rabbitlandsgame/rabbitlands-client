@tool
extends RefCounted
## Editor-only time-of-day lighting for authored territories.
##
## Builds the lighting the game would show: the territory's published manifest
## is the noon reference, bound with WorldEnvironmentBinder, then moved to the
## chosen game minute with DayNightBinder (the server's own daylight curve;
## 360 minutes a day, noon at minute 180, shown as 3:00 like the in-game clock).
##
## The sun, moon and environment are internal, ownerless children of the edited
## root, so they are never saved or baked. Scenes that save their own Sun or
## WorldEnvironment (the pilot) are left alone: those are authored lighting,
## not a preview.

const CATALOG_PATH := "res://world_authoring/territories.json"
const NODE_NAME := "__MapAuthoringTimeOfDay"
const MINUTES_PER_DAY := 360.0
const PRESETS := {"Midnight": 0.0, "Dawn": 90.0, "Noon": 180.0, "Dusk": 270.0}
## Used when a territory has no readable manifest: a plain clear day.
const FALLBACK_ENVIRONMENT := {
	"sky": {"topColor": "3d7ec2", "horizonColor": "bcc9cd"},
	"sun": {"rotationDegrees": [-55.0, 35.0, 0.0], "energy": 1.2, "shadows": true},
	"ambient": {"energy": 0.85},
}

var _root: Node3D
var _holder: Node3D
var _environment: WorldEnvironment
var _sun: DirectionalLight3D
var _moon: DirectionalLight3D
var _manifest: WorldManifest
var _minute := 180.0
var manifest_path := ""
var last_message := ""


func is_active() -> bool:
	return is_instance_valid(_holder) and _holder.is_inside_tree()


func minute() -> float:
	return _minute


func nodes() -> Node3D:
	return _holder if is_instance_valid(_holder) else null


## Shows the preview on `root` at `game_minute`. Returns false (with
## last_message explaining why) when the scene saves its own lighting.
func enable(root: Node3D, game_minute: float) -> bool:
	disable()
	if root == null:
		last_message = "Open a map authoring scene first."
		return false
	var saved := saved_lighting(root)
	if not saved.is_empty():
		last_message = ("This scene saves its own %s; edit those nodes instead. The time-of-day " +
			"preview only covers territories lit by their published manifest.") % \
			" and ".join(saved)
		return false
	_root = root
	_manifest = _load_manifest(root)
	_holder = Node3D.new()
	_holder.name = NODE_NAME
	_environment = WorldEnvironment.new()
	_environment.name = "Environment"
	_sun = DirectionalLight3D.new()
	_sun.name = "Sun"
	_moon = DirectionalLight3D.new()
	_moon.name = "Moon"
	for node: Node in [_environment, _sun, _moon]:
		_holder.add_child(node)
	# A parent outside the tree makes the binder skip manifest lamps; its lamp
	# pass would otherwise free every "manifest_lights" node in the editor.
	var detached := Node.new()
	WorldEnvironmentBinder.apply(_manifest, _environment, _sun, detached)
	detached.free()
	root.add_child(_holder, false, Node.INTERNAL_MODE_BACK)
	set_minute(game_minute)
	return true


func set_minute(game_minute: float) -> void:
	_minute = fposmod(game_minute, MINUTES_PER_DAY)
	if not is_active():
		return
	if not DayNightBinder.apply(_manifest, _environment, _sun, _minute, _moon):
		# The manifest opts out of the day/night cycle: keep its authored noon.
		_moon.visible = false
		last_message = "This territory's manifest keeps a fixed daylight; showing it unchanged."
	else:
		last_message = "Previewing %s. Editor only; never saved or baked." % describe(_minute)


func disable() -> void:
	if is_instance_valid(_holder):
		if _holder.get_parent() != null:
			_holder.get_parent().remove_child(_holder)
		_holder.queue_free()
	_holder = null
	_environment = null
	_sun = null
	_moon = null
	_root = null


## Saved (owned) lights the scene authors itself, e.g. the pilot's Sun.
static func saved_lighting(root: Node) -> PackedStringArray:
	var found := PackedStringArray()
	if not root.find_children("*", "DirectionalLight3D", true, true).is_empty():
		found.append("Sun (DirectionalLight3D)")
	if not root.find_children("*", "WorldEnvironment", true, true).is_empty():
		found.append("WorldEnvironment")
	return found


## "3:00 noon"-style label in the game's own clock (60 minutes per hour).
static func describe(game_minute: float) -> String:
	var whole := int(floorf(fposmod(game_minute, MINUTES_PER_DAY)))
	var light := DayNightBinder.daylight(game_minute)
	var phase := "night"
	if light > 0.85:
		phase = "midday"
	elif light > 0.15:
		phase = "morning" if fposmod(game_minute, MINUTES_PER_DAY) < 180.0 else "evening"
	for preset: String in PRESETS:
		if absf(float(PRESETS[preset]) - fposmod(game_minute, MINUTES_PER_DAY)) < 0.5:
			phase = preset.to_lower()
	return "%d:%02d %s" % [whole / 60, whole % 60, phase]


func _load_manifest(root: Node3D) -> WorldManifest:
	manifest_path = manifest_path_for(String(root.get("region_id")))
	if not manifest_path.is_empty():
		var loaded := WorldManifest.load_file(manifest_path)
		if loaded.data.get("environment") is Dictionary:
			return loaded
	manifest_path = ""
	var fallback := WorldManifest.new()
	fallback.data = {"environment": FALLBACK_ENVIRONMENT.duplicate(true)}
	return fallback


## The territory's entry in the catalog the editor reads (the project setting
## map_authoring/territory_catalog_path, see territory_catalog.gd), else in the
## shared catalog; {} when neither lists it.
static func catalog_entry(region_id: String) -> Dictionary:
	if region_id.is_empty():
		return {}
	var catalogs: Array[String] = []
	var configured := String(ProjectSettings.get_setting(
		"map_authoring/territory_catalog_path", "")).strip_edges()
	if not configured.is_empty() and configured != CATALOG_PATH:
		catalogs.append(configured)
	catalogs.append(CATALOG_PATH)
	for catalog in catalogs:
		if not FileAccess.file_exists(catalog):
			continue
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(catalog))
		if not parsed is Dictionary:
			continue
		for value: Variant in (parsed as Dictionary).get("entries", []):
			if value is Dictionary and String((value as Dictionary).get("id", "")) == region_id:
				return value
	return {}


## The territory's manifest: its catalog entry's manifestPath. For a legacy
## territory that is its published package; for a continent-v2 territory it is
## the bootstrap's stub (frame, ownership, environment), which never carries a
## served grid, a collision block or a minimap. "" when the file is missing.
static func manifest_path_for(region_id: String) -> String:
	return _existing(String(catalog_entry(region_id).get("manifestPath", "")))


## The territory's published package: its catalog entry's publishedManifestPath
## when it names one (a continent-v2 territory's client/world.json, where
## _continent_v2/publish_client.py writes the served grid, the collision block
## and the minimap), else its manifestPath (a legacy manifest is its package).
## "" when that file is missing: an unpublished territory has no package yet.
static func published_manifest_path_for(region_id: String) -> String:
	var entry := catalog_entry(region_id)
	if entry.has("publishedManifestPath"):
		return _existing(String(entry.publishedManifestPath))
	return _existing(String(entry.get("manifestPath", "")))


static func _existing(path: String) -> String:
	return path if not path.is_empty() and FileAccess.file_exists(path) else ""
