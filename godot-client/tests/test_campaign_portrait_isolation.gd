extends SceneTree
## Real native actors reproduce a player directly between speaker and camera.
const Dialogue := preload("res://src/ui/campaign_dialogue.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	checks += 1
	if value: print("PASS: ", message)
	else: failures += 1; push_error(message)

func make_actor(type: int, id: int) -> ReplicatedActor3D:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var model: Dictionary = registry.models[registry.actorTypes[str(type)]]
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id":id, "actor_type":type, "kind":1,
		"name":"Portrait isolation probe", "x":0, "y":0, "rotation":0,
		"health":50, "max_health":50, "appearance":{}, "equipment_visuals":{}},
		CoordinateAdapter.new({"walkingHeight":0}), model,
		JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap))), equipment)
	expect(errors.is_empty(), "the current native actor " + str(type) + " loads")
	actor.set_process(false); actor.set_physics_process(false)
	return actor

func native_layers(actor: Node3D) -> Dictionary:
	var result: Dictionary = {}
	for mesh: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		result[mesh.get_instance_id()] = {"node":mesh, "layers":mesh.layers}
	return result

func intersects(rows: Dictionary, mask: int) -> bool:
	for row: Dictionary in rows.values():
		if row.node.layers & mask: return true
	return false

func exact(rows: Dictionary) -> bool:
	for row: Dictionary in rows.values():
		if row.node.layers != row.layers: return false
	return true

func run() -> void:
	create_timer(50).timeout.connect(func() -> void: push_error("Portrait isolation checks timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var mother := make_actor(0, 1)
	var player := make_actor(1, 2)
	mother.global_position = Vector3.ZERO
	player.global_position = Vector3(0, 0, -0.55)
	var mother_rows := native_layers(mother)
	var player_rows := native_layers(player)
	var post := mother.global_transform
	var skeleton := mother.get_skeleton()
	var head := skeleton.get_bone_pose(skeleton.find_bone("Head"))
	var health := mother._health_current
	var widget = Dialogue.new(); root.add_child(widget)
	widget.set_line("Elen Reed", "Thank you. Please save my daughter.", mother)
	var first: int = widget._camera.cull_mask
	expect(first != 0 and first != 1 and (first & (1 << 19)) == 0,
		"the portrait camera receives a dedicated bit outside world/native label layers")
	expect(intersects(mother_rows, first) and not intersects(player_rows, first),
		"only the speaking mother renders while the player stands directly in front of her")
	expect(exact(player_rows), "the nearby player's world mesh masks are untouched")
	var player_head := player.get_skeleton().global_transform * player.get_skeleton().get_bone_global_pose(player.get_skeleton().find_bone("Head")).origin
	var mother_head := skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin
	expect(widget._camera.global_position.distance_to(player_head) < widget._camera.global_position.distance_to(mother_head),
		"the native player reproduces the closer-than-speaker portrait occluder")
	var overlay := MeshInstance3D.new(); overlay.layers = 2; mother.add_child(overlay)
	var replacement := MeshInstance3D.new(); replacement.layers = 1; mother.add_child(replacement)
	widget._update_portrait()
	expect((overlay.layers & first) == 0 and (replacement.layers & first) != 0,
		"new native meshes join the speaker lease while gameplay overlays stay excluded")
	replacement.reparent(root)
	widget._update_portrait()
	expect(replacement.layers == 1, "a replaced or reparented mesh releases its portrait membership")
	var second_widget = Dialogue.new(); root.add_child(second_widget)
	second_widget.set_line("Player", "We will bring her home.", player)
	var second: int = second_widget._camera.cull_mask
	expect(first != second and not intersects(mother_rows, second) and not intersects(player_rows, first),
		"simultaneous dialogues cannot see each other's selected actors")
	var shared_widget = Dialogue.new(); root.add_child(shared_widget)
	shared_widget.set_line("Elen Reed", "Hurry.", mother)
	var shared: int = shared_widget._camera.cull_mask
	widget.set_line("", "The path falls silent.")
	expect(not intersects(mother_rows, first) and intersects(mother_rows, shared),
		"narration releases only this portrait's membership on a multiply observed actor")
	shared_widget.reset()
	expect(exact(mother_rows), "reset restores every original speaker mesh mask exactly")
	widget.set_line("Player", "Follow me.", player)
	widget.set_line("Elen Reed", "I am coming.", mother)
	expect(not intersects(player_rows, widget._camera.cull_mask) and intersects(player_rows, second),
		"speaker changes release the old actor without disturbing its other portrait")
	widget.hide(); widget._process(0.1)
	expect(exact(mother_rows) and widget._camera.cull_mask == 0,
		"a hidden dialogue releases render membership and disables the portrait camera")
	widget.show(); widget._update_portrait()
	var added_bit := 8
	var native_mesh: MeshInstance3D
	for row: Dictionary in mother_rows.values():
		if row.layers & 1: native_mesh = row.node; break
	native_mesh.layers |= added_bit
	widget.reset()
	expect((native_mesh.layers & added_bit) != 0, "cleanup preserves a legitimate concurrent gameplay layer change")
	native_mesh.layers &= ~added_bit
	widget.set_line("Elen Reed", "Stay close.", mother)
	widget.free()
	expect(exact(mother_rows), "freeing the dialogue restores speaker layers without a reset call")
	expect(mother.global_transform == post and skeleton.get_bone_pose(skeleton.find_bone("Head")) == head and mother._health_current == health,
		"portrait isolation never moves, reposes, or heals the live speaker")
	player.free()
	second_widget._update_portrait()
	expect(not second_widget.portrait_visible() and second_widget._camera.cull_mask == 0,
		"a freed speaker fails closed and releases its viewport membership")
	second_widget.free(); shared_widget.free(); mother.free(); replacement.free()
	NativeAnimationImporter.clear(); GlbSceneCache.clear()
	await process_frame
	print("Campaign portrait isolation: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)
