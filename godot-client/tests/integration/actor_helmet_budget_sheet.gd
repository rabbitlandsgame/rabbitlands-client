extends SceneTree
## Helmet budget sheet (actor LODs C11): renders race-refit helmets on their
## race as drawn today and as the budget stage caps them, at the owner's
## look distance (3 m) and the guard depth (8 m), with the gameplay camera's
## field of view at 1920x1080, so the owner can judge the capped close-ups.
##
## Windowed, under the GPU lock. RABBITLANDS_HELMET_SHEET_OUT names the output
## folder; RABBITLANDS_HELMET_SHEET_CONFIGS optionally a JSON list of [label,
## race model, helmet visual id] replacing CONFIGS. Run with
## RABBITLANDS_ACTOR_GEOMETRY=off so no developer catalogue interferes.
##
## Per configuration the script runs the cook's budget stage (cook.gd
## plan_state + BudgetPolicy.apply, the Human source counted from its own
## parse) on a fresh parse of the refit, then swaps the worn helmet's mesh
## between `plain` (the worn mesh), `capped` (its own arrays with the capped
## base and the stage's levels) and, where it differs, `strict` (the largest
## simplifier level within twice the Human source with no error guard: what the
## plan's unguarded rule would draw). Captures per distance and view, in order:
## plain, capped, strict, plain again; a pixel the two plain frames disagree on
## moved by itself and is not judged; a pixel changed by more than STRONG_DELTA is
## drawn red, a fainter change (shading on a re-triangulated face) dark orange.
## Output: <out>/<label>/<distance>__<view>__
## {plain,capped,strict,plain2}.png, <out>/sheet__<label>.png (rows = distance
## and view; columns = plain, capped, capped changes, strict, strict changes,
## then plain, capped and strict at 3x) and <out>/manifest.json.

const Cook := preload("res://tools/actor_geometry/cook.gd")
const LodPolicy := preload("res://tools/actor_geometry/lod_policy.gd")
const BudgetPolicy := preload("res://tools/actor_geometry/budget_policy.gd")
const LiningPolicy := preload("res://tools/actor_geometry/lining_policy.gd")
const Format := preload("res://src/actors/actor_geometry_format.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")

const OUT_ENVIRONMENT := "RABBITLANDS_HELMET_SHEET_OUT"
const CONFIGS_ENVIRONMENT := "RABBITLANDS_HELMET_SHEET_CONFIGS"
const SIZE := Vector2i(1920, 1080)
## The gameplay camera's vertical field of view (LodPolicy's reference).
const FOV_DEGREES := 50.0
## Crop (pixels) around the head at each distance; the zoomed copy is 3x.
const CROP := {3: 240, 8: 96}
const ZOOM := 3
## Per-channel change (0-1) above which a changed pixel counts as strong.
const STRONG_DELTA := 32.0 / 255.0
## [label, race model, helmet visual]: the plan's two named refits on both
## sexes, plus the refits whose capped base carries the largest error.
const CONFIGS: Array = [
	["sun_headband_votary_male", "votary_male", 170],
	["sun_headband_votary_female", "votary_female", 170],
	["leafscale_hood_votary_male", "votary_male", 120],
	["leafscale_hood_votary_female", "votary_female", 120],
	["fang_hood_votary_female", "votary_female", 157],
	["acolyte_hood_votary_female", "votary_female", 115],
	["phoenix_helm_orun_male", "orun_male", 125],
]
## [label, yaw degrees round the actor, pitch degrees (negative looks down)].
const VIEWS: Array = [["front", 0.0, 0.0], ["three_quarter", 35.0, -15.0], ["side", 90.0, 0.0],
	["back", 180.0, -10.0], ["gameplay", 30.0, -50.0]]
const DISTANCES: Array[int] = [3, 8]

var _stage: Node3D
var _camera: Camera3D
var _out := ""
var _models: Dictionary
var _equipment: Dictionary
var _animations: Dictionary
var _manifest := {"configs": {}, "size": [SIZE.x, SIZE.y], "fov": FOV_DEGREES, "views": [], "distances": DISTANCES}
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_out = OS.get_environment(OUT_ENVIRONMENT)
	if _out.is_empty():
		printerr("set " + OUT_ENVIRONMENT)
		quit(2)
		return
	var configs: Array = CONFIGS
	if not OS.get_environment(CONFIGS_ENVIRONMENT).is_empty():
		configs = JSON.parse_string(OS.get_environment(CONFIGS_ENVIRONMENT))
	GltfQuantization.ensure_registered()
	DirAccess.make_dir_recursive_absolute(_out)
	root.size = SIZE
	_build_stage()
	_models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	_equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	_animations = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for view: Array in VIEWS:
		(_manifest.views as Array).append(view[0])
	for config: Array in configs:
		await _render_config(config)
	var file := FileAccess.open(_out.path_join("manifest.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_manifest, " ", true))
	file.close()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("HELMET BUDGET SHEET: %d configs, %d failures, out %s" % [configs.size(), _failures, _out])
	quit(1 if _failures > 0 else 0)


func _build_stage() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(.13, .16, .19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = .75
	_stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = 1.2
	_stage.add_child(light)
	_camera = Camera3D.new()
	_camera.fov = FOV_DEGREES
	_camera.current = true
	_stage.add_child(_camera)


func _render_config(config: Array) -> void:
	var label := str(config[0])
	var race := str(config[1])
	var visual := int(config[2])
	var folder := _out.path_join(label)
	DirAccess.make_dir_recursive_absolute(folder)
	var model: Dictionary = _equipment.models.get("3:%d" % visual, {})
	var sex := "female" if race.ends_with("_female") else "male"
	var variants: Dictionary = model.get("variants", {})
	var scene := str((variants.get("canonical_" + race, {}) as Dictionary).get("scene", ""))
	var reference := str((variants.get("canonical_human_" + sex, model) as Dictionary).get("scene", model.get("scene", "")))
	var entry := {"race": race, "visual": visual, "scene": scene, "reference": reference}
	_manifest.configs[label] = entry
	if scene.is_empty() or reference.is_empty():
		_fail("%s: no refit of 3:%d for %s" % [label, visual, race])
		return
	var record := _capped_record(scene, reference, entry)
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	var errors := actor.configure({"actor_id": 911, "kind": 1, "name": "", "x": 0, "y": 0, "rotation": 0,
		"appearance": {"hair": 1}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.}),
		_models[race], _animations, _equipment)
	if not errors.is_empty():
		_fail("%s configures: %s" % [label, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.global_position = Vector3.ZERO
	actor.rotation.y = PI
	actor._advance_facing_offset(1.)
	actor.apply_equipment_visuals({3: visual})
	for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
		(marker as MeshInstance3D).hide()
	actor.animation_player.play("Idle_Subtle")
	actor.animation_player.seek(0.3, true)
	actor.animation_player.pause()
	for frame: int in 3:
		await process_frame
	var helmet := _worn_helmet(actor, visual)
	if helmet == null or record.is_empty():
		_fail("%s: no worn helmet or no capped record" % label)
		actor.free()
		return
	var plain := helmet.mesh as ArrayMesh
	var capped := _capped_mesh(plain, record, entry)
	if capped == null:
		_fail("%s: the worn helmet does not match the parse the budget binds to" % label)
		actor.free()
		return
	var strict: ArrayMesh = null
	if record.has("strict_base"):
		strict = _capped_mesh(plain, {"index_digest": record.index_digest, "vertex_count": record.vertex_count,
			"base": record.strict_base, "lods": []}, {})
	var head := _head_position(actor)
	var rows: Array = []
	for distance: int in DISTANCES:
		for view: Array in VIEWS:
			_place_camera(view, head, float(distance))
			var stem := folder.path_join("%dm__%s__" % [distance, view[0]])
			helmet.mesh = plain
			var first := await _capture(stem + "plain.png")
			helmet.mesh = capped
			var second := await _capture(stem + "capped.png")
			var fourth: Image = null
			if strict != null:
				helmet.mesh = strict
				fourth = await _capture(stem + "strict.png")
			helmet.mesh = plain
			var third := await _capture(stem + "plain2.png")
			# The camera looks at the head: it sits at the image centre.
			rows.append(_row(first, second, third, fourth, Vector2i(first.get_size() / 2), int(CROP[distance]), entry,
				"%dm_%s" % [distance, view[0]]))
	_compose(rows, _out.path_join("sheet__%s.png" % label))
	actor.free()
	await process_frame
	print("HELMET BUDGET SHEET: %s done (%s)" % [label, JSON.stringify(entry.get("budget", {}))])


## The budget stage's sidecar record for the refit (single-surface helmets).
func _capped_record(scene: String, reference: String, entry: Dictionary) -> Dictionary:
	var reference_parse := Cook.parse(ProjectSettings.globalize_path(reference))
	var reference_triangles := 0
	for gltf_mesh: GLTFMesh in (reference_parse.state as GLTFState).get_meshes():
		for surface: int in gltf_mesh.mesh.get_surface_count():
			reference_triangles += (gltf_mesh.mesh.get_surface_arrays(surface)[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	var absolute := ProjectSettings.globalize_path(scene)
	var parsed := Cook.parse(absolute)
	var plan := Cook.plan_state(parsed.state, scene, FileAccess.get_sha256(absolute), 0, 1.0)
	plan = LiningPolicy.apply(parsed.state, plan, {})
	plan = BudgetPolicy.apply(parsed.state, plan, {"schema": BudgetPolicy.INPUT_SCHEMA, "reference": reference,
		"reference_sha256": FileAccess.get_sha256(ProjectSettings.globalize_path(reference)),
		"reference_triangles": reference_triangles})
	var row: Dictionary = plan.meshes[0].surfaces[0]
	entry["budget"] = row.get("budget", {})
	entry["levels"] = row.get("levels", [])
	if (plan.sidecar.meshes as Array).size() != 1 or (plan.sidecar.meshes[0].surfaces as Array).size() != 1:
		entry["skipped"] = "not a one-surface helmet"
		return {}
	var record: Dictionary = plan.sidecar.meshes[0].surfaces[0]
	if not record.has("base"):
		return {}
	# The plan's rule without the guard: the largest level within the limit.
	var importer: ImporterMesh = (parsed.state.get_meshes()[0] as GLTFMesh).mesh
	var arrays := importer.get_surface_arrays(0)
	var raw := LodPolicy.exact_chain(arrays, importer.get_surface_format(0))
	var triangles := (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	var chosen := BudgetPolicy.choose_level(raw, triangles, BudgetPolicy.limit_for(reference_triangles), INF)
	if int(chosen.index) >= 0 and str(chosen.status) == "capped" \
			and Format.index_digest(raw[int(chosen.index)][0]) != Format.index_digest(record.base):
		record["strict_base"] = raw[int(chosen.index)][0]
		entry["strict"] = {"base_triangles": (raw[int(chosen.index)][0] as PackedInt32Array).size() / 3,
			"error": float(raw[int(chosen.index)][1])}
	return record


func _worn_helmet(actor: ReplicatedActor3D, visual: int) -> MeshInstance3D:
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var path := str(actor.get_path_to(node))
		if path.contains("EquipmentPart_3_Visual_%d_" % visual) and (node as MeshInstance3D).mesh is ArrayMesh:
			return node as MeshInstance3D
	return null


func _capped_mesh(mesh: ArrayMesh, record: Dictionary, entry: Dictionary) -> ArrayMesh:
	if mesh.get_surface_count() != 1:
		return null
	var arrays := mesh.surface_get_arrays(0)
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	entry["worn_index_digest_matches"] = Format.index_digest(indices) == str(record.index_digest)
	entry["worn_vertices"] = (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	if not bool(entry.worn_index_digest_matches) or int(entry.worn_vertices) != int(record.vertex_count):
		return null
	arrays[Mesh.ARRAY_INDEX] = record.base
	var lods := {}
	for level: Array in record.lods:
		lods[float(level[0])] = level[1]
	var out := ArrayMesh.new()
	out.add_surface_from_arrays(mesh.surface_get_primitive_type(0), arrays, [], lods, mesh.surface_get_format(0))
	out.surface_set_material(0, mesh.surface_get_material(0))
	out.resource_name = mesh.resource_name
	return out


func _head_position(actor: ReplicatedActor3D) -> Vector3:
	var skeleton := actor.get_skeleton()
	var head := skeleton.find_bone("Head")
	if head < 0:
		return actor.global_position + Vector3(0, 1.6, 0)
	return skeleton.global_transform * skeleton.get_bone_global_pose(head).origin + Vector3(0, 0.08, 0)


func _place_camera(view: Array, focus: Vector3, distance: float) -> void:
	var yaw := deg_to_rad(float(view[1]))
	var pitch := deg_to_rad(float(view[2]))
	var direction := Vector3(sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch))
	_camera.position = focus + direction * distance
	_camera.look_at(focus, Vector3.UP if absf(direction.y) < 0.99 else Vector3.FORWARD)


func _capture(path: String) -> Image:
	for frame: int in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	if image.save_png(path) != OK:
		_fail("save " + path)
	return image


## One sheet row: plain and capped crops round the head, the capped changes
## (red when strong, dark orange when faint; grey where the two plain frames
## disagree), the strict crop and its changes when there is one, then plain,
## capped and strict at ZOOM.
func _row(first: Image, second: Image, third: Image, fourth: Image, centre: Vector2i, crop: int, entry: Dictionary,
		key: String) -> Image:
	var rect := Rect2i(centre - Vector2i(crop, crop) / 2, Vector2i(crop, crop)).intersection(Rect2i(Vector2i.ZERO, first.get_size()))
	var a := _crop(first, rect)
	var b := _crop(second, rect)
	var c := _crop(third, rect)
	var stats: Dictionary = entry.get("pixels", {})
	var capped := _diff(a, b, c)
	stats[key] = dict_with(capped.stats, {"crop": crop})
	var tiles: Array = [a, b, capped.image]
	var zoomed: Array = [a, b]
	if fourth != null:
		var d := _crop(fourth, rect)
		var strict := _diff(a, d, c)
		stats[key + "_strict"] = dict_with(strict.stats, {"crop": crop})
		tiles.append_array([d, strict.image])
		zoomed.append(d)
	entry["pixels"] = stats
	var tile := crop * ZOOM
	var row := Image.create(rect.size.x * tiles.size() + tile * zoomed.size() + 40, maxi(rect.size.y, tile), false,
		Image.FORMAT_RGBA8)
	row.fill(Color(0.06, 0.06, 0.06))
	var x := 0
	for part: Image in tiles:
		row.blit_rect(part, Rect2i(Vector2i.ZERO, part.get_size()), Vector2i(x, 0))
		x += part.get_width()
	x += 40
	for part: Image in zoomed:
		var big := part.duplicate() as Image
		big.resize(part.get_width() * ZOOM, part.get_height() * ZOOM, Image.INTERPOLATE_NEAREST)
		row.blit_rect(big, Rect2i(Vector2i.ZERO, big.get_size()), Vector2i(x, 0))
		x += big.get_width()
	return row


func _crop(image: Image, rect: Rect2i) -> Image:
	var out := image.get_region(rect)
	out.convert(Image.FORMAT_RGBA8)
	return out


## {image, stats}: pixels of `b` against `a`, not judged where `a` and its
## repeat `c` disagree.
func _diff(a: Image, b: Image, c: Image) -> Dictionary:
	var rect := Rect2i(Vector2i.ZERO, a.get_size())
	var diff := Image.create(rect.size.x, rect.size.y, false, Image.FORMAT_RGBA8)
	var changed := 0
	var strong := 0
	var unstable := 0
	var largest := 0.0
	for y: int in rect.size.y:
		for x: int in rect.size.x:
			var pa := a.get_pixel(x, y)
			var pb := b.get_pixel(x, y)
			var pc := c.get_pixel(x, y)
			if not pa.is_equal_approx(pc):
				unstable += 1
				diff.set_pixel(x, y, Color(0.5, 0.5, 0.5))
				continue
			var delta := maxf(absf(pa.r - pb.r), maxf(absf(pa.g - pb.g), absf(pa.b - pb.b)))
			largest = maxf(largest, delta)
			if delta > STRONG_DELTA:
				changed += 1
				strong += 1
				diff.set_pixel(x, y, Color(1, 0, 0))
			elif delta > 1.5 / 255.0:
				changed += 1
				diff.set_pixel(x, y, Color(0.55, 0.3, 0.05))
			else:
				diff.set_pixel(x, y, pa.darkened(0.6))
	return {"image": diff, "stats": {"changed": changed, "strong": strong, "unstable": unstable,
		"max_delta_255": roundi(largest * 255.0)}}


static func dict_with(base: Dictionary, extra: Dictionary) -> Dictionary:
	var out := base.duplicate()
	out.merge(extra, true)
	return out


func _compose(rows: Array, path: String) -> void:
	var width := 0
	var height := 0
	for row: Image in rows:
		width = maxi(width, row.get_width())
		height += row.get_height() + 6
	var sheet := Image.create(width, height, false, Image.FORMAT_RGBA8)
	sheet.fill(Color(0.02, 0.02, 0.02))
	var y := 0
	for row: Image in rows:
		sheet.blit_rect(row, Rect2i(Vector2i.ZERO, row.get_size()), Vector2i(0, y))
		y += row.get_height() + 6
	if sheet.save_png(path) != OK:
		_fail("save " + path)


func _fail(message: String) -> void:
	_failures += 1
	push_error(message)
