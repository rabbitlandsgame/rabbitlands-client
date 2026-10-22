extends RefCounted
## The server's clock as seen from this machine, for frames the server stamps
## with the time it built them.
##
## Every stamped frame gives one sample of `local arrival - server stamp`: the
## one-way delay plus whatever the two clocks disagree by. The smallest sample
## over a window is the delay of an unloaded link, so `server stamp + that
## minimum` is when a frame would have arrived had nothing held it up - a time
## on the local clock, free of jitter, that remote motion can be scheduled
## against. How far each real arrival lands above it is the jitter a playout
## buffer has to cover: queueing, a wireless hold, a frame the server sent
## late, and this client reading its socket once or twice a frame.
##
## Stamps are milliseconds on a wrapping counter (`stamp_modulus`); they are
## unwrapped against the newest one seen, so a long session and a stamp that
## arrives a little out of order are both read correctly.

## The minimum is taken over WINDOW_BUCKETS buckets of this many milliseconds,
## so a route that got slower is noticed within the window rather than never.
const WINDOW_BUCKET_MSEC := 2000
const WINDOW_BUCKETS := 8
## How many recent excess samples the playout percentile is read from: about
## six seconds of 20 Hz frames.
const EXCESS_SAMPLES := 128
const PLAYOUT_PERCENTILE := 0.95
## Added on top of the percentile, and the floor and ceiling of the result.
## The ceiling matches the most the arrival-time pacing ever buffers.
const PLAYOUT_MARGIN_MSEC := 10.0
const MINIMUM_PLAYOUT_MSEC := 20.0
const MAXIMUM_PLAYOUT_MSEC := 350.0
## Until this many frames have been seen, the delay is at least
## STARTUP_PLAYOUT_MSEC: a link's jitter is not known from a handful of frames,
## and starting short would stop the first walker seen at the first hold.
const WARM_SAMPLES := 20
const STARTUP_PLAYOUT_MSEC := 150.0
## How long a computed playout delay is reused before it is read again.
const PLAYOUT_REFRESH_MSEC := 500
## How fast the offset may rise, in milliseconds per second of local time. A
## better path is taken at once (it only moves the schedule earlier, which the
## pacing absorbs); a worse one is eased in so a schedule never jumps.
const OFFSET_RISE_PER_SECOND := 20.0

var stamp_modulus := 1 << 32
var synced := false
var _newest_stamp := 0
var _offset := 0.0
var _offset_updated_msec := 0
var _bucket_ids := PackedInt64Array()
var _bucket_minima := PackedFloat64Array()
var _excess := PackedFloat32Array()
var _excess_next := 0
var _excess_count := 0
var _playout_msec := -1.0
var _playout_read_msec := -1

func _init() -> void:
	reset()

func reset() -> void:
	synced = false
	_newest_stamp = 0
	_offset = 0.0
	_offset_updated_msec = 0
	_bucket_ids.resize(WINDOW_BUCKETS)
	_bucket_ids.fill(-1)
	_bucket_minima.resize(WINDOW_BUCKETS)
	_bucket_minima.fill(INF)
	_excess.resize(EXCESS_SAMPLES)
	_excess.fill(0.0)
	_excess_next = 0
	_excess_count = 0
	_playout_msec = -1.0
	_playout_read_msec = -1

## One stamped frame: the server's stamp and the local tick it was read at
## (`Time.get_ticks_msec()`). Returns the stamp unwrapped onto this session's
## running count.
func observe(stamp: int, local_msec: int) -> int:
	var server_msec: int = unwrap(stamp)
	if not synced or server_msec > _newest_stamp:
		_newest_stamp = server_msec
	var sample: float = float(local_msec - server_msec)
	var bucket: int = floori(float(local_msec) / float(WINDOW_BUCKET_MSEC))
	var slot: int = posmod(bucket, WINDOW_BUCKETS)
	if _bucket_ids[slot] != bucket:
		_bucket_ids[slot] = bucket
		_bucket_minima[slot] = sample
	else:
		_bucket_minima[slot] = minf(_bucket_minima[slot], sample)
	var target: float = INF
	for index: int in WINDOW_BUCKETS:
		if _bucket_ids[index] > bucket - WINDOW_BUCKETS:
			target = minf(target, _bucket_minima[index])
	if not synced:
		_offset = target
		synced = true
	elif target <= _offset:
		_offset = target
	else:
		var elapsed: float = maxf(0.0, float(local_msec - _offset_updated_msec))
		_offset = minf(target, _offset + OFFSET_RISE_PER_SECOND * elapsed / 1000.0)
	_offset_updated_msec = local_msec
	_excess[_excess_next] = maxf(0.0, sample - _offset)
	_excess_next = (_excess_next + 1) % EXCESS_SAMPLES
	_excess_count = mini(_excess_count + 1, EXCESS_SAMPLES)
	return server_msec

## A stamp as a count of milliseconds on this session's running clock: the
## representative of its residue nearest the newest stamp seen.
func unwrap(stamp: int) -> int:
	var residue: int = posmod(stamp, stamp_modulus)
	if not synced:
		return residue
	var base: int = _newest_stamp - posmod(_newest_stamp, stamp_modulus)
	var candidate: int = base + residue
	var half: int = stamp_modulus >> 1
	if candidate - _newest_stamp > half:
		candidate -= stamp_modulus
	elif _newest_stamp - candidate > half:
		candidate += stamp_modulus
	return candidate

## When a stamp would have been read on an unloaded link, on the local tick
## clock. Unsynced, the stamp is returned unchanged; callers check `synced`.
func to_local_msec(stamp: int) -> int:
	return roundi(float(unwrap(stamp)) + _offset)

## An unwrapped server time (a deadline, say) on the local tick clock.
func server_to_local_msec(server_msec: int) -> int:
	return roundi(float(server_msec) + _offset)

## The server's running clock now, as best this side can tell: the newest
## frame's time, advanced by the local time since it would have arrived.
func server_now_msec(local_msec: int) -> int:
	return roundi(float(local_msec) - _offset)

## The offset in use, local minus server, in milliseconds.
func offset_msec() -> float:
	return _offset

## How long to hold remote motion behind the jitter-free schedule so that
## nearly every frame has arrived before it is needed: the 95th percentile of
## recent lateness plus a margin, within MINIMUM/MAXIMUM_PLAYOUT_MSEC.
func playout_delay_msec(local_msec: int) -> float:
	if _playout_msec >= 0.0 and local_msec - _playout_read_msec < PLAYOUT_REFRESH_MSEC:
		return _playout_msec
	_playout_read_msec = local_msec
	var count: int = _excess_count
	var late: float = 0.0
	if count > 0:
		var ordered: PackedFloat32Array = _excess.slice(0, count)
		ordered.sort()
		late = ordered[mini(count - 1, floori(PLAYOUT_PERCENTILE * float(count)))]
	var floor_msec: float = STARTUP_PLAYOUT_MSEC if count < WARM_SAMPLES else MINIMUM_PLAYOUT_MSEC
	_playout_msec = clampf(late + PLAYOUT_MARGIN_MSEC, floor_msec, MAXIMUM_PLAYOUT_MSEC)
	return _playout_msec
