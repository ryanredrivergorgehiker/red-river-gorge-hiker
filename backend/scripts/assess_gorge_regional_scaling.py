"""Offline regional scaling audit. Evidence/math only; no network or dispatcher.

Input paths are explicit preserved evidence. Estimates never authorize spending.
"""
import argparse,hashlib,json,math,statistics
from collections import Counter,defaultdict
from decimal import Decimal as D
from pathlib import Path

GIB=2**30
def sha(raw):return hashlib.sha256(raw).hexdigest()
def cost(storage,reads,a,b):
    return (D(storage)/GIB*D('.03')+D(reads)/GIB*D('.23')+D(a)/1000*D('.01')+D(b)/1000*D('.001'))*D('1.2')
def maximum_reads(allowance,storage,a,b):
    available=D(allowance)/D('1.2')-D(storage)/GIB*D('.03')-D(a)/1000*D('.01')-D(b)/1000*D('.001')
    return max(0,int(available/D('.23')*GIB))
def all_caps_fit(usage,limits):return all(0<=usage[k]<=v for k,v in limits.items())

def locality(jobs,batch_size):
    batches=[jobs[i:i+batch_size]for i in range(0,len(jobs),batch_size)]
    incidences=sum(len({s for j in b for s in j['sourceIDs']})for b in batches)
    return {'jobs':len(jobs),'batches':len(batches),'sourceBatchIncidences':incidences,
        'uniqueSources':len({s for j in jobs for s in j['sourceIDs']}),'batchSize':batch_size,
        'incidencesAreNotBytes':True}

def capacity(entries,partition,part_size,part_manifest,json_bytes,shared_bytes):
    # Metadata only: no fake payload files, archive writing or source processing.
    out={}
    for group,es in entries.items():
        if group=='core':
            # Preserve measured total and 340-file count; reserve max safe path
            # length. This is a size fixture, never a genuine shared manifest.
            sizes=[shared_bytes//340+(i<shared_bytes%340)for i in range(340)]
            es=es+[{'path':'shared/'+str(i).zfill(5)+'-'+'x'*74+'.bin','bytes':v,'sha256':'0'*64,'layer':'shared'}for i,v in enumerate(sizes)]
        parts=partition(group,es);archives=[part_size(group,p)for p in parts]
        e=sum(sum(x['bytes']for x in p)+len(json_bytes(part_manifest(group,p)))for p in parts)
        allocated=sum((x['bytes']+4095)//4096*4096 for x in es)
        allocated+=sum((len(json_bytes(part_manifest(group,p)))+4095)//4096*4096 for p in parts)
        out[group]={'parts':len(parts),'partCountLimit':64,'partCountPass':len(parts)<=64,'largestPartBytes':max(archives),
         'largestPartEntries':max(len(p)+1 for p in parts),'downloadBytes':sum(archives),'installedLogicalBytes':e,
         'modeled4096AllocationBytes':allocated,'sequentialCleanPeakLogicalBytes':e+max(archives),
         'sequentialUpdateWithTwoDistinctOldGenerationsBytes':3*e+max(archives),
         'simulatedAllTiles':len(es)-(340 if group=='core'else 0),'qualityProfileUnchanged':True}
    total=sum(x['installedLogicalBytes']for x in out.values());largest=max(x['largestPartBytes']for x in out.values())
    return {'groups':out,'combined':{'downloadBytes':sum(x['downloadBytes']for x in out.values()),'installedLogicalBytes':total,
      'sequentialCleanPeakLogicalBytes':total+largest,'threeConcurrentGroupDownloadsPeakBytes':total+sum(x['largestPartBytes']for x in out.values()),
      'worstAllChangedUpdateTwoOldLogicalBytes':3*total+largest,
      'modeled4096AllocationBytes':sum(x['modeled4096AllocationBytes']for x in out.values()),
      'modeled4096WorstUpdateTwoOldBytes':3*sum(x['modeled4096AllocationBytes']for x in out.values())+largest,
      'physicalDeviceMeasurement':False,'sharedFileSizeDistributionMeasured':False,'directoryAPFSAndOSOverheadIncluded':False,
      'privateSharedBytes':shared_bytes,'metadataReserveAdditionalBytes':4*2**20}}

def assess(args):
    root=Path(args.workspace);old=root/'stage6';out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    hashes={}
    def read(p):
        p=Path(p);raw=p.read_bytes();hashes[str(p.relative_to(root))]={'bytes':len(raw),'sha256':sha(raw)};return json.loads(raw)
    pins=read(old/'forecast/inputs/ORIGINAL-SOURCE-PINS.json');prior=read(old/'forecast/inputs/PRIOR-REGION-PLAN.json')
    graph=read(old/'forecast/evidence/REGIONAL-DEPENDENCY-GRAPH.json');r4=read(old/'forecast/inputs/PRIOR-RECEIPTS.json')
    stage=read(old/'evidence/SECOND-STAGE-OFFLINE-FORECAST.json');cost2=read(old/'evidence/SECOND-STAGE-COST-RECONCILIATION.json')
    prod=read(old/'evidence/RUN-41050828307-PRODUCER-EVENTS.json');recovery=read(old/'evidence/RUN-41050828307-RECOVERY-EVENTS.json')
    envelope=read(old/'forecast/evidence/CAMPAIGN-FORECAST.json');oldpackage=read(old/'forecast/inputs/INHERITED-PACKAGE-FORECAST.json')
    parsed=read(root/'stage7/evidence/PRESERVED-TIFF-LOCALITY.json')
    expected=read(old/'forecast/evidence/INPUT-HASHES.json')
    for n,h in expected.items():
        p=old/'forecast/inputs'/n
        if p.stat().st_size!=h['bytes']or sha(p.read_bytes())!=h['sha256']:raise ValueError('Preserved forecast input changed: '+n)
    done=set(stage['preservedJobIDs']);jobs=graph['jobs'];jm={j['id']:j for j in jobs}
    assert len(done)==44 and sum(len(jm[j]['outputTiles'])for j in done)==436
    consumed=defaultdict(set);boundaries={};loc={}
    for layer in ['hiking','terrain','leaf-off','leaf-on']:
        js=[j for j in jobs if j['layer']==layer and j['operation']=='source-window']
        boundaries[layer]={'windows':len(js),'multipleSourceWindows':sum(len(j['sourceIDs'])>1 for j in js),
                           'maximumSources':max(map(lambda j:len(j['sourceIDs']),js))}
        consumed['dem'if layer=='terrain'else layer]={s for j in js for s in j['sourceIDs']}
        loc[layer]={'currentMorton':[locality(js,n)for n in (12,48,192)],
            'sourceSorted':[locality(sorted(js,key=lambda j:(tuple(j['sourceIDs']),j['x'],j['y'])),n)for n in(12,48,192)]}
    validated=[x for x in parsed if x['status']=='metadata-validated'];locality_bounds={}
    for family in ['hiking','dem','leaf-off']:
        rs=[x for x in validated if x['regionalIdentity']and x['regionalIdentity'][0]==family]
        repeated=sum(x['allLevelHaloIndependentBytes']for x in rs);unique=sum(x['allLevelHaloUniqueBytes']for x in rs)
        locality_bounds[family]={'knownSources':len(rs),'requiredSources':len(consumed[family]),'independentAllLevelHaloBytes':repeated,
         'uniqueAllLevelHaloBytes':unique,'boundRatio':repeated/unique if unique else None,'actualTransferSavingsProven':False}
    stagejobs=[x for x in prod if 'job'in x];phase=next(x for x in prod if x.get('phase')=='stage')
    bootstrap=next(x for x in prod if x.get('phase')=='bootstrap');rec=next(x for x in recovery if x.get('phase')=='fresh-recovery')
    scenario_source={}
    for layer in boundaries:
        sample=[x for x in stagejobs if jm[x['job']]['layer']==layer]
        scenario_source[layer]=math.ceil(sum(x['execution']['sourceUsage']['actual']['receivedBodyBytes']for x in sample)/len(sample)*boundaries[layer]['windows'])
    source_total=sum(scenario_source.values())
    old_raw=oldpackage['sourceAndCompute']['totalSourceCacheBytes']
    raw_cases={'historicalColdTransferSampleBytes':old_raw,'stage2RoleWeightedTransferScenarioBytes':source_total,
      'roleWeightedByLayer':scenario_source,'neitherScenarioIsUniqueRegionalBytes':True,
      'persistAndReadOnceScenarioExcludingOperationsAndDeliveryUSD':str(cost(source_total,source_total,0,0)),
      'persistMonthlyWithContingencyUSD':str(D(source_total)/GIB*D('.036'))}
    candidate=stage['nextRecommendation']['candidateJobs']
    accepted_sources={s for j in done for s in jm[j]['sourceIDs']}
    candidate_new=sorted({s for j in candidate for s in j['sourceIDs']}-accepted_sources)
    # Actual per-tile sample receipts, preserving source hashes and no pixels.
    densities=defaultdict(list);seen={}
    for rep in [r4,read(root/'benchmark/v2/BENCHMARK.json')['receipts'],read(root/'benchmark2/final-services/BENCHMARK.json')['receipts']]:
        for r in rep:
            for e in r['outputs']:
                p=e['path'].split('/');layer=p[1]
                if layer not in stage['layerMeasurements']:continue
                key=e['path']
                if key in seen:
                    # Different accepted historical recipes remain separate evidence;
                    # current R4 sample is first and wins for density only.
                    continue
                seen[key]=e['sha256'];densities[(layer,int(p[2]))].append(e['bytes'])
    from build_gorge_map_bundles import partition,part_size,part_manifest
    from benchmark_gorge_pipeline import json_bytes
    capacity_results={}
    for mode in ['mean','sample_max','mean_plus_20_percent']:
        es=defaultdict(list)
        for j in jobs:
            for z,x,y in j['outputTiles']:
                vals=densities.get((j['layer'],z),densities.get((j['layer'],16)))
                if not vals:raise ValueError('Missing density sample')
                amount=math.ceil(max(vals)if mode=='sample_max'else statistics.mean(vals)*(1.2 if mode.endswith('percent')else 1))
                es[j['group']].append({'path':f"tiles/{j['layer']}/{z}/{x}/{y}.jpg",'bytes':amount,'sha256':'0'*64,'layer':j['layer'],'z':z,'x':x,'y':y})
        capacity_results[mode]=capacity(es,partition,part_size,part_manifest,json_bytes,stage['capacity']['combinedBytes'])
    # Full graph grid/manifest calculations, without region payload generation.
    for m in capacity_results.values():
        assert sum(g['simulatedAllTiles']for g in m['groups'].values())==278278
        for g in m['groups'].values():
            assert g['largestPartBytes']<=256_000_000 and g['largestPartEntries']<=60_000
    known_sources={(x['regionalIdentity'][0],x['regionalIdentity'][1])for x in validated if x['regionalIdentity']}
    survey=[]
    for family in ['hiking','dem','leaf-off']:
        for s in prior['inventory']['sources'][family]:
            if s['id']in consumed[family]and(family,s['id'])not in known_sources:survey.append({'family':family,**s})
    # Replacement is evidence acquisition plus genuinely diverse two-window trial.
    # It is a proposal only; conditional authority names a different exact job set.
    excluded=set(done)
    # Exclude any earlier benchmark pixel position, even if it lacks a graph receipt.
    for path in seen:
        p=path.split('/');z,x,y=int(p[2]),int(p[3]),int(Path(p[4]).stem)
        if z>=16:excluded.add(f'{p[1]}-16-{x//2**(z-16)}-{y//2**(z-16)}')
    windows=[]
    for target in[(17530,25300),(17565,25345)]:
        options=[]
        for j in jobs:
            if j['layer']!='leaf-off'or j['operation']!='source-window'or len(j['sourceIDs'])<2:continue
            ids=[f'{l}-16-{j["x"]}-{j["y"]}'for l in ['hiking','terrain','leaf-off','leaf-on','usgs-topo']]
            if any(i not in jm or i in excluded for i in ids):continue
            dist=(j['x']-target[0])**2+(j['y']-target[1])**2
            options.append((dist,-len(j['sourceIDs']),j['id'],ids))
        best=min(options);windows.append(best[3]);excluded.update(best[3])
    replacement=sum(windows,[])+['leaf-on-15-8772-12661','leaf-off-15-8772-12661']
    assert len(replacement)==12 and sum(len(jm[i]['outputTiles'])for i in replacement)==108 and not set(replacement)&done
    # A role-weighted target envelope avoids the invalid jobs-equal-cost assumption.
    costs={'existingEnvelopeUSD':str(cost(24*GIB,21*GIB,90000,150000)),
       'flatJobRepetitionUSD':stage['throughput']['stageRepetitionStressScenarioUSD'],
       'roleWeightedRawCacheScenario':raw_cases,
       'secondStageDecomposition':{'newStoredBytes':cost2['actualMeteredUsage']['newFinalizedObjectBytes'],'outputsBytes':3080460,
        'nonOutputStoredBytes':cost2['actualMeteredUsage']['newFinalizedObjectBytes']-3080460,'bootstrapReadBytes':bootstrap['gcsIncludingReceipt']['responseBodyBytes'],
        'recoveryReadBytes':rec['gcsIncludingReceipt']['responseBodyBytes'],'failedPreflightIncluded':True},
       'maxReadsAtOriginal24GiBStorageAndOperationsBytes':maximum_reads('8',24*GIB,90000,150000),
       'requiresIndependentRecoveryToDoubleAsAssemblyRead':True,'allRawCachePersistenceFits5GiB':False,
       'sharedBootstrapAtEveryOldBatchBytes':stage['capacity']['combinedBytes']*graph['statistics']['productionBatches'],
       'selectiveFutureCachePolicyImplemented':False,'allOriginalCachePreserved':True,
       'qualityReductionAllowed':False,'budgetFitProven':False,
       'sameEnvelopeWithAll5GiBCacheIndependentlyRecoveredUSD':str(cost(24*GIB,25*GIB,90000,150000)),
       'historicalReleasedAmountRetainedUSD':'.70',
       'futureScalingAdmissionTarget':{'notAMeasuredForecast':True,'historicalReleasedUSD':'.70','futureStoredBytes':22*GIB,
         'futureReadBytes':int(19.5*GIB),'futureClassA':75000,'futureClassB':120000,
         'futureCostWith20PercentUSD':str(cost(22*GIB,int(19.5*GIB),75000,120000)),
         'totalIncludingHistoricalReleaseUSD':str(D('.70')+cost(22*GIB,int(19.5*GIB),75000,120000)),
         'conditions':['Larger source-local batches reduce per-slot claim overhead; future batch authority is separate.',
          'Preserve all existing private caches. Future new durable cache growth must be <=0.5GiB or recompute the target.',
          'Exact source pins and bounded refetch of future transient public-source ranges require a validated recovery policy; no credit yet.',
          'Independent output recovery performs package assembly in the same read; final package independently hashed once.',
          'Compact source catalogs and receipt references keep metadata reads <=0.5GiB; no repeated shared-payload bootstrap.',
          'Current high sample is still not a regional upper bound. Recompute before every paid tranche.']}}
    # Count selected job categories to make the conditional no-go auditable.
    gate={'conditionalApproval':'Third original 12-job /108-tile candidate, only after capacity/cache pass and material scaling evidence',
      'originalCandidateJobs':[j['id']for j in candidate],'originalCandidateNewSourceIDs':candidate_new,
      'newDominantLeafOffSources':sorted({s for j in candidate if j['layer']=='leaf-off'for s in j['sourceIDs']}-accepted_sources),
      'newSharedCacheRetentionOrAssemblyPathTested':False,'fullRegionCapacityPass':False,
      'meaningfulScalingEvidencePass':False,'releasedUSD':'0.00','lockedUSD':'7.30','dispatchEnabled':False,
      'reasons':['Same leaf-off source and unchanged all-cache checkpoint policy do not test the dominant scaling cost.',
       'One new DEM source does not validate the regional aerial inventory or per-source reuse.',
       'Exact full-region capacity and cache footprint cannot be certified from the current limited sample; +20% sensitivity exceeds the existing 8GiB category.']}
    proposal={'format':'rrgh-regional-scaling-validation-proposal-v1','approved':False,'dispatchEnabled':False,
      'releaseRequestedUSD':'.35','releaseFromExistingLockedBalanceOnly':True,'lockedAfterSeparateApprovalUSD':'6.95',
      'preservedMetadataSources':len(known_sources),'uninspectedRequiredSources':len(survey),'metadataTargets':survey,
      'rasterJobs':[jm[i]for i in replacement], 'rasterTiles':108,'knownCompletedOverviewDependencies':True,
      'phases':['Pin and inspect regional source headers/IFD arrays using bounded metadata ranges; reuse prior header checkpoints.',
       'Recalculate unique pixel-range demand at unchanged production settings and validate selective future-cache/output/recovery capacity.',
       'If phase-two admission passes, execute the twelve specified diverse/boundary jobs, using source-local batch telemetry and packed checkpoints.',
       'Fresh independent recovery validates outputs and assembles a bounded genuine part from those same recovered bytes; do not reread for assembly.'],
      'limits':{'storedBytes':GIB,'egressBytes':GIB,'classARequests':200,'classBRequests':500,'sourceBytes':2*GIB,'sourceRequests':2000,'seconds':10800,'attempts':12,'maxConcurrency':1},
      'internalCaps':{'metadataStoredBytes':128*2**20,'futureCacheGrowthBytes':448*2**20,'outputsAndAssemblyBytes':64*2**20,'stateBytes':12*2**20,'bookkeepingBytes':4*2**20},
      'estimatedWorstCaseWith20PercentUSD':str(cost(GIB,GIB,200,500)),
      'implementationPrerequisites':['Native first-range source identity pinning; conditional If-Match for every later range, no unbounded HEAD/retry loop.',
       'Export exact metadata catalogs and per-job block demand, measured bytes, read reasons and cache reuse; no protected pixel or credential artifacts.',
       'Pre-operation cumulative reservations must include metadata, production, independently recovered output/cache and assembly; stop before any projected excess.',
       'No raw cache retention reduction is credited until a prospective policy proves reproducible recovery. Never delete or rewrite an existing cache or checkpoint.'],
       'stopStillUseful':'If source metadata or resource admission fails, persist the measured regional inventory and reasons. Do not spend remaining slots on low-value warm duplicates.',
       'successCriteria':{'sourceSurvey':'Every required COG has parsed byte-count/offset/georeference metadata or an explicit unresolved record; missing metadata never counts as zero demand.',
        'demand':'Compute unique ranges and reuse per source/overview level; compare observed job requests against admitted bounds.',
        'retention':'Separate immutable metadata, useful future raw ranges, completed output and ledger bytes. Prove any proposed transient source recovery without deleting prior caches.',
        'assembly':'One fresh output read supplies independent QA and a real unchanged-quality part; enforce 256,000,000 B /60,000 members /64 parts per group.',
        'decision':'Publish a measured remaining-campaign forecast, or identify the exact budget/capacity deficit before any later release.'}}
    result={'format':'rrgh-regional-scaling-assessment-v1','dateEastern':'2026-10-30','networkOperations':0,'cloudCostIncurredUSD':'0',
      'preserved':{'jobs':44,'rasterTiles':436,'sunlightAssets':320},'graph':graph['statistics'],
      'requiredUniqueSources':{k:len(v)for k,v in consumed.items()},'sourceBoundaries':boundaries,'batchLocality':loc,
      'preservedHeaderDemandBounds':locality_bounds,'packageCapacity':capacity_results,'costReconciliation':costs,'conditionalStageGate':gate,
      'nativeCapacitySourceCommit':'00ab0a531a310e7459ad310e2f9ba997f668aab7','nativeCIRepeated':False,
      'uncertainties':['Metadata bounds include all TIFF levels and full source-tile halo; not actual GDAL request predictions or guaranteed savings.',
       'Physical APFS allocation, existing legacy package, app/route data and OS reserve are additional.',
       'Compression samples are local convenience windows; sample_max is not a regional statistical upper bound.',
       'GitHub budget observation is historical; refresh before any future dispatched stage.']}
    for name,value in [('REGIONAL-SCALING-ASSESSMENT.json',result),('REPLACEMENT-SCALING-STAGE-PROPOSAL.json',proposal),('INPUT-HASHES.json',hashes)]:
        (out/name).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
    return result,proposal

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    r,p=assess(args);print(json.dumps({'conditionalGate':r['conditionalStageGate'],'sources':r['requiredUniqueSources'],
      'capacity':{k:v['combined']for k,v in r['packageCapacity'].items()},'locality':r['preservedHeaderDemandBounds'],
      'replacementJobs':[j['id']for j in p['rasterJobs']],'metadataTargets':p['uninspectedRequiredSources']},indent=2))

if __name__=='__main__':main()
