"""Failure, ledger and ownership regressions for finite larger USGS batches."""
import copy
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

import rrgh_completion_phase as c
import rrgh_checkpoint_recovery as recovery
import rrgh_checkpoint_salvage as salvage
import rrgh_dispatcher as d
from test_rrgh_checkpoint_recovery import fixture,original_fixture,inspection
from test_rrgh_dispatcher import DispatcherTests,FakeGitHub,ROOT


def selected():
    r=dict(boundsWGS84=c.BOUNDS,profiles={'core':{'usgs-topo':16}})
    pilot=c.select(r,[],{},c.POLICY_V1);accepted=[j['id'] for j in pilot]
    r['jobs']=c.select(r,accepted,dict.fromkeys(accepted,1),c.POLICY)
    return r


class LargerCheckpointTests(unittest.TestCase):
    def test_sixty_three_saved_checkpoints_can_be_inspected_without_replay(self):
        f=fixture();p=f['plan'];r=selected();ids=[j['id'] for j in r['jobs']]
        p.update(approvedJobIDs=ids,completionPhase=c.PHASE,
            jobPolicies={j:c.job_policy(c.POLICY) for j in ids})
        f['state']['completionPolicy']=c.POLICY
        template=next(row for row in f['producerRows'] if 'durableJobReceipt' in row)
        rows=[row for row in f['producerRows'] if 'durableJobReceipt' not in row]
        for i,jid in enumerate(ids[:-1]):
            row=copy.deepcopy(template);old=row['job'];row.update(job=jid,jobTiles=1,completedJobs=i+1)
            row['durableJobReceipt']['key']=row['durableJobReceipt']['key'].replace(old+'.json',jid+'.json')
            rows.insert(-1,row)
        f['producerRows']=rows
        (m,p),_=original_fixture(f)
        self.assertEqual((m['jobs'],m['tiles'],m['uncertainJobIDs']),(63,63,ids[-1:]))
        evidence=inspection(m,p);evidence['readRequests']=140
        actual=recovery.inspect_manifest(m,p,evidence)
        self.assertEqual(actual['inspectionUsage']['classBRequests'],140)
        evidence['readRequests']=141
        with self.assertRaises(d.Halt):recovery.inspect_manifest(m,p,evidence)
        p['approvedJobIDs'].append('usgs-topo-9-1-1')
        with self.assertRaises(d.Halt):original_fixture(f)


class ServiceLedgerTests(unittest.TestCase):
    def setup_case(self,path):
        r=selected();r['jobs']=r['jobs'][:3];ids=[j['id'] for j in r['jobs']]
        p=dict(completionPhase=c.PHASE,approvedJobIDs=ids,
            jobPolicies={j:c.job_policy(c.POLICY) for j in ids})
        cog=path/'cog.sqlite';service=path/'service.sqlite'
        with sqlite3.connect(cog) as db:
            db.execute('CREATE TABLE sources(url TEXT PRIMARY KEY,identity TEXT,metadata TEXT)')
            db.execute("INSERT INTO sources VALUES ('prior','identity','metadata')")
        with sqlite3.connect(service) as db:
            db.executescript('CREATE TABLE budget(bytes INTEGER,requests INTEGER);'
                'CREATE TABLE calls(id INTEGER PRIMARY KEY,key TEXT,reserved INTEGER,received INTEGER,status TEXT,seconds REAL);'
                "INSERT INTO budget VALUES (100000000,10000);INSERT INTO calls VALUES (1,'prior',500,500,'complete',1.5);")
        records=[]
        for j in r['jobs'][:2]:
            url=f"https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{j['z']}/{j['y']}/{j['x']}"
            pin=dict(url=url,parameters={},bytes=100,sha256='a'*64)
            out=dict(path=f"tiles/usgs-topo/{j['z']}/{j['x']}/{j['y']}.png",bytes=100,sha256='a'*64)
            receipt=dict(sourceEvidence=[pin],outputs=[out],execution=dict(sourceUsage=dict(
                actual=dict(operations=1,receivedBodyBytes=100),reserved=dict(sourceRequests=1,sourceBytes=500001))))
            records.append(dict(job=j['id'],result=dict(originalReceipt=receipt)))
        return cog,service,records,r,p,ids[2:]

    def test_preserves_old_ledgers_and_retains_uncertain_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.setup_case(Path(tmp));before=args[0].read_bytes()
            result=salvage.recover_usgs_ledger(*args)
            self.assertEqual(args[0].read_bytes(),before)
            self.assertEqual(result['recoveredServiceRequests'],2)
            self.assertEqual(result['uncertainServiceRequestsRetained'],1)
            with sqlite3.connect(args[1]) as db:
                self.assertEqual(db.execute('SELECT SUM(reserved),SUM(received) FROM calls').fetchone(),(500+200+1048576,700))
                self.assertEqual(db.execute('SELECT * FROM calls WHERE id=1').fetchone(),(1,'prior',500,500,'complete',1.5))
            with self.assertRaises(ValueError):salvage.recover_usgs_ledger(*args)

    def test_changed_response_scope_or_usage_rolls_back_ledger_transaction(self):
        for fault in ('url','hash','count','bytes','replay'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                args=self.setup_case(Path(tmp));receipt=args[2][-1]['result']['originalReceipt']
                if fault=='url':receipt['sourceEvidence'][0]['url']='https://example.invalid'
                elif fault=='hash':receipt['sourceEvidence'][0]['sha256']='b'*64
                elif fault=='count':receipt['execution']['sourceUsage']['actual']['operations']=2
                elif fault=='bytes':receipt['execution']['sourceUsage']['actual']['receivedBodyBytes']=99
                else:args[5].append(args[2][0]['job'])
                with self.assertRaises(ValueError):salvage.recover_usgs_ledger(*args)
                with sqlite3.connect(args[1]) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM calls').fetchone()[0],1)


class UpgradeTests(unittest.TestCase):
    def prepared(self):
        helper=DispatcherTests();api=helper.launch();inputs=helper.inputs(api)
        api.value.update(controlDigest='a'*64,completionPolicy=c.POLICY_V1,
            lastRecovered=dict(acceptedRasterTiles=265738),checkpoint=dict(immutable='preserved'),
            pendingControllerUpgrade=dict(fromDigest='a'*64,toDigest=d.local_digest(ROOT),
                authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-09',preserveAcceptedHistory=True,
                completionPolicy=c.POLICY))
        return api,inputs

    def test_policy_upgrade_is_atomic_with_new_worker_claim(self):
        api,inputs=self.prepared();before=copy.deepcopy(api.value)
        d.claim(api,ROOT,inputs,123)
        self.assertEqual(api.value['completionPolicy'],c.POLICY)
        self.assertNotIn('pendingControllerUpgrade',api.value)
        for key in ('lastRecovered','checkpoint','sourceSHA','planSHA256','sequence','dispatchID'):
            self.assertEqual(api.value[key],before[key])
        with self.assertRaises(d.Halt):d.claim(api,ROOT,inputs,124)

    def test_unreviewed_policy_or_digest_cannot_mutate_state(self):
        for field in ('policy','digest'):
            api,inputs=self.prepared()
            if field=='policy':api.value['pendingControllerUpgrade']['completionPolicy']={**c.POLICY,'maxJobs':65}
            else:api.value['pendingControllerUpgrade']['toDigest']='b'*64
            before=copy.deepcopy(api.value)
            with self.assertRaises((d.Halt,ValueError)):d.claim(api,ROOT,inputs,123)
            self.assertEqual(api.value,before)


if __name__=='__main__':unittest.main()
