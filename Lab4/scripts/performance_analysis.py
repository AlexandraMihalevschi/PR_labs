"""
Performance analysis script for the key-value store.
It benchmarks write latency for quorum values 1..5, verifies replica integrity,
and generates a latency plot + JSON report.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

import httpx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


async def wait_for_services(max_retries: int = 30, delay: float = 0.5) -> None:
    """Wait until the leader and all followers respond."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        for _ in range(max_retries):
            try:
                leader_resp = await client.get(LEADER_URL)
                if leader_resp.status_code == 200:
                    followers_ready = True
                    for follower_url in FOLLOWER_URLS:
                        try:
                            resp = await client.get(follower_url)
                            if resp.status_code != 200:
                                followers_ready = False
                                break
                        except httpx.HTTPError:
                            followers_ready = False
                            break
                    if followers_ready:
                        return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)
    raise RuntimeError("Services did not become ready in time")


async def configure_write_quorum(quorum: int) -> None:
    """Update the leader write quorum using the runtime config endpoint."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.post(f"{LEADER_URL}/config/write_quorum", json={"write_quorum": quorum})
        resp.raise_for_status()


async def write_key(client: httpx.AsyncClient, key: str, value: str) -> Tuple[bool, float]:
    """Write a key and measure latency."""
    start_time = time.perf_counter()
    try:
        response = await client.post(f"{LEADER_URL}/set", json={"key": key, "value": value})
        latency = time.perf_counter() - start_time
        return response.status_code == 200, latency
    except httpx.HTTPError as exc:
        latency = time.perf_counter() - start_time
        print(f"Error writing {key}: {exc}")
        return False, latency


async def run_concurrent_writes(num_writes: int = 100, num_keys: int = 10, concurrency: int = 10) -> List[float]:
    """Run concurrent writes and return latencies."""
    latencies: List[float] = []
    keys = [f"perf_key_{i % num_keys}" for i in range(num_writes)]

    async with httpx.AsyncClient(timeout=30.0) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def write_with_semaphore(key: str, value: str):
            async with semaphore:
                success, latency = await write_key(client, key, value)
                if success:
                    latencies.append(latency)

        await asyncio.gather(
            *[write_with_semaphore(key, f"value_{i}_{time.time()}") for i, key in enumerate(keys)],
            return_exceptions=False,
        )

    return latencies


async def fetch_diagnostics(client: httpx.AsyncClient, url: str) -> Dict[str, str]:
    resp = await client.get(f"{url}/diagnostics")
    resp.raise_for_status()
    return resp.json()


async def verify_data_consistency() -> Dict[str, Dict[str, str]]:
    """Compare leader checksum with each follower checksum."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        leader_diag = await fetch_diagnostics(client, LEADER_URL)
        follower_diags = {url: await fetch_diagnostics(client, url) for url in FOLLOWER_URLS}

    inconsistencies = {}
    for url, diag in follower_diags.items():
        inconsistencies[url] = {
            "checksum_match": diag["checksum"] == leader_diag["checksum"],
            "follower_checksum": diag["checksum"],
            "leader_checksum": leader_diag["checksum"],
            "follower_keys": diag["keys"],
            "leader_keys": leader_diag["keys"],
        }
    return {"leader": leader_diag, "followers": inconsistencies}


async def test_write_quorum_performance():
    """Benchmark quorum values 1..5 with 100 writes (10 concurrent, 10 keys)."""
    quorum_values = [1, 2, 3, 4, 5]
    num_writes = 100
    num_keys = 10
    concurrency = 10
    results: Dict[int, Dict[str, float]] = {}

    print("=" * 60)
    print("Performance Analysis: Write Quorum vs Average Latency")
    print("=" * 60)
    print(f"Writes per run: {num_writes}, Keys: {num_keys}, Concurrency: {concurrency}")

    await wait_for_services()

    for quorum in quorum_values:
        await configure_write_quorum(quorum)
        print(f"\nRunning benchmark with WRITE_QUORUM={quorum} ...")

        start_time = time.perf_counter()
        latencies = await run_concurrent_writes(num_writes, num_keys, concurrency)
        total_time = time.perf_counter() - start_time

        if not latencies:
            print("No successful writes recorded!")
            continue

        avg_latency = float(np.mean(latencies))
        median_latency = float(np.median(latencies))
        p95_latency = float(np.percentile(latencies, 95))
        p99_latency = float(np.percentile(latencies, 99))
        success_rate = len(latencies) / num_writes

        results[quorum] = {
            "avg_latency": avg_latency,
            "median_latency": median_latency,
            "p95_latency": p95_latency,
            "p99_latency": p99_latency,
            "total_time": total_time,
            "success_rate": success_rate,
            "num_successful": len(latencies),
        }

        print(f"  Average latency: {avg_latency * 1000:.2f} ms")
        print(f"  Median latency: {median_latency * 1000:.2f} ms")
        print(f"  P95 latency: {p95_latency * 1000:.2f} ms")
        print(f"  P99 latency: {p99_latency * 1000:.2f} ms")
        print(f"  Success rate: {success_rate * 100:.1f}%")
        print(f"  Total runtime: {total_time:.2f} s")

    if not results:
        print("No results captured; aborting.")
        return

    quorums = sorted(results.keys())
    avg_latencies_ms = [results[q]["avg_latency"] * 1000 for q in quorums]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(quorums, avg_latencies_ms, marker="o", linewidth=2, markersize=8)
    ax.set_xlabel("Write Quorum")
    ax.set_ylabel("Average Latency (ms)")
    ax.set_title("Write Quorum vs Average Latency\n(100 writes, 10 keys, 10 concurrent)")
    ax.grid(alpha=0.3)
    ax.set_xticks(quorums)

    for q, latency in zip(quorums, avg_latencies_ms):
        ax.text(q, latency, f"{latency:.1f} ms", ha="center", va="bottom", fontsize=9)

    plot_path = RESULTS_DIR / "write_quorum_vs_latency.png"
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"\nLatency plot saved to {plot_path}")

    print("\nVerifying replica checksums...")
    consistency_report = await verify_data_consistency()
    all_consistent = all(info["checksum_match"] for info in consistency_report["followers"].values())
    if all_consistent:
        print("Replica data integrity: OK (all checksums match)")
    else:
        print("Replica data integrity: ALERT (checksum mismatch detected)")

    explanation = (
        "Higher write quorums require more follower confirmations before the leader "
        "can acknowledge a write, so average latency increases roughly linearly with "
        "the quorum size. Lower quorums return faster but tolerate fewer replica failures."
    )

    report = {
        "results": results,
        "consistency_report": consistency_report,
        "explanation": explanation,
        "parameters": {
            "num_writes": num_writes,
            "num_keys": num_keys,
            "concurrency": concurrency,
        },
    }

    json_path = RESULTS_DIR / "performance_results.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"Results saved to {json_path}")
    print(f"\nExplanation: {explanation}")


if __name__ == "__main__":
    asyncio.run(test_write_quorum_performance())
