class_name RLFaceExpression
extends Node
## The face's expression: every `ex_*` blend-shape weight on the RL head and
## its beard, and nothing else. Identity (`id_*`) belongs to RLHeadRig; this
## node refuses any other name, so neither can disturb the other.
##
## Runs the eyes on its own: a blink every two to six seconds, 0.12 s closing
## and 0.16 s opening, sometimes twice. Expressions fade in and out over the
## time asked for; a small preset table maps readable names (smile, frown,
## surprise...) onto whichever `ex_` shapes the head actually has, so a head
## with fewer shapes simply shows less. `set_talking` loops the jaw.
##
## Near actors are updated every frame, the rest every third or fourth frame,
## and actors beyond FAR_METRES not at all (eyes left open). An actor the
## animation gate pauses has its model's processing switched off, this node's
## with it. The stride is chosen once per update cycle (a far actor looks
## again every FAR_RECHECK_FRAMES), and a face with nothing to show - no
## expression, no blink under way, not talking - only counts down to its next
## blink: a crowd's idle faces cost a few microseconds a frame each. `advance` steps the face by hand, for deterministic renders.
## `hold_neutral` keeps the face neutral with the eyes open and no blink while
## a portrait (dialogue line, leaderboard card) is taken of it.

signal weights_changed

const NEAR_METRES := 12.0
const FAR_METRES := 40.0
const MID_STRIDE := 3
const QUARTER_STRIDE := 4
const FAR_RECHECK_FRAMES := 8
const BLINK_CLOSE := 0.12
const BLINK_OPEN := 0.16
const BLINK_GAP := Vector2(2.0, 6.0)
const DOUBLE_BLINK_CHANCE := 0.15
const DOUBLE_BLINK_PAUSE := 0.08
const BLINK_SHAPES := ["ex_blink_l", "ex_blink_r"]
## Readable expressions as `ex_` weights. Shapes a head lacks are skipped.
const PRESETS := {
	"neutral": {},
	"smile": {"ex_smile": 1.0, "ex_squint": 0.25, "ex_brow_up": 0.1},
	"grin": {"ex_grin": 1.0, "ex_smile": 0.3, "ex_squint": 0.35},
	"frown": {"ex_frown": 1.0, "ex_brow_down": 0.55},
	"angry": {"ex_brow_down": 1.0, "ex_frown": 0.45, "ex_sneer": 0.45, "ex_squint": 0.35},
	"surprise": {"ex_brow_up": 1.0, "ex_eyes_wide": 1.0, "ex_jaw_open": 0.45},
	"sad": {"ex_brow_sad": 1.0, "ex_frown": 0.6},
	"squint": {"ex_squint": 1.0},
	"pucker": {"ex_pucker": 1.0, "ex_lips_pucker": 1.0},
	"sneer": {"ex_sneer": 1.0, "ex_brow_down": 0.3},
}

var auto_blink := true
## Forces every-frame updates whatever the distance (the lab, the renders).
var always_update := false

var _targets: Array[MeshInstance3D] = []
var _available: PackedStringArray = PackedStringArray()
## The expression's own weights, fading towards `_goal` at `_rate` per second.
var _current: Dictionary = {}
var _goal: Dictionary = {}
var _rate: Dictionary = {}
## What was last written to the meshes, so unchanged weights cost nothing.
var _written: Dictionary = {}
var _blink_phase := -1.0
var _blink_pause := 0.0
var _blink_again := false
var _blink_wait := 3.0
var _talking := false
var _talk_time := 0.0
var _stride_count := 0
var _pending_delta := 0.0
var _random := RandomNumberGenerator.new()
var _look := Vector2.ZERO
var _held := false
var _held_auto_blink := true
## The stride chosen for the current update cycle, and the frames a far
## actor waits before it looks again.
var _cycle_stride := 1
var _far_wait := 0
## The actor (the CharacterBody3D above), found once.
var _actor_node: Node = null
var _actor_found := false


func _ready() -> void:
	_random.randomize()
	_blink_wait = _random.randf_range(BLINK_GAP.x, BLINK_GAP.y)


## The meshes to drive and the `ex_` shapes the head declares.
func configure(targets: Array[MeshInstance3D], available: PackedStringArray) -> void:
	_available = PackedStringArray()
	for shape: String in available:
		if shape.begins_with("ex_"):
			_available.append(shape)
	set_targets(targets)


## New meshes (a quality change, a beard): every current weight is written again.
func set_targets(targets: Array[MeshInstance3D]) -> void:
	_targets = targets.duplicate()
	_written.clear()
	_write()
	_write_look()


## The `ex_` shapes this head has: the declared ones that exist on a mesh.
func available_shapes() -> PackedStringArray:
	var found := PackedStringArray()
	for shape: String in _available:
		if has_shape(shape):
			found.append(shape)
	return found


func has_shape(shape: String) -> bool:
	for mesh_node: MeshInstance3D in _targets:
		if is_instance_valid(mesh_node) and RLHeadRig.shape_index(mesh_node, shape) >= 0:
			return true
	return false


## Fades into a preset (by name) or a single `ex_` shape at `amount`. Other
## held shapes fade out unless `additive`. A name that is neither is ignored.
func set_expression(expression_name: String, amount: float = 1.0, fade: float = 0.2,
		additive: bool = false) -> void:
	if _held:
		return
	var wanted := {}
	if PRESETS.has(expression_name):
		var preset: Dictionary = PRESETS[expression_name]
		for shape: String in preset:
			wanted[shape] = float(preset[shape]) * amount
	elif expression_name.begins_with("ex_"):
		wanted[expression_name] = amount
	else:
		return
	if not additive:
		for shape: Variant in _goal.keys():
			if not wanted.has(shape):
				_fade(str(shape), 0.0, fade)
	for shape: String in wanted:
		if has_shape(shape):
			_fade(shape, clampf(float(wanted[shape]), 0.0, 1.0), fade)


## Fades every held shape back to neutral.
func clear_expression(fade: float = 0.25) -> void:
	for shape: Variant in _goal.keys():
		_fade(str(shape), 0.0, fade)


## Makes the blink timing repeatable (the evidence renders).
func set_seed(value: int) -> void:
	_random.seed = value
	_blink_wait = _random.randf_range(BLINK_GAP.x, BLINK_GAP.y)


## Starts a blink now (if one is not already under way).
func blink() -> void:
	if _held:
		return
	if _blink_phase < 0.0 and _blink_pause <= 0.0:
		_blink_phase = 0.0
		_blink_again = _random.randf() < DOUBLE_BLINK_CHANCE


func set_auto_blink(enabled: bool) -> void:
	auto_blink = enabled


## Holds the face neutral - no expression, the jaw shut, the eyes open and
## looking ahead, no blinking - until released, when blinking resumes as it
## was. Expressions asked for while held are ignored.
func hold_neutral(held: bool) -> void:
	if held == _held:
		return
	_held = held
	if held:
		_held_auto_blink = auto_blink
		auto_blink = false
		_blink_phase = -1.0
		_blink_pause = 0.0
		_blink_again = false
		_talking = false
		_current.clear()
		_goal.clear()
		_rate.clear()
		_look = Vector2.ZERO
		_write()
		_write_look()
	else:
		auto_blink = _held_auto_blink
		_blink_wait = _random.randf_range(BLINK_GAP.x, BLINK_GAP.y)


func is_held_neutral() -> bool:
	return _held


func set_talking(enabled: bool) -> void:
	_talking = enabled and not _held
	_talk_time = 0.0
	if not enabled:
		_fade("ex_jaw_open", float(_goal.get("ex_jaw_open", 0.0)), 0.1)


func is_talking() -> bool:
	return _talking


## Turns both irises by a look angle in radians (x towards model +X, y up).
func set_look(look: Vector2) -> void:
	_look = look
	_write_look()


## The weights last written to the meshes, by shape.
func weights() -> Dictionary:
	return _written.duplicate()


## Steps blink, fades and talk by `delta` seconds and writes the result.
func advance(delta: float) -> void:
	var idle := _goal.is_empty() and _written.is_empty() and not _talking
	if idle and _blink_phase < 0.0 and _blink_pause <= 0.0:
		# Nothing shows: only the wait for the next blink runs. A blink started
		# here writes nothing until it has closed the eyes a little.
		if auto_blink:
			_blink_wait -= delta
			if _blink_wait <= 0.0:
				blink()
		return
	for shape: Variant in _goal.keys():
		var now := float(_current.get(shape, 0.0))
		var goal := float(_goal[shape])
		var step := float(_rate.get(shape, 1000.0)) * delta
		now = goal if absf(goal - now) <= step else now + signf(goal - now) * step
		_current[shape] = now
		if is_zero_approx(goal) and is_zero_approx(now):
			_current.erase(shape)
			_goal.erase(shape)
			_rate.erase(shape)
	if _blink_pause > 0.0:
		# Between the two blinks of a double blink.
		_blink_pause -= delta
		if _blink_pause <= 0.0:
			_blink_phase = 0.0
	elif _blink_phase >= 0.0:
		_blink_phase += delta
		if _blink_phase >= BLINK_CLOSE + BLINK_OPEN:
			_blink_phase = -1.0
			if _blink_again:
				_blink_again = false
				_blink_pause = DOUBLE_BLINK_PAUSE
			else:
				_blink_wait = _random.randf_range(BLINK_GAP.x, BLINK_GAP.y)
	elif auto_blink:
		_blink_wait -= delta
		if _blink_wait <= 0.0:
			blink()
	if _talking:
		_talk_time += delta
	_write()


func blink_amount() -> float:
	if _blink_phase < 0.0:
		return 0.0
	if _blink_phase < BLINK_CLOSE:
		return smoothstep(0.0, 1.0, _blink_phase / BLINK_CLOSE)
	return 1.0 - smoothstep(0.0, 1.0, (_blink_phase - BLINK_CLOSE) / BLINK_OPEN)


func _process(delta: float) -> void:
	if _held:
		return
	if _far_wait > 0:
		_far_wait -= 1
		return
	if always_update:
		_cycle_stride = 1
	elif _stride_count == 0:
		_cycle_stride = _stride()
	var stride := _cycle_stride
	if stride <= 0:
		_far_wait = FAR_RECHECK_FRAMES - 1
		if _blink_phase >= 0.0 or _blink_pause > 0.0:
			_blink_phase = -1.0
			_blink_pause = 0.0
			_write()
		return
	_pending_delta += delta
	_stride_count += 1
	if _stride_count < stride:
		return
	_stride_count = 0
	advance(_pending_delta)
	_pending_delta = 0.0


## How many frames apart to update: 1 near, MID_STRIDE or the animation
## gate's quarter rate further out, 0 (not at all) beyond FAR_METRES.
func _stride() -> int:
	var camera := get_viewport().get_camera_3d() if is_inside_tree() else null
	var body := get_parent() as Node3D
	if camera == null or body == null:
		return 1
	var distance := camera.global_position.distance_to(body.global_position)
	if distance > FAR_METRES:
		return 0
	var stride := 1 if distance <= NEAR_METRES else MID_STRIDE
	var actor := _actor()
	if actor != null and actor.has_method("animation_tier"):
		if int(actor.call("animation_tier")) == AnimationGate.Tier.QUARTER:
			stride = maxi(stride, QUARTER_STRIDE)
	return stride


func _actor() -> Node:
	if not _actor_found or (_actor_node != null and not is_instance_valid(_actor_node)):
		_actor_found = true
		var walker := get_parent()
		while walker != null and walker is not CharacterBody3D:
			walker = walker.get_parent()
		_actor_node = walker
	return _actor_node


func _exit_tree() -> void:
	_actor_found = false
	_actor_node = null


func _fade(shape: String, goal: float, fade: float) -> void:
	if not shape.begins_with("ex_"):
		return
	var now := float(_current.get(shape, 0.0))
	_goal[shape] = goal
	_rate[shape] = absf(goal - now) / maxf(fade, 0.001) if fade > 0.0 else 1000.0
	if fade <= 0.0:
		_current[shape] = goal


func _write() -> void:
	var wanted := _current.duplicate()
	var closing := blink_amount()
	for shape: String in BLINK_SHAPES:
		wanted[shape] = maxf(float(wanted.get(shape, 0.0)), closing)
	if _talking:
		# Syllables: two incommensurate rates, so the jaw never settles into a
		# visible loop; the base stays open a little while speaking.
		var syllable := 0.5 + 0.5 * sin(_talk_time * 23.0) * sin(_talk_time * 7.3 + 1.1)
		wanted["ex_jaw_open"] = maxf(float(wanted.get("ex_jaw_open", 0.0)), 0.08 + 0.32 * syllable)
	for shape: Variant in _written.keys():
		if not wanted.has(shape):
			wanted[shape] = 0.0
	var changed := false
	for shape: Variant in wanted:
		var value := float(wanted[shape])
		# Meshes start at 0 and `_written` holds every non-zero weight, so an
		# unchanged weight - the open eyes most of all - is never written.
		if is_equal_approx(float(_written.get(shape, 0.0)), value):
			continue
		for mesh_node: MeshInstance3D in _targets:
			if not is_instance_valid(mesh_node):
				continue
			var index := RLHeadRig.shape_index(mesh_node, str(shape))
			if index >= 0:
				mesh_node.set_blend_shape_value(index, value)
		changed = true
		if is_zero_approx(value):
			_written.erase(shape)
		else:
			_written[shape] = value
	if changed:
		weights_changed.emit()


func _write_look() -> void:
	if RLHeadLibrary.material_values():
		# The look is a material value there (per-face eye material).
		var rig := get_parent() as RLHeadRig
		if rig != null:
			rig.set_eye_look(_look)
		return
	for mesh_node: MeshInstance3D in _targets:
		if is_instance_valid(mesh_node) and mesh_node.name.begins_with("RLHead"):
			mesh_node.set_instance_shader_parameter("eye_look", _look)
