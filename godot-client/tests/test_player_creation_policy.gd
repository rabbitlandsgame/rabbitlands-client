extends SceneTree
## Player creation is restricted independently of NPC/authoring availability.
const POLICY := preload("res://src/actors/player_creation_policy.gd")
const BASES := preload("res://src/ui/creation_base_library.gd")

var checks := 0
var failures := 0

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var original := JSON.stringify(registry)
	var options := POLICY.options(registry)
	check(options.size() == 2, "only the two Human player bodies are enabled")
	check((registry.creationOptions as Array).size() == 16, "full race/body catalog remains available to NPC and authoring consumers")
	var enabled := []
	for option: Dictionary in options:
		enabled.append(int(option.actorType))
		check(registry.models[option.model].culture == "luminous", "enabled options have actual Human models")
	enabled.sort()
	check(enabled == [0, 1], "enabled player actor types agree with server Human policy")
	var rows := BASES.rows(registry)
	check(rows.size() == 41, "all 41 Human starting looks remain available")
	for row: Dictionary in rows:
		check(row.race_id == "luminous" and POLICY.allows_actor_type(row.look.actor_type), "every base is a Human player choice")
	for option: Dictionary in registry.creationOptions:
		var actor_type := int(option.actorType)
		check(registry.models.has(option.model) and registry.actorTypes[str(actor_type)] == option.model,
			"full actor type/model routing remains available: " + str(actor_type))
		check(FileAccess.file_exists(str(registry.models[option.model].scene)),
			"registered body asset remains available: " + str(option.model))
		check(POLICY.allows_actor_type(actor_type) == (actor_type in [0, 1]),
			"non-Human catalog bodies do not become player options")
	# Defer loading the Network subclass until AppState and the other autoloads
	# exist; an inner/preloaded subclass would create an autoload compile cycle.
	var network: Variant = load("res://tests/fixtures/creation_policy_recording_network.gd").new()
	network._set_appearance_protocol(4)
	for actor_type: int in [0, 1]:
		check(network.create_character("Policy test", "dummy", {"actor_type": actor_type}) == OK,
			"Human creation reaches the recording transport")
	check(network.frames.size() == 2, "both Human requests were serialized exactly once")
	for option: Dictionary in registry.creationOptions:
		var actor_type := int(option.actorType)
		if actor_type in [0, 1]: continue
		check(network.validate_creation_appearance({"actor_type": actor_type}) == ERR_UNAVAILABLE,
			"ordinary non-Human request is unavailable even without advanced fields")
		check(network.create_character("Policy test", "dummy", {"actor_type": actor_type}) == ERR_UNAVAILABLE,
			"direct network creation refuses non-Human actor " + str(actor_type))
		check(network.appearance_error == POLICY.MESSAGE, "creation refusal explains the currently available race")
	check(network.frames.size() == 2, "no rejected non-Human request reaches transport")
	for value: Variant in [-1, 2, 41, 42, 255, 1.5, "1", false, null, NAN, INF]:
		check(not POLICY.allows_actor_type(value), "invalid/non-Human actor input cannot bypass policy")
		check(network.create_character("Policy test", "dummy", {"actor_type": value}) == ERR_UNAVAILABLE,
			"invalid actor input cannot be coerced into a Human network request")
	check(network.frames.size() == 2, "invalid actor inputs never reach transport")
	# Filtering must not trust a Human actor ID attached to an unrelated model.
	var forged := registry.duplicate(true)
	forged.creationOptions = [{"actorType": 0, "model": "ssarathi_female"},
		{"actorType": 41, "model": "luminous_female"}]
	check(POLICY.options(forged).is_empty(), "both actor ID and actual Human model must be eligible")
	options[0].model = "changed"
	check(JSON.stringify(registry) == original, "filtering and edited results never mutate the NPC/model registry")
	network.free()
	print("Player creation policy: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
