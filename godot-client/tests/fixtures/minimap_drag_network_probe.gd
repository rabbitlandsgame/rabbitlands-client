extends "res://src/network/network_client.gd"
## Deferred-loaded fixture: keep the production offline-preview guard and
## network dispatch while retaining only synthetic outgoing frames in memory.
var outgoing: Array[PackedByteArray] = []

func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
	outgoing.append(frame.duplicate())
	return OK
