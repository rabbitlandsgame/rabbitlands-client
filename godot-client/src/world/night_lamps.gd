class_name NightLamps
extends Node3D
## Lights the lamps the streamed maps already place, at dusk and through the
## night.
##
## The Landfall isles carry about a hundred lantern posts, lamp buoys and two
## lighthouses, and not one of them gave light: the only lamp on all fifteen
## maps was the landing beacon, the one placement whose kit declares a light
## (publish_client.py lighting.markers). After sundown the town read as dark
## shapes under the moon.
##
## Nothing is republished for this. A pooled kit placement keeps its model's
## name in every chunk (`kit-lantern-post-1`), so each streamed cell is read
## as it arrives (ContinentChunkStream.cell_ready) and every lamp it holds is
## found by name. LAMPS says where in its model the flame sits and what
## colour it burns.
##
## Each lamp gets a halo: a soft additive billboard at the flame, drawn per
## cell as one MultiMesh, so a cell's lamps cost one draw however many it
## holds. The halo rides on the cell, so it streams and rebases with it. Real
## light is a small pool of omni lights (LIGHTS_BY_QUALITY), handed each tick
## to the lamps nearest the camera's focus and faded out towards the edge of
## their reach, so a light changing hands is never seen: a hundred lit lamps
## would be a hundred lights in the clustered pass for the ones in view. No
## light casts a shadow.
##
## How lit they are follows the server's clock (DayNightBinder.daylight) and,
## a little, the weather: lamps are lit in a dark storm too.

## Per kit model: where its flame is in the model's own frame (metres), the
## colour it burns, the light it throws (energy, range) and its halo's size.
## The anchors were measured on the published prototypes.
const LAMPS := {
	"kit-lantern-post-1": {"anchor": Vector3(-0.565, 1.62, 0.0),
		"colour": Color(1.0, 0.6, 0.26), "energy": 1.6, "range": 9.0, "halo": 1.1},
	"kit-lamp-buoy-1": {"anchor": Vector3(0.0, 0.56, 0.0),
		"colour": Color(1.0, 0.74, 0.40), "energy": 1.2, "range": 7.0, "halo": 0.9},
	"kit-sw-lighthouse-red": {"anchor": Vector3(0.0, 18.2, 0.0),
		"colour": Color(1.0, 0.36, 0.26), "energy": 3.0, "range": 16.0, "halo": 4.5},
	"kit-sw-lighthouse-green": {"anchor": Vector3(0.0, 16.6, 0.0),
		"colour": Color(0.42, 1.0, 0.52), "energy": 3.0, "range": 16.0, "halo": 4.5},
}
## Real lights by LookProfile.Quality (LOW, MEDIUM, HIGH). The halos are drawn
## at every quality.
const LIGHTS_BY_QUALITY: Array[int] = [4, 8, 12]
## How far from the camera's focus a lamp may hold a real light; the light
## fades out over the last third of it.
const LIGHT_REACH := 64.0
## How often the lights are handed out again, in seconds.
const REFRESH_SECONDS := 0.2
## The lamps are lit below this much daylight and fully lit below NIGHT_FULL.
const DUSK_LIGHT := 0.55
const NIGHT_FULL := 0.18
## How lit a full storm alone makes them, in daylight.
const STORM_LAMPS := 0.4

var _material: ShaderMaterial
var _quad: QuadMesh
## Lamps by cell key: [{node, kind}].
var _lamps: Dictionary = {}
## The halo MultiMesh nodes by cell key.
var _halos: Dictionary = {}
var _streams: Array[ContinentChunkStream] = []
var _lights: Array[OmniLight3D] = []
var _strength := -1.0
var _refresh_at := 0.0

func _ready() -> void:
	name = "NightLamps"

## How lit the lamps are at `minute` under `overcast` (Weather3D.overcast).
static func strength_at(minute: float, overcast: float) -> float:
	var light := DayNightBinder.daylight(minute)
	var night := 1.0 - smoothstep(NIGHT_FULL, DUSK_LIGHT, light)
	return clampf(maxf(night, overcast * STORM_LAMPS), 0.0, 1.0)

## The kind of lamp a node is (a LAMPS key), or "".
static func kind_of(node_name: String) -> String:
	# A glTF import keeps names unique across the whole file by appending a
	# number (GLTFDocument._gen_unique_name), so the second post in a cell is
	# `kit-lantern-post-12`: the model's name followed by digits only.
	for kind: String in LAMPS:
		if node_name.begins_with(kind) \
				and node_name.substr(kind.length()).lstrip("0123456789").is_empty():
			return kind
	return ""

## Where a lamp's flame is, in the world: its model's anchor through the
## placement's transform.
static func flame_of(lamp: Node3D, kind: String) -> Vector3:
	return lamp.global_transform * (LAMPS[kind].anchor as Vector3)

## Follows a streamed territory's cells: the active map's and each resident
## neighbour's, so a lamp across a border is lit too.
func watch(stream: ContinentChunkStream) -> void:
	if stream == null or _streams.has(stream):
		return
	_streams.append(stream)
	stream.cell_ready.connect(_on_cell_ready.bind(stream))
	stream.cell_retiring.connect(_on_cell_retiring.bind(stream))
	for identity: String in stream.cells:
		_on_cell_ready(identity, stream.cells[identity].root as Node3D, stream)

## How many lamps the resident cells hold, and how many have a light now.
func lamp_count() -> int:
	var total := 0
	for lamps: Array in _lamps.values():
		total += lamps.size()
	return total

func lit_count() -> int:
	var lit := 0
	for light: OmniLight3D in _lights:
		if light.visible:
			lit += 1
	return lit

## Every frame: lights the halos for the hour and, every REFRESH_SECONDS,
## hands the lights to the lamps nearest `focus`. `active` false (a map whose
## hour does not drive its light) puts every lamp out.
func update(focus: Vector3, minute: float, overcast: float, active := true) -> void:
	var strength := strength_at(minute, overcast) if active else 0.0
	if not is_equal_approx(strength, _strength):
		_strength = strength
		_material_for_halos().set_shader_parameter(&"strength", strength)
		for halo: Variant in _halos.values():
			if is_instance_valid(halo):
				(halo as Node3D).visible = strength > 0.001
	var now := Time.get_ticks_msec() / 1000.0
	if now < _refresh_at:
		return
	_refresh_at = now + REFRESH_SECONDS
	_prune()
	_hand_out_lights(focus, strength)

func _hand_out_lights(focus: Vector3, strength: float) -> void:
	var wanted: int = LIGHTS_BY_QUALITY[clampi(LookProfile.quality(), 0, LIGHTS_BY_QUALITY.size() - 1)]
	var nearest: Array = []
	if strength > 0.001:
		for lamps: Array in _lamps.values():
			for lamp: Dictionary in lamps:
				var node: Variant = lamp.node
				# Not `is_visible_in_tree`: a pooled prop is drawn by the batch
				# that replaced its node, which is left hidden. A cell going out
				# of residency says so (cell_retiring).
				if not is_instance_valid(node) or not (node as Node3D).is_inside_tree():
					continue
				var at := flame_of(node as Node3D, str(lamp.kind))
				var distance := at.distance_to(focus)
				if distance < LIGHT_REACH:
					nearest.append([distance, at, lamp.kind])
		nearest.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
	while _lights.size() < mini(wanted, nearest.size()):
		var light := OmniLight3D.new()
		light.name = "LampLight%d" % _lights.size()
		light.shadow_enabled = false
		light.light_specular = 0.3
		add_child(light)
		_lights.append(light)
	for index: int in _lights.size():
		var light := _lights[index]
		if index >= wanted or index >= nearest.size():
			light.visible = false
			continue
		var entry: Array = nearest[index]
		var lamp: Dictionary = LAMPS[entry[2]]
		var fade := 1.0 - smoothstep(LIGHT_REACH * 0.66, LIGHT_REACH, float(entry[0]))
		light.global_position = entry[1]
		light.light_color = lamp.colour
		light.omni_range = lamp.range
		light.light_energy = float(lamp.energy) * strength * fade
		light.visible = light.light_energy > 0.01

func _on_cell_ready(identity: String, imported: Node3D, stream: ContinentChunkStream) -> void:
	var key := _key(stream, identity)
	_drop(key)
	if not is_instance_valid(imported):
		return
	var found: Array = []
	var stack: Array[Node] = [imported]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		if node is Node3D:
			var kind := kind_of(String(node.name))
			if not kind.is_empty():
				found.append({"node": node, "kind": kind})
				continue
		stack.append_array(node.get_children())
	if found.is_empty():
		return
	_lamps[key] = found
	_halos[key] = _build_halos(imported, found)

func _on_cell_retiring(identity: String, _imported: Node3D, stream: ContinentChunkStream) -> void:
	_drop(_key(stream, identity))

## Lets go of territories that have been freed (a map left, a neighbour
## evicted); their cells, and the halos on them, went with them. A territory
## adopted across a border is the same node and is kept.
func _prune() -> void:
	var alive: Array[ContinentChunkStream] = []
	for stream: Variant in _streams:
		if is_instance_valid(stream):
			alive.append(stream as ContinentChunkStream)
	_streams = alive
	for key: String in _lamps.keys():
		var valid := false
		for lamp: Dictionary in _lamps[key]:
			if is_instance_valid(lamp.node):
				valid = true
				break
		if not valid:
			_drop(key)

func _drop(key: String) -> void:
	_lamps.erase(key)
	var halo: Variant = _halos.get(key)
	if is_instance_valid(halo):
		# Out of the cell at once, so a cell read again gets its halos back
		# under the same name.
		if (halo as Node).get_parent() != null:
			(halo as Node).get_parent().remove_child(halo as Node)
		(halo as Node).queue_free()
	_halos.erase(key)

static func _key(stream: ContinentChunkStream, identity: String) -> String:
	return "%d:%s" % [stream.get_instance_id(), identity]

## One MultiMesh of halos under the cell's root, in its frame, so it streams
## out and rebases with the cell.
func _build_halos(cell: Node3D, lamps: Array) -> MultiMeshInstance3D:
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_colors = true
	multimesh.mesh = _halo_quad()
	multimesh.instance_count = lamps.size()
	var into_cell := cell.global_transform.affine_inverse()
	for index: int in lamps.size():
		var lamp: Dictionary = lamps[index]
		var kind: Dictionary = LAMPS[lamp.kind]
		var at: Vector3 = into_cell * flame_of(lamp.node as Node3D, str(lamp.kind))
		multimesh.set_instance_transform(index, Transform3D(Basis.from_scale(
			Vector3.ONE * float(kind.halo)), at))
		multimesh.set_instance_color(index, kind.colour)
	var halos := MultiMeshInstance3D.new()
	halos.name = "LampHalos"
	halos.multimesh = multimesh
	halos.material_override = _material_for_halos()
	halos.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	halos.visible = _strength > 0.001
	cell.add_child(halos)
	return halos

func _material_for_halos() -> ShaderMaterial:
	if _material == null:
		_material = ShaderMaterial.new()
		_material.shader = preload("res://src/world/night_lamp_glow.gdshader")
		_material.set_shader_parameter(&"strength", maxf(_strength, 0.0))
	return _material

func _halo_quad() -> QuadMesh:
	if _quad == null:
		_quad = QuadMesh.new()
		_quad.size = Vector2.ONE
		# The shader turns the quad to the camera, so its box is a cube, or a
		# halo seen edge-on at the frame's border would be culled.
		_quad.custom_aabb = AABB(Vector3(-0.5, -0.5, -0.5), Vector3.ONE)
	return _quad
