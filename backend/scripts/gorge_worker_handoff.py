"""One shared, network-free bootstrap-to-worker handoff used by tests and live runs."""
import json,os,sqlite3,subprocess,sys
from pathlib import Path
from gorge_checkpoint import canonical,digest
from gorge_stage_preflight import require_input_proof,install_prior_tiles

def prepare_worker(plan,region,proof,roots,root):
    from gorge_cache_selection import seed_selected_cog
    from gorge_stage_inputs import private_write
    from benchmark_ky_naip_usgs import ServiceCache
    root=Path(root)
    verified=require_input_proof({**plan,'inputProofSHA256':digest(canonical(proof))},proof,roots)
    seed_selected_cog(proof['cogSelection'],roots['cog'],root/'working-cog',region['sourceLimits']['cogBytes'])
    service=root/'working-service';service.mkdir(mode=0o700)
    for p in Path(roots['service']).iterdir():private_write(service/p.name,p.read_bytes())
    svc=ServiceCache(service,byte_limit=region['sourceLimits']['serviceBytes'],request_limit=region['sourceLimits']['serviceRequests']);svc.close()
    output=root/'worker';output.mkdir(mode=0o700);install_prior_tiles(verified,output)
    check={'plan':region,'approvedJobs':plan['approvedJobIDs'],'root':str(root)}
    ticket=root/'HANDOFF-CHECK.json';private_write(ticket,canonical(check))
    # Native imports, exact recipe pins, both fresh ledgers, source identities,
    # service cache pairs and all overview children are checked in a real child.
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(ticket)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,
        env={**os.environ,'GDAL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
    if result.returncode:raise ValueError('Complete native worker handoff failed')
    audit=json.loads(result.stdout)
    if audit!={'jobs':12,'networkOperations':0,'workerHandoffValidated':True}:raise ValueError('Invalid handoff audit')
    return audit

def check_child(ticket):
    import socket
    def blocked(*args,**kwargs):raise RuntimeError('Network prohibited during worker handoff')
    socket.socket.connect=blocked;socket.create_connection=blocked
    import orchestrate_gorge_region as engine
    from cached_cog_source import Cache
    from benchmark_ky_naip_usgs import ServiceCache,NAIP
    from PIL import Image
    p=json.loads(Path(ticket).read_bytes());plan=p['plan'];root=Path(p['root'])
    for name,sha in plan['engineHashes'].items():
        if Path(name).name!=name or digest((Path(__file__).parent/name).read_bytes())!=sha:raise ValueError('Engine pin changed')
    jobs={j['id']:j for j in plan['jobs']};source_ids={s['id']:s for values in plan['inventory']['sources'].values() for s in values}
    cache=Cache(root/'working-cog',limit=plan['sourceLimits']['cogBytes'],maximum_limit=1_000_000_000_000)
    try:
        if cache.db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise ValueError('COG ledger')
        for key in p['approvedJobs']:
            job=jobs[key]
            for sid in job['sourceIDs']:
                if job['layer']=='leaf-on':continue
                source=source_ids[sid]
                if not cache.db.execute('SELECT 1 FROM sources WHERE url=?',(source['url'],)).fetchone():raise ValueError('Unseeded required COG source')
            if job['operation']=='overview':
                for dx in range(2):
                    for dy in range(2):
                        x,y=2*job['x']+dx,2*job['y']+dy
                        if (x,y) not in set(engine.tile_coords(job['z']+1)):continue
                        files=list((root/f"worker/tiles/{job['layer']}/{job['z']+1}/{x}").glob(str(y)+'.*'))
                        if len(files)!=1:raise ValueError('Missing overview dependency')
                        with Image.open(files[0]) as im:im.load();assert im.size==(256,256)
    finally:cache.close()
    service=ServiceCache(root/'working-service',byte_limit=plan['sourceLimits']['serviceBytes'],request_limit=plan['sourceLimits']['serviceRequests'])
    try:
        metadata,_=service.fetch(NAIP,{'f':'pjson'})
        if not json.loads(metadata):raise ValueError('Missing NAIP metadata')
    finally:service.close()
    print(json.dumps({'jobs':len(p['approvedJobs']),'networkOperations':0,'workerHandoffValidated':True}))

if __name__=='__main__':check_child(sys.argv[1])
