"""Coherent tail intent, distributed on each actor's native joint chain."""
import numpy as np

TAIL_ROLES = ('tail_lower', 'tail_end', 'tail_tip')


def apply_tail_intent(package, rig, parameters):
    intent = package.get('secondary_motion', {}).get('coherent_tail_intent')
    if intent is None:
        return np.asarray(parameters).copy()
    adapter = rig.profile.get('secondary_motion_adaptation', {})
    weights = np.asarray(adapter.get('tail_bend_weights', intent['bend_weights']), float)
    scale = float(adapter.get('tail_amplitude_scale', 1))
    bend = np.asarray(intent['bend_radians'], float)
    result = np.asarray(parameters).copy()
    if weights.shape != (3,) or np.any(weights < 0) or not np.isclose(weights.sum(), 1) or not 0 <= scale <= 1:
        raise ValueError('Tail adaptation requires three nonnegative weights summing to one and scale in [0,1]')
    if len(bend) != len(result) or not np.isfinite(bend).all():
        raise ValueError('Tail intent must match the motion samples')
    if adapter.get('tail_center_bend_on_native_rest', False):
        bend = bend - bend[:-1].mean()
    mapping = {c['role']: i for i, c in enumerate(rig.controls)}
    parent = rig.roles.get('tail')
    if parent is None:
        raise ValueError('Map the native tail chain before transferring tail motion')
    present=[r for r in TAIL_ROLES if r in mapping and r in rig.roles]
    if not present:raise ValueError('Map at least one native distal tail control')
    native_weights={r:0. for r in present}
    for role,weight in zip(TAIL_ROLES,weights):
        native_weights[role if role in present else present[-1]]+=float(weight)
    for role, weight in native_weights.items():
        node = rig.roles[role]
        ancestor = int(rig.asset.parent[node])
        while ancestor >= 0 and ancestor != parent:
            ancestor = int(rig.asset.parent[ancestor])
        if ancestor != parent:
            raise ValueError('Tail roles must follow the native serial chain')
        column = mapping[role]
        result[:, column] = bend * scale * weight
        if np.any(result[:, column] < rig.lower[column]) or np.any(result[:, column] > rig.upper[column]):
            raise ValueError('Coherent tail adaptation exceeds the native control bounds')
        parent = node
    return result
