//! SHA-256 of installed content: the digest every manifest, cache key,
//! prepared record and server value already carries (FIPS 180-4, 32 bytes),
//! produced faster. Nothing here defines a new digest format.
//!
//! * `Sha256` is a streaming state. Its block function is chosen once per
//!   process: the x86 SHA extensions (SHA-NI) when the CPU has them, otherwise
//!   a portable implementation. `RABBITLANDS_CONTENT_DIGEST_SHA=portable`
//!   forces the portable path (qualification on a SHA-NI machine).
//! * `hash_file` streams one file in reads of at most `READ_BYTES`; a whole
//!   file is never held in memory. `FLAG_FOLD_CRLF` hashes the file with every
//!   CR that is directly followed by LF dropped (a lone CR and a CR at the end
//!   of the file stay; a CR that ends one read is decided by the next read).
//!   That is `ContentDigest.FOLD_CRLF` / `MapSceneCache.package_digest`.
//! * `hash_files` hashes a batch on scoped threads plus the caller, taking the
//!   files in caller order from one atomic index. It never uses an engine
//!   thread pool and touches no engine object, so any thread may call it.
//!
//! Strictness: every call reads and hashes every byte of every row it is
//! given. Nothing is remembered between calls.
//!
//! Paths are UTF-8, absolute, at most `MAX_PATH_BYTES`, without NUL. Anything
//! else (an empty path, a relative path, a `res://` path) is `STATUS_BAD_PATH`
//! without touching the file system: the caller maps engine paths first and
//! keeps PCK paths on the engine reader.

use std::fs::File;
use std::io::{ErrorKind, Read};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::Path;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicUsize, Ordering};

pub const DIGEST_API: u32 = 1;
pub const BACKEND_SHA_NI: u32 = 1;
pub const BACKEND_PORTABLE: u32 = 2;
pub const BACKEND_ENVIRONMENT: &str = "RABBITLANDS_CONTENT_DIGEST_SHA";

/// Row flags. Unknown bits are ignored.
pub const FLAG_FOLD_CRLF: u32 = 1;
pub const KNOWN_FLAGS: u32 = FLAG_FOLD_CRLF;

/// Per-row status, the codes `ContentDigest` already uses.
pub const STATUS_OK: i32 = 0;
pub const STATUS_OPEN: i32 = 1;
pub const STATUS_READ: i32 = 2;
pub const STATUS_BAD_PATH: i32 = 3;
pub const STATUS_INTERNAL: i32 = 4;

/// Largest single read. Smaller files get a buffer just big enough.
pub const READ_BYTES: usize = 1 << 20;
const MIN_READ_BYTES: usize = 4096;
pub const MAX_FILES: usize = 1 << 20;
pub const MAX_THREADS: usize = 64;
/// UTF-8 of the longest Windows path (32,767 UTF-16 units, 3 bytes each).
pub const MAX_PATH_BYTES: usize = 3 * 32_767;

const CR: u8 = b'\r';
const LF: u8 = b'\n';

const H0: [u32; 8] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];

const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Backend {
    ShaNi,
    Portable,
}

impl Backend {
    pub fn code(self) -> u32 {
        match self {
            Backend::ShaNi => BACKEND_SHA_NI,
            Backend::Portable => BACKEND_PORTABLE,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Backend::ShaNi => "sha_ni",
            Backend::Portable => "portable",
        }
    }
}

/// True when this CPU can run the SHA-NI block function.
pub fn sha_ni_supported() -> bool {
    #[cfg(target_arch = "x86_64")]
    {
        std::is_x86_feature_detected!("sha")
            && std::is_x86_feature_detected!("sse2")
            && std::is_x86_feature_detected!("ssse3")
            && std::is_x86_feature_detected!("sse4.1")
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        false
    }
}

/// Pure choice, for tests: SHA-NI when supported and not forced off.
pub fn choose_backend(supported: bool, forced: Option<&str>) -> Backend {
    let portable = forced.is_some_and(|value| value.trim().eq_ignore_ascii_case("portable"));
    if supported && !portable { Backend::ShaNi } else { Backend::Portable }
}

/// The process-wide backend, decided once.
pub fn backend() -> Backend {
    static BACKEND: OnceLock<Backend> = OnceLock::new();
    *BACKEND.get_or_init(|| {
        let forced = std::env::var(BACKEND_ENVIRONMENT).ok();
        choose_backend(sha_ni_supported(), forced.as_deref())
    })
}

/// FIPS 180-4 block function, any number of whole 64-byte blocks. Rounds are
/// unrolled eight at a time with the working variables renamed instead of
/// moved, and the message schedule is computed in place in a 16-word ring
/// (the last rounds' ring writes are never read, hence the allow).
#[allow(unused_assignments)]
fn compress_portable(state: &mut [u32; 8], blocks: &[u8]) {
    debug_assert!(blocks.len() % 64 == 0);
    for block in blocks.chunks_exact(64) {
        let mut w = [0u32; 16];
        for (index, word) in w.iter_mut().enumerate() {
            let at = index * 4;
            *word = u32::from_be_bytes([block[at], block[at + 1], block[at + 2], block[at + 3]]);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = *state;
        // One round: `d` receives the new e, `h` the new a; the next round
        // names the variables one place further on.
        macro_rules! round {
            ($a:ident, $b:ident, $c:ident, $d:ident, $e:ident, $f:ident, $g:ident, $h:ident, $index:expr, $word:expr) => {
                let t1 = $h
                    .wrapping_add($e.rotate_right(6) ^ $e.rotate_right(11) ^ $e.rotate_right(25))
                    .wrapping_add($g ^ ($e & ($f ^ $g)))
                    .wrapping_add(K[$index])
                    .wrapping_add($word);
                $d = $d.wrapping_add(t1);
                $h = t1
                    .wrapping_add($a.rotate_right(2) ^ $a.rotate_right(13) ^ $a.rotate_right(22))
                    .wrapping_add(($a & $b) | ($c & ($a | $b)));
            };
        }
        macro_rules! given {
            ($index:expr) => {
                w[$index]
            };
        }
        macro_rules! scheduled {
            ($index:expr) => {{
                let w15 = w[($index + 1) & 15];
                let w2 = w[($index + 14) & 15];
                let s0 = w15.rotate_right(7) ^ w15.rotate_right(18) ^ (w15 >> 3);
                let s1 = w2.rotate_right(17) ^ w2.rotate_right(19) ^ (w2 >> 10);
                let word = w[$index & 15].wrapping_add(s0).wrapping_add(w[($index + 9) & 15]).wrapping_add(s1);
                w[$index & 15] = word;
                word
            }};
        }
        macro_rules! eight {
            ($base:expr, $message:ident) => {
                round!(a, b, c, d, e, f, g, h, $base, $message!($base));
                round!(h, a, b, c, d, e, f, g, $base + 1, $message!($base + 1));
                round!(g, h, a, b, c, d, e, f, $base + 2, $message!($base + 2));
                round!(f, g, h, a, b, c, d, e, $base + 3, $message!($base + 3));
                round!(e, f, g, h, a, b, c, d, $base + 4, $message!($base + 4));
                round!(d, e, f, g, h, a, b, c, $base + 5, $message!($base + 5));
                round!(c, d, e, f, g, h, a, b, $base + 6, $message!($base + 6));
                round!(b, c, d, e, f, g, h, a, $base + 7, $message!($base + 7));
            };
        }
        eight!(0, given);
        eight!(8, given);
        eight!(16, scheduled);
        eight!(24, scheduled);
        eight!(32, scheduled);
        eight!(40, scheduled);
        eight!(48, scheduled);
        eight!(56, scheduled);
        for (word, value) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) {
            *word = word.wrapping_add(value);
        }
    }
}

/// The SHA-NI block function. Its structure is the well-known Intel sample:
/// the state is kept as the ABEF/CDGH register pair `sha256rnds2` expects,
/// four rounds per message vector, and `sha256msg1`/`sha256msg2` plus one
/// `palignr` extend the schedule four words at a time.
///
/// # Safety
/// The CPU must support SHA, SSE2, SSSE3 and SSE4.1 (`sha_ni_supported`).
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "sha,sse2,ssse3,sse4.1")]
unsafe fn compress_sha_ni(state: &mut [u32; 8], blocks: &[u8]) {
    use std::arch::x86_64::*;
    debug_assert!(blocks.len() % 64 == 0);
    // Four rounds: add the round constants to one message vector, run two
    // `sha256rnds2` (each consumes the low two words).
    macro_rules! rounds4 {
        ($abef:ident, $cdgh:ident, $message:expr, $group:expr) => {{
            let constants = unsafe { _mm_loadu_si128(K.as_ptr().add($group * 4) as *const __m128i) };
            let sum = _mm_add_epi32($message, constants);
            $cdgh = _mm_sha256rnds2_epu32($cdgh, $abef, sum);
            $abef = _mm_sha256rnds2_epu32($abef, $cdgh, _mm_shuffle_epi32(sum, 0x0E));
        }};
    }
    // W[i..i+4] from W[i-16..i]: the four previous vectors, oldest first.
    macro_rules! schedule {
        ($w0:expr, $w1:expr, $w2:expr, $w3:expr) => {
            _mm_sha256msg2_epu32(
                _mm_add_epi32(_mm_sha256msg1_epu32($w0, $w1), _mm_alignr_epi8($w3, $w2, 4)),
                $w3,
            )
        };
    }
    let byte_swap = _mm_set_epi64x(0x0c0d_0e0f_0809_0a0b, 0x0405_0607_0001_0203);
    let (low, high) = unsafe {
        (
            _mm_loadu_si128(state.as_ptr() as *const __m128i),
            _mm_loadu_si128(state.as_ptr().add(4) as *const __m128i),
        )
    };
    // low = [a b c d], high = [e f g h] (lane 0 first).
    let cdab = _mm_shuffle_epi32(low, 0xB1);
    let efgh = _mm_shuffle_epi32(high, 0x1B);
    let mut abef = _mm_alignr_epi8(cdab, efgh, 8);
    let mut cdgh = _mm_blend_epi16(efgh, cdab, 0xF0);
    for block in blocks.chunks_exact(64) {
        let saved_abef = abef;
        let saved_cdgh = cdgh;
        let data = block.as_ptr() as *const __m128i;
        let (mut w0, mut w1, mut w2, mut w3) = unsafe {
            (
                _mm_shuffle_epi8(_mm_loadu_si128(data), byte_swap),
                _mm_shuffle_epi8(_mm_loadu_si128(data.add(1)), byte_swap),
                _mm_shuffle_epi8(_mm_loadu_si128(data.add(2)), byte_swap),
                _mm_shuffle_epi8(_mm_loadu_si128(data.add(3)), byte_swap),
            )
        };
        rounds4!(abef, cdgh, w0, 0);
        rounds4!(abef, cdgh, w1, 1);
        rounds4!(abef, cdgh, w2, 2);
        rounds4!(abef, cdgh, w3, 3);
        w0 = schedule!(w0, w1, w2, w3);
        rounds4!(abef, cdgh, w0, 4);
        w1 = schedule!(w1, w2, w3, w0);
        rounds4!(abef, cdgh, w1, 5);
        w2 = schedule!(w2, w3, w0, w1);
        rounds4!(abef, cdgh, w2, 6);
        w3 = schedule!(w3, w0, w1, w2);
        rounds4!(abef, cdgh, w3, 7);
        w0 = schedule!(w0, w1, w2, w3);
        rounds4!(abef, cdgh, w0, 8);
        w1 = schedule!(w1, w2, w3, w0);
        rounds4!(abef, cdgh, w1, 9);
        w2 = schedule!(w2, w3, w0, w1);
        rounds4!(abef, cdgh, w2, 10);
        w3 = schedule!(w3, w0, w1, w2);
        rounds4!(abef, cdgh, w3, 11);
        w0 = schedule!(w0, w1, w2, w3);
        rounds4!(abef, cdgh, w0, 12);
        w1 = schedule!(w1, w2, w3, w0);
        rounds4!(abef, cdgh, w1, 13);
        w2 = schedule!(w2, w3, w0, w1);
        rounds4!(abef, cdgh, w2, 14);
        w3 = schedule!(w3, w0, w1, w2);
        rounds4!(abef, cdgh, w3, 15);
        abef = _mm_add_epi32(abef, saved_abef);
        cdgh = _mm_add_epi32(cdgh, saved_cdgh);
    }
    let feba = _mm_shuffle_epi32(abef, 0x1B);
    let dchg = _mm_shuffle_epi32(cdgh, 0xB1);
    let low = _mm_blend_epi16(feba, dchg, 0xF0);
    let high = _mm_alignr_epi8(dchg, feba, 8);
    unsafe {
        _mm_storeu_si128(state.as_mut_ptr() as *mut __m128i, low);
        _mm_storeu_si128(state.as_mut_ptr().add(4) as *mut __m128i, high);
    }
}

/// Streaming SHA-256.
#[derive(Clone)]
pub struct Sha256 {
    state: [u32; 8],
    pending: [u8; 64],
    pending_len: usize,
    length: u64,
    backend: Backend,
}

impl Default for Sha256 {
    fn default() -> Self {
        Self::new()
    }
}

impl Sha256 {
    /// A state on the process backend.
    pub fn new() -> Self {
        Self::on(backend())
    }

    /// A state on a named backend; `None` for SHA-NI on a CPU without it.
    pub fn with_backend(backend: Backend) -> Option<Self> {
        if backend == Backend::ShaNi && !sha_ni_supported() {
            return None;
        }
        Some(Self::on(backend))
    }

    fn on(backend: Backend) -> Self {
        Self {
            state: H0,
            pending: [0; 64],
            pending_len: 0,
            length: 0,
            backend,
        }
    }

    pub fn backend(&self) -> Backend {
        self.backend
    }

    fn compress(&mut self, blocks: &[u8]) {
        match self.backend {
            #[cfg(target_arch = "x86_64")]
            // SAFETY: a ShaNi state exists only where `sha_ni_supported()`
            // held (`with_backend`, or `backend()` which checked it).
            Backend::ShaNi => unsafe { compress_sha_ni(&mut self.state, blocks) },
            _ => compress_portable(&mut self.state, blocks),
        }
    }

    pub fn update(&mut self, mut data: &[u8]) {
        self.length = self.length.wrapping_add(data.len() as u64);
        if self.pending_len > 0 {
            let take = (64 - self.pending_len).min(data.len());
            self.pending[self.pending_len..self.pending_len + take].copy_from_slice(&data[..take]);
            self.pending_len += take;
            data = &data[take..];
            if self.pending_len < 64 {
                return;
            }
            let block = self.pending;
            self.compress(&block);
            self.pending_len = 0;
        }
        let whole = data.len() / 64 * 64;
        if whole > 0 {
            self.compress(&data[..whole]);
        }
        let rest = &data[whole..];
        self.pending[..rest.len()].copy_from_slice(rest);
        self.pending_len = rest.len();
    }

    pub fn finish(mut self) -> [u8; 32] {
        let bits = self.length.wrapping_mul(8);
        let mut tail = [0u8; 128];
        tail[..self.pending_len].copy_from_slice(&self.pending[..self.pending_len]);
        tail[self.pending_len] = 0x80;
        let total = if self.pending_len < 56 { 64 } else { 128 };
        tail[total - 8..total].copy_from_slice(&bits.to_be_bytes());
        self.compress(&tail[..total]);
        let mut digest = [0u8; 32];
        for (index, word) in self.state.iter().enumerate() {
            digest[index * 4..index * 4 + 4].copy_from_slice(&word.to_be_bytes());
        }
        digest
    }
}

/// SHA-256 of bytes in memory, on the process backend.
pub fn sha256(data: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hasher.finish()
}

/// Lowercase hex, the form every manifest stores.
pub fn hex(digest: &[u8; 32]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut text = String::with_capacity(64);
    for byte in digest {
        text.push(DIGITS[(byte >> 4) as usize] as char);
        text.push(DIGITS[(byte & 15) as usize] as char);
    }
    text
}

/// Streaming CRLF fold (see the module comment). Feed reads in order, then
/// `finish`.
#[derive(Default)]
pub struct CrlfFold {
    pending_cr: bool,
    folded: bool,
}

impl CrlfFold {
    pub fn feed(&mut self, hasher: &mut Sha256, block: &[u8]) {
        if block.is_empty() {
            return;
        }
        let size = block.len();
        let mut start = 0;
        if self.pending_cr {
            self.pending_cr = false;
            if block[0] == LF {
                self.folded = true;
            } else {
                hasher.update(&[CR]);
            }
        }
        let mut from = 0;
        while let Some(offset) = block[from..].iter().position(|&byte| byte == CR) {
            let at = from + offset;
            if at + 1 >= size {
                // The read's last byte: the next read decides.
                hasher.update(&block[start..at]);
                start = size;
                self.pending_cr = true;
                break;
            }
            if block[at + 1] == LF {
                hasher.update(&block[start..at]);
                start = at + 1;
                self.folded = true;
            }
            from = at + 1;
        }
        if start < size {
            hasher.update(&block[start..]);
        }
    }

    /// Emits a CR still held at the end of the input; returns whether any CR
    /// was dropped.
    pub fn finish(&mut self, hasher: &mut Sha256) -> bool {
        if self.pending_cr {
            self.pending_cr = false;
            hasher.update(&[CR]);
        }
        self.folded
    }
}

/// One row of a batch.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FileDigest {
    pub digest: [u8; 32],
    pub status: i32,
    /// FLAG_FOLD_CRLF dropped at least one byte.
    pub folded: bool,
    /// Bytes read from the file (before folding).
    pub bytes: u64,
}

impl FileDigest {
    pub fn failed(status: i32) -> Self {
        Self { digest: [0; 32], status, folded: false, bytes: 0 }
    }
}

/// UTF-8, non-empty, no NUL, absolute, at most MAX_PATH_BYTES.
pub fn checked_path(bytes: &[u8]) -> Option<&Path> {
    if bytes.is_empty() || bytes.len() > MAX_PATH_BYTES || bytes.contains(&0) {
        return None;
    }
    let text = std::str::from_utf8(bytes).ok()?;
    let path = Path::new(text);
    path.is_absolute().then_some(path)
}

/// Hashes a reader with `buffer`-sized reads (tests use tiny buffers to put
/// CRs on read boundaries).
pub fn hash_reader<R: Read>(reader: &mut R, fold: bool, buffer: &mut [u8], backend: Backend) -> FileDigest {
    let Some(mut hasher) = Sha256::with_backend(backend) else {
        return FileDigest::failed(STATUS_INTERNAL);
    };
    if buffer.is_empty() {
        return FileDigest::failed(STATUS_INTERNAL);
    }
    let mut fold_state = CrlfFold::default();
    let mut bytes = 0u64;
    loop {
        let read = match reader.read(buffer) {
            Ok(0) => break,
            Ok(read) => read,
            Err(error) if error.kind() == ErrorKind::Interrupted => continue,
            Err(_) => return FileDigest { bytes, ..FileDigest::failed(STATUS_READ) },
        };
        bytes += read as u64;
        if fold {
            fold_state.feed(&mut hasher, &buffer[..read]);
        } else {
            hasher.update(&buffer[..read]);
        }
    }
    let folded = fold && fold_state.finish(&mut hasher);
    FileDigest { digest: hasher.finish(), status: STATUS_OK, folded, bytes }
}

/// Hashes one file. `buffer` is reused between files on one thread and grows
/// to at most READ_BYTES.
pub fn hash_file(path: &[u8], flags: u32, buffer: &mut Vec<u8>) -> FileDigest {
    hash_file_on(path, flags, buffer, backend())
}

pub fn hash_file_on(path: &[u8], flags: u32, buffer: &mut Vec<u8>, backend: Backend) -> FileDigest {
    let Some(path) = checked_path(path) else {
        return FileDigest::failed(STATUS_BAD_PATH);
    };
    let Ok(mut file) = File::open(path) else {
        return FileDigest::failed(STATUS_OPEN);
    };
    // A directory is not a file (Windows already refuses to open one; other
    // platforms open it and fail the read). `ContentDigest` reports open.
    let length = match file.metadata() {
        Ok(metadata) if metadata.is_dir() => return FileDigest::failed(STATUS_OPEN),
        Ok(metadata) => metadata.len(),
        Err(_) => return FileDigest::failed(STATUS_OPEN),
    };
    // One read more than the file needs sees the end in the same pass.
    let wanted = usize::try_from(length.saturating_add(1)).unwrap_or(READ_BYTES).clamp(MIN_READ_BYTES, READ_BYTES);
    if buffer.len() < wanted {
        buffer.resize(wanted, 0);
    }
    let fold = flags & KNOWN_FLAGS & FLAG_FOLD_CRLF != 0;
    hash_reader(&mut file, fold, &mut buffer[..wanted], backend)
}

/// Hashes every row on up to `threads` threads (the caller is one of them).
/// Rows are taken in caller order; results are per row. Returns the results
/// and the number of threads that hashed. A row whose hashing panicked is
/// STATUS_INTERNAL; a helper thread that cannot start leaves its share to the
/// others.
pub fn hash_files(paths: &[&[u8]], flags: &[u32], threads: usize) -> (Vec<FileDigest>, usize) {
    hash_files_on(paths, flags, threads, backend())
}

pub fn hash_files_on(paths: &[&[u8]], flags: &[u32], threads: usize, backend: Backend) -> (Vec<FileDigest>, usize) {
    let count = paths.len();
    let mut results = vec![FileDigest::failed(STATUS_INTERNAL); count];
    let wanted = threads.clamp(1, MAX_THREADS).min(count.max(1));
    let next = AtomicUsize::new(0);
    let work = || {
        let mut rows = Vec::new();
        let mut buffer = Vec::new();
        loop {
            let index = next.fetch_add(1, Ordering::Relaxed);
            if index >= count {
                break;
            }
            let flag = flags.get(index).copied().unwrap_or(0);
            let row = catch_unwind(AssertUnwindSafe(|| hash_file_on(paths[index], flag, &mut buffer, backend)))
                .unwrap_or(FileDigest::failed(STATUS_INTERNAL));
            rows.push((index, row));
        }
        rows
    };
    let mut used = 1;
    std::thread::scope(|scope| {
        let mut helpers = Vec::new();
        for _ in 1..wanted {
            match std::thread::Builder::new().name("rl-content-digest".into()).spawn_scoped(scope, work) {
                Ok(handle) => helpers.push(handle),
                Err(_) => break,
            }
        }
        used += helpers.len();
        for (index, row) in work() {
            results[index] = row;
        }
        for helper in helpers {
            if let Ok(rows) = helper.join() {
                for (index, row) in rows {
                    results[index] = row;
                }
            }
        }
    });
    (results, used)
}

/// `hash_files`, then each row passes when it was read, its expected value is
/// present and the digest equals it. Every row is hashed even after a
/// failure. `present` (when given) marks rows whose expected value the caller
/// could parse; an absent row never passes.
pub fn verify_files(
    paths: &[&[u8]],
    flags: &[u32],
    expected: &[[u8; 32]],
    present: Option<&[u8]>,
    threads: usize,
) -> (Vec<FileDigest>, Vec<bool>, usize) {
    let (results, used) = hash_files(paths, flags, threads);
    let passed = results
        .iter()
        .enumerate()
        .map(|(index, row)| {
            row.status == STATUS_OK
                && present.is_none_or(|marks| marks.get(index).is_some_and(|&mark| mark != 0))
                && expected.get(index).is_some_and(|value| *value == row.digest)
        })
        .collect();
    (results, passed, used)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::path::PathBuf;

    fn backends() -> Vec<Backend> {
        let mut list = vec![Backend::Portable];
        if sha_ni_supported() {
            list.push(Backend::ShaNi);
        } else {
            eprintln!("note: this CPU has no SHA-NI; only the portable backend is tested");
        }
        list
    }

    fn digest_on(backend: Backend, data: &[u8]) -> [u8; 32] {
        let mut hasher = Sha256::with_backend(backend).unwrap();
        hasher.update(data);
        hasher.finish()
    }

    /// Deterministic bytes (xorshift64*).
    fn noise(seed: u64, length: usize) -> Vec<u8> {
        let mut state = seed.wrapping_mul(0x9e37_79b9_7f4a_7c15) | 1;
        (0..length)
            .map(|_| {
                state ^= state >> 12;
                state ^= state << 25;
                state ^= state >> 27;
                (state.wrapping_mul(0x2545_f491_4f6c_dd1d) >> 56) as u8
            })
            .collect()
    }

    /// The per-byte fold `MapSceneCache._strip_carriage_returns` used.
    fn reference_fold(raw: &[u8]) -> (Vec<u8>, bool) {
        let mut out = Vec::with_capacity(raw.len());
        for (index, &byte) in raw.iter().enumerate() {
            if byte == CR && raw.get(index + 1) == Some(&LF) {
                continue;
            }
            out.push(byte);
        }
        let folded = out.len() != raw.len();
        (out, folded)
    }

    const NIST: [(&str, &str); 4] = [
        ("", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        ("abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        (
            "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
        ),
        (
            "abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
            "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1",
        ),
    ];

    #[test]
    fn nist_vectors_on_every_backend() {
        for backend in backends() {
            for (input, expected) in NIST {
                assert_eq!(hex(&digest_on(backend, input.as_bytes())), expected, "{backend:?} {input:?}");
            }
            let million = vec![b'a'; 1_000_000];
            assert_eq!(
                hex(&digest_on(backend, &million)),
                "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
                "{backend:?} million a"
            );
            // The same million fed in uneven pieces.
            let mut hasher = Sha256::with_backend(backend).unwrap();
            let mut at = 0;
            let mut step = 1;
            while at < million.len() {
                let end = (at + step).min(million.len());
                hasher.update(&million[at..end]);
                at = end;
                step = step * 7 % 1013 + 1;
            }
            assert_eq!(hex(&hasher.finish()), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
        }
        assert_eq!(hex(&sha256(b"abc")), NIST[1].1);
    }

    #[test]
    fn sha_ni_equals_portable_on_every_length_to_8192_and_split_updates() {
        if !sha_ni_supported() {
            eprintln!("skipped: no SHA-NI on this CPU");
            return;
        }
        let data = noise(7, 8192 + 257);
        for length in 0..=8192 {
            let slice = &data[..length];
            assert_eq!(
                digest_on(Backend::ShaNi, slice),
                digest_on(Backend::Portable, slice),
                "length {length}"
            );
        }
        // Block boundaries with every split point around them.
        for length in [55, 56, 57, 63, 64, 65, 119, 120, 127, 128, 129, 191, 192, 193, 4095, 4096, 4097] {
            let slice = &data[..length];
            let expected = digest_on(Backend::Portable, slice);
            for split in 0..=length {
                for backend in [Backend::ShaNi, Backend::Portable] {
                    let mut hasher = Sha256::with_backend(backend).unwrap();
                    hasher.update(&slice[..split]);
                    hasher.update(&slice[split..]);
                    assert_eq!(hasher.finish(), expected, "{backend:?} length {length} split {split}");
                }
            }
        }
        // Random lengths and random seeds.
        for seed in 1..200u64 {
            let length = (seed as usize * 7919) % 8193;
            let slice = noise(seed, length);
            assert_eq!(digest_on(Backend::ShaNi, &slice), digest_on(Backend::Portable, &slice), "seed {seed}");
        }
    }

    #[test]
    fn backend_choice_and_names() {
        assert_eq!(choose_backend(true, None), Backend::ShaNi);
        assert_eq!(choose_backend(true, Some("portable")), Backend::Portable);
        assert_eq!(choose_backend(true, Some(" Portable ")), Backend::Portable);
        assert_eq!(choose_backend(true, Some("auto")), Backend::ShaNi);
        assert_eq!(choose_backend(true, Some("")), Backend::ShaNi);
        assert_eq!(choose_backend(false, None), Backend::Portable);
        assert_eq!(Backend::ShaNi.code(), BACKEND_SHA_NI);
        assert_eq!(Backend::Portable.name(), "portable");
        if !sha_ni_supported() {
            assert!(Sha256::with_backend(Backend::ShaNi).is_none());
        }
    }

    fn fold_cases() -> Vec<Vec<u8>> {
        let mut cases: Vec<Vec<u8>> = [
            &b""[..], b"a\r\nb", b"a\rb", b"a\r", b"\r\r\n", b"\r", b"\n\r", b"\r\n", b"\r\n\r\n",
            b"\r\r", b"\n\n", b"abc", b"x\r\ny\rz\r\n\r", b"\r\r\r\n\n\r",
        ]
        .iter()
        .map(|case| case.to_vec())
        .collect();
        // CR/LF-rich noise.
        for seed in 1..40u64 {
            let bytes = noise(seed, (seed as usize * 37) % 300)
                .into_iter()
                .map(|byte| match byte % 5 {
                    0 => CR,
                    1 => LF,
                    _ => b'a' + byte % 26,
                })
                .collect();
            cases.push(bytes);
        }
        cases
    }

    #[test]
    fn crlf_fold_matches_the_per_byte_rule_at_every_read_size() {
        for backend in backends() {
            for case in fold_cases() {
                let (folded_bytes, folded) = reference_fold(&case);
                let expected = digest_on(backend, &folded_bytes);
                for read in [1usize, 2, 3, 4, 5, 7, 8, 64, 4096] {
                    let mut buffer = vec![0u8; read];
                    let row = hash_reader(&mut &case[..], true, &mut buffer, backend);
                    assert_eq!(row.status, STATUS_OK);
                    assert_eq!(row.digest, expected, "{backend:?} read {read} case {case:?}");
                    assert_eq!(row.folded, folded, "{backend:?} read {read} case {case:?}");
                    assert_eq!(row.bytes, case.len() as u64);
                    let raw = hash_reader(&mut &case[..], false, &mut buffer, backend);
                    assert_eq!(raw.digest, digest_on(backend, &case));
                    assert!(!raw.folded);
                }
            }
        }
    }

    struct Temp(PathBuf);

    impl Temp {
        fn new(label: &str) -> Self {
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|value| value.as_nanos())
                .unwrap_or(0);
            let path = std::env::temp_dir().join(format!("rl-digest-{label}-{}-{nanos}", std::process::id()));
            std::fs::create_dir_all(&path).unwrap();
            Self(path)
        }

        fn write(&self, name: &str, bytes: &[u8]) -> PathBuf {
            let path = self.0.join(name);
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).unwrap();
            }
            let mut file = File::create(&path).unwrap();
            file.write_all(bytes).unwrap();
            path
        }
    }

    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn utf8(path: &Path) -> Vec<u8> {
        path.to_str().unwrap().as_bytes().to_vec()
    }

    #[test]
    fn files_empty_missing_directory_non_ascii_long_and_bad_paths() {
        let temp = Temp::new("files");
        let big = noise(3, READ_BYTES * 2 + 3);
        let mut crlf_at_boundary = vec![b'x'; READ_BYTES - 1];
        crlf_at_boundary.extend_from_slice(b"\r\nend\r");
        let long_name = format!("{}/{}.bin", "d".repeat(120), "f".repeat(150));
        let files = [
            ("empty.bin", Vec::new()),
            ("small.bin", b"hello".to_vec()),
            ("big.bin", big.clone()),
            ("block.bin", big[..READ_BYTES].to_vec()),
            ("block-1.bin", big[..READ_BYTES - 1].to_vec()),
            ("block+1.bin", big[..READ_BYTES + 1].to_vec()),
            ("crlf.json", crlf_at_boundary.clone()),
        ];
        let mut paths = Vec::new();
        let mut expected = Vec::new();
        for (name, bytes) in files.iter() {
            paths.push(temp.write(name, bytes));
            expected.push(sha256(bytes));
        }
        let unicode = temp.write("café ünïcødé 名前 😀.bin", b"non-ascii");
        paths.push(unicode.clone());
        expected.push(sha256(b"non-ascii"));
        let long = temp.write(&long_name, b"long path");
        assert!(long.as_os_str().len() > 260, "fixture path is longer than MAX_PATH");
        paths.push(long.clone());
        expected.push(sha256(b"long path"));
        let mut buffer = Vec::new();
        for (path, digest) in paths.iter().zip(&expected) {
            let row = hash_file(&utf8(path), 0, &mut buffer);
            assert_eq!(row.status, STATUS_OK, "{path:?}");
            assert_eq!(&row.digest, digest, "{path:?}");
            assert_eq!(row.bytes, std::fs::metadata(path).unwrap().len());
        }
        assert!(buffer.len() <= READ_BYTES);
        // Fold on a file whose CRLF straddles the first read.
        let (folded_bytes, _) = reference_fold(&crlf_at_boundary);
        let folded = hash_file(&utf8(&temp.0.join("crlf.json")), FLAG_FOLD_CRLF | 0x40, &mut buffer);
        assert_eq!(folded.digest, sha256(&folded_bytes));
        assert!(folded.folded);
        // Unknown flag bits alone change nothing.
        assert_eq!(hash_file(&utf8(&temp.0.join("crlf.json")), 0x40, &mut buffer).digest, sha256(&crlf_at_boundary));
        // Failures.
        let missing = temp.0.join("missing.bin");
        assert_eq!(hash_file(&utf8(&missing), 0, &mut buffer).status, STATUS_OPEN);
        assert_eq!(hash_file(&utf8(&temp.0), 0, &mut buffer).status, STATUS_OPEN);
        for bad in [&b""[..], b"relative/file.bin", b"res://world.json", b"user://x", b"C:/nul\0byte", b"\xff\xfe/x"] {
            assert_eq!(hash_file(bad, 0, &mut buffer).status, STATUS_BAD_PATH, "{bad:?}");
        }
        #[cfg(windows)]
        assert_eq!(hash_file(b"/rooted/without/drive", 0, &mut buffer).status, STATUS_BAD_PATH);
        let too_long = vec![b'a'; MAX_PATH_BYTES + 1];
        assert_eq!(hash_file(&too_long, 0, &mut buffer).status, STATUS_BAD_PATH);
    }

    #[test]
    fn batches_keep_caller_order_on_any_thread_count_and_mark_each_row() {
        let temp = Temp::new("batch");
        let mut rows: Vec<Vec<u8>> = Vec::new();
        let mut expected = Vec::new();
        for index in 0..37usize {
            let bytes = noise(index as u64 + 11, index * 977 % 70_000);
            rows.push(utf8(&temp.write(&format!("f{index:02}.bin"), &bytes)));
            expected.push((STATUS_OK, sha256(&bytes)));
        }
        rows.insert(5, b"relative.bin".to_vec());
        expected.insert(5, (STATUS_BAD_PATH, [0; 32]));
        rows.insert(9, utf8(&temp.0.join("absent.bin")));
        expected.insert(9, (STATUS_OPEN, [0; 32]));
        rows.push(rows[0].clone());
        expected.push(expected[0]);
        let paths: Vec<&[u8]> = rows.iter().map(|row| row.as_slice()).collect();
        for threads in [0usize, 1, 2, 3, 4, 8, 64, 1000] {
            let (results, used) = hash_files(&paths, &[], threads);
            assert!(used >= 1 && used <= threads.clamp(1, MAX_THREADS).min(paths.len()), "threads {threads} used {used}");
            assert_eq!(results.len(), paths.len());
            for (index, (row, (status, digest))) in results.iter().zip(&expected).enumerate() {
                assert_eq!(row.status, *status, "threads {threads} row {index}");
                if *status == STATUS_OK {
                    assert_eq!(&row.digest, digest, "threads {threads} row {index}");
                } else {
                    assert_eq!(row.digest, [0; 32]);
                    assert_eq!(row.bytes, 0);
                }
            }
        }
        let (empty, used) = hash_files(&[], &[], 4);
        assert!(empty.is_empty());
        assert_eq!(used, 1);
        // Flags shorter than the rows: missing entries are 0.
        let crlf = utf8(&temp.write("text.json", b"a\r\nb"));
        let (rows_flags, _) = hash_files(&[&crlf, &crlf], &[FLAG_FOLD_CRLF], 2);
        assert_eq!(rows_flags[0].digest, sha256(b"a\nb"));
        assert!(rows_flags[0].folded);
        assert_eq!(rows_flags[1].digest, sha256(b"a\r\nb"));
        assert!(!rows_flags[1].folded);
        // Verify: per-row pass/fail in caller order, absent expectations fail.
        let good = sha256(b"a\r\nb");
        let (_, passed, _) = verify_files(&[&crlf, &crlf, &crlf, b"x"], &[], &[good, [1; 32], good, good], None, 2);
        assert_eq!(passed, vec![true, false, true, false]);
        let (_, passed, _) = verify_files(&[&crlf, &crlf], &[], &[good, good], Some(&[1, 0]), 1);
        assert_eq!(passed, vec![true, false]);
        let (_, passed, _) = verify_files(&[&crlf], &[], &[], None, 1);
        assert_eq!(passed, vec![false]);
    }
}
