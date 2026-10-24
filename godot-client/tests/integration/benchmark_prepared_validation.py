"""Validate requested prepared selectors against actual, untimed runtime evidence."""


def configure_prepared_request(args):
    mode = getattr(args, "prepared_content", "raw")
    policy = getattr(args, "prepared_node_policy", "retain")
    if mode not in ("raw", "auto", "require-pilot") or policy not in ("retain", "lazy-source-v1"):
        raise ValueError("unsupported prepared-content/node-policy request")
    if mode == "raw" and policy != "retain":
        raise ValueError("lazy-source-v1 requires prepared content auto or require-pilot")


def _count(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " must be a nonnegative integer")
    return value


def validate_prepared(backends, request, label):
    actual = backends.get("preparedContent")
    if not isinstance(actual, dict):
        raise ValueError(label + ": actual prepared-content snapshot is missing")
    # Historical reports had no selector request and an unimplemented marker.
    # New runner requests always include both fields and require real evidence.
    if "prepared_content" not in request and "prepared_node_policy" not in request:
        return
    mode = request.get("prepared_content", "raw")
    policy = request.get("prepared_node_policy", "retain")
    if mode not in ("raw", "auto", "require-pilot") or policy not in ("retain", "lazy-source-v1"):
        raise ValueError(label + ": invalid prepared selector request")
    if mode == "raw" and policy != "retain":
        raise ValueError(label + ": raw content cannot attest lazy node policy")
    if actual.get("mode") != mode or backends.get("preparedNodePolicy") != policy:
        raise ValueError(label + ": actual prepared selectors differ or are unsupported")
    hits = _count(actual.get("hits"), label + ".preparedContent.hits")
    if actual.get("active") is not (hits > 0):
        raise ValueError(label + ": prepared active flag disagrees with actual hits")
    consumed = actual.get("consumed_entries")
    if not isinstance(consumed, list) or not isinstance(actual.get("misses"), dict):
        raise ValueError(label + ": prepared consumed/miss inventory is missing")
    for reason, count in actual["misses"].items():
        if not isinstance(reason, str) or not reason:
            raise ValueError(label + ": prepared miss reason is invalid")
        _count(count, label + ".preparedContent.misses." + reason)
    seen = set()
    counted = 0
    for row in consumed:
        if not isinstance(row, dict):
            raise ValueError(label + ": malformed prepared consumed entry")
        identity = row.get("entry_id")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError(label + ": missing/duplicate prepared entry identity")
        seen.add(identity)
        kind = row.get("kind")
        if kind not in ("world", "scene", "mesh") or not isinstance(row.get("source"), str) or not row["source"]:
            raise ValueError(label + ": prepared consumed source/kind is invalid")
        if not isinstance(row.get("texture_token"), str) or not row["texture_token"]:
            raise ValueError(label + ": prepared texture policy identity is missing")
        if row.get("node_policy") != (policy if kind == "world" else "retain"):
            raise ValueError(label + ": consumed prepared node policy differs")
        count = _count(row.get("hits"), label + ".preparedContent.consumed.hits")
        if count == 0:
            raise ValueError(label + ": zero-hit prepared consumed entry")
        counted += count
    if counted != hits:
        raise ValueError(label + ": prepared hit total differs from consumed inventory")
    if mode == "raw" and (hits != 0 or consumed):
        raise ValueError(label + ": prepared content ran while raw was requested")
    # require-pilot applies only to catalog pilot sources. A start snapshot or
    # unrelated workload can have zero hits. Arm-specific positive exact source
    # and node-reduction assertions remain mandatory for P8/P10 qualification.
