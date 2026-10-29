#!/usr/bin/env python3
"""Offline dependency/cache/capacity assessor. No network or dispatch capability.

Complete graph and finite quota validation are distinct from measured regional
completion. Unknown COG block demand never earns a cache-hit or cost credit.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from gorge_checkpoint import canonical, digest, COMPACT_CLAIM, COMPACT_RECEIPT, MAX_CATALOG

GIB=2**30
MIB=2**20
PROFILES={'core':{'hiking':17,'terrain':17,'usgs-topo':16},'leaf-on':{'leaf-on':18},'leaf-off':{'leaf-off':18}}
BOUNDS=[-83.8,37.65,-83.4,37.95]
VECTORS=['hydro-flowline','hydro-waterbody','local-roads','forest-service-trails','state-park-trails','forest-service-roads','forest-ownership','wilderness','special-management','national-forest-land','county-boundaries','community-informal','oil-gas-wells']


def xy(lon,lat,z):
    n=2**z
    return math.floor((lon+180)/360*n),math.floor((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)


def coords(z):
    left,bottom=xy(BOUNDS[0],BOUNDS[1],z);right,top=xy(BOUNDS[2],BOUNDS[3],z)
    return {(x,y) for x in range(left,right+1) for y in range(top,bottom+1)}


def bbox(z,x,y,halo=0):
    n=2**z
    def lon(a):return a/n*360-180
    def lat(b):return math.degrees(math.atan(math.sinh(math.pi*(1-2*b/n))))
    return [lon(x-halo),lat(y+1+halo),lon(x+1+halo),lat(y-halo)]


def intersects(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]


def job_id(layer,z,x,y):return f'{layer}-{z}-{x}-{y}'


def morton(x,y):
    return sum(((x>>b)&1)<<(2*b) | ((y>>b)&1)<<(2*b+1) for b in range(19))


def build_graph(prior,receipts):
    if prior['boundsWGS84']!=BOUNDS or prior['profiles']!=PROFILES:
        raise ValueError('Quality/region profile changed')
    sources=prior['inventory']['sources'];jobs=[];tiles=set();source_consumers=defaultdict(list)
    completed={r['job']:r for r in receipts}
    if len(completed)!=len(receipts):raise ValueError('Duplicate prior job')
    grids={z:coords(z) for z in range(10,19)}
    for group,layers in PROFILES.items():
        for layer,maxz in layers.items():
            levels=list(range(10,17)) if layer=='usgs-topo' else list(range(16,9,-1))
            for z in levels:
                for x,y in sorted(grids[z],key=lambda p:morton(*p)):
                    identity=job_id(layer,z,x,y)
                    op='usgs-tile' if layer=='usgs-topo' else 'source-window' if z==16 else 'overview'
                    family='dem' if layer=='terrain' else layer
                    # Terrain needs one finest-grid pixel of neighbor DEM context.
                    window=bbox(z,x,y,1/512 if layer=='terrain' and z==16 else 0)
                    selected=[s['id'] for s in sources.get(family,[]) if intersects(s['bbox'],window)] if z==16 and layer!='usgs-topo' else []
                    if op=='source-window' and not selected:raise ValueError('Missing source candidates')
                    deps=[job_id(layer,z+1,2*x+dx,2*y+dy) for dx in range(2) for dy in range(2) if (2*x+dx,2*y+dy) in grids[z+1]] if op=='overview' else []
                    outputs=[]
                    for level in range(z,maxz+1) if op=='source-window' else [z]:
                        n=2**(level-z)
                        for dx in range(n):
                            for dy in range(n):
                                xx,yy=x*n+dx,y*n+dy
                                if (xx,yy) in grids[level]:outputs.append([level,xx,yy]);tiles.add((layer,level,xx,yy))
                    node={'id':identity,'layer':layer,'group':group,'z':z,'x':x,'y':y,'operation':op,'sourceIDs':selected,'dependencies':deps,'outputTiles':outputs,'preservedComplete':identity in completed}
                    if identity in completed:
                        r=completed[identity]
                        observed={(int(e['path'].split('/')[2]),int(e['path'].split('/')[3]),int(Path(e['path']).stem)) for e in r['outputs']}
                        if observed!=set(map(tuple,outputs)):raise ValueError('Prior output grid changed')
                        node['priorReceiptSHA256']=digest(canonical(r));node['priorRecipeSHA256']=r['recipeSHA256']
                    else:
                        for sid in selected:source_consumers[family+'|'+sid].append(identity)
                    jobs.append(node)
    ids={j['id'] for j in jobs}
    if not completed.keys()<=ids:raise ValueError('Prior completed work outside graph')
    seen=set();edges=0
    for j in jobs:
        if not set(j['dependencies'])<=seen:raise ValueError('Non-topological or missing dependency')
        seen.add(j['id']);edges+=len(j['dependencies'])
    expected={(layer,z,x,y) for layers in PROFILES.values() for layer,m in layers.items() for z in range(10,m+1) for x,y in grids[z]}
    if tiles!=expected:raise ValueError('Regional tile partition missing/extra')
    batches=[];batch=[];key=None
    for j in jobs:
        if j['preservedComplete']:continue
        k=(j['layer'],j['z'])
        if batch and (len(batch)==12 or k!=key):batches.append(batch);batch=[]
        batch.append(j['id']);key=k
    if batch:batches.append(batch)
    return {'format':'rrgh-offline-region-graph-v1','bounds':BOUNDS,'profiles':PROFILES,'jobs':jobs,'batches':batches,
            'sourceConsumers':dict(source_consumers),'statistics':{'jobs':len(jobs),'preservedJobs':len(completed),'remainingJobs':len(jobs)-len(completed),'tileFiles':len(tiles),'dependencyEdges':edges,'productionBatches':len(batches),'layerTiles':dict(Counter(t[0] for t in tiles)),'maxSourcesPerJob':max(len(j['sourceIDs']) for j in jobs)},
            'privateDependencies':{'vectorIDs':VECTORS,'weather':'accepted manifest and all referenced static members','sunlight':'preserved 80 sectors / 320 files','acceptedVectorWeatherBytesKnown':False},'sourcePixelCoverageVerified':False,'networkOperations':0}


def selected_cache(graph, prior, recovery, receipts, original_pins):
    by_url={s['url']:(family,s['id']) for family,entries in prior['inventory']['sources'].items() for s in entries}
    pins={p['identity']:p for p in original_pins}
    for r in receipts:
        for p in r['sourceEvidence']:
            if 'identity' in p and 'url' in p:pins[p['identity']]=p
    selected=[];unmapped=0;excluded=0
    for e in recovery['completeCacheFiles']:
        if e['kind']!='cog':continue
        identity=e['path'].split('/')[1];p=pins.get(identity)
        family_sid=by_url.get(p['url']) if p else None
        consumers=graph['sourceConsumers'].get('|'.join(family_sid),[]) if family_sid else []
        if not p or not family_sid:unmapped+=1;continue
        if not consumers:excluded+=1;continue
        selected.append({**e,'sourceKey':'|'.join(family_sid),'remainingSourceConsumers':len(consumers),'origin':'r4-delta' if e['includedInDelta'] else 'original-cache'})
    # All selections are explicit, immutable existing block identities. This does
    # not assert that a candidate source's every block will be used by each job.
    selected.sort(key=lambda e:(-e['remainingSourceConsumers'],e['sourceKey'],e['path']))
    total=sum(e['bytes'] for e in selected)
    if total>5*GIB:raise ValueError('Existing selected cache exceeds proposed cumulative cap')
    return {'format':'rrgh-offline-selected-cache-v1','originManifestSHA256':digest(canonical(recovery)),
            'sourceIdentityPinsSHA256':digest(canonical(pins)),
            'entries':selected,'selectedBytes':total,'selectedBlocks':len(selected),'unmappedBlocksPreservedButNotSelected':unmapped,'outOfScopeBlocksPreservedButNotSelected':excluded,'futureCachePersistenceCapBytes':5*GIB,'allCumulativeCacheBytesIncludingExisting':5*GIB,'externalRecoveryCapBytes':GIB,'assumedFutureCacheSavingsBytes':0,'originalArchiveLibraryFile':recovery['requiresOriginalCOGCacheLibraryFile'],'r4ArchiveSHA256':recovery['archiveSHA256'],'payloadReadOrRestored':False,'serviceCachePolicy':'Do not persist duplicate completed USGS/NAIP responses; keep original archives. Reuse exact surviving local request keys only; no assumed future savings.','sunlightElevationPolicy':'Preserve existing archive; no new persistence or recomputation needed for completed Sunlight.'}


def allocate_exact(total,weights):
    if type(total)is not int or total<0 or not weights or any(type(w)is not int or w<=0 for w in weights):raise ValueError('Invalid allocation')
    denom=sum(weights);result=[total*w//denom for w in weights]
    left=total-sum(result)
    for i in range(left):result[i]+=1
    return result


def cost(storage,reads,class_a,class_b):
    d=Decimal
    gross=d(storage)/GIB*d('.03')+d(reads)/GIB*d('.23')+d(class_a)/1000*d('.01')+d(class_b)/1000*d('.001')
    return {'firstMonthGrossUSD':str(gross),'firstMonthWith20PercentUSD':str(gross*d('1.2')),'monthlyStorageWith20PercentUSD':str(d(storage)/GIB*d('.03')*d('1.2'))}


def validate_envelope(envelope):
    """Validate reservations, never convert forecast acceptance into authority."""
    limits=envelope['limits']
    for category,dimension in [('storageCategories','storedBytes'),('readCategories','egressBytes')]:
        values=list(envelope[category].values())
        if any(type(v)is not int or v<0 for v in values) or sum(values)!=limits[dimension]:
            raise ValueError('Cumulative category reservation mismatch')
    if envelope['checkpointBookkeeping']['reservedBytes']>envelope['storageCategories']['allBookkeepingAndCatalogs']:
        raise ValueError('Bookkeeping allocation exceeded')
    if envelope['operationForecast']['classAUpperAllocated']>limits['classARequests'] or envelope['operationForecast']['classBStructuralAndRecoveryAllowance']>limits['classBRequests']:
        raise ValueError('Operation allocation exceeded')
    source=envelope['sourceForecast']
    if source['primarySourceReservationBytes']+source['rescueSourceReservationBytes']!=limits['sourceBytes']:
        raise ValueError('Source reservations double counted or omitted')
    actual=cost(limits['storedBytes'],limits['egressBytes'],limits['classARequests'],limits['classBRequests'])
    if actual!=envelope['cost']:
        raise ValueError('Stale cost result')
    if Decimal(actual['firstMonthWith20PercentUSD'])>Decimal('8') or Decimal(actual['monthlyStorageWith20PercentUSD'])>Decimal('1'):
        raise ValueError('Proposed financial envelope exceeded')
    if envelope['approved'] is not False or envelope['dispatchEnabled'] is not False or envelope['accountAuthorization']['eitherApproved'] is not False:
        raise ValueError('Offline forecast cannot grant spending authority')
    return True


def capacity(graph,cache,prior_forecast):
    n=graph['statistics']['remainingJobs'];b=graph['statistics']['productionBatches'];rescue_jobs=64
    # One independently funded recovery slot per primary batch plus 64 finite
    # rescue slots. No universal second pass; retries retain all prior charges.
    slots=2*b+rescue_jobs
    bookkeeping=slots*(COMPACT_CLAIM+COMPACT_RECEIPT)+(n+rescue_jobs)*COMPACT_RECEIPT+512*MAX_CATALOG+128*MIB
    if bookkeeping>GIB:raise ValueError('Metadata allocation does not fit')
    primary_a=2*n+2*slots+2*512+2*rescue_jobs+256+256
    if primary_a>90000:raise ValueError('Create operation allocation does not fit')
    modeled_b=2*n+graph['statistics']['dependencyEdges']+2*b+512*2+256+10000
    if modeled_b>150000:raise ValueError('Read operation allocation does not fit')
    storage={'checkpointPayloadsIncludingShared':8*GIB,'deliveryPackages':8*GIB,'selectedCacheCumulative':5*GIB,'orphanRetryPayloads':2*GIB,'allBookkeepingAndCatalogs':GIB}
    reads={'assemblyCheckpointPayloads':8*GIB,'finalPackageHashVerification':8*GIB,'overviewChildPayloads':GIB,'selectiveCacheRecovery':GIB,'metadataReceiptsCatalogsRecovery':3*GIB}
    source_estimate=prior_forecast['sourceAndCompute']['totalSourceCacheBytes']
    forecast=prior_forecast['combined']['archiveBytes']
    high=sum(g['sampleSpreadArchiveBytes'][1] for g in prior_forecast['groups'].values())
    # These are quota slices, NOT new empirical estimates of required work.
    remaining=[j for j in graph['jobs'] if not j['preservedComplete']]
    source=[j for j in remaining if j['operation']!='overview']
    weights=[30 if j['layer']=='leaf-off' else 10 if j['layer']=='hiking' else 6 if j['layer']=='terrain' else 3 if j['layer']=='leaf-on' else 1 for j in source]
    allocations=allocate_exact(704*GIB,weights)
    return {'format':'rrgh-offline-campaign-envelope-v2','approved':False,'dispatchEnabled':False,'bulkProductionEnabled':False,
      'storageCategories':storage,'readCategories':reads,'limits':{'storedBytes':sum(storage.values()),'egressBytes':sum(reads.values()),'classARequests':90000,'classBRequests':150000,'sourceBytes':720*GIB,'workerSeconds':900*3600,'attempts':n+rescue_jobs,'maxConcurrency':1},
      'checkpointBookkeeping':{'slots':slots,'claimBytesPerSlot':COMPACT_CLAIM,'finalBytesPerSlot':COMPACT_RECEIPT,'jobReceiptMaxBytes':COMPACT_RECEIPT,'cachePackCountCap':512,'cacheCatalogMaxBytes':MAX_CATALOG,'reservedBytes':bookkeeping,'legacySameSlotsBytes':slots*2*MIB,'metadataHeadroomBytes':GIB-bookkeeping},
      'operationForecast':{'classAUpperAllocated':primary_a,'classBStructuralAndRecoveryAllowance':modeled_b,'classAHeadroom':90000-primary_a,'classBHeadroom':150000-modeled_b},
      'packageProjection':{'inheritedMeanBytes':forecast,'inheritedSampleSpreadUpperSumBytes':high,'perCopyHardCapBytes':8*GIB,'qualityUnchanged':True,'highSampleScenarioFits':high<=8*GIB,'completionGuaranteed':False},
      'sourceForecast':{'inheritedColdBytes':source_estimate,'inheritedHours':prior_forecast['sourceAndCompute']['totalHoursBeforeSetupAndRetries'],'primarySourceReservationBytes':704*GIB,'rescueSourceReservationBytes':16*GIB,'cacheSavingsCreditedBytes':0,'requiredCOGBlockRangesFullyKnown':False,'quotaSlicesSHA256':digest(canonical(list(zip([j['id'] for j in source],allocations)))),'quotaSlicesAreMeasuredDemand':False},
      'cost':cost(sum(storage.values()),sum(reads.values()),90000,150000),
      'accountAuthorization':{'proposedFirstMonthUSD':'8','proposedRecurringUSD':'1','eitherApproved':False,'previousDrillAuthorizationReusable':False,'trialCreditIsAllowance':False,'billingAlertsAreHardStop':False,'githubHardCeilingUSD':350},
      'validation':{'topologyComplete':True,'qualityAndExtentPreserved':True,'capacityArithmeticPass':True,'regionalSourceDemandValidated':False,'acceptedPrivateInputsMeasured':False,'fullProductionReady':False},
      'stopConditions':['Any global/category/slot/operation/source/time/attempt reservation exhausted','Unexpected source identity, missing dependency, gap, seam, pixel, hash or generation failure','Ambiguous upload or absent completion receipt: preserve claim, do not automatically rerender','Unmeasured private input or output exceeds allocation: stop without downsampling, pruning layers, deleting, increasing budgets or reusing old approval'],
      'readAccounting':'All receipt/catalog/metadata bodies and +1 bounded-reader probes count. Each exact ref is passed durably; extra metadata lookup or range fragmentation consumes the same fixed quotas.',
      'retryPolicy':'At most 64 specifically authorized rescue jobs within total budget; at most two attempts per logical job including preserved prior attempts. Failed allocations never refunded. No full second campaign.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['prior','receipts','recovery','source-pins','prior-forecast','output']:p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();read=lambda p:json.loads(p.read_bytes())
    prior,receipts,recovery,pins,old=map(read,[a.prior,a.receipts,a.recovery,a.source_pins,a.prior_forecast])
    graph=build_graph(prior,receipts);cache=selected_cache(graph,prior,recovery,receipts,pins);forecast=capacity(graph,cache,old)
    validate_envelope(forecast)
    a.output.mkdir(parents=True,exist_ok=True)
    for name,obj in [('REGIONAL-DEPENDENCY-GRAPH.json',graph),('SELECTED-CACHE-FORECAST.json',cache),('CAMPAIGN-FORECAST.json',forecast)]:
        (a.output/name).write_bytes(canonical(obj))
    print(json.dumps({'graph':graph['statistics'],'selectedCacheBytes':cache['selectedBytes'],'unmappedCacheBlocks':cache['unmappedBlocksPreservedButNotSelected'],'bookkeeping':forecast['checkpointBookkeeping'],'operations':forecast['operationForecast'],'cost':forecast['cost'],'validation':forecast['validation']},indent=2))

if __name__=='__main__':main()
