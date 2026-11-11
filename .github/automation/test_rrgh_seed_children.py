"""Real historical receipt topology with synthetic job pixels; no acceptance."""
import base64,copy,json,zlib,unittest
from pathlib import Path
import rrgh_seed_children as seed

def fixture():
    objects=json.loads(zlib.decompress(base64.b64decode((Path(__file__).with_name('fixtures')/'seed-history-inspection.json.z.b64').read_bytes())))
    bykey={o['key']:o['record'] for o in objects};h=seed.AUTHORITY['history']
    initial,proof,worker,recovered=[copy.deepcopy(bykey[h[k]['key']]) for k in ('acceptedBootstrap','proof','secondWorker','secondRecovery')]
    proof['files']=proof.pop('priorFiles')
    first=copy.deepcopy(bykey[seed.HISTORICAL['finalRecovery']['key']]);qa=copy.deepcopy(bykey[seed.HISTORICAL['finalQA']['key']])
    def receipt(jid,size=100):
        layer,z,x,y=jid.rsplit('-',3);z,x,y=map(int,(z,x,y));maxz=17 if layer in ('hiking','terrain') else 16 if layer=='usgs-topo' else 18
        outputs=[]
        for zz in range(z,maxz+1) if z==16 else [z]:
            scale=2**(zz-z)
            for dx in range(scale):
                for dy in range(scale):outputs.append(dict(path=f'tiles/{layer}/{zz}/{x*scale+dx}/{y*scale+dy}.png',bytes=size,sha256='a'*64))
        return dict(job=jid,validated=True,recipeSHA256='b'*64,outputs=outputs)
    def records(refs):
        result=[]
        for ref in refs:
            parts=ref['key'].split('/');jid=parts[-1][:-5];r=receipt(jid)
            pack=dict(key='/'.join(parts[:6])+'/outputs/'+'a'*64,bytes=100000,generation='123',sha256='a'*64)
            result.append(dict(job=jid,planSHA256=parts[3],slot=int(parts[5]),result=dict(originalReceipt=r,
                outputPacks=[dict(ref=pack,members=[dict(e,offset=i*100) for i,e in enumerate(r['outputs'])])])) )
        return result
    restored=dict(format='rrgh-preserved-r4-restoration-v1',archiveSHA256=seed.ARCHIVE_SHA,jobCount=12,rasterTiles=172,bytes=4845866,jobs=[])
    cursor=0;count=0
    for layer in ('leaf-on','leaf-off','usgs-topo'):
        for x in (17544,17545):
            for y in (25322,25323):
                r=receipt(f'{layer}-16-{x}-{y}',28173);members=[]
                for out in r['outputs']:
                    count+=1
                    if count==172:out['bytes']=4845866-cursor
                    members.append(dict(out,offset=cursor));cursor+=out['bytes']
                restored['jobs'].append(dict(job=r['job'],originalReceipt=r,members=members))
    return initial,proof,worker,recovered,records(worker['result']['completedJobReceipts']),first,qa,records(qa['completedJobReceipts']),restored

class SeedTests(unittest.TestCase):
    def test_real_historical_partition(self):
        rows=seed.validate_metadata(*fixture())
        self.assertEqual(len(rows),44);self.assertEqual(sum(len(r['outputs']) for r in rows.values()),436)
        counts={kind:sum(r['kind']==kind for r in rows.values()) for kind in {r['kind'] for r in rows.values()}}
        self.assertEqual(counts,{'original-accepted-seed':8,'restored-original-accepted-seed':12,'first-stage-accepted-seed':12,'second-stage-accepted-seed':12})
    def test_corrupt_or_missing_history_rejected(self):
        for fault in ('missing','failed','wrong_proof','changed_output','duplicate','first_failure','first_qa','wrong_first_slot','restored_hash','restored_member','restored_offset','wrong_namespace'):
            with self.subTest(fault=fault):
                a=list(fixture())
                if fault=='missing':a[4].pop()
                elif fault=='failed':a[3]['result']['status']='failed'
                elif fault=='wrong_proof':a[0]['result']['proofRef']['sha256']='e'*64
                elif fault=='changed_output':next(e for e in a[1]['files'] if e['path'].startswith('tiles/'))['sha256']='d'*64
                elif fault=='duplicate':a[1]['priorReceipts'].append(a[1]['priorReceipts'][0])
                elif fault=='first_failure':a[5]['result']['status']='failed'
                elif fault=='first_qa':a[5]['result']['qaRef']['sha256']='f'*64
                elif fault=='wrong_first_slot':a[7][-1]['slot']=1
                elif fault=='restored_hash':a[8]['archiveSHA256']='0'*64
                elif fault=='restored_member':a[8]['jobs'][0]['members'][0]['sha256']='0'*64
                elif fault=='restored_offset':a[8]['jobs'][0]['members'][0]['offset']=1
                else:a[7][0]['result']['outputPacks'][0]['ref']['key']='engineering/map-production/other'
                with self.assertRaises((ValueError,KeyError)):seed.validate_metadata(*a)

if __name__=='__main__':unittest.main()
