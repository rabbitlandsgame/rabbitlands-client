#include "client_runtime.h"
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <gdextension_interface.h>
#include <godot_cpp/godot.hpp>
#include <limits>

using namespace godot;

RabbitLandsClientRuntime::RabbitLandsClientRuntime() {
    owner_thread = OS::get_singleton()->get_thread_caller_id();
    if (rl_client_runtime_abi() == 1) core = rl_client_runtime_create();
}
RabbitLandsClientRuntime::~RabbitLandsClientRuntime() { rl_client_runtime_destroy(core); }
bool RabbitLandsClientRuntime::on_owner_thread() {
    if (!core || OS::get_singleton()->get_thread_caller_id() != owner_thread) {
        last_status = 1; return false;
    }
    return true;
}
Dictionary RabbitLandsClientRuntime::runtime_info() const {
    Dictionary info;
    info["abi"] = rl_client_runtime_abi();
    info["engine_major"] = 4; info["engine_minor"] = 7;
    info["core_version"] = "0.1.0";
    info["language"] = "rust";
    info["ready"] = core != nullptr;
    info["plan_calls"] = static_cast<int64_t>(calls);
    info["records_planned"] = static_cast<int64_t>(records_planned);
    info["precision"] = "f64";
    info["rest_layout"] = "column-major-affine-12";
    info["pose_layout"] = "position-xyz,quaternion-xyzw,scale-xyz";
    return info;
}
int64_t RabbitLandsClientRuntime::get_last_status() const { return last_status; }
int64_t RabbitLandsClientRuntime::reset_epoch(int64_t epoch) {
    if (!on_owner_thread()) return last_status;
    last_status = rl_client_runtime_reset(core, epoch);
    return last_status;
}
int64_t RabbitLandsClientRuntime::register_rig(const PackedInt32Array &parents, const PackedFloat64Array &rest, const PackedFloat64Array &pose) {
    if (!on_owner_thread() || parents.size() == 0 || parents.size() > 1024 || rest.size() != parents.size() * 12 || pose.size() != parents.size() * 10) {
        last_status = 1; return 0;
    }
    uint64_t handle = 0;
    last_status = rl_client_runtime_register_rig(core, parents.ptr(), rest.ptr(), pose.ptr(), static_cast<size_t>(parents.size()), &handle);
    return last_status == 0 && handle <= static_cast<uint64_t>(std::numeric_limits<int64_t>::max()) ? static_cast<int64_t>(handle) : 0;
}
bool RabbitLandsClientRuntime::unregister_rig(int64_t handle) {
    if (!on_owner_thread() || handle <= 0) { last_status = 1; return false; }
    last_status = rl_client_runtime_unregister_rig(core, static_cast<uint64_t>(handle));
    return last_status == 0;
}
PackedInt64Array RabbitLandsClientRuntime::plan_batch(const PackedInt64Array &records, int64_t epoch, int64_t tick) {
    PackedInt64Array result;
    if (!on_owner_thread() || records.size() % 5 || records.size() / 5 > 65536) { last_status = 1; return result; }
    const size_t count = static_cast<size_t>(records.size() / 5);
    inputs.resize(count); outputs.resize(count);
    for (size_t i = 0; i < count; ++i) {
        if (records[i * 5 + 2] < 0) { last_status = 1; return result; }
        inputs[i] = {records[i*5], records[i*5+1], static_cast<uint64_t>(records[i*5+2]), records[i*5+3], records[i*5+4]};
    }
    last_status = rl_client_runtime_plan(core, inputs.data(), count, epoch, tick, outputs.data(), count);
    if (last_status != 0) return result;
    result.resize(static_cast<int64_t>(count * 4));
    int64_t *target = result.ptrw();
    for (size_t i = 0; i < count; ++i) {
        target[i*4] = outputs[i].id; target[i*4+1] = outputs[i].generation;
        target[i*4+2] = outputs[i].epoch; target[i*4+3] = outputs[i].due;
    }
    ++calls; records_planned += count;
    return result;
}
void RabbitLandsClientRuntime::_bind_methods() {
    ClassDB::bind_method(D_METHOD("runtime_info"), &RabbitLandsClientRuntime::runtime_info);
    ClassDB::bind_method(D_METHOD("get_last_status"), &RabbitLandsClientRuntime::get_last_status);
    ClassDB::bind_method(D_METHOD("reset_epoch", "epoch"), &RabbitLandsClientRuntime::reset_epoch);
    ClassDB::bind_method(D_METHOD("register_rig", "parents", "rest", "pose"), &RabbitLandsClientRuntime::register_rig);
    ClassDB::bind_method(D_METHOD("unregister_rig", "handle"), &RabbitLandsClientRuntime::unregister_rig);
    ClassDB::bind_method(D_METHOD("plan_batch", "records", "epoch", "tick"), &RabbitLandsClientRuntime::plan_batch);
}
static void initialize_runtime(ModuleInitializationLevel level) {
    if (level == MODULE_INITIALIZATION_LEVEL_SCENE) ClassDB::register_class<RabbitLandsClientRuntime>();
}
static void terminate_runtime(ModuleInitializationLevel) {}
extern "C" GDExtensionBool GDE_EXPORT rl_client_runtime_library_init(GDExtensionInterfaceGetProcAddress address,
    GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject object(address, library, initialization);
    object.register_initializer(initialize_runtime); object.register_terminator(terminate_runtime);
    object.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return object.init();
}
