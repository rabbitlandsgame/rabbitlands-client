#include "mounted_upper_sampler.h"
#include <cmath>
#include <algorithm>

using namespace godot;
namespace {
bool finite_numbers(const double *values, size_t count) {
    for (size_t i=0;i<count;++i) if (!std::isfinite(values[i])) return false;
    return true;
}
Basis read_basis(const double *v) {
    Basis b;
    b.set_column(0, Vector3(v[0],v[1],v[2]));
    b.set_column(1, Vector3(v[3],v[4],v[5]));
    b.set_column(2, Vector3(v[6],v[7],v[8]));
    return b;
}
Quaternion read_rotation(const double *v) { return Quaternion(v[0],v[1],v[2],v[3]); }
bool valid_rotation(const Quaternion &q) { return q.is_finite() && q.length_squared()>1e-12; }
void write_rotation(double *v, const Quaternion &q) { v[0]=q.x;v[1]=q.y;v[2]=q.z;v[3]=q.w; }
}

bool MountedUpperSampler::configure(Skeleton3D *skeleton,const PackedInt32Array &upper_bones,
    const PackedInt32Array &parent_chain,const PackedFloat64Array &definition) {
    if (!skeleton || definition.size()!=22+parent_chain.size()*4 || upper_bones.is_empty()
        || !finite_numbers(definition.ptr(),definition.size())) return false;
    const int count=skeleton->get_bone_count();
    if (count<=0 || count>1024 || upper_bones.size()>count || parent_chain.size()>=count) return false;
    spine=skeleton->find_bone("spine_01");
    if (spine<0) return false;
    std::vector<int> expected_chain;
    int parent=skeleton->get_bone_parent(spine);
    while(parent>=0) { expected_chain.insert(expected_chain.begin(),parent);parent=skeleton->get_bone_parent(parent); }
    if (parent_chain.size()!=static_cast<int64_t>(expected_chain.size())) return false;
    for(size_t i=0;i<expected_chain.size();++i) if(parent_chain[i]!=expected_chain[i]) return false;
    std::vector<int> expected_mask;
    for(int bone=0;bone<count;++bone) {
        int ancestor=bone;
        while(ancestor>=0 && ancestor!=spine) ancestor=skeleton->get_bone_parent(ancestor);
        if(ancestor==spine) expected_mask.push_back(bone);
    }
    if(upper_bones.size()!=static_cast<int64_t>(expected_mask.size())) return false;
    for(size_t i=0;i<expected_mask.size();++i) if(upper_bones[i]!=expected_mask[i]) return false;
    neutral_spine=read_rotation(definition.ptr());
    reference_parent=read_basis(definition.ptr()+4);
    spine_rest=read_basis(definition.ptr()+13);
    if(!valid_rotation(neutral_spine) || std::abs(reference_parent.determinant())<1e-12
        || std::abs(spine_rest.determinant())<1e-12) return false;
    bone_count=static_cast<size_t>(count);mask=std::move(expected_mask);chain=std::move(expected_chain);
    parent_rests.clear();parent_defaults.clear();captured.clear();clips.clear();
    for(size_t i=0;i<chain.size();++i) {
        const Quaternion q=read_rotation(definition.ptr()+22+i*4);
        if(!valid_rotation(q))return false;
        parent_rests.push_back(skeleton->get_bone_rest(chain[i]).basis);
        parent_defaults.push_back(q);
    }
    for(int bone:mask) captured.push_back(skeleton->get_bone_pose_rotation(bone));
    return true;
}

bool MountedUpperSampler::set_clips(Skeleton3D *skeleton,const Array &animations,const PackedFloat64Array &facings) {
    if(!skeleton || static_cast<size_t>(skeleton->get_bone_count())!=bone_count
        || animations.size()!=10 || facings.size()!=10 || !finite_numbers(facings.ptr(),10)) return false;
    std::vector<Clip> next(10);
    for(int action=0;action<10;++action) {
        Clip &clip=next[action];
        if(animations[action].get_type()!=Variant::NIL) {
            clip.animation=animations[action];
            if(clip.animation.is_null()) return false;
        }
        clip.facing=facings[action];
        if(clips.size()==10 && clips[action].animation==clip.animation) {
            const double facing=clip.facing;clip=clips[action];clip.facing=facing;continue;
        }
        clip.parent_tracks.assign(chain.size(),-1);
        if(clip.animation.is_null()) continue;
        for(int track=0;track<clip.animation->get_track_count();++track) {
            if(clip.animation->track_get_type(track)!=Animation::TYPE_ROTATION_3D) continue;
            const int bone=skeleton->find_bone(clip.animation->track_get_path(track).get_concatenated_subnames());
            if(std::find(mask.begin(),mask.end(),bone)!=mask.end()) clip.rotations.push_back({bone,track});
            else {
                auto at=std::find(chain.begin(),chain.end(),bone);
                if(at!=chain.end()) clip.parent_tracks[static_cast<size_t>(at-chain.begin())]=track;
            }
        }
    }
    clips.swap(next);
    return true;
}

bool MountedUpperSampler::set_capture(const PackedFloat64Array &rotations) {
    if(rotations.size()!=static_cast<int64_t>(mask.size()*4) || !finite_numbers(rotations.ptr(),rotations.size())) return false;
    for(size_t i=0;i<mask.size();++i) if(!valid_rotation(read_rotation(rotations.ptr()+i*4))) return false;
    for(size_t i=0;i<mask.size();++i) captured[i]=read_rotation(rotations.ptr()+i*4);
    return true;
}

bool MountedUpperSampler::apply(std::vector<double> &values,size_t offset,const double *state) const {
    if(!finite_numbers(state,4) || state[0]!=std::floor(state[0]) || state[0]<-1. || state[0]>9.
        || state[1]<0. || state[2]<0. || state[2]>1. || (state[3]!=0. && state[3]!=1.)
        || offset>values.size() || values.size()-offset<17+bone_count*10 || captured.size()!=mask.size()) return false;
    if(state[0]<0.) return true;
    const int action=static_cast<int>(state[0]);
    if(clips.size()!=10 || clips[action].animation.is_null()) return false;
    const double weight=state[2];
    auto rotation=[&](int bone) { return read_rotation(values.data()+offset+12+static_cast<size_t>(bone)*10+3); };
    auto write=[&](int bone,Quaternion q) { if(!valid_rotation(q))return false;write_rotation(values.data()+offset+12+static_cast<size_t>(bone)*10+3,q);return true; };
    if(state[3]!=0.) {
        for(size_t i=0;i<mask.size();++i) if(!write(mask[i],rotation(mask[i]).slerp(captured[i],weight)))return false;
        return true;
    }
    const Clip &clip=clips[action];
    Basis source_parent;
    for(size_t i=0;i<chain.size();++i) {
        const Quaternion q=clip.parent_tracks[i]<0 ? parent_defaults[i]
            : clip.animation->rotation_track_interpolate(clip.parent_tracks[i],state[1]);
        if(!valid_rotation(q)) return false;
        source_parent=(source_parent*parent_rests[i]*Basis(q)).orthonormalized();
    }
    const Basis facing(Vector3(0,1,0),static_cast<real_t>(clip.facing*3.14159265358979323846/180.));
    const Basis parent_delta=reference_parent.inverse()*facing*source_parent;
    for(const Track &track:clip.rotations) {
        Quaternion target=clip.animation->rotation_track_interpolate(track.track,state[1]);
        if(!valid_rotation(target))return false;
        if(track.bone==spine) {
            target=(Basis(rotation(spine)*neutral_spine.inverse())*spine_rest.inverse()*parent_delta*spine_rest*Basis(target)).get_rotation_quaternion();
        }
        const auto at=std::find(mask.begin(),mask.end(),track.bone);
        const size_t index=static_cast<size_t>(at-mask.begin());
        if(!write(track.bone,captured[index].slerp(target,weight).normalized()))return false;
    }
    return true;
}
