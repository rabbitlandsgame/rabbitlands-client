extends SceneTree

## Known-answer checks for OccluderFade against a hand-built world.
##
## The camera sits above and behind the player, so the segment between them runs
## through a fixed point. A box parked on that point must fade, a box beside it
## must not, ground must never fade at all, and everything must come back
## exactly as it was found - including a prop the loader had collapsed into a
## MultiMesh, which has to be lifted out for the fade and handed back after.
##
## Every check runs twice: with the look pass off (ELORIA_LOOK=0), where a
## faded obstacle takes a blended copy of its material as on develop, and with
## it on (the variable unset, the client's default), where LookFade swaps in a
## dithered copy that stays solid and opens a hole round the player, and a
## wall hands its shadow to a shadow-only twin while it fades.
##
## Run: Godot_v4.7.2-stable_win64.exe --headless --path . \
##         --script tests/test_occluder_fade.gd

# Preloaded rather than reached by class name: the global class cache is a
# build artifact, and a working copy that has not been opened in the editor
# since this file was added does not carry OccluderFade in it yet.
const OccluderFadeScript := preload("res://src/world/occluder_fade.gd")

const PLAYER_POSITION := Vector3.ZERO
const CAMERA_POSITION := Vector3(0.0, 10.0, 10.0)
## On the segment from the camera to the player's chest, roughly half way.
const ON_THE_LINE := Vector3(0.0, 5.5, 5.0)
const OFF_TO_THE_SIDE := Vector3(20.0, 5.5, 5.0)
## Long enough that a fade of FADE_SECONDS finishes inside one step.
const SETTLE := 0.5

var failures: int = 0
## Which pass is running: the look on (the default) or off (ELORIA_LOOK=0).
var look := false

var world: Node3D
var camera: Camera3D
var player: Node3D
var blocker: MeshInstance3D
var aside: MeshInstance3D
var ground: MeshInstance3D
var batched: MeshInstance3D
var batch: MultiMeshInstance3D

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	for look_on: bool in [false, true]:
		look = look_on
		if look_on:
			OS.unset_environment(LookProfile.ENABLE_VARIABLE)
		else:
			OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
		_expect(LookProfile.enabled() == look_on, "the pass is switched as this run expects")
		await _run_pass()
	if previous.is_empty():
		OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	else:
		OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	print("occluder fade tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _run_pass() -> void:
	_build_world()
	await process_frame

	var fade: RefCounted = OccluderFadeScript.new()
	var indexed: int = fade.configure(null, world)
	_expect(indexed == 3,
		"blocker, aside and the batched prop index; the walk surface does not")

	# Disabled: the probe runs but marks nothing.
	fade.update(SETTLE, camera, player)
	_expect(blocker.get_surface_override_material(0) == null,
		"nothing fades while the setting is off")

	fade.set_enabled(true)
	fade.update(SETTLE, camera, player)

	var faded: Material = blocker.get_surface_override_material(0)
	if look:
		_expect(faded is ShaderMaterial
				and (faded as ShaderMaterial).shader == LookFade.SHADER_STANDARD,
			"an obstacle on the sight line takes a dithered copy of its material")
		if faded is ShaderMaterial:
			_expect(is_equal_approx(float((faded as ShaderMaterial).get_shader_parameter(
					LookFade.OPEN_PARAMETER)), 1.0),
				"the settled fade has opened its hole all the way")
		# LookFade decides how it fades: a wall that keeps its hole hands its
		# shadow to a solid twin, one that vanishes casts none.
		_expect(blocker.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				and (_shadow_twin(blocker) != null)
					== (LookFade.mode_of(blocker) == LookFade.Mode.HOLE),
			"the faded wall stops casting, its shadow on a twin only while it keeps a hole")
	else:
		_expect(faded is BaseMaterial3D,
			"an obstacle on the sight line takes a faded material of its own")
		if faded is BaseMaterial3D:
			_expect((faded as BaseMaterial3D).transparency == BaseMaterial3D.TRANSPARENCY_ALPHA,
				"the faded material blends instead of writing depth")
		_expect(blocker.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON
				and _shadow_twin(blocker) == null,
			"with the pass off the faded obstacle keeps its own shadow")
	_expect(is_equal_approx(_opacity(faded), OccluderFadeScript.FADED_ALPHA),
		"the fade settles at FADED_ALPHA")
	_expect(faded != blocker.mesh.surface_get_material(0),
		"the shared imported material is duplicated, not edited")
	_expect(is_equal_approx(blocker.mesh.surface_get_material(0).albedo_color.a, 1.0),
		"the material the mesh still shares with every other copy stays opaque")

	_expect(aside.get_surface_override_material(0) == null,
		"an obstacle beside the sight line is left alone")
	_expect(ground.get_surface_override_material(0) == null,
		"the walk surface under the player never fades")

	_expect(batched.visible and batched.get_surface_override_material(0) != null,
		"a batched prop on the sight line is lifted out of the batch to fade")
	if _multimesh_stores_transforms():
		_expect(batch.multimesh.get_instance_transform(0).basis.determinant() == 0.0,
			"the batch stops drawing the instance that was lifted out")

	# Walking clear of the obstacles: everything blends back and is handed back.
	player.global_position = Vector3(0.0, 0.0, 60.0)
	camera.global_position = Vector3(0.0, 10.0, 70.0)
	await process_frame
	fade.update(SETTLE, camera, player)
	_expect(blocker.get_surface_override_material(0) == null,
		"an obstacle that clears the sight line gets its own material back")
	_expect(blocker.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			and _shadow_twin(blocker) == null,
		"and its own shadow, with no twin left behind")
	_expect(not batched.visible
			and batched.get_surface_override_material(0) == null,
		"the lifted prop is handed back to the batch")
	if _multimesh_stores_transforms():
		_expect(batch.multimesh.get_instance_transform(0).origin.is_equal_approx(
				ON_THE_LINE),
			"the batch draws the returned instance where it always stood")

	# A map change frees the world while obstacles are still faded.
	player.global_position = PLAYER_POSITION
	camera.global_position = CAMERA_POSITION
	await process_frame
	fade.update(SETTLE, camera, player)
	_expect(blocker.get_surface_override_material(0) != null, "faded again")
	fade.reset()
	_expect(blocker.get_surface_override_material(0) == null,
		"reset restores every obstacle it was holding")
	_expect(fade.configure(null, null) == 0, "a world that failed to load indexes nothing")

	var manifest := WorldManifest.new()
	manifest.data = {"rendering": {"occluderFadeAlpha": 0.08}}
	fade.configure(manifest, world)
	fade.update(SETTLE, camera, player)
	_expect(is_equal_approx(_opacity(blocker.get_surface_override_material(0)), 0.08),
		"layered gates use their map's readable opacity")
	fade.configure(null, world)
	fade.update(SETTLE, camera, player)
	_expect(is_equal_approx(_opacity(blocker.get_surface_override_material(0)), OccluderFadeScript.FADED_ALPHA),
		"the following map restores the ordinary fade opacity")
	fade.reset()
	_test_causeway_structures()
	_test_authored_ground_patches()

	_test_precise_blockers()

	world.queue_free()
	await process_frame

## A miniature of what the world loader leaves behind: loose meshes, a walk
## surface carrying navigation collision, and one prop collapsed into a batch
## with its source node hidden and stamped.
func _build_world() -> void:
	world = Node3D.new()
	world.name = "ImportedWorld_test"
	root.add_child(world)

	camera = Camera3D.new()
	camera.position = CAMERA_POSITION
	world.add_child(camera)

	player = Node3D.new()
	player.position = PLAYER_POSITION
	world.add_child(player)

	blocker = _box("Blocker", ON_THE_LINE)
	aside = _box("Aside", OFF_TO_THE_SIDE)

	ground = _box("Terrain_Ground", ON_THE_LINE)
	var body := StaticBody3D.new()
	body.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	ground.add_child(body)

	batched = _box("BatchedProp", ON_THE_LINE)
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.mesh = batched.mesh
	multimesh.instance_count = 1
	multimesh.set_instance_transform(0, batched.transform)
	batch = MultiMeshInstance3D.new()
	batch.name = "StaticBatch_0_BatchedProp"
	batch.multimesh = multimesh
	world.add_child(batch)
	batched.visible = false
	batched.set_meta(WorldLoader.BATCH_META, batch)
	batched.set_meta(WorldLoader.BATCH_INDEX_META, 0)

func _test_causeway_structures() -> void:
	var causeway_nodes: Array[MeshInstance3D] = []
	for node_name: String in [
			"Structure_StreamCauseway_four-gates-crownwater_pale_ashlar",
			"Structure_StreamCauseway_four-gates-crownwater_rubble_stone",
			"Structure_StreamCauseway_four-gates-crownwater_pale_ashlar_StreamOverflow_four-gates-crownwater",
			"StreamView_four-gates-crownwater__Structure_StreamCauseway_four-gates-crownwater_pale_ashlar"]:
		var curb := _box(node_name, Vector3(0.0, -0.2, 0.0))
		# The real merged slab/curb bounds: growing the top from 0.4m by
		# PROBE_RADIUS incorrectly reaches the player's 1m chest target.
		(curb.mesh as BoxMesh).size = Vector3(42.0, 1.2, 7.76)
		causeway_nodes.append(curb)
	var tower := _box("Structure_WatchTower", ON_THE_LINE)
	var preview_tower := _box(
		"StreamView_four-gates-crownwater__Structure_WatchTower", ON_THE_LINE)
	var fade: RefCounted = OccluderFadeScript.new()
	var manifest := WorldManifest.new()
	manifest.data = {"rendering": {"occluderFadeAlpha": 0.08}}
	_expect(fade.configure(manifest, world) == 5,
		"canonical causeway native/overflow/preview structures do not index; tall structures still do")
	fade.set_enabled(true)
	fade.update(SETTLE, camera, player)
	for curb: MeshInstance3D in causeway_nodes:
		_expect(curb.get_surface_override_material(0) == null,
			"low causeway stays opaque despite its enlarged sight-line box: " + str(curb.name))
	_expect(tower.get_surface_override_material(0) != null,
		"a tall native structure still fades")
	_expect(preview_tower.get_surface_override_material(0) != null,
		"a tall preview structure still fades")
	fade.reset()

## The continent exporter's ground patches - the Four Gates east forecourt, an
## Amberwood bed of leaf litter - lie over the walk surface with no collision of
## their own and are far narrower than the extent cap. They follow the ground's
## relief, so a patch the player stands on has a box deep enough that, grown by
## the probe radius, it holds the player's chest: left indexed, the ground under
## the player faded and the biome grass showed through.
func _test_authored_ground_patches() -> void:
	var fade: RefCounted = OccluderFadeScript.new()
	var before: int = fade.configure(null, world)
	var patches: Array[MeshInstance3D] = []
	for node_name: String in [
			"AuthoredGround_four_gates_four_gates-pass1-eastforecourt_four_gates_06_08",
			"AuthoredGround_amberwood_ground-04_leaf_litter",
			"StreamView_amberwood-four-gates__AuthoredGround_amberwood_ground-07_leaf_litter"]:
		var patch := _box(node_name, PLAYER_POSITION)
		(patch.mesh as BoxMesh).size = Vector3(28.0, 1.6, 38.0)
		patches.append(patch)
	# A walk surface is still known by its collision whatever it is called.
	var deck := _box("Deck_Harbour", ON_THE_LINE)
	var body := StaticBody3D.new()
	body.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	deck.add_child(body)

	# The patch geometry really does reach the probe; only its name saves it.
	var grown: AABB = patches[0].get_aabb().grow(OccluderFadeScript.PROBE_RADIUS)
	var chest: Vector3 = PLAYER_POSITION + Vector3(0.0, OccluderFadeScript.PROBE_HEIGHT, 0.0)
	_expect(OccluderFadeScript._segment_hits_box(grown,
			patches[0].to_local(camera.global_position), patches[0].to_local(chest)),
		"the patch's grown box holds the player's chest")

	_expect(fade.configure(null, world) == before,
		"authored ground patches, and a walk deck known only by its collision, do not index")
	fade.set_enabled(true)
	fade.update(SETTLE, camera, player)
	for patch: MeshInstance3D in patches:
		_expect(patch.get_surface_override_material(0) == null,
			"the ground patch under the player stays opaque: " + str(patch.name))
	_expect(deck.get_surface_override_material(0) == null,
		"a walk deck on the sight line stays opaque")
	_expect(blocker.get_surface_override_material(0) != null,
		"an obstacle standing on a ground patch still fades")
	fade.reset()

func _test_precise_blockers() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var view := Camera3D.new()
	view.position = CAMERA_POSITION
	stage.add_child(view)
	var actor := Node3D.new()
	stage.add_child(actor)
	var nearby := _box("Nearby", ON_THE_LINE + Vector3(1.55, 0, 0))
	var behind := _box("BehindPlayer", Vector3(0, -3.5, -5))
	# Two separated triangles enclose the sight line in their combined bounds,
	# but leave a real gap where the character is visible.
	var mesh := ArrayMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([
		Vector3(-3, -1, 0), Vector3(-1, -1, 0), Vector3(-2, 1, 0),
		Vector3(1, -1, 0), Vector3(3, -1, 0), Vector3(2, 1, 0)])
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, StandardMaterial3D.new())
	var gap := MeshInstance3D.new()
	gap.mesh = mesh
	gap.position = ON_THE_LINE
	stage.add_child(gap)
	var solid := _box("Solid", ON_THE_LINE)
	for prop: MeshInstance3D in [nearby, behind, solid]:
		prop.reparent(stage, false)
	var fade: RefCounted = OccluderFadeScript.new()
	fade.configure(null, stage)
	fade.set_enabled(true)
	fade.update(0.09, view, actor)
	_expect(nearby.get_surface_override_material(0) == null,
		"nearby scenery outside the tight body probe stays opaque")
	_expect(behind.get_surface_override_material(0) == null,
		"geometry behind the player stays opaque")
	_expect(gap.get_surface_override_material(0) == null,
		"empty space inside mesh bounds does not count as a blocker")
	var partial: Material = solid.get_surface_override_material(0)
	_expect(partial != null and _opacity(partial) > OccluderFadeScript.FADED_ALPHA
		and _opacity(partial) < 1.0, "a real blocker fades gradually")
	fade.update(SETTLE, view, actor)
	var alpha: float = _opacity(solid.get_surface_override_material(0))
	view.position.x = 20
	actor.position.x = 20
	fade.update(0.09, view, actor)
	_expect(is_equal_approx(_opacity(solid.get_surface_override_material(0)), alpha),
		"a brief clear sample holds the fade to avoid flicker")
	fade.update(0.09, view, actor)
	_expect(_opacity(solid.get_surface_override_material(0)) > alpha,
		"scenery restores smoothly after the hold")
	fade.update(SETTLE, view, actor)
	_expect(solid.get_surface_override_material(0) == null,
		"clear scenery regains its original material")
	fade.reset()
	stage.queue_free()

func _box(node_name: String, position: Vector3) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = Vector3(2.0, 2.0, 2.0)
	mesh.material = StandardMaterial3D.new()
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.position = position
	world.add_child(node)
	return node

## Whether the running rendering server keeps MultiMesh instance transforms at
## all. Godot's headless server is a stub that accepts every write and reports
## identity back, so under --headless the two assertions about what the batch
## draws would be testing the stub rather than this client. The node-side half
## of the same behaviour - hidden, lifted, hidden again - is observable either
## way, and is asserted unconditionally.
func _multimesh_stores_transforms() -> bool:
	var probe := MultiMesh.new()
	probe.transform_format = MultiMesh.TRANSFORM_3D
	probe.mesh = BoxMesh.new()
	probe.instance_count = 1
	var written := Transform3D(Basis(), Vector3(1.0, 2.0, 3.0))
	probe.set_instance_transform(0, written)
	return probe.get_instance_transform(0).origin.is_equal_approx(written.origin)

## A faded copy's opacity: a blended copy's albedo alpha, or the opacity a
## dithered look copy records (LookFade.FADE_PARAMETER); -1 for anything else.
func _opacity(material: Material) -> float:
	if material is BaseMaterial3D:
		return (material as BaseMaterial3D).albedo_color.a
	if material is ShaderMaterial:
		var value: Variant = (material as ShaderMaterial).get_shader_parameter(LookFade.FADE_PARAMETER)
		return float(value) if value != null else -1.0
	return -1.0

func _shadow_twin(node: MeshInstance3D) -> Node:
	return node.get_node_or_null(NodePath(String(LookFade.SHADOW_TWIN_NAME)))

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL (look %s): %s" % ["on" if look else "off", label])
