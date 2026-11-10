"""Synthetic metadata fixtures; these tests cannot accept production output."""
import copy,unittest
import rrgh_seed_children as seed

def fixture():
    h=copy.deepcopy(seed.AUTHORITY['history']);first=h['acceptedBootstrap']['key'].split('/')[3]
    second=h['secondRecovery']['key'].split('/')[3];base={'immutableFixture':True}
    initial=dict(planSHA256=first,slot=0,result=dict(inputProofValidated=True,proofRef=h['proof'],acceptedBase=base))
    proof=dict(format='rrgh-stage-input-proof-v1',acceptedBase=base,priorReceipts=[],files=[],checkpointRefs=[h['proof']])
    refs=[];records=[]
    for jid in seed.AUTHORITY['jobs']:
        layer,z,x,y=jid.rsplit('-',3);z,x,y=map(int,(z,x,y));maxz=17 if layer in ('hiking','terrain') else 16 if layer=='usgs-topo' else 18
        outputs=[]
        for zz in range(z,maxz+1) if z==16 else [z]:
            scale=2**(zz-z)
            for dx in range(scale):
                for dy in range(scale):outputs.append(dict(path=f'tiles/{layer}/{zz}/{x*scale+dx}/{y*scale+dy}.png',bytes=100,sha256='a'*64))
        receipt=dict(job=jid,validated=True,recipeSHA256='b'*64,outputs=outputs)
        if x!=17546:
            proof['priorReceipts'].append(receipt)
            proof['files'].extend(dict(e,kind='prior',checkpointIndex=0,offset=i*100) for i,e in enumerate(outputs))
        else:
            ref=dict(key='engineering/map-production/plans/'+second+'/slots/00001/jobs/'+jid+'.json',bytes=1000,generation='123',sha256='c'*64)
            refs.append(ref);records.append(dict(planSHA256=second,slot=1,job=jid,result=dict(originalReceipt=receipt,
                outputPacks=[dict(ref=h['proof'],members=[dict(e,offset=i*100) for i,e in enumerate(outputs)])])))
    worker=dict(planSHA256=second,slot=1,result=dict(status='complete',completedJobReceipts=refs))
    recovered=dict(planSHA256=second,slot=2,result=dict(status='verified',workerReceipt=h['secondWorker'],
        historicalProofReused=h['proof'],completedJobReceipts=refs,
        production=dict(jobs=12,files=116,priorJobsPreserved=32,priorRasterTilesPreserved=320)))
    return initial,proof,worker,recovered,records

class SeedTests(unittest.TestCase):
    def test_exact_original_and_second_stage_union(self):
        rows=seed.validate_metadata(*fixture())
        self.assertEqual(set(rows),set(seed.AUTHORITY['jobs']))
        self.assertEqual(sum(r['kind']=='original-accepted-seed' for r in rows.values()),32)
        self.assertEqual(sum(r['kind']=='second-stage-accepted-seed' for r in rows.values()),12)
        self.assertEqual(sum(len(r['outputs']) for r in rows.values()),436)

    def test_missing_record_or_false_independent_success_is_rejected(self):
        for fault in ('missing','failed','wrong_proof','extra_job','changed_output','duplicate'):
            with self.subTest(fault=fault):
                initial,proof,worker,recovered,records=fixture()
                if fault=='missing':records.pop()
                elif fault=='failed':recovered['result']['status']='failed'
                elif fault=='wrong_proof':initial['result']['proofRef']['sha256']='e'*64
                elif fault=='extra_job':records[-1]['job']='unaccepted-16-17546-25323'
                elif fault=='changed_output':proof['files'][0]['sha256']='d'*64
                else:proof['files'].append(copy.deepcopy(proof['files'][0]))
                with self.assertRaises(ValueError):seed.validate_metadata(initial,proof,worker,recovered,records)

if __name__=='__main__':unittest.main()
