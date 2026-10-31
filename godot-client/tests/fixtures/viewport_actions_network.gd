extends "res://src/network/network_client.gd"
## Load after autoload registration; never open a real socket for input probes.
var frames: Array[PackedByteArray] = []

func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
	frames.append(frame)
	return OK
