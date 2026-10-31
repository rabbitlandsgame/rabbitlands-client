extends RefCounted
## Lantern Mine's ordinary atmosphere, independent of campaign progress.
## Landfall Underground contains many disjoint interiors; only these named
## levels receive the lantern-lit environment. Published map lights are reused.
const SECTION := "lantern_mine"
const SECTIONS := ["lantern_upper_galleries", SECTION, "old_seam"]
const MAP := "landfall_insides"
const AMBIENT_ENERGY := 0.015
const LANTERN_ENERGY := 2.4
const LANTERN_RANGE := 16.0
const COMPATIBILITY_LIGHT_LIMIT := 8
var lamps: Array[OmniLight3D] = []
var _owner: WeakRef
var _original: Environment
var _dark: Environment
var _directionals: Dictionary = {}
var _markers: Dictionary = {}
var _marker_root: WeakRef
var _marker_section := ""
var _cinematic_manifest: WorldManifest
var _cinematic_focus := Vector3.ZERO
var _cinematic_markers: WeakRef

func set_cinematic_region(manifest: WorldManifest, focus: Vector3, markers: Node3D = null) -> bool:
	# A remote cutaway may stand in the published mine while the real player
	# remains outdoors. Its actual stage focus, not the player, selects lighting.
	if manifest == null or manifest.asset_id() != MAP or section_at(manifest, focus) not in SECTIONS:
		clear_cinematic_region()
		return false
	_cinematic_manifest = manifest
	_cinematic_focus = focus
	_cinematic_markers = weakref(markers) if is_instance_valid(markers) else null
	return true

func clear_cinematic_region() -> void:
	_cinematic_manifest = null
	_cinematic_markers = null

static func section_at(manifest: WorldManifest, point: Vector3) -> String:
	if manifest == null or not point.is_finite(): return ""
	for entry: Dictionary in manifest.data.get("sections", []):
		var bounds: Dictionary = entry.get("bounds", {})
		var lo: Array = bounds.get("min", [])
		var hi: Array = bounds.get("max", [])
		if lo.size() < 2 or hi.size() < 2: continue
		if point.x >= float(lo[0]) and point.x <= float(hi[0]) and point.z >= float(lo[1]) and point.z <= float(hi[1]):
			return str(entry.get("id", ""))
	return ""

func wants_mine(manifest: WorldManifest, section: String) -> bool:
	if _cinematic_manifest != null:
		manifest = _cinematic_manifest
		section = section_at(manifest, _cinematic_focus)
	return manifest != null and manifest.asset_id() == MAP and section in SECTIONS

func before_regrade(manifest: WorldManifest, section: String) -> void:
	# Restore the ordinary resource before its normal clock/grade is evaluated.
	if not wants_mine(manifest, section): _restore()

func apply(manifest: WorldManifest, section: String, owner: WorldEnvironment,
		sun: DirectionalLight3D = null, moon: DirectionalLight3D = null,
		markers: Node3D = null, focus := Vector3.INF) -> void:
	if not wants_mine(manifest, section) or not is_instance_valid(owner):
		_restore()
		return
	var previous := _owner.get_ref() as WorldEnvironment if _owner != null else null
	if previous != owner: _restore()
	_owner = weakref(owner)
	if owner.environment != _dark or _dark == null:
		_original = owner.environment
		_dark = _original.duplicate(true) if _original != null else Environment.new()
	owner.environment = _dark
	_dark.background_mode = Environment.BG_COLOR
	_dark.background_color = Color("080a13")
	_dark.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_dark.ambient_light_color = Color("59616f")
	_dark.ambient_light_energy = AMBIENT_ENERGY
	_dark.ambient_light_sky_contribution = 0.0
	_dark.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
	_dark.sdfgi_enabled = false
	_dark.ssil_enabled = false
	_dark.fog_enabled = false
	for light: DirectionalLight3D in [sun, moon]:
		if not is_instance_valid(light): continue
		var key := light.get_instance_id()
		if not _directionals.has(key) or not is_zero_approx(light.light_energy):
			_directionals[key] = {"node":weakref(light), "energy":light.light_energy}
		light.light_energy = 0.0
	if _cinematic_manifest != null:
		markers = _cinematic_markers.get_ref() as Node3D if _cinematic_markers != null else null
	_apply_markers(markers, section_at(_cinematic_manifest, _cinematic_focus) if _cinematic_manifest != null else section)
	if _cinematic_manifest != null: focus = _cinematic_focus
	if RenderingServer.get_current_rendering_method() == "gl_compatibility" and focus.is_finite():
		limit_lamps(focus)

func _apply_markers(root: Node3D, section: String) -> void:
	var previous := _marker_root.get_ref() as Node3D if _marker_root != null else null
	if previous != root or _marker_section != section: _restore_markers()
	if not is_instance_valid(root): return
	_marker_root = weakref(root)
	_marker_section = section
	lamps.clear()
	for node: Node in root.find_children("*", "OmniLight3D", true, false):
		if not node is OmniLight3D: continue
		var light := node as OmniLight3D
		var lamp := str(light.name).begins_with(section + "-lamp-")
		var daylight := str(light.name) == section + "-daylight"
		if not lamp and not daylight: continue
		var key := light.get_instance_id()
		if not _markers.has(key):
			_markers[key] = {"node":weakref(light), "energy":light.light_energy,
				"range":light.omni_range, "color":light.light_color, "mask":light.light_cull_mask}
		# Do not write visibility: SecretSections owns whether a room is shown.
		light.light_energy = LANTERN_ENERGY if lamp else 0.0
		light.light_cull_mask = int(_markers[key].mask) if lamp else 0
		if lamp:
			light.omni_range = LANTERN_RANGE
			light.light_color = Color(1.0, 0.7, 0.4)
			lamps.append(light)

func limit_lamps(focus: Vector3) -> void:
	# Compatibility allows eight lights per mesh. A level's floor is one mesh,
	# so distant lamps otherwise consume its entire budget and black out the
	# room being played. A separate parent gate preserves SecretSections' own
	# light visibility; mask=0 alone still consumes a GLES per-mesh light slot.
	var nearest := lamps.duplicate()
	nearest.sort_custom(func(a: OmniLight3D, b: OmniLight3D) -> bool:
		return a.global_position.distance_squared_to(focus) < b.global_position.distance_squared_to(focus))
	for index in nearest.size():
		var light: OmniLight3D = nearest[index]
		var row: Dictionary = _markers[light.get_instance_id()]
		if not row.has("gate"):
			var parent := light.get_parent() as Node3D
			var gate := Node3D.new()
			gate.name = "MineLightGate_" + str(light.name)
			parent.add_child(gate)
			light.reparent(gate)
			row["parent"] = weakref(parent)
			row["gate"] = weakref(gate)
		var gate := (row.gate as WeakRef).get_ref() as Node3D
		gate.visible = index < COMPATIBILITY_LIGHT_LIMIT

func is_active() -> bool:
	var owner := _owner.get_ref() as WorldEnvironment if _owner != null else null
	return is_instance_valid(owner) and _dark != null and owner.environment == _dark

func _restore_markers() -> void:
	for row: Dictionary in _markers.values():
		var light := (row.node as WeakRef).get_ref() as OmniLight3D
		if is_instance_valid(light):
			if row.has("gate"):
				var parent := (row.parent as WeakRef).get_ref() as Node3D
				var gate := (row.gate as WeakRef).get_ref() as Node3D
				if is_instance_valid(parent): light.reparent(parent)
				if is_instance_valid(gate): gate.queue_free()
			light.light_energy = float(row.energy)
			light.omni_range = float(row.range)
			light.light_color = row.color
			light.light_cull_mask = int(row.mask)
	_markers.clear(); lamps.clear(); _marker_root = null; _marker_section = ""

func _restore() -> void:
	var owner := _owner.get_ref() as WorldEnvironment if _owner != null else null
	if is_instance_valid(owner) and owner.environment == _dark: owner.environment = _original
	for row: Dictionary in _directionals.values():
		var light := (row.node as WeakRef).get_ref() as DirectionalLight3D
		if is_instance_valid(light): light.light_energy = float(row.energy)
	_directionals.clear(); _owner = null; _original = null; _dark = null
	_restore_markers()

func clear() -> void:
	_restore()
	clear_cinematic_region()
