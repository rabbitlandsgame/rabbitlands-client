"""Bounded host-side memory observations of the runner's own child process."""
from __future__ import annotations

import os
import time

INTERVAL_SECONDS = 1.0
MAX_SERIES_SAMPLES = 4096
METRICS = ("workingSetBytes", "privateBytes", "osPeakWorkingSetBytes", "osPeakPrivateCommitBytes")


def _owned_windows_reader(process):
    """Borrow Popen's handle; never open another process or close its handle."""
    if os.name != "nt":
        raise OSError("unsupported_platform: Windows process memory API unavailable")
    handle = getattr(process, "_handle", None)
    if not isinstance(handle, int) or isinstance(handle, bool) or handle <= 0:
        raise OSError("owned_process_handle_unavailable")
    import ctypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]

    api = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    api.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_uint32]
    api.restype = ctypes.c_int

    def read():
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not api(ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return {"workingSetBytes": counters.WorkingSetSize, "privateBytes": counters.PrivateUsage,
                "osPeakWorkingSetBytes": counters.PeakWorkingSetSize,
                "osPeakPrivateCommitBytes": counters.PeakPagefileUsage}

    return read


class ProcessMemorySampler:
    """At most one query per second; unavailable is explicit, never zero.

    Working set is resident process memory. PrivateUsage and PeakPagefileUsage
    are private committed bytes and its OS lifetime peak, not GPU allocations
    or allocator-only Godot memory. OS peaks are observed values; their true
    peak occurrence time is not supplied by Windows.
    """

    def __init__(self, process, started_monotonic: float, *, reader_factory=None,
                 clock=None, wall_clock=None, series_limit=MAX_SERIES_SAMPLES):
        self.pid = process.pid
        self.started = started_monotonic
        self.clock = clock or time.monotonic
        self.wall_clock = wall_clock or time.time
        self.limit = min(MAX_SERIES_SAMPLES, max(0, int(series_limit)))
        self.last_attempt = None
        self.samples = []
        self.count = 0
        self.peaks = {key: None for key in METRICS}
        self.failure = None
        self.query_total_usec = 0
        self.query_max_usec = 0
        self.reader = None
        try:
            self.reader = (reader_factory or _owned_windows_reader)(process)
        except Exception as error:
            self._fail(error, self.clock())

    def _stamp(self, now: float) -> dict:
        return {"elapsedSeconds": round(max(0.0, now - self.started), 6),
                "unixTime": round(self.wall_clock(), 3)}

    def _fail(self, error: Exception, now: float) -> None:
        self.failure = self._stamp(now) | {"reason": type(error).__name__ + ": " + str(error)}
        self.reader = None  # Stop repeated failure work/logging; preserve earlier observations.

    def sample_if_due(self, now: float | None = None) -> bool:
        if self.reader is None:
            return False
        now = self.clock() if now is None else now
        if self.last_attempt is not None and now - self.last_attempt < INTERVAL_SECONDS:
            return False
        self.last_attempt = now
        query_started = time.perf_counter_ns()
        try:
            raw = self.reader()
            values = {}
            for key in METRICS:
                value = raw.get(key)
                # An absent OS peak is not a zero-byte observation. Current
                # process values must be positive before a sample is accepted.
                if type(value) is int and value > 0:
                    values[key] = value
                elif key.startswith("osPeak") and (value is None or type(value) is int and value == 0):
                    values[key] = None
                else:
                    raise ValueError("unavailable/nonpositive memory counter: " + key)
            stamp = self._stamp(now)
            sample = stamp | values
            self.count += 1
            if len(self.samples) < self.limit:
                self.samples.append(sample)
            for key, value in values.items():
                peak = self.peaks[key]
                if value is not None and (peak is None or value > peak["bytes"]):
                    self.peaks[key] = {"bytes": value, "observedAt": stamp.copy()}
            return True
        except Exception as error:
            self._fail(error, now)
            return False
        finally:
            cost = max(0, (time.perf_counter_ns() - query_started) // 1000)
            self.query_total_usec += cost
            self.query_max_usec = max(self.query_max_usec, cost)

    def snapshot(self) -> dict:
        status = "partial" if self.count and self.failure else "available" if self.count else "unavailable"
        reason = self.failure
        if not self.count and reason is None:
            reason = {"reason": "no_workload_wait_sample_observed"}
        return {"schemaVersion": 1, "pid": self.pid, "status": status,
                "source": "Windows.GetProcessMemoryInfo(PROCESS_MEMORY_COUNTERS_EX)",
                "handleScope": "borrowed owned Popen._handle; never opened or closed by sampler",
                "window": "acknowledged workload wait, including teardown; excludes identity hashing",
                "intervalSeconds": INTERVAL_SECONDS, "sampleCount": self.count,
                "seriesLimit": self.limit, "seriesTruncated": self.count > len(self.samples),
                "samples": list(self.samples), "peaks": self.peaks.copy(), "unavailableReason": reason,
                "queryOverheadMicroseconds": {"total": self.query_total_usec, "maximum": self.query_max_usec},
                "limits": ["OS peaks cover process lifetime only through the last successful observation",
                           "sampled current peaks can miss events between one-second observations",
                           "OS peak timestamps are observation times, not true peak occurrence times",
                           "working set and private commit are not allocator-only or GPU memory"]}
