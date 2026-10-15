# Verified bounded command runner

`run_verified_limited.py` runs one frozen command without a shell. It checks the
complete JSON schema, resolves and compares `argv[0]` and `argv[1]` with the two
expected paths supplied independently on the command line, then verifies every
SHA-256 pin before starting the child. The approved Python and wrapper must both
appear in `pins`. Relative invocation paths resolve against the verifier's
working directory and are replaced with their canonical approved paths before
execution under the command's `cwd`; using absolute paths is recommended.

```powershell
C:\Python\Python313\python.exe eloria-assets\tools\run_verified_limited.py run.json `
  --expected-python C:\Python\Python313\python.exe `
  --expected-run-limited C:\path\to\run_limited.py
```

The JSON object requires `argv`, `pins`, `cwd`, a finite positive
`timeoutSeconds`, and the six distinct paths `argvLog`, `stdoutLog`,
`stderrLog`, `exitLog`, `timingLog`, and `resultLog`. Unknown keys are rejected.
Paths are resolved before comparison. `cwd` must already exist. Parent
directories for logs are created after structural validation. Pins contain
exactly `path` and `sha256`; duplicate paths, malformed digests, and output/input
collisions are rejected.

The timeout covers command execution after preflight and launcher setup. The
requested command receives ordinary inherited environment but noninteractive
stdin (the verifier uses the launcher's pipe solely as its release gate).

The argv record is written before launch. An approved-Python launcher waits on
stdin while the verifier attaches its PID to the owned job/process group; the
record is then updated with both launcher and requested argv before the gate is
released. The result JSON records `success`, `nonzero`, `preflight_failed`,
`runtime_failed`, `timeout`, or `interrupted`, plus elapsed time and exit
information. Timeout and interrupt stop only the created PID tree (a
kill-on-close Windows job or a dedicated process group elsewhere). Exit codes
are 125 for preflight/runtime setup failure, 124 for timeout, and 130 for
interruption; ordinary child exit codes propagate. If output paths are unsafe,
the verifier reports only to its own stderr and leaves every referenced file
unchanged.
