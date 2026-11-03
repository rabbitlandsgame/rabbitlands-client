#pragma once
#include <cstddef>
#include <cstdint>
extern "C" {
struct RlRuntime;
struct RlPlanRecord { int64_t id, generation; uint64_t rig; int64_t tier, phase; };
struct RlPlanResult { int64_t id, generation, epoch, due; };
struct RlMountedRecord { int64_t id, generation; uint64_t rider; int64_t gait, frame; };
struct RlMountedResult { int64_t id, generation, epoch, frame; uint64_t offset, bones; };
uint32_t rl_client_runtime_abi();
RlRuntime *rl_client_runtime_create();
void rl_client_runtime_destroy(RlRuntime *);
int32_t rl_client_runtime_reset(RlRuntime *, int64_t epoch);
int32_t rl_client_runtime_register_rig(RlRuntime *, const int32_t *, const double *, const double *, size_t, uint64_t *);
int32_t rl_client_runtime_unregister_rig(RlRuntime *, uint64_t);
int32_t rl_client_runtime_plan(RlRuntime *, const RlPlanRecord *, size_t, int64_t, int64_t, RlPlanResult *, size_t);
int32_t rl_client_runtime_register_mounted_rider(RlRuntime *, uint64_t rig, const int32_t *, const double *,
    const int32_t *thumbs, const double *grips, size_t thumb_count, uint64_t *handle);
int32_t rl_client_runtime_unregister_mounted_rider(RlRuntime *, uint64_t);
int32_t rl_client_runtime_set_mounted_lean(RlRuntime *, uint64_t, double);
int32_t rl_client_runtime_solve_mounted(RlRuntime *, const RlMountedRecord *, const double *, size_t count,
    int64_t epoch, RlMountedResult *, size_t output_capacity, double *, size_t value_capacity, size_t *value_count);
// Content digest (core/src/digest_ffi.rs): stateless, any thread.
uint32_t rl_digest_api();
uint32_t rl_digest_backend();
uint32_t rl_digest_cpu_sha_ni();
int32_t rl_digest_limits(uint64_t *max_files, uint32_t *max_threads, uint64_t *max_path_bytes, uint64_t *read_bytes);
int32_t rl_digest_sha256_buffer(const uint8_t *data, size_t length, uint8_t *output32);
int32_t rl_digest_sha256_files(const uint8_t *const *paths, const size_t *lengths, const uint32_t *flags, size_t count,
    uint32_t threads, uint8_t *out_digests, int32_t *out_status, uint8_t *out_folded, uint64_t *out_bytes,
    uint32_t *out_threads);
int32_t rl_digest_verify_files(const uint8_t *const *paths, const size_t *lengths, const uint32_t *flags,
    const uint8_t *expected, const uint8_t *expected_present, size_t count, uint32_t threads, uint8_t *out_digests,
    int32_t *out_status, uint8_t *out_folded, uint8_t *out_ok, uint64_t *out_bytes, uint32_t *out_threads);
}
