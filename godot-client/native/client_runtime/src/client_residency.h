#pragma once
#include "client_core.h"
struct RlAdmissionInput { uint64_t estimated_bytes,candidate_bytes,budget_bytes,live_workers,maximum_workers,
    retiring_roots,unknown_resources,unknown_limit,pinned,synchronous; };
struct RlAdmissionDecision { uint64_t lease,reason; };
struct RlAdmissionSnapshot { uint64_t reserved,loading,ready,active,retiring,cancelled,old_epoch,denials,forced_sync; };
struct RlAdmissionGraphSnapshot { uint64_t resources,edges,lease_links,loading,ready,active,retiring,registrations,physical_releases; };

struct RlResourceKey { uint64_t words[4]; };
struct RlResidencyDescriptor {
    RlResourceKey key;
    uint64_t cpu_bytes, gpu_bytes, flags, dependency_start, dependency_count;
};
struct RlResidencyWanted { RlResourceKey key; int64_t priority, pinned; };
struct RlResidencyEvent { RlResourceKey key; uint64_t generation; int64_t epoch, kind; };
struct RlResidencyAction { RlResourceKey key; uint64_t generation; int64_t epoch, kind, pinned; };
struct RlResidencyBudget { uint64_t cpu_bytes, gpu_bytes, in_flight, unknown_resources; };
struct RlResidencySnapshot {
    int64_t epoch;
    uint64_t queued, loading, ready, active, retiring, cancel_pending;
    uint64_t cpu_bytes, gpu_bytes, unknown_resources, cpu_over_budget, gpu_over_budget, stale_events, failed;
};

extern "C" {
int32_t rl_client_runtime_admission_begin(RlRuntime*, int64_t, RlAdmissionInput, RlAdmissionDecision*);
int32_t rl_client_runtime_admission_event(RlRuntime*, uint64_t, int64_t, int64_t);
int32_t rl_client_runtime_admission_snapshot(const RlRuntime*, RlAdmissionSnapshot*);
int32_t rl_client_runtime_admission_dependencies(RlRuntime*, uint64_t, int64_t, const RlResidencyDescriptor*, size_t, const RlResourceKey*, size_t);
int32_t rl_client_runtime_admission_release_dependencies(RlRuntime*, const RlResourceKey*, size_t, RlResourceKey*, size_t, size_t*);
int32_t rl_client_runtime_admission_graph_snapshot(const RlRuntime*, RlAdmissionGraphSnapshot*);
uint32_t rl_client_runtime_residency_schema();
int32_t rl_client_runtime_residency_catalog(RlRuntime*, const RlResidencyDescriptor*, size_t, const RlResourceKey*, size_t);
int32_t rl_client_runtime_residency_reconcile(RlRuntime*, const RlResidencyWanted*, size_t, int64_t);
int32_t rl_client_runtime_residency_events(RlRuntime*, const RlResidencyEvent*, size_t);
int32_t rl_client_runtime_residency_retry(RlRuntime*, const RlResourceKey*, size_t, int64_t);
int32_t rl_client_runtime_residency_step(RlRuntime*, int64_t, RlResidencyBudget, RlResidencyAction*, size_t, size_t*);
int32_t rl_client_runtime_residency_snapshot(const RlRuntime*, RlResidencyBudget, RlResidencySnapshot*);
}

static_assert(sizeof(RlResourceKey)==32);
static_assert(sizeof(RlResidencyDescriptor)==72);
static_assert(sizeof(RlResidencyAction)==64);
static_assert(sizeof(RlAdmissionInput)==80);
static_assert(sizeof(RlAdmissionSnapshot)==72);
static_assert(sizeof(RlAdmissionGraphSnapshot)==72);
