"""Offline revalidation of the original wave574 -> published575 transaction."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import rrgh_dispatcher as d

root=Path(sys.argv[1]).resolve();published=Path(sys.argv[2]).resolve()
fixture=json.loads(Path(sys.argv[3]).read_bytes());state=fixture['state'];audit=fixture['audit']
def git(folder,*args):return subprocess.check_output(['git','-C',str(folder),*args],text=True).strip()
assert git(root,'rev-parse','HEAD')==state['sourceSHA']
assert git(published,'rev-parse','HEAD')==fixture['publishedSourceSHA']
assert git(published,'show','-s','--format=%P','HEAD').split()==[state['sourceSHA']]
changed=git(published,'diff','--name-only','HEAD^','HEAD').splitlines()
saved={}
try:
    for name in changed:
        assert not name.startswith('/') and '..' not in name.split('/')
        target=root/name;saved[name]=target.read_bytes() if target.exists() else None
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(published/name,target)
    parent,plan_hash,plan,entries=d.candidate_entries(root,audit,state)
    assert parent==state['sourceSHA'] and plan_hash==fixture['publishedPlanSHA256']
    assert set(changed)=={e['path'] for e in entries}
    assert all((published/e['path']).read_text()==e['content'] for e in entries)
    assert plan['campaign']['carry']['priorRasterTiles']==178946
    sys.path.insert(0,str(root/'backend/scripts'))
    from gorge_campaign import configuration
    configuration()
    print(json.dumps({'test':'ACTUAL_PUBLISHED_SOURCE_574_TO_575','publishedSourceValidated':True,
        'sourceSHA':fixture['publishedSourceSHA'],'planSHA256':plan_hash,
        'acceptedRasterTiles':178946,'changedFiles':changed,'cloudWrites':0}))
finally:
    for name,raw in saved.items():
        if raw is None:(root/name).unlink()
        else:(root/name).write_bytes(raw)
