class_name LightMarkerBinder
extends RefCounted
## Turns a manifest's `lighting.markers` into real lights in the scene.
##
## Packages declare their warm landmark lights and brazier lights as named
## markers with a colour, an energy hint and a range hint rather than as glTF
## light extensions, so the package needs no loader change and no extension the
## client does not implement. This binder is the client side of that contract.
##
## Maps that declare no markers get nothing, so this is a no-op for every
## package authored before the convention existed.
##
## Switching a bound light on and off. Several systems touch these lights, and
## each keeps to its own property:
## - SecretSections owns the light's own `visible` (only the player's section
##   is shown). Nothing else writes it.
## - A light is switched off by a gate: a plain Node3D put between the light
##   and its parent (`gate_for`), hidden or shown. A light with mask 0 or
##   energy 0 still takes one of the 8 lights a mesh may have in Mobile and
##   Compatibility; a hidden gate frees it. LightMarkerBudget (the per-quality
##   nearest-N budget) and LanternMineLighting's fallback both use these gates.
## - A system that sets a light's energy itself (LanternMineLighting) marks it
##   with LEASE_META while it does, so the budget never fades that energy, and
##   reads the energy to put back with `resting_energy`, never a fade's.
## The binder itself puts no gate in: a gate is added the first time a light
## has to be switched off, so maps with few lights keep the tree as bound.

const DEFAULT_ENERGY := 2.4
const DEFAULT_RANGE := 14.0
## A gate's name is this followed by its light's name.
const GATE_PREFIX := "LightGate_"
## On a gate node, to tell it from any other parent.
const GATE_META := &"rl_light_gate"
## On the binder's parent while a LightMarkerBudget manages its lights
## (LightMarkerBudget.bind); others then leave the gates to the budget.
const BUDGET_META := &"rl_light_marker_budget"
## On a light whose energy another system sets (the value names the system).
const LEASE_META := &"rl_light_energy_lease"
## On a light while a LightMarkerBudget fades its energy: the energy it burns
## at when fully lit (`resting_energy`).
const RESTING_ENERGY_META := &"rl_light_resting_energy"

static func apply(manifest: WorldManifest, parent: Node3D,
		shadows: bool = false) -> int:
	if manifest == null or parent == null:
		return 0
	var lighting: Variant = manifest.data.get("lighting", {})
	if lighting is not Dictionary:
		return 0
	var markers: Variant = (lighting as Dictionary).get("markers", [])
	if markers is not Array:
		return 0
	var bound := 0
	for raw: Variant in markers as Array:
		if raw is not Dictionary:
			continue
		var marker: Dictionary = raw
		var position: Variant = marker.get("position")
		if position is not Array or (position as Array).size() < 3:
			continue
		var light := OmniLight3D.new()
		light.name = str(marker.get("id", "Light_%d" % bound))
		light.position = Vector3(float((position as Array)[0]),
			float((position as Array)[1]), float((position as Array)[2]))
		light.light_color = _colour(marker.get("color"))
		light.light_energy = float(marker.get("energyHint", DEFAULT_ENERGY))
		light.omni_range = float(marker.get("rangeHint", DEFAULT_RANGE))
		# Point lights that cast shadows are expensive and a marker light is a
		# fill, not a key light, so shadows stay off unless a caller asks.
		light.shadow_enabled = shadows
		parent.add_child(light)
		bound += 1
	return bound

## The light's gate, put in between the light and its parent if it has none
## yet. The gate is at the parent's origin, so the light stays where it is,
## and takes the light's place among its parent's children. Null for a light
## with no parent.
static func gate_for(light: Light3D) -> Node3D:
	var gate := gate_of(light)
	if gate != null:
		return gate
	var parent := light.get_parent() if is_instance_valid(light) else null
	if parent == null:
		return null
	gate = Node3D.new()
	gate.name = GATE_PREFIX + str(light.name)
	gate.set_meta(GATE_META, true)
	var at := light.get_index()
	parent.add_child(gate)
	parent.move_child(gate, at)
	# Not keeping the global transform: the gate adds none, and a light out of
	# the tree has no global transform to keep.
	light.reparent(gate, false)
	return gate

## The light's gate, or null when it has none.
static func gate_of(light: Light3D) -> Node3D:
	if not is_instance_valid(light):
		return null
	var parent := light.get_parent() as Node3D
	return parent if parent != null and parent.has_meta(GATE_META) else null

## Takes the light's gate out again: the light goes back to the gate's parent,
## in the gate's place, and the gate is freed. The light's own visibility is
## left as it is.
static func ungate(light: Light3D) -> void:
	var gate := gate_of(light)
	if gate == null:
		return
	var parent := gate.get_parent()
	if parent != null:
		var at := gate.get_index()
		light.reparent(parent, false)
		parent.move_child(light, at)
	gate.queue_free()

## True while a LightMarkerBudget manages the lights under `root`.
static func budgeted(root: Node) -> bool:
	return is_instance_valid(root) and root.has_meta(BUDGET_META)

## The energy `light` burns at when fully lit: its energy, or, while a
## LightMarkerBudget fades it, the energy the fade is towards or from. A system
## that keeps a light's own energy to put back (LanternMineLighting) reads it
## here, not mid-fade.
static func resting_energy(light: Light3D) -> float:
	return float(light.get_meta(RESTING_ENERGY_META, light.light_energy))

static func _colour(value: Variant) -> Color:
	if value is Array and (value as Array).size() >= 3:
		var values: Array = value
		return Color(float(values[0]), float(values[1]), float(values[2]))
	if value is String:
		return Color(str(value))
	return Color(1.0, 0.85, 0.65)
