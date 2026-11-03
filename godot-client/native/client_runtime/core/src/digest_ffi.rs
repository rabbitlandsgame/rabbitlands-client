//! C ABI of the content digest (`digest.rs`), used by the `RabbitLandsContentDigest`
//! adapter. Stateless: no runtime handle, callable from any thread. Every entry
//! is wrapped in `catch_unwind`; outputs are written only after the whole batch
//! succeeded, so INVALID/INTERNAL leave the caller's buffers untouched.
//!
//! Path rows are UTF-8 byte ranges (`paths[i]`, `lengths[i]`), not
//! NUL-terminated. A row longer than MAX_PATH_BYTES is reported as
//! STATUS_BAD_PATH without being read; a null row pointer with a nonzero length
//! makes the whole call INVALID.
use std::panic::{AssertUnwindSafe, catch_unwind};

use crate::digest::*;
use crate::{INTERNAL, INVALID, OK};

unsafe fn rows<'a, T>(pointer: *const T, count: usize) -> &'a [T] {
    if count == 0 || pointer.is_null() { &[] } else { unsafe { std::slice::from_raw_parts(pointer, count) } }
}

/// Borrowed path rows; None when a row pointer is null with a nonzero length.
unsafe fn path_rows<'a>(paths: *const *const u8, lengths: *const usize, count: usize) -> Option<Vec<&'a [u8]>> {
    let pointers = unsafe { rows(paths, count) };
    let sizes = unsafe { rows(lengths, count) };
    let mut out = Vec::with_capacity(count);
    for (&pointer, &length) in pointers.iter().zip(sizes) {
        if length == 0 || length > MAX_PATH_BYTES {
            out.push(&[][..]);
        } else if pointer.is_null() {
            return None;
        } else {
            out.push(unsafe { std::slice::from_raw_parts(pointer, length) });
        }
    }
    Some(out)
}

unsafe fn write_rows(
    results: &[FileDigest],
    used: usize,
    out_digests: *mut u8,
    out_status: *mut i32,
    out_folded: *mut u8,
    out_bytes: *mut u64,
    out_threads: *mut u32,
) {
    let mut bytes = 0u64;
    for (index, row) in results.iter().enumerate() {
        unsafe {
            std::ptr::copy_nonoverlapping(row.digest.as_ptr(), out_digests.add(index * 32), 32);
            *out_status.add(index) = row.status;
            if !out_folded.is_null() {
                *out_folded.add(index) = u8::from(row.folded);
            }
        }
        bytes = bytes.saturating_add(row.bytes);
    }
    unsafe {
        if !out_bytes.is_null() {
            *out_bytes = bytes;
        }
        if !out_threads.is_null() {
            *out_threads = used as u32;
        }
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn rl_digest_api() -> u32 {
    DIGEST_API
}

/// BACKEND_SHA_NI or BACKEND_PORTABLE; 0 if the choice itself failed.
#[unsafe(no_mangle)]
pub extern "C" fn rl_digest_backend() -> u32 {
    catch_unwind(|| backend().code()).unwrap_or(0)
}

/// 1 when this CPU has the SHA extensions (whatever the backend choice).
#[unsafe(no_mangle)]
pub extern "C" fn rl_digest_cpu_sha_ni() -> u32 {
    catch_unwind(|| u32::from(sha_ni_supported())).unwrap_or(0)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_digest_limits(max_files: *mut u64, max_threads: *mut u32, max_path_bytes: *mut u64,
    read_bytes: *mut u64) -> i32 {
    if max_files.is_null() || max_threads.is_null() || max_path_bytes.is_null() || read_bytes.is_null() {
        return INVALID;
    }
    unsafe {
        *max_files = MAX_FILES as u64;
        *max_threads = MAX_THREADS as u32;
        *max_path_bytes = MAX_PATH_BYTES as u64;
        *read_bytes = READ_BYTES as u64;
    }
    OK
}

/// SHA-256 of `length` bytes at `data` into `output[32]`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_digest_sha256_buffer(data: *const u8, length: usize, output: *mut u8) -> i32 {
    if output.is_null() || (length != 0 && data.is_null()) || length > isize::MAX as usize {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let digest = sha256(rows(data, length));
        std::ptr::copy_nonoverlapping(digest.as_ptr(), output, 32);
        OK
    }))
    .unwrap_or(INTERNAL)
}

/// Hashes `count` files on up to `threads` threads (the caller included).
/// `flags` may be null (all 0). `out_digests` holds count*32 bytes (zero for
/// a failed row), `out_status` count STATUS_* values; `out_folded` (count
/// bytes), `out_bytes` (total bytes read) and `out_threads` (threads that
/// hashed) may be null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_digest_sha256_files(
    paths: *const *const u8,
    lengths: *const usize,
    flags: *const u32,
    count: usize,
    threads: u32,
    out_digests: *mut u8,
    out_status: *mut i32,
    out_folded: *mut u8,
    out_bytes: *mut u64,
    out_threads: *mut u32,
) -> i32 {
    if count > MAX_FILES
        || (count != 0 && (paths.is_null() || lengths.is_null() || out_digests.is_null() || out_status.is_null()))
    {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let Some(rows_in) = path_rows(paths, lengths, count) else {
            return INVALID;
        };
        let (results, used) = hash_files(&rows_in, rows(flags, count), threads as usize);
        write_rows(&results, used, out_digests, out_status, out_folded, out_bytes, out_threads);
        OK
    }))
    .unwrap_or(INTERNAL)
}

/// `rl_digest_sha256_files`, then `out_ok[i]` = 1 when row i was read and
/// equals `expected[i*32..]`. `expected_present` (count bytes, may be null for
/// all present) marks rows whose expected value the caller could parse; an
/// absent row never passes. Every row is hashed even after a failure.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rl_digest_verify_files(
    paths: *const *const u8,
    lengths: *const usize,
    flags: *const u32,
    expected: *const u8,
    expected_present: *const u8,
    count: usize,
    threads: u32,
    out_digests: *mut u8,
    out_status: *mut i32,
    out_folded: *mut u8,
    out_ok: *mut u8,
    out_bytes: *mut u64,
    out_threads: *mut u32,
) -> i32 {
    if count > MAX_FILES
        || (count != 0
            && (paths.is_null()
                || lengths.is_null()
                || expected.is_null()
                || out_digests.is_null()
                || out_status.is_null()
                || out_ok.is_null()))
    {
        return INVALID;
    }
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let Some(rows_in) = path_rows(paths, lengths, count) else {
            return INVALID;
        };
        let wanted: Vec<[u8; 32]> = rows(expected, count * 32)
            .chunks_exact(32)
            .map(|chunk| chunk.try_into().unwrap_or([0; 32]))
            .collect();
        let present = if expected_present.is_null() { None } else { Some(rows(expected_present, count)) };
        let (results, passed, used) = verify_files(&rows_in, rows(flags, count), &wanted, present, threads as usize);
        write_rows(&results, used, out_digests, out_status, out_folded, out_bytes, out_threads);
        for (index, pass) in passed.iter().enumerate() {
            *out_ok.add(index) = u8::from(*pass);
        }
        OK
    }))
    .unwrap_or(INTERNAL)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_file(name: &str, bytes: &[u8]) -> std::path::PathBuf {
        let path = std::env::temp_dir().join(format!("rl-digest-ffi-{}-{name}", std::process::id()));
        std::fs::write(&path, bytes).unwrap();
        path
    }

    #[test]
    fn ffi_rejects_bad_pointers_and_leaves_outputs_untouched() {
        let mut digest = [7u8; 32];
        assert_eq!(unsafe { rl_digest_sha256_buffer(std::ptr::null(), 3, digest.as_mut_ptr()) }, INVALID);
        assert_eq!(digest, [7u8; 32]);
        assert_eq!(unsafe { rl_digest_sha256_buffer(b"abc".as_ptr(), 3, std::ptr::null_mut()) }, INVALID);
        assert_eq!(unsafe { rl_digest_sha256_buffer(std::ptr::null(), 0, digest.as_mut_ptr()) }, OK);
        assert_eq!(hex(&digest), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
        assert_eq!(unsafe { rl_digest_sha256_buffer(b"abc".as_ptr(), 3, digest.as_mut_ptr()) }, OK);
        assert_eq!(hex(&digest), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");

        let mut out = [9u8; 64];
        let mut status = [9i32; 2];
        let null_rows = [std::ptr::null::<u8>(), std::ptr::null()];
        let lengths = [4usize, 0];
        let code = unsafe {
            rl_digest_sha256_files(null_rows.as_ptr(), lengths.as_ptr(), std::ptr::null(), 2, 2, out.as_mut_ptr(),
                status.as_mut_ptr(), std::ptr::null_mut(), std::ptr::null_mut(), std::ptr::null_mut())
        };
        assert_eq!(code, INVALID);
        assert_eq!((out, status), ([9u8; 64], [9i32; 2]));
        let code = unsafe {
            rl_digest_sha256_files(std::ptr::null(), std::ptr::null(), std::ptr::null(), MAX_FILES + 1, 1,
                out.as_mut_ptr(), status.as_mut_ptr(), std::ptr::null_mut(), std::ptr::null_mut(), std::ptr::null_mut())
        };
        assert_eq!(code, INVALID);
        let code = unsafe {
            rl_digest_sha256_files(std::ptr::null(), std::ptr::null(), std::ptr::null(), 0, 1, std::ptr::null_mut(),
                std::ptr::null_mut(), std::ptr::null_mut(), std::ptr::null_mut(), std::ptr::null_mut())
        };
        assert_eq!(code, OK);
        let (mut files, mut threads, mut path_bytes, mut read) = (0u64, 0u32, 0u64, 0u64);
        assert_eq!(unsafe { rl_digest_limits(&mut files, &mut threads, &mut path_bytes, &mut read) }, OK);
        assert_eq!((files, threads, path_bytes, read), (MAX_FILES as u64, MAX_THREADS as u32,
            MAX_PATH_BYTES as u64, READ_BYTES as u64));
        assert_eq!(rl_digest_api(), 1);
        assert!(matches!(rl_digest_backend(), BACKEND_SHA_NI | BACKEND_PORTABLE));
        assert_eq!(rl_digest_cpu_sha_ni() == 1, sha_ni_supported());
    }

    #[test]
    fn ffi_batches_write_every_row_and_verify_marks_passes() {
        let text = temp_file("text.json", b"a\r\nb");
        let raw = temp_file("raw.bin", b"abc");
        let text_path = text.to_str().unwrap().to_string();
        let raw_path = raw.to_str().unwrap().to_string();
        let long = "x".repeat(MAX_PATH_BYTES + 1);
        let names = [text_path.as_str(), raw_path.as_str(), "relative", long.as_str(), ""];
        let pointers: Vec<*const u8> = names.iter().map(|name| name.as_ptr()).collect();
        let lengths: Vec<usize> = names.iter().map(|name| name.len()).collect();
        let flags = [FLAG_FOLD_CRLF, FLAG_FOLD_CRLF];
        let mut digests = [0xAAu8; 5 * 32];
        let mut status = [99i32; 5];
        let mut folded = [9u8; 5];
        let mut bytes = 0u64;
        let mut threads = 0u32;
        let code = unsafe {
            rl_digest_sha256_files(pointers.as_ptr(), lengths.as_ptr(), flags.as_ptr(), 5, 3, digests.as_mut_ptr(),
                status.as_mut_ptr(), folded.as_mut_ptr(), &mut bytes, &mut threads)
        };
        assert_eq!(code, OK);
        assert_eq!(status, [STATUS_OK, STATUS_OK, STATUS_BAD_PATH, STATUS_BAD_PATH, STATUS_BAD_PATH]);
        assert_eq!(digests[..32], sha256(b"a\nb"));
        assert_eq!(digests[32..64], sha256(b"abc"));
        assert!(digests[64..].iter().all(|&byte| byte == 0));
        assert_eq!(folded, [1, 0, 0, 0, 0]);
        assert_eq!(bytes, 4 + 3);
        assert!((1..=3).contains(&threads));

        let mut expected = [0u8; 5 * 32];
        expected[..32].copy_from_slice(&sha256(b"a\nb"));
        expected[32..64].copy_from_slice(&sha256(b"abc"));
        let present = [1u8, 0, 1, 1, 1];
        let mut ok = [9u8; 5];
        let code = unsafe {
            rl_digest_verify_files(pointers.as_ptr(), lengths.as_ptr(), flags.as_ptr(), expected.as_ptr(),
                present.as_ptr(), 5, 2, digests.as_mut_ptr(), status.as_mut_ptr(), std::ptr::null_mut(),
                ok.as_mut_ptr(), std::ptr::null_mut(), std::ptr::null_mut())
        };
        assert_eq!(code, OK);
        assert_eq!(ok, [1, 0, 0, 0, 0]);
        let code = unsafe {
            rl_digest_verify_files(pointers.as_ptr(), lengths.as_ptr(), flags.as_ptr(), std::ptr::null(),
                std::ptr::null(), 5, 2, digests.as_mut_ptr(), status.as_mut_ptr(), std::ptr::null_mut(),
                ok.as_mut_ptr(), std::ptr::null_mut(), std::ptr::null_mut())
        };
        assert_eq!(code, INVALID);
        let _ = std::fs::remove_file(text);
        let _ = std::fs::remove_file(raw);
    }
}
