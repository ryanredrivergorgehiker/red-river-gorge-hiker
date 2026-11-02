"""Synthetic overview migration/provenance tests; no live acceptance."""
import copy
import os
from pathlib import Path
import sys
import unittest

import rrgh_overview_integration as i
import rrgh_overview_pilot as p

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(os.environ.get('RRGH_TEST_SOURCE','rrgh-expansion-source')).resolve()


def synthetic_proof():
    m=i.manifest();prefix='engineering/map-production/plans/'+m['sourcePlanSHA256']+'/'
    rows=[]
    for jid in m['children']:
        x,y=map(int,jid.rsplit('-',2)[1:])
        rows.append(dict(job=jid,tile=['leaf-on',16,x,y],path=f'tiles/leaf-on/16/{x}/{y}.png',
            pixelReadbackVerified=True,bytes=100,sha256='c'*64,checkpointOffset=0,
            jobReceipt=dict(key=prefix+'slots/00001/jobs/'+jid+'.json',generation='1',sha256='a'*64,bytes=1000),
            checkpointObject=dict(key=prefix+'slots/00001/outputs/'+'b'*64,generation='2',sha256='b'*64,bytes=1000)))
    return dict(job=m['job'],fourChildrenHashAndPixelVerified=True,independentParentRecomputationMatches=True,
        officialSourceRequests=0,sourceQualityUnchanged=True,
        childProof=dict(format='rrgh-overview-dependency-proof-v1',job=m['job'],children=rows,
            originalIndependentRecovery=m['recovery'],sourceRecipeSHA256=m['sourceRecipeSHA256'],
            officialSourceRequests=0,priorChildrenUnmodified=True))


class OverviewProductionTests(unittest.TestCase):
    def test_exact_campaign_integration_is_idempotent(self):
        code=(SOURCE/'backend/scripts/gorge_campaign.py').read_text()
        from rrgh_recovery_catalog_integration import augment_campaign
        baseline=augment_campaign(code);new=i.augment(code)
        self.assertEqual(i.augment(new),new);self.assertEqual(i.strip(new),baseline)
        for before,after in i.HOOKS:
            with self.assertRaises(ValueError):i.augment(new.replace(after,before,1))
        with self.assertRaises(ValueError):i.augment(new+'\n# unreviewed source change')
    def test_pilot_replaces_one_native_job_and_never_replays(self):
        picked=[dict(id=f'{layer}-{n}',layer=layer,operation='source-window') for layer in ('hiking','terrain','leaf-off') for n in range(4)]
        m=i.manifest();old=copy.deepcopy(picked)
        new,authority=i.select(picked,m['children'],{},True)
        self.assertEqual(picked,old);self.assertEqual(len(new),12);self.assertEqual(new[-1],i.pilot_job())
        self.assertEqual(authority,m)
        for accepted,attempts,enabled in [(m['children'],{},False),(m['children']+[m['job']],{},True),
                                         (m['children'],{m['job']:1},True),(m['children'][:-1],{},True)]:
            self.assertEqual(i.select(picked,accepted,attempts,enabled),(picked,None))
    def test_scope_requires_zero_source_caps_and_four_accepted_children(self):
        m=i.manifest();job=i.pilot_job()
        plan=dict(overviewPilot=m,approvedJobIDs=[m['job']],completedJobIDs=m['children'],priorAttemptCounts={},
                  jobPolicies={m['job']:dict(seconds=600,sourceBytes=0,sourceRequests=0)})
        region=dict(boundsWGS84=m['boundsWGS84'],jobs=[job])
        self.assertEqual(p.validate_scope(plan,region,job),m)
        for field in ('sourceBytes','sourceRequests'):
            bad=copy.deepcopy(plan);bad['jobPolicies'][m['job']][field]=1
            with self.assertRaises(ValueError):p.validate_scope(bad,region,job)
        bad=copy.deepcopy(plan);bad['completedJobIDs']=m['children'][:-1]
        with self.assertRaises(ValueError):p.validate_scope(bad,region,job)
    def test_recovery_requires_both_child_readback_and_independent_parent_match(self):
        proof=synthetic_proof();self.assertEqual(i.validate_verification(proof),proof)
        for field in ('fourChildrenHashAndPixelVerified','independentParentRecomputationMatches','sourceQualityUnchanged'):
            bad=copy.deepcopy(proof);bad[field]=False
            with self.assertRaises(ValueError):i.validate_verification(bad)
        for fault in ('missing','source','recipe','foreign_ref','bad_range'):
            bad=copy.deepcopy(proof);child=bad['childProof']
            if fault=='missing':child['children'].pop()
            if fault=='source':bad['officialSourceRequests']=1
            if fault=='recipe':child['sourceRecipeSHA256']='f'*64
            if fault=='foreign_ref':child['children'][0]['jobReceipt']['key']=child['children'][0]['jobReceipt']['key'].replace(i.manifest()['sourcePlanSHA256'],'f'*64)
            if fault=='bad_range':child['children'][0]['checkpointOffset']=1000
            with self.assertRaises(ValueError):i.validate_verification(bad)
    def test_parent_plan_cannot_omit_or_invent_recovery_proof(self):
        for plan,audit in [(dict(overviewPilot=i.manifest()),{}),({},dict(overviewPilotVerification=synthetic_proof()))]:
            with self.assertRaises(ValueError):i.validate_recovery(plan,audit)
        i.validate_recovery(dict(overviewPilot=i.manifest()),dict(overviewPilotVerification=synthetic_proof()))


if __name__=='__main__':unittest.main()
