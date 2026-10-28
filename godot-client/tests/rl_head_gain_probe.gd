extends SceneTree
## Gain calibration probe for RLHeadPortraitMap (owner decision D3).
##
## Each develop face field moves the Low/Medium head through
## CharacterProportions.face_point, linear in p = (v - 50) / 50; at High the
## field drives its RL control by x = g * (v - c) / 50 with c the sex's preset.
## Matching the two near the centre means matching displacement per unit of
## the slider, so |g| is the ratio of the two displacement magnitudes (the
## 95th percentile over the RL skin and eye vertices each one moves by more
## than 15% of its largest move), the mean of the + and - directions. The sign
## is the least-squares projection's (the RL control moving the face the same
## way as the slider) where the two fields agree in shape (|cosine| >= 0.2),
## else +. The least-squares scale itself (with the plan's fixed couplings to
## a second control taken out first; eye_size fits its eyelid coupling by
## two-control least squares) and the cosine are reported too: a field whose
## RL control moves a different part of the face (jaw: the Low/Medium jaw is
## the front of the lower face, RL jaw_width the jaw angle) has a cosine near
## 0 and a meaningless projection, which is why the magnitude sets |g|.
##
## Headless, no GPU:
##   Godot --headless --path godot-client --script res://tests/rl_head_gain_probe.gd -- --out=<abs.json>
## Prints RL_HEAD_GAIN_PROBE_DONE; the result goes into
## data/actors/rl_head_wire_defaults.json `controls` by hand.

const FIELDS := ["jaw", "cheekbones", "nose", "face_length", "eye_size", "eye_tilt",
	"eye_spacing", "nose_width", "lip_fullness", "brow_depth"]
## Small steps where the field is not linear in p (the eye tilt is a rotation).
const STEPS := {"eye_tilt": 0.25}
const SIGNIFICANT := 0.15
const GAIN_RANGE := Vector2(0.25, 2.5)

var _out := ""


func _init() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			_out = argument.trim_prefix("--out=")
	call_deferred("_run")


func _json(path: String) -> Variant:
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _run() -> void:
	var registry: Dictionary = _json("res://data/actors/models.json")
	var equipment: Dictionary = _json("res://data/actors/equipment.json")
	var report := {"fields": {}, "secondary": {}, "method": "least squares on RL skin+eye vertices, |u| > 15% max"}
	for sex: String in ["female", "male"]:
		var model: Dictionary = (registry.models as Dictionary)["luminous_" + sex]
		var animation: Dictionary = _json(str(model.get("animationMap", "res://data/animations/luminous.json")))
		var actor := ReplicatedActor3D.new()
		actor.apply_render_quality(ActorRenderQuality.Quality.MEDIUM, false)
		root.add_child(actor)
		actor.configure({"actor_id": 9500, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "",
			"appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
			model, animation, equipment)
		var native := actor.get_node("NativeModel") as Node3D
		var skeleton := actor.get_skeleton()
		var frame := CharacterProportions.face_frame(native, skeleton)
		var to_head: Transform3D = frame.to_head
		var points := _rl_points(sex)
		var base: PackedVector3Array = points.base
		var shapes: Dictionary = points.shapes
		var head_points := PackedVector3Array()
		for point: Vector3 in base:
			head_points.append(to_head * point)
		for field: String in FIELDS:
			var index := FIELDS.find(field)
			var step := float(STEPS.get(field, 1.0))
			var control := str(RLHeadPortraitMap.PRIMARY[field])
			var entry := {}
			for direction: float in [1.0, -1.0]:
				var shape := PackedFloat32Array()
				shape.resize(FIELDS.size())
				shape[index] = step * direction
				# Low/Medium displacement for one unit of p in this direction.
				var lm := PackedVector3Array()
				lm.resize(base.size())
				var peak := 0.0
				for i: int in base.size():
					lm[i] = (CharacterProportions.face_point(head_points[i], frame, shape) - head_points[i]) / step
					peak = maxf(peak, lm[i].length())
				var suffix := "_p" if direction > 0.0 else "_n"
				var primary := _delta(shapes, "id_%s%s" % [control, suffix], base, to_head)
				var residual := lm.duplicate()
				for coupling: Dictionary in RLHeadPortraitMap.secondaries():
					if str(coupling.field) != field or field == "eye_size":
						continue
					var s := float(coupling.gain)
					var side := suffix if s >= 0.0 else ("_n" if suffix == "_p" else "_p")
					var secondary := _delta(shapes, "id_%s%s" % [coupling.control, side], base, to_head)
					for i: int in base.size():
						residual[i] -= absf(s) * secondary[i]
				var key := "plus" if direction > 0.0 else "minus"
				var ratio := _p95(lm) / maxf(_p95(primary), 1e-9)
				if field == "eye_size":
					var lid := _delta(shapes, "id_eyelid%s" % suffix, base, to_head)
					var fit := _fit2(primary, lid, residual, peak)
					entry[key] = {"ls_gain": fit.x, "eyelid": fit.y, "magnitude_ratio": ratio,
						"cosine": _cosine(primary, lm, peak, fit.x, lid, fit.y), "lm_peak_mm": peak * 1000.0,
						"rl_p95_mm": _p95(primary) * 1000.0}
				else:
					var g := _fit1(primary, residual, peak)
					entry[key] = {"ls_gain": g, "magnitude_ratio": ratio,
						"cosine": _cosine(primary, residual, peak, 1.0, PackedVector3Array(), 0.0),
						"lm_peak_mm": peak * 1000.0, "rl_p95_mm": _p95(primary) * 1000.0}
			var cosine := (float(entry.plus.cosine) + float(entry.minus.cosine)) * 0.5
			var sign := -1.0 if cosine <= -0.2 else 1.0
			var mean := sign * (float(entry.plus.magnitude_ratio) + float(entry.minus.magnitude_ratio)) * 0.5
			if field == "eye_size":
				# The Low/Medium eye control also opens the lids: two controls
				# share its displacement, so the joint least squares sets both.
				mean = (float(entry.plus.ls_gain) + float(entry.minus.ls_gain)) * 0.5
			entry["control"] = control
			entry["cosine"] = cosine
			entry["ls_gain"] = (float(entry.plus.ls_gain) + float(entry.minus.ls_gain)) * 0.5
			entry["gain_raw"] = mean
			entry["gain"] = snappedf(signf(mean) * clampf(absf(mean), GAIN_RANGE.x, GAIN_RANGE.y), 0.01)
			if field == "eye_size":
				entry["eyelid"] = snappedf((float(entry.plus.eyelid) + float(entry.minus.eyelid)) * 0.5, 0.01)
			var fields: Dictionary = report.fields
			if not fields.has(field):
				fields[field] = {}
			(fields[field] as Dictionary)[sex] = entry
			print("RL gain %s %s -> %s: g=%.3f (magnitude +%.3f / -%.3f; least squares %.3f; cos %.2f)" % [sex,
				field, control, mean, float(entry.plus.magnitude_ratio), float(entry.minus.magnitude_ratio),
				float(entry.ls_gain), cosine])
		actor.free()
	if not _out.is_empty():
		var file := FileAccess.open(_out, FileAccess.WRITE)
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	print("RL_HEAD_GAIN_PROBE_DONE")
	quit(0)


## The RL head lod0 skin and eye vertices (model space) and every blend shape
## on them.
func _rl_points(sex: String) -> Dictionary:
	var info := RLHeadLibrary.head(sex)
	var base := PackedVector3Array()
	var shapes := {}
	for piece: Dictionary in (info.lods as Array)[0]:
		var mesh := piece.mesh as Mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface)
			if material == null or material.resource_name not in ["rl_skin", "rl_eye"]:
				continue
			var arrays := mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var blends := mesh.surface_get_blend_shape_arrays(surface)
			var offset := base.size()
			base.append_array(vertices)
			for shape: int in mesh.get_blend_shape_count():
				var name := str(mesh.get_blend_shape_name(shape))
				if not shapes.has(name):
					shapes[name] = PackedVector3Array()
				var positions: PackedVector3Array = (blends[shape] as Array)[Mesh.ARRAY_VERTEX]
				var list: PackedVector3Array = shapes[name]
				list.resize(offset)
				list.append_array(positions)
				shapes[name] = list
	for name: String in shapes:
		(shapes[name] as PackedVector3Array).resize(base.size())
	return {"base": base, "shapes": shapes}


## A blend shape's displacement per vertex at weight 1, in the Head frame.
## Godot hands blend shapes back as positions; offsets are told apart by size.
func _delta(shapes: Dictionary, name: String, base: PackedVector3Array, to_head: Transform3D) -> PackedVector3Array:
	var result := PackedVector3Array()
	result.resize(base.size())
	if not shapes.has(name):
		push_warning("RL gain probe: no blend shape " + name)
		return result
	var positions: PackedVector3Array = shapes[name]
	var absolute := 0.0
	var relative := 0.0
	for i: int in mini(64, base.size()):
		absolute += (positions[i] - base[i]).length()
		relative += positions[i].length()
	var offsets := relative < absolute
	for i: int in base.size():
		var moved := positions[i] if offsets else positions[i] - base[i]
		result[i] = to_head.basis * moved
	return result


## The 95th percentile displacement over the vertices a field moves (more than
## SIGNIFICANT of its own largest move).
func _p95(field: PackedVector3Array) -> float:
	var peak := 0.0
	for value: Vector3 in field:
		peak = maxf(peak, value.length())
	var sizes: Array[float] = []
	for value: Vector3 in field:
		if value.length() >= SIGNIFICANT * peak and peak > 0.0:
			sizes.append(value.length())
	if sizes.is_empty():
		return 0.0
	sizes.sort()
	return sizes[mini(sizes.size() - 1, int(sizes.size() * 0.95))]


func _fit1(w: PackedVector3Array, u: PackedVector3Array, peak: float) -> float:
	var num := 0.0
	var den := 0.0
	for i: int in w.size():
		if u[i].length() < SIGNIFICANT * peak:
			continue
		num += w[i].dot(u[i])
		den += w[i].dot(w[i])
	return num / den if den > 1e-12 else 1.0


func _fit2(a: PackedVector3Array, b: PackedVector3Array, u: PackedVector3Array, peak: float) -> Vector2:
	var aa := 0.0
	var ab := 0.0
	var bb := 0.0
	var au := 0.0
	var bu := 0.0
	for i: int in a.size():
		if u[i].length() < SIGNIFICANT * peak:
			continue
		aa += a[i].dot(a[i])
		ab += a[i].dot(b[i])
		bb += b[i].dot(b[i])
		au += a[i].dot(u[i])
		bu += b[i].dot(u[i])
	var determinant := aa * bb - ab * ab
	if absf(determinant) < 1e-18:
		return Vector2(_fit1(a, u, peak), 0.0)
	return Vector2((au * bb - bu * ab) / determinant, (bu * aa - au * ab) / determinant)


## Cosine between the fitted RL displacement and the Low/Medium one over the
## vertices the field moves.
func _cosine(a: PackedVector3Array, u: PackedVector3Array, peak: float, ga: float,
		b: PackedVector3Array, gb: float) -> float:
	var dot := 0.0
	var nn := 0.0
	var uu := 0.0
	for i: int in a.size():
		if u[i].length() < SIGNIFICANT * peak:
			continue
		var w := a[i] * ga + (b[i] * gb if not b.is_empty() else Vector3.ZERO)
		dot += w.dot(u[i])
		nn += w.dot(w)
		uu += u[i].dot(u[i])
	return dot / sqrt(nn * uu) if nn > 0.0 and uu > 0.0 else 0.0
