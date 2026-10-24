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
int32_t rl_client_runtime_solve_mounted(RlRuntime *, const RlMountedRecord *, const double *, size_t count,
    int64_t epoch, RlMountedResult *, size_t output_capacity, double *, size_t value_capacity, size_t *value_count);
}
