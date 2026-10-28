#!/usr/bin/env python3
"""Bounded one-job processes for the resumable Gorge benchmark.

Native raster libraries are isolated per job. One interrupted native process
may be retried once; a normal validation failure stops. The persistent source
ledger and committed output hashes remain authoritative across child exits.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from benchmark_gorge_pipeline import run, json_bytes
from cached_cog_source import atomic


def pending(plan, root):
    jobs = []
    for sample in plan["samples"]:
        for role in ("hiking", "terrain-sunlight", "leaf-off", "leaf-on"):
            source = "dem" if role == "terrain-sunlight" else role
            key = f"{sample['id']}-{role}"
            if plan["sources"].get(source) and not (root / "receipts" / (key + ".json")).exists():
                jobs.append(key)
    return jobs


def orchestrate(plan_path, root, cache, limit=8, byte_limit=250_000_000, child_timeout=300):
    if not 0 <= limit <= 12 or not 30 <= child_timeout <= 600:
        raise ValueError("Bounded job/time limits required")
    plan = json.loads(Path(plan_path).read_text())
    root = Path(root)
    # Rehash committed receipts before any further original transfers.
    run(plan, root, cache, max_jobs=0, byte_limit=byte_limit)
    attempts = []
    for job in pending(plan, root)[:limit]:
        for attempt in (1, 2):
            log = root / "process-logs" / f"{job}-{time.time_ns()}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            env = {**os.environ, "GDAL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
            command = [sys.executable, str(Path(__file__).with_name("benchmark_gorge_pipeline.py")),
                       "--plan", str(plan_path), "--output", str(root), "--cache", str(cache),
                       "--max-jobs", "1", "--max-source-bytes", str(byte_limit), "--live-source-benchmark"]
            start = time.perf_counter()
            try:
                with log.open("wb") as stream:
                    result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                            timeout=child_timeout, env=env, check=False)
                status = result.returncode
            except subprocess.TimeoutExpired:
                status = "timeout"
            attempts.append({"job": job, "attempt": attempt, "exit": status,
                             "elapsedSeconds": time.perf_counter() - start,
                             "log": str(log.relative_to(root))})
            atomic(root / "PROCESS-ATTEMPTS.json", json_bytes(attempts))
            receipt = root / "receipts" / (job + ".json")
            if receipt.exists():
                run(plan, root, cache, max_jobs=0, byte_limit=byte_limit)
                break
            if status in (0, 2) or attempt == 2:
                raise RuntimeError(f"Benchmark job {job} stopped; see its private process log. No production action occurred.")
    report = run(plan, root, cache, max_jobs=0, byte_limit=byte_limit)
    return {"validatedJobs": len(report["receipts"]), "remainingJobs": pending(plan, root),
            "sourceLedger": report["after"], "attempts": attempts}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--max-jobs", type=int, default=8)
    p.add_argument("--max-source-bytes", type=int, default=250_000_000)
    p.add_argument("--child-timeout", type=int, default=300)
    p.add_argument("--live-source-benchmark", action="store_true")
    a = p.parse_args()
    if not a.live_source_benchmark and a.max_jobs:
        p.error("Explicit --live-source-benchmark required for source processing")
    print(json.dumps(orchestrate(a.plan, a.output, a.cache, a.max_jobs, a.max_source_bytes, a.child_timeout), indent=2))
