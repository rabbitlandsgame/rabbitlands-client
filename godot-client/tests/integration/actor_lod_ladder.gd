extends SceneTree
## Actor LOD ladder (actor LODs C5; wave-2 gate G5): what actors draw at the
## gameplay camera's field of view as the camera backs away, per quality, so
## the chain levels the cook placed (tools/actor_geometry/) and the quality
## biases (ActorRenderQuality) can be judged on screen and in primitives, on
## every renderer the game runs.
##
## Windowed, under the GPU lock: a SubViewport of 1920x1080 (FOV 50, the
## gameplay camera), one directional light with shadows, no ground. Each
## subject (two equipped Humans in the crowd benchmark's kits A and B, an
## unequipped Glasswarden, a creature) is built as a remote actor at each
## quality, posed (idle, paused), and the camera orbits it at 4 / 8 / 12 / 18 /
## 26 / 36 / 50 / 70 m (the orbit distance, as the gameplay camera's
## `distance`; pitch -35, yaw 30). Per step it records the viewport's visible
## and shadow primitives and draw calls (only the actor's model is drawn: its
## nameplate, map dot and selection geometry are hidden), the primitives
## Godot's LOD rule predicts from the meshes' chains (per piece: drawn level
## and triangles), and a crop of the frame around the actor at native pixels.
##
## The process draws one renderer and one actor geometry variant; the
## companion actor_lod_ladder.py composes strips across runs and judges gate
## G5 (Compatibility draws the same levels as Forward+). Select the variant
## with the applier's own switches: RABBITLANDS_ACTOR_GEOMETRY=off for the plain
## parse, RABBITLANDS_ACTOR_GEOMETRY_ROOT=<catalogue folder> for a cook. By
## default every actor file is parsed as an exported build parses it (the raw
## glTF parse: equipment ships loose and is never editor-imported), so the
## ladder shows what players draw; RABBITLANDS_LADDER_PARSE=editor keeps a
## checkout's imported actor scenes (races, hair and creatures, with the
## importer's own LODs; a guarded checkout's equipment is importer=skip, so it
## is parsed raw either way).
##
## Environment:
##   RABBITLANDS_LADDER_OUT        output folder (required); the run writes
##                                 <out>/<renderer>__<variant>/
##   RABBITLANDS_LADDER_VARIANT    variant label (default: the applier's mode)
##   RABBITLANDS_LADDER_MODE       "ladder" (default) or "clip": a zoom clip
##                                 of one subject at High, Medium and Low side
##                                 by side, 3 -> 70 -> 3 m, as numbered JPEG
##                                 frames (actor_lod_ladder.py clip encodes)
##   RABBITLANDS_LADDER_PARSE      "raw" (default) or "editor"
##   RABBITLANDS_LADDER_SUBJECTS   comma-separated subject labels (default all;
##                                 the clip's subject, default kit_b_human)
##   RABBITLANDS_LADDER_QUALITIES  comma-separated high,medium,low (default all)
##   RABBITLANDS_LADDER_CAPTURE    "0" skips the crops
## Output: manifest.json (run header, then one row per subject, quality and
## distance) and <subject>/<quality>/<distance>m.png crops. Exit 1 when a
## subject fails to configure, primitives grow with distance, or a cooked
## variant applied no sidecar.

const Policy := preload("res://src/actors/actor_render_quality.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const MapGeometryCache := preload("res://src/world/map_geometry_cache.gd")
const Look := preload("res://src/world/look/look_profile.gd")

const OUT_ENVIRONMENT := "RABBITLANDS_LADDER_OUT"
const VARIANT_ENVIRONMENT := "RABBITLANDS_LADDER_VARIANT"
const MODE_ENVIRONMENT := "RABBITLANDS_LADDER_MODE"
const PARSE_ENVIRONMENT := "RABBITLANDS_LADDER_PARSE"
const SUBJECTS_ENVIRONMENT := "RABBITLANDS_LADDER_SUBJECTS"
const QUALITIES_ENVIRONMENT := "RABBITLANDS_LADDER_QUALITIES"
const CAPTURE_ENVIRONMENT := "RABBITLANDS_LADDER_CAPTURE"

const SCHEMA := 1
const SIZE := Vector2i(1920, 1080)
## The gameplay camera (main.tscn) and the cook's reference camera.
const FOV_DEGREES := 50.0
const PITCH_DEGREES := -35.0
const YAW_DEGREES := 30.0
const DISTANCES: Array[float] = [4.0, 8.0, 12.0, 18.0, 26.0, 36.0, 50.0, 70.0]
## Pixels added round the actor's projected bounds in a crop.
const CROP_PADDING := 6
## The crowd benchmark's two equipped kits (tests/integration/
## crowd_presentation_benchmark.gd FULL_KIT_A / FULL_KIT_B; checked against
## its source at start): part -> equipment visual.
const KIT_A := {0: 114, 1: 106, 2: 0, 3: 117, 4: 171, 5: 184, 6: 192}
const KIT_B := {0: 164, 1: 111, 2: 1, 3: 109, 4: 172, 5: 185, 6: 193}
const HARNESS := "res://tests/integration/crowd_presentation_benchmark.gd"
## [label, model, actor kind, equipment visuals].
const SUBJECTS: Array = [
	["kit_a_human", "luminous_male", 1, KIT_A],
	["kit_b_human", "luminous_male", 1, KIT_B],
	["glasswarden_female", "glasswarden_female", 1, {}],
	["brambleback_boar", "brambleback_boar", 5, {}],
]
## Idle pose: the human clip and time the lining pose sheet uses; a creature
## takes its animation map's fallback action.
const HUMAN_IDLE := "Idle_Subtle"
const IDLE_SECONDS := 0.3
## Clip: frames per second of the encoded clip, near and far orbit distance,
## seconds out (and back), seconds held at each end, spacing of the three
## actors, and the clip camera's pitch.
const CLIP_FPS := 30
const CLIP_NEAR := 3.0
const CLIP_FAR := 70.0
const CLIP_TRAVEL_SECONDS := 8.0
const CLIP_HOLD_SECONDS := 1.0
const CLIP_SPACING := 1.4
const CLIP_PITCH_DEGREES := -20.0
const CLIP_JPEG_QUALITY := 0.9

var _viewport: SubViewport
var _stage: Node3D
var _camera: Camera3D
var _out := ""
var _folder := ""
var _renderer := ""
var _variant := ""
var _capture := true
var _models: Dictionary
var _equipment: Dictionary
var _animation_configs := {}
var _lod_tables := {}
var _rows: Array = []
var _failures := 0
var _next_actor_id := 950


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_out = OS.get_environment(OUT_ENVIRONMENT).strip_edges()
	if _out.is_empty():
		printerr("set " + OUT_ENVIRONMENT)
		quit(2)
		return
	if DisplayServer.get_name() == "headless":
		printerr("actor LOD ladder: run windowed (it measures what the renderer draws)")
		quit(2)
		return
	GltfQuantization.ensure_registered()
	var parse := OS.get_environment(PARSE_ENVIRONMENT).strip_edges().to_lower()
	parse = "editor" if parse == "editor" else "raw"
	# An exported build never sees an editor-imported actor scene: equipment
	# ships loose and GlbSceneCache parses it raw. The map geometry cook's
	# switch makes GlbSceneCache take that same raw parse in a checkout.
	var cooking_before := MapGeometryCache.cooking
	MapGeometryCache.cooking = parse == "raw"
	_capture = OS.get_environment(CAPTURE_ENVIRONMENT).strip_edges() != "0"
	_renderer = RenderingServer.get_current_rendering_method()
	var geometry: Dictionary = ActorGeometry.snapshot()
	_variant = OS.get_environment(VARIANT_ENVIRONMENT).strip_edges()
	if _variant.is_empty():
		_variant = str(geometry.get("mode", "sidecar"))
	_folder = _out.path_join("%s__%s" % [_renderer, _variant])
	DirAccess.make_dir_recursive_absolute(_folder)
	_build_stage()
	_models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	_equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	_check_kits()
	var subjects := _selected_subjects()
	var qualities := _selected_qualities()
	var mode := OS.get_environment(MODE_ENVIRONMENT).strip_edges().to_lower()
	var header := {"schema": SCHEMA, "renderer": _renderer, "variant": _variant, "parse": parse,
		"mode": "clip" if mode == "clip" else "ladder", "engine": Engine.get_version_info().get("string", ""),
		"adapter": RenderingServer.get_video_adapter_name(), "size": [SIZE.x, SIZE.y], "fov": FOV_DEGREES,
		"pitch": PITCH_DEGREES, "yaw": YAW_DEGREES, "distances": DISTANCES,
		"lod_threshold_px": _viewport.mesh_lod_threshold,
		"subjects": subjects.map(func(subject: Array) -> String: return str(subject[0])),
		"qualities": qualities.map(func(level: int) -> String: return Policy.quality_name(level)),
		"actor_geometry_environment": {"mode": OS.get_environment(ActorGeometry.MODE_ENVIRONMENT),
			"root": OS.get_environment(ActorGeometry.ROOT_ENVIRONMENT)}}
	if mode == "clip":
		await _clip(subjects[0] if OS.get_environment(SUBJECTS_ENVIRONMENT).strip_edges() != "" \
			else SUBJECTS[1], header)
	else:
		for subject: Array in subjects:
			for level: int in qualities:
				await _ladder(subject, level)
	geometry = ActorGeometry.snapshot()
	header["actor_geometry"] = geometry
	header["lod_multiplier"] = _camera.get_camera_projection().get_lod_multiplier()
	var statuses: Dictionary = geometry.get("statuses", {})
	if str(geometry.get("catalog", "")) == "ready" and int(statuses.get("applied", 0)) == 0:
		_fail("the catalogue at %s applied no sidecar" % str(geometry.get("root", "")))
	header["failures"] = _failures
	header["rows"] = _rows
	var file := FileAccess.open(_folder.path_join("manifest.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(header, " ", true))
	file.close()
	MapGeometryCache.cooking = cooking_before
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("ACTOR LOD LADDER: %s %s, %d rows, %d failures, out %s" % [_renderer, _variant, _rows.size(),
		_failures, _folder])
	quit(1 if _failures > 0 else 0)


func _build_stage() -> void:
	_viewport = SubViewport.new()
	_viewport.size = SIZE
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(_viewport)
	_stage = Node3D.new()
	_viewport.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(.13, .16, .19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = .75
	_stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-50, -30, 0)
	light.light_energy = 1.2
	light.shadow_enabled = true
	_stage.add_child(light)
	_camera = Camera3D.new()
	_camera.fov = FOV_DEGREES
	_camera.far = 500.0
	_camera.current = true
	_stage.add_child(_camera)
	# A small live preview of the capture for whoever watches the run.
	root.size = Vector2i(640, 360)
	var preview := TextureRect.new()
	preview.texture = _viewport.get_texture()
	preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	preview.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(preview)


## The kits must stay the crowd benchmark's, so the ladder's Humans are the
## market's Humans.
func _check_kits() -> void:
	var source := FileAccess.get_file_as_string(HARNESS)
	if source.is_empty():
		return
	for pair: Array in [["FULL_KIT_A", KIT_A], ["FULL_KIT_B", KIT_B]]:
		var expected := "const %s := %s" % [pair[0], _kit_literal(pair[1])]
		if not source.contains(expected):
			_fail("%s no longer matches the crowd benchmark's %s" % [pair[0], pair[0]])


func _kit_literal(kit: Dictionary) -> String:
	var parts: PackedStringArray = []
	for key: int in kit:
		parts.append("%d: %d" % [key, int(kit[key])])
	return "{" + ", ".join(parts) + "}"


func _selected_subjects() -> Array:
	var wanted := OS.get_environment(SUBJECTS_ENVIRONMENT).strip_edges()
	if wanted.is_empty():
		return SUBJECTS
	var selected: Array = []
	for label: String in wanted.split(",", false):
		var found := false
		for subject: Array in SUBJECTS:
			if str(subject[0]) == label.strip_edges():
				selected.append(subject)
				found = true
		if not found:
			_fail("unknown subject " + label)
	return selected if not selected.is_empty() else SUBJECTS


func _selected_qualities() -> Array[int]:
	var levels: Array[int] = [Policy.Quality.HIGH, Policy.Quality.MEDIUM, Policy.Quality.LOW]
	var wanted := OS.get_environment(QUALITIES_ENVIRONMENT).strip_edges().to_lower()
	if wanted.is_empty():
		return levels
	var selected: Array[int] = []
	for level: int in levels:
		if Policy.quality_name(level) in wanted.split(",", false):
			selected.append(level)
	return selected if not selected.is_empty() else levels


## One subject at one quality, all distances.
func _ladder(subject: Array, level: int) -> void:
	var label := str(subject[0])
	var quality := Policy.quality_name(level)
	var actor := await _build_actor(subject, level, Vector3.ZERO)
	if actor == null:
		return
	var model := actor.get("_native_model") as Node3D
	var box := _model_box(model)
	var focus := box.get_center()
	var folder := _folder.path_join(label).path_join(quality)
	if _capture:
		DirAccess.make_dir_recursive_absolute(folder)
	var previous := -1
	for distance: float in DISTANCES:
		_place_camera(focus, distance, PITCH_DEGREES, YAW_DEGREES)
		var info := await _measure()
		var predicted := _predict(model)
		var row := {"subject": label, "quality": quality, "distance": distance,
			"primitives": info.primitives, "draw_calls": info.draw_calls,
			"shadow_primitives": info.shadow_primitives, "stable": info.stable,
			"predicted": predicted.drawn, "base": predicted.base, "pieces": predicted.pieces}
		if _capture:
			var image := _viewport.get_texture().get_image()
			var rect := _crop_rect(box)
			var path := folder.path_join("%02dm.png" % int(distance))
			if image.get_region(rect).save_png(path) != OK:
				_fail("save " + path)
			row["crop"] = [rect.position.x, rect.position.y, rect.size.x, rect.size.y]
			row["image"] = path.trim_prefix(_folder + "/")
		_rows.append(row)
		print("ladder %s %s %4.0f m: %d primitives (predicted %d of %d), %d shadow, %d draws" % [label,
			quality, distance, info.primitives, predicted.drawn, predicted.base, info.shadow_primitives,
			info.draw_calls])
		if previous >= 0 and int(info.primitives) > previous:
			_fail("%s %s draws more at %.0f m (%d) than nearer (%d)" % [label, quality, distance,
				info.primitives, previous])
		previous = int(info.primitives)
	actor.queue_free()
	await process_frame


## The zoom clip: one subject at High, Medium and Low side by side, the
## camera backing out from CLIP_NEAR to CLIP_FAR (equal steps in log
## distance) and coming back, as JPEG frames. clip.json lists each frame's
## distance and primitives.
func _clip(subject: Array, header: Dictionary) -> void:
	var levels: Array[int] = [Policy.Quality.HIGH, Policy.Quality.MEDIUM, Policy.Quality.LOW]
	var actors: Array = []
	var box := AABB()
	for index: int in levels.size():
		var actor := await _build_actor(subject, levels[index],
			Vector3((index - 1) * CLIP_SPACING, 0.0, 0.0))
		if actor == null:
			return
		actors.append(actor)
		var part := _model_box(actor.get("_native_model") as Node3D)
		box = part if index == 0 else box.merge(part)
	var folder := _folder.path_join("clip")
	DirAccess.make_dir_recursive_absolute(folder)
	var travel := int(round(CLIP_TRAVEL_SECONDS * CLIP_FPS))
	var hold := int(round(CLIP_HOLD_SECONDS * CLIP_FPS))
	var distances: Array[float] = []
	for frame: int in hold:
		distances.append(CLIP_NEAR)
	for frame: int in travel + 1:
		distances.append(CLIP_NEAR * pow(CLIP_FAR / CLIP_NEAR, float(frame) / float(travel)))
	for frame: int in hold:
		distances.append(CLIP_FAR)
	for frame: int in travel + 1:
		distances.append(CLIP_FAR * pow(CLIP_NEAR / CLIP_FAR, float(frame) / float(travel)))
	for frame: int in hold:
		distances.append(CLIP_NEAR)
	var frames: Array = []
	for index: int in distances.size():
		_place_camera(box.get_center(), distances[index], CLIP_PITCH_DEGREES, 0.0)
		await process_frame
		await RenderingServer.frame_post_draw
		var image := _viewport.get_texture().get_image()
		var path := folder.path_join("frame_%05d.jpg" % index)
		if image.save_jpg(path, CLIP_JPEG_QUALITY) != OK:
			_fail("save " + path)
			break
		frames.append({"frame": index, "distance": distances[index], "primitives": RenderingServer.viewport_get_render_info(
			_viewport.get_viewport_rid(), RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,
			RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME)})
	var clip := header.duplicate()
	clip.merge({"subject": str(subject[0]), "fps": CLIP_FPS, "near": CLIP_NEAR, "far": CLIP_FAR,
		"pitch": CLIP_PITCH_DEGREES, "yaw": 0.0, "order": ["high", "medium", "low"], "frames": frames}, true)
	var file := FileAccess.open(folder.path_join("clip.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(clip, " ", true))
	file.close()
	for actor: Node in actors:
		actor.queue_free()
	await process_frame


## A remote actor built the way Main builds one at `level`: the quality is
## the frame's quality when it configures and its render role afterwards.
func _build_actor(subject: Array, level: int, at: Vector3) -> ReplicatedActor3D:
	var label := str(subject[0])
	var model_config: Dictionary = _models.get(str(subject[1]), {})
	if model_config.is_empty():
		_fail("%s: no model %s" % [label, subject[1]])
		return null
	Look.set_player_quality(level)
	var kit: Dictionary = subject[3]
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	_next_actor_id += 1
	var errors := actor.configure({"actor_id": _next_actor_id, "x": 0, "y": 0, "rotation": 0,
		"actor_type": 1, "kind": int(subject[2]), "name": "", "health": 100, "max_health": 100,
		"alive": true, "appearance": {}, "equipment_visuals": kit.duplicate(),
		"equipment_fallback_parts": []}, CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0}),
		model_config, _animation_config(model_config), _equipment, true)
	actor.apply_render_quality(level, false)
	if not errors.is_empty():
		_fail("%s configures: %s" % [label, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.global_position = at
	actor.rotation.y = PI
	if actor.has_method("_advance_facing_offset"):
		actor.call("_advance_facing_offset", 1.0)
	for frame: int in 4:
		await process_frame
	if actor.get("_native_model") == null:
		_fail("%s has no model" % label)
		actor.queue_free()
		return null
	_pose(actor, model_config)
	_hide_presentation(actor)
	for frame: int in 2:
		await process_frame
	return actor


func _animation_config(model_config: Dictionary) -> Dictionary:
	var path := str(model_config.get("animationMap", "res://data/animations/luminous.json"))
	if not _animation_configs.has(path):
		_animation_configs[path] = JSON.parse_string(FileAccess.get_file_as_string(path))
	return _animation_configs[path] as Dictionary


func _pose(actor: ReplicatedActor3D, model_config: Dictionary) -> void:
	var player := actor.animation_player
	if player == null:
		return
	var config := _animation_config(model_config)
	var wanted := HUMAN_IDLE
	if str(model_config.get("animationMap", "")) != "" \
			and not str(model_config.get("animationMap", "")).ends_with("luminous.json"):
		wanted = str((config.get("actions", {}) as Dictionary).get(str(config.get("fallbackAction", "idle")), ""))
	var clip := ""
	for name: StringName in player.get_animation_list():
		if str(name) == wanted or str(name).ends_with("/" + wanted):
			clip = str(name)
			break
	if clip.is_empty():
		player.pause()
		return
	player.play(clip)
	player.seek(IDLE_SECONDS, true)
	player.pause()


## Only the actor's model is drawn: nameplate, map dot, selection ring and
## footprint outline (actor children outside the model) are hidden, so the
## viewport's primitives are the model's.
func _hide_presentation(actor: ReplicatedActor3D) -> void:
	var model := actor.get("_native_model") as Node
	for node: Node in actor.find_children("*", "GeometryInstance3D", true, false):
		if model == null or not (node == model or model.is_ancestor_of(node)) \
				or str(node.name).begins_with("MapDot"):
			(node as GeometryInstance3D).visible = false


func _model_box(model: Node3D) -> AABB:
	var box := AABB()
	var first := true
	for node: Node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null or not mesh.is_visible_in_tree():
			continue
		var part := mesh.global_transform * mesh.get_aabb()
		box = part if first else box.merge(part)
		first = false
	return box


func _place_camera(focus: Vector3, distance: float, pitch_degrees: float, yaw_degrees: float) -> void:
	var pitch := deg_to_rad(pitch_degrees)
	var yaw := deg_to_rad(yaw_degrees)
	_camera.global_position = focus + Vector3(sin(yaw) * cos(pitch), -sin(pitch),
		cos(yaw) * cos(pitch)) * distance
	_camera.look_at(focus, Vector3.UP)
	# The gameplay camera's near plane rule (IsometricCameraController).
	_camera.near = clampf(distance * 0.25, 0.2, 1.0)


## The viewport's counters for a frame drawn with the current camera, read
## twice to show they are settled.
func _measure() -> Dictionary:
	var readings: Array = []
	for reading: int in 2:
		await process_frame
		await RenderingServer.frame_post_draw
		await process_frame
		await RenderingServer.frame_post_draw
		var rid := _viewport.get_viewport_rid()
		readings.append([
			RenderingServer.viewport_get_render_info(rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,
				RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME),
			RenderingServer.viewport_get_render_info(rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,
				RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME),
			RenderingServer.viewport_get_render_info(rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_SHADOW,
				RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME)])
	return {"primitives": int(readings[1][0]), "draw_calls": int(readings[1][1]),
		"shadow_primitives": int(readings[1][2]), "stable": readings[0] == readings[1]}


## What Godot's LOD rule selects for every drawn surface of the model from
## this camera: level i of a surface draws while
##   edge_i * model_scale * lod_bias / (distance * lod_multiplier) <= threshold / width,
## distance = camera to the nearest point of the instance's bounds (grown by
## its extra cull margin). Visibility ranges (the RL head and hair bands) are
## judged by the distance to the bounds' centre. A skinned surface's bounds
## come from its mesh here and from the posed skeleton in the renderer, so
## the prediction can pick a neighbouring level right at a switch.
func _predict(model: Node3D) -> Dictionary:
	var eye := _camera.global_position
	var multiplier := _camera.get_camera_projection().get_lod_multiplier()
	var threshold := _viewport.mesh_lod_threshold / float(SIZE.x)
	var drawn := 0
	var base := 0
	var pieces := {}
	for node: Node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null or not mesh.is_visible_in_tree() \
				or mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:
			continue
		var box := (mesh.global_transform * mesh.get_aabb()).grow(mesh.extra_cull_margin)
		var centre := eye.distance_to(box.get_center())
		if (mesh.visibility_range_end > 0.0 and centre >= mesh.visibility_range_end) \
				or (mesh.visibility_range_begin > 0.0 and centre < mesh.visibility_range_begin):
			continue
		var distance := eye.distance_to(eye.clamp(box.position, box.end))
		var scale := mesh.global_transform.basis.get_scale().abs()
		var model_scale := maxf(scale.x, maxf(scale.y, scale.z))
		var piece := {"base": 0, "drawn": 0, "levels": [], "chains": 0}
		for table: Dictionary in _lod_table(mesh.mesh):
			var level := 0
			var count := int(table.indices)
			if distance > 0.0:
				var lods: Array = table.lods
				for index: int in lods.size():
					var screen := float(lods[index][0]) * model_scale * mesh.lod_bias / (distance * multiplier)
					if screen > threshold:
						break
					level = index + 1
					count = int(lods[index][1])
			piece.base += int(table.indices) / 3
			piece.drawn += count / 3
			(piece.levels as Array).append(level)
			piece.chains += int(not (table.lods as Array).is_empty())
		piece["distance"] = snappedf(distance, 0.01)
		piece["lod_bias"] = snappedf(mesh.lod_bias, 0.0001)
		var key := _piece_name(mesh, model)
		while pieces.has(key):
			key += "+"
		pieces[key] = piece
		drawn += int(piece.drawn)
		base += int(piece.base)
	return {"drawn": drawn, "base": base, "pieces": pieces}


## Per surface: {indices, lods: [[edge_length, indices], ...]} as the
## renderer holds them (read once per mesh).
func _lod_table(mesh: Mesh) -> Array:
	var rid := mesh.get_rid()
	if _lod_tables.has(rid):
		return _lod_tables[rid]
	var surfaces: Array = []
	for surface: int in mesh.get_surface_count():
		var data: Dictionary = RenderingServer.mesh_get_surface(rid, surface)
		var count := int(data.get("index_count", 0))
		if count == 0:
			count = int(data.get("vertex_count", 0))
		var stride := 4
		var index_bytes: PackedByteArray = data.get("index_data", PackedByteArray())
		if count > 0 and not index_bytes.is_empty():
			stride = maxi(1, index_bytes.size() / count)
		var lods: Array = []
		for lod: Dictionary in data.get("lods", []):
			lods.append([float(lod.get("edge_length", 0.0)),
				(lod.get("index_data", PackedByteArray()) as PackedByteArray).size() / stride])
		surfaces.append({"indices": count, "lods": lods})
	_lod_tables[rid] = surfaces
	return surfaces


func _piece_name(mesh: MeshInstance3D, model: Node) -> String:
	var name := str(mesh.name)
	var parent := mesh.get_parent()
	if parent != null and parent != model and not (parent is Skeleton3D):
		name = str(parent.name) + "/" + name
	return name


func _crop_rect(box: AABB) -> Rect2i:
	var rect := Rect2()
	for corner: int in 8:
		var point := _camera.unproject_position(box.get_endpoint(corner))
		rect = Rect2(point, Vector2.ZERO) if corner == 0 else rect.expand(point)
	rect = rect.grow(CROP_PADDING)
	var bounds := Rect2(Vector2.ZERO, Vector2(SIZE))
	rect = rect.intersection(bounds)
	var crop := Rect2i(rect.position.floor(), rect.size.ceil())
	crop.size = crop.size.max(Vector2i.ONE)
	return crop


func _fail(message: String) -> void:
	_failures += 1
	push_error("actor LOD ladder: " + message)
