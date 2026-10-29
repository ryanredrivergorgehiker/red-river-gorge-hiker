#!/usr/bin/env python3
"""Verify saved R4 completion evidence without extracting caches or rendering."""
import json
from pathlib import Path
import zipfile
from gorge_checkpoint import digest, relative_path


def import_saved_evidence(archive, expected_sha256):
    path=Path(archive)
    if digest(path.read_bytes())!=expected_sha256:raise ValueError('Saved evidence archive hash mismatch')
    with zipfile.ZipFile(path) as z:
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('Duplicate archive member')
        prefix='region-adjacent/'
        plan_raw=z.read(prefix+'PLAN.json');plan=json.loads(plan_raw)
        recipe=digest((json.dumps(plan,indent=2,sort_keys=True)+'\n').encode())
        records=[];seen=set();total=0;files=0
        jobs={j['id']:j for j in plan['jobs']}
        for name in sorted(n for n in z.namelist() if n.startswith(prefix+'receipts/') and n.endswith('.json')):
            raw=z.read(name);r=json.loads(raw)
            if r['job'] in seen or r['job'] not in jobs or r['validated'] is not True or r['recipeSHA256']!=recipe:
                raise ValueError('Invalid preserved receipt/recipe')
            seen.add(r['job'])
            for e in r['outputs']:
                member=prefix+relative_path(e['path']);body=z.read(member)
                if len(body)!=e['bytes'] or digest(body)!=e['sha256']:raise ValueError('Preserved output mismatch')
                files+=1;total+=len(body)
            records.append({'job':r['job'],'receiptSHA256':digest(raw),'recipeSHA256':recipe,
                            'jobDefinition':jobs[r['job']],'outputs':r['outputs']})
        if seen!=set(jobs):raise ValueError('Completed R4 plan missing a receipt')
        ledgers={n:digest(z.read(n)) for n in z.namelist() if n.endswith('.sqlite')}
        return {'format':'rrgh-prior-work-import-v1','archiveSHA256':expected_sha256,
                'priorPlanSHA256':digest(plan_raw),'priorLimits':plan['limits'],
                'priorSourceLimits':plan['sourceLimits'],'ledgerHashes':ledgers,
                'completedJobs':records,'filesVerified':files,'bytesVerified':total,
                'sourceTransfers':0,'rasterJobsExecuted':0,'oldLedgersModified':False}
