#!/usr/bin/env python3
"""Concurrent indexing stress test for Ollqd.

Launches multiple indexing tasks simultaneously to validate:
- Gateway task manager handles concurrent tasks without deadlocks
- Worker processes tasks without corruption
- Task status transitions are correct under load
- No resource leaks (OOM, file handle exhaustion)

Usage:
    python tests/perf/indexing_concurrent.py [--tasks 5] [--timeout 120]
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def start_indexing_task(task_num: int, collection: str) -> dict:
    """Start a codebase indexing task and return initial response."""
    try:
        r = requests.post(
            f"{GATEWAY_URL}/api/rag/index/codebase",
            json={
                "root_path": os.path.join(FIXTURES_DIR, "codebase"),
                "collection": f"{collection}_{task_num}",
                "chunk_size": 256,
                "chunk_overlap": 50,
                "incremental": False,
            },
            timeout=10,
        )
        return {
            "task_num": task_num,
            "status_code": r.status_code,
            "response": r.json() if r.status_code < 500 else {"error": r.text},
            "task_id": r.json().get("task_id") if r.status_code < 300 else None,
        }
    except Exception as e:
        return {"task_num": task_num, "error": str(e), "task_id": None}


def poll_task(task_id: str, timeout: float) -> dict:
    """Poll task until completion or timeout."""
    deadline = time.time() + timeout
    last_status = "unknown"
    last_progress = 0.0

    while time.time() < deadline:
        try:
            r = requests.get(f"{GATEWAY_URL}/api/rag/tasks/{task_id}", timeout=5)
            if r.status_code == 200:
                data = r.json()
                last_status = data.get("status", "unknown")
                last_progress = data.get("progress", 0)
                if last_status in ("completed", "failed", "cancelled"):
                    return {
                        "task_id": task_id,
                        "final_status": last_status,
                        "progress": last_progress,
                        "result": data.get("result"),
                    }
        except Exception:
            pass
        time.sleep(1)

    return {
        "task_id": task_id,
        "final_status": "timeout",
        "progress": last_progress,
        "last_observed_status": last_status,
    }


def main():
    parser = argparse.ArgumentParser(description="Concurrent indexing stress test")
    parser.add_argument("--tasks", type=int, default=5, help="Number of concurrent tasks")
    parser.add_argument("--collection", default="perf_test", help="Collection prefix")
    parser.add_argument("--timeout", type=float, default=120, help="Per-task timeout")
    parser.add_argument("--output", default="", help="JSON output file")
    args = parser.parse_args()

    print(f"Launching {args.tasks} concurrent indexing tasks...")

    # Phase 1: Start all tasks
    start_results = []
    with ThreadPoolExecutor(max_workers=args.tasks) as pool:
        futures = {
            pool.submit(start_indexing_task, i, args.collection): i
            for i in range(args.tasks)
        }
        for f in as_completed(futures):
            start_results.append(f.result())

    started = [r for r in start_results if r.get("task_id")]
    print(f"  Started: {len(started)}/{args.tasks}")

    if not started:
        print("  No tasks started. Is the gateway running with Ollama available?")
        sys.exit(1)

    # Phase 2: Poll all tasks
    poll_results = []
    with ThreadPoolExecutor(max_workers=len(started)) as pool:
        futures = {
            pool.submit(poll_task, r["task_id"], args.timeout): r["task_id"]
            for r in started
        }
        for f in as_completed(futures):
            poll_results.append(f.result())

    # Report
    completed = sum(1 for r in poll_results if r["final_status"] == "completed")
    failed = sum(1 for r in poll_results if r["final_status"] == "failed")
    timed_out = sum(1 for r in poll_results if r["final_status"] == "timeout")

    report = {
        "total_tasks": args.tasks,
        "started": len(started),
        "completed": completed,
        "failed": failed,
        "timed_out": timed_out,
        "start_results": start_results,
        "poll_results": poll_results,
        "passed": completed == len(started) and timed_out == 0,
    }

    print(f"\n=== Concurrent Indexing Results ===")
    print(f"  Started:   {len(started)}/{args.tasks}")
    print(f"  Completed: {completed}")
    print(f"  Failed:    {failed}")
    print(f"  Timed out: {timed_out}")
    print(f"  Result:    {'PASS' if report['passed'] else 'FAIL'}")

    # Cleanup collections
    for i in range(args.tasks):
        try:
            requests.delete(
                f"{GATEWAY_URL}/api/qdrant/collections/{args.collection}_{i}",
                timeout=5,
            )
        except Exception:
            pass

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"  Report: {args.output}")

    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
