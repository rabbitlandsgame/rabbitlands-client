extends Node
## A readable presentation of the opening's existing interaction markers.
## Every action remains a normal server-owned work object or NPC conversation.
const LabelStyle := preload("res://src/ui/world_label_style.gd")
const NEXT_COLOUR := Color("f0ce73")
const MAX_LABELS := 3
const APPROACH_TARGETS := {"repair": ["damage", "component", "ballast", "fit", "test"],
	"evacuate": ["worker", "safe"], "defend": ["defend", "secure"]}
var _controlled: Dictionary = {}
var _labels: Dictionary = {}
var _identity := ""

static func is_opening(snapshot: Dictionary) -> bool:
	return str(snapshot.get("kind", "opening")) in ["", "opening"]

static func work_targets(snapshot: Dictionary) -> Array[Dictionary]:
	var targets: Array[Dictionary] = []
	for navigation: bool in [true, false]:
		for row: Dictionary in snapshot.get("targets", []):
			if str(row.get("id", "")) in ["return", "leave"] or not bool(row.get("enabled", true)) \
					or bool(row.get("completed", false)) or (int(row.get("object_id", -1)) == 0) != navigation:
				continue
			targets.append(row)
	# Lead with work for the player's chosen approach, keeping every other
	# server-enabled method available and preserving genuine material choices.
	var preferred: Array = APPROACH_TARGETS.get(str(snapshot.get("approach", "")), [])
	if preferred.is_empty():
		return targets
	var ordered: Array[Dictionary] = []
	for row: Dictionary in targets:
		if int(row.get("object_id", -1)) == 0 or str(row.id) in preferred: ordered.append(row)
	for row: Dictionary in targets:
		if int(row.get("object_id", -1)) != 0 and str(row.id) not in preferred: ordered.append(row)
	return ordered

static func near(target: Dictionary, tile: Vector2i) -> bool:
	var raw: Array = target.get("tile", [0,0])
	return maxi(absi(tile.x-int(raw[0])), absi(tile.y-int(raw[1]))) <= maxf(1, float(target.get("range",3)))

static func conversation_actor(snapshot: Dictionary, target: Dictionary) -> int:
	var role := str(target.get("role", ""))
	var actor_id := int(target.get("actor_id", -1))
	if int(target.get("object_id", -1)) == 0 and not role.is_empty() and actor_id > 0 \
			and int((snapshot.get("actors", {}) as Dictionary).get(role,-1)) == actor_id:
		return actor_id
	return -1

static func legend(snapshot: Dictionary) -> String:
	var targets := work_targets(snapshot)
	if targets.is_empty():
		if bool((snapshot.get("party", {}) as Dictionary).get("waiting_for_scene", false)):
			return "Waiting for the party to finish the scene. Work markers appear when everyone is ready."
		return "Follow the crew's instructions. New work sites appear when they are ready."
	var next := "Next: " + str(targets[0].label) if targets.size()==1 or targets[0].has("actor_id") else "Choose one of the labelled work sites."
	if targets.size() > 1 and not targets[0].has("actor_id") and not str(snapshot.get("approach", "")).is_empty():
		next = "Follow your current objective above. Other labelled sites are alternate ways to help."
	if targets[0].has("actor_id"):
		return next + "\nClick the named NPC when close. Choose the action below to walk over first if needed."
	return next + "\nGround circles mark available work. Click to interact; if distant, click to approach and again when close."

func apply_snapshot(snapshot: Dictionary, objects: Dictionary, actors: Dictionary,
		current_map: String, local_tile: Vector2i, tracked: bool, blocked: bool) -> void:
	if not is_opening(snapshot) or not bool(snapshot.get("active", false)) \
			or not (snapshot.get("travel", {}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) \
			!= EloriaProtocol.map_id_from_reference(current_map):
		clear()
		return
	var identity := str(snapshot.get("run_id", "")) + ":" + EloriaProtocol.map_id_from_reference(current_map)
	if identity != _identity:
		clear()
		_identity = identity
	var available := work_targets(snapshot)
	var ids: Dictionary = {}
	for row: Dictionary in available:
		ids[str(row.id)] = true
	var object_ids: Dictionary = {}
	for row: Dictionary in snapshot.get("targets", []):object_ids[int(row.get("object_id",-1))] = true
	for id: int in _controlled:
		if not object_ids.has(id):
			var old := (_controlled[id].node as WeakRef).get_ref() as MapObject3D
			if is_instance_valid(old):
				old.collision_layer = 0
				old.set_meta("campaign_work_available",false)
				for child: String in ["Ring","MapMarker"]:
					var mark := old.get_node_or_null(child) as Node3D
					if mark!=null:mark.hide()
	for label: Label3D in _labels.values():
		if is_instance_valid(label):label.hide()
	var shown := 0
	var ordered: Array[Dictionary] = available.duplicate()
	for row: Dictionary in snapshot.get("targets", []):
		if not ids.has(str(row.id)):ordered.append(row)
	for row: Dictionary in ordered:
		var object_id := int(row.get("object_id", -1))
		var enabled := ids.has(str(row.id))
		var object: MapObject3D = objects.get(object_id) as MapObject3D
		if is_instance_valid(object) and object_id > 0:
			_register(object)
			object.set_meta("campaign_work_available", enabled)
			var ring := object.get_node_or_null("Ring") as MeshInstance3D
			var pin := object.get_node_or_null("MapMarker") as Node3D
			if ring != null:
				ring.visible = enabled and not blocked
				var material := ring.material_override as StandardMaterial3D
				if material != null:
					material.albedo_color = NEXT_COLOUR if tracked and available.size()==1 else _controlled[object_id].colour
			if pin != null:pin.visible = enabled
			object.collision_layer = int(_controlled[object_id].pick_layer) if enabled and not blocked else 0
		if not enabled or not tracked or blocked or shown >= MAX_LABELS:
			continue
		var parent: Node3D = object
		var actor_id := conversation_actor(snapshot,row)
		if actor_id > 0:
			parent = actors.get(actor_id) as Node3D
		if not is_instance_valid(parent):continue
		var key := str(row.id)
		var label: Label3D = _labels.get(key) as Label3D
		if not is_instance_valid(label):
			label = Label3D.new()
			label.name = "CampaignWork_" + key
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.fixed_size = true
			LabelStyle.apply(label,14,0.0012953,5)
			label.visibility_range_end = 45
			parent.add_child(label)
			_labels[key] = label
		elif label.get_parent() != parent:
			label.reparent(parent)
		label.position = Vector3.UP * (2.4 if actor_id>0 else 1.1)
		var verb := "Talk" if actor_id>0 and near(row,local_tile) else "Interact" if near(row,local_tile) else "Walk to"
		var next := available.size()==1 or actor_id>0
		label.text = ("NEXT · " if next else "WORK · ") + str(row.label) + "\n" + verb
		label.modulate = NEXT_COLOUR if next else Color.WHITE
		label.show()
		shown += 1

func _register(object: MapObject3D) -> void:
	var id := object.object_id
	if _controlled.has(id) and (_controlled[id].node as WeakRef).get_ref() == object:return
	var ring := object.get_node_or_null("Ring") as MeshInstance3D
	var pin := object.get_node_or_null("MapMarker") as Node3D
	var colour := MapObject3D.INTERACTIVE_COLOUR
	if ring != null and ring.material_override is StandardMaterial3D:
		colour = (ring.material_override as StandardMaterial3D).albedo_color
	_controlled[id] = {"node":weakref(object),"ring_visible":ring.visible if ring!=null else false,
		"pin_visible":pin.visible if pin!=null else false,"pick_layer":object.collision_layer,"colour":colour}

func clear() -> void:
	for saved: Dictionary in _controlled.values():
		var object := (saved.node as WeakRef).get_ref() as MapObject3D
		if not is_instance_valid(object):continue
		object.collision_layer = int(saved.pick_layer)
		object.remove_meta("campaign_work_available")
		var ring := object.get_node_or_null("Ring") as MeshInstance3D
		var pin := object.get_node_or_null("MapMarker") as Node3D
		if ring != null:
			ring.visible = bool(saved.ring_visible)
			if ring.material_override is StandardMaterial3D:
				(ring.material_override as StandardMaterial3D).albedo_color = saved.colour
		if pin != null:pin.visible = bool(saved.pin_visible)
	for label: Label3D in _labels.values():
		if is_instance_valid(label):label.queue_free()
	_controlled.clear()
	_labels.clear()
	_identity = ""

func _exit_tree() -> void:
	clear()
