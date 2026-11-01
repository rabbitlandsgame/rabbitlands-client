#include "mounted_cape_projector.h"
#include "mounted_cape_body_surface.h"
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/plane.hpp>
#include <godot_cpp/variant/vector2i.hpp>
#include <godot_cpp/variant/vector3i.hpp>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <thread>
#include <atomic>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <utility>
#include <vector>

using namespace godot;
namespace {
// Persistent workers read only an immutable numeric contact batch.
const size_t CONTACT_WORKERS_LIMIT = [] {
    const unsigned cores = std::thread::hardware_concurrency();
    return cores > 3 ? std::min<size_t>(6, cores - 2) : size_t(0);
}();
class ContactWorkers {
    const size_t worker_limit;
    std::mutex submit_mutex, mutex;
    std::condition_variable begin, complete;
    std::vector<std::thread> workers;
    std::function<void(size_t, size_t, size_t)> job;
    size_t count = 0, finished = 0;
    std::atomic<size_t> next{0};
    uint64_t generation = 0;
    bool stop = false;
    void work(size_t slot) {
        uint64_t seen = 0;
        std::unique_lock<std::mutex> lock(mutex);
        for (;;) {
            begin.wait(lock, [&] { return stop || generation != seen; });
            if (stop) return;
            seen = generation;
            const auto task = job;
            const size_t total = count, width = worker_limit;
            lock.unlock();
            for (;;) {
                const size_t first = next.fetch_add(256, std::memory_order_relaxed);
                if (first >= total) break;
                task(first, std::min(first + 256, total), slot);
            }
            lock.lock();
            if (++finished == width) complete.notify_one();
        }
    }
public:
    explicit ContactWorkers(size_t limit = CONTACT_WORKERS_LIMIT) : worker_limit(limit) {}
    ~ContactWorkers() { shutdown(); }
    void run(size_t size, std::function<void(size_t, size_t, size_t)> task) {
        // A batch keeps its owning Contacts/Body Ref alive until every worker finishes.
        std::unique_lock<std::mutex> submission(submit_mutex);
        if (worker_limit < 2) {task(0, size, 0);return;}
        std::unique_lock<std::mutex> lock(mutex);
        if (workers.empty()) {
            stop = false;
            for (size_t i = 0; i < worker_limit; ++i) workers.emplace_back([this, i] { work(i); });
        }
        count = size; finished = 0; next.store(0, std::memory_order_relaxed); job = std::move(task); ++generation;
        begin.notify_all();
        complete.wait(lock, [&] { return finished == worker_limit; });
        job = {};
    }
    void shutdown() {
        std::unique_lock<std::mutex> submission(submit_mutex);
        { std::lock_guard<std::mutex> lock(mutex); stop = true; begin.notify_all(); }
        for (auto &worker : workers) if (worker.joinable()) worker.join();
        workers.clear();
    }
};
ContactWorkers contact_workers;
constexpr int COUNT = 12;
constexpr std::array<int, 9> FREE = {1, 2, 3, 5, 6, 7, 9, 10, 11};
constexpr int MAX_VERTICES = 200000, MAX_CONSTRAINTS = 200000;
using Clock = std::chrono::steady_clock;
uint64_t elapsed_us(Clock::time_point start) {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - start).count());
}
bool finite(const Vector3 &v) { return v.is_finite(); }
bool finite(const Transform3D &t) {
    return finite(t.origin) && finite(t.basis.get_column(0)) && finite(t.basis.get_column(1))
        && finite(t.basis.get_column(2)) && std::isfinite(t.basis.determinant())
        && std::abs(t.basis.determinant()) > 1e-12;
}
bool finite(const Plane &p) { return finite(p.normal) && std::isfinite(p.d); }
Variant field(const Dictionary &d, const char *name) {
    const String key(name);
    return d.has(key) ? d[key] : d.get(String("_") + key, Variant());
}
bool packed_vectors(const Variant &v, std::vector<Vector3> &out, int expected = -1) {
    if (v.get_type() != Variant::PACKED_VECTOR3_ARRAY) return false;
    const PackedVector3Array values = v;
    if (values.size() > MAX_VERTICES || (expected >= 0 && values.size() != expected)) return false;
    out.clear();
    if (!values.is_empty()) out.assign(values.ptr(), values.ptr() + values.size());
    for (const auto &p : out) if (!finite(p)) return false;
    return true;
}
template <typename T> bool packed_scalars(const Variant &v, std::vector<T> &out, int expected) {
    if (v.get_type() == Variant::PACKED_FLOAT32_ARRAY) {
        const PackedFloat32Array values = v;
        if (values.size() != expected) return false;
        out.clear();if (!values.is_empty()) out.assign(values.ptr(), values.ptr() + values.size());
    } else if (v.get_type() == Variant::PACKED_FLOAT64_ARRAY) {
        const PackedFloat64Array values = v;
        if (values.size() != expected) return false;
        out.clear();if (!values.is_empty()) out.assign(values.ptr(), values.ptr() + values.size());
    } else return false;
    for (const auto x : out) if (!std::isfinite(x)) return false;
    return true;
}
template <typename T, size_t N> bool scalar_rows(const Variant &v, std::vector<std::array<T, N>> &out, int expected) {
    if (v.get_type() != Variant::ARRAY) return false;
    const Array rows = v;
    if (rows.size() != expected) return false;
    out.resize(expected);
    std::vector<T> row;
    for (int i = 0; i < expected; ++i) {
        if (!packed_scalars(rows[i], row, N)) return false;
        std::copy(row.begin(), row.end(), out[i].begin());
    }
    return true;
}
bool active_rows(const Variant &v, std::vector<std::vector<uint8_t>> &out, int expected, int limit) {
    if (v.get_type() != Variant::ARRAY) return false;
    const Array rows = v;
    if (rows.size() != expected) return false;
    out.resize(expected);
    for (int i = 0; i < expected; ++i) {
        if (rows[i].get_type() != Variant::PACKED_INT32_ARRAY) return false;
        const PackedInt32Array row = rows[i];
        if (row.size() > limit) return false;
        int last = -1;
        for (int64_t j = 0; j < row.size(); ++j) {
            if (row[j] <= last || row[j] >= limit) return false;
            last = row[j];out[i].push_back(static_cast<uint8_t>(last));
        }
    }
    return true;
}
template <size_t N> bool valid_weights(const std::array<float, N> &row, const std::vector<uint8_t> &active) {
    std::array<bool, N> seen{};
    for (const int id : active) seen[id] = true;
    double sum = 0.;
    for (size_t i = 0; i < N; ++i) {
        if (row[i] < 0.f || row[i] > 1.001f || (row[i] > 0.f) != seen[i]) return false;
        sum += row[i];
    }
    return sum <= 1.001;
}
struct Vertex {
    Vector3 position, idle;
    std::array<float, COUNT> weights{};
    std::vector<uint8_t> active, body_active;
    std::array<Vector3, 5> body_points{};
    std::array<float, 5> body_weights{};
    float share = 0.f, norm = 0.f;
};
struct Edge {
    int a = 0, b = 0;
    float length = 0.f, norm = 0.f;
    std::vector<uint8_t> active;
    std::vector<float> weights;
    std::array<double, 9> gains{};
};
struct VirtualSample {
    std::array<int, 3> vertices{};
    std::array<float, COUNT> weights{};
    std::vector<uint8_t> active;
    Vector3 factors = Vector3(1.f / 3.f, 1.f / 3.f, 1.f / 3.f);
    bool uniform = true;
    float norm = 0.f;
};
struct Sample { int id = 0;std::array<double, 9> gains{};double norm = 0.; };
struct Template {
    std::vector<Vertex> vertices;
    std::vector<int> needed;
    std::vector<Edge> edges;
    std::vector<VirtualSample> virtuals;
    std::vector<Sample> samples;
    std::array<Vector3, COUNT> idle{}, centres{};
    std::array<std::array<float, 3>, 3> spans{};
    double edge_limit = 1.79, gap_limit = .003, strain_tolerance = .005;
    int cold_iterations = 24, warm_iterations = 12;
    bool activate_contacts = true, covered_clear = true, exact_memo = false, trusted_body = false, parallel_contacts = false, parallel_residuals = false, refresh_clear_contacts = false;
};
bool read_template(const Dictionary &d, Template &t) {
    const Variant settings = d.get("solver", Dictionary());
    if (settings.get_type() != Variant::DICTIONARY) return false;
    const Dictionary solver = settings;
    const auto scalar = [&](const char *key, double &target, double low, double high) {
        const Variant value = solver.get(key, target);
        if (value.get_type() != Variant::FLOAT && value.get_type() != Variant::INT) return false;
        target = value;
        return std::isfinite(target) && target >= low && target <= high;
    };
    const auto iterations = [&](const char *key, int &target) {
        const Variant value = solver.get(key, target);
        if (value.get_type() != Variant::INT) return false;
        const int64_t count = value;
        if (count < 2 || count > 128 || count % 2 != 0) return false;
        target = static_cast<int>(count);return true;
    };
    const Variant activation = solver.get("activate_contacts", true);
    const Variant barriers = solver.get("covered_clear", true);
    if (!scalar("edge_limit", t.edge_limit, 1., 1.8)
        || !scalar("gap_limit_m", t.gap_limit, .00001, .006)
        || !scalar("strain_tolerance", t.strain_tolerance, 0., .1)
        || !iterations("cold_iterations", t.cold_iterations)
        || !iterations("warm_iterations", t.warm_iterations)
        || activation.get_type() != Variant::BOOL || barriers.get_type() != Variant::BOOL) return false;
    t.activate_contacts = activation;
    t.covered_clear = barriers;
    const Variant memo = solver.get("exact_memo", false);
    if (memo.get_type() != Variant::BOOL) return false;
    t.exact_memo = memo;
    const Variant trusted = solver.get("trusted_body", false);
    if (trusted.get_type() != Variant::BOOL) return false;
    t.trusted_body = trusted;
    const Variant parallel = solver.get("parallel_contacts", false);
    if (parallel.get_type() != Variant::BOOL) return false;
    t.parallel_contacts = parallel;
    if (t.parallel_contacts && !t.trusted_body) return false;
    const Variant residuals = solver.get("parallel_residuals", false);
    if (residuals.get_type() != Variant::BOOL) return false;
    t.parallel_residuals = residuals;
    if (t.parallel_residuals && (!t.parallel_contacts || !t.exact_memo)) return false;
    const Variant refresh = solver.get("refresh_clear_contacts", false);
    if (refresh.get_type() != Variant::BOOL) return false;
    t.refresh_clear_contacts = refresh;
    std::vector<Vector3> positions, idle, centres, weighted_idle;
    if (!packed_vectors(field(d, "positions"), positions) || positions.empty()
        || !packed_vectors(field(d, "idle"), idle, COUNT)
        || !packed_vectors(field(d, "centres"), centres, COUNT)) return false;
    const int n = static_cast<int>(positions.size());
    std::vector<std::array<float, COUNT>> weights;
    std::vector<std::array<float, 5>> body_weights;
    std::vector<std::vector<uint8_t>> active, body_active;
    std::vector<float> shares, norms;
    if (!scalar_rows(field(d, "weights"), weights, n)
        || !scalar_rows(field(d, "body_weights"), body_weights, n)
        || !active_rows(field(d, "active"), active, n, COUNT)
        || !active_rows(field(d, "body_active"), body_active, n, 5)
        || !packed_scalars(field(d, "shares"), shares, n)
        || !packed_scalars(field(d, "norms"), norms, n)
        || !packed_vectors(field(d, "idle_weights"), weighted_idle, n)) return false;
    const Variant bp = field(d, "body_points");
    if (bp.get_type() != Variant::ARRAY) return false;
    const Array body_points = bp;
    if (body_points.size() != n) return false;
    t.vertices.resize(n);
    std::vector<Vector3> points;
    for (int i = 0; i < n; ++i) {
        if (!valid_weights(weights[i], active[i]) || !valid_weights(body_weights[i], body_active[i])
            || shares[i] < 0.f || shares[i] > 1.001f || norms[i] < 0.f
            || !packed_vectors(body_points[i], points, 5)) return false;
        auto &v = t.vertices[i];v.position = positions[i];v.idle = weighted_idle[i];
        v.weights = weights[i];v.active = std::move(active[i]);v.body_weights = body_weights[i];
        v.body_active = std::move(body_active[i]);v.share = shares[i];v.norm = norms[i];
        std::copy(points.begin(), points.end(), v.body_points.begin());
    }
    std::copy(idle.begin(), idle.end(), t.idle.begin());
    std::copy(centres.begin(), centres.end(), t.centres.begin());
    for (int chain = 0; chain < 3; ++chain) for (int link = 0; link < 3; ++link) {
        const int i = chain * 4 + link;
        t.spans[chain][link] = std::max(.02f, (centres[i] + idle[i]).distance_to(centres[i + 1] + idle[i + 1]));
    }
    const Variant nv = field(d, "needed");
    if (nv.get_type() != Variant::PACKED_INT32_ARRAY) return false;
    const PackedInt32Array needed = nv;
    if (needed.is_empty() || needed.size() > n) return false;
    std::vector<bool> prepared(n, false);
    for (int64_t i = 0; i < needed.size(); ++i) {
        const int id = needed[i];
        if (id < 0 || id >= n || prepared[id]) return false;
        prepared[id] = true;t.needed.push_back(id);
    }
    const Variant vf = field(d, "virtual_sources");
    if (vf.get_type() != Variant::ARRAY) return false;
    const Array faces = vf;
    if (faces.size() > MAX_CONSTRAINTS) return false;
    std::vector<std::array<float, COUNT>> virtual_weights;
    std::vector<std::vector<uint8_t>> virtual_active;
    std::vector<float> virtual_norms;
    if (!scalar_rows(field(d, "virtual_weights"), virtual_weights, faces.size())
        || !active_rows(field(d, "virtual_active"), virtual_active, faces.size(), COUNT)
        || !packed_scalars(field(d, "virtual_norms"), virtual_norms, faces.size())) return false;
    // Older templates retain the original sum-then-divide arithmetic. Explicit
    // factors describe a point on the rendered triangle, not a newly skinned
    // interpolated rest vertex; this also keeps the supplied weight Jacobian exact.
    std::vector<Vector3> virtual_factors;
    const Variant factors = field(d, "virtual_factors");
    if (factors.get_type() != Variant::NIL) {
        if (!packed_vectors(factors, virtual_factors, faces.size())) return false;
        for (const auto &factor : virtual_factors) {
            if (factor.x < 0.f || factor.y < 0.f || factor.z < 0.f
                || std::abs(static_cast<double>(factor.x) + factor.y + factor.z - 1.) > .00001) return false;
        }
    }
    t.virtuals.resize(faces.size());
    for (int64_t i = 0; i < faces.size(); ++i) {
        if (faces[i].get_type() != Variant::VECTOR3I || virtual_norms[i] < 0.f
            || !valid_weights(virtual_weights[i], virtual_active[i])) return false;
        const Vector3i face = faces[i];
        for (int corner = 0; corner < 3; ++corner) {
            if (face[corner] < 0 || face[corner] >= n || !prepared[face[corner]]) return false;
            t.virtuals[i].vertices[corner] = face[corner];
        }
        t.virtuals[i].weights = virtual_weights[i];t.virtuals[i].active = std::move(virtual_active[i]);
        if (!virtual_factors.empty()) {
            t.virtuals[i].factors = virtual_factors[i];
            t.virtuals[i].uniform = virtual_factors[i] == Vector3(1.f / 3.f, 1.f / 3.f, 1.f / 3.f);
        }
        t.virtuals[i].norm = virtual_norms[i];
    }
    const Variant ev = field(d, "edges");
    if (ev.get_type() != Variant::ARRAY) return false;
    const Array edges = ev;
    if (edges.is_empty() || edges.size() > MAX_CONSTRAINTS) return false;
    std::vector<float> edge_lengths, edge_norms;
    std::vector<std::vector<uint8_t>> edge_active;
    std::vector<std::array<double, 9>> edge_gains;
    if (!packed_scalars(field(d, "edge_lengths"), edge_lengths, edges.size())
        || !packed_scalars(field(d, "edge_norms"), edge_norms, edges.size())
        || !active_rows(field(d, "edge_bones"), edge_active, edges.size(), COUNT)
        || !scalar_rows(field(d, "edge_gains"), edge_gains, edges.size())) return false;
    const Variant ew = field(d, "edge_weights");
    if (ew.get_type() != Variant::ARRAY) return false;
    const Array edge_weights = ew;
    if (edge_weights.size() != edges.size()) return false;
    t.edges.resize(edges.size());
    for (int64_t i = 0; i < edges.size(); ++i) {
        if (edges[i].get_type() != Variant::VECTOR2I || edge_lengths[i] <= .000001f || edge_norms[i] < 0.f) return false;
        const Vector2i edge = edges[i];
        if (edge.x < 0 || edge.y < 0 || edge.x >= n || edge.y >= n || edge.x == edge.y
            || !prepared[edge.x] || !prepared[edge.y]) return false;
        auto &out = t.edges[i];out.a = edge.x;out.b = edge.y;out.length = edge_lengths[i];
        out.norm = edge_norms[i];out.active = std::move(edge_active[i]);out.gains = edge_gains[i];
        if (!packed_scalars(edge_weights[i], out.weights, out.active.size())) return false;
    }
    const Variant sv = field(d, "samples");
    if (sv.get_type() != Variant::PACKED_INT32_ARRAY) return false;
    const PackedInt32Array samples = sv;
    if (samples.is_empty() || samples.size() > MAX_CONSTRAINTS) return false;
    std::vector<std::array<double, 9>> sample_gains;
    std::vector<double> sample_norms;
    if (!scalar_rows(field(d, "sample_gains"), sample_gains, samples.size())
        || !packed_scalars(field(d, "sample_norms"), sample_norms, samples.size())) return false;
    t.samples.resize(samples.size());
    for (int64_t i = 0; i < samples.size(); ++i) {
        const int64_t id = samples[i];
        if ((id >= 0 && (id >= n || !prepared[id])) || (id < 0 && -id - 1 >= static_cast<int64_t>(t.virtuals.size()))
            || sample_norms[i] < 0.) return false;
        t.samples[i] = {static_cast<int>(id), sample_gains[i], sample_norms[i]};
    }
    return true;
}

struct Capsule { Vector3 a, axis;double span = 0., radius = 0.;int kind = 2;std::vector<float> reaches; };
struct Contacts {
    struct Envelope { Transform3D frame, inverse;Vector3 centre, radii;std::vector<std::pair<double, double>> profile; };
    std::vector<Capsule> capsules;
    std::vector<Envelope> mounts;
    double clearance = 0., idle = 0., scale = 1., body_margin = .015;
    Ref<RabbitLandsCapeBodySurface> body;
    bool bad = false, covered_clear = true, trusted_body = false;
    static Transform3D affine(const double *v) {
        Basis b;b.set_column(0, Vector3(v[0], v[1], v[2]));b.set_column(1, Vector3(v[3], v[4], v[5]));
        b.set_column(2, Vector3(v[6], v[7], v[8]));return Transform3D(b, Vector3(v[9], v[10], v[11]));
    }
    bool configure(const Dictionary &d, const PackedFloat64Array &mount, double world_scale,
        const Ref<RabbitLandsCapeBodySurface> &body_surface, bool keep_clear, bool trust_owner = false) {
        body = body_surface;scale = world_scale;covered_clear = keep_clear;trusted_body = trust_owner;
        if (body.is_valid() && trusted_body && !body->batch_owner_valid()) return false;
        const auto get = [&](const char *key) -> Variant {
            const Variant direct = field(d, key);
            if (direct.get_type() != Variant::NIL) return direct;
            const String name = String("collision_") + String(key);
            return d.has(name) ? d[name] : d.get(String("_") + name, Variant());
        };
        std::vector<Vector3> points, axes;
        if (!packed_vectors(get("world"), points) || !packed_vectors(get("axes"), axes)) return false;
        const Variant pv = get("pairs"), rv = get("reaches"), kv = get("kinds");
        if (pv.get_type() != Variant::ARRAY || rv.get_type() != Variant::ARRAY || kv.get_type() != Variant::PACKED_INT32_ARRAY) return false;
        const Array pairs = pv, reaches = rv;
        const PackedInt32Array kinds = kv;
        if (pairs.size() > 128 || reaches.size() != pairs.size() || axes.size() != pairs.size() || kinds.size() != pairs.size()) return false;
        std::vector<double> spans, radii;
        if (!packed_scalars(get("spans"), spans, pairs.size()) || !packed_scalars(get("radii"), radii, pairs.size())) return false;
        const Variant margin = d.get("body_margin_m", .015);
        if (margin.get_type() != Variant::FLOAT && margin.get_type() != Variant::INT) return false;
        body_margin = margin;
        if (!std::isfinite(body_margin) || body_margin < 0. || body_margin > 1.) return false;
        for (int64_t i = 0; i < pairs.size(); ++i) {
            if (pairs[i].get_type() != Variant::VECTOR2I || spans[i] < 0. || radii[i] < 0. || kinds[i] < 0 || kinds[i] > 2) return false;
            const Vector2i pair = pairs[i];
            if (pair.x < 0 || pair.y < 0 || pair.x >= static_cast<int>(points.size()) || pair.y >= static_cast<int>(points.size())) return false;
            if (reaches[i].get_type() != Variant::PACKED_FLOAT32_ARRAY) return false;
            const PackedFloat32Array reach = reaches[i];
            if (reach.size() > 4096) return false;
            Capsule c;c.a = points[pair.x];c.axis = axes[i];c.span = spans[i];c.radius = radii[i];c.kind = kinds[i];
            if (!reach.is_empty()) c.reaches.assign(reach.ptr(), reach.ptr() + reach.size());
            for (const auto r : c.reaches) if (!std::isfinite(r) || r < 0.f) return false;
            capsules.push_back(std::move(c));
        }
        if (mount.size() < 17 || mount.size() > 4096) return false;
        const double *v = mount.ptr();
        for (int64_t i = 0; i < mount.size(); ++i) if (!std::isfinite(v[i])) return false;
        if (v[0] != 1. || v[1] != std::floor(v[1]) || v[1] < 0. || v[1] > 8.
            || v[2] < 0. || v[3] < 0. || v[3] > 1. || v[4] < 0. || v[4] > 1.
            || v[5] < 0. || v[5] > 1. || v[16] < 0. || v[16] > 1. / 30. + 1e-12) return false;
        clearance = v[2];idle = v[3];size_t at = 17;
        for (int i = 0; i < static_cast<int>(v[1]); ++i) {
            if (at + 31 > static_cast<size_t>(mount.size())) return false;
            Envelope e;e.frame = affine(v + at);e.inverse = affine(v + at + 12);
            e.centre = Vector3(v[at + 24], v[at + 25], v[at + 26]);e.radii = Vector3(v[at + 27], v[at + 28], v[at + 29]);
            const double count = v[at + 30];at += 31;
            if (!finite(e.frame) || !finite(e.inverse) || e.radii.x <= 1e-9 || e.radii.y <= 1e-9 || e.radii.z <= 1e-9
                || count != std::floor(count) || count < 0. || count > 64. || at + static_cast<size_t>(count) * 2 > static_cast<size_t>(mount.size())) return false;
            for (int j = 0; j < static_cast<int>(count); ++j) {
                const double z = v[at++], y = v[at++];
                if (!e.profile.empty() && z >= e.profile.back().first) return false;
                e.profile.emplace_back(z, y);
            }
            mounts.push_back(std::move(e));
        }
        return at == static_cast<size_t>(mount.size());
    }
    Plane plane(const Vector3 &point) { return plane_core(point, bad); }
    Plane plane_core(const Vector3 &point, bool &bad) const {
        Plane result;double depth = 0.;
        if (!finite(point)) {bad = true;return result;}
        for (const auto &e : mounts) {
            const Vector3 p = e.inverse.xform(point);
            const double x = (static_cast<double>(p.x) - e.centre.x) / e.radii.x;
            const double z = (static_cast<double>(p.z) - e.centre.z) / e.radii.z;
            const double radial = x * x + z * z;
            if (radial >= 1. || static_cast<double>(p.y) <= static_cast<double>(e.centre.y) - e.radii.y) continue;
            const double root = std::sqrt(std::max(.0001, 1. - radial));
            double top = e.centre.y + e.radii.y * root;
            double dx = -e.radii.y * x / (e.radii.x * root), dz = -e.radii.y * z / (e.radii.z * root);
            if (!e.profile.empty() && idle > 0.) {
                double height = e.profile.back().second, slope = 0.;
                for (size_t i = 1; i < e.profile.size(); ++i) if (p.z >= e.profile[i].first) {
                    const auto a = e.profile[i - 1], b = e.profile[i];
                    const double u = std::clamp((a.first - p.z) / (a.first - b.first), 0., 1.);
                    height = a.second + (b.second - a.second) * u;
                    slope = (b.second - a.second) / (b.first - a.first);break;
                }
                top += (height - top) * idle;dx *= 1. - idle;dz += (slope - dz) * idle;
            }
            top += clearance / std::max(.01, static_cast<double>(e.frame.basis.get_column(1).length()));
            if (p.y >= top) continue;
            const Vector3 normal = e.inverse.basis.transposed().xform(Vector3(-dx, 1., -dz)).normalized();
            const Vector3 at = e.frame.xform(Vector3(p.x, top, p.z));
            const Plane candidate(normal, at.dot(normal));
            const double gap = -candidate.distance_to(point);
            if (gap > depth) {depth = gap;result = candidate;}
        }
        bool covered = false;
        if (body.is_valid()) {
            const Plane candidate = trusted_body ? body->trusted_body_plane_at(point) : body->body_plane_at(point);
            if (!finite(candidate)) {bad = true;return Plane();}
            covered = candidate.normal != Vector3();
            const double gap = -candidate.distance_to(point);
            if (covered && (gap > depth || (covered_clear && result.normal == Vector3()))) {
                // A clear rear-surface plane is still a unilateral barrier:
                // edge correction must not push this sample through it.
                depth = std::max(depth, gap);result = candidate;
            }
        }
        for (const auto &c : capsules) {
            if (covered && c.kind < 2) continue;
            const double travel = c.span < .000001 ? 0. : std::clamp(static_cast<double>((point - c.a).dot(c.axis)) / c.span, 0., 1.);
            double radius = c.radius;
            if (!c.reaches.empty()) {
                const double at = travel * static_cast<double>(c.reaches.size() - 1);
                const auto i = static_cast<size_t>(at), j = std::min(i + 1, c.reaches.size() - 1);
                radius = std::max(radius, static_cast<double>(c.reaches[i]) + (static_cast<double>(c.reaches[j]) - c.reaches[i]) * (at - static_cast<double>(i)));
            }
            radius = radius * scale + body_margin;
            const Vector3 near = c.a + c.axis * static_cast<real_t>(travel), away = point - near;
            const double gap = radius - away.length();
            if (gap > depth && away.length_squared() > .000001) {
                const Vector3 normal = away.normalized();
                result = Plane(normal, (near + normal * static_cast<real_t>(radius)).dot(normal));depth = gap;
            }
        }
        if (!finite(result)) bad = true;
        return result;
    }
    Vector3 project(const Vector3 &point) {
        const Plane contact = plane(point);
        return point - contact.normal * static_cast<real_t>(std::min(0., static_cast<double>(contact.distance_to(point))));
    }
};
PackedVector3Array packed(const std::vector<Vector3> &v) {
    PackedVector3Array out;out.resize(v.size());
    for (size_t i = 0; i < v.size(); ++i) out.set(i, v[i]);
    return out;
}
}

struct RabbitLandsCapeProjector::Impl {
    int64_t owner_thread = 0;
    Template data;
    bool configured = false, history = false;
    std::array<Vector3, COUNT> last{};
    Basis last_basis;
    std::vector<Vector3> world, virtual_world, edge_dual, normals;
    std::vector<double> planes, multipliers, edge_maximum;
    std::vector<Vector3> edge_base;
    double gap = 0., correction = 0., strain = 1.;
    int iterations = 0;
    uint64_t refreshed_contacts = 0;
    uint64_t project_usec = 0, prepare_usec = 0, calls = 0, rejected = 0;
    String last_error;
    std::vector<Vector3> plane_points, residual_points, batch_points;
    std::vector<Plane> batch_planes;
    std::vector<uint8_t> batch_active;
    uint64_t parallel_batches = 0, parallel_query_usec = 0, serial_updates_usec = 0, strain_scan_usec = 0, point_prep_usec = 0;
    std::vector<Plane> plane_cache;
    std::vector<uint8_t> plane_valid;
    std::vector<uint32_t> residual_epochs;
    uint32_t residual_epoch = 0;
    uint64_t plane_queries = 0, plane_hits = 0, residual_hits = 0, residual_misses = 0;
    // The exact serial access count is immutable: eligible real samples followed
    // by both endpoints of every edge. Worker scheduling never changes counters.
    std::vector<int> residual_needed;
    uint64_t residual_accesses_per_scan = 0;
    uint64_t parallel_residual_batches = 0, parallel_strain_batches = 0;
    void prepare_initial_sample_points(const std::array<Vector3, COUNT> &translations) {
        contact_workers.run(data.samples.size(), [&](size_t first, size_t end, size_t) {
            for (size_t i = first; i < end; ++i) if (batch_active[i]) {
                batch_points[i] = point(data.samples[i].id, translations);
            }
        });
    }
    void prepare_parallel_residual_points(const std::array<Vector3, COUNT> &translations) {
        ++parallel_residual_batches;
        // Every destination is unique. No epoch, counter, body query or Godot
        // API is touched by these workers; translations are frozen for the scan.
        contact_workers.run(residual_needed.size(), [&](size_t first, size_t end, size_t) {
            for (size_t i = first; i < end; ++i) {
                const int index = residual_needed[i];
                residual_points[index] = point(index, translations);
            }
        });
        contact_workers.run(data.samples.size(), [&](size_t first, size_t end, size_t) {
            for (size_t i = first; i < end; ++i) if (batch_active[i]) {
                const int index = data.samples[i].id;
                // Preserve the virtual baseline-plus-weighted-translations
                // arithmetic; do not replace it with averaged posed corners.
                batch_points[i] = index >= 0 ? residual_points[index] : point(index, translations);
            }
        });
        residual_misses += static_cast<uint64_t>(residual_needed.size());
        residual_hits += residual_accesses_per_scan - static_cast<uint64_t>(residual_needed.size());
    }
    bool parallel_residual_strain(double scale, double &maximum) {
        struct alignas(64) Maximum { double value = 1.; bool bad = false; };
        std::array<Maximum, 6> maxima{};
        ++parallel_strain_batches;
        contact_workers.run(data.edges.size(), [&](size_t first, size_t end, size_t worker) {
            auto &result = maxima[worker];
            for (size_t i = first; i < end; ++i) {
                const auto &edge = data.edges[i];
                // Vector3::distance_to evaluates (to - from).length(). Keep
                // exactly that subtraction and the original sqrt/division for
                // every edge that could increase the finite maximum.
                const Vector3 delta = residual_points[edge.b] - residual_points[edge.a];
                const real_t squared = delta.length_squared();
                const double denominator = edge.length * scale;
                const double bound = result.value * denominator;
                constexpr double rounding_guard = 1. + 4. * std::numeric_limits<real_t>::epsilon();
                if (std::isfinite(squared) && static_cast<double>(squared) * rounding_guard < bound * bound) continue;
                const double ratio = static_cast<double>(delta.length()) / denominator;
                if (!std::isfinite(ratio)) result.bad = true;
                else result.value = std::max(result.value, ratio);
            }
        });
        // Max selects an existing finite value, rather than accumulating a sum.
        // Reducing in worker-index order gives exactly the original finite max.
        maximum = 1.;
        for (const auto &result : maxima) {
            if (result.bad) return false;
            maximum = std::max(maximum, result.value);
        }
        return true;
    }
    Vector3 residual_point(int index, const std::array<Vector3, COUNT> &translations) {
        if (!data.exact_memo || index < 0) return point(index, translations);
        if (residual_epochs[index] == residual_epoch) {++residual_hits;return residual_points[index];}
        ++residual_misses;residual_epochs[index] = residual_epoch;
        return residual_points[index] = point(index, translations);
    }
    Plane query_plane(Contacts &contacts, size_t i, const Vector3 &p) {
        ++plane_queries;
        const auto same = [](const Vector3 &a, const Vector3 &b) {
            return std::memcmp(&a.x, &b.x, sizeof(real_t)) == 0
                && std::memcmp(&a.y, &b.y, sizeof(real_t)) == 0
                && std::memcmp(&a.z, &b.z, sizeof(real_t)) == 0;
        };
        if (data.exact_memo && plane_valid[i] && finite(p) && same(p, plane_points[i])) {
            ++plane_hits;return plane_cache[i];
        }
        const Plane result = contacts.plane(p);
        if (data.exact_memo && finite(p)) {plane_valid[i] = 1;plane_points[i] = p;plane_cache[i] = result;}
        return result;
    }
    void query_batch(Contacts &contacts) {
        const auto query_started = Clock::now();
        struct alignas(64) Count { uint64_t queries = 0, hits = 0; bool bad = false; };
        std::array<Count, 6> counts{};
        ++parallel_batches;
        contact_workers.run(data.samples.size(), [&](size_t first, size_t end, size_t worker) {
            auto &counter = counts[worker];
            for (size_t i = first; i < end; ++i) {
                if (!batch_active[i]) continue;
                const Vector3 &p = batch_points[i];
                ++counter.queries;
                const auto same = [](const Vector3 &a, const Vector3 &b) {
                    return std::memcmp(&a.x, &b.x, sizeof(real_t)) == 0
                        && std::memcmp(&a.y, &b.y, sizeof(real_t)) == 0
                        && std::memcmp(&a.z, &b.z, sizeof(real_t)) == 0;
                };
                if (data.exact_memo && plane_valid[i] && finite(p) && same(p, plane_points[i])) {
                    ++counter.hits; batch_planes[i] = plane_cache[i]; continue;
                }
                const Plane result = contacts.plane_core(p, counter.bad);
                if (data.exact_memo && finite(p)) {plane_valid[i] = 1;plane_points[i] = p;plane_cache[i] = result;}
                batch_planes[i] = result;
            }
        });
        for (const auto &counter : counts) {plane_queries += counter.queries;plane_hits += counter.hits;contacts.bad |= counter.bad;}
        parallel_query_usec += elapsed_us(query_started);
    }
    bool on_owner() const { return OS::get_singleton()->get_thread_caller_id() == owner_thread; }
    Vector3 point(int index, const std::array<Vector3, COUNT> &translations) const {
        Vector3 p;
        if (index < 0) {
            const auto &v = data.virtuals[-static_cast<int64_t>(index) - 1];p = virtual_world[-static_cast<int64_t>(index) - 1];
            for (const int bone : v.active) p += translations[bone] * v.weights[bone];
        } else {
            const auto &v = data.vertices[index];p = world[index];
            for (const int bone : v.active) p += translations[bone] * v.weights[bone];
        }
        return p;
    }
    float norm(int index) const {return index < 0 ? data.virtuals[-static_cast<int64_t>(index) - 1].norm : data.vertices[index].norm;}
};
RabbitLandsCapeProjector::RabbitLandsCapeProjector() : state(std::make_unique<Impl>()) {
    state->owner_thread = OS::get_singleton()->get_thread_caller_id();
}
RabbitLandsCapeProjector::~RabbitLandsCapeProjector() = default;
bool RabbitLandsCapeProjector::configure(const Dictionary &values) {
    if (!state->on_owner()) return false;
    Template candidate;
    if (!read_template(values, candidate)) {state->last_error = "invalid_template";++state->rejected;return false;}
    state->data = std::move(candidate);state->configured = true;state->history = false;
    state->world.assign(state->data.vertices.size(), Vector3());state->virtual_world.assign(state->data.virtuals.size(), Vector3());
    state->edge_dual.resize(state->data.edges.size());state->normals.resize(state->data.samples.size());
    state->planes.resize(state->data.samples.size());state->multipliers.resize(state->data.samples.size());
    state->plane_points.resize(state->data.samples.size());state->plane_cache.resize(state->data.samples.size());
    state->batch_points.resize(state->data.samples.size());state->batch_planes.resize(state->data.samples.size());
    state->batch_active.resize(state->data.samples.size());
    state->plane_valid.resize(state->data.samples.size());state->residual_points.resize(state->data.vertices.size());
    state->residual_epochs.resize(state->data.vertices.size());
    state->residual_needed.clear();state->residual_accesses_per_scan = 0;
    if (state->data.parallel_residuals) {
        std::vector<uint8_t> included(state->data.vertices.size(), 0);
        const auto include = [&](int index) {
            if (!included[index]) {included[index] = 1;state->residual_needed.push_back(index);}
        };
        for (size_t i = 0; i < state->data.samples.size(); ++i) {
            const int index = state->data.samples[i].id;
            state->batch_active[i] = state->norm(index) >= .02;
            if (state->batch_active[i] && index >= 0) {
                ++state->residual_accesses_per_scan;include(index);
            }
        }
        for (const auto &edge : state->data.edges) {
            state->residual_accesses_per_scan += 2;include(edge.a);include(edge.b);
        }
    }
    state->gap = state->correction = 0.;state->strain = 1.;state->iterations = 0;
    state->project_usec = state->prepare_usec = 0;state->last_error = "";
    return true;
}
void RabbitLandsCapeProjector::reset() {
    if (!state->on_owner()) return;
    state->history = false;
}
Dictionary RabbitLandsCapeProjector::stats() const {
    Dictionary out;
    if (!state->on_owner()) {out["ready"] = false;out["error"] = "wrong_thread";return out;}
    out["ready"] = state->configured;out["history"] = state->history;out["error"] = state->last_error;
    out["samples"] = static_cast<int64_t>(state->data.samples.size());out["edges"] = static_cast<int64_t>(state->data.edges.size());
    out["triangle_interior_samples"] = static_cast<int64_t>(state->data.virtuals.size());out["gap_m"] = state->gap;
    out["correction_m"] = state->correction;out["strain"] = state->strain;out["iterations"] = state->iterations;
    out["project_usec"] = static_cast<int64_t>(state->project_usec);out["prepare_usec"] = static_cast<int64_t>(state->prepare_usec);
    out["calls"] = static_cast<int64_t>(state->calls);out["rejected"] = static_cast<int64_t>(state->rejected);
    out["refreshed_contacts"] = static_cast<int64_t>(state->refreshed_contacts);out["refresh_clear_contacts"] = state->data.refresh_clear_contacts;out["exact_memo"] = state->data.exact_memo;out["trusted_body"] = state->data.trusted_body;
    out["point_prep_usec"] = static_cast<int64_t>(state->point_prep_usec);
    out["parallel_query_usec"] = static_cast<int64_t>(state->parallel_query_usec);out["serial_updates_usec"] = static_cast<int64_t>(state->serial_updates_usec);out["strain_scan_usec"] = static_cast<int64_t>(state->strain_scan_usec);
    out["parallel_batches"] = static_cast<int64_t>(state->parallel_batches);out["parallel_contacts"] = state->data.parallel_contacts;
    out["parallel_residuals"] = state->data.parallel_residuals;
    out["parallel_residual_batches"] = static_cast<int64_t>(state->parallel_residual_batches);
    out["parallel_strain_batches"] = static_cast<int64_t>(state->parallel_strain_batches);
    out["residual_unique_real_points"] = static_cast<int64_t>(state->residual_needed.size());
    out["plane_queries"] = static_cast<int64_t>(state->plane_queries);out["plane_memo_hits"] = static_cast<int64_t>(state->plane_hits);
    out["residual_point_hits"] = static_cast<int64_t>(state->residual_hits);out["residual_point_misses"] = static_cast<int64_t>(state->residual_misses);
    out["edge_limit"] = state->data.edge_limit;out["gap_limit_m"] = state->data.gap_limit;
    return out;
}
Dictionary RabbitLandsCapeProjector::runtime_info() const {
    Dictionary out;out["api"] = 2;out["implementation"] = "native";
    out["refresh_clear_contacts"] = true;out["kind"] = "mounted_cape_material";out["virtual_factors"] = true;out["exact_memo"] = true;out["trusted_body"] = true;out["parallel_contacts"] = true;out["parallel_residuals"] = true;out["parallel_workers"] = static_cast<int64_t>(CONTACT_WORKERS_LIMIT);out["parallel_workers_limit"] = static_cast<int64_t>(CONTACT_WORKERS_LIMIT);out["parallel_serial_fallback"] = CONTACT_WORKERS_LIMIT < 2;out["parallel_chunk"] = 256;return out;
}
Dictionary RabbitLandsCapeProjector::project(const Transform3D &world, const Transform3D &frame,
    const Array &roots_in, const Array &bodies_in, const PackedVector3Array &incoming,
    const Dictionary &collision_data, const PackedFloat64Array &mount_data,
    const Ref<RabbitLandsCapeBodySurface> &body, bool debug_buffers) {
    Dictionary out;
    const auto fail = [&](const char *reason) {
        Dictionary failure;failure["ok"] = false;failure["error"] = reason;
        if (state->on_owner()) {state->last_error = reason;++state->rejected;}
        return failure;
    };
    if (!state->on_owner()) return fail("wrong_thread");
    const auto started = Clock::now();
    if (!state->configured || !finite(world) || !finite(frame) || roots_in.size() != 3 || bodies_in.size() != 5 || incoming.size() != COUNT) return fail("invalid_frame");
    std::array<Transform3D, 3> roots;
    std::array<Transform3D, 5> bodies;
    for (int i = 0; i < 3; ++i) {
        if (roots_in[i].get_type() != Variant::TRANSFORM3D) return fail("invalid_root");
        roots[i] = roots_in[i];if (!finite(roots[i])) return fail("invalid_root");
    }
    for (int i = 0; i < 5; ++i) {
        if (bodies_in[i].get_type() != Variant::TRANSFORM3D) return fail("invalid_body");
        bodies[i] = bodies_in[i];if (!finite(bodies[i])) return fail("invalid_body");
    }
    std::array<Vector3, COUNT> translations;
    for (int i = 0; i < COUNT; ++i) {translations[i] = incoming[i];if (!finite(translations[i])) return fail("invalid_translation");}
    Contacts contacts;
    const double scale = world.basis.get_column(0).length();
    if (!contacts.configure(collision_data, mount_data, scale, body, state->data.covered_clear, state->data.trusted_body)) return fail("invalid_contacts");
    for (int chain = 0; chain < 3; ++chain) translations[chain * 4] = Vector3();
    const bool cold = !state->history;
    const Basis basis = world.basis * frame.basis;
    if (!finite(Transform3D(basis, Vector3()))) return fail("invalid_combined_basis");
    if (!cold) {
        const Basis carry = basis * state->last_basis.inverse();
        for (const int bone : FREE) translations[bone] = carry.xform(state->last[bone]).lerp(translations[bone], .35f);
    }
    const auto &data = state->data;
    state->plane_queries = state->plane_hits = state->residual_hits = state->residual_misses = 0;
    state->residual_epoch = 0;state->parallel_batches = 0;state->parallel_query_usec = state->serial_updates_usec = state->strain_scan_usec = state->point_prep_usec = 0;
    state->parallel_residual_batches = state->parallel_strain_batches = 0;
    std::fill(state->plane_valid.begin(), state->plane_valid.end(), 0);
    std::fill(state->residual_epochs.begin(), state->residual_epochs.end(), 0);
    const Transform3D rigid = world * frame;
    for (int chain = 0; chain < 3; ++chain) {
        std::array<Vector3, 4> line;
        for (int link = 0; link < 4; ++link) {
            const int i = chain * 4 + link;
            const Transform3D base = link == 0 ? world * roots[chain] : rigid;
            line[link] = base.xform(data.centres[i] + data.idle[i]) + translations[i];
        }
        for (int link = 1; link < 3; ++link) {
            const double a = data.spans[chain][link - 1], b = data.spans[chain][link];
            const Vector3 target = line[link - 1].lerp(line[link + 1], static_cast<real_t>(a / (a + b)));
            translations[chain * 4 + link] += ((target - line[link]) * .12f).limit_length(.02f);
        }
    }
    for (const int index : data.needed) {
        const auto &v = data.vertices[index];
        double upper_share = 0.;Vector3 upper_idle, upper;
        for (int chain = 0; chain < 3; ++chain) {
            const int i = chain * 4;const float weight = v.weights[i];upper_share += weight;
            upper_idle += data.idle[i] * weight;upper += roots[chain].xform(v.position + data.idle[i]) * weight;
        }
        Vector3 base = frame.xform(v.position) * static_cast<real_t>(v.share - upper_share)
            + frame.basis.xform(v.idle - upper_idle) + upper;
        for (const int bone : v.body_active) base += bodies[bone].basis.xform(v.body_points[bone]) + bodies[bone].origin * v.body_weights[bone];
        state->world[index] = world.xform(base);
        if (!finite(state->world[index])) return fail("nonfinite_skin");
    }
    for (size_t i = 0; i < data.virtuals.size(); ++i) {
        const auto &v = data.virtuals[i];
        state->virtual_world[i] = v.uniform
            ? (state->world[v.vertices[0]] + state->world[v.vertices[1]] + state->world[v.vertices[2]]) / 3.f
            : state->world[v.vertices[0]] * v.factors.x + state->world[v.vertices[1]] * v.factors.y + state->world[v.vertices[2]] * v.factors.z;
    }
    const uint64_t prepared_us = elapsed_us(started);
    std::fill(state->edge_dual.begin(), state->edge_dual.end(), Vector3());
    std::fill(state->normals.begin(), state->normals.end(), Vector3());
    std::fill(state->planes.begin(), state->planes.end(), 0.);
    std::fill(state->multipliers.begin(), state->multipliers.end(), 0.);
    if (data.parallel_contacts) {
        const auto points_started = Clock::now();
        if (data.parallel_residuals) state->prepare_initial_sample_points(translations);
        else for (size_t i = 0; i < data.samples.size(); ++i) {
            const int index = data.samples[i].id;
            state->batch_active[i] = state->norm(index) >= .02;
            if (state->batch_active[i]) state->batch_points[i] = state->point(index, translations);
        }
        state->point_prep_usec += elapsed_us(points_started);
        state->query_batch(contacts);
        for (size_t i = 0; i < data.samples.size(); ++i) if (state->batch_active[i]) {
            state->normals[i] = state->batch_planes[i].normal;state->planes[i] = state->batch_planes[i].d;
        }
    } else {
    for (size_t i = 0; i < data.samples.size(); ++i) {
        const int index = data.samples[i].id;
        if (state->norm(index) < .02) continue;
        const Plane plane = state->query_plane(contacts, i, state->point(index, translations));
        state->normals[i] = plane.normal;state->planes[i] = plane.d;
    }
    }
    state->edge_base.resize(data.edges.size());state->edge_maximum.resize(data.edges.size());
    for (size_t i = 0; i < data.edges.size(); ++i) {
        const auto &edge = data.edges[i];
        state->edge_base[i] = state->world[edge.a] - state->world[edge.b];
        state->edge_maximum[i] = edge.length * scale * data.edge_limit;
    }
    state->refreshed_contacts = 0;
    double correction = 0., gap = 0., strain = 1.;int iterations = 0;
    for (int iteration = 0; iteration < (cold ? data.cold_iterations : data.warm_iterations); ++iteration) {
        iterations = iteration + 1;
        const auto updates_started = Clock::now();
        for (size_t i = 0; i < data.edges.size(); ++i) {
            const auto &edge = data.edges[i];
            if (edge.norm < .0000001) continue;
            Vector3 delta = state->edge_base[i];
            for (size_t slot = 0; slot < edge.active.size(); ++slot) delta += translations[edge.active[slot]] * edge.weights[slot];
            const double norm = edge.norm;delta += state->edge_dual[i] * static_cast<real_t>(norm);
            const double length = delta.length(), maximum = state->edge_maximum[i];
            if (norm < .0000001) continue;
            const Vector3 dual = delta * static_cast<real_t>(std::max(0., length - maximum) / std::max(length, .000001) / norm);
            const Vector3 change = state->edge_dual[i] - dual;
            if (change.length_squared() > .000000000001) for (size_t slot = 0; slot < FREE.size(); ++slot) {
                translations[FREE[slot]] += change * static_cast<real_t>(edge.gains[slot]);
            }
            state->edge_dual[i] = dual;
        }
        for (size_t i = 0; i < data.samples.size(); ++i) {
            const auto &sample = data.samples[i];const double norm = sample.norm;
            if (norm < .0001 || state->norm(sample.id) < .02) continue;
            if (state->normals[i] == Vector3()) continue;
            const Vector3 point = state->point(sample.id, translations);
            const double distance = state->planes[i] - point.dot(state->normals[i]);
            const double multiplier = std::max(0., state->multipliers[i] + distance / norm);
            const Vector3 change = state->normals[i] * static_cast<real_t>(multiplier - state->multipliers[i]);
            if (change.length_squared() > .000000000001) {
                real_t maximum_move_squared = 0.;
                for (size_t slot = 0; slot < FREE.size(); ++slot) {
                    const Vector3 move = change * static_cast<real_t>(sample.gains[slot]);
                    translations[FREE[slot]] += move;
                    maximum_move_squared = std::max(maximum_move_squared, move.length_squared());
                }
                correction = std::max(correction, static_cast<double>(Math::sqrt(maximum_move_squared)));
            }
            state->multipliers[i] = multiplier;
        }
        state->serial_updates_usec += elapsed_us(updates_started);
        if (iteration % 2 == 0) continue;
        ++state->residual_epoch;
        if (data.parallel_residuals) {
            const auto points_started = Clock::now();
            state->prepare_parallel_residual_points(translations);
            state->point_prep_usec += elapsed_us(points_started);
        }
        gap = 0.;
        if (data.parallel_contacts && data.activate_contacts) {
            const auto points_started = Clock::now();
            // The optional worker preparation already populated these exact
            // sample slots. The legacy owner path remains unchanged.
            if (!data.parallel_residuals) for (size_t i = 0; i < data.samples.size(); ++i) {
                const auto &sample = data.samples[i];
                state->batch_active[i] = state->norm(sample.id) >= .02;
                if (state->batch_active[i]) state->batch_points[i] = state->residual_point(sample.id, translations);
            }
            state->point_prep_usec += elapsed_us(points_started);
            state->query_batch(contacts);
            for (size_t i = 0; i < data.samples.size(); ++i) if (state->batch_active[i]) {
                const Vector3 point = state->batch_points[i];
                const Plane contact = state->batch_planes[i];
                const Vector3 projected = point - contact.normal * static_cast<real_t>(std::min(0., static_cast<double>(contact.distance_to(point))));
                const double residual_gap = static_cast<double>(point.distance_to(projected));
                gap = std::max(gap, residual_gap);
                if (contact.normal != Vector3() && (state->normals[i] == Vector3()
                    || (data.refresh_clear_contacts && state->multipliers[i] == 0.
                        && point.dot(state->normals[i]) >= state->planes[i]
                        && contact.distance_to(point) < -data.gap_limit))) {
                    if (state->normals[i] != Vector3()) ++state->refreshed_contacts;
                    // The previous clear plane has no stored dual correction.
                    // A newly encountered body region can replace that inactive
                    // barrier without changing the current primal/history.
                    state->normals[i] = contact.normal;state->planes[i] = contact.d;
                }
            }
        } else for (size_t i = 0; i < data.samples.size(); ++i) {
            const auto &sample = data.samples[i];
            if (state->norm(sample.id) < .02) continue;
            const Vector3 point = data.parallel_residuals ? state->batch_points[i] : state->residual_point(sample.id, translations);
            if (data.activate_contacts) {
                const Plane contact = state->query_plane(contacts, i, point);
                const Vector3 projected = point - contact.normal * static_cast<real_t>(std::min(0., static_cast<double>(contact.distance_to(point))));
                const double residual_gap = static_cast<double>(point.distance_to(projected));
                gap = std::max(gap, residual_gap);
                // Edge correction can move an initially clear sample into
                // clothing. Activate that contact before the next sweep.
                if (contact.normal != Vector3() && (state->normals[i] == Vector3()
                    || (data.refresh_clear_contacts && state->multipliers[i] == 0.
                        && point.dot(state->normals[i]) >= state->planes[i]
                        && contact.distance_to(point) < -data.gap_limit))) {
                    if (state->normals[i] != Vector3()) ++state->refreshed_contacts;
                    // The previous clear plane has no stored dual correction.
                    // A newly encountered body region can replace that inactive
                    // barrier without changing the current primal/history.
                    state->normals[i] = contact.normal;state->planes[i] = contact.d;
                }
            } else gap = std::max(gap, static_cast<double>(point.distance_to(contacts.project(point))));
        }
        const auto strain_started = Clock::now();
        strain = 1.;
        if (data.parallel_residuals) {
            if (!state->parallel_residual_strain(scale, strain)) return fail("nonfinite_residual_strain");
        } else for (const auto &edge : data.edges) strain = std::max(strain, static_cast<double>(state->residual_point(edge.a, translations).distance_to(state->residual_point(edge.b, translations))) / (edge.length * scale));
        state->strain_scan_usec += elapsed_us(strain_started);
        if (gap < data.gap_limit && strain < data.edge_limit + data.strain_tolerance) break;
    }
    for (const auto &v : translations) if (!finite(v)) return fail("nonfinite_output");
    if (contacts.bad || !std::isfinite(gap) || !std::isfinite(strain) || !std::isfinite(correction)) return fail("nonfinite_contact");
    // Commit warm history only after the complete candidate has validated.
    state->last = translations;state->last_basis = basis;state->history = true;
    state->gap = gap;state->strain = strain;state->correction = correction;state->iterations = iterations;
    state->prepare_usec = prepared_us;state->project_usec = elapsed_us(started);state->last_error = "";++state->calls;
    PackedVector3Array result;result.resize(COUNT);
    for (int i = 0; i < COUNT; ++i) result.set(i, translations[i]);
    out["ok"] = true;out["translations"] = result;out["stats"] = stats();
    if (debug_buffers) {
        out["world"] = packed(state->world);out["virtual_world"] = packed(state->virtual_world);
        std::vector<Vector3> posed_world(state->world.size()), posed_virtual(data.virtuals.size());
        for (const int index : data.needed) posed_world[index] = state->point(index, translations);
        for (size_t i = 0; i < data.virtuals.size(); ++i) posed_virtual[i] = state->point(-static_cast<int>(i) - 1, translations);
        out["posed_world"] = packed(posed_world);out["posed_virtual_world"] = packed(posed_virtual);
    }
    return out;
}
void RabbitLandsCapeProjector::_bind_methods() {
    ClassDB::bind_method(D_METHOD("configure", "template"), &RabbitLandsCapeProjector::configure);
    ClassDB::bind_method(D_METHOD("project", "world", "lower_frame", "root_frames", "body_poses", "translations", "collisions", "mount_surface", "body_surface", "debug_buffers"), &RabbitLandsCapeProjector::project, DEFVAL(false));
    ClassDB::bind_method(D_METHOD("reset"), &RabbitLandsCapeProjector::reset);
    ClassDB::bind_method(D_METHOD("stats"), &RabbitLandsCapeProjector::stats);
    ClassDB::bind_method(D_METHOD("runtime_info"), &RabbitLandsCapeProjector::runtime_info);
}

void rl_cape_shutdown_contact_workers() { contact_workers.shutdown(); }
