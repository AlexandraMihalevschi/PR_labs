#!/usr/bin/env python3
"""
Helper script to run the single-quorum benchmark for quorum values 1..5.
Usage: python scripts/run_performance_tests.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TEST_SCRIPT = Path(__file__).resolve().parents[1] / "tests" / "test_single_quorum.py"


def main():
    print("Performance Testing Script")
    print("=" * 60)
    print("This will run ~100 writes (10 concurrent) for quorum values 1..5.")
    print("Make sure `docker compose up -d` is running before starting.\n")

    for quorum in [1, 2, 3, 4, 5]:
        print(f"\n=== Running benchmark for WRITE_QUORUM={quorum} ===")
        try:
            subprocess.run(
                [sys.executable, str(TEST_SCRIPT), str(quorum)],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"Benchmark failed for quorum={quorum}: {exc}")
            break

    print("\nAll benchmarks complete. Individual JSON files are saved in `results/`.") 

if __name__ == "__main__":
    main()

