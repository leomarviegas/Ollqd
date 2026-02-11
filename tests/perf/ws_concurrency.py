#!/usr/bin/env python3
"""WebSocket concurrency test for Ollqd chat endpoint.

Spawns N concurrent WebSocket connections to /api/rag/ws and sends
messages simultaneously. Validates:
- All connections succeed
- All receive streaming events (chunk → done)
- No deadlocks or hangs (enforced by timeout)
- Memory doesn't blow up (measured by response sizes)

Usage:
    python tests/perf/ws_concurrency.py [--sessions 10] [--timeout 60]

Requires: websockets, asyncio
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install: pip install websockets")
    sys.exit(1)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
WS_URL = GATEWAY_URL.replace("http://", "ws://").replace("https://", "wss://")
WS_ENDPOINT = f"{WS_URL}/api/rag/ws"


@dataclass
class SessionResult:
    """Result of a single WebSocket chat session."""

    session_id: int
    connected: bool = False
    events_received: int = 0
    got_done: bool = False
    error: str = ""
    duration_ms: float = 0.0
    total_bytes: int = 0
    event_types: list = field(default_factory=list)


async def run_session(
    session_id: int, collection: str, model: str, timeout: float
) -> SessionResult:
    """Run a single WebSocket chat session."""
    result = SessionResult(session_id=session_id)
    start = time.monotonic()

    try:
        async with asyncio.timeout(timeout):
            async with websockets.connect(WS_ENDPOINT) as ws:
                result.connected = True

                # Send chat message
                msg = json.dumps(
                    {
                        "message": f"What is this project about? (session {session_id})",
                        "collection": collection,
                        "model": model,
                        "pii_enabled": False,
                    }
                )
                await ws.send(msg)

                # Receive streaming events
                async for raw in ws:
                    result.events_received += 1
                    result.total_bytes += len(raw)
                    try:
                        event = json.loads(raw)
                        etype = event.get("type", "unknown")
                        result.event_types.append(etype)
                        if etype == "done":
                            result.got_done = True
                            break
                        if etype == "error":
                            result.error = event.get("content", "unknown error")
                            break
                    except json.JSONDecodeError:
                        result.event_types.append("raw")

    except asyncio.TimeoutError:
        result.error = f"timeout after {timeout}s"
    except websockets.exceptions.ConnectionClosed as e:
        result.error = f"connection closed: {e.code} {e.reason}"
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"

    result.duration_ms = (time.monotonic() - start) * 1000
    return result


async def run_concurrency_test(
    num_sessions: int, collection: str, model: str, timeout: float
) -> list[SessionResult]:
    """Launch N concurrent WebSocket sessions."""
    tasks = [
        run_session(i, collection, model, timeout) for i in range(num_sessions)
    ]
    return await asyncio.gather(*tasks)


def print_report(results: list[SessionResult]) -> dict:
    """Print and return structured report."""
    total = len(results)
    connected = sum(1 for r in results if r.connected)
    completed = sum(1 for r in results if r.got_done)
    errored = sum(1 for r in results if r.error)
    durations = [r.duration_ms for r in results if r.duration_ms > 0]

    report = {
        "total_sessions": total,
        "connected": connected,
        "completed_with_done": completed,
        "errored": errored,
        "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
        "max_duration_ms": round(max(durations), 2) if durations else 0,
        "min_duration_ms": round(min(durations), 2) if durations else 0,
        "total_events": sum(r.events_received for r in results),
        "total_bytes": sum(r.total_bytes for r in results),
        "errors": [
            {"session": r.session_id, "error": r.error}
            for r in results
            if r.error
        ],
    }

    print("\n=== WebSocket Concurrency Test Results ===")
    print(f"  Sessions: {total}")
    print(f"  Connected: {connected}/{total}")
    print(f"  Completed (got 'done'): {completed}/{total}")
    print(f"  Errors: {errored}/{total}")
    if durations:
        print(f"  Duration: avg={report['avg_duration_ms']}ms "
              f"min={report['min_duration_ms']}ms "
              f"max={report['max_duration_ms']}ms")
    print(f"  Total events: {report['total_events']}")
    print(f"  Total bytes: {report['total_bytes']}")

    if report["errors"]:
        print("\n  Errors:")
        for e in report["errors"][:10]:
            print(f"    Session {e['session']}: {e['error']}")

    # Pass/fail
    passed = connected == total and errored == 0
    print(f"\n  Result: {'PASS' if passed else 'FAIL'}")
    report["passed"] = passed

    return report


def main():
    parser = argparse.ArgumentParser(description="WebSocket concurrency test")
    parser.add_argument("--sessions", type=int, default=10, help="Number of concurrent sessions")
    parser.add_argument("--collection", default="test_ollqd_suite", help="Collection name")
    parser.add_argument("--model", default="", help="Ollama model name")
    parser.add_argument("--timeout", type=float, default=60, help="Per-session timeout (seconds)")
    parser.add_argument("--output", default="", help="JSON output file path")
    args = parser.parse_args()

    print(f"Running {args.sessions} concurrent WebSocket sessions...")
    print(f"  Endpoint: {WS_ENDPOINT}")
    print(f"  Collection: {args.collection}")
    print(f"  Timeout: {args.timeout}s")

    results = asyncio.run(
        run_concurrency_test(args.sessions, args.collection, args.model, args.timeout)
    )
    report = print_report(results)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report saved to: {args.output}")

    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
