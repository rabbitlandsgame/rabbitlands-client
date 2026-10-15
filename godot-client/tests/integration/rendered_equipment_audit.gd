extends SceneTree
## Measures how every generated piece sits on the body, in the client.
##
## The rendered fit fixture shows a handful of pieces per slot and trusts the
## eye; this wears all of them through the same actor build and measures the
## result, so a helm two sizes big or a boot up the shin is a number rather
## than something to notice in a screenshot.
##
## Each piece is compared against the wearer's own anatomy, taken from the
## split body surfaces and the skeleton: a helm against the skull dome the
## scalp surface draws, a cuirass against the trunk, legs and boots against
## their limbs.  The checks are deliberately loose -- they catch pieces that
## are wrong, not pieces that are merely styled -- and every measurement is
## printed so a borderline piece can be judged rather than argued about.
##
## Set ELORIA_AUDIT_RACE to audit another body; it defaults to luminous_male.

const SCREEN_SIZE := Vector2i(640, 360)
## Per part: how wide a piece may be against its body reference, and how far
## its centre may sit from the reference centre.
const RULES := {
	3: {"name": "helm", "offsetMax": 0.045},
	4: {"name": "legs", "offsetMax": 0.060},
	5: {"name": "body", "offsetMax": 0.060},
	6: {"name": "boots", "offsetMax": 0.060},
}
const BATCH := 8

var _failures := 0
var _main: Control
var _stage: Node3D
var _adapter: CoordinateAdapter
var _model_config: Dictionary
var _animation_config: Dictionary
var _equipment_config: Dictionary
var _next_id := 7000
var _rows: Array[Dictionary] = []
var _flagged: Array[Dictionary] = []
var _sheet := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = SCREEN_SIZE
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_main.hide()
	await process_frame

	var models: Dictionary = _main.get("models") as Dictionary
	_equipment_config = _main.get("equipment_config") as Dictionary
	var race: String = OS.get_environment("ELORIA_AUDIT_RACE")
	if race.is_empty():
		race = "luminous_male"
	_model_config = models.get(race, {}) as Dictionary
	if _model_config.is_empty():
		print("audit: unknown race ", race)
		quit(1)
		return
	_animation_config = _main.call("_animation_for_model", _model_config) as Dictionary
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})

	_stage = Node3D.new()
	root.add_child(_stage)

	# The bare body first: every reference measurement comes from one actor
	# wearing nothing, so a piece is judged against anatomy rather than
	# against whatever else happens to be equipped.
	var bare := _spawn({}, 0.0)
	await _settle([bare])
	# Anatomy, not bone lines: the split body names the very surfaces the
	# armour covers, so a cuirass is judged against the shirt it replaces
	# and a boot against the boot the body paints on.
	var reference := {
		3: _surface_bounds(bare, ["scalp", "hair"]),
		5: _surface_bounds(bare, ["wardrobe_shirt"]),
		4: _surface_bounds(bare, ["wardrobe_pants"]),
		6: _surface_bounds(bare, ["wardrobe_boots"]),
	}
	for part: int in reference:
		var box: AABB = reference[part] as AABB
		print("reference part %d: centre %s size %s" % [part,
			_round(box.get_center()), _round(box.size)])
	bare.queue_free()
	await process_frame

	var models_map: Dictionary = _equipment_config.get("models", {}) as Dictionary
	var wanted: Dictionary = {}
	for key_value: Variant in models_map:
		var parts_of: PackedStringArray = str(key_value).split(":")
		if parts_of.size() != 2:
			continue
		var part: int = int(parts_of[0])
		var visual: int = int(parts_of[1])
		if not RULES.has(part) or visual < 100:
			continue
		if not wanted.has(part):
			wanted[part] = PackedInt32Array()
		var list: PackedInt32Array = wanted[part]
		list.append(visual)
		wanted[part] = list

	for part: int in [3, 5, 4, 6]:
		if not wanted.has(part):
			continue
		var visuals: PackedInt32Array = wanted[part]
		visuals.sort()
		await _audit_part(part, visuals, reference[part] as AABB)

	_report()
	await _capture_outliers()
	_main.queue_free()
	await process_frame
	quit(_failures)

func _audit_part(part: int, visuals: PackedInt32Array, reference: AABB) -> void:
	var rule: Dictionary = RULES[part] as Dictionary
	var index := 0
	while index < visuals.size():
		var actors: Array = []
		var batch: Array[int] = []
		for slot: int in range(BATCH):
			if index >= visuals.size():
				break
			var visual: int = visuals[index]
			index += 1
			batch.append(visual)
			actors.append(_spawn({str(part): visual}, float(slot) * 4.0))
		await _settle(actors)
		for slot: int in range(actors.size()):
			var actor: ReplicatedActor3D = actors[slot]
			var box: AABB = _equipment_bounds(actor)
			var row := {
				"part": part, "visual": batch[slot], "kind": rule["name"],
				"empty": box.size == Vector3.ZERO,
			}
			if not row["empty"]:
				var here: AABB = reference
				# The reference was measured at the origin; every actor stands
				# at its own x, so the piece comes back to it before comparing.
				var centre: Vector3 = box.get_center()
				centre.x -= actor.global_position.x
				row["width"] = box.size.x / maxf(here.size.x, 1e-4)
				row["height"] = box.size.y / maxf(here.size.y, 1e-4)
				var home: Vector3 = here.get_center()
				# Sideways only: a brim or a crest moves the box centre up
				# or down while the piece sits perfectly well, but nothing
				# legitimate moves it off the body's axis.
				row["offset"] = Vector2(centre.x - home.x,
					centre.z - home.z).length()
				row["dy"] = centre.y - home.y
				# And it must be ON what it covers -- the body part's own
				# centre inside the piece box is what separates a tall helm
				# from a helm hanging beside the head.
				var grown: AABB = box.grow(0.02)
				grown.position.x -= actor.global_position.x
				row["covers"] = grown.has_point(home)
				# Headgear has one more duty: it has to enclose the skull.
				# A helm that clears the centre can still leave the crown
				# out in the air, which is what a shrunken helm looks like.
				# Circlets and bands are not meant to enclose anything, so only
				# pieces that claim to cover are asked to.
				var scene: String = str((_equipment_config.get("models", {}) as Dictionary)
					.get("%d:%d" % [part, batch[slot]], {}).get("scene", ""))
				if row["part"] == 3 and not scene.contains("circlet"):
					var top: float = box.position.y + box.size.y
					row["crown"] = top - (here.position.y + here.size.y)
					row["skullWidth"] = box.size.x - here.size.x
			_rows.append(row)
			actor.queue_free()
		await process_frame

func _report() -> void:
	# Judged against the slot's own median rather than an absolute size:
	# a gauntleted sheet and a plain one differ honestly, and what matters
	# is the piece that does not sit where its peers do.
	var median: Dictionary = {}
	for part: int in RULES:
		var widths: Array[float] = []
		for row: Dictionary in _rows:
			if row["part"] == part and not row["empty"]:
				widths.append(float(row["width"]))
		if widths.is_empty():
			continue
		widths.sort()
		median[part] = widths[widths.size() / 2]
	var bad: Array[Dictionary] = []
	for row: Dictionary in _rows:
		var rule: Dictionary = RULES[row["part"]] as Dictionary
		if row["empty"]:
			row["why"] = "nothing attached"
			bad.append(row)
			continue
		var why: PackedStringArray = PackedStringArray()
		var middle: float = float(median.get(row["part"], row["width"]))
		if row["width"] > middle * 1.35:
			why.append("wide %.2f vs slot median %.2f" % [row["width"], middle])
		if row["width"] < middle * 0.70:
			why.append("narrow %.2f vs slot median %.2f" % [row["width"], middle])
		if row["offset"] > float(rule["offsetMax"]):
			why.append("sideways %.3f" % row["offset"])
		if not bool(row.get("covers", true)):
			why.append("sits off the body it covers (dy %+.3f)" % row["dy"])
		if row.has("crown") and float(row["crown"]) < -0.005:
			why.append("crown out by %.3f" % -float(row["crown"]))
		if row.has("skullWidth") and float(row["skullWidth"]) < -0.005:
			why.append("narrower than the skull by %.3f" % -float(row["skullWidth"]))
		if not why.is_empty():
			row["why"] = ", ".join(why)
			bad.append(row)
	print("")
	print("audited %d pieces, %d outside the fit rules" % [_rows.size(), bad.size()])
	for part: int in [3, 5, 4, 6]:
		var widths: Array[float] = []
		for row: Dictionary in _rows:
			if row["part"] == part and not row["empty"]:
				widths.append(float(row["width"]))
		if widths.is_empty():
			continue
		widths.sort()
		print("  %-5s n=%3d width x reference: min %.2f median %.2f max %.2f"
			% [RULES[part]["name"], widths.size(), widths[0],
			widths[widths.size() / 2], widths[widths.size() - 1]])
	for row: Dictionary in bad:
		print("  FIT %-5s %d:%-3d  %s" % [row["kind"], row["part"],
			row["visual"], row["why"]])
	_failures = bad.size()
	_flagged = bad
	print("rendered equipment audit: ", "PASS" if _failures == 0
		else "FAIL (%d)" % _failures)

## Everything the numbers flagged, worn and photographed side by side, so a
## piece that measures oddly because it is styled that way can be told from
## one that is genuinely misplaced.
func _capture_outliers() -> void:
	if _flagged.is_empty():
		return
	var artifacts: String = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		artifacts = ProjectSettings.globalize_path("res://test-artifacts/equipment-audit")
	DirAccess.make_dir_recursive_absolute(artifacts)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = 40.0
	# The gameplay cull mask: every actor hangs a map disc three metres
	# overhead for the map cameras, and framing to it shrinks the subject
	# to nothing.
	camera.cull_mask = 3
	_stage.add_child(camera)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.82, 0.84, 0.88)
	environment.environment.ambient_light_energy = 1.2
	_stage.add_child(environment)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-35.0, 150.0, 0.0)
	_stage.add_child(key)
	root.size = Vector2i(1280, 480)
	var index := 0
	while index < _flagged.size():
		var actors: Array = []
		var labels: PackedStringArray = PackedStringArray()
		for slot: int in range(5):
			if index >= _flagged.size():
				break
			var row: Dictionary = _flagged[index]
			index += 1
			labels.append("%d:%d" % [row["part"], row["visual"]])
			actors.append(_spawn({str(row["part"]): row["visual"]},
				float(slot) * 1.7))
		await _settle(actors)
		for actor: ReplicatedActor3D in actors:
			for child: Node in actor.get_children():
				if child.name != "NativeModel" and child is VisualInstance3D:
					(child as VisualInstance3D).visible = false
		var bounds := AABB()
		var found := false
		for actor: ReplicatedActor3D in actors:
			var model: Node = actor.get_node_or_null("NativeModel")
			if model == null:
				continue
			for mesh_value: Node in model.find_children("*", "MeshInstance3D", true, false):
				var vi := mesh_value as VisualInstance3D
				if vi == null or not vi.is_visible_in_tree():
					continue
				var box: AABB = vi.global_transform * vi.get_aabb()
				bounds = box if not found else bounds.merge(box)
				found = true
		var centre: Vector3 = bounds.get_center()
		camera.global_position = centre + Vector3(0.0, 0.0,
			maxf(bounds.size.x, bounds.size.y) * 1.15)
		camera.look_at(centre, Vector3.UP)
		for _f: int in range(4):
			await process_frame
		var image: Image = root.get_texture().get_image()
		_sheet += 1
		var name: String = "audit-outliers-%d.png" % _sheet
		image.save_png(artifacts.path_join(name))
		print("  captured %s: %s" % [name, ", ".join(labels)])
		for actor: ReplicatedActor3D in actors:
			actor.queue_free()
		await process_frame

func _spawn(visuals: Dictionary, x: float) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	_next_id += 1
	actor.configure({
		"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "audit", "appearance": {}, "equipment_visuals": visuals,
	}, _adapter, _model_config, _animation_config, _equipment_config)
	actor.server_target = Vector3(x, 0.0, 0.0)
	actor.global_position = actor.server_target
	actor.rotation.y = 0.0
	return actor

func _settle(actors: Array) -> void:
	for actor: ReplicatedActor3D in actors:
		actor.play_action(&"idle")
	for _f: int in range(12):
		await process_frame

## Everything the equipment system attached, in world space.  Equipment nodes
## carry a meta the actor sets when it builds them, which is what separates a
## worn piece from the body under it.
func _equipment_bounds(actor: ReplicatedActor3D) -> AABB:
	var bounds := AABB()
	var found := false
	for node_value: Node in actor.find_children("*", "", true, false):
		if not node_value.has_meta("native_equipment"):
			continue
		for mesh_value: Node in _self_and_children(node_value):
			var vi := mesh_value as VisualInstance3D
			if vi == null or not vi.is_visible_in_tree():
				continue
			var box: AABB = vi.global_transform * vi.get_aabb()
			bounds = box if not found else bounds.merge(box)
			found = true
	return bounds if found else AABB()

func _self_and_children(node: Node) -> Array[Node]:
	var out: Array[Node] = [node]
	out.append_array(node.find_children("*", "VisualInstance3D", true, false))
	return out

## The body's own surfaces, by mesh node name -- the split race bodies name
## them, so the skull the scalp draws is measurable.
func _surface_bounds(actor: ReplicatedActor3D, names: Array) -> AABB:
	var bounds := AABB()
	var found := false
	var model: Node = actor.get_node_or_null("NativeModel")
	if model == null:
		return AABB()
	for node_value: Node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		if not names.has(mesh_node.name.to_lower()):
			continue
		var box: AABB = mesh_node.global_transform * mesh_node.get_aabb()
		bounds = box if not found else bounds.merge(box)
		found = true
	return bounds if found else AABB()

## A box around a pair of bones, padded by the limb's own girth, for the
## regions no single surface names.
func _bone_span(actor: ReplicatedActor3D, first: String, second: String) -> AABB:
	var skeleton: Skeleton3D = _skeleton_of(actor)
	if skeleton == null:
		return AABB()
	var a: int = skeleton.find_bone(first)
	var b: int = skeleton.find_bone(second)
	if a < 0 or b < 0:
		return AABB()
	var pa: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(a).origin
	var pb: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(b).origin
	var box := AABB(pa, Vector3.ZERO).expand(pb)
	# The bones are a line; a body is not.  Grown by a shoulder's half width
	# so the reference is the volume a garment covers, not the skeleton.
	return box.grow(0.16)

func _skeleton_of(actor: ReplicatedActor3D) -> Skeleton3D:
	var model: Node = actor.get_node_or_null("NativeModel")
	if model == null:
		return null
	for node_value: Node in model.find_children("*", "Skeleton3D", true, false):
		return node_value as Skeleton3D
	return null

func _round(v: Vector3) -> String:
	return "(%.3f, %.3f, %.3f)" % [v.x, v.y, v.z]
