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
from typing import Dict, List, Tuple

import httpx

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


async def wait_for_services(max_retries: int = 60, delay: float = 0.5) -> None:
    """Wait for all services to be ready, with better error reporting."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        for attempt in range(max_retries):
            try:
                # Check leader
                try:
                    leader_resp = await client.get(LEADER_URL)
                    leader_ready = leader_resp.status_code == 200
                except Exception as e:
                    leader_ready = False
                    if attempt % 10 == 0:  # Print every 5 seconds
                        print(f"Waiting for leader... (attempt {attempt + 1}/{max_retries})")
                
                # Check followers
                follower_statuses = await asyncio.gather(
                    *[client.get(url) for url in FOLLOWER_URLS],
                    return_exceptions=True,
                )
                
                ready_count = sum(
                    1 for resp in follower_statuses
                    if isinstance(resp, httpx.Response) and resp.status_code == 200
                )
                
                if leader_ready and ready_count == len(FOLLOWER_URLS):
                    print("All services are ready!")
                    return
                
                if attempt % 10 == 0:  # Print every 5 seconds
                    print(f"Waiting for services... Leader: {leader_ready}, Followers: {ready_count}/{len(FOLLOWER_URLS)} (attempt {attempt + 1}/{max_retries})")
                    
            except Exception as e:
                if attempt % 10 == 0:
                    print(f"Error checking services: {e}")
            
            await asyncio.sleep(delay)
    
    # Final check with detailed error
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            leader_resp = await client.get(LEADER_URL)
            print(f"Leader status: {leader_resp.status_code}")
        except Exception as e:
            print(f"Leader unreachable: {e}")
        
        for url in FOLLOWER_URLS:
            try:
                resp = await client.get(url)
                print(f"{url}: {resp.status_code}")
            except Exception as e:
                print(f"{url}: unreachable - {e}")
    
    raise RuntimeError(f"Services did not become ready after {max_retries * delay} seconds. Check docker compose logs.")


async def configure_write_quorum(quorum: int) -> None:
    """Configure write quorum via the runtime API."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(
                f"{LEADER_URL}/config/write_quorum",
                json={"write_quorum": quorum},
            )
            resp.raise_for_status()
            print(f"Write quorum configured to {quorum}")
        except Exception as e:
            print(f"Warning: Failed to configure quorum via API: {e}")
            print("Continuing with default quorum from environment...")


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


async def check_race_conditions() -> Dict[str, any]:
    """
    Check for race conditions by comparing all key-value pairs across leader and followers.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        leader_store_resp = await client.get(f"{LEADER_URL}/store")
        leader_store = leader_store_resp.json()
        
        follower_stores = {}
        for url in FOLLOWER_URLS:
            try:
                resp = await client.get(f"{url}/store")
                follower_stores[url] = resp.json()
            except Exception:
                follower_stores[url] = {"store": {}, "count": 0, "checksum": "ERROR"}
        
        race_conditions = []
        leader_data = leader_store.get("store", {})
        
        # Check for value mismatches (lost updates)
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
        
        # Check for extra keys in followers
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
        
        return {
            "race_conditions_detected": len(race_conditions),
            "race_condition_details": race_conditions,
            "all_consistent": len(race_conditions) == 0,
        }


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

    # Calculate statistics without numpy
    sorted_latencies = sorted(latencies)
    avg_latency = sum(latencies) / len(latencies)
    median_latency = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0.0
    if len(sorted_latencies) > 1 and len(sorted_latencies) % 2 == 0:
        median_latency = (sorted_latencies[len(sorted_latencies) // 2 - 1] + median_latency) / 2
    
    def percentile(data: List[float], p: float) -> float:
        """Calculate percentile without numpy."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * p / 100
        f = int(k)
        c = k - f
        if f + 1 < len(sorted_data):
            return sorted_data[f] * (1 - c) + sorted_data[f + 1] * c
        return sorted_data[f]
    
    p95_latency = percentile(latencies, 95)
    p99_latency = percentile(latencies, 99)
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
    
    print("\nChecking for race conditions...")
    race_check = await check_race_conditions()
    if race_check["race_conditions_detected"] > 0:
        print(f"⚠️  RACE CONDITION DETECTED: {race_check['race_conditions_detected']} issues found!")
        for detail in race_check["race_condition_details"][:5]:  # Show first 5
            print(f"  - {detail['type']}: key='{detail['key']}' on {detail.get('follower', 'unknown')}")
        if detail["type"] == "value_mismatch":
            print(f"    Leader value: {detail['leader_value'][:60]}...")
            print(f"    Follower value: {detail['follower_value'][:60]}...")
    else:
        print("✓ No race conditions detected")

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
        "race_condition_check": race_check,
    }

    filename = RESULTS_DIR / f"results_quorum_{quorum}.json"
    with open(filename, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nResults saved to {filename}")


if __name__ == "__main__":
    asyncio.run(main())
