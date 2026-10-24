#pragma once
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/transform3d.hpp>
#include <godot_cpp/variant/vector3.hpp>
#include <algorithm>
#include <cmath>
#include <utility>
#include <vector>

namespace godot::rl_cape {
// Numeric view of the already sampled mount surface. The caller retains all
// Skeleton/Node ownership. No resource or node is stored by this arithmetic.
class MountedSurface {
    struct Envelope {
        Transform3D frame, inverse;
        Vector3 center, radii;
        std::vector<std::pair<double,double>> profile;
    };
    std::vector<Envelope> envelopes;
    double clearance=0.,idle=0.,moving=0.,gallop=0.,time=0.,ripple=1.,lift=1.,hang=0.;
    Vector3 back,side;
    bool ready=false;
    static Transform3D affine(const double *v) {
        Basis b;
        b.set_column(0,Vector3(v[0],v[1],v[2]));b.set_column(1,Vector3(v[3],v[4],v[5]));
        b.set_column(2,Vector3(v[6],v[7],v[8]));return Transform3D(b,Vector3(v[9],v[10],v[11]));
    }
public:
    // Original clamped delta; squaring first changes float Vector3 rounding.
    double step=0.;
    explicit MountedSurface(const PackedFloat64Array &values) {
        if(values.size()<17 || values.size()>4096)return;
        const double *v=values.ptr();
        for(int64_t i=0;i<values.size();++i)if(!std::isfinite(v[i]))return;
        if(v[0]!=1. || v[1]!=std::floor(v[1]) || v[1]<0. || v[1]>8.
            || v[3]<0. || v[3]>1. || v[4]<0. || v[4]>1. || v[5]<0. || v[5]>1.
            || v[16]<0. || v[16]>1./30.+1e-12)return;
        clearance=v[2];idle=v[3];moving=v[4];gallop=v[5];time=v[6];ripple=v[7];lift=v[8];hang=v[9];
        back=Vector3(v[10],v[11],v[12]);side=Vector3(v[13],v[14],v[15]);step=v[16];
        size_t at=17;
        for(int i=0;i<static_cast<int>(v[1]);++i) {
            if(at+31>static_cast<size_t>(values.size()))return;
            Envelope e;
            e.frame=affine(v+at);e.inverse=affine(v+at+12);
            e.center=Vector3(v[at+24],v[at+25],v[at+26]);e.radii=Vector3(v[at+27],v[at+28],v[at+29]);
            const double count=v[at+30];at+=31;
            if(count!=std::floor(count) || count<0. || count>64. || at+static_cast<size_t>(count)*2>static_cast<size_t>(values.size())
                || std::abs(e.frame.basis.determinant())<1e-12 || std::abs(e.inverse.basis.determinant())<1e-12
                || e.radii.x<=1e-9 || e.radii.y<=1e-9 || e.radii.z<=1e-9)return;
            for(int j=0;j<static_cast<int>(count);++j) {
                const double z=v[at++],y=v[at++];
                if(!e.profile.empty() && z>=e.profile.back().first)return;
                e.profile.emplace_back(z,y);
            }
            envelopes.push_back(std::move(e));
        }
        ready=at==static_cast<size_t>(values.size());
    }
    bool valid() const {return ready;}
    Vector3 project(Vector3 point) const {
        for(const Envelope &e:envelopes) {
            Vector3 native=e.inverse.xform(point);
            const double x=(static_cast<double>(native.x)-e.center.x)/e.radii.x,
                z=(static_cast<double>(native.z)-e.center.z)/e.radii.z;
            const double radial=x*x+z*z;
            if(radial>=1.)continue;
            double top=e.center.y+e.radii.y*std::sqrt(1.-radial);
            if(!e.profile.empty() && idle>0.) {
                double height=e.profile.back().second;
                for(size_t i=1;i<e.profile.size();++i) {
                    if(native.z>=e.profile[i].first) {
                        const auto ahead=e.profile[i-1],behind=e.profile[i];
                        const double t=std::clamp((ahead.first-native.z)/(ahead.first-behind.first),0.,1.);
                        height=ahead.second+(behind.second-ahead.second)*t;break;
                    }
                }
                top=top+(height-top)*idle;
            }
            const double margin=clearance/std::max(.01,static_cast<double>(e.frame.basis.get_column(1).length()));
            if(native.y<top+margin && static_cast<double>(native.y)>static_cast<double>(e.center.y)-static_cast<double>(e.radii.y)) {
                native.y=static_cast<real_t>(top+margin);point=e.frame.xform(native);
            }
        }
        return point;
    }
    PackedVector3Array seed(const PackedVector3Array &rest,const PackedFloat32Array &lengths) const {
        PackedVector3Array points=rest.duplicate();
        const Vector3 down=(rest[1]-rest[0]).normalized();
        const double angle=35.*3.14159265358979323846/180.;
        const Vector3 direction=(down*static_cast<real_t>(std::cos(angle))+back*static_cast<real_t>(std::sin(angle))).normalized();
        for(int64_t i=1;i<points.size();++i)points.set(i,project(points[i-1]+direction*lengths[i-1]));
        return points;
    }
    Vector3 flow(int chain,double fraction) const {
        constexpr double tau=6.28318530717958647692;
        const double phase=tau*2.2*time-fraction*4.2+static_cast<double>(chain-1)*.08;
        const Vector3 wave=Vector3(0,1,0)*static_cast<real_t>(24.*std::sin(phase)+8.*std::sin(phase*1.47))
            +back*static_cast<real_t>(12.*std::sin(phase-.6));
        const Vector3 raised=(Vector3(0,28,0)+back*45.f)*static_cast<real_t>(gallop*lift);
        const Vector3 settle=Vector3(0,-1,0)*static_cast<real_t>(28.*(1.-moving));
        return (raised+settle+wave*static_cast<real_t>(moving)*static_cast<real_t>(ripple))*static_cast<real_t>(fraction*fraction);
    }
    Vector3 limit_lift(Vector3 point,const Vector3 &root,double material_length,double fraction) const {
        constexpr double tau=6.28318530717958647692;
        const double wave=.0166*moving*(1.+gallop)*fraction*fraction*std::sin(tau*2.2*time-fraction*4.2)*ripple;
        const double sideways=static_cast<double>((point-root).dot(side));
        point+=side*static_cast<real_t>(wave-sideways);
        point.y=static_cast<real_t>(std::min(static_cast<double>(point.y),static_cast<double>(root.y)-material_length*hang));
        return project(point);
    }
};
}
