@tool
extends RefCounted
## Review notes: editor-only comments pinned to spots in a territory, kept in
## an unreferenced sibling of the region scene, <region>.editor-notes.json, in
## the map team's proposed eloria-editor-notes-v1 format:
##
##   {"schema": "eloria-editor-notes-v1", "regionId": "verdant_stair",
##    "notes": [{"id": "review-001", "position": [77, 20, -36],
##               "text": "Check apron transition", "status": "open"}]}
##
## Positions are territory-local metres. Nothing references the file, so the
## snapshot, the bake and the runtime never see it, and the client package
## leaves it out (tools/package_client.py). A file that fails validation is
## read for what is valid and never rewritten, so nothing in it is lost or
## silently "fixed". Notes are not scene edits and have no undo; every change
## is written straight to the file.

const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const SCHEMA := "eloria-editor-notes-v1"
const SUFFIX := ".editor-notes.json"
const STATUSES := ["open", "resolved"]
const NODE_NAME := "__MapAuthoringReviewNotes"
const OPEN_COLOR := Color(1.0, 0.62, 0.2)
const RESOLVED_COLOR := Color(0.62, 0.66, 0.7)

var notes: Array[Dictionary] = []
var errors := PackedStringArray()
var path := ""
var region_id := ""
var last_message := ""
var _root: Node3D
var _pins: Node3D
var _adding := false
var _pending_text := ""
## Which notes get pins: "all", "open" or "resolved" (the dock's filter).
var _shown := "all"


## The sidecar beside the open scene, or "" for an unsaved scene.
static func path_for(root: Node) -> String:
	if root == null or root.scene_file_path.is_empty():
		return ""
	var region := String(root.get("region_id")) if root.get("region_id") != null else ""
	if region.is_empty():
		return ""
	return root.scene_file_path.get_base_dir().path_join(region + SUFFIX)


## {"notes", "errors"} from a notes file; a missing file has neither.
static func read(file_path: String, region: String) -> Dictionary:
	if file_path.is_empty() or not FileAccess.file_exists(file_path):
		return {"notes": [], "errors": PackedStringArray()}
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(file_path)) != OK:
		return {"notes": [], "errors": PackedStringArray([
			"%s is not valid JSON (line %d: %s)." % [file_path.get_file(), json.get_error_line(),
				json.get_error_message()]])}
	return validate(json.data, region)


## The valid notes of a parsed document and what is wrong with the rest.
static func validate(document: Variant, region: String) -> Dictionary:
	var valid: Array[Dictionary] = []
	var problems := PackedStringArray()
	if not document is Dictionary:
		problems.append("The notes file is not a JSON object.")
		return {"notes": valid, "errors": problems}
	var data: Dictionary = document
	if String(data.get("schema", "")) != SCHEMA:
		problems.append("Unsupported schema %s (expected %s)." % [str(data.get("schema")), SCHEMA])
	if String(data.get("regionId", "")) != region:
		problems.append("The notes are for %s, not %s." % [str(data.get("regionId")), region])
	if not data.get("notes") is Array:
		problems.append("\"notes\" must be a list.")
		return {"notes": valid, "errors": problems}
	var seen := {}
	for index in (data.notes as Array).size():
		var raw: Variant = data.notes[index]
		var where := "Note %d" % (index + 1)
		if not raw is Dictionary:
			problems.append("%s is not an object." % where)
			continue
		var note: Dictionary = raw
		var identity: Variant = note.get("id")
		if not identity is String or (identity as String).strip_edges().is_empty():
			problems.append("%s has no id." % where)
			continue
		where = "Note %s" % identity
		if seen.has(identity):
			problems.append("%s appears twice." % where)
			continue
		seen[identity] = true
		var position: Variant = note.get("position")
		var point := Vector3.ZERO
		var finite := position is Array and (position as Array).size() == 3
		if finite:
			for value: Variant in position:
				finite = finite and (value is float or value is int) and is_finite(float(value))
		if not finite:
			problems.append("%s needs a position of three finite numbers." % where)
			continue
		point = Vector3(float(position[0]), float(position[1]), float(position[2]))
		if not note.get("text") is String:
			problems.append("%s needs its text as a string." % where)
			continue
		if not String(note.get("status", "")) in STATUSES:
			problems.append("%s has status %s (open or resolved)." % [where, str(note.get("status"))])
			continue
		valid.append({"id": identity, "position": point, "text": note.text, "status": note.status})
	return {"notes": valid, "errors": problems}


## The file's JSON for `note_list`, sorted by id.
static func document(region: String, note_list: Array) -> Dictionary:
	var sorted := note_list.duplicate()
	sorted.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return String(a.id) < String(b.id))
	var out: Array = []
	for note: Dictionary in sorted:
		var point: Vector3 = note.position
		out.append({"id": note.id, "position": [snappedf(point.x, 0.001), snappedf(point.y, 0.001),
			snappedf(point.z, 0.001)], "text": note.text, "status": note.status})
	return {"schema": SCHEMA, "regionId": region, "notes": out}


## `review-NNN`, one past the highest used.
static func next_id(note_list: Array) -> String:
	var highest := 0
	for note: Dictionary in note_list:
		var identity := String(note.id)
		if identity.begins_with("review-") and identity.substr(7).is_valid_int():
			highest = maxi(highest, int(identity.substr(7)))
	return "review-%03d" % (highest + 1)


## Loads the notes of `root`'s territory and pins them in the 3D view.
func open(root: Node3D) -> void:
	release()
	_root = root
	path = path_for(root)
	region_id = String(root.get("region_id")) if root != null and root.get("region_id") != null else ""
	var loaded := read(path, region_id)
	notes.assign(loaded.notes)
	errors = loaded.errors
	if path.is_empty():
		last_message = "Save the scene to keep review notes beside it." if root != null else ""
	elif not errors.is_empty():
		last_message = "%s has problems, so it is read only: %s" % [path.get_file(), " ".join(errors)]
	else:
		last_message = "%d review note%s in %s." % [notes.size(), "" if notes.size() == 1 else "s",
			path.get_file()]
	_draw_pins()


func can_write() -> bool:
	return not path.is_empty() and errors.is_empty() and _root != null and is_instance_valid(_root)


func find(identity: String) -> Dictionary:
	for note in notes:
		if String(note.id) == identity:
			return note
	return {}


## Adds a note at territory-local `local` and writes the file.
func add(local: Vector3, text: String) -> Dictionary:
	if not can_write():
		last_message = "Review notes cannot be written here: %s" % (
			"save the scene first." if path.is_empty() else " ".join(errors))
		return {}
	var note := {"id": next_id(notes), "position": local,
		"text": text.strip_edges() if not text.strip_edges().is_empty() else "Needs a look",
		"status": "open"}
	notes.append(note)
	_commit("Added %s." % String(note.id))
	return note


func set_text(identity: String, text: String) -> bool:
	var note := find(identity)
	if note.is_empty() or not can_write():
		return false
	note.text = text
	return _commit("Updated %s." % identity)


func set_status(identity: String, status: String) -> bool:
	var note := find(identity)
	if note.is_empty() or not status in STATUSES or not can_write():
		return false
	note.status = status
	return _commit("%s is %s." % [identity, status])


func remove(identity: String) -> bool:
	var note := find(identity)
	if note.is_empty() or not can_write():
		return false
	notes.erase(note)
	return _commit("Deleted %s." % identity)


## Waits for a click in the 3D view to place a note with `text`.
func arm_add(text: String) -> bool:
	if not can_write():
		last_message = "Review notes cannot be written here: %s" % (
			"save the scene first." if path.is_empty() else " ".join(errors))
		return false
	_adding = true
	_pending_text = text
	last_message = "Click the spot the note is about. Esc cancels."
	return true


func is_adding() -> bool:
	return _adding


func handle_input(camera: Camera3D, event: InputEvent) -> int:
	if not _adding or _root == null or not is_instance_valid(_root):
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventKey and event.pressed and (event as InputEventKey).keycode == KEY_ESCAPE:
		_adding = false
		last_message = "No note added."
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
		var button := event as InputEventMouseButton
		if button.button_index == MOUSE_BUTTON_RIGHT:
			_adding = false
			last_message = "No note added."
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if button.button_index != MOUSE_BUTTON_LEFT or button.alt_pressed:
			return EditorPlugin.AFTER_GUI_INPUT_PASS
		var hit: Variant = Probe.ray_hit(_root, camera.project_ray_origin(button.position),
			camera.project_ray_normal(button.position), 4096.0)
		if not hit is Vector3:
			last_message = "That click missed the terrain."
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		_adding = false
		add(_root.global_transform.affine_inverse() * (hit as Vector3), _pending_text)
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	return EditorPlugin.AFTER_GUI_INPUT_PASS


func set_shown(which: String) -> void:
	if which != _shown:
		_shown = which
		_draw_pins()


func pins() -> Node3D:
	return _pins if _pins != null and is_instance_valid(_pins) else null


func release() -> void:
	_adding = false
	if _pins != null and is_instance_valid(_pins):
		if _pins.get_parent() != null:
			_pins.get_parent().remove_child(_pins)
		_pins.queue_free()
	_pins = null
	_root = null
	notes.clear()
	errors = PackedStringArray()
	path = ""


func _commit(message: String) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		last_message = "Could not write %s: %s" % [path, error_string(FileAccess.get_open_error())]
		return false
	file.store_string(JSON.stringify(document(region_id, notes), "\t") + "\n")
	file.close()
	last_message = message
	_draw_pins()
	return true


func _draw_pins() -> void:
	if _pins != null and is_instance_valid(_pins):
		if _pins.get_parent() != null:
			_pins.get_parent().remove_child(_pins)
		_pins.queue_free()
	_pins = null
	if _root == null or not is_instance_valid(_root) or notes.is_empty():
		return
	_pins = Node3D.new()
	_pins.name = NODE_NAME
	_root.add_child(_pins, false, Node.INTERNAL_MODE_BACK)
	for note in notes:
		if _shown != "all" and String(note.status) != _shown:
			continue
		var color := RESOLVED_COLOR if String(note.status) == "resolved" else OPEN_COLOR
		var stem := MeshInstance3D.new()
		var mesh := CylinderMesh.new()
		mesh.top_radius = 0.12
		mesh.bottom_radius = 0.02
		mesh.height = 2.0
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.albedo_color = color
		mesh.material = material
		stem.mesh = mesh
		stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		stem.position = (note.position as Vector3) + Vector3(0.0, 1.0, 0.0)
		_pins.add_child(stem)
		var label := Label3D.new()
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		label.fixed_size = true
		label.pixel_size = 0.0012
		label.outline_size = 8
		label.modulate = color
		label.text = "%s%s: %s" % [String(note.id), " (resolved)" if String(note.status) == "resolved"
			else "", String(note.text)]
		label.position = (note.position as Vector3) + Vector3(0.0, 2.4, 0.0)
		_pins.add_child(label)
