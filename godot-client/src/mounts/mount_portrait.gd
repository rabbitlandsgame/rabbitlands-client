extends SubViewportContainer
## The card displays the actual approved runtime model, including horse tack.
const Profiles := preload("res://src/mounts/mount_profiles.gd")
var viewport: SubViewport
var actor: ReplicatedActor3D

func configure(id: String) -> void:
	viewport = SubViewport.new()
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	stretch = true
	custom_minimum_size = Vector2(220, 215)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	viewport.own_world_3d = true
	viewport.size = Vector2i(2, 2)
	viewport.msaa_3d = Viewport.MSAA_2X
	add_child(viewport)
	var stage := Node3D.new()
	viewport.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("1b262b")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("d0dcf0")
	environment.environment.ambient_light_energy = .7
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-40, -35, 0)
	light.light_energy = 1.1
	stage.add_child(light)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	var profile := Profiles.read(id)
	camera.size = float(profile.get("portraitCameraSize", 2.75 if id == "golden_plains_horse" else 2.1))
	stage.add_child(camera)
	var center := float(profile.get("portraitLookAtHeight", 1.05 if id == "golden_plains_horse" else .73))
	camera.position = Vector3(3.5, 2.2, -4.8)
	camera.look_at(Vector3(0, center, 0))
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var config: Dictionary = models[id].duplicate(true)
	config.import.scale = float(config.import.scale) * float(profile.get("visualScale", 1.0))
	actor = ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors := actor.configure({"actor_id": 0, "x": 0, "y": 0, "rotation": 0, "kind": 5, "name": ""},
		CoordinateAdapter.new({"walkingHeight": 0.0}), config,
		JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
	if not errors.is_empty():
		push_warning("Mount portrait: " + str(errors))
		return
	var offset: Array = profile.get("visualOffsetMetres", [0.0, 0.0, 0.0])
	actor.position += Vector3(float(offset[0]), float(offset[1]), float(offset[2]))
	actor.set_physics_process(false)
	actor.set_process(false)
	for child: Node in actor.get_children():
		if child is Node3D and child.name != "NativeModel":
			(child as Node3D).hide()
	if profile.has("borrowedTack"):
		var tack := preload("res://src/mounts/borrowed_mount_tack.gd").new()
		stage.add_child(tack)
		var tack_errors := tack.configure(actor.get_skeleton(), profile.borrowedTack)
		if not tack_errors.is_empty():
			push_warning("Mount portrait tack: " + str(tack_errors))
		# Static portrait uses the native rest frame; its saddle stays aligned.
		actor.animation_player.pause()
	set_active(true)

func set_active(active: bool) -> void:
	if viewport == null:
		return
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS if active else SubViewport.UPDATE_DISABLED
	if actor != null and actor.animation_player != null:
		# A still card avoids a second animation/attachment clock in the HUD.
		actor.animation_player.pause()
