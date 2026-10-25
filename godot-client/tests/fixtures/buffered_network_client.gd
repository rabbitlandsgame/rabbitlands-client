extends "res://src/network/network_client.gd"
## The transport stays empty: dispatch must resume bytes already buffered.
var empty_link := StreamPeerBuffer.new()
func _link() -> StreamPeer: return empty_link
