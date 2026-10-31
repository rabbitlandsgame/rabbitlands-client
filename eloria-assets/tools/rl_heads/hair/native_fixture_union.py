"""Conservative union of complete, hash-verified evaluated Native Rest surfaces.

This is authoring support, not the independent control/pose qualification gate.
It intentionally has no mesh/radial API: nearest distances are evaluated on each
complete fixture so detached patches cannot invent inside/outside signs.
"""
from pathlib import Path
import json
import numpy as np
from native_hair_fixtures import load_fixture


class NativeFixtureUnion:
    def __init__(self,manifest,sex,case_names=None):
        data=json.loads(Path(manifest).read_text())
        assert data.get('hair_identity_policy')=='native_fixed_skull','Use evaluated fixturev2 or later with zero High hair IDs'
        seen=set();self.surfaces=[];self.records=[]
        for record in data['cases']:
            if record['sex']!=sex or record['clip']!='Rest_Pose' or record['fraction']!=0:continue
            if case_names is not None and record['case'] not in case_names:continue
            assert not record['rl_hair_identity_controls'],'Native skull fitting must use zero High identity targets'
            signature=tuple(sorted((part['mesh'],part['sha256']) for part in record['parts'] if part['mesh'] in ['body','scalp','wardrobe_shirt']))
            if signature in seen:continue
            seen.add(signature);self.surfaces.append(load_fixture(manifest,record))
            self.records.append({'case':record['case'],'quality':record['quality']})
        assert self.surfaces,'No matching evaluated Native Rest surfaces'
    def signed(self,P):
        result=self.surfaces[0].signed(P)
        distance,point,normal=(np.array(array,copy=True) for array in result)
        for surface in self.surfaces[1:]:
            d,q,n=surface.signed(P);take=d<distance
            distance[take]=d[take];point[take]=q[take];normal[take]=n[take]
        return distance,point,normal
