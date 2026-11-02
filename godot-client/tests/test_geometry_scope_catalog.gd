extends SceneTree
## A bound release catalog prepared for this exact scope, registry and policy
## set supplies the geometry targets, so a launch need not parse every scope
## manifest. Eligibility and the producer's described targets must equal what
## the manifests declare; any mismatch keeps the manifest scan.
const Cache := preload("res://src/world/map_geometry_cache.gd")
const Installed := preload("res://src/world/installed_world_cache.gd")
const Collision := preload("res://src/world/map_collision_cache.gd")
const Paving := preload("res://src/world/map_paving_cache.gd")
var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func reset_cache() -> void:
	Cache._initialized = false
	Cache._targets = {}
	Cache._roots = {}
	Cache._scope_error = ""
	Cache._catalog_targets = false

func catalog(keys: Array, scope_sha: String) -> Dictionary:
	return {"scope_sha256": scope_sha, "registry_sha256": FileAccess.get_sha256(Cache.REGISTRY),
		"geometry_policy": Cache._policy_digest(), "collision_policy": Collision.policy(),
		"paving_policy": Paving.policy(), "target_keys": keys}

func run() -> void:
	var saved_loaded := Installed._loaded
	var saved_catalogs := Installed._catalogs.duplicate()
	reset_cache()
	var began := Time.get_ticks_usec()
	Cache.initialize()
	var scan_us := Time.get_ticks_usec() - began
	var described := Cache.targets()
	var keys: Array = Cache._targets.keys()
	keys.sort()
	var roots: Dictionary = Cache._roots.duplicate()
	expect(not Cache._catalog_targets and not keys.is_empty() and Cache._scope_error.is_empty(),
		"without an installed catalog the scope manifests are scanned")
	var world := ""
	for key: String in keys:
		if key.begins_with("world|"):
			world = key.get_slice("|", 1)

	Installed._loaded = true
	Installed._catalogs.assign([catalog(keys, FileAccess.get_sha256(Cache.SCOPE))])
	reset_cache()
	began = Time.get_ticks_usec()
	Cache.initialize()
	var catalog_us := Time.get_ticks_usec() - began
	var installed_keys: Array = Cache._targets.keys()
	installed_keys.sort()
	expect(Cache._catalog_targets and installed_keys == keys and Cache._roots == roots and Cache._scope_error.is_empty(),
		"a matching installed catalog supplies the same targets and roots without the manifests")
	expect(not world.is_empty() and Cache.eligible("world", world)
		and Cache.eligible("world", Cache.Sources.source_path(world)),
		"a scoped world target stays eligible from the catalog's keys")
	expect(not Cache.eligible("world", "res://../eloria-assets/maps/not-a-scoped-map/world.json"),
		"an unlisted map stays outside the scope")
	expect(Cache.targets() == described, "producers still see every target with its manifest id")
	var producer_keys: Array = Cache._targets.keys()
	producer_keys.sort()
	expect(not Cache._catalog_targets and producer_keys == keys and Cache._scope_error.is_empty(),
		"once a producer asks, the scope manifests decide eligibility as without a catalog")
	print("scope targets: manifest scan ", scan_us / 1000.0, " ms, installed catalog ", catalog_us / 1000.0, " ms")

	Installed._catalogs.assign([catalog(keys, "0".repeat(64))])
	reset_cache()
	Cache.initialize()
	expect(not Cache._catalog_targets and Cache.targets() == described,
		"a catalog for another scope leaves the manifest scan in charge")
	Installed._catalogs.assign([catalog(keys, FileAccess.get_sha256(Cache.SCOPE))])
	Cache.cooking = true
	expect(Cache._installed_target_keys(Cache._policy_digest()).is_empty(), "a producer always scans the manifests")
	Cache.cooking = false

	Installed._loaded = saved_loaded
	Installed._catalogs.assign(saved_catalogs)
	reset_cache()
	print("geometry scope catalog: ", failures, " failures")
	quit(failures)
