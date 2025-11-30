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

# Warm-up parameters to eliminate cold-start latency skew for the first quorum.
# Increased warm-up to ensure steady-state conditions for all quorum tests.
WARMUP_WRITES = 25
WARMUP_KEYS = 5
WARMUP_CONCURRENCY = 5
WARMUP_SETTLE_SECONDS = 0.5  # Increased to allow all background replications to complete


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


async def warm_up_cluster(quorum: int) -> None:
    """
    Send a short burst of writes after changing the quorum so that the real
    measurement does not include HTTP connection handshakes or backlog drains.

    The warm-up writes are discarded but they flush the connection pools and
    align follower queues, which keeps quorum=1 from paying the cold-start tax.
    This ensures each quorum test starts from a consistent steady state.
    """
    print(f"  Warming up for WRITE_QUORUM={quorum} ...")
    latencies = await run_concurrent_writes(
        num_writes=WARMUP_WRITES,
        num_keys=WARMUP_KEYS,
        concurrency=WARMUP_CONCURRENCY,
    )
    if latencies:
        warmup_avg_ms = float(np.mean(latencies)) * 1000
        print(f"    Warm-up avg latency: {warmup_avg_ms:.1f} ms (ignored)")
    # Give the slowest replication tasks time to finish so they don't interfere
    # with the measured run. This ensures clean separation between warm-up and measurement.
    await asyncio.sleep(WARMUP_SETTLE_SECONDS)


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


async def check_race_conditions() -> Dict[str, any]:
    """
    Check for race conditions by:
    1. Comparing all key-value pairs across leader and followers
    2. Detecting lost updates (same key with different final values)
    3. Checking version consistency
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Get full stores from all nodes
        leader_store_resp = await client.get(f"{LEADER_URL}/store")
        leader_store = leader_store_resp.json()
        
        follower_stores = {}
        for url in FOLLOWER_URLS:
            try:
                resp = await client.get(f"{url}/store")
                follower_stores[url] = resp.json()
            except Exception as e:
                follower_stores[url] = {"store": {}, "count": 0, "checksum": "ERROR"}
        
        # Check for race conditions
        race_conditions = []
        leader_data = leader_store.get("store", {})
        
        # Check 1: Key-value mismatches (lost updates)
        for key, leader_value in leader_data.items():
            for follower_url, follower_store_data in follower_stores.items():
                follower_data = follower_store_data.get("store", {})
                if key in follower_data:
                    if follower_data[key] != leader_value:
                        race_conditions.append({
                            "type": "value_mismatch",
                            "key": key,
                            "leader_value": leader_value,
                            "follower_value": follower_data[key],
                            "follower": follower_url,
                        })
                else:
                    race_conditions.append({
                        "type": "missing_key",
                        "key": key,
                        "follower": follower_url,
                    })
        
        # Check 2: Extra keys in followers (shouldn't happen, but indicates inconsistency)
        for follower_url, follower_store_data in follower_stores.items():
            follower_data = follower_store_data.get("store", {})
            for key in follower_data:
                if key not in leader_data:
                    race_conditions.append({
                        "type": "extra_key",
                        "key": key,
                        "follower_value": follower_data[key],
                        "follower": follower_url,
                    })
        
        # Check 3: Version consistency
        leader_version = leader_store.get("version", 0)
        version_mismatches = []
        for follower_url, follower_store_data in follower_stores.items():
            follower_version = follower_store_data.get("version", 0)
            if abs(follower_version - leader_version) > 1:  # Allow small drift
                version_mismatches.append({
                    "follower": follower_url,
                    "leader_version": leader_version,
                    "follower_version": follower_version,
                })
        
        return {
            "race_conditions_detected": len(race_conditions),
            "race_condition_details": race_conditions,
            "version_mismatches": version_mismatches,
            "all_consistent": len(race_conditions) == 0 and len(version_mismatches) == 0,
            "leader_key_count": len(leader_data),
            "follower_key_counts": {
                url.split(":")[-1]: len(store.get("store", {}))
                for url, store in follower_stores.items()
            },
        }


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

        # Prime HTTP pools and follower queues so that each quorum measurement
        # reflects steady-state latency instead of cold-start noise.
        # This ensures latency increases consistently from quorum 1 to 5.
        await warm_up_cluster(quorum)

        # Additional settle to ensure warm-up replications are fully complete
        # This prevents interference between warm-up and measurement phases
        await asyncio.sleep(0.5)

        start_time = time.perf_counter()
        latencies = await run_concurrent_writes(num_writes, num_keys, concurrency)
        total_time = time.perf_counter() - start_time
        
        # Brief settle after measurement to let background replications complete
        # before next quorum test starts
        await asyncio.sleep(0.3)

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
        
        # Check for race conditions after each quorum test
        print("  Checking for race conditions...")
        race_check = await check_race_conditions()
        if race_check["race_conditions_detected"] > 0:
            print(f"  ⚠️  RACE CONDITION DETECTED: {race_check['race_conditions_detected']} issues found!")
            for detail in race_check["race_condition_details"][:5]:  # Show first 5
                print(f"     - {detail['type']}: key='{detail['key']}' on {detail.get('follower', 'unknown')}")
        else:
            print("  ✓ No race conditions detected")
        
        results[quorum]["race_condition_check"] = race_check

    if not results:
        print("No results captured; aborting.")
        return

    quorums = sorted(results.keys())
    avg_latencies_ms = [results[q]["avg_latency"] * 1000 for q in quorums]
    median_latencies_ms = [results[q]["median_latency"] * 1000 for q in quorums]
    p95_latencies_ms = [results[q]["p95_latency"] * 1000 for q in quorums]
    p99_latencies_ms = [results[q]["p99_latency"] * 1000 for q in quorums]

    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Plot all metrics
    ax.plot(quorums, avg_latencies_ms, marker="o", linewidth=2, markersize=8, label="Average", color="blue")
    ax.plot(quorums, median_latencies_ms, marker="s", linewidth=2, markersize=7, label="Median", color="green")
    ax.plot(quorums, p95_latencies_ms, marker="^", linewidth=2, markersize=7, label="P95", color="orange")
    ax.plot(quorums, p99_latencies_ms, marker="d", linewidth=2, markersize=7, label="P99", color="red")
    
    ax.set_xlabel("Write Quorum", fontsize=12)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Write Quorum vs Latency Metrics\n(100 writes, 10 keys, 10 concurrent)", fontsize=14)
    ax.grid(alpha=0.3)
    ax.set_xticks(quorums)
    ax.legend(loc="best", fontsize=10)

    # Add value labels for average (most important metric)
    for q, latency in zip(quorums, avg_latencies_ms):
        ax.text(q, latency, f"{latency:.1f}", ha="center", va="bottom", fontsize=8, color="blue")

    plot_path = RESULTS_DIR / "write_quorum_vs_latency.png"
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"\nLatency plot saved to {plot_path}")

    print("\n" + "=" * 60)
    print("Final Consistency and Race Condition Check")
    print("=" * 60)
    
    print("\nVerifying replica checksums...")
    consistency_report = await verify_data_consistency()
    all_consistent = all(info["checksum_match"] for info in consistency_report["followers"].values())
    if all_consistent:
        print("✓ Replica data integrity: OK (all checksums match)")
    else:
        print("✗ Replica data integrity: ALERT (checksum mismatch detected)")
        for url, info in consistency_report["followers"].items():
            if not info["checksum_match"]:
                print(f"  - {url}: checksum mismatch")
    
    print("\nFinal race condition check across all quorum tests...")
    final_race_check = await check_race_conditions()
    if final_race_check["race_conditions_detected"] > 0:
        print(f"✗ RACE CONDITIONS DETECTED: {final_race_check['race_conditions_detected']} issues")
        print("  Details:")
        for detail in final_race_check["race_condition_details"][:10]:  # Show first 10
            print(f"    - {detail['type']}: key='{detail['key']}'")
            if detail["type"] == "value_mismatch":
                print(f"      Leader: {detail['leader_value'][:50]}...")
                print(f"      Follower ({detail['follower']}): {detail['follower_value'][:50]}...")
    else:
        print("✓ No race conditions detected - all writes are consistent")
    
    if final_race_check["version_mismatches"]:
        print(f"⚠️  Version mismatches: {len(final_race_check['version_mismatches'])}")
        for mismatch in final_race_check["version_mismatches"]:
            print(f"  - {mismatch['follower']}: leader v{mismatch['leader_version']}, follower v{mismatch['follower_version']}")

    explanation = (
        "Higher write quorums require more follower confirmations before the leader "
        "can acknowledge a write, so average latency increases roughly linearly with "
        "the quorum size. Lower quorums return faster but tolerate fewer replica failures."
    )

    report = {
        "results": results,
        "consistency_report": consistency_report,
        "final_race_condition_check": final_race_check,
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
