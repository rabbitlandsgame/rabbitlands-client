extends "res://tests/test_cape_cloth_pose_cache.gd"
## Runs the full cape parity/performance sequence against the immediately
## preceding pose-cache solver. The parent test still runs separately against
## the original solver, so this narrow comparison cannot hide older drift.

const POSE_CACHE_BASELINE := \
	"res://tests/fixtures/cape_cloth_pose_cache_baseline.gd"
const POSE_CACHE_BASELINE_BODY_SHA256 := \
	"78b9e684ab3dd72a9e2bd32d8a1685cfedee1698071411ce33eca110cfef3743"


func _baseline_path() -> String:
	return POSE_CACHE_BASELINE


func _baseline_body_sha256() -> String:
	return POSE_CACHE_BASELINE_BODY_SHA256


func _comparison_label() -> String:
	return "reviewed pose-cache solver vs capsule-invariant cache"
