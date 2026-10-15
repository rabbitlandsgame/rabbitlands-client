extends SceneTree
## Production actor materials through spawn, late login correction and unwear.
## Optional argument: JSON containing server-generated full-frame hex fixtures.

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func decode(frame: String) -> Dictionary:
	var bytes := frame.hex_decode()
	return EloriaProtocol.decode_server(bytes[0], bytes.slice(3))

func receive(state: Node, frame: String) -> void:
	var bytes := frame.hex_decode()
	state.call("_on_packet", bytes[0], bytes.slice(3))

func shirt(actor: ReplicatedActor3D) -> MeshInstance3D:
	return actor.find_child("wardrobe_shirt", true, false) as MeshInstance3D

func shirt_color(actor: ReplicatedActor3D) -> Color:
	return (shirt(actor).get_active_material(0) as StandardMaterial3D).albedo_color

func run() -> void:
	var bare_payload := PackedByteArray([9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0,
		1, 100, 5, 6, 10, 0, 11, 0, 30, 20, 0, 20, 0, 20, 0, 1,
		71, 114, 101, 101, 110, 0, 0, 128, 255, 1, 0])
	var legacy_armour := bare_payload.duplicate()
	legacy_armour[14] = 184
	var armour_payload := legacy_armour.duplicate()
	armour_payload.append_array(PackedByteArray([87, 65, 1, 5, 6, 10, 32]))
	bare_payload.append_array(PackedByteArray([87, 65, 1, 5, 6, 10, 0]))
	var frames := {
		"bare": EloriaProtocol.encode(51, bare_payload).hex_encode(),
		"legacy_armour": EloriaProtocol.encode(51, legacy_armour).hex_encode(),
		"armour": EloriaProtocol.encode(51, armour_payload).hex_encode(),
		"unwear": EloriaProtocol.encode(53, PackedByteArray([9, 0, 5])).hex_encode()}
	if not OS.get_cmdline_user_args().is_empty():
		frames = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var state := root.get_node("AppState")
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	for race: String in ["luminous_male", "luminous_female"]:
		var config: Dictionary = models[race]
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config["animationMap"]))
		var preview := ReplicatedActor3D.new()
		root.add_child(preview)
		var bare := decode(frames.bare)
		var preview_dto := bare.duplicate(true)
		preview_dto["equipment_visuals"] = {}
		expect(preview.configure(preview_dto, adapter, config, animations, equipment).is_empty(), race + " preview configures")
		var green := shirt_color(preview)
		expect(green.is_equal_approx(AppearanceVariants.wardrobe_color("luminous", 5, 5)), race + " preview is forest green")
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		expect(actor.configure(bare, adapter, config, animations, equipment).is_empty(), race + " spawn configures")
		expect(shirt_color(actor).is_equal_approx(green) and shirt(actor).visible, race + " spawn matches the chosen preview shirt")
		expect(int(actor.equipment_diagnostics().native) == 0, race + " dye IDs attach no gear")
		# An armoured login first arrives in the old format, then the capability
		# response corrects the saved dye on the very same actor node.
		actor.apply_server_state(decode(frames.legacy_armour), adapter)
		receive(state, frames.armour)
		actor.apply_server_state(state.actors[9], adapter)
		expect((shirt(actor).get_meta("wardrobe_color") as Color).is_equal_approx(green), race + " login correction preserves green under armour")
		expect(int(actor.equipment_diagnostics().native) > 0, race + " actual armour still renders")
		receive(state, frames.unwear)
		actor.apply_server_state(state.actors[9], adapter)
		expect(shirt_color(actor).is_equal_approx(green) and shirt(actor).visible, race + " unwear restores the chosen shirt")
		var material := shirt(actor).get_active_material(0)
		actor.apply_server_state(state.actors[9], adapter)
		expect(shirt(actor).get_active_material(0) == material, race + " unchanged state reuses appearance materials")
		actor.free()
		preview.free()
		await process_frame
	state.actors.clear()
	NativeAnimationImporter.clear()
	print("wardrobe replication: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
