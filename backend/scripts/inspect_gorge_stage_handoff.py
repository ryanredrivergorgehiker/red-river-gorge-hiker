#!/usr/bin/env python3
"""Offline private seed inspection. No credential lookup or execution mode."""
import argparse
import json
from pathlib import Path

from gorge_checkpoint import (canonical, digest, decode_record,
 MAX_CATALOG, MAX_DECODED_CATALOG, MAX_METADATA, MAX_PACK, relative_path)
from gorge_stage_preflight import require_stage_release
from run_gorge_checkpoint_slot import code_snapshot


def inspect_handoff(plan,evidence,directory):
    require_stage_release(plan,evidence)
    directory=Path(directory).resolve()
    raw=(directory/'HANDOFF.json').read_bytes()
    if digest(raw)!=plan.get('handoffSHA256'):raise ValueError('Unapproved handoff manifest')
    if code_snapshot(Path(__file__).parent)!=plan['sourceSnapshotSHA256']:
        raise ValueError('Executable source snapshot changed')
    manifest=json.loads(raw);packs=[];seen=set()
    if manifest.get('format')!='rrgh-private-stage-handoff-v1':raise ValueError('Unknown handoff')
    if plan.get('bootstrapSlot')!=0 or plan.get('slotJobs',{}).get('0'):
        raise ValueError('Dedicated zero-attempt import slot required')
    slot=plan['slots'][0]
    if slot['attempts'] or slot['sourceBytes'] or slot['sourceRequests']:
        raise ValueError('Import cannot allocate processing')
    stored=4096+16384;operations=2
    for e in manifest['packs']:
        name=relative_path(e['file']);catname=relative_path(e['catalog'])
        if name in seen or catname in seen:raise ValueError('Duplicate handoff file')
        seen.update([name,catname]);p=directory/name;c=directory/catname
        if p.is_symlink() or c.is_symlink() or directory not in p.resolve().parents or directory not in c.resolve().parents:
            raise ValueError('Unsafe handoff file')
        data=p.read_bytes();encoded=c.read_bytes()
        if not 0<len(data)<=MAX_PACK or len(data)!=e['bytes'] or digest(data)!=e['sha256']:
            raise ValueError('Handoff payload changed')
        if len(encoded)>MAX_CATALOG or len(encoded)!=e['catalogBytes'] or digest(encoded)!=e['catalogSHA256']:
            raise ValueError('Handoff catalog changed')
        catalog=decode_record(encoded,MAX_DECODED_CATALOG)
        if catalog['sha256']!=e['sha256'] or catalog['bytes']!=e['bytes']:raise ValueError('Catalog payload mismatch')
        end=0;members=set()
        for m in catalog['members']:
            relative_path(m['path'])
            if m['path'] in members or m['offset']!=end or m['bytes']<=0:raise ValueError('Invalid packed member layout')
            members.add(m['path']);end+=m['bytes']
            if digest(data[m['offset']:end])!=m['sha256']:raise ValueError('Packed member hash mismatch')
        if end!=len(data):raise ValueError('Uncatalogued payload')
        # Final remote catalog includes its exact generation reference; reserve
        # the complete catalog ceiling rather than assuming compressed size.
        stored+=len(data)+MAX_CATALOG;operations+=2
        packs.append((p,catalog))
    if stored>slot['storedBytes'] or operations>slot['classARequests'] or operations*(MAX_METADATA+1)>slot['egressBytes']:
        raise ValueError('Import exceeds its prepaid slot')
    return packs,{'payloadBytes':sum(p.stat().st_size for p,_ in packs),
      'maximumStoredBytes':stored,'maximumClassA':operations,'maximumClassB':0,
      'maximumResponseBytes':operations*(MAX_METADATA+1),'planSHA256':digest(canonical(plan)),
      'handoffSHA256':digest(raw),'executeRequested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['plan','evidence','handoff']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();plan=json.loads(args.plan.read_bytes());evidence=json.loads(args.evidence.read_bytes())
    packs,result=inspect_handoff(plan,evidence,args.handoff)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
