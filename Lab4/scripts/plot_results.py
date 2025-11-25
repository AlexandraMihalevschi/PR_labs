"""
Plot results from individual quorum benchmark JSON files located under results/.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"


def main():
    result_files = glob.glob(str(RESULTS_DIR / "results_quorum_*.json"))

    if not result_files:
        print("No result files found in results/ (results_quorum_*.json).")
        return

    results = {}
    for filename in result_files:
        try:
            with open(filename, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                results[data["quorum"]] = data
        except Exception as exc:
            print(f"Error loading {filename}: {exc}")

    if not results:
        print("No valid results found.")
        return

    quorums = sorted(results.keys())
    avg_latencies = [results[q]["avg_latency_ms"] for q in quorums]
    median_latencies = [results[q].get("median_latency_ms", 0) for q in quorums]
    p95_latencies = [results[q].get("p95_latency_ms", 0) for q in quorums]
    p99_latencies = [results[q].get("p99_latency_ms", 0) for q in quorums]

    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Plot all metrics
    ax.plot(quorums, avg_latencies, marker="o", linewidth=2, markersize=8, label="Average", color="blue")
    if any(median_latencies):  # Only plot if data exists
        ax.plot(quorums, median_latencies, marker="s", linewidth=2, markersize=7, label="Median", color="green")
    if any(p95_latencies):
        ax.plot(quorums, p95_latencies, marker="^", linewidth=2, markersize=7, label="P95", color="orange")
    if any(p99_latencies):
        ax.plot(quorums, p99_latencies, marker="d", linewidth=2, markersize=7, label="P99", color="red")
    
    ax.set_xlabel("Write Quorum", fontsize=12)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Write Quorum vs Latency Metrics\n(100 writes, 10 keys, 10 concurrent)", fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(quorums)
    ax.legend(loc="best", fontsize=10)
    
    # Add value labels for average (most important metric)
    for quorum, latency in zip(quorums, avg_latencies):
        ax.text(quorum, latency, f"{latency:.1f}", ha="center", va="bottom", fontsize=8, color="blue")

    output_path = RESULTS_DIR / "write_quorum_vs_latency.png"
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Plot saved to {output_path}")

    print("\nSummary:")
    for quorum in quorums:
        result = results[quorum]
        consistency = result.get("consistency", {}).get("all_consistent")
        consistency_flag = "OK" if consistency else "CHECK" if consistency is not None else "N/A"
        
        # Check for race conditions
        race_check = result.get("race_condition_check", {})
        race_flag = "OK" if race_check.get("all_consistent", True) else f"⚠️ {race_check.get('race_conditions_detected', 0)} issues"
        
        print(
            f"  Quorum {quorum}: "
            f"avg={result['avg_latency_ms']:.2f}ms, "
            f"median={result.get('median_latency_ms', 0):.2f}ms, "
            f"p95={result.get('p95_latency_ms', 0):.2f}ms, "
            f"p99={result.get('p99_latency_ms', 0):.2f}ms | "
            f"success={result['success_rate']*100:.1f}% | "
            f"consistency={consistency_flag} | "
            f"race_check={race_flag}"
        )


if __name__ == "__main__":
    main()
