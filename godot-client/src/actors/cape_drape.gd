class_name CapeDrape
extends RefCounted
## Holds a cape's rigid yoke outside the armour it is actually worn over.
##
## The cape's collar, and the sheet above the shoulder blades, are skinned to
## spine_03 and to nothing else - no cape bone touches them, so the cloth solver
## in `cape_cloth.gd` has no authority there whatever it does below. They were
## conformed once, offline, against the BARE back. Every torso in the ladder
## stands deeper than that: between 11 and 53 mm over the shoulder blades on the
## plainest shirt, and a gorget or a mantle reaches 100 mm further still. So the
## armour came through the cloth on every armoured wearer, in every pose.
##
## One authored cape cannot clear all sixty-four of them. Conformed to the
## deepest, its collar stands off the shoulders like a shelf on everything else
## - measured, and looked at. So the yoke is pushed out here instead, against
## the piece the actor is wearing, and the result is cached per cape and torso.

## The envelope is a radius per bearing around the trunk, per height band.
## A depth alone cannot describe a collar: it is a ring, and holding a ring back
## in z flattens it into a bar behind the shoulders. What a cape does over a
## gorget is take a wider radius at the same bearing, which is what this
## measures and what the push restores.
##
## The trunk line is taken as x = 0, z = 0 rather than the spine bone, which
## wanders 40 mm through the chest. Envelope and cloth are read against the same
## origin, so a shared one is all the clearance needs; over the back half of a
## torso every bearing still meets the surface once, which is the only property
## relied on.
const BEARING_STEP := 10.0
const BEARING_LIMIT := 90.0
const BAND_STEP := 0.05
const BAND_FLOOR := 0.90
const BAND_CEILING := 1.65
## Half the trunk the envelope is built from. Torso models are authored in an A
## pose, so a sleeve reaches 700 mm out; measured around the spine that reads as
## a bearing of 80 degrees at three times the radius of the back it belongs to,
## and it would inflate the cape into a barrel. A cape is worn over the trunk,
## and the arms hang outside it.
const TRUNK_HALF := 0.26
## How far outside the armour the cloth rides.
const CLEARANCE := 0.02
## The bare trunk's radius, and the floor under every measured reach: a bare
## back stands 0.18 behind the spine and the cloth rides clear of it. The
## solver holds this constant too, so it is stated once here.
const BARE_TRUNK_RADIUS := 0.205
## The cape is the outer layer across the back, and only there.
##
## A pauldron sitting over the end of the collar is how armour is worn, not a
## defect, and so is a gorget standing over the collar itself: the cloth tucks
## under both. Push those out and the collar stops being a ring around the
## shoulders and becomes a plank across them - which is what conforming the
## whole yoke looked like, rendered. So the push is full across the back and
## gone past the point of the shoulder, and full below the shoulder line and
## gone at the collar. What is left is the sheet over the shoulder blades,
## where the cape is unambiguously the outer layer and where the armour was in
## fact coming through.
##
## The bands follow the cape's own shape. The shared cape of 2026-10 hangs
## clear of every Human torso across the shoulder blades already, and its
## collar slopes down to 1.43 at the sides where the old one ran level at 1.53;
## its side edges cross the shoulder at a bearing of 40 to 50 degrees. At
## 50/65 and 1.44/1.53 nearly all the push landed on those edges and the
## sloping collar, and drew the trim out over the shoulder in a hook. Faded at
## 30/45 the side edges still tuck under the shoulders. The vertical fade
## now reaches 1.54 so the softened rear fold joins the armour fit gradually;
## ending it at 1.46 pinched the reshaped sheet against deep back plates.
const DRAPE_ARC := 30.0
const DRAPE_FADE := 45.0
const DRAPE_SHOULDER := 1.38
const DRAPE_COLLAR := 1.54
## Samples along a bone axis in the reach the cloth solver is given. Nine over
## the trunk is a sample every 55 mm, which follows a back plate without
## chasing the rivets on it.
const REACH_SAMPLES := 9
## A vertex with no weight on a cape bone is yoke, and takes the whole push;
## one the solver shares takes its share. Below that the solver owns the cloth
## and lifts it off the body every frame, and an offset baked in here would be
## added on top of whatever it does.
const CAPE_BONE_PREFIX := "cape_"
## The push one vertex wants is not limited by what the vertices beside it get.
## Where the fades fall off, at the sides of the collar, the shoulder of a coat
## stands 140 mm out along the same bearing as a collar vertex 30 mm from one the
## fade has already released: the first went out 110 mm, the second 20, and the
## edge between them drew a sliver of cloth off the shoulder on every torso in
## the ladder. So the push may change by at most SLOPE times the cloth between
## two vertices. A vertex is held back to what its neighbours allow, never
## pushed further than it wanted, so this only ever lets armour show near a
## fade, where tucking the cloth under it is the intent anyway.
const SLOPE := 1.0
## Relaxation sweeps; a ladder torso settles in under ten.
const SLOPE_PASSES := 64
## The solver's capsules are round, so a reach counted all the way round the
## back was the girth at the flanks: the Studded Jack's sides stand 0.29 from
## the spine where its back stands 0.15, and that capsule held the middle of
## the cape a hand's width off the jack. The chains hang within about 40
## degrees of straight back, so only the armour they can reach is counted.
const REACH_BEARING := 45.0
## How far below the pelvis the waist capsule's cap counts the worn torso: a
## coat tail or a plate skirt hangs there, behind the cape's middle joint.
const SEAT_BELOW := 0.20
## The floor under a shin's measured reach. The reach itself is read off the
## body's own calf, which stands 0.08-0.15 behind the knee-to-ankle line, and
## off what is worn over it; the floor only covers a rig whose body was not
## measured.
const BARE_SHIN_RADIUS := 0.10
## A shin's reach is kept per bearing from the leg's own back, in this many
## columns of SHIN_BEARING_STEP degrees, the last taking everything further
## round. Kept as one radius it was the round capsule again: a knee flap
## standing 0.31 straight back pushed the cape out at every bearing, where the
## legs reach 0.13-0.17, and an idle cape bowed 45 mm off the calves.
const SHIN_BEARINGS := 7
const SHIN_BEARING_STEP := 15.0
## How far off what is worn the legs' measured reach holds the cloth. Two
## centimetres held an idle Vanguard cape 2 cm out from legs it cleared.
const LEG_CLEARANCE := 0.01
## How far down the thigh, hip to knee, its reach starts counting: above, the
## seat and the skirts behind it are the waist capsule's.
const THIGH_FROM := 0.4
## The cape chains, as `cape_<side>_01..04` in the rig.
const CHAIN_SIDES: Array[String] = ["l", "c", "r"]
const CHAIN_LINKS := 4
## A chain's cloth is read in a strip this far either side of its root bone,
## and this far above and below each joint, as the middle of the sheet there:
## its folds stand in and out by a few centimetres either way.
const LINE_BAND := 0.05
const LINE_SLICE := 0.05
## The hem's trim rolls outward; the lowest joint reads the sheet above it.
const LINE_HEM := 0.08
## How far a joint's folds come in toward the body past its line, read this
## far through the strip: the inner crests the shins meet.
const LINE_FOLD := 0.90
## How far from the middle chain the sheet reaches at a joint, read this far
## out through it: 0.24 either side at the top link and 0.37 at the hem.
const LINE_WIDTH := 0.90
## Carry the clasp and upper side panels over the shoulders. The authored
## collar sides sat below the shoulders and behind them, like a back-mounted
## ledge. Lift and sweep the sides toward the front attachment, then release
## that shaping smoothly down the back before measuring the free cloth.
const SHOULDER_HEIGHT := 1.56
const SHOULDER_FORWARD := 0.10
const SHOULDER_DROP := 0.012
const SHOULDER_EASE := 0.055

## The cape's cross-section is read at this many places from side to side, at
## each joint, each from cloth within FOLD_WINDOW of it. Below the yoke the
## sheet is a U round the body: 25 cm out from the middle it stands 10-15 cm
## further in than the chains' line. Read over a wide stretch, a crest is the
## furthest-in cloth anywhere in it, and an idle cape was pushed 6 cm off legs
## it cleared.
const SECTION_BINS := 9
const FOLD_WINDOW := 0.04


static func columns() -> int:
	return int(round(BEARING_LIMIT * 2.0 / BEARING_STEP)) + 1


static func rows() -> int:
	return int(round((BAND_CEILING - BAND_FLOOR) / BAND_STEP)) + 1


## How far the worn torso reaches from the trunk line, per bearing and band.
## Empty when the pieces carry no geometry in the band a cape covers.
static func envelope(pieces: Array) -> PackedFloat32Array:
	var wide: int = columns()
	var tall: int = rows()
	var grid := PackedFloat32Array()
	grid.resize(tall * wide)
	grid.fill(0.0)
	var seen := false
	for piece_value: Variant in pieces:
		var piece: Dictionary = piece_value as Dictionary
		var mesh: Mesh = piece.get("mesh") as Mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var arrays: Array = mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			for point: Vector3 in vertices:
				if absf(point.x) > TRUNK_HALF:
					continue
				if point.y < BAND_FLOOR or point.y >= BAND_CEILING:
					continue
				var bearing: float = rad_to_deg(atan2(point.x, -point.z))
				if absf(bearing) > BEARING_LIMIT:
					continue
				var at: int = (int((point.y - BAND_FLOOR) / BAND_STEP) * wide
					+ int((bearing + BEARING_LIMIT) / BEARING_STEP))
				var radius: float = Vector2(point.x, point.z).length()
				if radius > grid[at]:
					grid[at] = radius
					seen = true
	if not seen:
		return PackedFloat32Array()
	return _dilate(grid, tall, wide)


## Deep cells spread into the bearings beside them before anything is read
## against them: a cell boundary is not a surface, and interpolating between a
## proud cell and the slack one beside it threads the cloth back through the
## plate that made the first one proud. Only sideways, though - a back that is
## deep at the shoulder blade and shallow at the collar is a slope, not a step,
## and smearing it up the spine lifted the collar off the shoulders.
static func _dilate(grid: PackedFloat32Array, tall: int,
		wide: int) -> PackedFloat32Array:
	var out := grid.duplicate()
	for row: int in range(tall):
		for column: int in range(wide):
			var best: float = grid[row * wide + column]
			for across: int in [-1, 0, 1]:
				var near_column: int = column + across
				if near_column < 0 or near_column >= wide:
					continue
				best = maxf(best, grid[row * wide + near_column])
			out[row * wide + column] = best
	return out


## The envelope at a bearing and height, bilinear between cell centres.
static func reach(grid: PackedFloat32Array, bearing: float, y: float) -> float:
	var wide: int = columns()
	var tall: int = rows()
	var across: float = clampf((bearing + BEARING_LIMIT) / BEARING_STEP - 0.5,
		0.0, float(wide) - 1.0001)
	var down: float = clampf((y - BAND_FLOOR) / BAND_STEP - 0.5,
		0.0, float(tall) - 1.0001)
	var column: int = int(across)
	var row: int = int(down)
	var fx: float = across - float(column)
	var fy: float = down - float(row)
	var top: float = lerpf(grid[row * wide + column],
		grid[row * wide + column + 1], fx)
	var bottom: float = lerpf(grid[(row + 1) * wide + column],
		grid[(row + 1) * wide + column + 1], fx)
	return lerpf(top, bottom, fy)


## A relaxed shoulder fold, then a fit to the worn torso's envelope. Empty
## armour still receives the shoulder fold; the source mesh stays untouched.
static func drape(mesh: Mesh, bones: PackedStringArray,
		grid: PackedFloat32Array) -> Mesh:
	if mesh == null:
		return mesh
	mesh = _hang_yoke(mesh)
	if grid.is_empty():
		return mesh
	var surfaces: Array = []
	# Vertices the yoke rules may move, welded by position across surfaces so
	# a trim and the cloth it borders keep one push along their seam.
	var node_of: Dictionary = {}
	var push: PackedFloat32Array = PackedFloat32Array()
	var moved := false
	for surface: int in range(mesh.get_surface_count()):
		var arrays: Array = mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bone_indices: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var per_vertex: int = 0
		if not vertices.is_empty() and not bone_indices.is_empty():
			per_vertex = bone_indices.size() / vertices.size()
		var nodes := PackedInt32Array()
		nodes.resize(vertices.size())
		nodes.fill(-1)
		for index: int in range(vertices.size()):
			var rigid: float = _rigid_share(bones, bone_indices, weights,
				index, per_vertex)
			if rigid <= 0.0:
				continue
			var point: Vector3 = vertices[index]
			if point.y < BAND_FLOOR or point.y >= BAND_CEILING:
				continue
			var bearing: float = rad_to_deg(atan2(point.x, -point.z))
			var fade: float = (1.0 - smoothstep(DRAPE_ARC, DRAPE_FADE,
				absf(bearing))) * (1.0 - smoothstep(DRAPE_SHOULDER,
				DRAPE_COLLAR, point.y))
			if fade <= 0.0:
				continue
			var radius: float = Vector2(point.x, point.z).length()
			if radius < 0.001:
				continue
			var wanted: float = reach(grid, bearing, point.y) + CLEARANCE
			var out: float = maxf(0.0, (wanted - radius) * rigid * fade)
			var key: Vector3 = point.snapped(Vector3.ONE * 0.00001)
			var node: int = int(node_of.get(key, -1))
			if node < 0:
				node = push.size()
				node_of[key] = node
				push.append(out)
			else:
				push[node] = maxf(push[node], out)
			nodes[index] = node
			if out > 0.0:
				moved = true
		surfaces.append({"arrays": arrays, "nodes": nodes})
	if not moved:
		return mesh
	_limit_slope(surfaces, push)
	var built := ArrayMesh.new()
	for surface: int in range(surfaces.size()):
		var arrays: Array = surfaces[surface]["arrays"]
		var nodes: PackedInt32Array = surfaces[surface]["nodes"]
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for index: int in range(vertices.size()):
			var node: int = nodes[index]
			if node < 0 or push[node] <= 0.0:
				continue
			# Straight out along its own bearing, so the ring stays a ring.
			var point: Vector3 = vertices[index]
			var scale: float = push[node] / Vector2(point.x, point.z).length()
			vertices[index] = Vector3(point.x + point.x * scale, point.y,
				point.z + point.z * scale)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		built.add_surface_from_arrays(mesh.surface_get_primitive_type(surface),
			arrays, [], {},
			mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		built.surface_set_material(surface, mesh.surface_get_material(surface))
		built.surface_set_name(surface, mesh.surface_get_name(surface))
	return built


## The upper cape wraps over the shoulder toward its clasp, while the rear
## fold eases into the hanging sheet. The hem stays at its authored height.
## Preserve folds, seams and skin weights.
static func _shoulder_point(point: Vector3) -> Vector3:
	var shoulder := smoothstep(0.0, 0.16, absf(point.x))
	var upper := smoothstep(1.20, 1.44, point.y)
	var over := SHOULDER_FORWARD * shoulder * smoothstep(1.30, 1.44, point.y)
	var shoulder_z := point.z + over
	var shoulder_y := SHOULDER_HEIGHT + 0.10 * (point.y - 1.44) \
		- 2.0 * (shoulder_z + 0.02) * (shoulder_z + 0.02)
	var lift := (shoulder_y - point.y) * shoulder * upper
	var down := SHOULDER_DROP * (1.0 - shoulder) * smoothstep(0.03, 0.21, -point.z) \
		* smoothstep(1.40, 1.56, point.y)
	var inward := SHOULDER_EASE * smoothstep(0.08, 0.23, -point.z) \
		* smoothstep(1.06, 1.38, point.y) * (1.0 - smoothstep(1.43, 1.60, point.y)) \
		* maxf(1.0 - smoothstep(0.08, 0.20, absf(point.x)), 0.25 * smoothstep(1.38, 1.46, point.y))
	var y := point.y + lift - down
	var radius := lerpf(BARE_TRUNK_RADIUS, 0.10, smoothstep(1.40, 1.60, y))
	var back := sqrt(maxf(0.0, radius * radius - point.x * point.x))
	inward = minf(inward, 0.65 * maxf(0.0, -point.z - back))
	return Vector3(point.x, y, point.z + inward + over)


static func _hang_yoke(mesh: Mesh) -> Mesh:
	var built := ArrayMesh.new()
	for surface: int in range(mesh.get_surface_count()):
		var arrays: Array = mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
		for index: int in range(vertices.size()):
			var point := vertices[index]
			var hung := _shoulder_point(point)
			if hung.is_equal_approx(point):
				continue
			# Differentiate the fit in all three directions: inverse transpose
			# for normals, direct transform for tangents. UVs and skin stay exact.
			var epsilon := 0.0001
			var warp := Basis.IDENTITY
			for axis: int in 3:
				var offset := Vector3.ZERO
				offset[axis] = epsilon
				warp[axis] = (_shoulder_point(point + offset)
					- _shoulder_point(point - offset)) / (2.0 * epsilon)
			vertices[index] = hung
			if index < normals.size():
				normals[index] = (warp.inverse().transposed() * normals[index]).normalized()
			if tangents.size() >= (index + 1) * 4:
				var tangent := (warp * Vector3(tangents[index * 4],
					tangents[index * 4 + 1], tangents[index * 4 + 2])).normalized()
				tangents[index * 4] = tangent.x
				tangents[index * 4 + 1] = tangent.y
				tangents[index * 4 + 2] = tangent.z
		arrays[Mesh.ARRAY_VERTEX] = vertices
		arrays[Mesh.ARRAY_NORMAL] = normals
		arrays[Mesh.ARRAY_TANGENT] = tangents
		built.add_surface_from_arrays(mesh.surface_get_primitive_type(surface),
			arrays, [], {}, mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		built.surface_set_material(surface, mesh.surface_get_material(surface))
		built.surface_set_name(surface, mesh.surface_get_name(surface))
	return built


## Holds each push to what the cloth beside it allows: no more than SLOPE times
## the rest length of an edge above its neighbour's. A vertex the yoke rules do
## not move is a neighbour that stays put.
static func _limit_slope(surfaces: Array, push: PackedFloat32Array) -> void:
	var from := PackedInt32Array()
	var to := PackedInt32Array()
	var allow := PackedFloat32Array()
	for entry: Dictionary in surfaces:
		var arrays: Array = entry["arrays"]
		var nodes: PackedInt32Array = entry["nodes"]
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices := PackedInt32Array()
		if arrays[Mesh.ARRAY_INDEX] != null:
			indices = arrays[Mesh.ARRAY_INDEX]
		var count: int = vertices.size()
		if not indices.is_empty():
			count = indices.size()
		for corner: int in range(0, count - 2, 3):
			for side: int in range(3):
				var a: int = corner + side
				var b: int = corner + (side + 1) % 3
				if not indices.is_empty():
					a = indices[a]
					b = indices[b]
				if nodes[a] < 0 and nodes[b] < 0:
					continue
				from.append(nodes[a])
				to.append(nodes[b])
				allow.append(SLOPE * vertices[a].distance_to(vertices[b]))
	for _pass: int in range(SLOPE_PASSES):
		var changed := false
		for edge: int in range(from.size()):
			var a: int = from[edge]
			var b: int = to[edge]
			var at_a: float = push[a] if a >= 0 else 0.0
			var at_b: float = push[b] if b >= 0 else 0.0
			if a >= 0 and at_a > at_b + allow[edge]:
				push[a] = at_b + allow[edge]
				changed = true
			elif b >= 0 and at_b > at_a + allow[edge]:
				push[b] = at_a + allow[edge]
				changed = true
		if not changed:
			return


## How much of a vertex the spine holds rather than the cloth solver.
static func _rigid_share(bones: PackedStringArray,
		bone_indices: PackedInt32Array, weights: PackedFloat32Array,
		index: int, per_vertex: int) -> float:
	if per_vertex <= 0 or weights.size() < (index + 1) * per_vertex:
		return 0.0
	var rigid := 0.0
	for slot: int in range(per_vertex):
		var at: int = index * per_vertex + slot
		var bone: int = bone_indices[at]
		if bone < 0 or bone >= bones.size():
			continue
		if bones[bone].begins_with(CAPE_BONE_PREFIX):
			continue
		rigid += weights[at]
	return clampf(rigid, 0.0, 1.0)


## How far the worn torso reaches from one of the solver's bone axes, sampled
## along it. The drape measures about the trunk line because it is cutting a
## ring; the solver pushes radially out of a capsule, so what it needs is the
## reach about that capsule's own axis and nothing else would be exact.
##
## The chest is left out. A breastplate is as proud as a back plate and no cape
## ever touches it, and counting it would inflate the capsule the hem swings
## around into a barrel the cloth could not fall inside of. So are the flanks
## past REACH_BEARING, for the same reason. What is counted is held CLEARANCE
## off: the solver pushes the cloth itself out to this radius.
##
## `below` also counts what hangs past the `from` end, up to that far along the
## axis, into the first sample as its distance from the end: that is the round
## cap the solver pushes the cloth out of there. The waist capsule ends at the
## pelvis, and a coat tail or a plate skirt hangs below it, right where the
## cape's middle joint is.
static func axis_reach(pieces: Array, from: Vector3, to: Vector3,
		floor_radius: float, below: float = 0.0) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(REACH_SAMPLES)
	out.fill(floor_radius)
	var axis: Vector3 = to - from
	var span: float = axis.length_squared()
	if span < 1e-9:
		return out
	for piece_value: Variant in pieces:
		var piece: Dictionary = piece_value as Dictionary
		var mesh: Mesh = piece.get("mesh") as Mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var arrays: Array = mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			for point: Vector3 in vertices:
				if absf(point.x) > TRUNK_HALF:
					continue
				# Only what stands beside the axis, not what stands past its
				# ends: a capsule's cap measures a shoulder from the waist
				# bone as if it were a metre of girth, which is how the first
				# cut of this pushed the cape 400 mm off the back.
				var travel: float = (point - from).dot(axis) / span
				if travel < 0.0 and -travel * sqrt(span) <= below:
					var hanging: Vector3 = point - from
					if hanging.z > 0.0 or rad_to_deg(atan2(absf(hanging.x),
							-hanging.z)) > REACH_BEARING:
						continue
					out[0] = maxf(out[0], hanging.length() + CLEARANCE)
					continue
				if travel < 0.0 or travel > 1.0:
					continue
				var away: Vector3 = point - (from + axis * travel)
				if away.z > 0.0:
					continue
				if rad_to_deg(atan2(absf(away.x), -away.z)) > REACH_BEARING:
					continue
				var slot: int = int(round(travel * float(REACH_SAMPLES - 1)))
				var radius: float = away.length() + CLEARANCE
				if radius > out[slot]:
					out[slot] = radius
	# A sample boundary is not a surface either: each one carries its
	# neighbours so the interpolation between two never dips inside the plate
	# that made the deeper of them deep.
	var smeared := out.duplicate()
	for slot: int in range(REACH_SAMPLES):
		if slot > 0:
			smeared[slot] = maxf(smeared[slot], out[slot - 1])
		if slot + 1 < REACH_SAMPLES:
			smeared[slot] = maxf(smeared[slot], out[slot + 1])
	return smeared


## Where each cape chain's cloth hangs behind the chain's material line, joint
## by joint, in the skeleton's rest space: the line the cloth solver simulates
## (`set_fabric_line` in cape_cloth.gd). One PackedVector3Array of offsets per
## chain, from the root's joint to the tip's; empty when the rig carries no
## cape chains or the cape has no cloth on them.
##
## The material line drops plumb from each chain's root bone, which sits on the
## spine. The cloth is read off the cape as it is skinned to this rig, and only
## where the chain itself carries it: the root's joint is in the yoke, which the
## spine holds and the collar wraps round, so the line starts where the chain's
## cloth leaves the yoke. That cloth was conformed to the bare back, so a drape
## over armour moves only the yoke above it. Each vertex is carried at rest by
## its heaviest bone; the line wants only a depth.
##
## `section`, when given, receives the cape's cross-section at each joint,
## across the middle chain's rest x: [the chains' x offsets from the middle
## one (PackedFloat32Array, low to high); the sheet's half-width at each
## joint; how far its folds come in toward the body, SECTION_BINS from -x to +x
## for each joint in turn; and each chain's share of the cloth at each of those
## places, CHAIN_SIDES order]. The middle chain carries nearly the whole sheet,
## its side panels too, and cloth between chains is a blend of them, so each
## place is read against the blend of the chains' lines that carries it.
## contacts receives actual inner-fold positions and their per-link weights
## for the surface collision correction, including the hem below the last bone.
static func fabric_line(skeleton: Skeleton3D, cape: Array,
		section: Array = [], contacts: Array = [], rest_overrides: Dictionary = {}) -> Array:
	var chains: Array[PackedInt32Array] = []
	for side: String in CHAIN_SIDES:
		var chain := PackedInt32Array()
		for link: int in range(CHAIN_LINKS):
			chain.append(skeleton.find_bone("cape_%s_%02d" % [side, link + 1]))
		chains.append(chain)
	var cloth := PackedVector3Array()
	var contact_grid: Dictionary = {}
	var carriers := PackedInt32Array()
	# Each vertex's weight on each chain, in CHAIN_SIDES order.
	var shares := PackedFloat32Array()
	for node_value: Variant in cape:
		var node := node_value as MeshInstance3D
		if node == null or node.mesh == null or node.skin == null:
			continue
		var carry: Array[Transform3D] = []
		var carrier := PackedInt32Array()
		for bind: int in range(node.skin.get_bind_count()):
			var bone: int = skeleton.find_bone(node.skin.get_bind_name(bind))
			if bone < 0:
				bone = node.skin.get_bind_bone(bind)
			if bone >= skeleton.get_bone_count():
				bone = -1
			carrier.append(bone)
			carry.append(Transform3D.IDENTITY if bone < 0
				else (rest_overrides.get(bone, skeleton.get_bone_global_rest(bone)) as Transform3D) * node.skin.get_bind_pose(bind))
		for surface: int in range(node.mesh.get_surface_count()):
			var arrays: Array = node.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			if arrays[Mesh.ARRAY_BONES] == null or arrays[Mesh.ARRAY_WEIGHTS] == null:
				continue
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			if vertices.is_empty() or bones.size() < vertices.size():
				continue
			var per: int = bones.size() / vertices.size()
			for index: int in range(vertices.size()):
				var heaviest: int = -1
				var most := 0.0
				for slot: int in range(per):
					var weight: float = weights[index * per + slot]
					if weight > most:
						most = weight
						heaviest = bones[index * per + slot]
				if heaviest < 0 or heaviest >= carry.size() or carrier[heaviest] < 0:
					continue
				_record_surface_sample(contact_grid, chains, carrier, carry, vertices[index],
					bones, weights, index, per)
				cloth.append(carry[heaviest] * vertices[index])
				carriers.append(carrier[heaviest])
				for chain: PackedInt32Array in chains:
					var share := 0.0
					for slot: int in range(per):
						var bone: int = bones[index * per + slot]
						if bone >= 0 and bone < carrier.size() and chain.has(carrier[bone]):
							share += weights[index * per + slot]
					shares.append(share)
	var contact_positions: Dictionary = {}
	for sample: Dictionary in contact_grid.values():
		var key: Vector3 = (sample.position as Vector3).snapped(Vector3.ONE * 0.000001)
		if not contact_positions.has(key):
			contacts.append(sample)
			contact_positions[key] = true
	var out: Array = []
	var roots: Array = []
	var heights: Array = []
	var carried_by := PackedInt32Array()
	for side: String in CHAIN_SIDES:
		var chain := PackedInt32Array()
		for link: int in range(CHAIN_LINKS):
			var bone: int = skeleton.find_bone("cape_%s_%02d" % [side, link + 1])
			if bone < 0:
				return []
			chain.append(bone)
		var root: Vector3 = skeleton.get_bone_global_rest(chain[0]).origin
		# The solver's link lengths: each child's offset, the last repeated.
		var lengths := PackedFloat32Array()
		for link: int in range(1, CHAIN_LINKS):
			lengths.append(skeleton.get_bone_rest(chain[link]).origin.length())
		lengths.append(lengths[lengths.size() - 1])
		var band := PackedVector3Array()
		var lowest := INF
		var highest := -INF
		for index: int in range(cloth.size()):
			var point: Vector3 = cloth[index]
			if absf(point.x - root.x) < LINE_BAND and chain.has(carriers[index]):
				band.append(point)
				lowest = minf(lowest, point.y)
				highest = maxf(highest, point.y)
		if band.is_empty():
			return []
		var offsets := PackedVector3Array()
		var height: float = root.y
		var levels := PackedFloat32Array()
		for joint: int in range(CHAIN_LINKS + 1):
			var at: float = clampf(height, lowest + LINE_HEM, highest - LINE_SLICE)
			levels.append(at)
			var depths := PackedFloat32Array()
			for point: Vector3 in band:
				if absf(point.y - at) < LINE_SLICE:
					depths.append(point.z)
			if depths.is_empty():
				offsets.append(Vector3.ZERO if offsets.is_empty()
					else offsets[offsets.size() - 1])
			else:
				# The middle half's mean: a pleat splits a thin strip into an
				# inner and an outer crest, and a median jumps between them.
				depths.sort()
				var first: int = depths.size() / 4
				var last: int = maxi(first + 1, depths.size() - depths.size() / 4)
				var total := 0.0
				for index: int in range(first, last):
					total += depths[index]
				offsets.append(Vector3(0.0, 0.0,
					total / float(last - first) - root.z))
			if joint < CHAIN_LINKS:
				height -= lengths[joint]
		out.append(offsets)
		roots.append(root)
		heights.append(levels)
		carried_by.append_array(chain)
	section.append_array(_cross_section(cloth, carriers, shares, carried_by, roots,
		heights, out))
	return out


## Actual free-surface samples for collision, retaining the link weights that
## the renderer uses. The innermost fold in each 7.5 by 5 cm patch is conservative
## without walking every cape vertex per frame. This also covers the hem,
## which extends below the last driven bone and cannot be inferred from the
## simulated joints alone.
static func _record_surface_sample(grid: Dictionary, chains: Array[PackedInt32Array],
		carrier: PackedInt32Array, carry: Array[Transform3D], vertex: Vector3,
		bones: PackedInt32Array, weights: PackedFloat32Array, index: int, per: int) -> void:
	var position := Vector3.ZERO
	var shares := PackedFloat32Array()
	shares.resize(CHAIN_SIDES.size() * CHAIN_LINKS)
	shares.fill(0.0)
	var total := 0.0
	for slot: int in per:
		var at := index * per + slot
		var bone := bones[at]
		if weights[at] <= 0.0 or bone < 0 or bone >= carrier.size():
			continue
		position += (carry[bone] * vertex) * weights[at]
		for chain: int in chains.size():
			var link := chains[chain].find(carrier[bone])
			if link >= 0:
				shares[chain * CHAIN_LINKS + link] += weights[at]
				total += weights[at]
	if total < 0.999:
		return
	var cell := Vector2i(floori(position.x / 0.075), floori(position.y / 0.05))
	var joint := 0.0
	for chain: int in CHAIN_SIDES.size():
		for link: int in CHAIN_LINKS:
			joint += shares[chain * CHAIN_LINKS + link] * float(link)
	var entry := {"position": position, "weights": shares, "joint": joint}
	var front := Vector3i(cell.x, cell.y, 0)
	var upper := Vector3i(cell.x, cell.y, 1)
	var lower := Vector3i(cell.x, cell.y, 2)
	if not grid.has(front) or position.z > (grid[front].position as Vector3).z:
		grid[front] = entry
	# Link weights can vary across a folded patch. Preserve both ends of
	# that blend too; a front crest alone can miss the back leg or a tail.
	if not grid.has(upper) or joint < float(grid[upper].joint):
		grid[upper] = entry
	if not grid.has(lower) or joint > float(grid[lower].joint):
		grid[lower] = entry



## The cape's cross-section at each joint (see `fabric_line`), read at the
## middle chain's joint heights: per place across, each chain's share of the
## cloth there and how far its folds come in past the blend of the chains'
## lines they make.
static func _cross_section(cloth: PackedVector3Array, carriers: PackedInt32Array,
		shares: PackedFloat32Array, carried_by: PackedInt32Array, roots: Array,
		heights: Array, lines: Array) -> Array:
	var count: int = roots.size()
	var middle: Vector3 = roots[1]
	var knots := PackedFloat32Array()
	for root: Vector3 in roots:
		knots.append(root.x - middle.x)
	var halves := PackedFloat32Array()
	var folds := PackedFloat32Array()
	var blend := PackedFloat32Array()
	var levels: PackedFloat32Array = heights[1]
	for joint: int in range(CHAIN_LINKS + 1):
		var at: float = levels[joint]
		var depths := PackedFloat32Array()
		for chain: int in range(count):
			depths.append((roots[chain] as Vector3).z + (lines[chain] as PackedVector3Array)[joint].z)
		var slice := PackedInt32Array()
		var reach := PackedFloat32Array()
		for index: int in range(cloth.size()):
			if carried_by.has(carriers[index]) and absf(cloth[index].y - at) < LINE_SLICE:
				slice.append(index)
				reach.append(absf(cloth[index].x - middle.x))
		reach.sort()
		var half: float = 0.0 if reach.is_empty() else reach[mini(int(
			LINE_WIDTH * float(reach.size())), reach.size() - 1)]
		halves.append(half)
		# Toward the body is toward the material line.
		var toward: float = signf(middle.z - depths[1])
		for bin: int in range(SECTION_BINS):
			var across: float = (2.0 * float(bin) / float(SECTION_BINS - 1) - 1.0) * half
			var weight := PackedFloat32Array()
			weight.resize(count)
			weight.fill(0.0)
			var inner := PackedFloat32Array()
			for index: int in slice:
				if absf(cloth[index].x - middle.x - across) >= FOLD_WINDOW:
					continue
				inner.append(cloth[index].z)
				for chain: int in range(count):
					weight[chain] += shares[index * count + chain]
			var total := 0.0
			for chain: int in range(count):
				total += weight[chain]
			if total <= 1e-6:
				# Nothing measured here: straight between the nearest chains.
				weight = _knot_weights(knots, across)
				total = 1.0
			var line := 0.0
			for chain: int in range(count):
				weight[chain] /= total
				line += weight[chain] * depths[chain]
			blend.append_array(weight)
			if inner.is_empty():
				folds.append(0.0)
				continue
			inner.sort()
			var crest: float = inner[mini(int(LINE_FOLD * float(inner.size())),
				inner.size() - 1)] if toward >= 0.0 else inner[mini(int(
				(1.0 - LINE_FOLD) * float(inner.size())), inner.size() - 1)]
			folds.append(maxf(0.0, (crest - line) * toward))
	return [knots, halves, folds, blend]


## Each chain's share `across` the cape when nothing was measured there:
## straight between neighbouring chains, all to an outer one past it.
static func _knot_weights(knots: PackedFloat32Array, across: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(knots.size())
	out.fill(0.0)
	if across <= knots[0]:
		out[0] = 1.0
		return out
	for knot: int in range(1, knots.size()):
		if across <= knots[knot]:
			var t: float = (across - knots[knot - 1]) / maxf(knots[knot] - knots[knot - 1], 1e-5)
			out[knot - 1] = 1.0 - t
			out[knot] = t
			return out
	out[knots.size() - 1] = 1.0
	return out


## How far the legs reach behind a shin	return out


## How far the legs reach behind a shin, by sample along it (REACH_SAMPLES, knee
## to ankle) and bearing from the leg's back (SHIN_BEARINGS columns), in rest
## space: the body's calf and whatever is worn over it, held CLEARANCE off.
## Only that leg's half of the body counts: the other leg's back flap stood
## within 45 degrees of the first shin's back. Each cell carries its neighbours along
## and around the shin, as `axis_reach` does along its axis.
static func shin_reach(pieces: Array, from: Vector3, to: Vector3,
		floor_radius: float, below: float = 0.0) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(REACH_SAMPLES * SHIN_BEARINGS)
	out.fill(floor_radius)
	var axis: Vector3 = to - from
	var span: float = axis.length_squared()
	if span < 1e-9:
		return out
	var along: Vector3 = axis / sqrt(span)
	# The rig's back is -z in its rest space.
	var back := Vector3(0.0, 0.0, -1.0)
	back = (back - along * back.dot(along)).normalized()
	for piece_value: Variant in pieces:
		var mesh: Mesh = (piece_value as Dictionary).get("mesh") as Mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var vertices: PackedVector3Array = mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			for point: Vector3 in vertices:
				if absf(point.x) > TRUNK_HALF or point.x * from.x < 0.0:
					continue
				var travel: float = (point - from).dot(axis) / span
				if travel < below or travel > 1.0:
					continue
				var away: Vector3 = point - (from + axis * travel)
				var gap: float = away.length()
				if gap < 1e-5:
					continue
				var bearing: float = rad_to_deg(acos(clampf(away.dot(back) / gap, -1.0, 1.0)))
				var column: int = mini(int(bearing / SHIN_BEARING_STEP), SHIN_BEARINGS - 1)
				var at: int = int(round(travel * float(REACH_SAMPLES - 1))) * SHIN_BEARINGS + column
				out[at] = maxf(out[at], gap + LEG_CLEARANCE)
	var smeared := out.duplicate()
	for slot: int in range(REACH_SAMPLES):
		for column: int in range(SHIN_BEARINGS):
			var best: float = out[slot * SHIN_BEARINGS + column]
			for near_slot: int in [slot - 1, slot, slot + 1]:
				for near_column: int in [column - 1, column, column + 1]:
					if near_slot < 0 or near_slot >= REACH_SAMPLES or near_column < 0 							or near_column >= SHIN_BEARINGS:
						continue
					best = maxf(best, out[near_slot * SHIN_BEARINGS + near_column])
			smeared[slot * SHIN_BEARINGS + column] = best
	return smeared
