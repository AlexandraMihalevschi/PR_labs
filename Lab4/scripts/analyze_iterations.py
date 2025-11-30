"""
Analyze and compare plots from result_iterations folder to identify discrepancies.
"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
ITERATIONS_DIR = Path(__file__).resolve().parents[1] / "result_iterations"


def analyze_iterations():
    """Compare results across iterations to identify patterns and discrepancies."""
    
    print("=" * 60)
    print("Analyzing Result Iterations")
    print("=" * 60)
    
    # Check if iterations directory exists
    if not ITERATIONS_DIR.exists():
        print(f"Error: {ITERATIONS_DIR} does not exist")
        return
    
    # List all iteration files
    iteration_files = sorted(ITERATIONS_DIR.glob("*.png"))
    print(f"\nFound {len(iteration_files)} iteration plots:")
    for f in iteration_files:
        print(f"  - {f.name}")
    
    # Check current results
    print(f"\nCurrent results in {RESULTS_DIR}:")
    result_files = sorted(RESULTS_DIR.glob("results_quorum_*.json"))
    
    if not result_files:
        print("  No result JSON files found")
        return
    
    # Load and compare current results
    current_results = {}
    for filename in result_files:
        try:
            with open(filename, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                quorum = data["quorum"]
                current_results[quorum] = {
                    "avg_latency_ms": data.get("avg_latency_ms", 0),
                    "median_latency_ms": data.get("median_latency_ms", 0),
                    "p95_latency_ms": data.get("p95_latency_ms", 0),
                    "p99_latency_ms": data.get("p99_latency_ms", 0),
                }
        except Exception as exc:
            print(f"  Error loading {filename}: {exc}")
    
    print("\nCurrent Results Summary:")
    print("-" * 60)
    for quorum in sorted(current_results.keys()):
        r = current_results[quorum]
        print(
            f"Quorum {quorum}: "
            f"avg={r['avg_latency_ms']:.2f}ms, "
            f"median={r['median_latency_ms']:.2f}ms, "
            f"p95={r['p95_latency_ms']:.2f}ms, "
            f"p99={r['p99_latency_ms']:.2f}ms"
        )
    
    # Check if latency increases with quorum
    print("\n" + "=" * 60)
    print("Latency Progression Analysis")
    print("=" * 60)
    
    quorums = sorted(current_results.keys())
    avg_latencies = [current_results[q]["avg_latency_ms"] for q in quorums]
    
    print(f"\nAverage Latencies by Quorum:")
    for q, lat in zip(quorums, avg_latencies):
        print(f"  Quorum {q}: {lat:.2f} ms")
    
    # Check if monotonic
    is_increasing = all(avg_latencies[i] <= avg_latencies[i+1] for i in range(len(avg_latencies)-1))
    is_decreasing = all(avg_latencies[i] >= avg_latencies[i+1] for i in range(len(avg_latencies)-1))
    
    if is_increasing:
        print("\n[OK] Latency increases consistently with quorum (expected behavior)")
    elif is_decreasing:
        print("\n[ERROR] Latency decreases with quorum (INVERTED - unexpected!)")
    else:
        print("\n[WARNING] Latency progression is non-monotonic (variable behavior)")
        print("  This suggests:")
        print("  - Delays may be too small relative to network overhead")
        print("  - Concurrent write queuing effects")
        print("  - System load variations between tests")
        print("  - Warm-up may not be sufficient")
    
    # Calculate differences
    print("\n" + "=" * 60)
    print("Latency Differences Between Quorums")
    print("=" * 60)
    for i in range(len(quorums) - 1):
        diff = avg_latencies[i+1] - avg_latencies[i]
        pct_change = (diff / avg_latencies[i] * 100) if avg_latencies[i] > 0 else 0
        print(f"Quorum {quorums[i]} -> {quorums[i+1]}: {diff:+.2f} ms ({pct_change:+.1f}%)")
    
    # Expected vs Actual
    print("\n" + "=" * 60)
    print("Expected vs Actual Behavior")
    print("=" * 60)
    print("\nExpected:")
    print("  - Quorum 1 should have LOWEST latency (waits for 1st fastest follower)")
    print("  - Quorum 5 should have HIGHEST latency (waits for 5th fastest follower)")
    print("  - Latency should increase monotonically from quorum 1 to 5")
    
    q1_lat = avg_latencies[0] if quorums[0] == 1 else None
    q5_lat = avg_latencies[-1] if quorums[-1] == 5 else None
    
    if q1_lat and q5_lat:
        if q1_lat < q5_lat:
            print(f"\n[OK] Actual: Quorum 1 ({q1_lat:.2f}ms) < Quorum 5 ({q5_lat:.2f}ms) - CORRECT")
        else:
            print(f"\n[ERROR] Actual: Quorum 1 ({q1_lat:.2f}ms) > Quorum 5 ({q5_lat:.2f}ms) - INVERTED!")
            print("\nPossible causes:")
            print("  1. Delays too small (MIN_DELAY/MAX_DELAY need to be larger)")
            print("  2. Cold-start overhead affecting quorum 1 more")
            print("  3. Concurrent write queuing causing follower 0 bottleneck")
            print("  4. Network/processing overhead dominating delay differences")
    
    print("\n" + "=" * 60)
    print("Recommendations")
    print("=" * 60)
    print("\nIf latency is inverted or variable:")
    print("  1. Increase MIN_DELAY and MAX_DELAY in docker-compose.yml")
    print("     (e.g., MIN_DELAY=0.05, MAX_DELAY=0.25 or larger)")
    print("  2. Ensure warm-up is sufficient (increase WARMUP_WRITES)")
    print("  3. Add settle periods between quorum tests")
    print("  4. Check for system load variations")
    print("  5. Verify delays are deterministic (no random component)")


if __name__ == "__main__":
    analyze_iterations()

