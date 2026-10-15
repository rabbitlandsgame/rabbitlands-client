# Native crowd lifecycle packet benchmark

`tests/integration/crowd_lifecycle_benchmark.gd` measures actor arrival and departure through the real protocol decoder and `AppState`, without instantiating `Main` or actor scenes. It covers mixed `ADD_NEW_ACTOR` and `ADD_NEW_ACTOR_EXTENDED` packets plus batched `REMOVE_ACTOR` packets at 100, 200, 300, and 500 actors. Each backend records nine add samples and nine remove samples at every count.

Correctness work stays outside each timed interval. Every add batch is compared with independently decoded actor dictionaries; dirty actor counts are checked; removal must empty the state without leaving dirty records; commands for removed and unknown actors must not recreate state; and reusing a removed id must produce only the fresh spawn dictionary and one dirty id.

From the `godot-client` directory, run both backends serially with the focused runner and the real Godot executable copied into this checkout:

```powershell
.\scripts\run_crowd_lifecycle_benchmark.ps1 `
    -GodotPath .\Godot_v4.7.2-stable_win64.exe `
    -InterferenceLabel "shared host; describe observed interference here"
```

The runner binds itself to affinity mask `0xF`, verifies that each direct Godot process keeps the inherited mask at 250 ms intervals, requests at most four workers, and uses `--single-threaded-scene`. It places `APPDATA`, `LOCALAPPDATA`, `USERPROFILE`, `TEMP`, Godot user data, logs, and JSON artifacts under this worktree. The benchmark verifies the actual `OS.get_user_data_dir()`. Per-backend process JSON records the executable and start time, affinity observations, exit status, script-error scan, report validation, exact source and binary hashes, commit, inputs, and their composite hashes. A timeout, nonzero exit, logged script error, or invalid report stops the serial run. Results and stdout, stderr, Godot, and process logs are written under `test-artifacts/native-crowd/lifecycle`.

The two JSON reports expose the active backend, raw samples, median, p95, minimum, and maximum add/remove milliseconds per batch. They also record the commit, a composite source hash, Godot version, run time, shared-host label, packet shape, protocol-error count, and machine-readable correctness failures. Compare like actor counts between the two reports. This benchmark covers only network decode and state lifecycle; the crowd harness remains the source for scene spawn/despawn and presentation costs.
