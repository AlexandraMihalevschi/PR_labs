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

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(quorums, avg_latencies, marker="o", linewidth=2, markersize=8)
    ax.set_xlabel("Write Quorum", fontsize=12)
    ax.set_ylabel("Average Latency (ms)", fontsize=12)
    ax.set_title("Write Quorum vs Average Latency\n(100 writes, 10 keys, 10 concurrent)", fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(quorums)
    for quorum, latency in zip(quorums, avg_latencies):
        ax.text(quorum, latency, f"{latency:.2f} ms", ha="center", va="bottom", fontsize=9)

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
        print(
            f"  Quorum {quorum}: {result['avg_latency_ms']:.2f} ms avg, "
            f"{result['success_rate']*100:.1f}% success "
            f"({result['num_successful']} successful writes) "
            f"[consistency={consistency_flag}]"
        )


if __name__ == "__main__":
    main()
