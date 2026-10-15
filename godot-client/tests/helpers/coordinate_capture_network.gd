extends "res://src/network/network_client.gd"
var sent: Array[PackedByteArray] = []
func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
	sent.append(frame)
	return OK
