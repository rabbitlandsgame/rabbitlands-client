extends SceneTree
## Equipment packets must preserve the current animation and its playback clock.

var failures := 0
var actor: ReplicatedActor3D
var state: Node
var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
var starts: Array[StringName] = []

func _init() -> void:
	call_deferred("run")

func expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func packet(command: int, payload: PackedByteArray) -> void:
	state.call("_on_packet", command, payload)
	actor.apply_server_state(state.get("actors")[901], adapter)

func equipment_packet(command: int, payload: PackedByteArray, label: String) -> void:
	var action := actor.current_action
	var clock := actor.animation_player.current_animation_position
	var count := starts.size()
	packet(command, payload)
	expect(actor.current_action == action, label + " preserves the current action")
	expect(starts.size() == count, label + " starts no animation")
	expect(is_equal_approx(actor.animation_player.current_animation_position, clock),
		label + " preserves the playback clock")

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	var dto := {"actor_id": 901, "x": 0, "y": 0, "rotation": 0,
		"appearance": {}, "equipment_visuals": {0: 64}, "in_combat": false,
		"command": 7, "command_sequence": 1}
	state = root.get_node("AppState")
	state.set("actors", {901: dto})
	actor = ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure(dto, adapter, models.models.luminous_male,
		animations, equipment)
	expect(errors.is_empty(), "the production player rig imports: " + str(errors))
	if actor.animation_player == null:
		quit(1)
		return
	actor.set_physics_process(false)
	actor.animation_player.animation_started.connect(
		func(clip: StringName) -> void: starts.append(clip))
	actor.apply_server_state(dto, adapter)

	# The stand command remains in the actor record after its transition ends.
	# Replaying Sitting_Exit on an unwear update makes the player sit down again.
	packet(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, PackedByteArray([0x85, 3, 14]))
	expect(actor.current_action == &"stand", "a new stand command plays its transition")
	actor.animation_player.advance(actor.animation_player.current_animation_length + 0.1)
	expect(actor.current_action == &"idle", "standing finishes in idle")
	equipment_packet(EloriaProtocol.ServerMessage.ACTOR_UNWEAR_ITEM,
		PackedByteArray([0x85, 3, 0]), "removing equipment after standing")
	expect(not actor.equipment_diagnostics().visuals.has(0), "the removed weapon disappears")

	actor.play_action(&"emote_greet", true)
	actor.animation_player.advance(0.2)
	equipment_packet(EloriaProtocol.ServerMessage.ACTOR_WEAR_ITEM,
		PackedByteArray([0x85, 3, 0, 64]), "equipping during an emote")
	actor.play_action(&"emote_greet", true)
	actor.animation_player.advance(0.2)
	equipment_packet(EloriaProtocol.ServerMessage.ACTOR_UNWEAR_ITEM,
		PackedByteArray([0x85, 3, 0]), "removing equipment during an emote")

	packet(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, PackedByteArray([0x85, 3, 13]))
	expect(actor.current_action == &"sit", "a new sit command still plays sitting")
	actor.play_action(&"seated_idle")
	actor.animation_player.advance(0.2)
	equipment_packet(EloriaProtocol.ServerMessage.ACTOR_WEAR_ITEM,
		PackedByteArray([0x85, 3, 0, 64]), "equipping while seated")
	equipment_packet(EloriaProtocol.ServerMessage.ACTOR_UNWEAR_ITEM,
		PackedByteArray([0x85, 3, 0]), "removing equipment while seated")
	expect(bool(state.get("actors")[901].sitting), "removal preserves the seated state")

	packet(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, PackedByteArray([0x85, 3, 14]))
	actor.animation_player.advance(actor.animation_player.current_animation_length + 0.1)
	packet(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, PackedByteArray([0x85, 3, 20]))
	expect(actor.current_action == &"walk", "a new movement command still starts walking")
	actor.animation_player.advance(0.2)
	equipment_packet(EloriaProtocol.ServerMessage.ACTOR_WEAR_ITEM,
		PackedByteArray([0x85, 3, 0, 64]), "equipping while walking")
	equipment_packet(EloriaProtocol.ServerMessage.ACTOR_UNWEAR_ITEM,
		PackedByteArray([0x85, 3, 0]), "removing equipment while walking")

	# Older callers omit command_sequence. Keep their active-cast protection.
	var legacy: Dictionary = state.get("actors")[901].duplicate()
	legacy.erase("command_sequence")
	legacy.command = 7
	actor.apply_server_state(legacy, adapter, true)
	actor.play_action(&"heal", true)
	actor.apply_server_state(legacy, adapter)
	expect(actor.current_action == &"heal", "legacy snapshots preserve an active cast")

	actor.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("equipment animation: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
