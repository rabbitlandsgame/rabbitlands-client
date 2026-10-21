#!/usr/bin/env python3
"""How late game packets reach the client at low frame rates, before and after.

Runs a probe server that writes EL-framed packets on a fixed cadence the way
the RL server writes - asyncio streams, optionally TLS, one write per flush, so
every write is one TLS record - and drives tests/integration/socket_read_latency.gd
against it. For each scenario it reports, in milliseconds after the packet
reached the socket:

  dispatch  when packet_received handed it to the game,
  present   when a Main-style deferred world sync could first draw it,

plus the interval error of a steady "own step" stream as the movement pacing
stamps it (at the world sync), and the Godot process's CPU time.

  python tests/integration/socket_read_latency.py --godot PATH \
      [--compare OLD_network_client.gd] [--scenario NAME ...] [--out FILE]

--compare loads another copy of network_client.gd (its class_name line is
stripped) for a before/after in one run, e.g. `git show develop:godot-client/src/
network/network_client.gd > old.gd`. The Nagle scenarios need a peer that
delays ACKs, which Windows loopback does not: --wsl-distro runs the server in a
WSL2 distribution and connects to the VM's own address. Needs `cryptography`
for the throwaway certificate; `psutil` (optional) for CPU time.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import ipaddress
import json
import os
import shutil
import ssl
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
PROBE = "res://tests/integration/socket_read_latency.gd"
CMD = 250

# Frame caps of 21 and 29 FPS and a 233-ms own-step stream are deliberately
# not multiples of the 50-ms server tick, so packet phases sweep the frame.
STEADY = ["--tick-ms", "50", "--frames-per-tick", "3", "--own-ms", "233"]
SCENARIOS = {
    # Sleep-bound frames: 20 tick writes + ~4.3 own-step writes per second.
    "tls_21fps": (True, STEADY, {"fps": 21}),
    "tls_29fps": (True, STEADY, {"fps": 29}),
    # A second flush per tick (the AI loop and the outbox loop both flush).
    "tls_29fps_two_flushes": (True, STEADY + ["--extra-per-tick", "1"], {"fps": 29}),
    "tls_60fps": (True, STEADY, {"fps": 60}),
    # CPU-bound frames (~24 FPS): physics ticks, _process work before the
    # world sync, and work after it standing in for rendering.
    "tls_busy_24fps": (True, STEADY, {"fps": 0, "busy-physics-ms": 4,
                                      "busy-process-ms": 15, "busy-after-ms": 15}),
    "tcp_busy_24fps": (False, STEADY, {"fps": 0, "busy-physics-ms": 4,
                                       "busy-process-ms": 15, "busy-after-ms": 15}),
}
NAGLE = {
    # A silent server: nothing to piggyback an ACK on, as between server ticks.
    "nagle_tcp": (False, ["--tick-ms", "100000", "--own-ms", "0", "--frames-per-tick", "1"],
                  {"fps": 60, "pair-ms": 100}),
    "nagle_tls": (True, ["--tick-ms", "100000", "--own-ms", "0", "--frames-per-tick", "1"],
                  {"fps": 60, "pair-ms": 100}),
}


# --- probe server -------------------------------------------------------------

def _frame(kind: int, seq: int) -> bytes:
    payload = struct.pack("<BIQ", kind, seq, time.perf_counter_ns())
    return struct.pack("<BH", CMD, len(payload) + 1) + payload


async def _pump(writer, args, stats) -> None:
    await asyncio.sleep(args.warmup)
    seq = 0
    start = time.perf_counter()
    end = start + args.duration
    tick, own = args.tick_ms / 1000.0, args.own_ms / 1000.0
    next_tick, next_own, next_extra = start, start + 0.013, start + 0.025
    while True:
        now = time.perf_counter()
        if now >= end:
            break
        due = min(next_tick, next_own if own > 0 else end, next_extra if args.extra_per_tick else end, end)
        if due > now:
            # asyncio sleeps in ~15.6-ms steps on Windows: sleep short, then spin.
            if due - now > 0.003:
                await asyncio.sleep(due - now - 0.002)
                continue
            while time.perf_counter() < due:
                pass
        now = time.perf_counter()
        if now >= next_tick:
            writer.write(b"".join(_frame(1, seq + i) for i in range(args.frames_per_tick)))
            seq += args.frames_per_tick
            stats["writes"] += 1
            next_tick += tick
        if own > 0 and now >= next_own:
            writer.write(_frame(2, seq))
            seq += 1
            stats["writes"] += 1
            next_own += own
        if args.extra_per_tick and now >= next_extra:
            for _ in range(args.extra_per_tick):
                writer.write(_frame(3, seq))
                seq += 1
                stats["writes"] += 1
            next_extra += tick
        if writer.transport.get_write_buffer_size() > 64 * 1024:
            await writer.drain()
        await asyncio.sleep(0)
    stats["sent"] = seq
    writer.write(struct.pack("<BH", CMD, 2) + b"\xff")
    await writer.drain()


async def _serve(args) -> None:
    context = None
    if args.cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.options |= ssl.OP_NO_COMPRESSION
        context.load_cert_chain(args.cert, args.key)
    done = asyncio.get_running_loop().create_future()

    async def handle(reader, writer):
        stats = {"writes": 0, "client_frames": []}
        task = asyncio.create_task(_pump(writer, args, stats))
        buffer = b""
        try:
            while data := await reader.read(65536):
                arrived = time.perf_counter_ns()
                buffer += data
                while len(buffer) >= 3:
                    command, length = struct.unpack_from("<BH", buffer, 0)
                    if len(buffer) < 2 + length:
                        break
                    stats["client_frames"].append([arrived, command, buffer[3:2 + length].hex()])
                    buffer = buffer[2 + length:]
        except (ConnectionError, ssl.SSLError):
            pass
        task.cancel()
        try:
            await task
        except BaseException:
            pass
        writer.close()
        Path(args.log).write_text(json.dumps(stats))
        if not done.done():
            done.set_result(True)

    server = await asyncio.start_server(handle, args.host, args.port, ssl=context)
    print("listening", flush=True)
    try:
        await asyncio.wait_for(done, timeout=args.warmup + args.duration + 90)
    finally:
        server.close()


# --- runner ---------------------------------------------------------------------

def _certificate(folder: Path, address: str) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, address)])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - datetime.timedelta(days=1))
                   .not_valid_after(now + datetime.timedelta(days=2))
                   .add_extension(x509.SubjectAlternativeName(
                       [x509.IPAddress(ipaddress.ip_address(address))]), False)
                   .sign(key, hashes.SHA256()))
    cert, private = folder / f"{address}.crt", folder / f"{address}.key"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                          serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return cert, private


def _wsl_path(path: Path) -> str:
    text = str(path.resolve()).replace("\\", "/")
    return "/mnt/" + text[0].lower() + text[2:]


def _pct(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(p / 100.0 * (len(ordered) - 1))))]


def _stats(values):
    if not values:
        return {}
    return {"p50": round(_pct(values, 50), 1), "p95": round(_pct(values, 95), 1),
            "max": round(max(values), 1), "mean": round(statistics.fmean(values), 1)}


def _summarize(probe: dict, server: dict, own_ms: float) -> dict:
    records = probe["records"]
    out: dict = {"packets": len(records), "sent": server.get("sent"), "writes": server.get("writes"),
                 "idle_read_usec_per_frame": None}
    if records:
        sent = [r[2] / 1000.0 for r in records]
        dispatched = [r[3] for r in records]
        presented = {index: at for index, at in probe["presented"]}
        # Both clocks are QueryPerformanceCounter-based on one machine but have
        # different origins; the smallest observed delay is taken as zero.
        offset = min(d - s for d, s in zip(dispatched, sent))
        dispatch = [(d - s - offset) / 1000.0 for d, s in zip(dispatched, sent)]
        present = [(presented[i] - sent[i] - offset) / 1000.0
                   for i in range(len(records)) if i in presented]
        third = max(1, len(dispatch) // 3)
        own = [presented[i] for i, r in enumerate(records) if r[0] == 2 and i in presented]
        errors = [(b - a) / 1000.0 - own_ms for a, b in zip(own, own[1:])]
        out.update({
            "dispatch_ms": _stats(dispatch), "present_ms": _stats(present),
            "dispatch_mean_first_third_ms": round(statistics.fmean(dispatch[:third]), 1),
            "dispatch_mean_last_third_ms": round(statistics.fmean(dispatch[-third:]), 1),
            "own_step_interval_error_ms": {
                "sd": round(statistics.pstdev(errors), 1),
                "p95_abs": round(_pct([abs(e) for e in errors], 95), 1)} if len(errors) > 1 else {},
        })
    starts = probe["frame_starts"]
    if len(starts) > 2:
        out["fps"] = round(1e6 * (len(starts) - 1) / (starts[-1] - starts[0]), 1)
    physics = probe["physics_starts"]
    if len(physics) > 2:
        gaps = [(b - a) / 1000.0 for a, b in zip(physics, physics[1:])]
        out["physics_tick_gap_ms"] = {"p10": round(_pct(gaps, 10), 3), "p50": round(_pct(gaps, 50), 3),
                                      "p90": round(_pct(gaps, 90), 1)}
    fires = probe.get("timer_fires", [])
    if len(fires) > 2 and len(starts) > 2:
        import bisect
        per_frame: dict = {}
        for at in fires:
            frame = bisect.bisect_right(starts, at)
            per_frame[frame] = per_frame.get(frame, 0) + 1
        out["timer"] = {"wait_ms": float(probe["opts"]["timer-ms"]),
                        "fires_per_s": round(1e6 * len(fires) / (starts[-1] - starts[0]), 1),
                        "most_in_one_frame": max(per_frame.values())}
    idle = [probe.get("idle_process_usec", -1), probe.get("idle_late_read_usec", -1)]
    if idle[0] >= 0:
        out["idle_read_usec_per_frame"] = round(idle[0] + max(0.0, idle[1]), 2)
    pairs: dict = {}
    for at, command, body in server.get("client_frames", []):
        if command == CMD:
            raw = bytes.fromhex(body)
            pairs.setdefault(int.from_bytes(raw[:4], "little"), {})[raw[4]] = at
    gaps = [(v[1] - v[0]) / 1e6 for v in pairs.values() if 0 in v and 1 in v]
    if gaps:
        out["pair_gap_ms"] = {"n": len(gaps), "p50": round(_pct(gaps, 50), 2),
                              "p95": round(_pct(gaps, 95), 2), "max": round(max(gaps), 2)}
    return out


def _run(options, folder: Path, label: str, script: str, tls: bool, server_flags, probe_flags,
         port: int, duration: float, wsl_ip: str | None) -> dict:
    probe_json, server_json = folder / f"{label}.probe.json", folder / f"{label}.server.json"
    address = wsl_ip or "127.0.0.1"
    cert, key = _certificate(folder, address) if tls else (None, None)
    here = Path(__file__).resolve()
    if wsl_ip:
        command = ["wsl.exe", "-d", options.wsl_distro, "--", "python3", "-I", _wsl_path(here),
                   "--serve", "--host", "0.0.0.0", "--log", _wsl_path(server_json)]
        if tls:
            command += ["--cert", _wsl_path(cert), "--key", _wsl_path(key)]
    else:
        command = [sys.executable, "-I", str(here), "--serve", "--host", address,
                   "--log", str(server_json)]
        if tls:
            command += ["--cert", str(cert), "--key", str(key)]
    command += ["--port", str(port), "--duration", str(duration)] + server_flags
    server = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    try:
        if server.stdout.readline().strip() != "listening":
            raise RuntimeError(f"{label}: probe server did not start")
        env = dict(os.environ, APPDATA=str(folder / "appdata"))
        godot = [options.godot, "--headless", "--path", str(PROJECT), "--script", PROBE,
                 "--log-file", str(folder / f"{label}.godot.log"), "--",
                 f"--net-script={script}", f"--host={address}", f"--port={port}",
                 f"--timeout={duration + 20}", f"--out={probe_json}"]
        godot += [f"--{name}={value}" for name, value in probe_flags.items()]
        if tls:
            godot += ["--tls", f"--cert={cert}"]
        cpu = _run_godot(godot, env, duration + 90)
        server.wait(timeout=60)
    finally:
        if server.poll() is None:
            server.kill()
    summary = _summarize(json.loads(probe_json.read_text()), json.loads(server_json.read_text()),
                         233.0)
    summary["cpu_s"] = cpu
    return summary


def _run_godot(command, env, timeout) -> float | None:
    try:
        import psutil
    except ImportError:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                       timeout=timeout, check=False)
        return None
    # The console build is a launcher; the engine runs in its child process.
    process = psutil.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    seen, used = {}, {}
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        try:
            for child in [process] + process.children(recursive=True):
                seen.setdefault(child.pid, child)
        except psutil.Error:
            pass
        for pid, child in seen.items():
            try:
                times = child.cpu_times()
                used[pid] = times.user + times.system
            except psutil.Error:
                pass
        time.sleep(0.05)
    if process.poll() is None:
        process.kill()
    return round(sum(used.values()), 3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=24601)
    parser.add_argument("--cert", help=argparse.SUPPRESS)
    parser.add_argument("--key", help=argparse.SUPPRESS)
    parser.add_argument("--log", help=argparse.SUPPRESS)
    parser.add_argument("--tick-ms", type=float, default=50, help=argparse.SUPPRESS)
    parser.add_argument("--frames-per-tick", type=int, default=3, help=argparse.SUPPRESS)
    parser.add_argument("--own-ms", type=float, default=233, help=argparse.SUPPRESS)
    parser.add_argument("--extra-per-tick", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--warmup", type=float, default=1.0, help=argparse.SUPPRESS)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--godot", default=shutil.which("godot"))
    parser.add_argument("--compare", type=Path, help="older network_client.gd to measure first")
    parser.add_argument("--scenario", action="append", choices=sorted({**SCENARIOS, **NAGLE, "timer": 0}))
    parser.add_argument("--wsl-distro", help="run the Nagle scenarios against a server in this WSL2 distro")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--out", type=Path)
    options = parser.parse_args()
    if options.serve:
        asyncio.run(_serve(options))
        return
    if not options.godot:
        parser.error("pass --godot PATH or put godot on PATH")
    folder = Path(tempfile.mkdtemp(prefix="rl-socket-latency-"))
    variants = {}
    if options.compare:
        source = options.compare.read_text(encoding="utf-8").splitlines(keepends=True)
        if source and source[0].startswith("class_name "):
            source[0] = "# class_name removed for side-by-side measurement\n"
        old = folder / "compare_network_client.gd"
        old.write_text("".join(source), encoding="utf-8")
        variants["before"] = str(old).replace("\\", "/")
    variants["after"] = "res://src/network/network_client.gd"
    chosen = options.scenario or sorted(SCENARIOS) + (sorted(NAGLE) if options.wsl_distro else [])
    wsl_ip = None
    if options.wsl_distro and any(name in NAGLE for name in chosen):
        wsl_ip = subprocess.run(["wsl.exe", "-d", options.wsl_distro, "--", "hostname", "-I"],
                                capture_output=True, text=True, check=True).stdout.split()[0]
    results: dict = {"godot": options.godot, "duration_s": options.duration, "scenarios": {}}
    port = options.port
    for name in chosen:
        if name == "timer":
            tls, server_flags, probe_flags = True, STEADY, {"fps": 21, "timer-ms": 5}
        else:
            tls, server_flags, probe_flags = {**SCENARIOS, **NAGLE}[name]
        for variant, script in variants.items():
            for repeat in range(options.repeat):
                port += 1
                label = f"{name}.{variant}" + (f".{repeat}" if options.repeat > 1 else "")
                summary = _run(options, folder, label, script, tls, server_flags, probe_flags, port,
                               options.duration, wsl_ip if name in NAGLE else None)
                results["scenarios"].setdefault(name, {})[label.split(".", 1)[1]] = summary
                print(label, json.dumps({k: summary.get(k) for k in
                                         ("dispatch_ms", "present_ms", "pair_gap_ms", "cpu_s")}),
                      flush=True)
    text = json.dumps(results, indent=1)
    if options.out:
        options.out.write_text(text + "\n")
    print(f"raw logs in {folder}")


if __name__ == "__main__":
    main()
