#!/usr/bin/env python3
"""Architecture storage/cost model, explicitly not physical iPhone measurements."""
import argparse,json,math
from pathlib import Path
from benchmark_gorge_pipeline import json_bytes
from cached_cog_source import atomic


def forecast(prior,sun):
 groups={};total=prior['combined'];cap=256_000_000
 for name,g in prior['groups'].items():
  a=g['archiveBytes'];e=g['extractedBytes'];largest=g['largestPartBytes']
  groups[name]={'downloadBytes':a,'installedContentBytes':e,'cleanInstallPeakContentBytes':e+largest,
                'updatePeakWithActiveOnlyBytes':2*e+largest,'updatePeakWithTwoDisjointOldGenerationsBytes':3*e+largest,
                'maxPartBytes':largest,'gcsUSDMonthPerVersion':a/2**30*.02,'egressUSDPerDownload':a/2**30*.12}
 e=total['extractedBytes'];a=total['archiveBytes'];largest=max(g['maxPartBytes'] for g in groups.values());count=total['tileFiles']
 return {'status':'Projection from measured benchmark compression; no physical iPhone test or regional release',
  'groups':groups,'combined':{'downloadBytes':a,'installedContentBytes':e,'cleanInstallPeakContentBytes':e+largest,
   'peakWithAllThreePartialGroupsAtHardCapBytes':e+3*cap+3*1_048_576,
   'steadyTwoDisjointGenerationsBytes':2*e,'allChangedUpdateWithTwoOldGenerationsBytes':3*e+largest,
   'tenPercentChangedFirstUpdateBytes':1.1*e+largest,'tenPercentChangedUpdateWithTenPercentPreviousUniqueBytes':1.2*e+largest,
   'modeled4096ByteAllocationSlackWorstCasePerGenerationBytes':count*4095,
   'modeled4096ByteAllocationSlackAveragePerGenerationBytes':count*2048,
   'gcsOneVersionUSDMonth':a/2**30*.02,'egressUSDAllMaps':a/2**30*.12,'delivery20PercentAllowanceUSD':a/2**30*.12*1.2},
  'sunlightMeasured':{'sectors':sun['counts']['sectors'],'files':sun['counts']['files'],'bytes':sun['counts']['bytes'],'sourceTransfers':sun['sourceLedger'],'elapsedSeconds':sun['elapsedSeconds']},
  'completionForecast':{**prior['sourceAndCompute'],'sourceInventoryObjects':{'hiking':9,'dem':614,'leafOff':614},
    'warning':'Cold transfer estimate is conservative sample extrapolation, not a measured full-region runtime. New PNG overview borders, shared vectors/weather, metadata, runner startup and per-job scheduling are not yet fully measured.'},
  'assumptions':['Existing 25MiB shared-content allowance retained; actual full Sunlight is included within it, not added twice.',
   'Removed transport TAR after verified extraction; active/rollback/pending share immutable same-hash parts.',
   'Three pending generations may temporarily coexist with active and rollback across independent groups; obsolete pending is reclaimed on next activation.',
   'APFS directory metadata, snapshots, OS reserve, existing legacy installation and app/route storage are additional; no physical iPhone figure is claimed.',
   'No speculative credit, free-tier or tax deduction. GCS rates use US regional Standard and NA internet delivery; backend service duration and retries remain separately metered.']}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--prior',required=True);p.add_argument('--sunlight',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=forecast(json.load(open(a.prior)),json.load(open(a.sunlight)));atomic(Path(a.output),json_bytes(r));print(json.dumps(r['combined'],indent=2))
