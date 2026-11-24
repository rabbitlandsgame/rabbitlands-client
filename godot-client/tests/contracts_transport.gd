extends "res://src/network/network_client.gd"
## Loaded after autoload registration; captures requests without a connection.
var sent: Array[String] = []
func send_chat(text: String) -> Error:
	sent.append(text)
	return OK
