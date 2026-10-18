extends RefCounted
## Reserved mount preview reducer. Live AppState and capabilities do not use it.
## A snapshot belongs to one spawned actor in one coordinate epoch; local UI
## cannot infer a successful summon from sending a request.

const MOUNT_ID := "moor_pony"
const MOUNT_IDS := ["moor_pony", "golden_plains_horse"]
const REASONS := ["", "disabled", "not_owned", "dead", "combat", "restricted_area",
	"no_clearance", "immobilized", "moving", "already_summoning"]
var actor_id := -1
var epoch := -1
var revision := -1
var state: Dictionary = {}
var last_error := ""

func reset(new_actor_id: int = -1, new_epoch: int = -1) -> void:
	actor_id = new_actor_id
	epoch = new_epoch
	revision = -1
	state = {}
	last_error = ""

static func _integer(value: Variant, minimum: int, maximum: int) -> bool:
	if typeof(value) not in [TYPE_INT, TYPE_FLOAT]:
		return false
	var number := float(value)
	return is_finite(number) and number == floor(number) and number >= minimum and number <= maximum

func apply_snapshot(value: Variant) -> bool:
	if not value is Dictionary:
		last_error = "invalid_snapshot"
		return false
	var incoming: Dictionary = value
	if (incoming.get("kind") != "mount_preview"
			or not _integer(incoming.get("schema_version"), 1, 1)
			or not _integer(incoming.get("actor_id"), 0, 65535)
			or not _integer(incoming.get("epoch"), 0, 2147483647)
			or not _integer(incoming.get("revision"), 1, 9007199254740991)):
		last_error = "invalid_identity"
		return false
	if actor_id < 0 or int(incoming.actor_id) != actor_id or int(incoming.epoch) != epoch:
		last_error = "different_spawn"
		return false
	if int(incoming.revision) <= revision:
		last_error = "stale_snapshot"
		return false
	var mode: Variant = incoming.get("mode")
	var gait: Variant = incoming.get("gait")
	var mount: Variant = incoming.get("mount_id")
	var selected: Variant = incoming.get("selected_mount_id")
	if (mode not in ["on_foot", "summoning", "mounted"]
			or gait not in ["on_foot", "walk", "cruise", "burst"]
			or (selected != "" and selected not in MOUNT_IDS)
			or typeof(incoming.get("can_summon")) != TYPE_BOOL
			or incoming.get("blocked_reason") not in REASONS):
		last_error = "invalid_mode"
		return false
	if ((mode == "on_foot" and (mount != "" or gait != "on_foot"))
			or (mode == "summoning" and (mount not in MOUNT_IDS or gait != "on_foot"))
			or (mode == "mounted" and (mount not in MOUNT_IDS or gait == "on_foot"))
			or (mode != "on_foot" and selected != mount)
			or (incoming.can_summon and (mode != "on_foot" or selected not in MOUNT_IDS
				or incoming.blocked_reason != ""))):
		last_error = "inconsistent_mode"
		return false
	if incoming.has("owned_mount_ids"):
		var owned: Variant = incoming.owned_mount_ids
		if not owned is Array or owned.size() > MOUNT_IDS.size():
			last_error = "invalid_ownership"
			return false
		var seen := {}
		for id: Variant in owned:
			if id not in MOUNT_IDS or seen.has(id):
				last_error = "invalid_ownership"
				return false
			seen[id] = true
		if selected != "" and selected not in owned:
			last_error = "invalid_ownership"
			return false
	for spec: Array in [["step_us", 10000, 2000000], ["endurance_ms", 0, 8000],
		["summon_remaining_ms", 0, 1500], ["combat_remaining_ms", 0, 10000]]:
		if not _integer(incoming.get(spec[0]), spec[1], spec[2]):
			last_error = "invalid_timing"
			return false
	if mode != "summoning" and int(incoming.summon_remaining_ms) != 0:
		last_error = "inconsistent_summon"
		return false
	state = incoming.duplicate(true)
	revision = int(incoming.revision)
	last_error = ""
	return true

static func request(action: String, argument: Variant = null) -> Dictionary:
	var message := {"kind": "mount_request", "schema_version": 1, "action": action}
	if action == "toggle" and argument == null:
		return message
	if action == "burst" and typeof(argument) == TYPE_BOOL:
		message["enabled"] = argument
		return message
	if action == "select" and argument in MOUNT_IDS:
		message["mount_id"] = argument
		return message
	return {}

func display_status() -> String:
	var mount_name := preload("res://src/mounts/mount_profiles.gd").display_name(str(state.get("selected_mount_id", "")))
	if state.is_empty():
		return "Waiting for the preview server"
	if state.mode == "summoning":
		return "Summoning " + mount_name
	if state.mode == "mounted":
		return "Riding " + mount_name + " — " + str(state.gait).capitalize()
	match state.blocked_reason:
		"combat": return "On foot — wait for combat to end"
		"restricted_area": return "On foot — riding is unavailable here"
		"no_clearance": return "On foot — this passage is too narrow"
		"moving": return "On foot — stop moving to summon"
		"not_owned": return "On foot — Moor Pony has not been unlocked"
		"disabled": return "Mount preview is disabled"
		"dead": return "On foot — revive before summoning"
		"immobilized": return "On foot — movement is restricted"
	return "On foot — ready to summon"
