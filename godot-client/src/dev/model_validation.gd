extends Node3D

@onready var status: Label = %Status
@onready var clip_label: Label = %Clip
@onready var light_pivot: Node3D = %LightPivot

var actor: ReplicatedActor3D
var models: Dictionary
var animation_config: Dictionary
var equipment_config: Dictionary
var clips: Array[StringName] = []
var clip_index := 0
var model_ids: Array[String] = []
var model_index := 0
var model_id := "luminous_female"

func _ready() -> void:
	var registry: Dictionary = _json("res://data/actors/models.json")
	models = registry.get("models", {})
	for raw_option: Variant in registry.get("creationOptions", []):
		if raw_option is Dictionary:
			model_ids.append(str((raw_option as Dictionary).get("model", "")))
	model_ids.append_array(["emberfox", "sunscale_drake", "armored_rhino", "two_tailed_fox"])
	equipment_config = _json("res://data/actors/equipment.json")
	_load_model(model_id)

func _process(delta: float) -> void:
	light_pivot.rotate_y(delta * 0.25)

func _load_model(id: String) -> void:
	if is_instance_valid(actor):
		actor.queue_free()
	model_id = id
	actor = ReplicatedActor3D.new()
	actor.name = "ValidatedActor"
	add_child(actor)
	var model_config: Dictionary = models[id] as Dictionary
	animation_config = _json(str(model_config.get(
		"animationMap", "res://data/animations/luminous.json")))
	var is_creature := str(model_config.get("animationMap", "")).ends_with("creature.json")
	# Modified 2026-08-28 for Eloria Client: exercise both attachment paths.
	# Parts 0, 1, 3 and 7 resolve a character-space socket; parts 2, 4, 5 and 6
	# rebind to this actor's skeleton, which the old registry could not do.
	var equipment_visuals: Dictionary = {} if is_creature else {
		0: 100, 1: 100, 2: 100, 3: 100, 4: 100, 5: 100, 6: 100, 7: 100}
	var dto := {"actor_id": 1, "x": 0, "y": 0, "rotation": 0,
		"appearance": {"skin": 1, "hair": 2, "eyes": 3,
			"shirt": 1, "pants": 2, "boots": 3, "head": 1},
		"equipment_visuals": equipment_visuals}
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true})
	var errors := actor.configure(dto, adapter, model_config, animation_config, equipment_config)
	var equipment_diagnostics: Dictionary = actor.equipment_diagnostics()
	if not is_creature:
		if int(equipment_diagnostics.get("socket", 0)) != 4:
			errors.append("socketed equipment missing: expected weapon, shield, "
				+ "helmet and neck, got %d" % int(equipment_diagnostics.get("socket", 0)))
		if int(equipment_diagnostics.get("skinned", 0)) < 4:
			errors.append("skinned garments missing: expected cape, legs, body "
				+ "and boots, got %d" % int(equipment_diagnostics.get("skinned", 0)))
		if int(equipment_diagnostics.get("fallback", 0)) != 0:
			errors.append("equipment fell back to placeholder meshes")
	clips.clear()
	for action in animation_config.get("actions", {}):
		var clip := StringName(animation_config.actions[action])
		if not clips.has(clip):
			clips.append(clip)
	clip_index = 0
	status.text = id + "\n" + ("PASS: source and mapped clips loaded" if errors.is_empty()
		else "ERRORS:\n" + "\n".join(errors))
	_play_current()

func _play_current() -> void:
	if clips.is_empty() or actor == null:
		return
	var clip := clips[clip_index]
	clip_label.text = "%d/%d  %s" % [clip_index + 1, clips.size(), clip]
	if actor.animation_player != null and actor.animation_player.has_animation(clip):
		actor.animation_player.play(clip)

func _on_previous_pressed() -> void:
	clip_index = wrapi(clip_index - 1, 0, clips.size())
	_play_current()

func _on_next_pressed() -> void:
	clip_index = wrapi(clip_index + 1, 0, clips.size())
	_play_current()

func _on_model_pressed() -> void:
	model_index = wrapi(model_index + 1, 0, model_ids.size())
	_load_model(model_ids[model_index])

static func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}
