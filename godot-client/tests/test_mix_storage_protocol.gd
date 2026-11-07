extends SceneTree

const Protocol := preload("res://src/network/protocol.gd")

func _init() -> void:
	var snapshot := Protocol.decode_mix_state("010000000200546f7263680000020007002c01".hex_decode())
	assert(snapshot.storage_known and snapshot.storage_recipes == [7, 300])
	assert(snapshot.output == "Torch" and snapshot.made == 2 and not snapshot.interrupted)
	var empty := Protocol.decode_mix_state("010000000200546f72636800000000".hex_decode())
	assert(empty.storage_known and empty.storage_recipes.is_empty())
	var legacy := Protocol.decode_mix_state("010000000200546f72636800".hex_decode())
	assert(not legacy.storage_known and not legacy.interrupted and legacy.output == "Torch")
	var interrupted := Protocol.decode_mix_state("010000000200546f7263680001".hex_decode())
	assert(interrupted.interrupted and not interrupted.storage_known)
	assert(Protocol.decode_mix_state("010000000200546f726368000002000700".hex_decode()).type == "invalid")
	print("Storage mixing protocol: 6 checks passed")
	quit()
