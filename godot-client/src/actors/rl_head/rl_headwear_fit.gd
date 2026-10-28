class_name RLHeadwearFit
extends RefCounted
## Seats OPEN headwear - circlets, bands, crowns, a veil on a band - on the RL
## head, and lets its cloth trails hang onto the shoulders.
##
## The shipped head-slot pieces are fitted offline to the shipped Human head
## with a helmet's rule: one uniform scale and a translation, sized so the
## piece clears an envelope of the bald skull AND every offered hairstyle by
## 9 mm, measured on one level section 32 mm over the eyes. A band authored
## tilted, openwork that most rays pass through, and ribbons hanging inside the
## band's line all make that rule grow a circlet far past the head; on the
## RL cranium and on the shipped heads alike it floats centimetres clear, and its
## ribbons stand stiffly beside the face. See .local/rl-heads/evidence/
## headwear_audit for the numbers.
##
## For an actor with an RL head, and - a separate switch, the data's
## `shippedBodies` - for the shipped luminous heads (ReplicatedActor3D calls
## this from its head-piece hook; nothing here runs for any other actor), a
## piece listed in data/actors/rl_head_headwear_fit.json is rebuilt once per
## piece, head and outfit, never per identity:
##
##   * Fit. The piece as the runtime places it (socket, rest pose) takes a
##     similarity - scale, a mild width/depth ratio, a pitch about the band's
##     centre, an offset - and a low-order radial warp in the band's plane, so
##     the band rests about level on the skull: on the forehead 2.5-3.5 cm over
##     the brows, over the ears and round the back of the head, never under the
##     occipital bulge, a few millimetres clear of the skin - or, with hair
##     drawn, on the hair's under-layer, at most 6 mm over the skull, so loose
##     locks pass over and through the band instead of holding it out on the
##     hair's silhouette (fits[<base>/<hairstyle>]). Solved offline by
##     .local/rl-heads/scripts/headwear/fit_open_headwear.py against each
##     head's skin and each hairstyle's under-layer.
##   * Trails. Vertices hanging below the band (`trails`) keep their authored
##     length and hang from where the band now holds them: each falls straight
##     down and, where it meets the neck, the hair, the shoulders or the worn
##     torso piece, slides outwards over it (a rope walked through a radial
##     envelope of those surfaces about the neck axis), so ribbons fan out over
##     the shoulders. Their top rides Head, their lower part neck_01, spine_03
##     and the clavicle on their side, so a head turn bends them instead of
##     swinging them through the shoulders.
##
## The result is one skinned mesh per piece surface on the actor's skeleton,
## built from the piece's own arrays; the shipped GLB is never changed. The
## BoneAttachment3D the actor made stays (empty) so the equipment bookkeeping
## is unchanged.
##
## Limits: the drape is computed once, in the rest pose, against the torso
## worn at that moment (the actor rebuilds it when the torso changes); it does
## not collide in motion, so a far head turn or a raised shoulder can still
## pass a trail through the body, and a cape's collar is not part of the
## envelope. Identity controls are not read: they move the face, not the
## cranium the band rests on (ear_size changes the ears by a few millimetres,
## well under the band's clearance over them).

const DATA_PATH := "res://data/actors/rl_head_headwear_fit.json"
const NODE_PREFIX := "RLHeadwear_"
## The bones a refitted piece is skinned to, in bind order.
const BONES: PackedStringArray = ["Head", "neck_01", "spine_03", "clavicle_l", "clavicle_r"]
## The drape envelope: a radius per bearing about a vertical axis through the
## neck, per 1 cm height band.
const AXIS_Z := -0.03
const ROW_FLOOR := 1.20
const ROW_STEP := 0.01
const ROWS := 75
const COLUMNS := 72
const TRUNK_HALF := 0.30
## How far over a surface a hanging trail rides, and how far its own layers
## (the back of a ribbon, a fold of a veil) keep from each other.
const CLEARANCE := 0.004
const THICKNESS_CAP := 0.02
## The rope's step, in metres along the trail.
const STEP := 0.005
const MESH_CACHE_LIMIT := 48
const ENVELOPE_CACHE_LIMIT := 16

static var _data: Dictionary = {}
static var _loaded := false
static var _shipped := true
static var _meshes: Dictionary = {}
static var _envelopes: Dictionary = {}
static var _skins: Dictionary = {}


## The fit data; empty - every piece as shipped - while the RL_HEADWEAR_FIT
## developer variable is 0/off/no (before-and-after evidence renders). "rl"
## keeps the RL-head fits and leaves the shipped heads as shipped.
static func data() -> Dictionary:
	if not _loaded:
		_loaded = true
		var switch := OS.get_environment("RL_HEADWEAR_FIT").strip_edges().to_lower()
		_shipped = switch != "rl"
		if switch in ["0", "off", "no"]:
			return _data
		if FileAccess.file_exists(DATA_PATH):
			var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
			if parsed is Dictionary:
				_data = parsed
	return _data


## The piece's record, or {} for a piece that keeps its shipped placement
## (every closed helm, hood, cap and hat).
static func piece(visual_id: int) -> Dictionary:
	return (data().get("pieces", {}) as Dictionary).get(str(visual_id), {}) as Dictionary


static func has_piece(visual_id: int) -> bool:
	return not piece(visual_id).is_empty()


## Whether a shipped head (no RL head) of `body` - a model scene name such as
## luminous_female - takes the fits too: the data's `shippedBodies`. A separate
## switch from the RL-head fits: other race bodies wear their own variants on
## their own heads and are not listed.
static func fits_shipped_body(body: String) -> bool:
	var bodies: Variant = data().get("shippedBodies", [])
	return _shipped and bodies is Array and (bodies as Array).has(body)


## Which fit applies for `base` (an RL head's sex, or a shipped body's name):
## the one for this hairstyle, the fallback for an unfitted hairstyle, or the
## bald fit ("" hair: bald, or hidden by the piece).
static func fit_name(entry: Dictionary, base: String, hair: String) -> String:
	var fits: Dictionary = entry.get("fits", {}) as Dictionary
	if not hair.is_empty():
		var own := "%s/%s" % [base, hair]
		if fits.has(own):
			return own
		if fits.has(base + "/*"):
			return base + "/*"
	return base if fits.has(base) else ""


## The fit's similarity in model space, applied after the shipped placement.
static func fit_transform(fit: Dictionary) -> Transform3D:
	var s := float(fit.get("scale", 1.0))
	var aniso := sqrt(maxf(float(fit.get("aniso", 1.0)), 1e-6))
	var basis := Basis(Vector3.RIGHT, deg_to_rad(float(fit.get("pitchDegrees", 0.0)))) \
		* Basis.from_scale(Vector3(s * aniso, s, s / aniso))
	var pivot := _vec(fit.get("pivot", []))
	return Transform3D(basis, pivot - basis * pivot + _vec(fit.get("offset", [])))


## The radial warp's factor at `phi` (radians from the band's front, towards +X).
static func warp_factor(warp: Dictionary, phi: float) -> float:
	var a: Array = warp.get("cos", [1.0]) as Array
	var b: Array = warp.get("sin", []) as Array
	var k := float(a[0]) if not a.is_empty() else 1.0
	for m: int in range(1, a.size()):
		k += float(a[m]) * cos(m * phi)
		if m - 1 < b.size():
			k += float(b[m - 1]) * sin(m * phi)
	return k


## Refits the piece hanging on `attachment` for the head `base` (an RL head's
## sex, or a listed shipped body) of body sex `sex`, whose drawn hairstyle is
## `hair` ("" when bald or hidden). `sources` are the surfaces the trails may
## lie on: {key, mesh, ymax?} with vertices in model space at rest. Returns the
## skinned meshes it added to `skeleton` (the caller owns them), or [] -
## leaving the piece exactly as shipped - when the piece has no fit.
static func apply(attachment: BoneAttachment3D, visual_id: int, skeleton: Skeleton3D,
		base: String, sex: String, hair: String, sources: Array) -> Array[Node]:
	var made: Array[Node] = []
	var entry := piece(visual_id)
	if entry.is_empty() or attachment == null or skeleton == null:
		return made
	var chosen := fit_name(entry, base, hair)
	if chosen.is_empty():
		return made
	var fit: Dictionary = (entry.get("fits", {}) as Dictionary)[chosen]
	var trails: Variant = (entry.get("trails", {}) as Dictionary).get(sex)
	var trail_rule: Dictionary = trails if trails is Dictionary else {}
	for bone: String in BONES:
		if skeleton.find_bone(bone) < 0:
			return made
	var holder := attachment.get_child(0) as Node3D if attachment.get_child_count() > 0 else null
	if holder == null:
		return made
	var head_rest := skeleton.get_bone_global_rest(skeleton.find_bone("Head"))
	var grid := PackedFloat32Array()
	var grid_key := ""
	if not trail_rule.is_empty():
		var keys := PackedStringArray()
		for source: Dictionary in sources:
			keys.append(str(source.get("key", "")))
		grid_key = "|".join(keys)
		grid = _envelope(sources, grid_key)
	var skin := _skin(skeleton)
	for node_value: Node in holder.find_children("*", "MeshInstance3D", true, false):
		var original := node_value as MeshInstance3D
		if original.mesh == null:
			continue
		# Where the shipped placement puts this mesh in model space at rest.
		var placed := head_rest * holder.transform * _relative(original, holder)
		var key := "%d|%s|%s|%s|%d" % [visual_id, chosen, grid_key, original.name,
			original.mesh.get_instance_id()]
		var mesh := _meshes.get(key) as ArrayMesh
		if mesh == null:
			if _meshes.size() >= MESH_CACHE_LIMIT:
				_meshes.clear()
			mesh = _build(original.mesh, placed, fit, trail_rule, grid, skeleton)
			_meshes[key] = mesh
		var refit := MeshInstance3D.new()
		refit.name = NODE_PREFIX + str(original.name)
		refit.mesh = mesh
		refit.skin = skin
		refit.material_override = original.material_override
		refit.cast_shadow = original.cast_shadow
		refit.lod_bias = original.lod_bias
		for surface: int in mini(original.mesh.get_surface_count(), mesh.get_surface_count()):
			refit.set_surface_override_material(surface, original.get_surface_override_material(surface))
		skeleton.add_child(refit)
		refit.skeleton = refit.get_path_to(skeleton)
		refit.set_meta("native_equipment", true)
		refit.set_meta(&"rl_headwear_fit", chosen)
		made.append(refit)
	if not made.is_empty():
		attachment.remove_child(holder)
		holder.queue_free()
		attachment.set_meta(&"rl_headwear_fit", chosen)
	return made


static func _relative(node: Node3D, root: Node3D) -> Transform3D:
	var result := Transform3D.IDENTITY
	var walker := node
	while walker != null and walker != root:
		result = walker.transform * result
		walker = walker.get_parent() as Node3D
	return result


static func _skin(skeleton: Skeleton3D) -> Skin:
	# One skin per rest pose: every actor of a body shares its rest, so the key
	# is the rest itself, not the skeleton instance.
	var rest_key := ""
	for bone: String in BONES:
		rest_key += str(skeleton.get_bone_global_rest(skeleton.find_bone(bone)).origin)
	var cached := _skins.get(rest_key) as Skin
	if cached != null:
		return cached
	var skin := Skin.new()
	for bone: String in BONES:
		skin.add_named_bind(bone, skeleton.get_bone_global_rest(skeleton.find_bone(bone)).affine_inverse())
	_skins[rest_key] = skin
	return skin


# ---------------------------------------------------------------- the mesh

static func _build(source: Mesh, placed: Transform3D, fit: Dictionary, rule: Dictionary,
		grid: PackedFloat32Array, skeleton: Skeleton3D) -> ArrayMesh:
	var similarity := fit_transform(fit)
	var warp: Dictionary = fit.get("warp", {}) as Dictionary
	var scale := float(fit.get("scale", 1.0))
	var rotation := (similarity.basis * placed.basis).orthonormalized()
	var head_y := skeleton.get_bone_global_rest(skeleton.find_bone("Head")).origin.y
	var neck_y := skeleton.get_bone_global_rest(skeleton.find_bone("neck_01")).origin.y
	var out := ArrayMesh.new()
	out.resource_name = source.resource_name
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var count := vertices.size()
		var shipped := PackedVector3Array()
		shipped.resize(count)
		var fitted := PackedVector3Array()
		fitted.resize(count)
		for index: int in count:
			var p := placed * vertices[index]
			shipped[index] = p
			fitted[index] = _warp(similarity * p, warp)
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null \
			else PackedInt32Array(range(count))
		var weights := trail_weights(shipped, indices, rule)
		var positions := fitted.duplicate()
		var any_trail := false
		if not rule.is_empty() and not grid.is_empty():
			var length := 1.0 + (1.0 / maxf(scale, 1e-3) - 1.0) * float(rule.get("length", 1.0))
			positions = _drape(shipped, fitted, weights, indices, rule, scale, length, grid)
			for w: float in weights:
				if w > 0.0:
					any_trail = true
					break
		var normals := PackedVector3Array()
		var source_normals: Variant = arrays[Mesh.ARRAY_NORMAL]
		normals.resize(count)
		var face_normals := _vertex_normals(positions, indices) if any_trail else PackedVector3Array()
		for index: int in count:
			var n := Vector3.UP
			if source_normals is PackedVector3Array and (source_normals as PackedVector3Array).size() == count:
				n = (rotation * (source_normals as PackedVector3Array)[index]).normalized()
			if any_trail and weights[index] > 0.0 and face_normals[index].length_squared() > 0.0:
				var m := face_normals[index]
				if m.dot(n) < 0.0:
					m = -m
				n = n.lerp(m, weights[index]).normalized()
			normals[index] = n
		arrays[Mesh.ARRAY_VERTEX] = positions
		arrays[Mesh.ARRAY_NORMAL] = normals
		var tangents: Variant = arrays[Mesh.ARRAY_TANGENT]
		if tangents is PackedFloat32Array and (tangents as PackedFloat32Array).size() == count * 4:
			var t: PackedFloat32Array = (tangents as PackedFloat32Array).duplicate()
			for index: int in count:
				var v := rotation * Vector3(t[index * 4], t[index * 4 + 1], t[index * 4 + 2])
				v = (v - normals[index] * v.dot(normals[index])).normalized()
				t[index * 4] = v.x
				t[index * 4 + 1] = v.y
				t[index * 4 + 2] = v.z
			arrays[Mesh.ARRAY_TANGENT] = t
		var bones := PackedInt32Array()
		var bone_weights := PackedFloat32Array()
		bones.resize(count * 4)
		bone_weights.resize(count * 4)
		for index: int in count:
			_skin_weights(positions[index], weights[index], head_y, neck_y, bones, bone_weights, index)
		arrays[Mesh.ARRAY_BONES] = bones
		arrays[Mesh.ARRAY_WEIGHTS] = bone_weights
		out.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		out.surface_set_material(surface, source.surface_get_material(surface))
		out.surface_set_name(surface, source.surface_get_name(surface))
	return out


static func _warp(p: Vector3, warp: Dictionary) -> Vector3:
	if warp.is_empty():
		return p
	var origin := _vec(warp.get("origin", []))
	var axis := _vec(warp.get("axis", [0.0, 1.0, 0.0])).normalized()
	var front := Vector3.RIGHT.cross(axis).normalized()
	var left := axis.cross(front)
	var d := p - origin
	var height := d.dot(axis)
	var radial := d - axis * height
	var phi := atan2(radial.dot(left), radial.dot(front))
	return origin + axis * height + radial * warp_factor(warp, phi)


## Per vertex, how much of it hangs as a trail (0 = rigid with the band): the
## data's rule, replayed on the piece in its SHIPPED placement - below the
## band plane by `start`..`full`, in a component (vertices welded by position)
## reaching `minReach` below it, outside the front sector - or, with
## `dropHalfWidth`, a thin drop on the midline in front of the face.
static func trail_weights(shipped: PackedVector3Array, indices: PackedInt32Array,
		rule: Dictionary) -> PackedFloat32Array:
	var count := shipped.size()
	var weights := PackedFloat32Array()
	weights.resize(count)
	weights.fill(0.0)
	if rule.is_empty():
		return weights
	var point := _vec(rule.get("point", []))
	var normal := _vec(rule.get("normal", [0.0, 1.0, 0.0])).normalized()
	var centre := _vec(rule.get("centre", []))
	var start := float(rule.get("start", 0.0))
	var full := maxf(float(rule.get("full", 0.01)), start + 1e-4)
	var reach_needed := float(rule.get("minReach", 0.0))
	var sector := float(rule.get("frontSector", 0.0))
	# A thin drop on the midline in front (down the nose bridge) hangs too.
	var drop := float(rule.get("dropHalfWidth", 0.0))
	# weld by position, then union over triangle edges
	var parent := PackedInt32Array()
	parent.resize(count)
	var first: Dictionary = {}
	for index: int in count:
		var p := shipped[index]
		var cell := Vector3i(roundi(p.x * 1e5), roundi(p.y * 1e5), roundi(p.z * 1e5))
		if first.has(cell):
			parent[index] = int(first[cell])
		else:
			first[cell] = index
			parent[index] = index
	for corner: int in range(0, indices.size() - 2, 3):
		var a := _root(parent, indices[corner])
		for other: int in [indices[corner + 1], indices[corner + 2]]:
			var b := _root(parent, other)
			if a != b:
				parent[b] = a
	var below := PackedFloat32Array()
	below.resize(count)
	var reach: Dictionary = {}
	for index: int in count:
		below[index] = (point - shipped[index]).dot(normal)
		var r := _root(parent, index)
		reach[r] = maxf(float(reach.get(r, -INF)), below[index])
	for index: int in count:
		var d := shipped[index] - centre
		var bearing := absf(rad_to_deg(atan2(d.x, d.z)))
		var midline := drop > 0.0 and bearing < 30.0 and absf(d.x) < drop
		if not midline and (float(reach[_root(parent, index)]) < reach_needed or bearing <= sector):
			continue
		var t := clampf((below[index] - start) / (full - start), 0.0, 1.0)
		weights[index] = t * t * (3.0 - 2.0 * t)
	return weights


static func _root(parent: PackedInt32Array, index: int) -> int:
	var r := index
	while parent[r] != r:
		parent[r] = parent[parent[r]]
		r = parent[r]
	return r


## Hangs every trail vertex from where the band now holds it: up from its
## fitted position by its scaled depth under the band's start line, then down
## a rope `length` times as long through the envelope.
static func _drape(shipped: PackedVector3Array, fitted: PackedVector3Array,
		weights: PackedFloat32Array, indices: PackedInt32Array, rule: Dictionary,
		scale: float, length: float, grid: PackedFloat32Array) -> PackedVector3Array:
	var out := fitted.duplicate()
	var point := _vec(rule.get("point", []))
	var normal := _vec(rule.get("normal", [0.0, 1.0, 0.0])).normalized()
	var start := float(rule.get("start", 0.0))
	# A layer's offset over the innermost layer of the same trail at the same
	# bearing: the back of a ribbon, a fold of a veil stay apart.
	var inner: Dictionary = {}
	var attach := PackedVector3Array()
	attach.resize(fitted.size())
	for index: int in fitted.size():
		if weights[index] <= 0.0:
			continue
		var hang := maxf(0.0, ((point - shipped[index]).dot(normal) - start) * scale)
		var a := fitted[index] + Vector3.UP * hang
		attach[index] = a
		var bin := _bearing_bin(a)
		var rho := Vector2(a.x, a.z - AXIS_Z).length()
		inner[bin] = minf(float(inner.get(bin, INF)), rho)
	for index: int in fitted.size():
		var w := weights[index]
		if w <= 0.0:
			continue
		var a := attach[index]
		var hang := a.y - fitted[index].y
		var bearing := rad_to_deg(atan2(a.x, a.z - AXIS_Z))
		var rho := Vector2(a.x, a.z - AXIS_Z).length()
		var layer := clampf(rho - float(inner.get(_bearing_bin(a), rho)), 0.0, THICKNESS_CAP)
		var end := _hang(grid, bearing, rho, a.y, hang * length, CLEARANCE + layer)
		var direction := Vector3(sin(deg_to_rad(bearing)), 0.0, cos(deg_to_rad(bearing)))
		var draped := Vector3(direction.x * end.x, end.y, AXIS_Z + direction.z * end.x)
		out[index] = fitted[index].lerp(draped, w)
	return out


static func _bearing_bin(p: Vector3) -> int:
	return int(floor((rad_to_deg(atan2(p.x, p.z - AXIS_Z)) + 180.0) / 4.0))


## A rope from (rho, y) at `bearing`, `length` long: straight down while it is
## clear of the envelope, along it (outwards and down) where it is not.
static func _hang(grid: PackedFloat32Array, bearing: float, rho: float, y: float,
		length: float, clearance: float) -> Vector2:
	var at := Vector2(rho, y)
	var walked := 0.0
	var guard := 0
	while walked < length - 1e-5 and guard < 400:
		guard += 1
		var step := minf(STEP, length - walked)
		var target := Vector2(at.x, at.y - step)
		var floor_rho := reach(grid, bearing, target.y) + clearance
		if target.x < floor_rho:
			target.x = floor_rho
		var move := target - at
		var size := move.length()
		if size < 1e-7:
			break
		at += move * (step / size)
		walked += step
	# never end inside the envelope
	at.x = maxf(at.x, reach(grid, bearing, at.y) + clearance)
	return at


## Skin weights: the band rides Head; a trail's share moves to neck_01 under
## the jaw and to spine_03 and its side's clavicle below the neck.
static func _skin_weights(p: Vector3, trail: float, head_y: float, neck_y: float,
		bones: PackedInt32Array, weights: PackedFloat32Array, index: int) -> void:
	var on_head := clampf((p.y - neck_y) / maxf(head_y - neck_y, 1e-3), 0.0, 1.0)
	var lower := clampf((neck_y - p.y) / 0.05, 0.0, 1.0)
	var side := clampf((absf(p.x) - 0.05) / 0.08, 0.0, 1.0)
	var rest := trail * (1.0 - on_head)
	var head := 1.0 - rest
	var neck := rest * (1.0 - lower)
	var body := rest * lower
	var clavicle := body * side
	var spine := body - clavicle
	var base := index * 4
	bones[base] = 0
	bones[base + 1] = 1
	bones[base + 2] = 2
	bones[base + 3] = 3 if p.x >= 0.0 else 4
	weights[base] = head
	weights[base + 1] = neck
	weights[base + 2] = spine
	weights[base + 3] = clavicle


static func _vertex_normals(positions: PackedVector3Array, indices: PackedInt32Array) -> PackedVector3Array:
	var normals := PackedVector3Array()
	normals.resize(positions.size())
	for corner: int in range(0, indices.size() - 2, 3):
		var a := indices[corner]
		var b := indices[corner + 1]
		var c := indices[corner + 2]
		# Godot's front faces wind clockwise; the cross product follows the
		# source normals' side, which _build checks per vertex anyway.
		var n := (positions[c] - positions[a]).cross(positions[b] - positions[a])
		normals[a] += n
		normals[b] += n
		normals[c] += n
	for index: int in normals.size():
		if normals[index].length_squared() > 0.0:
			normals[index] = normals[index].normalized()
	return normals


# ---------------------------------------------------------------- envelope

static func columns() -> int:
	return COLUMNS


## The surfaces' farthest reach from the neck axis per bearing and height
## band, from their vertices (model space, rest), each cell widened to its
## neighbours so a sparse mesh leaves no hole.
static func _envelope(sources: Array, key: String) -> PackedFloat32Array:
	var cached: Variant = _envelopes.get(key)
	if cached is PackedFloat32Array:
		return cached
	var grid := PackedFloat32Array()
	grid.resize(ROWS * COLUMNS)
	grid.fill(0.0)
	var ceiling := ROW_FLOOR + ROWS * ROW_STEP
	for source: Dictionary in sources:
		var mesh := source.get("mesh") as Mesh
		if mesh == null:
			continue
		var ymax := float(source.get("ymax", INF))
		for surface: int in mesh.get_surface_count():
			# Loose hair cards are strays the cloth presses flat; the clumps are the hair.
			var material := mesh.surface_get_material(surface)
			if material != null and material.resource_name.contains("card"):
				continue
			var vertices: PackedVector3Array = mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			for p: Vector3 in vertices:
				if absf(p.x) > TRUNK_HALF or p.y < ROW_FLOOR or p.y >= ceiling or p.y > ymax:
					continue
				var dz := p.z - AXIS_Z
				var column := int(fposmod(rad_to_deg(atan2(p.x, dz)), 360.0) / (360.0 / COLUMNS)) % COLUMNS
				var at := int((p.y - ROW_FLOOR) / ROW_STEP) * COLUMNS + column
				var radius := sqrt(p.x * p.x + dz * dz)
				if radius > grid[at]:
					grid[at] = radius
	var widened := grid.duplicate()
	for row: int in ROWS:
		for column: int in COLUMNS:
			var best := 0.0
			for dr: int in [-1, 0, 1]:
				var r := row + dr
				if r < 0 or r >= ROWS:
					continue
				for dc: int in [-1, 0, 1]:
					best = maxf(best, grid[r * COLUMNS + (column + dc + COLUMNS) % COLUMNS])
			widened[row * COLUMNS + column] = best
	if _envelopes.size() >= ENVELOPE_CACHE_LIMIT:
		_envelopes.clear()
	_envelopes[key] = widened
	return widened


## The envelope's radius at a bearing (degrees from +Z towards +X) and height,
## bilinear between cell centres; 0 outside its rows.
static func reach(grid: PackedFloat32Array, bearing: float, y: float) -> float:
	if grid.is_empty():
		return 0.0
	var fy := (y - ROW_FLOOR) / ROW_STEP - 0.5
	if fy < -0.5 or fy > ROWS - 0.5:
		return 0.0
	fy = clampf(fy, 0.0, ROWS - 1.0001)
	var fx := fposmod(bearing, 360.0) / (360.0 / COLUMNS) - 0.5
	var c0 := int(floor(fx))
	var tx := fx - c0
	var r0 := int(floor(fy))
	var ty := fy - r0
	var a0 := (c0 + COLUMNS) % COLUMNS
	var a1 := (c0 + 1 + COLUMNS) % COLUMNS
	var low := lerpf(grid[r0 * COLUMNS + a0], grid[r0 * COLUMNS + a1], tx)
	var high := lerpf(grid[(r0 + 1) * COLUMNS + a0], grid[(r0 + 1) * COLUMNS + a1], tx)
	return lerpf(low, high, ty)


static func _vec(value: Variant) -> Vector3:
	if value is Array and (value as Array).size() >= 3:
		var a := value as Array
		return Vector3(float(a[0]), float(a[1]), float(a[2]))
	return Vector3.ZERO
