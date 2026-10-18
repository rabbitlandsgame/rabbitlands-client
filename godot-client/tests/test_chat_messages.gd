extends SceneTree

const Messages = preload("res://src/ui/chat_messages.gd")
var failures := 0

func _init() -> void:
	var legacy := {"channel": 0, "text": "Gathered: 5 Gold Coins"}
	var current := {"channel": 3, "text": "Gathered: 1 Ancient Relic"}
	var nearby := {"channel": 0, "text": "[Loot] Tavi gathered: 1 Ancient Relic."}
	for pickup: Dictionary in [legacy, current]:
		_expect(Messages.matches(pickup, "system"), "pickup belongs in System")
		_expect(not Messages.matches(pickup, "local"), "pickup stays out of Local")
	_expect(Messages.matches(nearby, "local"), "nearby loot belongs in Local")
	_expect(not Messages.matches(nearby, "system"), "nearby loot stays out of System")
	_expect(Messages.kind({"channel": 0, "text": "Tavi: Gathered: 5 Gold Coins"}) == "local",
		"players can still discuss their pickups in Local")
	_expect(Messages.kind({"channel": 1, "text": "Gathered: private message"}) == "private",
		"private messages keep their channel")
	_expect(Messages.kind({"channel": 3, "text": "[Loot] A server notice"}) == "system",
		"explicit System channel takes precedence over loot text")
	print("chat message tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
