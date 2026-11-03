//! Micro-benchmark of the content digest (not shipped; `cargo test` only
//! compiles it). Run from `native/client_runtime/core`:
//!
//! ```text
//! cargo +1.99.1 run --release --offline --locked --example digest_bench -- <list> [threads] [reps] [mode]
//! ```
//!
//! `<list>` holds one absolute path per line. `mode`:
//! * `files` (default): `hash_files` over the list on `threads` threads (the
//!   caller included), open + read + hash, best and median of `reps`.
//!   `RABBITLANDS_CONTENT_DIGEST_SHA=portable` measures the portable backend.
//! * `fold`: as `files` with FLAG_FOLD_CRLF on every row.
//! * `memory`: reads every file once, then hashes the bytes in memory on one
//!   thread with each backend this CPU has (pure hash speed).
use std::time::Instant;

use rabbitlands_client_core::digest::{
    Backend, FLAG_FOLD_CRLF, STATUS_OK, Sha256, backend, hash_files, sha_ni_supported,
};

fn summary(label: &str, bytes: u64, mut samples: Vec<f64>) {
    samples.sort_by(|a, b| a.total_cmp(b));
    let best = samples[0];
    let median = samples[samples.len() / 2];
    let rate = bytes as f64 / (best / 1000.0) / 1e6;
    println!("{label:<36} MiB {:>8.2}  best {best:>9.2} ms  median {median:>9.2} ms  {rate:>8.0} MB/s",
        bytes as f64 / 1048576.0);
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let Some(list) = args.get(1) else {
        eprintln!("usage: digest_bench <list> [threads] [reps] [files|fold|memory]");
        std::process::exit(2);
    };
    let threads: usize = args.get(2).and_then(|value| value.parse().ok()).unwrap_or(1);
    let reps: usize = args.get(3).and_then(|value| value.parse().ok()).unwrap_or(7).max(1);
    let mode = args.get(4).map(String::as_str).unwrap_or("files");
    let text = std::fs::read_to_string(list).expect("list file");
    let rows: Vec<String> = text.lines().map(str::trim).filter(|line| !line.is_empty()).map(String::from).collect();
    let paths: Vec<&[u8]> = rows.iter().map(|row| row.as_bytes()).collect();
    match mode {
        "memory" => {
            let buffers: Vec<Vec<u8>> = rows.iter().map(|row| std::fs::read(row).expect("readable file")).collect();
            let bytes: u64 = buffers.iter().map(|buffer| buffer.len() as u64).sum();
            let mut backends = vec![Backend::Portable];
            if sha_ni_supported() {
                backends.push(Backend::ShaNi);
            }
            for which in backends {
                let mut samples = Vec::new();
                let mut sink = 0u8;
                for _ in 0..reps {
                    let began = Instant::now();
                    for buffer in &buffers {
                        let mut hasher = Sha256::with_backend(which).expect("backend");
                        hasher.update(buffer);
                        sink ^= hasher.finish()[0];
                    }
                    samples.push(began.elapsed().as_secs_f64() * 1000.0);
                }
                summary(&format!("memory {} x1 (sink {sink})", which.name()), bytes, samples);
            }
        }
        "files" | "fold" => {
            let flags = vec![if mode == "fold" { FLAG_FOLD_CRLF } else { 0 }; paths.len()];
            let mut samples = Vec::new();
            let mut bytes = 0;
            let mut used = 0;
            for _ in 0..reps {
                let began = Instant::now();
                let (results, threads_used) = hash_files(&paths, &flags, threads);
                samples.push(began.elapsed().as_secs_f64() * 1000.0);
                let failed = results.iter().filter(|row| row.status != STATUS_OK).count();
                assert_eq!(failed, 0, "every listed file must hash");
                bytes = results.iter().map(|row| row.bytes).sum();
                used = threads_used;
            }
            summary(&format!("{mode} {} x{used} ({} files)", backend().name(), paths.len()), bytes, samples);
        }
        other => {
            eprintln!("unknown mode {other}");
            std::process::exit(2);
        }
    }
}
