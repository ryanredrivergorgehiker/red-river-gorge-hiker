"""Read-only Git history test; never reads or writes protected Cloud objects."""
import json
from pathlib import Path
import sys

from rrgh_package_authority import historical_usgs, geometry, required_jobs, read_plan, digest, require
from rrgh_crosswave_batch import original_index
from rrgh_seed_children import AUTHORITY as SEEDS

source=Path(sys.argv[1]).resolve()
usgs=historical_usgs(source)
_,plan=read_plan(source,1419,'943a8fc21d34ce6dda1492c1ad80c58e56d6aa61da6660ecc50d70296c90326d')
waves=original_index()['waves']+usgs+plan['crosswaveHistory']
seen=set(SEEDS['jobs'])
for w in waves:
    jobs=w['acceptedJobIDs']
    require(not seen.intersection(jobs),'Duplicate accepted lineage')
    require(sum(len(geometry(j)) for j in jobs)==w['expectedTiles'],'Historical output count mismatch')
    seen.update(jobs)
require(seen==set(plan['completedJobIDs']),'Historical package sources do not cover the frozen actual baseline')
seen.update(plan['approvedJobIDs'])
require(len(seen)==33686 and sum(len(geometry(j)) for j in seen)==273868,
        'Frozen independently accepted wave1419 baseline changed')
missing=required_jobs()-seen
require(sum(len(geometry(j)) for j in missing)==4410,'Remaining package raster denominator changed')
print(json.dumps(dict(verified=True,actualAcceptedBaseline=1419,acceptedJobs=len(seen),
    acceptedRasterTiles=273868,restoredUSGSJobs=1770,usgsAcceptanceWaves=len(usgs),
    usgsAuthoritySHA256=digest(usgs),remainingRasterTiles=4410,
    sourceRequests=0,cloudReads=0,cloudWrites=0,productionAcceptanceChanged=False),sort_keys=True))
