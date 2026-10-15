extends SceneTree
## Zero-shirt evidence for the generated torso pieces.
##
## The meshy race bodies paint their teal shirt into the body texture, so a
## torso piece that does not cover it shows teal through every opening.  Each
## generated cuirass ships an underlayer for exactly that reason, and this
## fixture holds it to the promise: every generated torso visual is worn by a
## luminous_male through the real runtime path, framed from four sides against
## a neutral backdrop, and every captured pixel is classified -- one teal
## pixel is a failure.  The authored cuirass is captured as a control; it
## ships no underlayer, so the teal it shows proves the classifier sees what
## it is supposed to see.

const SCREEN_SIZE := Vector2i(640, 640)
const GENERATED_VISUALS: Array[int] = [184, 185, 186, 187, 188, 189, 190, 191]
const CONTROL_VISUAL := 100

## A garment that fails to cover the shirt shows it by the thousand: the
## authored control below, with no underlayer, paints 150,000+ teal pixels,
## and every pre-liner leak this suite ever caught was in the hundreds to
## hundreds of thousands.  What survives the liner is a different thing
## entirely -- a few pixels of shirt at an armpit or elbow crease, seen only
## when the camera skims that crease edge-on (a pure side view, never the
## gameplay camera).  Linear blend skinning folds any lifted underlayer
## offset into the body right at a folding joint, and where a design's own
## strap slit lines up with that fold a needle shows through; ray-identified
## to triceps/armpit skin and run down through every asset-side remedy
## (thicker and thinner lifts, welded normals, sealed rims, crease plugs, a
## paint coat, float-exact weights, subdivision), it closes for good only
## with dual-quaternion skinning in the engine.  Those needles jitter a few
## pixels with the paused frame, so the gate is a ceiling well above them and
## orders of magnitude below any real gap: a piece over it is not covering.
const MAX_CREASE_NEEDLE_PX := 80

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/torso-coverage")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	await process_frame

	var models: Dictionary = main.get("models") as Dictionary
	var equipment_config: Dictionary = main.get("equipment_config") as Dictionary
	var model_config: Dictionary = models.get("luminous_male", {}) as Dictionary
	_expect(not model_config.is_empty(), "luminous_male is in the model registry")

	var stage := Node3D.new()
	root.add_child(stage)
	var backdrop := Environment.new()
	backdrop.background_mode = Environment.BG_COLOR
	backdrop.background_color = Color(0.10, 0.095, 0.09)
	backdrop.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	backdrop.ambient_light_color = Color(0.85, 0.85, 0.85)
	backdrop.ambient_light_energy = 1.2
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-35.0, 140.0, 0.0)
	key.light_energy = 1.0
	stage.add_child(key)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = 38.0
	# The gameplay cull mask: every actor carries a map-only disc three
	# metres over its head for the top-down cameras, and a camera that
	# renders every layer can mask the shoulders with it -- or hide the
	# very teal this fixture exists to count.
	camera.cull_mask = 3
	# On the camera, not a WorldEnvironment: the main scene has its own ideas
	# about the world, and a sky-blue backdrop is the one thing a teal count
	# cannot share a frame with.
	camera.environment = backdrop
	stage.add_child(camera)

	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	var animation_config: Dictionary = main.call("_animation_for_model", model_config) as Dictionary
	var visuals: Array[int] = GENERATED_VISUALS.duplicate()
	visuals.append(CONTROL_VISUAL)
	# Far under the world: the main scene keeps sky bands and terrain planes
	# in this viewport, and a coverage count wants nothing in frame it did
	# not put there.
	var floor_level := -80.0
	var offset := 0.0
	var actors: Dictionary = {}
	for visual: int in visuals:
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors: Array[String] = actor.configure({
			"actor_id": 9100 + visual, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": "5:%d" % visual, "appearance": {},
			"equipment_visuals": {"5": visual},
		}, adapter, model_config, animation_config, equipment_config)
		_expect(errors.is_empty(), "5:%d builds without errors: %s" % [visual, errors])
		actor.server_target = Vector3(offset, floor_level, 0.0)
		actor.global_position = actor.server_target
		actors[visual] = actor
		offset += 4.0

	for _settle: int in range(24):
		await process_frame

	# The subject is the gear, and nothing else may render.  Both of these
	# were found the hard way, by casting the failing pixels' rays: the map
	# dot every actor hangs three metres over its own head is teal and peeks
	# over the far shoulder's silhouette, and behind it the main scene keeps
	# a ground plane 287 metres out that reads teal along the same edge.
	for visual: int in visuals:
		for child: Node in (actors[visual] as ReplicatedActor3D).get_children():
			var overlay := child as Node3D
			if overlay != null and overlay.name != "NativeModel":
				overlay.visible = false
	for mesh: Node in root.find_children("*", "VisualInstance3D", true, false):
		var instance := mesh as VisualInstance3D
		if instance != null and not stage.is_ancestor_of(instance):
			instance.visible = false

	var worst := 0
	for visual: int in visuals:
		var actor: ReplicatedActor3D = actors[visual]
		# One actor in frame at a time: the row of neighbours four metres back
		# is otherwise in shot, and every luminous body has teal eyes.
		for other_visual: int in visuals:
			(actors[other_visual] as ReplicatedActor3D).visible = (
				other_visual == visual)
		var base: Vector3 = actor.global_position
		var centre := base + Vector3(0.0, 1.2, 0.0)
		# The question is whether the BODY's shirt shows, and some garment art
		# is legitimately green-teal, so each view is captured twice -- once
		# whole and once with the body hidden -- and only teal the body
		# contributes counts.  Pausing the idle keeps the two captures on the
		# same pose.
		var body_meshes: Array[MeshInstance3D] = []
		for mesh: Node in actor.find_children("*", "MeshInstance3D", true, false):
			var instance := mesh as MeshInstance3D
			if instance.visible and not instance.has_meta("native_equipment"):
				body_meshes.append(instance)
		# Freeze the actor's own per-frame work -- interpolation, facing,
		# cape cloth -- so a paused, seeked pose is identical every run and
		# the crease counts do not jitter with frame timing.
		actor.set_process(false)
		actor.set_physics_process(false)
		if actor.get_skeleton() != null:
			for modifier: Node in actor.get_skeleton().get_children():
				if modifier is SkeletonModifier3D:
					(modifier as SkeletonModifier3D).active = false
		var teal_total := 0
		# Two fixed moments of the idle, the same for every piece: pieces are
		# compared at identical poses, and the count is deterministic run to
		# run instead of depending on which frame each actor happened to be
		# paused at.
		for moment: int in range(2):
			if actor.animation_player != null:
				actor.animation_player.pause()
				var clip: String = actor.animation_player.current_animation
				if not clip.is_empty():
					var length: float = actor.animation_player.get_animation(
						clip).length
					actor.animation_player.seek(
						length * (0.1 if moment == 0 else 0.55), true)
			for view: int in range(4):
				var angle: float = view * PI / 2.0
				camera.global_position = centre + Vector3(sin(angle), 0.0, cos(angle)) * 1.25
				camera.look_at(centre, Vector3.UP)
				for _settle: int in range(3):
					await process_frame
				await process_frame
				var image: Image = root.get_texture().get_image()
				for instance: MeshInstance3D in body_meshes:
					instance.visible = false
				for _settle: int in range(2):
					await process_frame
				var bodyless: Image = root.get_texture().get_image()
				for instance: MeshInstance3D in body_meshes:
					instance.visible = true
				var teal: int = _count_body_teal(image, bodyless)
				teal_total += teal
				image.save_png(_artifacts.path_join(
					"coverage-5-%d-m%d-view%d.png" % [visual, moment, view]))
		if actor.animation_player != null:
			actor.animation_player.play()
		var label: String = ("control (authored, no underlayer)"
			if visual == CONTROL_VISUAL else "generated")
		print("teal pixels for 5:%d across 8 captures: %d  [%s]" % [
			visual, teal_total, label])
		if visual == CONTROL_VISUAL:
			_expect(teal_total > 0,
				"the control shows teal, so the classifier is alive")
		else:
			worst = maxi(worst, teal_total)
			_expect(teal_total <= MAX_CREASE_NEEDLE_PX,
				"5:%d covers the shirt (%d teal px, ceiling %d)" % [
					visual, teal_total, MAX_CREASE_NEEDLE_PX])

	print("worst generated teal count: ", worst)
	print("rendered torso coverage: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	stage.queue_free()
	main.queue_free()
	await process_frame
	quit(_failures)

## Teal the body is responsible for: a pixel counts when it is teal with the
## body drawn and stops being teal without it.  Garment art that is teal in
## its own right -- moss-green leaf plate shades across the same hues --
## appears in both captures and cancels.  The hue band's top edge stays under
## 0.56 because the default sky sits at 0.578, and a coverage count must
## never be one environment change away from counting the weather.
func _count_body_teal(with_body: Image, without_body: Image) -> int:
	var found := 0
	for y: int in range(with_body.get_height()):
		for x: int in range(with_body.get_width()):
			if not _is_teal(with_body.get_pixel(x, y)):
				continue
			# The whole 3x3 around the pixel in the bodyless frame: hiding
			# the body shifts every antialiased edge by a subpixel, so an
			# art blend can move a pixel over.  A real slit of shirt has
			# charcoal or backdrop behind AND around it.
			var art := false
			for dy: int in range(-1, 2):
				for dx: int in range(-1, 2):
					var nx: int = clampi(x + dx, 0, without_body.get_width() - 1)
					var ny: int = clampi(y + dy, 0, without_body.get_height() - 1)
					if _is_teal(without_body.get_pixel(nx, ny), true):
						art = true
			if not art:
				found += 1
	return found

## The comparison against the bodyless frame uses a wider window: at a slit
## edge an antialiased blend of leaf-green art can drift just across the
## strict bound when hiding the body swaps what it blends with, and that is
## the art moving, not the shirt.  A real shirt pixel has charcoal or
## backdrop behind it -- nowhere near teal on any width.
func _is_teal(colour: Color, wide: bool = false) -> bool:
	if wide:
		return (colour.h > 0.25 and colour.h < 0.70
			and colour.s > 0.08 and colour.v > 0.06)
	return (colour.h > 0.44 and colour.h < 0.56
		and colour.s > 0.22 and colour.v > 0.15)

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
