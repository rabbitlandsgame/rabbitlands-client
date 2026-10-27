extends RefCounted
## Set the loader's final sampler before ImporterMesh first binds a material.
## This preserves the final material and avoids preparing an unused initial
## filter permutation. The opt-out restores the old ordering for diagnostics.
const ENVIRONMENT := "ELORIA_EARLY_MAP_FILTER"
const FILTER := BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC

static func enabled() -> bool:
	return OS.get_environment(ENVIRONMENT) != "0"

static func prepare(state: GLTFState) -> int:
	if state == null or not enabled(): return 0
	var changed := 0
	for value: Material in state.get_materials():
		var material := value as BaseMaterial3D
		if material != null and material.texture_filter != FILTER:
			material.texture_filter = FILTER
			changed += 1
	return changed
