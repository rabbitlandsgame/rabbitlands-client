extends SceneTree
const Lease := preload("res://src/platform/browser_loading_lease.gd")
var messages: Array[String] = []
var outcome := OK

func send(message: String) -> int:
	messages.append(message)
	return outcome

func _initialize() -> void:
	var lease := Lease.new()
	lease.update(false, "landfall", 0, send)
	assert(messages.is_empty())
	lease.update(true, "landfall", 0, send)
	lease.update(true, "landfall", 14999, send)
	assert(messages == ["#loading landfall"])
	lease.update(true, "landfall", 15000, send)
	assert(messages.size() == 2)
	lease.update(true, "four_gates", 15001, send)
	assert(messages.back() == "#loading four_gates")
	lease.update(false, "four_gates", 16000, send)
	lease.update(true, "four_gates", 16001, send)
	assert(messages.size() == 4)
	outcome = ERR_CONNECTION_ERROR
	lease.update(true, "landfall", 16002, send)
	lease.update(true, "landfall", 17001, send)
	assert(messages.size() == 5, "failed sends must not spin each frame")
	lease.update(true, "landfall", 17002, send)
	assert(messages.size() == 6)
	var native := EloriaProtocol.client_capabilities().slice(3).get_string_from_utf8()
	var browser := EloriaProtocol.client_capabilities(0, true).slice(3).get_string_from_utf8()
	assert("arrival_ready_v1" in browser and "browser_asset_loading_v1" in browser)
	assert("browser_asset_loading_v1" not in native)
	print("browser loading lease: PASS")
	quit()
