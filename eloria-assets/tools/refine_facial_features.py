"""Refine the lower faces of the six humanoid races on fitted shared bodies.

The compact deformation field is evaluated identically across material/UV
seams. It leaves lips, eyes, scalp, rig, weights and clothing untouched. Run on
the fitted bodies once, before baking face masks and neck texture manifests.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from shared_player_bodies import append_array
from build_face_masks import g

# Chin centre, forward projection, jaw breadth, under-chin recess (metres).
# Broad male jaws and softer female chins retain the original race proportions.
PROFILES = {
    'glasswarden_female': (1.539, .004, .002, .017),
    'glasswarden_male': (1.534, .006, .004, .021),
    'greyhaven_female': (1.525, .009, .003, .025),
    'greyhaven_male': (1.535, .012, .006, .026),
    'luminous_female': (1.538, .0048, .003, .014),
    'luminous_male': (1.538, .014, .006, .029),
    'mycelari_female': (1.537, .008, .003, .023),
    'mycelari_male': (1.543, .008, .004, .024),
    'orun_female': (1.542, .0068, .003, .0195),
    'orun_male': (1.536, .012, .007, .026),
    'votary_female': (1.523, .009, .003, .023),
    'votary_male': (1.525, .012, .005, .025),
}


def smooth(a, b, values):
    t = np.clip((values-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def mound(values, centre, radius):
    """Compact, differentiable falloff with an exactly unchanged exterior."""
    return np.maximum(1-((values-centre)/radius)**2, 0)**3


def reshape(v, profile):
    chin, projection, breadth, recess = profile
    x, y, z = v.T
    front = smooth(.005, .075, z)
    centre = mound(x, 0, .052)
    chin_pad = mound(y, chin, .023)*centre*front
    jaw = mound(y, chin+.004+np.abs(x)*.20, .027)
    jaw *= mound(np.abs(x), .048, .036)*smooth(-.015, .055, z)
    throat = mound(y, chin-.038, .033)*smooth(.005, .075, z)
    result = v.copy()
    result[:, 2] += projection*chin_pad - recess*throat
    result[:, 0] += np.sign(x)*breadth*jaw
    # Taper below the jaw without changing the back of the neck or collar.
    result[:, 0] -= x*.12*throat
    return result


def refine(source, target, profile):
    d, b = g.read(source)
    if d.get('extras', {}).get('facialFeaturesVersion'):
        raise ValueError(f'{source}: facial refinement already applied')
    binary = bytearray(b)
    changed, maximum = 0, 0.
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            if p.get('extras', {}).get('sourceRole') not in ('race_head', 'neck_join'):
                continue
            a = p['attributes']
            v = g.accessor(d, b, a['POSITION'])
            moved = reshape(v, profile)
            delta = np.linalg.norm(moved-v, axis=1)
            if delta.max() < 1e-10:
                continue
            faces = g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3)
            old_cross = np.cross(v[faces[:, 1]]-v[faces[:, 0]], v[faces[:, 2]]-v[faces[:, 0]])
            new_cross = np.cross(moved[faces[:, 1]]-moved[faces[:, 0]], moved[faces[:, 2]]-moved[faces[:, 0]])
            if (np.einsum('ij,ij->i', old_cross, new_cross) < -1e-16).any():
                raise ValueError(f'{source}: source triangle turned over')
            changed += int((delta > 1e-8).sum())
            maximum = max(maximum, float(delta.max()))
            # Inverse-transpose normals preserve authored shading under the
            # deformation; tangents use the forward Jacobian and keep parity.
            epsilon = 1e-5
            jac = np.stack([(reshape(v+np.eye(3)[i]*epsilon, profile)-
                             reshape(v-np.eye(3)[i]*epsilon, profile))/(2*epsilon)
                            for i in range(3)], axis=-1)
            if np.linalg.det(jac).min() <= 0:
                raise ValueError(f'{source}: folded deformation')
            normal = g.accessor(d, b, a['NORMAL'])
            normal = np.linalg.solve(jac.transpose(0, 2, 1), normal[..., None])[..., 0]
            normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
            a['POSITION'] = append_array(d, binary, moved, 'VEC3')
            a['NORMAL'] = append_array(d, binary, normal, 'VEC3')
            if 'TANGENT' in a:
                tangent = g.accessor(d, b, a['TANGENT'])
                t = np.einsum('nij,nj->ni', jac, tangent[:, :3])
                t -= normal*np.einsum('ij,ij->i', t, normal)[:, None]
                tangent[:, :3] = t/np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
                a['TANGENT'] = append_array(d, binary, tangent, 'VEC4')
    d.setdefault('extras', {})['facialFeaturesVersion'] = 1
    d, binary = g.compact(d, bytes(binary))
    g.write(target, d, binary)
    return {'sourceSHA256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'modelSHA256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'changedVertices': changed, 'maximumDisplacementMetres': maximum,
            'profile': list(profile)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reports = {}
    for slug, profile in PROFILES.items():
        reports[slug] = refine(args.models/(slug+'.glb'), args.out/(slug+'.glb'), profile)
        print(slug, reports[slug]['changedVertices'])
    (args.out/'facial-features-manifest.json').write_text(json.dumps(reports, indent=2)+'\n')


if __name__ == '__main__':
    main()
