"""Compare serial and parallel pinned overview renders in private scratch."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import statistics
import tempfile
from time import perf_counter
from hashlib import sha256
from PIL import Image

from rrgh_verified_overview import render


def render_job(task):
    region, item, child_root, destination, source_root = task
    started = perf_counter()
    result = render(region, item["job"], item["children"], child_root,
                    destination, source_root)
    output=result['receipt']['outputs'][0]
    return dict(sha256=output['sha256'], path=str(Path(destination)/output['path']), bytes=output['bytes'],
                pid=os.getpid(), started=started, finished=perf_counter())


def readback(result):
    """Fresh-process hash/pixel readback; scratch results never enter coverage."""
    path=Path(result['path']);raw=path.read_bytes()
    if len(raw)!=result['bytes'] or sha256(raw).hexdigest()!=result['sha256']:
        raise ValueError('Independent output hash/length differs')
    with Image.open(path) as im:
        im.load()
        if im.size!=(256,256) or (im.mode=='RGBA' and im.getextrema()[3]!=(255,255)):
            raise ValueError('Independent output pixels incomplete')
    return dict(sha256=result['sha256'],pid=os.getpid())


def benchmark(manifest, children, source, rounds=3):
    jobs = manifest["jobs"]
    targets = {tuple(item["job"][k] for k in ("layer", "z", "x", "y"))
               for item in jobs}
    if len(jobs) < 2 or len(targets) != len(jobs):
        raise ValueError("Provide at least two distinct target tiles")
    if any(tuple(child["tile"]) in targets for item in jobs for child in item["children"]):
        raise ValueError("Assignments must use pre-existing children")
    if rounds != 3:
        raise ValueError("Exactly three bounded comparison rounds required")
    # Warm imports equally before timing; each measured pass gets new output
    # directories and includes process-pool construction/destruction overhead.
    with tempfile.TemporaryDirectory(prefix="rrgh-render-warm-") as directory:
        render_job((manifest['region'], jobs[0], children, Path(directory)/'warm', source))
    baseline = None
    measurements = {workers: [] for workers in (1, 2, 4)}
    for order in ((1, 2, 4), (2, 4, 1), (4, 1, 2)):
        for workers in order:
            with tempfile.TemporaryDirectory(prefix="rrgh-render-") as directory:
                tasks = [(manifest["region"], item, children, Path(directory) / str(i), source)
                         for i, item in enumerate(jobs)]
                start = perf_counter()
                if workers == 1:
                    results = list(map(render_job, tasks))
                else:
                    with ProcessPoolExecutor(max_workers=workers) as pool:
                        results = list(pool.map(render_job, tasks))
                with ProcessPoolExecutor(max_workers=1) as verifier:
                    checked=list(verifier.map(readback, results))
                if [r['sha256'] for r in checked] != [r['sha256'] for r in results]:
                    raise ValueError('Independent verification changed output')
                if {r['pid'] for r in checked} & {r['pid'] for r in results}:
                    raise ValueError('Readback was not in an independent process')
                elapsed = perf_counter() - start
                hashes = [r['sha256'] for r in results]
                if baseline is None:
                    baseline = hashes
                elif baseline != hashes:
                    raise ValueError("Parallel render differs from serial baseline")
                events = sorted([(r['started'], 1) for r in results] +
                                [(r['finished'], -1) for r in results])
                active = peak = 0
                for _, delta in events:
                    active += delta; peak = max(peak, active)
                if workers > 1 and peak < 2:
                    raise ValueError("Parallel execution was not observed")
                measurements[workers].append(dict(seconds=elapsed, peakConcurrentRenders=peak,
                    distinctWorkerProcesses=len({r['pid'] for r in results})))
    serial = statistics.median(r['seconds'] for r in measurements[1])
    report = []
    result_digest = sha256(json.dumps(baseline, separators=(',', ':')).encode()).hexdigest()
    for workers, runs in measurements.items():
        median = statistics.median(r['seconds'] for r in runs)
        report.append(dict(workers=workers, tiles=len(jobs), runs=runs, medianSeconds=median,
                           speedupVsSerial=serial/median, renderedTilesPerHour=3600*len(jobs)/median,
                           outputHashesSHA256=result_digest, outputsIdentical=True,
                           independentHashPixelReadback=True,productionAccepted=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("manifest", "children", "source"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    print(json.dumps(benchmark(json.loads(args.manifest.read_text()), args.children, args.source), sort_keys=True))
