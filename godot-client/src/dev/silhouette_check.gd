extends Node3D

## Verifies the occluded-actor silhouette against a known-answer scene.
##
## An actor stand-in is half hidden behind an opaque blocker. Three frames are
## captured: the actor alone (its full screen footprint), the actor behind the
## blocker (the part still visible), and the same with the silhouette on. The
## silhouette must cover exactly the hidden part, none of the visible part, and
## nothing outside the actor at all.
##
##     Godot --path godot-client --rendering-driver opengl3 \
##         --script src/dev/silhouette_check.gd

var actor_root: Node3D
var actor_mesh: MeshInstance3D
var blocker: MeshInstance3D
var silhouette: OccludedSilhouette

func _ready() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.09, 0.09, 0.14)
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var cam := Camera3D.new()
	cam.position = Vector3(0, 0, 4)
	cam.current = true
	add_child(cam)

	actor_root = Node3D.new()
	add_child(actor_root)
	actor_mesh = MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.9
	sphere.height = 1.8
	sphere.radial_segments = 48
	sphere.rings = 24
	actor_mesh.mesh = sphere
	var amat := StandardMaterial3D.new()
	amat.albedo_color = Color(0.15, 0.25, 0.9)
	amat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	actor_mesh.material_override = amat
	actor_root.add_child(actor_mesh)

	blocker = MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(1.6, 4.0, 0.2)
	blocker.mesh = box
	var bmat := StandardMaterial3D.new()
	bmat.albedo_color = Color(0.9, 0.9, 0.2)
	bmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	blocker.material_override = bmat
	blocker.position = Vector3(-0.8, 0, 1.5)
	add_child(blocker)

	silhouette = OccludedSilhouette.new(actor_root, null)
	silhouette.set_enabled(true)
	var full := await _grab()

	silhouette.set_enabled(false)
	var control := await _grab()

	blocker.visible = false
	var mask := await _grab()

	var footprint := 0
	var visible_px := 0
	var drawn := 0
	var on_hidden := 0
	var on_visible := 0
	var outside := 0
	for y in mask.get_height():
		for x in mask.get_width():
			var is_actor := _is_actor(mask.get_pixel(x, y))
			var still_visible := _is_actor(control.get_pixel(x, y))
			# Colour-independent: the silhouette drew wherever turning it on
			# changed the pixel. No predicate to mis-tune on the rim.
			var is_silhouette := full.get_pixel(x, y) != control.get_pixel(x, y)
			if is_actor:
				footprint += 1
			if still_visible:
				visible_px += 1
			if is_silhouette:
				drawn += 1
				if is_actor and not still_visible:
					on_hidden += 1
				elif still_visible:
					on_visible += 1
				else:
					outside += 1
	var hidden_px := footprint - visible_px
	print("[silhouette] footprint=%d visible=%d hidden=%d" % [footprint, visible_px, hidden_px])
	print("[silhouette] drawn=%d on_hidden=%d on_visible=%d outside=%d"
		% [drawn, on_hidden, on_visible, outside])

	var covers: bool = hidden_px > 0 and float(on_hidden) / float(hidden_px) > 0.99
	var spares: bool = on_visible == 0
	var contained: bool = outside == 0
	# Disabling it must leave nothing behind: no clones, no marker overlay.
	var clean: bool = actor_mesh.material_overlay == null \
		and actor_root.find_children("*" + OccludedSilhouette.CLONE_PREFIX + "*",
			"MeshInstance3D", true, false).is_empty()
	print("[silhouette] covers_hidden=%s spares_visible=%s contained=%s teardown_clean=%s"
		% [covers, spares, contained, clean])
	var geometry_ok: bool = covers and spares and contained and clean
	var skinned_ok: bool = await _check_real_actor()
	print("[silhouette] verdict=%s"
		% ("PASS" if (geometry_ok and skinned_ok) else "FAIL"))
	get_tree().quit(0 if (geometry_ok and skinned_ok) else 1)

## The pixel test above uses an unskinned stand-in. Real actors are skinned, and
## a silhouette clone that does not follow the skeleton would sit in the bind
## pose while the character walks out from under it. This builds an actual
## ReplicatedActor3D from the model registry, wearing the full equipment set,
## and checks that every clone is bound to the skeleton and moves with the pose.
func _check_real_actor() -> bool:
	actor_root.visible = false
	blocker.visible = false
	var registry: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/models.json"))
	var models: Dictionary = registry.get("models", {}) as Dictionary
	var model_id := "luminous_female"
	var model_config: Dictionary = models.get(model_id, {}) as Dictionary
	var animation_config: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(str(model_config.get(
			"animationMap", "res://data/animations/luminous.json"))))
	var equipment_config: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/equipment.json"))

	var real := ReplicatedActor3D.new()
	real.name = "SilhouetteActor"
	add_child(real)
	var dto := {"actor_id": 1, "x": 0, "y": 0, "rotation": 0,
		"appearance": {"skin": 1, "hair": 2, "eyes": 3,
			"shirt": 1, "pants": 2, "boots": 3, "head": 1},
		"equipment_visuals": {0: 100, 1: 100, 2: 100, 3: 100,
			4: 100, 5: 100, 6: 100, 7: 100}}
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true})
	var errors := real.configure(dto, adapter, model_config,
		animation_config, equipment_config)
	if not errors.is_empty():
		print("[silhouette] real actor failed to build: ", "; ".join(errors))
		return false

	# The body meshes the silhouette should copy: everything except the
	# gameplay-only overlays (the selection ring), which are UI, not anatomy.
	var body_meshes := 0
	for node: Node in real.find_children("*", "MeshInstance3D", true, false):
		var m: MeshInstance3D = node as MeshInstance3D
		if m.layers != OccludedSilhouette.GAMEPLAY_ONLY_VISUAL_LAYER 				and m.mesh != null and m.mesh.get_surface_count() > 0:
			body_meshes += 1
	var before_meshes: int = real.render_diagnostics()["meshes"].size()
	real.set_occlusion_silhouette_enabled(true)
	var clones: Array[Node] = real.find_children(
		OccludedSilhouette.CLONE_PREFIX + "*", "MeshInstance3D", true, false)
	var after_meshes: int = real.render_diagnostics()["meshes"].size()

	# A clone deforms identically to its source exactly when it carries the same
	# Skin and resolves to the same Skeleton3D. There is no way to read back
	# deformed vertices, so this is the check that actually proves it - a clone
	# left in the bind pose would fail one of the two.
	var skinned := 0
	var unskinned := 0
	var unbound: Array[String] = []
	for node: Node in clones:
		var clone: MeshInstance3D = node as MeshInstance3D
		var source_name: String = clone.name.trim_prefix(OccludedSilhouette.CLONE_PREFIX)
		if clone.skin != null:
			var clone_skeleton: Node = clone.get_node_or_null(clone.skeleton)
			if clone_skeleton is Skeleton3D and clone_skeleton == real.get_skeleton():
				skinned += 1
			else:
				unbound.append(source_name + " (skin not bound to the actor skeleton)")
		elif clone.get_parent() is MeshInstance3D 				and clone.transform == Transform3D.IDENTITY:
			unskinned += 1      # rides its source's transform
		else:
			unbound.append(source_name + " (neither skinned nor parented to its source)")

	# Advance a walk cycle and confirm the clones deform with it. A clone stuck
	# in the bind pose would report the same box on every frame.
	var sample: MeshInstance3D = null
	for node: Node in clones:
		var clone: MeshInstance3D = node as MeshInstance3D
		if clone.skin != null:
			sample = clone
			break
	var animated := false
	var skeleton: Skeleton3D = real.get_skeleton()
	if sample != null and real.animation_player != null and skeleton != null:
		var clips: PackedStringArray = real.animation_player.get_animation_list()
		if clips.size() > 0:
			real.animation_player.play(StringName(clips[0]))
		var first: Array[Transform3D] = []
		for b in skeleton.get_bone_count():
			first.append(skeleton.get_bone_global_pose(b))
		for i in 30:
			await RenderingServer.frame_post_draw
		var moved := 0
		for b in skeleton.get_bone_count():
			if not first[b].is_equal_approx(skeleton.get_bone_global_pose(b)):
				moved += 1
		animated = moved > 0
		print("[silhouette] real actor: clips=%d playing=%s bones=%d moved=%d"
			% [clips.size(), real.animation_player.current_animation,
				skeleton.get_bone_count(), moved])

	print("[silhouette] real actor: body_meshes=%d clones=%d skinned=%d unskinned=%d unbound=%s"
		% [body_meshes, clones.size(), skinned, unskinned, str(unbound)])
	print("[silhouette] real actor: diagnostics_unchanged=%s skeleton_animated=%s"
		% [before_meshes == after_meshes, animated])

	var ok: bool = clones.size() == body_meshes and clones.size() > 0 		and unbound.is_empty() and skinned > 0 and animated 		and before_meshes == after_meshes
	real.set_occlusion_silhouette_enabled(false)
	await get_tree().process_frame          # queue_free() lands next frame
	var left_behind := 0
	for node: Node in real.find_children("*", "MeshInstance3D", true, false):
		if node.has_meta(OccludedSilhouette.CLONE_META):
			left_behind += 1
	var overlays_left := 0
	for node: Node in real.find_children("*", "MeshInstance3D", true, false):
		if (node as MeshInstance3D).material_overlay != null:
			overlays_left += 1
	print("[silhouette] real actor: clones_after_disable=%d overlays_after_disable=%d ok=%s"
		% [left_behind, overlays_left, ok])
	return ok and left_behind == 0 and overlays_left == 0

func _grab() -> Image:
	for i in 3:
		await RenderingServer.frame_post_draw
	return get_viewport().get_texture().get_image()

func _is_actor(c: Color) -> bool:
	return c.b > 0.6 and c.b > c.r + 0.2 and c.b > c.g + 0.2
