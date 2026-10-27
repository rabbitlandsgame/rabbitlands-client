extends SceneTree
## Uses the current imported rigs, not a replacement mesh or mock head.
const Dialogue := preload("res://src/ui/campaign_dialogue.gd")
var checks := 0
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(value: bool, message: String) -> void:
	checks += 1
	if value:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _run() -> void:
	create_timer(45).timeout.connect(func() -> void: push_error("Creature portrait check timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var stage := Node3D.new()
	root.add_child(stage)
	var widget = Dialogue.new()
	root.add_child(widget)
	widget.size = Vector2(1200, 125)
	for spec: Array in [[624, 5, "Goblin captor", "head"], [671, 2, "The unseen claimant", "Bone_021"]]:
		var model: Dictionary = registry.models[registry.actorTypes[str(spec[0])]]
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var dto := {"actor_id": int(spec[0]), "actor_type": int(spec[0]), "kind": int(spec[1]),
			"name": str(spec[2]), "x": 0, "y": 0, "rotation": 0, "frame": 0,
			"health": 100, "max_health": 100, "appearance": {}}
		var errors := actor.configure(dto, CoordinateAdapter.new({"walkingHeight":0}), model,
			JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap))), equipment)
		expect(errors.is_empty(), str(spec[2]) + " loads its current approved native rig")
		actor.set_process(false)
		actor.set_physics_process(false)
		var skeleton := actor.get_skeleton()
		expect(is_instance_valid(skeleton) and skeleton.find_bone(str(spec[3])) >= 0, "the actual rig contains its measured head binding")
		expect(skeleton.find_bone("Head") < 0, "this native speaker exercises the nonhumanoid fallback")
		var transform := actor.global_transform
		var poses: Array[Transform3D] = []
		for bone: int in range(skeleton.get_bone_count()):
			poses.append(skeleton.get_bone_pose(bone))
		widget.set_line(str(spec[2]), "You have not heard the last of this.", actor)
		expect(widget.portrait_visible(), "the native creature receives the same framed headshot")
		expect(widget._viewport.world_3d == actor.get_world_3d(), "the portrait observes the real creature in its existing world")
		expect(widget._camera.cull_mask != 0 and (widget._camera.cull_mask & 7) == 0, "creature headshots isolate the speaker from other world actors and gameplay overlays")
		expect(widget.speaker_label.get_theme_color("font_color") != widget.body_label.get_theme_color("font_color"), "the speaker name keeps its contrasting color")
		var profile: Dictionary = widget._creature_head_profile(actor, skeleton)
		expect(str(profile.bone) == str(spec[3]), "only the exact native asset selects the measured head envelope")
		_assert_envelope_visible(widget, skeleton, profile)
		expect(widget._camera.size > 0.5 and widget._camera.size < 1.3, "the head frame includes the goblin ears or lich crown at native scale")
		expect(widget._camera.far > widget._camera.near, "the complete native head remains inside the portrait depth range")
		var unchanged := actor.global_transform == transform
		for bone: int in range(skeleton.get_bone_count()):
			unchanged = unchanged and skeleton.get_bone_pose(bone) == poses[bone]
		expect(unchanged and actor._health_current == 100, "portrait framing changes neither authoritative actor state nor any bone pose")
		if int(spec[0]) == 624:
			actor.play_action(&"death", true)
			actor.animation_player.seek(1.8, true)
			var fallen := skeleton.get_bone_global_pose(skeleton.find_bone("head"))
			widget._update_portrait()
			_assert_envelope_visible(widget, skeleton, profile)
			expect(widget.portrait_visible(), "the fallen boss retains its real last-words portrait")
			expect(skeleton.get_bone_global_pose(skeleton.find_bone("head")) == fallen, "a fallen portrait never restores or reposes the creature")
		widget.set_line("Narrator", "A voice fades into the tunnel.")
		expect(not widget.portrait_visible() and widget._viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED, "unbound dialogue stops the prior creature camera")
		actor.free()
	_humanoid_portraits(stage, widget, registry, equipment)
	var unknown := ReplicatedActor3D.new()
	stage.add_child(unknown)
	var numeric := Skeleton3D.new()
	unknown.add_child(numeric)
	numeric.add_bone("Bone_021")
	expect(widget._creature_head_profile(unknown, numeric).is_empty(), "an unrelated numeric skeleton cannot inherit the lich's head profile")
	unknown.free()
	widget.reset()
	expect(not widget.portrait_visible() and widget._viewport.world_3d == null, "reset releases the creature portrait world and render request")
	widget.free()
	stage.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	print("campaign creature portraits: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

func _humanoid_portraits(stage: Node3D, widget, registry: Dictionary, equipment: Dictionary) -> void:
	# The actual Watch patient's native appearance, shield and HP1 are retained.
	var dto := {"actor_id":2231, "actor_type":0, "kind":2, "name":"Injured woman",
		"x":268, "y":128, "rotation":-32768, "frame":3, "health":1, "max_health":50,
		"appearance":{"skin":1,"hair":107,"shirt":5,"pants":4,"boots":1,"head":0,"eyes":2},
		"equipment_visuals":{"0":163,"3":122,"5":189,"4":176,"6":205,"2":100}}
	var model: Dictionary = registry.models[registry.actorTypes["0"]]
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors := actor.configure(dto, CoordinateAdapter.new({"walkingHeight":0}), model,
		JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap))), equipment)
	expect(errors.is_empty(), "the real Watch patient's native female rig, clothes and shield load")
	actor.set_process(false)
	actor.set_physics_process(false)
	var skeleton := actor.get_skeleton()
	var bone := skeleton.find_bone("Head")
	expect(bone >= 0, "the Watch patient exercises the ordinary humanoid Head path")
	widget.set_line("Elen Reed", "Please help my daughter.", actor)
	var standing_size: float = widget._camera.size
	expect(widget.portrait_visible() and standing_size > 0.4, "the standing humanoid portrait retains its upright head framing")
	var standing_forward := _head_forward(actor, skeleton, bone)
	var standing_head := skeleton.global_transform * skeleton.get_bone_global_pose(bone).origin
	expect((widget._camera.global_position-standing_head).normalized().dot(standing_forward) > 0.98, "the standing native humanoid is viewed from its actual face")
	actor.set_cinematic_presentation(actor.global_position, actor.rotation.y, &"injury_pinned")
	actor.set_physics_process(false)
	expect(actor._cinematic_injury != null and actor._cinematic_injury.held, "the test uses the real native injury_pinned hold")
	var post := actor.global_transform
	var pinned := skeleton.get_bone_global_pose(bone)
	widget._update_portrait()
	var fallen_head := skeleton.global_transform * pinned.origin
	var fallen_forward := _head_forward(actor, skeleton, bone)
	expect(widget.portrait_visible() and is_equal_approx(widget._camera.size, standing_size), "lying down keeps the rest-sized headshot rather than shrinking to ground height")
	expect((widget._camera.global_position-fallen_head).normalized().dot(fallen_forward) > 0.98, "the lying patient's camera observes her face instead of her shield and hands")
	expect(absf(fallen_forward.dot(standing_forward)) < 0.9, "the real injury pose changes head orientation enough to reproduce the old foot-yaw bug")
	expect(widget._camera.unproject_position(fallen_head).distance_to(Vector2(widget._viewport.size)*0.5) < 28, "the actual injured head remains centered in the portrait")
	expect(actor.global_transform == post and skeleton.get_bone_global_pose(bone) == pinned \
		and actor._health_current == 1 and actor.current_action == &"injury_pinned", "the portrait neither heals, reposes nor changes the living patient")
	actor.end_cinematic_presentation()
	actor.set_physics_process(false)
	widget.reset()
	actor.free()

func _head_forward(actor: Node3D, skeleton: Skeleton3D, bone: int) -> Vector3:
	var world := skeleton.global_basis.orthonormalized()
	var delta := world * skeleton.get_bone_global_pose(bone).basis.orthonormalized() \
		* skeleton.get_bone_global_rest(bone).basis.orthonormalized().inverse() * world.inverse()
	return (delta * -actor.global_basis.z).normalized()

func _assert_envelope_visible(widget, skeleton: Skeleton3D, profile: Dictionary) -> void:
	var bone := skeleton.find_bone(str(profile.bone))
	var delta := skeleton.get_bone_global_pose(bone) * skeleton.get_bone_global_rest(bone).affine_inverse()
	var bounds: AABB = profile.bounds
	var inside := true
	for endpoint: int in range(8):
		var point := skeleton.global_transform * (delta * bounds.get_endpoint(endpoint))
		var projected: Vector2 = widget._camera.unproject_position(point)
		inside = inside and not widget._camera.is_position_behind(point) \
			and Rect2(Vector2.ZERO, Vector2(widget._viewport.size)).grow(1).has_point(projected)
	expect(inside, "the measured head envelope fits the square portrait, including its current pose")
