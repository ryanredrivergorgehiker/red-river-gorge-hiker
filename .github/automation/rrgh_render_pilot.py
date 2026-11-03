"""Compare serial and parallel pinned overview renders in private scratch."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import tempfile
from time import perf_counter

from rrgh_verified_overview import render


def render_job(task):
    region, item, child_root, destination, source_root = task
    result = render(region, item["job"], item["children"], child_root,
                    destination, source_root)
    return result["receipt"]["outputs"][0]["sha256"]


def benchmark(manifest, children, source):
    jobs = manifest["jobs"]
    targets = {tuple(item["job"][k] for k in ("layer", "z", "x", "y"))
               for item in jobs}
    if len(jobs) < 2 or len(targets) != len(jobs):
        raise ValueError("Provide at least two distinct target tiles")
    if any(tuple(child["tile"]) in targets for item in jobs for child in item["children"]):
        raise ValueError("Assignments must use pre-existing children")
    baseline = None
    for workers in (1, 2, 4):
        with tempfile.TemporaryDirectory(prefix="rrgh-render-") as directory:
            tasks = [(manifest["region"], item, children, Path(directory) / str(i), source)
                     for i, item in enumerate(jobs)]
            start = perf_counter()
            if workers == 1:
                hashes = list(map(render_job, tasks))
            else:
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    hashes = list(pool.map(render_job, tasks))
            elapsed = perf_counter() - start
            if baseline is None:
                baseline = hashes
            elif baseline != hashes:
                raise ValueError("Parallel render differs from serial baseline")
            print(json.dumps(dict(workers=workers, tiles=len(hashes), seconds=elapsed,
                                  rendered_tiles_per_hour=3600*len(hashes)/elapsed)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("manifest", "children", "source"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    benchmark(json.loads(args.manifest.read_text()), args.children, args.source)
