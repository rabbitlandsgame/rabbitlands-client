"""Strict same-process route-soak clocks/leg completion. No package reads."""
from __future__ import annotations
import math
import re

def soak_ids(selector):
    match=re.fullmatch(r'route-soak-([0-9]+)',selector)
    if not match or not 2<=int(match[1])<=32 or str(int(match[1]))!=match[1]:
        raise ValueError('route soak requires route-soak-N with 2 <= N <= 32')
    return ['traversal-southern-soak-'+chr(97+i//26)+chr(97+i%26)
            for i in range(int(match[1]))]

def _clock(value,label):
    if not isinstance(value,dict):raise ValueError(label+': clock missing')
    for key in ('ticksUsec','unixTime'):
        x=value.get(key)
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0:
            raise ValueError(label+': invalid '+key)
    if not isinstance(value['ticksUsec'],int):raise ValueError(label+': monotonic microseconds must be integer')
    return value

def validate_soak(report,selector):
    if not selector.startswith('route-soak-'):return None
    ids=soak_ids(selector)
    cells=report.get('cells')
    if not isinstance(cells,list) or any(not isinstance(c,dict) for c in cells) or [c.get('id') for c in cells]!=ids:
        raise ValueError('route soak missing, duplicate or reordered iterations')
    process=None;main=None;previous_end=None;previous_wall=None;first=None;last=None;transitions=0
    for index,cell in enumerate(cells):
        route=cell.get('route',{})
        if not isinstance(route,dict):raise ValueError('route soak route object missing')
        witness=route.get('iterationClock',{})
        if not isinstance(witness,dict):raise ValueError('route soak iteration clock object missing')
        if witness.get('index')!=index or witness.get('plannedIterations')!=len(ids):
            raise ValueError('route soak iteration index/count differs')
        pid=witness.get('pid');owner=witness.get('mainInstanceId')
        if type(pid) is not int or pid<=0 or type(owner) is not int or owner<=0:
            raise ValueError('route soak ownership witness missing')
        if process is None:process,main=pid,owner
        if (pid,owner)!=(process,main):raise ValueError('route soak restarted process or Main')
        begin=_clock(witness.get('begin'),cell['id']+'.begin')
        end=_clock(witness.get('end'),cell['id']+'.end')
        if end['ticksUsec']<=begin['ticksUsec'] or (previous_end is not None and begin['ticksUsec']<previous_end):
            raise ValueError('route soak monotonic iteration clock regressed/overlapped')
        if end['unixTime']<begin['unixTime'] or (previous_wall is not None and begin['unixTime']<previous_wall):
            raise ValueError('wall clock regressed; retain run invalid for memory alignment')
        previous_end=end['ticksUsec'];previous_wall=end['unixTime'];first=first or begin;last=end
        if witness.get('visit')!=('cold' if index==0 else 'warm'):
            raise ValueError('only the first same-process route pass is cold')
        legs=route.get('legs',[])
        expected=['first-southern-border','consecutive-southern-border','interior-entry','interior-return','teleport','return']
        if not isinstance(legs,list) or any(not isinstance(leg,dict) for leg in legs) or [leg.get('id') for leg in legs]!=expected or any(
            leg.get('success') is not True or leg.get('readiness',{}).get('ready') is not True for leg in legs):
            raise ValueError('route soak failed/missing transition or final readiness')
        if cell.get('readiness',{}).get('ready') is not True or cell.get('status')!='complete':
            raise ValueError('route soak iteration not ready/complete')
        transitions+=len(legs)
    teardown=report.get('teardown',{})
    if teardown.get('ready') is not True or teardown.get('ownedSubtreeDisabledAfterDrain') is not True \
            or teardown.get('ownedInstrumentationDisconnected') is not True \
            or any(teardown.get(k,{}).get('ready') is not True for k in ('beforeUnload','afterUnload','afterMainFree')):
        raise ValueError('route soak lacks complete owned worker/retirement/Main teardown')
    return {'kind':'same-process-synthetic-client-route-soak','pid':process,'mainInstanceId':main,
            'iterations':len(ids),'successfulTransitions':transitions,'expectedTransitions':6*len(ids),
            'firstIterationBegin':first,'lastIterationEnd':last,
            'iterationWindowSeconds':(last['ticksUsec']-first['ticksUsec'])/1e6,
            'coldPasses':1,'warmPasses':len(ids)-1,
            'scope':'includes iteration readiness; excludes initial process/map setup, final teardown and package hashes',
            'serverNavigationCertified':False,'osStorageCacheColdCertified':False}
