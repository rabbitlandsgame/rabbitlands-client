# Blender-side port of equipment_authoring.cape_weights (z up, x across), made continuous.
#
# The original weights the two nearest chains as (near link k, near link k+1)
# and (far link k+1): a different pair of links on each chain. Where the
# nearest chain changes - halfway between two chains, x = +-0.075 - a vertex
# jumps from (c_01, c_02, r_02) to (r_01, r_02, c_02). At rest every chain has
# the same transform and nothing shows; once the cloth solver bends the chains
# the two sides of that line move apart, and on this two-sided shell the inner
# face came through the outer in slits down the upper back. Here both chains
# take the same pair of links, so the swap is invisible. And within the top
# fifth, where spine_03 still holds part of the vertex, the chains use their
# first link only - spine plus two links on each chain would be five
# influences, and glTF carries four - with the second link faded in below it
# (`along` ramps in from travel 0.20 to 0.333, where the first span ends).
import bpy, numpy as np, math


def cape_weight(obj, arm, chains=("l", "c", "r"), links=4, body_frac=0.20):
    bones = arm.data.bones
    heads = {(c, k): np.array(bones["cape_%s_%02d" % (c, k + 1)].head_local) for c in chains for k in range(links)}
    ladder = [heads[(chains[0], k)][2] for k in range(links)]
    top, bottom = max(ladder), min(ladder)
    across = np.array([heads[(c, 0)][0] for c in chains])
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    names = ["spine_03"] + ["cape_%s_%02d" % (c, k + 1) for c in chains for k in range(links)]
    groups = {n: obj.vertex_groups.new(name=n) for n in names}
    co = np.array([tuple(v.co) for v in obj.data.vertices])
    M = np.array(obj.matrix_world); A = np.array(arm.matrix_world.inverted())
    co = co @ M[:3, :3].T + M[:3, 3]; co = co @ A[:3, :3].T + A[:3, 3]
    first_span = 1.0 / (links - 1)
    for i, p in enumerate(co):
        travel = float(np.clip((top - p[2]) / (top - bottom), 0, 1))
        body = float(np.clip(1 - travel / body_frac, 0, 1))
        step = travel * (links - 1); low = int(np.clip(math.floor(step), 0, links - 2)); along = step - low
        if low == 0:
            t = float(np.clip((travel - body_frac) / (first_span - body_frac), 0, 1))
            along *= t * t * (3 - 2 * t)
        order = np.argsort(np.abs(across - p[0])); near, far = chains[order[0]], chains[order[1]]
        gap = abs(across[order[0]] - across[order[1]])
        side = float(np.clip(1 - abs(p[0] - across[order[0]]) / max(gap, 1e-6), 0, 1))
        share = 1 - body
        ent = [("spine_03", body),
               ("cape_%s_%02d" % (near, low + 1), share * side * (1 - along)),
               ("cape_%s_%02d" % (near, low + 2), share * side * along),
               ("cape_%s_%02d" % (far, low + 1), share * (1 - side) * (1 - along)),
               ("cape_%s_%02d" % (far, low + 2), share * (1 - side) * along)]
        tot = sum(w for _, w in ent) or 1
        acc = {}
        for n, w in ent:
            acc[n] = acc.get(n, 0) + w / tot
        for n, w in acc.items():
            if w > 1e-4:
                groups[n].add([i], w, 'REPLACE')
    for m in list(obj.modifiers):
        if m.type == 'ARMATURE':
            obj.modifiers.remove(m)
    mod = obj.modifiers.new("Armature", 'ARMATURE'); mod.object = arm
