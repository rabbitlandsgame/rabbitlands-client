extends SceneTree
## Product mount additions must not change the historical mixed-mounted workload.
const Workloads := preload("res://tests/integration/performance_workloads.gd")
const Profiles := preload("res://src/mounts/mount_profiles.gd")
const Controller := preload("res://src/runtime/client_runtime.gd")
const LOCAL_ID := 1000
const EXPECTED_ORDER := ["crystalback_tortoise", "giant_rat", "golden_plains_horse",
	"jadefeather_raptor", "moor_pony", "rabbit"]
const ADDED_PROFILES := ["cave_salamander", "lantern_stag", "cheetah"]
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)

func _run() -> void:
	var catalog_before: Dictionary = Profiles.PATHS.duplicate(true)
	var catalog_key_order: Array = Profiles.PATHS.keys()
	var cohort_before: Array = Workloads.MIXED_MOUNT_PROFILE_IDS.duplicate()
	_check(cohort_before == EXPECTED_ORDER, "exact original six-profile order is explicit")
	for profile: String in EXPECTED_ORDER:
		_check(Profiles.PATHS.has(profile) and FileAccess.file_exists(str(Profiles.PATHS.get(profile, ""))),
			"historical profile is still registered with a current profile file: " + profile)
	for profile: String in ADDED_PROFILES:
		_check(Profiles.PATHS.has(profile) and FileAccess.file_exists(str(Profiles.PATHS.get(profile, ""))),
			"new product profile remains registered: " + profile)
		_check(not Workloads.MIXED_MOUNT_PROFILE_IDS.has(profile),
			"new product profile does not silently alter historical cohort: " + profile)
	var records: Dictionary = {}
	# Reverse insertion proves membership is chosen by sorted actor identity.
	for index: int in range(159, -1, -1):
		var id := LOCAL_ID + index
		records[id] = {"actor_id": id, "name": "Synthetic actor %d" % id, "map": "prior"}
	var record_ids: Array = records.keys()
	var rows := Workloads.mount_rows(records, 80, "four_gates")
	_check(records.size() == 160 and records.keys() == record_ids,
		"fixture keeps all 160 actor records and their identity ordering")
	_check(rows.size() == 80 and rows.has(LOCAL_ID), "exactly 80 mounts include the local actor")
	var supported := 0
	var expected_keys: Array = []
	for index: int in 160:
		var id := LOCAL_ID + index
		_check(rows.has(id) == (index < 80), "exact mounted membership for actor %d" % id)
		if index >= 80:
			continue
		expected_keys.append(id)
		var row: Dictionary = rows[id]
		var expected: String = EXPECTED_ORDER[index % EXPECTED_ORDER.size()]
		_check(row.actor_id == id and row.mount_id == expected and row.selected_mount_id == expected
			and row.owner == records[id].name and row.map == "four_gates",
			"ordered profile, owner and map for actor %d" % id)
		supported += int(Controller.MOUNTED_PROFILE_IDS.has(expected))
	_check(rows.keys() == expected_keys, "returned rows preserve deterministic sorted membership")
	var counts := Workloads.mount_profile_counts(rows)
	_check(counts == {"crystalback_tortoise": 14, "giant_rat": 14,
		"golden_plains_horse": 13, "jadefeather_raptor": 13, "moor_pony": 13, "rabbit": 13},
		"exact historical per-profile counts")
	_check(supported == 66 and int(counts.get("giant_rat", 0)) == 14,
		"five supported native profiles total 66 with 14 deliberate Giant Rat fallbacks")
	var next := Workloads.mount_rows(records, 80, "four_gates")
	_check(next == rows, "repeated fixture creation is identical")
	rows[LOCAL_ID]["mount_id"] = "caller-mutated-row"
	var fresh := Workloads.mount_rows(records, 80, "four_gates")
	_check(fresh == next, "mutating returned rows cannot poison subsequent calls")
	var partial := Workloads.mount_rows(records, 7, "four_gates")
	_check(partial.size() == 7 and partial[LOCAL_ID].mount_id == EXPECTED_ORDER[0]
		and partial[LOCAL_ID + 6].mount_id == EXPECTED_ORDER[0], "short calls retain the same cycle")
	_check(Profiles.PATHS == catalog_before and Profiles.PATHS.keys() == catalog_key_order,
		"calls never mutate the product catalog or its ordering")
	_check(Workloads.MIXED_MOUNT_PROFILE_IDS == cohort_before,
		"calls never mutate the shared historical cohort array")
	print("historical mount cohort: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
