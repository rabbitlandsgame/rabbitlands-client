#include "client_runtime.h"
#include "client_residency.h"
#include "client_flights.h"
#include "../../native_crowd/src/native_spell_flight_geometry.h"
#include <godot_cpp/classes/class_db_singleton.hpp>
#include "../../shared/cape_constraint_math.h"
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <gdextension_interface.h>
#include <godot_cpp/godot.hpp>
#include <limits>
#include <cmath>
#include <algorithm>
#include <utility>
#include <chrono>
#include <godot_cpp/core/object.hpp>
#include <godot_cpp/classes/ref.hpp>
#include <godot_cpp/variant/transform3d.hpp>
#include <godot_cpp/variant/quaternion.hpp>

using namespace godot;

namespace {
using PoseClock = std::chrono::steady_clock;
uint64_t pose_elapsed_us(PoseClock::time_point start) {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(PoseClock::now() - start).count());
}
struct PoseTimeScope {
    uint64_t &counter;
    PoseClock::time_point began = PoseClock::now();
    explicit PoseTimeScope(uint64_t &value) : counter(value) {}
    ~PoseTimeScope() { counter += pose_elapsed_us(began); }
};
}

RabbitLandsClientRuntime::RabbitLandsClientRuntime() {
    owner_thread = OS::get_singleton()->get_thread_caller_id();
    const Dictionary version = Engine::get_singleton()->get_version_info();
    template_bone_commit = OS::get_singleton()->has_feature("template") &&
        String(version.get("hash", "")) == "ed1daf0bf001b61586d9930840f2f1394092c079";
    if (rl_client_runtime_abi() == 1) core = rl_client_runtime_create();
}
RabbitLandsClientRuntime::~RabbitLandsClientRuntime() { rl_client_runtime_destroy(core); }
bool RabbitLandsClientRuntime::on_owner_thread() const {
    // owner_thread is immutable after construction. Foreign calls never read
    // mutable counters, buffers, status or guard flags and never change them.
    return OS::get_singleton()->get_thread_caller_id() == owner_thread;
}
bool RabbitLandsClientRuntime::can_mutate() {
    if (!on_owner_thread()) return false;
    if (!core || mounted_operation) {
        last_status = 1;
        if (mounted_operation) ++reentrant_rejections;
        return false;
    }
    return true;
}
RabbitLandsClientRuntime::MountedOperationGuard::MountedOperationGuard(RabbitLandsClientRuntime &value) : owner(value) {
    owner.mounted_operation = true; owner.cancel_mounted_apply = false;
}
RabbitLandsClientRuntime::MountedOperationGuard::~MountedOperationGuard() { owner.finish_mounted_operation(); }
void RabbitLandsClientRuntime::finish_mounted_operation() {
    const int32_t status = last_status;
    mounted_operation = false;
    // Lifecycle releases are accepted during a callback, but core/bindings and
    // reusable outputs stay untouched until the complete owned operation ends.
    auto removed_riders = std::move(pending_rider_removals);
    auto removed_rigs = std::move(pending_rig_removals);
    pending_rider_removals.clear(); pending_rig_removals.clear();
    for (auto handle : removed_riders) unregister_mounted_rider(static_cast<int64_t>(handle));
    for (auto handle : removed_rigs) unregister_rig(static_cast<int64_t>(handle));
    cancel_mounted_apply = false;
    last_status = status;
}
bool RabbitLandsClientRuntime::resolve_mounted_target(const RiderBinding &binding,Skeleton3D *&s,Node3D *&v) const {
    if(cancel_mounted_apply) return false;
    s=Object::cast_to<Skeleton3D>(ObjectDB::get_instance(binding.skeleton));
    v=Object::cast_to<Node3D>(ObjectDB::get_instance(binding.visual));
    auto *owner=Object::cast_to<Node3D>(ObjectDB::get_instance(binding.owner));
    return s && v && owner && !s->is_queued_for_deletion() && !v->is_queued_for_deletion()
        && !owner->is_queued_for_deletion() && s->is_inside_tree() && v->is_inside_tree()
        && owner->is_inside_tree() && v->is_ancestor_of(s) && owner->get_parent()==v->get_parent()
        && static_cast<size_t>(s->get_bone_count())==binding.bones;
}
Dictionary RabbitLandsClientRuntime::runtime_info() const {
    Dictionary info;
    if (!on_owner_thread()) { info["ready"] = false; info["status"] = 1; info["reason"] = "wrong_thread"; return info; }
    info["abi"] = rl_client_runtime_abi();
    info["engine_major"] = 4; info["engine_minor"] = 7;
    info["core_version"] = "0.1.0";
    info["language"] = "rust";
    info["cpp_spell_flight_provider"] = client_runtime_owns_cpp_flight() ? "client_runtime" :
        (ClassDBSingleton::get_singleton()->class_exists("NativeSpellFlightGeometry") ? "external" : "absent");
    info["ready"] = core != nullptr;
    info["plan_calls"] = static_cast<int64_t>(calls);
    info["records_planned"] = static_cast<int64_t>(records_planned);
    info["precision"] = "f64";
    info["residency_schema"] = rl_client_runtime_residency_schema();
    info["mounted_pose_api"] = 1;
    info["mounted_profile_api"] = 1;
    info["mounted_upper_api"] = 1;
    info["mounted_cape_api"] = 1;
    info["mounted_reins_api"] = 1;
    info["rein_attempts"] = static_cast<int64_t>(rein_attempts);
    info["rein_failures"] = static_cast<int64_t>(rein_failures);
    info["rein_calls"] = static_cast<int64_t>(rein_calls);
    info["rein_us"] = static_cast<int64_t>(rein_us);
    info["mounted_cape_attempts"] = static_cast<int64_t>(mounted_cape_attempts);
    info["mounted_cape_calls"] = static_cast<int64_t>(mounted_cape_calls);
    info["mounted_cape_us"] = static_cast<int64_t>(mounted_cape_us);
    info["upper_solved"] = static_cast<int64_t>(upper_solved);
    info["upper_applied"] = static_cast<int64_t>(upper_applied);
    info["pose_upper_us"] = static_cast<int64_t>(pose_upper_us);
    info["bone_transform_commits"] = static_cast<int64_t>(bone_transform_commits);
    info["bone_guarded_trs_commits"] = static_cast<int64_t>(bone_guarded_trs_commits);
    info["bone_commit_mode"] = template_bone_commit ? "verified-template-transform" : "guarded-trs";
    info["bone_commit_verified_source"] = "ed1daf0bf001b61586d9930840f2f1394092c079";
    info["engine_scalar_bytes"] = static_cast<int64_t>(sizeof(real_t));
    info["reentrant_rejections"] = static_cast<int64_t>(reentrant_rejections);
    info["pose_calls"] = static_cast<int64_t>(pose_calls);
    info["poses_solved"] = static_cast<int64_t>(poses_solved);
    info["poses_applied"] = static_cast<int64_t>(poses_applied);
    info["pose_attempts"] = static_cast<int64_t>(pose_attempts);
    info["pose_total_us"] = static_cast<int64_t>(pose_total_us);
    info["pose_convert_us"] = static_cast<int64_t>(pose_convert_us);
    info["pose_solve_us"] = static_cast<int64_t>(pose_solve_us);
    info["pose_validate_us"] = static_cast<int64_t>(pose_validate_us);
    info["pose_apply_us"] = static_cast<int64_t>(pose_apply_us);
    info["rig_count"] = static_cast<int64_t>(rig_sizes.size());
    info["mounted_rider_count"] = static_cast<int64_t>(riders.size());
    info["rest_layout"] = "column-major-affine-12";
    info["pose_layout"] = "position-xyz,quaternion-xyzw,scale-xyz";
    return info;
}
int64_t RabbitLandsClientRuntime::get_last_status() const { return on_owner_thread() ? last_status : 1; }
int64_t RabbitLandsClientRuntime::reset_epoch(int64_t epoch) {
    if (!on_owner_thread()) return 1;
    if (mounted_operation) { cancel_mounted_apply = true; ++reentrant_rejections; last_status = 1; return 1; }
    if (!can_mutate()) return 1;
    last_status = rl_client_runtime_reset(core, epoch);
    if (last_status == 0) { rig_sizes.clear(); riders.clear(); mounted_inputs.clear(); mounted_outputs.clear(); mounted_values.clear(); mounted_value_count = 0; }
    return last_status;
}
int64_t RabbitLandsClientRuntime::register_rig(const PackedInt32Array &parents, const PackedFloat64Array &rest, const PackedFloat64Array &pose) {
    if (!can_mutate()) return 0;
    if (parents.size() == 0 || parents.size() > 1024 || rest.size() != parents.size() * 12 || pose.size() != parents.size() * 10) {
        last_status = 1; return 0;
    }
    uint64_t handle = 0;
    last_status = rl_client_runtime_register_rig(core, parents.ptr(), rest.ptr(), pose.ptr(), static_cast<size_t>(parents.size()), &handle);
    if (last_status == 0) rig_sizes[handle] = static_cast<size_t>(parents.size());
    return last_status == 0 && handle <= static_cast<uint64_t>(std::numeric_limits<int64_t>::max()) ? static_cast<int64_t>(handle) : 0;
}
bool RabbitLandsClientRuntime::unregister_rig(int64_t handle) {
    if (!on_owner_thread()) return false;
    if (mounted_operation) {
        if (handle <= 0 || !rig_sizes.count(static_cast<uint64_t>(handle))) {last_status = 1; return false;}
        if (std::find(pending_rig_removals.begin(),pending_rig_removals.end(),static_cast<uint64_t>(handle))==pending_rig_removals.end()) pending_rig_removals.push_back(static_cast<uint64_t>(handle));
        cancel_mounted_apply = true; last_status = 0; return true;
    }
    if (!can_mutate()) return false;
    if (handle <= 0) { last_status = 1; return false; }
    last_status = rl_client_runtime_unregister_rig(core, static_cast<uint64_t>(handle));
    if (last_status == 0) {
        rig_sizes.erase(static_cast<uint64_t>(handle));
        for (auto i = riders.begin(); i != riders.end();) {
            if (i->second.rig == static_cast<uint64_t>(handle)) i = riders.erase(i); else ++i;
        }
    }
    return last_status == 0;
}

namespace {
Transform3D read_affine(const double *v) {
    Basis b; b.set_column(0, Vector3(v[0],v[1],v[2])); b.set_column(1, Vector3(v[3],v[4],v[5]));
    b.set_column(2, Vector3(v[6],v[7],v[8]));
    return Transform3D(b,Vector3(v[9],v[10],v[11]));
}
bool finite_values(const double *v,size_t n) {
    for(size_t i=0;i<n;++i) if(!std::isfinite(v[i])) return false;
    return true;
}
}
int64_t RabbitLandsClientRuntime::register_mounted_rider(int64_t rig,const PackedInt32Array &bones,
    const PackedFloat64Array &constants,const PackedInt32Array &thumbs,const PackedFloat64Array &grips) {
    if(!can_mutate()) return 0;
    if(sizeof(real_t)!=4 || rig<=0 || bones.size()!=38 || constants.size()!=113 || grips.size()!=thumbs.size()*4
        || riders.size()>=4096 || !rig_sizes.count(static_cast<uint64_t>(rig))) {last_status=1;return 0;}
    uint64_t handle=0;
    last_status=rl_client_runtime_register_mounted_rider(core,static_cast<uint64_t>(rig),bones.ptr(),constants.ptr(),
        thumbs.ptr(),grips.ptr(),static_cast<size_t>(thumbs.size()),&handle);
    if(last_status!=0 || handle>static_cast<uint64_t>(std::numeric_limits<int64_t>::max())) return 0;
    RiderBinding binding;binding.rig=static_cast<uint64_t>(rig);binding.bones=rig_sizes[binding.rig];
    riders.emplace(handle,binding);return static_cast<int64_t>(handle);
}
bool RabbitLandsClientRuntime::bind_mounted_rider(int64_t handle,Skeleton3D *skeleton,Node3D *visual,Node3D *owner,int64_t actor,int64_t generation) {
    if(!can_mutate()) return false;
    if(handle<=0 || !riders.count(static_cast<uint64_t>(handle)) || !skeleton || !visual || !owner
        || skeleton==visual || !visual->is_ancestor_of(skeleton) || skeleton->is_queued_for_deletion()
        || visual->is_queued_for_deletion() || owner->is_queued_for_deletion() || owner->get_parent()!=visual->get_parent() || actor<0 || generation<=0) {last_status=1;return false;}
    auto &b=riders[static_cast<uint64_t>(handle)];
    if(static_cast<size_t>(skeleton->get_bone_count())!=b.bones || b.generation>0) {last_status=1;return false;}
    b.skeleton=skeleton->get_instance_id();b.visual=visual->get_instance_id();b.owner=owner->get_instance_id();b.actor=actor;b.generation=generation;
    last_status=0;return true;
}
bool RabbitLandsClientRuntime::unregister_mounted_rider(int64_t handle) {
    if(!on_owner_thread()) return false;
    if(mounted_operation) {
        if(handle<=0 || !riders.count(static_cast<uint64_t>(handle))) {last_status=1;return false;}
        if(std::find(pending_rider_removals.begin(),pending_rider_removals.end(),static_cast<uint64_t>(handle))==pending_rider_removals.end()) pending_rider_removals.push_back(static_cast<uint64_t>(handle));
        cancel_mounted_apply=true;last_status=0;return true;
    }
    if(!can_mutate()) return false;
    if(handle<=0) {last_status=1;return false;}
    last_status=rl_client_runtime_unregister_mounted_rider(core,static_cast<uint64_t>(handle));
    riders.erase(static_cast<uint64_t>(handle));return last_status==0;
}
bool RabbitLandsClientRuntime::set_mounted_lean(int64_t handle,double degrees) {
    if(!can_mutate()) return false;
    if(handle<=0 || !riders.count(static_cast<uint64_t>(handle)) || !std::isfinite(degrees)) {last_status=1;return false;}
    last_status=rl_client_runtime_set_mounted_lean(core,static_cast<uint64_t>(handle),degrees);
    return last_status==0;
}
bool RabbitLandsClientRuntime::step_mounted_cape(Array points,Array previous,const Array &rests,const Array &lengths,
    const PackedVector3Array &collision_world,const Array &collision_pairs,
    const PackedVector3Array &collision_axes,const PackedFloat64Array &collision_spans,
    const PackedFloat64Array &collision_radii,const Array &collision_reaches,
    const Vector3 &fall,double damping,const Vector3 &forward,double plane_at,double anchor_y,
    const Transform3D &to_world,bool settled,const PackedFloat64Array &surface) {
    if(!can_mutate())return false;
    PoseTimeScope timer(mounted_cape_us);++mounted_cape_attempts;
    const rl_cape::MountedSurface sampled(surface);
    if(!sampled.valid()) {last_status=1;return false;}
    const bool ok=rl_cape::step(points,previous,rests,lengths,collision_world,collision_pairs,collision_axes,
        collision_spans,collision_radii,collision_reaches,fall,damping,forward,plane_at,anchor_y,to_world,settled,&sampled);
    last_status=ok?0:1;if(ok)++mounted_cape_calls;return ok;
}
bool RabbitLandsClientRuntime::configure_mounted_reins(int64_t handle,Node3D *reins_node,MeshInstance3D *straps,Skeleton3D *pony,
    const PackedInt32Array &bones,const PackedFloat64Array &anchors,const PackedFloat64Array &parameters,const Array &paths) {
    if(!can_mutate())return false;
    auto found=riders.find(static_cast<uint64_t>(handle));Skeleton3D *s=nullptr;Node3D *v=nullptr;
    if(handle<=0 || found==riders.end() || !resolve_mounted_target(found->second,s,v)) {last_status=2;return false;}
    auto *owner=Object::cast_to<Node3D>(ObjectDB::get_instance(found->second.owner));
    auto renderer=std::make_shared<MountedReinRenderer>();
    if(!renderer->configure(s,owner,reins_node,straps,pony,bones,anchors,parameters,paths)) {last_status=1;return false;}
    found->second.reins=std::move(renderer);last_status=0;return true;
}
Dictionary RabbitLandsClientRuntime::mounted_rein_snapshot(int64_t handle,bool geometry) const {
    Dictionary result;if(!on_owner_thread()) {result["available"]=false;result["reason"]="wrong_thread";return result;}
    auto found=riders.find(static_cast<uint64_t>(handle));
    if(handle<=0 || found==riders.end() || !found->second.reins) {result["available"]=false;return result;}
    result=found->second.reins->snapshot(geometry);result["available"]=true;
    result["lastAppliedTag"]=found->second.last_frame;result["generation"]=found->second.generation;return result;
}
bool RabbitLandsClientRuntime::configure_mounted_upper(int64_t handle,const PackedInt32Array &bones,const PackedInt32Array &chain,
    const PackedFloat64Array &definition,const Array &animations,const PackedFloat64Array &facings) {
    if(!can_mutate())return false;
    auto found=riders.find(static_cast<uint64_t>(handle));
    Skeleton3D *s=nullptr;Node3D *v=nullptr;
    if(handle<=0 || found==riders.end() || !resolve_mounted_target(found->second,s,v)) {last_status=2;return false;}
    auto upper=std::make_shared<MountedUpperSampler>();
    if(!upper->configure(s,bones,chain,definition) || !upper->set_clips(s,animations,facings)) {last_status=1;return false;}
    found->second.upper=std::move(upper);last_status=0;return true;
}
bool RabbitLandsClientRuntime::set_mounted_upper_clips(int64_t handle,const Array &animations,const PackedFloat64Array &facings) {
    if(!can_mutate())return false;
    auto found=riders.find(static_cast<uint64_t>(handle));
    Skeleton3D *s=nullptr;Node3D *v=nullptr;
    if(handle<=0 || found==riders.end() || !found->second.upper || !resolve_mounted_target(found->second,s,v)) {last_status=2;return false;}
    const bool ok=found->second.upper->set_clips(s,animations,facings);last_status=ok?0:1;return ok;
}
bool RabbitLandsClientRuntime::set_mounted_upper_capture(int64_t handle,const PackedFloat64Array &rotations) {
    if(!can_mutate())return false;
    auto found=riders.find(static_cast<uint64_t>(handle));
    if(handle<=0 || found==riders.end() || !found->second.upper) {last_status=2;return false;}
    const bool ok=found->second.upper->set_capture(rotations);last_status=ok?0:1;return ok;
}
bool RabbitLandsClientRuntime::solve_mounted_presentation_batch(const PackedInt64Array &records,const PackedFloat64Array &samples,
    const PackedFloat64Array &upper,int64_t epoch,bool apply) {
    if(!can_mutate())return false;
    if(upper.size()!=records.size()/5*5 || records.size()%5) {last_status=1;return false;}
    return solve_mounted_impl(records,samples,upper,epoch,apply);
}
bool RabbitLandsClientRuntime::solve_mounted_batch(const PackedInt64Array &records,const PackedFloat64Array &samples,
    int64_t epoch,bool apply) {
    return solve_mounted_impl(records,samples,PackedFloat64Array(),epoch,apply);
}
bool RabbitLandsClientRuntime::solve_mounted_impl(const PackedInt64Array &records,const PackedFloat64Array &samples,
    const PackedFloat64Array &upper,int64_t epoch,bool apply) {
    if(!can_mutate()) return false;
    Ref<RabbitLandsClientRuntime> keep_alive(this);
    PoseTimeScope total_time(pose_total_us);
    const auto convert_began = PoseClock::now();
    ++pose_attempts;
    MountedOperationGuard guard(*this);
    mounted_value_count=0; mounted_outputs.clear();
    if(records.size()%5 || records.size()/5>4096 || samples.size()!=records.size()/5*14) {last_status=1;return false;}
    const size_t count=static_cast<size_t>(records.size()/5);
    mounted_inputs.resize(count); mounted_outputs.resize(count);
    size_t required=0;
    for(size_t i=0;i<count;++i) {
        if(records[i*5+2]<=0) {last_status=1;mounted_outputs.clear();return false;}
        const uint64_t handle=static_cast<uint64_t>(records[i*5+2]);
        auto found=riders.find(handle);
        if(found==riders.end()) {last_status=2;mounted_outputs.clear();return false;}
        const auto &b=found->second;
        Skeleton3D *s=nullptr;Node3D *v=nullptr;
        if(!resolve_mounted_target(b,s,v)
            || records[i*5]!=b.actor || records[i*5+1]!=b.generation || records[i*5+4]<=b.last_frame) {
            last_status=2;mounted_outputs.clear();return false;
        }
        required+=17+b.bones*10;
        if(required>8388608) {last_status=1;mounted_outputs.clear();return false;}
        mounted_inputs[i]={records[i*5],records[i*5+1],handle,records[i*5+3],records[i*5+4]};
    }
    mounted_values.resize(required);
    size_t used=0;
    pose_convert_us += pose_elapsed_us(convert_began);
    const auto solve_began = PoseClock::now();
    last_status=rl_client_runtime_solve_mounted(core,mounted_inputs.data(),samples.ptr(),count,epoch,
        mounted_outputs.data(),count,mounted_values.data(),mounted_values.size(),&used);
    pose_solve_us += pose_elapsed_us(solve_began);
    if(last_status!=0 || used!=required || !finite_values(mounted_values.data(),used)) {
        if(last_status==0)last_status=1;mounted_outputs.clear();return false;
    }
    if(!upper.is_empty()) {
        const auto upper_began=PoseClock::now();
        for(size_t i=0;i<count;++i) {
            const auto found=riders.find(mounted_inputs[i].rider);
            if(found==riders.end() || !found->second.upper
                || !found->second.upper->apply(mounted_values,static_cast<size_t>(mounted_outputs[i].offset),upper.ptr()+i*5)) {
                last_status=1;mounted_outputs.clear();return false;
            }
        }
        pose_upper_us+=pose_elapsed_us(upper_began);upper_solved+=count;
    }
    // Validate every tagged complete output before the first scene mutation.
    const auto validation_began = PoseClock::now();
    for(size_t i=0;i<count;++i) {
        const auto &row=mounted_outputs[i]; const auto &input=mounted_inputs[i];const auto &b=riders[input.rider];
        if(row.id!=input.id || row.generation!=input.generation || row.epoch!=epoch || row.frame!=input.frame
            || row.bones!=b.bones || row.offset>used || 17+row.bones*10>used-row.offset
            || std::abs(read_affine(mounted_values.data()+row.offset).basis.determinant())<1e-12) {
            last_status=1;mounted_outputs.clear();return false;
        }
        for(size_t j=0;j<b.bones;++j) {
            const double *p=mounted_values.data()+row.offset+12+j*10;
            const double q=p[3]*p[3]+p[4]*p[4]+p[5]*p[5]+p[6]*p[6];
            if(q<1e-12 || std::abs(q-1.0)>0.0001 || std::abs(p[7]*p[8]*p[9])<1e-12) {
                last_status=1;mounted_outputs.clear();return false;
            }
        }
    }
    pose_validate_us += pose_elapsed_us(validation_began);
    mounted_value_count=used;++pose_calls;poses_solved+=count;
    if(!apply) return true;
    PoseTimeScope apply_time(pose_apply_us);
    for(size_t i=0;i<count;++i) {
        // Values and binding snapshots must not be references across engine calls.
        const auto row=mounted_outputs[i];const auto handle=mounted_inputs[i].rider;
        const RiderBinding binding=riders.at(handle);
        Skeleton3D *s=nullptr;Node3D *v=nullptr;
        auto valid=[&]() {return resolve_mounted_target(binding,s,v);};
        auto reject=[&]() {last_status=2;mounted_value_count=0;mounted_outputs.clear();return false;};
        if(!valid()) return reject();
        v->set_global_transform(read_affine(mounted_values.data()+row.offset));
        if(!valid()) return reject(); // set_global_transform can invoke callbacks.
        for(size_t j=0;j<binding.bones;++j) {
            const double *p=mounted_values.data()+row.offset+12+j*10;
            if(template_bone_commit && p[7]>0. && p[8]>0. && p[9]>0.) {
                // Verified template setters defer callbacks. Reflections keep
                // separate TRS because Basis decomposition can change signs.
                Basis basis(Quaternion(p[3],p[4],p[5],p[6]));
                basis.scale_local(Vector3(p[7],p[8],p[9]));
                s->set_bone_pose(static_cast<int32_t>(j),Transform3D(basis,Vector3(p[0],p[1],p[2])));
                ++bone_transform_commits;
            } else {
                if(!valid()) return reject();
                s->set_bone_pose_position(static_cast<int32_t>(j),Vector3(p[0],p[1],p[2]));
                if(!valid()) return reject();
                s->set_bone_pose_rotation(static_cast<int32_t>(j),Quaternion(p[3],p[4],p[5],p[6]));
                if(!valid()) return reject();
                s->set_bone_pose_scale(static_cast<int32_t>(j),Vector3(p[7],p[8],p[9]));
                ++bone_guarded_trs_commits;
            }
        }
        if(!valid()) return reject();
        s->force_update_all_bone_transforms();
        // skeleton_updated/transform callbacks may free nodes or request reset.
        if(!valid()) return reject();
        if(!upper.is_empty()) {
            PoseTimeScope rein_time(rein_us);++rein_attempts;
            if(!binding.reins || !binding.reins->render(s,read_affine(samples.ptr()+i*14),upper[i*5+4],valid)) {++rein_failures;return reject();}
            ++rein_calls;
        }
        riders.at(handle).last_frame=row.frame;++poses_applied;
        if(!upper.is_empty())++upper_applied;
    }
    last_status=0;return true;
}
PackedInt64Array RabbitLandsClientRuntime::mounted_pose_metadata() const {
    PackedInt64Array result;if(!on_owner_thread()) return result;result.resize(static_cast<int64_t>(mounted_outputs.size()*6));auto *p=result.ptrw();
    for(size_t i=0;i<mounted_outputs.size();++i) {
        const auto &r=mounted_outputs[i];p[i*6]=r.id;p[i*6+1]=r.generation;p[i*6+2]=r.epoch;p[i*6+3]=r.frame;
        p[i*6+4]=static_cast<int64_t>(r.offset);p[i*6+5]=static_cast<int64_t>(r.bones);
    }return result;
}
PackedFloat64Array RabbitLandsClientRuntime::mounted_pose_values() const {
    PackedFloat64Array result;if(!on_owner_thread()) return result;result.resize(static_cast<int64_t>(mounted_value_count));
    auto *p=result.ptrw();for(size_t i=0;i<mounted_value_count;++i)p[i]=mounted_values[i];return result;
}
PackedFloat64Array RabbitLandsClientRuntime::mounted_contact_errors(int64_t actor,int64_t generation,int64_t frame) const {
    PackedFloat64Array result;
    if(!on_owner_thread()) return result;
    for(const auto &row:mounted_outputs) {
        if(row.id!=actor || row.generation!=generation || row.frame!=frame) continue;
        const size_t start=static_cast<size_t>(row.offset+12+row.bones*10);
        if(start+5>mounted_value_count) return result;
        result.resize(5);auto *p=result.ptrw();for(size_t i=0;i<5;++i)p[i]=mounted_values[start+i];return result;
    }
    return result;
}

PackedInt64Array RabbitLandsClientRuntime::plan_batch(const PackedInt64Array &records, int64_t epoch, int64_t tick) {
    PackedInt64Array result;
    if (!can_mutate()) return result;
    if (records.size() % 5 || records.size() / 5 > 65536) { last_status = 1; return result; }
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
    bind_residency_methods();
    ClassDB::bind_method(D_METHOD("register_mounted_rider","rig","bones","constants","thumbs","grips"), &RabbitLandsClientRuntime::register_mounted_rider);
    ClassDB::bind_method(D_METHOD("bind_mounted_rider","rider","skeleton","visual","owner","actor","generation"), &RabbitLandsClientRuntime::bind_mounted_rider);
    ClassDB::bind_method(D_METHOD("unregister_mounted_rider","rider"), &RabbitLandsClientRuntime::unregister_mounted_rider);
    ClassDB::bind_method(D_METHOD("step_mounted_cape","points","previous","rests","lengths",
        "collision_world","collision_pairs","collision_axes","collision_spans","collision_radii","collision_reaches",
        "fall","damping","forward","plane_at","anchor_y","to_world","settled","surface"), &RabbitLandsClientRuntime::step_mounted_cape);
    ClassDB::bind_method(D_METHOD("configure_mounted_reins","rider","reins","straps","pony","bones","anchors","parameters","paths"), &RabbitLandsClientRuntime::configure_mounted_reins);
    ClassDB::bind_method(D_METHOD("mounted_rein_snapshot","rider","geometry"), &RabbitLandsClientRuntime::mounted_rein_snapshot);
    ClassDB::bind_method(D_METHOD("configure_mounted_upper","rider","bones","chain","definition","animations","facings"), &RabbitLandsClientRuntime::configure_mounted_upper);
    ClassDB::bind_method(D_METHOD("set_mounted_upper_clips","rider","animations","facings"), &RabbitLandsClientRuntime::set_mounted_upper_clips);
    ClassDB::bind_method(D_METHOD("set_mounted_upper_capture","rider","rotations"), &RabbitLandsClientRuntime::set_mounted_upper_capture);
    ClassDB::bind_method(D_METHOD("solve_mounted_presentation_batch","records","samples","upper","epoch","apply"), &RabbitLandsClientRuntime::solve_mounted_presentation_batch);
    ClassDB::bind_method(D_METHOD("set_mounted_lean","rider","degrees"), &RabbitLandsClientRuntime::set_mounted_lean);
    ClassDB::bind_method(D_METHOD("solve_mounted_batch","records","samples","epoch","apply"), &RabbitLandsClientRuntime::solve_mounted_batch);
    ClassDB::bind_method(D_METHOD("mounted_pose_metadata"), &RabbitLandsClientRuntime::mounted_pose_metadata);
    ClassDB::bind_method(D_METHOD("mounted_pose_values"), &RabbitLandsClientRuntime::mounted_pose_values);
    ClassDB::bind_method(D_METHOD("mounted_contact_errors","actor","generation","frame"), &RabbitLandsClientRuntime::mounted_contact_errors);
    ClassDB::bind_method(D_METHOD("runtime_info"), &RabbitLandsClientRuntime::runtime_info);
    ClassDB::bind_method(D_METHOD("get_last_status"), &RabbitLandsClientRuntime::get_last_status);
    ClassDB::bind_method(D_METHOD("reset_epoch", "epoch"), &RabbitLandsClientRuntime::reset_epoch);
    ClassDB::bind_method(D_METHOD("register_rig", "parents", "rest", "pose"), &RabbitLandsClientRuntime::register_rig);
    ClassDB::bind_method(D_METHOD("unregister_rig", "handle"), &RabbitLandsClientRuntime::unregister_rig);
    ClassDB::bind_method(D_METHOD("plan_batch", "records", "epoch", "tick"), &RabbitLandsClientRuntime::plan_batch);
}
static void initialize_runtime(ModuleInitializationLevel level) {
    if (level == MODULE_INITIALIZATION_LEVEL_SCENE) {
        ClassDB::register_class<RabbitLandsClientRuntime>();
        ClassDB::register_class<RabbitLandsSpellFlightRuntime>();
        if (!ClassDBSingleton::get_singleton()->class_exists("NativeSpellFlightGeometry")) {
            ClassDB::register_class<NativeSpellFlightGeometry>();
            client_runtime_mark_cpp_flight_owned();
        }
    }
}
static void terminate_runtime(ModuleInitializationLevel) {}
extern "C" GDExtensionBool GDE_EXPORT rl_client_runtime_library_init(GDExtensionInterfaceGetProcAddress address,
    GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject object(address, library, initialization);
    object.register_initializer(initialize_runtime); object.register_terminator(terminate_runtime);
    object.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return object.init();
}
