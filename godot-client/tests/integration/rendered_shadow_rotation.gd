extends SceneTree
## Rendered regression for camera-dependent clipping of tall sun-shadow casters.
## A fixed 68 m tower casts onto a fixed point on the ground. Orbit that point
## at several pitches and sun elevations; its shadow must remain there even
## when the tower is outside the camera view. Compare with a shadowless render
## of the same frame so the assertion measures lighting, not a property value.
## Run with the Compatibility renderer (not --headless). Add -- --baseline to
## reproduce the old 20 m depth and verify this test catches the regression.

const SIZE := Vector2i(640, 360)
var failures := 0
var samples := 0
var sun: DirectionalLight3D
var camera: Camera3D

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("This regression needs a real renderer; omit --headless.")
		quit(1)
		return
	root.size = SIZE
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	stage.add_child(environment)
	sun = DirectionalLight3D.new()
	stage.add_child(sun)
	var manifest := WorldManifest.new()
	manifest.data = {"environment": {"sun": {"shadows": true}}}
	WorldEnvironmentBinder.apply(manifest, environment, sun)
	if "--baseline" in OS.get_cmdline_user_args():
		sun.directional_shadow_pancake_size = 20.0
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.15
	environment.environment.ambient_light_sky_contribution = 0.0
	environment.environment.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
	environment.environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	camera = Camera3D.new()
	camera.current = true
	camera.fov = 50.0
	camera.near = 1.0
	camera.far = 1800.0
	stage.add_child(camera)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.7, 0.7, 0.7)
	material.roughness = 1.0
	var floor_node := MeshInstance3D.new()
	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = Vector2(800.0, 800.0)
	floor_mesh.material = material
	floor_node.mesh = floor_mesh
	stage.add_child(floor_node)
	var tower := MeshInstance3D.new()
	var tower_mesh := BoxMesh.new()
	tower_mesh.size = Vector3(6.0, 68.0, 6.0)
	tower_mesh.material = material
	tower.mesh = tower_mesh
	tower.position = Vector3(0.0, 34.0, 0.0)
	stage.add_child(tower)
	for elevation: float in [-15.5, -48.8, -62.0]:
		sun.rotation_degrees = Vector3(elevation, 130.0, 0.0)
		var direction := -sun.global_basis.z
		# Ground hit of a light ray through the upper tower, safely inside the
		# silhouette. The entire orbit sees this receiver without the tower
		# blocking it; moving the camera must never turn it into a lit point.
		var target := Vector3.UP * 55.0 + direction * (55.0 / -direction.y)
		for pitch_degrees: float in [-15.0, -40.0, -80.0]:
			for angle: int in range(0, 360, 45):
				var yaw := deg_to_rad(float(angle))
				var pitch := deg_to_rad(pitch_degrees)
				camera.look_at_from_position(target + Vector3(sin(yaw) * cos(pitch),
					-sin(pitch), cos(yaw) * cos(pitch)) * 26.0, target)
				sun.shadow_enabled = false
				var lit: float = await _sample()
				sun.shadow_enabled = true
				var shadowed: float = await _sample()
				samples += 1
				if shadowed >= lit * 0.75:
					failures += 1
					push_error("shadow clipped: sun=%s pitch=%s yaw=%s lit=%.3f shadow=%.3f"
						% [elevation, pitch_degrees, angle, lit, shadowed])
	print("shadow rotation: %d/%d passed (caster depth %.0f m)" %
		[samples - failures, samples, sun.directional_shadow_pancake_size])
	stage.queue_free()
	await process_frame
	quit(1 if failures > 0 else 0)

func _sample() -> float:
	for frame: int in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	var frame := root.get_texture().get_image()
	# The project's stretch mode can keep a larger render target than the
	# native window. Sample the actual image centre, where the camera aims.
	var centre := frame.get_size() / 2
	var brightness := 0.0
	for x: int in range(centre.x - 2, centre.x + 3):
		for y: int in range(centre.y - 2, centre.y + 3):
			brightness += frame.get_pixel(x, y).get_luminance()
	return brightness / 25.0
