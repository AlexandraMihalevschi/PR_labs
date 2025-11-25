"""
Test performance for a single write quorum value.
Usage: python tests/test_single_quorum.py <quorum_value>
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import List, Tuple

import httpx
import numpy as np

LEADER_URL = "http://localhost:8000"
FOLLOWER_URLS = [
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003",
    "http://localhost:8004",
    "http://localhost:8005",
]
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
RESULTS_DIR.mkdir(exist_ok=True)


async def wait_for_services(max_retries: int = 30, delay: float = 0.5) -> None:
    async with httpx.AsyncClient(timeout=2.0) as client:
        for _ in range(max_retries):
            try:
                leader_ready = (await client.get(LEADER_URL)).status_code == 200
                follower_statuses = await asyncio.gather(
                    *[client.get(url) for url in FOLLOWER_URLS],
                    return_exceptions=True,
                )
                followers_ready = all(
                    isinstance(resp, httpx.Response) and resp.status_code == 200
                    for resp in follower_statuses
                )
                if leader_ready and followers_ready:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)
    raise RuntimeError("Services did not become ready in time")


async def configure_write_quorum(quorum: int) -> None:
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.post(f"{LEADER_URL}/config/write_quorum", json={"write_quorum": quorum})
        resp.raise_for_status()


async def write_key(client: httpx.AsyncClient, key: str, value: str) -> Tuple[bool, float]:
    start_time = time.perf_counter()
    try:
        response = await client.post(f"{LEADER_URL}/set", json={"key": key, "value": value})
        latency = time.perf_counter() - start_time
        return response.status_code == 200, latency
    except httpx.HTTPError:
        latency = time.perf_counter() - start_time
        return False, latency


async def run_concurrent_writes(num_writes: int = 100, num_keys: int = 10, concurrency: int = 10) -> List[float]:
    latencies: List[float] = []
    keys = [f"perf_key_{i % num_keys}" for i in range(num_writes)]

    async with httpx.AsyncClient(timeout=30.0) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def write_with_limit(key: str, value: str):
            async with semaphore:
                success, latency = await write_key(client, key, value)
                if success:
                    latencies.append(latency)

        await asyncio.gather(
            *[write_with_limit(key, f"value_{i}_{time.time()}") for i, key in enumerate(keys)],
            return_exceptions=False,
        )

    return latencies


async def verify_data_consistency():
    async with httpx.AsyncClient(timeout=5.0) as client:
        leader_store = (await client.get(f"{LEADER_URL}/store")).json()
        follower_checksums = {}
        for follower_url in FOLLOWER_URLS:
            resp = await client.get(f"{follower_url}/store")
            follower_checksums[follower_url] = resp.json()

    all_consistent = all(
        store["checksum"] == leader_store["checksum"] and store["count"] == leader_store["count"]
        for store in follower_checksums.values()
    )

    return {
        "all_consistent": all_consistent,
        "leader_keys": leader_store["count"],
        "follower_keys": {
            url.split(":")[-1]: store["count"] for url, store in follower_checksums.items()
        },
    }


async def main():
    if len(sys.argv) < 2:
        print("Usage: python tests/test_single_quorum.py <quorum_value>")
        sys.exit(1)

    quorum = int(sys.argv[1])
    num_writes = 100
    num_keys = 10
    concurrency = 10

    print(f"Testing with WRITE_QUORUM={quorum}")
    print(f"Total writes: {num_writes}, Keys: {num_keys}, Concurrency: {concurrency}")

    await wait_for_services()
    await configure_write_quorum(quorum)

    print("Running concurrent writes...")
    start_time = time.perf_counter()
    latencies = await run_concurrent_writes(num_writes, num_keys, concurrency)
    total_time = time.perf_counter() - start_time

    if not latencies:
        print("No successful writes captured!")
        return

    avg_latency = np.mean(latencies)
    median_latency = np.median(latencies)
    p95_latency = np.percentile(latencies, 95)
    p99_latency = np.percentile(latencies, 99)
    success_rate = len(latencies) / num_writes

    print(f"\nResults for WRITE_QUORUM={quorum}:")
    print(f"  Average latency: {avg_latency * 1000:.2f} ms")
    print(f"  Median latency: {median_latency * 1000:.2f} ms")
    print(f"  P95 latency: {p95_latency * 1000:.2f} ms")
    print(f"  P99 latency: {p99_latency * 1000:.2f} ms")
    print(f"  Success rate: {success_rate * 100:.2f}%")
    print(f"  Total time: {total_time:.2f} seconds")
    print(f"  Successful writes: {len(latencies)}/{num_writes}")

    print("\nVerifying data consistency...")
    consistency = await verify_data_consistency()
    print(f"Leader has {consistency['leader_keys']} keys")
    for follower_id, key_count in consistency["follower_keys"].items():
        print(f"Follower {follower_id} has {key_count} keys")
    print("Consistency:", "OK" if consistency["all_consistent"] else "CHECK")

    results = {
        "quorum": quorum,
        "avg_latency_ms": avg_latency * 1000,
        "median_latency_ms": median_latency * 1000,
        "p95_latency_ms": p95_latency * 1000,
        "p99_latency_ms": p99_latency * 1000,
        "success_rate": success_rate,
        "total_time": total_time,
        "num_successful": len(latencies),
        "consistency": consistency,
    }

    filename = RESULTS_DIR / f"results_quorum_{quorum}.json"
    with open(filename, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nResults saved to {filename}")


if __name__ == "__main__":
    asyncio.run(main())
