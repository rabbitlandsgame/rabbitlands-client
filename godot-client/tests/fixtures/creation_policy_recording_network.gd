extends "res://src/network/network_client.gd"
## Loaded after autoload initialization; no real socket or outgoing request.
var frames: Array[PackedByteArray] = []

func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
	frames.append(frame)
	return OK
