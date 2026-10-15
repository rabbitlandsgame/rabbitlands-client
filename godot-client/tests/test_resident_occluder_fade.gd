extends SceneTree

const ManagerScript := preload("res://src/world/occluder_fade_manager.gd")
const FadeScript := preload("res://src/world/occluder_fade.gd")
const SETTLE := 0.5
const SIGHT_POINT := Vector3(0, 5.5, 5)
var failures := 0
var checks := 0
## Which pass is running: the look on (the default; a faded mesh takes
## LookFade's dithered copy) or off (ELORIA_LOOK=0; a blended copy, as on
## develop). Every check runs under both.
var look := false

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	for look_on: bool in [false, true]:
		look = look_on
		if look_on:
			OS.unset_environment(LookProfile.ENABLE_VARIABLE)
		else:
			OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
		_expect(LookProfile.enabled() == look_on, "the pass is switched as this run expects")
		_test_roots()
		_test_oriented_box()
		_test_main_binding()
		await process_frame
	if previous.is_empty():
		OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	else:
		OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	print("resident occluder fade: %d checks, %d failures" % [checks, failures])
	quit(failures)

func _test_roots() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var first := Node3D.new()
	var second := Node3D.new()
	stage.add_child(first)
	stage.add_child(second)
	second.position.x = 256
	var camera := Camera3D.new()
	var player := Node3D.new()
	stage.add_child(camera)
	stage.add_child(player)
	camera.position = Vector3(0, 10, 10)
	var first_prop := _box(first, "FirstTree", SIGHT_POINT)
	var second_prop := _box(second, "ResidentTree", SIGHT_POINT - second.position)
	var oversized := _box(second, "LargeScenery", SIGHT_POINT - second.position, Vector3(4, 2, 4))
	var actor := _box(stage, "ActorOutsideImportedRoots", SIGHT_POINT)
	var proxy := _box(second, "CollisionProxy", SIGHT_POINT - second.position)
	proxy.visible = false
	var preview_ground := _box(second, "ResidentGround", SIGHT_POINT - second.position)
	var preview_body := StaticBody3D.new()
	preview_body.collision_layer = 16
	preview_body.set_meta("stream_collision_layer", WorldLoader.NAVIGATION_SURFACE_LAYER)
	preview_ground.add_child(preview_body)
	var hidden_ground := _box(second, "HiddenNavigation", SIGHT_POINT - second.position)
	var hidden_body := StaticBody3D.new()
	hidden_body.collision_layer = 0
	hidden_body.set_meta("stream_collision_layer", WorldLoader.NAVIGATION_SURFACE_LAYER)
	hidden_ground.add_child(hidden_body)
	var batch_prop := _box(first, "BatchedTree", SIGHT_POINT)
	var batch := MultiMeshInstance3D.new()
	batch.multimesh = MultiMesh.new()
	batch.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	batch.multimesh.mesh = batch_prop.mesh
	batch.multimesh.instance_count = 1
	var batch_transform := batch_prop.transform
	batch.multimesh.set_instance_transform(0, batch_transform)
	first.add_child(batch)
	batch_prop.visible = false
	batch_prop.set_meta(WorldLoader.BATCH_META, batch)
	batch_prop.set_meta(WorldLoader.BATCH_INDEX_META, 0)
	var stored_transforms := batch.multimesh.get_instance_transform(0).is_equal_approx(batch_transform)
	var first_manifest := _manifest(0.22, 60)
	var second_manifest := _manifest(0.08, 3)
	second_manifest.data["collision"] = {"nodesAreProxies": true, "nodeNames": ["CollisionProxy"]}
	var manager: RefCounted = ManagerScript.new()
	var residents := {"second": {"root": second, "manifest": second_manifest}}
	_expect(manager.sync_worlds(first_manifest, first, residents) == 3,
		"only two trees and one batch source index; preview/hidden ground, proxy and oversized scenery do not")
	manager.update(SETTLE, camera, player)
	_expect(_material(first_prop) == null and _material(second_prop) == null,
		"disabled setting leaves both roots opaque")
	manager.set_enabled(true)
	# Cross the existing 12Hz probe interval, but keep the 140ms fade partial.
	manager.update(0.09, camera, player)
	var first_fade := _material(first_prop)
	var second_fade := _material(second_prop)
	_expect(first_fade != null and second_fade != null, "active and resident scenery both begin fading")
	_expect(batch_prop.visible and _material(batch_prop) != null, "resident-aware probe lifts the batch source")
	_expect(_material(actor) == null and _material(proxy) == null, "actor and collision proxy remain untouched")
	var first_alpha := _opacity(first_fade)
	var second_alpha := _opacity(second_fade)
	# The resident becomes active and the previous root stays resident. All
	# geometry, camera and player adopt the destination's translated frame.
	var rebase := Vector3(-256, 0, 0)
	first.position += rebase
	second.position += rebase
	camera.position += rebase
	player.position += rebase
	preview_body.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	residents = {"first": {"root": first, "manifest": first_manifest}}
	manager.sync_worlds(second_manifest, second, residents)
	_expect(_material(first_prop) == first_fade and _material(second_prop) == second_fade,
		"promotion retains the exact faded materials on both actual roots")
	_expect(first_fade != null and is_equal_approx(_opacity(first_fade), first_alpha)
		and second_fade != null and is_equal_approx(_opacity(second_fade), second_alpha),
		"promotion does not reset partially completed fades")
	manager.update(SETTLE, camera, player)
	_expect(_alpha(first_prop, 0.22) and _alpha(second_prop, 0.08),
		"root-local probes still hit after a 256m rebase and preserve each manifest's alpha")
	_expect(_material(preview_ground) == null and _material(hidden_ground) == null,
		"resident navigation never fades after physics-layer promotion")
	_expect(_material(oversized) == null, "resident maximum-extent rule survives promotion")
	# Moving and rotating an ancestor changes every global XZ grid cell, but
	# no mesh moved within its own imported root.
	stage.transform = Transform3D(Basis(Vector3.UP, 0.8), Vector3(371, 4, -293))
	manager.update(SETTLE, camera, player)
	_expect(_material(first_prop) == first_fade and _material(second_prop) == second_fade
		and _alpha(first_prop, 0.22) and _alpha(second_prop, 0.08),
		"whole-root translation/rotation keeps both original faded instances")
	for tick: int in 12:
		manager.sync_worlds(second_manifest, second, residents)
		manager.update(0.02, camera, player)
	_expect(_material(first_prop) == first_fade and _material(second_prop) == second_fade,
		"unchanged membership polls do not reconfigure or replace materials")
	manager.set_enabled(false)
	manager.update(0.02, camera, player)
	_expect(_material(first_prop) == first_fade and _opacity(first_fade) > 0.22 and _opacity(first_fade) < 1,
		"disabling blends all roots back rather than snapping")
	manager.update(SETTLE, camera, player)
	_expect(_material(first_prop) == null and _material(second_prop) == null,
		"disabled setting restores both roots' exact material overrides")
	_expect(not batch_prop.visible and _material(batch_prop) == null, "disabled setting restores the batch source")
	if stored_transforms:
		_expect(batch.multimesh.get_instance_transform(0).is_equal_approx(batch_transform), "disabled setting restores batch transform")
	else:
		print("resident fade: headless MultiMesh transform storage unavailable; material/node lifecycle checked")
	manager.set_enabled(true)
	manager.update(SETTLE, camera, player)
	first.visible = false
	manager.update(SETTLE, camera, player)
	_expect(not batch_prop.visible and _material(first_prop) == null and _alpha(second_prop, 0.08),
		"hidden resident batches stay hidden while the active root still fades")
	first.visible = true
	manager.update(SETTLE, camera, player)
	_expect(batch_prop.visible and _alpha(first_prop, 0.22), "visible retained root resumes fading")
	second_fade = _material(second_prop)
	manager.sync_worlds(second_manifest, second, {})
	_expect(_material(first_prop) == null and not batch_prop.visible and _material(batch_prop) == null,
		"eviction restores the retired root's materials and batch membership immediately")
	_expect(_material(second_prop) == second_fade, "eviction does not disturb the surviving root")
	if stored_transforms:
		_expect(batch.multimesh.get_instance_transform(0).is_equal_approx(batch_transform), "eviction restores batch transform after rebase")
	stage.remove_child(second)
	manager.update(SETTLE, camera, player)
	_expect(_material(second_prop) == null and not manager.is_active(), "detached root safely restores and leaves the manager")
	second.free()
	manager.sync_worlds(null, null, {"freed": {"root": second, "manifest": second_manifest}})
	manager.update(SETTLE, camera, player)
	_expect(not manager.is_active(), "stale freed resident reference is harmless")
	manager.sync_worlds(first_manifest, first, {})
	manager.update(SETTLE, camera, player)
	first.free()
	manager.update(SETTLE, camera, player)
	_expect(not manager.is_active(), "freeing an indexed root with an active batch fade is safe")
	manager.reset()
	stage.free()

func _test_oriented_box() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var world := Node3D.new()
	stage.add_child(world)
	world.position = Vector3(194, 0, -230)
	var wall := _box(world, "AngledWall", Vector3(0, 1, 0), Vector3(8, 2, 0.2))
	wall.rotation.y = PI / 4
	var target_prop := _box(world, "SightLineTree", Vector3(2.5, 1, 2.6), Vector3(0.2, 0.2, 0.2))
	var camera := Camera3D.new()
	var player := Node3D.new()
	stage.add_child(camera)
	stage.add_child(player)
	camera.position = world.position + Vector3(2.5, 1, 4)
	player.position = world.position + Vector3(2.5, 0, 2.5)
	var fade: RefCounted = FadeScript.new()
	fade.configure(null, world)
	fade.set_enabled(true)
	fade.update(SETTLE, camera, player)
	_expect(_material(target_prop) != null, "control obstacle on the short segment fades")
	_expect(_material(wall) == null, "oriented thin wall does not fade for a ray through only its expanded world AABB")
	fade.reset()
	stage.free()

func _test_main_binding() -> void:
	# Load after the SceneTree has installed actual project autoloads. A raw
	# --check-only invocation of main.gd lacks its Network/AppState globals.
	var main_script := load("res://src/app/main.gd") as GDScript
	_expect(main_script != null and main_script.can_instantiate(), "main script compiles with project autoloads")
	if main_script == null or not main_script.can_instantiate():
		return
	var hud: Control = main_script.new()
	var stage := Node3D.new()
	root.add_child(stage)
	var first := Node3D.new()
	var second := Node3D.new()
	stage.add_child(first)
	stage.add_child(second)
	var camera := Camera3D.new()
	var player := Node3D.new()
	stage.add_child(camera)
	stage.add_child(player)
	camera.position = Vector3(0, 10, 10)
	var a := _box(first, "First", SIGHT_POINT)
	var b := _box(second, "Second", SIGHT_POINT)
	var manifest := _manifest(0.3, 60)
	var loader := WorldLoader.new()
	loader.world_root = first
	loader.manifest = manifest
	var stream := ExteriorRegionStream.new()
	stream.residents = {"second": {"root": second, "manifest": manifest}}
	hud.world_loader = loader
	hud.exterior_stream = stream
	hud.gameplay_camera = camera
	var state := root.get_node("AppState")
	hud.actor_nodes[state.local_actor_id] = player
	hud._show_through_obstacles = true
	hud._configure_occluder_fade(manifest)
	hud._update_occluder_fade(SETTLE)
	var saved_a := _material(a)
	var saved_b := _material(b)
	_expect(saved_a != null and saved_b != null, "main configuration and update fade actual active and resident roots")
	loader.world_root = second
	stream.residents = {"first": {"root": first, "manifest": manifest}}
	hud._configure_occluder_fade(manifest)
	_expect(_material(a) == saved_a and _material(b) == saved_b,
		"main's load-completed configuration preserves retained fade state")
	stream.residents.clear()
	hud._update_occluder_fade(SETTLE)
	_expect(_material(a) == null and _material(b) == saved_b,
		"main frame reconciliation restores retired scenery without resetting active scenery")
	hud.occluder_fade.reset()
	loader.world_root = null
	hud.free()
	loader.free()
	stream.free()
	stage.free()

func _manifest(alpha: float, max_extent: float) -> WorldManifest:
	var result := WorldManifest.new()
	result.data = {"rendering": {"occluderFadeAlpha": alpha, "occluderFadeMaxExtentMetres": max_extent}}
	return result

func _box(parent: Node3D, label: String, position: Vector3, size := Vector3(2, 2, 2)) -> MeshInstance3D:
	var result := MeshInstance3D.new()
	result.name = label
	result.mesh = BoxMesh.new()
	(result.mesh as BoxMesh).size = size
	result.mesh.surface_set_material(0, StandardMaterial3D.new())
	result.position = position
	parent.add_child(result)
	return result

## The faded copy on a test box's surface, or null while it rests.
func _material(node: MeshInstance3D) -> Material:
	return node.get_surface_override_material(0)

## A faded copy's opacity: a blended copy's albedo alpha, or the opacity a
## dithered look copy records (LookFade.FADE_PARAMETER); -1 for anything else.
func _opacity(material: Material) -> float:
	if material is BaseMaterial3D:
		return (material as BaseMaterial3D).albedo_color.a
	if material is ShaderMaterial:
		var value: Variant = (material as ShaderMaterial).get_shader_parameter(LookFade.FADE_PARAMETER)
		return float(value) if value != null else -1.0
	return -1.0

## True when the box has faded to `expected` in the way this pass fades: a
## dithered look copy with the look on, a blended copy with it off.
func _alpha(node: MeshInstance3D, expected: float) -> bool:
	var material := _material(node)
	var kind_ok := material is ShaderMaterial if look else material is BaseMaterial3D
	return material != null and kind_ok and is_equal_approx(_opacity(material), expected)

func _expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL (look %s): %s" % ["on" if look else "off", label])
