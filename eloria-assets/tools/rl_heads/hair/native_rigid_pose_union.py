"""Optional exact authoring queries against complete posed Native fixtures.

This does not fit or qualify an asset. Callers must prove that their queried
hair points share the one rigid carrier bone selected here.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from native_hair_fixtures import load_fixture, matrix, verified_fixture_signature


class RigidNativePoseUnion:
    def __init__(self, manifest, sex, case_names=None, quality=0,
                 carrier_bone='Head', horizontal_slice_proof=False,
                 closest_section_proof=False):
        manifest = Path(manifest)
        document = json.loads(manifest.read_text())
        assert document.get('hair_identity_policy') == 'native_fixed_skull'
        requested = None if case_names is None else set(case_names)
        assert requested is None or requested, 'An explicit pose selection cannot be empty'
        self.poses = []
        sources = []
        found = set()
        for record in document['cases']:
            if record['sex'] != sex or record['quality'] != quality:
                continue
            if requested is not None and record['case'] not in requested:
                continue
            assert not record['rl_hair_identity_controls'], 'Native hair uses zero High identity fields'
            assert carrier_bone in record['bone_deltas'], 'The evaluated carrier bone is absent'
            transform = matrix(record['bone_deltas'][carrier_bone])
            basis = transform[:3, :3]
            assert np.allclose(basis.T @ basis, np.eye(3), atol=1e-6, rtol=0), 'Carrier must be rigid'
            assert np.linalg.det(basis) > 0, 'Carrier must preserve orientation'
            signature, _ = verified_fixture_signature(manifest, record)
            options = {'horizontal_slice_proof': horizontal_slice_proof}
            if closest_section_proof:
                options['closest_section_proof'] = True
            surface = load_fixture(manifest, record, **options)
            self.poses.append((surface, transform, np.linalg.inv(basis)))
            found.add(record['case'])
            sources.append({'case': record['case'], 'quality': record['quality'],
                            'clip': record['clip'], 'fraction': record['fraction'],
                            'fixture_signature_sha256': signature,
                            'carrier_transform': transform.tolist()})
        assert self.poses, 'No matching evaluated poses'
        assert requested is None or requested <= found, 'A requested pose is absent'
        self.source = {'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
                       'sex': sex, 'quality': quality, 'carrier_bone': carrier_bone,
                       'horizontal_slice_proof': bool(horizontal_slice_proof),
                       'poses': sources, 'authoring_only': True, 'qualified': False}
        if closest_section_proof:
            self.source['closest_section_proof'] = True
            self.source['closest_section_tool_sha256'] = hashlib.sha256(
                Path(__file__).with_name('closest_section_outside.py').read_bytes()).hexdigest()

    def signed(self, points):
        points = np.asarray(points, dtype=np.float64)
        assert points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all()
        if not len(points):
            return np.empty(0), np.empty((0, 3)), np.empty((0, 3))
        distance = np.full(len(points), np.inf)
        closest = np.empty_like(points)
        normal = np.empty_like(points)
        for surface, transform, inverse in self.poses:
            basis = transform[:3, :3]
            world = points @ basis.T + transform[:3, 3]
            # Retain the complete fixture's original axes and outside proof.
            # Rotating its triangles would change which contours are queried.
            d, cp, n = surface.signed(world)
            take = d < distance
            distance[take] = d[take]
            closest[take] = (cp[take] - transform[:3, 3]) @ inverse.T
            bind_normal = n[take] @ basis
            bind_normal /= np.linalg.norm(bind_normal, axis=1, keepdims=True)
            normal[take] = bind_normal
        return distance, closest, normal
