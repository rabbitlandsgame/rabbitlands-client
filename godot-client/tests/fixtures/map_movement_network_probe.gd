extends "res://src/network/network_client.gd"
## Keep production move/spell dispatch and signals; replace only the transport.
var send_error: Error = OK
var sent_frames: Array[PackedByteArray] = []

func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
	if send_error == OK:
		sent_frames.append(frame)
	return send_error
