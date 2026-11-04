extends RefCounted
## How many of a map's marker lights (LightMarkerBinder) burn at once: the
## nearest N to the camera's focus, N by graphics quality (LIGHTS_BY_QUALITY:
## LOW 6, MEDIUM 12, HIGH 24) and never more than the renderer lights on one
## mesh (RendererFamily.per_mesh_light_limit: 8 in Mobile and Compatibility).
##
## Why: Landfall Town binds 112 marker lights and Landfall Insides 464. Mobile
## and Compatibility light a mesh instance with at most 8 omni lights and drop
## the rest in cull order, not by distance, so a big floor (the castle's
## flagstones are reached by 22 of its lights, the serpent undercity's terrace
## by 78) lost lights at random, often the ones by the player. Forward+ has no
## such limit, but every light in view is clustered and shaded, so the quality
## sets how many are worth it.
##
## Who writes what (LightMarkerBinder's header):
## - SecretSections owns a light's own `visible`. A light it hides is not
##   counted, and is never shown here.
## - The budget switches a light with its gate (LightMarkerBinder.gate_for),
##   added only when that light first has to go out, so a map whose lights all
##   fit keeps its tree exactly as bound.
## - A light coming on or going out because the focus moved fades its energy
##   over FADE_SECONDS. A light that has just been shown (a room entered) comes
##   on at once with its room, and one another system sets the energy of
##   (LightMarkerBinder.LEASE_META: LanternMineLighting) is switched without a
##   fade, its energy never written. While a light fades it carries its full
##   energy (LightMarkerBinder.RESTING_ENERGY_META), so a system keeping the
##   light's own energy to put back reads LightMarkerBinder.resting_energy,
##   not the fade's.
## - Under a per-mesh limit a light fading out keeps its slot until it is out,
##   so the limit holds on every frame, mid-fade too; a light waiting for that
##   slot comes on after. In Forward+ the two fade across each other, and at
##   most N + EDGE_SLOTS lights are drawn: when the focus moves fast, the
##   farthest of the lights still fading out go out at once.
##
## Which lights: the nearest by distance to the focus. The nearest N -
## EDGE_SLOTS always burn; the last EDGE_SLOTS slots keep a light that is
## already lit until it falls to rank N + HYSTERESIS_RANKS or beyond, so a
## focus walking along a row of lamps does not hand the last slots back and
## forth.
##
## Main binds it to the map's light root after LightMarkerBinder.apply and
## calls `update(focus)` every frame. The lights are chosen again every
## REFRESH_SECONDS (5 Hz), after the focus has moved REFRESH_DISTANCE, after a
## fade has freed a slot, and before the frame is drawn when SecretSections
## shows or hides a bound light, or the root or a parent of it is shown or
## hidden (their visibility_changed signals, deferred).
## Between those an update only steps the fades in progress. Only a bind or a
## visibility change looks at every bound light (Landfall Insides: 464); the
## timed choices look at the lights then shown (one cave's).
##
## No class_name: main and the tests preload this file.

const RendererFamily := preload("res://src/runtime/renderer_family.gd")

## Marker lights that burn at once by LookProfile.Quality (LOW, MEDIUM, HIGH).
const LIGHTS_BY_QUALITY: Array[int] = [6, 12, 24]
## The last slots, which keep a lit light while it stays within
## HYSTERESIS_RANKS of them.
const EDGE_SLOTS := 2
const HYSTERESIS_RANKS := 2
## Seconds a light takes to come on or go out when the focus moved.
const FADE_SECONDS := 0.3
## How often the lights are chosen again, and how far the focus may move
## before they are chosen sooner.
const REFRESH_SECONDS := 0.2
const REFRESH_DISTANCE := 1.5
## Ranking keys: squared distance in 1/RANK_SCALE m^2 steps times INDEX_SPAN,
## plus the light's index, so one native float sort ranks the lights nearest
## first with ties broken by binding order. INDEX_SPAN bounds the lights one
## budget takes; RANK_CEILING keeps the key exact in a float64.
const RANK_SCALE := 1024.0
const INDEX_SPAN := 65536
const RANK_CEILING := 1.0e8

enum { SETTLED, FADING_IN, FADING_OUT }

var _root: WeakRef
## Per bound light, by index: the light (a Variant: it may be freed), its
## position in the root's frame, the energy it burns at when lit, how lit it is
## now (0..1), whether its gate is open (or it has none), its fade state, and
## whether it was counted at the last choice.
var _lights: Array = []
var _local := PackedVector3Array()
var _base := PackedFloat64Array()
var _level := PackedFloat64Array()
var _open := PackedByteArray()
var _state := PackedByteArray()
var _counted := PackedByteArray()
## The lights shown (own visibility, root in view) at the last full look, and
## whether the next choice must look at every light again.
var _shown := PackedInt32Array()
var _rescan := true
var _fading := 0
var _focus := Vector3.INF
var _chosen_focus := Vector3.INF
var _refresh_at := 0.0
var _now := -1.0
var _dirty := false
var _deferred := false
var _writing := false
## Choices made, and the cost of the last one (microseconds), for diagnostics.
var choices := 0
var last_choice_usec := 0
## A quality to use instead of LookProfile.quality() (tests); -1 for none.
var quality_override := -1

## The most marker lights that burn at once: by `quality` (-1 for the one in
## use) and never more than `rendering_method`'s per-mesh limit ("" for the
## renderer in use).
static func light_limit(quality := -1, rendering_method := "") -> int:
	var level: int = LookProfile.quality() if quality < 0 else quality
	var wanted: int = LIGHTS_BY_QUALITY[clampi(level, 0, LIGHTS_BY_QUALITY.size() - 1)]
	var per_mesh: int = RendererFamily.per_mesh_light_limit(rendering_method)
	return mini(wanted, per_mesh) if per_mesh > 0 else wanted

## Takes the lights LightMarkerBinder put under `root` (after `apply`), letting
## go of any bound before. Null lets go only.
func bind(root: Node3D) -> void:
	release()
	if not is_instance_valid(root):
		return
	_root = weakref(root)
	root.set_meta(LightMarkerBinder.BUDGET_META, true)
	for node: Node in root.find_children("*", "OmniLight3D", true, false):
		if _lights.size() >= INDEX_SPAN:
			push_warning("LightMarkerBudget: more than %d lights under %s; the rest are left alone"
				% [INDEX_SPAN, root.name])
			break
		var light := node as OmniLight3D
		_lights.append(light)
		_local.append(_position_in(root, light))
		_base.append(light.light_energy)
		var open := LightMarkerBinder.gate_of(light) == null or LightMarkerBinder.gate_of(light).visible
		_level.append(1.0 if open else 0.0)
		_open.append(1 if open else 0)
		_state.append(SETTLED)
		_counted.append(0)
		light.visibility_changed.connect(_on_visibility_changed)
	# The root (or a parent of it) shown again tells no light under a shut
	# gate, so the root's own signal asks for the full look too.
	root.visibility_changed.connect(_on_visibility_changed)
	_dirty = true
	_rescan = true

## Lets go of the bound lights: every one back at its energy with its gate
## open (the gates stay), and the root unmarked.
func release() -> void:
	var root := _root.get_ref() as Node3D if _root != null else null
	if is_instance_valid(root):
		root.remove_meta(LightMarkerBinder.BUDGET_META)
		if root.visibility_changed.is_connected(_on_visibility_changed):
			root.visibility_changed.disconnect(_on_visibility_changed)
	_writing = true
	for index: int in _lights.size():
		var value: Variant = _lights[index]
		if not is_instance_valid(value):
			continue
		var light := value as OmniLight3D
		if light.visibility_changed.is_connected(_on_visibility_changed):
			light.visibility_changed.disconnect(_on_visibility_changed)
		if _state[index] != SETTLED:
			light.remove_meta(LightMarkerBinder.RESTING_ENERGY_META)
			if not _leased(light):
				light.light_energy = _base[index]
		var gate := LightMarkerBinder.gate_of(light)
		if gate != null:
			gate.visible = true
	_writing = false
	_root = null
	_lights.clear()
	_local.clear()
	_base.clear()
	_level.clear()
	_open.clear()
	_state.clear()
	_counted.clear()
	_shown.clear()
	_rescan = true
	_fading = 0
	_chosen_focus = Vector3.INF
	_dirty = false

func is_bound() -> bool:
	return _root != null and is_instance_valid(_root.get_ref())

## Every frame, with the camera's focus. `now` (seconds) is for tests; left
## out, the engine's clock is read.
func update(focus: Vector3, now := -1.0) -> void:
	if _lights.is_empty():
		return
	var clock := now if now >= 0.0 else Time.get_ticks_usec() / 1000000.0
	var step := 0.0 if _now < 0.0 else maxf(clock - _now, 0.0)
	_now = clock
	_focus = focus
	if _fading > 0:
		_step_fades(step)
	if not focus.is_finite():
		return
	if _dirty or clock >= _refresh_at \
			or _chosen_focus.distance_squared_to(focus) >= REFRESH_DISTANCE * REFRESH_DISTANCE:
		_choose()

## Chooses again now, with the last focus (tests, and the deferred call after
## SecretSections showed or hid a light).
func flush() -> void:
	_deferred = false
	if _lights.is_empty() or not _focus.is_finite():
		return
	_choose()

## The bound lights that burn now (shown, gate open), for tests and diagnostics.
func lit_lights() -> Array[OmniLight3D]:
	var out: Array[OmniLight3D] = []
	for index: int in _lights.size():
		var value: Variant = _lights[index]
		if is_instance_valid(value) and _open[index] == 1 and _counted[index] == 1 \
				and (value as OmniLight3D).is_visible_in_tree():
			out.append(value as OmniLight3D)
	return out

## Counts for diagnostics and probes.
func stats() -> Dictionary:
	var counted := 0
	for flag: int in _counted:
		counted += flag
	var per_mesh: int = RendererFamily.per_mesh_light_limit()
	return {"bound": _lights.size(), "counted": counted, "lit": lit_lights().size(),
		"fading": _fading, "limit": light_limit(quality_override), "per_mesh_limit": per_mesh,
		"choices": choices, "last_choice_usec": last_choice_usec}

func _on_visibility_changed() -> void:
	if _writing:
		return
	_rescan = true
	if _deferred:
		return
	_deferred = true
	flush.call_deferred()

func _choose() -> void:
	var started := Time.get_ticks_usec()
	_dirty = false
	_refresh_at = (_now if _now >= 0.0 else Time.get_ticks_usec() / 1000000.0) + REFRESH_SECONDS
	_chosen_focus = _focus
	var root := _root.get_ref() as Node3D if _root != null else null
	if not is_instance_valid(root) or not root.is_inside_tree():
		return
	var shown := root.is_visible_in_tree()
	var local_focus := root.global_transform.affine_inverse() * _focus
	var wanted := light_limit(quality_override)
	var per_mesh: int = RendererFamily.per_mesh_light_limit()
	var slots: int = per_mesh if per_mesh > 0 else wanted + EDGE_SLOTS
	_writing = true
	# Which lights count, nearest first. A light another system holds at zero
	# energy or with mask 0 lights nothing, but would still take a slot.
	var keys := PackedFloat64Array()
	var appeared := PackedByteArray()
	appeared.resize(_lights.size())
	# A light SecretSections hides can only come back through its visibility
	# signal, which asks for the full look again: between those the shown list
	# is all there is to rank.
	var full := _rescan
	_rescan = false
	var looked := _shown
	if full:
		looked = PackedInt32Array()
		looked.resize(_lights.size())
		for index: int in _lights.size():
			looked[index] = index
		_shown = PackedInt32Array()
	for index: int in looked:
		var value: Variant = _lights[index]
		if not is_instance_valid(value):
			_counted[index] = 0
			continue
		var light := value as OmniLight3D
		var counted := shown and light.visible and light.is_inside_tree()
		if full and counted:
			_shown.append(index)
		if counted and _state[index] == SETTLED:
			_base[index] = light.light_energy
		counted = counted and light.light_cull_mask != 0 and _base[index] > 0.0
		if not counted:
			if _state[index] != SETTLED:
				_settle(index, light, _open[index] == 1)
			# Shown but lighting nothing: out, so it frees its slot.
			if light.visible and shown and _open[index] == 1:
				_switch(index, light, false)
			_counted[index] = 0
			continue
		appeared[index] = 1 - _counted[index]
		_counted[index] = 1
		var near := minf(_local[index].distance_squared_to(local_focus), RANK_CEILING)
		keys.append(floorf(near * RANK_SCALE) * INDEX_SPAN + index)
	keys.sort()
	var ranked := PackedInt32Array()
	ranked.resize(keys.size())
	for rank: int in keys.size():
		ranked[rank] = int(fmod(keys[rank], INDEX_SPAN))
	var chosen := _pick(ranked, wanted)
	var is_chosen := PackedByteArray()
	is_chosen.resize(_lights.size())
	for index: int in chosen:
		is_chosen[index] = 1
	# Lights that stay on keep their slots; one fading out is taken back.
	for index: int in chosen:
		if _open[index] == 1:
			slots -= 1
			if _state[index] == FADING_OUT:
				_begin(index, FADING_IN)
	# A room just shown, and leased lights: on at once while a slot is free.
	for index: int in chosen:
		if _open[index] == 0 and (appeared[index] == 1 or _leased(_lights[index])) and slots > 0:
			_switch(index, _lights[index] as OmniLight3D, true)
			slots -= 1
	# Lights no longer chosen: out at once if just shown or leased, else fade.
	for index: int in ranked:
		if is_chosen[index] == 1 or _open[index] == 0:
			continue
		if appeared[index] == 1 or _leased(_lights[index]):
			_switch(index, _lights[index] as OmniLight3D, false)
		elif _state[index] != FADING_OUT:
			_begin(index, FADING_OUT)
	# Under a per-mesh limit a light fading out keeps its slot first and the
	# chosen ones wait for it; in Forward+ the chosen come first.
	if per_mesh > 0:
		slots = _hold_fading_out(ranked, slots)
	for index: int in chosen:
		if _open[index] == 0 and slots > 0:
			_begin(index, FADING_IN)
			slots -= 1
	if per_mesh <= 0:
		_hold_fading_out(ranked, slots)
	_writing = false
	choices += 1
	last_choice_usec = Time.get_ticks_usec() - started

## Lights fading out keep a slot, nearest first, while there is one; the rest
## go out now. Returns the slots left.
func _hold_fading_out(ranked: PackedInt32Array, slots: int) -> int:
	for index: int in ranked:
		if _open[index] == 0 or _state[index] != FADING_OUT:
			continue
		if slots > 0:
			slots -= 1
		else:
			_switch(index, _lights[index] as OmniLight3D, false)
	return slots

## The indices to light: the nearest `wanted - EDGE_SLOTS` by rank, then for
## the last slots first a light already lit up to rank wanted +
## HYSTERESIS_RANKS, then the nearest left.
func _pick(ranked: PackedInt32Array, wanted: int) -> PackedInt32Array:
	var core := mini(maxi(wanted - EDGE_SLOTS, 0), ranked.size())
	var chosen := ranked.slice(0, core)
	var reach := mini(wanted + HYSTERESIS_RANKS, ranked.size())
	for rank: int in range(core, reach):
		if chosen.size() >= wanted:
			break
		var index := ranked[rank]
		if _open[index] == 1 and _state[index] != FADING_OUT:
			chosen.append(index)
	for rank: int in range(core, ranked.size()):
		if chosen.size() >= wanted:
			break
		var index := ranked[rank]
		if not chosen.has(index):
			chosen.append(index)
	return chosen

func _step_fades(step: float) -> void:
	_writing = true
	var delta := step / FADE_SECONDS
	for index: int in _lights.size():
		var state := _state[index]
		if state == SETTLED:
			continue
		var value: Variant = _lights[index]
		if not is_instance_valid(value):
			_state[index] = SETTLED
			_fading -= 1
			continue
		var light := value as OmniLight3D
		# Another system set the energy mid-fade: theirs is the energy now.
		if not is_equal_approx(light.light_energy, _base[index] * _level[index]):
			_base[index] = light.light_energy
			_settle(index, light, state == FADING_IN)
			continue
		if state == FADING_IN:
			_level[index] = minf(1.0, _level[index] + delta)
			if _level[index] >= 1.0:
				_settle(index, light, true)
				continue
		else:
			_level[index] = maxf(0.0, _level[index] - delta)
			if _level[index] <= 0.0:
				_settle(index, light, false)
				# Its slot is free for a light waiting to come on.
				_dirty = true
				continue
		light.light_energy = _base[index] * _level[index]
	_writing = false

## Starts a fade from the light's present level.
func _begin(index: int, state: int) -> void:
	var light := _lights[index] as OmniLight3D
	if _leased(light):
		_switch(index, light, state == FADING_IN)
		return
	if _state[index] == SETTLED:
		_fading += 1
		# What it burns at when lit, for whoever keeps its energy to put back.
		light.set_meta(LightMarkerBinder.RESTING_ENERGY_META, _base[index])
	_state[index] = state
	if state == FADING_IN and _open[index] == 0:
		_level[index] = 0.0
		light.light_energy = 0.0
		_set_gate(index, light, true)

## Ends any fade: the light fully on (gate open) or out (gate shut), at its
## energy either way.
func _settle(index: int, light: OmniLight3D, on: bool) -> void:
	if _state[index] != SETTLED:
		_fading -= 1
		_state[index] = SETTLED
		light.remove_meta(LightMarkerBinder.RESTING_ENERGY_META)
		if not _leased(light):
			light.light_energy = _base[index]
	_level[index] = 1.0 if on else 0.0
	_set_gate(index, light, on)

## Switches at once, ending any fade.
func _switch(index: int, light: OmniLight3D, on: bool) -> void:
	_settle(index, light, on)

func _set_gate(index: int, light: OmniLight3D, on: bool) -> void:
	if (_open[index] == 1) == on:
		return
	var gate := LightMarkerBinder.gate_of(light)
	if gate == null and not on:
		gate = LightMarkerBinder.gate_for(light)
		if gate == null:
			# No parent to put a gate under: the light stays as it is.
			return
	_open[index] = 1 if on else 0
	if gate != null:
		gate.visible = on

static func _leased(value: Variant) -> bool:
	return is_instance_valid(value) and (value as Object).has_meta(LightMarkerBinder.LEASE_META)

static func _position_in(root: Node3D, light: Node3D) -> Vector3:
	# The binder puts its lights straight under the root, so their position is
	# already in the root's frame; anything deeper is walked up.
	var at := light.position
	var node := light.get_parent() as Node3D
	while node != null and node != root:
		at = node.transform * at
		node = node.get_parent() as Node3D
	return at
