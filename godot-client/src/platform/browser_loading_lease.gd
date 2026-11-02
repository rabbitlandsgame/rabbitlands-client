extends RefCounted
## Negotiated, bounded server protection while a browser arrival is loading.
const INTERVAL_MSEC := 15000
var _map := ""
var _next := 0

func update(active: bool, map_id: String, now: int, send: Callable) -> void:
	if not active or map_id.is_empty():
		_map = ""
		_next = 0
		return
	if _map != map_id:
		_map = map_id
		_next = 0
	if now < _next: return
	var result: int = send.call("#loading " + map_id)
	_next = now + (INTERVAL_MSEC if result == OK else 1000)
