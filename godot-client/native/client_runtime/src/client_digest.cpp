#include "client_digest.h"
#include "client_core.h"
#include <godot_cpp/core/class_db.hpp>
#include <algorithm>
#include <chrono>
#include <thread>
#include <vector>

using namespace godot;

namespace {
constexpr int32_t RESULT_OK = 0;
constexpr int32_t RESULT_INVALID = 1;
constexpr int32_t STATUS_INTERNAL = 4;

const char *backend_name(uint32_t code) {
    switch (code) {
        case 1: return "sha_ni";
        case 2: return "portable";
        default: return "unavailable";
    }
}

String hex(const uint8_t *digest) {
    static const char digits[] = "0123456789abcdef";
    char text[65];
    for (int i = 0; i < 32; ++i) {
        text[i * 2] = digits[digest[i] >> 4];
        text[i * 2 + 1] = digits[digest[i] & 15];
    }
    text[64] = 0;
    return String(text);
}

// Exactly 64 lowercase hex digits; anything else is "absent" and never
// passes, as `FileAccess.get_sha256(path) != expected` never matched it.
bool parse_expected(const String &text, uint8_t *out) {
    if (text.length() != 64) return false;
    for (int64_t i = 0; i < 64; ++i) {
        const char32_t c = text[i];
        int value;
        if (c >= U'0' && c <= U'9') value = static_cast<int>(c - U'0');
        else if (c >= U'a' && c <= U'f') value = static_cast<int>(c - U'a') + 10;
        else return false;
        if (i % 2 == 0) out[i / 2] = static_cast<uint8_t>(value << 4);
        else out[i / 2] |= static_cast<uint8_t>(value);
    }
    return true;
}
}

Dictionary RabbitLandsContentDigest::api_info() const {
    Dictionary info;
    info["digest_api"] = static_cast<int64_t>(rl_digest_api());
    info["sha256_backend"] = String(backend_name(rl_digest_backend()));
    info["cpu_sha_ni"] = rl_digest_cpu_sha_ni() != 0;
    info["logical_cpus"] = static_cast<int64_t>(std::thread::hardware_concurrency());
    uint64_t max_files = 0, max_path_bytes = 0, read_bytes = 0;
    uint32_t max_threads = 0;
    if (rl_digest_limits(&max_files, &max_threads, &max_path_bytes, &read_bytes) == RESULT_OK) {
        info["max_files"] = static_cast<int64_t>(max_files);
        info["max_threads"] = static_cast<int64_t>(max_threads);
        info["max_path_bytes"] = static_cast<int64_t>(max_path_bytes);
        info["read_bytes"] = static_cast<int64_t>(read_bytes);
    }
    info["flags"] = static_cast<int64_t>(1); // FOLD_CRLF
    // Phase B (BLAKE3 equivalence index) is not built: every row is SHA-256.
    Dictionary index;
    index["supported"] = false;
    index["active"] = false;
    info["index"] = index;
    return info;
}

String RabbitLandsContentDigest::sha256_buffer(const PackedByteArray &bytes) const {
    uint8_t digest[32];
    if (rl_digest_sha256_buffer(bytes.ptr(), static_cast<size_t>(bytes.size()), digest) != RESULT_OK) return String();
    return hex(digest);
}

Dictionary RabbitLandsContentDigest::sha256_files(const PackedStringArray &paths, const PackedInt32Array &flags,
        int64_t threads) const {
    return run(paths, nullptr, flags, threads);
}

Dictionary RabbitLandsContentDigest::verify_files(const PackedStringArray &paths, const PackedStringArray &expected,
        const PackedInt32Array &flags, int64_t threads) const {
    return run(paths, &expected, flags, threads);
}

Dictionary RabbitLandsContentDigest::run(const PackedStringArray &paths, const PackedStringArray *expected,
        const PackedInt32Array &flags, int64_t threads) const {
    const auto began = std::chrono::steady_clock::now();
    const int64_t count = paths.size();
    const size_t rows = static_cast<size_t>(count);
    std::vector<CharString> text;
    text.reserve(rows);
    for (int64_t i = 0; i < count; ++i) text.push_back(paths[i].utf8());
    std::vector<const uint8_t *> pointers(rows);
    std::vector<size_t> lengths(rows);
    for (size_t i = 0; i < rows; ++i) {
        pointers[i] = reinterpret_cast<const uint8_t *>(text[i].get_data());
        lengths[i] = static_cast<size_t>(text[i].length());
    }
    std::vector<uint32_t> row_flags(rows, 0);
    for (int64_t i = 0; i < std::min<int64_t>(count, flags.size()); ++i) row_flags[i] = static_cast<uint32_t>(flags[i]);
    const uint32_t thread_count = static_cast<uint32_t>(std::clamp<int64_t>(threads, 1, 64));
    std::vector<uint8_t> digests(rows * 32, 0), folded(rows, 0), ok(rows, 0);
    std::vector<int32_t> status(rows, STATUS_INTERNAL);
    uint64_t bytes = 0;
    uint32_t used = 0;
    int32_t code = RESULT_OK;
    if (expected == nullptr) {
        code = rl_digest_sha256_files(pointers.data(), lengths.data(), row_flags.data(), rows, thread_count,
            digests.data(), status.data(), folded.data(), &bytes, &used);
    } else if (expected->size() != count) {
        code = RESULT_INVALID;
    } else {
        std::vector<uint8_t> wanted(rows * 32, 0), present(rows, 0);
        for (size_t i = 0; i < rows; ++i)
            present[i] = parse_expected((*expected)[static_cast<int64_t>(i)], wanted.data() + i * 32) ? 1 : 0;
        code = rl_digest_verify_files(pointers.data(), lengths.data(), row_flags.data(), wanted.data(), present.data(),
            rows, thread_count, digests.data(), status.data(), folded.data(), ok.data(), &bytes, &used);
    }
    if (code != RESULT_OK) {
        // Whole-call failure: every row reads as an internal failure.
        std::fill(status.begin(), status.end(), STATUS_INTERNAL);
        std::fill(folded.begin(), folded.end(), 0);
        std::fill(ok.begin(), ok.end(), 0);
        bytes = 0;
        used = 0;
    }
    PackedStringArray out_digests;
    PackedInt32Array out_status;
    PackedByteArray out_folded;
    out_digests.resize(count);
    out_status.resize(count);
    out_folded.resize(count);
    String *digest_rows = out_digests.ptrw();
    int32_t *status_rows = out_status.ptrw();
    uint8_t *folded_rows = out_folded.ptrw();
    for (size_t i = 0; i < rows; ++i) {
        status_rows[i] = status[i];
        folded_rows[i] = folded[i];
        digest_rows[i] = status[i] == 0 ? hex(digests.data() + i * 32) : String();
    }
    Dictionary result;
    result["result"] = code;
    result["digests"] = out_digests;
    result["status"] = out_status;
    result["folded"] = out_folded;
    if (expected != nullptr) {
        PackedByteArray out_ok;
        out_ok.resize(count);
        uint8_t *ok_rows = out_ok.ptrw();
        for (size_t i = 0; i < rows; ++i) ok_rows[i] = ok[i];
        result["ok"] = out_ok;
    }
    result["bytes"] = static_cast<int64_t>(bytes);
    result["threads"] = static_cast<int64_t>(used);
    result["backend"] = String(backend_name(rl_digest_backend()));
    result["elapsed_us"] = static_cast<int64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - began).count());
    return result;
}

void RabbitLandsContentDigest::_bind_methods() {
    ClassDB::bind_method(D_METHOD("api_info"), &RabbitLandsContentDigest::api_info);
    ClassDB::bind_method(D_METHOD("sha256_buffer", "bytes"), &RabbitLandsContentDigest::sha256_buffer);
    ClassDB::bind_method(D_METHOD("sha256_files", "paths", "flags", "threads"), &RabbitLandsContentDigest::sha256_files,
        DEFVAL(PackedInt32Array()), DEFVAL(1));
    ClassDB::bind_method(D_METHOD("verify_files", "paths", "expected", "flags", "threads"),
        &RabbitLandsContentDigest::verify_files, DEFVAL(PackedInt32Array()), DEFVAL(1));
}
