#pragma once
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <godot_cpp/variant/string.hpp>
#include <cstdint>

namespace godot {
// SHA-256 of files and buffers for ContentDigest (src/runtime/content_digest.gd).
// Stateless and safe on any thread: every method is const, touches no engine
// object other than its arguments and results, and the Rust core runs its own
// scoped threads (never the WorkerThreadPool). Paths are absolute OS paths
// (UTF-8); the caller maps res:// and user:// first and keeps PCK paths on
// FileAccess. Digests are lowercase hex, exactly what FileAccess.get_sha256
// returns.
class RabbitLandsContentDigest : public RefCounted {
    GDCLASS(RabbitLandsContentDigest, RefCounted);
    Dictionary run(const PackedStringArray &paths, const PackedStringArray *expected, const PackedInt32Array &flags,
        int64_t threads) const;
protected:
    static void _bind_methods();
public:
    Dictionary api_info() const;
    String sha256_buffer(const PackedByteArray &bytes) const;
    Dictionary sha256_files(const PackedStringArray &paths, const PackedInt32Array &flags, int64_t threads) const;
    Dictionary verify_files(const PackedStringArray &paths, const PackedStringArray &expected,
        const PackedInt32Array &flags, int64_t threads) const;
};
}
