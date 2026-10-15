extends SceneTree
## Actors that stand on more than one tile.
##
## The client does no collision of its own - the server reserves the ground
## and this only has to draw the actor on it. Which makes one thing the whole
## point: the tile an actor reports is the anchor of its box, and for an
## even-sized box the anchor is not the middle. Getting that wrong puts a
## two-by-two creature half a tile up and left of the ground it holds, which
## reads as the model being subtly misaligned rather than as a bug in the
## arithmetic below.

const P := preload("res://src/network/protocol.gd")

var _failures := 0

func _init() -> void:
	_decoding()
	_centring()
	_selection()
	_ground_marker()
	_scale_decoding()
	_scale_applied()
	print("actor footprints: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

# --- the packet -------------------------------------------------------------

func _footprint_payload(rows: Array) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.append(rows.size() & 0xFF)
	payload.append((rows.size() >> 8) & 0xFF)
	for row: Variant in rows:
		var entry: Array = row as Array
		payload.append(int(entry[0]) & 0xFF)
		payload.append((int(entry[0]) >> 8) & 0xFF)
		payload.append(int(entry[1]))
		payload.append(int(entry[2]))
	return payload

func _decoding() -> void:
	var decoded: Dictionary = P.decode_actor_footprints(
		_footprint_payload([[400, 2, 2], [512, 3, 3], [900, 4, 2]]))
	_expect(decoded.get("type") == "actor_footprints",
		"a footprint table decodes")
	var sizes: Dictionary = decoded.get("footprints", {}) as Dictionary
	_expect(sizes.size() == 3, "every listed type survives the decode")
	_expect(sizes.get(400) == Vector2i(2, 2), "a square footprint decodes")
	_expect(sizes.get(900) == Vector2i(4, 2),
		"a rectangle keeps its two axes the right way round")
	_expect(int((sizes.get(512) as Vector2i).x) == 3, "an actor type above 255 decodes")

	# An empty table is a legitimate answer: it means this profile authors no
	# creature larger than one tile.
	var empty: Dictionary = P.decode_actor_footprints(_footprint_payload([]))
	_expect(empty.get("type") == "actor_footprints"
		and (empty.get("footprints") as Dictionary).is_empty(),
		"an empty table is stated rather than refused")

	var truncated := _footprint_payload([[400, 2, 2]])
	truncated.resize(truncated.size() - 1)
	_expect(P.decode_actor_footprints(truncated).get("type") == "invalid",
		"a truncated table is refused rather than half read")
	_expect(P.decode_actor_footprints(PackedByteArray()).get("type") == "invalid",
		"an empty payload is refused")
	var zero := _footprint_payload([[400, 0, 2]])
	_expect(P.decode_actor_footprints(zero).get("type") == "invalid",
		"a zero-width footprint is refused")

	_expect(P.ServerMessage.ELORIA_ACTOR_FOOTPRINTS == 246,
		"the packet keeps the number the server sends it on")
	_expect(P.CLIENT_CAPABILITIES.has("actor_footprints_v1"),
		"the capability is advertised, or the server never sends the table")

# --- where the model goes ---------------------------------------------------

func _centring() -> void:
	# One metre per tile, no offset: server (x, y) maps to Godot (x, -y), so a
	# tile centre lands on the half.
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})

	var single: Vector3 = adapter.footprint_center(10, 10, Vector2i.ONE)
	_expect(single.is_equal_approx(adapter.tile_center(10, 10)),
		"a single tile is drawn exactly where it always was")

	# 3x3 spans 9..11 on both axes, whose middle is the anchor's own centre.
	var odd: Vector3 = adapter.footprint_center(10, 10, Vector2i(3, 3))
	_expect(odd.is_equal_approx(adapter.tile_center(10, 10)),
		"an odd footprint is centred on its anchor already")

	# 2x2 spans 10..11, whose middle is the corner between them - half a tile
	# further on each axis than the anchor's centre.
	var even: Vector3 = adapter.footprint_center(10, 10, Vector2i(2, 2))
	var anchor: Vector3 = adapter.tile_center(10, 10)
	_expect(is_equal_approx(even.x - anchor.x, 0.5),
		"an even footprint shifts half a tile east")
	_expect(is_equal_approx(even.z - anchor.z, -0.5),
		"an even footprint shifts half a tile north, in Godot's -Z")

	var rectangle: Vector3 = adapter.footprint_center(10, 10, Vector2i(4, 3))
	_expect(is_equal_approx(rectangle.x - anchor.x, 0.5)
		and is_equal_approx(rectangle.z - anchor.z, 0.0),
		"a rectangle shifts only on the axis whose extent is even")

	# The centre of the box the server reserved, derived independently from
	# the same bounds rule the server uses, for every size it can send.
	for width: int in range(1, 11):
		for depth: int in range(1, 11):
			var back_x: int = (width - 1) / 2
			var back_y: int = (depth - 1) / 2
			var min_x: int = 20 - back_x
			var max_x: int = 20 + width / 2
			var min_y: int = 30 - back_y
			var max_y: int = 30 + depth / 2
			var expected: Vector3 = adapter.server_to_godot(
				(float(min_x) + float(max_x) + 1.0) * 0.5,
				(float(min_y) + float(max_y) + 1.0) * 0.5)
			var actual: Vector3 = adapter.footprint_center(
				20, 30, Vector2i(width, depth))
			if not actual.is_equal_approx(expected):
				_expect(false, "%dx%d is centred on its reserved box" % [width, depth])
				return
	_expect(true, "every footprint from 1x1 to 10x10 is centred on its box")

# --- the click target -------------------------------------------------------

func _selection() -> void:
	var actor := ReplicatedActor3D.new()
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	root.add_child(actor)
	actor.configure({"actor_id": 1, "x": 10, "y": 10, "rotation": 0,
		"actor_type": 400, "kind": 1, "name": "Giant", "health": 10,
		"max_health": 10, "footprint": Vector2i(3, 3)}, adapter, {}, {})
	var shape: CollisionShape3D = actor.get_node_or_null(
		"SelectionCollision") as CollisionShape3D
	_expect(shape != null, "the actor has a click target")
	if shape != null:
		var capsule: CapsuleShape3D = shape.shape as CapsuleShape3D
		_expect(is_equal_approx(capsule.radius,
			ReplicatedActor3D.SELECTION_RADIUS * 3.0),
			"a three-tile creature is clickable across its body")

	# The table is a login packet and can land after an actor is built, so an
	# actor must take a corrected size rather than keep the one it started at.
	actor.set_footprint(Vector2i(1, 1))
	if shape != null:
		_expect(is_equal_approx((shape.shape as CapsuleShape3D).radius,
			ReplicatedActor3D.SELECTION_RADIUS),
			"a later correction resizes the click target")
	actor.queue_free()


# --- how large the model is drawn -------------------------------------------
#
# A creature's scale rides after its name's terminator and only when it is not
# life size, so where it sits depends on how long the name was. A player's is
# in a fixed trailer and always written. Both were previously ignored - the
# plain one entirely, the player's read under the name "attached actor id",
# which is what it never was.

## A scale is held to half a step of the encoding, which is a sixtieth of
## a percent - finer than anything will notice and coarser than
## `is_equal_approx`, which is why comparisons below use this instead.
## Powers of two are exact and are checked with equality.
const SCALE_TOLERANCE := 0.0005

func _scale_near(actual: float, expected: float) -> bool:
	return absf(actual - expected) <= expected * SCALE_TOLERANCE

## The server's encoder, mirrored so the fixtures below are built the way
## the wire really carries a scale rather than by copying constants out
## of the decoder they are meant to check.
func _scale_word(scale: float) -> int:
	return int(round(EloriaProtocol.ACTOR_SCALE_ZERO
		+ log(scale) / log(2.0) * EloriaProtocol.ACTOR_SCALE_STEPS_PER_OCTAVE))

func _u16(value: int) -> PackedByteArray:
	return PackedByteArray([value & 0xFF, (value >> 8) & 0xFF])

## ADD_NEW_ACTOR: the creature layout, name at 17, optional scale after it.
func _plain_actor(name: String, scale_word: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.append_array(_u16(42))       # actor id
	payload.append_array(_u16(10))       # x
	payload.append_array(_u16(20))       # y
	payload.append_array(_u16(0))        # reserved
	payload.append_array(_u16(0))        # rotation
	payload.append(40)                   # actor type
	payload.append(0)                    # frame
	payload.append_array(_u16(30))       # max health
	payload.append_array(_u16(30))       # health
	payload.append(3)                    # kind
	payload.append_array(name.to_utf8_buffer())
	payload.append(0)
	if scale_word > 0:
		payload.append_array(_u16(scale_word))
	return payload

func _scale_decoding() -> void:
	var life_size: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ACTOR, _plain_actor("Rat", 0))
	_expect(life_size.get("type") == "actor_spawn",
		"a creature with no scale word still decodes")
	_expect(float(life_size.get("scale", -1.0)) == 1.0,
		"an actor with no scale word is life size, not zero")

	var scaled: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ACTOR,
		_plain_actor("Rat", _scale_word(1.5)))
	_expect(_scale_near(float(scaled.get("scale", 0.0)), 1.5),
		"a creature's scale decodes from after its name")

	# The offset depends on the name's length, which is the part that would
	# break if the trailer were read from a fixed position.
	var long_name: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ACTOR,
		_plain_actor("Ancient Sunscale Basilisk", _scale_word(2.5)))
	_expect(_scale_near(float(long_name.get("scale", 0.0)), 2.5),
		"a long-named creature's scale is found after its own terminator")
	_expect(str(long_name.get("name", "")) == "Ancient Sunscale Basilisk",
		"and the name is still read whole")

	_expect(EloriaProtocol.ACTOR_SCALE_ZERO == 32768.0
		and _scale_word(1.0) == 32768,
		"life size is the midpoint the server encodes it as")

	# The range the profile allows, both ends and a power of two between.
	# Exactness at powers of two is the property the logarithmic field was
	# chosen for - a linear one could not even reach 128x in sixteen bits.
	for scale: float in [1.0 / 128.0, 0.25, 1.0, 8.0, 128.0]:
		var word: int = _scale_word(scale)
		_expect(word >= 0 and word <= 0xFFFF,
			"scale %f fits the 16-bit field" % scale)
		_expect(EloriaProtocol.decode_actor_scale(word) == scale,
			"scale %f is a power of two and survives exactly" % scale)
	var extreme: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ACTOR,
		_plain_actor("World Serpent", _scale_word(128.0)))
	_expect(float(extreme.get("scale", 0.0)) == 128.0,
		"a hundred and twenty-eight times life size decodes from the wire")
	var tiny: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ACTOR,
		_plain_actor("Mote", _scale_word(1.0 / 128.0)))
	_expect(float(tiny.get("scale", 0.0)) == 1.0 / 128.0,
		"and a hundred and twenty-eighth of it does too")

	# The player packet: a fixed trailer of scale, attachment sentinel, eyes,
	# neck. The first two bytes used to be read as an attached actor id.
	var enhanced := PackedByteArray()
	enhanced.append_array(_u16(7))
	enhanced.append_array(_u16(5))
	enhanced.append_array(_u16(6))
	enhanced.append_array(_u16(0))
	enhanced.append_array(_u16(0))
	enhanced.append(1)                   # actor type
	enhanced.append(0)
	for _look: int in range(10):
		enhanced.append(1)
	enhanced.append(0)                   # frame
	enhanced.append_array(_u16(50))      # max health
	enhanced.append_array(_u16(50))      # health
	enhanced.append(0)                   # kind
	enhanced.append_array("Kellan".to_utf8_buffer())
	enhanced.append(0)
	enhanced.append_array(_u16(_scale_word(1.0)))
	enhanced.append_array(PackedByteArray([255, 4, 0]))
	var player: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ENHANCED_ACTOR, enhanced)
	_expect(player.get("type") == "actor_spawn", "the player packet decodes")
	_expect(float(player.get("scale", 0.0)) == 1.0,
		"the player's trailer is read as a scale, not an actor id")
	_expect(int(player.get("attachment_type", -1)) == 255,
		"the no-attachment sentinel is where it belongs")
	_expect(int((player.get("appearance", {}) as Dictionary).get("eyes", -1)) == 4,
		"and the eyes after it are still read correctly")

func _scale_applied() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	# No model config, so this takes the missing-model fallback - which is the
	# path that would silently skip the scale if only the import adapter set it.
	actor.configure({"actor_id": 1, "x": 0, "y": 0, "rotation": 0,
		"actor_type": 40, "kind": 3, "name": "Dire Giant", "health": 10,
		"max_health": 10, "scale": 2.0}, adapter, {}, {})
	_expect(is_equal_approx(actor.server_scale, 2.0),
		"the actor takes the scale its packet carried")
	var fallback: Node3D = actor.get_node_or_null("MissingModelFallback") as Node3D
	if _expect(fallback != null, "the fallback stand-in was built"):
		_expect(is_equal_approx(fallback.scale.x, 2.0),
			"a stand-in for a giant is drawn giant")
	var plate: Node3D = actor.get_node_or_null("Nameplate") as Node3D
	if _expect(plate != null, "the actor has a nameplate"):
		_expect(is_equal_approx(plate.position.y,
			ReplicatedActor3D.NAMEPLATE_HEIGHT * 2.0),
			"the nameplate is lifted clear of the larger model")

	# Scale can change without a respawn - an ordinary creature promoted to an
	# invasion boss is redrawn larger in place.
	actor.set_server_scale(1.0)
	_expect(is_equal_approx(actor.server_scale, 1.0)
		and is_equal_approx((actor.get_node("MissingModelFallback") as Node3D).scale.x, 1.0)
		and is_equal_approx((actor.get_node("Nameplate") as Node3D).position.y,
			ReplicatedActor3D.NAMEPLATE_HEIGHT),
		"a later scale change is applied to model and nameplate together")
	actor.queue_free()


# --- the ground marker ------------------------------------------------------
#
# It used to be a torus scaled by the widest side of the footprint, which for
# anything but a single tile said the wrong thing: a circle cannot show which
# way a rectangle lies, and it either overhangs the ground the creature holds
# or sits inside it. It is now the box itself.

## The marker's extent on each axis, read back off the mesh it was built from.
func _outline_size(width_m: float, depth_m: float) -> Vector2:
	var mesh: ArrayMesh = ReplicatedActor3D.footprint_outline(width_m, depth_m)
	var box: AABB = mesh.get_aabb()
	return Vector2(box.size.x, box.size.z)

func _ground_marker() -> void:
	var single: Vector2 = _outline_size(1.0, 1.0)
	_expect(single.x < 1.0 and single.y < 1.0,
		"a single tile's marker sits inside its tile rather than covering it")

	# The claim the whole change is about: three tiles of creature, three tiles
	# of marker.
	var three: Vector2 = _outline_size(3.0, 3.0)
	_expect(absf(three.x - three.y) < 0.001, "a square footprint is marked square")
	_expect(three.x > single.x * 2.5,
		"a three-tile creature's marker is about three times a one-tile one")

	# A rectangle is marked as a rectangle, the right way round. A circle could
	# never have shown this.
	var wide: Vector2 = _outline_size(4.0, 2.0)
	_expect(wide.x > wide.y, "a marker wider than it is deep is drawn that way")
	_expect(absf(wide.x - wide.y - 2.0) < 0.01,
		"and by the two tiles that separate its sides")
	var deep: Vector2 = _outline_size(2.0, 4.0)
	_expect(is_equal_approx(deep.x, wide.y) and is_equal_approx(deep.y, wide.x),
		"the two axes are not transposed")

	# It is an outline: a hollow frame, not a filled slab. Each side is cut
	# into pieces short enough for GroundDrape to lay over the ground without
	# the straight line between two draped corners diving through the hill in
	# between, so the count is four sides of that many quads.
	var mesh: ArrayMesh = ReplicatedActor3D.footprint_outline(4.0, 4.0)
	var arrays: Array = mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var pieces: int = ceili((4.0 - 2.0 * ReplicatedActor3D.RING_INSET)
		/ ReplicatedActor3D.RING_SEGMENT_METRES)
	_expect(vertices.size() == 4 * pieces * 6,
		"four sides of %d quads: %d vertices" % [pieces, vertices.size()])
	var interior := 0
	for point: Vector3 in vertices:
		if absf(point.x) < 1.5 and absf(point.z) < 1.5:
			interior += 1
	_expect(interior == 0, "the middle of the box is left open")

	# Every footprint the server can send builds a mesh rather than degenerating.
	for width: int in range(1, 11):
		for depth: int in range(1, 11):
			var size: Vector2 = _outline_size(float(width), float(depth))
			if size.x <= 0.0 or size.y <= 0.0:
				_expect(false, "%dx%d built an empty marker" % [width, depth])
				return
	_expect(true, "every footprint from 1x1 to 10x10 builds a marker")

	# A footprint does not rotate with the creature standing in it, so the
	# marker gives back the yaw it inherits as a child of the actor.
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.configure({"actor_id": 2, "x": 4, "y": 4, "rotation": 0,
		"actor_type": 40, "kind": 3, "name": "Bear", "health": 10,
		"max_health": 10, "footprint": Vector2i(2, 2)}, adapter, {}, {})
	var ring: MeshInstance3D = actor.get_node_or_null("SelectionRing") as MeshInstance3D
	if _expect(ring != null, "the actor has a ground marker"):
		var marked: AABB = (ring.mesh as ArrayMesh).get_aabb()
		_expect(marked.size.x > 1.5 and marked.size.z > 1.5,
			"a two-tile creature is marked across two tiles, not one")
		actor.set_selected(true)
		actor.rotation.y = PI / 2.0
		actor.call("_level_selection_ring")
		_expect(is_equal_approx(ring.rotation.y, -PI / 2.0),
			"the marker stays square to the world while the actor turns")
		# And it follows the actor back, rather than sticking at one correction.
		actor.rotation.y = 0.0
		actor.call("_level_selection_ring")
		_expect(is_equal_approx(ring.rotation.y, 0.0),
			"the correction tracks the actor rather than latching")
	actor.queue_free()

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
