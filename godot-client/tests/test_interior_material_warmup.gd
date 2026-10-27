extends SceneTree
## InteriorMaterialWarmup (src/world/interior_material_warmup.gd), headless.
##
##   godot --headless --path godot-client --script res://tests/test_interior_material_warmup.gd
##
## Covers: the materials-only GLB (header, chunks, one shared 1x1 image), the
## keys a synthetic document binds (samplers, the vertex-colour flag a
## coloured primitive sets, a primitive without a material, the loader's
## filter and alpha-scissor passes kept as separate keys), and on the real
## Landfall Town package: every material its shell ends up drawing with - as
## the preload's worker builds it, after the scenery stepper's styling - has
## a key the warm-up built (so the preload compiles no shader), and
## WorldPark.bind_map warms the Town once a session. The warm-up spread over
## frames (a walk over Landfall's border, final review 2026-10-27): one
## material's GLB keeps only what that material names, re-indexed; the plan
## and its steps bind exactly the keys `warm` binds, one material a frame; and
## WorldPark, bound with no curtain, spreads the Town's warm-up and holds its
## preload until it has run.
const Warmup := preload("res://src/world/interior_material_warmup.gd")
const Preparation := preload("res://src/world/map_material_preparation.gd")
const UndergroundScenery := preload("res://src/world/underground_scenery.gd")
const WorldParkScript := preload("res://src/world/world_park.gd")
const TOWN := "landfall_town"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func _run() -> void:
	_test_glb_container()
	_test_synthetic_keys()
	_test_spread_synthetic()
	await _test_town()
	for frame: int in 4:
		await process_frame
	print("Interior material warm-up: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)

func _document() -> Dictionary:
	return {"asset": {"version": "2.0"},
		"samplers": [{"wrapS": 10497, "wrapT": 10497}, {"wrapS": 33071, "wrapT": 33071}],
		"images": [{"uri": "missing-a.png"}, {"uri": "missing-b.png"}],
		"textures": [{"sampler": 0, "source": 0}, {"sampler": 1, "source": 1}],
		"materials": [
			{"name": "plaster", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
			{"name": "banner", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
			{"name": "spill", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 0.2]},
				"emissiveFactor": [0.3, 0.2, 0.1], "alphaMode": "BLEND"},
			{"name": "leaves", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}, "alphaMode": "MASK"}],
		"meshes": [{"primitives": [
			{"attributes": {"POSITION": 0}, "material": 0},
			{"attributes": {"POSITION": 0, "COLOR_0": 1}, "material": 3},
			{"attributes": {"POSITION": 0, "COLOR_0": 1}}]}]}

func _test_glb_container() -> void:
	var bytes := Warmup.materials_glb(_document())
	var stream := StreamPeerBuffer.new()
	stream.data_array = bytes
	_expect(stream.get_u32() == Warmup.GLB_MAGIC and stream.get_u32() == 2 and stream.get_u32() == bytes.size(),
		"the materials GLB has a glTF 2 header naming its own length")
	var json_length := stream.get_u32()
	_expect(stream.get_u32() == Warmup.CHUNK_JSON and json_length % 4 == 0, "its first chunk is padded JSON")
	var json: Variant = JSON.parse_string(stream.get_data(json_length)[1].get_string_from_utf8())
	_expect(json is Dictionary and not (json as Dictionary).has("meshes") and not (json as Dictionary).has("nodes"),
		"the JSON keeps no meshes or nodes")
	_expect(json is Dictionary and ((json as Dictionary).images as Array).size() == 2
		and str(((json as Dictionary).images as Array)[1]) == str(((json as Dictionary).images as Array)[0])
		and ((json as Dictionary).samplers as Array).size() == 2,
		"every image is the one embedded picture; the samplers are kept")
	var binary_length := stream.get_u32()
	_expect(stream.get_u32() == Warmup.CHUNK_BIN and binary_length % 4 == 0
		and stream.get_position() + binary_length == bytes.size(), "the second chunk is the padded picture")

func _test_synthetic_keys() -> void:
	var materials := Warmup.materials_of(_document())
	var by_name: Dictionary = {}
	for material: BaseMaterial3D in materials:
		if not by_name.has(material.resource_name):
			by_name[material.resource_name] = []
		(by_name[material.resource_name] as Array).append(material)
	_expect(by_name.has("plaster") and by_name.has("banner") and by_name.has("spill") and by_name.has("leaves"),
		"every material of the document is built")
	var plaster: BaseMaterial3D = (by_name.get("plaster", [null]) as Array)[0]
	var banner: BaseMaterial3D = (by_name.get("banner", [null]) as Array)[0]
	_expect(plaster != null and banner != null and plaster.albedo_texture != null
		and plaster.texture_repeat and not banner.texture_repeat,
		"textures are filled and a clamped sampler stays clamped (its own key)")
	_expect(plaster != null and plaster.texture_filter == Preparation.FILTER,
		"the loader's early filter is applied before the key is taken")
	_expect(plaster != null and banner != null and Warmup.signature(plaster) != Warmup.signature(banner),
		"the clamped decal and the wrapped wall differ in signature")
	var spill: BaseMaterial3D = (by_name.get("spill", [null]) as Array)[0]
	_expect(spill != null and spill.emission_enabled and spill.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED,
		"an emissive blend keeps its emission and transparency")
	var leaves: BaseMaterial3D = (by_name.get("leaves", [null]) as Array)[0]
	_expect(leaves != null and leaves.vertex_color_use_as_albedo
		and leaves.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR,
		"a coloured primitive turns its material's vertex colours on, as GLTFDocument does")
	var defaults := materials.filter(func(m: BaseMaterial3D) -> bool: return m.resource_name.is_empty())
	_expect(defaults.size() == 2 and defaults.any(func(m: BaseMaterial3D) -> bool:
			return m.vertex_color_use_as_albedo and m.texture_filter != Preparation.FILTER)
		and defaults.any(func(m: BaseMaterial3D) -> bool:
			return m.vertex_color_use_as_albedo and m.texture_filter == Preparation.FILTER),
		"a primitive without a material gets the import's default, at both of its keys (before and after the filter pass)")
	var empty := Warmup.materials_of({"asset": {"version": "2.0"}})
	_expect(empty.is_empty(), "a document with no materials or meshes builds nothing")
	var unreadable := Warmup.warm("user://no-such.glb")
	_expect(str(unreadable.error) == "glb_unreadable" and (unreadable.materials as Array).is_empty(),
		"a missing GLB warms nothing and says so")

## Runs a plan's steps as WorldPark does, one material (one RID) per step,
## the after-pass copy of a material as its own step: the materials built and
## the most a step took (microseconds).
static func _run_steps(plan: Dictionary) -> Dictionary:
	var materials: Array = []
	var slowest := 0
	for step: Dictionary in plan.get("steps", []) as Array:
		var began := Time.get_ticks_usec()
		var material := Warmup.build_step(step)
		slowest = maxi(slowest, Time.get_ticks_usec() - began)
		if material == null:
			continue
		materials.append(material)
		began = Time.get_ticks_usec()
		var after := Warmup.after_pass(material, bool(step.get("coloured", false)))
		if after != null:
			after.get_rid()
			materials.append(after)
		slowest = maxi(slowest, Time.get_ticks_usec() - began)
	return {"materials": materials, "slowest_usec": slowest}

static func _signatures(materials: Array) -> Dictionary:
	var keys: Dictionary = {}
	for material: BaseMaterial3D in materials:
		keys[Warmup.signature(material)] = true
	return keys

## A GLB holding `document`'s JSON alone (what `plan` reads).
static func _json_glb(document: Dictionary) -> PackedByteArray:
	var json := JSON.stringify(document).to_utf8_buffer()
	while json.size() % 4 != 0:
		json.append(0x20)
	var stream := StreamPeerBuffer.new()
	stream.put_u32(Warmup.GLB_MAGIC)
	stream.put_u32(2)
	stream.put_u32(12 + 8 + json.size())
	stream.put_u32(json.size())
	stream.put_u32(Warmup.CHUNK_JSON)
	stream.put_data(json)
	return stream.data_array

func _test_spread_synthetic() -> void:
	# One material's GLB: only its texture, that texture's sampler and image.
	var bytes := Warmup.materials_glb(_document(), [1])
	var stream := StreamPeerBuffer.new()
	stream.data_array = bytes
	stream.seek(12)
	var json_length := stream.get_u32()
	stream.get_u32()
	var json: Dictionary = JSON.parse_string(stream.get_data(json_length)[1].get_string_from_utf8())
	_expect((json.materials as Array).size() == 1 and str((json.materials as Array)[0].name) == "banner"
		and int(((json.materials as Array)[0].pbrMetallicRoughness as Dictionary).baseColorTexture.index) == 0
		and (json.textures as Array).size() == 1 and int((json.textures as Array)[0].sampler) == 0
		and int((json.textures as Array)[0].source) == 0 and (json.samplers as Array).size() == 1
		and int((json.samplers as Array)[0].wrapS) == 33071 and (json.images as Array).size() == 1,
		"one material's GLB keeps only its texture, re-indexed, with that texture's clamped sampler and one image")
	var lone := Warmup.materials_glb(_document(), [2])
	stream.data_array = lone
	stream.seek(12)
	json_length = stream.get_u32()
	stream.get_u32()
	json = JSON.parse_string(stream.get_data(json_length)[1].get_string_from_utf8())
	_expect((json.materials as Array).size() == 1 and (json.textures as Array).is_empty()
		and (json.images as Array).is_empty(), "an untextured material's GLB carries no texture or image")
	# The plan of the synthetic document, run step by step, binds warm's keys.
	var path := ProjectSettings.globalize_path("user://warmup-spread-test.glb")
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(_json_glb(_document()))
	file.close()
	var plan := Warmup.plan(path)
	_expect(str(plan.error).is_empty() and (plan.steps as Array).size() == 5,
		"the plan is one step per material and one per default material (%d)" % (plan.steps as Array).size())
	_expect(bool((plan.steps as Array)[3].coloured) and not bool((plan.steps as Array)[0].coloured)
		and bool((plan.steps as Array)[4].get("default", false)),
		"a step knows whether a coloured primitive draws its material")
	var spread := _run_steps(plan)
	var whole := _signatures(Warmup.materials_of(_document()))
	var stepped := _signatures(spread.materials)
	_expect(stepped.size() == whole.size() and stepped.keys().all(func(key: String) -> bool: return whole.has(key)),
		"the steps bind exactly the keys the whole warm-up binds (%d keys)" % whole.size())
	_expect(str(Warmup.plan("user://no-such.glb").error) == "glb_unreadable", "a missing GLB plans nothing and says so")
	DirAccess.remove_absolute(path)

## Every material the Town's shell draws with, as a worker builds it and the
## stepper styles it.
func _town_materials(shell: Node) -> Array:
	var found: Array = []
	for node: Node in shell.find_children("*", "GeometryInstance3D", true, false):
		var geometry := node as GeometryInstance3D
		if geometry.material_override is BaseMaterial3D:
			found.append(geometry.material_override)
		var mesh: Mesh = null
		if geometry is MeshInstance3D:
			mesh = (geometry as MeshInstance3D).mesh
		elif geometry is MultiMeshInstance3D and (geometry as MultiMeshInstance3D).multimesh != null:
			mesh = (geometry as MultiMeshInstance3D).multimesh.mesh
		if mesh == null:
			continue
		for surface: int in mesh.get_surface_count():
			if mesh.surface_get_material(surface) is BaseMaterial3D:
				found.append(mesh.surface_get_material(surface))
			if geometry is MeshInstance3D and (geometry as MeshInstance3D).get_surface_override_material(surface) is BaseMaterial3D:
				found.append((geometry as MeshInstance3D).get_surface_override_material(surface))
	return found

func _test_town() -> void:
	var registry: Dictionary = (JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json")) as Dictionary).get("maps", {})
	var entry := MapRegistry.resolve(registry, TOWN)
	var path := ProjectSettings.globalize_path(str(entry.get("manifest", "")))
	if not FileAccess.file_exists(path):
		print("SKIP: the Landfall Town package is not on disk")
		return
	preload("res://src/world/gltf_quantization.gd").ensure_registered()
	preload("res://src/world/vram_textures.gd").ensure_registered()
	preload("res://src/world/map_mesh_extension.gd").ensure_registered()
	var manifest := WorldManifest.load_file(path)
	var warmed := Warmup.warm(manifest.glb_path())
	_expect(str(warmed.error).is_empty() and int(warmed.keys) >= 4,
		"the Town's shell warms at least its four keys a fresh session lacked")
	var signatures: Dictionary = {}
	for material: BaseMaterial3D in warmed.materials:
		signatures[Warmup.signature(material)] = true
	var builder := WorldLoader.prepare_detached(path, false)
	var resident := builder.release_world(true, true)
	builder.free()
	var shell := resident.get("root") as Node3D
	_expect(shell != null, "the Town's shell builds as the preload's worker builds it")
	if shell == null:
		return
	var config := UndergroundScenery.config_for(TOWN)
	var surfaces: Variant = config.get("surfaces", {})
	UndergroundScenery.style_surfaces(shell, surfaces if surfaces is Dictionary else {},
		UndergroundScenery.floor_default(TOWN, config))
	var drawn := _town_materials(shell)
	var missing: Array = []
	for material: BaseMaterial3D in drawn:
		var key := Warmup.signature(material)
		if not signatures.has(key) and not missing.has(material.resource_name):
			missing.append(material.resource_name)
	_expect(drawn.size() > 20 and missing.is_empty(),
		"every material the shell draws with has a warmed key (%d drawn; unwarmed: %s)" % [drawn.size(), missing])
	shell.free()
	# WorldPark warms a flagged interior once, when its parent binds.
	var park: Node = WorldParkScript.new()
	get_root().add_child(park)
	park.configure(registry)
	park.enabled = true
	park.warm_materials = true
	park.bind_map("landfall")
	park.bind_map("landfall")
	park.finish_estimates(true)
	var warms: Array = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "warm" and str(e.map) == TOWN)
	_expect(warms.size() == 1 and int(warms[0].keys) == int(warmed.keys) and str(warms[0].error).is_empty(),
		"binding Landfall warms the Town once a session (%s)" % [warms])
	# The same bind estimates the Town from its textures: the review measured
	# +424 MiB of texture memory once it was built (2026-10-27), where the
	# GLB-size guess said 34 MiB; with the kits halved and its images
	# uploaded from BC sidecars the assets wave measured +90 MiB. The art
	# keeps changing, so the bounds are loose: well above the GLB guess,
	# mostly scenery, and below the raw RGBA reading of every header.
	var estimates: Array = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "estimate" and str(e.map) == TOWN)
	var guess := float(preload("res://src/world/world_park_policy.gd").whole_map_estimate(
		FileAccess.get_file_as_bytes(manifest.glb_path()).size())) / 1048576.0
	_expect(estimates.size() == 1 and float(estimates[0].estimated_mib) > 2.0 * guess
		and float(estimates[0].estimated_mib) < 1024.0
		and float(estimates[0].scenery_texture_mib) > float(estimates[0].shell_texture_mib),
		"binding Landfall estimates the Town from its textures, not its GLB's size (GLB guess %.1f MiB; %s)" % [guess, estimates])
	park.queue_free()
	await process_frame
	await _test_town_spread(registry, manifest, signatures, int(warmed.usec))

## The Town's warm-up spread over frames: the same keys as `warm`, no step
## near `warm`'s cost, and WorldPark bound with no curtain holding the Town's
## preload until the warm-up has run.
func _test_town_spread(registry: Dictionary, manifest: WorldManifest, signatures: Dictionary, warm_usec: int) -> void:
	var plan := Warmup.plan(manifest.glb_path())
	var spread := _run_steps(plan)
	var stepped := _signatures(spread.materials)
	_expect(stepped.size() == signatures.size() and stepped.keys().all(func(key: String) -> bool: return signatures.has(key)),
		"the Town's steps bind exactly warm's %d keys (%d materials)" % [signatures.size(), (spread.materials as Array).size()])
	print("town warm-up: whole %.1f ms on one frame; spread: plan %.1f ms on a worker, %d steps, slowest step %.2f ms"
		% [warm_usec / 1000.0, float(plan.usec) / 1000.0, (plan.steps as Array).size(), int(spread.slowest_usec) / 1000.0])
	_expect(int(spread.slowest_usec) * 4 < maxi(warm_usec, 4000),
		"no step costs a quarter of the whole warm-up (slowest %.2f ms, whole %.1f ms)" % [int(spread.slowest_usec) / 1000.0, warm_usec / 1000.0])
	var park: Node = WorldParkScript.new()
	get_root().add_child(park)
	park.configure(registry)
	park.enabled = true
	park.warm_materials = true
	park.prepare_function = _no_prepare
	var began := Time.get_ticks_usec()
	park.bind_map("landfall", false)
	var bind_ms := float(Time.get_ticks_usec() - began) / 1000.0
	print("walk-over bind of Landfall (first of the session): %.1f ms" % bind_ms)
	_expect(park.warming().has(TOWN) and not park.events.any(func(e: Dictionary) -> bool: return str(e.event) == "warm"),
		"bound with no curtain (a walk over the border), Landfall spreads the Town's warm-up")
	park.finish_estimates(true)
	var doors: Dictionary = park.doors()
	_expect(not doors.is_empty(), "(fixture) the Town's doors are indexed on Landfall")
	var door_tile: Vector2i = park._door_tiles[doors.keys()[0]]
	park.observe("landfall", door_tile, {}, true)
	_expect(park.preload_state() == "" and int(park.counters.preload_start) == 0,
		"at a Town door, no preload starts while its keys are being warmed")
	var frames := 0
	while park.warming().has(TOWN) and frames < 600:
		await process_frame
		frames += 1
	var warms: Array = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "warm" and str(e.map) == TOWN)
	_expect(warms.size() == 1 and bool(warms[0].spread) and int(warms[0].keys) == signatures.size()
		and int(warms[0].frames) >= int(warms[0].materials) and float(warms[0].max_step_ms) < 16.0,
		"the spread warm-up ran one material a frame over %d frames (%s)" % [frames, warms])
	park.observe("landfall", door_tile, {}, true)
	_expect(park.preload_state(TOWN) != "", "once it has run, the Town's preload starts at the door")
	park.clear()
	var idle := false
	for wait: int in 300:
		if park.is_idle():
			idle = true
			break
		await process_frame
	_expect(idle, "(fixture) the park winds down")
	park.release_now()
	park.queue_free()
	await process_frame

## A preload worker that builds nothing (the preload itself is not under test).
static func _no_prepare(_path: String, _cache: bool, _visuals: PackedStringArray) -> WorldLoader:
	var builder := WorldLoader.new()
	builder.detached_build = true
	return builder
