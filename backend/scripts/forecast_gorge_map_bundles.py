#!/usr/bin/env python3
"""Forecast all map families from receipts; never fetch or produce regional tiles.

Synthetic byte sizes below are estimates, never source or package integrity
proofs. USD rates are explicit scenarios; account rates/usage remain external.
"""
import argparse
import json
import math
from pathlib import Path
import sqlite3
import statistics

from benchmark_gorge_pipeline import AOI, json_bytes
from build_gorge_base_native_v4 import xy
from build_gorge_map_bundles import PROFILE, partition, part_size, part_manifest
from cached_cog_source import atomic

GIB=1024**3
SHARED_ALLOWANCE=25*1024**2  # Includes accepted Sunlight, its regional extension, vectors/weather/manifests.


def forecast(original_root,service_root,source_ledger,service_cache):
    original=json.loads((Path(original_root)/'BENCHMARK.json').read_text())
    service=json.loads((Path(service_root)/'BENCHMARK.json').read_text())
    density={}
    for report in (original,service):
        for receipt in report['receipts']:
            by_zoom={}
            for entry in receipt['outputs']:
                fields=entry['path'].split('/');key=(fields[1],int(fields[2]))
                by_zoom.setdefault(key,[]).append(entry['bytes'])
            for key,values in by_zoom.items():density.setdefault(key,[]).append(statistics.mean(values))
    groups={};spread={};layer_sizes={}
    for group,levels in PROFILE.items():
        entries=[];low=0;high=0
        for layer,max_zoom in levels.items():
            count=0;content=0
            for z in range(10,max_zoom+1):
                samples=density.get((layer,z),density.get((layer,16)))
                if not samples:raise ValueError('Missing measured layer '+layer)
                size=round(statistics.mean(samples));left,bottom=xy(AOI[0],AOI[1],z);right,top=xy(AOI[2],AOI[3],z)
                cells=(right-left+1)*(bottom-top+1);count+=cells;content+=cells*size
                low+=cells*(min(samples)+767.5);high+=cells*(max(samples)+767.5)
                for x in range(left,right+1):
                    for y in range(top,bottom+1):
                        entries.append({'path':f'tiles/{layer}/{z}/{x}/{y}.jpg','sha256':'0'*64,'bytes':size,
                                        'layer':layer,'z':z,'x':x,'y':y})
            layer_sizes[layer]={'maximumZoom':max_zoom,'tiles':count,'estimatedContentBytes':content}
        if group=='core':
            entries.append({'path':'shared/forecast-allowance.bin','sha256':'0'*64,'bytes':SHARED_ALLOWANCE,'layer':'sunlight-accepted'})
            low+=SHARED_ALLOWANCE;high+=SHARED_ALLOWANCE
        parts=partition(group,entries)
        if len(parts)>64:raise ValueError('Estimated regional part count exceeds native index bound')
        archives=[part_size(group,p) for p in parts]
        extracted=sum(sum(e['bytes'] for e in p)+len(json_bytes(part_manifest(group,p))) for p in parts)
        a=sum(archives);fixed=a-sum(e['bytes']+767.5 for e in entries)
        # Exact synthetic manifest sizes/part padding; uncertainty is in regional image density.
        groups[group]={'archiveBytes':a,'extractedBytes':extracted,'installedLogicalBytes':a+extracted,
                       'sameVolumeCleanPeakLogicalBytes':a+extracted,'legacyWholeBundleCopyPeakLogicalBytes':2*a+extracted,
                       'copyFallbackSequentialPeakUpperBytes':a+extracted+max(archives),
                       'twoGenerationsRetainedBytes':2*(a+extracted),
                       'allChangedUpdatePeakWithTwoOldGenerationsBytes':3*(a+extracted),
                       'parts':len(parts),'largestPartBytes':max(archives),'tileFiles':sum(1 for e in entries if e.get('z')),
                       'sampleSpreadArchiveBytes':[round(low+fixed),round(high+fixed)],
                       'gcsOneGenerationUSDMonth':a/GIB*.02,'egressUSDPerDownload':a/GIB*.12,
                       'rangeRequests8MiB':sum(math.ceil(x/(8*1024**2)) for x in archives)}
    combined={k:sum(g[k] for g in groups.values()) for k in (
        'archiveBytes','extractedBytes','installedLogicalBytes','sameVolumeCleanPeakLogicalBytes',
        'twoGenerationsRetainedBytes','allChangedUpdatePeakWithTwoOldGenerationsBytes','parts','tileFiles','rangeRequests8MiB')}
    combined['gcsOneGenerationUSDMonth']=combined['archiveBytes']/GIB*.02
    combined['egressUSDPerDownload']=combined['archiveBytes']/GIB*.12
    combined['classBTwoOpsPerRangeUSD']=combined['rangeRequests8MiB']*2*.0004/1000
    combined['deliveryAllowanceUSD']=1.2*(combined['egressUSDPerDownload']+combined['classBTwoOpsPerRangeUSD'])
    source=json.loads(Path(source_ledger).read_text());windows=5180
    db=sqlite3.connect(service_cache);calls=db.execute('SELECT key,received,seconds,status FROM calls').fetchall();db.close()
    service_stats={'leaf-on':[],'usgs-topo':[]}
    for key,received,seconds,status in calls:
        meta=Path(service_cache).parent/(key+'.json')
        if status!='complete' or not meta.exists():continue
        m=json.loads(meta.read_text());url=m.get('url','')
        if url.endswith('/exportImage') and received>1_000_000:service_stats['leaf-on'].append((received,seconds))
        if '/USGSTopo/MapServer/tile/' in url:service_stats['usgs-topo'].append((received,seconds))
    cold_hours=sum(source[k]['networkSeconds']/n*windows/3600 for k,n in [('hiking',3),('dem',3),('leaf-off',2)])
    original_bytes=sum(source[k]['receivedRangeBytes']/n*windows for k,n in [('hiking',3),('dem',3),('leaf-off',2)])
    naip_bytes=statistics.mean(x[0] for x in service_stats['leaf-on'])*windows
    cold_hours+=statistics.mean(x[1] for x in service_stats['leaf-on'])*windows/3600
    cold_hours+=statistics.mean(x[1] for x in service_stats['usgs-topo'])*6950/3600
    old_groups={}
    for r in original['receipts']:
        role='leaf-off' if 'leaf-off' in r['job'] else 'terrain' if 'terrain' in r['job'] else 'hiking'
        old_groups.setdefault(role,[]).append(r['elapsedSeconds'])
    warm_hours=sum(statistics.mean(v)*windows/3600 for v in old_groups.values())
    warm_hours+=statistics.mean(r['elapsedSeconds'] for r in service['receipts'] if r['job'].endswith('leaf-on'))*windows/3600
    cache_bytes=original_bytes+naip_bytes+layer_sizes['usgs-topo']['estimatedContentBytes']
    compute_hours=cold_hours+warm_hours
    return {'status':'FORECAST ONLY; NO REGIONAL IMAGERY PRODUCED; NOT MEASURED ON IPHONE OR GITHUB',
            'aoi':AOI,'profiles':PROFILE,'groups':groups,'combined':combined,'layers':layer_sizes,
            'sharedContentAllowanceBytes':SHARED_ALLOWANCE,'regionalSunlightAccepted':False,
            'sourceAndCompute':{'projectedLocalColdNetworkHours':cold_hours,'projectedLocalWarmComputeHours':warm_hours,
                'totalHoursBeforeSetupAndRetries':compute_hours,'privateLinuxUSDAt006PerMinute':math.ceil(compute_hours*60)*.006,
                'privateLinuxUSDWithDoubleAllowance':math.ceil(compute_hours*60)*.006*2,
                'publicStandardHostedComputeUSD':0,'macOS30MinuteBoundedValidationUSD':30*.062,
                'projectedOriginalRangesBytes':round(original_bytes),'projectedNativeNAIPExportsBytes':round(naip_bytes),
                'totalSourceCacheBytes':round(cache_bytes),'oneMonthCacheStorageUSD':cache_bytes/GIB*.02,
                'sevenDayCacheStorageUSD':cache_bytes/GIB*.02*7/30,'completeExternalCacheRestoreUSD':cache_bytes/GIB*.12},
            'assumptions':['Three convenience windows (leaf-off two), not confidence intervals.',
              'USGS z10-15 uses actual independent cached cartography; other lower zoom densities approximate z16.',
              'Synthetic regional entries use mean byte density and real partition/manifest logic; no actual regional package exists.',
              '25 MiB shared allowance includes vectors/weather and unaccepted full-extent Sunlight extension; not a measurement.',
              'Package download = TAR logical bytes. Installed retains verified TAR plus extracted files. Physical APFS/device allocation unknown.',
              'Same-volume move implemented in existing installer; multi-part activation, optional UI and unchanged-part reuse remain integration work.',
              'Full-change update upper model retains two existing generations until successful new activation. Delta updates can reuse identical part hashes.',
              'Source timings reflect this runtime, not GitHub. Cold extrapolation repeats source locality; source grouping may reduce it.',
              'USD .02/GiB-month regional Standard and .12/GiB NA egress; same-region backend avoids double egress; no free tier assumed.',
              'Customer compute/requests, database and logs use 20% delivery allowance, not actual metered invoice. Retry and destination affect costs.',
              'No paid job, budget increase, GCS upload, production deployment or entitlement change performed.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original-benchmark',required=True);p.add_argument('--service-benchmark',required=True)
    p.add_argument('--source-ledger',required=True);p.add_argument('--service-cache',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=forecast(a.original_benchmark,a.service_benchmark,a.source_ledger,a.service_cache)
    atomic(Path(a.output),json_bytes(r));print(json.dumps(r,indent=2))
