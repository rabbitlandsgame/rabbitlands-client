@tool
class_name MapAuthoringTerrainSculptTool
extends RefCounted

signal status_changed(message: String)
signal flatten_height_picked(height: float)
signal stroke_started
signal stroke_ended

const BRUSH := preload("res://src/dev/map_authoring_region/terrain_sculpt_brush.gd")
const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const OWNERSHIP := preload("res://src/dev/map_authoring_region/ownership_source.gd")
const PREVIEW_INTERVAL := 0.14
const RING_SEGMENTS := 48

## Hover rays walk only the grid cells they cross; MapAuthoringTerrainControl's
## own ray test scans the whole height grid, which stalls large territories on
## every mouse move while sculpting.
const PROBE := preload("res://addons/map_authoring_usability/terrain_probe.gd")

var _root: Node3D
var _terrain: MapAuthoringTerrainControl
var _undo_redo: Object
var _entry: Dictionary = {}
var _base := PackedFloat32Array()
var _base_sha := ""
var _locked := PackedByteArray()
var _boundary_weights := PackedFloat32Array()
var _ring: MeshInstance3D
var _ring_mesh: ImmediateMesh
var _ring_material: StandardMaterial3D
var _enabled := false
var _picking_height := false
var _dragging := false
var _changed := false
var _preview_dirty := false
var _before: Resource
var _pending: Resource
var _last_sample := Vector2.INF
var _preview_elapsed := 0.0
var _settings := {}
## A heightmap shown on the terrain but not imported yet, and the layer it
## replaced (see preview_heightmap).
var _heightmap_previewing := false
var _heightmap_original: Resource
var _hover_reason := ""


func bind(root: Node3D, terrain: MapAuthoringTerrainControl,
		entry: Dictionary, undo_redo: Object) -> bool:
	unbind()
	if root == null or terrain == null or undo_redo == null or \
			GEOMETRY.from_entry(entry).is_empty():
		return false
	if not OWNERSHIP.entry_error(root, entry).is_empty():
		return false
	_root = root
	_terrain = terrain
	_entry = entry.duplicate(true)
	_undo_redo = undo_redo
	_base = _terrain.base_heights()
	_base_sha = _terrain.base_sha256()
	var fields := boundary_fields(GEOMETRY.from_entry(_entry),
		_entry.translation, _terrain.origin, _terrain.grid_size,
		_terrain.cell_metres, _root.global_transform.affine_inverse() *
		_terrain.global_transform)
	_locked = fields.locked
	_boundary_weights = fields.weights
	if _locked.size() != _base.size() or _base.is_empty():
		unbind()
		return false
	_ring_mesh = ImmediateMesh.new()
	_ring = MeshInstance3D.new()
	_ring.name = "__TerrainSculptCursor"
	_ring.mesh = _ring_mesh
	_ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_ring_material = StandardMaterial3D.new()
	_ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_ring_material.no_depth_test = true
	_ring_material.albedo_color = Color(0.22, 0.94, 0.79)
	_ring.material_override = _ring_material
	_ring.visible = false
	_terrain.add_child(_ring, false, Node.INTERNAL_MODE_FRONT)
	return true


func unbind() -> void:
	cancel_heightmap_preview()
	cancel_stroke()
	_enabled = false
	_picking_height = false
	if is_instance_valid(_ring):
		_ring.queue_free()
	_ring = null
	_ring_mesh = null
	_ring_material = null
	_root = null
	_terrain = null
	_undo_redo = null
	_entry.clear()
	_base.clear()
	_base_sha = ""
	_locked.clear()
	_boundary_weights.clear()
	_hover_reason = ""


func set_enabled(enabled: bool) -> void:
	if not enabled:
		cancel_stroke()
		_picking_height = false
		if is_instance_valid(_ring):
			_ring.visible = false
	_enabled = enabled and _terrain != null
	if _enabled:
		status_changed.emit("Drag on the active terrain. Borders protected; Alt/RMB/MMB navigate.")
	else:
		_hover_reason = ""


func is_enabled() -> bool:
	return _enabled


func is_dragging() -> bool:
	return _dragging


func pick_flatten_height() -> void:
	if _enabled:
		_picking_height = true
		status_changed.emit("Click editable terrain to sample the flatten target.")


func tick(delta: float) -> void:
	if not _dragging or not is_instance_valid(_terrain):
		return
	# The viewport may miss a mouse release outside its bounds.
	if not Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
		finish_stroke()
		return
	if not _preview_dirty:
		return
	_preview_elapsed += delta
	if _preview_elapsed >= PREVIEW_INTERVAL:
		if _terrain.apply_sculpt_layer(_pending):
			_preview_dirty = false
		_preview_elapsed = 0.0


func handle_input(camera: Camera3D, event: InputEvent,
		settings: Dictionary) -> int:
	if not _enabled or not is_instance_valid(_terrain) or camera == null:
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventKey and event.pressed and not event.echo and \
			event.ctrl_pressed and event.keycode in [KEY_S, KEY_Z, KEY_Y]:
		if _dragging:
			finish_stroke()
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventKey and event.pressed and not event.echo and \
			event.keycode == KEY_ESCAPE:
		if _dragging:
			cancel_stroke()
		elif _picking_height:
			_picking_height = false
		else:
			return EditorPlugin.AFTER_GUI_INPUT_PASS
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	if event is InputEventMouseMotion:
		if event.alt_pressed or (_dragging and \
			(event.button_mask & MOUSE_BUTTON_MASK_LEFT) == 0):
			if _dragging:
				finish_stroke()
			return EditorPlugin.AFTER_GUI_INPUT_PASS
		var active_settings: Dictionary = _settings if _dragging else settings
		var hover := _hover(camera, event.position,
			float(active_settings.get("radius", 8.0)))
		if _dragging:
			if hover.ok:
				_sample_drag(hover.hit, _settings)
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		var reason := "" if hover.ok else String(hover.reason)
		if reason != _hover_reason:
			_hover_reason = reason
			status_changed.emit(reason if not reason.is_empty() else
				"Ready to sculpt the active terrain. Borders protected.")
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventMouseButton:
		if event.button_index in [MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE]:
			if event.pressed and _dragging:
				finish_stroke()
			return EditorPlugin.AFTER_GUI_INPUT_PASS
		if event.button_index != MOUSE_BUTTON_LEFT or event.alt_pressed:
			if event.alt_pressed and _dragging:
				finish_stroke()
			return EditorPlugin.AFTER_GUI_INPUT_PASS
		if not event.pressed:
			if _dragging:
				finish_stroke()
				return EditorPlugin.AFTER_GUI_INPUT_STOP
			return EditorPlugin.AFTER_GUI_INPUT_PASS
		var hover := _hover(camera, event.position, float(settings.get("radius", 8.0)))
		if not hover.ok:
			status_changed.emit(String(hover.reason))
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if _picking_height:
			_picking_height = false
			flatten_height_picked.emit(_terrain.to_local(hover.hit).y)
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		_start_stroke(hover.hit, settings)
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	return EditorPlugin.AFTER_GUI_INPUT_PASS


func _start_stroke(hit: Vector3, settings: Dictionary) -> void:
	_before = _terrain.sculpt_layer
	_pending = _before
	_settings = settings.duplicate(true)
	_last_sample = Vector2.INF
	_changed = false
	_preview_dirty = false
	_preview_elapsed = 0.0
	_dragging = true
	stroke_started.emit()
	_sample_drag(hit, _settings)


func _sample_drag(hit: Vector3, settings: Dictionary) -> void:
	var local := _terrain.to_local(hit)
	var at := Vector2(local.x, local.z)
	var spacing := maxf(_terrain.cell_metres * 0.5,
		float(settings.get("radius", 8.0)) * 0.18)
	if _last_sample.is_finite() and at.distance_to(_last_sample) < spacing:
		return
	var start := _last_sample if _last_sample.is_finite() else at
	var count := clampi(ceili(start.distance_to(at) / spacing), 1, 32)
	for step in range(1, count + 1):
		var point := start.lerp(at, float(step) / float(count))
		var candidate: Resource = BRUSH.apply_stamp(_base, _pending,
			_base_sha, _terrain.origin, _terrain.grid_size,
			_terrain.cell_metres, point, int(settings.get("mode", 0)),
			float(settings.get("radius", 8.0)),
			float(settings.get("strength", 0.35)),
			float(settings.get("softness", 0.65)),
			float(settings.get("flatten_target", NAN)), _locked,
			_boundary_weights)
		if candidate != null:
			_pending = candidate
			_changed = true
			_preview_dirty = true
	_last_sample = at


func finish_stroke() -> void:
	if not _dragging:
		return
	_dragging = false
	if _changed and is_instance_valid(_terrain) and is_instance_valid(_root):
		if _preview_dirty and not _terrain.apply_sculpt_layer(_pending):
			_terrain.apply_sculpt_layer(_before)
			_clear_stroke()
			stroke_ended.emit()
			status_changed.emit("Terrain preview could not be applied; stroke cancelled.")
			return
		if _undo_redo is EditorUndoRedoManager:
			_undo_redo.create_action("Sculpt terrain", UndoRedo.MERGE_DISABLE,
				_root)
		else:
			_undo_redo.create_action("Sculpt terrain", UndoRedo.MERGE_DISABLE)
		_undo_redo.add_do_method(_terrain, &"apply_sculpt_layer", _pending)
		_undo_redo.add_undo_method(_terrain, &"apply_sculpt_layer", _before)
		# The pending preview is already current; a second do would rebuild it.
		_undo_redo.commit_action(false)
		status_changed.emit("Terrain sculpt saved in this scene's undo history. Ctrl+S saves it.")
	else:
		status_changed.emit("No editable terrain sample changed.")
	_clear_stroke()
	stroke_ended.emit()


func cancel_stroke() -> void:
	if not _dragging:
		return
	if _changed and is_instance_valid(_terrain):
		_terrain.apply_sculpt_layer(_before)
	_clear_stroke()
	stroke_ended.emit()
	status_changed.emit("Terrain stroke cancelled; no undo step was added.")


func _clear_stroke() -> void:
	_dragging = false
	_changed = false
	_preview_dirty = false
	_before = null
	_pending = null
	_last_sample = Vector2.INF
	_settings.clear()
	_preview_elapsed = 0.0


## The bound territory's border protection, for other editor tools that write
## terrain (the plateau stamp): {locked, weights, origin, grid, cell, polygon
## (territory-local)}, or empty when no editable territory is bound.
func protection_fields() -> Dictionary:
	if _terrain == null or not is_instance_valid(_terrain) or _locked.is_empty():
		return {}
	var translation: Vector3 = _entry.get("translation", Vector3.ZERO)
	var polygons := GEOMETRY.local(GEOMETRY.from_entry(_entry), translation)
	var polygon := polygons[0] if not polygons.is_empty() else PackedVector2Array()
	return {"locked": _locked, "weights": _boundary_weights, "origin": _terrain.origin,
		"grid": _terrain.grid_size, "cell": _terrain.cell_metres, "polygon": polygon, "polygons": polygons,
		"terrain": _terrain}


## Imports a greyscale heightmap into the sparse sculpt layer as one undo step.
## `area` is the terrain-local X/Z rectangle the image covers, north (smaller Z)
## at the top row; black maps to `low` metres and white to `high`. Replace sets
## editable samples to that height; Offset adds it to what is there. Borders are
## protected as for the brush: locked samples never change, the fade band is
## blended, and the original base heights are never rewritten. Returns
## {"changed": n} or {"error"}.
func import_heightmap(image: Image, area: Rect2, low: float, high: float,
		replace: bool) -> Dictionary:
	if _terrain == null or not is_instance_valid(_terrain) or _base.is_empty():
		return {"error": "Open an editable territory from the Territories dock first."}
	if _dragging:
		return {"error": "Finish the current stroke first."}
	# A preview is put back first, so the undo step returns to the ground as it was.
	cancel_heightmap_preview()
	var current: Resource = _terrain.sculpt_layer
	var result := _heightmap_layer(image, area, low, high, replace, current)
	if result.has("error"):
		return result
	var layer: Resource = result.layer
	if _undo_redo is EditorUndoRedoManager:
		_undo_redo.create_action("Import heightmap", UndoRedo.MERGE_DISABLE, _root)
	else:
		_undo_redo.create_action("Import heightmap", UndoRedo.MERGE_DISABLE)
	_undo_redo.add_do_method(_terrain, &"apply_sculpt_layer", layer)
	_undo_redo.add_undo_method(_terrain, &"apply_sculpt_layer", current)
	_undo_redo.commit_action()
	status_changed.emit("Heightmap imported into the sculpt layer: %d samples changed, %d protected." % [
		int(result.changed), int(result.protected)])
	return {"changed": result.changed, "protected": result.protected}


## Shows what import_heightmap would do on the terrain, without an undo step or
## any change to the saved layer: import_heightmap keeps it (as one undo step),
## cancel_heightmap_preview puts the ground back. Previewing again replaces the
## previous preview. Returns {"changed", "protected"} or {"error"}.
func preview_heightmap(image: Image, area: Rect2, low: float, high: float,
		replace: bool) -> Dictionary:
	if _terrain == null or not is_instance_valid(_terrain) or _base.is_empty():
		return {"error": "Open an editable territory from the Territories dock first."}
	if _dragging:
		return {"error": "Finish the current stroke first."}
	var original: Resource = _heightmap_original if _heightmap_previewing else _terrain.sculpt_layer
	var result := _heightmap_layer(image, area, low, high, replace, original)
	if result.has("error"):
		return result
	if not _heightmap_previewing:
		_heightmap_original = original
		_heightmap_previewing = true
	_terrain.apply_sculpt_layer(result.layer)
	status_changed.emit(("Previewing the heightmap: %d samples change, %d protected. Import keeps " +
		"it as one undo step; Cancel puts the ground back.") % [int(result.changed),
		int(result.protected)])
	return {"changed": result.changed, "protected": result.protected}


func is_previewing_heightmap() -> bool:
	return _heightmap_previewing


## Puts the ground back as it was before preview_heightmap.
func cancel_heightmap_preview() -> void:
	if not _heightmap_previewing:
		return
	_heightmap_previewing = false
	if _terrain != null and is_instance_valid(_terrain):
		_terrain.apply_sculpt_layer(_heightmap_original)
	_heightmap_original = null


## The sculpt layer a heightmap import makes from `current`, with its counts,
## or {"error"}.
func _heightmap_layer(image: Image, area: Rect2, low: float, high: float, replace: bool,
		current: Resource) -> Dictionary:
	var result := heightmap_layer_deltas(image, area, low, high, replace, _base,
		current.indices if current != null else PackedInt32Array(),
		current.deltas if current != null else PackedFloat32Array(),
		_locked, _boundary_weights, _terrain.origin, _terrain.grid_size, _terrain.cell_metres)
	if result.has("error"):
		return result
	var layer: Resource = current.copy_with(result.indices, result.deltas) \
		if current != null else null
	if layer == null:
		layer = load("res://src/dev/map_authoring_region/terrain_sculpt_layer.gd").new()
		layer.bind_base(_base_sha, _terrain.origin, _terrain.grid_size, _terrain.cell_metres)
		layer.indices = result.indices
		layer.deltas = result.deltas
	var error: String = layer.validation_error(_base_sha, _terrain.origin, _terrain.grid_size,
		_terrain.cell_metres)
	if not error.is_empty():
		return {"error": error}
	return {"layer": layer, "changed": result.changed, "protected": result.protected}


## The pure heightmap-to-sculpt-layer computation behind import_heightmap.
static func heightmap_layer_deltas(image: Image, area: Rect2, low: float, high: float,
		replace: bool, base: PackedFloat32Array, indices: PackedInt32Array,
		deltas: PackedFloat32Array, locked: PackedByteArray, weights: PackedFloat32Array,
		origin: Vector2, grid: Vector2i, cell: float) -> Dictionary:
	if image == null or image.is_empty():
		return {"error": "The heightmap image could not be read."}
	if area.size.x <= 0.0 or area.size.y <= 0.0 or not is_finite(low) or not is_finite(high):
		return {"error": "Give the heightmap a positive area and finite metre heights."}
	var samples := image.duplicate() as Image
	if samples.is_compressed():
		samples.decompress()
	samples.convert(Image.FORMAT_RF)
	var width := samples.get_width()
	var height := samples.get_height()
	var existing := PackedFloat32Array()
	existing.resize(grid.x * grid.y)
	for offset in indices.size():
		existing[indices[offset]] = deltas[offset]
	var changed := 0
	var protected := 0
	for z in grid.y:
		for x in grid.x:
			var index := z * grid.x + x
			var point := Vector2(origin.x + float(x) * cell, origin.y + float(z) * cell)
			if point.x < area.position.x - 0.0001 or point.x > area.end.x + 0.0001 or \
					point.y < area.position.y - 0.0001 or point.y > area.end.y + 0.0001:
				continue
			if locked[index] != 0 or weights[index] <= 0.0:
				protected += 1
				continue
			# Pixel centres: pixel i covers [i, i+1) of width in image space.
			var u := clampf((point.x - area.position.x) / area.size.x * float(width) - 0.5,
				0.0, float(width - 1))
			var v := clampf((point.y - area.position.y) / area.size.y * float(height) - 0.5,
				0.0, float(height - 1))
			var x0 := floori(u)
			var y0 := floori(v)
			var x1 := mini(x0 + 1, width - 1)
			var y1 := mini(y0 + 1, height - 1)
			var fx := u - float(x0)
			var fy := v - float(y0)
			var value := lerpf(lerpf(samples.get_pixel(x0, y0).r, samples.get_pixel(x1, y0).r, fx),
				lerpf(samples.get_pixel(x0, y1).r, samples.get_pixel(x1, y1).r, fx), fy)
			var metres := lerpf(low, high, value)
			var before := existing[index]
			var after := lerpf(before, metres - base[index], weights[index]) if replace \
				else before + metres * weights[index]
			if absf(after) > 4096.0 or not is_finite(after):
				return {"error": "The heightmap would move the ground more than 4096 m."}
			if not is_equal_approx(after, before):
				changed += 1
			existing[index] = after
	var new_indices := PackedInt32Array()
	var new_deltas := PackedFloat32Array()
	for index in existing.size():
		if absf(existing[index]) > 0.000001:
			new_indices.append(index)
			new_deltas.append(existing[index])
	return {"indices": new_indices, "deltas": new_deltas, "changed": changed,
		"protected": protected}


## Tints the brush ring so the active brush reads at a glance.
func set_ring_color(color: Color) -> void:
	if _ring_material != null:
		_ring_material.albedo_color = color


func _hover(camera: Camera3D, position: Vector2, radius: float) -> Dictionary:
	var hit: Variant = PROBE.ray_hit(_root, camera.project_ray_origin(position),
		camera.project_ray_normal(position), 4096.0)
	if not hit is Vector3:
		_ring.visible = false
		return {"ok": false, "reason": "Brush ray missed the active terrain."}
	var local: Vector3 = _terrain.to_local(hit)
	var x := roundi((local.x - _terrain.origin.x) / _terrain.cell_metres)
	var z := roundi((local.z - _terrain.origin.y) / _terrain.cell_metres)
	if x < 0 or z < 0 or x >= _terrain.grid_size.x or z >= _terrain.grid_size.y:
		_ring.visible = false
		return {"ok": false, "reason": "Outside the active terrain grid."}
	var index := z * _terrain.grid_size.x + x
	if _locked[index] != 0 or _boundary_weights[index] <= 0.0:
		_ring.visible = false
		return {"ok": false, "reason": "Borders protected: move the brush inside the editable area."}
	_draw_ring(local, radius)
	return {"ok": true, "hit": hit}


func _draw_ring(local: Vector3, radius: float) -> void:
	_ring_mesh.clear_surfaces()
	_ring_mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
	for index in range(RING_SEGMENTS + 1):
		var angle := TAU * float(index) / float(RING_SEGMENTS)
		var x := local.x + cos(angle) * radius
		var z := local.z + sin(angle) * radius
		var y := _terrain.height_at_local(x, z)
		_ring_mesh.surface_add_vertex(Vector3(x,
			y + 0.15 if is_finite(y) else local.y + 0.15, z))
	_ring_mesh.surface_end()
	_ring.visible = true


static func boundary_fields(polygon: Variant,
		translation: Vector3, origin: Vector2, grid: Vector2i,
		cell: float, terrain_to_root := Transform3D.IDENTITY) -> Dictionary:
	var locked := PackedByteArray()
	var weights := PackedFloat32Array()
	var polygons := GEOMETRY.polygons(polygon)
	if polygons.is_empty() or grid.x < 2 or grid.y < 2 or cell <= 0.0:
		return {"locked": locked, "weights": weights}
	locked.resize(grid.x * grid.y)
	weights.resize(locked.size())
	var hard := 2.0 * cell
	var fade := 2.0 * cell
	for z in grid.y:
		for x in grid.x:
			var index := z * grid.x + x
			if x < 2 or z < 2 or x >= grid.x - 2 or z >= grid.y - 2:
				locked[index] = 1
				continue
			var local := Vector3(origin.x + float(x) * cell, 0.0,
				origin.y + float(z) * cell)
			var root_point: Vector3 = terrain_to_root * local
			var point := Vector2(root_point.x + translation.x,
				root_point.z + translation.z)
			if not GEOMETRY.contains(point, polygons):
				locked[index] = 1
				continue
			var distance := GEOMETRY.edge_distance(point, polygons)
			if distance <= hard:
				locked[index] = 1
				continue
			var amount := clampf((distance - hard) / fade, 0.0, 1.0)
			weights[index] = amount * amount * (3.0 - 2.0 * amount)
	return {"locked": locked, "weights": weights}
